"""Bringt den Auftragsbestand-Drilldown mit seiner Kopfzahl in Deckung.

Im Unternehmensmonitor meldet „Überschrittene Liefertermine" 6 Aufträge, die
Detailliste zeigte 207 – sie listet alle offenen Aufträge, nicht die
überfälligen. Dazu kamen zwei Altlasten aus der Aufräumaktion vom 2026-08-29
(backend/auftragsbestand.py): die dort ergänzten SQL-Spalten wurden nie in die
Zielfeldliste der Mappings eingetragen, und die Zielfelder filtern die Ausgabe.
Die sechs neuen Kennzahlen des Backlog-KPI und der getrennte offene Warenwert
kamen deshalb nie in der Oberfläche an (die vier neuen Kacheln blieben leer).

1. M63 „Vertrieb – Backlog KPI": Zielfelder um die sechs Kennzahlen ergänzt.
   „Überfällig" zählt jetzt über DATEDIFF statt über einen Datumsvergleich –
   wortgleich mit dem Filter der Detailliste, damit beide nicht auseinander
   laufen können.
2. M64 „Vertrieb – Offene Aufträge": Zielfeld „OffenerWert" existiert im SQL
   nicht mehr, dafür fehlten „OffenerWarenwert" und „OffenerZahlbetrag".
   Neue Spalte „TageUeberfaellig" (NULL ohne Liefertermin) – sie trägt den
   Filter des Drilldowns und ist auch in der Cockpit-Liste nützlich.
3. Regel „vertrieb_backlog": Der Drilldown bekommt den Zeilenfilter
   TageUeberfaellig 1..365 – dieselbe Abgrenzung wie die Kopfzahl.

Anwenden – Template UND Live-DB (siehe backend/auftragsbestand.py):

    python backend/backlog_zielfelder.py --templates
    python backend/backlog_zielfelder.py --templates --anwenden

    docker cp backend/backlog_zielfelder.py datenmonster-backend:/tmp/
    docker exec datenmonster-backend python /tmp/backlog_zielfelder.py --live
    docker exec datenmonster-backend python /tmp/backlog_zielfelder.py --live --anwenden
"""
import argparse
import json
import os
import sqlite3

DB = "/app/uploads/datenmonster.db"

UEBERFAELLIG_ALT = """SUM(CASE WHEN A.dVoraussichtlichesLieferdatum < GETDATE()
              AND A.dVoraussichtlichesLieferdatum >= DATEADD(YEAR, -1, GETDATE())
             THEN 1 ELSE 0 END) AS Ueberfaellig,
    SUM(CASE WHEN A.dVoraussichtlichesLieferdatum < DATEADD(YEAR, -1, GETDATE())
             THEN 1 ELSE 0 END) AS UeberfaelligAlt,"""
# Wortgleich mit dem Zeilenfilter des Drilldowns (1..365 Tage): so kann die
# Kopfzahl nicht mehr von der Liste abweichen.
UEBERFAELLIG_NEU = """SUM(CASE WHEN DATEDIFF(DAY, A.dVoraussichtlichesLieferdatum, GETDATE())
                  BETWEEN 1 AND 365 THEN 1 ELSE 0 END) AS Ueberfaellig,
    SUM(CASE WHEN DATEDIFF(DAY, A.dVoraussichtlichesLieferdatum, GETDATE()) > 365
             THEN 1 ELSE 0 END) AS UeberfaelligAlt,"""

TERMIN_ALT = "    ISNULL(CONVERT(char(10), A.dVoraussichtlichesLieferdatum, 104), '') AS Liefertermin,"
TERMIN_NEU = (TERMIN_ALT + "\n"
              "    DATEDIFF(DAY, A.dVoraussichtlichesLieferdatum, GETDATE()) AS TageUeberfaellig,")

# Zielfelder = Anzeigefilter. Reihenfolge wie im SELECT.
FELDER = {
    "Vertrieb – Backlog KPI": [
        ("OffeneAuftraege", "int"), ("Auftragsbestand", "float"), ("AvgAlterTage", "float"),
        ("Ueberfaellig", "int"), ("UeberfaelligAlt", "int"), ("OhneLiefertermin", "int"),
        ("AuftraegeLaufend", "int"), ("BestandLaufend", "float"),
        ("AuftraegeAlt", "int"), ("BestandAlt", "float"), ("WertAelter30", "float"),
    ],
    "Vertrieb – Offene Aufträge": [
        ("Auftragsnr", "string"), ("Datum", "string"), ("AlterTage", "int"),
        ("Kunde", "string"), ("Wert", "float"), ("OffenerWarenwert", "float"),
        ("OffenerZahlbetrag", "float"), ("Lieferstatus", "string"),
        ("Liefertermin", "string"), ("TageUeberfaellig", "int"), ("kAuftrag", "string"),
    ],
}

# Die Kopfzahl der Regel zählt Liefertermine der letzten 12 Monate; ältere sind
# Karteileichen und laufen als UeberfaelligAlt mit.
ZEILENFILTER = [
    {"column": "TageUeberfaellig", "op": ">=", "value": 1},
    {"column": "TageUeberfaellig", "op": "<=", "value": 365},
]


def feld(name, typ, quelle="__sql__sql1"):
    return {"source_field": name, "target_field": name, "target_type": typ,
            "source_dataset_id": quelle,
            "transformer": {"type": "direct", "source_field": name}}


def patche_sql(sql):
    if not isinstance(sql, str):
        return sql, []
    schritte = []
    if UEBERFAELLIG_ALT in sql:
        sql = sql.replace(UEBERFAELLIG_ALT, UEBERFAELLIG_NEU)
        schritte.append("Überfällig über DATEDIFF (deckungsgleich mit dem Filter)")
    if TERMIN_ALT in sql and "TageUeberfaellig" not in sql:
        sql = sql.replace(TERMIN_ALT, TERMIN_NEU)
        schritte.append("Spalte TageUeberfaellig")
    return sql, schritte


