"""Fachwissen des Abfrage-Generators: Körnungen, Join-Gerüste, Felder, Kennzahlen.

Hier steht, was gegen die JTL-Tabellen richtig ist. Der SQL-Bauer daneben ist
reine Mechanik — er setzt zusammen, was hier definiert wurde, und erfindet nichts.

**Warum fest verdrahtet und nicht aus dem Schema-Katalog abgeleitet:** Dort haben
ausgerechnet `dbo.tBestellPos` und `dbo.tKunde` null Beziehungen, weil die
JTL-Spaltennamen (`tBestellung_kBestellung`, `tArtikel_kArtikel`) jede
namensbasierte Ableitung unterlaufen. Und die fachlichen Regeln — Rechnungs-
adresse über `nTyp=1 AND nStandard=1`, Storno-Ausschluss, der Kundenname aus
Firma plus Firmenzusatz — stehen dort ohnehin nirgends.

**Sicherheits-Invariante:** Alles in diesem Modul ist serverseitig und
unveränderlich. Der Client schickt nur Schlüssel (`key`), niemals SQL-Ausdrücke.
Werte werden vom SQL-Bauer ausnahmslos gebunden.
"""

# Der Kundenname steht selten allein in cFirma: bei PPS trägt sie 5.342-mal nur
# „Zahnarztpraxis“. Der echte Name steckt im Firmenzusatz. Die CHARINDEX-Prüfung
# ist nicht optional – sonst steht da „Zahnarztpraxis Uwe Göselt Uwe Göselt“.
def _name(p: str) -> str:
    return (f"LTRIM(RTRIM(ISNULL({p}.cFirma,'')) + CASE WHEN ISNULL({p}.cZusatz,'') = '' "
            f"OR CHARINDEX(LTRIM(RTRIM({p}.cZusatz)), ISNULL({p}.cFirma,'')) > 0 THEN '' "
            f"ELSE ' ' + LTRIM(RTRIM({p}.cZusatz)) END)")

# Zeitfenster einer Kennzahl. Ohne Fenster ist „Anzahl Rechnungen = 0“ wertlos:
# über die ganze Historie trifft es fast niemanden, über den Berichtszeitraum
# genau die interessanten Fälle. :von/:bis kommen aus dem Zeitraum des Reports.
def _fenster(spalte: str) -> str:
    return f"{spalte} >= :von AND {spalte} < DATEADD(DAY, 1, :bis)"


# ── Körnung „Kunde“ ──────────────────────────────────────────────────────────
# Basis ist tKunde, die Kennzahlen sind Unterabfragen. Nur so entstehen Zeilen
# für Kunden, die gar keine Rechnung haben – ein GROUP BY über Rechnungen kann
# einen Nullfall prinzipiell nicht liefern, und genau die sind gesucht.
# Geprüft: je Kunde existiert genau eine Adresse mit nTyp=1 AND nStandard=1,
# der LEFT JOIN verdoppelt also keine Zeilen (22.495 Kunden, 0 Dubletten).

_KUNDE_BASIS = """FROM dbo.tKunde k
LEFT JOIN dbo.tAdresse a ON a.kKunde = k.kKunde AND a.nTyp = 1 AND a.nStandard = 1"""

_KUNDE_FELDER = [
    {"key": "kunde.nr",        "label": "Kundennummer",   "typ": "text",
     "sql": "k.cKundenNr",     "ausgabe": True},
    {"key": "kunde.name",      "label": "Kundenname",     "typ": "text",
     "sql": _name("a"),        "ausgabe": True,
     "hinweis": "Firma plus Firmenzusatz – bei PPS steht in cFirma meist nur die Gattung."},
    {"key": "kunde.ort",       "label": "Ort",            "typ": "text",
     "sql": "a.cOrt",          "ausgabe": True},
    {"key": "kunde.plz",       "label": "PLZ",            "typ": "text",
     "sql": "a.cPLZ",          "ausgabe": True},
    {"key": "kunde.land",      "label": "Land",           "typ": "text",
     "sql": "a.cISO",          "ausgabe": True},
    {"key": "kunde.mail",      "label": "E-Mail",         "typ": "text",
     "sql": "a.cMail",         "ausgabe": False},
    {"key": "kunde.id",        "label": "Kunde (Auswahl)", "typ": "zahl",
     "sql": "k.kKunde",        "ausgabe": False, "lookup": "kunde",
     "hinweis": "Für die Auswahl bestimmter Kunden."},
    {"key": "kunde.gesperrt",  "label": "Gesperrt",       "typ": "ja_nein",
     "sql": "CASE WHEN ISNULL(k.cSperre,'N') = 'Y' THEN 1 ELSE 0 END", "ausgabe": False},
    {"key": "kunde.seit",      "label": "Kunde seit",     "typ": "datum",
     "sql": "k.dErstellt",     "ausgabe": False},
]

