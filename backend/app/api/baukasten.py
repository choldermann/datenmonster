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
        conn, schema = ausfuehren.verbindung(db, body.connection_id, user)
        erg = ausfuehren.uebersetzen(body.kette, schema, conn.db_type, literal=True)
        cockpit = ausfuehren.ins_cockpit(db, user, body.project_id, m, body.kette, erg.spalten, erg.nutzt_zeitraum,
                                            auswahl=erg.auswahl, connection_id=body.connection_id)
    except BaukastenFehler as e:
        raise HTTPException(400, str(e))
    return {"mapping_id": m.id, "name": m.name, "cockpit": cockpit}


@router.get("/cockpits")
def cockpits(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Cockpits (Formulare) des Projekts mit ihren Reitern – Auswahl im Stein „Ausgabe“."""
    from app.models.form import Form
    _kein_portal(user)
    schreiben_pruefen(project_id, user, db)
    return [{"id": f.id, "name": f.name,
             "reiter": [{"id": t.get("id"), "label": t.get("label")} for t in (f.schema or {}).get("result_tabs") or []]}
            for f in db.query(Form).filter(Form.project_id == project_id).order_by(Form.name).all()]


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


@router.get("/rezepte")
def rezepte(connection_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Fertige Steinketten, die in dieser Datenbank funktionieren."""
    from app.services.baukasten import rezepte as rz
    _kein_portal(user)
    try:
        conn, schema = ausfuehren.verbindung(db, connection_id, user)
        return {"rezepte": rz.passende(schema, conn.db_type)}
    except BaukastenFehler as e:
        raise HTTPException(400, str(e))


class KiIn(BaseModel):
    connection_id: int
    text: str


@router.post("/ki")
async def ki(body: KiIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Satz → Steinkette. Die KI baut nur mit Steinen; der Übersetzer prüft (und lässt bis zu zweimal nachbessern)."""
    from app.api.ai import _require_ai
    from app.services.baukasten import rezepte as rz
    from app.services.schema_cache_service import get_cached_schema
    _kein_portal(user)
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(400, "Bitte beschreiben, was die Auswertung zeigen soll.")
    if len(text) > 500:
        raise HTTPException(400, "Bitte kürzer fassen (höchstens 500 Zeichen).")
    svc = _require_ai(db)
    try:
        conn, schema = ausfuehren.verbindung(db, body.connection_id, user)
        def probe(k):
            try:
                w = ausfuehren.rechnen(db, user, body.connection_id, k).get("warnungen") or {}
                return {b: t for b, t in w.items() if "keine Zeile" in t}     # nur echte Fehlgriffe zurückgeben
            except Exception:
                return {}
        return await rz.ki_kette(svc, get_cached_schema(conn) or {}, schema, conn.db_type, text, probe=probe)
    except BaukastenFehler as e:
        raise HTTPException(400, str(e))
