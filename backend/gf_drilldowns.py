"""Macht das GF-Cockpit weitgehend aufklappbar.

Neun Auswertungen führten schon weiter, über dreißig nicht. Wer im Umsatzverlauf
einen Einbruch sah, kam an keine einzige Rechnung dieses Monats heran; wer eine
Warengruppe verlieren sah, an keinen Artikel.

Vier Bausteine tragen die meisten Klicks: Rechnungen eines Monats, Rechnungen
eines Kunden, Rechnungen mit einem Artikel und Artikel einer Warengruppe. Dazu
die vier Retouren-Sichten. Zweite Ebene ist überall die Positionsliste.

WICHTIG – der Filter auf gesperrte Kunden: die Verlaufs- und Warengruppen-
Auswertungen filtern ihn NICHT (sie sind Summen), die Listentabellen schon.
Ein Detail muss es machen wie seine Übersicht, sonst weicht die Summe ab.

Anwenden:
    docker cp backend/gf_drilldowns.py datenmonster-backend:/tmp/
    docker exec datenmonster-backend python /tmp/gf_drilldowns.py --anwenden
    python3 backend/gf_drilldowns.py --template templates/jtl_gf_cockpit.json --anwenden
"""
import sys
sys.path.insert(0, "/tmp")
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from drilldown_werkzeug import mit_sammelzeile, hauptlauf

FORM_ID = 1

# Gültige Rechnungen, Plattformfilter des Formulars – wortgleich zu den Übersichten.
RECHNUNGEN = ("(SELECT * FROM Rechnung.vRechnung WHERE ISNULL(nStorno,0) = 0 "
              "AND (:plattform_empty = 1 OR kPlattform IN "
              "(SELECT nPlattform FROM dbo.tPlattform WHERE nTyp IN (:plattform)))) RE")
KUNDE = ("ISNULL(NULLIF(RA.cFirma, ''), LTRIM(RTRIM(ISNULL(RA.cVorname,'') "
         "+ ' ' + ISNULL(RA.cName,''))))")

BELEG_FELDER = ["Sortierung", "Rechnungsnr", "Datum", "Kunde", "Umsatz",
                "Rohertrag", "Positionen", "kRechnung"]


def rechnungen(zusatz: str) -> str:
    """Rechnungsliste im Zeitraum, gefiltert wie die angeklickte Zeile."""
    return f"""WITH beleg AS (
    SELECT RE.kRechnung, MAX(RE.cRechnungsnr) AS Rechnungsnr,
        MAX(RE.dErstellt) AS dErstellt,
        MAX({KUNDE}) AS Kunde,
        SUM(POS.fAnzahl * POS.fVkNetto) AS Umsatz,
        SUM(POS.fAnzahl * (POS.fVkNetto - COALESCE(NULLIF(POS.fEkNetto, 0), A.fEKNetto, 0))) AS Rohertrag,
        COUNT(*) AS Positionen
    FROM {RECHNUNGEN}
    JOIN Rechnung.tRechnungPosition POS ON POS.kRechnung = RE.kRechnung
    LEFT JOIN dbo.tArtikel A ON A.cArtNr = POS.cArtNr
    LEFT JOIN Rechnung.vRechnungRechnungsadresse RA ON RA.kRechnung = RE.kRechnung
    WHERE {zusatz}
    GROUP BY RE.kRechnung
), sortiert AS (
    SELECT *, ROW_NUMBER() OVER (ORDER BY Umsatz DESC) AS rn FROM beleg
)
""" + mit_sammelzeile(
        "sortiert",
        """Rechnungsnr, CONVERT(char(10), dErstellt, 104) AS Datum, Kunde,
    CAST(Umsatz AS DECIMAL(18,2)) AS Umsatz,
    CAST(Rohertrag AS DECIMAL(18,2)) AS Rohertrag,
    Positionen, CAST(kRechnung AS VARCHAR(20)) AS kRechnung""",
        """'', '', CONCAT('… ', COUNT(*), ' weitere Rechnungen'),
    CAST(SUM(Umsatz) AS DECIMAL(18,2)),
    CAST(SUM(Rohertrag) AS DECIMAL(18,2)), SUM(Positionen), ''""",
        "Umsatz DESC")


ARTIKEL_FELDER = ["Sortierung", "ArtNr", "Artikel", "Menge", "Umsatz",
                  "Rohertrag", "Rechnungen", "kArtikel"]

RETOURE_FELDER = ["Sortierung", "Datum", "Retourennr", "ArtNr", "Artikel",
                  "Menge", "Wert", "Grund", "Kunde"]


