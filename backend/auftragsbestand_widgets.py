"""Ergänzt die Kennzahlen des Auftragsbestands im Vertriebs-Cockpit.

Gehört zu backend/auftragsbestand.py: das Mapping „Vertrieb – Backlog KPI"
liefert seit dem Umbau laufend/Altbestand/ohne-Termin getrennt. Ohne passende
Widgets bliebe das unsichtbar.

Auch hier gilt der Doppelort: Formular in der DB UND Form-Schema im Template.

    python backend/auftragsbestand_widgets.py --templates --anwenden
    docker exec datenmonster-backend python /tmp/auftragsbestand_widgets.py --live --anwenden
"""
import argparse
import json
import os
import sqlite3

DB = "/app/uploads/datenmonster.db"
TEMPLATE = "jtl_vertrieb_cockpit.json"
ANKER = "w_ve_b_ueberf"          # hinter diesem Widget wird eingefügt

NEUE = [
    {"id": "w_ve_b_laufend", "type": "kpi", "label": "Bestand laufend (bis 90 Tage)",
     "action_id": "act_ve_backlog_kpi",
     "config": {"width": 3, "column": "BestandLaufend", "aggregation": "first",
                "prefix": "€ ", "suffix": "", "decimals": 2}},
    {"id": "w_ve_b_altbestand", "type": "kpi", "label": "Altbestand (über 90 Tage)",
     "action_id": "act_ve_backlog_kpi",
     "config": {"width": 3, "column": "BestandAlt", "aggregation": "first",
                "prefix": "€ ", "suffix": "", "decimals": 2,
                "info": "Aufträge, die seit über 90 Tagen offen sind. Bei PPS sind das "
                        "172 von 207 Vorgängen – der Bestand ist überwiegend Altbestand."}},
    {"id": "w_ve_b_ohne_termin", "type": "kpi", "label": "ohne Liefertermin",
     "action_id": "act_ve_backlog_kpi",
     "config": {"width": 3, "column": "OhneLiefertermin", "aggregation": "first",
                "prefix": "", "suffix": "", "decimals": 0,
                "info": "Diese Aufträge können nie „überfällig\" werden – "
                        "dVoraussichtlichesLieferdatum ist leer."}},
    {"id": "w_ve_b_ueberf_alt", "type": "kpi", "label": "Termin über 1 Jahr überfällig",
     "action_id": "act_ve_backlog_kpi",
     "config": {"width": 3, "column": "UeberfaelligAlt", "aggregation": "first",
                "prefix": "", "suffix": "", "decimals": 0,
                "info": "Karteileichen: bewusst aus der Kennzahl „Liefertermin "
                        "überschritten\" herausgehalten, damit die Warnung nicht "
                        "dauerhaft auf Altfälle zeigt."}},
]

# Bestehende Beschriftungen/Hinweise, die durch den Umbau ungenau geworden sind.
ANPASSUNGEN = {
    "w_ve_b_ueberf": {
        "label": "Liefertermin überschritten (letzte 12 Monate)"},
    "w_ve_tbl_backlog": {
        "config.info": "Momentaufnahme – unabhängig vom gewählten Zeitraum. Alle nicht "
                       "komplett ausgelieferten, nicht stornierten Aufträge ohne "
                       "MUSTER-Vorgänge. „Offener Warenwert\" ist die noch zu liefernde "
                       "Ware, „Offener Zahlbetrag\" der noch nicht bezahlte Rechnungsanteil."},
}


def bearbeite(schema):
    ws = schema.get("widgets")
    if not isinstance(ws, list):
        return 0
    vorhanden = {w.get("id") for w in ws if isinstance(w, dict)}
    n = 0

    for wid, felder in ANPASSUNGEN.items():
        for w in ws:
            if not isinstance(w, dict) or w.get("id") != wid:
                continue
            for pfad, wert in felder.items():
                if pfad.startswith("config."):
                    w.setdefault("config", {})[pfad.split(".", 1)[1]] = wert
                else:
                    w[pfad] = wert
            n += 1

    fehlend = [w for w in NEUE if w["id"] not in vorhanden]
    if fehlend:
        i = next((k for k, w in enumerate(ws)
                  if isinstance(w, dict) and w.get("id") == ANKER), len(ws) - 1)
        ws[i + 1:i + 1] = [json.loads(json.dumps(w)) for w in fehlend]
        n += len(fehlend)
    return n


def templates(anwenden):
    pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "templates", TEMPLATE)
    doc = json.load(open(pfad, encoding="utf-8"))
    n = sum(bearbeite(f.get("schema", {})) for f in doc.get("forms", []))
    print(f"  {TEMPLATE}: {n} Widgets ergänzt/angepasst")
    if anwenden and n:
        with open(pfad, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, ensure_ascii=False)
    return n


def live(anwenden):
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    gesamt = 0
    for r in c.execute("SELECT id, name, schema FROM forms").fetchall():
        if not r["schema"] or "act_ve_backlog_kpi" not in r["schema"]:
            continue
        schema = json.loads(r["schema"])
        n = bearbeite(schema)
        if not n:
            continue
        gesamt += n
        print(f"  Form {r['id']} ({r['name']}): {n} Widgets ergänzt/angepasst")
        if anwenden:
            c.execute("UPDATE forms SET schema = ? WHERE id = ?",
                      (json.dumps(schema, ensure_ascii=False), r["id"]))
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
    n = 0
    if a.templates:
        n += templates(a.anwenden)
    if a.live:
        n += live(a.anwenden)
    print(f"\n{n} {'angewandt' if a.anwenden else 'gefunden (Trockenlauf)'}")
