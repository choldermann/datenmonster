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


# ── Zugriff ───────────────────────────────────────────────────────────────────
# Das KI-Gedächtnis landet in den Prompts ANDERER Benutzer (always_include sogar
# in jedem). Globales und verbindungsweites Wissen darf deshalb nur ein Admin
# ändern; projektgebundenes der Editor des Projekts. Lesen: nur eigene Projekte.

def _projekt_id(scope: Optional[str], scope_id) -> Optional[int]:
    if scope != "project" or scope_id in (None, ""):
        return None
    try:
        return int(scope_id)
    except (TypeError, ValueError):
        return None


def _darf_schreiben(project_id: Optional[int], user, db) -> None:
    from app.core.zugriff import nur_admin, schreiben_pruefen
    if project_id is None:
        nur_admin(user, "Globales KI-Wissen dürfen nur Administratoren ändern")
    else:
        schreiben_pruefen(project_id, user, db)


def _wissen_schreiben(scope, scope_id, user, db) -> None:
    _darf_schreiben(_projekt_id(scope, scope_id), user, db)


def _lesbare_projekte(user, db) -> Optional[set]:
    """None = alles sichtbar (Admin)."""
    from app.core.zugriff import ist_admin, projekte_mit_rolle
    return None if ist_admin(user) else projekte_mit_rolle(user, db)


def _projekt_lesen(project_id, user, db) -> None:
    if project_id:
        from app.core.zugriff import lesen_pruefen
        lesen_pruefen(project_id, user, db)


# ── Knowledge ─────────────────────────────────────────────────────────────────

class KnowledgeBody(BaseModel):
    scope:    str = "global"    # global | datasource | project
    scope_id: Optional[str] = None
    category: str = "rule"
    title:    str
    content:  str
    enabled:  bool = True
    always_include: bool = False   # Grundregel: überspringt die Relevanzauswahl


