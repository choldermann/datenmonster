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


def _verbindung_aufloesen(connection_id: int, user: User, db: Session) -> int:
    """Wer darf hier arbeiten – und an WELCHER Wawi?

    Zwei Fragen, die auseinandergehalten werden müssen:

    1. **Darf der Benutzer überhaupt?** Gesteuert über die Formular-Veröffent-
       lichung, nicht über die Benutzerrolle: ein Portal-Benutzer darf, wenn ein
       für ihn freigegebenes Formular diese Verbindung in einem „debitoren“-Widget
       führt. Dieselbe Prüfung nutzt der Eingangsrechnungs-Import, der ganze
       Rechnungen schreibt — das Nachpflegen einer Debitorennummer ist der
       kleinere Eingriff, und genau die Buchhaltung, die es braucht, arbeitet oft
       nur im Portal.

    2. **In welche Wawi?** ⭐ Die Verbindung aus der Widget-Konfiguration ist nur
       die Vorgabe. Die Reiter dieses Formulars folgen dem Mandanten-Umschalter
       (das erledigt der Mapping-Pfad selbst), und die Kunden-IDs, die das Widget
       anzeigt, stammen deshalb aus der Datenbank des AKTIVEN Mandanten. Bliebe
       das Schreiben bei der Vorgabe, träfen dieselben IDs in der anderen Wawi
       wildfremde Kunden. Also folgt auch der Schreibpfad dem Umschalter — und
       gegen dessen Ziel wird die Mandantenfreigabe geprüft.
    """
    from app.api.eingangsrechnung import _check_connection_access
    from app.models.dataset import DbConnection
    from app.services import mandant_service

    _check_connection_access(connection_id, user, db, widget_types=("debitoren",))
    conn = db.query(DbConnection).filter(DbConnection.id == connection_id).first()
    if not conn:
        raise HTTPException(404, f"Verbindung {connection_id} gibt es nicht")
    ziel = mandant_service.schreibziel(connection_id, conn.project_id, user, db)
    if not mandant_service.darf_nutzen(ziel, user, db, conn.project_id):
        raise HTTPException(403, "Für diesen Mandanten nicht freigegeben")
    return ziel


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
    ziel = _verbindung_aufloesen(req.connection_id, user, db)
    from app.services import mandant_service
    return {"faelle": _writer(ziel).offene_faelle(req.year, req.month),
            "connection_id": ziel,
            "wawi": mandant_service.name_von(ziel, db)}


@router.post("/debitoren-schreiben")
def debitoren_schreiben(req: SchreibenRequest, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """Setzt die Debitorennummern. Ohne `bestaetigt` nur eine Vorschau.

    Auch mit Bestätigung wird jede Zeile noch einmal frisch geprüft: der Kunde
    darf keine Nummer haben, die Nummer muss frei sein. Zwischen dem Anzeigen der
    Liste und dem Klick kann in der Wawi gearbeitet worden sein.
    """
    ziel = _verbindung_aufloesen(req.connection_id, user, db)
    w = _writer(ziel)
    kunden = [k.model_dump() for k in req.kunden]
    plan = w.build_plan(kunden, dry_run=not req.bestaetigt)
    if req.bestaetigt:
        protokolliere(db, user, ziel, plan)
    ergebnis = plan.to_dict()
    ergebnis["connection_id"] = ziel
    return ergebnis
