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

    # Für „seit 90 Tagen nicht bestellt": ein Datum lässt sich nicht relativ
    # filtern, eine Tageszahl schon. Nie berechnete Kunden bleiben NULL und fallen
    # damit heraus – „seit X Tagen nicht" setzt voraus, dass es ein Vorher gab.
    {"key": "tage_seit_rechnung", "label": "Tage seit letzter Rechnung", "typ": "zahl",
     "decimals": 0,
     "sql": """DATEDIFF(DAY, (SELECT MAX(r.dErstellt)
                FROM Rechnung.vRechnung r
                JOIN Rechnung.vRechnungRechnungsadresse ra ON ra.kRechnung = r.kRechnung
                WHERE ra.kKunde = k.kKunde AND ISNULL(r.nStorno,0) = 0), GETDATE())"""},

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
        # „stamm“: eine Zeile je Stammsatz, Kennzahlen als Unterabfragen (findet
        # Nullfälle). Alle anderen Körnungen folgen der Zeilen-Bauart.
        "bauart": "stamm",
    },
}


# ── Gemeinsame Bausteine der Zeilen-Körnungen ────────────────────────────────
# Aufbau: innen eine Zwischenebene mit den Rohwerten je Zeile, außen Gruppierung
# und Aggregate. Das ist nicht nur einheitlich, es ist notwendig – MSSQL verbietet
# SUM(<Unterabfrage>), und der Auftrags- bzw. Rechnungswert IST eine Unterabfrage.
# Gruppierungen und Kennzahlen rechnen darum mit den Aliasnamen (x.…).

def _alias(key: str) -> str:
    return key.replace(".", "_")


def _kundenfelder(adr: str, kunde: str | None = None) -> list:
    felder = [
        {"key": "kunde.name", "label": "Kundenname", "typ": "text",
         "sql": _name(adr), "ausgabe": True},
        {"key": "kunde.ort", "label": "Ort", "typ": "text",
         "sql": f"{adr}.cOrt", "ausgabe": False},
        {"key": "kunde.plz", "label": "PLZ", "typ": "text",
         "sql": f"{adr}.cPLZ", "ausgabe": False},
        {"key": "kunde.land", "label": "Land", "typ": "text",
         "sql": f"{adr}.cISO", "ausgabe": False},
    ]
    if kunde:
        felder.append({"key": "kunde.id", "label": "Kunde (Auswahl)", "typ": "zahl",
                       "sql": kunde, "ausgabe": False, "lookup": "kunde"})
    return felder


def _gruppierungen(datum_key: str, artnr_key: str | None = None,
                   artname_key: str | None = None) -> list:
    g = [
        {"key": "kunde", "label": "je Kunde",
         "sql": [("x.kunde_id", "kKunde"), ("x.kunde_name", "Kunde")]},
        {"key": "monat", "label": "je Monat", "verlauf": True,
         "sql": [(f"FORMAT(x.{_alias(datum_key)}, 'yyyy-MM')", "Monat")]},
        {"key": "land", "label": "je Land", "sql": [("x.kunde_land", "Land")]},
    ]
    if artnr_key:
        g.insert(1, {"key": "artikel", "label": "je Artikel",
                     "sql": [(f"x.{_alias(artnr_key)}", "ArtNr"),
                             (f"MAX(x.{_alias(artname_key)})", "Artikel")]})
    return g


# ── Körnung „Auftrag" ────────────────────────────────────────────────────────
_AUFTRAG_WERT = """(SELECT CAST(ISNULL(SUM(bp.nAnzahl * bp.fVkNetto), 0) AS DECIMAL(18,2))
                    FROM dbo.tBestellPos bp
                    WHERE bp.tBestellung_kBestellung = b.kBestellung)"""

