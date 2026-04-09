# Datenmonster – Bugfix & Feature Session (zwischen Part 10 und Part 11)

---

## Was in dieser Session umgesetzt wurde

### 1. Bugfix: Doppelte Spaltennamen bei SQL JOINs

**`backend/app/services/db_service.py`**

- `SELECT *` mit mehreren JOINs erzeugte doppelte Spaltennamen → `DataFrame` hatte mehrere Spalten gleichen Namens → `infer_column_types` crashte mit `'DataFrame' object has no attribute 'dtype'`
- Fix: neue Hilfsfunktion `_dedup_columns()` benennt Duplikate automatisch um: `kEingangsrechnung` → `kEingangsrechnung`, `kEingangsrechnung_1`
- Betrifft: `query_full()`, `query_full_with_types()`, `query_preview()`

### 2. Bugfix: Gleiche Feldnamen aus mehreren Datasets im Mapping

**`backend/app/services/mapping_service.py`**

- Wenn zwei Datasets identische Feldnamen hatten (z.B. beide `Betrag` und `Gegenkonto`), wurde beim Auflösen immer der Wert des ersten Datasets genommen
- Root cause: `flat_no_prefix` speichert kurzen Namen beim ersten Treffer (`if short not in flat_no_prefix`). `_apply_transformer` suchte nach kurzem Namen und traf immer den ersten
- Fix: `_apply_transformer` bekommt `dataset_names` dict; `_resolve_field` sucht **zuerst** nach dem vollen Prefix-Key `DatasetName.Feldname` wenn `source_dataset_id` bekannt ist
- Gilt für beliebig viele gejoinede Datasets

### 3. Bugfix: ODS-Datasets im Mapping Editor nicht ladbar

**`backend/app/connectors/factory.py`**

- Fehlermeldung: `Kein Connector für file_type='ods' verfügbar`
- Fix: `"ods"` und `"static"` zur Liste der dateibasierten Connectors hinzugefügt

### 4. Bugfix: Kopieren-Button im DataExplorer (Firefox)

**`frontend/src/components/dashboard/panels/DatasetsPanel.jsx`**

- Firefox blockiert `execCommand('copy')` und `navigator.clipboard` außerhalb direkter User-Aktivierung
- Fix: `<pre>` durch `<textarea readonly>` ersetzt – Text ist direkt selektierbar
- Klick auf Textarea → Text wird automatisch komplett selektiert
- Kopieren-Button versucht `clipboard.writeText()`, bei Fehler wird Text selektiert + Hinweis "Strg+C drücken" angezeigt

### 5. Bugfix: Falsche Typ-Erkennung bei Belegnummern

**`backend/app/services/file_service.py`** – `infer_column_types()`

- Belegnummern wie `0010001378254` wurden als `integer` klassifiziert (führende Null ignoriert)
- Alphanumerische Felder wie `26301756-RI` wurden teilweise falsch erkannt
- Fix: Vorprüfung vor dem Zahlen-Test:
  - Strings mit führenden Nullen (`^0\d+$`) → immer `string`
  - Strings mit Buchstaben/Bindestrichen (`[a-zA-Z\-/\\]`) → immer `string`

### 6. Feature: Typ-Konvertierung mit Bestätigungs-Modal

**`backend/app/api/datasets.py`** – neuer Endpoint `POST /api/datasets/{id}/convert_column`

- Konvertiert tatsächliche Feldwerte in der JSON-Datei
- `decimal → integer`: rundet (`1.7` → `2`)
- `* → string`: String-Darstellung
- `* → boolean`: `true/1/ja/yes` → `true`
- `* → date`: erkennt gängige Formate
- Nicht konvertierbare Werte → `null`
- Gibt `{converted, failed}` zurück
- Log-Level: `success` (0 Fehler) / `warning` (teilweise) / `error` (alles fehlgeschlagen)

**`frontend/src/components/dashboard/panels/DatasetsPanel.jsx`** – `TypeBadgeEditor`

- Klick auf Typ-Badge öffnet Bestätigungs-Modal mit 3 Optionen:
  - **Abbrechen** – nichts ändern
  - **Nur Label ändern** – wie bisher, Daten unverändert
  - **Daten konvertieren** – tatsächliche Werte werden umgeschrieben
- Nach Konvertierung: DataExplorer lädt Seite automatisch neu
- Gleiches Modal im `EditDatasetModal` Tab "Spalten & Schlüssel" beim Speichern

### 7. Feature: SQL Dataset Auto-Refresh mit Zeitplan

**`backend/app/models/dataset.py`**

Neue Felder:
- `cron_expr` – Cron-Ausdruck für automatisches Requery
- `auto_refresh` – 0/1
- `last_refresh_at` – Zeitpunkt der letzten automatischen Aktualisierung
- `last_refresh_status` – `success` | `error`
- `last_refresh_msg` – Meldung der letzten Aktualisierung

**`backend/app/services/scheduler_service.py`**

