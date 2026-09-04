# -*- coding: utf-8 -*-
"""API für den DATEV-Export: Debitorennummern nachpflegen.

Zwei Endpunkte, bewusst zweistufig wie bei den Artikelstammdaten: erst zeigen,
was passieren würde, dann – mit ausdrücklicher Bestätigung – schreiben.

Geschrieben wird ausschließlich `tkunde.nDebitorennr`, siehe jtl_kunde_writer.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.services.jtl_kunde_writer import KundeWriter, protokolliere

router = APIRouter(prefix="/api/datev", tags=["datev"])


def _pruefe_zugriff(connection_id: int, user: User, db: Session) -> None:
    """Wer darf an dieser Wawi Debitorennummern setzen?

    Gesteuert über die Formular-Veröffentlichung, nicht über die Benutzerrolle:
    ein Portal-Benutzer darf, wenn ein für ihn freigegebenes Formular diese
    Verbindung in einem „debitoren“-Widget führt. Dieselbe Prüfung nutzt der
    Eingangsrechnungs-Import, der ganze Rechnungen in die Wawi schreibt – das
    Nachpflegen einer Debitorennummer ist der deutlich kleinere Eingriff, und
    genau die Buchhaltung, die es braucht, arbeitet oft nur im Portal.
    """
    from app.api.eingangsrechnung import _check_connection_access
    _check_connection_access(connection_id, user, db, widget_types=("debitoren",))


def _writer(connection_id: int) -> KundeWriter:
    try:
        return KundeWriter(connection_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


class OffeneRequest(BaseModel):
    connection_id: int
    year: int
    month: int


class KundeEintrag(BaseModel):
    kKunde: int
    nummer: int


class SchreibenRequest(BaseModel):
    connection_id: int
    kunden: List[KundeEintrag]
    bestaetigt: bool = False


@router.post("/debitoren-offen")
def debitoren_offen(req: OffeneRequest, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """Kunden mit Umsatz im Zeitraum, die keine Debitorennummer führen."""
    _pruefe_zugriff(req.connection_id, user, db)
    return {"faelle": _writer(req.connection_id).offene_faelle(req.year, req.month)}


@router.post("/debitoren-schreiben")
def debitoren_schreiben(req: SchreibenRequest, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """Setzt die Debitorennummern. Ohne `bestaetigt` nur eine Vorschau.

    Auch mit Bestätigung wird jede Zeile noch einmal frisch geprüft: der Kunde
    darf keine Nummer haben, die Nummer muss frei sein. Zwischen dem Anzeigen der
    Liste und dem Klick kann in der Wawi gearbeitet worden sein.
    """
    _pruefe_zugriff(req.connection_id, user, db)
    w = _writer(req.connection_id)
    kunden = [k.model_dump() for k in req.kunden]
    plan = w.build_plan(kunden, dry_run=not req.bestaetigt)
    if req.bestaetigt:
        protokolliere(db, user, req.connection_id, plan)
    return plan.to_dict()
