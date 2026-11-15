#Requires -Version 5.1
<#
.SYNOPSIS
  Lädt die täglichen microtech-büro+-Exporte in den SQL Server (Staging stg.* → dbo.*).

.DESCRIPTION
  Liest die CSV-Dateien aus dem Exportordner mit den büro+-Eigenheiten:
    - Textfelder stehen in "…", innere Anführungszeichen werden NICHT verdoppelt,
    - Zeilenumbrüche und Semikolons dürfen im Text stehen.
  Regel: Ein Feld in Anführungszeichen endet erst bei '";' bzw. '"' + Zeilenende.

  Je Gruppe (Artikel | Adressen | Vorgänge) werden die Dateien roh in stg.* geschrieben
  und anschließend dbo.bp_Uebernehmen aufgerufen. Die Prozedur prüft alle Werte, wandelt
  sie um und ersetzt die Zieltabellen in EINER Transaktion – bei einem Fehler bleibt der
  bisherige Stand vollständig erhalten. Protokoll: Logdatei + Tabelle dbo.ImportLog.

.PARAMETER Konfig
  Pfad zur Konfigurationsdatei (Vorgabe: bp_import.config.psd1 neben dem Skript).

.PARAMETER Trockenlauf
  Nur lesen und prüfen (Kopfzeilen, Feldzahlen). Schreibt nichts in die Datenbank.

.PARAMETER PasswortSetzen
  Fragt das Passwort des SQL-Benutzers ab und speichert es verschlüsselt (Windows-DPAPI,
  nur für DIESEN Windows-Benutzer auf DIESEM Rechner lesbar). Unter dem Konto ausführen,
  unter dem später die Aufgabenplanung läuft.

.EXAMPLE
  .\bp_import.ps1 -PasswortSetzen
  .\bp_import.ps1 -Trockenlauf
  .\bp_import.ps1
