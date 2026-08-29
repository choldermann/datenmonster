"""Macht das Versand-Cockpit aufklappbar – es hatte als einziges gar keine Drilldowns.

Sieben Auswertungen waren Sackgassen: man sah, dass im Mai 1.200 Sendungen rausgingen
oder dass 40 länger als sieben Tage brauchten, kam aber an keine einzige davon heran.

Zwei Dinge, die bei den Detailabfragen zählen:

1. Das Formular hat einen Filter „Versandart". Die Detailliste MUSS ihn genauso
   binden wie die Übersicht, sonst zeigt der Klick mehr Sendungen, als in der
   angeklickten Zahl stecken.
2. Die Durchlaufzeit-Klassen zählen nur Sendungen mit Auftragsdatum und nicht
   negativer Dauer (`A.dErstellt IS NOT NULL`, `DauerStd >= 0`). Wer diese
   Bedingungen im Detail weglässt, bekommt mehr Zeilen als die Klasse hat.

Anwenden:
    docker cp backend/versand_drilldowns.py datenmonster-backend:/tmp/
    docker exec datenmonster-backend python /tmp/versand_drilldowns.py --anwenden
    python3 backend/versand_drilldowns.py --template templates/jtl_versand_cockpit.json --anwenden
"""
import sqlite3, json, sys

DB = "/app/uploads/datenmonster.db"
FORM_ID = 5
REST_GRENZE = 499

# Gemeinsame Verbindungen aller Sendungslisten – wortgleich zu den Übersichten.
BASIS = """    FROM dbo.tVersand V
    JOIN dbo.tLieferschein LS ON LS.kLieferschein = V.kLieferschein
    LEFT JOIN Verkauf.tAuftrag A ON A.kAuftrag = LS.kBestellung AND A.nType = 1
    LEFT JOIN dbo.tVersandArt VA ON VA.kVersandArt = V.kVersandArt
    LEFT JOIN Verkauf.vAuftragRechnungsadresse RA ON RA.kAuftrag = A.kAuftrag
    WHERE V.dVersendet >= :von AND V.dVersendet < DATEADD(DAY, 1, :bis)
      AND (:versandart_empty = 1 OR V.kVersandArt IN (:versandart))"""

# Die Wochentags-Übersicht rechnet mit @@DATEFIRST, damit Montag = 1 bleibt.
WOCHENTAG = """CASE DATEPART(WEEKDAY, DATEADD(DAY, @@DATEFIRST - 1, V.dVersendet))
             WHEN 1 THEN 'Montag' WHEN 2 THEN 'Dienstag' WHEN 3 THEN 'Mittwoch'
             WHEN 4 THEN 'Donnerstag' WHEN 5 THEN 'Freitag' WHEN 6 THEN 'Samstag'
             ELSE 'Sonntag' END"""

DAUER_KLASSE = """CASE WHEN DATEDIFF(HOUR, A.dErstellt, V.dVersendet) <= 24 THEN 'bis 24 h'
             WHEN DATEDIFF(HOUR, A.dErstellt, V.dVersendet) <= 48 THEN '24-48 h'
             WHEN DATEDIFF(HOUR, A.dErstellt, V.dVersendet) <= 72 THEN '48-72 h'
             WHEN DATEDIFF(HOUR, A.dErstellt, V.dVersendet) <= 168 THEN '3-7 Tage'
             ELSE 'über 7 Tage' END"""

SENDUNG_FELDER = ["Sortierung", "Versanddatum", "Auftragsnr", "Kunde", "Versandart",
                  "Gewicht", "Tracking", "DauerStunden", "Lieferschein", "kAuftrag"]


