"""Macht die beiden Diagramme des Einkaufs-Cockpits aufklappbar.

Die Tabellen führen längst weiter, die Diagramme waren Sackgassen: das
Bestellvolumen je Monat und der offene Bestellwert nach Verzug.

Anwenden:
    docker cp backend/einkauf_drilldowns.py datenmonster-backend:/tmp/
    docker exec datenmonster-backend python /tmp/einkauf_drilldowns.py --anwenden
    python3 backend/einkauf_drilldowns.py --template templates/jtl_einkauf_cockpit.json --anwenden
"""
import sys
sys.path.insert(0, "/tmp")
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from drilldown_werkzeug import mit_sammelzeile, hauptlauf

FORM_ID = 4

# Das Formular filtert nach Lieferant – die Detailliste muss ihn genauso binden.
LIEFERANT = "(:lieferant_empty = 1 OR B.kLieferant IN (:lieferant))"
LEBEND = "ISNULL(B.nDeleted, 0) = 0"

BESTELL_FELDER = ["Sortierung", "Bestellnr", "Datum", "Lieferant", "Liefertermin",
                  "Wert", "OffenerWert", "Status", "kLieferantenBestellung"]


def bestellungen(zusatz: str, ohne_zeitraum: bool = False) -> str:
    zeitraum = "" if ohne_zeitraum else \
        "\n      AND B.dErstellt >= :von AND B.dErstellt < DATEADD(DAY, 1, :bis)"
    return f"""WITH bestellung AS (
    -- `tLieferantenBestellung` hat keine cBestellNr; die Wawi führt die
    -- eigene Nummer in cEigeneBestellnummer, sonst bleibt nur der Schlüssel.
    SELECT ISNULL(B.cEigeneBestellnummer,
                  CAST(B.kLieferantenBestellung AS VARCHAR(20))) AS Bestellnr,
        B.dErstellt, B.dLieferdatum,
        ISNULL(NULLIF(LTRIM(RTRIM(ISNULL(L.cFirma,'')) + CASE WHEN ISNULL(L.cFirmenZusatz,'') = '' OR CHARINDEX(LTRIM(RTRIM(L.cFirmenZusatz)), ISNULL(L.cFirma,'')) > 0 THEN '' ELSE ' ' + LTRIM(RTRIM(L.cFirmenZusatz)) END), ''), 'unbekannt') AS Lieferant,
        (SELECT ISNULL(SUM(P.fMenge * P.fEKNetto), 0) FROM dbo.tLieferantenBestellungPos P
          WHERE P.kLieferantenBestellung = B.kLieferantenBestellung) AS Wert,
        (SELECT ISNULL(SUM(P.fAnzahlOffen * P.fEKNetto), 0) FROM dbo.tLieferantenBestellungPos P
          WHERE P.kLieferantenBestellung = B.kLieferantenBestellung AND P.fAnzahlOffen > 0) AS OffenerWert,
        CASE WHEN ISNULL(B.nManuellAbgeschlossen, 0) = 1 THEN 'abgeschlossen'
             WHEN B.dLieferdatum IS NULL THEN 'ohne Termin'
             WHEN B.dLieferdatum < GETDATE() THEN 'überfällig' ELSE 'im Termin' END AS Status,
        CAST(B.kLieferantenBestellung AS VARCHAR(20)) AS kLieferantenBestellung,
        ROW_NUMBER() OVER (ORDER BY B.dErstellt DESC) AS rn
    FROM dbo.tLieferantenBestellung B
    LEFT JOIN dbo.tlieferant L ON L.kLieferant = B.kLieferant
    WHERE {LEBEND} AND {LIEFERANT}{zeitraum}
      AND {zusatz}
)
""" + mit_sammelzeile(
        "bestellung",
        """Bestellnr, CONVERT(char(10), dErstellt, 104) AS Datum, Lieferant,
    ISNULL(CONVERT(char(10), dLieferdatum, 104), '') AS Liefertermin,
    CAST(Wert AS DECIMAL(18,2)) AS Wert,
    CAST(OffenerWert AS DECIMAL(18,2)) AS OffenerWert,
    Status, kLieferantenBestellung""",
        """'', '', CONCAT('… ', COUNT(*), ' ältere Bestellungen'), '',
    CAST(SUM(Wert) AS DECIMAL(18,2)),
    CAST(SUM(OffenerWert) AS DECIMAL(18,2)), '', ''""",
        "Datum DESC")


NEUE_MAPPINGS = {
    "m_ek_monat_detail": {
        "name": "Einkauf – Bestellungen des Monats (Detail)",
        "felder": BESTELL_FELDER,
        "sql": bestellungen("CONVERT(char(7), B.dErstellt, 120) = :monat"),
    },
    "m_ek_verzug_detail": {
        "name": "Einkauf – Offene Bestellungen der Verzugsklasse (Detail)",
        "felder": BESTELL_FELDER,
        # Die Verzugs-Übersicht kennt KEINEN Zeitraum und zählt nur Bestellungen
        # mit offener Position, die nicht manuell abgeschlossen sind. Beides muss
        # das Detail genauso machen – siehe die Karteileichen im Bestellwesen.
        "sql": bestellungen(
            """ISNULL(B.nManuellAbgeschlossen, 0) = 0
      AND EXISTS (SELECT 1 FROM dbo.tLieferantenBestellungPos P2
                   WHERE P2.kLieferantenBestellung = B.kLieferantenBestellung
                     AND P2.fAnzahlOffen > 0)
      AND CASE WHEN B.dLieferdatum IS NULL THEN 'ohne Termin'
             WHEN B.dLieferdatum >= GETDATE() THEN 'im Termin'
             WHEN DATEDIFF(DAY, B.dLieferdatum, GETDATE()) <= 7  THEN 'bis 7 Tage über'
             WHEN DATEDIFF(DAY, B.dLieferdatum, GETDATE()) <= 30 THEN '8-30 Tage über'
             ELSE 'über 30 Tage über' END = :klasse""", ohne_zeitraum=True),
    },
}

BESTEHENDE = {"m_ek_pos": "Einkauf – Bestellpositionen (Detail)"}
EBENE2 = {"mapping": "m_ek_pos", "param": "kLieferantenBestellung",
          "key_column": "kLieferantenBestellung", "title": "Positionen der Bestellung"}

DRILLDOWNS = {
    "w_ek_line_monat":  ("m_ek_monat_detail", "Monat", "monat",
                         "Bestellungen dieses Monats", True),
    "w_ek_bar_verzug":  ("m_ek_verzug_detail", "Verzugsklasse", "klasse",
                         "Offene Bestellungen dieser Klasse", True),
}

if __name__ == "__main__":
    hauptlauf(sys.modules[__name__], FORM_ID)
