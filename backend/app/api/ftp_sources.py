"""
FTP/SFTP Sources API – CRUD + Test + manueller Trigger
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.ftp_source import FtpSource
from app.api.projects import require_editor
from app.core.security import encrypt_credential, decrypt_credential

router = APIRouter(prefix="/api/ftp-sources", tags=["ftp-sources"])


class FtpSourceCreate(BaseModel):
    name: str
    protocol: str = "ftp"
    host: str
    port: Optional[int] = None
    username: str
    password: Optional[str] = None
    remote_dir: str = "/"
    filename_filter: str = "*"
    file_type: str = "csv"
    csv_delimiter: str = ";"
    skip_rows: int = 0
    after_import: str = "nothing"   # nothing | move | delete
    move_dir: Optional[str] = None
    dataset_id: Optional[int] = None
    dataset_mode: str = "replace"
    dataset_name_tpl: Optional[str] = None
    cron_expr: Optional[str] = None
    active: bool = True
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    project_id: Optional[int] = None


def _out(s: FtpSource) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "protocol": s.protocol,
        "host": s.host,
        "port": s.port,
        "username": s.username,
        "remote_dir": s.remote_dir,
        "filename_filter": s.filename_filter,
        "file_type": s.file_type,
        "csv_delimiter": s.csv_delimiter,
        "after_import": s.after_import,
        "move_dir": s.move_dir,
        "dataset_id": s.dataset_id,
        "dataset_mode": s.dataset_mode,
        "dataset_name_tpl": s.dataset_name_tpl,
        "cron_expr": s.cron_expr,
        "active": s.active,
        "start_date": s.start_date,
        "end_date": s.end_date,
        "project_id": s.project_id,
        "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
        "last_run_status": s.last_run_status,
        "last_run_msg": s.last_run_msg,
        "last_rows": s.last_rows,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


@router.get("/")
def list_ftp_sources(
    project_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.api.projects import get_accessible_project_ids, can_read_project
    if project_id is not None and not can_read_project(project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    q = db.query(FtpSource)
    if project_id is not None:
        q = q.filter(FtpSource.project_id == project_id)
    else:
        accessible = get_accessible_project_ids(user, db)
        if accessible is not None:
            q = q.filter((FtpSource.project_id.in_(accessible)) | (FtpSource.project_id.is_(None)))
    return [_out(s) for s in q.order_by(FtpSource.id.desc()).all()]


@router.post("/")
def create_ftp_source(
    data: FtpSourceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_editor(data.project_id, user, db)
    d = data.model_dump()
    if d.get("password"):
        d["password"] = encrypt_credential(d["password"])
    s = FtpSource(**d)
    db.add(s); db.commit(); db.refresh(s)
    _sync_scheduler(s)
    return _out(s)


@router.get("/{source_id}")
def get_ftp_source(source_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    s = db.query(FtpSource).filter(FtpSource.id == source_id).first()
    if not s: raise HTTPException(404, "FTP-Quelle nicht gefunden")
    return _out(s)


@router.put("/{source_id}")
def update_ftp_source(
    source_id: int,
    data: FtpSourceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    s = db.query(FtpSource).filter(FtpSource.id == source_id).first()
    if not s: raise HTTPException(404, "FTP-Quelle nicht gefunden")
    require_editor(s.project_id, user, db)
    for k, v in data.model_dump().items():
        if k == "password" and not v:
            continue  # Passwort nicht überschreiben wenn leer
        setattr(s, k, v)
    db.commit(); db.refresh(s)
    _sync_scheduler(s)
    return _out(s)


@router.delete("/{source_id}")
def delete_ftp_source(source_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    s = db.query(FtpSource).filter(FtpSource.id == source_id).first()
    if not s: raise HTTPException(404, "FTP-Quelle nicht gefunden")
    require_editor(s.project_id, user, db)
    _unregister_ftp_job(source_id)
    db.delete(s); db.commit()
    return {"ok": True}


@router.post("/{source_id}/trigger")
def trigger_ftp_source(source_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Manueller Sofort-Sync."""
    s = db.query(FtpSource).filter(FtpSource.id == source_id).first()
    if not s: raise HTTPException(404, "FTP-Quelle nicht gefunden")
    import threading
    from app.services.ftp_service import run_ftp_sync
    from app.core.database import SessionLocal, safe_commit
    from datetime import datetime, timezone

    def _run():
        thread_db = SessionLocal()
        src = thread_db.query(FtpSource).filter(FtpSource.id == source_id).first()
        try:
            result = run_ftp_sync(src, thread_db)
            src.last_run_at = datetime.now(timezone.utc)
            src.last_run_status = "success"
            src.last_rows = result.get("rows", 0)
            src.last_run_msg = f"{len(result.get('files_processed', []))} Datei(en) · {result.get('rows', 0)} Zeilen" + ((" · Fehler: " + "; ".join(result["errors"])) if result.get("errors") else "")
            safe_commit(thread_db)
        except Exception as e:
            src.last_run_at = datetime.now(timezone.utc)
            src.last_run_status = "error"
            src.last_run_msg = str(e)[:500]
            safe_commit(thread_db)
        finally:
            thread_db.close()

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "message": "Sync gestartet"}


