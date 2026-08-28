"""Nimmt die Versandkosten-Lücke in die KI-Kurzanalyse des GF-Cockpits auf.

Versandarten ohne hinterlegten Einkaufspreis lassen ihren Erlös als 100 % Marge
in den Rohertrag laufen (bei PPS betrifft das ALLE Versandpositionen). Die Kachel
„Versand ohne Kosten" zeigt die Zahl schon – die Lagebeurteilung soll sie
einordnen: woher sie kommt und was zu tun ist.

Die Auswertung selbst steckt im Code, nicht im Prompt: `buildSectionText(kind
"versandluecke")` im Frontend und `_versandluecke_text` in cockpit_report.py
formulieren denselben Text aus den Zahlen. Das Modell bekommt also einen fertigen
Befund und muss ihn nur einordnen – es kann ihn nicht verrechnen. Ist keine Lücke
da, liefert der Block nichts und das Thema kommt gar nicht erst vor.

Hier wird nur der Verweis darauf in die Widget-Konfiguration eingetragen.

Anwenden:
    docker cp backend/ki_versandluecke.py datenmonster-backend:/tmp/
    docker exec datenmonster-backend python /tmp/ki_versandluecke.py --anwenden
    python3 backend/ki_versandluecke.py --template templates/jtl_gf_cockpit.json --anwenden
"""
import sqlite3, json, sys

DB = "/app/uploads/datenmonster.db"

SEKTION = {"action_id": "act_overview_kpi",
           "label": "Datenqualität: Versandkosten",
           "kind": "versandluecke"}


def sektion_ergaenzen(widgets: list) -> bool:
    """Hängt den Block hinten an die extra_sections des KI-Widgets. True, wenn geändert."""
    for w in widgets:
        if w.get("type") != "ai_summary" or w.get("id") != "w_ai_uebersicht":
            continue
        cfg = w.setdefault("config", {})
        sek = cfg.setdefault("extra_sections", [])
        if any(s.get("kind") == SEKTION["kind"] for s in sek):
            return False
        # Ans Ende: der Befund gehört hinter die Fachbereiche, nicht zwischen sie.
        sek.append(dict(SEKTION))
        return True
    raise SystemExit("KI-Widget w_ai_uebersicht nicht gefunden")


def main_db(anwenden: bool):
    c = sqlite3.connect(DB)
    sch = json.loads(c.execute("select schema from forms where id=1").fetchone()[0])
    geaendert = sektion_ergaenzen(sch.get("widgets") or [])
    anz = len(next(w for w in sch["widgets"] if w.get("id") == "w_ai_uebersicht")
              ["config"]["extra_sections"])
    print(f"Formular 1: {anz} Zusatzblöcke, geändert: {geaendert}")
    if not anwenden:
        print("\n(Trockenlauf – mit --anwenden schreiben)")
        return
    if geaendert:
        c.execute("update forms set schema=? where id=1", (json.dumps(sch, ensure_ascii=False),))
        c.commit()
    print("geschrieben." if geaendert else "nichts zu tun.")


def main_template(pfad: str, anwenden: bool):
    with open(pfad, encoding="utf-8") as f:
        t = json.load(f)
    geaendert = sektion_ergaenzen(t["forms"][0]["schema"].get("widgets") or [])
    if geaendert:
        t["version"] = "2.9"
    print(f"{pfad}: geändert: {geaendert}")
    if not anwenden:
        print("\n(Trockenlauf – mit --anwenden schreiben)")
        return
    if geaendert:
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump(t, f, ensure_ascii=False, indent=2); f.write("\n")
    print("geschrieben." if geaendert else "nichts zu tun.")


if __name__ == "__main__":
    anwenden = "--anwenden" in sys.argv
    if "--template" in sys.argv:
        main_template(sys.argv[sys.argv.index("--template") + 1], anwenden)
    else:
        main_db(anwenden)
