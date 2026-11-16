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

.EXAMPLE
  .\bp_import.ps1 -Trockenlauf
  .\bp_import.ps1
#>
[CmdletBinding()]
param(
    [string]$Konfig = '',
    [switch]$Trockenlauf
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

# Windows PowerShell 5.1 füllt $PSScriptRoot im param()-Block nicht, wenn das Skript per
# „powershell.exe -File …“ (Aufgabenplanung) gestartet wird → Vorgabe erst hier setzen.
$skriptOrdner = $PSScriptRoot
if ([string]::IsNullOrEmpty($skriptOrdner)) { $skriptOrdner = Split-Path -Parent $MyInvocation.MyCommand.Path }
if ([string]::IsNullOrEmpty($Konfig)) { $Konfig = Join-Path $skriptOrdner 'bp_import.config.psd1' }

# ── Konfiguration ───────────────────────────────────────────────────────────
if (-not (Test-Path -LiteralPath $Konfig)) { throw "Konfigurationsdatei nicht gefunden: $Konfig" }
$cfg = Import-PowerShellDataFile -LiteralPath $Konfig

function Get-Pfad([string]$p) {
    if ([System.IO.Path]::IsPathRooted($p)) { return $p }
    return (Join-Path $skriptOrdner $p)
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
    static readonly char[] FeldEnde = new char[] { ';', '\n' };

    // Liefert alle Datensätze inkl. Kopfzeile. Ein Feld in "..." endet erst bei
    // '";' oder '"' + Zeilenende (CRLF oder LF, bzw. Dateiende); innere " bleiben stehen.
    // Kodierung: UTF-8 (mit/ohne BOM) oder UTF-16 per BOM. Alle Suchen sind begrenzt,
    // damit die Laufzeit linear bleibt (früher: ohne CRLF quadratisch → „hängt“).
    public static List<string[]> Lesen(string pfad)
    {
        string text;
        using (StreamReader sr = new StreamReader(pfad, new UTF8Encoding(false), true)) { text = sr.ReadToEnd(); }
        if (text.Length > 0 && text[0] == '﻿') text = text.Substring(1);
        List<string[]> saetze = new List<string[]>();
        List<string> satz = new List<string>();
        int i = 0, n = text.Length;
        while (i < n)
        {
            if (text[i] == '"')
            {
                int a = text.IndexOf("\";", i + 1, StringComparison.Ordinal);
                int grenze = (a != -1) ? a : n;
                int b = QuoteVorZeilenende(text, i + 1, grenze);
                if (b == -1 && a == -1)
                    throw new FormatException("Nicht abgeschlossenes Textfeld ab Zeichen " + i + ": " + Ausschnitt(text, i));
                if (b != -1)
                {
                    satz.Add(text.Substring(i + 1, b - i - 1));
                    saetze.Add(satz.ToArray()); satz = new List<string>();
                    i = b + 1;
                    if (i < n && text[i] == '\r') i++;
                    i++;   // '\n'
                }
                else
                {
                    satz.Add(text.Substring(i + 1, a - i - 1));
                    i = a + 2;
                }
            }
            else
            {
                int j = text.IndexOfAny(FeldEnde, i);
                if (j == -1) j = n;
                if (j < n && text[j] == ';')
                {
                    satz.Add(text.Substring(i, j - i));
                    i = j + 1;
                }
                else
                {
                    int e = j;
                    if (e > i && text[e - 1] == '\r') e--;
                    satz.Add(text.Substring(i, e - i));
                    saetze.Add(satz.ToArray()); satz = new List<string>();
                    i = j + 1;
                }
            }
        }
        if (satz.Count > 0) saetze.Add(satz.ToArray());
        // Leerzeilen (z. B. abschließendes CRLF) entfernen
        saetze.RemoveAll(delegate (string[] s) { return s.Length == 1 && s[0].Length == 0; });
        return saetze;
    }

    // Position eines '"', dem ein Zeilenende (CRLF/LF) oder das Dateiende folgt, im Bereich [start, grenze); sonst -1.
    static int QuoteVorZeilenende(string t, int start, int grenze)
    {
        int n = t.Length;
        int j = (start < grenze) ? t.IndexOf('"', start, grenze - start) : -1;
        while (j != -1)
        {
            if (j == n - 1) return j;
            char c = t[j + 1];
            if (c == '\n' || (c == '\r' && j + 2 < n && t[j + 2] == '\n')) return j;
            j = (j + 1 < grenze) ? t.IndexOf('"', j + 1, grenze - j - 1) : -1;
        }
        return -1;
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
    if ([string]::IsNullOrEmpty($cfg.Passwort)) { throw "Kein Passwort in der Konfiguration (Schlüssel 'Passwort')." }
    $sb = New-Object System.Data.SqlClient.SqlConnectionStringBuilder
    $sb['Data Source'] = $cfg.Server
    $sb['Initial Catalog'] = $cfg.Datenbank
    $sb['User ID'] = $cfg.Benutzer
    $sb['Password'] = $cfg.Passwort
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
    $n = $spalten.Length
    for ($z = 1; $z -lt $saetze.Count; $z++) {
        $f = [string[]]$saetze[$z]
        # büro+ beendet Datenzeilen oft mit „;“ – unabhängig davon, ob die Kopfzeile es auch tut.
        # Ein leeres Feld genau hinter der letzten Spalte wird deshalb weggelassen.
        if ($f.Length -eq $n + 1) {
            if ($f[$n] -ne '') { throw "$tabelle`: Datensatz $z hat Inhalt hinter der letzten Spalte (beginnt mit '$($f[0])')." }
            $f = $f[0..($n - 1)]
        }
        if ($f.Length -ne $n) {
            throw ("$tabelle`: Datensatz {0} hat {1} statt {2} Felder (beginnt mit '{3}')." -f $z, $f.Length, $n, $f[0])
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
