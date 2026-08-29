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
from app.models.plugin import Plugin
from app.models.scheduled_job import ScheduledJob, JobRun
from app.models.export_file import ExportFile
from app.models.ftp_source import FtpSource
from app.models.rest_source import RestSource
from app.models.api_studio import ApiCollection, ApiEnvironment, ApiRequestHistory
from app.models.form import Form, FormSubmission
from app.models.article_exclusion import ArticleExclusion
from app.models.business_config import BusinessConfig
from app.models.mandant import MandantFreigabe, MandantAuswahl
from app.models.alert import AlertRule, AlertRun
from app.models.preisregel import PriceRuleset, PriceRule, PriceRun, PriceChange
from app.models.schema_catalog import SchemaTableMeta, SchemaColumnMeta, SchemaRelationMeta
from app.models.ai_memory import AiMemoryKnowledge, AiMemorySolution, AiMemoryCorrection, AiPromptCache
from app import auth
from app.api import monitoring as monitoring_api, dispatcher as dispatcher_api, logs as logs_api, pipelines as pipelines_api, templates as templates_api, settings as settings_api, datasets, connections, mappings, projects, scheduler, exports, ftp_sources, rest_sources
from app.api import smart_mapping as smart_mapping_api
from app.api import update as update_api
from app.api import plugins as plugins_api
from app.api import events as events_api
from app.api import db_write as db_write_api
from app.api import eingangsrechnung as eingangsrechnung_api
from app.api import intrastat as intrastat_api
from app.api import api_studio as api_studio_api


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
            "ALTER TABLE db_connections ADD COLUMN schema_cache TEXT",
            "ALTER TABLE db_connections ADD COLUMN schema_cached_at DATETIME",
            "ALTER TABLE scheduled_jobs ADD COLUMN start_date DATE",
            "ALTER TABLE scheduled_jobs ADD COLUMN end_date DATE",
            "ALTER TABLE mappings ADD COLUMN targets JSON DEFAULT '[]'",
            "ALTER TABLE mappings ADD COLUMN sort_nodes JSON DEFAULT '[]'",
            "ALTER TABLE mappings ADD COLUMN agg_nodes JSON DEFAULT '[]'",
            "ALTER TABLE mappings ADD COLUMN rest_nodes JSON DEFAULT '[]'",
            "ALTER TABLE mappings ADD COLUMN lookup_nodes JSON DEFAULT '[]'",
            "ALTER TABLE mappings ADD COLUMN calc_nodes JSON DEFAULT '[]'",
            "ALTER TABLE mappings ADD COLUMN switch_nodes JSON DEFAULT '[]'",
            "ALTER TABLE mappings ADD COLUMN expr_nodes JSON DEFAULT '[]'",
            "ALTER TABLE mappings ADD COLUMN quality_nodes JSON DEFAULT '[]'",
            "ALTER TABLE mappings ADD COLUMN param_nodes JSON DEFAULT '[]'",
            """CREATE TABLE IF NOT EXISTS forms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                project_id INTEGER,
                schema JSON DEFAULT '{}',
                version INTEGER DEFAULT 1,
                created_by INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",
            "ALTER TABLE datasets ADD COLUMN source_mapping_id INTEGER",
            "ALTER TABLE datasets ADD COLUMN column_types JSON DEFAULT '{}'",
            "ALTER TABLE scheduled_jobs ADD COLUMN created_by INTEGER",
            "ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0",
            "ALTER TABLE users ADD COLUMN is_portal_only BOOLEAN DEFAULT 0",
            "ALTER TABLE forms ADD COLUMN slug TEXT",
            "ALTER TABLE forms ADD COLUMN published BOOLEAN DEFAULT 0",
            "ALTER TABLE forms ADD COLUMN portal_config JSON DEFAULT '{}'",
            "ALTER TABLE templates ADD COLUMN installations JSON DEFAULT '[]'",
            # API Studio: Requests sind erweiterte rest_sources
            "ALTER TABLE rest_sources ADD COLUMN collection_id INTEGER",
            "ALTER TABLE rest_sources ADD COLUMN description TEXT",
            "ALTER TABLE rest_sources ADD COLUMN sort_order INTEGER DEFAULT 0",
            "ALTER TABLE rest_sources ADD COLUMN store_response INTEGER DEFAULT 0",
            "ALTER TABLE rest_sources ADD COLUMN environment_id INTEGER",
            # Importierte OpenAPI-Doku – Grundlage des Doku-Assistenten
            "ALTER TABLE api_collections ADD COLUMN openapi_doc JSON",
            # Grundregeln, die die Relevanzauswahl des AI-Memory nie wegfiltert
            "ALTER TABLE ai_memory_knowledge ADD COLUMN always_include BOOLEAN DEFAULT 0",
            # Woher ein Warnungslauf kam – trennt die nächtliche Grundlinie vom Klick
            "ALTER TABLE alert_runs ADD COLUMN triggered_by TEXT DEFAULT 'manuell'",
            # Mandantenfähigkeit: eine Verbindung kann ein Mandant sein, und
            # Kosten, Warnungsläufe und Nachtläufe gehören dann genau einem.
            "ALTER TABLE db_connections ADD COLUMN is_mandant BOOLEAN DEFAULT 0",
            "ALTER TABLE db_connections ADD COLUMN mandant_label TEXT",
            "ALTER TABLE db_connections ADD COLUMN is_mandant_default BOOLEAN DEFAULT 0",
            "ALTER TABLE db_connections ADD COLUMN mandant_sort INTEGER DEFAULT 100",
            "ALTER TABLE business_config ADD COLUMN mandant_id INTEGER",
            "ALTER TABLE alert_runs ADD COLUMN mandant_id INTEGER",
            "ALTER TABLE alert_schedules ADD COLUMN mandant_id INTEGER",
            # Regelumfang des Laufs – ohne ihn ist der Vergleich mit dem Vortag unsauber
            "ALTER TABLE alert_runs ADD COLUMN checked_keys JSON",
            # Preisautomatik: Kundengruppenname im Journal (Lesbarkeit)
            "ALTER TABLE price_changes ADD COLUMN kundengruppe TEXT",
            "ALTER TABLE price_changes ADD COLUMN steuersatz FLOAT",
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
            """CREATE TABLE IF NOT EXISTS plugins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plugin_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                version TEXT,
                tier INTEGER DEFAULT 1,
                status TEXT DEFAULT 'active',
                capabilities JSON DEFAULT '[]',
                manifest JSON DEFAULT '{}',
                config JSON DEFAULT '{}',
                installed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME
            )""",
            """CREATE TABLE IF NOT EXISTS event_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                channel TEXT NOT NULL,
                plugin_id TEXT,
                source_type_id TEXT,
                payload JSON DEFAULT '{}',
                triggered_mappings JSON DEFAULT '[]',
                status TEXT DEFAULT 'received',
                error TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS mail_processing_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_hash TEXT NOT NULL,
                message_id TEXT,
                uid TEXT NOT NULL,
                subject TEXT,
                from_addr TEXT,
                received_at TEXT,
                processed_at TEXT,
                status TEXT DEFAULT 'new',
                rule_name TEXT,
                mapping_id INTEGER,
                error TEXT,
                UNIQUE(account_hash, uid)
            )""",
            """CREATE TABLE IF NOT EXISTS ai_memory_knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope TEXT NOT NULL DEFAULT 'global',
                scope_id TEXT,
                category TEXT DEFAULT 'rule',
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                use_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS ai_memory_solutions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                category TEXT DEFAULT 'other',
                title TEXT NOT NULL,
                prompt TEXT,
                response TEXT NOT NULL,
                use_count INTEGER DEFAULT 1,
                rating INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_used_at DATETIME
            )""",
            """CREATE TABLE IF NOT EXISTS ai_memory_corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                original_prompt TEXT,
                ai_response TEXT NOT NULL,
                user_correction TEXT NOT NULL,
                category TEXT DEFAULT 'other',
                applied_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS ai_prompt_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cache_key TEXT UNIQUE NOT NULL,
                prompt TEXT NOT NULL,
                response TEXT NOT NULL,
                model TEXT,
                project_id INTEGER,
                hit_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_hit_at DATETIME
            )""",
        ]:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass

        # ── Eindeutigkeit um den Mandanten erweitern ─────────────────────────
        # SQLite kann eine benannte UNIQUE-Bedingung nicht ändern, sie steckt im
        # CREATE TABLE. Ohne diesen Umbau könnten zwei Mandanten nicht dieselbe
        # Kostenart (»miete«) bzw. denselben Artikel ausschließen – der zweite
        # Betrieb liefe in einen Eindeutigkeitsfehler. Beide Tabellen sind klein,
        # der Umbau kopiert sie deshalb einfach um.
        def _tabelle_umbauen(tabelle: str, alte_bedingung: str, neues_create: str,
                             spalten: str):
            try:
                vorhanden = conn.execute(text(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name=:n"
                ), {"n": tabelle}).fetchone()
                if not vorhanden or alte_bedingung not in (vorhanden[0] or ""):
                    return
                conn.execute(text("PRAGMA foreign_keys=OFF"))
                conn.execute(text(f"ALTER TABLE {tabelle} RENAME TO {tabelle}_alt"))
                conn.execute(text(neues_create))
                conn.execute(text(
                    f"INSERT INTO {tabelle} ({spalten}) SELECT {spalten} FROM {tabelle}_alt"))
                conn.execute(text(f"DROP TABLE {tabelle}_alt"))
                conn.commit()
                print(f"Eindeutigkeit von {tabelle} auf Mandanten erweitert")
            except Exception as e:
                conn.rollback()
                print(f"Umbau von {tabelle} übersprungen: {e}")

        _tabelle_umbauen(
            "business_config", "UNIQUE (project_id, scope",
            """CREATE TABLE business_config (
                id INTEGER NOT NULL PRIMARY KEY,
                project_id INTEGER,
                mandant_id INTEGER,
                scope VARCHAR NOT NULL,
                "key" VARCHAR NOT NULL,
                value JSON,
                updated_at DATETIME,
                CONSTRAINT uq_business_config_key_mandant
                    UNIQUE (project_id, mandant_id, scope, "key")
            )""",
            'id, project_id, mandant_id, scope, "key", value, updated_at')

        _tabelle_umbauen(
            "article_exclusions", "UNIQUE (project_id, k_artikel)",
            """CREATE TABLE article_exclusions (
                id INTEGER NOT NULL PRIMARY KEY,
                project_id INTEGER,
                connection_id INTEGER,
                k_artikel INTEGER NOT NULL,
                art_nr VARCHAR,
                name VARCHAR,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_article_excl_mandant_artikel
                    UNIQUE (project_id, connection_id, k_artikel)
            )""",
            "id, project_id, connection_id, k_artikel, art_nr, name, created_at")

    db = SessionLocal()
    try:
        import os as _os, secrets as _secrets
        _admin_pw_env = _os.environ.get("ADMIN_PASSWORD", "")
        _admin = db.query(User).filter(User.username == "admin").first()
        if not _admin:
            if _admin_pw_env:
                _admin_pw = _admin_pw_env
            else:
                _admin_pw = _secrets.token_urlsafe(16)
                print("=" * 60)
                print(f"  ADMIN-PASSWORT (nur einmalig sichtbar): {_admin_pw}")
                print("  Bitte sofort notieren und in ADMIN_PASSWORD Env setzen!")
                print("=" * 60)
            _admin = User(username="admin", hashed_password=hash_password(_admin_pw), is_admin=True)
            db.add(_admin)
            db.commit()
        else:
            _changed = False
            if _admin_pw_env:
                _admin.hashed_password = hash_password(_admin_pw_env)
                _changed = True
                print("Admin-Passwort aus ADMIN_PASSWORD Env aktualisiert")
            if not getattr(_admin, "is_admin", False):
                _admin.is_admin = True
                _changed = True
            if _changed:
                db.commit()
        # Formulare ohne Slug nachziehen: im Portal wird /app/<slug> aufgerufen,
        # ohne Slug landet der Benutzer auf "Formular nicht gefunden".
        from app.models.form import Form as _Form
        from app.api.forms import unique_slug as _unique_slug
        _ohne_slug = db.query(_Form).filter((_Form.slug == None) | (_Form.slug == "")).all()
        if _ohne_slug:
            for _f in _ohne_slug:
                _f.slug = _unique_slug(db, _f.name or "formular", exclude_id=_f.id)
                db.flush()   # sonst sieht die nächste Prüfung den neuen Slug nicht
            db.commit()
            print(f"Slug für {len(_ohne_slug)} Formular(e) nachgetragen")
    finally:
        db.close()
    from app.services.scheduler_service import (start_scheduler, reload_all_jobs,
                                                 reload_all_dataset_jobs, reload_all_alert_jobs)
    start_scheduler()
    reload_all_jobs()
    reload_all_dataset_jobs()
    reload_all_alert_jobs()
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

    # Plugins laden und in Capability Registry registrieren
    from app.plugins.loader import load_builtin_plugins, load_all_plugins, load_tier2_plugins
    plugin_db = SessionLocal()
    try:
        load_builtin_plugins(db=plugin_db)   # eingebaute Plugins (web, document, mail, ...)
        load_all_plugins(db=plugin_db)        # externe Tier-1 Plugins aus /plugins/
        load_tier2_plugins(db=plugin_db)      # Tier-2 Docker-Container-Plugins
    finally:
        plugin_db.close()

    # Mail-Poller für bestehende IMAP-Datasets starten
    from app.plugins.registry import registry as _plugin_registry
    _mail_plugin = _plugin_registry.get_source("mail_imap")
    if _mail_plugin and hasattr(_mail_plugin, "start_pollers_from_db"):
        _mail_db = SessionLocal()
        try:
            _mail_plugin.start_pollers_from_db(db=_mail_db)
        finally:
            _mail_db.close()

    # EventBus-Listener starten (Redis Pub/Sub)
    from app.services.eventbus import start_listener
    start_listener()

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
app.include_router(plugins_api.router)
app.include_router(events_api.router)
app.include_router(db_write_api.router)
app.include_router(eingangsrechnung_api.router)
app.include_router(intrastat_api.router)
app.include_router(api_studio_api.router)
from app.api import forms as forms_api
from app.api import portal as portal_api
from app.api import web_proxy as web_proxy_api
app.include_router(forms_api.router)
app.include_router(portal_api.router)
app.include_router(web_proxy_api.router)
from app.api import mail as mail_api
app.include_router(mail_api.router)
from app.api import lookup as lookup_api
app.include_router(lookup_api.router)
from app.api import ai as ai_api
app.include_router(ai_api.router)
from app.api import ai_memory as ai_memory_api
app.include_router(ai_memory_api.router)
from app.api import schema_catalog as schema_catalog_api
app.include_router(schema_catalog_api.router)
from app.api import insights as insights_api
app.include_router(insights_api.router)
from app.api import license as license_api
app.include_router(license_api.router)
from app.api import business_config as business_config_api
app.include_router(business_config_api.router)
from app.api import alerts as alerts_api
app.include_router(alerts_api.router)
from app.api import preisregeln as preisregeln_api
app.include_router(preisregeln_api.router)
from app.api import mandanten as mandanten_api
app.include_router(mandanten_api.router)
from app.api import research as research_api
app.include_router(research_api.router)
from app.api import stammdaten as stammdaten_api
app.include_router(stammdaten_api.router)
from app.api import backup as backup_api
app.include_router(backup_api.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "Datenmonster ETL v2"}