@router.get("/knowledge")
def list_knowledge(
    scope: Optional[str] = None,
    scope_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = svc.list_knowledge(db, scope=scope, scope_id=scope_id)
    erlaubt = _lesbare_projekte(user, db)
    if erlaubt is not None:
        rows = [r for r in rows if r.scope != "project"
                or _projekt_id(r.scope, r.scope_id) in erlaubt]
    return [_serialize_knowledge(r) for r in rows]


@router.post("/knowledge")
def create_knowledge(
    body: KnowledgeBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _wissen_schreiben(body.scope, body.scope_id, user, db)
    row = svc.create_knowledge(db, body.model_dump())
    return _serialize_knowledge(row)


@router.put("/knowledge/{id}")
def update_knowledge(
    id: int,
    body: KnowledgeBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.models.ai_memory import AiMemoryKnowledge
    alt = db.query(AiMemoryKnowledge).filter(AiMemoryKnowledge.id == id).first()
    if not alt:
        raise HTTPException(404, "Nicht gefunden")
    # Bisheriger UND neuer Geltungsbereich: sonst ließe sich ein fremder
    # Eintrag per Umzug ins eigene Projekt übernehmen (oder umgekehrt).
    _wissen_schreiben(alt.scope, alt.scope_id, user, db)
    _wissen_schreiben(body.scope, body.scope_id, user, db)
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
    from app.models.ai_memory import AiMemoryKnowledge
    alt = db.query(AiMemoryKnowledge).filter(AiMemoryKnowledge.id == id).first()
    if alt:
        _wissen_schreiben(alt.scope, alt.scope_id, user, db)
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
    _projekt_lesen(project_id, user, db)
    rows = svc.list_solutions(db, project_id=project_id, category=category)
    erlaubt = _lesbare_projekte(user, db)
    if erlaubt is not None:
        rows = [r for r in rows if r.project_id is None or r.project_id in erlaubt]
    return [_serialize_solution(r) for r in rows]


@router.post("/solutions")
def create_solution(
    body: SolutionBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _darf_schreiben(body.project_id, user, db)
    row = svc.create_solution(db, body.model_dump())
    return _serialize_solution(row)


@router.put("/solutions/{id}")
def update_solution(
    id: int,
    body: SolutionBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    alt = db.query(AiMemorySolution).filter(AiMemorySolution.id == id).first()
    if not alt:
        raise HTTPException(404, "Nicht gefunden")
    _darf_schreiben(alt.project_id, user, db)
    _darf_schreiben(body.project_id, user, db)
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
    sol = db.query(AiMemorySolution).filter(AiMemorySolution.id == id).first()
    if sol:
        _projekt_lesen(sol.project_id, user, db)
    svc.increment_solution_use(db, id)
    return {"ok": True}


@router.delete("/solutions/{id}")
def delete_solution(
    id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    alt = db.query(AiMemorySolution).filter(AiMemorySolution.id == id).first()
    if alt:
        _darf_schreiben(alt.project_id, user, db)
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
    _projekt_lesen(project_id, user, db)
    rows = svc.list_corrections(db, project_id=project_id)
    erlaubt = _lesbare_projekte(user, db)
    if erlaubt is not None:
        rows = [r for r in rows if r.project_id is None or r.project_id in erlaubt]
    return [_serialize_correction(r) for r in rows]


@router.post("/corrections")
def create_correction(
    body: CorrectionBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _darf_schreiben(body.project_id, user, db)
    row = svc.create_correction(db, body.model_dump())
    return _serialize_correction(row)


@router.delete("/corrections/{id}")
def delete_correction(
    id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.models.ai_memory import AiMemoryCorrection
    alt = db.query(AiMemoryCorrection).filter(AiMemoryCorrection.id == id).first()
    if alt:
        _darf_schreiben(alt.project_id, user, db)
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
    from app.core.zugriff import nur_admin
    nur_admin(user)  # Cache ist instanzweit
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
    _projekt_lesen(project_id, user, db)
    vorschlaege = svc.get_learning_suggestions(db, project_id=project_id)
    erlaubt = _lesbare_projekte(user, db)
    if erlaubt is not None:
        ids = {v.get("solution_id") or v.get("id") for v in vorschlaege if isinstance(v, dict)}
        ok = {s.id for s in db.query(AiMemorySolution).filter(AiMemorySolution.id.in_(ids)).all()
              if s.project_id is None or s.project_id in erlaubt}
        vorschlaege = [v for v in vorschlaege
                       if isinstance(v, dict) and (v.get("solution_id") or v.get("id")) in ok]
    return vorschlaege


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
    _projekt_lesen(sol.project_id, user, db)
    _wissen_schreiben(body.scope, body.scope_id, user, db)
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
    _wissen_schreiben(body.scope, body.scope_id, user, db)
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
    frage:           str = ""      # wie im Chat: bestimmt die Auswahl
    hinweise:        str = ""      # Seitenkontext (Tabellen, Node …)
    budget:          Optional[int] = None


@router.post("/context-preview")
def context_preview(
    body: ContextPreviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Zeigt, was bei dieser Frage tatsächlich in den Prompt geht — inklusive der
    Einträge, die nicht mehr ins Budget passten. Ohne diese Zahlen lässt sich
    nicht beurteilen, ob die Wissensdatenbank den Assistenten überlädt.
    """
    _projekt_lesen(body.project_id, user, db)
    ctx, stats = svc.build_memory_context_details(
        db,
        project_id=body.project_id,
        datasource_ids=body.datasource_ids or None,
        category_hint=body.category_hint,
        frage=body.frage,
        hinweise=body.hinweise,
        budget=body.budget,
    )
    return {
        "context": ctx,
        "length":  len(ctx),
        # Faustregel für Deutsch, reicht zum Vergleichen von vorher/nachher.
        "tokens_geschaetzt": round(len(ctx) / 4),
        "stats":   stats,
    }


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
        "always_include": bool(r.always_include),
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
