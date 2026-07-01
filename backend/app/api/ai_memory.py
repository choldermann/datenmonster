from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.services import ai_memory_service as svc
from app.models.ai_memory import AiMemorySolution

router = APIRouter(prefix="/api/ai-memory", tags=["ai-memory"])


# ── Knowledge ─────────────────────────────────────────────────────────────────

class KnowledgeBody(BaseModel):
    scope:    str = "global"    # global | datasource | project
    scope_id: Optional[str] = None
    category: str = "rule"
    title:    str
    content:  str
    enabled:  bool = True


@router.get("/knowledge")
def list_knowledge(
    scope: Optional[str] = None,
    scope_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = svc.list_knowledge(db, scope=scope, scope_id=scope_id)
    return [_serialize_knowledge(r) for r in rows]


@router.post("/knowledge")
def create_knowledge(
    body: KnowledgeBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = svc.create_knowledge(db, body.model_dump())
    return _serialize_knowledge(row)


@router.put("/knowledge/{id}")
def update_knowledge(
    id: int,
    body: KnowledgeBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = svc.update_knowledge(db, id, body.model_dump())
    if not row:
        raise HTTPException(404, "Nicht gefunden")
    return _serialize_knowledge(row)


@router.delete("/knowledge/{id}")
def delete_knowledge(
    id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not svc.delete_knowledge(db, id):
        raise HTTPException(404, "Nicht gefunden")
    return {"ok": True}


# ── Solutions ─────────────────────────────────────────────────────────────────

class SolutionBody(BaseModel):
    project_id: Optional[int] = None
    category:   str = "other"
    title:      str
    prompt:     Optional[str] = None
    response:   str
    rating:     int = 0


@router.get("/solutions")
def list_solutions(
    project_id: Optional[int] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = svc.list_solutions(db, project_id=project_id, category=category)
    return [_serialize_solution(r) for r in rows]


@router.post("/solutions")
def create_solution(
    body: SolutionBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = svc.create_solution(db, body.model_dump())
    return _serialize_solution(row)


@router.put("/solutions/{id}")
def update_solution(
    id: int,
    body: SolutionBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = svc.update_solution(db, id, body.model_dump())
    if not row:
        raise HTTPException(404, "Nicht gefunden")
    return _serialize_solution(row)


@router.post("/solutions/{id}/use")
def use_solution(
    id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    svc.increment_solution_use(db, id)
    return {"ok": True}


@router.delete("/solutions/{id}")
def delete_solution(
    id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not svc.delete_solution(db, id):
        raise HTTPException(404, "Nicht gefunden")
    return {"ok": True}


# ── Corrections ───────────────────────────────────────────────────────────────

class CorrectionBody(BaseModel):
    project_id:      Optional[int] = None
    original_prompt: Optional[str] = None
    ai_response:     str
    user_correction: str
    category:        str = "other"


@router.get("/corrections")
def list_corrections(
    project_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = svc.list_corrections(db, project_id=project_id)
    return [_serialize_correction(r) for r in rows]


@router.post("/corrections")
def create_correction(
    body: CorrectionBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = svc.create_correction(db, body.model_dump())
    return _serialize_correction(row)


@router.delete("/corrections/{id}")
def delete_correction(
    id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not svc.delete_correction(db, id):
        raise HTTPException(404, "Nicht gefunden")
    return {"ok": True}


# ── Prompt Cache ──────────────────────────────────────────────────────────────

@router.get("/cache/stats")
def cache_stats(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return svc.cache_stats(db)


@router.delete("/cache")
def clear_cache(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    count = svc.cache_clear(db)
    return {"ok": True, "cleared": count}


# ── Lern-Vorschläge ──────────────────────────────────────────────────────────

@router.get("/suggestions")
def get_suggestions(
    project_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Gibt Lern-Vorschläge zurück (Lösungen die oft verwendet wurden, aber noch kein Projektwissen sind)."""
    return svc.get_learning_suggestions(db, project_id=project_id)


class PromoteSolutionBody(BaseModel):
    solution_id: int
    scope:       str = "project"
    scope_id:    Optional[str] = None
    category:    str = "rule"


@router.post("/suggestions/promote")
def promote_solution(
    body: PromoteSolutionBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Wandelt eine gespeicherte Lösung in einen Projektwissen-Eintrag um."""
    sol = db.query(AiMemorySolution).filter(AiMemorySolution.id == body.solution_id).first()
    if not sol:
        raise HTTPException(404, "Lösung nicht gefunden")
    knowledge = svc.create_knowledge(db, {
        "scope":    body.scope,
        "scope_id": body.scope_id,
        "category": body.category,
        "title":    sol.title,
        "content":  sol.response[:500],
        "enabled":  True,
    })
    return _serialize_knowledge(knowledge)


# ── Schema Memory Quick-Import ────────────────────────────────────────────────

class SchemaImportBody(BaseModel):
    text:     str           # "fVKNetto = Umsatz\ndErstellt = Datum\n..."
    scope:    str = "global"
    scope_id: Optional[str] = None


@router.post("/knowledge/import-schema")
def import_schema(
    body: SchemaImportBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Schnell-Import von Feld-Definitionen im Format 'feldname = bedeutung'.
    Erstellt für jede Zeile einen Wissenseintrag vom Typ 'field_mapping'.
    """
    created = []
    for line in body.text.strip().splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        parts = line.split("=", 1)
        field_name = parts[0].strip()
        meaning    = parts[1].strip()
        if not field_name or not meaning:
            continue
        row = svc.create_knowledge(db, {
            "scope":    body.scope,
            "scope_id": body.scope_id,
            "category": "field_mapping",
            "title":    field_name,
            "content":  f"{field_name} = {meaning}",
            "enabled":  True,
        })
        created.append(_serialize_knowledge(row))
    return {"created": len(created), "entries": created}


# ── Kontext-Preview (zum Testen) ──────────────────────────────────────────────

class ContextPreviewRequest(BaseModel):
    project_id:      Optional[int] = None
    datasource_ids:  list[str] = []
    category_hint:   Optional[str] = None


@router.post("/context-preview")
def context_preview(
    body: ContextPreviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ctx = svc.build_memory_context(
        db,
        project_id=body.project_id,
        datasource_ids=body.datasource_ids or None,
        category_hint=body.category_hint,
    )
    return {"context": ctx, "length": len(ctx)}


# ── Serializer ────────────────────────────────────────────────────────────────

def _serialize_knowledge(r) -> dict:
    return {
        "id":         r.id,
        "scope":      r.scope,
        "scope_id":   r.scope_id,
        "category":   r.category,
        "title":      r.title,
        "content":    r.content,
        "enabled":    r.enabled,
        "use_count":  r.use_count,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def _serialize_solution(r) -> dict:
    return {
        "id":           r.id,
        "project_id":   r.project_id,
        "category":     r.category,
        "title":        r.title,
        "prompt":       r.prompt,
        "response":     r.response,
        "use_count":    r.use_count,
        "rating":       r.rating,
        "created_at":   r.created_at.isoformat() if r.created_at else None,
        "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
    }


def _serialize_correction(r) -> dict:
    return {
        "id":               r.id,
        "project_id":       r.project_id,
        "original_prompt":  r.original_prompt,
        "ai_response":      r.ai_response,
        "user_correction":  r.user_correction,
        "category":         r.category,
        "applied_count":    r.applied_count,
        "created_at":       r.created_at.isoformat() if r.created_at else None,
    }
