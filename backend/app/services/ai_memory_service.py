"""
AI Memory Service — speichert und liefert projektbezogenes KI-Wissen.

Kein Fine-Tuning: Das Modell bleibt unverändert.
Wissen wird als Kontext vor jedem LLM-Aufruf eingefügt.
"""

import hashlib
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.ai_memory import AiMemoryKnowledge, AiMemorySolution, AiMemoryCorrection, AiPromptCache

log = logging.getLogger("datenmonster")

# Maximale Kontext-Einträge pro Kategorie (klein halten für lokale Modelle)
MAX_KNOWLEDGE   = 20
MAX_SOLUTIONS   = 5
MAX_CORRECTIONS = 3


# ── Kontext-Builder ───────────────────────────────────────────────────────────

def build_memory_context(
    db: Session,
    project_id: int | None = None,
    datasource_ids: list[str] | None = None,
    category_hint: str | None = None,
) -> str:
    """
    Assembles memory context for injection into the system prompt.
    Returns an empty string if no relevant memory exists.
    """
    sections: list[str] = []

    # 1. Globales Wissen
    global_rows = (
        db.query(AiMemoryKnowledge)
        .filter(AiMemoryKnowledge.scope == "global", AiMemoryKnowledge.enabled == True)
        .order_by(desc(AiMemoryKnowledge.use_count))
        .limit(MAX_KNOWLEDGE)
        .all()
    )

    # 2. Datasource-spezifisches Wissen
    ds_rows: list[AiMemoryKnowledge] = []
    if datasource_ids:
        ds_rows = (
            db.query(AiMemoryKnowledge)
            .filter(
                AiMemoryKnowledge.scope == "datasource",
                AiMemoryKnowledge.scope_id.in_(datasource_ids),
                AiMemoryKnowledge.enabled == True,
            )
            .order_by(desc(AiMemoryKnowledge.use_count))
            .limit(MAX_KNOWLEDGE)
            .all()
        )

    # 3. Projekt-spezifisches Wissen
    proj_rows: list[AiMemoryKnowledge] = []
    if project_id:
        proj_rows = (
            db.query(AiMemoryKnowledge)
            .filter(
                AiMemoryKnowledge.scope == "project",
                AiMemoryKnowledge.scope_id == str(project_id),
                AiMemoryKnowledge.enabled == True,
            )
            .order_by(desc(AiMemoryKnowledge.use_count))
            .limit(MAX_KNOWLEDGE)
            .all()
        )

    all_knowledge = global_rows + ds_rows + proj_rows
    if all_knowledge:
        lines = ["Projektwissen (projektspezifische Regeln und Definitionen):"]
        for r in all_knowledge:
            lines.append(f"  • {r.title}: {r.content}")
        sections.append("\n".join(lines))

    # 4. Gespeicherte Lösungen (nach Kategorie filtern wenn Hinweis vorhanden)
    sol_query = db.query(AiMemorySolution)
    if category_hint:
        sol_query = sol_query.filter(AiMemorySolution.category == category_hint)
    if project_id:
        from sqlalchemy import or_
        sol_query = sol_query.filter(
            or_(AiMemorySolution.project_id == project_id, AiMemorySolution.project_id == None)
        )
    solutions = (
        sol_query
        .order_by(desc(AiMemorySolution.use_count), desc(AiMemorySolution.rating))
        .limit(MAX_SOLUTIONS)
        .all()
    )
    if solutions:
        lines = ["Bewährte Lösungen (bereits akzeptierte Antworten):"]
        for s in solutions:
            cat_label = f"[{s.category}] " if s.category else ""
            lines.append(f"  • {cat_label}{s.title}:")
            lines.append(f"    {s.response[:300]}")
        sections.append("\n".join(lines))

    # 5. Benutzerkorrekturen
    corr_query = db.query(AiMemoryCorrection)
    if project_id:
        from sqlalchemy import or_
        corr_query = corr_query.filter(
            or_(AiMemoryCorrection.project_id == project_id, AiMemoryCorrection.project_id == None)
        )
    corrections = (
        corr_query
        .order_by(desc(AiMemoryCorrection.applied_count))
        .limit(MAX_CORRECTIONS)
        .all()
    )
    if corrections:
        lines = ["Benutzerkorrekturen (vom Benutzer verbesserte KI-Antworten bevorzugen):"]
        for c in corrections:
            lines.append(f"  • Statt: {c.ai_response[:150]}")
            lines.append(f"    Besser: {c.user_correction[:150]}")
        sections.append("\n".join(lines))

    if not sections:
        return ""

    header = "─── AI Memory (Projektwissen) ───"
    footer = "─── Ende AI Memory ───"
    return f"\n{header}\n" + "\n\n".join(sections) + f"\n{footer}\n"


# ── Prompt Cache ──────────────────────────────────────────────────────────────

def _cache_key(prompt: str, model: str, project_id: int | None) -> str:
    raw = f"{prompt}|{model}|{project_id or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def cache_lookup(db: Session, prompt: str, model: str, project_id: int | None) -> str | None:
    key = _cache_key(prompt, model, project_id)
    return cache_lookup_by_key(db, key)


def cache_lookup_by_key(db: Session, key: str) -> str | None:
    row = db.query(AiPromptCache).filter(AiPromptCache.cache_key == key).first()
    if row:
        row.hit_count += 1
        row.last_hit_at = datetime.utcnow()
        db.commit()
        return row.response
    return None


def cache_store(db: Session, prompt: str, response: str, model: str, project_id: int | None) -> None:
    key = _cache_key(prompt, model, project_id)
    cache_store_by_key(db, key, prompt, response, model, project_id)


