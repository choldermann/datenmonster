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
            "options": ["auto", "tables", "links", "images", "lists", "meta", "css_selector"],
            "default": "auto",
            "description": "Welche Daten sollen aus der Seite extrahiert werden?",
        },
        {
            "key": "table_index",
            "label": "Tabellen-Index",
            "type": "number",
            "default": 0,
            "description": "Bei Modus 'tables': welche Tabelle (0 = erste)?",
        },
        {
            "key": "css_selector",
            "label": "CSS-Selektor",
            "type": "string",
            "placeholder": "table.products, div.item, #main-content",
            "description": "Nur bei Modus 'css_selector'. Leerlassen wenn Visual-Selektor genutzt wird.",
            "default": "",
        },
        {
            "key": "list_selector",
            "label": "Listen-Selektor (optional)",
            "type": "string",
            "placeholder": "ul.results",
            "default": "",
            "description": "Bei Modus 'lists': nur Listen innerhalb dieses Selektors extrahieren.",
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
        resp = requests.get(
            url,
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
