"""Ergänzt das GF-Cockpit um die Kachel „davon storniert".

Warum: JTLs Statistik weist den Umsatz INKLUSIVE stornierter Rechnungen aus und
stellt die Stornobelege als eigene Zeile daneben. Unser Cockpit zieht sie ab. Ohne
eine sichtbare Storno-Zahl lässt sich die Differenz zur JTL-Statistik nicht erklären –
mit ihr ist die Brücke ein Blick: Cockpit-Umsatz + Storno = JTL-Umsatz.

Die Storno-Summen kommen als eigenständige Unterabfragen dazu; die bestehende
Kennzahlen-Logik bleibt unangetastet. Die Marke »storno-absicht« schützt sie davor,
vom Storno-Filter-Patch (doku/storno_filter_patch.py) stumm auf 0 gesetzt zu werden.
"""
import sqlite3, json, sys

DB = "/app/uploads/datenmonster.db"

STORNO_SQL = """,
    (SELECT CAST(ISNULL(SUM(SP.fAnzahl * SP.fVkNetto), 0) AS DECIMAL(18,2))
     FROM Rechnung.vRechnung SR   /* storno-absicht: hier sind Stornos der Zweck */
     JOIN Rechnung.tRechnungPosition SP ON SP.kRechnung = SR.kRechnung
     WHERE SR.nStorno = 1
       AND (:plattform_empty = 1 OR SR.kPlattform IN (SELECT nPlattform FROM dbo.tPlattform WHERE nTyp IN (:plattform)))
       AND SR.dErstellt >= :von AND SR.dErstellt < DATEADD(DAY, 1, :bis)) AS StornoWert,
    (SELECT CAST(ISNULL(SUM(SP.fAnzahl * SP.fVkNetto), 0) AS DECIMAL(18,2))
     FROM Rechnung.vRechnung SR   /* storno-absicht */
     JOIN Rechnung.tRechnungPosition SP ON SP.kRechnung = SR.kRechnung
     WHERE SR.nStorno = 1
       AND (:plattform_empty = 1 OR SR.kPlattform IN (SELECT nPlattform FROM dbo.tPlattform WHERE nTyp IN (:plattform)))
       AND SR.dErstellt >= DATEADD(YEAR, -1, :von)
       AND SR.dErstellt < DATEADD(DAY, 1, DATEADD(YEAR, -1, :bis))) AS StornoWertVJ,
    (SELECT COUNT(*)
     FROM Rechnung.vRechnung SR   /* storno-absicht */
     WHERE SR.nStorno = 1
       AND (:plattform_empty = 1 OR SR.kPlattform IN (SELECT nPlattform FROM dbo.tPlattform WHERE nTyp IN (:plattform)))
       AND SR.dErstellt >= :von AND SR.dErstellt < DATEADD(DAY, 1, :bis)) AS StornoAnzahl"""

NEUE_FELDER = [("StornoWert", "float"), ("StornoWertVJ", "float"), ("StornoAnzahl", "int")]

KACHEL = {
    "id": "w_kpi_storno",
    "type": "kpi",
    "label": "davon storniert",
    "action_id": "act_overview_kpi",
    "config": {
        "width": 4,
        "column": "StornoWert",
        "aggregation": "first",
        "prefix": "€ ",
        "suffix": "",
        "decimals": 2,
        "compare_column": "StornoWertVJ",
        "compare_label": "Vorjahr",
        # Mehr Storno ist schlechter – ohne invert_delta färbte ein Anstieg grün.
        "invert_delta": True,
        "breakdown": [{"label": "Stornierte Rechnungen", "column": "StornoAnzahl"}],
        "hint": ("Bereits aus dem Umsatz herausgerechnet. JTLs Statistik zeigt den "
                 "Umsatz einschließlich dieser Belege – Cockpit-Umsatz plus dieser "
                 "Betrag ergibt die JTL-Zahl."),
    },
}


def sql_ergaenzen(sql: str) -> str:
    if "StornoWert" in sql:
        return sql                                  # schon vorhanden
    anker = "    CAST(CASE WHEN UmsatzVJ > 0 THEN 100.0 * DB2VJ / UmsatzVJ END AS DECIMAL(18,2)) AS DB2MargeVJ"
    if anker not in sql:
        raise SystemExit("Anker in der Kennzahlen-Abfrage nicht gefunden")
    return sql.replace(anker, anker + STORNO_SQL, 1)


def felder_ergaenzen(fields: list) -> list:
    hat = {f.get("target_field") for f in fields}
    for name, typ in NEUE_FELDER:
        if name in hat:
            continue
        fields.append({"source_field": name, "target_field": name, "target_type": typ,
                       "source_dataset_id": "__sql__sql1",
                       "transformer": {"type": "direct", "source_field": name}})
    return fields


def widgets_ergaenzen(widgets: list) -> list:
    if any(w.get("id") == "w_kpi_storno" for w in widgets):
        return widgets
    # Direkt hinter „Rechnungen“ einsortieren – dort steht der Belegbezug.
    idx = next((i for i, w in enumerate(widgets) if w.get("id") == "w_kpi_rechnungen"), None)
    stelle = idx + 1 if idx is not None else len(widgets)
    widgets.insert(stelle, json.loads(json.dumps(KACHEL)))
    return widgets


def main(anwenden: bool):
    c = sqlite3.connect(DB)

    # ── Mapping 1 ────────────────────────────────────────────────────────────
    sn, tg = c.execute("select sql_nodes, targets from mappings where id=1").fetchone()
    nodes = json.loads(sn); targets = json.loads(tg)
    nodes[0]["sql"] = sql_ergaenzen(nodes[0]["sql"])
    targets[0]["fields"] = felder_ergaenzen(targets[0].get("fields") or [])
    print(f"Mapping 1: {len(targets[0]['fields'])} Zielfelder, "
          f"StornoWert im SQL: {'StornoWert' in nodes[0]['sql']}")

    # ── Formular 1 ───────────────────────────────────────────────────────────
    sch = json.loads(c.execute("select schema from forms where id=1").fetchone()[0])
    sch["widgets"] = widgets_ergaenzen(sch.get("widgets") or [])
    print(f"Formular 1: {len(sch['widgets'])} Widgets, Kachel vorhanden: "
          f"{any(w.get('id') == 'w_kpi_storno' for w in sch['widgets'])}")

    if not anwenden:
        print("\n(Trockenlauf – mit --anwenden schreiben)")
        return
    c.execute("update mappings set sql_nodes=?, targets=? where id=1",
              (json.dumps(nodes, ensure_ascii=False), json.dumps(targets, ensure_ascii=False)))
    c.execute("update forms set schema=? where id=1", (json.dumps(sch, ensure_ascii=False),))
    c.commit()
    print("\ngeschrieben.")


if __name__ == "__main__":
    main("--anwenden" in sys.argv)
