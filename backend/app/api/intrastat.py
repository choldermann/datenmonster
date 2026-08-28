"""
Intrastat API – Ausschlussartikel verwalten und Artikel in der JTL-DB suchen.

Ausschlussartikel (z.B. Europaletten/Verpackung) werden pro Projekt gepflegt und
beim Mapping-Lauf automatisch als gebundener Listen-Parameter :excluded_articles
in die betroffenen SQL-Statements injiziert (siehe article_exclusions-Service).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.article_exclusion import ArticleExclusion
from app.api.projects import can_read_project, require_editor
from app.api.portal import user_can_access_portal_project

router = APIRouter(prefix="/api/intrastat", tags=["intrastat"])


def _out(e: ArticleExclusion) -> dict:
    return {
        "id": e.id,
        "project_id": e.project_id,
        "connection_id": e.connection_id,
        "k_artikel": e.k_artikel,
        "art_nr": e.art_nr,
        "name": e.name,
    }


# ─── Ausschlussliste ──────────────────────────────────────────────────────────

@router.get("/exclusions")
def list_exclusions(project_id: Optional[int] = None,
                    db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    if not (can_read_project(project_id, user, db)
            or user_can_access_portal_project(project_id, user, db)):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    q = db.query(ArticleExclusion)
    if project_id is not None:
        q = q.filter(ArticleExclusion.project_id == project_id)
    else:
        q = q.filter(ArticleExclusion.project_id.is_(None))
    rows = q.order_by(ArticleExclusion.art_nr.asc()).all()
    # kArtikel ist eine interne ID der jeweiligen WaWi – die Liste zeigt deshalb
    # nur die Ausschlüsse des aktiven Mandanten. Alteinträge ohne Verbindung
    # gehören dem Standard-Mandanten, weil es damals nur einen gab.
    from app.services import mandant_service
    aktiv = mandant_service.aktiver(project_id, user, db)
    if aktiv is not None:
        ist_standard = mandant_service.standard(project_id, db) == aktiv
        rows = [e for e in rows if e.connection_id == aktiv
                or (e.connection_id is None and ist_standard)]
    return [_out(e) for e in rows]


class ExclusionIn(BaseModel):
    project_id: Optional[int] = None
    connection_id: Optional[int] = None
    k_artikel: int
    art_nr: Optional[str] = None
    name: Optional[str] = None


@router.post("/exclusions")
def add_exclusion(data: ExclusionIn,
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    # Portal-Only-Nutzer dürfen Ausschlüsse eines freigegebenen Formulars pflegen;
    # alle anderen brauchen wie bisher Editor-Rechte am Projekt.
    if not (getattr(user, "is_portal_only", False)
            and user_can_access_portal_project(data.project_id, user, db)):
        require_editor(data.project_id, user, db)
    # Der Ausschluss gehört zu der WaWi, in der die Artikel-ID gilt.
    from app.services import mandant_service
    conn_id = data.connection_id or mandant_service.aktiver(data.project_id, user, db)
    existing = (db.query(ArticleExclusion)
                .filter(ArticleExclusion.project_id == data.project_id,
                        ArticleExclusion.k_artikel == data.k_artikel,
                        ArticleExclusion.connection_id == conn_id)
                .first())
    if existing:
        # Anzeige-Daten auffrischen, aber kein Duplikat anlegen
        existing.art_nr = data.art_nr or existing.art_nr
        existing.name = data.name or existing.name
        existing.connection_id = conn_id or existing.connection_id
        db.commit()
        return _out(existing)
    e = ArticleExclusion(
        project_id=data.project_id,
        connection_id=conn_id,
        k_artikel=data.k_artikel,
        art_nr=data.art_nr,
        name=data.name,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return _out(e)


@router.delete("/exclusions/{excl_id}")
def delete_exclusion(excl_id: int,
                     db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    e = db.query(ArticleExclusion).filter(ArticleExclusion.id == excl_id).first()
    if not e:
        raise HTTPException(404, "Ausschluss nicht gefunden")
    if not (getattr(user, "is_portal_only", False)
            and user_can_access_portal_project(e.project_id, user, db)):
        require_editor(e.project_id, user, db)
    db.delete(e)
    db.commit()
    return {"ok": True}


# ─── Artikel-Suche gegen die JTL-DB ───────────────────────────────────────────

@router.get("/articles/search")
def search_articles(connection_id: int,
                    q: str = Query("", min_length=0),
                    project_id: Optional[int] = None,
                    limit: int = 50,
                    db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """Sucht Artikel (kArtikel, cArtNr, cName) in der JTL-WaWi über die gewählte
    Verbindung. Parametrisiert – kein String-Interpolieren des Suchbegriffs."""
    if not (can_read_project(project_id, user, db)
            or user_can_access_portal_project(project_id, user, db)):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")

    from sqlalchemy import text as _text
    from app.services.sql_helpers import _get_sql_engine

    term = (q or "").strip()
    like = f"%{term}%"
    limit = max(1, min(int(limit or 50), 200))
    sql = _text(
        f"SELECT TOP {limit} a.kArtikel, a.cArtNr, b.cName "
        "FROM dbo.tArtikel a "
        "LEFT JOIN dbo.tArtikelBeschreibung b "
        "  ON b.kArtikel = a.kArtikel "
        "  AND b.kSprache = 1 AND b.kPlattform = 1 AND b.kShop = 0 "
        "WHERE (:term = '' OR a.cArtNr LIKE :like OR b.cName LIKE :like) "
        "ORDER BY a.cArtNr"
    )
    try:
        engine = _get_sql_engine(connection_id)
        with engine.connect() as con:
            rows = con.execute(sql, {"term": term, "like": like}).fetchall()
    except Exception as e:
        raise HTTPException(400, f"Artikel-Suche fehlgeschlagen: {str(e)[:200]}")

    return [{"k_artikel": r[0], "art_nr": r[1], "name": r[2]} for r in rows]
