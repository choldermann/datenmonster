# Datenmonster – Was wir können (Stand 2026-06-27)

## Datenquellen & Formate

### Datenbankverbindungen
- **MS SQL Server** (MSSQL/pyodbc)
- **MySQL / MariaDB**
- **PostgreSQL**
- **SQLite**
- **Microsoft Access** (.mdb / .accdb via mdbtools)

### Dateiformate
- CSV, Excel (.xlsx / .xls), XML, JSON, ODS
- Parquet (für Hochleistungs-JOINs via DuckDB)
- Statische Datasets (manuell gepflegte Tabellen im Browser)

### Sonstige Quellen
- **REST-API** (GET/POST, Auth: Bearer/Basic, JSON-Pfad-Extraktion)
- **E-Mail / IMAP** (Mail-Connector, regelbasiert)
- **HTML-Seiten** (Web-Scraper mit Visual Selector)
- **MongoDB** (Plugin, Collection als Quelle und Ziel)

---

## Dataset-Management

- Datasets anlegen aus: Datei-Upload, DB-Abfrage (SQL), REST, Plugin, manuell
- **KI-Dataset-Assistent**: Beschreibung → KI findet Tabellen → generiert SELECT-Abfragen
- Schema-Editor: Spaltentypen, Pflichtfelder, FK-Badges
- **Database Analyzer**: interaktives ER-Diagramm, FK-Beziehungen visualisieren, Pfadfinder mit Zwischenstationen, Dataset direkt aus Diagramm importieren
- Auto-Refresh: Datasets per Zeitplan automatisch neu laden
- Daten-Explorer: Inline-Vorschau, Suche, Sortierung
- Dataset-Zeilen-Editor (für statische Datasets)
- FK-Badge in Spaltenköpfen

---

## Mapping-Editor (ETL-Canvas)

Visueller Flow-Editor mit Nodes per Drag & Drop.

### Daten-Eingang
| Node | Funktion |
|---|---|
| **Dataset Node** | Zieht Daten aus einem Dataset (DB, Datei, REST, …) |
| **Params Node** | Laufzeit-Parameter (werden bei Ausführung abgefragt) |

### Transformation
| Node | Funktion |
|---|---|
| **Transform Node** | Feldmapping, Umbenennen, Typen, Standardwerte, String-/Zahlen-/Datumsoperationen |
| **Calc Node** | Berechnungen zwischen Feldern |
| **Constant Node** | Feste Werte einfügen |
| **Expression Node** | Formelausdrücke: `{feldname}`, `upper()`, `if_()`, `concat()`, `today()` u.v.m. |
| **Python Node** | Beliebiges Python-Skript pro Datensatz (Sandbox, Timeout 3s) |
| **SQL Node** | SQL-Abfrage direkt auf DB-Quelle; Lookup-Modus mit `:param`-Binding (row_by_row / batch-IN) |
| **Aggregation Node** | GROUP BY + Aggregatfunktionen (SUM, COUNT, AVG, …) |
| **REST Node** | HTTP-Requests als Transformation (Lookup, Anreicherung) |
| **Switch Node** | Routing nach Bedingungen (mehrere Ausgänge) |
| **Data Quality Node** | Validierungsregeln pro Feld (required, number, email, IBAN, EAN, Regex, …), gibt `__dq_valid__` und `__dq_errors__` aus |

### Canvas-Features
- Zoom, Pan, Minimap
- Nodes minimieren/expandieren
- Verbindungslinien per Klick löschbar
- Auto-Join-Erkennung beim Hinzufügen von Datasets
- PK/FK automatisch erkennen und als Badge anzeigen
- Dataset-Nodes resizable
- Filter & Sortierung direkt im Canvas konfigurierbar
- SQL Filter-Pushdown für DB-Quellen (bis 25× schneller)
- Anti-Join (LEFT ANTI / RIGHT ANTI)
- Vorschau an jeder Verbindungslinie
- Node Statistics: nach Debug-Run zeigt jeder Node Zeilen-In/Out + Fehler

### Debug-Run
- **Phase 1**: Stage-Flow mit Sample-Daten je Stage
- **Phase 2**: Canvas-Glow, Feld-Tooltips, Row Inspector, Step-Through
- Einzeldatensatz durch alle Stages verfolgen

### KI im Mapping
- SQL erklären / generieren
- Python-Code generieren / Fehler erklären
- Ausdruck vorschlagen (Expression Node)
- Feld-Verknüpfungsvorschläge (Smart Mapping)
- Aktives Modell im Modal-Header sichtbar

