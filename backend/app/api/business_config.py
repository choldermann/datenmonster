"""Geschäftsparameter je Projekt: Schwellwerte, Kostensätze, Ziele.

Die Werte werden bei jedem Formular-/Drilldown-/Report-Lauf als :cfg_<key> in die
Mappings injiziert (business_config_service.apply_config).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, Any
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.api.projects import can_read_project, require_editor
from app.services import business_config_service as cfg_service

router = APIRouter(prefix="/api/business-config", tags=["business-config"])


@router.get("/thresholds")
def get_thresholds(project_id: Optional[int] = None,
                   db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """Alle Schwellwerte mit Standardwert, aktuellem Wert und Beschreibung."""
    if not can_read_project(project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    aktuell = cfg_service.get_thresholds(project_id, db)
    out = []
    for meta in cfg_service.threshold_meta():
        key = meta["key"]
        out.append({**meta, "value": aktuell.get(key, meta["default"]),
                    "is_default": aktuell.get(key, meta["default"]) == meta["default"]})
    return {"project_id": project_id, "thresholds": out}


class ThresholdIn(BaseModel):
    project_id: Optional[int] = None
    key: str
    value: Any


@router.put("/thresholds")
def set_threshold(body: ThresholdIn, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    require_editor(body.project_id, user, db)
    bekannt = {m["key"] for m in cfg_service.threshold_meta()}
    if body.key not in bekannt:
        raise HTTPException(400, f"Unbekannter Schwellwert: {body.key}")
    wert = body.value
    if isinstance(wert, str):
        try:
            wert = float(wert.replace(",", "."))
        except ValueError:
            raise HTTPException(400, "Schwellwert muss eine Zahl sein")
    if isinstance(wert, float) and wert.is_integer():
        wert = int(wert)
    cfg_service.set_value(body.project_id, db, "threshold", body.key, wert)
    return {"key": body.key, "value": wert}


@router.delete("/thresholds/{key}")
def reset_threshold(key: str, project_id: Optional[int] = None,
                    db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """Überschreibung entfernen – der Standardwert gilt wieder."""
    require_editor(project_id, user, db)
    cfg_service.reset_value(project_id, db, "threshold", key)
    return {"key": key, "value": dict(
        (m["key"], m["default"]) for m in cfg_service.threshold_meta()).get(key)}


# ── Kostensätze und Ziele: Speicher steht, Auswertung folgt in Phase 2/4 ──────

@router.get("/costs")
def list_costs(project_id: Optional[int] = None, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    if not can_read_project(project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    return cfg_service.get_costs(project_id, db)


class ScopedValueIn(BaseModel):
    project_id: Optional[int] = None
    key: str
    value: dict


@router.put("/costs")
def set_cost(body: ScopedValueIn, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    require_editor(body.project_id, user, db)
    cfg_service.set_value(body.project_id, db, "cost", body.key, body.value)
    return {"key": body.key, "value": body.value}


@router.delete("/costs/{key}")
def delete_cost(key: str, project_id: Optional[int] = None,
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_editor(project_id, user, db)
    return {"deleted": cfg_service.reset_value(project_id, db, "cost", key)}


@router.get("/goals")
def list_goals(project_id: Optional[int] = None, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    if not can_read_project(project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    return cfg_service.get_goals(project_id, db)


@router.put("/goals")
def set_goal(body: ScopedValueIn, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    require_editor(body.project_id, user, db)
    cfg_service.set_value(body.project_id, db, "goal", body.key, body.value)
    return {"key": body.key, "value": body.value}


@router.delete("/goals/{key}")
def delete_goal(key: str, project_id: Optional[int] = None,
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_editor(project_id, user, db)
    return {"deleted": cfg_service.reset_value(project_id, db, "goal", key)}
