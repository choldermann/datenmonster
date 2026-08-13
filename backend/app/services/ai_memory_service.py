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
from app.services.stichworte import stichworte

log = logging.getLogger("datenmonster")

# Der Wissensblock steht vor JEDEM LLM-Aufruf im Prompt. Auf einem lokalen
# CPU-Modell kostet jedes Zeichen Rechenzeit, über den Gateway kostet es Credits
# — deshalb wird nicht die ganze Wissensdatenbank eingesetzt, sondern nur das,
# was zur Frage passt (siehe _auswaehlen).
#
# Gedeckelt wird in ZEICHEN, nicht in Einträgen: 40 kurze und 40 lange Regeln
# kosten völlig unterschiedlich viel, eine Obergrenze in Zeilen sagt über den
# tatsächlichen Prompt also nichts aus. Grobe Umrechnung für Deutsch: ~4 Zeichen
# je Token, 6.000 Zeichen ≈ 1.500 Token.
KONTEXT_BUDGET  = 6000
MAX_SOLUTIONS   = 5
MAX_CORRECTIONS = 3

# Sicherheitsnetz beim Laden — bewertet wird im Speicher, nicht in SQL.
_HARTE_GRENZE   = 500

# Ab wie vielen Punkten ein Eintrag als passend gilt. Ein einzelner Treffer
# irgendwo im Fließtext ist noch keiner: sonst zieht jedes Allerweltswort die
# halbe Wissensdatenbank herbei (dieselbe Erfahrung wie beim Doku-Assistenten,
# siehe openapi_import.doku_suchen).
_MINDESTPUNKTE  = 3

# Wörter, die in einer Frage an ein Datenwerkzeug immer vorkommen und deshalb
# nichts unterscheiden — „welche Tabelle liefert …" trifft sonst jeden Eintrag,
# weil jeder von Tabellen und Feldern handelt.
_META_WOERTER = {
    "tabelle", "tabellen", "spalte", "spalten", "feld", "felder", "wert", "werte",
    "daten", "datenbank", "abfrage", "query", "liefert", "liefern", "zeige",
    "zeigen", "brauche", "nehme", "nutze", "verwende", "finde", "suche",
}

# Wissen zum eigenen Projekt schlägt bei gleicher Punktzahl das globale.
# Der Bonus wird erst NACH der Mindestpunktzahl vergeben, damit er nichts
# Unpassendes über die Schwelle hebt.
_SCOPE_BONUS = {"project": 2, "datasource": 1, "global": 0}


# ── Kontext-Builder ───────────────────────────────────────────────────────────

def _kandidaten(
    db: Session,
    project_id: int | None,
    datasource_ids: list[str] | None,
) -> list[AiMemoryKnowledge]:
    """Alles, was für diesen Aufruf überhaupt in Frage kommt — in EINER Abfrage."""
    from sqlalchemy import and_, or_

    bedingungen = [AiMemoryKnowledge.scope == "global"]
    if datasource_ids:
        bedingungen.append(and_(
            AiMemoryKnowledge.scope == "datasource",
            AiMemoryKnowledge.scope_id.in_(datasource_ids),
        ))
    if project_id:
        bedingungen.append(and_(
            AiMemoryKnowledge.scope == "project",
            AiMemoryKnowledge.scope_id == str(project_id),
        ))
    return (
        db.query(AiMemoryKnowledge)
        .filter(AiMemoryKnowledge.enabled == True, or_(*bedingungen))
        .order_by(AiMemoryKnowledge.id)          # stabil, nicht zufällig
        .limit(_HARTE_GRENZE)
        .all()
    )


def _trefferart(wort: str, text: str) -> int:
    """
    0 = kein Treffer, 1 = irgendwo im Wort, 2 = am Wortanfang.

    Der Unterschied ist im Deutschen wichtig: „Lagerbestand" soll „Lagerbestände"
    finden (Wortanfang, echter Treffer), aber „liefert" soll nicht über
    „geliefert" jede Einkaufsregel herbeiziehen (mitten im Wort, meist nur eine
    Verbform). Deshalb zählt der Wortanfang voll und der Rest nur halb.
    """
    stelle = text.find(wort)
    if stelle < 0:
        return 0
    while stelle >= 0:
        if stelle == 0 or not text[stelle - 1].isalnum():
            return 2
        stelle = text.find(wort, stelle + 1)
    return 1


def _punkte(row: AiMemoryKnowledge, woerter: list[str]) -> int:
    """Wie gut passt der Eintrag zu den Stichwörtern? Titel wiegt am schwersten."""
    titel     = (row.title or "").lower()
    inhalt    = (row.content or "").lower()
    kategorie = (row.category or "").lower()
    p = 0
    for w in woerter:
        p += 2 * _trefferart(w, titel)          # Wortanfang 4, sonst 2
        p += _trefferart(w, inhalt)             # Wortanfang 2, sonst 1
        if w in kategorie: p += 2
    return p