KOERNUNGEN["auftrag"] = {
    "label": "Auftrag", "plural": "Aufträge",
    "beschreibung": "Eine Zeile je Auftrag. Für Listen auffälliger oder offener Vorgänge.",
    "basis": """FROM dbo.tBestellung b
LEFT JOIN dbo.tKunde k ON k.kKunde = b.tKunde_kKunde
LEFT JOIN dbo.tAdresse a ON a.kKunde = k.kKunde AND a.nTyp = 1 AND a.nStandard = 1""",
    "grundfilter": "ISNULL(b.nStorno,0) = 0 AND " + _fenster("b.dErstellt"),
    "schluessel": {"sql": "b.kBestellung", "name": "kBestellung"},
    "felder": [
        {"key": "auftrag.nr", "label": "Auftragsnummer", "typ": "text",
         "sql": "b.cBestellNr", "ausgabe": True},
        {"key": "auftrag.datum", "label": "Auftragsdatum", "typ": "datum",
         "sql": "b.dErstellt", "ausgabe": True},
    ] + _kundenfelder("a", "k.kKunde") + [
        {"key": "auftrag.wert", "label": "Auftragswert netto", "typ": "geld",
         "sql": _AUFTRAG_WERT, "ausgabe": True},
    ],
    "gruppierungen": _gruppierungen("auftrag.datum"),
    "kennzahlen": [
        {"key": "anzahl", "label": "Anzahl Aufträge", "typ": "zahl", "decimals": 0,
         "sql": "COUNT(DISTINCT x.kBestellung)"},
        {"key": "summe_wert", "label": "Summe Auftragswert netto", "typ": "geld",
         "decimals": 2, "sql": "CAST(SUM(x.auftrag_wert) AS DECIMAL(18,2))"},
        {"key": "kunden", "label": "Anzahl Kunden", "typ": "zahl", "decimals": 0,
         "sql": "COUNT(DISTINCT x.kunde_id)"},
    ],
}

# ── Körnung „Auftragsposition" ───────────────────────────────────────────────
KOERNUNGEN["auftragsposition"] = {
    "label": "Auftragsposition", "plural": "Auftragspositionen",
    "beschreibung": "Eine Zeile je Auftragsposition – die Artikelebene der Aufträge.",
    "basis": """FROM dbo.tBestellung b
JOIN dbo.tBestellPos bp ON bp.tBestellung_kBestellung = b.kBestellung
LEFT JOIN dbo.tKunde k ON k.kKunde = b.tKunde_kKunde
LEFT JOIN dbo.tAdresse a ON a.kKunde = k.kKunde AND a.nTyp = 1 AND a.nStandard = 1""",
    "grundfilter": "ISNULL(b.nStorno,0) = 0 AND " + _fenster("b.dErstellt"),
    "schluessel": {"sql": "bp.kBestellPos", "name": "kBestellPos"},
    "felder": [
        {"key": "pos.artnr", "label": "Artikelnummer", "typ": "text",
         "sql": "bp.cArtNr", "ausgabe": True},
        {"key": "pos.artikel", "label": "Artikelbezeichnung", "typ": "text",
         "sql": "bp.cString", "ausgabe": True},
        # nType 1 sind die echten Artikelzeilen; 0/2/3 sind Text-, Versand- und
        # Rabattzeilen und verfälschen jede Mengenauswertung.
        {"key": "pos.artikelzeile", "label": "Artikelposition", "typ": "ja_nein",
         "sql": "CASE WHEN bp.nType = 1 THEN 1 ELSE 0 END", "ausgabe": False,
         "hinweis": "Nein = Text-, Versand- oder Rabattzeile."},
        {"key": "pos.menge", "label": "Menge", "typ": "zahl",
         "sql": "CAST(bp.nAnzahl AS DECIMAL(18,2))", "ausgabe": True},
        {"key": "pos.preis", "label": "Einzelpreis netto", "typ": "geld",
         "sql": "CAST(bp.fVkNetto AS DECIMAL(18,2))", "ausgabe": True},
        {"key": "pos.wert", "label": "Positionswert netto", "typ": "geld",
         "sql": "CAST(bp.nAnzahl * bp.fVkNetto AS DECIMAL(18,2))", "ausgabe": True},
        {"key": "auftrag.nr", "label": "Auftragsnummer", "typ": "text",
         "sql": "b.cBestellNr", "ausgabe": True},
        {"key": "auftrag.datum", "label": "Auftragsdatum", "typ": "datum",
         "sql": "b.dErstellt", "ausgabe": False},
        {"key": "auftrag.id", "label": "Auftrag (intern)", "typ": "zahl",
         "sql": "b.kBestellung", "ausgabe": False},
    ] + _kundenfelder("a", "k.kKunde"),
    "gruppierungen": _gruppierungen("auftrag.datum", "pos.artnr", "pos.artikel"),
    "kennzahlen": [
        {"key": "positionen", "label": "Anzahl Positionen", "typ": "zahl", "decimals": 0,
         "sql": "COUNT(*)"},
        {"key": "menge", "label": "Summe Menge", "typ": "zahl", "decimals": 0,
         "sql": "CAST(SUM(x.pos_menge) AS DECIMAL(18,0))"},
        {"key": "wert", "label": "Summe Wert netto", "typ": "geld", "decimals": 2,
         "sql": "CAST(SUM(x.pos_wert) AS DECIMAL(18,2))"},
        {"key": "kunden", "label": "Anzahl Kunden", "typ": "zahl", "decimals": 0,
         "sql": "COUNT(DISTINCT x.kunde_id)"},
        {"key": "auftraege", "label": "Anzahl Aufträge", "typ": "zahl", "decimals": 0,
         "sql": "COUNT(DISTINCT x.auftrag_id)"},
    ],
}

