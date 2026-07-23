# Datenmonster – Feature-Übersicht

Stand: 2026-07-01 | Holdermann IT ETL-Plattform

---

## Mapping Editor / Canvas

### Grundfunktionen
- Visueller Canvas mit Drag & Drop für Datasets und Nodes
- Felder per Klick oder Drag verbinden (Quelle → Ziel)
- Mehrere Ziele pro Mapping (Multi-Target)
- Zielfelder umbenennen, Standardwerte setzen
- Typ-Konvertierung pro Verbindung (int, float, date, string)
- Typ-Durchsetzung mit Warnung bei Typkonflikten (2026-06-25)
- Upsert-Modus für Dataset-Ziele (Append / Replace / Upsert per Key) (2026-05-01)
- Sortierung und Limit im Zielschritt (2026-04-18)
- Template-Export und -Import (alle Node-Typen) (2026-06-25)
- Vorschau-Panel: Ergebnis der aktuellen Mapping-Konfiguration
- Schema-Ansicht: Spaltentypen der Ausgabe

### Nodes
| Node | Farbe | Funktion | Seit |
|---|---|---|---|
| **Dataset-Node** | blau | Quell-Dataset auf Canvas, filterbar, sortierbar, resizable | v1.0 |
| **Transform-Node** | lila | Zahlenformate, Datumsformate, String-Operationen, Verkettung, Bedingte Werte | v1.0 / 2026-06-26 |
| **Konstante** | violett | Statischer Wert oder berechneter Ausdruck als Quelle | v1.0 |
| **SQL-Node** | cyan | Direkte SQL-Abfrage auf DB-Verbindung, Scalar/Lookup-Modus | 2026-04-18 |
| **Aggregation-Node** | amber | GROUP BY, SUM, COUNT, AVG, MIN, MAX, DISTINCT | v1.0 |
| **Berechnung-Node** | rosa | Fensterfunktionen: Cumsum, Moving Average, Row Number, Rank, Lag/Lead | 2026-06-26 |
| **REST-Node** | teal | HTTP-GET/POST pro Zeile, Auth (Bearer, Basic, API-Key), JSON-Pfad | v1.0 |
| **Lookup-Node** | grün | Dataset-Lookup per Schlüsselfeld, on_missing konfigurierbar | v1.0 |
| **Switch-Node** | orange | Bedingte Verzweigung (has_rows, Schwellenwert, always) | v1.0 |
| **Python-Node** | grün | Freies Python-Skript mit DataFrame-Zugriff, eigene Output-Felder | 2026-06-26 |
| **Expression-Node** | lila | Formelausdrücke: upper/lower/concat/if_/round/today/regex_match u.v.m. | 2026-06-26 |
| **Datenqualität-Node** | cyan | Validierungsregeln: required, email, PLZ, IBAN, EAN, Regex u.v.m. | 2026-06-26 |
| **AI-Transform-Node** | violett-lila | LLM-Transformation pro Zeile: Prompt-Template mit `{{feldname}}`, Structured Output (Ollama), Batch-Größe, Vorschau | 2026-06-29 |

### Transform-Node Operationen (2026-06-26)
- **Zahlen:** Runden, Tausendertrennzeichen, Min/Max-Clamp, Betrag, Vorzeichen
- **Datum:** Format-Konvertierung, Datumsarithmetik (+/- Tage/Monate/Jahre), Wochentag/Quartal extrahieren
- **String:** Trim, Upper/Lower, Substring, Replace, Regex-Replace, Pad, Split, Länge, Reverse, Enthält-Prüfung
- **Bedingt:** If/Else, Nullwert-Ersatz

### Canvas-Hilfsfunktionen
- **Minimap** – Übersicht über den gesamten Canvas, Klick-Navigation (2026-06-26)
- **Node-Palette Accordion** – gruppierte Node-Auswahl links (Transform / Abfrage & Daten / Berechnung / Logik & Skript) mit Info-Modal (2026-06-26)
- **Nodes per Drag & Drop platzieren** aus der Palette (2026-06-26)
- **Dataset-Node resizable** – Breite und Höhe anpassbar (2026-06-26)
- **Verbindungslinien löschbar** per Klick (2026-04-12)
- **DB-Tabellen-Browser** – linkes Panel Tab "Datasets" | "DB-Tabellen": DB-Verbindungen expandierbar, Tabellen per Drag auf Canvas, erzeugt Dataset automatisch per Import-API (2026-06-29)

