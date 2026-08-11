"""
Deterministische Antwort-Analyse für das API Studio.

Zwei Grundsätze:

1. **Erst rechnen, dann fragen.** Struktur, Typen, Datenpfade und Paginierungs-
   Hinweise lassen sich exakt aus der Antwort ableiten – dafür braucht es kein
   Sprachmodell. Das ist sofort da, kostet nichts und kann nicht halluzinieren.
   Die KI bekommt anschließend nur das verdichtete Inventar zu sehen.

2. **Was zur KI geht, verlässt möglicherweise diese Maschine.** Läuft der
   Gateway-Provider, landen Auszüge bei einem fremden Anbieter. Deshalb werden
   Beispielwerte grundsätzlich maskiert; echte Werte gibt es nur, wenn der
   Nutzer das für diese eine Analyse ausdrücklich einschaltet.

Die Typ-Erkennung arbeitet auf den echten Daten – maskiert wird erst das, was
als Beispiel herausgereicht wird. So bleibt die Analyse exakt und trotzdem dicht.
"""

import re
from typing import Any, Optional

# ── Schlüssel, deren Wert nie im Klartext herausgeht ──────────────────────────
GEHEIM_SCHLUESSEL = {
    "token", "secret", "password", "passwort", "pwd", "pass", "apikey",
    "api_key", "apitoken", "auth", "authorization", "credential", "credentials",
    "signature", "sign", "session", "sessionid", "cookie", "privatekey",
    "clientsecret", "refreshtoken", "accesstoken", "bearer", "otp", "pin",
}

# Schlüssel, die eindeutig auf personenbezogene Daten zeigen. Bewusst eng
# gehalten: „name" steckt auch in Artikelnamen, „adresse" nicht.
PII_SCHLUESSEL = {
    "email", "mail", "emailadresse", "telefon", "phone", "tel", "mobil",
    "mobile", "handy", "fax", "iban", "bic", "kontonummer", "ssn",
    "sozialversicherungsnummer", "steuernummer", "ustid", "vatid",
    "geburtsdatum", "birthdate", "geburtstag", "vorname", "nachname",
    "firstname", "lastname", "surname", "familienname",
    "strasse", "street", "hausnummer", "adresse", "address", "anschrift",
}

# ── Wertmuster, die immer maskiert werden – unabhängig vom Feldnamen ──────────
MUSTER = [
    ("email",    re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)),
    ("jwt",      re.compile(r"^ey[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.")),
    ("iban",     re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$")),
    ("uuid",     re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)),
    ("telefon",  re.compile(r"^[+(]?[\d][\d\s()/.-]{7,}\d$")),
    ("kreditkarte", re.compile(r"^\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{3,4}$")),
    ("datumzeit", re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")),
    ("datum",    re.compile(r"^\d{4}-\d{2}-\d{2}$")),
    ("url",      re.compile(r"^https?://", re.I)),
]

# Lange, zufällig aussehende Zeichenketten sind fast immer Schlüssel oder Tokens.
_ZUFALL = re.compile(r"^[A-Za-z0-9+/_=-]{28,}$")

# Kurze, offensichtlich unkritische Werte, die auch im sicheren Modus stehen
# bleiben – sie tragen die eigentliche Information für die Schema-Erkennung.
_UNBEDENKLICH = re.compile(r"^[A-Za-z0-9_.\-/ ]{0,24}$")

MAX_DATENSAETZE = 200      # so viele Datensätze fließen in das Inventar
MAX_FELDER      = 250      # Deckel gegen absurd breite Antworten
MAX_TIEFE       = 8


def _schluessel_teile(name: str) -> list:
    """Feldnamen in Wortteile zerlegen: `customer_apiKey` → [customer, api, key]."""
    if not name:
        return []
    mit_luecken = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(name))
    return [t for t in re.split(r"[^A-Za-z0-9]+", mit_luecken.lower()) if t]


def _kompakt(name: str) -> str:
    """Feldname ohne Trennzeichen: `first_name` → `firstname`.

    Unverzichtbar, weil sonst jede zusammengesetzte Schreibweise durchrutscht:
    `first_name` zerfällt in `first` + `name`, und weder das eine noch das andere
    steht (bewusst) auf der Liste.
    """
    return "".join(_schluessel_teile(name))


def _ist_geheimer_schluessel(name: str) -> bool:
    if set(_schluessel_teile(name)) & GEHEIM_SCHLUESSEL:
        return True
    kompakt = _kompakt(name)
    return any(g in kompakt for g in GEHEIM_SCHLUESSEL if len(g) >= 6)


