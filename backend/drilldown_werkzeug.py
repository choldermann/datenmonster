"""Gemeinsame Mechanik, um ein Cockpit aufklappbar zu machen.

Das Muster ist bei jedem Cockpit dasselbe: ein paar Detail-Abfragen anlegen, sie
den Widgets als `config.drilldown` zuordnen und beides in die Installation UND in
die Template-Datei schreiben. Nur die Abfragen und die Zuordnung unterscheiden
sich – die stehen im jeweiligen Cockpit-Skript, alles andere hier.

Ein Cockpit-Skript liefert:
    NEUE_MAPPINGS  {symbolische_id: {name, felder, sql}}
    DRILLDOWNS     {widget_id: (mapping, key_column, param, titel, mit_ebene2)}
    EBENE2         {"mapping": …, "param": …, "key_column": …, "title": …} oder None
    UEBERSICHT_ERWEITERN  {symbolische_id: {name_teil, anker, zusatz, feld}}
    BESTEHENDE     {symbolische_id: "Name in der Datenbank"}  – für wiederverwendete
                   Detail-Mappings, die es schon gibt
"""
import sqlite3, json, sys

DB = "/app/uploads/datenmonster.db"
REST_GRENZE = 499
# Der Drilldown-Endpunkt liefert höchstens 500 Zeilen. Listen, die darüber
# hinausgehen, zeigen die ersten 499 und den Rest als eine beschriftete
# Sammelzeile – sonst fehlte ein Teil der Summe unbemerkt.


def mit_sammelzeile(quelle: str, spalten: str, rest: str, sortierung: str) -> str:
    """„Die ersten N einzeln + eine Sammelzeile" um eine Quelle mit Spalte `rn`."""
    return f"""SELECT 0 AS Sortierung, {spalten}
FROM {quelle} WHERE rn <= {REST_GRENZE}
UNION ALL
SELECT 1, {rest}
FROM {quelle} WHERE rn > {REST_GRENZE}
HAVING COUNT(*) > 0
ORDER BY Sortierung, {sortierung}"""


def sql_node(sql: str, felder: list, connection_id) -> dict:
    return {"id": "sql1", "x": 120, "y": 40, "width": 380, "height": 260,
            "connection_id": connection_id, "mode": "transform",
            "output_field": "sql_1", "output_fields": list(felder), "sql": sql}


def target(name: str, felder: list) -> dict:
    return {"id": "t1", "name": name, "target_type": "dataset",
            "target_connection_id": None, "target_table": "",
            "target_write_mode": "replace", "target_options": {},
            "fields": [{"source_field": f, "target_field": f, "target_type": "string",
                        "source_dataset_id": "__sql__sql1",
                        "transformer": {"type": "direct", "source_field": f}}
                       for f in felder]}


# Spalten, die nur den Klick tragen und niemanden interessieren.
VERBORGEN = ["Sortierung", "kArtikel", "kAuftrag", "kKunde", "kLieferant",
             "kLieferantenBestellung", "kEingangsrechnung", "kRechnung",
             "Schluessel", "sort"]


def widgets_verdrahten(widgets: list, drilldowns: dict, ebene2, aufloesen) -> int:
    n = 0
    for w in widgets:
        eintrag = drilldowns.get(w.get("id"))
        if not eintrag:
            continue
        mapping, schluessel, param, titel, tiefer = eintrag
        neu = {"mapping_id": aufloesen(mapping), "key_column": schluessel,
               "param": param, "title": titel, "hidden_columns": list(VERBORGEN)}
        if tiefer and ebene2:
            neu["levels"] = [{"mapping_id": aufloesen(ebene2["mapping"]),
                              "param": ebene2["param"],
                              "key_column": ebene2["key_column"],
                              "title": ebene2["title"]}]
        cfg = w.setdefault("config", {})
        if cfg.get("drilldown") == neu:
            continue
        cfg["drilldown"] = neu
        n += 1
    return n