### JOIN-System
- INNER JOIN, LEFT JOIN, RIGHT JOIN, FULL OUTER JOIN
- Anti-Join: LEFT ANTI JOIN, RIGHT ANTI JOIN (2026-04-14)
- **Auto-Join-Erkennung** beim Drop eines Datasets auf Canvas (PK/FK-Matching) (2026-06-26)
- PK/FK-Kennzeichnung in Dataset-Nodes (Schlüsselsymbol / FK-Badge) (2026-06-26)
- PK/FK-Schema automatisch aus DB erkennen per Knopf (2026-06-26)
- SQL Filter-Pushdown für DB-Quellen (~25× schneller bei gefilterten Datasets) (2026-06-26)
- JOIN-Engine: **pandas (`pd.merge`)**. Join-Keys werden vor dem Merge typ-angeglichen, sodass Cross-DB-JOINs mit unterschiedlichen Typen matchen (z.B. INT aus MSSQL ↔ String aus CSV, Float aus Excel ↔ INT, CHAR-Padding aus JTL) (2026-07-23). Historie: 2026-04-20 gab es kurzzeitig eine DuckDB-basierte Variante, die beim Modul-Refactor am 2026-06-28 verloren ging; DuckDB wurde am 2026-07-23 entfernt und der Type-Mismatch stattdessen direkt in pandas gelöst.
- **Multi-Pass-Join-Engine** – Join-Reihenfolge-unabhängig: mehrere Durchläufe bis alle Abhängigkeiten aufgelöst (2026-06-29)

### Smart Mapping / KI-Node-Generator
- KI-gestützte Tabellenerkennung per Texteingabe
- Schlägt Datasets und JOINs vor (FK-Traversal bis Tiefe 1, max. 10 Tabellen)
- Fehlende Datasets werden automatisch importiert
- **KI-Node-Generator**: Mapping-Nodes aus natürlichsprachlicher Beschreibung generieren und direkt auf Canvas übernehmen (2026-06-29)
- **Mapping-Fehler-Assistent**: KI erklärt Laufzeitfehler automatisch im Debug-Modus (2026-06-29)

### Filter & Typ-Konvertierung
- Zeilenfilter pro Dataset-Feld (LIKE, =, >, <, BETWEEN, IS NULL, Regex)
- Wildcards `%` und `_` in LIKE korrekt unterstützt
- Cast-Regeln pro Quellfeld (Typ, Datumsformat, Dezimaltrennzeichen, on_error)

---

## Debug-Modus (Mapping Canvas)

### Phase 1 – Debug-Trace (2026-06-26)
- **Debug-Button** in der Toolbar startet einen Testlauf
- **Debug-Trace Panel**: Stage-für-Stage-Ansicht mit Zeilenzahlen und Laufzeit
- Stages: Dataset-Load → Join → Aggregation → Transform → Calc → Python → Ausgabe
- Jede Stage aufklappbar mit Sample-Tabelle (5 Zeilen)
- Fehler-Badge pro Stage, Gesamtfehler im Header

### Phase 2 – Interaktiver Debug + Node Statistics (2026-06-26)
- **Canvas-Glow**: Stage-Karte anklicken → passende Canvas-Nodes leuchten in Stage-Farbe auf
- **Feld-Tooltips**: Im Debug-Modus erscheint beim Hover über ein Dataset-Feld ein Tooltip mit den Sample-Werten
- **Row Inspector**: Zeile in Sample-Tabelle anklicken → Detailansicht aller Felder dieser Zeile
- **Step-Through**: Prev/Next-Pfeile und Breadcrumb-Dots navigieren Stage für Stage
- **"Zeile X verfolgen"**-Badge im Panel-Header mit Clear-Button
- **Node Statistics**: Nach Debug-Run zeigt jeder Node-Typ (Dataset, Transform, Agg, Calc, Python, Expression, DQ) Zeilenanzahl und Fehleranzahl als kleinen Badge

---

## KI-Assistent & KI-Integration

### Architektur
- Ollama Docker Container als LLM-Backend (OpenAI-kompatible API)
- `ai_service.py`, `ai_context_builder.py`, `schema_cache_service.py` im Backend
- Austauschbar: Ollama → Groq / OpenAI / LM Studio per `base_url`-Wechsel
- **Sicherheits-Invariante:** Die KI verändert niemals automatisch etwas — Vorschlag anzeigen → Benutzer bestätigt → dann Aktion

