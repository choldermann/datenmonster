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
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.models.form import Form as FormModel
from app.services.eingangsrechnung_parser import parse_erechnung, ERechnungParseError
from app.services.jtl_eingangsrechnung_writer import (
    EingangsrechnungWriter, serialize_kopf, deserialize_kopf)

router = APIRouter(prefix="/api/eingangsrechnung", tags=["eingangsrechnung"])

MAX_UPLOAD = 20 * 1024 * 1024  # 20 MB


def _check_connection_access(connection_id: int, user: User, db: Session,
                            widget_types: tuple = ("eingangsrechnung",)) -> None:
    """Stellt sicher, dass der Benutzer diese JTL-Verbindung nutzen darf.

    Admins und interne Editoren haben ohnehin vollen Connection-Zugriff im Editor.
    Ein reiner Portal-Benutzer (is_portal_only) darf eine Verbindung NUR ansprechen,
    wenn sie in einem veröffentlichten Formular als Widget gebunden ist, auf das er
    Zugriff hat — sonst könnte er in eine fremde WaWi schreiben. Freigegeben wird
    also über die Formular-Veröffentlichung, nicht über die Benutzerrolle.

    `widget_types` sagt, welche Widgets als Freigabe zählen; der DATEV-Export
    nutzt dieselbe Prüfung mit seinem eigenen Typ.
    """
    if getattr(user, "is_admin", False) or not getattr(user, "is_portal_only", False):
        return
    # Lazy-Import vermeidet jegliche Import-Reihenfolge-Probleme beim Modul-Load.
    from app.api.portal import _check_portal_access
    forms = db.query(FormModel).filter(FormModel.published == True).all()
    for f in forms:
        widgets = (f.schema or {}).get("widgets", [])
        bound = {str(w.get("config", {}).get("connection_id"))
                 for w in widgets if w.get("type") in widget_types}
        if str(connection_id) in bound:
            try:
                _check_portal_access(f, user)
                return
            except HTTPException:
                continue
    raise HTTPException(403, "Kein Zugriff auf diese Verbindung")


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
    db: Session = Depends(get_db),
):
    """E-Rechnung hochladen → parsen → Dry-Run-Plan. Gibt {kopf, plan} zurück."""
    _check_connection_access(connection_id, user, db)
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Datei zu groß")
    # Zuerst der exakte Weg: strukturierte E-Rechnung (ZUGFeRD/Factur-X, XRechnung).
    # Erst wenn die Datei keine ist, wird das PDF ausgelesen – in dieser
    # Reihenfolge, weil strukturierte Daten stimmen und die Auslesung nur schätzt.
    befund = None
    try:
        kopf = parse_erechnung(data, file.filename or "")
    except ERechnungParseError as struktur_fehler:
        if not data[:5] == b"%PDF-":
            raise HTTPException(422, f"E-Rechnung nicht lesbar: {struktur_fehler}")
        from app.services.pdf_rechnung_leser import lese_pdf_rechnung
        try:
            kopf, befund = await lese_pdf_rechnung(
                data, file.filename or "", connection_id, db)
        except ERechnungParseError as pdf_fehler:
            raise HTTPException(
                422, f"Weder E-Rechnung noch lesbares PDF: {pdf_fehler}")
    ov = json.loads(overrides) if overrides else None
    p = _writer(connection_id).build_plan(kopf, dry_run=True, overrides=ov)
    return {"kopf": serialize_kopf(kopf), "plan": p.to_dict(), "befund": befund}


@router.post("/replan")
def replan(req: ReplanRequest, user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    """Plan mit geänderten Overrides neu berechnen (Live-Vorschau, kein Write)."""
    _check_connection_access(req.connection_id, user, db)
    kopf = deserialize_kopf(req.kopf)
    p = _writer(req.connection_id).build_plan(kopf, dry_run=True, overrides=req.overrides)
    return p.to_dict()


@router.post("/write")
def write(req: WriteRequest, user: User = Depends(get_current_user),
          db: Session = Depends(get_db)):
    """Freigabe: echten Write ausführen (nur wenn Plan fehlerfrei). Optional lernen."""
    _check_connection_access(req.connection_id, user, db)
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
def artikel_suche(connection_id: int, q: str, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Artikelsuche fürs manuelle Zuordnen (eigene ArtNr / Lieferanten-ArtNr / Name)."""
    _check_connection_access(connection_id, user, db)
    if len(q.strip()) < 2:
        return {"results": []}
    return {"results": _writer(connection_id).search_artikel(q.strip())}


@router.get("/kostenarten")
def kostenarten(connection_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """Zusatzkosten-Katalog dieser Wawi (fürs manuelle Zuordnen im Formular).

    Die IDs sind installationsspezifisch – dieselbe Nummer heißt bei einem Kunden
    „Frachtkosten", beim nächsten „Gefahrgutzuschlag". Deshalb bietet das Formular
    die Namen dieser Wawi an, statt eine ID zu raten.
    """
    _check_connection_access(connection_id, user, db)
    return {"results": _writer(connection_id).kostenarten()}
