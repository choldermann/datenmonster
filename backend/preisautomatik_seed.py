# -*- coding: utf-8 -*-
"""Legt die Kandidaten-Auswertung der Preisautomatik an bzw. bringt sie auf Stand.

Was ein Ladenhüter ist, steht bewusst in einem ganz normalen Mapping und nicht im
Code – so ist es im Mapping-Editor nachvollziehbar und änderbar. Die Definition
(Bestand und letzter Warenausgang aus dbo.vArtikelHistorie) ist dieselbe wie im
Lager-Cockpit; ergänzt sind der aktuelle Preis je Kundengruppe aus JTLs eigener
View Preisliste.vPreislisteNetto und die Frage, ob schon ein Sonderpreis läuft.

Nie verkaufte Artikel werden nicht automatisch zum tiefsten Rabatt: Für sie zählt
die Liegezeit seit dem ersten Lagerzugang, sonst bekäme frisch eingebuchte Ware
sofort den höchsten Nachlass.

    docker cp backend/preisautomatik_seed.py datenmonster-backend:/tmp/
    docker exec datenmonster-backend python /tmp/preisautomatik_seed.py --projekt 1 --verbindung 3
"""
import argparse
import json
import sqlite3

DB = "/app/uploads/datenmonster.db"
NAME = "Preisautomatik – Ladenhüter-Kandidaten"

SQL = r"""WITH bestand AS (
    SELECT H.kArtikel, SUM(H.fAnzahl) AS Menge
    FROM dbo.vArtikelHistorie H
    WHERE H.dGebucht < DATEADD(DAY, 1, :bis)
    GROUP BY H.kArtikel HAVING SUM(H.fAnzahl) > 0
), ek AS (
    SELECT kArtikel, fEKNetto FROM (
        SELECT H.kArtikel, H.fEKNetto,
            ROW_NUMBER() OVER (PARTITION BY H.kArtikel ORDER BY H.dGebucht DESC) AS rn
        FROM dbo.vArtikelHistorie H
        WHERE H.dGebucht < DATEADD(DAY, 1, :bis)
          AND H.cTyp = 'Eingang' AND ISNULL(H.fEKNetto, 0) > 0
    ) x WHERE rn = 1
), zugang AS (
    SELECT H.kArtikel, MIN(H.dGebucht) AS ErsterZugang
    FROM dbo.vArtikelHistorie H
    WHERE H.cTyp = 'Eingang' AND H.dGebucht < DATEADD(DAY, 1, :bis)
    GROUP BY H.kArtikel
), abgang AS (
    SELECT H.kArtikel, MAX(H.dGebucht) AS LetzterAbgang
    FROM dbo.vArtikelHistorie H
    WHERE H.cTyp = 'Ausgang' AND H.cBuchungsart = 'Warenausgang'
      AND H.dGebucht < DATEADD(DAY, 1, :bis)
    GROUP BY H.kArtikel
), je_artikel AS (
    SELECT A.kArtikel, A.cArtNr, ISNULL(AB.cName, '') AS Artikel,
        ISNULL(NULLIF(W.cName, ''), '') AS Warengruppe,
        b.Menge AS Bestand, COALESCE(ek.fEKNetto, A.fEKNetto, 0) AS EK,
        ab2.LetzterAbgang, zu.ErsterZugang,
        -- Nie verkauft ist nicht automatisch ein Ladenhüter: für Artikel ohne
        -- Abgang zählt, wie lange sie schon im Lager liegen. Sonst bekäme
        -- frisch eingebuchte Ware sofort den tiefsten Rabatt.
        COALESCE(DATEDIFF(DAY, ab2.LetzterAbgang, :bis),
                 DATEDIFF(DAY, zu.ErsterZugang, :bis), 0) AS TageOhneAbgang,
        CASE WHEN ab2.LetzterAbgang IS NULL THEN 1 ELSE 0 END AS NieVerkauft
    FROM bestand b
    JOIN dbo.tArtikel A ON A.kArtikel = b.kArtikel AND A.cAktiv = 'Y' AND A.kVaterArtikel = 0
    LEFT JOIN dbo.tArtikelBeschreibung AB ON AB.kArtikel = A.kArtikel
     AND AB.kSprache = 1 AND AB.kPlattform = 1 AND AB.kShop = 0
    LEFT JOIN dbo.tWarengruppe W ON W.kWarengruppe = A.kWarengruppe
    LEFT JOIN ek ON ek.kArtikel = b.kArtikel
    LEFT JOIN abgang ab2 ON ab2.kArtikel = b.kArtikel
    LEFT JOIN zugang zu ON zu.kArtikel = b.kArtikel
)
SELECT
    J.kArtikel, J.cArtNr AS ArtNr, J.Artikel, J.Warengruppe,
    CAST(J.Bestand AS DECIMAL(18,2)) AS Bestand,
    CAST(J.EK AS DECIMAL(18,4)) AS EKNetto,
    CAST(J.Bestand * J.EK AS DECIMAL(18,2)) AS GebundenesKapital,
    ISNULL(CONVERT(varchar(10), J.LetzterAbgang, 104), '') AS LetzterAbgang,
    ISNULL(CONVERT(varchar(10), J.ErsterZugang, 104), '') AS ErsterZugang,
    J.TageOhneAbgang, J.NieVerkauft,
    PL.kKundenGruppe, KG.cName AS Kundengruppe, PL.kShop,
    CAST(PL.fNettoPreis AS DECIMAL(18,4)) AS PreisAktuell,
    CASE WHEN EXISTS (SELECT 1 FROM dbo.tPreis P JOIN dbo.tPreisDetail D ON D.kPreis = P.kPreis
                      WHERE P.kArtikel = J.kArtikel AND P.kKundenGruppe = PL.kKundenGruppe
                        AND P.kShop = PL.kShop AND P.kKunde = 0 AND D.nAnzahlAb = 0)
         THEN 'tPreisDetail' ELSE 'fVKNetto' END AS PreisQuelle,
    CASE WHEN EXISTS (
        SELECT 1 FROM dbo.tArtikelSonderpreis S
        JOIN dbo.tSonderpreise SP ON SP.kArtikelSonderpreis = S.kArtikelSonderpreis
        WHERE S.kArtikel = J.kArtikel AND S.nAktiv = 1
          AND SP.kKundenGruppe = PL.kKundenGruppe AND SP.kShop = PL.kShop
          AND (S.nIstDatum = 0 OR (S.dStart <= GETDATE() AND S.dEnde >= GETDATE()))
    ) THEN 1 ELSE 0 END AS SonderpreisAktiv
FROM je_artikel J
JOIN Preisliste.vPreislisteNetto PL ON PL.kArtikel = J.kArtikel AND PL.nAnzahlAb = 0
JOIN dbo.tkundenGruppe KG ON KG.kKundenGruppe = PL.kKundenGruppe
WHERE J.TageOhneAbgang >= :tage_min AND PL.kShop = 0
  AND PL.fNettoPreis > 0
ORDER BY J.Bestand * J.EK DESC"""

