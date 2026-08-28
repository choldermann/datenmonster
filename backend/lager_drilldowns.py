"""Macht die restlichen Auswertungen des Lager-Cockpits aufklappbar.

Bisher führten nur fünf Tabellen weiter (Artikel nach Kapital, Fehlmengen,
Zulauf, Umschlag, Ladenhüter, Korrektur-Artikel). Die Summenzeilen darüber –
Warengruppe, Hersteller, Warenlager, Buchungsart, Benutzer – und die drei
Diagramme waren Sackgassen: man sah, DASS eine Warengruppe 300.000 € bindet,
aber nicht, welche Artikel das sind.

WICHTIG bei jeder Detailabfrage: dieselben Joins wie in der Summenzeile. Die
Übersichten über Warengruppe/Hersteller/Lager verbinden `dbo.tArtikel` OHNE
`cAktiv = 'Y'`, die Klassen-Diagramme MIT `cAktiv = 'Y' AND kVaterArtikel = 0`.
Wer das vermischt, bekommt ein Detail, dessen Summe nicht zur angeklickten Zeile
passt – und niemand weiß dann, welche der beiden Zahlen stimmt.

Anwenden:
    docker cp backend/lager_drilldowns.py datenmonster-backend:/tmp/
    docker exec datenmonster-backend python /tmp/lager_drilldowns.py --anwenden
    python3 backend/lager_drilldowns.py --template templates/jtl_lager_cockpit.json --anwenden
"""
import sqlite3, json, sys

DB = "/app/uploads/datenmonster.db"
FORM_ID = 7

# ── Bausteine ───────────────────────────────────────────────────────────────
# Bestand, letzter Einkaufspreis und letzter Abgang je Artikel zum Stichtag –
# wortgleich zu den Übersichtsabfragen, damit die Zahlen zusammenpassen.
CTE = """WITH bestand AS (
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
), abgang AS (
    SELECT H.kArtikel, MAX(H.dGebucht) AS LetzterAbgang
    FROM dbo.vArtikelHistorie H
    WHERE H.cTyp = 'Ausgang' AND H.cBuchungsart = 'Warenausgang'
      AND H.dGebucht < DATEADD(DAY, 1, :bis)
    GROUP BY H.kArtikel
)"""

ARTIKEL_FELDER = ["ArtNr", "Artikel", "Warengruppe", "Bestand", "EKNetto",
                  "Lagerwert", "LetzterAbgang", "TageOhneAbgang", "kArtikel"]

def artikel_liste(joins: str, filter_: str, aktiv_filter: bool = False) -> str:
    """Artikelliste zum Stichtag. `aktiv_filter` spiegelt die Klassen-Diagramme."""
    aktiv = " AND A.cAktiv = 'Y' AND A.kVaterArtikel = 0" if aktiv_filter else ""
    return f"""{CTE}
SELECT TOP 300 A.cArtNr AS ArtNr,
    ISNULL(AB.cName, '') AS Artikel,
    ISNULL(NULLIF(W.cName, ''), '') AS Warengruppe,
    CAST(b.Menge AS DECIMAL(18,2)) AS Bestand,
    CAST(COALESCE(ek.fEKNetto, A.fEKNetto, 0) AS DECIMAL(18,4)) AS EKNetto,
    CAST(b.Menge * COALESCE(ek.fEKNetto, A.fEKNetto, 0) AS DECIMAL(18,2)) AS Lagerwert,
    ISNULL(CONVERT(varchar(10), ab2.LetzterAbgang, 104), '') AS LetzterAbgang,
    DATEDIFF(DAY, ab2.LetzterAbgang, :bis) AS TageOhneAbgang,
    CAST(A.kArtikel AS VARCHAR(20)) AS kArtikel
FROM bestand b
JOIN dbo.tArtikel A ON A.kArtikel = b.kArtikel{aktiv}
LEFT JOIN dbo.tArtikelBeschreibung AB ON AB.kArtikel = A.kArtikel
     AND AB.kSprache = 1 AND AB.kPlattform = 1 AND AB.kShop = 0
LEFT JOIN ek ON ek.kArtikel = b.kArtikel
LEFT JOIN dbo.tWarengruppe W ON W.kWarengruppe = A.kWarengruppe
LEFT JOIN abgang ab2 ON ab2.kArtikel = b.kArtikel{joins}
WHERE {filter_}
ORDER BY b.Menge * COALESCE(ek.fEKNetto, A.fEKNetto, 0) DESC"""