Neue Funktionen:
- `_run_dataset_requery(dataset_id)` – führt Requery aus, loggt via `db_logger`
- `register_dataset_job(dataset_id, cron_expr)` – registriert Job im APScheduler
- `unregister_dataset_job(dataset_id)` – entfernt Job
- `reload_all_dataset_jobs()` – lädt alle aktiven Jobs beim Start

**`backend/app/api/datasets.py`**

- `PATCH /{id}` akzeptiert jetzt `cron_expr` und `auto_refresh`
- Registriert/entfernt Scheduler-Job automatisch beim Speichern
- `dataset_out()` liefert neue Felder

**`backend/app/main.py`**

- DB-Migration für neue Felder automatisch beim Start
- `reload_all_dataset_jobs()` beim App-Start aufgerufen

**`frontend/src/components/dashboard/panels/DatasetsPanel.jsx`**

- `EditDatasetModal` bekommt Tab **⏰ Zeitplan** – nur bei DB-Datasets sichtbar
- Cron-Presets: Alle 5 Min, Alle 15 Min, Stündlich, Täglich 06:00, Täglich 22:00, Wöchentlich Mo
- Checkbox "Automatisch aktualisieren"
- Zeigt letzten Refresh-Status (✓/✗ mit Zeitstempel und Meldung)
- **⏰ AUTO** Badge auf Dataset-Kachel (grün = ok, rot = Fehler) mit Tooltip

**`frontend/src/pages/Dashboard.jsx`**

- Pencil-Button öffnet jetzt für **alle** Dataset-Typen das `EditDatasetModal` (nicht mehr `NewDatasetWizard` für DB-Datasets)

### 8. Fix: SQL Dataset Spalten read-only

**`frontend/src/components/dashboard/panels/DatasetsPanel.jsx`**

- Tab "Spalten & Schlüssel" bei SQL-Datasets zeigt jetzt einen Info-Banner und read-only Spaltenliste
- Keine editierbaren Dropdowns oder 🔑-Buttons für DB-Datasets
- Hintergrund: Typen werden beim Requery sowieso neu inferiert

---

## Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `backend/app/services/db_service.py` | `_dedup_columns()`, JOIN-Dedup in query-Funktionen |
| `backend/app/services/mapping_service.py` | `_resolve_field` mit dataset_names-Priorität |
| `backend/app/connectors/factory.py` | ODS + Static Connector |
| `backend/app/services/file_service.py` | Führende Nullen + Alphanumerisch → string |
| `backend/app/api/datasets.py` | `convert_column` Endpoint, `PATCH` mit cron_expr |
| `backend/app/models/dataset.py` | 5 neue Felder für Auto-Refresh |
| `backend/app/services/scheduler_service.py` | Dataset-Requery Job-Funktionen |
| `backend/app/main.py` | DB-Migration + reload_all_dataset_jobs |
| `frontend/.../DatasetsPanel.jsx` | Kopieren-Fix, Typ-Konvertierung Modal, Auto-Refresh UI, read-only SQL-Spalten |
| `frontend/src/pages/Dashboard.jsx` | Immer EditDatasetModal beim Bearbeiten |

---

## Deployment-Cheatsheet

```bash
# Backend
docker cp db_service.py datenmonster-backend:/app/app/services/db_service.py
docker cp mapping_service.py datenmonster-backend:/app/app/services/mapping_service.py
docker cp factory.py datenmonster-backend:/app/app/connectors/factory.py
docker cp file_service.py datenmonster-backend:/app/app/services/file_service.py
docker cp datasets.py datenmonster-backend:/app/app/api/datasets.py
docker cp dataset.py datenmonster-backend:/app/app/models/dataset.py
docker cp scheduler_service.py datenmonster-backend:/app/app/services/scheduler_service.py
docker cp main.py datenmonster-backend:/app/app/main.py
docker compose restart backend

# Frontend
cp DatasetsPanel.jsx ~/Nextcloud/Documents/Datenmonster/frontend/src/components/dashboard/panels/DatasetsPanel.jsx
cp Dashboard.jsx ~/Nextcloud/Documents/Datenmonster/frontend/src/pages/Dashboard.jsx
```

---

## Nächste Session – Part 11: Database Analyzer

### Ziel
Interaktiver Schema-Explorer für Datenbankverbindungen mit ER-Diagramm.

### Stufe 1 – Backend
- Neuer Endpoint `GET /api/connections/{id}/analyze`
- Alle Tabellen + Spalten + Typen + PKs + Foreign Keys laden
- Implizite Beziehungen erkennen (gleicher Feldname + kompatibler Typ)
- Tabellenstatistiken (Zeilenanzahl)

### Stufe 2 – Frontend
- Neuer Tab im Verbindungs-Panel: "Schema Analyzer"
- Interaktives ER-Diagramm (Nodes = Tabellen, Kanten = Beziehungen)
- Farbcodierung: gesicherte FK vs. vermutete Beziehung
- Zoom + Pan
- Klick auf Tabelle → Felder + Typen + PKs

### Stufe 3 – Extras
- Export als PNG
- "In Mapping verwenden" Button
