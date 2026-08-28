"""Schiebt „Heute zu tun" unter die Kacheln und Diagramme.

Die Warnungsliste stand als erstes Widget im Übersichts-Reiter. Wer das Cockpit
öffnet, will aber zuerst die Lage sehen – Umsatz, Ertrag, Verlauf – und danach,
was daraus zu tun ist. Eine lange Aufgabenliste ganz oben schob die Kennzahlen
unter die Falz.

Die Liste wandert ans ENDE ihres eigenen Reiters, nicht ans Ende des Formulars:
ein Cockpit hat viele Reiter hintereinander in derselben Widget-Liste, und die
Zugehörigkeit steckt in result_tabs[].action_ids. Wer stumpf ans Listenende
schiebt, verfrachtet die Warnungen in den letzten Reiter.

Anwenden:
    docker cp backend/aufgaben_nach_unten.py datenmonster-backend:/tmp/
    docker exec datenmonster-backend python /tmp/aufgaben_nach_unten.py --anwenden
    python3 backend/aufgaben_nach_unten.py --template templates/jtl_gf_cockpit.json --anwenden
"""
import sqlite3, json, sys

DB = "/app/uploads/datenmonster.db"


# Beide Bauformen der Aufgabenliste: die Warnungen der Cockpits (alerts) und die
# Ampel-Prüfliste des Health-Checks (tasklist). Beide beantworten „was ist zu tun",
# beide gehören unter die Lage.
AUFGABEN_TYPEN = ("alerts", "tasklist")


def _reiter_von(schema: dict, action_id):
    """action_ids des Reiters, in dem diese Action angezeigt wird (oder None)."""
    for tab in (schema.get("result_tabs") or []):
        ids = tab.get("action_ids") or []
        if action_id in ids:
            return set(ids)
    return None


def umsortieren(schema: dict) -> list:
    """Verschiebt jede Aufgabenliste ans Ende ihres Reiters. Gibt die Namen zurück."""
    widgets = schema.get("widgets") or []
    bewegt = []
    for w in list(widgets):
        if w.get("type") not in AUFGABEN_TYPEN:
            continue
        gruppe = _reiter_von(schema, w.get("action_id"))
        # Ohne Reiter-Zuordnung ist das ganze Formular die Gruppe.
        geschwister = [i for i, x in enumerate(widgets)
                       if gruppe is None or x.get("action_id") in gruppe]
        if not geschwister or widgets[geschwister[-1]] is w:
            continue                                   # steht schon unten
        widgets.remove(w)
        # Nach dem Entfernen neu bestimmen, sonst zeigt der Index daneben.
        geschwister = [i for i, x in enumerate(widgets)
                       if gruppe is None or x.get("action_id") in gruppe]
        widgets.insert(geschwister[-1] + 1, w)
        bewegt.append(w.get("label") or w.get("id"))
    schema["widgets"] = widgets
    return bewegt


def _bericht(schema, wo):
    for tab in (schema.get("result_tabs") or [{"id": "-", "action_ids": None}]):
        ids = tab.get("action_ids")
        reihe = [w for w in schema["widgets"]
                 if ids is None or w.get("action_id") in ids]
        if not any(w.get("type") in AUFGABEN_TYPEN for w in reihe):
            continue
        print(f"  {wo} / {tab.get('label') or tab.get('id')}:")
        for w in reihe:
            print(f"      {w.get('type'):12} {w.get('label')}")


def main_db(anwenden: bool):
    c = sqlite3.connect(DB)
    aenderungen = []
    for fid, name, roh in c.execute("select id,name,schema from forms").fetchall():
        if not roh:
            continue
        schema = json.loads(roh) if isinstance(roh, str) else roh
        bewegt = umsortieren(schema)
        if not bewegt:
            continue
        aenderungen.append((fid, name, schema, bewegt))
        print(f"Formular {fid} ({name}): {bewegt} nach unten")
        _bericht(schema, f"Formular {fid}")
        if anwenden:
            c.execute("update forms set schema=? where id=?",
                      (json.dumps(schema, ensure_ascii=False), fid))

    # Dieselbe Reihenfolge in den installierten Templates, sonst kommt sie bei
    # einer Neuinstallation zurück.
    for tid, roh in c.execute("select template_id,content from templates").fetchall():
        if not roh:
            continue
        inhalt = json.loads(roh) if isinstance(roh, str) else roh
        bewegt = []
        for form in (inhalt.get("forms") or []):
            bewegt += umsortieren(form.get("schema") or {})
        if not bewegt:
            continue
        print(f"DB-Template {tid}: {bewegt} nach unten")
        aenderungen.append((tid, tid, None, bewegt))
        if anwenden:
            c.execute("update templates set content=? where template_id=?",
                      (json.dumps(inhalt, ensure_ascii=False), tid))

    if not aenderungen:
        print("nichts zu tun – alle Aufgabenlisten stehen schon unten.")
        return
    if not anwenden:
        print("\n(Trockenlauf – mit --anwenden schreiben)")
        return
    c.commit()
    print("\ngeschrieben.")


def main_template(pfad: str, anwenden: bool):
    with open(pfad, encoding="utf-8") as f:
        t = json.load(f)
    bewegt = []
    for form in (t.get("forms") or []):
        bewegt += umsortieren(form.get("schema") or {})
    print(f"{pfad}: {bewegt or 'nichts zu tun'}")
    if not bewegt or not anwenden:
        if bewegt:
            print("\n(Trockenlauf – mit --anwenden schreiben)")
        return
    # Minor hochzählen statt einer festen Nummer – das Skript läuft über mehrere
    # Templates mit ganz unterschiedlichen Ständen.
    teile = str(t.get("version") or "1.0").split(".")
    t["version"] = f"{teile[0]}.{int(teile[1]) + 1}" if len(teile) > 1 and teile[1].isdigit() \
        else str(t.get("version") or "1.0")
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(t, f, ensure_ascii=False, indent=2); f.write("\n")
    print("geschrieben.")


if __name__ == "__main__":
    anwenden = "--anwenden" in sys.argv
    if "--template" in sys.argv:
        main_template(sys.argv[sys.argv.index("--template") + 1], anwenden)
    else:
        main_db(anwenden)