---

## Pipeline-Editor

- Mehrere Mappings in einer Pipeline sequenziell oder parallel verknüpfen
- Ausführungsreihenfolge konfigurierbar

---

## Scheduler

- Mappings und Pipelines per Cron-Zeitplan automatisch ausführen
- Log der letzten Ausführungen

---

## Dispatcher

- Zentrales Routing von eingehenden Daten auf verschiedene Ziele/Mappings

---

## Exporte

- Mapping-Ergebnis als CSV, Excel, JSON, XML, Parquet exportieren
- Export-Liste: alle erzeugten Exporte mit Download

---

## Form-System

### Form Builder
- Drag & Drop Canvas mit Feldtypen: Text, Zahl, Datum, Auswahl, Checkbox, Textarea
- 3-Panel-Layout: Palette | Canvas | Eigenschaften
- Pflichtfelder, Platzhalter, Reihenfolge konfigurierbar

### Portal (öffentliche Formulare)
- Formulare ohne Login zugänglich (eigene URL)
- Responsives Grid-Layout
- Vollständige Validierung, Einreichung per POST

### Ergebnis-Widgets
- Nach Submit: konfigurierbare Ergebnis-Seite
- Widgets: Text, Tabelle, Diagramm (Chart.js), Karte
- Mapping kann als Datenquelle für Widgets dienen

---

## KI-Assistent (lokal, Ollama)

- Läuft vollständig **lokal** auf eigenem Server (kein Cloud-API-Key)
- Kompatibel mit OpenAI-API → austauschbar gegen Groq, LM Studio, Azure
- Modell-Verwaltung direkt im UI: installieren, wechseln, Download-Fortschritt

### KI-Dataset-Assistent (3-Step-Flow)
1. **Beschreibung**: Freitext ("Rechnungen mit Lieferantendaten")
2. **Tabellenauswahl**: KI schlägt Tabellen vor (Keyword + FK-Expansion, deutsches Stemming), Preview-Modal je Tabelle
3. **SQL-Generierung**: KI generiert SELECT-Abfragen, bearbeitbar, direkt als Datasets anlegbar

### Schema-Cache
- Vollständiges DB-Schema (Tabellen, Spalten, Typen, PK/FK) persistent gespeichert
- MSSQL: Single-Query-Ansatz (kein Inspector-Hang bei 1000+ Tabellen)
- Wird automatisch beim Connection-Test aufgebaut

---

## Verbindungs-Manager (Datenbanken)

- Verbindungen anlegen: MSSQL, MySQL, PostgreSQL, SQLite, Access
- Connection-Test mit automatischem Schema-Cache-Aufbau
- Schema-Cache-Status + Alter auf jeder Kachel
- Rebuild-Button
- KI-Dataset-Assistent direkt aus Verbindungs-Kachel starten
- Import: Tabelle direkt als Dataset importieren

---

## FTP / SFTP

- FTP/SFTP-Verbindungen verwalten
- Dateien hoch-/herunterladen, als Quelle/Ziel in Mappings nutzbar

---

## REST-API (eingehend)

- Eigene REST-Endpunkte definieren (intern)
- Daten per POST empfangen → Mapping auslösen

---

## Monitoring & System

- CPU, RAM, Speichernutzung, SQLite-Größe, Uptime
- System-Log mit Projekt-Spalte
- Ausführungshistorie

---

## Projekte & Benutzer

- Mehrmandantenfähig: Projekte isolieren Datasets, Mappings, Formulare
- Benutzer-Verwaltung mit Rollen
- Projekt teilen zwischen Benutzern
- Passwort ändern

---

## Plugin-System

- **Tier-1**: Builtin-Plugins im Backend (Mail, Web/HTML)
- **Tier-2**: Externe Python-Plugins (`manifest.json` + `connector.py`)
- Installiertes Plugin: **MongoDB Connector**
- Neue Plugins per Datei-Upload installierbar

---

## Technischer Stack

| Schicht | Technologie |
|---|---|
| Backend | FastAPI + SQLAlchemy + SQLite |
| Frontend | React + Tailwind CSS |
| KI | Ollama (lokal), qwen2.5-coder:3b empfohlen |
| JOINs | DuckDB (in-process) |
| Scheduling | APScheduler |
| Container | Docker Compose |
| Proxy | nginx mit SSE-Support |
