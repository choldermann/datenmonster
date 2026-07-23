# Datenbanken bei Datenmonster – Übersicht

Stand: 2026-07-23

Datenmonster hat es mit mehreren „Datenbanken" zu tun, die aber **völlig unterschiedliche Rollen** spielen. Wichtig ist die Trennung zwischen der **eigenen Anwendungsdatenbank** (wo Datenmonster seine Einstellungen, Mappings, Nutzer etc. speichert) und den **externen Datenbanken der Kunden** (die als Datenquelle angezapft oder als Ziel beschrieben werden).

---

## Auf einen Blick

| DB / Dienst | Rolle | Pflicht? | Wo konfiguriert |
|-------------|-------|----------|-----------------|
| **SQLite** | Interne Anwendungs-/Metadaten-DB | ✅ immer | `DATABASE_URL` (Default) |
| **PostgreSQL** | *Externe* Quell- **oder** Ziel-DB (eine von 3 Optionen) | optional | pro DB-Verbindung im UI |
| **MySQL / MariaDB** | *Externe* Quell- oder Ziel-DB | optional | pro DB-Verbindung im UI |
| **MSSQL (SQL Server)** | *Externe* Quell- oder Ziel-DB (typisch für JTL) | optional | pro DB-Verbindung im UI |
| **Redis** | Pub/Sub-EventBus (keine klassische DB) | ✅ im Compose-Stack | `REDIS_URL` |

> **Kurzfassung deiner Ausgangsfrage:** SQLite ist die eine interne DB. PostgreSQL ist *nicht* die interne DB, sondern nur eine von mehreren externen Verbindungsarten. DuckDB war zeitweise als Dependency vorhanden, wurde aber am 2026-07-23 entfernt (siehe unten) – die Daten-Engine ist pandas.

---

## 1. SQLite – die interne Anwendungsdatenbank

**Das ist die „Datenbank von Datenmonster selbst".** Hier legt die Plattform ihren gesamten eigenen Zustand ab.

- **Konfiguration:** `DATABASE_URL` (`backend/app/core/config.py`)
  - Default lokal: `sqlite:///./datenmonster.db`
  - Im Docker-Stack: `sqlite:///./uploads/datenmonster.db` → liegt im Volume `datenmonster-data`, damit sie Updates übersteht.
- **Zugriff:** SQLAlchemy ORM (`backend/app/core/database.py`)
- **Besonderheit:** Wegen des Single-File-Charakters von SQLite gibt es eine Retry-Logik (`db_retry`, `safe_commit`) gegen `database is locked`-Fehler bei parallelen Schreibzugriffen.

### Was liegt in der SQLite-DB?

Alle Tabellen der Anwendung, u. a.:

| Bereich | Tabellen |
|---------|----------|
| Nutzer & Rechte | `users`, `projects`, `project_members` |
| Datenquellen | `datasets`, `db_connections` (⚠️ Zugangsdaten **verschlüsselt**, Fernet), `rest_sources`, `ftp_sources` |
| Transformation | `mappings`, `pipelines`, `templates` |
| Formulare | `forms`, `form_submissions` |
| Schema-Cache (externe DBs) | `schema_table_meta`, `schema_column_meta`, `schema_relation_meta` |
| Automatisierung | `scheduled_jobs`, `job_runs`, `dispatcher_rules` |
| KI-Gedächtnis | `ai_memory_knowledge`, `ai_memory_solutions`, `ai_memory_corrections`, `ai_prompt_cache` |
| Betrieb | `system_logs`, `event_log`, `system_settings`, `plugins`, `export_files`, `reports` |

> **Wichtig:** In `db_connections` stehen die Zugangsdaten zu den externen Kunden-Datenbanken – die Passwörter werden mit einem aus `SECRET_KEY` abgeleiteten Fernet-Key verschlüsselt gespeichert, nicht im Klartext.

### Kann man SQLite gegen PostgreSQL tauschen?

Technisch ja: Der Zugriff läuft komplett über SQLAlchemy und ist DB-agnostisch. Man müsste nur `DATABASE_URL` auf `postgresql+psycopg2://…` setzen. Aktuell ist das aber **nicht der ausgelieferte Betriebsmodus** – der Stack fährt bewusst mit SQLite (einfacher, wartungsarm, keine extra Container). Die Retry-Logik ist SQLite-spezifisch.

---

## 2. PostgreSQL / MySQL / MSSQL – externe Quell- und Ziel-Datenbanken

Das sind **die Datenbanken der Kunden**, nicht die von Datenmonster. Sie tauchen an zwei Stellen auf:

