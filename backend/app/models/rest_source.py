from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.sql import func
from app.core.database import Base


class RestSource(Base):
    """
    Konfiguration für einen REST API Connector.

    Unterstützt:
    - Beliebige HTTP-Methoden (GET, POST, PUT, PATCH)
    - Header, Query-Parameter, Body (JSON / Form / Raw)
    - Auth: None, Basic, Bearer Token, API-Key (Header oder Query), OAuth2 Client Credentials
    - Paginierung: None, page/limit, offset/limit, cursor, Link-Header (RFC 5988)
    - JSON-Path-Extraction: Daten-Array aus verschachteltem JSON extrahieren
    - Scheduler-fähig (cron_expr)
    - Template-Variablen in URL, Headern und Body: {{heute}}, {{gestern}}, {{timestamp}}
    """
    __tablename__ = "rest_sources"

    id           = Column(Integer, primary_key=True, index=True)
    name         = Column(String,  nullable=False)
    project_id   = Column(Integer, nullable=True)

    # ── Request ──────────────────────────────────────────────────────────────
    url          = Column(String,  nullable=False)            # https://api.example.com/v1/orders
    method       = Column(String,  default="GET")             # GET POST PUT PATCH
    headers      = Column(JSON,    default=dict)              # {"Authorization": "Bearer x", ...}
    query_params = Column(JSON,    default=dict)              # {"api_key": "x", "format": "json"}
    body_type    = Column(String,  default="none")            # none | json | form | raw
    body_content = Column(Text,    nullable=True)             # JSON-String oder Raw-Text

    # ── Auth ─────────────────────────────────────────────────────────────────
    auth_type    = Column(String,  default="none")            # none | basic | bearer | apikey | oauth2_cc
    auth_config  = Column(JSON,    default=dict)
    # basic:      { username, password }
    # bearer:     { token }
    # apikey:     { key, value, location: "header"|"query" }
    # oauth2_cc:  { token_url, client_id, client_secret, scope }

    # ── Response ─────────────────────────────────────────────────────────────
    data_path    = Column(String,  nullable=True)             # "data.items" oder "results" – JSONPath zu Array
    flatten      = Column(Integer, default=1)                 # verschachtelte Objekte flach machen

    # ── Paginierung ───────────────────────────────────────────────────────────
    pagination   = Column(JSON,    default=dict)
    # { type: "none" }
    # { type: "page",   page_param: "page",   limit_param: "per_page", limit: 100, start_page: 1 }
    # { type: "offset", offset_param: "skip", limit_param: "take",     limit: 100 }
    # { type: "cursor", cursor_param: "cursor", cursor_path: "meta.next_cursor", stop_when_empty: true }
    # { type: "link_header" }   – RFC 5988 Link: <url>; rel="next"

    # ── Scheduler ────────────────────────────────────────────────────────────
    dataset_id   = Column(Integer, nullable=True)             # Ziel-Dataset (replace/append)
    dataset_mode = Column(String,  default="replace")         # replace | append
    cron_expr    = Column(String,  nullable=True)             # "0 6 * * *"
    active       = Column(Integer, default=1)

    # ── Meta ─────────────────────────────────────────────────────────────────
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())
    last_run_at     = Column(DateTime(timezone=True), nullable=True)
    last_run_status = Column(String,  nullable=True)          # ok | error
    last_run_msg    = Column(Text,    nullable=True)
    last_rows       = Column(Integer, nullable=True)
