import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.core.zugriff import ist_admin, lade_dataset, projekte_mit_rolle


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/mail", tags=["mail"])


def _lesbare_mail_datasets(user, db) -> list:
    """Mail-Datasets, deren Projekt der Benutzer lesen darf."""
    from app.models.dataset import Dataset
    from app.api.projects import can_read_project
    return [ds for ds in db.query(Dataset).filter(Dataset.file_type == "mail_imap").all()
            if can_read_project(ds.project_id, user, db)]


def _editor_irgendwo(user, db) -> None:
    """Der Test baut eine Verbindung zu einem frei gewählten Host auf. Das soll
    nur, wer irgendwo Datasets anlegen darf – nicht jeder Betrachter."""
    if ist_admin(user):
        return
    from app.api.projects import get_project_role
    if not any(get_project_role(pid, user, db) in ("owner", "editor")
               for pid in projekte_mit_rolle(user, db)):
        raise HTTPException(403, "Betrachter dürfen keine Verbindungen testen")


# ── Verbindungstest ────────────────────────────────────────────────────────────

class ConnectionTestBody(BaseModel):
    host: str
    port: int = 993
    user: str
    password: str
    ssl: bool = True
    folder: str = "INBOX"


@router.post("/test-connection")
def test_connection(body: ConnectionTestBody, db=Depends(get_db),
                    user: User = Depends(get_current_user)):
    # Passwort kommt aus der Anfrage, gespeicherte Zugangsdaten werden hier
    # nicht verwendet – daher genügt die Editor-Prüfung.
    _editor_irgendwo(user, db)
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
    if not ist_admin(user):
        # Das Protokoll gilt für alle Postfächer der Instanz – nur die eigener
        # Projekte zeigen (Zuordnung über den Konto-Hash des Datasets).
        from app.plugins.builtin.mail.processing import _account_hash
        hashes = []
        for ds in _lesbare_mail_datasets(user, db):
            try:
                hashes.append(_account_hash(json.loads(ds.query_config or "{}")))
            except Exception:
                continue
        if not hashes:
            return []
        platzhalter = []
        for i, h in enumerate(hashes):
            params[f"h{i}"] = h
            platzhalter.append(f":h{i}")
        conditions.append(f"account_hash IN ({', '.join(platzhalter)})")

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
def list_pollers(db=Depends(get_db), user: User = Depends(get_current_user)):
    from app.plugins.builtin.mail import get_instance
    instance = get_instance()
    if not instance:
        return []
    pollers = instance.list_pollers()
    if not ist_admin(user):
        erlaubt = {str(ds.id) for ds in _lesbare_mail_datasets(user, db)}
        pollers = [p for p in pollers if str(p.get("dataset_id")) in erlaubt]
    return pollers


@router.get("/pollers/{dataset_id}/status")
def poller_status(dataset_id: str, db=Depends(get_db), user: User = Depends(get_current_user)):
    if not ist_admin(user):
        lade_dataset(_ds_id(dataset_id), user, db)
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

    ds = lade_dataset(_ds_id(dataset_id), user, db, schreiben=True)
    if ds.file_type != "mail_imap":
        raise HTTPException(404, "Mail-Dataset nicht gefunden")

    cfg = json.loads(ds.query_config or "{}")
    if not cfg.get("host") or not cfg.get("user") or not cfg.get("password"):
        raise HTTPException(400, "Dataset hat keine vollständige IMAP-Konfiguration")

    instance.start_poller(dataset_id, cfg)
    return {"ok": True, "dataset_id": dataset_id}


@router.post("/pollers/{dataset_id}/stop")
def stop_poller(dataset_id: str, db=Depends(get_db), user: User = Depends(get_current_user)):
    # Admins dürfen auch Poller verwaister (gelöschter) Datasets stoppen.
    if not ist_admin(user):
        lade_dataset(_ds_id(dataset_id), user, db, schreiben=True)
    from app.plugins.builtin.mail import get_instance
    instance = get_instance()
    if not instance:
        raise HTTPException(503, "Mail-Plugin nicht geladen")
    instance.stop_poller(dataset_id)
    return {"ok": True, "dataset_id": dataset_id}


def _ds_id(dataset_id: str) -> int:
    try:
        return int(dataset_id)
    except (TypeError, ValueError):
        raise HTTPException(400, "Ungültige Dataset-ID")
