"""
Produktdaten aus Shop-Seiten – ohne Klick-Selektoren.

Fast jeder Shop liefert Name, Preis, Verfügbarkeit, EAN usw. maschinenlesbar mit,
weil Google es für die Suchergebnisse auswertet (schema.org/Product):
  1. JSON-LD   <script type="application/ld+json"> … "@type": "Product" …
  2. Microdata itemscope itemtype="…schema.org/Product" + itemprop="price" …
  3. OpenGraph <meta property="product:price:amount"> (Rückfall, nur Preis/Name)

Das ist robuster als CSS-Selektoren: Layout-Änderungen des Shops lassen es kalt.
"""
import json
import re
from typing import List, Optional

from bs4 import BeautifulSoup

SPALTEN = ["name", "preis", "waehrung", "verfuegbar", "gtin", "sku", "mpn", "marke",
           "bild", "produkt_url", "quelle_daten"]


def _text(v) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, list):
        v = v[0] if v else None
        return _text(v)
    if isinstance(v, dict):
        return _text(v.get("name") or v.get("@id") or v.get("url") or v.get("contentUrl"))
    s = str(v).strip()
    return s or None


def preis_zahl(v) -> Optional[float]:
    """„1.234,56 €“, „1,234.56“, „19.99“, 19.99 → float."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d,.\-]", "", str(v))
    if not s:
        return None
    if "," in s and "." in s:
        # das letzte Trennzeichen ist das Dezimalzeichen
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".") if len(s.split(",")[-1]) != 3 else s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _verfuegbar(v) -> Optional[str]:
    t = _text(v)
    if not t:
        return None
    t = t.rsplit("/", 1)[-1]  # https://schema.org/InStock → InStock
    return {"InStock": "lieferbar", "OutOfStock": "nicht lieferbar", "PreOrder": "Vorbestellung",
            "BackOrder": "nachbestellt", "LimitedAvailability": "begrenzt", "SoldOut": "ausverkauft",
            "Discontinued": "ausgelaufen", "InStoreOnly": "nur im Laden",
            "OnlineOnly": "nur online"}.get(t, t)


def _typen(obj) -> List[str]:
    t = obj.get("@type") if isinstance(obj, dict) else None
    if isinstance(t, list):
        return [str(x) for x in t]
    return [str(t)] if t else []


def _alle_objekte(daten):
    """Alle Objekte aus JSON-LD – auch in @graph, Listen und verschachtelt."""
    if isinstance(daten, list):
        for d in daten:
            yield from _alle_objekte(d)
    elif isinstance(daten, dict):
        yield daten
        for k in ("@graph", "itemListElement", "item", "mainEntity", "hasVariant"):
            if k in daten:
                yield from _alle_objekte(daten[k])


def _angebot(offers) -> dict:
    """Offer / AggregateOffer / Liste von Offers → günstigstes Angebot."""
    kandidaten = []
    for o in (offers if isinstance(offers, list) else [offers]):
        if not isinstance(o, dict):
            continue
        if "AggregateOffer" in _typen(o) or ("lowPrice" in o and "price" not in o):
            p = preis_zahl(o.get("lowPrice") if o.get("lowPrice") is not None else o.get("price"))
            kandidaten.append({"preis": p, "waehrung": _text(o.get("priceCurrency")),
                               "verfuegbar": _verfuegbar(o.get("availability"))})
            if o.get("offers"):
                kandidaten.append(_angebot(o["offers"]))
            continue
        preis = o.get("price")
        if preis is None and isinstance(o.get("priceSpecification"), (dict, list)):
            spec = o["priceSpecification"]
            spec = spec[0] if isinstance(spec, list) and spec else spec
            if isinstance(spec, dict):
                preis = spec.get("price")
        kandidaten.append({"preis": preis_zahl(preis), "waehrung": _text(o.get("priceCurrency")),
                           "verfuegbar": _verfuegbar(o.get("availability"))})
    mit_preis = [k for k in kandidaten if k.get("preis") is not None]
    if mit_preis:
        return min(mit_preis, key=lambda k: k["preis"])
    return kandidaten[0] if kandidaten else {}


def _gtin(o: dict) -> Optional[str]:
    for k in ("gtin13", "gtin", "gtin14", "gtin12", "gtin8", "ean", "isbn"):
        v = _text(o.get(k))
        if v:
            return re.sub(r"\D", "", v) or v
    return None


def _aus_jsonld(soup, seiten_url: str) -> List[dict]:
    zeilen = []
    for tag in soup.find_all("script", type=lambda t: t and "ld+json" in t.lower()):
        roh = tag.string or tag.get_text() or ""
        try:
            daten = json.loads(roh)
        except json.JSONDecodeError:
            # manche Shops hängen Kommentare/Kommata an – einmal entschärft probieren
            try:
                daten = json.loads(re.sub(r",\s*([}\]])", r"\1", roh.strip().rstrip(";")))
            except json.JSONDecodeError:
                continue
        for o in _alle_objekte(daten):
            typen = _typen(o)
            if not any(t in ("Product", "ProductGroup", "IndividualProduct", "Vehicle", "Book")
                       for t in typen):
                continue
            a = _angebot(o.get("offers")) if o.get("offers") else {}
            zeilen.append({
                "name": _text(o.get("name")),
                "preis": a.get("preis"),
                "waehrung": a.get("waehrung"),
                "verfuegbar": a.get("verfuegbar"),
                "gtin": _gtin(o),
                "sku": _text(o.get("sku")),
                "mpn": _text(o.get("mpn")),
                "marke": _text(o.get("brand")),
                "bild": _text(o.get("image")),
                "produkt_url": _text(o.get("url")) or seiten_url,
                "quelle_daten": "json-ld",
            })
    # ProductGroup ohne Preis neben Varianten mit Preis: nur die mit Preis behalten
    mit_preis = [z for z in zeilen if z["preis"] is not None]
    return mit_preis or zeilen


def _itemprop(scope, name):
    el = scope.find(attrs={"itemprop": name})
    if el is None:
        return None
    for attr in ("content", "href", "src", "value"):
        if el.get(attr):
            return el.get(attr)
    return el.get_text(" ", strip=True)


def _aus_microdata(soup, seiten_url: str) -> List[dict]:
    zeilen = []
    for scope in soup.find_all(attrs={"itemtype": re.compile(r"schema\.org/Product", re.I)}):
        angebot = scope.find(attrs={"itemtype": re.compile(r"schema\.org/(Aggregate)?Offer", re.I)}) or scope
        preis = _itemprop(angebot, "price") or _itemprop(angebot, "lowPrice")
        zeilen.append({
            "name": _itemprop(scope, "name"),
            "preis": preis_zahl(preis),
            "waehrung": _itemprop(angebot, "priceCurrency"),
            "verfuegbar": _verfuegbar(_itemprop(angebot, "availability")),
            "gtin": next((re.sub(r"\D", "", v) for k in ("gtin13", "gtin", "gtin14", "gtin12", "gtin8")
                          if (v := _itemprop(scope, k))), None),
            "sku": _itemprop(scope, "sku"),
            "mpn": _itemprop(scope, "mpn"),
            "marke": _itemprop(scope, "brand"),
            "bild": _itemprop(scope, "image"),
            "produkt_url": _itemprop(scope, "url") or seiten_url,
            "quelle_daten": "microdata",
        })
    return zeilen


def _aus_opengraph(soup, seiten_url: str) -> List[dict]:
    def meta(*namen):
        for n in namen:
            el = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
            if el and el.get("content"):
                return el["content"]
        return None

    preis = meta("product:price:amount", "og:price:amount")
    if preis is None:
        return []
    return [{
        "name": meta("og:title"),
        "preis": preis_zahl(preis),
        "waehrung": meta("product:price:currency", "og:price:currency"),
        "verfuegbar": _verfuegbar(meta("product:availability", "og:availability")),
        "gtin": None, "sku": meta("product:retailer_item_id"), "mpn": None,
        "marke": meta("product:brand"),
        "bild": meta("og:image"),
        "produkt_url": meta("og:url") or seiten_url,
        "quelle_daten": "opengraph",
    }]


def produkte_aus_html(html: str, seiten_url: str) -> List[dict]:
    soup = BeautifulSoup(html, "lxml")
    for verfahren in (_aus_jsonld, _aus_microdata, _aus_opengraph):
        zeilen = verfahren(soup, seiten_url)
        if zeilen:
            return zeilen
    return []
