<p align="center">
  <img src="frontend/public/datenmonster.svg" width="100" height="100" alt="Datenmonster Logo" />
</p>

<h1 align="center">Datenmonster</h1>

<p align="center">
  <strong>Self-hosted ETL & data integration platform by <a href="https://holdermann.me">Holdermann IT</a></strong>
</p>

<p align="center">
  <em>Connect, transform and automate your data pipelines – without cloud dependency.</em>
</p>

![License](https://img.shields.io/badge/license-MIT-green)
![Docker](https://img.shields.io/badge/docker-ready-blue)
![Python](https://img.shields.io/badge/python-3.11-blue)
![React](https://img.shields.io/badge/react-18-61dafb)

<p align="center">
  <a href="https://monstersuite.de/produkt/datenmonster/">Website</a> ·
  <a href="https://datenmonster.monstersuite.de/download">Installation</a> ·
  <a href="https://datenmonster.monstersuite.de/docs">Dokumentation</a> ·
  <a href="https://monstersuite.de/jtl-wawi/">Module für JTL-Wawi</a>
</p>

---

## 🧾 Für JTL-Wawi

Datenmonster liest direkt aus der JTL-Datenbank. Fertige Module bringen Abfragen, Formulare und
Dashboards mit – installieren, Datenbankverbindung wählen, fertig. Die Regeln dahinter (Stornos,
Rohertrag, Lagerwert zum Stichtag, Vaterartikel) sind an echten Wawi-Datenbanken geprüft.

- **Cockpits** für [Geschäftsführung](https://monstersuite.de/jtl-wawi/geschaeftsfuehrer-cockpit/),
  [Vertrieb](https://monstersuite.de/jtl-wawi/vertriebs-cockpit/),
  [Einkauf](https://monstersuite.de/jtl-wawi/einkaufs-cockpit/),
  [Lager](https://monstersuite.de/jtl-wawi/lager-cockpit/) und
  [Versand](https://monstersuite.de/jtl-wawi/versand-cockpit/), dazu der
  [Unternehmensmonitor](https://monstersuite.de/jtl-wawi/unternehmensmonitor/)
- **[E-Rechnungen empfangen](https://monstersuite.de/jtl-wawi/e-rechnung-empfangen/)** – ZUGFeRD, XRechnung und PDF einlesen, gegen die Bestellung abgleichen, in die Wawi schreiben
- **[DATEV-Export](https://monstersuite.de/jtl-wawi/datev-export/)** – EXTF-Buchungsstapel, auch für Eingangsrechnungen
- **[Intrastat](https://monstersuite.de/jtl-wawi/intrastat/)** und **[Stammdaten-Health-Check](https://monstersuite.de/jtl-wawi/stammdaten-health-check/)**
- **[Markt und Umfeld](https://monstersuite.de/jtl-wawi/markt-und-umfeld/)** – eigene Zahlen neben Branche, Preisen und Konjunktur
- **[Wissen](https://monstersuite.de/jtl-wawi/wissen/)** – Fallen in der JTL-Datenbank, mit SQL-Beispielen

Die Module werden über [MonsterSuite](https://monstersuite.de/jtl-wawi/) erworben; Datenmonster selbst installierst du kostenlos.

---

## ✨ Features

### Datasets
- File upload: CSV, XLSX, XML, ODS, MS Access
- SQL import from MSSQL / MySQL databases
- FTP / SFTP sync with wildcard filter (`*.csv`, `export_*.xlsx`)
- Manual dataset creation with column definitions
- Primary key + autoincrement support
- Dataset Explorer with pagination, search and inline type editor

### Mapping Editor
- Visual node-based ETL pipeline builder
- Source nodes: Datasets, SQL, REST API, Constants, Formulas, Aggregations, Lookups, Switch
- Join support (INNER, LEFT, RIGHT, FULL)
- Write modes: Replace, Append, Upsert (Primary Key matching)
- Export targets: CSV, XLSX, JSON, XML, MSSQL, MySQL, Dataset

### Pipelines
- Scheduled execution via Cron expressions
- Multi-step pipelines with conditions and branching
- APScheduler-based background execution

### Monitoring
- Live dashboard: KPIs, pipeline status, error log
- System log with stacktrace viewer
- Auto-refresh every 30 seconds

### Forms, Cockpits & AI
- Forms with tabs, filters and drill-down down to the single document – usable without SQL, optionally via a customer portal
- Multi-tenant: several databases, one switch for all cockpits
- Scheduled checks with e-mail alerts
- AI assistant for SQL, mappings and summaries – with a local model on your own server or Datenmonster AI

### Reporting
- Drag-and-drop report canvas
- Widget types: KPI, Bar, Line, Pie/Donut, Table, Heatmap/Calendar
- Dynamic filters and comparison periods
- PDF export and email delivery

---

## 🚀 Quick Start

Voraussetzungen: Docker Engine 20.10+ mit Docker Compose v2, ca. 1 GB freier RAM und 2 GB Speicherplatz.

### Option 1 – Installer (recommended)

Das Skript prüft die Voraussetzungen, installiert Docker bei Bedarf, legt die Konfiguration
(inkl. `SECRET_KEY`) an und startet Datenmonster.

**Linux / macOS / Windows mit WSL2:**
```bash
curl -fsSL https://raw.githubusercontent.com/choldermann/datenmonster/main/install.sh | bash
```

**Windows (PowerShell as Administrator):**
```powershell
irm https://raw.githubusercontent.com/choldermann/datenmonster/main/install.ps1 | iex
```

### Option 2 – Manual

> [!WARNING]
> **Pflicht vor dem ersten Start:** Konfiguriere `.env` mit einem sicheren `SECRET_KEY`.
> Ohne diesen Schritt startet der Container nicht. Die `.env`-Datei enthält Passwörter und
> darf **niemals** ins Repository committed werden (sie steht in `.gitignore`).

```bash
git clone https://github.com/choldermann/datenmonster.git
cd datenmonster

# 1. Konfiguration anlegen und SECRET_KEY setzen (Pflicht!)
cp .env.example .env
echo "SECRET_KEY=$(openssl rand -hex 32)" >> .env
# Optional: ADMIN_PASSWORD in .env setzen, sonst wird ein Zufallspasswort
# beim ersten Start generiert und einmalig in den Container-Logs angezeigt.

# 2. Starten
docker compose up --build -d
```

Then open: **http://localhost:5174**

Default login: `admin` / *(Passwort aus `.env` oder beim ersten Start aus den Container-Logs)*

---

## 🛠 Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, SQLAlchemy, APScheduler |
| Database | SQLite |
| Frontend | React 18, Vite, Tailwind CSS |
| Infrastructure | Docker Compose |

---

## 📁 Project Structure

```
datenmonster/
├── docker-compose.yml
├── .env.example
├── install.sh              # Linux/macOS installer
├── install.ps1             # Windows installer
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py
│       ├── core/           # config, database, security
│       ├── models/         # SQLAlchemy models
│       ├── api/            # FastAPI routers
│       ├── services/       # Business logic
│       └── connectors/     # Data source connectors
└── frontend/
    ├── Dockerfile
    └── src/
        ├── pages/          # Dashboard, MappingEditor, Login
        ├── components/     # UI components
        └── api/            # Axios client
```

---

## 🔧 Development (without Docker)

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

API Docs: http://localhost:8000/docs

---

## 📄 License

MIT License – see [LICENSE](LICENSE) for details.

---

## 🌐 Links

- Website: [monstersuite.de/produkt/datenmonster](https://monstersuite.de/produkt/datenmonster/)
- Module für JTL-Wawi: [monstersuite.de/jtl-wawi](https://monstersuite.de/jtl-wawi/)
- Installation & Dokumentation: [datenmonster.monstersuite.de](https://datenmonster.monstersuite.de/download)
- Kontakt: [datenmonster.monstersuite.de/kontakt](https://datenmonster.monstersuite.de/kontakt)
- Holdermann IT: [holdermann.me](https://holdermann.me)