# Reichweite in Tagen – Zähler und Nenner wie im Klassen-Diagramm.
REICHWEITE = """(b.Menge + CASE WHEN ISNULL(bs.Menge, 0) > 0 THEN bs.Menge ELSE 0 END) / 2.0"""

BUCHUNG_FELDER = ["Datum", "ArtNr", "Artikel", "Typ", "Buchungsart", "Menge",
                  "BestandDanach", "Wert", "Benutzer", "kArtikel"]

def buchungen(filter_: str) -> str:
    """Einzelbuchungen im Zeitraum – die Detailebene unter jeder Buchungs-Summe."""
    return f"""SELECT TOP 500
    CONVERT(varchar(10), H.dGebucht, 104) AS Datum,
    A.cArtNr AS ArtNr,
    ISNULL(AB.cName, '') AS Artikel,
    H.cTyp AS Typ, H.cBuchungsart AS Buchungsart,
    CAST(H.fAnzahl AS DECIMAL(18,2)) AS Menge,
    CAST(H.fLagerBestandGesamt AS DECIMAL(18,2)) AS BestandDanach,
    CAST(H.fAnzahl * COALESCE(NULLIF(H.fEKNetto, 0), A.fEKNetto, 0) AS DECIMAL(18,2)) AS Wert,
    ISNULL(NULLIF(B.cName, ''), 'unbekannt') AS Benutzer,
    CAST(A.kArtikel AS VARCHAR(20)) AS kArtikel
FROM dbo.vArtikelHistorie H
JOIN dbo.tArtikel A ON A.kArtikel = H.kArtikel
LEFT JOIN dbo.tArtikelBeschreibung AB ON AB.kArtikel = A.kArtikel
     AND AB.kSprache = 1 AND AB.kPlattform = 1 AND AB.kShop = 0
LEFT JOIN dbo.tBenutzer B ON B.kBenutzer = H.kBenutzer
WHERE {filter_}
ORDER BY H.dGebucht DESC"""