def _ist_pii_schluessel(name: str) -> bool:
    if set(_schluessel_teile(name)) & PII_SCHLUESSEL:
        return True
    kompakt = _kompakt(name)
    return any(p in kompakt for p in PII_SCHLUESSEL if len(p) >= 5)


def wert_form(wert: Any) -> str:
    """
    Beschreibt einen Wert, ohne ihn preiszugeben: `<email>`, `<text:14>`, `<zahl>`.
    Für die Schema-Erkennung reicht die Form vollkommen aus.
    """
    if wert is None:
        return "<leer>"
    if isinstance(wert, bool):
        return "<ja/nein>"
    if isinstance(wert, (int, float)):
        return "<zahl>"
    text = str(wert)
    for name, muster in MUSTER:
        if muster.match(text):
            return f"<{name}>"
    if _ZUFALL.match(text):
        return "<schluessel>"
    return f"<text:{len(text)}>"


def maskiere(schluessel: Optional[str], wert: Any, modus: str = "sicher") -> Any:
    """
    Einen einzelnen Wert für die Weitergabe an die KI aufbereiten.

    modus="sicher"        – Standard: nur unbedenklich kurze Werte bleiben stehen,
                            alles andere wird zur Form verdichtet.
    modus="vollstaendig"  – der Nutzer hat echte Werte ausdrücklich freigegeben;
                            Geheimnisse und klare personenbezogene Daten werden
                            trotzdem maskiert.
    """
    if _ist_geheimer_schluessel(schluessel or ""):
        return "<geheim>"
    if wert is None or isinstance(wert, (bool, int, float)):
        return wert
    if isinstance(wert, list):
        return f"<liste:{len(wert)}>"
    if isinstance(wert, dict):
        return f"<objekt:{len(wert)}>"

    text = str(wert)
    for name, muster in MUSTER:
        if muster.match(text):
            # Datum und URL sind für das Verständnis wertvoll und kaum heikel.
            if name in ("datum", "datumzeit"):
                return text[:19]
            if name == "url":
                return text.split("?")[0][:120]   # Query kann Schlüssel enthalten
            return f"<{name}>"
    if _ZUFALL.match(text):
        return "<schluessel>"
    if _ist_pii_schluessel(schluessel or ""):
        return wert_form(text)

    if modus == "vollstaendig":
        return text[:200]
    return text if _UNBEDENKLICH.match(text) else wert_form(text)


def redigiere(daten: Any, modus: str = "sicher", schluessel: Optional[str] = None,
              tiefe: int = 0, max_liste: int = 3) -> Any:
    """Eine ganze Struktur maskieren – für Beispiel-Ausschnitte."""
    if tiefe > MAX_TIEFE:
        return "<zu tief>"
    if isinstance(daten, dict):
        return {k: redigiere(v, modus, k, tiefe + 1, max_liste) for k, v in daten.items()}
    if isinstance(daten, list):
        gekuerzt = [redigiere(v, modus, schluessel, tiefe + 1, max_liste) for v in daten[:max_liste]]
        if len(daten) > max_liste:
            gekuerzt.append(f"… {len(daten) - max_liste} weitere")
        return gekuerzt
    return maskiere(schluessel, daten, modus)


# ── Feld-Inventar ─────────────────────────────────────────────────────────────

def _typ_name(wert: Any) -> str:
    if wert is None:
        return "leer"
    if isinstance(wert, bool):
        return "ja/nein"
    if isinstance(wert, int):
        return "ganzzahl"
    if isinstance(wert, float):
        return "kommazahl"
    if isinstance(wert, list):
        return "liste"
    if isinstance(wert, dict):
        return "objekt"
    text = str(wert)
    for name, muster in MUSTER:
        if muster.match(text) and name in ("datum", "datumzeit", "email", "url", "uuid"):
            return name
    return "text"


def _sammle(obj: Any, prefix: str, out: dict, tiefe: int = 0):
    """Alle Blattpfade eines Datensatzes einsammeln."""
    if tiefe > MAX_TIEFE or len(out) > MAX_FELDER:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            _sammle(v, f"{prefix}.{k}" if prefix else str(k), out, tiefe + 1)
    elif isinstance(obj, list):
        out.setdefault(prefix, []).append(obj)
        for item in obj[:3]:
            if isinstance(item, (dict, list)):
                _sammle(item, f"{prefix}[]", out, tiefe + 1)
    else:
        out.setdefault(prefix, []).append(obj)


