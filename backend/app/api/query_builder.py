"""Abfrage-Generator: Katalog ausliefern, Vorschau rechnen.

Der Client schickt nie SQL, sondern nur eine Definition aus Schlüsseln des
serverseitigen Katalogs. Alles hier ist lesend.
"""
import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.services.query_builder import katalog, sql_bauer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/query", tags=["query-builder"])

VORSCHAU_MAX = 200


def _check_editor(user: User):
    if getattr(user, "is_portal_only", False):
        raise HTTPException(403, "Nur Admins und Editoren können Abfragen bauen")


def _projekt_pruefen(db, project_id, user: User, schreiben: bool, erstellt_von=None) -> None:
    """Der Mandant wird aus dem Projekt aufgelöst – mit fremder project_id liefe
    die Abfrage sonst gegen die Wawi eines anderen Projekts. Ohne Projekt:
    neue Abfragen erlaubt, bestehende nur für den, der sie angelegt hat."""
    from app.core.zugriff import ist_admin, lesen_pruefen, schreiben_pruefen
    if ist_admin(user) or project_id is None and (
            erstellt_von is None or erstellt_von == user.id):
        return
    (schreiben_pruefen if schreiben else lesen_pruefen)(project_id, user, db)


def _mandant_pruefen(db, mandant_id, project_id, user: User) -> None:
    """Frei übergebene mandant_id = beliebige Verbindung; nur freigegebene."""
    from app.core.zugriff import ist_admin, verbindung_pruefen
    from app.services import mandant_service
    if ist_admin(user) or not mandant_id:
        return
    if not mandant_service.darf_nutzen(mandant_id, user, db, project_id):
        raise HTTPException(403, "Dieser Mandant ist für Sie nicht freigegeben")
    verbindung_pruefen(mandant_id, user, db)


def _lade_abfrage(db, query_id: int, user: User, schreiben: bool = False):
    from app.models.report import AdHocQuery
    q = db.query(AdHocQuery).filter(AdHocQuery.id == query_id).first()
    if not q:
        raise HTTPException(404, "Auswertung nicht gefunden")
    _projekt_pruefen(db, q.project_id, user, schreiben, erstellt_von=q.created_by or -1)
    return q


class VorschauRequest(BaseModel):
    definition: dict
    project_id: Optional[int] = None
    mandant_id: Optional[int] = None
    von: Optional[str] = None
    bis: Optional[str] = None


@router.get("/schema")
def schema(user: User = Depends(get_current_user)):
    """Körnungen, Felder, Kennzahlen und die je Typ erlaubten Vergleiche."""
    _check_editor(user)
    return katalog.schema()


