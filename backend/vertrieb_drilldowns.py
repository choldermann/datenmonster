"""Macht die vier Diagramme des Vertriebs-Cockpits aufklappbar.

Die Tabellen führen längst weiter, die Diagramme waren Sackgassen: der
Auftragseingang je Monat, der Backlog nach Alter, die Angebote je Monat und die
Bundesland-Auswertung (Tabelle wie Balken).

Anwenden:
    docker cp backend/vertrieb_drilldowns.py datenmonster-backend:/tmp/
    docker exec datenmonster-backend python /tmp/vertrieb_drilldowns.py --anwenden
    python3 backend/vertrieb_drilldowns.py --template templates/jtl_vertrieb_cockpit.json --anwenden
"""
import sys
sys.path.insert(0, "/tmp")
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from drilldown_werkzeug import mit_sammelzeile, hauptlauf

FORM_ID = 3

PLATTFORM = ("(:plattform_empty = 1 OR A.kPlattform IN "
             "(SELECT nPlattform FROM dbo.tPlattform WHERE nTyp IN (:plattform)))")

# Wortgleich mit „Vertrieb – Auftragseingang je Bundesland". Weicht sie ab, zeigt
# der Klick andere Aufträge als die Zeile – deshalb prüft pruefen() das nach.
BUNDESLAND = """CASE
            WHEN UPPER(ISNULL(RA.cLand, '')) NOT IN ('', 'DE', 'D', 'DEU', 'DEUTSCHLAND', 'GERMANY') THEN '(Ausland)'
            WHEN TRY_CONVERT(INT, LEFT(RA.cPLZ, 2)) IS NULL THEN '(ohne PLZ)'
            WHEN TRY_CONVERT(INT, LEFT(RA.cPLZ, 2)) IN (1,2,4,8,9) THEN 'Sachsen'
            WHEN TRY_CONVERT(INT, LEFT(RA.cPLZ, 2)) IN (3,15,16) THEN 'Brandenburg'
            WHEN TRY_CONVERT(INT, LEFT(RA.cPLZ, 2)) IN (6,39) THEN 'Sachsen-Anhalt'
            WHEN TRY_CONVERT(INT, LEFT(RA.cPLZ, 2)) IN (7,98,99) THEN 'Thüringen'
            WHEN TRY_CONVERT(INT, LEFT(RA.cPLZ, 2)) IN (10,11,12,13,14) THEN 'Berlin'
            WHEN TRY_CONVERT(INT, LEFT(RA.cPLZ, 2)) IN (17,18,19) THEN 'Mecklenburg-Vorpommern'
            WHEN TRY_CONVERT(INT, LEFT(RA.cPLZ, 2)) IN (20,21,22) THEN 'Hamburg'
            WHEN TRY_CONVERT(INT, LEFT(RA.cPLZ, 2)) IN (23,24,25) THEN 'Schleswig-Holstein'
            WHEN TRY_CONVERT(INT, LEFT(RA.cPLZ, 2)) IN (26,27,29,30,31,37,38,49) THEN 'Niedersachsen'
            WHEN TRY_CONVERT(INT, LEFT(RA.cPLZ, 2)) = 28 THEN 'Bremen'
            WHEN TRY_CONVERT(INT, LEFT(RA.cPLZ, 2)) IN (32,33,40,41,42,44,45,46,47,48,50,51,52,53,57,58,59) THEN 'Nordrhein-Westfalen'
            WHEN TRY_CONVERT(INT, LEFT(RA.cPLZ, 2)) IN (34,35,36,60,61,63,64,65) THEN 'Hessen'
            WHEN TRY_CONVERT(INT, LEFT(RA.cPLZ, 2)) IN (54,55,56,67) THEN 'Rheinland-Pfalz'
            WHEN TRY_CONVERT(INT, LEFT(RA.cPLZ, 2)) = 66 THEN 'Saarland'
            WHEN TRY_CONVERT(INT, LEFT(RA.cPLZ, 2)) IN (68,69,88) OR TRY_CONVERT(INT, LEFT(RA.cPLZ, 2)) BETWEEN 70 AND 79 THEN 'Baden-Württemberg'
            WHEN TRY_CONVERT(INT, LEFT(RA.cPLZ, 2)) BETWEEN 80 AND 87 OR TRY_CONVERT(INT, LEFT(RA.cPLZ, 2)) BETWEEN 89 AND 97 THEN 'Bayern'
            ELSE '(unbekannt)'
        END"""

AUFTRAG_FELDER = ["Sortierung", "Auftragsnr", "Datum", "Kunde", "Wert",
                  "Positionen", "Status", "kAuftrag"]