# ── Die neuen Detail-Abfragen ───────────────────────────────────────────────
# Schlüssel = symbolische Template-ID; so heißen sie in der Datei und im Formular.
NEUE_MAPPINGS = {
    "m_lg_wg_artikel": {
        "name": "Lager – Artikel der Warengruppe (Detail)",
        "felder": ARTIKEL_FELDER,
        # Die Übersicht fasst leere Warengruppen unter „(ohne Warengruppe)"
        # zusammen; der Klick liefert genau diesen Text zurück.
        "sql": artikel_liste("", "(:warengruppe = '(ohne Warengruppe)' AND ISNULL(W.cName, '') = '')\n"
                                 "   OR W.cName = :warengruppe"),
    },
    "m_lg_hst_artikel": {
        "name": "Lager – Artikel des Herstellers (Detail)",
        "felder": ARTIKEL_FELDER,
        "sql": artikel_liste("\nLEFT JOIN dbo.tHersteller HS ON HS.kHersteller = A.kHersteller",
                             "(:hersteller = '(ohne Hersteller)' AND ISNULL(HS.cName, '') = '')\n"
                             "   OR HS.cName = :hersteller"),
    },
    "m_lg_lager_artikel": {
        "name": "Lager – Artikel im Warenlager (Detail)",
        "felder": ARTIKEL_FELDER,
        # Bestand JE LAGER statt gesamt: derselbe Aufbau wie die Übersicht.
        "sql": f"""WITH bestand AS (
    SELECT H.kArtikel, SUM(H.fAnzahl) AS Menge
    FROM dbo.vArtikelHistorie H
    JOIN dbo.tWarenLagerPlatz WLP ON WLP.kWarenLagerPlatz = H.kWarenLagerPlatz
    JOIN dbo.tWarenLager WL ON WL.kWarenLager = WLP.kWarenLager
    WHERE H.dGebucht < DATEADD(DAY, 1, :bis) AND WL.cName = :lager
    GROUP BY H.kArtikel HAVING SUM(H.fAnzahl) > 0
), ek AS (
    SELECT kArtikel, fEKNetto FROM (
        SELECT H.kArtikel, H.fEKNetto,
            ROW_NUMBER() OVER (PARTITION BY H.kArtikel ORDER BY H.dGebucht DESC) AS rn
        FROM dbo.vArtikelHistorie H
        WHERE H.dGebucht < DATEADD(DAY, 1, :bis)
          AND H.cTyp = 'Eingang' AND ISNULL(H.fEKNetto, 0) > 0
    ) x WHERE rn = 1
), abgang AS (
    SELECT H.kArtikel, MAX(H.dGebucht) AS LetzterAbgang
    FROM dbo.vArtikelHistorie H
    WHERE H.cTyp = 'Ausgang' AND H.cBuchungsart = 'Warenausgang'
      AND H.dGebucht < DATEADD(DAY, 1, :bis)
    GROUP BY H.kArtikel
)
SELECT TOP 300 A.cArtNr AS ArtNr,
    ISNULL(AB.cName, '') AS Artikel,
    ISNULL(NULLIF(W.cName, ''), '') AS Warengruppe,
    CAST(b.Menge AS DECIMAL(18,2)) AS Bestand,
    CAST(COALESCE(ek.fEKNetto, A.fEKNetto, 0) AS DECIMAL(18,4)) AS EKNetto,
    CAST(b.Menge * COALESCE(ek.fEKNetto, A.fEKNetto, 0) AS DECIMAL(18,2)) AS Lagerwert,
    ISNULL(CONVERT(varchar(10), ab2.LetzterAbgang, 104), '') AS LetzterAbgang,
    DATEDIFF(DAY, ab2.LetzterAbgang, :bis) AS TageOhneAbgang,
    CAST(A.kArtikel AS VARCHAR(20)) AS kArtikel
FROM bestand b
JOIN dbo.tArtikel A ON A.kArtikel = b.kArtikel
LEFT JOIN dbo.tArtikelBeschreibung AB ON AB.kArtikel = A.kArtikel
     AND AB.kSprache = 1 AND AB.kPlattform = 1 AND AB.kShop = 0
LEFT JOIN ek ON ek.kArtikel = b.kArtikel
LEFT JOIN dbo.tWarengruppe W ON W.kWarengruppe = A.kWarengruppe
LEFT JOIN abgang ab2 ON ab2.kArtikel = b.kArtikel
ORDER BY b.Menge * COALESCE(ek.fEKNetto, A.fEKNetto, 0) DESC""",
    },
    "m_lg_reichweite_artikel": {
        "name": "Lager – Artikel der Reichweite-Klasse (Detail)",
        "felder": ["ArtNr", "Artikel", "Bestand", "Abgang12M", "ReichweiteTage",
                   "EKNetto", "Lagerwert", "kArtikel"],
        "sql": f"""{CTE}
, bestand_start AS (
    SELECT H.kArtikel, SUM(H.fAnzahl) AS Menge FROM dbo.vArtikelHistorie H
    WHERE H.dGebucht < DATEADD(MONTH, -12, :bis) GROUP BY H.kArtikel
), abgang12 AS (
    SELECT H.kArtikel, SUM(-H.fAnzahl) AS Menge12M
    FROM dbo.vArtikelHistorie H
    WHERE H.cTyp = 'Ausgang' AND H.cBuchungsart = 'Warenausgang'
      AND H.dGebucht >= DATEADD(MONTH, -12, :bis) AND H.dGebucht < DATEADD(DAY, 1, :bis)
    GROUP BY H.kArtikel
), je_artikel AS (
    SELECT A.kArtikel, A.cArtNr, ISNULL(AB.cName, '') AS Artikel,
        b.Menge AS Bestand, ISNULL(ab12.Menge12M, 0) AS Abgang12M,
        {REICHWEITE} AS DurchschnittBestand,
        COALESCE(ek.fEKNetto, A.fEKNetto, 0) AS EK
    FROM bestand b
    JOIN dbo.tArtikel A ON A.kArtikel = b.kArtikel AND A.cAktiv = 'Y' AND A.kVaterArtikel = 0
    LEFT JOIN dbo.tArtikelBeschreibung AB ON AB.kArtikel = A.kArtikel
     AND AB.kSprache = 1 AND AB.kPlattform = 1 AND AB.kShop = 0
    LEFT JOIN bestand_start bs ON bs.kArtikel = b.kArtikel
    LEFT JOIN abgang12 ab12 ON ab12.kArtikel = b.kArtikel
    LEFT JOIN ek ON ek.kArtikel = b.kArtikel
)
SELECT TOP 300 cArtNr AS ArtNr, Artikel,
    CAST(Bestand AS DECIMAL(18,2)) AS Bestand,
    CAST(Abgang12M AS DECIMAL(18,2)) AS Abgang12M,
    CASE WHEN Abgang12M = 0 THEN NULL
         ELSE CAST(Bestand / (Abgang12M / 365.0) AS DECIMAL(18,0)) END AS ReichweiteTage,
    CAST(EK AS DECIMAL(18,4)) AS EKNetto,
    CAST(Bestand * EK AS DECIMAL(18,2)) AS Lagerwert,
    CAST(kArtikel AS VARCHAR(20)) AS kArtikel
FROM je_artikel
WHERE CASE
        WHEN Abgang12M = 0 THEN '5 – kein Abgang'
        WHEN Bestand / (Abgang12M / 365.0) < 30 THEN '1 – unter 30 Tage'
        WHEN Bestand / (Abgang12M / 365.0) < 90 THEN '2 – 30 bis 90 Tage'
        WHEN Bestand / (Abgang12M / 365.0) < 180 THEN '3 – 90 bis 180 Tage'
        ELSE '4 – über 180 Tage' END = :klasse
ORDER BY Bestand * EK DESC""",
    },
    "m_lg_lh_artikel": {
        "name": "Lager – Artikel der Ladenhüter-Klasse (Detail)",
        "felder": ["ArtNr", "Artikel", "Warengruppe", "Bestand", "EKNetto",
                   "GebundenesKapital", "LetzterAbgang", "TageOhneAbgang", "kArtikel"],
        "sql": f"""{CTE}
, je_artikel AS (
    SELECT A.kArtikel, A.cArtNr, ISNULL(AB.cName, '') AS Artikel,
        ISNULL(NULLIF(W.cName, ''), '') AS Warengruppe,
        b.Menge AS Bestand, COALESCE(ek.fEKNetto, A.fEKNetto, 0) AS EK,
        ab2.LetzterAbgang,
        COALESCE(DATEDIFF(DAY, ab2.LetzterAbgang, :bis), 9999) AS TageOhneAbgang
    FROM bestand b
    JOIN dbo.tArtikel A ON A.kArtikel = b.kArtikel AND A.cAktiv = 'Y' AND A.kVaterArtikel = 0
    LEFT JOIN dbo.tArtikelBeschreibung AB ON AB.kArtikel = A.kArtikel
     AND AB.kSprache = 1 AND AB.kPlattform = 1 AND AB.kShop = 0
    LEFT JOIN dbo.tWarengruppe W ON W.kWarengruppe = A.kWarengruppe
    LEFT JOIN ek ON ek.kArtikel = b.kArtikel
    LEFT JOIN abgang ab2 ON ab2.kArtikel = b.kArtikel
)
SELECT TOP 300 cArtNr AS ArtNr, Artikel, Warengruppe,
    CAST(Bestand AS DECIMAL(18,2)) AS Bestand,
    CAST(EK AS DECIMAL(18,4)) AS EKNetto,
    CAST(Bestand * EK AS DECIMAL(18,2)) AS GebundenesKapital,
    ISNULL(CONVERT(varchar(10), LetzterAbgang, 104), '') AS LetzterAbgang,
    NULLIF(TageOhneAbgang, 9999) AS TageOhneAbgang,
    CAST(kArtikel AS VARCHAR(20)) AS kArtikel
FROM je_artikel
WHERE CASE
        WHEN TageOhneAbgang = 9999 THEN '6 – nie verkauft'
        WHEN TageOhneAbgang <= 90 THEN '1 – bis 90 Tage'
        WHEN TageOhneAbgang <= 180 THEN '2 – 90 bis 180 Tage'
        WHEN TageOhneAbgang <= 365 THEN '3 – 180 Tage bis 1 Jahr'
        WHEN TageOhneAbgang <= 730 THEN '4 – 1 bis 2 Jahre'
        ELSE '5 – über 2 Jahre' END = :klasse
ORDER BY Bestand * EK DESC""",
    },
    "m_lg_buchungsart_detail": {
        "name": "Lager – Buchungen der Buchungsart (Detail)",
        "felder": BUCHUNG_FELDER,
        # Die Übersicht gruppiert nach Buchungsart UND Typ – „Korrekturbuchung"
        # steht dort zweimal, als Eingang und als Ausgang. Ein Drilldown reicht
        # aber nur EINEN Wert durch; ohne den Typ zöge der Klick beide Zeilen
        # zusammen (geprüft: 424 statt 84 Buchungen). Deshalb ein
        # zusammengesetzter Schlüssel „Buchungsart|Typ", den die Übersicht als
        # verborgene Spalte mitliefert.
        "sql": buchungen("H.cBuchungsart = LEFT(:schluessel, CHARINDEX('|', :schluessel) - 1)\n"
                         "  AND H.cTyp = SUBSTRING(:schluessel, CHARINDEX('|', :schluessel) + 1, 100)\n"
                         "  AND H.dGebucht >= :von AND H.dGebucht < DATEADD(DAY, 1, :bis)"),
    },
    "m_lg_benutzer_detail": {
        "name": "Lager – Korrekturen des Benutzers (Detail)",
        "felder": BUCHUNG_FELDER,
        # „unbekannt" fasst in der Übersicht alle Buchungen ohne Benutzer zusammen.
        "sql": buchungen("H.cBuchungsart IN ('Korrekturbuchung', 'Inventurdifferenzbuchung')\n"
                         "  AND H.dGebucht >= :von AND H.dGebucht < DATEADD(DAY, 1, :bis)\n"
                         "  AND ((:benutzer = 'unbekannt' AND ISNULL(B.cName, '') = '')\n"
                         "       OR B.cName = :benutzer)"),
    },
    "m_lg_schwund_monat_detail": {
        "name": "Lager – Korrekturen des Monats (Detail)",
        "felder": BUCHUNG_FELDER,
        "sql": buchungen("H.cBuchungsart IN ('Korrekturbuchung', 'Inventurdifferenzbuchung')\n"
                         "  AND CONVERT(varchar(7), H.dGebucht, 126) = :monat"),
    },
}

