"""Umfelddaten (Wetter, Atemwegsinfekte, Preisindizes, Handelsumsatz, Außenhandel) vom monstersuite-Datendienst durchreichen.

Die Installation schickt nur Lizenz, Größen, Regionen und Zeitraum – keine Kundendaten.
Beim Außenhandel gehen zusätzlich die Warennummern (KN8) mit, nie Mengen, Preise oder Lieferanten.
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
    # Antworten mit Hinweis („wird gerade geladen“, „letzter Abruf fehlgeschlagen“) nicht 6 h festhalten,
    # sonst bliebe ein Cockpit den halben Tag leer, obwohl die Daten eine Minute später da sind.
    vorlaeufig = bool(daten.get("hinweis")) or any((x or {}).get("hinweis") for x in
                                                   (daten.get("reihen") or []) + (daten.get("warennummern") or []))
    if not vorlaeufig:
        _CACHE[schluessel] = (time.time(), daten)
    return daten


@router.get("/preise/katalog")
def preise_katalog(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Preisindizes (Destatis) für die Preisbereinigung: Großhandel je Branche, Verbraucherpreise."""
    return _fragen(db, "preise/katalog", {})


@router.get("/branchen/katalog")
def branchen_katalog(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Branchen für den Umsatzvergleich (Eurostat, Groß- und Einzelhandel Deutschland)."""
    return _fragen(db, "branchen/katalog", {})


@router.get("/strukturdaten")
def strukturdaten(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Einwohner und verfügbares Einkommen je Bundesland (Destatis) – Bezugsgrößen für die Deutschlandkarte."""
    return _fragen(db, "strukturdaten", {})


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


class AussenhandelIn(BaseModel):
    warennummern: List[str]
    von: Optional[str] = ""
    bis: Optional[str] = ""


@router.post("/aussenhandel")
def aussenhandel(body: AussenhandelIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Ein- und Ausfuhr Deutschlands je Warennummer (Eurostat Comext): Monate Welt, Länder im Zeitraum."""
    codes = sorted({"".join(ch for ch in c if ch.isdigit()) for c in body.warennummern} - {""})
    if not codes or len(codes) > 15 or any(len(c) != 8 for c in codes):
        raise HTTPException(400, "1 bis 15 achtstellige Warennummern angeben")
    return _fragen(db, "aussenhandel", {"warennummern": codes, "von": body.von or "", "bis": body.bis or ""})