def auftraege(typ_filter: str, zusatz: str, ohne_zeitraum: bool = False) -> str:
    """Auftrags-/Angebotsliste. `typ_filter` unterscheidet Auftrag (1) und Angebot (0)."""
    zeitraum = "" if ohne_zeitraum else \
        "\n      AND A.dErstellt >= :von AND A.dErstellt < DATEADD(DAY, 1, :bis)"
    return f"""WITH vorgang AS (
    SELECT A.cAuftragsNr AS Auftragsnr, A.dErstellt,
        LTRIM(RTRIM(ISNULL(NULLIF(LTRIM(RTRIM(ISNULL(RA.cFirma,'')) + CASE WHEN ISNULL(RA.cZusatz,'') = '' OR CHARINDEX(LTRIM(RTRIM(RA.cZusatz)), ISNULL(RA.cFirma,'')) > 0 THEN '' ELSE ' ' + LTRIM(RTRIM(RA.cZusatz)) END), ''),
            ISNULL(RA.cVorname, '') + ' ' + ISNULL(RA.cName, '')))) AS Kunde,
        E.fWertNetto AS Wert,
        (SELECT COUNT(*) FROM Verkauf.tAuftragPosition P
          WHERE P.kAuftrag = A.kAuftrag) AS Positionen,
        CASE WHEN A.nKomplettAusgeliefert = 1 THEN 'ausgeliefert'
             WHEN A.nStorno = 1 THEN 'storniert' ELSE 'offen' END AS Status,
        CAST(A.kAuftrag AS VARCHAR(20)) AS kAuftrag,
        ROW_NUMBER() OVER (ORDER BY E.fWertNetto DESC) AS rn
    FROM Verkauf.tAuftrag A
    JOIN Verkauf.tAuftragEckdaten E ON E.kAuftrag = A.kAuftrag
    LEFT JOIN Verkauf.vAuftragRechnungsadresse RA ON RA.kAuftrag = A.kAuftrag
    WHERE {typ_filter}
      AND {PLATTFORM}{zeitraum}
      AND {zusatz}
)
""" + mit_sammelzeile(
        "vorgang",
        """Auftragsnr, CONVERT(char(10), dErstellt, 104) AS Datum, Kunde,
    CAST(Wert AS DECIMAL(18,2)) AS Wert, Positionen, Status, kAuftrag""",
        """'', '', CONCAT('… ', COUNT(*), ' weitere Vorgänge'),
    CAST(SUM(Wert) AS DECIMAL(18,2)), NULL, '', ''""",
        "Wert DESC")


NEUE_MAPPINGS = {
    "m_ve_monat_detail": {
        "name": "Vertrieb – Aufträge des Monats (Detail)",
        "felder": AUFTRAG_FELDER,
        "sql": auftraege("A.nType = 1 AND A.nStorno = 0",
                         "CONVERT(char(7), A.dErstellt, 120) = :monat"),
    },
    "m_ve_angebot_detail": {
        "name": "Vertrieb – Angebote des Monats (Detail)",
        "felder": AUFTRAG_FELDER,
        # Angebote sind nType = 0 (siehe „Angebote je Monat").
        "sql": auftraege("A.nType = 0", "CONVERT(char(7), A.dErstellt, 120) = :monat"),
    },
    "m_ve_alter_detail": {
        "name": "Vertrieb – Offene Aufträge der Altersklasse (Detail)",
        "felder": AUFTRAG_FELDER,
        # Der Backlog kennt KEINEN Zeitraum – er zählt alle nicht komplett
        # ausgelieferten Aufträge, egal wann sie erfasst wurden. Ein Zeitraum im
        # Detail würde die Liste kürzer machen als die angeklickte Säule.
        "sql": auftraege(
            "A.nType = 1 AND A.nStorno = 0 AND A.nKomplettAusgeliefert = 0 AND ISNULL(A.kVorgangsstatus, 1) <> 2",
            """CASE WHEN DATEDIFF(DAY, A.dErstellt, GETDATE()) <= 7  THEN 'bis 7 Tage'
             WHEN DATEDIFF(DAY, A.dErstellt, GETDATE()) <= 14 THEN '8-14 Tage'
             WHEN DATEDIFF(DAY, A.dErstellt, GETDATE()) <= 30 THEN '15-30 Tage'
             WHEN DATEDIFF(DAY, A.dErstellt, GETDATE()) <= 60 THEN '31-60 Tage'
             ELSE 'über 60 Tage' END = :klasse""", ohne_zeitraum=True),
    },
    "m_ve_bundesland_detail": {
        "name": "Vertrieb – Aufträge des Bundeslands (Detail)",
        "felder": AUFTRAG_FELDER,
        "sql": auftraege("A.nType = 1 AND A.nStorno = 0", f"{BUNDESLAND} = :bundesland"),
    },
}

BESTEHENDE = {"m_auftrag_pos": "Cockpit – Auftragspositionen (Detail)"}
EBENE2 = {"mapping": "m_auftrag_pos", "param": "kAuftrag", "key_column": "kAuftrag",
          "title": "Positionen des Vorgangs"}

DRILLDOWNS = {
    "w_ve_line_monat":     ("m_ve_monat_detail", "Monat", "monat",
                            "Aufträge dieses Monats", True),
    "w_ve_line_angebot":   ("m_ve_angebot_detail", "Monat", "monat",
                            "Angebote dieses Monats", True),
    "w_ve_bar_alter":      ("m_ve_alter_detail", "Altersklasse", "klasse",
                            "Offene Aufträge dieser Altersklasse", True),
    "w_ve_tbl_bundesland": ("m_ve_bundesland_detail", "Bundesland", "bundesland",
                            "Aufträge dieses Bundeslands", True),
    "w_ve_bar_bundesland": ("m_ve_bundesland_detail", "Bundesland", "bundesland",
                            "Aufträge dieses Bundeslands", True),
}


def pruefen():
    """Warnt, wenn die Bundesland-Herleitung von der Übersicht abgewichen ist."""
    import sqlite3, json
    db = sqlite3.connect("/app/uploads/datenmonster.db")
    treffer = db.execute("select sql_nodes from mappings where name like "
                         "'%Auftragseingang je Bundesland%'").fetchone()
    if not treffer:
        return
    sql = json.loads(treffer[0])[0]["sql"]
    kern = BUNDESLAND.split("\n", 1)[1]
    if kern not in sql:
        raise SystemExit("Die Bundesland-Herleitung weicht von der Übersicht ab – "
                         "erst angleichen, sonst zeigt der Klick andere Aufträge.")


if __name__ == "__main__":
    if "--template" not in sys.argv:
        pruefen()
    hauptlauf(sys.modules[__name__], FORM_ID)
