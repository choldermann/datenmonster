"""Schritt 2: in eazybusiness_synth ALLES leeren außer ERLAUBT.

Standard ist Löschen (Erlaubt-Liste statt Sperrliste): eine Produktionskopie
Spalte für Spalte zu säubern konvergiert nicht – vier Durchgänge an der alten
Demo fanden jedes Mal neue Reste. Trigger und Fremdschlüssel werden dafür
abgeschaltet und bleiben aus (der Generator schreibt danach ohne die
JTL-Prozeduren; gelesen wird die DB nur von Datenmonster).

    python -m tools.demo_daten.leeren            # Probelauf: zeigt, was ginge
    python -m tools.demo_daten.leeren --wirklich
"""
import sys
import time

from tools.demo_daten.erlaubt import ERLAUBT
from tools.demo_daten.verbindung import ZIEL, verbinden


def tabellen(cur):
    return cur.execute("""
        SELECT s.name, t.name, SUM(p.rows)
        FROM sys.tables t JOIN sys.schemas s ON s.schema_id = t.schema_id
        JOIN sys.partitions p ON p.object_id = t.object_id AND p.index_id IN (0, 1)
        WHERE t.is_ms_shipped = 0
        GROUP BY s.name, t.name""").fetchall()


def main(wirklich: bool):
    con = verbinden(ZIEL)
    cur = con.cursor()
    assert cur.execute("SELECT DB_NAME()").fetchone()[0] == ZIEL
    alle = tabellen(cur)
    erlaubt_klein = {e.lower() for e in ERLAUBT}
    weg = [(s, t, n) for s, t, n in alle if f"{s}.{t}".lower() not in erlaubt_klein and n > 0]
    print(f"{len(alle)} Tabellen, {len(weg)} mit Daten werden geleert "
          f"({sum(n for *_, n in weg):,} Zeilen), {len(alle) - len(weg)} bleiben/leer")
    if not wirklich:
        for s, t, n in sorted(weg, key=lambda x: -x[2])[:15]:
            print(f"   {s}.{t}: {n:,}")
        print("Probelauf – mit --wirklich ausführen"); return

    cur.execute("DISABLE TRIGGER ALL ON DATABASE")
    for s, t, _ in alle:
        cur.execute(f"ALTER TABLE [{s}].[{t}] NOCHECK CONSTRAINT ALL")
        cur.execute(f"ALTER TABLE [{s}].[{t}] DISABLE TRIGGER ALL")
    referenziert = {(r[0], r[1]) for r in cur.execute("""
        SELECT DISTINCT SCHEMA_NAME(o.schema_id), o.name FROM sys.foreign_keys f
        JOIN sys.objects o ON o.object_id = f.referenced_object_id""")}
    t0 = time.time()
    for i, (s, t, n) in enumerate(sorted(weg, key=lambda x: -x[2]), 1):
        if (s, t) not in referenziert:
            try:
                cur.execute(f"TRUNCATE TABLE [{s}].[{t}]")
                continue
            except Exception:
                pass
        while True:  # in Häppchen, damit das Protokoll klein bleibt
            cur.execute(f"DELETE TOP (50000) FROM [{s}].[{t}]")
            if cur.rowcount < 50000:
                break
        if cur.execute("SELECT OBJECTPROPERTY(OBJECT_ID(?), 'TableHasIdentity')", f"[{s}].[{t}]").fetchone()[0]:
            cur.execute(f"DBCC CHECKIDENT ('[{s}].[{t}]', RESEED, 0) WITH NO_INFOMSGS")
        if i % 50 == 0:
            cur.execute("CHECKPOINT")
            print(f"   {i}/{len(weg)} … {time.time() - t0:.0f}s")
    rest = [(s, t, n) for s, t, n in tabellen(cur)
            if n > 0 and f"{s}.{t}".lower() not in erlaubt_klein]
    print("Übrig außerhalb der Erlaubt-Liste:", rest or "nichts")


if __name__ == "__main__":
    main("--wirklich" in sys.argv)
