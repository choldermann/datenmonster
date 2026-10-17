"""Händler-Ansicht: die einfache Startseite für JTL-Kunden.

Die Händler-Ansicht ist eine neue Schale über der vorhandenen Maschine. Die
Endpunkte hier bündeln nur, was die Startseite in einem Aufruf braucht –
Cockpits, Warnungen, Kennzahl-Kacheln, persönliche Einstellungen. Ausgeführt
wird weiterhin über die bekannten Wege (FormRunner/PortalRunner, Alerts,
Zustellpläne). Plan: ~/.claude/plans/haendler-ansicht.md, Phase 1.

Projekte kommen hier bewusst nicht vor: der Händler sieht alle Cockpits, die er
lesen darf, nebeneinander.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db, safe_commit
from app.core.zugriff import ist_admin, projekte_mit_rolle, schreiben_pruefen
from app.models.form import Form
from app.models.user import User

router = APIRouter(prefix="/api/start", tags=["start"])

# Kennzeichen des versteckten Formulars mit den Kennzahl-Kacheln der Übersicht.
ROLLE_STARTSEITE = "startseite"

# Vorgabe für die Kacheln: aus dem Reiter „Unternehmensübersicht“ des GF-Cockpits.
KENNZAHLEN_VORGABE = ["w_kpi_umsatz_netto", "w_kpi_rohertrag", "w_kpi_marge", "w_kpi_kunden"]

SEVERITY_RANG = {"kritisch": 0, "warnung": 1, "hinweis": 2, "info": 3}


def _portal(user) -> bool:
    return bool(getattr(user, "is_portal_only", False)) and not ist_admin(user)


def _sichtbare_formulare(user, db) -> List[Form]:
    """Alle Formulare, die dieser Benutzer öffnen darf.

    Portal-Benutzer: veröffentlichte Formulare mit Freigabe (wie /api/portal/forms).
    Editoren: alle Formulare ihrer Projekte, Admins alle.
    """
    if _portal(user):
        from app.api.portal import _check_portal_access
        erlaubt = []
        for f in db.query(Form).filter(Form.published == True).all():  # noqa: E712
            try:
                _check_portal_access(f, user)
                erlaubt.append(f)
            except HTTPException:
                continue
        return erlaubt
    q = db.query(Form)
    if not ist_admin(user):
        projekte = projekte_mit_rolle(user, db)
        q = q.filter(Form.project_id.in_(projekte)) if projekte else q.filter(False)
    return q.all()


def _ist_startseite(f: Form) -> bool:
    return (f.schema or {}).get("rolle") == ROLLE_STARTSEITE


def _cockpit_out(f: Form, projektnamen: dict, db) -> dict:
    schema = f.schema or {}
    gesperrt = None
    try:
        from app.core import vorlagen_gate
        gesperrt = vorlagen_gate.sperre_fuer_objekt(db, "forms", f.id)
    except Exception:
        gesperrt = None
    return {
        "id": f.id,
        "name": f.name,
        "slug": f.slug,
        "project_id": f.project_id,
        "projekt": projektnamen.get(f.project_id),
        "intro": ((schema.get("doku") or {}).get("intro") or "").strip(),
        "reiter": len(schema.get("result_tabs") or []),
        # Aus dem Report-Baukasten = selbst zusammengestellt, sonst aus einer Vorlage.
        "art": "bericht" if schema.get("report_builder") else "cockpit",
        "gesperrt": gesperrt,
    }


def _projektnamen(db) -> dict:
    from app.models.project import Project
    return {p.id: p.name for p in db.query(Project).all()}


@router.get("/cockpits")
def cockpits(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Alle Dashboards, die der Benutzer öffnen darf – ohne reine Eingabeformulare
    und ohne das versteckte Startseiten-Formular."""
    namen = _projektnamen(db)
    liste = [f for f in _sichtbare_formulare(user, db)
             if (f.schema or {}).get("widgets") and not _ist_startseite(f)]
    liste.sort(key=lambda f: (f.name or "").lower())
    aus = [_cockpit_out(f, namen, db) for f in liste]
    # Dasselbe Cockpit in zwei Projekten sähe sonst doppelt aus: dann den
    # Projektnamen als Zusatz zeigen, sonst nicht.
    zaehler: dict = {}
    for c in aus:
        zaehler[c["name"]] = zaehler.get(c["name"], 0) + 1
    for c in aus:
        c["zusatz"] = c["projekt"] if zaehler[c["name"]] > 1 else None
    return aus


