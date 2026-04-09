"""
Scheduler Service – verwaltet APScheduler Jobs.
Läuft im FastAPI-Prozess, kein extra Service nötig.
"""
import time
import logging
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.memory import MemoryJobStore

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler = None


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    return _scheduler


def start_scheduler():
    global _scheduler
    _scheduler = BackgroundScheduler(
        jobstores={"default": MemoryJobStore()},
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
        timezone="Europe/Berlin",
    )
    _scheduler.start()
    logger.info("✓ APScheduler gestartet")


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler gestoppt")


def _run_job(scheduled_job_id: int, mapping_id: int, triggered_by: str = "scheduler"):
    """Wird von APScheduler aufgerufen. Nutzt run_mapping_object als einheitlichen Einstiegspunkt."""
    from app.core.database import SessionLocal, safe_commit
    from app.models.scheduled_job import ScheduledJob, JobRun
    from app.models.mapping import Mapping
    from app.models.project import Project
    from app.services.mapping_service import MappingContext, run_mapping_object

    db = SessionLocal()
    run = None
    started = time.time()

    try:
        run = JobRun(scheduled_job_id=scheduled_job_id, mapping_id=mapping_id,
                     status="running", triggered_by=triggered_by)
        db.add(run); db.commit(); db.refresh(run)

        job     = db.query(ScheduledJob).filter(ScheduledJob.id == scheduled_job_id).first()
        mapping = db.query(Mapping).filter(Mapping.id == mapping_id).first()
        if not mapping:
            raise ValueError(f"Mapping {mapping_id} nicht gefunden")

        user_id      = job.created_by if job and hasattr(job, "created_by") and job.created_by else 1
        project_id   = mapping.project_id
        mapping_name = mapping.name
        project_name = None
        if project_id:
            proj = db.query(Project).filter(Project.id == project_id).first()
            project_name = proj.name if proj else None

        ctx = MappingContext.from_orm(mapping)
        if not ctx.targets:
            raise ValueError("Keine Ziele im Mapping konfiguriert")

        # Job-Timeout: Mapping darf maximal JOB_TIMEOUT_SECONDS laufen
        JOB_TIMEOUT_SECONDS = 3600  # 1 Stunde – via Env überschreibbar
        import os as _os
        try:
            JOB_TIMEOUT_SECONDS = int(_os.environ.get("SCHEDULER_JOB_TIMEOUT", 3600))
        except (ValueError, TypeError):
            pass

        import concurrent.futures as _cf
        with _cf.ThreadPoolExecutor(max_workers=1) as _exec:
            _future = _exec.submit(
                run_mapping_object,
                ctx,
                preview_rows=999999,
                db=db,
                mapping_id=mapping_id,
                mapping_name=mapping_name,
                project_id=project_id,
                project_name=project_name,
                user_id=user_id,
                triggered_by=triggered_by,
                scheduled_job_id=scheduled_job_id,
            )
            try:
                result = _future.result(timeout=JOB_TIMEOUT_SECONDS)
            except _cf.TimeoutError:
                _future.cancel()
                raise ValueError(
                    f"Job-Timeout nach {JOB_TIMEOUT_SECONDS}s – "
                    f"Mapping '{mapping_name}' zu langsam oder DB-Verbindung hängt"
                )

        total_rows = result.get("total_rows_written", 0)
        errors     = [t["error"] for t in result.get("targets_results", [])
                      if t.get("status") == "error" and t.get("error")]

        if errors and total_rows == 0:
            raise ValueError("; ".join(errors))

        duration = round(time.time() - started, 2)
        run.status        = "success"
        run.rows_processed = total_rows
        run.duration_sec  = duration
        run.finished_at   = datetime.now(timezone.utc)
        if errors:
            run.error_msg = "Teilfehler: " + "; ".join(errors)
        safe_commit(db)
        logger.info(f"✓ Job {scheduled_job_id} – {total_rows} Zeilen in {duration}s")

    except Exception as e:
        duration = round(time.time() - started, 2)
        logger.error(f"✗ Job {scheduled_job_id} fehlgeschlagen: {e}")
        if run:
            run.status       = "error"
            run.error_msg    = str(e)[:1000]
            run.duration_sec = duration
            run.finished_at  = datetime.now(timezone.utc)
            safe_commit(db)
    finally:
        db.close()


