from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
from app.core.database import engine, SessionLocal, Base
from app.core.config import ALLOWED_ORIGINS
from app.core.security import hash_password
from app.models.user import User
from app.models.dataset import Dataset, DbConnection
from app.models.mapping import Mapping
from app.models.project import Project, ProjectMember
from app.models.scheduled_job import ScheduledJob, JobRun
from app.models.export_file import ExportFile
from app.models.ftp_source import FtpSource
from app.models.rest_source import RestSource
from app import auth
from app.api import monitoring as monitoring_api, dispatcher as dispatcher_api, logs as logs_api, pipelines as pipelines_api, templates as templates_api, settings as settings_api, reports as reports_api, datasets, connections, mappings, projects, scheduler, exports, ftp_sources, rest_sources
from app.api import smart_mapping as smart_mapping_api
from app.api import update as update_api


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        from sqlalchemy import text
        for stmt in [
            "ALTER TABLE datasets ADD COLUMN query_config JSON",
            "ALTER TABLE datasets ADD COLUMN project_id INTEGER",
            "ALTER TABLE mappings ADD COLUMN project_id INTEGER",
            "ALTER TABLE mappings ADD COLUMN constant_nodes JSON DEFAULT '[]'",
            "ALTER TABLE db_connections ADD COLUMN project_id INTEGER",
            "ALTER TABLE scheduled_jobs ADD COLUMN start_date DATE",
            "ALTER TABLE scheduled_jobs ADD COLUMN end_date DATE",
            "ALTER TABLE mappings ADD COLUMN targets JSON DEFAULT '[]'",
            "ALTER TABLE mappings ADD COLUMN sort_nodes JSON DEFAULT '[]'",
            "ALTER TABLE mappings ADD COLUMN agg_nodes JSON DEFAULT '[]'",
            "ALTER TABLE mappings ADD COLUMN rest_nodes JSON DEFAULT '[]'",
            "ALTER TABLE mappings ADD COLUMN lookup_nodes JSON DEFAULT '[]'",
            "ALTER TABLE mappings ADD COLUMN calc_nodes JSON DEFAULT '[]'",
            "ALTER TABLE mappings ADD COLUMN switch_nodes JSON DEFAULT '[]'",
            "ALTER TABLE datasets ADD COLUMN source_mapping_id INTEGER",
            "ALTER TABLE datasets ADD COLUMN column_types JSON DEFAULT '{}'",
            "ALTER TABLE scheduled_jobs ADD COLUMN created_by INTEGER",
            "ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0",
            """CREATE TABLE IF NOT EXISTS ftp_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                protocol TEXT DEFAULT 'ftp',
                host TEXT NOT NULL,
                port INTEGER,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                remote_dir TEXT DEFAULT '/',
                filename_filter TEXT DEFAULT '*',
                file_type TEXT DEFAULT 'csv',
                csv_delimiter TEXT DEFAULT ';',
                after_import TEXT DEFAULT 'nothing',
                move_dir TEXT,
                dataset_id INTEGER,
                dataset_mode TEXT DEFAULT 'replace',
                dataset_name_tpl TEXT,
                cron_expr TEXT,
                active INTEGER DEFAULT 1,
                start_date TEXT,
                end_date TEXT,
                project_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME,
                last_run_at DATETIME,
                last_run_status TEXT,
                last_run_msg TEXT,
                last_rows INTEGER
            )""",
            """CREATE TABLE IF NOT EXISTS rest_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                project_id INTEGER,
                url TEXT NOT NULL,
                method TEXT DEFAULT 'GET',
                headers JSON DEFAULT '{}',
                query_params JSON DEFAULT '{}',
                body_type TEXT DEFAULT 'none',
                body_content TEXT,
                auth_type TEXT DEFAULT 'none',
                auth_config JSON DEFAULT '{}',
                data_path TEXT,
                flatten INTEGER DEFAULT 1,
                pagination JSON DEFAULT '{}',
                dataset_id INTEGER,
                dataset_mode TEXT DEFAULT 'replace',
                cron_expr TEXT,
                active INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME,
                last_run_at DATETIME,
                last_run_status TEXT,
                last_run_msg TEXT,
                last_rows INTEGER
            )""",
            """CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                project_id INTEGER,
                widgets JSON DEFAULT '[]',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME
            )""",
            """CREATE TABLE IF NOT EXISTS pipelines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                project_id INTEGER,
                active INTEGER DEFAULT 1,
                nodes JSON DEFAULT '[]',
                connections JSON DEFAULT '[]',
                last_run_at DATETIME,
                last_run_status TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME
            )""",
            """CREATE TABLE IF NOT EXISTS templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                category TEXT DEFAULT 'general',
                version TEXT DEFAULT '1.0',
                author TEXT,
                content JSON NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",
        ]:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass
    db = SessionLocal()
    try:
        import os as _os
        _admin_pw = _os.environ.get("ADMIN_PASSWORD", "admin123")
        _admin = db.query(User).filter(User.username == "admin").first()
        if not _admin:
            _admin = User(username="admin", hashed_password=hash_password(_admin_pw), is_admin=True)
            db.add(_admin)
            db.commit()
            print("Admin-User angelegt")
        else:
            _changed = False
            if _os.environ.get("ADMIN_PASSWORD"):
                _admin.hashed_password = hash_password(_admin_pw)
                _changed = True
                print("Admin-Passwort aus ADMIN_PASSWORD Env aktualisiert")
            if not getattr(_admin, "is_admin", False):
                _admin.is_admin = True
                _changed = True
            if _changed:
                db.commit()
    finally:
        db.close()
    from app.services.scheduler_service import start_scheduler, reload_all_jobs, reload_all_dataset_jobs
    start_scheduler()
    reload_all_jobs()
    reload_all_dataset_jobs()
    # FTP-Jobs laden
    from app.api.ftp_sources import _sync_scheduler
    ftp_db = SessionLocal()
    try:
        for src in ftp_db.query(FtpSource).filter(FtpSource.active == True).all():
            _sync_scheduler(src)
    finally:
        ftp_db.close()

    # Pipeline-Scheduler registrieren (Trigger-Nodes mit Cron)
    from app.models.pipeline import Pipeline
    from app.api.pipelines import _sync_pipeline_scheduler
    pipe_db = SessionLocal()
    try:
        for pipeline in pipe_db.query(Pipeline).filter(Pipeline.active == True).all():
            _sync_pipeline_scheduler(pipeline)
    finally:
        pipe_db.close()

    yield
    from app.services.scheduler_service import stop_scheduler
    stop_scheduler()


app = FastAPI(title="Datenmonster ETL", version="2.0.0", lifespan=lifespan)

# ─── Security-Header Middleware ───────────────────────────────────────────────
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Clickjacking verhindern
        response.headers["X-Frame-Options"] = "DENY"
        # MIME-Sniffing verhindern
        response.headers["X-Content-Type-Options"] = "nosniff"
        # XSS-Schutz (ältere Browser)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Kein Referrer bei externen Links
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Permissions Policy - keine Kamera/Mikrofon etc.
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # HSTS - nur wenn HTTPS (Caddy setzt das, aber doppelt hält besser)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # Content-Security-Policy - API gibt nur JSON zurück
        if request.url.path.startswith("/api/"):
            response.headers["Content-Security-Policy"] = "default-src 'none'"
        return response

app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
)

app.include_router(auth.router)
app.include_router(monitoring_api.router)
app.include_router(dispatcher_api.router)
app.include_router(logs_api.router)
app.include_router(pipelines_api.router)
app.include_router(templates_api.router)
app.include_router(settings_api.router)
app.include_router(reports_api.router)
app.include_router(datasets.router)
app.include_router(connections.router)
app.include_router(mappings.router)
app.include_router(projects.router)
app.include_router(scheduler.router)
app.include_router(exports.router)
app.include_router(ftp_sources.router)
app.include_router(rest_sources.router)
app.include_router(smart_mapping_api.router)
app.include_router(update_api.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "Datenmonster ETL v2"}
