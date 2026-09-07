"""Kunden-Ausschlussliste – verbundene Unternehmen aus Auswertungen nehmen.

Wozu: Wer wissen will, welche Kunden einen Artikel wirklich kaufen, muss die
Lieferungen an die eigene Firma und an Schwestergesellschaften ausblenden. Sonst
steht der Konzern mengenmäßig ganz oben und verdeckt das echte Kundenbild. JTL
kennt dafür kein Kennzeichen – die Liste wird hier gepflegt und beim Mapping-Lauf
als :excluded_customers injiziert (customer_exclusion_service).

Aufbau bewusst identisch zur Artikel-Ausschlussliste in intrastat.py – wer die
eine kennt, findet sich in der anderen sofort zurecht.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.customer_exclusion import CustomerExclusion
from app.api.projects import can_read_project, require_editor
from app.api.portal import user_can_access_portal_project

router = APIRouter(prefix="/api/kunden-ausschluss", tags=["kunden-ausschluss"])


def _out(e: CustomerExclusion) -> dict:
    return {
        "id": e.id,
        "project_id": e.project_id,
        "connection_id": e.connection_id,
        "k_kunde": e.k_kunde,
        "kunden_nr": e.kunden_nr,
        "name": e.name,
        "grund": e.grund,
    }


@router.get("")
def list_exclusions(project_id: Optional[int] = None,
                    db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    if not (can_read_project(project_id, user, db)
            or user_can_access_portal_project(project_id, user, db)):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    q = db.query(CustomerExclusion)
    if project_id is not None:
        q = q.filter(CustomerExclusion.project_id == project_id)
    else:
        q = q.filter(CustomerExclusion.project_id.is_(None))
    rows = q.order_by(CustomerExclusion.name.asc()).all()
    # kKunde ist eine interne ID der jeweiligen WaWi – nur die Einträge des
    # aktiven Mandanten zeigen. Alteinträge ohne Verbindung gehören dem
    # Standard-Mandanten, weil es damals nur einen gab.
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
    k_kunde: int
    kunden_nr: Optional[str] = None
    name: Optional[str] = None
    grund: Optional[str] = None


@router.post("")
def add_exclusion(data: ExclusionIn,
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    if not (getattr(user, "is_portal_only", False)
            and user_can_access_portal_project(data.project_id, user, db)):
        require_editor(data.project_id, user, db)
    from app.services import mandant_service
    conn_id = data.connection_id or mandant_service.aktiver(data.project_id, user, db)
    existing = (db.query(CustomerExclusion)
                .filter(CustomerExclusion.project_id == data.project_id,
                        CustomerExclusion.k_kunde == data.k_kunde,
                        CustomerExclusion.connection_id == conn_id)
                .first())
    if existing:
        existing.kunden_nr = data.kunden_nr or existing.kunden_nr
        existing.name = data.name or existing.name
        if data.grund is not None:
            existing.grund = data.grund
        db.commit()
        return _out(existing)
    e = CustomerExclusion(
        project_id=data.project_id,
        connection_id=conn_id,
        k_kunde=data.k_kunde,
        kunden_nr=data.kunden_nr,
        name=data.name,
        grund=data.grund,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return _out(e)


@router.delete("/{excl_id}")
def delete_exclusion(excl_id: int,
                     db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    e = db.query(CustomerExclusion).filter(CustomerExclusion.id == excl_id).first()
    if not e:
        raise HTTPException(404, "Eintrag nicht gefunden")
    if not (getattr(user, "is_portal_only", False)
            and user_can_access_portal_project(e.project_id, user, db)):
        require_editor(e.project_id, user, db)
    db.delete(e)
    db.commit()
    return {"ok": True}


@router.get("/kunden/suche")
def search_customers(connection_id: Optional[int] = None,
                     q: str = Query("", min_length=0),
                     project_id: Optional[int] = None,
                     limit: int = 40,
                     db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """Sucht Kunden (kKunde, cKundenNr, Firma/Name) in der JTL-WaWi.

    Der Name kommt aus der Rechnungsadresse, nicht aus tkunde – dort gibt es
    keine Namensspalten. `cZusatz` wird angehängt, weil bei manchen Betrieben
    in cFirma nur eine Gattung steht („Zahnarztpraxis") und der echte Name im
    Zusatz.
    """
    if not (can_read_project(project_id, user, db)
            or user_can_access_portal_project(project_id, user, db)):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")

    # Ohne Angabe die WaWi des aktiven Mandanten – die Oberfläche muss die
    # Verbindung dann nicht selbst kennen und kann sie auch nicht verwechseln.
    from app.services import mandant_service
    if connection_id is None:
        connection_id = mandant_service.aktiver(project_id, user, db)
    if connection_id is None:
        raise HTTPException(400, "Keine Datenbankverbindung (Mandant) bestimmbar.")

    from sqlalchemy import text as _text
    from app.services.sql_helpers import _get_sql_engine

    term = (q or "").strip()
    like = f"%{term}%"
    limit = max(1, min(int(limit or 40), 200))
    sql = _text(
        f"SELECT TOP {limit} k.kKunde, k.cKundenNr, "
        "  LTRIM(RTRIM(ISNULL(NULLIF(adr.cFirma,''),'') + ' ' "
        "        + ISNULL(NULLIF(adr.cZusatz,''),''))) AS firma, "
        "  LTRIM(RTRIM(ISNULL(adr.cVorname,'') + ' ' + ISNULL(adr.cName,''))) AS person, "
        "  adr.cOrt "
        "FROM dbo.tkunde k "
        "OUTER APPLY (SELECT TOP 1 a.cFirma, a.cZusatz, a.cVorname, a.cName, a.cOrt "
        "             FROM dbo.tAdresse a WHERE a.kKunde = k.kKunde AND a.nTyp = 1 "
        "             ORDER BY a.nStandard DESC, a.kAdresse) adr "
        "WHERE :term = '' OR k.cKundenNr LIKE :like OR adr.cFirma LIKE :like "
        "   OR adr.cZusatz LIKE :like OR adr.cName LIKE :like "
        "ORDER BY adr.cFirma, adr.cName"
    )
    try:
        engine = _get_sql_engine(connection_id)
        with engine.connect() as con:
            rows = con.execute(sql, {"term": term, "like": like}).fetchall()
    except Exception as e:
        raise HTTPException(400, f"Kundensuche fehlgeschlagen: {str(e)[:200]}")

    out = []
    for r in rows:
        firma = (r[2] or "").strip()
        person = (r[3] or "").strip()
        name = firma or person
        if firma and person and person.lower() not in firma.lower():
            name = f"{firma} ({person})"
        out.append({"k_kunde": r[0], "kunden_nr": r[1], "name": name, "ort": r[4]})
    return out