_KUNDE_KENNZAHLEN = [
    {"key": "auftraege", "label": "Anzahl Aufträge", "typ": "zahl", "decimals": 0,
     "sql": """(SELECT COUNT(*) FROM dbo.tBestellung b
                WHERE b.tKunde_kKunde = k.kKunde AND ISNULL(b.nStorno,0) = 0
                  AND """ + _fenster("b.dErstellt") + ")"},

    {"key": "auftragswert", "label": "Summe Auftragswert netto", "typ": "geld", "decimals": 2,
     "sql": """(SELECT CAST(ISNULL(SUM(bp.nAnzahl * bp.fVkNetto), 0) AS DECIMAL(18,2))
                FROM dbo.tBestellung b
                JOIN dbo.tBestellPos bp ON bp.tBestellung_kBestellung = b.kBestellung
                WHERE b.tKunde_kKunde = k.kKunde AND ISNULL(b.nStorno,0) = 0
                  AND """ + _fenster("b.dErstellt") + ")"},

    # Lieferscheine sind die einzige Möglichkeit, „Ware raus, aber nicht
    # berechnet" zu erkennen. Ohne sie bleibt die Ausgangsfrage unbeantwortbar.
    {"key": "lieferscheine", "label": "Anzahl Lieferscheine", "typ": "zahl", "decimals": 0,
     "sql": """(SELECT COUNT(DISTINCT l.kLieferschein)
                FROM dbo.tLieferschein l
                JOIN dbo.tBestellung b ON b.kBestellung = l.kBestellung
                WHERE b.tKunde_kKunde = k.kKunde AND """ + _fenster("l.dErstellt") + ")"},

    {"key": "rechnungen", "label": "Anzahl Rechnungen", "typ": "zahl", "decimals": 0,
     "sql": """(SELECT COUNT(DISTINCT r.kRechnung)
                FROM Rechnung.vRechnung r
                JOIN Rechnung.vRechnungRechnungsadresse ra ON ra.kRechnung = r.kRechnung
                WHERE ra.kKunde = k.kKunde AND ISNULL(r.nStorno,0) = 0
                  AND """ + _fenster("r.dErstellt") + ")"},

    {"key": "umsatz", "label": "Summe Umsatz netto", "typ": "geld", "decimals": 2,
     "sql": """(SELECT CAST(ISNULL(SUM(rp.fAnzahl * rp.fVkNetto), 0) AS DECIMAL(18,2))
                FROM Rechnung.vRechnung r
                JOIN Rechnung.vRechnungRechnungsadresse ra ON ra.kRechnung = r.kRechnung
                JOIN Rechnung.tRechnungPosition rp ON rp.kRechnung = r.kRechnung
                WHERE ra.kKunde = k.kKunde AND ISNULL(r.nStorno,0) = 0
                  AND """ + _fenster("r.dErstellt") + ")"},

    # Der Zähler allein hätte Hygiene Daheim nicht gefunden: deren Schatten-
    # lieferungen liefen über Rechnungen ÜBER NULL EURO. Erkennungsmerkmal ist
    # der Wert, nicht die Anzahl.
    {"key": "positionen_zu_null", "label": "Anzahl Rechnungspositionen zu 0 €", "typ": "zahl",
     "decimals": 0,
     "sql": """(SELECT COUNT(*)
                FROM Rechnung.vRechnung r
                JOIN Rechnung.vRechnungRechnungsadresse ra ON ra.kRechnung = r.kRechnung
                JOIN Rechnung.tRechnungPosition rp ON rp.kRechnung = r.kRechnung
                WHERE ra.kKunde = k.kKunde AND ISNULL(r.nStorno,0) = 0
                  AND rp.fVkNetto = 0 AND """ + _fenster("r.dErstellt") + ")"},

    {"key": "letzte_rechnung", "label": "Letzte Rechnung", "typ": "datum",
     "sql": """(SELECT MAX(r.dErstellt)
                FROM Rechnung.vRechnung r
                JOIN Rechnung.vRechnungRechnungsadresse ra ON ra.kRechnung = r.kRechnung
                WHERE ra.kKunde = k.kKunde AND ISNULL(r.nStorno,0) = 0)"""},

    {"key": "letzte_lieferung", "label": "Letzte Lieferung", "typ": "datum",
     "sql": """(SELECT MAX(l.dErstellt)
                FROM dbo.tLieferschein l
                JOIN dbo.tBestellung b ON b.kBestellung = l.kBestellung
                WHERE b.tKunde_kKunde = k.kKunde)"""},
]