# Die Buchungsarten-Übersicht bekommt eine verborgene Schlüsselspalte, sonst
# lässt sich ihre Doppel-Gruppierung nicht eindeutig aufklappen.
UEBERSICHT_ERWEITERN = {
    "m_lg_buchungsarten": {
        "name_teil": "Buchungsarten im Zeitraum",
        "anker": "    H.cBuchungsart AS Buchungsart, H.cTyp AS Typ,",
        "zusatz": "\n    H.cBuchungsart + '|' + H.cTyp AS Schluessel,",
        "feld": "Schluessel",
    },
}


def uebersicht_erweitern(sql: str, ziel_felder: list, d: dict) -> tuple:
    """Ergänzt die Schlüsselspalte in Abfrage und Zielfeldern. (sql, felder, geändert?)"""
    if d["feld"] in [f.get("target_field") for f in ziel_felder]:
        return sql, ziel_felder, False
    if d["anker"] not in sql:
        raise SystemExit(f"Anker in {d['name_teil']} nicht gefunden")
    sql = sql.replace(d["anker"], d["anker"] + d["zusatz"], 1)
    ziel_felder = ziel_felder + [{
        "source_field": d["feld"], "target_field": d["feld"], "target_type": "string",
        "source_dataset_id": "__sql__sql1",
        "transformer": {"type": "direct", "source_field": d["feld"]}}]
    return sql, ziel_felder, True


