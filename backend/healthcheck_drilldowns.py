"""Macht die letzten beiden Stellen im Stammdaten-Health-Check aufklappbar.

Das Balkendiagramm „Fehlende Angaben je Feld" war die auffälligste Sackgasse:
es zeigt, dass 1.229 Artikel keine Warentarifnummer haben, führte aber zu keinem
davon. Und die Tabelle der dürftigen Beschreibungen kam nicht zum Artikel-Detail,
obwohl es das längst gibt.

Nicht aufklappbar bleibt „Adressen ohne Kunden" – dort IST die Zeile schon der
ganze Sachverhalt, darunter liegt nichts mehr.

Anwenden:
    docker cp backend/healthcheck_drilldowns.py datenmonster-backend:/tmp/
    docker exec datenmonster-backend python /tmp/healthcheck_drilldowns.py --anwenden
    python3 backend/healthcheck_drilldowns.py --template templates/jtl_health_check.json --anwenden
"""
import sys
sys.path.insert(0, "/tmp")
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from drilldown_werkzeug import mit_sammelzeile, hauptlauf

FORM_ID = 6

# Grundgesamtheit des Health-Checks: aktive, nicht gelöschte Einzelartikel.
BASIS = """ISNULL(A.nDelete, 0) = 0 AND ISNULL(A.cAktiv, 'Y') = 'Y'
      AND ISNULL(A.nIstVater, 0) = 0"""

# Je Balken die Bedingung, die ihn zählt – wortgleich zu „Lücken je Feld".
LUECKEN = """CASE :feld
        WHEN 'EAN/Barcode'      THEN CASE WHEN ISNULL(A.cBarcode, '') = '' THEN 1 ELSE 0 END
        WHEN 'Gewicht'          THEN CASE WHEN ISNULL(A.fGewicht, 0) = 0
                                           AND ISNULL(A.fArtGewicht, 0) = 0 THEN 1 ELSE 0 END
        WHEN 'Einkaufspreis'    THEN CASE WHEN ISNULL(A.fEKNetto, 0) = 0 THEN 1 ELSE 0 END
        WHEN 'Warengruppe'      THEN CASE WHEN ISNULL(A.kWarengruppe, 0) = 0 THEN 1 ELSE 0 END
        WHEN 'Warentarifnummer' THEN CASE WHEN ISNULL(A.cTaric, '') = '' THEN 1 ELSE 0 END
        WHEN 'Herkunftsland'    THEN CASE WHEN ISNULL(A.cHerkunftsland, '') = '' THEN 1 ELSE 0 END
        WHEN 'Bezeichnung'      THEN CASE WHEN ISNULL(AB.cName, '') = '' THEN 1 ELSE 0 END
        ELSE 0 END = 1"""

NEUE_MAPPINGS = {
    "m_hc_luecke_artikel": {
        "name": "Health-Check – Artikel ohne dieses Feld (Detail)",
        "felder": ["Sortierung", "ArtNr", "Artikel", "Hersteller", "Warengruppe",
                   "EKNetto", "Bestand", "kArtikel"],
        "sql": f"""WITH artikel AS (
    SELECT A.cArtNr AS ArtNr, ISNULL(AB.cName, '') AS Artikel,
        ISNULL(H.cName, '') AS Hersteller,
        ISNULL(WG.cName, '') AS Warengruppe,
        ISNULL(A.fEKNetto, 0) AS EKNetto,
        ISNULL((SELECT SUM(LB.fLagerbestand) FROM dbo.tlagerbestand LB
                 WHERE LB.kArtikel = A.kArtikel), 0) AS Bestand,
        CAST(A.kArtikel AS VARCHAR(20)) AS kArtikel,
        ROW_NUMBER() OVER (ORDER BY A.cArtNr) AS rn
    FROM dbo.tArtikel A
    LEFT JOIN dbo.tArtikelBeschreibung AB ON AB.kArtikel = A.kArtikel
         AND AB.kSprache = 1 AND AB.kPlattform = 1 AND AB.kShop = 0
    LEFT JOIN dbo.tHersteller H ON H.kHersteller = A.kHersteller
    LEFT JOIN dbo.tWarengruppe WG ON WG.kWarengruppe = A.kWarengruppe
    WHERE {BASIS}
      AND {LUECKEN}
)
""" + mit_sammelzeile(
            "artikel",
            """ArtNr, Artikel, Hersteller, Warengruppe,
    CAST(EKNetto AS DECIMAL(18,2)) AS EKNetto,
    CAST(Bestand AS DECIMAL(18,2)) AS Bestand, kArtikel""",
            """'', CONCAT('… ', COUNT(*), ' weitere Artikel'), '', '', NULL,
    CAST(SUM(Bestand) AS DECIMAL(18,2)), ''""",
            "ArtNr"),
    },
}

BESTEHENDE = {"m_hc_artikel_detail": "Health-Check – Artikel-Detail (Drilldown)"}
EBENE2 = {"mapping": "m_hc_artikel_detail", "param": "kArtikel",
          "key_column": "kArtikel", "title": "Artikel-Detail"}

DRILLDOWNS = {
    "w_hc_bar_luecken":       ("m_hc_luecke_artikel", "Feld", "feld",
                               "Artikel ohne diese Angabe", True),
    "w_hc_tbl_beschreibung":  ("m_hc_artikel_detail", "kArtikel", "kArtikel",
                               "Artikel-Detail", False),
}

if __name__ == "__main__":
    hauptlauf(sys.modules[__name__], FORM_ID)
