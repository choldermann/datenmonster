# 🐉 Datenmonster

**Self-hosted ETL & data integration platform by [Holdermann IT](https://datenmonster.com)**

> Connect, transform and automate your data pipelines – without cloud dependency.

![License](https://img.shields.io/badge/license-MIT-green)
![Docker](https://img.shields.io/badge/docker-ready-blue)
![Python](https://img.shields.io/badge/python-3.11-blue)
![React](https://img.shields.io/badge/react-18-61dafb)

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

### Reporting
- Drag-and-drop report canvas
- Widget types: KPI, Bar, Line, Pie/Donut, Table, Heatmap/Calendar
- Dynamic filters and comparison periods
- PDF export and email delivery

---

## 🚀 Quick Start

### Option 1 – Installer (recommended)

**Linux / macOS:**
```bash
curl -fsSL https://install.datenmonster.com/install.sh | bash
```

**Windows (PowerShell as Administrator):**
```powershell
irm https://install.datenmonster.com/install.ps1 | iex
```

### Option 2 – Manual

```bash
git clone https://github.com/HoldermannIT/datenmonster.git
cd datenmonster
cp .env.example .env
# Edit .env and set your passwords
docker compose up --build -d
```

Then open: **http://localhost:5173**

Default login: `admin` / *(see your .env)*

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

- Website: [datenmonster.com](https://datenmonster.com)
- Support: [datenmonster.com/support](https://datenmonster.com/support)
- Holdermann IT: [holdermann.me](https://holdermann.me)