# ── Körnung „Rechnung" ───────────────────────────────────────────────────────
# FALLE: vRechnung.cFirma ist die EIGENE Firma. Der Kunde kommt ausschließlich
# aus vRechnungRechnungsadresse (geprüft: genau eine Adresse je Rechnung).
_RECHNUNG_WERT = """(SELECT CAST(ISNULL(SUM(rp.fAnzahl * rp.fVkNetto), 0) AS DECIMAL(18,2))
                     FROM Rechnung.tRechnungPosition rp
                     WHERE rp.kRechnung = r.kRechnung)"""

KOERNUNGEN["rechnung"] = {
    "label": "Rechnung", "plural": "Rechnungen",
    "beschreibung": "Eine Zeile je Rechnung. Stornierte Belege sind immer ausgeschlossen.",
    "basis": """FROM Rechnung.vRechnung r
JOIN Rechnung.vRechnungRechnungsadresse ra ON ra.kRechnung = r.kRechnung""",
    "grundfilter": "ISNULL(r.nStorno,0) = 0 AND " + _fenster("r.dErstellt"),
    "schluessel": {"sql": "r.kRechnung", "name": "kRechnung"},
    "felder": [
        {"key": "rechnung.nr", "label": "Rechnungsnummer", "typ": "text",
         "sql": "r.cRechnungsnr", "ausgabe": True},
        {"key": "rechnung.datum", "label": "Rechnungsdatum", "typ": "datum",
         "sql": "r.dErstellt", "ausgabe": True},
    ] + _kundenfelder("ra", "ra.kKunde") + [
        {"key": "rechnung.wert", "label": "Rechnungswert netto", "typ": "geld",
         "sql": _RECHNUNG_WERT, "ausgabe": True},
        {"key": "rechnung.zahlungsart", "label": "Zahlungsart", "typ": "text",
         "sql": "r.cZahlungsart", "ausgabe": False},
    ],
    "gruppierungen": _gruppierungen("rechnung.datum"),
    "kennzahlen": [
        {"key": "anzahl", "label": "Anzahl Rechnungen", "typ": "zahl", "decimals": 0,
         "sql": "COUNT(DISTINCT x.kRechnung)"},
        {"key": "umsatz", "label": "Summe Umsatz netto", "typ": "geld", "decimals": 2,
         "sql": "CAST(SUM(x.rechnung_wert) AS DECIMAL(18,2))"},
        {"key": "kunden", "label": "Anzahl Kunden", "typ": "zahl", "decimals": 0,
         "sql": "COUNT(DISTINCT x.kunde_id)"},
    ],
}