def sendungen(filter_: str) -> str:
    """Einzelsendungen im Zeitraum, gefiltert wie die jeweilige Übersichtszeile."""
    return f"""WITH sendung AS (
    SELECT V.dVersendet,
        ISNULL(A.cAuftragsNr, '') AS Auftragsnr,
        LTRIM(RTRIM(ISNULL(NULLIF(LTRIM(RTRIM(ISNULL(RA.cFirma,'')) + CASE WHEN ISNULL(RA.cZusatz,'') = '' OR CHARINDEX(LTRIM(RTRIM(RA.cZusatz)), ISNULL(RA.cFirma,'')) > 0 THEN '' ELSE ' ' + LTRIM(RTRIM(RA.cZusatz)) END), ''),
            ISNULL(RA.cVorname, '') + ' ' + ISNULL(RA.cName, '')))) AS Kunde,
        ISNULL(NULLIF(VA.cName, ''), 'ohne Versandart') AS Versandart,
        ISNULL(V.fGewicht, 0) AS Gewicht,
        CASE WHEN ISNULL(V.cIdentCode, '') <> '' THEN 'ja' ELSE 'nein' END AS Tracking,
        CASE WHEN A.dErstellt IS NOT NULL
             THEN DATEDIFF(HOUR, A.dErstellt, V.dVersendet) END AS DauerStunden,
        LS.cLieferscheinNr AS Lieferschein,
        CAST(ISNULL(A.kAuftrag, 0) AS VARCHAR(20)) AS kAuftrag,
        ROW_NUMBER() OVER (ORDER BY V.dVersendet DESC) AS rn
{BASIS}
      AND {filter_}
)
SELECT 0 AS Sortierung,
    CONVERT(char(10), dVersendet, 104) AS Versanddatum,
    Auftragsnr, Kunde, Versandart,
    CAST(Gewicht AS DECIMAL(18,2)) AS Gewicht,
    Tracking, DauerStunden, Lieferschein, kAuftrag
FROM sendung WHERE rn <= {REST_GRENZE}
UNION ALL
SELECT 1, '', '', CONCAT('… ', COUNT(*), ' ältere Sendungen'), '',
    CAST(SUM(Gewicht) AS DECIMAL(18,2)), '', NULL, '', ''
FROM sendung WHERE rn > {REST_GRENZE}
HAVING COUNT(*) > 0
ORDER BY Sortierung, Versanddatum DESC"""


NEUE_MAPPINGS = {
    "m_vs_monat_detail": {
        "name": "Versand – Sendungen des Monats (Detail)",
        "felder": SENDUNG_FELDER,
        "sql": sendungen("CONVERT(char(7), V.dVersendet, 120) = :monat"),
    },
    "m_vs_art_detail": {
        "name": "Versand – Sendungen der Versandart (Detail)",
        "felder": SENDUNG_FELDER,
        # Die Übersicht fasst Sendungen ohne Versandart unter „ohne Versandart".
        "sql": sendungen("ISNULL(NULLIF(VA.cName, ''), 'ohne Versandart') = :versandart_name"),
    },
    "m_vs_wochentag_detail": {
        "name": "Versand – Sendungen des Wochentags (Detail)",
        "felder": SENDUNG_FELDER,
        "sql": sendungen(f"{WOCHENTAG} = :wochentag"),
    },
    "m_vs_klasse_detail": {
        "name": "Versand – Sendungen der Durchlaufzeit-Klasse (Detail)",
        "felder": SENDUNG_FELDER,
        # Dieselben drei Zusatzbedingungen wie die Klassen-Übersicht, sonst
        # enthält das Detail Sendungen, die in keiner Klasse gezählt werden.
        "sql": sendungen("A.dErstellt IS NOT NULL\n"
                         f"      AND DATEDIFF(HOUR, A.dErstellt, V.dVersendet) >= 0\n"
                         f"      AND {DAUER_KLASSE} = :klasse"),
    },
    "m_vs_lieferschein_pos": {
        "name": "Versand – Positionen des Lieferscheins (Detail)",
        "felder": ["ArtNr", "Bezeichnung", "Menge", "Einheit", "kArtikel"],
        # `tLieferscheinPos` führt nur `kBestellPos` – Artikelnummer und
        # Bezeichnung stehen an der Auftragsposition, nicht am Lieferschein.
        "sql": """SELECT
    ISNULL(POS.cArtNr, '') AS ArtNr,
    ISNULL(POS.cName, '') AS Bezeichnung,
    CAST(LP.fAnzahl AS DECIMAL(18,2)) AS Menge,
    ISNULL(POS.cEinheit, '') AS Einheit,
    CAST(ISNULL(POS.kArtikel, 0) AS VARCHAR(20)) AS kArtikel
FROM dbo.tLieferscheinPos LP
JOIN dbo.tLieferschein LS ON LS.kLieferschein = LP.kLieferschein
LEFT JOIN Verkauf.tAuftragPosition POS ON POS.kAuftragPosition = LP.kBestellPos
WHERE LS.cLieferscheinNr = :lieferschein
ORDER BY LP.kLieferscheinPos""",
    },
}