@router.post("/preview")
def preview(data: VorschauRequest, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    """Rechnet die Abfrage mit Zeilenobergrenze und gibt auch das SQL zurück.

    Das erzeugte SQL wird bewusst mitgeliefert: wer es lesen kann, prüft es;
    wer nicht, sieht wenigstens, dass nichts gezaubert wird.
    """
    _check_editor(user)
    from app.services import mandant_service
    from app.services.query_builder import ausfuehren

    # Der Mandant bestimmt, gegen welche Wawi gerechnet wird. Ohne ihn liefe die
    # Vorschau womöglich gegen den anderen Betrieb – Zahlen, die in sich stimmen
    # und trotzdem falsch sind.
    _projekt_pruefen(db, data.project_id, user, False)
    _mandant_pruefen(db, data.mandant_id, data.project_id, user)
    mandant_id = data.mandant_id or mandant_service.aktiver(data.project_id, user, db)
    if not mandant_id:
        raise HTTPException(400, "Kein Mandant gewählt – es ist unklar, gegen welche "
                                 "Warenwirtschaft gerechnet werden soll.")

    try:
        return ausfuehren.rechnen(db, data.definition or {}, mandant_id,
                                  von=data.von, bis=data.bis)
    except sql_bauer.AbfrageFehler as e:
        raise HTTPException(400, str(e))
    except ausfuehren.LaufFehler as e:
        raise HTTPException(500, str(e))


# ── Speichern ────────────────────────────────────────────────────────────────

class SpeichernRequest(BaseModel):
    name: str
    definition: dict
    project_id: Optional[int] = None
    mandant_id: Optional[int] = None
    beschreibung: Optional[str] = None


def _abfrage_out(q, form_id=None) -> dict:
    return {
        "id": q.id, "name": q.name, "beschreibung": q.beschreibung,
        "project_id": q.project_id, "koernung": q.koernung,
        "definition": q.definition or {}, "mapping_id": q.mapping_id,
        "form_id": q.form_id, "widget_ids": q.widget_ids or [],
    }


@router.get("/list")
def liste(project_id: Optional[int] = None, db: Session = Depends(get_db),
          user: User = Depends(get_current_user)):
    _check_editor(user)
    from app.models.report import AdHocQuery
    q = db.query(AdHocQuery)
    if project_id is not None:
        q = q.filter(AdHocQuery.project_id == project_id)
    raus = []
    for x in q.order_by(AdHocQuery.id.desc()).all():
        try:
            _projekt_pruefen(db, x.project_id, user, False, erstellt_von=x.created_by or -1)
        except HTTPException:
            continue  # Auswertungen fremder Projekte nicht zeigen
        raus.append(_abfrage_out(x))
    return raus


@router.post("/save")
def speichern(data: SpeichernRequest, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    """Legt Mapping und Bausteine an. Die Abfrage taucht danach im
    Report-Baukasten unter „Eigene Auswertungen" auf."""
    _check_editor(user)
    from app.core.database import safe_commit
    from app.models.report import AdHocQuery
    from app.services import mandant_service
    from app.services.query_builder import erzeugen

    _projekt_pruefen(db, data.project_id, user, True)
    _mandant_pruefen(db, data.mandant_id, data.project_id, user)
    mandant_id = data.mandant_id or mandant_service.aktiver(data.project_id, user, db)
    if not mandant_id:
        raise HTTPException(400, "Kein Mandant gewählt.")

    try:
        gebaut = erzeugen.speichern(db, data.name, data.definition,
                                    data.project_id, mandant_id)
    except sql_bauer.AbfrageFehler as e:
        raise HTTPException(400, str(e))

    q = AdHocQuery(
        name=data.name.strip(), beschreibung=data.beschreibung,
        project_id=data.project_id,
        koernung=(data.definition or {}).get("koernung") or "kunde",
        definition=data.definition or {},
        mapping_id=gebaut["mapping"].id, verlauf_mapping_id=gebaut.get("verlauf_mapping_id"),
        form_id=gebaut["form"].id,
        widget_ids=gebaut["widget_ids"], created_by=user.id,
    )
    db.add(q)
    safe_commit(db)
    db.refresh(q)

    return {**_abfrage_out(q),
            "form_name": gebaut["form"].name,
            "spalten": len(gebaut["spalten"])}


@router.get("/{query_id}")
def holen(query_id: int, db: Session = Depends(get_db),
          user: User = Depends(get_current_user)):
    """Die gespeicherte Definition, um den Generator damit zu öffnen."""
    _check_editor(user)
    return _abfrage_out(_lade_abfrage(db, query_id, user))


@router.put("/{query_id}")
def aktualisieren(query_id: int, data: SpeichernRequest,
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """Ändert eine gespeicherte Auswertung.

    Mapping und Bausteine werden ersetzt, nicht danebengelegt – ein Report, der
    den Baustein schon verwendet, zeigt danach die neue Fassung.
    """
    _check_editor(user)
    from app.core.database import safe_commit
    from app.models.report import AdHocQuery
    from app.services import mandant_service
    from app.services.query_builder import erzeugen

    q = _lade_abfrage(db, query_id, user, schreiben=True)
    _mandant_pruefen(db, data.mandant_id, q.project_id, user)

    mandant_id = data.mandant_id or mandant_service.aktiver(q.project_id, user, db)
    if not mandant_id:
        raise HTTPException(400, "Kein Mandant gewählt.")

    try:
        gebaut = erzeugen.speichern(db, data.name or q.name, data.definition,
                                    q.project_id, mandant_id, vorhandene=q)
    except sql_bauer.AbfrageFehler as e:
        raise HTTPException(400, str(e))

    q.name = (data.name or q.name).strip()
    q.definition = data.definition or {}
    q.koernung = (data.definition or {}).get("koernung") or q.koernung
    q.mapping_id = gebaut["mapping"].id
    q.verlauf_mapping_id = gebaut.get("verlauf_mapping_id")
    q.form_id = gebaut["form"].id
    q.widget_ids = gebaut["widget_ids"]
    safe_commit(db)
    db.refresh(q)
    return {**_abfrage_out(q), "form_name": gebaut["form"].name}


@router.delete("/{query_id}")
def loeschen(query_id: int, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    """Entfernt die Auswertung samt Bausteinen und Mappings."""
    _check_editor(user)
    from app.core.database import safe_commit
    from app.models.report import AdHocQuery
    from app.services.query_builder import erzeugen

    q = _lade_abfrage(db, query_id, user, schreiben=True)
    name = q.name
    entfernt = erzeugen.entfernen(db, q)
    safe_commit(db)
    return {"ok": True, "name": name, **entfernt}