### Globaler KI-Assistent
- Floating Panel auf jeder Seite (Drag & Resize) (2026-06-29)
- **Page-Context**: Assistent kennt aktiven Kontext (Mapping-Canvas, Pipeline, Form Editor)
- **Canvas Awareness**: KI kennt exakt welche Nodes auf dem Canvas sind (Pipeline + Mapping + Form Editor) (2026-07-01)
- **Node-Wissen**: KI kennt die Funktion aller Node-Typen und gibt konkrete Verbesserungsvorschläge (2026-07-01)
- **Parameter-Workflow-Wissen**: KI erklärt wie Parameter (Variablen) aus Formularen in Mappings genutzt werden (2026-07-01)
- **Active-Node-Kontext**: aktuell ausgewählter Node wird automatisch als Kontext übergeben
- **Schnellaktionen-Buttons** je nach Kontext (z. B. "SQL erklären", "Fehler erklären") (2026-06-29)
- **Schema-Wissensdatenbank** (🗄): KI nutzt beschriebene Tabellen/Spalten aus dem Datenkatalog (2026-06-29)
- **KI-Modi** wählbar:
  - ⚡ Schnell – kleinstes verfügbares Modell
  - ⚖ Auto – modellgrößenabhängig (überschreitet nie konfigurierte Größe)
  - 🧠 Analyse – größtes verfügbares Modell
- **Expertenmodus (⚙)**: System-Prompt sichtbar + bearbeitbar (2026-06-29)
- **Token-Zähler** und **Abbrechen-Funktion** während Streaming (2026-06-29)
- **Sekunden-Timer** (Elapsed Time) während des Streamings (2026-06-29)
- **Frage-Wiederholen** (↩): letzte Anfrage erneut senden (2026-06-29)
- Antwort per SSE gestreamt, Markdown-Rendering

### Modell-Katalog & -Verwaltung
- Modell-Bibliothek mit Sprach-Badges und Suchfeld (2026-06-29)
- Modell-Katalog umfassend: llama4, mistral-small, gemma3n, deepseek-r1, Qwen3.5, qwen2.5-coder, phi4-mini u.v.m. (2026-06-29)
- Model-Capability-Registry: top_p, Auto-Modus Parameter, Modellgröße-Limits (2026-06-29)
- Pull-Modell direkt aus dem Frontend (SSE-Stream mit Fortschritt)
- Aktives Modell in der Sidebar und AiStreamModal sichtbar

### KI-Funktionen im Mapping Editor
| Ort | Funktion | Seit |
|---|---|---|
| SQL-Node | SQL erklären + generieren | 2026-06-29 |
| Python-Node | Python-Code generieren + Fehler erklären | 2026-06-29 |
| Expression-Node | Ausdruck vorschlagen | 2026-06-29 |
| AI-Transform-Node | LLM-Transformation pro Zeile mit Structured Output | 2026-06-29 |
| KI-Node-Generator | Nodes aus Beschreibung generieren | 2026-06-29 |
| Mapping-Fehler-Assistent | KI erklärt Laufzeitfehler im Debug-Panel | 2026-06-29 |

### KI-Dataset-Assistent (AiDatasetWizard)
- 3-Schritt-Flow: Beschreibung → Tabellenauswahl → SQL-Generierung
- Preview-Modal pro Tabelle (Spalten, Typen, PK/FK)
- SQL-Vorschlagskarten, alle deaktiviert per Default
- FK-Traversal bis Tiefe 1, max. 10 Tabellen

### Schema-Wissensdatenbank / Datenkatalog
- Tabellen, Spalten und Relationen beschreiben (freitext)
- KI schlägt Beschreibungen vor
- Export / Import (JSON)
- Wird als Kontext in alle KI-Anfragen eingebettet

### Form Builder KI
- **KI-Feldvorschlag** (AiFieldSuggest): Felder automatisch aus Beschreibung vorschlagen (2026-06-29)
- Vorschläge immer deaktiviert – Benutzer wählt aktiv aus

---

## Datasets

- Import von CSV, Excel (xlsx/xls), ODS, Access (.mdb/.accdb), Parquet, JSON
- Import aus Datenbankverbindungen (SQL-Abfrage frei definierbar)
- Import aus FTP/SFTP (CSV, Excel)
- Statische Datasets (manuell bearbeitbare Tabelle)
- SQLite-Datasets (lokale DB, SQL-Editor)
- **Auto-Refresh**: Zeitgesteuerte Neuabfrage aus DB-Quellen (Cron-Syntax)
- PK/FK-Badge in der Datasets-Ansicht (Spaltenköpfe + Schema-Editor) (2026-06-26)
- Dataset-Vorschau im Explorer (erste 50 Zeilen)
- Dataset als Mapping-Ziel speichern (save_as_dataset)