HISTORIE = "m_lg_artikel_historie"          # bestehende Buchungshistorie je Artikel
EBENE_ARTIKEL = {"param": "kArtikel", "key_column": "kArtikel",
                 "title": "Buchungshistorie des Artikels"}

# ── Wo welcher Drilldown hin soll ───────────────────────────────────────────
DRILLDOWNS = {
    "w_lg_tbl_warengruppe": ("m_lg_wg_artikel", "Warengruppe", "warengruppe",
                             "Artikel der Warengruppe"),
    "w_lg_tbl_hersteller":  ("m_lg_hst_artikel", "Hersteller", "hersteller",
                             "Artikel des Herstellers"),
    "w_lg_tbl_lager":       ("m_lg_lager_artikel", "Lager", "lager",
                             "Artikel im Warenlager"),
    "w_lg_tbl_buchungsarten": ("m_lg_buchungsart_detail", "Schluessel", "schluessel",
                               "Buchungen dieser Art"),
    "w_lg_tbl_schwund_benutzer": ("m_lg_benutzer_detail", "Benutzer", "benutzer",
                                  "Korrekturen dieses Benutzers"),
    "w_lg_bar_reichweite":  ("m_lg_reichweite_artikel", "Klasse", "klasse",
                             "Artikel dieser Reichweite-Klasse"),
    "w_lg_bar_lh":          ("m_lg_lh_artikel", "Klasse", "klasse",
                             "Artikel dieser Klasse"),
    "w_lg_line_schwund":    ("m_lg_schwund_monat_detail", "Monat", "monat",
                             "Korrekturen dieses Monats"),
}