def retouren(quelle: str, zusatz: str, zeitraum: str = None) -> str:
    """Einzelne Retourenpositionen – die Ebene unter jeder Retouren-Summe."""
    zeit = zeitraum or "R.dErstellt >= :von AND R.dErstellt < DATEADD(DAY, 1, :bis)"
    kunde = ("ISNULL(NULLIF(LTRIM(RTRIM(ISNULL(NULLIF(R.cKundeFirma, ''), "
             "LTRIM(RTRIM(ISNULL(R.cVorname, '') + ' ' + ISNULL(R.cName, '')))))), ''), "
             "'(unbekannt)')") if quelle.startswith("RM.lvRetoure ") else "''"
    return f"""WITH pos AS (
    SELECT R.dErstellt, R.cRetoureNr AS Retourennr,
        ISNULL(POS.cArtNr, '') AS ArtNr, ISNULL(POS.cName, '') AS Artikel,
        POS.fAnzahl AS Menge, POS.fAnzahl * POS.fVKNetto AS Wert,
        ISNULL(NULLIF(LTRIM(RTRIM(POS.Grund)), ''), '(ohne Angabe)') AS Grund,
        {kunde} AS Kunde,
        ROW_NUMBER() OVER (ORDER BY POS.fAnzahl * POS.fVKNetto DESC) AS rn
    FROM {quelle}
    JOIN RM.lvRetourePosition POS ON POS.kRMRetoure = R.kRMRetoure
    WHERE {zeit}
      AND {zusatz}
)
""" + mit_sammelzeile(
        "pos",
        """CONVERT(char(10), dErstellt, 104) AS Datum, Retourennr, ArtNr, Artikel,
    CAST(Menge AS DECIMAL(18,2)) AS Menge,
    CAST(Wert AS DECIMAL(18,2)) AS Wert, Grund, Kunde""",
        """'', '', '', CONCAT('… ', COUNT(*), ' weitere Positionen'),
    CAST(SUM(Menge) AS DECIMAL(18,2)),
    CAST(SUM(Wert) AS DECIMAL(18,2)), '', ''""",
        "Wert DESC")


