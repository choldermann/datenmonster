"""API für den Posteingang der Eingangsrechnungen.

Quellen verwalten darf nur ein Admin: dort stehen Zugangsdaten, und eine falsch
gesetzte Quelle wuerde Belege in den falschen Mandanten schuetten. Die Belege
selbst darf jeder sehen, der auch die Rechnung freigeben duerfte — dieselbe
Pruefung wie im Import.
"""
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.api.eingangsrechnung import _check_connection_access
from app.core.database import get_db
from app.core.security import encrypt_credential
from app.models.er_posteingang import ErPosteingangBeleg, ErPosteingangQuelle
from app.models.user import User
from app.services import er_posteingang_service as dienst
from app.services.scheduler_service import (register_er_posteingang_job,
                                            unregister_er_posteingang_job)

router = APIRouter(prefix="/api/er-posteingang", tags=["er-posteingang"])

GEHEIM = "********"


def _nur_admin(user: User) -> None:
    if not getattr(user, "is_admin", False):
        raise HTTPException(403, "Nur Administratoren dürfen Posteingangs-Quellen verwalten")


class QuelleBody(BaseModel):
    name: str
    art: str = "imap"                    # imap | ordner
    aktiv: bool = True
    mandant_id: int
    project_id: Optional[int] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None       # GEHEIM = unveraendert lassen
    ssl: bool = True
    ordner: Optional[str] = "INBOX"
    nach_abholung: str = "gelesen"
    ziel_ordner: Optional[str] = None
    pfad: Optional[str] = None
    endungen: str = ".xml,.pdf"
    cron_expr: Optional[str] = None


def _raus(q: ErPosteingangQuelle) -> dict:
    return {
        "id": q.id, "name": q.name, "art": q.art, "aktiv": bool(q.aktiv),
        "mandant_id": q.mandant_id, "project_id": q.project_id,
        "host": q.host, "port": q.port, "username": q.username,
        "password": GEHEIM if q.password else "", "ssl": bool(q.ssl),
        "ordner": q.ordner, "nach_abholung": q.nach_abholung,
        "ziel_ordner": q.ziel_ordner, "pfad": q.pfad, "endungen": q.endungen,
        "cron_expr": q.cron_expr,
        "letzter_lauf": q.letzter_lauf.isoformat() if q.letzter_lauf else None,
        "letzter_status": q.letzter_status, "letzter_fehler": q.letzter_fehler,
    }