def _sql_node(sql: str, felder: list, connection_id) -> dict:
    return {"id": "sql1", "x": 120, "y": 40, "width": 380, "height": 260,
            "connection_id": connection_id, "mode": "transform",
            "output_field": "sql_1", "output_fields": list(felder)}


def _target(name: str, felder: list) -> dict:
    return {"id": "t1", "name": name, "target_type": "dataset",
            "target_connection_id": None, "target_table": "",
            "target_write_mode": "replace", "target_options": {},
            "fields": [{"source_field": f, "target_field": f, "target_type": "string",
                        "source_dataset_id": "__sql__sql1",
                        "transformer": {"type": "direct", "source_field": f}}
                       for f in felder]}


def widgets_verdrahten(widgets: list, id_aufloesen) -> int:
    """Trägt die Drilldowns ein. `id_aufloesen` liefert die Mapping-Referenz."""
    n = 0
    for w in widgets:
        eintrag = DRILLDOWNS.get(w.get("id"))
        if not eintrag:
            continue
        mapping, schluessel, param, titel = eintrag
        cfg = w.setdefault("config", {})
        neu = {"mapping_id": id_aufloesen(mapping), "key_column": schluessel,
               "param": param, "title": titel,
               "levels": [{"mapping_id": id_aufloesen(HISTORIE), **EBENE_ARTIKEL}],
               "hidden_columns": ["kArtikel", "Schluessel"]}
        if cfg.get("drilldown") == neu:
            continue
        cfg["drilldown"] = neu
        n += 1
    return n


def main_db(anwenden: bool):
    c = sqlite3.connect(DB)
    # Verbindung vom bestehenden Detail-Mapping übernehmen, nicht raten.
    vorbild = c.execute("select sql_nodes, project_id from mappings "
                        "where name like 'Lager – Buchungshistorie%'").fetchone()
    conn_id = json.loads(vorbild[0])[0].get("connection_id")
    projekt = vorbild[1]

    ids = {}
    for schluessel, d in NEUE_MAPPINGS.items():
        vorhanden = c.execute("select id from mappings where name=?", (d["name"],)).fetchone()
        nodes = json.dumps([{**_sql_node(d["sql"], d["felder"], conn_id), "sql": d["sql"]}],
                           ensure_ascii=False)
        ziele = json.dumps([_target(d["name"], d["felder"])], ensure_ascii=False)
        if vorhanden:
            ids[schluessel] = vorhanden[0]
            if anwenden:
                c.execute("update mappings set sql_nodes=?, targets=? where id=?",
                          (nodes, ziele, vorhanden[0]))
            print(f"  ~ {d['name']}  (Mapping {vorhanden[0]}, aktualisiert)")
        elif anwenden:
            cur = c.execute(
                "insert into mappings (name, canvas_nodes, joins, fields, transform_nodes, "
                "constant_nodes, sql_nodes, agg_nodes, rest_nodes, lookup_nodes, calc_nodes, "
                "switch_nodes, sort_nodes, target_type, target_table, target_write_mode, "
                "target_options, targets, project_id) "
                "values (?, '[]','[]','[]','[]','[]', ?, '[]','[]','[]','[]','[]','[]', "
                "'dataset','','replace','{}', ?, ?)",
                (d["name"], nodes, ziele, projekt))
            ids[schluessel] = cur.lastrowid
            print(f"  + {d['name']}  (Mapping {cur.lastrowid}, neu)")
        else:
            ids[schluessel] = f"<neu:{schluessel}>"
            print(f"  + {d['name']}  (würde neu angelegt)")

    hist = c.execute("select id from mappings where name like 'Lager – Buchungshistorie%'").fetchone()
    ids[HISTORIE] = hist[0]

    for _, d in UEBERSICHT_ERWEITERN.items():
        mid, sn, tg = c.execute("select id, sql_nodes, targets from mappings where name like ?",
                                (f"%{d['name_teil']}%",)).fetchone()
        nodes, ziele = json.loads(sn), json.loads(tg)
        sql, felder, geaendert = uebersicht_erweitern(nodes[0]["sql"], ziele[0]["fields"], d)
        if not geaendert:
            print(f"  = {d['name_teil']}: Schlüsselspalte schon vorhanden")
            continue
        nodes[0]["sql"] = sql
        nodes[0].setdefault("output_fields", []).append(d["feld"])
        ziele[0]["fields"] = felder
        print(f"  ± {d['name_teil']}: Spalte {d['feld']} ergänzt (Mapping {mid})")
        if anwenden:
            c.execute("update mappings set sql_nodes=?, targets=? where id=?",
                      (json.dumps(nodes, ensure_ascii=False),
                       json.dumps(ziele, ensure_ascii=False), mid))

    sch = json.loads(c.execute("select schema from forms where id=?", (FORM_ID,)).fetchone()[0])
    n = widgets_verdrahten(sch.get("widgets") or [], lambda k: ids[k])
    print(f"\nFormular {FORM_ID}: {n} Drilldowns gesetzt")
    if not anwenden:
        print("\n(Trockenlauf – mit --anwenden schreiben)")
        return
    c.execute("update forms set schema=? where id=?",
              (json.dumps(sch, ensure_ascii=False), FORM_ID))
    c.commit()
    print("geschrieben.")