#>
[CmdletBinding()]
param(
    [string]$Konfig = (Join-Path $PSScriptRoot 'bp_import.config.psd1'),
    [switch]$Trockenlauf,
    [switch]$PasswortSetzen
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

# ── Konfiguration ───────────────────────────────────────────────────────────
if (-not (Test-Path -LiteralPath $Konfig)) { throw "Konfigurationsdatei nicht gefunden: $Konfig" }
$cfg = Import-PowerShellDataFile -LiteralPath $Konfig

function Get-Pfad([string]$p) {
    if ([System.IO.Path]::IsPathRooted($p)) { return $p }
    return (Join-Path $PSScriptRoot $p)
}
$passwortDatei = Get-Pfad $cfg.PasswortDatei

if ($PasswortSetzen) {
    $sec = Read-Host -AsSecureString "Passwort für SQL-Benutzer '$($cfg.Benutzer)'"
    $sec | ConvertFrom-SecureString | Set-Content -LiteralPath $passwortDatei -Encoding ASCII
    Write-Host "Gespeichert (verschlüsselt): $passwortDatei"
    return
}

# ── Protokoll ───────────────────────────────────────────────────────────────
$logDir = Get-Pfad $cfg.LogVerzeichnis
if (-not (Test-Path -LiteralPath $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$logDatei = Join-Path $logDir ("bp_import_{0:yyyy-MM-dd}.log" -f (Get-Date))
function Log([string]$text, [string]$stufe = 'INFO') {
    $zeile = "{0:yyyy-MM-dd HH:mm:ss} [{1}] {2}" -f (Get-Date), $stufe, $text
    Add-Content -LiteralPath $logDatei -Value $zeile -Encoding UTF8
    if ($stufe -eq 'FEHLER') { Write-Host $zeile -ForegroundColor Red } else { Write-Host $zeile }
}
# alte Logdateien aufräumen
$tage = 30; if ($cfg.ContainsKey('LogTage')) { $tage = [int]$cfg.LogTage }
Get-ChildItem -LiteralPath $logDir -Filter 'bp_import_*.log' -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$tage) } | Remove-Item -ErrorAction SilentlyContinue

# ── büro+-CSV-Leser (C#, schnell auch bei 300.000 Zeilen) ───────────────────
if (-not ('BpCsv' -as [type])) {
Add-Type -Language CSharp -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

public static class BpCsv
{
    // Liefert alle Datensätze inkl. Kopfzeile. Ein Feld in "..." endet erst bei
    // '";' oder '"' + CRLF (bzw. Dateiende); innere " bleiben unverändert stehen.
    public static List<string[]> Lesen(string pfad)
    {
        string text = File.ReadAllText(pfad, new UTF8Encoding(false));
        if (text.Length > 0 && text[0] == '\uFEFF') text = text.Substring(1);
        List<string[]> saetze = new List<string[]>();
        List<string> satz = new List<string>();
        int i = 0, n = text.Length;
        while (i < n)
        {
            if (text[i] == '"')
            {
                int a = text.IndexOf("\";", i + 1, StringComparison.Ordinal);
                int grenze = (a != -1) ? a : n;
                int b = text.IndexOf("\"\r\n", i + 1, grenze - (i + 1), StringComparison.Ordinal);
                if (b == -1 && a == -1)
                {
                    if (text.EndsWith("\"")) b = n - 1;
                    else throw new FormatException("Nicht abgeschlossenes Textfeld ab Zeichen " + i + ": " + Ausschnitt(text, i));
                }
                if (b != -1)
                {
                    satz.Add(text.Substring(i + 1, b - i - 1));
                    saetze.Add(satz.ToArray()); satz = new List<string>();
                    i = b + 3;
                }
                else
                {
                    satz.Add(text.Substring(i + 1, a - i - 1));
                    i = a + 2;
                }
            }
            else
            {
                int a = text.IndexOf(';', i);
                int b = text.IndexOf("\r\n", i, StringComparison.Ordinal);
                if (b == -1) b = n;
                if (a != -1 && a < b)
                {
                    satz.Add(text.Substring(i, a - i));
                    i = a + 1;
                }
                else
                {
                    satz.Add(text.Substring(i, b - i));
                    saetze.Add(satz.ToArray()); satz = new List<string>();
                    i = b + 2;
                }
            }
        }
        if (satz.Count > 0) saetze.Add(satz.ToArray());
        // Leerzeilen (z. B. abschließendes CRLF) entfernen
        saetze.RemoveAll(delegate (string[] s) { return s.Length == 1 && s[0].Length == 0; });
        return saetze;
    }

    static string Ausschnitt(string t, int i)
    {
        int len = Math.Min(60, t.Length - i);
        return t.Substring(i, len).Replace("\r", "\\r").Replace("\n", "\\n");
    }
}
'@
}

# ── Datenbank ───────────────────────────────────────────────────────────────
function Neue-Verbindung {
    if (-not (Test-Path -LiteralPath $passwortDatei)) {
        throw "Kein Passwort hinterlegt. Einmal ausführen: .\bp_import.ps1 -PasswortSetzen"
    }
    $sec = Get-Content -LiteralPath $passwortDatei | ConvertTo-SecureString
    $sb = New-Object System.Data.SqlClient.SqlConnectionStringBuilder
    $sb['Data Source'] = $cfg.Server
    $sb['Initial Catalog'] = $cfg.Datenbank
    $sb['User ID'] = $cfg.Benutzer
    $sb['Password'] = [System.Net.NetworkCredential]::new('', $sec).Password
    $sb['Encrypt'] = $true
    $sb['TrustServerCertificate'] = $true
    $sb['Connect Timeout'] = 30
    $sb['Application Name'] = 'bp_import'
    $con = New-Object System.Data.SqlClient.SqlConnection $sb.ConnectionString
    $con.Open()
    return $con
}

function Get-StagingSpalten($con, [string]$tabelle) {
    $cmd = $con.CreateCommand()
    $cmd.CommandText = "SELECT name FROM sys.columns WHERE object_id = OBJECT_ID(@t) ORDER BY column_id"
    [void]$cmd.Parameters.AddWithValue('@t', "stg.$tabelle")
    $r = $cmd.ExecuteReader(); $sp = New-Object System.Collections.Generic.List[string]
    while ($r.Read()) { $sp.Add($r.GetString(0)) }
    $r.Close()
    if ($sp.Count -eq 0) { throw "Staging-Tabelle stg.$tabelle fehlt – bp_import.sql auf dem Server ausführen." }
    return ,$sp.ToArray()
}

# Datei lesen und gegen die erwarteten Spalten prüfen → DataTable (alles Text)
function Lese-Datei([string]$pfad, [string[]]$spalten, [string]$tabelle) {
    $saetze = [BpCsv]::Lesen($pfad)
    if ($saetze.Count -eq 0) { throw "$tabelle`: Datei ist leer." }
    $kopf = [string[]]$saetze[0]
    $leerAmEnde = ($kopf.Length -gt 0 -and $kopf[$kopf.Length - 1] -eq '')
    $kopfOhne = if ($leerAmEnde) { $kopf[0..($kopf.Length - 2)] } else { $kopf }
    if (($kopfOhne -join ';') -cne ($spalten -join ';')) {
        throw ("$tabelle`: Kopfzeile passt nicht zum Layout.`n  erwartet: {0}`n  Datei:    {1}" -f ($spalten -join ';'), ($kopfOhne -join ';'))
    }
    $dt = New-Object System.Data.DataTable
    foreach ($s in $spalten) { [void]$dt.Columns.Add($s, [string]) }
    $erwartet = $kopf.Length
    for ($z = 1; $z -lt $saetze.Count; $z++) {
        $f = [string[]]$saetze[$z]
        if ($f.Length -ne $erwartet) {
            throw ("$tabelle`: Datensatz {0} hat {1} statt {2} Felder (beginnt mit '{3}')." -f $z, $f.Length, $erwartet, $f[0])
        }
        if ($leerAmEnde) {
            if ($f[$f.Length - 1] -ne '') { throw "$tabelle`: Datensatz $z hat Inhalt in der letzten, unbenannten Spalte." }
            $f = $f[0..($f.Length - 2)]
        }
        [void]$dt.Rows.Add([object[]]$f)
    }
    return ,$dt
}

function Schreibe-Staging($con, [System.Data.DataTable]$dt, [string]$tabelle) {
    $cmd = $con.CreateCommand(); $cmd.CommandTimeout = 0
    $cmd.CommandText = "TRUNCATE TABLE stg.[$tabelle]"; [void]$cmd.ExecuteNonQuery()
    $bc = New-Object System.Data.SqlClient.SqlBulkCopy($con, [System.Data.SqlClient.SqlBulkCopyOptions]::TableLock, $null)
    $bc.DestinationTableName = "stg.[$tabelle]"
    $bc.BulkCopyTimeout = 0
    $bc.BatchSize = 10000
    foreach ($c in $dt.Columns) { [void]$bc.ColumnMappings.Add($c.ColumnName, $c.ColumnName) }
    $bc.WriteToServer($dt)
    $bc.Close()
}

function Uebernehmen($con, [string[]]$tabellen) {
    $cmd = $con.CreateCommand(); $cmd.CommandTimeout = 0
    $cmd.CommandText = "dbo.bp_Uebernehmen"
    $cmd.CommandType = [System.Data.CommandType]::StoredProcedure
    [void]$cmd.Parameters.AddWithValue('@Tabellen', ($tabellen -join ','))
    $p = $cmd.Parameters.Add('@MinAnteil', [System.Data.SqlDbType]::Decimal)
    $p.Precision = 5; $p.Scale = 2; $p.Value = [decimal]$cfg.MinAnteil
    [void]$cmd.ExecuteNonQuery()
}

# ── Ablauf ──────────────────────────────────────────────────────────────────
$exportDir = $cfg.ExportVerzeichnis
Log ("Start{0} – Exportordner {1}" -f $(if ($Trockenlauf) { ' (Trockenlauf)' } else { '' }), $exportDir)
$fehler = 0
$con = $null
try {
    $con = Neue-Verbindung
    Log "Verbunden mit $($cfg.Server) / $($cfg.Datenbank)"

    foreach ($gruppe in $cfg.Gruppen) {
        $name = $gruppe.Name
        try {
            $tabellen = @()
            $daten = @()
            foreach ($d in $gruppe.Dateien) {
                $pfad = Join-Path $exportDir $d.Datei
                if (-not (Test-Path -LiteralPath $pfad)) { throw "Datei fehlt: $pfad" }
                $alter = (Get-Date) - (Get-Item -LiteralPath $pfad).LastWriteTime
                if ($cfg.MaxAlterStunden -gt 0 -and $alter.TotalHours -gt $cfg.MaxAlterStunden) {
                    throw ("{0} ist {1:N0} Stunden alt – der büro+-Export ist wohl nicht gelaufen." -f $d.Datei, $alter.TotalHours)
                }
                $spalten = Get-StagingSpalten $con $d.Tabelle
                $t0 = Get-Date
                $dt = Lese-Datei $pfad $spalten $d.Tabelle
                Log ("{0}: {1:N0} Datensätze gelesen ({2:N1} s)" -f $d.Datei, $dt.Rows.Count, ((Get-Date) - $t0).TotalSeconds)
                $tabellen += $d.Tabelle
                $daten += ,@($d.Tabelle, $dt)
            }
            if ($Trockenlauf) { Log "$name`: Prüfung bestanden (Trockenlauf, nichts geschrieben)"; continue }

            foreach ($eintrag in $daten) {
                $t0 = Get-Date
                Schreibe-Staging $con $eintrag[1] $eintrag[0]
                Log ("stg.{0}: geschrieben ({1:N1} s)" -f $eintrag[0], ((Get-Date) - $t0).TotalSeconds)
                $eintrag[1].Dispose()
            }
            $t0 = Get-Date
            Uebernehmen $con $tabellen
            Log ("{0}: übernommen nach dbo ({1}) in {2:N1} s" -f $name, ($tabellen -join ', '), ((Get-Date) - $t0).TotalSeconds)
        }
        catch {
            $fehler++
            Log ("{0}: NICHT aktualisiert – {1}" -f $name, $_.Exception.Message) 'FEHLER'
        }
        finally {
            [System.GC]::Collect()
        }
    }
}
catch {
    $fehler++
    Log ("Abbruch: {0}" -f $_.Exception.Message) 'FEHLER'
}
finally {
    if ($con) { $con.Close() }
}

if ($fehler -gt 0) { Log "Ende mit $fehler Fehler(n)" 'FEHLER'; exit 1 }
Log "Ende ohne Fehler"
exit 0