---

## DB-Verbindungen & Analyzer

### DB-Verbindungen
- Microsoft SQL Server (pyodbc), PostgreSQL, MySQL, SQLite
- Passwort-Verschlüsselung (Fernet)
- Test-Button pro Verbindung
- SQL Editor Modal: freie Abfragen mit Tabellen-Browser und Schema-Prüfung (2026-04-19)

### Database Analyzer (2026-04-09 – 2026-04-19)
- Interaktives ER-Diagramm aller Tabellen einer DB-Verbindung
- Schema-Filter, Tabellenfilter, Whitelist-Modus
- Views in Analyse und Dropdown einbinden
- JTL-Namenskonvention-Beziehungserkennung (tPrefix + PK/FK-Konvention)
- Inferred Relationships (auch ohne explizite FK-Constraints)
- **Pfadfinder**: kürzester Weg zwischen zwei Tabellen mit Zwischenstationen (Segment-BFS)
- Starttabelle und Traversierungstiefe konfigurierbar
- Dataset-Import direkt aus dem ER-Diagramm
- PNG-Export des Diagramms
- Toggle-Legende, Node-Header mit Schema-Anzeige

---

## Pipelines

- Visuelle Pipeline mit Trigger-Node, Mapping-Nodes und Verbindungslinien
- Scheduling (Cron) mit Start-/Enddatum
- Manueller Start / Stopp
- Nächster-Lauf-Anzeige
- Letzter-Lauf-Status (Erfolg, Warnung, Fehler) im Dashboard
- Verbindungslinien löschbar (2026-04-12)
- Projektspalte im System-Log (2026-04-15)
- **PageContext.actions**: Pipeline-Kontext mit Schnellaktionen im KI-Assistenten (2026-06-29)

### Pipeline Nodes
| Node | Funktion | Seit |
|---|---|---|
| **Trigger** | Zeitplan (Cron), manueller Start | v1.0 |
| **FTP-Import** | Dateien von FTP/SFTP holen | v1.0 |
| **REST Fetch** | REST API abrufen, Ergebnis als Dataset | v1.0 |
| **Mapping** | Mapping ausführen (alle konfigurierten Ziele) | v1.0 |
| **Verzweigung** | Bedingungen & Routing | v1.0 |
| **Bedingung** | Wenn/Dann Verzweigung | v1.0 |
| **FTP Upload** | Datei auf FTP/SFTP hochladen | v1.0 |
| **E-Mail** | E-Mail mit optionalem Anhang senden | v1.0 |
| **Business Insights** | Umsatz, Trends & Anomalien analysieren (pandas, kein LLM für Berechnungen) | 2026-06-29 |

---

## Export & Mapping-Ziele

- Mapping-Ergebnis als CSV, Excel, JSON herunterladen
- Export wird unter **Exporte** gespeichert (kein direkter Browser-Download)
- XML-Ziel: Template-basierter XML-Export (INSTAT, eigene Formate)
- **DB-Schreiben als Ziel** (2026-07-01):
  - Verbindung + Tabelle (inkl. Schema-Prefix wie `Amazon.vFBABestand`) + Schreibmodus
  - Modi: Insert, Truncate+Insert, Update, Upsert
  - Schlüsselspalten für Update/Upsert
  - **Safety-Check-Wizard**: Verbindung, Schreibrechte, Tabelle/View-Erkennung, Key-Spalten-Validierung
  - Bestätigungs-Checkbox bevor Daten geschrieben werden
  - Feldauswahl aus Tabellenschema (FieldPicker)

---

## Dashboard & UI

- Tab-Navigation: Projekte → DB-Connectors → Datasets → FTP/SFTP → REST API → Templates → Mappings → Pipelines → Formulare → Exporte → Monitoring → Plugins (2026-07-01)
- Visuelle Trennlinien nach Projekte, Templates, Exporte (2026-07-01)
- Standard-Tab: Projekte (2026-07-01)
- **Light/Dark/System Theme** – Umschalter in Einstellungen → Optik, kein Flash beim Laden (2026-07-01)

---

## Onboarding