def main_template(pfad: str, anwenden: bool):
    with open(pfad, encoding="utf-8") as f:
        t = json.load(f)
    vorhandene = {m["id"]: m for m in t["mappings"]}
    conn = vorhandene[HISTORIE]["sql_nodes"][0].get("connection_id")
    for schluessel, d in NEUE_MAPPINGS.items():
        eintrag = {"id": schluessel, "name": d["name"], "canvas_nodes": [], "joins": [],
                   "sql_nodes": [{**_sql_node(d["sql"], d["felder"], conn), "sql": d["sql"]}],
                   "agg_nodes": [], "transform_nodes": [], "constant_nodes": [],
                   "rest_nodes": [], "lookup_nodes": [], "calc_nodes": [],
                   "switch_nodes": [], "sort_nodes": [],
                   "targets": [_target(d["name"], d["felder"])]}
        if schluessel in vorhandene:
            t["mappings"][t["mappings"].index(vorhandene[schluessel])] = eintrag
            print(f"  ~ {schluessel} aktualisiert")
        else:
            t["mappings"].append(eintrag)
            print(f"  + {schluessel} ergänzt")
    for schluessel, d in UEBERSICHT_ERWEITERN.items():
        m = vorhandene[schluessel]
        sql, felder, geaendert = uebersicht_erweitern(
            m["sql_nodes"][0]["sql"], m["targets"][0]["fields"], d)
        if geaendert:
            m["sql_nodes"][0]["sql"] = sql
            m["sql_nodes"][0].setdefault("output_fields", []).append(d["feld"])
            m["targets"][0]["fields"] = felder
            print(f"  ± {schluessel}: Spalte {d['feld']} ergänzt")
    n = widgets_verdrahten(t["forms"][0]["schema"].get("widgets") or [], lambda k: k)
    print(f"\n{pfad}: {n} Drilldowns gesetzt, {len(t['mappings'])} Mappings")
    if not anwenden:
        print("\n(Trockenlauf – mit --anwenden schreiben)")
        return
    teile = str(t.get("version") or "1.0").split(".")
    t["version"] = f"{teile[0]}.{int(teile[1]) + 1}"
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(t, f, ensure_ascii=False, indent=2); f.write("\n")
    print(f"geschrieben (Version {t['version']}).")


if __name__ == "__main__":
    anwenden = "--anwenden" in sys.argv
    if "--template" in sys.argv:
        main_template(sys.argv[sys.argv.index("--template") + 1], anwenden)
    else:
        main_db(anwenden)