KOERNUNGEN = {
    "kunde": {
        "label": "Kunde",
        "plural": "Kunden",
        "beschreibung": ("Eine Zeile je Kunde. Als einzige Körnung findet sie auch "
                         "Nullfälle – „Kunden ohne Rechnung“ ist nur so beantwortbar."),
        "basis": _KUNDE_BASIS,
        "schluessel": {"sql": "k.kKunde", "name": "kKunde"},
        "felder": _KUNDE_FELDER,
        "kennzahlen": _KUNDE_KENNZAHLEN,
        # Ein Kunde hat kein Datum. „Wie viele Kunden hatten in Monat X keine
        # Rechnung" wäre eine rollierende Neuberechnung je Monat – eine andere
        # und deutlich teurere Frage.
        "verlauf": None,
        "verlauf_grund": ("Ein Kunde hat kein Datum. Für eine Entwicklung über die "
                          "Zeit die Körnung „Rechnung“ oder „Auftrag“ wählen."),
    },
}


# ── Vergleiche je Feldtyp ────────────────────────────────────────────────────
# Die Schlüssel sind Teil des Vertrags mit der Oberfläche; der SQL-Bauer kennt
# genau diese und weist alles andere ab.
VERGLEICHE = {
    "text":    [("=", "ist"), ("<>", "ist nicht"), ("enthaelt", "enthält"),
                ("beginnt", "beginnt mit"), ("in", "ist eines von"),
                ("leer", "ist leer"), ("nicht_leer", "ist nicht leer")],
    "zahl":    [("=", "="), ("<>", "≠"), ("<", "<"), ("<=", "≤"), (">", ">"),
                (">=", "≥"), ("zwischen", "zwischen"), ("in", "ist eines von")],
    "geld":    [("=", "="), ("<>", "≠"), ("<", "<"), ("<=", "≤"), (">", ">"),
                (">=", "≥"), ("zwischen", "zwischen")],
    "datum":   [("<", "vor"), ("<=", "bis"), (">", "nach"), (">=", "ab"),
                ("zwischen", "zwischen"), ("leer", "fehlt"), ("nicht_leer", "vorhanden")],
    "ja_nein": [("=", "ist")],
}

# Vergleiche ohne Wertfeld – die Oberfläche blendet die Eingabe aus.
OHNE_WERT = {"leer", "nicht_leer"}
# Vergleiche mit zwei Werten.
ZWEI_WERTE = {"zwischen"}
# Vergleiche mit einer Werteliste.
LISTE = {"in"}


def schema() -> dict:
    """Was die Oberfläche zum Bauen braucht. Ohne SQL – das bleibt hier."""
    raus = []
    for key, k in KOERNUNGEN.items():
        raus.append({
            "key": key,
            "label": k["label"],
            "plural": k.get("plural") or k["label"],
            "beschreibung": k["beschreibung"],
            "verlauf": k["verlauf"] is not None,
            "verlauf_grund": k.get("verlauf_grund"),
            "felder": [{kk: vv for kk, vv in f.items() if kk != "sql"}
                       for f in k["felder"]],
            "kennzahlen": [{kk: vv for kk, vv in m.items() if kk != "sql"}
                           for m in k["kennzahlen"]],
        })
    return {
        "koernungen": raus,
        "vergleiche": {t: [{"key": o, "label": l} for o, l in v]
                       for t, v in VERGLEICHE.items()},
        "ohne_wert": sorted(OHNE_WERT),
        "zwei_werte": sorted(ZWEI_WERTE),
        "liste": sorted(LISTE),
    }


def feld(koernung: str, key: str) -> dict | None:
    k = KOERNUNGEN.get(koernung)
    if not k:
        return None
    return next((f for f in k["felder"] if f["key"] == key), None)


def kennzahl(koernung: str, key: str) -> dict | None:
    k = KOERNUNGEN.get(koernung)
    if not k:
        return None
    return next((m for m in k["kennzahlen"] if m["key"] == key), None)