@router.get("/quellen")
def quellen(mandant_id: Optional[int] = None, user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    _nur_admin(user)
    q = db.query(ErPosteingangQuelle)
    if mandant_id:
        q = q.filter(ErPosteingangQuelle.mandant_id == mandant_id)
    return [_raus(x) for x in q.order_by(ErPosteingangQuelle.id).all()]


@router.post("/quellen")
def quelle_anlegen(body: QuelleBody, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    _nur_admin(user)
    daten = body.model_dump()
    passwort = daten.pop("password", None)
    quelle = ErPosteingangQuelle(**daten)
    if passwort and passwort != GEHEIM:
        quelle.password = encrypt_credential(passwort)
    db.add(quelle)
    db.commit()
    db.refresh(quelle)
    if quelle.aktiv:
        register_er_posteingang_job(quelle.id, quelle.cron_expr or "")
    return _raus(quelle)


@router.put("/quellen/{quelle_id}")
def quelle_aendern(quelle_id: int, body: QuelleBody, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    _nur_admin(user)
    quelle = db.query(ErPosteingangQuelle).filter(ErPosteingangQuelle.id == quelle_id).first()
    if not quelle:
        raise HTTPException(404, "Quelle gibt es nicht")
    daten = body.model_dump()
    passwort = daten.pop("password", None)
    for feld, wert in daten.items():
        setattr(quelle, feld, wert)
    # Das Kennwort kommt nur als Sternchen zurueck; wer es nicht aendert,
    # schickt die Sternchen wieder – die duerfen es nicht ueberschreiben.
    if passwort and passwort != GEHEIM:
        quelle.password = encrypt_credential(passwort)
    db.commit()
    if quelle.aktiv:
        register_er_posteingang_job(quelle.id, quelle.cron_expr or "")
    else:
        unregister_er_posteingang_job(quelle.id)
    return _raus(quelle)


@router.delete("/quellen/{quelle_id}")
def quelle_loeschen(quelle_id: int, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    _nur_admin(user)
    quelle = db.query(ErPosteingangQuelle).filter(ErPosteingangQuelle.id == quelle_id).first()
    if not quelle:
        raise HTTPException(404, "Quelle gibt es nicht")
    unregister_er_posteingang_job(quelle_id)
    db.delete(quelle)
    db.commit()
    return {"geloescht": quelle_id}


@router.post("/quellen/{quelle_id}/abholen")
def quelle_abholen(quelle_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    _nur_admin(user)
    quelle = db.query(ErPosteingangQuelle).filter(ErPosteingangQuelle.id == quelle_id).first()
    if not quelle:
        raise HTTPException(404, "Quelle gibt es nicht")
    return dienst.abholen(db, quelle)


@router.post("/abholen")
def alle_abholen(mandant_id: Optional[int] = None, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """Alle aktiven Quellen eines Mandanten abfragen (Knopf in der Oberfläche)."""
    if mandant_id:
        _check_connection_access(mandant_id, user, db)
    else:
        _nur_admin(user)
    return {"quellen": dienst.alle_abholen(db, mandant_id)}


# ── Belege ────────────────────────────────────────────────────────────────────

@router.get("/belege")
def belege(mandant_id: int, status: str = "neu", limit: int = 100,
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _check_connection_access(mandant_id, user, db)
    q = db.query(ErPosteingangBeleg).filter(ErPosteingangBeleg.mandant_id == mandant_id)
    if status != "alle":
        q = q.filter(ErPosteingangBeleg.status == status)
    zeilen = q.order_by(ErPosteingangBeleg.id.desc()).limit(min(limit, 500)).all()
    return [{
        "id": b.id, "dateiname": b.dateiname, "groesse": b.groesse,
        "absender": b.absender, "betreff": b.betreff, "status": b.status,
        "empfangen_am": b.empfangen_am.isoformat() if b.empfangen_am else None,
        "kEingangsrechnung": b.kEingangsrechnung, "notiz": b.notiz,
        "quelle_id": b.quelle_id,
    } for b in zeilen]


@router.get("/belege/{beleg_id}/datei")
def beleg_datei(beleg_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """Die Originaldatei – fürs Ansehen im Beleg-Modal."""
    beleg = db.query(ErPosteingangBeleg).filter(ErPosteingangBeleg.id == beleg_id).first()
    if not beleg:
        raise HTTPException(404, "Beleg gibt es nicht")
    _check_connection_access(beleg.mandant_id, user, db)
    pfad = Path(beleg.pfad)
    if not pfad.is_file():
        raise HTTPException(410, "Die Datei liegt nicht mehr im Posteingang")
    typ = "application/pdf" if pfad.suffix.lower() == ".pdf" else "application/xml"
    return FileResponse(str(pfad), media_type=typ, filename=beleg.dateiname)


class StatusBody(BaseModel):
    status: str                          # neu | erledigt | verworfen
    notiz: Optional[str] = None
    kEingangsrechnung: Optional[int] = None


@router.post("/belege/{beleg_id}/status")
def beleg_status(beleg_id: int, body: StatusBody, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    beleg = db.query(ErPosteingangBeleg).filter(ErPosteingangBeleg.id == beleg_id).first()
    if not beleg:
        raise HTTPException(404, "Beleg gibt es nicht")
    _check_connection_access(beleg.mandant_id, user, db)
    if body.status not in ("neu", "erledigt", "verworfen"):
        raise HTTPException(422, "status muss neu, erledigt oder verworfen sein")
    beleg.status = body.status
    if body.notiz is not None:
        beleg.notiz = body.notiz[:500]
    if body.kEingangsrechnung:
        beleg.kEingangsrechnung = body.kEingangsrechnung
    db.commit()
    return {"id": beleg.id, "status": beleg.status}
