# Datenmonster – Anleitung

*Self-hosted ETL- & Datenintegrations-Plattform von Holdermann IT*

Datenmonster verbindet Datenquellen (Dateien, Datenbanken, REST-APIs, FTP), transformiert
die Daten über einen visuellen Node-Editor und automatisiert alles über Pipelines und
Formulare – vollständig auf dem eigenen Server, ohne Cloud-Abhängigkeit.

Diese Anleitung führt von der Einrichtung über den Menüaufbau bis zu den einzelnen
Funktionen. Die Kapitel **Mapping**, **Pipeline**, **Formulare** und **KI-Assistenten**
sind besonders ausführlich.

---

## Inhaltsverzeichnis

1. [Grundbegriffe](#1-grundbegriffe)
2. [Einrichtung & Installation](#2-einrichtung--installation)
3. [Menüaufbau (Übersicht)](#3-menüaufbau-übersicht)
4. [Die Menüpunkte im Detail](#4-die-menüpunkte-im-detail)
5. [Mapping-Editor – Nodes im Detail](#5-mapping-editor--nodes-im-detail)
6. [Pipeline-Editor – Nodes im Detail](#6-pipeline-editor--nodes-im-detail)
7. [Formular-Builder](#7-formular-builder)
8. [KI-Assistenten](#8-ki-assistenten)
9. [Portal (Endanwender-Sicht)](#9-portal-endanwender-sicht)
10. [Typischer Arbeitsablauf](#10-typischer-arbeitsablauf)

---

## 1. Grundbegriffe

| Begriff | Bedeutung |
|---|---|
| **Dataset** | Eine Datenquelle: hochgeladene Datei (CSV/Excel/XML), DB-Tabelle, REST-Antwort oder manuell angelegte Tabelle. |
| **DB-Connector** | Gespeicherte Datenbankverbindung (MSSQL / MySQL), die von Datasets und Nodes wiederverwendet wird. |
| **Mapping** | Ein visueller ETL-Ablauf: Quelldaten → Transformation → Zielausgabe. Das Herzstück der Anwendung. |
| **Node** | Ein einzelner Baustein im Mapping- oder Pipeline-Editor (z. B. „Transform“, „SQL“, „Aggregation“). |
| **Pipeline** | Verkettung mehrerer Schritte (Mappings, FTP, E-Mail …), zeitgesteuert oder manuell ausführbar. |
| **Formular** | Eine Eingabemaske, die beim Absenden ein Mapping oder eine Pipeline startet. |
| **Portal** | Vereinfachte Oberfläche für Endanwender, die nur Formulare ausfüllen sollen. |
| **Template** | Exportierbare/importierbare Vorlage eines Mappings inkl. aller Abhängigkeiten. |

---

## 2. Einrichtung & Installation

### Voraussetzungen
- Docker + Docker Compose
- Für KI-Funktionen: der mitgelieferte **Ollama**-Container (lokales LLM, keine Cloud)

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
docker compose up --build -d
```

Danach im Browser öffnen: **http://localhost:5173**
Standard-Login: `admin` / *(Passwort aus `.env` oder aus den Container-Logs)*.

> ⚠️ **Wichtig:** Die `.env` enthält Passwörter und darf **niemals** ins Repository
> committed werden (steht bereits in `.gitignore`). Ohne `SECRET_KEY` startet der
> Backend-Container nicht.

### Architektur der Container
- **Backend** – FastAPI (Python), stellt die REST-API unter `/api/` bereit.
- **Frontend** – React/Vite, per nginx ausgeliefert (Port 5173 → 80).
- **Ollama** – lokales LLM für alle KI-Funktionen (`OLLAMA_BASE_URL=http://ollama:11434`).
- **Datenbank** – standardmäßig SQLite (Pfad über `DATABASE_URL`), Daten unter `/app/uploads/`.

> **Hinweis bei Änderungen:** Frontend-Änderungen erfordern einen Neubau mit
> `docker compose up --build -d frontend`, reines Backend-Rebuild reicht dafür nicht.

---

## 3. Menüaufbau (Übersicht)

Nach dem Login landet man im **Dashboard**. Links befindet sich die feste Seitenleiste
(Sidebar) mit allen Bereichen. Die Reihenfolge ist in logische Blöcke gegliedert:

**Block 1 – Organisation**
- **Projekte** – oberste Gliederungsebene, bündelt zusammengehörige Daten.

**Block 2 – Datenquellen**
- **DB-Connectors** – Datenbankverbindungen
- **Datasets** – alle Datensätze/Tabellen
- **FTP / SFTP** – Dateiquellen per (S)FTP
- **REST API** – externe HTTP-Schnittstellen als Quelle

**Block 3 – Verarbeitung**
- **Templates** – Vorlagen exportieren/importieren
- **Mappings** – visuelle ETL-Abläufe
- **Pipelines** – automatisierte Ketten
- **Formulare** – Eingabemasken
- **Exporte** – erzeugte Ausgabedateien

**Block 4 – Betrieb**
- **Monitoring** – Live-Status, KPIs, Fehlerprotokoll
- **Plugins** – installierte Konnektor-Erweiterungen

**Block 5 – KI & Verwaltung**
- **AI Memory** – Wissensdatenbank des KI-Assistenten
- **Lizenz** – Lizenzverwaltung

Jeder Eintrag zeigt rechts eine **Badge** mit der Anzahl der jeweiligen Objekte.

---

## 4. Die Menüpunkte im Detail

### Projekte
Die oberste Gliederungsebene. Ein Projekt bündelt Datasets, Mappings, Pipelines und Jobs.
Beim Löschen eines Projekts werden **alle** zugehörigen Daten unwiderruflich entfernt –
die Anwendung fragt hier ausdrücklich nach.

### DB-Connectors
Verwaltung gespeicherter Datenbankverbindungen (MSSQL / MySQL). Angelegte Connectors
lassen sich testen und werden anschließend überall wiederverwendet: als Dataset-Quelle,
im **SQL-Node**, beim **DB-Schreiben** und im Datenbank-Analyzer. Zugangsdaten werden im
Backend optional per Fernet verschlüsselt gespeichert.

### Datasets
Zentrale Übersicht aller Datenquellen. Ein neues Dataset legt man über den **Assistenten**
(*New Dataset Wizard*) an. Unterstützte Typen:
- **Datei-Upload:** CSV, XLSX, XML, ODS, MS Access
- **SQL-Import:** aus einem DB-Connector (Tabelle oder eigene Abfrage)
- **FTP/SFTP-Sync:** mit Wildcard-Filter (`*.csv`, `export_*.xlsx`)
- **REST-Quelle:** JSON-Antwort einer HTTP-API
- **Manuelles Dataset:** Spalten selbst definieren, inkl. Primärschlüssel & Auto-Increment

Im **Dataset-Explorer** lassen sich Daten mit Paginierung und Suche durchblättern, der
Datentyp einzelner Spalten inline ändern und (bei manuellen Datasets) Zeilen direkt
bearbeiten. Ein Dataset, das noch in einem Mapping verwendet wird, warnt beim Löschen.

### FTP / SFTP
Verwaltung von FTP-/SFTP-Quellen als eigene Kategorie: Serveradresse, Zugangsdaten,
Verzeichnis und Dateifilter. Diese Quellen werden sowohl für Datasets als auch für den
**FTP-Input-Node** in Pipelines genutzt.

### REST API
Verwaltung wiederverwendbarer REST-Quellen: URL, Methode, Authentifizierung und
JSON-Pfad. Dient als Dataset-Quelle und als Vorlage für REST-Nodes.

### Templates
Mappings lassen sich als **Template** exportieren und wieder importieren. Beim Export
werden interne IDs in portable Referenzen umgeschrieben, sodass ein Mapping inklusive
seiner Abhängigkeiten auf einer anderen Instanz installiert werden kann.

### Exporte
Liste aller durch Mappings/Pipelines erzeugten Ausgabedateien (CSV, Excel, JSON, XML …)
zum Herunterladen. Ältere Exporte können hier entfernt werden.

### Monitoring
Live-Dashboard mit Kennzahlen (KPIs), Pipeline-Status und Fehlerprotokoll. Enthält ein
System-Log mit Stacktrace-Ansicht und aktualisiert sich automatisch alle 30 Sekunden.

### Plugins
Übersicht der installierten Konnektor-Erweiterungen. Datenmonster kennt zwei Stufen:
- **Tier 1** – reine Python-Module (kein eigener Container), z. B. MongoDB, SFTP, Mail.
- **Tier 2** – eigenständige Docker-Container mit REST-API (lizenzgeprüft), z. B.
  eSTATISTIK.core.

### AI Memory
Die Wissens- und Gedächtnisverwaltung des KI-Assistenten. Drei Bereiche:
- **Knowledge** – dauerhaftes Fachwissen (z. B. Bedeutung von Tabellen/Spalten). Kann
  auch automatisch aus einem DB-Schema importiert werden.
- **Solutions** – bewährte Lösungen/Snippets, die der Assistent wiederverwenden kann.
- **Corrections** – Korrekturen, aus denen der Assistent lernt.

Zusätzlich verwaltet dieser Bereich einen Antwort-Cache (Statistiken einsehbar/leerbar)
und **Suggestions**, die zu dauerhaftem Wissen „befördert“ werden können.

### Lizenz
Eingabe und Statusanzeige des Lizenzschlüssels; schaltet Tier-2-Plugins und optionale
Funktionen frei.

---

## 5. Mapping-Editor – Nodes im Detail

Der Mapping-Editor ist der zentrale visuelle ETL-Baukasten (basiert auf React Flow).
Man zieht **Nodes** auf die Arbeitsfläche, verbindet sie durch Ziehen der Ports und
baut so den Datenfluss von der Quelle bis zum Ziel auf. Über eine Info-Schaltfläche an
jedem Node öffnet sich eine Beschreibung seiner Funktionen.

**Grundprinzip:** Links stehen Quell-Nodes, in der Mitte Transformationen, rechts das
Zielfeld-Mapping bzw. das Export-Ziel. Zwischen Quell-Datasets können **Joins** gelegt
werden.

### Quell- und Struktur-Nodes

**Dataset-Node**
Bindet ein vorhandenes Dataset als Datenquelle ein. Mehrere Dataset-Nodes lassen sich
über Joins verknüpfen. Verfügbare Join-Typen:
`INNER`, `LEFT`, `RIGHT`, `FULL OUTER`, `LEFT ANTI`, `RIGHT ANTI`.

**Konstante (Constant-Node)**
Erzeugt einen festen Wert als virtuelles Quellfeld – ganz ohne Datenquelle. Typen:
- Statischer Text oder Zahl
- Aktuelles Datum, Datum + Uhrzeit oder Jahr (zur Laufzeit berechnet)
- Zufällige UUID (v4)
- Boolean `true` / `false`

**Parameter-Node**
Stellt Laufzeit-Parameter bereit (z. B. aus einem Formular oder beim Pipeline-Start
übergeben), die in nachfolgenden Nodes verwendet werden können.

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
- Die Felder des gewählten Datasets werden in die Pipeline eingespeist

### Nachschlage- und Integrations-Nodes

**Lookup-Node** – schlägt Werte aus einem anderen Dataset über ein Schlüsselfeld nach:
- Schlüsselfeld der Pipeline gegen eine Spalte im Lookup-Dataset abgleichen
- beliebig viele Ausgabefelder übernehmen
- Verhalten bei fehlendem Treffer: `null`, leer lassen oder fester Fallback

**SQL-Node** – führt eine SQL-Abfrage auf einem DB-Connector aus:
- **Scalar-Modus:** liefert einen Wert pro Ausgabezeile (klassische Lookup-Abfrage)
- **Transform-Modus:** ersetzt die gesamte Datenpipeline durch das SQL-Ergebnis
- Parameter aus Quellfeldern über `{{feldname}}`
- unterstützt MSSQL und MySQL
- Der KI-Assistent kann SQL erklären oder aus einer Beschreibung generieren.

**REST-Node** – ruft pro Zeile (oder als Batch) eine externe HTTP-API auf:
- GET und POST, beliebige URL mit `{{feldname}}`-Platzhaltern
- Auth: Bearer-Token, API-Key-Header oder HTTP Basic
- JSON-Pfad zur Antwort (z. B. `data.result.price`)
- **Batch-Modus:** alle Schlüssel in einem einzigen API-Call bündeln

**Python-Node** – eigene Python-Logik pro Datensatz, wenn kein Standard-Node reicht:
- Eingabe ist ein `row`-Dict mit allen aktuellen Feldern
- Felder neu anlegen, überschreiben oder löschen
- Zugriff auf `math`, `re`, `json`, `decimal`, `statistics`, `datetime`
- **Sicherheits-Sandbox:** kein Dateisystem, kein Netzwerk, kein `import`; Timeout 3 s
  pro Zeile; ein Fehler stoppt nur die betroffene Zeile
- Der KI-Assistent kann Python-Code aus einer Beschreibung generieren.

**Data-Quality-Node** – prüft Feldwerte gegen Regeln (z. B. Regex wie `^\d{5}$` für PLZ)
und markiert/meldet fehlerhafte Datensätze mit einer eigenen Fehlermeldung.

**AI-Transform-Node** (lila) – wendet ein KI-Modell auf jede Zeile an:
- Freitext-Prompt mit `{{feldname}}`-Platzhaltern (Felder per Doppelklick einfügbar)
- liefert strukturierte Ausgabe (Structured Output) in Zielfelder
- Modell wählbar (z. B. `qwen2.5:7b`)
- Panel „Verfügbare Felder“ zum schnellen Einsetzen von Platzhaltern
- Ideal für Kategorisierung, Textbereinigung, Extraktion aus Freitext.

### Ziel / Ausgabe

Das rechte Ende des Mappings definiert, **wohin** geschrieben wird. Export-Ziele:
- **Dateien:** CSV, Excel (XLSX), JSON, XML, Destatis-CSV
- **Datenbank:** MSSQL / MySQL (über einen DB-Connector)
- **Dataset:** Ergebnis als neues/aktualisiertes Dataset zurückschreiben

**Schreibmodi** beim DB-/Dataset-Ziel:
- **Replace** – Zieldaten ersetzen
- **Append** – anhängen
- **Upsert** – über Primärschlüssel abgleichen (aktualisieren oder einfügen)

### Hilfsfunktionen im Editor
- **Vorschau-Panel (Preview):** zeigt die Ergebniszeilen live, bevor exportiert wird.
- **Debug-Panel:** Zwischenergebnisse einzelner Nodes nachvollziehen.
- **Minimap:** Navigation bei großen Mappings.
- **Smart Mapping:** KI-gestützter Vorschlag der Feldzuordnungen (siehe Kapitel 8).
- **SQL-Editor-Modal / Filter-&-Sort-Editor:** komfortable Detaileinstellungen.
- **Export-Modal:** Zielformat und Optionen wählen und Datei erzeugen.

---

## 6. Pipeline-Editor – Nodes im Detail

Eine **Pipeline** verkettet mehrere Schritte zu einem automatisierten Ablauf. Auch hier
zieht man Nodes auf die Fläche und verbindet sie. Nodes haben Ein- und Ausgangs-Ports;
Verzweigungs-Nodes besitzen mehrere Ausgänge.

### Trigger (⏰, gold)
Der **Startpunkt** jeder Pipeline. Auslöser-Modus **Zeitplan**: Über eine komfortable
Oberfläche (Uhrzeit, Intervall, Wochentage, Monatstage) wird im Hintergrund automatisch
ein **Cron-Ausdruck** gebaut; eine Vorschau zeigt den Zeitplan an. Die Ausführung
übernimmt der APScheduler im Backend. Pipelines lassen sich zusätzlich manuell starten.

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
- Nach einem **Datei-/FTP-Eingang:** z. B. Datei vorhanden, Anzahl Dateien, Namensmuster.
- Nach einem **Mapping:** z. B. Ergebnis hat Zeilen, Zeilenzahl über/unter Schwellwert.
Bei mehreren Bedingungen sind sie per **AND/OR** verknüpfbar.

### Bedingung (❓, amber)
Einfache Wenn/Dann-Verzweigung als eigenständiger Node – schlanker als der Dispatcher,
für einzelne Ja/Nein-Entscheidungen.

### FTP Upload (📤, orange)
Lädt eine erzeugte Datei auf einen FTP-/SFTP-Server hoch – typischer Abschluss-Schritt.

### E-Mail (📧, pink)
Versendet eine Benachrichtigung oder ein Ergebnis (z. B. eine Export-Datei oder einen
Report) per E-Mail.

### Business Insights (💡, violet)
Analysiert die Daten betriebswirtschaftlich und erzeugt Kennzahlen, Trends und Anomalien.
Die Felder werden semantisch zugeordnet – Pflichtfelder **Umsatz/Kennzahl** und
**Datumsfeld**, optional **Land/Region, Kunde, Artikel, Menge, Lagerbestand**.
Fertige **Presets** beschleunigen die Einrichtung:
- Umsatzentwicklung
- Länderanalyse
- Top-Kunden
- Lagerbestand

Vergleichszeiträume: aktueller Monat vs. Vormonat, Monat vs. Vorjahresmonat, Jahr vs.
Vorjahr oder ein frei gewählter Zeitraum.

---

## 7. Formular-Builder

Formulare sind Eingabemasken, die beim Absenden eine Aktion auslösen (Mapping oder
Pipeline). Damit werden ETL-Abläufe auch für Nicht-Techniker im **Portal** nutzbar.

### Aufbau des Editors
- **Feld-Palette** (links): alle verfügbaren Feldtypen zum Hineinziehen.
- **Canvas** (Mitte): das Formular im 12-Spalten-Raster; Felder werden per Drag & Drop
  angeordnet, jede `colSpan` bestimmt die Breite.
- **Eigenschaften** (rechts): Label, Feldname, Pflichtfeld, Platzhalter, Standardwert,
  Optionen usw. für das ausgewählte Feld.
- **Vorschau** und **Submissions** (eingegangene Ausfüllungen) sind ebenfalls einsehbar.

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

**Aktionen**
| Typ | Beschreibung |
|---|---|
| Button | löst eine hinterlegte Aktion aus (z. B. „Auswerten“) |

**Layout**
| Typ | Beschreibung |
|---|---|
| Überschrift | Gliederungstitel |
| Text / Label | erklärender Text |
| Trennlinie | optische Trennung |
| Container | Gruppierung mehrerer Felder |

### Pflichtfelder & Validierung
Jedes Feld kann als **Pflichtfeld** markiert werden. Beim Absenden validiert das
Formular, dass alle Pflichtfelder ausgefüllt sind.

### Aktionen (was beim Absenden passiert)
Über den **Aktionen-Editor** wird festgelegt, was ein Button/das Formular auslöst:
- **Mapping ausführen** (`run_mapping`) – startet ein ausgewähltes Mapping und übergibt
  die Formularwerte als Parameter.
- **Pipeline ausführen** (`run_pipeline`) – startet eine komplette Pipeline.

Jede Aktion bekommt ein eigenes Label (z. B. „Auswerten“, „Bericht erzeugen“).

### KI-Unterstützung im Formular
Der Button **AI Field Suggest** schlägt anhand einer Beschreibung passende Formularfelder
vor, sodass man ein Formular nicht komplett von Hand aufbauen muss.

### Ausführen
Ein Formular lässt sich direkt über den **Form-Runner** testen. Für Endanwender wird es
über das **Portal** bereitgestellt (siehe Kapitel 9).

---

## 8. KI-Assistenten

Alle KI-Funktionen laufen über den lokalen **Ollama**-Container – es verlassen keine Daten
den Server. Der KI-Status (verbunden? welche Modelle installiert?) ist einsehbar, und
Modelle können bei Bedarf nachgeladen (`pull`) werden.

### Der schwebende KI-Assistent (Floating AI Assistant)
Ein Chat-Fenster, das auf jeder Seite verfügbar ist. Er kennt den **Kontext der aktuellen
Seite** (welches Mapping/Dataset gerade offen ist, welche Daten sichtbar sind) und
beantwortet Fragen dazu. Drei Modi steuern Tempo vs. Tiefe:
- **⚡ Schnell** – kleines Modell, kurze Antworten, ohne „Nachdenken“.
- **⚖ Auto** – Datenmonster wählt Modell und Modus automatisch.
- **🧠 Analyse** – großes Modell, ausführliche Antworten mit „Reasoning“.

Optional lässt sich die **Schema-Wissensdatenbank** zuschalten: Dann lädt der Assistent
das DB-Schema und gibt bessere Antworten zu JOINs und Tabellenbeziehungen.

### KI im Mapping-Editor
- **Smart Mapping** – schlägt automatisch Feldzuordnungen zwischen Quelle und Ziel vor
  (semantischer Abgleich der Feldnamen), inklusive vorgefertigter Presets.
- **AI-Transform-Node** – KI-Transformation pro Zeile mit strukturierter Ausgabe
  (siehe Kapitel 5).
- **SQL generieren / erklären** – im SQL-Node aus Beschreibung SQL erzeugen oder
  bestehendes SQL erklären lassen.
- **Python generieren** – im Python-Node Code aus einer Beschreibung erstellen.
- **Ausdruck generieren** – im Expression-Node Formeln aus Text ableiten.
- **Fehler erklären** – Fehlermeldungen verständlich aufschlüsseln lassen.
- **Node-Vorschläge** – ganze Node-Ketten aus einer Aufgabenbeschreibung generieren.

### KI beim Dataset-Anlegen (AI Dataset Wizard)
Auf Grundlage einer Beschreibung schlägt die KI passende **Datasets/Tabellen** und deren
Felder vor, statt dass man die Struktur manuell definiert.

### KI im Formular
**AI Field Suggest** erzeugt Formularfelder aus einer Beschreibung (siehe Kapitel 7).

### AI Memory (Wissen & Lernen)
Damit die KI über Sitzungen hinweg besser wird (siehe auch Kapitel 4):
- **Knowledge** – dauerhaftes Fachwissen, auch per **Schema-Import** befüllbar.
- **Solutions** – wiederverwendbare Lösungen; „use“ zählt die Nutzung.
- **Corrections** – Korrekturen, aus denen der Assistent lernt.
- **Cache** – Antwort-Cache mit Statistik; kann geleert werden.
- **Suggestions** – automatische Vorschläge, die zu Wissen befördert werden können.

---

## 9. Portal (Endanwender-Sicht)

Neben der vollen Editor-Oberfläche gibt es das **Portal** – eine reduzierte Ansicht für
Anwender, die nur Formulare bedienen sollen:
- **Portal-Startseite** (`/portal`) – Übersicht der bereitgestellten Anwendungen/Formulare.
- **Portal-Runner** (`/app/:slug`) – ein einzelnes Formular ausfüllen und absenden.

Benutzer mit reiner Portal-Berechtigung werden automatisch dorthin geleitet und sehen die
Editor-Bereiche (Mappings, Pipelines …) nicht. So kann man z. B. Kollegen ein
„Intrastat-Meldung erzeugen“-Formular geben, ohne ihnen die gesamte Plattform zu öffnen.

---

## 10. Typischer Arbeitsablauf

1. **Projekt anlegen** – als organisatorische Klammer.
2. **Datenquellen verbinden** – DB-Connector einrichten und/oder Datasets über den
   Wizard erstellen (Upload, SQL, FTP, REST oder manuell).
3. **Mapping bauen** – Quell-Datasets einbinden, ggf. joinen, Transformations-Nodes
   ergänzen (Transform, Lookup, SQL, Python, KI …), Feldzuordnung – gern per Smart
   Mapping – und ein Export-Ziel mit passendem Schreibmodus wählen. Zwischendurch das
   **Vorschau-Panel** nutzen.
4. **Formular erstellen** (optional) – Eingabemaske mit Feldern bauen und als Aktion das
   Mapping oder eine Pipeline hinterlegen.
5. **Pipeline automatisieren** (optional) – Trigger (Zeitplan) → Mapping → ggf.
   Verzweigung → FTP-Upload / E-Mail / Business Insights verketten.
6. **Bereitstellen** – Formulare über das Portal für Endanwender freigeben.
7. **Überwachen** – im Monitoring KPIs, Pipeline-Status und Fehlerprotokoll prüfen;
   Ausgaben unter „Exporte“ herunterladen.

---

*Diese Anleitung beschreibt den Funktionsstand von Datenmonster zum Zeitpunkt der
Erstellung. Bei Fragen hilft der eingebaute KI-Assistent kontextbezogen auf jeder Seite
weiter.*
