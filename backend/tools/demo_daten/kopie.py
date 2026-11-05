"""(Erledigt 05.11.2026 – die Quelle gibt es nicht mehr; nur zur Nachvollziehbarkeit.)
Schritt 1: eazybusiness_demo → eazybusiness_synth kopieren (COPY_ONLY).
Die Quelle bleibt unverändert. Bricht ab, wenn das Ziel schon existiert."""
import sys

from tools.demo_daten.verbindung import QUELLE, ZIEL, verbinden, ausfuehren_leeren

DATEN = r"C:\Program Files\Microsoft SQL Server\MSSQL16.SQLEXPRESS\MSSQL\DATA"


def main():
    con = verbinden("master")
    cur = con.cursor()
    if cur.execute("SELECT 1 FROM sys.databases WHERE name = ?", ZIEL).fetchone():
        print(f"{ZIEL} gibt es schon – nichts getan."); sys.exit(1)
    bak = rf"{DATEN}\{ZIEL}_quelle.bak"
    print("Sichere", QUELLE, "…")
    ausfuehren_leeren(cur, f"BACKUP DATABASE [{QUELLE}] TO DISK = N'{bak}' WITH COPY_ONLY, INIT")
    namen = [r[0] for r in cur.execute(f"RESTORE FILELISTONLY FROM DISK = N'{bak}'").fetchall()]
    print("Logische Dateien:", namen)
    move = ", ".join(
        f"MOVE N'{n}' TO N'{DATEN}\\{ZIEL}{'_log.ldf' if n.endswith('_log') else '.mdf'}'" for n in namen)
    print("Stelle als", ZIEL, "wieder her …")
    ausfuehren_leeren(cur, f"RESTORE DATABASE [{ZIEL}] FROM DISK = N'{bak}' WITH {move}, RECOVERY")
    ausfuehren_leeren(cur, f"ALTER DATABASE [{ZIEL}] SET RECOVERY SIMPLE")
    print("Fertig:", cur.execute("SELECT name, state_desc FROM sys.databases WHERE name = ?", ZIEL).fetchone())


if __name__ == "__main__":
    main()
