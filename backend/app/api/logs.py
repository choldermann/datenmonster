from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.models.system_log import SystemLog

router = APIRouter(prefix="/api/logs", tags=["logs"])


def log_out(l):
    return {
        "id": l.id, "level": l.level, "module": l.module,
        "action": l.action, "message": l.message,
        "details": l.details, "entity_id": l.entity_id,
        "entity_name": l.entity_name, "project_id": l.project_id,
        "duration_ms": l.duration_ms, "rows_processed": l.rows_processed,
        "rows_before": l.rows_before, "rows_after": l.rows_after,
        "created_at": str(l.created_at or ""),
    }


@router.get("/")
def list_logs(
    level: Optional[str] = None,
    module: Optional[str] = None,
    project_id: Optional[int] = None,
    entity_id: Optional[int] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(SystemLog).order_by(desc(SystemLog.created_at))
    if level: q = q.filter(SystemLog.level == level)
    if module: q = q.filter(SystemLog.module == module)
    if project_id:
        from app.api.projects import can_read_project
        if not can_read_project(project_id, user, db):
            raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
        q = q.filter((SystemLog.project_id == project_id) | (SystemLog.project_id == None))
    else:
        # Ohne project_id: nur eigene Projekte + globale Logs (project_id=NULL)
        from app.api.projects import get_accessible_project_ids
        accessible = get_accessible_project_ids(user, db)
        if accessible is not None:
            q = q.filter((SystemLog.project_id.in_(accessible)) | (SystemLog.project_id == None))
    if entity_id: q = q.filter(SystemLog.entity_id == entity_id)
    total = q.count()
    logs = q.offset(offset).limit(limit).all()
    return {"total": total, "logs": [log_out(l) for l in logs]}


@router.delete("/")
def clear_logs(
    older_than_days: int = 30,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Nur der erste User (älteste ID) darf Logs löschen – kein echtes Admin-System vorhanden
    from app.models.user import User as _User
    first_user = db.query(_User).order_by(_User.id).first()
    if not first_user or first_user.id != user.id:
        from fastapi import HTTPException
        raise HTTPException(403, "Nur der primäre Benutzer darf Logs löschen")
    from datetime import datetime, timezone, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    deleted = db.query(SystemLog).filter(SystemLog.created_at < cutoff).delete()
    db.commit()
    return {"deleted": deleted}
