import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/mail", tags=["mail"])


# ── Verbindungstest ────────────────────────────────────────────────────────────

class ConnectionTestBody(BaseModel):
    host: str
    port: int = 993
    user: str
    password: str
    ssl: bool = True
    folder: str = "INBOX"


@router.post("/test-connection")
def test_connection(body: ConnectionTestBody, user: User = Depends(get_current_user)):
    from app.plugins.builtin.mail.imap_client import IMAPClient
    client = IMAPClient(body.host, body.port, body.user, body.password, body.ssl)
    return client.test_connection()


# ── Verarbeitungsprotokoll ─────────────────────────────────────────────────────

@router.get("/log")
def get_log(
    limit: int = Query(100, le=1000),
    status: str = Query(None),
    account_hash: str = Query(None),
    db=Depends(get_db),
    user: User = Depends(get_current_user),
):
    conditions = []
    params: dict = {"limit": limit}
    if status:
        conditions.append("status=:status")
        params["status"] = status
    if account_hash:
        conditions.append("account_hash=:account_hash")
        params["account_hash"] = account_hash

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = db.execute(
        text(f"SELECT * FROM mail_processing_log {where} ORDER BY processed_at DESC LIMIT :limit"),
        params,
    ).fetchall()
    return [dict(r._mapping) for r in rows]


@router.delete("/log")
def clear_log(db=Depends(get_db), user: User = Depends(get_current_user)):
    if not getattr(user, "is_admin", False):
        raise HTTPException(403, "Nur Admins dürfen das Protokoll löschen")
    db.execute(text("DELETE FROM mail_processing_log"))
    db.commit()
    return {"ok": True}


# ── Poller-Verwaltung ──────────────────────────────────────────────────────────

@router.get("/pollers")
def list_pollers(user: User = Depends(get_current_user)):
    from app.plugins.builtin.mail import get_instance
    instance = get_instance()
    if not instance:
        return []
    return instance.list_pollers()


@router.get("/pollers/{dataset_id}/status")
def poller_status(dataset_id: str, user: User = Depends(get_current_user)):
    from app.plugins.builtin.mail import get_instance
    instance = get_instance()
    if not instance:
        return {"running": False, "dataset_id": dataset_id}
    status = instance.get_poller_status(dataset_id)
    return status or {"running": False, "dataset_id": dataset_id}


@router.post("/pollers/{dataset_id}/start")
def start_poller(dataset_id: str, db=Depends(get_db), user: User = Depends(get_current_user)):
    from app.plugins.builtin.mail import get_instance
    from app.models.dataset import Dataset

    instance = get_instance()
    if not instance:
        raise HTTPException(503, "Mail-Plugin nicht geladen")

    ds = db.query(Dataset).filter(
        Dataset.id == int(dataset_id),
        Dataset.file_type == "mail_imap",
    ).first()
    if not ds:
        raise HTTPException(404, "Mail-Dataset nicht gefunden")

    cfg = json.loads(ds.query_config or "{}")
    if not cfg.get("host") or not cfg.get("user") or not cfg.get("password"):
        raise HTTPException(400, "Dataset hat keine vollständige IMAP-Konfiguration")

    instance.start_poller(dataset_id, cfg)
    return {"ok": True, "dataset_id": dataset_id}


@router.post("/pollers/{dataset_id}/stop")
def stop_poller(dataset_id: str, user: User = Depends(get_current_user)):
    from app.plugins.builtin.mail import get_instance
    instance = get_instance()
    if not instance:
        raise HTTPException(503, "Mail-Plugin nicht geladen")
    instance.stop_poller(dataset_id)
    return {"ok": True, "dataset_id": dataset_id}
