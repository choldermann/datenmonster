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


def _wawi_verbindung(project_id, angefragt, user, db):
    """Welche WaWi ist hier gemeint – und darf dieser Benutzer sie befragen?

    Der aktive Mandant hat Vorrang vor der Verbindung, die der Aufrufer mitschickt.
    Diese stammt aus `config.connection_id` des Formularfelds und ist dort beim
    Installieren eingefroren worden; die Ausschlussliste (`list_exclusions`) filtert
    dagegen längst nach dem aktiven Mandanten. Ohne diesen Vorrang zeigt die Liste
    die Artikel des einen Betriebs, während die Suche im anderen sucht – und nach
    einem Serverwechsel befragt sie eine Datenbank, die es nicht mehr gibt.

    Arbeitet das Projekt ohne Mandanten, bleibt die mitgeschickte Verbindung –
    dann ist alles wie bisher.
    """
    from app.services import mandant_service
    aktiv = mandant_service.aktiver(project_id, user, db)
    if aktiv is not None:
        return aktiv
    if angefragt is not None and not mandant_service.darf_nutzen(
            angefragt, user, db, project_id):
        raise HTTPException(403, "Diese Verbindung ist für Sie nicht freigegeben")
    return angefragt


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
    # Der Ausschluss gehört zu der WaWi, in der die Artikel-ID gilt – also zu
    # derselben, in der die Suche den Artikel gefunden hat.
    conn_id = _wawi_verbindung(data.project_id, data.connection_id, user, db)
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


# ─── Übernahme aus einer anderen Verbindung ──────────────────────────────────
# Wechselt ein Betrieb den SQL-Server oder legt jemand die WaWi als neue
# Verbindung an, sind die gepflegten Ausschlüsse plötzlich unsichtbar und wirkungslos:
# sie hängen an der alten Verbindung. Sie einfach umzuhängen wäre falsch – kArtikel
# ist eine interne ID der jeweiligen Datenbank und bezeichnet anderswo einen
# anderen Artikel. Deshalb wird über die ARTIKELNUMMER neu aufgelöst.

def _andere_ausschluesse(project_id, ziel_conn, user, db):
    """Ausschlüsse desselben Projekts, die an einer anderen Verbindung hängen.

    Nur aus Verbindungen, die dieser Benutzer auch sehen darf – sonst verriete die
    Übernahme die Artikelnummern eines Mandanten, für den er nicht freigegeben ist.
    """
    from app.services import mandant_service
    rows = (db.query(ArticleExclusion)
            .filter(ArticleExclusion.project_id == project_id).all())
    ist_standard = mandant_service.standard(project_id, db) == ziel_conn
    fremd = []
    for r in rows:
        eigen = (r.connection_id == ziel_conn
                 or (r.connection_id is None and ist_standard))
        if eigen:
            continue
        if not mandant_service.darf_nutzen(r.connection_id, user, db, project_id):
            continue
        fremd.append(r)
    return fremd


