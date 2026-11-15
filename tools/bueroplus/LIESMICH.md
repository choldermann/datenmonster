# büro+-Import in den SQL Server

Lädt die täglichen Exporte aus microtech büro+ (Export-Layouts als CSV) in den SQL Server, auf dem
die Datenmonster-Cockpits laufen (Vorlage **büro+ – GF-Cockpit**).

```
büro+ (Export-Layouts, täglich)  →  C:\Datenmonster\Export\*.csv
bp_import.ps1 (Aufgabenplanung)  →  stg.* (Rohtext)  →  dbo.bp_Uebernehmen  →  dbo.* (typisiert)
```

## Dateien

| Datei | Zweck |
|---|---|
| `bp_import.sql` | Einmal auf dem SQL Server ausführen: Schema `stg`, Staging-Tabellen, Zieltabellen (falls fehlend), Prozeduren `dbo.bp_Lade_*` / `dbo.bp_Uebernehmen`, Protokoll `dbo.ImportLog`. Ändert keine vorhandenen Daten. |
| `sql_bauen.py` | Erzeugt `bp_import.sql` aus den Spaltendefinitionen. Neue Felder im Layout → hier eintragen, neu erzeugen, ausführen. |
| `bp_import.ps1` | Das Ladeskript (Windows PowerShell 5.1, keine Zusatzmodule). |
| `bp_import.config.beispiel.psd1` | Vorlage für `bp_import.config.psd1`. |

## Einrichten beim Kunden

1. `bp_import.sql` auf der Kunden-Datenbank ausführen (SSMS oder Datenmonster-SQL-Konsole).
2. Ordner z. B. `C:\Datenmonster\Import\` anlegen, `bp_import.ps1` und die Konfiguration
   (`bp_import.config.psd1`) hineinkopieren und anpassen.
3. Passwort hinterlegen – **unter dem Konto, unter dem die Aufgabe laufen wird**:
   `powershell -ExecutionPolicy Bypass -File C:\Datenmonster\Import\bp_import.ps1 -PasswortSetzen`
   Verschlüsselt per Windows-DPAPI mit dem Schlüssel des Kontos; ist der nicht nutzbar (Meldung
   „Dem Computer muss für Delegierungszwecke vertraut werden“), automatisch mit dem Rechnerschlüssel –
   die Datei ist dann per Dateirechten nur für dieses Konto, SYSTEM und Administratoren lesbar.
   Läuft die Aufgabe unter einem anderen Konto, `-PasswortSetzen` unter genau diesem ausführen.
4. Probelauf ohne Schreiben: `… bp_import.ps1 -Trockenlauf` → prüft Kopfzeilen und Feldzahlen.
5. Echter Lauf: `… bp_import.ps1` → Logdatei unter `LogVerzeichnis`, Zeilen in `dbo.ImportLog`.
6. Aufgabenplanung: täglich nach dem büro+-Export, Programm `powershell.exe`, Argumente
   `-NoProfile -ExecutionPolicy Bypass -File "C:\Datenmonster\Import\bp_import.ps1"`,
   „Unabhängig von der Benutzeranmeldung ausführen“. Exitcode 1 = mindestens eine Gruppe nicht aktualisiert.

## Was geprüft wird (sonst bleibt der alte Stand)

- Kopfzeile der Datei = Spalten der Staging-Tabelle (Reihenfolge und Schreibweise). Eine geänderte
  Feldauswahl im büro+-Layout fällt dadurch sofort auf.
- Jeder Datensatz hat genau so viele Felder wie die Kopfzeile.
- Datei nicht älter als `MaxAlterStunden` (Export ist gelaufen).
- Mindestens `MinAnteil` (80 %) der bisherigen Zeilenzahl (kein halber Export).
- Jeder Wert lässt sich umwandeln (Zahl, Datum, Ja/Nein), Texte passen in die Spaltenbreite,
  Schlüssel vorhanden und eindeutig. Die Fehlermeldung nennt Spalte, Anzahl und ein Beispiel.
- Vorgänge (Kopf, Archiv, Positionen) werden zusammen ersetzt – nie Köpfe neu und Positionen alt.

## Regeln für die büro+-Layouts

- Textfelder in `"…"` setzen, Zahlen/Datum/Ja-Nein ohne.
- Kopfzeile = büro+-Feldname ohne `«»`, ohne Anführungszeichen, ohne Punkte (`Vog.Li.AdrNr` → `VogLiAdrNr`).
- Datum `TT.MM.JJJJ`, Zahlen mit Dezimalkomma (büro+-Standard). `30.12.1899` = leer.
