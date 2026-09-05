"""Geschäftsparameter je Projekt: Schwellwerte, Kostensätze, Ziele.

Die Werte werden bei jedem Formular-/Drilldown-/Report-Lauf als :cfg_<key> in die
Mappings injiziert (business_config_service.apply_config).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, Any
from datetime import date
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.api.projects import can_read_project, require_editor
from app.services import business_config_service as cfg_service
from app.services import mandant_service

router = APIRouter(prefix="/api/business-config", tags=["business-config"])


@router.get("/thresholds")
def get_thresholds(project_id: Optional[int] = None,
                   db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """Alle Schwellwerte mit Standardwert, aktuellem Wert und Beschreibung."""
    if not can_read_project(project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    mandant_id = mandant_service.aktiver(project_id, user, db)
    aktuell = cfg_service.get_thresholds(project_id, db, mandant_id)
    out = []
    for meta in cfg_service.threshold_meta():
        key = meta["key"]
        out.append({**meta, "value": aktuell.get(key, meta["default"]),
                    "is_default": aktuell.get(key, meta["default"]) == meta["default"]})
    return {"project_id": project_id, "thresholds": out}


class ThresholdIn(BaseModel):
    project_id: Optional[int] = None
    key: str
    value: Any


@router.put("/thresholds")
def set_threshold(body: ThresholdIn, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    require_editor(body.project_id, user, db)
    bekannt = {m["key"] for m in cfg_service.threshold_meta()}
    if body.key not in bekannt:
        raise HTTPException(400, f"Unbekannter Schwellwert: {body.key}")
    wert = body.value
    if isinstance(wert, str):
        try:
            wert = float(wert.replace(",", "."))
        except ValueError:
            raise HTTPException(400, "Schwellwert muss eine Zahl sein")
    if isinstance(wert, float) and wert.is_integer():
        wert = int(wert)
    cfg_service.set_value(body.project_id, db, "threshold", body.key, wert)
    return {"key": body.key, "value": wert}


@router.delete("/thresholds/{key}")
def reset_threshold(key: str, project_id: Optional[int] = None,
                    db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """Überschreibung entfernen – der Standardwert gilt wieder."""
    require_editor(project_id, user, db)
    cfg_service.reset_value(project_id, db, "threshold", key)
    return {"key": key, "value": dict(
        (m["key"], m["default"]) for m in cfg_service.threshold_meta()).get(key)}


# ── Kostenarten: Fixkosten je Monat mit "gültig ab" ──────────────────────────
# Die Standardarten sind vorgeblendet (COST_DEFAULTS) – gepflegt werden nur
# Betrag und Beginn. Eigene Arten bekommen einen Schlüssel "x_<slug>".

@router.get("/datev")
def get_datev(project_id: Optional[int] = None, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    """DATEV-Stammdaten des AKTIVEN Mandanten.

    Wie bei den Fixkosten wandert der Mandantenname mit: bei zwei Betrieben muss
    an der Maske stehen, wessen Beraternummer man gerade tippt.
    """
    if not can_read_project(project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    mandant_id = mandant_service.aktiver(project_id, user, db)
    werte = cfg_service.get_datev(project_id, db, mandant_id)
    felder = [{**meta, "value": werte.get(meta["key"], meta["default"]),
               "is_default": werte.get(meta["key"], meta["default"]) == meta["default"]}
              for meta in cfg_service.datev_meta()]
    return {"project_id": project_id,
            "mandant_id": mandant_id,
            "mandant_name": mandant_service.name_von(mandant_id, db),
            "felder": felder,
            "fehlend": cfg_service.datev_unvollstaendig(werte)}


class DatevFeldIn(BaseModel):
    project_id: Optional[int] = None
    key: str
    value: str


@router.put("/datev")
def set_datev(body: DatevFeldIn, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    """Ein Stammdatenfeld für den aktiven Mandanten speichern.

    Immer mit mandant_id: ein projektweit abgelegter Wert würde für den zweiten
    Betrieb mitgelten und ihn unter fremder Kennung buchen lassen.
    """
    require_editor(body.project_id, user, db)
    if body.key not in {m["key"] for m in cfg_service.datev_meta()}:
        raise HTTPException(400, f"Unbekanntes DATEV-Feld: {body.key}")

    wert = (body.value or "").strip()
    meta = next(m for m in cfg_service.datev_meta() if m["key"] == body.key)
    # Nummernfelder dürfen nur Ziffern tragen - DATEV weist den Stapel sonst ab,
    # und zwar erst beim Steuerberater.
    if body.key in ("datev_berater", "datev_mandant", "datev_sachkontenlaenge") \
            and wert and not wert.isdigit():
        raise HTTPException(400, f"{meta['label']}: nur Ziffern")
    if body.key == "datev_wj_beginn" and wert and (len(wert) != 8 or not wert.isdigit()):
        raise HTTPException(400, "Wirtschaftsjahr als JJJJMMTT, z. B. 20260101")

    mandant_id = mandant_service.aktiver(body.project_id, user, db)
    if wert == "":
        cfg_service.reset_value(body.project_id, db, "datev", body.key, mandant_id)
    else:
        cfg_service.set_value(body.project_id, db, "datev", body.key, wert, mandant_id)
    return {"key": body.key, "value": wert, "mandant_id": mandant_id}


@router.get("/costs")
def list_costs(project_id: Optional[int] = None, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    if not can_read_project(project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    # Fixkosten gehören immer genau einem Mandanten. Der Name wandert mit in die
    # Antwort, damit die Maske zeigen kann, wessen Kosten gerade gepflegt werden –
    # ohne diese Angabe wäre bei zwei Betrieben nie sicher, wo man gerade tippt.
    mandant_id = mandant_service.aktiver(project_id, user, db)
    kosten = cfg_service.get_costs(project_id, db, mandant_id)
    return {"project_id": project_id,
            "mandant_id": mandant_id,
            "mandant_name": mandant_service.name_von(mandant_id, db),
            "gruppen": cfg_service.COST_GROUPS,
            "kosten": kosten,
            "summe_monat": cfg_service.kosten_monat(project_id, db, None, mandant_id)}


class KostenEintragIn(BaseModel):
    gueltig_ab: str
    betrag: float


class KostenartIn(BaseModel):
    project_id: Optional[int] = None
    key: str
    eintraege: list[KostenEintragIn] = []


def _slug(text: str) -> str:
    umlaute = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
    t = "".join(umlaute.get(c, c) for c in (text or "").strip().lower())
    t = "".join(c if c.isalnum() else "_" for c in t)
    return "_".join(p for p in t.split("_") if p)[:40]


@router.put("/costs")
def set_cost(body: KostenartIn, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    """Zeitscheiben einer Kostenart speichern (ersetzt die bisherigen)."""
    require_editor(body.project_id, user, db)

    mandant_id = mandant_service.aktiver(body.project_id, user, db)
    bestand = {k["key"]: k for k in cfg_service.get_costs(body.project_id, db, mandant_id)}
    art = bestand.get(body.key)
    if art is None:
        raise HTTPException(400, f"Unbekannte Kostenart: {body.key}")

    eintraege = []
    for e in body.eintraege:
        datum = cfg_service._parse_datum(e.gueltig_ab)
        if datum is None:
            raise HTTPException(400, f"Ungültiges Datum: {e.gueltig_ab}")
        if e.betrag < 0:
            raise HTTPException(400, "Der Betrag darf nicht negativ sein")
        eintraege.append({"gueltig_ab": datum.isoformat(), "betrag": round(e.betrag, 2)})
    # Doppelte Startdaten würden je nach Sortierung unterschiedlich gewinnen –
    # der zuletzt eingetragene Betrag gilt.
    entdoppelt = {e["gueltig_ab"]: e for e in eintraege}
    eintraege = sorted(entdoppelt.values(), key=lambda e: e["gueltig_ab"])

    wert = {"eintraege": eintraege}
    if art["custom"]:            # Bezeichnung/Gruppe leben nur bei eigenen Arten im Wert
        wert.update({"label": art["label"], "gruppe": art["gruppe"],
                     "gruppe_key": art["gruppe_key"], "custom": True})
    cfg_service.set_value(body.project_id, db, "cost", body.key, wert, mandant_id)
    return {**art, "eintraege": eintraege, "mandant_id": mandant_id,
            "betrag_aktuell": cfg_service.betrag_am(eintraege, date.today())}


class EigeneKostenartIn(BaseModel):
    project_id: Optional[int] = None
    label: str
    gruppe_key: Optional[str] = "sonstiges"


@router.post("/costs/custom")
def add_custom_cost(body: EigeneKostenartIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """Eigene Kostenart anlegen – erscheint danach wie eine Standardart."""
    require_editor(body.project_id, user, db)
    if not (body.label or "").strip():
        raise HTTPException(400, "Bezeichnung fehlt")

    basis = _slug(body.label)
    if not basis:
        raise HTTPException(400, "Bezeichnung ergibt keinen gültigen Schlüssel")
    mandant_id = mandant_service.aktiver(body.project_id, user, db)
    vorhanden = {k["key"] for k in cfg_service.get_costs(body.project_id, db, mandant_id)}
    key, n = f"x_{basis}", 2
    while key in vorhanden:
        key, n = f"x_{basis}_{n}", n + 1

    gruppe = next((g for g in cfg_service.COST_GROUPS if g["key"] == body.gruppe_key), None)
    wert = {"label": body.label.strip(), "custom": True, "eintraege": [],
            "gruppe_key": gruppe["key"] if gruppe else "sonstiges",
            "gruppe": gruppe["label"] if gruppe else "Sonstiges"}
    cfg_service.set_value(body.project_id, db, "cost", key, wert, mandant_id)
    return {"key": key, **wert, "betrag_aktuell": 0, "hinweis": "",
            "mandant_id": mandant_id}


@router.delete("/costs/{key}")
def delete_cost(key: str, project_id: Optional[int] = None,
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Eigene Art entfernen bzw. eine Standardart wieder auf ungepflegt setzen."""
    require_editor(project_id, user, db)
    return {"deleted": cfg_service.reset_value(
        project_id, db, "cost", key,
        mandant_service.aktiver(project_id, user, db))}


# ── Ziele: Speicher steht, Auswertung folgt in Phase 4 ───────────────────────

class ScopedValueIn(BaseModel):
    project_id: Optional[int] = None
    key: str
    value: dict


@router.get("/goals")
def list_goals(project_id: Optional[int] = None, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    if not can_read_project(project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    return cfg_service.get_goals(project_id, db)


@router.put("/goals")
def set_goal(body: ScopedValueIn, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    require_editor(body.project_id, user, db)
    cfg_service.set_value(body.project_id, db, "goal", body.key, body.value)
    return {"key": body.key, "value": body.value}


@router.delete("/goals/{key}")
def delete_goal(key: str, project_id: Optional[int] = None,
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_editor(project_id, user, db)
    return {"deleted": cfg_service.reset_value(project_id, db, "goal", key)}
