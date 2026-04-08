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


@router.get("/")
def list_rules(project_id: Optional[int] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(DispatcherRule)
    if project_id:
        q = q.filter(DispatcherRule.project_id == project_id)
    return [rule_out(r) for r in q.order_by(DispatcherRule.priority, DispatcherRule.id).all()]


@router.post("/")
def create_rule(body: RuleBody, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    r = DispatcherRule(**body.dict())
    db.add(r); db.commit(); db.refresh(r)
    return rule_out(r)


@router.put("/{rule_id}")
def update_rule(rule_id: int, body: RuleBody, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    r = db.query(DispatcherRule).filter(DispatcherRule.id == rule_id).first()
    if not r: raise HTTPException(404, "Nicht gefunden")
    for k, v in body.dict().items():
        setattr(r, k, v)
    db.commit(); db.refresh(r)
    return rule_out(r)


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    r = db.query(DispatcherRule).filter(DispatcherRule.id == rule_id).first()
    if not r: raise HTTPException(404, "Nicht gefunden")
    db.delete(r); db.commit()
    return {"ok": True}


@router.post("/{rule_id}/test")
def test_rule(rule_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Testet eine Regel manuell ohne Datei."""
    r = db.query(DispatcherRule).filter(DispatcherRule.id == rule_id).first()
    if not r: raise HTTPException(404, "Nicht gefunden")
    return {"ok": True, "message": f"Regel '{r.name}' würde bei Match Mapping #{r.mapping_id} starten"}