# ── Körnung „Rechnungsposition" ──────────────────────────────────────────────
# Artikelnummer und -name stehen auf der Position selbst – das ist der Stand zum
# Rechnungszeitpunkt und damit richtiger als der heutige Artikelstamm.
KOERNUNGEN["rechnungsposition"] = {
    "label": "Rechnungsposition", "plural": "Rechnungspositionen",
    "beschreibung": ("Eine Zeile je Rechnungsposition – die Artikelebene des Umsatzes. "
                     "Für „wer kauft was“ die richtige Körnung."),
    "basis": """FROM Rechnung.vRechnung r
JOIN Rechnung.tRechnungPosition rp ON rp.kRechnung = r.kRechnung
JOIN Rechnung.vRechnungRechnungsadresse ra ON ra.kRechnung = r.kRechnung""",
    "grundfilter": "ISNULL(r.nStorno,0) = 0 AND " + _fenster("r.dErstellt"),
    "schluessel": {"sql": "rp.kRechnungPosition", "name": "kRechnungPosition"},
    "felder": [
        {"key": "pos.artnr", "label": "Artikelnummer", "typ": "text",
         "sql": "rp.cArtNr", "ausgabe": True},
        {"key": "pos.artikel", "label": "Artikelbezeichnung", "typ": "text",
         "sql": "rp.cName", "ausgabe": True},
        {"key": "pos.artikelzeile", "label": "Artikelposition", "typ": "ja_nein",
         "sql": "CASE WHEN rp.nType = 1 THEN 1 ELSE 0 END", "ausgabe": False,
         "hinweis": "Nein = Text-, Versand- oder Rabattzeile."},
        {"key": "pos.menge", "label": "Menge", "typ": "zahl",
         "sql": "CAST(rp.fAnzahl AS DECIMAL(18,2))", "ausgabe": True},
        {"key": "pos.preis", "label": "Einzelpreis netto", "typ": "geld",
         "sql": "CAST(rp.fVkNetto AS DECIMAL(18,2))", "ausgabe": True},
        {"key": "pos.wert", "label": "Positionswert netto", "typ": "geld",
         "sql": "CAST(rp.fAnzahl * rp.fVkNetto AS DECIMAL(18,2))", "ausgabe": True},
        {"key": "pos.rohertrag", "label": "Rohertrag Ware", "typ": "geld",
         "sql": "CAST(rp.fAnzahl * (rp.fVkNetto - rp.fEkNetto) AS DECIMAL(18,2))",
         "ausgabe": False},
        {"key": "rechnung.nr", "label": "Rechnungsnummer", "typ": "text",
         "sql": "r.cRechnungsnr", "ausgabe": True},
        {"key": "rechnung.datum", "label": "Rechnungsdatum", "typ": "datum",
         "sql": "r.dErstellt", "ausgabe": False},
        {"key": "rechnung.id", "label": "Rechnung (intern)", "typ": "zahl",
         "sql": "r.kRechnung", "ausgabe": False},
    ] + _kundenfelder("ra", "ra.kKunde"),
    "gruppierungen": _gruppierungen("rechnung.datum", "pos.artnr", "pos.artikel"),
    "kennzahlen": [
        {"key": "positionen", "label": "Anzahl Positionen", "typ": "zahl", "decimals": 0,
         "sql": "COUNT(*)"},
        {"key": "menge", "label": "Summe Menge", "typ": "zahl", "decimals": 0,
         "sql": "CAST(SUM(x.pos_menge) AS DECIMAL(18,0))"},
        {"key": "umsatz", "label": "Summe Umsatz netto", "typ": "geld", "decimals": 2,
         "sql": "CAST(SUM(x.pos_wert) AS DECIMAL(18,2))"},
        {"key": "rohertrag", "label": "Summe Rohertrag Ware", "typ": "geld", "decimals": 2,
         "sql": "CAST(SUM(x.pos_rohertrag) AS DECIMAL(18,2))"},
        {"key": "kunden", "label": "Anzahl Kunden", "typ": "zahl", "decimals": 0,
         "sql": "COUNT(DISTINCT x.kunde_id)"},
        {"key": "rechnungen", "label": "Anzahl Rechnungen", "typ": "zahl", "decimals": 0,
         "sql": "COUNT(DISTINCT x.rechnung_id)"},
    ],
}


# ── Körnung „Artikel" ────────────────────────────────────────────────────────
# Stamm-Bauart wie „Kunde": eine Zeile je Artikel, auch für Artikel ohne jeden
# Verkauf – „Ladenhüter" und „nie verkauft" sind genau diese Nullfälle.
# Bestand, Menge in Aufträgen und Zulauf stehen in dbo.tlagerbestand (eine Zeile
# je Artikel, dieselbe Quelle wie die Fehlmengen im Lager-Cockpit; geprüft in
# JTL 1.8 und 2.0.5). Vaterartikel sind ausgeschlossen: ihr Bestand ist die Summe
# der Kinder und würde jede Summe verdoppeln.
_ART_VERKAUF = """FROM Rechnung.vRechnung r
                JOIN Rechnung.tRechnungPosition rp ON rp.kRechnung = r.kRechnung
                WHERE rp.kArtikel = art.kArtikel AND ISNULL(r.nStorno,0) = 0"""