@router.post("/{source_id}/test")
def test_ftp_connection(source_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Verbindungstest + Dateilisting."""
    s = db.query(FtpSource).filter(FtpSource.id == source_id).first()
    if not s: raise HTTPException(404, "FTP-Quelle nicht gefunden")
    try:
        from app.services.ftp_service import (
            _connect_ftp, _connect_sftp,
            list_files_ftp, list_files_sftp,
        )
        proto = (s.protocol or "ftp").lower()
        if proto == "sftp":
            conn = _connect_sftp(s.host, s.port, s.username, decrypt_credential(s.password))
            files = list_files_sftp(conn, s.remote_dir, s.filename_filter or "*")
            conn.close()
        else:
            conn = _connect_ftp(s.host, s.port, s.username, decrypt_credential(s.password))
            files = list_files_ftp(conn, s.remote_dir, s.filename_filter or "*")
            conn.quit()
        return {"ok": True, "files": files, "count": len(files)}
    except Exception as e:
        raise HTTPException(400, f"Verbindungsfehler: {str(e)[:300]}")


# ─── Scheduler-Hilfsfunktionen ────────────────────────────────────────────────

def _sync_scheduler(source: FtpSource):
    """Registriert oder entfernt den APScheduler-Job für diese FTP-Quelle."""
    from app.services.scheduler_service import get_scheduler
    from apscheduler.triggers.cron import CronTrigger
    from datetime import datetime, time as dtime

    sched = get_scheduler()
    if not sched:
        return

    job_id_prefix = f"ftp_{source.id}_"
    # Alle alten Sub-Jobs entfernen
    for job in sched.get_jobs():
        if job.id.startswith(job_id_prefix):
            sched.remove_job(job.id)

    if not source.active or not source.cron_expr:
        return

    cron_list = [c.strip() for c in source.cron_expr.split(";") if c.strip()]
    for idx, expr in enumerate(cron_list):
        parts = expr.strip().split()
        if len(parts) != 5:
            continue
        start_dt = None
        end_dt = None
        if source.start_date:
            try:
                from datetime import date
                d = date.fromisoformat(source.start_date)
                start_dt = datetime.combine(d, dtime.min)
            except Exception as e:
                import logging as _log
                _log.getLogger("datenmonster").warning(f"FTP {source.id}: Ungültiges start_date '{source.start_date}': {e}")
        if source.end_date:
            try:
                from datetime import date
                d = date.fromisoformat(source.end_date)
                end_dt = datetime.combine(d, dtime.max)
            except Exception as e:
                import logging as _log
                _log.getLogger("datenmonster").warning(f"FTP {source.id}: Ungültiges end_date '{source.end_date}': {e}")
        trigger = CronTrigger(
            minute=parts[0], hour=parts[1],
            day=parts[2], month=parts[3], day_of_week=parts[4],
            start_date=start_dt, end_date=end_dt,
            timezone="Europe/Berlin",
        )
        sched.add_job(
            _run_ftp_job,
            trigger=trigger,
            id=f"{job_id_prefix}{idx}",
            args=[source.id],
            replace_existing=True,
            misfire_grace_time=3600,
        )


def _unregister_ftp_job(source_id: int):
    from app.services.scheduler_service import get_scheduler
    sched = get_scheduler()
    if not sched:
        return
    for job in sched.get_jobs():
        if job.id.startswith(f"ftp_{source_id}_"):
            sched.remove_job(job.id)


def _run_ftp_job(source_id: int):
    """Wird von APScheduler aufgerufen."""
    from app.core.database import SessionLocal
    from app.services.ftp_service import run_ftp_sync
    from datetime import datetime, timezone

    db = SessionLocal()
    try:
        source = db.query(FtpSource).filter(FtpSource.id == source_id).first()
        if not source or not source.active:
            return
        result = run_ftp_sync(source, db)
        source.last_run_at = datetime.now(timezone.utc)
        source.last_run_status = "success"
        source.last_rows = result.get("rows", 0)
        source.last_run_msg = (
            f"{len(result.get('files_processed', []))} Datei(en) · {result.get('rows', 0)} Zeilen"
            + ((" · Fehler: " + "; ".join(result["errors"])) if result.get("errors") else "")
        )
        db.commit()
    except Exception as e:
        try:
            source = db.query(FtpSource).filter(FtpSource.id == source_id).first()
            if source:
                source.last_run_at = datetime.now(timezone.utc)
                source.last_run_status = "error"
                source.last_run_msg = str(e)[:500]
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
