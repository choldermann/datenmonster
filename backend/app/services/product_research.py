"""
Herstellerdaten zu einem Artikel nachschlagen (Pilot: Deiss, Denios).

Bewusst KEINE Suchmaschine: Suchmaschinen-Trefferseiten auszulesen verstößt gegen
deren Nutzungsbedingungen, wird bei Serienabfragen blockiert und trifft ohne
eindeutige Nummer oft das falsche Produkt. Stattdessen der exakte Weg:

  1. Produkt-Sitemap des Herstellers laden (die weisen sie selbst aus)
  2. Hersteller-Artikelnummer (HAN) in der Produktadresse wiederfinden
  3. genau diese eine Produktseite abrufen und die technischen Daten auslesen

Damit ist die Zuordnung eindeutig statt geraten. robots.txt wird vor jedem Abruf
geprüft; der Sitemap-Index wird zwischengespeichert, damit je Beschreibung nur
ein einziger Seitenabruf anfällt.
"""
from __future__ import annotations

import html
import logging
import re
import time
import urllib.robotparser
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

USER_AGENT = "DatenmonsterBot/1.0 (+https://datenmonster.monstersuite.de)"
TIMEOUT = 20
SITEMAP_TTL = 24 * 3600          # Produktlisten ändern sich selten
_sitemap_cache: dict[str, tuple[float, dict[str, str]]] = {}
_robots_cache: dict[str, tuple[float, urllib.robotparser.RobotFileParser]] = {}

# Je Hersteller: woran erkennen, wo die Sitemap liegt, wie die Nummer in der
# Adresse steht. Neue Hersteller sind reine Konfiguration – solange ihre Seite
# demselben Muster folgt (Sitemap + Nummer in der URL).
HERSTELLER = [
    {
        "id": "deiss",
        "muster": r"deiss",
        "name": "Emil Deiss KG",
        "sitemaps": ["https://www.deiss.de/sitemap.xml?sitemap=products"],
        # .../produkte/muellsaecke-blau-20304/
        "nummer_aus_url": r"-(\d+)/?$",
    },
    {
        "id": "denios",
        "muster": r"denios",
        "name": "DENIOS SE",
        "sitemaps": [
            "https://www.denios.de/sitemaps/de/products.xml",
            "https://www.denios.de/sitemaps/de/products_2.xml",
            "https://www.denios.de/sitemaps/de/products_3.xml",
            "https://www.denios.de/sitemaps/de/products_4.xml",
        ],
        # .../regalwanne-…-201373/201373
        "nummer_aus_url": r"/(\d+)/?$",
    },
    {
        # Rhenus führt im HAN-Feld den Produktnamen statt einer Nummer, und die
        # Produktadresse ist dieser Name als Slug. Zuordnung deshalb über den
        # Namen. Die Seiten haben keine Wertetabelle, sondern Textabschnitte —
        # und keine EANs (Schmierstoffe werden nach Gewicht verkauft).
        "id": "rhenus",
        "muster": r"rhenus",
        "name": "Rhenus Lub GmbH & Co. KG",
        "sitemaps": ["https://www.rhenuslub.de/product-sitemap.xml"],
        "zuordnung": "name",
        "slug_aus_url": r"/produkt/([^/]+)/?$",
        "slug_praefix": "rhenus-",
        "abschnitte": ["Anwendung", "Vorteile", "Eigenschaften", "Hinweise"],
    },
]

# Überschriften, die einen Textabschnitt beenden (Seitengerüst statt Inhalt)
_ABSCHNITT_ENDE = re.compile(
    r"^(downloads?|sicherheitsdatenblatt|kontakt|newsletter|impressum|datenschutz|"
    r"ähnliche produkte|produktfinder|weitere produkte|technisches merkblatt|"
    r"jetzt anfragen|zum produkt)$", re.I)

# Zeilen der technischen Daten, die als Beschriftung gelten
_LABEL = re.compile(r"^[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß0-9 .\-/()\[\]²³%]{1,44}:$")
# Beschriftung ohne Doppelpunkt, z.B. „Auffangvolumen [l]“ oder „Werkstoff“
_LABEL_OHNE_DOPPELPUNKT = re.compile(
    r"^[A-ZÄÖÜ][A-Za-zÄÖÜäöüß./-]*(?: [A-Za-zÄÖÜäöüß0-9./-]+){0,4}(?: \[[^\]]{1,8}\])?$")
