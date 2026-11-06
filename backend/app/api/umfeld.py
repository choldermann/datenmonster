"""Umfelddaten (Wetter, Atemwegsinfekte) vom monstersuite-Datendienst durchreichen.

Die Installation schickt nur Lizenz, Größen, Regionen und Zeitraum – keine Kundendaten.
Antworten werden im Prozess 6 Stunden gehalten: die Quellen ändern sich höchstens täglich
(DWD monatlich, RKI wöchentlich), und ein Cockpit fragt bei jedem Öffnen.
"""
import json
import time
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/umfeld", tags=["umfeld"])

_CACHE: dict = {}
_TTL = 6 * 3600


def _fragen(db: Session, pfad: str, extra: dict) -> dict:
    from app.api.license import license_auth_body, LICENSE_SERVER
    schluessel = pfad + json.dumps(extra, sort_keys=True)
    hit = _CACHE.get(schluessel)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    try:
        with httpx.Client(timeout=90) as c:   # erster Abruf holt die Quellen nach: großzügig
            r = c.post(f"{LICENSE_SERVER}/api/v1/umfeld/{pfad}", json={**license_auth_body(db), **extra})
    except Exception as e:
        raise HTTPException(502, f"Datendienst nicht erreichbar: {e}")
    if r.status_code == 403:
        raise HTTPException(403, "Umfelddaten brauchen eine aktive Lizenz.")
    if r.status_code >= 400:
        try:
            msg = r.json().get("message")
        except Exception:
            msg = None
        raise HTTPException(502, msg or f"Datendienst antwortet mit {r.status_code}")
    daten = r.json()
    _CACHE[schluessel] = (time.time(), daten)
    return daten


@router.get("/katalog")
def katalog(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _fragen(db, "katalog", {})


class ReihenIn(BaseModel):
    groessen: List[str]
    regionen: List[str] = []
    von: Optional[str] = ""
    bis: Optional[str] = ""


@router.post("/reihen")
def reihen(body: ReihenIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not body.groessen or len(body.groessen) > 8 or len(body.regionen) > 17:
        raise HTTPException(400, "Zu viele oder keine Größen/Regionen")
    return _fragen(db, "reihen", {"groessen": sorted(set(body.groessen)), "regionen": sorted(set(body.regionen)),
                                  "von": body.von or "", "bis": body.bis or ""})