def _einstellungen(user) -> dict:
    e = getattr(user, "einstellungen", None)
    return dict(e) if isinstance(e, dict) else {}


def _warnungen(user, formulare: List[Form], db) -> list:
    """Neueste Warnungen aller Projekte, die der Benutzer sieht – schlimmste zuerst."""
    from app.services import alert_service, mandant_service
    projekte = {f.project_id for f in formulare if f.project_id is not None}
    if not _portal(user):
        projekte |= ({p for p in _projektnamen(db)} if ist_admin(user)
                     else projekte_mit_rolle(user, db))
    aus = []
    for pid in sorted(projekte):
        try:
            lauf = alert_service.latest_run(db, pid, mandant_service.aktiver(pid, user, db))
        except Exception:
            continue
        for a in (lauf or {}).get("alerts") or []:
            if a.get("status") != "alert":
                continue
            aus.append({
                "project_id": pid,
                "rule_key": a.get("rule_key"),
                "titel": a.get("titel") or a.get("name"),
                "untertitel": a.get("untertitel") or "",
                "severity": a.get("severity"),
                "ampel": a.get("Ampel"),
                "cockpit": a.get("cockpit"),
                "neu": bool(a.get("neu")),
            })
    # Bei Warnungen aus mehreren Projekten (z. B. Echtbetrieb und Demo) muss
    # dabeistehen, woher sie kommen – sonst stehen zwei verschiedene Zahlen
    # zum selben Thema nebeneinander.
    if len({a["project_id"] for a in aus}) > 1:
        namen = _projektnamen(db)
        for a in aus:
            a["projekt"] = namen.get(a["project_id"])
    aus.sort(key=lambda a: (SEVERITY_RANG.get(a["severity"], 9), a["titel"] or ""))
    return aus


