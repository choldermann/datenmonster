"""Unternehmenswarnungen: Regeln verwalten und auswerten.

Die Regeln sind Daten (AlertRule), keine Programmierung – neue Warnungen kommen
als Template-Inhalt oder über diese API hinzu, ohne Code-Änderung.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, Any
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.alert import AlertRule
from app.api.projects import can_read_project, require_editor
from app.api.portal import user_can_access_portal_project
from app.services import alert_service

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def _out(r: AlertRule) -> dict:
    return {
        "id": r.id, "project_id": r.project_id, "rule_key": r.rule_key,
        "name": r.name, "description": r.description, "category": r.category,
        "cockpit": r.cockpit, "severity": r.severity,
        "severity_levels": r.severity_levels or [],
        "mapping_id": r.mapping_id, "mapping_name": r.mapping_name,
        "params": r.params or {}, "condition": r.condition or {},
        "facts": r.facts or [], "title_template": r.title_template,
        "subtitle": r.subtitle, "drilldown": r.drilldown or {},
        "action_kind": r.action_kind, "active": bool(r.active), "sort": r.sort,
    }


@router.get("/rules")
def list_rules(project_id: Optional[int] = None, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    if not can_read_project(project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    q = db.query(AlertRule)
    q = q.filter(AlertRule.project_id == project_id) if project_id is not None \
        else q.filter(AlertRule.project_id.is_(None))
    rows = q.order_by(AlertRule.sort.asc(), AlertRule.id.asc()).all()
    return [_out(r) for r in rows]


class RuleIn(BaseModel):
    project_id: Optional[int] = None
    rule_key: str
    name: str
    description: Optional[str] = None
    category: str = "allgemein"
    cockpit: Optional[str] = None
    severity: str = "warnung"
    severity_levels: list = []
    mapping_id: Optional[int] = None
    mapping_name: Optional[str] = None
    params: dict = {}
    condition: dict = {}
    facts: list = []
    title_template: Optional[str] = None
    subtitle: Optional[str] = None
    drilldown: dict = {}
    action_kind: Optional[str] = None
    active: bool = True
    sort: int = 100


@router.post("/rules")
def upsert_rule(body: RuleIn, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    """Anlegen oder – bei gleichem rule_key im Projekt – aktualisieren."""
    require_editor(body.project_id, user, db)
    if not (body.mapping_id or body.mapping_name):
        raise HTTPException(400, "Regel braucht mapping_id oder mapping_name")
    q = db.query(AlertRule).filter(AlertRule.rule_key == body.rule_key)
    q = q.filter(AlertRule.project_id == body.project_id) if body.project_id is not None \
        else q.filter(AlertRule.project_id.is_(None))
    r = q.first()
    daten = body.model_dump()
    if r is None:
        r = AlertRule(**daten)
        db.add(r)
    else:
        for k, v in daten.items():
            setattr(r, k, v)
    db.commit()
    db.refresh(r)
    return _out(r)


class RulePatch(BaseModel):
    active: Optional[bool] = None
    severity: Optional[str] = None
    sort: Optional[int] = None
    subtitle: Optional[str] = None
    condition: Optional[dict] = None


@router.patch("/rules/{rule_id}")
def patch_rule(rule_id: int, body: RulePatch, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    r = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
    if not r:
        raise HTTPException(404, "Regel nicht gefunden")
    require_editor(r.project_id, user, db)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(r, k, v)
    db.commit()
    db.refresh(r)
    return _out(r)


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    r = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
    if not r:
        raise HTTPException(404, "Regel nicht gefunden")
    require_editor(r.project_id, user, db)
    db.delete(r)
    db.commit()
    return {"deleted": rule_id}


class EvaluateIn(BaseModel):
    project_id: Optional[int] = None
    params: dict = {}
    include_ok: bool = False
    rule_keys: Optional[list] = None
    cockpits: Optional[list] = None


@router.post("/evaluate")
def evaluate(body: EvaluateIn, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    """Führt die Regeln jetzt aus (read-only gegen die Quell-DB)."""
    if not (can_read_project(body.project_id, user, db)
            or user_can_access_portal_project(body.project_id, user, db)):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    return alert_service.evaluate(db, body.project_id, body.params,
                                  include_ok=body.include_ok,
                                  rule_keys=body.rule_keys,
                                  cockpits=body.cockpits,
                                  user=user)


@router.get("/latest")
def latest(project_id: Optional[int] = None, db: Session = Depends(get_db),
           user: User = Depends(get_current_user)):
    """Letzter gespeicherter Lauf – ohne die Quell-DB erneut zu belasten."""
    if not (can_read_project(project_id, user, db)
            or user_can_access_portal_project(project_id, user, db)):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    from app.services import mandant_service
    run = alert_service.latest_run(db, project_id,
                                   mandant_service.aktiver(project_id, user, db))
    if not run:
        return {"alerts": [], "run_id": None, "started_at": None,
                "checked": 0, "triggered": 0, "errors": []}
    return run


# ---------------------------------------------------------------------------
# Nächtlicher Lauf
# ---------------------------------------------------------------------------

class ScheduleIn(BaseModel):
    project_id: Optional[int] = None
    mandant_id: Optional[int] = None
    cron_expr: str = "30 5 * * *"
    active: bool = False
    email_to: Optional[str] = None
    min_severity: str = "warnung"
    only_new: bool = False
    params: dict = {}
    rule_keys: Optional[list] = None
    cockpits: Optional[list] = None


def _naechster_lauf(schedule_id: int) -> Optional[str]:
    """Nächster geplanter Lauf laut APScheduler – die einzige ehrliche Quelle.

    Ein `active`-Häkchen in der Datenbank sagt nur, was gewollt ist; ob der Job
    im laufenden Prozess wirklich registriert ist, steht allein hier.
    """
    try:
        from app.services.scheduler_service import get_scheduler
        sched = get_scheduler()
        if not sched:
            return None
        job = sched.get_job(f"alerts_{schedule_id}")
        return job.next_run_time.isoformat() if job and job.next_run_time else None
    except Exception:
        return None


def _schedule_out(s) -> dict:
    return {
        "next_run": _naechster_lauf(s.id),
        "id": s.id, "project_id": s.project_id,
        "mandant_id": getattr(s, "mandant_id", None), "cron_expr": s.cron_expr,
        "active": bool(s.active), "email_to": s.email_to or "",
        "min_severity": s.min_severity or "warnung", "only_new": bool(s.only_new),
        "params": s.params or {}, "rule_keys": s.rule_keys or [],
        "cockpits": s.cockpits or [],
        "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
        "last_status": s.last_status, "last_message": s.last_message,
    }


def _get_schedule(db: Session, project_id: Optional[int], mandant_id: Optional[int] = None):
    """Der Zeitplan dieses Projekts und Mandanten.

    Ein Zeitplan aus der Zeit vor der Mandantenfähigkeit (mandant_id NULL) wird
    beim ersten Zugriff dem Standard-Mandanten zugeschlagen – sonst stünde nach
    dem Update ein verwaister Nachtlauf da, während die Oberfläche „noch nicht
    eingerichtet" meldet und ein zweiter angelegt würde.
    """
    from app.models.alert import AlertSchedule
    q = db.query(AlertSchedule)
    q = q.filter(AlertSchedule.project_id == project_id) if project_id is not None \
        else q.filter(AlertSchedule.project_id.is_(None))
    alle = q.all()
    if mandant_id is None:
        return alle[0] if alle else None
    treffer = [s for s in alle if getattr(s, "mandant_id", None) == mandant_id]
    if treffer:
        return treffer[0]
    from app.services import mandant_service
    if mandant_service.standard(project_id, db) == mandant_id:
        verwaist = [s for s in alle if getattr(s, "mandant_id", None) is None]
        if verwaist:
            verwaist[0].mandant_id = mandant_id
            db.commit()
            return verwaist[0]
    return None


@router.get("/schedule")
def get_schedule(project_id: Optional[int] = None, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """Zeitplan des Projekts. Ohne angelegten Zeitplan die Voreinstellung."""
    if not can_read_project(project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    from app.services import mandant_service
    mandant_id = mandant_service.aktiver(project_id, user, db)
    s = _get_schedule(db, project_id, mandant_id)
    if not s:
        return {"id": None, "project_id": project_id, "mandant_id": mandant_id,
                "cron_expr": "30 5 * * *",
                "active": False, "email_to": "", "min_severity": "warnung",
                "only_new": False, "params": {}, "rule_keys": [], "cockpits": [],
                "last_run_at": None, "last_status": None, "last_message": None,
                "next_run": None}
    return _schedule_out(s)


@router.put("/schedule")
def put_schedule(body: ScheduleIn, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """Zeitplan anlegen oder ändern. Registriert den Job sofort neu."""
    from app.models.alert import AlertSchedule
    from app.services.scheduler_service import register_alert_job, unregister_alert_job

    require_editor(body.project_id, user, db)

    parts = (body.cron_expr or "").strip().split()
    if len(parts) != 5:
        raise HTTPException(400, "Cron-Ausdruck muss fünf Felder haben, z. B. „30 5 * * *“")

    from app.services import mandant_service
    mandant_id = body.mandant_id if body.mandant_id is not None \
        else mandant_service.aktiver(body.project_id, user, db)
    if not mandant_service.darf_nutzen(mandant_id, user, db):
        raise HTTPException(403, "Dieser Mandant ist für Sie nicht freigegeben")
    s = _get_schedule(db, body.project_id, mandant_id)
    if not s:
        s = AlertSchedule(project_id=body.project_id, mandant_id=mandant_id)
        db.add(s)

    s.cron_expr = body.cron_expr.strip()
    s.active = bool(body.active)
    s.email_to = (body.email_to or "").strip() or None
    s.min_severity = body.min_severity or "warnung"
    s.only_new = bool(body.only_new)
    s.params = body.params or {}
    s.rule_keys = body.rule_keys or []
    s.cockpits = body.cockpits or []
    db.commit()
    db.refresh(s)

    if s.active:
        register_alert_job(s.id, s.cron_expr)
    else:
        unregister_alert_job(s.id)
    return _schedule_out(s)


@router.post("/schedule/run-now")
def run_schedule_now(project_id: Optional[int] = None, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """Führt den Lauf sofort aus – gleicher Weg wie nachts, inklusive Versand.

    Bewusst synchron: der Anwender soll sehen, ob die Mail tatsächlich rausging,
    statt einem Hintergrundprozess vertrauen zu müssen. Ein Lauf dauert rund
    eine Sekunde.
    """
    from app.models.alert import AlertSchedule
    from app.services.scheduler_service import _run_alert_check

    require_editor(project_id, user, db)
    from app.services import mandant_service
    mandant_id = mandant_service.aktiver(project_id, user, db)
    s = _get_schedule(db, project_id, mandant_id)
    if not s:
        s = AlertSchedule(project_id=project_id, mandant_id=mandant_id)
        db.add(s); db.commit(); db.refresh(s)

    _run_alert_check(s.id, triggered_by="manuell")
    db.refresh(s)
    return _schedule_out(s)