def feld_inventar(records: list, modus: str = "sicher") -> list:
    """
    Was steckt in diesen Datensätzen? Pro Feld: Typ, Füllgrad, Beispiel, Vielfalt.

    Das ist die Grundlage für alles Weitere – und gleichzeitig das Einzige, was
    die KI je zu sehen bekommt.
    """
    gesammelt: dict = {}
    for r in records[:MAX_DATENSAETZE]:
        _sammle(r, "", gesammelt)

    anzahl = min(len(records), MAX_DATENSAETZE) or 1
    inventar = []
    for pfad, werte in list(gesammelt.items())[:MAX_FELDER]:
        gefuellt = [w for w in werte if w is not None and w != "" and w != []]
        typen = {}
        for w in gefuellt[:50]:
            typen[_typ_name(w)] = typen.get(_typ_name(w), 0) + 1
        haeufigster = max(typen, key=typen.get) if typen else "leer"

        # Vielfalt nur für einfache Werte – sagt, ob ein Feld ein Schlüssel ist.
        einfach = [w for w in gefuellt if isinstance(w, (str, int, float, bool))]
        eindeutig = len(set(einfach)) if einfach else 0

        inventar.append({
            "pfad": pfad or "(Wurzel)",
            "typ": haeufigster,
            "anteil_gefuellt": round(len(gefuellt) / max(len(werte), 1), 2),
            "vorkommen": len(werte),
            "eindeutige_werte": eindeutig,
            "wirkt_wie_schluessel": bool(einfach) and eindeutig == len(einfach) and len(einfach) > 1,
            "beispiel": maskiere(pfad.split(".")[-1], gefuellt[0], modus) if gefuellt else None,
        })
    inventar.sort(key=lambda f: (-f["anteil_gefuellt"], f["pfad"]))
    return inventar


# ── Datenpfade ────────────────────────────────────────────────────────────────

def datenpfad_kandidaten(body: Any, prefix: str = "", tiefe: int = 0, out: Optional[list] = None) -> list:
    """
    Alle Stellen finden, an denen eine Liste von Objekten liegt – nach Nützlichkeit
    sortiert (viele Zeilen, wenig Verschachtelung gewinnt).
    """
    if out is None:
        out = []
    if tiefe > 5:
        return out
    if isinstance(body, list) and body and isinstance(body[0], dict):
        out.append({"pfad": prefix, "zeilen": len(body),
                    "spalten": len(body[0].keys()), "tiefe": tiefe})
        return out
    if isinstance(body, dict):
        for k, v in body.items():
            pfad = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, list) and v and isinstance(v[0], dict):
                out.append({"pfad": pfad, "zeilen": len(v),
                            "spalten": len(v[0].keys()), "tiefe": tiefe})
            elif isinstance(v, dict):
                datenpfad_kandidaten(v, pfad, tiefe + 1, out)
    out.sort(key=lambda k: (k["tiefe"], -k["zeilen"]))
    return out


# ── Paginierung ───────────────────────────────────────────────────────────────

_PAG_FELDER = {
    "cursor": ("next_cursor", "nextcursor", "cursor", "next_page_token", "continuation",
               "scroll_id", "after"),
    "page":   ("page", "current_page", "page_number", "pagenumber", "seite"),
    "offset": ("offset", "skip", "start", "from"),
    "limit":  ("limit", "per_page", "perpage", "page_size", "pagesize", "take", "count"),
    "gesamt": ("total", "total_count", "totalcount", "total_items", "gesamt", "anzahl",
               "record_count", "num_results"),
    "weiter": ("has_more", "hasmore", "has_next", "hasnext", "more", "is_last", "islast"),
    "next_url": ("next", "next_url", "nexturl", "next_page_url"),
}


def _flach_schluessel(body: Any, tiefe: int = 0, out: Optional[dict] = None) -> dict:
    """Alle Schlüssel der oberen Ebenen mit ihrem Wert – für die Paginierungssuche."""
    if out is None:
        out = {}
    if tiefe > 3 or not isinstance(body, dict):
        return out
    for k, v in body.items():
        if not isinstance(v, (dict, list)):
            out.setdefault(str(k).lower(), v)
        elif isinstance(v, dict):
            _flach_schluessel(v, tiefe + 1, out)
    return out


