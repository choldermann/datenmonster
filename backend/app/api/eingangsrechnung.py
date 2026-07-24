"""
API für den Eingangsrechnungs-Import (Freigabe-Workflow).

Zustandslos: 'plan' parst die hochgeladene E-Rechnung und liefert den geparsten
Kopf (JSON) + den Dry-Run-Plan zurück. Das Frontend hält den Kopf, schickt ihn
mit Overrides an 'replan' (Live-Vorschau beim manuellen Zuordnen) und schließlich
an 'write' (echte Freigabe → Write in JTL).
"""
import json
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.models.user import User
from app.services.eingangsrechnung_parser import parse_erechnung, ERechnungParseError
from app.services.jtl_eingangsrechnung_writer import (
    EingangsrechnungWriter, serialize_kopf, deserialize_kopf)

router = APIRouter(prefix="/api/eingangsrechnung", tags=["eingangsrechnung"])

MAX_UPLOAD = 20 * 1024 * 1024  # 20 MB


def _writer(connection_id: int) -> EingangsrechnungWriter:
    try:
        return EingangsrechnungWriter(connection_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


class ReplanRequest(BaseModel):
    connection_id: int
    kopf: dict
    overrides: Optional[dict] = None


class WriteRequest(BaseModel):
    connection_id: int
    kopf: dict
    overrides: Optional[dict] = None
    learn: Optional[List[dict]] = None      # [{kLieferant, cLiefArtNr, kArtikel}, ...]


@router.post("/plan")
async def plan(
    connection_id: int = Form(...),
    file: UploadFile = File(...),
    overrides: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
):
    """E-Rechnung hochladen → parsen → Dry-Run-Plan. Gibt {kopf, plan} zurück."""
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Datei zu groß")
    try:
        kopf = parse_erechnung(data, file.filename or "")
    except ERechnungParseError as e:
        raise HTTPException(422, f"E-Rechnung nicht lesbar: {e}")
    ov = json.loads(overrides) if overrides else None
    p = _writer(connection_id).build_plan(kopf, dry_run=True, overrides=ov)
    return {"kopf": serialize_kopf(kopf), "plan": p.to_dict()}


@router.post("/replan")
def replan(req: ReplanRequest, user: User = Depends(get_current_user)):
    """Plan mit geänderten Overrides neu berechnen (Live-Vorschau, kein Write)."""
    kopf = deserialize_kopf(req.kopf)
    p = _writer(req.connection_id).build_plan(kopf, dry_run=True, overrides=req.overrides)
    return p.to_dict()


@router.post("/write")
def write(req: WriteRequest, user: User = Depends(get_current_user)):
    """Freigabe: echten Write ausführen (nur wenn Plan fehlerfrei). Optional lernen."""
    kopf = deserialize_kopf(req.kopf)
    w = _writer(req.connection_id)
    p = w.build_plan(kopf, dry_run=False, overrides=req.overrides)
    learned = []
    if p.ok and req.learn:
        for l in req.learn:
            try:
                res = w.learn_liefartikel(int(l["kLieferant"]), str(l["cLiefArtNr"]), int(l["kArtikel"]))
                learned.append({**l, **res})
            except Exception as e:  # Lernen darf den erfolgreichen Write nicht kippen
                learned.append({**l, "created": False, "reason": str(e)[:120]})
    out = p.to_dict()
    out["learned"] = learned
    return out


@router.get("/artikel-suche")
def artikel_suche(connection_id: int, q: str, user: User = Depends(get_current_user)):
    """Artikelsuche fürs manuelle Zuordnen (eigene ArtNr / Lieferanten-ArtNr / Name)."""
    if len(q.strip()) < 2:
        return {"results": []}
    return {"results": _writer(connection_id).search_artikel(q.strip())}
