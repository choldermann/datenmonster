"""KI-Werkbank: Bauvorhaben planen, vorschauen, bauen und zurückbauen.

Der Bauzettel wird als Datenstrom geliefert (SSE), weil dahinter mehrere
Modellaufrufe hintereinander stehen. Als eine einzige lange Antwort liefe er in
Zeitüberschreitungen der Zwischenschichten – dieselbe Klasse Fehler wie der
„Network Error" beim sequenziellen Formularlauf.
"""
import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.api.auth import get_current_user
from app.core.database import get_db, safe_commit
from app.models.user import User
from app.models.vorhaben import Vorhaben, VorhabenArtefakt
from app.services import mandant_service
from app.services.werkbank import bauen as bauen_service
from app.services.werkbank import plan_ki, rueckbau, werkzeuge
from app.services.werkbank.werkzeuge import WerkzeugFehler

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/werkbank", tags=["werkbank"])


def _check_editor(user: User):
    if getattr(user, "is_portal_only", False):
        raise HTTPException(403, "Nur Admins und Editoren können Vorhaben bauen")


def _hole(db: Session, vorhaben_id: int) -> Vorhaben:
    v = db.query(Vorhaben).filter(Vorhaben.id == vorhaben_id).first()
    if not v:
        raise HTTPException(404, "Vorhaben nicht gefunden")
    return v


def _artefakte_out(db: Session, v: Vorhaben) -> list:
    rows = (db.query(VorhabenArtefakt)
              .filter(VorhabenArtefakt.vorhaben_id == v.id)
              .order_by(VorhabenArtefakt.schritt, VorhabenArtefakt.id).all())
    return [{"id": a.id, "schritt": a.schritt, "werkzeug": a.werkzeug,
             "art": a.art, "ziel_id": a.ziel_id, "ziel_key": a.ziel_key,
             "label": a.label, "erzeugt": bool(a.erzeugt)} for a in rows]


def _out(db: Session, v: Vorhaben, mit_artefakten: bool = False) -> dict:
    d = {
        "id": v.id, "name": v.name, "beschreibung": v.beschreibung,
        "project_id": v.project_id, "mandant_id": v.mandant_id,
        "mandant": mandant_service.name_von(v.mandant_id, db) if v.mandant_id else None,
        "status": v.status, "bauplan": v.bauplan or [],
        "hinweise": v.hinweise or [], "verlauf": v.verlauf or [],
        "created_at": str(v.created_at or ""), "gebaut_am": str(v.gebaut_am or ""),
        "zurueckgebaut_am": str(v.zurueckgebaut_am or ""),
    }
    if mit_artefakten:
        d["artefakte"] = _artefakte_out(db, v)
    return d


# ── Werkzeugkasten ───────────────────────────────────────────────────────────

@router.get("/werkzeuge")
def werkzeugkasten(user: User = Depends(get_current_user)):
    """Was die Werkbank bauen kann – für die Oberfläche und zum Nachlesen."""
    _check_editor(user)
    from app.services.zeitraum import PRESETS
    return {
        "werkzeuge": [
            {"key": k, "label": w["label"], "wofuer": w["wofuer"],
             "baut_objekte": bool(w.get("baut_objekte")),
             "hat_vorschau": bool(w.get("vorschau"))}
            for k in werkzeuge.REIHENFOLGE for w in [werkzeuge.WERKZEUGE[k]]
        ],
        "zeitraeume": [{"key": k, "label": v} for k, v in PRESETS.items()],
        "takte": [{"key": k, "label": v} for k, v in werkzeuge.TAKTE],
        "dringlichkeiten": ["kritisch", "warnung", "hinweis", "info"],
    }


# ── Verstehen ────────────────────────────────────────────────────────────────

class VerstehenRequest(BaseModel):
    beschreibung: str
    project_id: Optional[int] = None
    mandant_id: Optional[int] = None


