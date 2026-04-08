from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Any
from app.core.database import get_db
from app.core.security import get_current_user
from app.api.projects import can_read_project, require_editor, get_accessible_project_ids
from app.models.user import User
from app.models.scheduled_job import ScheduledJob, JobRun
from app.models.mapping import Mapping

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _job_out(job: ScheduledJob, db: Session) -> dict:
    # Letzten Run laden
    last_run = (
        db.query(JobRun)
        .filter(JobRun.scheduled_job_id == job.id)
        .order_by(JobRun.started_at.desc())
        .first()
    )
    # Nächsten Lauf aus APScheduler – frühesten aller Sub-Jobs nehmen
    from app.services.scheduler_service import get_scheduler
    sched = get_scheduler()
    next_run = None
    if sched:
        next_times = []
        for apjob in sched.get_jobs():
            if apjob.id.startswith(f"job_{job.id}_") and apjob.next_run_time:
                next_times.append(apjob.next_run_time)
        if next_times:
            next_run = min(next_times).isoformat()

    return {
        "id": job.id,
        "name": job.name,
        "mapping_id": job.mapping_id,
        "cron_expr": job.cron_expr,
        "active": job.active,
        "project_id": job.project_id,
        "start_date": job.start_date.isoformat() if job.start_date else None,
        "end_date": job.end_date.isoformat() if job.end_date else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "next_run": next_run,
        "last_run": {
            "status": last_run.status,
            "started_at": last_run.started_at.isoformat() if last_run.started_at else None,
            "duration_sec": last_run.duration_sec,
            "rows_processed": last_run.rows_processed,
            "error_msg": last_run.error_msg,
        } if last_run else None,
    }


def _validate_cron(expr: str):
    for part in expr.split(";"):
        part = part.strip()
        if not part:
            continue
        parts = part.split()
        if len(parts) != 5:
            raise HTTPException(400, f"Ungültiger Cron-Ausdruck '{part}': muss genau 5 Felder haben")


# ─── Schemas ──────────────────────────────────────────────────────────────────

class JobCreate(BaseModel):
    name: str
    mapping_id: int
    cron_expr: str
    active: Optional[bool] = True
    start_date: Optional[str] = None   # ISO date string YYYY-MM-DD
    end_date: Optional[str] = None
    project_id: Optional[int] = None


class JobUpdate(BaseModel):
    name: Optional[str] = None
    cron_expr: Optional[str] = None
    active: Optional[bool] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/jobs")
def list_jobs(
    project_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if project_id is not None and not can_read_project(project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    accessible = get_accessible_project_ids(user, db) if project_id is None else None
    q = db.query(ScheduledJob)
    if project_id:
        q = q.filter(ScheduledJob.project_id == project_id)
    elif accessible is not None:
        q = q.filter((ScheduledJob.project_id.in_(accessible)) | (ScheduledJob.project_id.is_(None)))
    jobs = q.order_by(ScheduledJob.id.desc()).all()
    return [_job_out(j, db) for j in jobs]


@router.post("/jobs")
def create_job(
    data: JobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validate_cron(data.cron_expr)
    # Mapping muss existieren und User muss Zugriff aufs Projekt haben
    mapping = db.query(Mapping).filter(Mapping.id == data.mapping_id).first()
    if not mapping:
        raise HTTPException(404, "Mapping nicht gefunden")
    require_editor(mapping.project_id, user, db)
    # project_id aus Mapping übernehmen (verhindert Cross-Project Jobs)
    if data.project_id and data.project_id != mapping.project_id:
        raise HTTPException(400, "project_id stimmt nicht mit Mapping-Projekt überein")
    from datetime import date
    job = ScheduledJob(
        name=data.name,
        mapping_id=data.mapping_id,
        cron_expr=data.cron_expr,
        active=data.active,
        start_date=date.fromisoformat(data.start_date) if data.start_date else None,
        end_date=date.fromisoformat(data.end_date) if data.end_date else None,
        project_id=data.project_id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    if job.active:
        from app.services.scheduler_service import register_job
        register_job(job.id, job.mapping_id, job.cron_expr,
                     start_date=job.start_date, end_date=job.end_date)
    return _job_out(job, db)


@router.patch("/jobs/{job_id}")
def update_job(
    job_id: int,
    data: JobUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job nicht gefunden")
    if data.name is not None:
        job.name = data.name
    if data.cron_expr is not None:
        _validate_cron(data.cron_expr)
        job.cron_expr = data.cron_expr
    if data.active is not None:
        job.active = data.active
    if data.start_date is not None:
        from datetime import date
        job.start_date = date.fromisoformat(data.start_date) if data.start_date else None
    if data.end_date is not None:
        from datetime import date
        job.end_date = date.fromisoformat(data.end_date) if data.end_date else None
    db.commit()
    db.refresh(job)

    from app.services.scheduler_service import register_job, unregister_job
    if job.active:
        register_job(job.id, job.mapping_id, job.cron_expr,
                     start_date=job.start_date, end_date=job.end_date)
    else:
        unregister_job(job.id)
    return _job_out(job, db)


@router.delete("/jobs/{job_id}")
def delete_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job nicht gefunden")
    from app.services.scheduler_service import unregister_job
    unregister_job(job_id)
    db.delete(job)
    db.commit()
    return {"ok": True}


@router.post("/jobs/{job_id}/trigger")
def trigger_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job nicht gefunden")
    from app.services.scheduler_service import trigger_job_now
    trigger_job_now(job.id, job.mapping_id)
    return {"ok": True, "message": "Job wird ausgeführt..."}


@router.get("/jobs/{job_id}/runs")
def get_runs(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    runs = (
        db.query(JobRun)
        .filter(JobRun.scheduled_job_id == job_id)
        .order_by(JobRun.started_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": r.id,
            "status": r.status,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "duration_sec": r.duration_sec,
            "rows_processed": r.rows_processed,
            "error_msg": r.error_msg,
            "triggered_by": r.triggered_by,
        }
        for r in runs
    ]