### a) Als Datenquelle (lesen)
Ein Dataset mit `file_type` `db_postgresql`, `db_mysql` oder `db_mssql` verweist auf eine `db_connection` + ein SQL-Statement. Der passende Connector wird in `backend/app/connectors/factory.py` gebaut.

### b) Als Schreibziel (schreiben)
Der **db_write-Node** einer Pipeline schreibt Ergebnisse zurück in eine dieser DBs. Tabellen/Spalten werden vorher über die `db-write`-API inspiziert (`backend/app/api/db_write.py`).

### Unterstützte Treiber
Definiert in `db_service.get_engine_str()` und `connectors/factory.py`:

| Typ | SQLAlchemy-Treiber | Python-Paket |
|-----|--------------------|--------------|
| PostgreSQL | `postgresql+psycopg2` | `psycopg2-binary` |
| MySQL / MariaDB | `mysql+pymysql` | `pymysql` |
| MSSQL (SQL Server) | `mssql+pyodbc` (ODBC Driver 18) | `pyodbc` |

> **PostgreSQL ist hier also eine gleichrangige Option unter mehreren** – nicht die „Haupt-DB". Für JTL-Umgebungen ist meist MSSQL oder MySQL relevant.

### Schema-Cache
Damit das UI die Tabellen/Spalten externer DBs schnell anzeigen kann, ohne jedes Mal live abzufragen, spiegelt der `schema_cache_service` deren Struktur in die **SQLite**-Tabellen `schema_*_meta`. Der Cache liegt also intern, die Wahrheit in der externen DB.

---

## 3. DuckDB – entfernt (2026-07-23)

DuckDB war zeitweise als Dependency (`duckdb>=1.0.0`) und in der Doku als „JOIN-Engine" geführt. Historie:

- **2026-04-20:** DuckDB wurde als Join-Engine eingebaut (`CAST … AS VARCHAR` gegen Type-Mismatch bei Cross-DB-Joins, mit pandas-Fallback).
- **2026-06-28:** Beim Refactor (Aufteilen von `mapping_service.py`) ging die DuckDB-Variante unbemerkt verloren – die Joins liefen seitdem wieder über reines pandas.
- **2026-07-23:** DuckDB komplett entfernt (aus `requirements.txt` und allen Doku-/Kommentar-Verweisen), da im Code ungenutzt. Das ursprüngliche Ziel – Type-Mismatch bei Cross-DB-Joins – wird stattdessen **direkt in pandas** gelöst (siehe unten).

**Fazit:** Es gibt keine DuckDB-Abhängigkeit mehr. Die Daten-Engine ist pandas.

### Type-Mismatch bei Joins (der eigentliche Punkt)

`pd.merge` matcht nur bei gleichem Datentyp der Join-Keys. `mapping_utils._apply_join` gleicht die Keys daher vor dem Merge an (`_prep_join_keys`):

- Sind **beide Seiten überwiegend numerisch** parsebar → numerischer Vergleich (deckt `INT ↔ Float ↔ String-Zahl` ab, z.B. `10` ↔ `10.0` ↔ `"10"`).
- Sonst → Vergleich als **getrimmte Strings** (löst u.a. das CHAR-Padding von JTL: `"ABC  "` ↔ `"ABC"`).

Die Original-Keyspalten bleiben unverändert im Ergebnis; der Abgleich läuft über temporäre Hilfsspalten. NULL-Keys werden bewusst **nicht** verändert (bestehendes pandas-Verhalten).

---

## 4. Redis – EventBus (keine klassische Datenbank)

- Container `redis:7-alpine` im Compose-Stack, `REDIS_URL=redis://redis:6379`.
- Genutzt als **Pub/Sub-EventBus** (`backend/app/services/eventbus.py`) für die Kommunikation zwischen Backend und Plugin-Manager sowie interne Events.
- Speichert **keine** dauerhaften Anwendungsdaten – fällt Redis weg, wird der EventBus-Listener nur deaktiviert (die App läuft weiter).

---

## Merksatz

> **Eine** interne DB (SQLite) verwaltet Datenmonster selbst.
> **Beliebig viele** externe DBs (PostgreSQL / MySQL / MSSQL) werden pro Kundenverbindung angezapft oder beschrieben.
> **Redis** ist Nachrichtenbus, keine Ablage für Anwendungsdaten. **DuckDB** wird nicht mehr verwendet.

Das grafische Schema dazu: [`datenbank-schema.drawio`](./datenbank-schema.drawio) (in [draw.io / diagrams.net](https://app.diagrams.net) öffnen).