def register_job(scheduled_job_id: int, mapping_id: int, cron_expr: str,
                 start_date=None, end_date=None):
    """Registriert oder ersetzt einen Job im Scheduler.
    cron_expr kann mehrere Ausdrücke enthalten, getrennt durch ';'.
    start_date / end_date: datetime.date oder None
    """
    from datetime import datetime, time
    sched = get_scheduler()
    if not sched:
        return
    for job in sched.get_jobs():
        if job.id.startswith(f"job_{scheduled_job_id}_"):
            sched.remove_job(job.id)

    # Konvertiere date → datetime für APScheduler
    start_dt = datetime.combine(start_date, time.min) if start_date else None
    end_dt   = datetime.combine(end_date,   time.max) if end_date   else None

    cron_list = [c.strip() for c in cron_expr.split(";") if c.strip()]
    for idx, expr in enumerate(cron_list):
        try:
            parts = expr.strip().split()
            if len(parts) != 5:
                logger.warning(f"Ungültiger Cron-Ausdruck: {expr}")
                continue
            trigger = CronTrigger(
                minute=parts[0], hour=parts[1],
                day=parts[2], month=parts[3], day_of_week=parts[4],
                start_date=start_dt, end_date=end_dt,
                timezone="Europe/Berlin",
            )
            job_id = f"job_{scheduled_job_id}_{idx}"
            sched.add_job(
                _run_job,
                trigger=trigger,
                id=job_id,
                args=[scheduled_job_id, mapping_id, "scheduler"],
                replace_existing=True,
            )
        except Exception as e:
            logger.error(f"Fehler beim Registrieren von Job {scheduled_job_id} ({expr}): {e}")
    logger.info(f"Job {scheduled_job_id}: {len(cron_list)} Ausführungszeit(en) registriert")


def unregister_job(scheduled_job_id: int):
    sched = get_scheduler()
    if not sched:
        return
    removed = 0
    for job in sched.get_jobs():
        if job.id.startswith(f"job_{scheduled_job_id}_"):
            sched.remove_job(job.id)
            removed += 1
    if removed:
        logger.info(f"Job {scheduled_job_id}: {removed} Ausführungszeit(en) entfernt")


def trigger_job_now(scheduled_job_id: int, mapping_id: int):
    """Manueller Sofort-Start – läuft in eigenem Thread."""
    import threading
    t = threading.Thread(
        target=_run_job,
        args=[scheduled_job_id, mapping_id, "manual"],
        daemon=True,
    )
    t.start()


def reload_all_jobs():
    """Beim Start: alle aktiven Jobs aus DB laden."""
    from app.core.database import SessionLocal
    from app.models.scheduled_job import ScheduledJob
    db = SessionLocal()
    try:
        jobs = db.query(ScheduledJob).filter(ScheduledJob.active == True).all()
        for job in jobs:
            register_job(job.id, job.mapping_id, job.cron_expr,
                         start_date=job.start_date, end_date=job.end_date)
        logger.info(f"✓ {len(jobs)} Scheduled Jobs geladen")
    finally:
        db.close()


# ─── Dataset Auto-Refresh ─────────────────────────────────────────────────────