# Zeilen, die nach einer Maß-/Mengenangabe aussehen
_WERT = re.compile(r"\d\s*(mm|cm|m\b|l\b|liter|µm|my|kg|g\b|stk|stück|%|x\s*\d)", re.I)
_STOPP = re.compile(r"^(downloads?|dateiname|merkliste|vergleichen|kontakt|newsletter|"
                    r"cookie|impressum|datenschutz|zum produkt|produkt anfragen|"
                    r"kundenbewertungen|ähnliche produkte|sie haben fragen.*|"
                    r"in den warenkorb|ihre vorteile|andere kauften auch)$", re.I)
# Rein gliedernde Zeilen – nie Beschriftung und nie Wert
_UEBERSCHRIFT = re.compile(r"^(details|technische daten|produktinformationen|neu|sale|"
                           r"bestseller|drucken|merken|weiterleiten|dibt)$", re.I)


def hersteller_profil(name: str) -> dict | None:
    """Passendes Profil zu einem Herstellernamen aus der Wawi finden."""
    if not name:
        return None
    n = name.lower()
    for p in HERSTELLER:
        if re.search(p["muster"], n):
            return p
    return None


def _robots_erlaubt(url: str) -> bool:
    """robots.txt der Domain prüfen (zwischengespeichert). Im Zweifel: nein."""
    teile = urlparse(url)
    basis = f"{teile.scheme}://{teile.netloc}"
    eintrag = _robots_cache.get(basis)
    if not eintrag or time.time() - eintrag[0] > SITEMAP_TTL:
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(f"{basis}/robots.txt")
        try:
            r = requests.get(f"{basis}/robots.txt", timeout=TIMEOUT,
                             headers={"User-Agent": USER_AGENT})
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except Exception as e:
            logger.warning("robots.txt von %s nicht abrufbar: %s", basis, e)
            return False
        _robots_cache[basis] = (time.time(), rp)
        eintrag = _robots_cache[basis]
    try:
        return eintrag[1].can_fetch(USER_AGENT, url)
    except Exception:
        return False


def _hole(url: str) -> str | None:
    if not _robots_erlaubt(url):
        logger.info("robots.txt verbietet %s", url)
        return None
    try:
        r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
        if r.status_code != 200:
            return None
        return r.text
    except Exception as e:
        logger.warning("Abruf fehlgeschlagen (%s): %s", url, e)
        return None


def _slug(text: str) -> str:
    """Produktnamen auf einen vergleichbaren Adressteil bringen."""
    s = re.sub(r"\(.*?\)", "", (text or "").lower().strip())   # Klammerzusätze weg
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _sitemap_index(profil: dict) -> dict[str, str]:
    """{Schlüssel: Produktadresse} für einen Hersteller, zwischengespeichert.

    Schlüssel ist je nach Hersteller die Artikelnummer aus der Adresse oder —
    wo im HAN-Feld ein Produktname steht — der Adress-Slug.
    """
    eintrag = _sitemap_cache.get(profil["id"])
    if eintrag and time.time() - eintrag[0] < SITEMAP_TTL:
        return eintrag[1]

    per_name = profil.get("zuordnung") == "name"
    muster = re.compile(profil["slug_aus_url"] if per_name else profil["nummer_aus_url"])
    index: dict[str, str] = {}
    for sm in profil["sitemaps"]:
        text = _hole(sm)
        if not text:
            continue
        for url in re.findall(r"<loc>([^<]+)</loc>", text):
            url = html.unescape(url.strip())
            # Fremdsprachige Ausgaben derselben Seite überspringen
            if re.search(r"/(en|es|nl|it|fr|pl|cs|hu)/", url):
                continue
            m = muster.search(url)
            if m:
                index.setdefault(m.group(1).lower() if per_name
                                 else m.group(1).lstrip("0"), url)
    _sitemap_cache[profil["id"]] = (time.time(), index)
    logger.info("Sitemap %s: %d Produktseiten indiziert", profil["id"], len(index))
    return index


def _seitentext(html_text: str) -> list[str]:
    """Sichtbaren Text als Zeilenliste – ohne Skripte, ohne Dubletten."""
    s = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html_text, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "\n", s))
    # Weiche Trennzeichen zerlegen Wörter („Lebensmittel­unbedenklich“) und
    # brachten die Beschriftung/Wert-Zuordnung durcheinander.
    text = text.replace("­", "").replace("​", "")
    zeilen, gesehen = [], set()
    for z in (x.strip() for x in text.splitlines()):
        if z and z not in gesehen and len(z) < 400:
            gesehen.add(z)
            zeilen.append(z)
    return zeilen


