from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List, Any
from pydantic import BaseModel
from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.models.dispatcher import DispatcherRule

router = APIRouter(prefix="/api/dispatcher", tags=["dispatcher"])


def rule_out(r):
    return {
        "id": r.id, "name": r.name, "project_id": r.project_id,
        "ftp_source_id": r.ftp_source_id, "active": r.active,
        "priority": r.priority, "condition_mode": r.condition_mode,
        "conditions": r.conditions or [], "mapping_id": r.mapping_id,
        "post_actions": r.post_actions or [],
        "created_at": str(r.created_at or ""),
    }


class RuleBody(BaseModel):
    name: str
    project_id: Optional[int] = None
    ftp_source_id: Optional[int] = None
    active: bool = True
    priority: int = 0
    condition_mode: str = "AND"
    conditions: Optional[List[Any]] = []
    mapping_id: Optional[int] = None
    post_actions: Optional[List[Any]] = []


def _regel_lesbar(rule_id: int, db: Session, user: User) -> DispatcherRule:
    """Regel holen – nur wenn der Nutzer ihr Projekt lesen darf."""
    from app.api.projects import can_read_project
    r = db.query(DispatcherRule).filter(DispatcherRule.id == rule_id).first()
    if not r:
        raise HTTPException(404, "Nicht gefunden")
    if not can_read_project(r.project_id, user, db):
        raise HTTPException(404, "Nicht gefunden")
    return r


def _regel_aenderbar(rule_id: int, db: Session, user: User) -> DispatcherRule:
    from app.api.projects import require_editor
    r = _regel_lesbar(rule_id, db, user)
    require_editor(r.project_id, user, db)
    return r


@router.get("/")
def list_rules(project_id: Optional[int] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.api.projects import get_accessible_project_ids, can_read_project
    if project_id is not None and not can_read_project(project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    q = db.query(DispatcherRule)
    if project_id:
        q = q.filter(DispatcherRule.project_id == project_id)
    else:
        erlaubt = get_accessible_project_ids(user, db)
        if erlaubt is not None:
            q = q.filter((DispatcherRule.project_id.in_(erlaubt))
                         | (DispatcherRule.project_id.is_(None)))
    return [rule_out(r) for r in q.order_by(DispatcherRule.priority, DispatcherRule.id).all()]


@router.post("/")
def create_rule(body: RuleBody, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.api.projects import require_editor
    require_editor(body.project_id, user, db)
    r = DispatcherRule(**body.dict())
    db.add(r); db.commit(); db.refresh(r)
    return rule_out(r)


@router.put("/{rule_id}")
def update_rule(rule_id: int, body: RuleBody, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.api.projects import require_editor
    r = _regel_aenderbar(rule_id, db, user)
    require_editor(body.project_id, user, db)   # nicht in ein fremdes Projekt verschieben
    for k, v in body.dict().items():
        setattr(r, k, v)
    db.commit(); db.refresh(r)
    return rule_out(r)


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    r = _regel_aenderbar(rule_id, db, user)
    db.delete(r); db.commit()
    return {"ok": True}


@router.post("/{rule_id}/test")
def test_rule(rule_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Testet eine Regel manuell ohne Datei."""
    r = _regel_lesbar(rule_id, db, user)
    return {"ok": True, "message": f"Regel '{r.name}' würde bei Match Mapping #{r.mapping_id} starten"}