@router.get("/exclusions/uebertragbar")
def uebertragbar(project_id: Optional[int] = None,
                 connection_id: Optional[int] = None,
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """Liegen Ausschlüsse an einer anderen Verbindung? – für den Hinweis im Panel.

    Gezählt wird nur, was sich auch übernehmen lässt: ohne Artikelnummer gibt es
    nichts, woran der Artikel in der anderen Datenbank wiederzuerkennen wäre.
    """
    if not (can_read_project(project_id, user, db)
            or user_can_access_portal_project(project_id, user, db)):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    ziel = _wawi_verbindung(project_id, connection_id, user, db)
    if ziel is None:
        return {"quellen": [], "gesamt": 0}

    from app.services import mandant_service
    je_quelle: dict = {}
    for r in _andere_ausschluesse(project_id, ziel, user, db):
        if not (r.art_nr or "").strip():
            continue
        e = je_quelle.setdefault(r.connection_id, {"connection_id": r.connection_id,
                                                   "name": None, "anzahl": 0})
        e["anzahl"] += 1
    for cid, e in je_quelle.items():
        e["name"] = mandant_service.name_von(cid, db) or (
            f"Verbindung {cid}" if cid is not None else "ohne Verbindung")
    quellen = sorted(je_quelle.values(), key=lambda e: -e["anzahl"])
    return {"quellen": quellen, "gesamt": sum(e["anzahl"] for e in quellen)}


class UebernahmeIn(BaseModel):
    project_id: Optional[int] = None
    connection_id: Optional[int] = None           # Ziel; None = aktiver Mandant
    from_connection_id: Optional[int] = None      # None = alle Quellen


@router.post("/exclusions/uebernehmen")
def uebernehmen(data: UebernahmeIn,
                db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    """Übernimmt Ausschlüsse einer anderen Verbindung in die aktive WaWi.

    Der Abgleich läuft über cArtNr: die Artikelnummer ist das, was in beiden
    Datenbanken denselben Artikel bezeichnet. Was dort nicht existiert, wird
    gemeldet statt stillschweigend übergangen – ein Ausschluss, von dem der
    Anwender glaubt, er greife, ist schlimmer als gar keiner.
    """
    if not (getattr(user, "is_portal_only", False)
            and user_can_access_portal_project(data.project_id, user, db)):
        require_editor(data.project_id, user, db)

    ziel = _wawi_verbindung(data.project_id, data.connection_id, user, db)
    if ziel is None:
        raise HTTPException(400, "Keine JTL-Verbindung aktiv")

    quelle = _andere_ausschluesse(data.project_id, ziel, user, db)
    if data.from_connection_id is not None:
        quelle = [r for r in quelle if r.connection_id == data.from_connection_id]
    nummern = {(r.art_nr or "").strip(): r for r in quelle if (r.art_nr or "").strip()}
    if not nummern:
        return {"uebernommen": 0, "schon_vorhanden": 0, "nicht_gefunden": []}

    from sqlalchemy import text as _text, bindparam
    from app.services.sql_helpers import _get_sql_engine
    sql = _text(
        "SELECT a.kArtikel, a.cArtNr, b.cName "
        "FROM dbo.tArtikel a "
        "LEFT JOIN dbo.tArtikelBeschreibung b "
        "  ON b.kArtikel = a.kArtikel "
        "  AND b.kSprache = 1 AND b.kPlattform = 1 AND b.kShop = 0 "
        "WHERE a.cArtNr IN :nrs"
    ).bindparams(bindparam("nrs", expanding=True))
    try:
        engine = _get_sql_engine(ziel)
        with engine.connect() as con:
            treffer = con.execute(sql, {"nrs": list(nummern.keys())}).fetchall()
    except Exception as e:
        raise HTTPException(400, f"Artikel-Abgleich fehlgeschlagen: {str(e)[:200]}")

    from app.services import mandant_service as _ms
    ziel_ist_standard = _ms.standard(data.project_id, db) == ziel
    vorhanden = {r.k_artikel for r in db.query(ArticleExclusion)
                 .filter(ArticleExclusion.project_id == data.project_id).all()
                 if r.connection_id == ziel
                 or (r.connection_id is None and ziel_ist_standard)}
    neu, schon, gefunden = 0, 0, set()
    for k_artikel, art_nr, name in treffer:
        nr = (art_nr or "").strip()
        gefunden.add(nr)
        if k_artikel in vorhanden:
            schon += 1
            continue
        db.add(ArticleExclusion(project_id=data.project_id, connection_id=ziel,
                                k_artikel=k_artikel, art_nr=nr,
                                name=name or nummern[nr].name))
        vorhanden.add(k_artikel)
        neu += 1
    db.commit()

    fehlt = [{"art_nr": nr, "name": r.name} for nr, r in nummern.items()
             if nr not in gefunden]
    return {"uebernommen": neu, "schon_vorhanden": schon, "nicht_gefunden": fehlt}


# ─── Artikel-Suche gegen die JTL-DB ───────────────────────────────────────────

@router.get("/articles/search")
def search_articles(connection_id: Optional[int] = None,
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

    connection_id = _wawi_verbindung(project_id, connection_id, user, db)
    if connection_id is None:
        raise HTTPException(400, "Keine JTL-Verbindung gewählt")

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
