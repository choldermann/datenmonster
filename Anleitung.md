# Datenmonster – Anleitung

*Self-hosted ETL-, Integrations- und Auswertungsplattform von Holdermann IT*

Datenmonster verbindet Datenquellen (Dateien, Datenbanken, REST-APIs, FTP, E-Mail),
transformiert die Daten über einen visuellen Node-Editor, schreibt sie zurück oder
exportiert sie, automatisiert alles über Pipelines und Zeitpläne und stellt die
Ergebnisse als Formulare, Dashboards und Berichte bereit – auf dem eigenen Server,
ohne Zwang zur Cloud.

Diese Anleitung führt von der Einrichtung über den Menüaufbau bis zu den einzelnen
Funktionen. Die Kapitel **Mapping**, **Pipeline**, **Formulare & Dashboards**,
**KI-Assistenten** und **Auswertung** sind besonders ausführlich.

Stand: 27.08.2026 · Version 1.0.2

---

## Inhaltsverzeichnis

1. [Grundbegriffe](#1-grundbegriffe)
2. [Einrichtung & Installation](#2-einrichtung--installation)
3. [Menüaufbau (Übersicht)](#3-menüaufbau-übersicht)
4. [Die Menüpunkte im Detail](#4-die-menüpunkte-im-detail)
5. [Mapping-Editor – Nodes im Detail](#5-mapping-editor--nodes-im-detail)
6. [Pipeline-Editor – Nodes im Detail](#6-pipeline-editor--nodes-im-detail)
7. [Formulare & Dashboards](#7-formulare--dashboards)
8. [KI-Assistenten](#8-ki-assistenten)
9. [Auswertung: Warnungen, Schwellwerte, Kosten](#9-auswertung-warnungen-schwellwerte-kosten)
10. [Fertige Vorlagen für die JTL-Wawi](#10-fertige-vorlagen-für-die-jtl-wawi)
11. [Fachmodule](#11-fachmodule)
12. [Portal (Endanwender-Sicht)](#12-portal-endanwender-sicht)
13. [Benutzer, Rollen & Systemeinstellungen](#13-benutzer-rollen--systemeinstellungen)
14. [Typischer Arbeitsablauf](#14-typischer-arbeitsablauf)

---

## 1. Grundbegriffe

| Begriff | Bedeutung |
|---|---|
| **Dataset** | Eine Datenquelle: hochgeladene Datei (CSV/Excel/XML/ODS/Parquet), DB-Tabelle, REST-Antwort oder manuell angelegte Tabelle. |
| **DB-Connector** | Gespeicherte Datenbankverbindung (MSSQL, MySQL/MariaDB, PostgreSQL, SQLite, Access), die von Datasets und Nodes wiederverwendet wird. |
| **Mapping** | Ein visueller ETL-Ablauf: Quelldaten → Transformation → Zielausgabe. Das Herzstück der Anwendung. |
| **Node** | Ein einzelner Baustein im Mapping- oder Pipeline-Editor (z. B. „Transform“, „SQL“, „Aggregation“). |
| **Pipeline** | Verkettung mehrerer Schritte (Mappings, FTP, E-Mail …), zeitgesteuert oder manuell ausführbar. |
| **Formular** | Eine Eingabemaske, die beim Absenden ein Mapping, eine Pipeline oder eine Auswertung startet. |
| **Widget** | Ein Ergebnisbaustein im Formular: Tabelle, Kennzahl, Diagramm, KI-Analyse … Aus Formular + Widgets entsteht ein **Dashboard**. |
| **Portal** | Vereinfachte Oberfläche für Endanwender, die nur Formulare und Dashboards bedienen sollen. |
| **Template (Vorlage)** | Ein komplettes Paket aus Mappings, Formularen und Pipelines, das sich in einem Zug installieren lässt – eigene oder gekaufte. |
| **Warnung** | Eine Regel auf Kennzahlen oder Listen, die bei Überschreitung anschlägt (siehe Kapitel 9). |

---

## 2. Einrichtung & Installation

### Voraussetzungen
- Docker + Docker Compose
- Für KI-Funktionen wahlweise der mitgelieferte **Ollama**-Container (lokales
  Sprachmodell, keine Cloud) **oder** ein Guthaben für **Datenmonster AI**

### Erststart (manuell)

```bash
git clone https://github.com/HoldermannIT/datenmonster.git
cd datenmonster

# 1. Konfiguration anlegen – SECRET_KEY ist Pflicht!
cp .env.example .env
echo "SECRET_KEY=$(openssl rand -hex 32)" >> .env
# Optional: ADMIN_PASSWORD in .env setzen.
# Ohne diesen Eintrag wird beim ersten Start ein Zufallspasswort erzeugt
# und einmalig in den Container-Logs angezeigt.

# 2. Starten
docker compose up -d
```

Danach im Browser öffnen: **http://localhost:5174**
(Der Port lässt sich über `FRONTEND_PORT` in der `.env` ändern.)
Standard-Login: `admin` / *(Passwort aus `.env` oder aus den Container-Logs)*.

> ⚠️ **Wichtig:** Die `.env` enthält Passwörter und darf **niemals** ins Repository
> committed werden (steht bereits in `.gitignore`). Ohne `SECRET_KEY` startet der
> Backend-Container nicht.
>
> Der `SECRET_KEY` verschlüsselt auch alle gespeicherten Zugangsdaten. Bei einem
> Serverumzug muss die alte `.env` zwingend mitgenommen werden – sonst sind sämtliche
> hinterlegten Datenbank- und FTP-Passwörter nicht mehr lesbar.

### Architektur der Container
- **Backend** – FastAPI (Python), stellt die REST-API unter `/api/` bereit.
- **Frontend** – React/Vite, per nginx ausgeliefert (Port 5174 → 80).
- **Ollama** – lokales Sprachmodell für die KI-Funktionen (`OLLAMA_BASE_URL=http://ollama:11434`).
- **Datenbank** – SQLite (Pfad über `DATABASE_URL`); die Daten liegen in einem
  Docker-Volume, **nicht** im Projektordner.

### Updates
Neue Versionen lassen sich direkt in der Anwendung einspielen: Version prüfen,
Änderungsliste ansehen, installieren. Die Auslieferung erfolgt über die
Container-Registry, ein Eingriff auf der Kommandozeile ist nicht nötig.

### Datensicherung

Die Anwendungsdaten liegen **nicht** im Projektordner, sondern im Docker-Volume
`datenmonster-data`: die Datenbank mit allen Mappings, Formularen, Warnregeln und
Zeitplänen, dazu die Dateien der Datasets. Ein verlorenes Volume bedeutet den
Verlust der gesamten Einrichtungsarbeit.

Es gibt zwei Wege, die sich **dasselbe Verzeichnis teilen** (`./backups` auf dem
Server): den Bereich **Systemeinstellungen → Sicherung** für die tägliche Arbeit
und das Skript `./backup.sh` für den geplanten Lauf. Was der eine anlegt, sieht
der andere.

**In der Oberfläche** (nur für Administratoren):
Sicherung anlegen, herunterladen, zurückspielen, löschen – dazu die Liste aller
vorhandenen Archive. Über *Archiv einspielen* lässt sich auch eine Sicherung aus
einer **anderen Installation** hereinholen; sie erscheint dann als „eingespielt"
gekennzeichnet in der Liste.

**Auf der Kommandozeile:**

```bash
./backup.sh                    # Sicherung anlegen
./backup.sh --list             # vorhandene Sicherungen anzeigen
./backup.sh --restore <datei>  # zurückspielen (fragt vorher nach)
```

Die Datenbank wird dabei über die Sicherungsschnittstelle von SQLite kopiert, nicht
mit `cp` – bei laufendem Schreibzugriff wäre eine einfache Dateikopie unbrauchbar.
Die Anwendung muss dafür nicht angehalten werden.

Das Archiv enthält die Datenbank und die Dataset-Dateien. Das Skript legt
zusätzlich die `.env` mit hinein – sie gehört zwingend dazu, denn ohne den darin
enthaltenen `SECRET_KEY` lassen sich die gespeicherten Zugangsdaten nicht mehr
entschlüsseln. Sicherungen aus der Oberfläche enthalten sie **nicht**; wer nur
diesen Weg nutzt, sichert die `.env` bitte getrennt.

**Zum Zurückspielen:** Zuerst wird das Archiv nur geprüft und angezeigt, was
darin steckt – wie viele Mappings, Formulare und Warnregeln. Erst die
Bestätigung schreibt. Der bisherige Stand wandert dabei automatisch in ein
eigenes Archiv. Danach ist ein Neustart nötig, weil die laufende Anwendung die
alte Datei noch offen hält:

```bash
docker compose restart backend
```

Ein eingespieltes Archiv aus einer fremden Anlage lässt sich genauso
zurückspielen. Die Oberfläche weist ausdrücklich darauf hin und zeigt den
Inhalt – ob er zur eigenen Anlage passt, entscheidet der Mensch.

> ⚠️ Damit enthält jedes Archiv Geheimnisse. Es liegt unter `backups/` (von der
> Versionsverwaltung ausgenommen) mit den Rechten `600` und gehört an einen
> geschützten Ort – nicht in einen offenen Netzwerkordner.

Standardmäßig bleiben die letzten 14 Sicherungen liegen; über die Umgebungsvariablen
`DM_BACKUP_DIR` und `DM_BACKUP_KEEP` lässt sich beides ändern. Eingespielte
Archive werden dabei nie automatisch entfernt – die hat jemand bewusst
hergebracht. Für einen täglichen
Lauf genügt ein Eintrag in der Aufgabenplanung des Servers, z. B.:

```
0 2 * * *  cd /pfad/zu/datenmonster && ./backup.sh >> backups/backup.log 2>&1
```

**Prüfe die Wiederherstellung gelegentlich.** Eine Sicherung, die noch nie
zurückgespielt wurde, ist keine.

---

## 3. Menüaufbau (Übersicht)

Nach dem Login landet man im **Dashboard**. Links befindet sich die feste Seitenleiste
mit allen Bereichen, gegliedert in Blöcke:

**Block 1 – Organisation**
- **Projekte** – oberste Gliederungsebene, bündelt zusammengehörige Daten.

**Block 2 – Datenquellen**
- **DB-Connectors** – Datenbankverbindungen
- **Datasets** – alle Datensätze/Tabellen
- **FTP / SFTP** – Dateiquellen per (S)FTP
- **REST API** – externe HTTP-Schnittstellen als Quelle
- **API Studio** – Arbeitsplatz zum Erkunden und Anbinden fremder Schnittstellen
- **Templates** – Vorlagenpakete installieren, erstellen und aus dem Store beziehen

**Block 3 – Verarbeitung**
- **Mappings** – visuelle ETL-Abläufe
- **Pipelines** – automatisierte Ketten
- **Formulare** – Eingabemasken und Dashboards
- **Exporte** – erzeugte Ausgabedateien

**Block 4 – Betrieb**
- **Monitoring** – Live-Status, Kennzahlen, Fehlerprotokoll
- **Plugins** – Konnektor-Erweiterungen

**Block 5 – Auswertung, KI & Verwaltung**
- **Warnungen** – Regeln, Schwellwerte und der nächtliche Prüflauf
- **AI Memory** – Wissensdatenbank des KI-Assistenten
- **Lizenz** – Lizenzverwaltung und Funktionsumfang

Jeder Eintrag zeigt rechts eine **Badge** mit der Anzahl der jeweiligen Objekte.
Oben rechts führt das Zahnrad zu den **Systemeinstellungen** (Kapitel 13).

---

## 4. Die Menüpunkte im Detail

### Projekte
Die oberste Gliederungsebene. Ein Projekt bündelt Datasets, Mappings, Pipelines,
Formulare und Jobs. Projekte lassen sich mit anderen Benutzern teilen. Beim Löschen
eines Projekts werden **alle** zugehörigen Daten unwiderruflich entfernt – die
Anwendung fragt hier ausdrücklich nach.

### DB-Connectors
Verwaltung gespeicherter Datenbankverbindungen: **MSSQL, MySQL/MariaDB, PostgreSQL,
SQLite und Microsoft Access**. Angelegte Connectors lassen sich testen und werden
anschließend überall wiederverwendet: als Dataset-Quelle, im **SQL-Node**, beim
**DB-Schreiben** und im Datenbank-Analyzer. Zugangsdaten werden verschlüsselt
gespeichert.

Beim Verbindungstest wird automatisch ein **Schema-Cache** aufgebaut (alle Tabellen,
Spalten, Typen, Primär- und Fremdschlüssel). Auf jeder Verbindungskachel sind Status
und Alter des Caches sichtbar; er lässt sich jederzeit neu aufbauen.

Direkt aus der Kachel erreichbar:
- **KI-Dataset-Assistent** – Datasets aus einer Beschreibung erzeugen lassen
- **Datenbank-Analyzer** – interaktives Beziehungsdiagramm mit Pfadfinder
- **Schema-Katalog** – die Datenbank dokumentieren (siehe unten)

> **Häufigstes Verbindungsproblem bei SQL Server Express:** In der SQL Server
> Konfiguration muss das **TCP/IP-Protokoll aktiviert** und ein **fester Port**
> unter „TCP-Port“ eingetragen sein (nicht „Dynamische Ports“), danach den Dienst
> neu starten.

### Schema-Katalog
Die dauerhafte Dokumentation einer Datenbank – die Grundlage dafür, dass die KI
sinnvolle Abfragen bauen kann:
- Schema einlesen und Tabellen/Spalten beschreiben (manuell oder per KI-Vorschlag)
- Beziehungen pflegen oder **aus den Schlüsseln ableiten** (Fremdschlüssel plus
  Namensgleichheit mit Primärschlüsseln), Massenübernahme möglich
- Katalog exportieren und auf einer anderen Instanz importieren

### Datasets
Zentrale Übersicht aller Datenquellen. Ein neues Dataset legt man über den
**Assistenten** an. Unterstützte Typen:
- **Datei-Upload:** CSV, XLSX/XLS, XML, JSON, ODS, Parquet, MS Access
- **SQL-Import:** aus einem DB-Connector (Tabelle oder eigene Abfrage)
- **FTP/SFTP-Sync:** mit Wildcard-Filter (`*.csv`, `export_*.xlsx`)
- **REST-Quelle:** JSON-Antwort einer HTTP-API
- **Plugin-Quelle:** z. B. eine MongoDB-Collection
- **Manuelles Dataset:** Spalten selbst definieren, inkl. Primärschlüssel & Auto-Increment

Im **Dataset-Explorer** lassen sich Daten mit Paginierung und Suche durchblättern, der
Datentyp einzelner Spalten inline ändern und (bei manuellen Datasets) Zeilen direkt
bearbeiten. Datasets können sich per Zeitplan selbst aktualisieren. Ein Dataset, das
noch in einem Mapping verwendet wird, warnt beim Löschen.

### FTP / SFTP
Verwaltung von FTP-/SFTP-Quellen: Serveradresse, Zugangsdaten, Verzeichnis und
Dateifilter. Diese Quellen werden für Datasets, für den **FTP-Input-Node** in
Pipelines und als Ablageziel genutzt.

### REST API
Verwaltung wiederverwendbarer REST-Quellen: URL, Methode, Authentifizierung und
JSON-Pfad. Dient als Dataset-Quelle und als Vorlage für REST-Nodes. Zusätzlich lassen
sich **eigene eingehende Endpunkte** definieren, an die fremde Systeme per POST Daten
liefern und damit ein Mapping auslösen.

### API Studio
Ein vollwertiger Arbeitsplatz für fremde Schnittstellen – vergleichbar mit den
bekannten API-Werkzeugen, aber direkt mit der ETL-Strecke verbunden:
- **Sammlungen** und **Umgebungen** (Variablen; Geheimnisse werden maskiert)
- Anfragen senden, **Verlauf** mit Wiederholung
- **Analyse und Fehler-Debugger**: warum ein Aufruf fehlschlägt, in Klartext
- **Variablen vorschlagen** lassen, eine Sammlung befragen („was macht dieser Endpunkt?“)
- **OpenAPI-Import**: eine Spezifikation einlesen und daraus eine Sammlung erzeugen
- **Verkettung**: mehrere Aufrufe hintereinander (Token holen → Daten abrufen)
- **Integration erstellen**: aus einem funktionierenden Aufruf direkt Dataset,
  Mapping und Pipeline generieren

### Templates (Vorlagen)
Vorlagen sind komplette Pakete: Mappings, Formulare, Dashboards und Pipelines in einem
Zug. Der Bereich hat drei Teile:
- **Installierte Vorlagen** – anzeigen, aktualisieren, entfernen
- **Eigene erstellen** – aus vorhandenen Mappings und Formularen eine Vorlage bauen
  und als Datei exportieren
- **Template-Store** – was über monstersuite erhältlich ist; Gekauftes lässt sich
  direkt installieren, Vorlagen als Datei hochladen geht immer

Beim Installieren werden interne IDs in portable Referenzen aufgelöst. Vorhandene
Elemente werden abgeglichen und aktualisiert statt doppelt angelegt.

### Exporte
Liste aller durch Mappings und Pipelines erzeugten Ausgabedateien (CSV, Excel, JSON,
XML, Parquet, amtliche Formate) zum Herunterladen. Ältere Exporte können hier entfernt
werden.

### Monitoring
Live-Übersicht mit Systemkennzahlen (CPU, Arbeitsspeicher, Plattenplatz,
Datenbankgröße, Laufzeit), Pipeline-Status und Fehlerprotokoll. Enthält ein System-Log
mit Projektspalte und Stacktrace-Ansicht und aktualisiert sich automatisch.

### Plugins
Ein **einheitlicher Katalog** aller Konnektor-Erweiterungen, aufgeteilt in „Aktiv“ und
„Verfügbar“. Ob eine Erweiterung im Backend eingebaut ist oder als eigenständiger
Dienst läuft, ist Sache der Technik und spielt für die Bedienung keine Rolle.

Mitgeliefert bzw. verfügbar sind unter anderem der **Mail-Connector** (E-Mails und
Anhänge als Quelle), der **Web-/HTML-Connector** (Seiten auslesen mit visuellem
Selektor), **MongoDB**, **eSTATISTIK.core** und eine **Testdaten-Quelle**.
Erweiterungen lassen sich als Datei hochladen; kostenpflichtige werden über die Lizenz
freigeschaltet.

### Warnungen
Regelbasierte Überwachung des Unternehmens – siehe Kapitel 9.

### AI Memory
Die Wissens- und Gedächtnisverwaltung des KI-Assistenten:
- **Knowledge** – dauerhaftes Fachwissen (z. B. Bedeutung von Tabellen und Spalten,
  Besonderheiten der eigenen Warenwirtschaft). Kann auch automatisch aus einem
  DB-Schema importiert werden.
- **Solutions** – bewährte Lösungen und Bausteine, die der Assistent wiederverwendet.
- **Corrections** – Korrekturen, aus denen der Assistent lernt.
- **Cache** – Antwort-Zwischenspeicher mit Trefferstatistik, jederzeit leerbar.
- **Suggestions** – automatische Vorschläge, die zu dauerhaftem Wissen befördert
  werden können.
- **Kontext-Vorschau** – zeigt, welches Wissen bei einer Frage tatsächlich mitgeschickt
  würde. Es wird nach Stichwörtern und einem Token-Budget ausgewählt, nicht alles auf
  einmal.

### Lizenz
Eingabe und Statusanzeige des Lizenzschlüssels. Die Aktivierung läuft über
monstersuite, danach wird täglich neu geprüft. Ist der Lizenzserver einmal nicht
erreichbar, läuft die Anwendung 14 Tage in einer Kulanzzeit weiter und fällt erst
danach auf den kostenlosen Umfang zurück.

Freischaltbare Bereiche: unbegrenzte Projekte, DB-Schreiben, Pipelines & Zeitpläne,
FTP/SFTP, REST-Quellen, Mail-Anbindung, KI-Assistent, KI-Wissensdatenbank,
Schema-Katalog, Formular-Builder & Portal, erweiterte Plugins, mehrere Benutzer,
erweitertes Monitoring.

> **Hinweis:** Meldet die KI „Gateway nicht erreichbar“, ist meist keine Störung die
> Ursache, sondern eine nicht aktivierte Lizenz. Der Lizenzbereich zeigt dann den
> Status „kostenlos“.

---

## 5. Mapping-Editor – Nodes im Detail

Der Mapping-Editor ist der zentrale visuelle ETL-Baukasten. Man zieht **Nodes** auf die
Arbeitsfläche, verbindet sie durch Ziehen der Ports und baut so den Datenfluss von der
Quelle bis zum Ziel auf. Über eine Info-Schaltfläche an jedem Node öffnet sich eine
Beschreibung seiner Funktionen.

**Grundprinzip:** Links stehen Quell-Nodes, in der Mitte Transformationen, rechts das
Zielfeld-Mapping bzw. das Export-Ziel. Zwischen Quell-Datasets können **Joins** gelegt
werden.

### Quell- und Struktur-Nodes

**Dataset-Node**
Bindet ein vorhandenes Dataset als Datenquelle ein. Mehrere Dataset-Nodes lassen sich
über Joins verknüpfen. Verfügbare Join-Typen:
`INNER`, `LEFT`, `RIGHT`, `FULL OUTER`, `LEFT ANTI`, `RIGHT ANTI`.
Beim Hinzufügen weiterer Datasets werden passende Joins automatisch vorgeschlagen,
Primär- und Fremdschlüssel als Kennzeichen angezeigt. Filter und Sortierung lassen sich
direkt am Node einstellen; bei Datenbankquellen werden sie in die Datenbank
hineingeschoben statt im Speicher angewendet.

**Konstante (Constant-Node)**
Erzeugt einen festen Wert als virtuelles Quellfeld – ganz ohne Datenquelle. Typen:
- Statischer Text oder Zahl
- Aktuelles Datum, Datum + Uhrzeit oder Jahr (zur Laufzeit berechnet)
- Zufällige UUID (v4)
- Boolean `true` / `false`

**Parameter-Node**
Stellt Laufzeit-Parameter bereit (z. B. aus einem Formular oder beim Pipeline-Start
übergeben), die in nachfolgenden Nodes verwendet werden können – die Brücke zwischen
Dashboard-Filtern und Abfrage.

### Transformations-Nodes

**Transform-Node** – das Universal-Werkzeug zum Umformen von Feldwerten:
- **Zahlenformat:** Dezimalstellen, Tausender- und Dezimaltrennzeichen
- **Zahlenrechnung:** `+`, `−`, `×`, `÷`, Modulo, Min, Max, AutoID
- **Datumsformat:** DE ↔ ISO ↔ US und beliebige eigene Formate
- **Datumsrechnung:** Tag/Monat/Jahr/Stunde/Minute/Sekunde extrahieren, AddDays,
  DaysDiff, Now
- **Zeichenketten:** Trim, GROSS/klein, Ersetzen, Prefix/Suffix, Erste/Letzte N Zeichen,
  Teilbereich „von X bis Y“, Aufteilen & Teil N, Länge, Umkehren
- **Regex:** Gruppe N extrahieren oder ersetzen
- **Verkettung:** mehrere Quellfelder mit Trennzeichen zusammenführen

**Expression-Node (Expr)**
Berechnet ein Ausgabefeld über eine Formel-/Ausdruckssprache – kompakter als der
Transform-Node, wenn man mehrere Felder in einem Ausdruck kombinieren will. Der
KI-Assistent kann Ausdrücke aus einer Beschreibung generieren.

**Berechnungs-Node (Calc)** – fensterbasierte Berechnungen über geordnete/gruppierte Zeilen:
- Kumulierte Summe (Cumsum), optional mit Gruppierung
- Gleitender Durchschnitt (Rolling Avg) mit konfigurierbarer Fenstergröße
- Rang (Rank) und Zeilennummer (Row Number)
- Prozentrang (Percent Rank) innerhalb der Gruppe

**Aggregations-Node (Agg)** – verdichtet Werte über alle Zeilen:
`SUM`, `COUNT`, `COUNT DISTINCT`, `AVG`, `MIN`, `MAX`, `STDDEV`, `MEDIAN`, `FIRST`,
`LAST` sowie `GROUP BY` für spätere Joins. Mehrere Aggregationen sind pro Node parallel
möglich.

**Switch-Node** – wählt zur Laufzeit anhand von Bedingungen eine alternative Datenquelle:
- Bedingung „Dataset hat Zeilen / hat keine Zeilen“
- Bedingung „Zeilenzahl größer / kleiner als Schwellwert“
- Fallback-Zweig („immer“) als letzter Ast
- Die Felder des gewählten Datasets werden in den Ablauf eingespeist

### Nachschlage- und Integrations-Nodes

**Lookup-Node** – schlägt Werte aus einem anderen Dataset über ein Schlüsselfeld nach:
- Schlüsselfeld gegen eine Spalte im Lookup-Dataset abgleichen
- beliebig viele Ausgabefelder übernehmen
- Verhalten bei fehlendem Treffer: `null`, leer lassen oder fester Fallback

**SQL-Node** – führt eine SQL-Abfrage auf einem DB-Connector aus:
- **Scalar-Modus:** liefert einen Wert pro Ausgabezeile (klassische Lookup-Abfrage),
  wahlweise zeilenweise oder gebündelt über eine IN-Liste
- **Transform-Modus:** das SQL-Ergebnis wird selbst zur Datenquelle des Mappings –
  der übliche Weg für Auswertungen und Dashboards
- **Ausführender Modus:** eine Anweisung oder Stored Procedure ausführen, ohne
  Ergebnismenge
- Parameter aus Quellfeldern über `{{feldname}}`, Laufzeitparameter über `:name`
- unterstützt alle angebundenen Datenbanktypen
- Der KI-Assistent kann SQL erklären oder aus einer Beschreibung generieren

**REST-Node** – ruft pro Zeile (oder als Batch) eine externe HTTP-API auf:
- GET und POST, beliebige URL mit `{{feldname}}`-Platzhaltern
- Auth: Bearer-Token, API-Key-Header oder HTTP Basic
- JSON-Pfad zur Antwort (z. B. `data.result.price`)
- **Batch-Modus:** alle Schlüssel in einem einzigen Aufruf bündeln

**Python-Node** – eigene Python-Logik pro Datensatz, wenn kein Standard-Node reicht:
- Eingabe ist ein `row`-Dict mit allen aktuellen Feldern
- Felder neu anlegen, überschreiben oder löschen
- Zugriff auf `math`, `re`, `json`, `decimal`, `statistics`, `datetime`
- **Sicherheits-Sandbox:** kein Dateisystem, kein Netzwerk, kein `import`; Zeitlimit
  pro Zeile; ein Fehler stoppt nur die betroffene Zeile
- Der KI-Assistent kann Python-Code aus einer Beschreibung generieren

**Data-Quality-Node** – prüft Feldwerte gegen Regeln: Pflichtfeld, Zahl, E-Mail, IBAN,
EAN, eigene reguläre Ausdrücke (z. B. `^\d{5}$` für PLZ). Der Node liefert zusätzlich
ein Gültigkeitskennzeichen und eine Fehlerliste je Datensatz, sodass sich fehlerhafte
Zeilen im Anschluss gezielt aussteuern lassen.

**AI-Transform-Node** (lila) – wendet ein Sprachmodell auf jede Zeile an:
- Freitext-Anweisung mit `{{feldname}}`-Platzhaltern (Felder per Doppelklick einfügbar)
- liefert strukturierte Ausgabe in Zielfelder
- Modell wählbar
- Panel „Verfügbare Felder“ zum schnellen Einsetzen von Platzhaltern
- Ideal für Kategorisierung, Textbereinigung, Extraktion aus Freitext

### Ziel / Ausgabe

Das rechte Ende des Mappings definiert, **wohin** geschrieben wird:
- **Dateien:** CSV, Excel (XLSX), JSON, XML, Parquet
- **Amtliche Formate:** Destatis-CSV, Intrahandels-CSV, IDEV-Datei (`.idev`)
- **Datenbank:** über einen DB-Connector
- **Dataset:** Ergebnis als neues oder aktualisiertes Dataset zurückschreiben
- **FTP/SFTP-Ablage**
- **Plugin-Ziel:** z. B. eine MongoDB-Collection

**Schreibmodi** beim Datenbank- und Dataset-Ziel:
- **Replace / Truncate+Insert** – Zieldaten ersetzen
- **Append / Insert** – anhängen
- **Update** – vorhandene Sätze aktualisieren
- **Upsert** – über Schlüssel abgleichen (aktualisieren oder einfügen)
- **Delete** – Sätze anhand des Ergebnisses löschen

Ein Mapping kann mehrere Ziele gleichzeitig bedienen.

> ⚠️ Beim Schreiben in eine produktive Warenwirtschaft gilt: erst mit dem Vorschau-
> bzw. Trockenlauf prüfen, dann ausführen.

### Hilfsfunktionen im Editor
- **Vorschau-Panel:** zeigt die Ergebniszeilen live, bevor exportiert wird – auch an
  jeder einzelnen Verbindungslinie.
- **Debug-Lauf:** stufenweiser Durchlauf mit Stichprobendaten, Zeilen rein/raus und
  Fehler je Node, einzelne Datensätze durch alle Stufen verfolgen.
- **Minimap**, Zoom, Nodes minimieren/aufklappen – Navigation bei großen Mappings.
- **Smart Mapping:** KI-gestützter Vorschlag der Feldzuordnungen (siehe Kapitel 8).
- **SQL-Editor / Filter-&-Sort-Editor:** komfortable Detaileinstellungen.
- **Export-Modal:** Zielformat und Optionen wählen und Datei erzeugen.
- **Als Vorlage exportieren/importieren:** ganze Mappings weitergeben.

---

## 6. Pipeline-Editor – Nodes im Detail

Eine **Pipeline** verkettet mehrere Schritte zu einem automatisierten Ablauf. Auch hier
zieht man Nodes auf die Fläche und verbindet sie. Nodes haben Ein- und Ausgangs-Ports;
Verzweigungs-Nodes besitzen mehrere Ausgänge.

### Trigger (⏰, gold)
Der **Startpunkt** jeder Pipeline. Auslöser-Modus **Zeitplan**: Über eine komfortable
Oberfläche (Uhrzeit, Intervall, Wochentage, Monatstage) wird im Hintergrund automatisch
ein **Cron-Ausdruck** gebaut; eine Vorschau zeigt den Zeitplan an. Die Ausführung
übernimmt der Scheduler im Backend. Pipelines lassen sich zusätzlich jederzeit manuell
starten.

### FTP Input (📥, sky)
Holt Dateien von einer FTP-/SFTP-Quelle (mit Wildcard-Filter) und stellt sie den
folgenden Schritten bereit.

### REST Fetch (🌐, teal)
Ruft eine REST-API ab und übergibt die Antwort an die nächste Stufe – das Gegenstück zum
REST-Node auf Pipeline-Ebene.

### Mapping (⚙️, emerald)
Führt ein gespeichertes **Mapping** aus. Das ist meistens der Kern der Pipeline: Die
eigentliche Transformationslogik liegt im Mapping, die Pipeline orchestriert nur.

### Verzweigung / Dispatcher (🔀, violet)
Wertet **Bedingungen** aus und leitet den Ablauf auf zwei Ausgänge:
„✓ Bedingung erfüllt“ und „✗ Nicht erfüllt“. Die möglichen Bedingungen hängen vom
Kontext ab:
- Nach einem **Datei-/FTP-Eingang:** Datei vorhanden, Anzahl Dateien, Namensmuster,
  Inhalt oder XML-Struktur.
- Nach einem **Mapping:** Ergebnis hat Zeilen, Zeilenzahl über/unter Schwellwert.
Bei mehreren Bedingungen sind sie per **AND/OR** verknüpfbar. So lassen sich eingehende
Dateien automatisch dem passenden Mapping zuordnen.

### Bedingung (❓, amber)
Einfache Wenn/Dann-Verzweigung als eigenständiger Node – schlanker als der Dispatcher,
für einzelne Ja/Nein-Entscheidungen.

### FTP Upload (📤, orange)
Lädt eine erzeugte Datei auf einen FTP-/SFTP-Server hoch – typischer Abschluss-Schritt.

### E-Mail (📧, pink)
Versendet eine Benachrichtigung oder ein Ergebnis (z. B. eine Export-Datei oder einen
Bericht) per E-Mail. Die Zugangsdaten des Postausgangs werden einmalig in den
Systemeinstellungen hinterlegt.

### Business Insights (💡, violet)
Analysiert die Daten betriebswirtschaftlich und erzeugt Kennzahlen, Trends und
Auffälligkeiten. Die Felder werden semantisch zugeordnet – Pflichtfelder
**Umsatz/Kennzahl** und **Datumsfeld**, optional **Land/Region, Kunde, Artikel, Menge,
Lagerbestand**. Fertige **Voreinstellungen** beschleunigen die Einrichtung:
- Umsatzentwicklung
- Länderanalyse
- Top-Kunden
- Lagerbestand

Vergleichszeiträume: aktueller Monat vs. Vormonat, Monat vs. Vorjahresmonat, Jahr vs.
Vorjahr oder ein frei gewählter Zeitraum.

---

## 7. Formulare & Dashboards

Ein Formular ist eine Eingabemaske, die beim Absenden eine Aktion auslöst. Ergänzt man
es um **Widgets**, wird daraus ein vollwertiges **Dashboard** mit Kennzahlen,
Diagrammen, Tabellen und KI-Analyse. Beides wird im selben Editor gebaut und im Portal
bereitgestellt – Auswertungen gehören damit in den Formularbereich, nicht in einen
eigenen Berichtsbereich.

### Aufbau des Editors
- **Feld-Palette** (links): alle verfügbaren Feld- und Widget-Typen zum Hineinziehen.
- **Canvas** (Mitte): das Formular im 12-Spalten-Raster; Elemente werden per Drag & Drop
  angeordnet, die Spaltenbreite bestimmt die Größe.
- **Eigenschaften** (rechts): Label, Feldname, Pflichtfeld, Platzhalter, Standardwert,
  Optionen, Reiterzuordnung usw. für das ausgewählte Element.
- **Vorschau** und **Einreichungen** (eingegangene Ausfüllungen) sind ebenfalls einsehbar.

Felder und Widgets lassen sich auf **Reiter** verteilen, sodass umfangreiche Dashboards
übersichtlich bleiben.

### Feldtypen

**Eingabe**
| Typ | Beschreibung |
|---|---|
| Textfeld | einzeiliger Text |
| Mehrzeiliger Text | Textbereich |
| Zahl | numerische Eingabe |
| Datum | Datumsauswahl |
| Uhrzeit | Zeitauswahl |
| Dateiauswahl | Datei-Upload |

**Auswahl**
| Typ | Beschreibung |
|---|---|
| Checkbox | einzelnes Ja/Nein |
| Switch | Schalter (an/aus) |
| Dropdown | Einfachauswahl aus Liste |
| Mehrfachauswahl | mehrere Werte aus Liste |
| Radio Buttons | genau eine Option sichtbar auswählen |

**Dashboard-Filter**
| Typ | Beschreibung |
|---|---|
| Zeitraum (Kalender) | Von-/Bis-Auswahl über ein Kalender-Popover mit Schnellwahl |
| DB-Auswahl | Auswahlliste, deren Werte live aus der Datenbank kommen – mit Tippsuche und optional mehrfach wählbar |

Die Werte dieser Filter landen als Laufzeitparameter in den Abfragen (`:von`, `:bis` …).

**Aktionen**
| Typ | Beschreibung |
|---|---|
| Button | löst die hinterlegten Aktionen aus (z. B. „Auswerten“) |

**Layout**
| Typ | Beschreibung |
|---|---|
| Überschrift | Gliederungstitel |
| Text / Label | erklärender Text |
| Trennlinie | optische Trennung |
| Container | Gruppierung mehrerer Felder |

### Widgets (die Ergebnisdarstellung)

| Widget | Zweck |
|---|---|
| **Tabelle** | sortierbar, Spalten konfigurierbar, klickbar für Drilldown, als Datei herunterladbar |
| **KPI** | einzelne Kennzahl, optional mit Vorjahresvergleich und Ampel |
| **Balken- / Linien- / Kreisdiagramm** | Diagramme, ebenfalls klickbar |
| **KI-Analyse** | ein Sprachmodell kommentiert die Zahlen des Dashboards – knapp oder ausführlich, mit deterministischer Bewertungstabelle „gut / verbesserungswürdig“ |
| **Aufgabenliste** | Ampel mit Anzahl; Klick öffnet die zugehörige Detailliste |
| **Unternehmenswarnungen** | zeigt die Ergebnisse der Warn-Engine (Kapitel 9) |
| **Kostenstruktur** | Maske zum Pflegen der monatlichen Fixkosten je Kostenart |
| **Eingangsrechnungs-Freigabe** | E-Rechnung einlesen, prüfen und übernehmen |
| **EAN-Recherche / Hersteller-Navigator / Stammdatenprüfung** | Stammdaten anreichern (Kapitel 11) |

### Interaktion im Dashboard
- **Drilldown:** Klick auf eine Tabellenzeile oder ein Diagrammsegment öffnet die
  Detailebene – mehrstufig bis auf die Belegebene.
- **KI-Handlungsempfehlung:** Klick auf eine Zeile (z. B. einen Kunden mit
  Umsatzrückgang oder einen Ladenhüter) öffnet einen konkreten Vorschlag, was zu tun
  ist. Die Fakten dazu werden serverseitig ermittelt, nicht vom Modell erfunden.
- **Tabelle per E-Mail:** eine Ergebnistabelle direkt aus dem Dashboard versenden.
- **PDF-Bericht:** das gesamte Dashboard inklusive Diagrammen, KI-Analyse und
  Bewertungstabelle als PDF erzeugen – mit den Firmendaten aus der Warenwirtschaft.

### Pflichtfelder & Validierung
Jedes Feld kann als **Pflichtfeld** markiert werden. Beim Absenden validiert das
Formular, dass alle Pflichtfelder ausgefüllt sind.

### Aktionen (was beim Absenden passiert)
Über den **Aktionen-Editor** wird festgelegt, was ein Button auslöst:
- **Mapping ausführen** – startet ein Mapping und übergibt die Formularwerte als
  Parameter
- **Pipeline ausführen** – startet eine komplette Pipeline
- **Warnungen auswerten** – lässt die Warn-Regeln über die aktuellen Zahlen laufen
- **Mapping exportieren** – erzeugt direkt eine Ausgabedatei (z. B. die Intrastat-Meldung)

Mehrere Aktionen laufen gebündelt über einen Ausführen-Knopf; bei umfangreichen
Dashboards werden sie parallel abgearbeitet, damit die Wartezeit kurz bleibt.

Ein Dashboard ohne Eingabefelder startet beim Öffnen von selbst. Bei Dashboards mit
Zeitraumfilter lässt sich einstellen, ob sie sofort loslaufen oder erst auf den
Ausführen-Knopf warten sollen.

### KI-Unterstützung im Formular
Die Schaltfläche **Feldvorschlag** erzeugt anhand einer Beschreibung passende
Formularfelder, sodass man ein Formular nicht komplett von Hand aufbauen muss.

### Ausführen und Veröffentlichen
Ein Formular lässt sich direkt im Editor testen. Für Endanwender wird es
**veröffentlicht** und ist dann über das **Portal** unter einer eigenen Adresse
erreichbar (siehe Kapitel 12).

---

## 8. KI-Assistenten

### Zwei Anbieter zur Wahl
In den Systemeinstellungen unter **KI** wird festgelegt, wer rechnet:

| Anbieter | Eigenschaften |
|---|---|
| **Lokal / Ollama** | Läuft komplett auf dem eigenen Server. Kostenlos, keine Daten verlassen das Haus. Antworten sind je nach Hardware langsamer und bei langen Analysetexten schwächer. |
| **Datenmonster AI** | Zentraler Dienst über monstersuite, abgerechnet über **Credits** – kein eigener API-Schlüssel nötig. Deutlich stärker bei ausführlichen Auswertungen und komplexem SQL. |

Bei Datenmonster AI ist das Guthaben immer sichtbar; Pakete lassen sich nachkaufen und
eine Rechnung abrufen. Die Modellwahl steht auf **Automatisch** (die Plattform wählt je
Aufgabe zwischen günstig und leistungsfähig) oder wird fest vorgegeben.

An einzelnen Stellen – etwa im Schema-Katalog oder im Portal – lässt sich der Anbieter
pro Aufruf umschalten, ohne die Grundeinstellung zu ändern.

### Modelle
Der Reiter **Modelle** zeigt den Status (verbunden? welche Modelle installiert?) und
erlaubt das Nachladen weiterer Modelle. Es gibt getrennte Einstellungen für
**Code-Modell** (SQL, Python, Ausdrücke) und **Text-Modell** (Analysen, Berichte).
Modelle lassen sich **vorwärmen**, damit der erste Aufruf nach einer Pause nicht ins
Zeitlimit läuft – das war früher der häufigste Grund für eine fehlende KI-Analyse im
PDF-Bericht.

### Der schwebende KI-Assistent
Ein Chat-Fenster, das auf jeder Seite verfügbar ist. Er kennt den **Kontext der
aktuellen Seite** (welches Mapping oder Dataset gerade offen ist, welche Daten sichtbar
sind) und beantwortet Fragen dazu. Drei Modi steuern Tempo gegen Tiefe:
- **⚡ Schnell** – kleines Modell, kurze Antworten
- **⚖ Auto** – Datenmonster wählt Modell und Modus automatisch
- **🧠 Analyse** – großes Modell, ausführliche Antworten

Optional lässt sich die **Schema-Wissensdatenbank** zuschalten: Dann kennt der Assistent
den Aufbau der Datenbank und gibt bessere Antworten zu Joins und Tabellenbeziehungen.

### KI im Mapping-Editor
- **Smart Mapping** – schlägt Feldzuordnungen zwischen Quelle und Ziel vor
  (semantischer Abgleich der Feldnamen), inklusive fertiger Voreinstellungen
- **AI-Transform-Node** – KI-Transformation pro Zeile mit strukturierter Ausgabe
- **SQL generieren / erklären** – im SQL-Node aus einer Beschreibung SQL erzeugen oder
  bestehendes SQL erklären lassen
- **Python generieren** – im Python-Node Code aus einer Beschreibung erstellen
- **Ausdruck generieren** – im Expression-Node Formeln aus Text ableiten
- **Fehler erklären** – Fehlermeldungen verständlich aufschlüsseln lassen
- **Node-Vorschläge** – ganze Node-Ketten aus einer Aufgabenbeschreibung generieren

### KI beim Dataset-Anlegen
Der **KI-Dataset-Assistent** führt in drei Schritten:
1. **Beschreibung** in Alltagssprache („Rechnungen mit Lieferantendaten“)
2. **Tabellenauswahl** – die KI schlägt passende Tabellen vor (Stichwortsuche plus
   Erweiterung über Fremdschlüssel, deutsches Stemming), jede mit Vorschau
3. **SQL-Generierung** – fertige SELECT-Abfragen, die sich vor dem Anlegen noch
   bearbeiten lassen

### KI in Auswertungen
- **Dashboard-Analyse** – kommentiert die Zahlen eines Cockpits, wahlweise knapp oder
  ausführlich; Erfreuliches wird grün, Kritisches rot hervorgehoben, und zwar auf den
  Zahlen, nicht auf Floskeln
- **Handlungsempfehlung je Zeile** – konkret zu einem Kunden, Artikel oder Vorgang
- **Artikelbeschreibungen** vorschlagen

> **Zur Einordnung:** Die Qualität einer Auswertung hängt stärker von der Datenlage und
> der Fragestellung ab als vom Modell. Bei lokalen Modellen weist die Anwendung darauf
> hin, dass ausführliche Analysen ungenauer ausfallen können; der Modus „ausführlich“
> steht deshalb nur über Datenmonster AI zur Verfügung.

### AI Memory (Wissen & Lernen)
Damit die KI über Sitzungen hinweg besser wird (siehe auch Kapitel 4):
**Knowledge** (dauerhaftes Fachwissen, auch per Schema-Import befüllbar), **Solutions**
(wiederverwendbare Lösungen), **Corrections** (Korrekturen), **Cache** (Antwortspeicher
mit Statistik) und **Suggestions** (Vorschläge, die zu Wissen befördert werden können).

Das Wissen wird nicht komplett mitgeschickt, sondern nach Stichwörtern und Budget
ausgewählt. Die **Kontext-Vorschau** zeigt, was bei einer konkreten Frage tatsächlich
beim Modell ankommt.

---

## 9. Auswertung: Warnungen, Schwellwerte, Kosten

Der Bereich **Warnungen** macht aus Zahlen Handlungsbedarf.

### Warn-Regeln
Eine Regel prüft das Ergebnis eines Mappings – entweder eine Kennzahl oder eine Liste –
und schlägt an, wenn eine Bedingung erfüllt ist. Zu jeder Warnung gehören:
- **Schweregrad**, abhängig von der Höhe der Abweichung
- **Fakten**: die konkreten Zahlen, die zur Warnung geführt haben
- **Drilldown**: die betroffenen Datensätze direkt einsehbar

Warnungen erscheinen im gleichnamigen Bereich und als **Widget** in jedem Dashboard.

### Nächtlicher Lauf
Die Regeln laufen automatisch in der Nacht. Der Vergleich mit dem Vortag zeigt, was
**neu seit gestern** ist – man sieht also nicht jeden Morgen dieselbe Liste, sondern die
Veränderung. Vergangene Läufe werden archiviert, der nächste geplante Lauf wird
ausgewiesen. Der Lauf lässt sich jederzeit sofort anstoßen.

### Zentrale Schwellwerte
Grenzwerte werden einmal zentral gepflegt (z. B. ab wann ein Zahlungsverzug kritisch
ist, ab welcher Retourenquote gewarnt wird) und von allen Regeln und Cockpits
gleichermaßen verwendet. Ändert sich die Einschätzung, ändert man sie an einer Stelle.

### Kostenstruktur
Über das Widget **Kostenstruktur** werden die monatlichen Fixkosten gepflegt:
25 gängige Kostenarten sind vorbereitet, eigene lassen sich ergänzen. Jede Kostenart
bekommt eine **„gültig ab“-Zeitleiste**, sodass Mieterhöhungen oder neue Verträge
historisch korrekt abgebildet werden.

Diese Werte fließen automatisch in die Auswertung ein – im GF-Cockpit etwa in den Reiter
**Ergebnis** mit Betriebsergebnis nach Fixkosten und Break-even.

### Unternehmensziele
Zielwerte (z. B. Jahresumsatz) lassen sich hinterlegen und werden in den Auswertungen
gegen den Ist-Stand gestellt.

---

## 10. Fertige Vorlagen für die JTL-Wawi

Für die JTL-Warenwirtschaft liegen fertige Auswertungspakete bereit. Sie werden über
**Templates** installiert, fragen dabei die zu verwendende Datenbankverbindung ab und
bringen Mappings, Dashboard und Warn-Regeln mit. Alle Cockpits bieten Zeitraumfilter,
Vorjahresvergleich, Drilldown bis auf Belegebene, KI-Analyse und PDF-Bericht.

| Vorlage | Inhalt |
|---|---|
| **GF-Cockpit** | Das Unternehmenscockpit für Geschäftsführung und Inhaber: Übersicht, Ergebnis (Betriebsergebnis und Break-even nach Fixkosten), Kundenentwicklung inkl. Zahlungsmoral, Umsatzanalyse, Kapitalbindung, Einkauf & Verbindlichkeiten, Offene Posten, Retouren, Mitarbeiter, Ausblick (Umsatz-Hochrechnung und abwandernde Kunden) sowie Warnungen. |
| **Vertriebs-Cockpit** | Auftragseingang statt nur Rechnungen, Auftragsbestand, Angebote mit Nachfassliste und Conversion, Kunden, Artikel, Mitarbeiter. |
| **Einkaufs-Cockpit** | Bestellvolumen und Lieferanten, offene Bestellungen mit Verzug (laufende Beschaffung getrennt vom Altbestand), Termintreue aus echten Wareneingängen, offene Verbindlichkeiten, EK-Preisentwicklung. |
| **Lager-Cockpit** | Lagerwert zum Stichtag – bewertet zum historischen Einkaufspreis –, Verlauf, Disposition mit Fehlmengen und Zulauf, Umschlag und Reichweite, Preisverlauf EK gegen VK. |
| **Versand-Cockpit** | Sendungsaufkommen je Versandart, Durchlaufzeit vom Auftrag bis zum Versand, Tracking-Qualität, Rückstand nicht versendeter Lieferscheine. |
| **Health-Check** | Prüft Artikel- und Kundenstammdaten auf Lücken und Widersprüche: fehlende EAN, Gewichte und Einkaufspreise, VK unter EK, fehlende Warentarifnummer und Herkunftsland, doppelte EANs, Kunden ohne vollständige Rechnungsadresse. |
| **Intrastat** | Vollständiges Meldewesen für Ausfuhr und Einfuhr: Mappings, Zeitraum-Formular und monatliche Pipelines. |

Gesperrte Kunden und inaktive Artikel werden in Listen und Ranglisten ausgeblendet,
fließen aber weiterhin in die Gesamtkennzahlen ein – sonst würden Umsätze verschwinden.

---

## 11. Fachmodule

### Intrastat
Erzeugt die Intrahandelsstatistik für **Ausfuhr und Einfuhr**. Ausgabe wahlweise als
**IDEV-Datei** für das Meldeportal oder als **Destatis-CSV**. Dazu gehören:
- ein Zeitraum-Formular zum Auslösen der Meldung
- eine **Ausschlussliste** für Artikel, die nicht in die Statistik gehören
- eine Datenqualitätsprüfung, die fehlende Warennummern, Gewichte oder Herkunftsländer
  vorab meldet, mit Ersatzwert für das Herkunftsland

### Eingangsrechnungen (E-Rechnung)
Liest **ZUGFeRD/Factur-X** und **XRechnung** ein – aus PDF oder XML. Die Positionen
werden den vorhandenen Bestellungen zugeordnet, offene Punkte lassen sich über eine
Artikelsuche klären. Vor dem Schreiben zeigt eine Vorschau, was in der Warenwirtschaft
entstehen würde. Das Modul steht auch als Widget im Portal zur Verfügung, sodass eine
Buchhaltungskraft Rechnungen freigeben kann, ohne Zugriff auf die Plattform zu haben.

### Stammdaten-Übernahme
Ergebnisse lassen sich direkt in die Warenwirtschaft zurückschreiben. Ein
**Trockenlauf** zeigt zuerst den vollständigen Plan; gleichzeitige Änderungen durch
andere Benutzer werden über die Zeilenversion erkannt, damit nichts überschrieben wird.

### Produktrecherche
Für Artikel mit lückenhaften Stammdaten durchsucht die Plattform die Herstellerseiten
(unter Beachtung der `robots.txt`) und schlägt **EAN, Warennummer, Herkunftsland und
Gewicht** vor. Jeder Vorschlag bekommt einen **Sicherheitsgrad** – gesichert, zu prüfen
oder ungesichert –, sodass nichts blind übernommen wird. Der **Hersteller-Navigator**
führt vom Hersteller über den Artikel bis zum fertigen Vorschlag.

---

## 12. Portal (Endanwender-Sicht)

Neben der vollen Editor-Oberfläche gibt es das **Portal** – eine reduzierte Ansicht für
Anwender, die nur Formulare und Auswertungen bedienen sollen:
- **Portal-Startseite** (`/portal`) – Übersicht der bereitgestellten Anwendungen
- **Portal-Ansicht** (`/app/:slug`) – ein einzelnes Formular oder Dashboard

Benutzer mit reiner Portal-Berechtigung werden automatisch dorthin geleitet und sehen
die Editor-Bereiche (Mappings, Pipelines …) nicht. So kann man Kollegen oder Kunden ein
„Intrastat-Meldung erzeugen“-Formular oder ein Kennzahlen-Cockpit geben, ohne ihnen die
gesamte Plattform zu öffnen.

Das Portal ist funktional gleichwertig: Zeitraumfilter, Drilldown, KI-Empfehlungen,
KI-Anbieterwahl mit sichtbarem Guthaben, Exporte, Ausschlusslisten und der PDF-Bericht
funktionieren dort genauso. Ein Portal kann mehrere Formulare enthalten.

Damit ein Formular im Portal erscheint, muss es **veröffentlicht** sein und eine Adresse
(Slug) haben.

---

## 13. Benutzer, Rollen & Systemeinstellungen

### Rollen
| Rolle | Umfang |
|---|---|
| **Admin** | Vollzugriff inklusive Benutzerverwaltung |
| **Editor** | Zugriff auf die volle Plattform (Mappings, Pipelines, Formulare …) |
| **Portal** | Sieht nur veröffentlichte Formulare, keinen Editor |

Projekte lassen sich einzelnen Benutzern freigeben. Das Passwort ändert jeder selbst.

### Systemeinstellungen (Zahnrad oben rechts)
| Reiter | Inhalt |
|---|---|
| **E-Mail** | Postausgang für Benachrichtigungen und den Versand von Tabellen/Berichten |
| **KI** | Anbieterwahl (Ollama oder Datenmonster AI), Guthaben, Modellstrategie |
| **Modelle** | Installierte Modelle, Nachladen, Code- und Textmodell, Vorwärmen |
| **Benutzer** | Benutzer anlegen, Rollen vergeben |
| **Netzwerk** | Schutz vor missbräuchlichen ausgehenden Aufrufen: Cloud-Metadaten-Adressen sind immer gesperrt, interne Netze für den Betrieb vor Ort erlaubt und protokolliert; per Positiv- und Negativliste anpassbar |
| **Optik** | Dunkles oder helles Erscheinungsbild, oder der Systemeinstellung folgen |
| **Sicherung** | Datensicherung anlegen, herunterladen, zurückspielen – nur für Administratoren sichtbar, weil ein Archiv die Zugangsdaten aller Verbindungen enthält |

### Erste Schritte
Für neue Installationen gibt es eine **Erste-Schritte-Checkliste** auf dem Dashboard;
leere Bereiche erklären, was dort hingehört und wie man anfängt.

---

## 14. Typischer Arbeitsablauf

1. **Projekt anlegen** – als organisatorische Klammer.
2. **Datenquellen verbinden** – DB-Connector einrichten, Verbindung testen (dabei
   entsteht der Schema-Cache) und Datasets über den Assistenten erstellen.
3. **Alternativ: fertige Vorlage installieren** – bei der JTL-Wawi bringt eine Vorlage
   Mappings, Dashboard und Warn-Regeln fertig mit (Kapitel 10).
4. **Mapping bauen** – Quell-Datasets einbinden, joinen, Transformations-Nodes ergänzen
   (Transform, Lookup, SQL, Python, Datenqualität, KI …), Feldzuordnung – gern per Smart
   Mapping – und ein Ziel mit passendem Schreibmodus wählen. Zwischendurch das
   **Vorschau-Panel** und den **Debug-Lauf** nutzen.
5. **Formular oder Dashboard erstellen** – Eingabefelder und Filter anlegen, als Aktion
   das Mapping hinterlegen und die Ergebnisse mit Widgets darstellen.
6. **Pipeline automatisieren** – Trigger (Zeitplan) → Mapping → ggf. Verzweigung →
   FTP-Upload / E-Mail / Business Insights verketten.
7. **Warnungen einrichten** – Schwellwerte und Fixkosten pflegen, Regeln festlegen, den
   nächtlichen Lauf aktivieren.
8. **Bereitstellen** – Formulare veröffentlichen und über das Portal für Endanwender
   freigeben.
9. **Überwachen** – im Monitoring Kennzahlen, Status und Fehlerprotokoll prüfen;
   Ausgaben unter „Exporte“ herunterladen.

---

*Diese Anleitung beschreibt den Funktionsstand von Datenmonster zum genannten Zeitpunkt.
Bei Fragen hilft der eingebaute KI-Assistent kontextbezogen auf jeder Seite weiter.*