def uebersicht_erweitern(sql: str, ziel_felder: list, d: dict):
    """Ergänzt eine Schlüsselspalte in Abfrage und Zielfeldern.

    Manche Abfragen brauchen die Spalte an ZWEI Stellen – einmal in der inneren
    Gruppierung, einmal in der äußeren Auswahl. Dafür nimmt `ersetzungen` eine
    Liste von (Anker, Zusatz)-Paaren statt eines einzelnen Paars.
    """
    if d["feld"] in [f.get("target_field") for f in ziel_felder]:
        return sql, ziel_felder, False
    paare = d.get("ersetzungen") or [(d["anker"], d["zusatz"])]
    for anker, zusatz in paare:
        if anker not in sql:
            raise SystemExit(f"Anker in {d['name_teil']} nicht gefunden:\n  {anker!r}")
        sql = sql.replace(anker, anker + zusatz, 1)
    ziel_felder = ziel_felder + [{
        "source_field": d["feld"], "target_field": d["feld"], "target_type": "string",
        "source_dataset_id": "__sql__sql1",
        "transformer": {"type": "direct", "source_field": d["feld"]}}]
    return sql, ziel_felder, True


def anwenden_db(mod, form_id: int, anwenden: bool):
    c = sqlite3.connect(DB)
    # Verbindung und Projekt von einem Mapping des Cockpits übernehmen statt raten.
    schema_roh = c.execute("select schema from forms where id=?", (form_id,)).fetchone()[0]
    mapping_ids = [a.get("mapping_id") for a in json.loads(schema_roh).get("actions", [])
                   if a.get("mapping_id")]
    if not mapping_ids:
        raise SystemExit(f"Formular {form_id} hat keine Mapping-Action")
    conn_id, projekt = c.execute(
        "select json_extract(sql_nodes,'$[0].connection_id'), project_id "
        "from mappings where id=?", (mapping_ids[0],)).fetchone()

    ids = {}
    for schluessel, name in (getattr(mod, "BESTEHENDE", {}) or {}).items():
        treffer = c.execute("select id from mappings where name=?", (name,)).fetchone()
        if not treffer:
            raise SystemExit(f"Erwartetes Mapping fehlt: {name!r}")
        ids[schluessel] = treffer[0]

    for schluessel, d in mod.NEUE_MAPPINGS.items():
        nodes = json.dumps([sql_node(d["sql"], d["felder"], conn_id)], ensure_ascii=False)
        ziele = json.dumps([target(d["name"], d["felder"])], ensure_ascii=False)
        da = c.execute("select id from mappings where name=?", (d["name"],)).fetchone()
        if da:
            ids[schluessel] = da[0]
            if anwenden:
                c.execute("update mappings set sql_nodes=?, targets=? where id=?",
                          (nodes, ziele, da[0]))
            print(f"  ~ {d['name']}  (Mapping {da[0]}, aktualisiert)")
        elif anwenden:
            cur = c.execute(
                "insert into mappings (name, canvas_nodes, joins, fields, transform_nodes, "
                "constant_nodes, sql_nodes, agg_nodes, rest_nodes, lookup_nodes, calc_nodes, "
                "switch_nodes, sort_nodes, target_type, target_table, target_write_mode, "
                "target_options, targets, project_id) "
                "values (?, '[]','[]','[]','[]','[]', ?, '[]','[]','[]','[]','[]','[]', "
                "'dataset','','replace','{}', ?, ?)", (d["name"], nodes, ziele, projekt))
            ids[schluessel] = cur.lastrowid
            print(f"  + {d['name']}  (Mapping {cur.lastrowid}, neu)")
        else:
            ids[schluessel] = f"<neu:{schluessel}>"
            print(f"  + {d['name']}  (würde neu angelegt)")

    for _, d in (getattr(mod, "UEBERSICHT_ERWEITERN", {}) or {}).items():
        mid, sn, tg = c.execute("select id, sql_nodes, targets from mappings where name like ?",
                                (f"%{d['name_teil']}%",)).fetchone()
        nodes, ziele = json.loads(sn), json.loads(tg)
        sql, felder, geaendert = uebersicht_erweitern(nodes[0]["sql"], ziele[0]["fields"], d)
        if not geaendert:
            print(f"  = {d['name_teil']}: Spalte {d['feld']} schon vorhanden")
            continue
        nodes[0]["sql"] = sql
        nodes[0].setdefault("output_fields", []).append(d["feld"])
        ziele[0]["fields"] = felder
        print(f"  ± {d['name_teil']}: Spalte {d['feld']} ergänzt (Mapping {mid})")
        if anwenden:
            c.execute("update mappings set sql_nodes=?, targets=? where id=?",
                      (json.dumps(nodes, ensure_ascii=False),
                       json.dumps(ziele, ensure_ascii=False), mid))

    sch = json.loads(c.execute("select schema from forms where id=?", (form_id,)).fetchone()[0])
    n = widgets_verdrahten(sch.get("widgets") or [], mod.DRILLDOWNS,
                           getattr(mod, "EBENE2", None), lambda k: ids[k])
    print(f"\nFormular {form_id}: {n} Drilldowns gesetzt")
    if not anwenden:
        print("\n(Trockenlauf – mit --anwenden schreiben)")
        return
    c.execute("update forms set schema=? where id=?",
              (json.dumps(sch, ensure_ascii=False), form_id))
    c.commit()
    print("geschrieben.")