def paginierung_erkennen(body: Any, headers: Optional[dict] = None) -> dict:
    """
    Aus der Antwort ableiten, wie weitere Seiten zu holen sind – und das als
    fertige Konfiguration für die vorhandene Paginierungs-Engine zurückgeben.
    """
    headers = {k.lower(): v for k, v in (headers or {}).items()}
    if "link" in headers and 'rel="next"' in str(headers["link"]):
        return {"typ": "link_header", "begruendung": 'Link-Header mit rel="next" vorhanden',
                "config": {"type": "link_header"}}

    flach = _flach_schluessel(body)
    treffer = {art: [k for k in flach if k in namen] for art, namen in _PAG_FELDER.items()}

    if treffer["cursor"]:
        feld = treffer["cursor"][0]
        return {"typ": "cursor",
                "begruendung": f"Feld »{feld}« in der Antwort deutet auf Cursor-Paginierung",
                "config": {"type": "cursor", "cursor_param": "cursor", "cursor_path": feld}}
    if treffer["next_url"]:
        return {"typ": "link_header",
                "begruendung": f"Feld »{treffer['next_url'][0]}« enthält die nächste Seite",
                "config": {"type": "link_header"}}
    if treffer["page"]:
        limit_feld = treffer["limit"][0] if treffer["limit"] else "per_page"
        return {"typ": "page",
                "begruendung": f"Felder »{treffer['page'][0]}« und »{limit_feld}« deuten auf Seiten-Paginierung",
                "config": {"type": "page", "page_param": treffer["page"][0],
                           "limit_param": limit_feld, "limit": 100, "start_page": 1}}
    if treffer["offset"]:
        limit_feld = treffer["limit"][0] if treffer["limit"] else "limit"
        return {"typ": "offset",
                "begruendung": f"Felder »{treffer['offset'][0]}« und »{limit_feld}« deuten auf Offset-Paginierung",
                "config": {"type": "offset", "offset_param": treffer["offset"][0],
                           "limit_param": limit_feld, "limit": 100}}
    if treffer["gesamt"] or treffer["weiter"]:
        hinweis = (treffer["gesamt"] or treffer["weiter"])[0]
        return {"typ": "unklar",
                "begruendung": f"Feld »{hinweis}« zeigt, dass es mehr Daten gibt – "
                               "wie sie zu holen sind, geht aus der Antwort nicht hervor",
                "config": None}
    return {"typ": "none", "begruendung": "Keine Hinweise auf weitere Seiten", "config": None}


# ── Gesamtanalyse ─────────────────────────────────────────────────────────────

def analysiere(body: Any, headers: Optional[dict] = None, data_path: Optional[str] = None,
               modus: str = "sicher") -> dict:
    """
    Die vollständige deterministische Analyse einer Antwort.
    Kein Sprachmodell beteiligt – das Ergebnis ist reproduzierbar und exakt.
    """
    kandidaten = datenpfad_kandidaten(body)
    pfad = data_path if data_path is not None else (kandidaten[0]["pfad"] if kandidaten else None)

    records = body
    if pfad:
        for teil in pfad.split("."):
            if isinstance(records, dict):
                records = records.get(teil)
            else:
                records = None
                break
    if isinstance(records, dict):
        records = [records]
    if not isinstance(records, list):
        records = [body] if isinstance(body, dict) else []

    return {
        "datenpfad": pfad,
        "datenpfad_kandidaten": kandidaten[:5],
        "zeilen": len(records),
        "inventar": feld_inventar(records, modus),
        "paginierung": paginierung_erkennen(body, headers),
        "beispiel": redigiere(records[0], modus) if records else None,
        "modus": modus,
    }


# ── Variablen-Vorschläge ──────────────────────────────────────────────────────

def variablen_vorschlaege(cfg: dict) -> list:
    """
    Aus einer Request-Konfiguration ableiten, was in eine Umgebung gehört:
    der Host (wechselt zwischen Test und Produktion) und alles, was nach
    Zugangsdaten aussieht.

    Rein deterministisch – hierfür braucht es keine KI.
    """
    vorschlaege = []
    url = (cfg.get("url") or "").strip()

    m = re.match(r"^(https?://[^/]+)(/.*)?$", url, re.I)
    if m:
        vorschlaege.append({
            "key": "basis_url", "wert": m.group(1), "secret": False,
            "quelle": "URL",
            "begruendung": "Der Host wechselt typischerweise zwischen Test- und Produktivsystem.",
            "ersetzt": m.group(1),
        })

    for bereich, daten in (("Header", cfg.get("headers") or {}),
                           ("Query-Parameter", cfg.get("query_params") or {})):
        for k, v in daten.items():
            wert = str(v)
            if not wert:
                continue
            geheim = _ist_geheimer_schluessel(k) or _ZUFALL.match(wert) is not None
            if not geheim:
                continue
            vorschlaege.append({
                "key": re.sub(r"[^a-z0-9]+", "_", k.lower()).strip("_") or "geheimnis",
                "wert": wert, "secret": True,
                "quelle": f"{bereich} »{k}«",
                "begruendung": "Sieht nach einem Zugangsschlüssel aus – gehört verschlüsselt "
                               "in die Umgebung statt in den Request.",
                "ersetzt": wert,
            })

    return vorschlaege