AUFTRAGSPOSITIONEN = "m_auftrag_pos_detail"     # bestehendes Mapping 119
EBENE_AUFTRAG = {"param": "kAuftrag", "key_column": "kAuftrag",
                 "title": "Positionen des Auftrags"}

DRILLDOWNS = {
    # Übersichten → Einzelsendungen → Auftragspositionen
    "w_vs_line_monat":   ("m_vs_monat_detail", "Monat", "monat",
                          "Sendungen dieses Monats", True),
    "w_vs_tbl_art":      ("m_vs_art_detail", "Versandart", "versandart_name",
                          "Sendungen dieser Versandart", True),
    "w_vs_bar_wt":       ("m_vs_wochentag_detail", "Wochentag", "wochentag",
                          "Sendungen dieses Wochentags", True),
    "w_vs_bar_klassen":  ("m_vs_klasse_detail", "Klasse", "klasse",
                          "Sendungen dieser Klasse", True),
    # Zeilen sind schon Einzelbelege → direkt eine Ebene tiefer
    "w_vs_tbl_lang":     (AUFTRAGSPOSITIONEN, "kAuftrag", "kAuftrag",
                          "Positionen des Auftrags", False),
    "w_vs_tbl_ohne":     (AUFTRAGSPOSITIONEN, "kAuftrag", "kAuftrag",
                          "Positionen des Auftrags", False),
    "w_vs_tbl_rueck":    ("m_vs_lieferschein_pos", "Lieferschein", "lieferschein",
                          "Positionen des Lieferscheins", False),
}

# Die drei Belegtabellen führen den Auftrags-/Lieferscheinschlüssel noch nicht mit.
UEBERSICHT_ERWEITERN = {
    "m_vs_langsam": {
        "name_teil": "Längste Durchlaufzeiten",
        "anker": "    X.Versandart AS Versandart",
        "zusatz": ",\n    CAST(X.kAuftrag AS VARCHAR(20)) AS kAuftrag",
        "feld": "kAuftrag",
    },
    "m_vs_ohne_tracking": {
        "name_teil": "Sendungen ohne Tracking",
        "anker": "    ISNULL(NULLIF(VA.cName, ''), 'ohne Versandart') AS Versandart,",
        "zusatz": "\n    CAST(ISNULL(A.kAuftrag, 0) AS VARCHAR(20)) AS kAuftrag,",
        "feld": "kAuftrag",
    },
}

# Wiederverwendet: die Auftragspositionen gibt es schon (Mapping 119).
BESTEHENDE = {AUFTRAGSPOSITIONEN: "Cockpit – Auftragspositionen (Detail)"}
EBENE2 = {"mapping": AUFTRAGSPOSITIONEN, **EBENE_AUFTRAG}

if __name__ == "__main__":
    import drilldown_werkzeug
    drilldown_werkzeug.hauptlauf(sys.modules[__name__], FORM_ID)
