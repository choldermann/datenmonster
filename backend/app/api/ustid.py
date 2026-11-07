"""USt-ID-Prüfung über VIES (Mehrwertsteuer-Informationsaustauschsystem der EU-Kommission).

Für steuerfreie innergemeinschaftliche Lieferungen muss die USt-ID des Abnehmers gültig sein.
Geprüft wird nur auf Knopfdruck im Cockpit: die USt-IDs gehen dabei direkt von dieser Installation
an die EU-Kommission (https://ec.europa.eu/taxation_customs/vies/), nicht über monstersuite.
VIES bestätigt nur „gültig/ungültig“ (einfache Bestätigung) und nennt, wenn der Mitgliedstaat es
erlaubt, Name und Anschrift. Die qualifizierte Bestätigung für den Nachweis gegenüber dem
Finanzamt bleibt beim BZSt.

Ergebnisse je Mandant in business_config (scope „ustid_pruefung“, key = USt-ID), damit nicht jede
Ansicht neu fragt.
"""
import re
import time
from datetime import datetime
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.projects import can_read_project, require_editor
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services import business_config_service as cfg_service
from app.services import mandant_service

router = APIRouter(prefix="/api/ustid", tags=["ustid"])

VIES_URL = "https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number"
SCOPE = "ustid_pruefung"
MAX_JE_AUFRUF = 40
# Ländercodes der USt-IDs in VIES (Griechenland = EL, Nordirland = XI)
EU = {"AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT",
      "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK", "XI"}


def zerlegen(ustid: str) -> Optional[tuple[str, str]]:
    """„ATU 123.456-78“ → ("AT", "U12345678"); GR wird zu EL. None, wenn kein EU-Präfix."""
    s = re.sub(r"[^A-Za-z0-9]", "", ustid or "").upper()
    if len(s) < 4:
        return None
    cc, nr = s[:2], s[2:]
    if cc == "GR":
        cc = "EL"
    if cc not in EU or not re.fullmatch(r"[A-Z0-9]{2,12}", nr):
        return None
    return cc, nr


def vies_pruefen(client: httpx.Client, cc: str, nr: str) -> dict:
    """Eine USt-ID bei VIES prüfen. status: gueltig | ungueltig | nicht_erreichbar."""
    jetzt = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    try:
        r = client.post(VIES_URL, json={"countryCode": cc, "vatNumber": nr})
        d = r.json() if r.content else {}
    except Exception as e:
        return {"status": "nicht_erreichbar", "meldung": f"VIES nicht erreichbar: {str(e)[:120]}", "geprueft_am": jetzt}
    if r.status_code >= 400 or d.get("errorWrappers") or d.get("actionSucceed") is False:
        fehler = ", ".join(w.get("error", "") for w in d.get("errorWrappers") or []) or f"HTTP {r.status_code}"
        # MS_UNAVAILABLE, TIMEOUT, MS_MAX_CONCURRENT_REQ …: Dienst des Mitgliedstaats gerade nicht da
        return {"status": "nicht_erreichbar", "meldung": f"VIES: {fehler}", "geprueft_am": jetzt}
    gueltig = bool(d.get("valid", d.get("isValid")))
    name = (d.get("name") or "").strip()
    adresse = re.sub(r"\s*\n\s*", ", ", (d.get("address") or "").strip())
    return {"status": "gueltig" if gueltig else "ungueltig",
            "name": "" if name in ("---", "") else name[:160],
            "adresse": "" if adresse in ("---", "") else adresse[:240],
            "geprueft_am": jetzt}


@router.get("/ergebnisse")
def ergebnisse(project_id: Optional[int] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not can_read_project(project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    mandant_id = mandant_service.aktiver(project_id, user, db)
    zeilen = cfg_service._rows(project_id, db, SCOPE, mandant_id, strikt=True)
    return {"ergebnisse": {z.key: z.value for z in zeilen}, "mandant_id": mandant_id}


class PruefenIn(BaseModel):
    project_id: Optional[int] = None
    ustids: List[str]


@router.post("/pruefen")
def pruefen(body: PruefenIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Prüft bis zu 40 USt-IDs nacheinander bei VIES und legt das Ergebnis je Mandant ab."""
    require_editor(body.project_id, user, db)
    mandant_id = mandant_service.aktiver(body.project_id, user, db)
    ids = []
    for u in body.ustids:
        z = zerlegen(u)
        if z and (z[0] + z[1]) not in ids:
            ids.append(z[0] + z[1])
    if not ids:
        raise HTTPException(400, "Keine USt-ID mit EU-Ländercode")
    if len(ids) > MAX_JE_AUFRUF:
        raise HTTPException(400, f"Höchstens {MAX_JE_AUFRUF} USt-IDs je Prüfung")
    aus = {}
    with httpx.Client(timeout=30, headers={"User-Agent": "datenmonster-ustid/1.0"}) as c:
        for i, uid in enumerate(ids):
            if i:
                time.sleep(0.4)        # VIES drosselt parallele Anfragen je Mitgliedstaat
            erg = vies_pruefen(c, uid[:2], uid[2:])
            erg["von"] = user.username
            aus[uid] = erg
            if erg["status"] != "nicht_erreichbar":   # Ausfälle überschreiben kein früheres Ergebnis
                cfg_service.set_value(body.project_id, db, SCOPE, uid, erg, mandant_id)
    return {"ergebnisse": aus}