def patche_mapping(m):
    """m ist ein dict mit name/sql_nodes/targets (Template wie Live gleich aufgebaut)."""
    schritte = []
    for sn in m.get("sql_nodes") or []:
        if isinstance(sn, dict) and sn.get("sql"):
            sn["sql"], s = patche_sql(sn["sql"])
            schritte += s
    soll = FELDER.get(m.get("name"))
    if soll:
        for ziel in m.get("targets") or []:
            ist = [f.get("source_field") for f in ziel.get("fields") or []]
            if ist == [n for n, _ in soll]:
                continue
            quelle = next((f.get("source_dataset_id") for f in ziel.get("fields") or []
                           if f.get("source_dataset_id")), "__sql__sql1")
            alt = {f.get("source_field"): f for f in ziel.get("fields") or []}
            ziel["fields"] = [alt.get(n) or feld(n, t, quelle) for n, t in soll]
            fehlten = [n for n, _ in soll if n not in alt]
            tot = [n for n in ist if n not in {x for x, _ in soll}]
            if fehlten:
                schritte.append("Zielfelder +" + ", +".join(fehlten))
            if tot:
                schritte.append("Zielfelder -" + ", -".join(tot))
            if not fehlten and not tot:
                schritte.append("Zielfelder umsortiert")
    return schritte


def patche_regel(regel):
    """Drilldown der Regel vertrieb_backlog auf die überfälligen Aufträge einengen."""
    dd = regel.get("drilldown") or {}
    if regel.get("rule_key") != "vertrieb_backlog" or not dd:
        return []
    if dd.get("row_filter") == ZEILENFILTER:
        return []
    dd["row_filter"] = ZEILENFILTER
    dd["title"] = "Aufträge mit überschrittenem Liefertermin"
    regel["drilldown"] = dd
    return ["Drilldown nur noch überfällige Aufträge"]


def regeln_im_dokument(doc):
    """Warnregeln liegen je nach Template an unterschiedlichen Stellen."""
    for r in doc.get("alert_rules") or []:
        yield r
    for f in doc.get("forms") or []:
        for r in (f.get("schema") or {}).get("alert_rules") or []:
            yield r


def templates(anwenden):
    wurzel = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "templates")
    gesamt = 0
    for datei, version_neu in (("jtl_vertrieb_cockpit.json", "1.8"), ("jtl_monitor.json", "1.3")):
        pfad = os.path.join(wurzel, datei)
        doc = json.load(open(pfad, encoding="utf-8"))
        treffer = []
        for m in doc.get("mappings") or []:
            treffer += [f"{m['name']}: {s}" for s in patche_mapping(m)]
        for r in regeln_im_dokument(doc):
            treffer += [f"Regel {r['rule_key']}: {s}" for s in patche_regel(r)]
        if not treffer:
            continue
        doc["version"] = version_neu
        gesamt += len(treffer)
        print(f"  {datei} (Version -> {version_neu})")
        for t in treffer:
            print(f"      - {t}")
        if anwenden:
            # Zeilenende so lassen, wie die Datei es hatte – sonst steht im Diff
            # eine Änderung, die keine ist.
            schluss = "\n" if open(pfad, encoding="utf-8").read().endswith("\n") else ""
            with open(pfad, "w", encoding="utf-8") as fh:
                json.dump(doc, fh, indent=2, ensure_ascii=False)
                fh.write(schluss)
    return gesamt


def live(anwenden):
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    gesamt = 0
    for r in c.execute("SELECT id, name, sql_nodes, targets FROM mappings").fetchall():
        m = {"name": r["name"],
             "sql_nodes": json.loads(r["sql_nodes"] or "[]"),
             "targets": json.loads(r["targets"] or "[]")}
        treffer = patche_mapping(m)
        if not treffer:
            continue
        gesamt += len(treffer)
        print(f"  M{r['id']:<4} {(r['name'] or '')[:44]:44} {'; '.join(treffer)}")
        if anwenden:
            c.execute("UPDATE mappings SET sql_nodes = ?, targets = ? WHERE id = ?",
                      (json.dumps(m["sql_nodes"], ensure_ascii=False),
                       json.dumps(m["targets"], ensure_ascii=False), r["id"]))
    for r in c.execute("SELECT id, rule_key, drilldown FROM alert_rules").fetchall():
        regel = {"rule_key": r["rule_key"], "drilldown": json.loads(r["drilldown"] or "{}")}
        treffer = patche_regel(regel)
        if not treffer:
            continue
        gesamt += len(treffer)
        print(f"  Regel {r['rule_key']:<22} {'; '.join(treffer)}")
        if anwenden:
            c.execute("UPDATE alert_rules SET drilldown = ? WHERE id = ?",
                      (json.dumps(regel["drilldown"], ensure_ascii=False), r["id"]))
    if anwenden:
        c.commit()
    c.close()
    return gesamt


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--templates", action="store_true")
    p.add_argument("--live", action="store_true")
    p.add_argument("--anwenden", action="store_true")
    a = p.parse_args()
    if not (a.templates or a.live):
        p.error("--templates und/oder --live angeben")
    n = 0
    if a.templates:
        print("== Templates ==")
        n += templates(a.anwenden)
    if a.live:
        print("== Live ==")
        n += live(a.anwenden)
    print(f"\n{n} Änderungen {'angewandt' if a.anwenden else 'gefunden (Trockenlauf)'}")
