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
                                  cockpits=body.cockpits)


@router.get("/latest")
def latest(project_id: Optional[int] = None, db: Session = Depends(get_db),
           user: User = Depends(get_current_user)):
    """Letzter gespeicherter Lauf – ohne die Quell-DB erneut zu belasten."""
    if not (can_read_project(project_id, user, db)
            or user_can_access_portal_project(project_id, user, db)):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    run = alert_service.latest_run(db, project_id)
    if not run:
        return {"alerts": [], "run_id": None, "started_at": None,
                "checked": 0, "triggered": 0, "errors": []}
    return run
