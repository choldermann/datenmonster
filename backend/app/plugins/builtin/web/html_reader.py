import logging
from typing import List

import pandas as pd
import requests

from app.plugins.builtin.web.base import DocumentSourcePlugin

logger = logging.getLogger(__name__)


class HtmlDocumentSource(DocumentSourcePlugin):
    """
    HTML-Dokument / Webseite als Datenquelle.

    Extraktions-Modi:
      auto          – Tabellen bevorzugt, sonst Textzeilen
      tables        – HTML-Tabellen (pandas.read_html)
      links         – Alle Hyperlinks (<a href>)
      images        – Alle Bilder (<img>)
      lists         – Listenelemente (<ul>/<ol>)
      meta          – Meta-Tags der Seite
      css_selector  – Benutzerdefinierter CSS-Selektor oder Visual-Selektor-Konfig

    Visual-Selektor-Konfiguration (future, in visual_selector_config):
      {
        "row_selector": "div.product",   // optional: wiederkehrende Zeilen
        "selections": [
          {"field_name": "preis", "css_selector": "span.price", "transform": "text"},
          {"field_name": "titel", "css_selector": "h2.name",    "transform": "text"},
          {"field_name": "bild",  "css_selector": "img.main",   "transform": "attr:src"}
        ]
      }
    """

    id = "datenmonster-plugin-web-html"
    name = "HTML / Webseite"
    version = "1.0.0"
    description = "Lädt eine Webseite und extrahiert Tabellen, Links, Bilder oder beliebige Inhalte per CSS-Selektor."
    author = "Datenmonster"
    license = "free"
    capabilities = ["source"]

    source_type_id = "doc_html"
    source_type_label = "HTML / Webseite"
    source_type_icon = "globe"
    source_category = "document"

    config_schema: List[dict] = DocumentSourcePlugin._COMMON_CONFIG + [
        {
            "key": "extract_type",
            "label": "Extraktion",
            "type": "select",
            "options": ["auto", "produkte", "ki", "tables", "links", "images", "lists", "meta", "css_selector"],
            "option_labels": {
                "auto": "Automatisch (Tabelle, sonst Text)",
                "produkte": "Produkte – Preis, EAN, Verfügbarkeit (empfohlen für Shops)",
                "ki": "KI – frei wählbare Felder aus dem Seitentext (kostet KI-Guthaben)",
                "tables": "Tabelle", "links": "Links", "images": "Bilder", "lists": "Listen",
                "meta": "Meta-Angaben der Seite", "css_selector": "CSS-Selektor / Visueller Selektor",
            },
            "default": "auto",
            "description": "produkte = Name, Preis, EAN, Verfügbarkeit aus den Produktdaten der Shopseite "
                           "(JSON-LD/Microdata) – für Wettbewerbspreise die erste Wahl.",
        },
        {
            "key": "table_index",
            "label": "Tabellen-Index",
            "zeige_bei": {"extract_type": ["auto", "tables"]},
            "type": "number",
            "default": 0,
            "description": "Bei Modus 'tables': welche Tabelle (0 = erste)?",
        },
        {
            "key": "css_selector",
            "label": "CSS-Selektor",
            "zeige_bei": {"extract_type": ["css_selector"]},
            "type": "string",
            "placeholder": "table.products, div.item, #main-content",
            "description": "Nur bei Modus 'css_selector'. Leerlassen wenn Visual-Selektor genutzt wird.",
            "default": "",
        },
        {
            "key": "list_selector",
            "label": "Listen-Selektor (optional)",
            "zeige_bei": {"extract_type": ["lists"]},
            "type": "string",
            "placeholder": "ul.results",
            "default": "",
            "description": "Bei Modus 'lists': nur Listen innerhalb dieses Selektors extrahieren.",
        },
        {
            "key": "ki_felder",
            "label": "KI: gewünschte Felder",
            "zeige_bei": {"extract_type": ["ki"]},
            "type": "string",
            "placeholder": "name, preis, lieferzeit, verfuegbar",
            "default": "name, preis",
            "description": "Kommagetrennt. Ein Feld „preis“ wird für den Preisvergleich genutzt. "
                           "Nur Werte, die wörtlich auf der Seite stehen, werden übernommen. "
                           "Ein KI-Aufruf je Seite; unveränderte Seiten kosten beim nächsten Abruf nichts.",
        },
        {
            "key": "ki_hinweis",
            "label": "KI: Hinweis (optional)",
            "zeige_bei": {"extract_type": ["ki"]},
            "type": "string",
            "placeholder": "z.B. nur der Preis für 1 Stück, ohne Versand",
            "default": "",
        },
        # ── Viele Seiten ──────────────────────────────────────────────────────
        {
            "key": "urls",
            "label": "Weitere URLs (eine je Zeile)",
            "type": "code",
            "placeholder": "https://shop-a.de/artikel/123\nhttps://shop-b.de/p/456",
            "default": "",
            "description": "Zusätzlich zur URL oben. Jede Zeile wird abgerufen.",
        },
        {
            "key": "url_dataset_id",
            "label": "URLs aus Dataset (ID, optional)",
            "type": "number",
            "default": "",
            "description": "Z.B. eine Excel-Liste ArtNr ↔ Wettbewerber-URL. Die übrigen Spalten "
                           "(ArtNr …) kommen mit ins Ergebnis.",
        },
        {
            "key": "url_spalte",
            "label": "Spalte mit der URL",
            "type": "string",
            "default": "url",
        },
        {
            "key": "folge_links",
            "label": "Detail-Links folgen (CSS-Selektor, optional)",
            "type": "string",
            "placeholder": "a.product-link",
            "default": "",
            "description": "Auf Listenseiten: diese Links öffnen und dort auslesen (z.B. jedes Produkt).",
        },
        {
            "key": "weiter_selector",
            "label": "Blättern: „Weiter“-Link (CSS-Selektor, optional)",
            "type": "string",
            "placeholder": "a.next, a[rel=next]",
            "default": "",
            "description": "Alternativ {seite} in der URL, z.B. https://shop.de/kategorie?page={seite}",
        },
        {
            "key": "max_seiten",
            "label": "Höchstens Seiten je Start-URL",
            "type": "number",
            "default": 20,
        },
        # ── Rücksicht ─────────────────────────────────────────────────────────
        {
            "key": "pause_ms",
            "label": "Pause zwischen Abrufen (ms)",
            "type": "number",
            "default": 1500,
        },
        {
            "key": "max_abrufe",
            "label": "Höchstens Abrufe je Lauf",
            "type": "number",
            "default": 200,
        },
        {
            "key": "robots_beachten",
            "label": "robots.txt beachten",
            "type": "select",
            "options": ["ja", "nein"],
            "default": "ja",
            "description": "Nur für eigene Seiten abschalten.",
        },
        # ── Speichern & Vergleichen ───────────────────────────────────────────
        {
            "key": "verlauf",
            "label": "Verlauf führen",
            "type": "select",
            "options": ["nein", "ja"],
            "default": "nein",
            "description": "ja = jeder Abruf bleibt mit Zeitstempel erhalten; nein = nur der letzte Stand "
                           "(mit Vergleich zum vorigen: preis_vorher, aenderung_prozent, status).",
        },
        {
            "key": "verlauf_tage",
            "label": "Verlauf aufbewahren (Tage)",
            "zeige_bei": {"verlauf": ["ja"]},
            "type": "number",
            "default": 365,
            "description": "Ältere Abrufe werden beim nächsten Abruf gelöscht. 0 = unbegrenzt.",
        },
        {
            "key": "schluessel",
            "label": "Schlüssel für den Vergleich (Spalten, optional)",
            "type": "string",
            "placeholder": "quelle_url, gtin",
            "default": "",
            "description": "Woran ein Produkt beim nächsten Abruf wiedererkannt wird. "
                           "Leer = quelle_url + EAN/SKU/Name.",
        },
    ]

    # ── Kern-Implementierung ──────────────────────────────────────────────────

    def read(self, url: str, config: dict) -> pd.DataFrame:
        html = self._download(url, config)
        extract_type = config.get("extract_type") or "auto"

        extractors = {
            "tables":       self._extract_tables,
            "links":        self._extract_links,
            "images":       self._extract_images,
            "lists":        self._extract_lists,
            "meta":         self._extract_meta,
            "css_selector": self._extract_css_selector,
            "auto":         self._extract_auto,
        }

        extractor = extractors.get(extract_type, self._extract_auto)
        df = extractor(html, url, config)

        if df is None or df.empty:
            logger.warning(f"HtmlReader '{url}': keine Daten für Modus '{extract_type}'")
            return pd.DataFrame()

        return df

    # ── Download ──────────────────────────────────────────────────────────────

    def _download(self, url: str, config: dict) -> str:
        # SSRF-Schutz: die URL steht frei in der Quelle – ohne Prüfung wäre das
        # ein Weg ins interne Netz (Metadata, Loopback, Updater …), inkl. Redirects.
        from app.core.net_guard import guarded_request
        resp = guarded_request(
            requests.Session(), "GET", url,
            headers=self._build_headers(config),
            timeout=self._timeout(config),
            allow_redirects=True,
        )
        resp.raise_for_status()
        return resp.text

    # ── Extraktoren ───────────────────────────────────────────────────────────

    def _extract_auto(self, html: str, url: str, config: dict) -> pd.DataFrame:
        """Tabellen bevorzugt, sonst Text-Fallback."""
        try:
            from io import StringIO
            tables = pd.read_html(StringIO(html), flavor="lxml")
            if tables:
                idx = self._table_index(config, len(tables))
                logger.info(f"HtmlReader auto: {len(tables)} Tabelle(n) gefunden, nutze Index {idx}")
                return tables[idx]
        except Exception:
            pass

        # Fallback: Sichtbarer Text zeilenweise
        return self._extract_text_lines(html)

    def _extract_tables(self, html: str, url: str, config: dict) -> pd.DataFrame:
        try:
            from io import StringIO
            tables = pd.read_html(StringIO(html), flavor="lxml")
        except Exception as e:
            raise ValueError(f"Keine HTML-Tabellen gefunden: {e}")
        if not tables:
            raise ValueError("Seite enthält keine HTML-Tabellen (<table>).")
        idx = self._table_index(config, len(tables))
        logger.info(f"HtmlReader tables: {len(tables)} Tabelle(n), Index {idx}")
        return tables[idx]

    def _extract_links(self, html: str, url: str, config: dict) -> pd.DataFrame:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        rows = []
        for a in soup.find_all("a", href=True):
            href = a.get("href", "").strip()
            # Relative URLs auflösen
            if href and not href.startswith(("http://", "https://", "//", "#", "mailto:")):
                from urllib.parse import urljoin
                href = urljoin(url, href)
            rows.append({
                "href":  href,
                "text":  a.get_text(strip=True),
                "title": a.get("title", ""),
                "rel":   " ".join(a.get("rel", [])),
            })
        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["href", "text", "title", "rel"])

    def _extract_images(self, html: str, url: str, config: dict) -> pd.DataFrame:
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin
        soup = BeautifulSoup(html, "lxml")
        rows = []
        for img in soup.find_all("img"):
            src = img.get("src", "").strip()
            if src and not src.startswith(("http://", "https://", "//")):
                src = urljoin(url, src)
            rows.append({
                "src":    src,
                "alt":    img.get("alt", ""),
                "title":  img.get("title", ""),
                "width":  img.get("width", ""),
                "height": img.get("height", ""),
            })
        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["src", "alt", "title", "width", "height"])

    def _extract_lists(self, html: str, url: str, config: dict) -> pd.DataFrame:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        list_selector = (config.get("list_selector") or "").strip()
        if list_selector:
            scope = soup.select(list_selector) or [soup]
        else:
            scope = [soup]

        rows = []
        list_idx = 0
        for container in scope:
            for lst in container.find_all(["ul", "ol"]):
                list_type = lst.name
                for item_idx, li in enumerate(lst.find_all("li", recursive=False)):
                    rows.append({
                        "list_index": list_idx,
                        "list_type":  list_type,
                        "item_index": item_idx,
                        "text":       li.get_text(strip=True),
                    })
                list_idx += 1

        return pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=["list_index", "list_type", "item_index", "text"])

    def _extract_meta(self, html: str, url: str, config: dict) -> pd.DataFrame:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        rows = []

        # <title>
        if soup.title:
            rows.append({"name": "title", "property": "", "content": soup.title.get_text(strip=True)})

        for m in soup.find_all("meta"):
            name     = m.get("name", "")
            prop     = m.get("property", "")
            content  = m.get("content", "")
            http_eq  = m.get("http-equiv", "")
            if content or http_eq:
                rows.append({"name": name or http_eq, "property": prop, "content": content})

        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["name", "property", "content"])

    def _extract_css_selector(self, html: str, url: str, config: dict) -> pd.DataFrame:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")

        # Visual-Selektor-Konfiguration hat Priorität
        visual_cfg = config.get("visual_selector_config")
        if visual_cfg and isinstance(visual_cfg, dict) and visual_cfg.get("selections"):
            return self._extract_visual_selector(soup, visual_cfg)

        selector = (config.get("css_selector") or "").strip()
        if not selector:
            raise ValueError("css_selector-Modus benötigt einen CSS-Selektor oder eine Visual-Selektor-Konfiguration.")

        elements = soup.select(selector)
        if not elements:
            logger.warning(f"CSS-Selektor '{selector}' – keine Treffer")
            return pd.DataFrame(columns=["index", "text", "html"])

        rows = [
            {"index": i, "text": el.get_text(strip=True), "html": str(el)}
            for i, el in enumerate(elements)
        ]
        return pd.DataFrame(rows)

    # ── Visual-Selektor (v1: statisch, v2: interaktiv) ────────────────────────

    def _extract_visual_selector(self, soup, visual_cfg: dict) -> pd.DataFrame:
        """
        Extrahiert strukturierte Daten anhand einer Visual-Selektor-Konfiguration.

        row_selector (optional): CSS-Selektor für wiederholende Zeilen (z.B. "div.product").
        selections: Liste von Felddefinitionen mit field_name, css_selector, transform.

        Transform-Werte:
          text        – Sichtbarer Text (Standard)
          html        – Inner HTML
          attr:<name> – Wert eines Attributs, z.B. "attr:href" oder "attr:src"
        """
        selections = visual_cfg.get("selections", [])
        row_selector = (visual_cfg.get("row_selector") or "").strip()

        def _apply_transform(el, transform: str) -> str:
            if not el:
                return ""
            transform = (transform or "text").strip().lower()
            if transform == "text":
                return el.get_text(strip=True)
            if transform == "html":
                return str(el)
            if transform.startswith("attr:"):
                attr_name = transform[5:]
                return el.get(attr_name, "")
            return el.get_text(strip=True)

        if row_selector:
            containers = soup.select(row_selector)
            rows = []
            for container in containers:
                row = {}
                for sel in selections:
                    field = sel.get("field_name") or sel.get("css_selector", "?")
                    el = container.select_one(sel.get("css_selector", ""))
                    row[field] = _apply_transform(el, sel.get("transform", "text"))
                rows.append(row)
        else:
            # Ein einzelner Record aus der gesamten Seite
            row = {}
            for sel in selections:
                field = sel.get("field_name") or sel.get("css_selector", "?")
                el = soup.select_one(sel.get("css_selector", ""))
                row[field] = _apply_transform(el, sel.get("transform", "text"))
            rows = [row] if row else []

        if not rows:
            fields = [s.get("field_name", "?") for s in selections]
            return pd.DataFrame(columns=fields)
        return pd.DataFrame(rows)

    # ── Hilfsmethoden ─────────────────────────────────────────────────────────

    # ── Viele Seiten ──────────────────────────────────────────────────────────

    def _start_urls(self, config: dict):
        """[(url, zusatzspalten)] aus URL-Feld, URL-Liste und URL-Dataset."""
        starts = []
        haupt = (config.get("url") or "").strip()
        if haupt:
            starts.append((haupt, {}))
        for zeile in str(config.get("urls") or "").splitlines():
            z = zeile.strip()
            if z and not z.startswith("#"):
                starts.append((z, {}))
        ds_id = config.get("url_dataset_id")
        if ds_id not in (None, "", 0, "0"):
            from app.connectors.factory import get_connector
            df = get_connector(int(ds_id)).fetch_full()
            spalte = (config.get("url_spalte") or "url").strip()
            if spalte not in df.columns:
                raise ValueError(f"URL-Dataset #{ds_id}: Spalte „{spalte}“ fehlt "
                                 f"(vorhanden: {', '.join(map(str, df.columns))})")
            for row in df.to_dict("records"):
                u = str(row.get(spalte) or "").strip()
                if u.startswith("http"):
                    starts.append((u, {k: v for k, v in row.items() if k != spalte}))
        if not starts:
            raise ValueError("Keine URL angegeben (URL, weitere URLs oder URL-Dataset)")
        return starts

    def _extrahieren(self, html: str, url: str, config: dict) -> pd.DataFrame:
        art = config.get("extract_type") or "auto"
        if art == "produkte":
            from app.plugins.builtin.web.produktdaten import produkte_aus_html, SPALTEN
            zeilen = produkte_aus_html(html, url)
            return pd.DataFrame(zeilen, columns=SPALTEN) if zeilen else pd.DataFrame()
        if art == "ki":
            from app.plugins.builtin.web.ki_extraktion import ki_extrahieren
            felder = [f.strip() for f in str(config.get("ki_felder") or "name, preis").split(",")]
            zeilen = ki_extrahieren(html, felder, str(config.get("ki_hinweis") or ""))
            return pd.DataFrame(zeilen, columns=[f for f in felder if f]) if zeilen else pd.DataFrame()
        extractors = {
            "tables": self._extract_tables, "links": self._extract_links,
            "images": self._extract_images, "lists": self._extract_lists,
            "meta": self._extract_meta, "css_selector": self._extract_css_selector,
            "auto": self._extract_auto,
        }
        try:
            df = extractors.get(art, self._extract_auto)(html, url, config)
        except ValueError:
            return pd.DataFrame()
        if art in ("tables", "auto"):
            df = tabelle_saeubern(df)
        return df if df is not None else pd.DataFrame()

    def abrufen(self, config: dict):
        """Alle Seiten abrufen. → (DataFrame, info) mit info = {abrufe, fehler, uebersprungen}.
        config["limit"] begrenzt für die Vorschau Zeilen und Abrufe."""
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin
        from app.plugins.builtin.web.abruf import Abrufer, AbrufGrenze

        limit = config.get("limit")
        vorschau = bool(limit)
        abrufer = Abrufer(
            self._build_headers(config), timeout=self._timeout(config),
            pause_ms=min(int(config.get("pause_ms") or 1500), 300) if vorschau else (
                config.get("pause_ms") if config.get("pause_ms") not in (None, "") else 1500),
            max_abrufe=5 if vorschau else (config.get("max_abrufe") or 200),
            robots_beachten=str(config.get("robots_beachten", "ja")).lower() not in ("nein", "false", "0"),
        )
        folge = (config.get("folge_links") or "").strip()
        weiter = (config.get("weiter_selector") or "").strip()
        try:
            max_seiten = int(config.get("max_seiten") or 20)
        except (TypeError, ValueError):
            max_seiten = 20

        teile, fehler = [], []
        anzahl = 0

        def sammeln(df, url, extra):
            nonlocal anzahl
            if df is None or df.empty:
                return 0
            df = df.copy()
            df.insert(0, "quelle_url", url)
            for k, v in extra.items():
                df[k if k not in df.columns else f"{k}_liste"] = v
            teile.append(df)
            anzahl += len(df)
            return len(df)

        try:
            for start, extra in self._start_urls(config):
                blaettern = "{seite}" in start
                url = start.replace("{seite}", "1")
                gesehen, n = set(), 1
                while url:
                    if limit and anzahl >= int(limit):
                        raise AbrufGrenze("Vorschau voll")
                    try:
                        html = abrufer.holen(url)
                    except AbrufGrenze:
                        raise
                    except Exception as e:
                        fehler.append(f"{url}: {str(e)[:150]}")
                        break
                    if html is None:   # robots.txt
                        break
                    links = []
                    if folge:
                        for a in BeautifulSoup(html, "lxml").select(folge):
                            href = a.get("href")
                            if href:
                                voll = urljoin(url, href)
                                if voll not in links:
                                    links.append(voll)
                    if links:   # Listenseite → Detailseiten; sonst die Seite selbst
                        neu = 0
                        for link in links:
                            if limit and anzahl >= int(limit):
                                raise AbrufGrenze("Vorschau voll")
                            try:
                                h = abrufer.holen(link)
                            except AbrufGrenze:
                                raise
                            except Exception as e:
                                fehler.append(f"{link}: {str(e)[:150]}")
                                continue
                            if h is not None:
                                neu += sammeln(self._extrahieren(h, link, config), link, extra)
                        signatur = tuple(links)
                    else:
                        df = self._extrahieren(html, url, config)
                        neu = sammeln(df, url, extra)
                        signatur = tuple(map(tuple, df.astype(str).values.tolist())) if neu else ()
                    # Ende des Blätterns: leere Seite oder dieselbe Seite noch einmal
                    if not neu or signatur in gesehen:
                        break
                    gesehen.add(signatur)
                    n += 1
                    if n > max_seiten:
                        break
                    if blaettern:
                        url = start.replace("{seite}", str(n))
                    elif weiter:
                        el = BeautifulSoup(html, "lxml").select_one(weiter)
                        url = urljoin(url, el["href"]) if el is not None and el.get("href") else None
                    else:
                        url = None
        except AbrufGrenze as e:
            if not vorschau:
                fehler.append(str(e))

        df = pd.concat(teile, ignore_index=True) if teile else pd.DataFrame()
        if limit:
            df = df.head(int(limit))
        return df, {"abrufe": abrufer.abrufe, "fehler": fehler,
                    "uebersprungen": [f"{u}: {g}" for u, g in abrufer.uebersprungen]}

    def fetch(self, config: dict):
        if config.get("render_mode") == "browser":
            raise NotImplementedError("Browser-Modus (Playwright) ist noch nicht verfügbar.")
        df, info = self.abrufen(config)
        if df.empty and (info["fehler"] or info["uebersprungen"]):
            raise ValueError("; ".join((info["fehler"] + info["uebersprungen"])[:3]))
        df = df.astype(str).replace("nan", "").replace("None", "")
        return df.to_dict("records")

    def test_connection(self, config: dict) -> dict:
        url = (config.get("url") or "").strip().replace("{seite}", "1")
        if not url:
            starts = self._start_urls(config)
            url = starts[0][0]
        return super().test_connection(dict(config, url=url))

    def _table_index(self, config: dict, total: int) -> int:
        try:
            idx = int(config.get("table_index") or 0)
        except (ValueError, TypeError):
            idx = 0
        return max(0, min(idx, total - 1))

    def _extract_text_lines(self, html: str) -> pd.DataFrame:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        # Script/Style entfernen
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        return pd.DataFrame({"text": lines})


def tabelle_saeubern(df: pd.DataFrame) -> pd.DataFrame:
    """Tabellen aus Webseiten lesbar machen: mehrzeilige Kopfzeilen zu einem Namen,
    Fußnoten-Marker [3] und geschützte Leerzeichen raus."""
    import re
    if df is None or df.empty:
        return df
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        namen = []
        for teile in df.columns:
            t = []
            for x in teile:
                x = str(x)
                if x.startswith("Unnamed") or x in t:
                    continue
                t.append(x)
            namen.append(" ".join(t))
        df.columns = namen
    fussnote = re.compile(r"\[\s*[\w\s]{1,6}\]")
    def rein(v):
        if isinstance(v, str):
            return fussnote.sub("", v.replace("\xa0", " ")).strip()
        return v
    df.columns = [rein(str(c)) for c in df.columns]
    # doppelte Spaltennamen eindeutig machen
    gesehen = {}
    neu = []
    for c in df.columns:
        if c in gesehen:
            gesehen[c] += 1
            neu.append(f"{c}_{gesehen[c]}")
        else:
            gesehen[c] = 1
            neu.append(c)
    df.columns = neu
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].map(rein)
    return df