KOERNUNGEN["artikel"] = {
    "label": "Artikel", "plural": "Artikel",
    "beschreibung": ("Eine Zeile je Artikel mit Bestand und Verkäufen im Zeitraum. "
                     "Findet auch Artikel, die gar nicht verkauft wurden."),
    "bauart": "stamm",
    "basis": """FROM dbo.tArtikel art
LEFT JOIN dbo.tArtikelBeschreibung ab ON ab.kArtikel = art.kArtikel
     AND ab.kSprache = 1 AND ab.kPlattform = 1 AND ab.kShop = 0
LEFT JOIN dbo.tlagerbestand lb ON lb.kArtikel = art.kArtikel""",
    "basis_filter": "ISNULL(art.nIstVater, 0) = 0",
    "schluessel": {"sql": "art.kArtikel", "name": "kArtikel"},
    "felder": [
        {"key": "artikel.nr", "label": "Artikelnummer", "typ": "text",
         "sql": "art.cArtNr", "ausgabe": True},
        {"key": "artikel.name", "label": "Artikelbezeichnung", "typ": "text",
         "sql": "ab.cName", "ausgabe": True},
        {"key": "artikel.bestand", "label": "Bestand", "typ": "zahl",
         "sql": "CAST(ISNULL(lb.fLagerbestand, 0) AS DECIMAL(18,2))", "ausgabe": True},
        {"key": "artikel.in_auftraegen", "label": "In offenen Aufträgen", "typ": "zahl",
         "sql": "CAST(ISNULL(lb.fInAuftraegen, 0) AS DECIMAL(18,2))", "ausgabe": True},
        {"key": "artikel.fehlmenge", "label": "Fehlmenge", "typ": "zahl",
         "sql": "CAST(ISNULL(lb.fInAuftraegen, 0) - ISNULL(lb.fLagerbestand, 0) AS DECIMAL(18,2))",
         "ausgabe": False,
         "hinweis": "In Aufträgen minus Bestand; über 0 heißt: reicht nicht."},
        {"key": "artikel.zulauf", "label": "Zulauf (bestellt)", "typ": "zahl",
         "sql": "CAST(ISNULL(lb.fZulauf, 0) AS DECIMAL(18,2))", "ausgabe": True},
        {"key": "artikel.lieferdatum", "label": "Nächste Lieferung", "typ": "datum",
         "sql": "lb.dLieferdatum", "ausgabe": False},
        {"key": "artikel.mindestbestand", "label": "Mindestbestand", "typ": "zahl",
         "sql": "ISNULL(art.nMidestbestand, 0)", "ausgabe": False},
        {"key": "artikel.ek", "label": "EK netto", "typ": "geld",
         "sql": "CAST(art.fEKNetto AS DECIMAL(18,2))", "ausgabe": False},
        {"key": "artikel.vk", "label": "VK netto", "typ": "geld",
         "sql": "CAST(art.fVKNetto AS DECIMAL(18,2))", "ausgabe": False},
        {"key": "artikel.lagerwert", "label": "Lagerwert (EK)", "typ": "geld",
         "sql": "CAST(ISNULL(lb.fLagerbestand, 0) * ISNULL(art.fEKNetto, 0) AS DECIMAL(18,2))",
         "ausgabe": False},
        # Versand-, Zuschlags- und Dienstleistungsartikel führen keinen Bestand
        # und stünden sonst in jeder Fehlmengenliste ganz oben. Maßgeblich ist
        # cLagerAktiv (Lagerführung an); cLagerArtikel ist bei HaKo durchweg 'N'.
        # Wer in JTL gar keinen Bestand führt (HyDa), bekommt hier zu Recht nichts.
        {"key": "artikel.lagerartikel", "label": "Mit Lagerführung", "typ": "ja_nein",
         "sql": "CASE WHEN art.cLagerAktiv = 'Y' THEN 1 ELSE 0 END", "ausgabe": False},
        {"key": "artikel.aktiv", "label": "Aktiv", "typ": "ja_nein",
         "sql": "CASE WHEN art.cAktiv = 'Y' THEN 1 ELSE 0 END", "ausgabe": False},
        {"key": "artikel.angelegt", "label": "Angelegt am", "typ": "datum",
         "sql": "art.dErstelldatum", "ausgabe": False},
    ],
    "kennzahlen": [
        {"key": "menge", "label": "Verkaufte Menge", "typ": "zahl", "decimals": 0,
         "sql": "(SELECT CAST(ISNULL(SUM(rp.fAnzahl), 0) AS DECIMAL(18,2)) "
                + _ART_VERKAUF + " AND " + _fenster("r.dErstellt") + ")"},
        {"key": "umsatz", "label": "Umsatz netto", "typ": "geld", "decimals": 2,
         "sql": "(SELECT CAST(ISNULL(SUM(rp.fAnzahl * rp.fVkNetto), 0) AS DECIMAL(18,2)) "
                + _ART_VERKAUF + " AND " + _fenster("r.dErstellt") + ")"},
        {"key": "rohertrag", "label": "Rohertrag Ware", "typ": "geld", "decimals": 2,
         "sql": "(SELECT CAST(ISNULL(SUM(rp.fAnzahl * (rp.fVkNetto - rp.fEkNetto)), 0) AS DECIMAL(18,2)) "
                + _ART_VERKAUF + " AND " + _fenster("r.dErstellt") + ")"},
        # Ohne Umsatz gibt es keine Marge (NULL), nicht 0 % – sonst stünden alle
        # unverkauften Artikel bei „Marge unter 20 %".
        {"key": "marge", "label": "Marge in %", "typ": "zahl", "decimals": 1,
         "sql": "(SELECT CAST(100.0 * SUM(rp.fAnzahl * (rp.fVkNetto - rp.fEkNetto)) "
                "/ NULLIF(SUM(rp.fAnzahl * rp.fVkNetto), 0) AS DECIMAL(18,1)) "
                + _ART_VERKAUF + " AND " + _fenster("r.dErstellt") + ")"},
        {"key": "letzter_verkauf", "label": "Letzter Verkauf", "typ": "datum",
         "sql": "(SELECT MAX(r.dErstellt) " + _ART_VERKAUF + ")"},
        # Nie verkauft zählt ab Anlage – sonst fiele genau der schlimmste
        # Ladenhüter (gekauft, nie verkauft) aus „mehr als 180 Tage" heraus.
        {"key": "tage_ohne_verkauf", "label": "Tage ohne Verkauf", "typ": "zahl", "decimals": 0,
         "sql": "DATEDIFF(DAY, ISNULL((SELECT MAX(r.dErstellt) " + _ART_VERKAUF
                + "), art.dErstelldatum), GETDATE())"},
    ],
    "verlauf": None,
    "verlauf_grund": ("Ein Artikel hat kein Datum. Für eine Entwicklung über die Zeit "
                      "die Körnung „Rechnungsposition“ wählen."),
}