NEUE_MAPPINGS = {
    # Drei Monats-Details statt einem: die drei Verlaufsdiagramme haben
    # unterschiedliche Zeitfenster, und deren RÄNDER sind angeschnitten. Der
    # 24-Monats-Trend beginnt bei GETDATE() minus 24 Monate – sein erster Monat
    # deckt nur ein paar Tage ab (geprüft: 24.750 € statt 387.871 €). Ein Detail
    # ohne dieselbe Grenze zeigt den ganzen Monat und damit das Fünfzehnfache.
    "m_gf_rg_monat": {
        "name": "GF-Cockpit – Rechnungen des Monats (Detail)",
        "felder": BELEG_FELDER,
        "sql": rechnungen("CONVERT(char(7), RE.dErstellt, 120) = :monat\n"
                          "      AND RE.dErstellt >= :von AND RE.dErstellt < DATEADD(DAY, 1, :bis)"),
    },
    "m_gf_rg_monat_trend": {
        "name": "GF-Cockpit – Rechnungen des Monats, 24-Monats-Trend (Detail)",
        "felder": BELEG_FELDER,
        "sql": rechnungen("CONVERT(char(7), RE.dErstellt, 120) = :monat\n"
                          "      AND RE.dErstellt >= DATEADD(MONTH, -24, CAST(GETDATE() AS date))"),
    },
    "m_gf_rg_monat_ergebnis": {
        "name": "GF-Cockpit – Rechnungen des Monats, Ergebnisverlauf (Detail)",
        "felder": BELEG_FELDER,
        "sql": rechnungen(
            "CONVERT(char(7), RE.dErstellt, 120) = :monat\n"
            "      AND RE.dErstellt >= DATEADD(MONTH, -11, DATEFROMPARTS(YEAR(:bis), MONTH(:bis), 1))\n"
            "      AND RE.dErstellt <  DATEADD(MONTH, 1, DATEFROMPARTS(YEAR(:bis), MONTH(:bis), 1))"),
    },
    "m_gf_rg_kunde": {
        "name": "GF-Cockpit – Rechnungen des Kunden (Detail)",
        "felder": BELEG_FELDER,
        "sql": rechnungen("RE.kKunde = :kKunde\n"
                          "      AND RE.dErstellt >= :von AND RE.dErstellt < DATEADD(DAY, 1, :bis)"),
    },
    "m_gf_artikel_rg": {
        "name": "GF-Cockpit – Rechnungen mit diesem Artikel (Detail)",
        "felder": BELEG_FELDER,
        "sql": rechnungen("RE.dErstellt >= :von AND RE.dErstellt < DATEADD(DAY, 1, :bis)\n"
                          "      AND RE.kRechnung IN (SELECT P2.kRechnung "
                          "FROM Rechnung.tRechnungPosition P2 WHERE P2.cArtNr = :artnr)"),
    },
    "m_gf_wg_artikel": {
        "name": "GF-Cockpit – Artikel der Warengruppe (Detail)",
        "felder": ARTIKEL_FELDER,
        # Umsatzbasiert wie die Warengruppen-Übersicht – NICHT bestandsbasiert.
        "sql": f"""WITH je_artikel AS (
    SELECT POS.cArtNr AS ArtNr, MAX(POS.cName) AS Artikel,
        SUM(POS.fAnzahl) AS Menge,
        SUM(POS.fAnzahl * POS.fVkNetto) AS Umsatz,
        SUM(POS.fAnzahl * (POS.fVkNetto - COALESCE(NULLIF(POS.fEkNetto, 0), A.fEKNetto, 0))) AS Rohertrag,
        COUNT(DISTINCT RE.kRechnung) AS Rechnungen,
        CAST(MAX(A.kArtikel) AS VARCHAR(20)) AS kArtikel
    FROM {RECHNUNGEN}
    JOIN Rechnung.tRechnungPosition POS ON POS.kRechnung = RE.kRechnung
    LEFT JOIN dbo.tArtikel A ON A.cArtNr = POS.cArtNr
    LEFT JOIN dbo.tWarengruppe WG ON WG.kWarengruppe = A.kWarengruppe
    WHERE RE.dErstellt >= :von AND RE.dErstellt < DATEADD(DAY, 1, :bis)
      AND ISNULL(WG.cName, '') = CASE WHEN :warengruppe IN ('(ohne)', '') THEN ''
                                      ELSE :warengruppe END
    GROUP BY POS.cArtNr
), sortiert AS (
    SELECT *, ROW_NUMBER() OVER (ORDER BY Umsatz DESC) AS rn FROM je_artikel
)
""" + mit_sammelzeile(
            "sortiert",
            """ArtNr, Artikel,
    CAST(Menge AS DECIMAL(18,2)) AS Menge,
    CAST(Umsatz AS DECIMAL(18,2)) AS Umsatz,
    CAST(Rohertrag AS DECIMAL(18,2)) AS Rohertrag,
    Rechnungen, kArtikel""",
            """'', CONCAT('… ', COUNT(*), ' weitere Artikel'),
    CAST(SUM(Menge) AS DECIMAL(18,2)),
    CAST(SUM(Umsatz) AS DECIMAL(18,2)),
    CAST(SUM(Rohertrag) AS DECIMAL(18,2)), NULL, ''""",
            "Umsatz DESC"),
    },
    "m_gf_ret_grund": {
        "name": "GF-Cockpit – Retouren dieses Grundes (Detail)",
        "felder": RETOURE_FELDER,
        "sql": retouren("dbo.tRMRetoure R",
                        "ISNULL(NULLIF(LTRIM(RTRIM(POS.Grund)), ''), '(ohne Angabe)') = :grund"),
    },
    "m_gf_ret_artikel": {
        "name": "GF-Cockpit – Retouren dieses Artikels (Detail)",
        "felder": RETOURE_FELDER,
        "sql": retouren("dbo.tRMRetoure R", "POS.cArtNr = :artnr"),
    },
    "m_gf_ret_kunde": {
        "name": "GF-Cockpit – Retouren dieses Kunden (Detail)",
        "felder": RETOURE_FELDER,
        # Die Übersicht gruppiert nach dem zusammengesetzten Kundennamen, nicht
        # nach einem Schlüssel – das Detail muss denselben Ausdruck vergleichen.
        "sql": retouren("RM.lvRetoure R",
                        "ISNULL(NULLIF(LTRIM(RTRIM(ISNULL(NULLIF(R.cKundeFirma, ''), "
                        "LTRIM(RTRIM(ISNULL(R.cVorname, '') + ' ' + ISNULL(R.cName, '')))))), ''), "
                        "'(unbekannt)') = :kunde"),
    },
    "m_gf_ret_monat": {
        "name": "GF-Cockpit – Retouren dieses Monats (Detail)",
        "felder": RETOURE_FELDER,
        # Der Trend läuft 13 Monate zurück und endet an :bis – der LETZTE Monat
        # ist damit angeschnitten, wenn :bis mitten im Monat liegt. Beide Grenzen
        # müssen deshalb mit, nicht nur der Monat.
        "sql": retouren("dbo.tRMRetoure R", "1 = 1",
                        zeitraum="CONVERT(char(7), R.dErstellt, 126) = :monat\n"
                                 "      AND R.dErstellt >= DATEADD(MONTH, -12, "
                                 "DATEFROMPARTS(YEAR(:bis), MONTH(:bis), 1))\n"
                                 "      AND R.dErstellt < DATEADD(DAY, 1, :bis)"),
    },
}

BESTEHENDE = {"m_rg_pos": "Cockpit – Rechnungspositionen"}
EBENE2 = {"mapping": "m_rg_pos", "param": "kRechnung", "key_column": "kRechnung",
          "title": "Positionen der Rechnung"}

