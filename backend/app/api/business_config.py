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
    rahmen = werte.get("kontenrahmen") or cfg_service.KONTENRAHMEN_STANDARD
    rahmen_konten = cfg_service.KONTENRAHMEN.get(rahmen, {}).get("konten", {})

    felder = []
    for meta in cfg_service.datev_meta():
        key = meta["key"]
        # "Standard" heisst beim Konto: der Wert dieses Kontenrahmens, nicht der
        # eingebaute SKR03-Wert - sonst zeigte jedes SKR04-Konto faelschlich den
        # Zuruecksetzen-Knopf.
        standard = rahmen_konten.get(key, meta["default"])
        eintrag = {**meta, "value": werte.get(key, standard),
                   "default": standard,
                   "is_default": werte.get(key, standard) == standard}
        if meta.get("typ") == "auswahl":
            eintrag["optionen"] = cfg_service.kontenrahmen_optionen()
        felder.append(eintrag)

    return {"project_id": project_id,
            "mandant_id": mandant_id,
            "mandant_name": mandant_service.name_von(mandant_id, db),
            "kontenrahmen": rahmen,
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

    if body.key == "kontenrahmen" and wert and wert not in cfg_service.KONTENRAHMEN:
        raise HTTPException(400, f"Unbekannter Kontenrahmen: {wert}")

    mandant_id = mandant_service.aktiver(body.project_id, user, db)
    if wert == "":
        cfg_service.reset_value(body.project_id, db, "datev", body.key, mandant_id)
    else:
        cfg_service.set_value(body.project_id, db, "datev", body.key, wert, mandant_id)

    # Ein Rahmenwechsel raeumt die von Hand gesetzten Konten weg. Sonst waehlt man
    # SKR04 und die alten SKR03-Nummern blieben stehen, weil sie ausdruecklich
    # gespeichert waren - die Auswahl haette sichtbar nichts bewirkt.
    if body.key == "kontenrahmen":
        for konto in cfg_service.KONTENRAHMEN.get(
                cfg_service.KONTENRAHMEN_STANDARD, {}).get("konten", {}):
            cfg_service.reset_value(body.project_id, db, "datev", konto, mandant_id)

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


# ── Eigene Ereignisse: Aktionen, Messen, Preisänderungen … als Marker in Verläufen ──
# Gespeichert wie die Fixkosten: Bereich "ereignis", je Projekt und streng je Mandant –
# die Rabattaktion des einen Betriebs gehört nicht in die Kurve des anderen.

EREIGNIS_KATEGORIEN = ["Aktion", "Messe", "Werbung", "Preisänderung", "Lieferengpass", "Sonstiges"]


def _ereignis_out(row) -> dict:
    v = dict(row.value or {})
    return {"id": row.key, "datum": v.get("datum"), "bis": v.get("bis"), "titel": v.get("titel", ""),
            "kategorie": v.get("kategorie") or "Sonstiges", "notiz": v.get("notiz") or ""}


class EreignisIn(BaseModel):
    project_id: Optional[int] = None
    datum: str
    bis: Optional[str] = None
    titel: str
    kategorie: Optional[str] = "Sonstiges"
    notiz: Optional[str] = ""


def _ereignis_wert(body: EreignisIn, user: User) -> dict:
    von = cfg_service._parse_datum(body.datum)
    if von is None:
        raise HTTPException(400, f"Ungültiges Datum: {body.datum}")
    bis = cfg_service._parse_datum(body.bis) if body.bis else None
    if body.bis and bis is None:
        raise HTTPException(400, f"Ungültiges Enddatum: {body.bis}")
    if bis is not None and bis < von:
        raise HTTPException(400, "Das Enddatum liegt vor dem Beginn")
    titel = (body.titel or "").strip()
    if not titel:
        raise HTTPException(400, "Bezeichnung fehlt")
    if len(titel) > 120:
        raise HTTPException(400, "Bezeichnung höchstens 120 Zeichen")
    notiz = (body.notiz or "").strip()
    if len(notiz) > 1000:
        raise HTTPException(400, "Notiz höchstens 1000 Zeichen")
    kat = body.kategorie if body.kategorie in EREIGNIS_KATEGORIEN else "Sonstiges"
    return {"datum": von.isoformat(), "bis": bis.isoformat() if bis and bis != von else None,
            "titel": titel, "kategorie": kat, "notiz": notiz, "von": user.username}


@router.get("/ereignisse")
def list_ereignisse(project_id: Optional[int] = None, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    if not can_read_project(project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    mandant_id = mandant_service.aktiver(project_id, user, db)
    zeilen = cfg_service._rows(project_id, db, "ereignis", mandant_id, strikt=True)
    liste = sorted((_ereignis_out(r) for r in zeilen), key=lambda e: (e["datum"] or "", e["titel"]))
    return {"project_id": project_id, "mandant_id": mandant_id,
            "mandant_name": mandant_service.name_von(mandant_id, db),
            "kategorien": EREIGNIS_KATEGORIEN, "ereignisse": liste}


@router.post("/ereignisse")
def add_ereignis(body: EreignisIn, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    require_editor(body.project_id, user, db)
    import uuid
    mandant_id = mandant_service.aktiver(body.project_id, user, db)
    row = cfg_service.set_value(body.project_id, db, "ereignis", uuid.uuid4().hex[:12],
                                _ereignis_wert(body, user), mandant_id)
    return _ereignis_out(row)


@router.put("/ereignisse/{eid}")
def update_ereignis(eid: str, body: EreignisIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    require_editor(body.project_id, user, db)
    mandant_id = mandant_service.aktiver(body.project_id, user, db)
    if cfg_service._eine_zeile(db, body.project_id, "ereignis", eid, mandant_id) is None:
        raise HTTPException(404, "Ereignis nicht gefunden")
    row = cfg_service.set_value(body.project_id, db, "ereignis", eid, _ereignis_wert(body, user), mandant_id)
    return _ereignis_out(row)


@router.delete("/ereignisse/{eid}")
def delete_ereignis(eid: str, project_id: Optional[int] = None, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    require_editor(project_id, user, db)
    mandant_id = mandant_service.aktiver(project_id, user, db)
    if not cfg_service.reset_value(project_id, db, "ereignis", eid, mandant_id):
        raise HTTPException(404, "Ereignis nicht gefunden")
    return {"ok": True}


# ── Preisindex für die Preisbereinigung: welche Branche gehört zu diesem Betrieb ──
# Ein Wert je Mandant (streng, wie Ereignisse): der Großhändler für Reinigungsmittel und der
# Shop desselben Projekts haben verschiedene Preisentwicklungen. Die Liste der Indizes kommt
# vom Datendienst (/api/umfeld/preise/katalog), hier steht nur die Auswahl.

class PreisindexIn(BaseModel):
    project_id: Optional[int] = None
    key: str            # preise_grosshandel | preise_verbraucher
    region: str         # WZ08-… bzw. Deutschland
    label: str = ""


@router.get("/preisindex")
def get_preisindex(project_id: Optional[int] = None, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    if not can_read_project(project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    mandant_id = mandant_service.aktiver(project_id, user, db)
    zeilen = cfg_service._rows(project_id, db, "preisindex", mandant_id, strikt=True)
    wahl = dict(zeilen[0].value or {}) if zeilen else None
    return {"project_id": project_id, "mandant_id": mandant_id,
            "mandant_name": mandant_service.name_von(mandant_id, db), "auswahl": wahl}


@router.put("/preisindex")
def set_preisindex(body: PreisindexIn, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    require_editor(body.project_id, user, db)
    import re
    if body.key not in ("preise_grosshandel", "preise_verbraucher"):
        raise HTTPException(400, "Unbekannter Preisindex")
    if not (body.region == "Deutschland" or re.fullmatch(r"WZ08-\d{2,5}", body.region or "")):
        raise HTTPException(400, "Unbekannte Branche")
    mandant_id = mandant_service.aktiver(body.project_id, user, db)
    wert = {"key": body.key, "region": body.region, "label": (body.label or "")[:160], "von": user.username}
    cfg_service.set_value(body.project_id, db, "preisindex", "auswahl", wert, mandant_id)
    return {"auswahl": wert}


@router.delete("/preisindex")
def delete_preisindex(project_id: Optional[int] = None, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    require_editor(project_id, user, db)
    mandant_id = mandant_service.aktiver(project_id, user, db)
    return {"ok": cfg_service.reset_value(project_id, db, "preisindex", "auswahl", mandant_id)}


# ── Branche für den Umsatzvergleich („Ich gegen meine Branche“) ──
# NACE-Code des Handelszweigs (Eurostat, bis zum 3-Steller), je Mandant streng wie der Preisindex.
# Ohne Auswahl schlägt das Widget eine Branche aus dem Preisindex vor.

class BrancheIn(BaseModel):
    project_id: Optional[int] = None
    code: str           # z. B. G464, G4791, G47_X_G473
    label: str = ""


@router.get("/branche")
def get_branche(project_id: Optional[int] = None, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    if not can_read_project(project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    mandant_id = mandant_service.aktiver(project_id, user, db)
    zeilen = cfg_service._rows(project_id, db, "branche", mandant_id, strikt=True)
    wahl = dict(zeilen[0].value or {}) if zeilen else None
    return {"project_id": project_id, "mandant_id": mandant_id,
            "mandant_name": mandant_service.name_von(mandant_id, db), "auswahl": wahl}


@router.put("/branche")
def set_branche(body: BrancheIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_editor(body.project_id, user, db)
    import re
    if not re.fullmatch(r"G\d{0,4}(_[A-Z0-9_]{1,20})?", body.code or ""):
        raise HTTPException(400, "Unbekannte Branche")
    mandant_id = mandant_service.aktiver(body.project_id, user, db)
    wert = {"code": body.code, "label": (body.label or "")[:160], "von": user.username}
    cfg_service.set_value(body.project_id, db, "branche", "auswahl", wert, mandant_id)
    return {"auswahl": wert}


@router.delete("/branche")
def delete_branche(project_id: Optional[int] = None, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    require_editor(project_id, user, db)
    mandant_id = mandant_service.aktiver(project_id, user, db)
    return {"ok": cfg_service.reset_value(project_id, db, "branche", "auswahl", mandant_id)}


# ── Arbeitstage (Kalenderbereinigung) ──
# Bundesland der Feiertage, Samstag als Arbeitstag, 24./31.12. halb. Je Mandant streng:
# zwei Firmen eines Projekts können in verschiedenen Ländern sitzen. Gerechnet wird im Frontend
# (components/forms/arbeitstage.tsx), hier steht nur die Einstellung.

_BUNDESLAENDER = {"Baden-Württemberg", "Bayern", "Berlin", "Brandenburg", "Bremen", "Hamburg", "Hessen",
                  "Mecklenburg-Vorpommern", "Niedersachsen", "Nordrhein-Westfalen", "Rheinland-Pfalz", "Saarland",
                  "Sachsen", "Sachsen-Anhalt", "Schleswig-Holstein", "Thüringen"}


class ArbeitstageIn(BaseModel):
    project_id: Optional[int] = None
    bundesland: str = ""
    samstag: bool = False
    halbe_tage: bool = False


@router.get("/arbeitstage")
def get_arbeitstage(project_id: Optional[int] = None, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    if not can_read_project(project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    mandant_id = mandant_service.aktiver(project_id, user, db)
    zeilen = cfg_service._rows(project_id, db, "arbeitstage", mandant_id, strikt=True)
    wahl = dict(zeilen[0].value or {}) if zeilen else None
    return {"project_id": project_id, "mandant_id": mandant_id,
            "mandant_name": mandant_service.name_von(mandant_id, db), "auswahl": wahl}


@router.put("/arbeitstage")
def set_arbeitstage(body: ArbeitstageIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_editor(body.project_id, user, db)
    if body.bundesland and body.bundesland not in _BUNDESLAENDER:
        raise HTTPException(400, "Unbekanntes Bundesland")
    mandant_id = mandant_service.aktiver(body.project_id, user, db)
    wert = {"bundesland": body.bundesland, "samstag": body.samstag, "halbe_tage": body.halbe_tage, "von": user.username}
    cfg_service.set_value(body.project_id, db, "arbeitstage", "auswahl", wert, mandant_id)
    return {"auswahl": wert}