# ── Körnung „Lieferantenbestellung" ──────────────────────────────────────────
# Zeilen-Bauart, aber OHNE Zeitfenster im Grundfilter: offene Bestellungen sind
# oft alt (bei HaKo 60 Stück über ein Jahr) – ein Fenster würde genau die
# Problemfälle ausblenden. Abfrage wie im Einkaufs-Cockpit; tLieferantenBestellung
# hat keine cBestellNr, die Wawi führt die eigene Nummer in cEigeneBestellnummer.
_LB_OFFENE_POS = """EXISTS (SELECT 1 FROM dbo.tLieferantenBestellungPos p
                     WHERE p.kLieferantenBestellung = lbe.kLieferantenBestellung
                       AND p.fAnzahlOffen > 0)"""

KOERNUNGEN["lieferantenbestellung"] = {
    "label": "Lieferantenbestellung", "plural": "Lieferanten-Bestellungen",
    "beschreibung": ("Eine Zeile je Bestellung beim Lieferanten, mit Liefertermin, "
                     "Verzug und offenem Wert."),
    "basis": """FROM dbo.tLieferantenBestellung lbe
LEFT JOIN dbo.tlieferant lf ON lf.kLieferant = lbe.kLieferant""",
    "grundfilter": "ISNULL(lbe.nDeleted, 0) = 0",
    "schluessel": {"sql": "lbe.kLieferantenBestellung", "name": "kLieferantenBestellung"},
    "felder": [
        {"key": "bestellung.nr", "label": "Bestellnummer", "typ": "text",
         "sql": "ISNULL(lbe.cEigeneBestellnummer, CAST(lbe.kLieferantenBestellung AS VARCHAR(20)))",
         "ausgabe": True},
        {"key": "lieferant.name", "label": "Lieferant", "typ": "text",
         "sql": ("LTRIM(RTRIM(ISNULL(lf.cFirma,'')) + CASE WHEN ISNULL(lf.cFirmenZusatz,'') = '' "
                 "OR CHARINDEX(LTRIM(RTRIM(lf.cFirmenZusatz)), ISNULL(lf.cFirma,'')) > 0 THEN '' "
                 "ELSE ' ' + LTRIM(RTRIM(lf.cFirmenZusatz)) END)"),
         "ausgabe": True},
        {"key": "bestellung.datum", "label": "Bestelldatum", "typ": "datum",
         "sql": "lbe.dErstellt", "ausgabe": True},
        {"key": "bestellung.liefertermin", "label": "Liefertermin", "typ": "datum",
         "sql": "lbe.dLieferdatum", "ausgabe": True},
        {"key": "bestellung.verzug", "label": "Tage überfällig", "typ": "zahl",
         "sql": ("CASE WHEN lbe.dLieferdatum IS NOT NULL AND lbe.dLieferdatum < GETDATE() "
                 "THEN DATEDIFF(DAY, lbe.dLieferdatum, GETDATE()) ELSE 0 END"),
         "ausgabe": True},
        {"key": "bestellung.offener_wert", "label": "Offener Wert", "typ": "geld",
         "sql": """(SELECT CAST(ISNULL(SUM(p.fAnzahlOffen * p.fEKNetto), 0) AS DECIMAL(18,2))
                   FROM dbo.tLieferantenBestellungPos p
                   WHERE p.kLieferantenBestellung = lbe.kLieferantenBestellung AND p.fAnzahlOffen > 0)""",
         "ausgabe": True},
        {"key": "bestellung.wert", "label": "Bestellwert", "typ": "geld",
         "sql": """(SELECT CAST(ISNULL(SUM(p.fMenge * p.fEKNetto), 0) AS DECIMAL(18,2))
                   FROM dbo.tLieferantenBestellungPos p
                   WHERE p.kLieferantenBestellung = lbe.kLieferantenBestellung)""",
         "ausgabe": False},
        {"key": "bestellung.offen", "label": "Offen", "typ": "ja_nein",
         "sql": f"CASE WHEN ISNULL(lbe.nManuellAbgeschlossen, 0) = 0 AND {_LB_OFFENE_POS} THEN 1 ELSE 0 END",
         "ausgabe": False, "hinweis": "Noch nicht abgeschlossen und mindestens eine Position offen."},
        {"key": "bestellung.teilgeliefert", "label": "Teilweise geliefert", "typ": "ja_nein",
         "sql": f"""CASE WHEN {_LB_OFFENE_POS} AND EXISTS (SELECT 1 FROM dbo.tLieferantenBestellungPos p
                     WHERE p.kLieferantenBestellung = lbe.kLieferantenBestellung
                       AND p.fAnzahlOffen < p.fMenge) THEN 1 ELSE 0 END""",
         "ausgabe": False},
        {"key": "lieferant.id", "label": "Lieferant (intern)", "typ": "zahl",
         "sql": "lbe.kLieferant", "ausgabe": False},
    ],
    "gruppierungen": [
        {"key": "lieferant", "label": "je Lieferant",
         "sql": [("x.lieferant_id", "kLieferant"), ("MAX(x.lieferant_name)", "Lieferant")]},
        {"key": "monat", "label": "je Monat", "verlauf": True,
         "sql": [("FORMAT(x.bestellung_datum, 'yyyy-MM')", "Monat")]},
    ],
    "kennzahlen": [
        {"key": "anzahl", "label": "Anzahl Bestellungen", "typ": "zahl", "decimals": 0,
         "sql": "COUNT(DISTINCT x.kLieferantenBestellung)"},
        {"key": "offener_wert", "label": "Summe offener Wert", "typ": "geld", "decimals": 2,
         "sql": "CAST(SUM(x.bestellung_offener_wert) AS DECIMAL(18,2))"},
        {"key": "max_verzug", "label": "Größter Verzug (Tage)", "typ": "zahl", "decimals": 0,
         "sql": "MAX(x.bestellung_verzug)"},
    ],
}


