"""Mapping-Baukasten: Steinkette → Mapping (Plan: Übersetzer = Schritt 2, Editor = Schritt 3).

Lesend: Tabellen/Spalten, Verknüpfungsvorschlag, Rechnen (Zähler je Stein + Vorschau).
Schreibend: Speichern als normales Mapping (Projekt-Editor).
"""
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.zugriff import lesen_pruefen, schreiben_pruefen
from app.models.user import User
from app.services.baukasten import ausfuehren
from app.services.baukasten.uebersetzer import BaukastenFehler

router = APIRouter(prefix="/api/baukasten", tags=["baukasten"])


def _kein_portal(user: User):
    if getattr(user, "is_portal_only", False):
        raise HTTPException(403, "Der Baukasten steht Portal-Benutzern nicht zur Verfügung.")


@router.get("/tabellen")
def tabellen(connection_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _kein_portal(user)
    try:
        return {"tabellen": ausfuehren.tabellen(db, connection_id, user)}
    except BaukastenFehler as e:
        raise HTTPException(400, str(e))


@router.get("/verknuepfung")
def verknuepfung(connection_id: int, von: str, zu: str, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    _kein_portal(user)
    try:
        return {"vorschlag": ausfuehren.verknuepfung(db, connection_id, user, von, zu)}
    except BaukastenFehler as e:
        raise HTTPException(400, str(e))


class RechnenIn(BaseModel):
    connection_id: int
    kette: List[Any]
    zeige: Optional[str] = None
    von: Optional[str] = None
    bis: Optional[str] = None


@router.post("/rechnen")
def rechnen(body: RechnenIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _kein_portal(user)
    try:
        return ausfuehren.rechnen(db, user, body.connection_id, body.kette, body.zeige, body.von, body.bis)
    except BaukastenFehler as e:
        raise HTTPException(400, str(e))


class SpeichernIn(BaseModel):
    project_id: Optional[int] = None
    connection_id: int
    name: str
    kette: List[Any]
    mapping_id: Optional[int] = None


@router.post("/speichern")
def speichern(body: SpeichernIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _kein_portal(user)
    schreiben_pruefen(body.project_id, user, db)
    try:
        m = ausfuehren.speichern(db, user, body.project_id, body.connection_id, body.name, body.kette, body.mapping_id)
    except BaukastenFehler as e:
        raise HTTPException(400, str(e))
    return {"mapping_id": m.id, "name": m.name}


@router.get("/mapping/{mapping_id}")
def mapping_laden(mapping_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Kette eines Baukasten-Mappings. „profi“: das SQL wurde außerhalb des Baukastens geändert."""
    from app.models.mapping import Mapping
    _kein_portal(user)
    m = db.get(Mapping, mapping_id)
    if m is None:
        raise HTTPException(404, "Mapping nicht gefunden")
    lesen_pruefen(m.project_id, user, db)
    knoten = (m.sql_nodes or [{}])[0] if m.sql_nodes else {}
    bk = knoten.get("baukasten") if isinstance(knoten, dict) else None
    if not bk:
        return {"baukasten": False, "name": m.name, "project_id": m.project_id}
    andere = any(getattr(m, f, None) for f in ("canvas_nodes", "python_nodes", "ai_nodes", "rest_nodes", "lookup_nodes",
                                                "transform_nodes", "calc_nodes", "expr_nodes"))
    geaendert = knoten.get("sql") != bk.get("sql") or len(m.sql_nodes) > 1 or andere
    return {"baukasten": True, "kette": bk.get("kette"), "connection_id": knoten.get("connection_id"),
            "name": m.name, "project_id": m.project_id, "profi_geaendert": geaendert}