def _auswaehlen(
    rows: list[AiMemoryKnowledge],
    woerter: list[str],
    budget: int,
) -> tuple[list[AiMemoryKnowledge], dict]:
    """
    Die passenden Einträge heraussuchen, bis das Zeichenbudget voll ist.

    Immer dabei sind Einträge mit `always_include` (die Grundregeln, ohne die
    jede Antwort falsch wird). Der Rest kommt nach Punktzahl. Ohne verwertbare
    Stichwörter — etwa wenn ein Aufrufer keine Frage mitgibt — wird der Reihe
    nach aufgefüllt; `getroffen` ist dann False.
    """
    def _laenge(r) -> int:
        return len(r.title or "") + len(r.content or "") + 6   # „  • : \n"

    immer   = [r for r in rows if getattr(r, "always_include", False)]
    uebrige = [r for r in rows if not getattr(r, "always_include", False)]

    verbraucht = sum(_laenge(r) for r in immer)
    gewaehlt   = list(immer)

    if woerter:
        bewertet = []
        for r in uebrige:
            p = _punkte(r, woerter)
            if p >= _MINDESTPUNKTE:
                bewertet.append((p + _SCOPE_BONUS.get(r.scope, 0), r))
        # Punktzahl absteigend, bei Gleichstand die ältere ID zuerst — die
        # Auswahl muss reproduzierbar sein, sonst ist sie nicht nachvollziehbar.
        bewertet.sort(key=lambda x: (-x[0], x[1].id))
        rangliste = [r for _, r in bewertet]
        getroffen = bool(rangliste)
    else:
        rangliste = uebrige
        getroffen = False

    verworfen = 0
    for r in rangliste:
        if verbraucht + _laenge(r) > budget:
            verworfen += 1           # weitersuchen: kürzere Einträge passen evtl. noch
            continue
        gewaehlt.append(r)
        verbraucht += _laenge(r)

    stats = {
        "kandidaten": len(rows),
        "immer":      len(immer),
        "passend":    len(rangliste),
        "gewaehlt":   len(gewaehlt),
        "verworfen":  verworfen,
        "zeichen":    verbraucht,
        "budget":     budget,
        "getroffen":  getroffen,
    }
    return gewaehlt, stats


def build_memory_context(
    db: Session,
    project_id: int | None = None,
    datasource_ids: list[str] | None = None,
    category_hint: str | None = None,
    frage: str = "",
    hinweise: str = "",
    budget: int | None = None,
) -> str:
    """
    Assembles memory context for injection into the system prompt.
    Returns an empty string if no relevant memory exists.

    `frage` ist die Nutzereingabe, `hinweise` alles, was die Seite an Kontext
    liefert (Tabellennamen, angeklickter Node …). Beides zusammen bestimmt,
    welches Wissen eingesetzt wird — ohne beides bleibt es beim Auffüllen nach
    Reihenfolge.
    """
    text, _ = build_memory_context_details(
        db, project_id=project_id, datasource_ids=datasource_ids,
        category_hint=category_hint, frage=frage, hinweise=hinweise, budget=budget,
    )
    return text


def build_memory_context_details(
    db: Session,
    project_id: int | None = None,
    datasource_ids: list[str] | None = None,
    category_hint: str | None = None,
    frage: str = "",
    hinweise: str = "",
    budget: int | None = None,
) -> tuple[str, dict]:
    """Wie build_memory_context, gibt zusätzlich die Auswahl-Kennzahlen zurück."""
    sections: list[str] = []
    budget = budget or KONTEXT_BUDGET

    woerter = stichworte(f"{frage}\n{hinweise}", zusatz_fuellwoerter=_META_WOERTER)
    rows = _kandidaten(db, project_id, datasource_ids)
    all_knowledge, stats = _auswaehlen(rows, woerter, budget)
    stats["stichworte"] = woerter[:20]

    # Sichtbar machen, was eingesetzt wurde und was wegfällt. Genau das war der
    # alte Fehler: der Deckel warf still Wissen weg, und niemand konnte es
    # merken. print statt log.info, weil die Anwendung kein Logging
    # konfiguriert (siehe ai_service._usage_merken).
    hinweis = (f" — {stats['verworfen']} passende Einträge haben nicht mehr ins Budget gepasst"
               if stats["verworfen"] else "")
    print(
        f"[AI Memory] {stats['gewaehlt']}/{stats['kandidaten']} Einträge eingesetzt "
        f"({stats['zeichen']} von {budget} Zeichen), Stichwörter: "
        f"{', '.join(woerter[:8]) or '—'}{hinweis}",
        flush=True,
    )

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
        stats["gesamt_zeichen"] = 0
        return "", stats

    header = "─── AI Memory (Projektwissen) ───"
    footer = "─── Ende AI Memory ───"
    text = f"\n{header}\n" + "\n\n".join(sections) + f"\n{footer}\n"
    stats["gesamt_zeichen"] = len(text)          # inkl. Lösungen und Korrekturen
    return text, stats


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
