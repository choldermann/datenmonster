"""Mandanten: welche WaWi-Datenbank ein Cockpit gerade auswertet.

Drei Dinge lassen sich hier steuern:
  * welche Verbindungen überhaupt Mandanten sind (Admin)
  * welcher Benutzer welche davon nutzen darf (Admin)
  * welchen ein Benutzer gerade ansieht (jeder für sich)

Der Umschalter im Portal spricht nur die letzte Gruppe an; alles andere ist
Verwaltung und braucht Administratorrechte.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.dataset import DbConnection
from app.services import mandant_service

router = APIRouter(prefix="/api/mandanten", tags=["mandanten"])


def _admin(user: User):
    if not getattr(user, "is_admin", False):
        raise HTTPException(403, "Nur Administratoren dürfen Mandanten verwalten")


# ── Anzeige und Umschalten ───────────────────────────────────────────────────

@router.get("")
def liste(project_id: Optional[int] = None, db: Session = Depends(get_db),
          user: User = Depends(get_current_user)):
    """Die für diesen Benutzer nutzbaren Mandanten plus der gerade aktive.

    Auch für Portal-Benutzer zugänglich: der Umschalter in der Kopfzeile ist
    genau das, was sie brauchen, und mehr als Name und ID gibt die Antwort nicht
    preis – keine Zugangsdaten, kein Host.
    """
    mandanten = mandant_service.erlaubte(project_id, user, db)
    aktiv = mandant_service.aktiver(project_id, user, db)
    return {
        "project_id": project_id,
        "aktiv": aktiv,
        "mandanten": [{"connection_id": m["connection_id"], "name": m["name"],
                       "ist_standard": m["ist_standard"]} for m in mandanten],
    }


class AuswahlIn(BaseModel):
    project_id: Optional[int] = None
    connection_id: int


@router.put("/aktiv")
def aktiv_setzen(body: AuswahlIn, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """Mandant wechseln. Gilt nur für diesen Benutzer und bleibt gespeichert."""
    mid = mandant_service.waehlen(body.project_id, user, body.connection_id, db)
    return {"aktiv": mid, "name": mandant_service.name_von(mid, db)}


# ── Verwaltung: welche Verbindung ist ein Mandant ────────────────────────────

def _verwaltung_out(c: DbConnection) -> dict:
    return {
        "connection_id": c.id, "verbindung": c.name, "datenbank": c.database,
        "project_id": c.project_id,
        "is_mandant": bool(getattr(c, "is_mandant", False)),
        "mandant_label": getattr(c, "mandant_label", None) or "",
        "ist_standard": bool(getattr(c, "is_mandant_default", False)),
        "sort": getattr(c, "mandant_sort", 100) or 100,
    }


@router.get("/verwaltung")
def verwaltung(project_id: Optional[int] = None, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """Alle Verbindungen mit ihrer Mandanten-Kennzeichnung."""
    _admin(user)
    q = db.query(DbConnection)
    if project_id is not None:
        q = q.filter(DbConnection.project_id == project_id)
    return [_verwaltung_out(c) for c in q.order_by(DbConnection.id.asc()).all()]


class MandantIn(BaseModel):
    connection_id: int
    is_mandant: bool = True
    mandant_label: Optional[str] = None
    ist_standard: bool = False
    sort: Optional[int] = None


@router.put("/verwaltung")
def verwaltung_setzen(body: MandantIn, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """Verbindung als Mandant kennzeichnen (oder die Kennzeichnung entfernen).

    Beim Setzen des Standard-Mandanten werden die bisher projektweiten Fixkosten
    und ein verwaister Nachtlauf einmalig ihm zugeschlagen. Vor der
    Mandantenfähigkeit gab es nur einen Betrieb – diese Daten gehören ihm, und
    ohne die Übernahme stünde die Kostenmaske nach dem Update leer da.
    """
    _admin(user)
    c = db.query(DbConnection).filter(DbConnection.id == body.connection_id).first()
    if not c:
        raise HTTPException(404, "Verbindung nicht gefunden")

    c.is_mandant = bool(body.is_mandant)
    c.mandant_label = (body.mandant_label or "").strip() or None
    if body.sort is not None:
        c.mandant_sort = body.sort

    uebernommen = {"kosten": 0, "zeitplan": 0}
    if body.is_mandant and body.ist_standard:
        # Standard ist eine Auszeichnung, die nur einmal je Projekt vergeben wird.
        for other in db.query(DbConnection).filter(
                DbConnection.project_id == c.project_id,
                DbConnection.id != c.id).all():
            other.is_mandant_default = False
        c.is_mandant_default = True
    elif not body.ist_standard:
        c.is_mandant_default = False
    db.commit()

    if c.is_mandant and c.is_mandant_default:
        from app.services.business_config_service import altdaten_uebernehmen
        uebernommen["kosten"] = altdaten_uebernehmen(c.project_id, db, c.id, "cost")
        uebernommen["zeitplan"] = _zeitplan_uebernehmen(c.project_id, c.id, db)

    return {**_verwaltung_out(c), "uebernommen": uebernommen}


def _zeitplan_uebernehmen(project_id: Optional[int], mandant_id: int, db) -> int:
    """Verwaisten Nachtlauf (ohne Mandant) dem Standard-Mandanten zuordnen."""
    from app.models.alert import AlertSchedule
    q = db.query(AlertSchedule).filter(AlertSchedule.mandant_id.is_(None))
    q = q.filter(AlertSchedule.project_id == project_id) if project_id is not None \
        else q.filter(AlertSchedule.project_id.is_(None))
    n = 0
    for s in q.all():
        s.mandant_id = mandant_id
        n += 1
    if n:
        db.commit()
    return n


# ── Verwaltung: wer darf welchen Mandanten ───────────────────────────────────

@router.get("/freigaben")
def freigaben(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Je Benutzer die freigegebenen Mandanten. Leere Liste = alle (keine Grenze)."""
    _admin(user)
    from app.models.mandant import MandantFreigabe
    je_user: dict = {}
    for r in db.query(MandantFreigabe).all():
        je_user.setdefault(r.user_id, []).append(r.connection_id)
    users = db.query(User).order_by(User.username.asc()).all()
    return [{"user_id": u.id, "username": u.username,
             "is_admin": bool(getattr(u, "is_admin", False)),
             "mandanten": sorted(je_user.get(u.id, []))} for u in users]


class FreigabeIn(BaseModel):
    user_id: int
    mandanten: List[int] = []


@router.put("/freigaben")
def freigaben_setzen(body: FreigabeIn, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """Freigaben eines Benutzers ersetzen. Leere Liste hebt die Einschränkung auf."""
    _admin(user)
    from app.models.mandant import MandantFreigabe, MandantAuswahl
    ziel = db.query(User).filter(User.id == body.user_id).first()
    if not ziel:
        raise HTTPException(404, "Benutzer nicht gefunden")

    db.query(MandantFreigabe).filter(MandantFreigabe.user_id == body.user_id).delete()
    for cid in dict.fromkeys(body.mandanten or []):
        db.add(MandantFreigabe(user_id=body.user_id, connection_id=cid))
    # Eine gespeicherte Auswahl, die gerade entzogen wurde, muss weg – sonst
    # zeigte das Cockpit beim nächsten Aufruf noch die alte Wahl an.
    if body.mandanten:
        for a in db.query(MandantAuswahl).filter(MandantAuswahl.user_id == body.user_id).all():
            if a.connection_id not in body.mandanten:
                db.delete(a)
    db.commit()
    return {"user_id": body.user_id, "mandanten": sorted(dict.fromkeys(body.mandanten or []))}
