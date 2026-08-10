"""Holt die KI-Wissensdatenbank aus einer alten datenmonster.db in die laufende DB.

Läuft IM Backend-Container (siehe import-wissen.sh). Überträgt nur Klartext-Wissen –
keine Zugangsdaten, daher ist der alte SECRET_KEY nicht nötig.

  ai_memory_knowledge / _solutions / _corrections   → 1:1 (neue IDs)
  schema_table_meta / _column_meta / _relation_meta → nur mit --connection-id,
                                                      da sie an einer Verbindung hängen

Doppelte Einträge werden anhand eines fachlichen Schlüssels übersprungen, der Import
ist also wiederholbar.
"""
import argparse
import sqlite3
import sys

NEW_DB = "/app/uploads/datenmonster.db"

# Tabelle → Spalten, die einen Eintrag fachlich eindeutig machen (gegen Doppelimport)
AI_TABLES = {
    "ai_memory_knowledge":   ("scope", "scope_id", "title"),
    "ai_memory_solutions":   ("title", "prompt"),
    "ai_memory_corrections": ("original_prompt", "user_correction"),
}
SCHEMA_TABLES = {
    "schema_table_meta":    ("connection_id", "table_full_name"),
    "schema_column_meta":   ("connection_id", "table_full_name", "column_name"),
    "schema_relation_meta": ("connection_id", "from_table", "from_col", "to_table", "to_col"),
}


def columns(conn, table):
    return [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]


def copy_table(old, new, table, key_cols, remap_connection=None):
    """Kopiert Zeilen, die es fachlich noch nicht gibt. Gibt (kopiert, übersprungen) zurück."""
    old_cols = columns(old, table)
    new_cols = columns(new, table)
    if not old_cols:
        return 0, 0, f"in der alten DB nicht vorhanden"

    # Nur Spalten übernehmen, die es in beiden Schemata gibt (Schema-Drift abfangen);
    # "id" weglassen, damit die neue DB eigene vergibt.
    shared = [c for c in old_cols if c in new_cols and c != "id"]
    if not shared:
        return 0, 0, "keine gemeinsamen Spalten"

    existing = {
        tuple(r) for r in new.execute(f'SELECT {",".join(key_cols)} FROM "{table}"')
    }

    copied = skipped = 0
    for row in old.execute(f'SELECT {",".join(shared)} FROM "{table}"'):
        values = dict(zip(shared, row))
        if remap_connection is not None and "connection_id" in values:
            values["connection_id"] = remap_connection

        key = tuple(values.get(k) for k in key_cols)
        if key in existing:
            skipped += 1
            continue

        cols = list(values)
        new.execute(
            f'INSERT INTO "{table}" ({",".join(cols)}) VALUES ({",".join("?" * len(cols))})',
            [values[c] for c in cols],
        )
        existing.add(key)
        copied += 1

    return copied, skipped, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("old_db", help="Pfad zur alten datenmonster.db (im Container)")
    ap.add_argument("--connection-id", type=int, default=None,
                    help="Neue Verbindungs-ID, auf die das Schema-Wissen umgebogen wird. "
                         "Ohne Angabe wird das Schema-Wissen übersprungen.")
    ap.add_argument("--dry-run", action="store_true", help="nichts schreiben, nur zählen")
    args = ap.parse_args()

    old = sqlite3.connect(f"file:{args.old_db}?mode=ro", uri=True)
    new = sqlite3.connect(NEW_DB)

    total = 0
    print("── KI-Gedächtnis ──")
    for table, key in AI_TABLES.items():
        copied, skipped, err = copy_table(old, new, table, key)
        total += copied
        note = f" ({err})" if err else (f", {skipped} schon vorhanden" if skipped else "")
        print(f"  {table:<24} {copied:>4} übernommen{note}")

    print("── Schema-Wissen ──")
    if args.connection_id is None:
        print("  übersprungen – ohne --connection-id nicht zuzuordnen")
    else:
        for table, key in SCHEMA_TABLES.items():
            copied, skipped, err = copy_table(old, new, table, key,
                                              remap_connection=args.connection_id)
            total += copied
            note = f" ({err})" if err else (f", {skipped} schon vorhanden" if skipped else "")
            print(f"  {table:<24} {copied:>4} übernommen{note}  → Verbindung {args.connection_id}")

    if args.dry_run:
        new.rollback()
        print(f"\nProbelauf – nichts geschrieben ({total} Zeilen wären übernommen worden).")
    else:
        new.commit()
        print(f"\n{total} Zeilen übernommen.")

    old.close()
    new.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
