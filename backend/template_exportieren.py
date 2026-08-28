"""Schreibt ein Template aus der Datenbank als Datei ins Repo.

Der Unternehmensmonitor lebte nur in der Datenbank – es gab kein
`templates/jtl_monitor.json`. Damit war er als einziges der sieben Cockpits nicht
versioniert: seine 26 Prüfregeln existierten ausschließlich in der laufenden
Installation, jede Regeländerung war unwiderruflich und auf keinem zweiten
Rechner nachvollziehbar.

Läuft IM Container (die Datenbank liegt im Docker-Volume) und schreibt über den
gemounteten Backend-Ordner ins Repo:

    docker cp backend/template_exportieren.py datenmonster-backend:/tmp/
    docker exec datenmonster-backend python /tmp/template_exportieren.py jtl_monitor

Ohne --ziel landet die Datei in /app/templates_export/ und muss von Hand
herübergeholt werden; mit --ziel schreibt sie direkt dorthin.
"""
import sqlite3, json, sys, os

DB = "/app/uploads/datenmonster.db"
# Die Datei-Konvention der übrigen Templates: zwei Leerzeichen Einrückung,
# Umlaute als Umlaute, abschließender Zeilenumbruch.
FORMAT_VERSION = "1.0"


def exportieren(template_id: str, ziel: str) -> str:
    c = sqlite3.connect(DB)
    zeile = c.execute("select content from templates where template_id=?",
                      (template_id,)).fetchone()
    if not zeile:
        raise SystemExit(f"Template {template_id!r} nicht in der Datenbank")
    inhalt = json.loads(zeile[0]) if isinstance(zeile[0], str) else zeile[0]

    # In der Datenbank stand die Format-Version als Zahl; die Spezifikation
    # (doku/template-format.md) und alle Repo-Dateien führen sie als Text "1.0".
    if str(inhalt.get("format_version")) != FORMAT_VERSION:
        print(f"  format_version {inhalt.get('format_version')!r} → {FORMAT_VERSION!r}")
        inhalt["format_version"] = FORMAT_VERSION

    os.makedirs(os.path.dirname(ziel) or ".", exist_ok=True)
    with open(ziel, "w", encoding="utf-8") as f:
        json.dump(inhalt, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"  {len(inhalt.get('mappings') or [])} Mappings, "
          f"{len(inhalt.get('forms') or [])} Formulare, "
          f"{len(inhalt.get('alert_rules') or [])} Prüfregeln "
          f"→ {ziel}")

    # Die korrigierte Format-Version gehört auch zurück in die Datenbank, sonst
    # weichen Datei und Installation beim nächsten Export wieder voneinander ab.
    c.execute("update templates set content=? where template_id=?",
              (json.dumps(inhalt, ensure_ascii=False), template_id))
    c.commit()
    return ziel


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    tid = args[0]
    ziel = next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--ziel"),
                f"/app/templates_export/{tid}.json")
    print(f"Template {tid}:")
    exportieren(tid, ziel)