@router.get("/uebersicht")
def uebersicht(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Alles für die Startseite in einem Aufruf."""
    formulare = _sichtbare_formulare(user, db)
    start = next((f for f in formulare if _ist_startseite(f)), None)
    namen = _projektnamen(db)
    nach_id = {f.id: f for f in formulare}

    pins = [i for i in (_einstellungen(user).get("pins") or []) if i in nach_id]
    angeheftet = [_cockpit_out(nach_id[i], namen, db) for i in pins]

    return {
        "kennzahlen": ({"id": start.id, "slug": start.slug, "project_id": start.project_id}
                       if start else None),
        # Kacheln einrichten kann nur, wer bauen darf, und nur wenn es ein GF-Cockpit gibt.
        "kennzahlen_moeglich": (start is None and not _portal(user)
                                and _gf_cockpit(formulare) is not None),
        "warnungen": _warnungen(user, formulare, db),
        "angeheftet": angeheftet,
    }


def _gf_cockpit(formulare: List[Form]) -> Optional[Form]:
    """Das erste Formular, das alle Vorgabe-Kacheln enthält (= GF-Cockpit)."""
    for f in formulare:
        ids = {w.get("id") for w in (f.schema or {}).get("widgets") or []}
        if all(k in ids for k in KENNZAHLEN_VORGABE):
            return f
    return None


@router.post("/kennzahlen")
def kennzahlen_einrichten(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Legt das versteckte Startseiten-Formular mit den Kennzahl-Kacheln an.

    Gebaut wird mit dem Report-Baukasten aus dem GF-Cockpit; das Ergebnis ist ein
    normales Formular, nur mit `rolle = startseite`. Veröffentlicht, damit es
    auch Portal-Benutzer auf ihrer Übersicht sehen.
    """
    if _portal(user):
        raise HTTPException(403, "Nur Admins und Editoren können die Übersicht einrichten")
    return kennzahlen_anlegen(db, user)


def kennzahlen_anlegen(db, user, project_id: Optional[int] = None) -> dict:
    """Wie oben; mit project_id nur innerhalb dieses Projekts (Einrichtungsassistent)."""
    formulare = [f for f in _sichtbare_formulare(user, db)
                 if project_id is None or f.project_id == project_id]
    vorhanden = next((f for f in formulare if _ist_startseite(f)), None)
    if vorhanden:
        return {"id": vorhanden.id, "slug": vorhanden.slug}
    gf = _gf_cockpit(formulare)
    if gf is None:
        raise HTTPException(400, "Für die Kennzahlen wird das Geschäftsführer-Cockpit gebraucht")
    schreiben_pruefen(gf.project_id, user, db)

    from app.services import report_catalog
    from app.api.forms import unique_slug
    gebaut = report_catalog.assemble(
        db, "Übersicht", [{"form_id": gf.id, "widget_id": w} for w in KENNZAHLEN_VORGABE],
        zeitraum_preset="this_month", project_id=gf.project_id)
    schema = gebaut["schema"]
    schema["rolle"] = ROLLE_STARTSEITE
    f = Form(name="Übersicht", project_id=gebaut["project_id"], schema=schema,
             created_by=user.id, slug=unique_slug(db, "uebersicht"), published=True,
             portal_config={"allowed_users": [], "allow_manual_run": True})
    db.add(f)
    safe_commit(db)
    db.refresh(f)
    return {"id": f.id, "slug": f.slug}


class EinstellungenIn(BaseModel):
    pins: Optional[List[int]] = None
    werkstatt_start: Optional[bool] = None


@router.get("/einstellungen")
def einstellungen_lesen(user: User = Depends(get_current_user)):
    e = _einstellungen(user)
    return {"pins": e.get("pins") or [], "werkstatt_start": bool(e.get("werkstatt_start"))}


@router.put("/einstellungen")
def einstellungen_speichern(data: EinstellungenIn, db: Session = Depends(get_db),
                            user: User = Depends(get_current_user)):
    e = _einstellungen(user)
    if data.pins is not None:
        # Nur Cockpits, die der Benutzer überhaupt sieht – sonst ließe sich über
        # die Pins herausfinden, welche Formular-IDs es gibt.
        sichtbar = {f.id for f in _sichtbare_formulare(user, db)}
        e["pins"] = [i for i in dict.fromkeys(data.pins) if i in sichtbar][:12]
    if data.werkstatt_start is not None:
        e["werkstatt_start"] = bool(data.werkstatt_start) and not _portal(user)
    user.einstellungen = e
    safe_commit(db)
    return {"pins": e.get("pins") or [], "werkstatt_start": bool(e.get("werkstatt_start"))}


@router.get("/status")
def status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Für „Einstellungen“: welche JTL-Verbindungen hängen an den eigenen Projekten,
    welche Version melden sie. Nur für Editoren und Admins."""
    if _portal(user):
        raise HTTPException(403, "Portal-Zugänge haben auf diesen Bereich keinen Zugriff.")
    from app.core.zugriff import erreichbare_verbindungen
    from app.models.dataset import DbConnection
    from app.services.jtl_kompatibilitaet import jtl_version

    erreichbar = erreichbare_verbindungen(user, db)
    q = db.query(DbConnection).filter(DbConnection.db_type == "mssql")
    if erreichbar is not None:
        q = q.filter(DbConnection.id.in_(erreichbar)) if erreichbar else q.filter(False)
    verbindungen = []
    for c in q.order_by(DbConnection.name).all():
        # Keine Version = keine JTL-Datenbank oder gerade nicht erreichbar. Beides
        # soll der Händler sehen, die Oberfläche sagt dann „nicht erreichbar“.
        verbindungen.append({"id": c.id, "name": c.mandant_label or c.name,
                             "server": c.host, "datenbank": c.database,
                             "jtl_version": jtl_version(c.id, db)})
    return {"verbindungen": verbindungen}