@router.post("/verstehen")
async def verstehen(data: VerstehenRequest, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """Satz → Bauzettel. Legt das Vorhaben als **Entwurf** an, baut nichts."""
    _check_editor(user)
    from app.api.ai import _require_ai

    svc = _require_ai(db)
    mandant_id = data.mandant_id or mandant_service.aktiver(data.project_id, user, db)
    if not mandant_id:
        raise HTTPException(400, "Kein Mandant gewählt – es ist unklar, gegen welche "
                                 "Warenwirtschaft gebaut werden soll.")

    ctx = {"project_id": data.project_id, "mandant_id": mandant_id,
           "email": getattr(user, "email", None) or ""}

    async def strom():
        try:
            ergebnis = None
            async for schritt in plan_ki.bauzettel_stufen(db, svc, data.beschreibung, ctx):
                if "ergebnis" in schritt:
                    ergebnis = schritt["ergebnis"]
                else:
                    yield f"data: {json.dumps(schritt, ensure_ascii=False)}\n\n"

            v = Vorhaben(
                name=ergebnis["name"], beschreibung=ergebnis["beschreibung"],
                project_id=data.project_id, mandant_id=mandant_id,
                status="entwurf", bauplan=ergebnis["bauplan"],
                hinweise=ergebnis["hinweise"],
                verlauf=[{"rolle": "anwender", "text": data.beschreibung}]
                        + [{"rolle": "rueckfrage", "text": r}
                           for r in ergebnis["rueckfragen"]],
                created_by=user.id,
            )
            db.add(v)
            safe_commit(db)
            db.refresh(v)
            yield ("data: " + json.dumps(
                {"vorhaben": _out(db, v), "rueckfragen": ergebnis["rueckfragen"]},
                ensure_ascii=False) + "\n\n")
        except plan_ki.PlanFehler as e:
            db.rollback()
            yield f"data: {json.dumps({'fehler': str(e)}, ensure_ascii=False)}\n\n"
        except Exception as e:
            db.rollback()
            logger.exception("Bauzettel fehlgeschlagen")
            yield (f"data: {json.dumps({'fehler': f'Planung fehlgeschlagen: {str(e)[:200]}'}, ensure_ascii=False)}\n\n")
        yield "data: [DONE]\n\n"

    return StreamingResponse(strom(), media_type="text/event-stream")


# ── Vorhaben verwalten ───────────────────────────────────────────────────────

@router.get("/vorhaben")
def liste(project_id: Optional[int] = None, db: Session = Depends(get_db),
          user: User = Depends(get_current_user)):
    _check_editor(user)
    q = db.query(Vorhaben)
    if project_id is not None:
        q = q.filter(Vorhaben.project_id == project_id)
    return [_out(db, v) for v in q.order_by(Vorhaben.id.desc()).all()]


@router.get("/vorhaben/{vorhaben_id}")
def holen(vorhaben_id: int, db: Session = Depends(get_db),
          user: User = Depends(get_current_user)):
    _check_editor(user)
    return _out(db, _hole(db, vorhaben_id), mit_artefakten=True)


class VorhabenPatch(BaseModel):
    name: Optional[str] = None
    beschreibung: Optional[str] = None
    mandant_id: Optional[int] = None
    bauplan: Optional[List[dict]] = None


@router.put("/vorhaben/{vorhaben_id}")
def aendern(vorhaben_id: int, data: VorhabenPatch, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    """Bauzettel nachbessern: Häkchen setzen, Eingaben korrigieren, umbenennen."""
    _check_editor(user)
    v = _hole(db, vorhaben_id)

    if data.name is not None:
        v.name = data.name.strip() or v.name
    if data.beschreibung is not None:
        v.beschreibung = data.beschreibung
    if data.mandant_id is not None:
        if not mandant_service.darf_nutzen(data.mandant_id, user, db):
            raise HTTPException(403, "Dieser Mandant ist nicht freigegeben.")
        v.mandant_id = data.mandant_id
    if data.bauplan is not None:
        gesaeubert = []
        for s in data.bauplan:
            key = s.get("werkzeug")
            if key not in werkzeuge.WERKZEUGE:
                raise HTTPException(400, f"Unbekanntes Werkzeug „{key}“.")
            eingabe = s.get("eingabe") or {}
            gesaeubert.append({
                "werkzeug": key, "aktiv": bool(s.get("aktiv", True)),
                "titel": werkzeuge.WERKZEUGE[key]["label"],
                "warum": s.get("warum") or "", "eingabe": eingabe,
                "zusammenfassung": werkzeuge.zusammenfassen(key, eingabe),
            })
        v.bauplan = werkzeuge.sortiert(gesaeubert)
        flag_modified(v, "bauplan")

    safe_commit(db)
    return _out(db, v, mit_artefakten=True)


@router.delete("/vorhaben/{vorhaben_id}/eintrag")
def eintrag_loeschen(vorhaben_id: int, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """Entfernt den Vorhaben-Eintrag selbst.

    Nur erlaubt, wenn nichts mehr daran hängt – sonst verlöre man die einzige
    Spur zu den gebauten Objekten und hätte exakt die Waisen erzeugt, gegen die
    das ganze Verfahren antritt.
    """
    _check_editor(user)
    v = _hole(db, vorhaben_id)
    offen = (db.query(VorhabenArtefakt)
               .filter(VorhabenArtefakt.vorhaben_id == v.id).count())
    if offen:
        raise HTTPException(409, f"An diesem Vorhaben hängen noch {offen} Objekt(e). "
                                 f"Erst zurückbauen, dann löschen.")
    db.delete(v)
    safe_commit(db)
    return {"geloescht": True}


# ── Vorschau und Bauen ───────────────────────────────────────────────────────

@router.post("/vorhaben/{vorhaben_id}/vorschau")
def vorschau(vorhaben_id: int, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    """Rechnet die Schritte mit echten Zahlen – ohne irgendetwas zu speichern."""
    _check_editor(user)
    v = _hole(db, vorhaben_id)
    try:
        return {"schritte": bauen_service.vorschau(db, v, user.id)}
    except WerkzeugFehler as e:
        raise HTTPException(400, str(e))


@router.post("/vorhaben/{vorhaben_id}/bauen")
def bauen(vorhaben_id: int, db: Session = Depends(get_db),
          user: User = Depends(get_current_user)):
    """Baut das Vorhaben – ganz oder gar nicht."""
    _check_editor(user)
    v = _hole(db, vorhaben_id)
    if v.status == "installiert":
        raise HTTPException(409, "Das Vorhaben ist schon gebaut. Zum Ändern „Neu "
                                 "bauen“ verwenden.")
    try:
        erg = bauen_service.ausfuehren(db, v, user.id)
    except WerkzeugFehler as e:
        db.rollback()
        raise HTTPException(400, str(e))
    except Exception as e:
        db.rollback()
        logger.exception("Bauen fehlgeschlagen")
        raise HTTPException(500, f"Bauen fehlgeschlagen: {str(e)[:300]}")
    return {**erg, "vorhaben": _out(db, v, mit_artefakten=True)}


@router.post("/vorhaben/{vorhaben_id}/neu-bauen")
def neu_bauen(vorhaben_id: int, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    """Zurückbauen und mit dem geänderten Bauplan neu bauen."""
    _check_editor(user)
    v = _hole(db, vorhaben_id)
    try:
        erg = bauen_service.neu_bauen(db, v, user.id)
    except WerkzeugFehler as e:
        db.rollback()
        raise HTTPException(400, str(e))
    except Exception as e:
        db.rollback()
        logger.exception("Neubau fehlgeschlagen")
        raise HTTPException(500, f"Neubau fehlgeschlagen: {str(e)[:300]}")
    return {**erg, "vorhaben": _out(db, v, mit_artefakten=True)}


# ── Rückbau ──────────────────────────────────────────────────────────────────

@router.post("/vorhaben/{vorhaben_id}/rueckbau/vorschau")
def rueckbau_vorschau(vorhaben_id: int, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """Was gelöscht würde, was nur bereinigt wird und was noch benutzt wird."""
    _check_editor(user)
    return rueckbau.pruefen(db, _hole(db, vorhaben_id))


@router.delete("/vorhaben/{vorhaben_id}")
def rueckbau_ausfuehren(vorhaben_id: int, nur_ungenutzte: bool = True,
                        db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    """Baut das Vorhaben zurück.

    `nur_ungenutzte=true` (Voreinstellung) lässt alles stehen, woran noch etwas
    hängt. Erst wenn der Anwender das ausdrücklich abwählt, wird auch das
    gelöscht – dann aber sehenden Auges.
    """
    _check_editor(user)
    v = _hole(db, vorhaben_id)
    try:
        return rueckbau.ausfuehren(db, v, nur_ungenutzte=nur_ungenutzte)
    except Exception as e:
        db.rollback()
        logger.exception("Rückbau fehlgeschlagen")
        raise HTTPException(500, f"Rückbau fehlgeschlagen: {str(e)[:300]}")