# ── Vergleichsgruppe ─────────────────────────────────────────────────────────
# „Welche Kunden kaufen dieselben Artikel wie …" ist keine Filterfrage, sondern
# eine abgeleitete Menge: erst das Sortiment einer Kundengruppe bestimmen, dann
# andere Kunden dagegen halten. Umgesetzt als zwei zusätzliche Kennzahlen der
# Körnung „Kunde", die nur verfügbar sind, wenn eine Gruppe gewählt wurde.
#
# GRUPPE ist der Platzhalter für die Kundenliste; der SQL-Bauer setzt sie als
# gebundene bzw. typgeprüfte Werte ein.
GRUPPE = "@@GRUPPE@@"

# Das Sortiment der Gruppe kommt aus den AUFTRAGSpositionen, nicht aus den
# Rechnungen: genau die interessanten Fälle bekommen Ware ohne Rechnung, ihr
# Sortiment stünde sonst gar nicht in den Daten.
#
# BEWUSSTE ASYMMETRIE: Für die Gruppe gilt KEIN Zeitfenster – ihr Sortiment ist
# eine Eigenschaft, keine Periodenzahl. Hygiene Daheim wurde zuletzt 2024/25
# beliefert; mit Fenster wäre die Artikelmenge leer und das ganze Merkmal still
# wirkungslos. Für den geprüften Kunden gilt das Fenster sehr wohl.
_GRUPPEN_ARTIKEL = f"""(SELECT DISTINCT bp9.tArtikel_kArtikel
                        FROM dbo.tBestellung b9
                        JOIN dbo.tBestellPos bp9
                          ON bp9.tBestellung_kBestellung = b9.kBestellung
                        WHERE b9.tKunde_kKunde IN ({GRUPPE})
                          AND ISNULL(b9.nStorno,0) = 0
                          AND bp9.tArtikel_kArtikel > 0)"""

