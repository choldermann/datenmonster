from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone, timedelta
from typing import Optional
from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.models.pipeline import Pipeline
from app.models.project import Project

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


def _cron_to_label(cron: str) -> str:
    """Wandelt einen Cron-Ausdruck in ein lesbares Label um."""
    if not cron:
        return None
    first = cron.split(";")[0].strip()
    parts = first.split()
    if len(parts) != 5:
        return cron[:20]
    minute, hour, day, month, dow = parts
    if minute == "0" and hour == "*" and day == "*" and month == "*" and dow == "*":
        return "stündlich"
    if minute == "0" and day == "*" and month == "*" and dow == "*":
        return f"täglich {hour}:00"
    if day == "*" and month == "*" and dow != "*":
        days = {"0": "So", "1": "Mo", "2": "Di", "3": "Mi", "4": "Do", "5": "Fr", "6": "Sa"}
        return f"wöchentlich {days.get(dow, dow)} {hour}:{minute.zfill(2)}"
    return first


def _next_run(cron: str) -> Optional[str]:
    """Berechnet den nächsten Laufzeitpunkt aus einem Cron-Ausdruck."""
    if not cron:
        return None
    try:
        from croniter import croniter
        first = cron.split(";")[0].strip()
        c = croniter(first, datetime.now())
        next_dt = c.get_next(datetime)
        now = datetime.now()
        diff = next_dt - now
        minutes = int(diff.total_seconds() / 60)
        if minutes < 60:
            return f"in {minutes} Min."
        elif minutes < 1440:
            hours = minutes // 60
            mins = minutes % 60
            return f"in {hours}h {mins}min" if mins else f"in {hours} Std."
        else:
            return next_dt.strftime("morgen %H:%M") if minutes < 2880 else next_dt.strftime("%d.%m. %H:%M")
    except Exception:
        return None


def _time_ago(dt) -> str:
    """Gibt eine lesbare Zeitangabe zurück."""
    if not dt:
        return "noch nie"
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except Exception:
            return "—"
    now = datetime.now(timezone.utc) if dt.tzinfo else datetime.now()
    diff = now - dt
    minutes = int(diff.total_seconds() / 60)
    if minutes < 1:
        return "gerade eben"
    elif minutes < 60:
        return f"vor {minutes} Min."
    elif minutes < 1440:
        hours = minutes // 60
        return f"vor {hours} Std."
    else:
        days = minutes // 1440
        return f"vor {days} Tagen"


@router.get("/")
def get_monitoring(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Liefert alle Monitoring-Daten für das Dashboard."""

    # Projekte laden
    projects = {p.id: p.name for p in db.query(Project).all()}

    # Pipelines laden
    pipelines = db.query(Pipeline).order_by(Pipeline.id).all()

    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    pipeline_data = []
    errors_today = 0
    runs_today = 0
    active_count = 0
    errors_list = []
    next_runs = []

    for p in pipelines:
        trigger = next((n for n in (p.nodes or []) if n.get("type") == "trigger"), None)
        cron = trigger.get("config", {}).get("cron") if trigger else None
        cron_label = _cron_to_label(cron)
        next_run = _next_run(cron) if p.active and cron else None
        project_name = projects.get(p.project_id, "—")

        # Status bestimmen
        status = "inactive"
        if p.active:
            active_count += 1
            if p.last_run_status == "success":
                status = "success"
            elif p.last_run_status == "error":
                status = "error"
                errors_today += 1
            elif p.last_run_status == "warning":
                status = "warning"
            else:
                status = "active"

        # Läufe heute aus system_logs zählen
        try:
            result = db.execute(
                text("SELECT COUNT(*) FROM system_logs WHERE entity_id = :pid AND created_at >= :today"),
                {"pid": p.id, "today": today_start.isoformat()}
            ).scalar()
            runs_pipeline_today = result or 0
        except Exception:
            runs_pipeline_today = 0

        runs_today += runs_pipeline_today

        pipeline_data.append({
            "id": p.id,
            "name": p.name,
            "project": project_name,
            "project_id": p.project_id,
            "active": p.active,
            "status": status,
            "last_run": _time_ago(p.last_run_at),
            "last_run_at": str(p.last_run_at) if p.last_run_at else None,
            "last_run_status": p.last_run_status,
            "next_run": next_run,
            "cron": cron_label,
            "runs_today": runs_pipeline_today,
        })

        # Fehler sammeln
        if status == "error" and p.last_run_at:
            errors_list.append({
                "pipeline": p.name,
                "level": "error",
                "message": "Pipeline-Lauf fehlgeschlagen",
                "time": _time_ago(p.last_run_at),
            })
        elif status == "warning" and p.last_run_at:
            errors_list.append({
                "pipeline": p.name,
                "level": "warning",
                "message": "Pipeline mit Warnungen abgeschlossen",
                "time": _time_ago(p.last_run_at),
            })

        # Nächste Läufe
        if next_run and p.active:
            next_runs.append({
                "pipeline": p.name,
                "next_run": next_run,
                "cron": cron_label,
            })

    # Fehler + alle Logs aus system_logs laden
    system_logs = []
    try:
        log_result = db.execute(
            text("SELECT id, level, module, action, message, entity_name, created_at, rows_processed, details FROM system_logs ORDER BY id DESC LIMIT 200")
        ).fetchall()
        for row in log_result:
            log_id, level, module, action, message, entity_name, created_at, rows, details_raw = row
            entry = {
                "id": log_id,
                "pipeline": entity_name or module or "System",
                "level": level or "info",
                "action": action or "",
                "message": message or "",
                "rows": rows,
                "time": _time_ago(created_at),
                "created_at": str(created_at) if created_at else "",
                "details": details_raw,
            }
            system_logs.append(entry)
            if level in ("error", "warning"):
                errors_list.append({
                    "pipeline": entity_name or module or "System",
                    "level": level,
                    "message": message or "",
                    "time": _time_ago(created_at),
                })
    except Exception:
        pass

    # Nächste Läufe sortieren
    next_runs = next_runs[:5]

    return {
        "summary": {
            "projects": len(projects),
            "pipelines_active": active_count,
            "pipelines_total": len(pipelines),
            "errors_today": errors_today,
            "runs_today": runs_today,
        },
        "pipelines": pipeline_data,
        "errors": errors_list[:10],
        "next_runs": next_runs,
        "projects": [{"id": k, "name": v} for k, v in projects.items()],
        "system_logs": system_logs,
    }

@router.delete("/logs/{log_id}")
def delete_log(log_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Einzelnen Log-Eintrag löschen."""
    db.execute(text("DELETE FROM system_logs WHERE id = :id"), {"id": log_id})
    db.commit()
    return {"ok": True}


@router.delete("/logs")
def delete_all_logs(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Alle Log-Einträge löschen."""
    db.execute(text("DELETE FROM system_logs"))
    db.commit()
    return {"ok": True}