def _daten_auslesen(zeilen: list[str], nummer: str) -> tuple[dict, list[str]]:
    """Beschriftung/Wert-Paare der technischen Daten plus auffällige Maßangaben.

    Absichtlich textbasiert statt über CSS-Auswahl: die Seitenstruktur ändert
    sich häufiger als die Beschriftungen. Zwei Schreibweisen kommen vor:
    'Material:' + Wert in der nächsten Zeile (Deiss) und 'Werkstoff' + Wert
    ohne Doppelpunkt (Denios).
    """
    daten: dict[str, str] = {}
    masse: list[str] = []

    start = 0
    for i, z in enumerate(zeilen):
        if re.fullmatch(r"technische daten", z, re.I):
            start = i + 1
            break

    def brauchbar(wert: str) -> bool:
        return bool(wert) and len(wert) < 120 and not _STOPP.match(wert) \
            and not _UEBERSCHRIFT.match(wert)

    i = start
    while i < len(zeilen) - 1:
        z, wert = zeilen[i], zeilen[i + 1]
        if _STOPP.match(z):
            break
        if _UEBERSCHRIFT.match(z):
            i += 1
            continue
        if _LABEL.match(z):                       # „Material:“
            if brauchbar(wert) and not _LABEL.match(wert):
                daten.setdefault(z.rstrip(":").strip(), wert)
                i += 2
                continue
        elif _LABEL_OHNE_DOPPELPUNKT.match(z):    # „Werkstoff“ + Wert
            if brauchbar(wert) and not _LABEL_OHNE_DOPPELPUNKT.match(wert):
                daten.setdefault(z.strip(), wert)
                i += 2
                continue
        if _WERT.search(z) and len(z) < 90 and z not in masse:
            masse.append(z)
        i += 1

    daten.pop("Artikel-Nr.", None)   # kennen wir bereits
    daten.pop("Artikelnummer", None)
    return dict(list(daten.items())[:20]), masse[:12]


def _abschnitte_auslesen(zeilen: list[str], ueberschriften: list[str]) -> dict:
    """Textabschnitte unter bekannten Überschriften einsammeln.

    Für Hersteller ohne Wertetabelle (Rhenus: „Anwendung“, „Vorteile“). Die
    Zeilen sind Rohmaterial für die KI — sie soll daraus eigenständig
    formulieren, nicht abschreiben (fremde Produkttexte sind geschützt).
    """
    if not ueberschriften:
        return {}
    gesucht = {u.lower(): u for u in ueberschriften}
    ergebnis: dict[str, list[str]] = {}
    aktuell = None
    for z in zeilen:
        k = z.strip().lower().rstrip(":")
        if k in gesucht:
            aktuell = gesucht[k]
            ergebnis.setdefault(aktuell, [])
            continue
        if aktuell is None:
            continue
        if _ABSCHNITT_ENDE.match(z) or k in gesucht:
            aktuell = None
            continue
        if len(ergebnis[aktuell]) >= 8:      # ein Abschnitt reicht knapp
            aktuell = None
            continue
        if 3 < len(z) < 300:
            ergebnis[aktuell].append(z)
    return {k: v for k, v in ergebnis.items() if v}


def recherchiere(hersteller: str, han: str) -> dict | None:
    """Herstellerdaten zu einer HAN suchen.

    Gibt None zurück, wenn der Hersteller nicht unterstützt wird, die Nummer
    nicht in der Sitemap steht oder die Seite nichts hergibt — der Aufrufer
    arbeitet dann einfach ohne Recherche weiter.
    """
    profil = hersteller_profil(hersteller or "")
    if not profil:
        return None
    roh = str(han or "").strip()
    if not roh:
        return None

    index = _sitemap_index(profil)
    if profil.get("zuordnung") == "name":
        s = _slug(roh)
        praefix = profil.get("slug_praefix", "")
        url = index.get(s) or (index.get(praefix + s) if praefix and not s.startswith(praefix)
                               else None)
    else:
        url = index.get(roh.lstrip("0"))
    if not url:
        return None

    seite = _hole(url)
    if not seite:
        return None

    zeilen = _seitentext(seite)
    daten, masse = _daten_auslesen(zeilen, roh)
    abschnitte = _abschnitte_auslesen(zeilen, profil.get("abschnitte") or [])
    if not daten and not masse and not abschnitte:
        return None
    return {
        "hersteller": profil["name"],
        "url": url,
        "daten": daten,
        "angaben": masse,
        "abschnitte": abschnitte,
    }


def unterstuetzt(hersteller: str) -> bool:
    """Gibt es für diesen Hersteller überhaupt einen Adapter?"""
    return hersteller_profil(hersteller or "") is not None