VERGLEICHS_KENNZAHLEN = [
    {"key": "gemeinsame_artikel", "label": "Gemeinsame Artikel", "typ": "zahl",
     "decimals": 0, "braucht_gruppe": True,
     "hinweis": "Artikel, die dieser Kunde gekauft hat und die die Vergleichsgruppe ebenfalls bezieht.",
     "sql": f"""(SELECT COUNT(DISTINCT rp9.kArtikel)
                 FROM Rechnung.vRechnung r9
                 JOIN Rechnung.vRechnungRechnungsadresse ra9 ON ra9.kRechnung = r9.kRechnung
                 JOIN Rechnung.tRechnungPosition rp9 ON rp9.kRechnung = r9.kRechnung
                 WHERE ra9.kKunde = k.kKunde AND ISNULL(r9.nStorno,0) = 0
                   AND {_fenster("r9.dErstellt")}
                   AND rp9.kArtikel IN {_GRUPPEN_ARTIKEL})"""},

    {"key": "gemeinsamer_umsatz", "label": "Umsatz mit diesen Artikeln", "typ": "geld",
     "decimals": 2, "braucht_gruppe": True,
     "hinweis": "Netto-Umsatz dieses Kunden mit dem Sortiment der Vergleichsgruppe.",
     "sql": f"""(SELECT CAST(ISNULL(SUM(rp9.fAnzahl * rp9.fVkNetto), 0) AS DECIMAL(18,2))
                 FROM Rechnung.vRechnung r9
                 JOIN Rechnung.vRechnungRechnungsadresse ra9 ON ra9.kRechnung = r9.kRechnung
                 JOIN Rechnung.tRechnungPosition rp9 ON rp9.kRechnung = r9.kRechnung
                 WHERE ra9.kKunde = k.kKunde AND ISNULL(r9.nStorno,0) = 0
                   AND {_fenster("r9.dErstellt")}
                   AND rp9.kArtikel IN {_GRUPPEN_ARTIKEL})"""},
]

KOERNUNGEN["kunde"]["kennzahlen"].extend(VERGLEICHS_KENNZAHLEN)
# Die Gruppe selbst gehört nicht in ihre eigene Ergebnisliste – sonst stünde
# Hygiene Daheim an der Spitze der Kunden, die kaufen wie Hygiene Daheim.
KOERNUNGEN["kunde"]["gruppe_ausschluss"] = f"k.kKunde NOT IN ({GRUPPE})"
KOERNUNGEN["kunde"]["vergleichsgruppe"] = {
    "lookup": "kunde",
    "label": "Vergleichsgruppe",
    "beschreibung": ("Kunden, deren Sortiment als Maßstab dient. Ihr Sortiment wird "
                     "ohne Zeitfenster bestimmt und sie selbst aus dem Ergebnis "
                     "genommen."),
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
            # Verlauf gibt es dort, wo eine Gruppierung „je Monat" existiert.
            "verlauf": any(g.get("verlauf") for g in k.get("gruppierungen") or []),
            "verlauf_grund": k.get("verlauf_grund"),
            "vergleichsgruppe": k.get("vergleichsgruppe"),
            "gruppierungen": [{"key": g["key"], "label": g["label"],
                               "verlauf": bool(g.get("verlauf"))}
                              for g in k.get("gruppierungen") or []],
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


def gruppierung(koernung: str, key: str) -> dict | None:
    k = KOERNUNGEN.get(koernung)
    if not k:
        return None
    return next((g for g in k.get("gruppierungen") or [] if g["key"] == key), None)


def kennzahl(koernung: str, key: str) -> dict | None:
    k = KOERNUNGEN.get(koernung)
    if not k:
        return None
    return next((m for m in k["kennzahlen"] if m["key"] == key), None)
