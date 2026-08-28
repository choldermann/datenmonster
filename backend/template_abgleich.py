"""Meldet, wo Template-Dateien und installierte Templates auseinanderlaufen.

Ein Template lebt an zwei Orten: als Datei unter `templates/` (versioniert) und
als Datensatz in der Datenbank (was bei einer Neuinstallation wirklich entsteht).
Wer nur einen der beiden ändert, merkt es erst, wenn ein Kunde ein Cockpit
installiert und etwas fehlt – so geschehen beim Unternehmensmonitor, dessen
KI-Widget in der Datei die Bewertungstabelle nicht eingeschaltet hatte.

Läuft auf dem HOST, holt sich die Datenbankstände über `docker exec` (die
Datenbank liegt im Docker-Volume, nicht im Projektordner).

    python3 backend/template_abgleich.py                    # Bericht, Rückgabewert 1 bei Abweichung
    python3 backend/template_abgleich.py --alle             # alle Unterschiede statt der ersten acht
    python3 backend/template_abgleich.py --export <id> …    # Datenbank → Datei
    python3 backend/template_abgleich.py --import <id> …    # Datei → Datenbank

Die Richtung ist bewusst NICHT automatisch: mal ist die Datenbank weiter (ein
Skript hat die Installation gepatcht), mal die Datei (ein Fix wurde committet,
aber nie eingespielt). Beides kam schon vor. Der Bericht sagt, was abweicht –
entscheiden muss ein Mensch, je Template.

Als Git-Hook einsetzbar: der Rückgabewert ist 0, solange alles deckungsgleich ist.
"""
import json, os, subprocess, sys

CONTAINER = os.environ.get("DM_CONTAINER", "datenmonster-backend")
ORDNER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")

_LESER = """
import sqlite3, json
db = sqlite3.connect("/app/uploads/datenmonster.db")
aus = {}
for tid, inhalt in db.execute("select template_id, content from templates"):
    aus[tid] = json.loads(inhalt) if isinstance(inhalt, str) else inhalt
print(json.dumps(aus, ensure_ascii=False))
"""


def db_templates() -> dict:
    p = subprocess.run(["docker", "exec", "-i", CONTAINER, "python", "-c", _LESER],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"Container {CONTAINER} nicht erreichbar:\n{p.stderr.strip()[:400]}")
    return json.loads(p.stdout)


def datei_templates() -> dict:
    aus = {}
    for name in sorted(os.listdir(ORDNER)):
        if not name.endswith(".json"):
            continue
        pfad = os.path.join(ORDNER, name)
        try:
            inhalt = json.load(open(pfad, encoding="utf-8"))
        except Exception as e:
            print(f"  ! {name}: kein gültiges JSON ({e})")
            continue
        tid = inhalt.get("template_id")
        if not tid:
            print(f"  ! {name}: template_id fehlt")
            continue
        aus[tid] = (pfad, inhalt)
    return aus


def _pfade(a, b, pfad="", tiefe=0, treffer=None, deckel=8):
    """Sammelt Stellen, an denen sich zwei Strukturen unterscheiden."""
    treffer = treffer if treffer is not None else []
    if len(treffer) >= deckel or tiefe > 12:
        return treffer
    if type(a) is not type(b):
        treffer.append(f"{pfad or '/'}: {type(a).__name__} ≠ {type(b).__name__}")
    elif isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                treffer.append(f"{pfad}/{k}: nur in der Datei, fehlt in der Datenbank")
            elif k not in b:
                treffer.append(f"{pfad}/{k}: nur in der Datenbank, fehlt in der Datei")
            else:
                _pfade(a[k], b[k], f"{pfad}/{k}", tiefe + 1, treffer, deckel)
    elif isinstance(a, list):
        if len(a) != len(b):
            treffer.append(f"{pfad}: {len(a)} Einträge in der DB, {len(b)} in der Datei")
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                _pfade(x, y, f"{pfad}[{i}]", tiefe + 1, treffer, deckel)
    elif a != b:
        treffer.append(f"{pfad}: DB {str(a)[:55]!r} ≠ Datei {str(b)[:55]!r}")
    return treffer


_SCHREIBER = """
import sqlite3, json, sys
inhalt = json.load(sys.stdin)
db = sqlite3.connect("/app/uploads/datenmonster.db")
db.execute("update templates set content=?, version=? where template_id=?",
           (json.dumps(inhalt, ensure_ascii=False), str(inhalt.get("version") or "1.0"),
            inhalt["template_id"]))
db.commit()
print("ok")
"""


def in_db_schreiben(inhalt: dict):
    p = subprocess.run(["docker", "exec", "-i", CONTAINER, "python", "-c", _SCHREIBER],
                       input=json.dumps(inhalt, ensure_ascii=False),
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"Schreiben fehlgeschlagen:\n{p.stderr.strip()[:400]}")


def main(exportieren: list, importieren: list, alle: bool) -> int:
    aus_db = db_templates()
    aus_datei = datei_templates()
    abweichungen = 0

    for tid in sorted(set(aus_db) | set(aus_datei)):
        in_db, in_datei = tid in aus_db, tid in aus_datei
        if in_db and not in_datei:
            # Nicht jedes DB-Template gehört ins Repo (selbst gebaute, importierte).
            print(f"  ~ {tid}: nur in der Datenbank, keine Datei im Repo")
            continue
        if in_datei and not in_db:
            print(f"  ~ {tid}: nur als Datei, in dieser Installation nicht vorhanden")
            continue
        pfad, inhalt = aus_datei[tid]
        if aus_db[tid] == inhalt:
            print(f"  ✓ {tid}")
            continue
        abweichungen += 1
        print(f"  ✗ {tid}: Datei und Datenbank weichen ab")
        for zeile in _pfade(aus_db[tid], inhalt, deckel=10**6 if alle else 8):
            print(f"      {zeile}")
        if tid in exportieren:
            with open(pfad, "w", encoding="utf-8") as f:
                json.dump(aus_db[tid], f, ensure_ascii=False, indent=2)
                f.write("\n")
            print(f"      → {os.path.relpath(pfad)} aus der Datenbank neu geschrieben")
            abweichungen -= 1
        elif tid in importieren:
            in_db_schreiben(inhalt)
            print(f"      → Datenbank aus {os.path.relpath(pfad)} überschrieben")
            abweichungen -= 1

    if not abweichungen:
        print("\nAlle Templates deckungsgleich.")
        return 0
    print(f"\n{abweichungen} Template(s) abweichend. Richtung je Template wählen:"
          f"\n  --export <id>  Datenbank → Datei      --import <id>  Datei → Datenbank")
    return 1


def _ids_nach(flag: str) -> list:
    """Alle Argumente hinter einem Schalter bis zum nächsten Schalter."""
    if flag not in sys.argv:
        return []
    aus = []
    for a in sys.argv[sys.argv.index(flag) + 1:]:
        if a.startswith("--"):
            break
        aus.append(a)
    return aus


if __name__ == "__main__":
    sys.exit(main(_ids_nach("--export"), _ids_nach("--import"), "--alle" in sys.argv))