FELDER = [
    [
        "kArtikel",
        "int"
    ],
    [
        "ArtNr",
        "string"
    ],
    [
        "Artikel",
        "string"
    ],
    [
        "Warengruppe",
        "string"
    ],
    [
        "Bestand",
        "float"
    ],
    [
        "EKNetto",
        "float"
    ],
    [
        "GebundenesKapital",
        "float"
    ],
    [
        "LetzterAbgang",
        "string"
    ],
    [
        "ErsterZugang",
        "string"
    ],
    [
        "TageOhneAbgang",
        "int"
    ],
    [
        "NieVerkauft",
        "int"
    ],
    [
        "kKundenGruppe",
        "int"
    ],
    [
        "Kundengruppe",
        "string"
    ],
    [
        "kShop",
        "int"
    ],
    [
        "PreisAktuell",
        "float"
    ],
    [
        "PreisQuelle",
        "string"
    ],
    [
        "SonderpreisAktiv",
        "int"
    ]
]


def feld(name, typ):
    return {"source_field": name, "target_field": name, "target_type": typ,
            "source_dataset_id": "__sql__sql1",
            "transformer": {"type": "direct", "source_field": name}}


def anlegen(projekt: int, verbindung: int, anwenden: bool):
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    knoten = [{"id": "sql1", "x": 120, "y": 40, "width": 380, "height": 260,
               "connection_id": verbindung, "sql": SQL, "mode": "transform",
               "output_field": "sql_1",
               "output_fields": [n for n, _ in FELDER]}]
    ziele = [{"id": "t1", "name": NAME, "target_type": "dataset",
              "target_connection_id": None, "target_table": "",
              "target_write_mode": "replace", "target_options": {},
              "fields": [feld(n, t) for n, t in FELDER]}]
    row = c.execute("SELECT id FROM mappings WHERE name = ? AND project_id = ?",
                    (NAME, projekt)).fetchone()
    if row:
        print(f"aktualisiere Mapping M{row['id']}")
        if anwenden:
            c.execute("UPDATE mappings SET sql_nodes = ?, targets = ?, "
                      "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                      (json.dumps(knoten, ensure_ascii=False),
                       json.dumps(ziele, ensure_ascii=False), row["id"]))
    else:
        print("lege Mapping neu an")
        if anwenden:
            c.execute(
                "INSERT INTO mappings (name, project_id, canvas_nodes, joins, fields, "
                "transform_nodes, constant_nodes, agg_nodes, rest_nodes, lookup_nodes, "
                "calc_nodes, switch_nodes, sort_nodes, python_nodes, ai_nodes, expr_nodes, "
                "quality_nodes, param_nodes, sql_nodes, targets, target_write_mode, "
                "target_options, created_at, updated_at) "
                "VALUES (?, ?, '[]', '[]', '[]', '[]', '[]', '[]', '[]', '[]', '[]', '[]', "
                "'[]', '[]', '[]', '[]', '[]', '[]', ?, ?, 'insert', '{}', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (NAME, projekt, json.dumps(knoten, ensure_ascii=False),
                 json.dumps(ziele, ensure_ascii=False)))
    if anwenden:
        c.commit()
    c.close()
    print("angewandt" if anwenden else "Trockenlauf – mit --anwenden schreiben")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--projekt", type=int, required=True)
    p.add_argument("--verbindung", type=int, required=True,
                   help="JTL-Verbindung, gegen die das SQL im Editor läuft "
                        "(zur Laufzeit ersetzt der Mandant sie ohnehin)")
    p.add_argument("--anwenden", action="store_true")
    a = p.parse_args()
    anlegen(a.projekt, a.verbindung, a.anwenden)