DRILLDOWNS = {
    # Verläufe → Rechnungen des Monats
    "w_line_umsatz":            ("m_gf_rg_monat", "Monat", "monat", "Rechnungen dieses Monats", True),
    "w_line_trend":             ("m_gf_rg_monat_trend", "Monat", "monat", "Rechnungen dieses Monats", True),
    "w_erg_verlauf":            ("m_gf_rg_monat_ergebnis", "Monat", "monat", "Rechnungen dieses Monats", True),
    "w_erg_verlauf_ergebnis":   ("m_gf_rg_monat_ergebnis", "Monat", "monat", "Rechnungen dieses Monats", True),
    # Kundenlisten → Rechnungen des Kunden
    "w_tbl_top_kunden":         ("m_gf_rg_kunde", "kKunde", "kKunde", "Rechnungen dieses Kunden", True),
    "w_tbl_rueckgang":          ("m_gf_rg_kunde", "kKunde", "kKunde", "Rechnungen dieses Kunden", True),
    "w_tbl_zm_kunden":          ("m_gf_rg_kunde", "kKunde", "kKunde", "Rechnungen dieses Kunden", True),
    "w_tbl_zm_verschlechterung":("m_gf_rg_kunde", "kKunde", "kKunde", "Rechnungen dieses Kunden", True),
    "w_churn":                  ("m_gf_rg_kunde", "kKunde", "kKunde", "Rechnungen dieses Kunden", True),
    "w_tbl_neukunden":          ("m_gf_rg_kunde", "kKunde", "kKunde", "Rechnungen dieses Kunden", True),
    # Warengruppen → Artikel der Warengruppe
    "w_bar_wg":                 ("m_gf_wg_artikel", "Warengruppe", "warengruppe", "Artikel dieser Warengruppe", False),
    "w_tbl_wg":                 ("m_gf_wg_artikel", "Warengruppe", "warengruppe", "Artikel dieser Warengruppe", False),
    "w_tbl_trend_wg":           ("m_gf_wg_artikel", "Warengruppe", "warengruppe", "Artikel dieser Warengruppe", False),
    # Artikellisten → Rechnungen mit diesem Artikel
    "w_tbl_top_artikel":        ("m_gf_artikel_rg", "ArtNr", "artnr", "Rechnungen mit diesem Artikel", True),
    "w_tbl_warn_ladenhueter":   ("m_gf_artikel_rg", "ArtNr", "artnr", "Rechnungen mit diesem Artikel", True),
    "w_tbl_warn_bestand":       ("m_gf_artikel_rg", "ArtNr", "artnr", "Rechnungen mit diesem Artikel", True),
    "w_tbl_warn_marge":         ("m_gf_artikel_rg", "ArtNr", "artnr", "Rechnungen mit diesem Artikel", True),
    "w_tbl_kapital_artikel":    ("m_gf_artikel_rg", "ArtNr", "artnr", "Rechnungen mit diesem Artikel", True),
    "w_tbl_kapital_umschlag":   ("m_gf_artikel_rg", "ArtNr", "artnr", "Rechnungen mit diesem Artikel", True),
    "w_tbl_abc_artikel":        ("m_gf_artikel_rg", "ArtNr", "artnr", "Rechnungen mit diesem Artikel", True),
    # Retouren
    "w_ret_gruende_tbl":        ("m_gf_ret_grund", "Grund", "grund", "Retouren dieses Grundes", False),
    "w_ret_gruende_pie":        ("m_gf_ret_grund", "Grund", "grund", "Retouren dieses Grundes", False),
    "w_ret_artikel":            ("m_gf_ret_artikel", "ArtNr", "artnr", "Retouren dieses Artikels", False),
    "w_ret_kunden":             ("m_gf_ret_kunde", "Kunde", "kunde", "Retouren dieses Kunden", False),
    "w_ret_trend":              ("m_gf_ret_monat", "Monat", "monat", "Retouren dieses Monats", False),
}

# Top-Kunden führt den Kundenschlüssel noch nicht mit.
UEBERSICHT_ERWEITERN = {
    "m_top_kunden": {
        "name_teil": "Cockpit – Top-Kunden",
        # Der Schlüssel muss zweimal durch: die innere Abfrage gruppiert bereits
        # nach X.kKunde, gibt ihn aber nicht aus, und die äußere kennt ihn dann nicht.
        "ersetzungen": [
            ("    SELECT ", " X.kKunde,"),
            ("SELECT TOP 10 Kunde,", "\n    CAST(kKunde AS VARCHAR(20)) AS kKunde,"),
        ],
        "feld": "kKunde",
    },
}

if __name__ == "__main__":
    hauptlauf(sys.modules[__name__], FORM_ID)
