from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List, Any
from pydantic import BaseModel
from datetime import datetime, timezone
import logging
from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.models.pipeline import Pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pipelines", tags=["pipelines"])


def pipeline_out(p):
    return {
        "id": p.id, "name": p.name, "project_id": p.project_id,
        "active": p.active, "nodes": p.nodes or [], "connections": p.connections or [],
        "last_run_at": str(p.last_run_at or ""), "last_run_status": p.last_run_status,
        "created_at": str(p.created_at or ""), "updated_at": str(p.updated_at or ""),
    }


def _sync_pipeline_scheduler(p: Pipeline):
    """
    Liest Trigger-Nodes aus der Pipeline und registriert/entfernt
    entsprechende APScheduler-Jobs.
    Job-ID: pipeline_{pipeline_id}
    """
    try:
        from app.services.scheduler_service import get_scheduler
        scheduler = get_scheduler()
        if not scheduler:
            return

        job_id = f"pipeline_{p.id}"

        # Trigger-Node mit Cron suchen — nur bei trigger_mode "schedule" (oder Default)
        cron_expr = None
        if p.active:
            for node in (p.nodes or []):
                if node.get("type") == "trigger":
                    cfg = node.get("config", {})
                    if cfg.get("trigger_mode", "schedule") == "schedule":
                        cron_expr = cfg.get("cron", "").strip()
                    # manual / ftp_event → kein Cron-Job
                    break

        if cron_expr and p.active:
            # Cron-Ausdrücke können mit ";" getrennt sein (mehrere)
            first_cron = cron_expr.split(";")[0].strip()
            parts = first_cron.split()
            if len(parts) == 5:
                minute, hour, day, month, day_of_week = parts
            else:
                return  # Ungültiger Cron

            def _run_pipeline_job():
                from app.core.database import SessionLocal
                from app.services.pipeline_service import run_pipeline as _run
                db = SessionLocal()
                try:
                    pipeline = db.query(Pipeline).filter(Pipeline.id == p.id).first()
                    if pipeline and pipeline.active:
                        result = _run(pipeline, db)
                        pipeline.last_run_at = datetime.now(timezone.utc)
                        pipeline.last_run_status = "success" if not result.get("errors") else "warning"
                        db.commit()
                except Exception as e:
                    import logging
                    logger.error(f"Pipeline #{p.id} Scheduler-Fehler: {e}")
                finally:
                    db.close()

            # Bestehenden Job entfernen und neu registrieren
            try:
                scheduler.remove_job(job_id)
            except Exception:
                pass

            scheduler.add_job(
                _run_pipeline_job,
                trigger="cron",
                id=job_id,
                name=f"Pipeline: {p.name}",
                minute=minute, hour=hour,
                day=day, month=month,
                day_of_week=day_of_week,
                replace_existing=True,
                misfire_grace_time=300,
            )
            import logging
            logger.info(
                f"Pipeline #{p.id} '{p.name}' scheduled: {first_cron}"
            )
        else:
            # Kein Cron oder inaktiv → Job entfernen
            try:
                scheduler.remove_job(job_id)
            except Exception:
                pass

    except Exception as e:
        import logging
        logger.warning(f"Pipeline Scheduler-Sync fehlgeschlagen: {e}")


class PipelineBody(BaseModel):
    name: str
    project_id: Optional[int] = None
    active: bool = True
    nodes: Optional[List[Any]] = []
    connections: Optional[List[Any]] = []


@router.get("/")
def list_pipelines(project_id: Optional[int] = None, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    q = db.query(Pipeline)
    if project_id:
        q = q.filter(Pipeline.project_id == project_id)
    return [pipeline_out(p) for p in q.order_by(Pipeline.id).all()]


@router.post("/")
def create_pipeline(body: PipelineBody, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    p = Pipeline(**body.dict())
    db.add(p); db.commit(); db.refresh(p)
    _sync_pipeline_scheduler(p)
    return pipeline_out(p)


@router.get("/{pipeline_id}")
def get_pipeline(pipeline_id: int, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    p = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not p: raise HTTPException(404, "Nicht gefunden")
    return pipeline_out(p)


@router.put("/{pipeline_id}")
def update_pipeline(pipeline_id: int, body: PipelineBody, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    p = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not p: raise HTTPException(404, "Nicht gefunden")
    for k, v in body.dict().items():
        setattr(p, k, v)
    p.updated_at = datetime.now(timezone.utc)
    db.commit(); db.refresh(p)
    _sync_pipeline_scheduler(p)
    return pipeline_out(p)


@router.delete("/{pipeline_id}")
def delete_pipeline(pipeline_id: int, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    p = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not p: raise HTTPException(404, "Nicht gefunden")
    # Scheduler-Job entfernen
    try:
        from app.services.scheduler_service import get_scheduler
        get_scheduler().remove_job(f"pipeline_{pipeline_id}")
    except Exception:
        pass
    db.delete(p); db.commit()
    return {"ok": True}


@router.post("/{pipeline_id}/run")
def run_pipeline(pipeline_id: int, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    p = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not p: raise HTTPException(404, "Nicht gefunden")
    from app.services.pipeline_service import run_pipeline as _run
    try:
        result = _run(p, db)
        p.last_run_at = datetime.now(timezone.utc)
        p.last_run_status = "success" if not result.get("errors") else "warning"
        db.commit()
        return result
    except Exception as e:
        import traceback
        p.last_run_at = datetime.now(timezone.utc)
        p.last_run_status = "error"
        db.commit()
        # Fehler wurde bereits in pipeline_service in system_logs geschrieben
        raise HTTPException(500, detail={
            "message": str(e)[:300],
            "type": type(e).__name__,
        })


@router.post("/{pipeline_id}/toggle")
def toggle_pipeline(pipeline_id: int, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """Aktiviert/Deaktiviert eine Pipeline und sync den Scheduler."""
    p = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not p: raise HTTPException(404, "Nicht gefunden")
    old_active = p.active
    p.active = not p.active
    p.updated_at = datetime.now(timezone.utc)
    db.commit(); db.refresh(p)
    _sync_pipeline_scheduler(p)
    # Logging
    try:
        from app.services.db_logger import log as _dblog
        action = "pipeline_started" if p.active else "pipeline_stopped"
        level = "success" if p.active else "info"
        msg = f"Pipeline {'aktiviert (Scheduler registriert)' if p.active else 'deaktiviert (Scheduler entfernt)'}"
        _dblog(db, level, "pipelines", action, msg,
               entity_id=p.id, entity_name=p.name,
               project_id=getattr(p, "project_id", None),
               details={"active": p.active, "triggered_by": user.username})
    except Exception:
        pass
    return {"ok": True, "active": p.active}