def anwenden_template(mod, pfad: str, anwenden: bool):
    with open(pfad, encoding="utf-8") as f:
        t = json.load(f)
    vorhandene = {m["id"]: m for m in t["mappings"]}
    conn = next((m["sql_nodes"][0].get("connection_id") for m in t["mappings"]
                 if m.get("sql_nodes")), None)
    for schluessel, d in mod.NEUE_MAPPINGS.items():
        eintrag = {"id": schluessel, "name": d["name"], "canvas_nodes": [], "joins": [],
                   "sql_nodes": [sql_node(d["sql"], d["felder"], conn)],
                   "agg_nodes": [], "transform_nodes": [], "constant_nodes": [],
                   "rest_nodes": [], "lookup_nodes": [], "calc_nodes": [],
                   "switch_nodes": [], "sort_nodes": [],
                   "targets": [target(d["name"], d["felder"])]}
        if schluessel in vorhandene:
            t["mappings"][t["mappings"].index(vorhandene[schluessel])] = eintrag
            print(f"  ~ {schluessel} aktualisiert")
        else:
            t["mappings"].append(eintrag)
            print(f"  + {schluessel} ergänzt")
    for schluessel, d in (getattr(mod, "UEBERSICHT_ERWEITERN", {}) or {}).items():
        m = vorhandene[schluessel]
        sql, felder, geaendert = uebersicht_erweitern(
            m["sql_nodes"][0]["sql"], m["targets"][0]["fields"], d)
        if geaendert:
            m["sql_nodes"][0]["sql"] = sql
            m["sql_nodes"][0].setdefault("output_fields", []).append(d["feld"])
            m["targets"][0]["fields"] = felder
            print(f"  ± {schluessel}: Spalte {d['feld']} ergänzt")
    n = widgets_verdrahten(t["forms"][0]["schema"].get("widgets") or [],
                           mod.DRILLDOWNS, getattr(mod, "EBENE2", None), lambda k: k)
    print(f"\n{pfad}: {n} Drilldowns gesetzt, {len(t['mappings'])} Mappings")
    if not anwenden:
        print("\n(Trockenlauf – mit --anwenden schreiben)")
        return
    teile = str(t.get("version") or "1.0").split(".")
    t["version"] = f"{teile[0]}.{int(teile[1]) + 1}" if len(teile) > 1 and teile[1].isdigit() \
        else t.get("version")
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(t, f, ensure_ascii=False, indent=2); f.write("\n")
    print(f"geschrieben (Version {t['version']}).")


def hauptlauf(mod, form_id: int):
    """Einstiegspunkt für ein Cockpit-Skript."""
    anwenden = "--anwenden" in sys.argv
    if "--template" in sys.argv:
        anwenden_template(mod, sys.argv[sys.argv.index("--template") + 1], anwenden)
    else:
        anwenden_db(mod, form_id, anwenden)