- **Getting-Started-Widget** 🚀 in der Sidebar — öffnet/schließt sich jederzeit (2026-06-29)
- 4 Schritte mit Live-Check: Verbindung, Dataset, Mapping, Pipeline
- Auto-öffnet sich beim ersten Login
- Empty States für Datasets- und Mappings-Tab

---

## Plugin-System

### Tier-1 Plugins (Python, eingebettet)
- Registrierung über `manifest.json` + `connector.py`
- Capability Registry: Plugins melden Datenquellen, Ziele, Events
- Dataset-Wizard erkennt Plugin-Quellen automatisch (2026-06-25)

### Tier-2 Plugins (Docker Container)
- Plugin Manager Service orchestriert externe Container
- REST-API-Kommunikation zwischen Core und Plugin
- Test-Button für Tier-2 Plugin-Karten (2026-06-25)
- Plugins können eigene Events feuern via EventBus (2026-06-25)
- Beispiel: Faker Datengenerator Plugin (2026-06-25)

### EventBus
- Redis Pub/Sub zwischen Backend und Plugins
- Event-History (letzte N Events pro Kanal) (2026-06-25)

### Verfügbare Plugins
| Plugin | Typ | Funktion | Seit |
|---|---|---|---|
| **Mail/IMAP Connector** | Tier-1 | E-Mails aus IMAP-Postfach als Dataset lesen | 2026-06-25 |
| **HTML-Reader** | Tier-1 | Tabellen aus HTML-Dokumenten extrahieren | 2026-06-25 |
| **Visual Selektor** | Tier-1 | CSS-Selektor interaktiv auf HTML-Quelle anwenden | 2026-06-25 |
| **eSTATISTIK.core** | Tier-1 | Mapping-Ziel für Statistisches Bundesamt eSTATISTIK-Format | 2026-06-25 |
| **Faker Generator** | Tier-2 | Synthetische Testdaten generieren | 2026-06-25 |

---

## Monitoring & Admin

- Dashboard mit Übersicht aller Projekte, aktiver Pipelines, Fehler heute, Läufe heute
- System-Tab: CPU, RAM, Speicher, SQLite-Größe, Uptime (2026-04-09)
- **Docker-Container-Übersicht** im System-Tab: Status, Image, Ports aller Container im Datenmonster-Netzwerk (2026-06-29)
- System-Log: alle Pipeline-Ereignisse mit Projekt-Spalte, filterbar nach Status/Projekt
- Fehler & Warnungen Widget auf dem Dashboard

### Benutzerverwaltung
- Mehrere Benutzer, Admin-Flag
- User-Management im Admin-Dashboard (2026-06-15)
- Passwort ändern (eigenes Profil)
- Zufälliges Admin-Passwort beim Erststart (kein Default) (2026-06-15)

### Projekte
- Projekte als Organisationsebene über allen Ressourcen
- Datasets, Mappings, Pipelines einem Projekt zuordnen
- Viewer-Rolle: nur Lesen, kein Speichern

---

## Sicherheit (2026-06-15)

- Rate-Limiting auf allen API-Endpunkten
- Path-Traversal-Schutz bei Access-Endpunkten
- Offene Registrierung geschlossen (nur Admin kann User anlegen)
- JWT-Authentifizierung (Bearer Token)
- Passwort-Hashing (bcrypt)
- Credential-Verschlüsselung für DB-Passwörter (Fernet/AES)
- Security-Headers (X-Frame-Options, CSP, XSS-Protection, HSTS)

---

## Deployment & Betrieb

- Docker Compose Setup (Backend, Frontend, Plugin Manager, Redis)
- `install.sh` für Linux-Server (interaktiv + `--yes` für non-interactive) (2026-04-20)
- `install.ps1` für Windows
- Update-Button im Frontend lädt neue Version von datenmonster.com (2026-04-21)
- CI/CD via GitHub Actions: ZIP-Build, Deploy auf Hetzner per SCP

---

## Tech Stack

| Schicht | Technologie |
|---|---|
| Backend | FastAPI (Python), SQLite, pandas, Fernet |
| Frontend | React, Vite, react-router, Lucide Icons |
| Daten-Engine | pandas (JOINs via `pd.merge`) |
| KI / LLM | Ollama (OpenAI-kompatibel), SSE-Streaming |
| Queue/Events | Redis (Pub/Sub) |
| Auth | JWT (python-jose), bcrypt |
| Deployment | Docker, Docker Compose, Nginx |
