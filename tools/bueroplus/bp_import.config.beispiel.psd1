# Konfiguration für bp_import.ps1 – als bp_import.config.psd1 neben das Skript kopieren und anpassen.
@{
    # Ordner, in den die büro+-Export-Layouts täglich schreiben
    ExportVerzeichnis = 'C:\Datenmonster\Export'

    # SQL Server (wie in Datenmonster: Host\Instanz,Port)
    Server    = 'c19753.servers.ecomdata.de\SQLSERVER,50000'
    Datenbank = 'gehlen'
    Benutzer  = 'egp'
    # Klartext – Datei per Dateirechten auf das Konto der Aufgabenplanung und Administratoren beschränken
    Passwort  = ''

    # Protokoll
    LogVerzeichnis = 'C:\Datenmonster\Export\Log'
    LogTage        = 30

    # Schutz vor halben Exporten: neue Zeilenzahl muss mindestens diesen Anteil der bisherigen haben
    MinAnteil = 0.80
    # Dateien, die älter sind, gelten als „Export nicht gelaufen“ (0 = keine Prüfung)
    MaxAlterStunden = 30

    # Je Gruppe eine Transaktion: scheitert eine Datei, bleibt die ganze Gruppe auf dem alten Stand.
    Gruppen = @(
        @{ Name = 'Artikel';  Dateien = @( @{ Datei = 'Artikel.csv';  Tabelle = 'Artikel' } ) }
        @{ Name = 'Adressen'; Dateien = @( @{ Datei = 'Adressen.csv'; Tabelle = 'Adressen' } ) }
        @{ Name = 'Vorgänge'; Dateien = @(
            @{ Datei = 'Vorgang.csv';               Tabelle = 'Vorgang' }
            @{ Datei = 'VorgangArchiv.csv';         Tabelle = 'VorgangArchiv' }
            @{ Datei = 'VorgangPosition.csv';       Tabelle = 'VorgangPosition' }
            @{ Datei = 'VorgangPositionArchiv.csv'; Tabelle = 'VorgangPositionArchiv' }
        ) }
    )
}