def _run_dataset_requery(dataset_id: int):
    """Wird von APScheduler aufgerufen – führt Requery für ein Dataset aus."""
    from app.core.database import SessionLocal
    from app.models.dataset import Dataset, DbConnection
    from app.services.db_service import query_full_with_types
    from app.services.file_service import dataframe_to_storage, infer_column_types
    from app.services.db_logger import log as _dblog
    from datetime import datetime, timezone
    import time

    db = SessionLocal()
    started = time.time()
    try:
        ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not ds:
            logger.error(f"Dataset-Requery: Dataset {dataset_id} nicht gefunden")
            return

        if not ds.source_connection_id or not ds.source_sql:
            logger.error(f"Dataset-Requery: Dataset {dataset_id} hat keine SQL-Verbindung")
            return

        conn = db.query(DbConnection).filter(DbConnection.id == ds.source_connection_id).first()
        if not conn:
            raise ValueError(f"Verbindung #{ds.source_connection_id} nicht gefunden")

        df, raw_types = query_full_with_types(conn, ds.source_sql)
        ds.row_count = len(df)
        ds.columns = df.columns.tolist()
        ds.column_types = infer_column_types(df, raw_types)
        ds.updated_at = datetime.now(timezone.utc)
        ds.last_refresh_at = datetime.now(timezone.utc)
        ds.last_refresh_status = "success"
        ds.last_refresh_msg = f"{len(df)} Zeilen geladen"
        db.commit()
        dataframe_to_storage(df, ds.id)

        duration = round(time.time() - started, 2)
        _dblog(db, "success", "datasets", "auto_refresh",
            f"Dataset '{ds.name}' automatisch aktualisiert: {len(df)} Zeilen in {duration}s",
            project_id=ds.project_id,
            rows_processed=len(df),
            details={"dataset_id": dataset_id, "duration_sec": duration})
        logger.info(f"✓ Dataset-Requery {dataset_id} '{ds.name}': {len(df)} Zeilen in {duration}s")

    except Exception as e:
        duration = round(time.time() - started, 2)
        logger.error(f"✗ Dataset-Requery {dataset_id} fehlgeschlagen: {e}")
        try:
            from datetime import datetime, timezone
            ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
            if ds:
                ds.last_refresh_at = datetime.now(timezone.utc)
                ds.last_refresh_status = "error"
                ds.last_refresh_msg = str(e)[:300]
                db.commit()
            from app.services.db_logger import log as _dblog
            _dblog(db, "error", "datasets", "auto_refresh_error",
                f"Dataset-Requery fehlgeschlagen: {str(e)[:200]}",
                details={"dataset_id": dataset_id, "traceback": __import__('traceback').format_exc()})
        except Exception:
            pass
    finally:
        db.close()


def register_dataset_job(dataset_id: int, cron_expr: str):
    """Registriert einen Auto-Refresh Job für ein Dataset."""
    sched = get_scheduler()
    if not sched:
        return
    job_id = f"dataset_{dataset_id}"
    # Bestehenden Job entfernen
    try:
        sched.remove_job(job_id)
    except Exception:
        pass

    if not cron_expr or not cron_expr.strip():
        return

    try:
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            logger.warning(f"Ungültiger Cron-Ausdruck für Dataset {dataset_id}: {cron_expr}")
            return
        trigger = CronTrigger(
            minute=parts[0], hour=parts[1],
            day=parts[2], month=parts[3], day_of_week=parts[4],
            timezone="Europe/Berlin",
        )
        sched.add_job(
            _run_dataset_requery,
            trigger=trigger,
            id=job_id,
            args=[dataset_id],
            replace_existing=True,
        )
        logger.info(f"Dataset-Job {dataset_id} registriert: {cron_expr}")
    except Exception as e:
        logger.error(f"Fehler beim Registrieren von Dataset-Job {dataset_id}: {e}")


def unregister_dataset_job(dataset_id: int):
    """Entfernt den Auto-Refresh Job eines Datasets."""
    sched = get_scheduler()
    if not sched:
        return
    try:
        sched.remove_job(f"dataset_{dataset_id}")
        logger.info(f"Dataset-Job {dataset_id} entfernt")
    except Exception:
        pass


def reload_all_dataset_jobs():
    """Beim Start: alle Datasets mit aktivem Auto-Refresh laden."""
    from app.core.database import SessionLocal
    from app.models.dataset import Dataset
    db = SessionLocal()
    try:
        datasets = db.query(Dataset).filter(
            Dataset.auto_refresh == 1,
            Dataset.cron_expr != None,
        ).all()
        for ds in datasets:
            register_dataset_job(ds.id, ds.cron_expr)
        logger.info(f"✓ {len(datasets)} Dataset Auto-Refresh Jobs geladen")
    finally:
        db.close()
