"""Naechtliche Pruefung: laufen unsere Vorlagen noch auf allen JTL-Staenden?

Nur fuer Administratoren - der Lauf oeffnet jede JTL-Verbindung dieser Installation
und sagt etwas ueber das Produkt aus, nicht ueber ein einzelnes Projekt.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.api.auth import get_current_user
from app.api.settings import get_setting, set_setting
from app.core.database import get_db
from app.models.user import User
from app.services import vorlagen_pruefung as vp

router = APIRouter(prefix="/api/vorlagen-pruefung", tags=["vorlagen-pruefung"])


def _admin(user: User):
    if not getattr(user, "is_admin", False):
        raise HTTPException(403, "Nur Administratoren")


class Einstellungen(BaseModel):
    aktiv: bool = False
    cron: str = vp.STANDARD_CRON
    empfaenger: str = ""


@router.get("/einstellungen")
def lies_einstellungen(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    return {
        "aktiv": (get_setting(db, vp.SCHLUESSEL_AKTIV, "0") or "0") == "1",
        "cron": get_setting(db, vp.SCHLUESSEL_CRON, vp.STANDARD_CRON),
        "empfaenger": get_setting(db, vp.SCHLUESSEL_EMPFAENGER, "") or "",
        "stand": vp._stand_lesen(db),
        # Welche Datenbanken vertreten gerade welche JTL-Version - beantwortet die
        # erste Rueckfrage ("wogegen prueft das eigentlich?") ohne Suche.
        "referenzen": vp.referenz_verbindungen(db),
    }


@router.put("/einstellungen")
def schreib_einstellungen(body: Einstellungen, db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)):
    _admin(user)
    set_setting(db, vp.SCHLUESSEL_AKTIV, "1" if body.aktiv else "0")
    set_setting(db, vp.SCHLUESSEL_CRON, (body.cron or "").strip() or vp.STANDARD_CRON)
    set_setting(db, vp.SCHLUESSEL_EMPFAENGER, (body.empfaenger or "").strip())

    from app.services.scheduler_service import register_vorlagen_pruefung_job
    register_vorlagen_pruefung_job(body.cron if body.aktiv else "")
    return lies_einstellungen(db, user)


@router.post("/jetzt")
def jetzt(senden: bool = False, db: Session = Depends(get_db),
          user: User = Depends(get_current_user)):
    """Von Hand anstossen. Ohne `senden` geht keine Mail raus - zum Ansehen."""
    _admin(user)
    if senden:
        return vp.lauf(db, immer_senden=True)
    ergebnis = vp.pruefe_alle(db)
    ergebnis["versand"] = {"gesendet": False, "grund": "nur Ansicht"}
    return ergebnis