def cache_store_by_key(
    db: Session, key: str, prompt: str, response: str,
    model: str | None = None, project_id: int | None = None,
) -> None:
    try:
        existing = db.query(AiPromptCache).filter(AiPromptCache.cache_key == key).first()
        if existing:
            return
        row = AiPromptCache(
            cache_key=key,
            prompt=prompt[:500],
            response=response,
            model=model,
            project_id=project_id,
        )
        db.add(row)
        db.commit()
    except Exception as e:
        log.warning(f"[AI Memory] Cache-Store fehlgeschlagen: {e}")
        db.rollback()


# ── Automatische Lern-Vorschläge ──────────────────────────────────────────────

def get_learning_suggestions(db: Session, project_id: int | None = None) -> list[dict]:
    """
    Returns solutions that have been used >= 3 times but aren't yet in knowledge.
    These are candidates for promotion to permanent project knowledge.
    """
    from sqlalchemy import or_

    q = db.query(AiMemorySolution).filter(AiMemorySolution.use_count >= 3)
    if project_id:
        q = q.filter(or_(AiMemorySolution.project_id == project_id, AiMemorySolution.project_id == None))

    candidates = q.order_by(desc(AiMemorySolution.use_count)).limit(10).all()

    suggestions = []
    for sol in candidates:
        suggestions.append({
            "type": "promote_solution",
            "solution_id": sol.id,
            "title": sol.title,
            "category": sol.category,
            "use_count": sol.use_count,
            "response_preview": sol.response[:120],
            "message": f'Lösung "{sol.title}" wurde {sol.use_count}× verwendet. Als Projektwissen speichern?',
        })
    return suggestions


# ── Knowledge CRUD ────────────────────────────────────────────────────────────

def list_knowledge(db: Session, scope: str | None = None, scope_id: str | None = None) -> list:
    q = db.query(AiMemoryKnowledge)
    if scope:
        q = q.filter(AiMemoryKnowledge.scope == scope)
    if scope_id:
        q = q.filter(AiMemoryKnowledge.scope_id == scope_id)
    return q.order_by(AiMemoryKnowledge.scope, AiMemoryKnowledge.category, AiMemoryKnowledge.title).all()


def create_knowledge(db: Session, data: dict) -> AiMemoryKnowledge:
    row = AiMemoryKnowledge(**{k: v for k, v in data.items() if hasattr(AiMemoryKnowledge, k)})
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_knowledge(db: Session, id: int, data: dict) -> AiMemoryKnowledge | None:
    row = db.query(AiMemoryKnowledge).filter(AiMemoryKnowledge.id == id).first()
    if not row:
        return None
    for k, v in data.items():
        if hasattr(row, k) and k != "id":
            setattr(row, k, v)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def delete_knowledge(db: Session, id: int) -> bool:
    row = db.query(AiMemoryKnowledge).filter(AiMemoryKnowledge.id == id).first()
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


# ── Solutions CRUD ────────────────────────────────────────────────────────────

def list_solutions(db: Session, project_id: int | None = None, category: str | None = None) -> list:
    q = db.query(AiMemorySolution)
    if project_id:
        from sqlalchemy import or_
        q = q.filter(or_(AiMemorySolution.project_id == project_id, AiMemorySolution.project_id == None))
    if category:
        q = q.filter(AiMemorySolution.category == category)
    return q.order_by(desc(AiMemorySolution.use_count), desc(AiMemorySolution.created_at)).all()


def create_solution(db: Session, data: dict) -> AiMemorySolution:
    row = AiMemorySolution(**{k: v for k, v in data.items() if hasattr(AiMemorySolution, k)})
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def increment_solution_use(db: Session, id: int) -> None:
    row = db.query(AiMemorySolution).filter(AiMemorySolution.id == id).first()
    if row:
        row.use_count += 1
        row.last_used_at = datetime.utcnow()
        db.commit()


def delete_solution(db: Session, id: int) -> bool:
    row = db.query(AiMemorySolution).filter(AiMemorySolution.id == id).first()
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


def update_solution(db: Session, id: int, data: dict) -> AiMemorySolution | None:
    row = db.query(AiMemorySolution).filter(AiMemorySolution.id == id).first()
    if not row:
        return None
    for k, v in data.items():
        if hasattr(row, k) and k != "id":
            setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


# ── Corrections CRUD ──────────────────────────────────────────────────────────

def list_corrections(db: Session, project_id: int | None = None) -> list:
    q = db.query(AiMemoryCorrection)
    if project_id:
        from sqlalchemy import or_
        q = q.filter(or_(AiMemoryCorrection.project_id == project_id, AiMemoryCorrection.project_id == None))
    return q.order_by(desc(AiMemoryCorrection.created_at)).all()


def create_correction(db: Session, data: dict) -> AiMemoryCorrection:
    row = AiMemoryCorrection(**{k: v for k, v in data.items() if hasattr(AiMemoryCorrection, k)})
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_correction(db: Session, id: int) -> bool:
    row = db.query(AiMemoryCorrection).filter(AiMemoryCorrection.id == id).first()
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


# ── Prompt Cache Stats ────────────────────────────────────────────────────────

def cache_stats(db: Session) -> dict:
    total = db.query(AiPromptCache).count()
    hits  = db.query(AiPromptCache).filter(AiPromptCache.hit_count > 0).count()
    total_hits = db.query(AiPromptCache).with_entities(
        AiPromptCache.hit_count
    ).all()
    total_hit_count = sum(r[0] for r in total_hits)
    return {
        "total_entries": total,
        "entries_with_hits": hits,
        "total_hit_count": total_hit_count,
        "hit_rate": round(total_hit_count / max(total + total_hit_count, 1) * 100, 1),
    }


def cache_clear(db: Session) -> int:
    count = db.query(AiPromptCache).count()
    db.query(AiPromptCache).delete()
    db.commit()
    return count
