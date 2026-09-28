"""Report-Baukasten: Katalog ausliefern und eine Auswahl zu einem Formular bauen.

Das Ergebnis ist ein ganz normales Formular – die Endpunkte hier legen es nur an,
bearbeitet und ausgeführt wird es im Form-Editor bzw. FormRunner.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel

from app.core.database import get_db, safe_commit
from app.api.auth import get_current_user
from app.models.user import User
from app.models.form import Form
from app.services import report_catalog
from app.core.zugriff import (ist_admin, lesen_pruefen, schreiben_pruefen,
                              verbindung_pruefen)

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _check_editor(user: User):
    if getattr(user, "is_portal_only", False):
        raise HTTPException(403, "Nur Admins und Editoren können Reports bauen")


def _quellen_pruefen(entries, user, db) -> None:
    """Jedes Quell-Cockpit muss lesbar sein – sonst ließen sich Abfragen fremder
    Projekte über einen eigenen Report herauskopieren."""
    ids = {e.form_id for e in entries}
    for f in db.query(Form).filter(Form.id.in_(ids)).all() if ids else []:
        lesen_pruefen(f.project_id, user, db)


def _lade_form(form_id, user, db, schreiben: bool = False, meldung="Formular nicht gefunden"):
    f = db.query(Form).filter(Form.id == form_id).first()
    if not f:
        raise HTTPException(404, meldung)
    if schreiben:
        schreiben_pruefen(f.project_id, user, db)
    else:
        lesen_pruefen(f.project_id, user, db)
    return f


class CatalogEntry(BaseModel):
    form_id: int
    widget_id: str


class BuildRequest(BaseModel):
    name: str
    entries: List[CatalogEntry]
    zeitraum_preset: Optional[str] = "this_month"
    project_id: Optional[int] = None


@router.get("/catalog")
def catalog(project_id: Optional[int] = None, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    """Alle wählbaren Bausteine, gruppiert nach Cockpit und Reiter."""
    _check_editor(user)
    if project_id is not None:
        lesen_pruefen(project_id, user, db)
    cockpits = report_catalog.build_catalog(db, project_id)
    if not ist_admin(user):
        # Ohne Projektfilter kämen sonst die Cockpits aller Projekte mit.
        from app.api.projects import can_read_project
        cockpits = [c for c in cockpits
                    if can_read_project(c.get("project_id"), user, db)]
    gesamt = sum(c["anzahl"] for c in cockpits)
    gesperrt = sum(1 for c in cockpits for r in c["reiter"]
                   for e in r["eintraege"] if not e["uebernehmbar"])
    return {"cockpits": cockpits, "gesamt": gesamt, "gesperrt": gesperrt}


@router.post("/build")
def build(data: BuildRequest, db: Session = Depends(get_db),
          user: User = Depends(get_current_user)):
    """Baut aus der Auswahl ein neues Formular und gibt dessen ID zurück."""
    _check_editor(user)
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(400, "Bitte einen Namen für den Report angeben")
    _quellen_pruefen(data.entries, user, db)

    try:
        gebaut = report_catalog.assemble(
            db, name,
            [e.model_dump() for e in data.entries],
            zeitraum_preset=data.zeitraum_preset or "this_month",
            project_id=data.project_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    # Zielprojekt erst nach assemble bekannt (ohne Angabe = Projekt der Quellen).
    schreiben_pruefen(gebaut["project_id"], user, db)

    f = Form(name=name, project_id=gebaut["project_id"],
             schema=gebaut["schema"], created_by=user.id)
    db.add(f)
    safe_commit(db)
    db.refresh(f)

    return {
        "id": f.id,
        "name": f.name,
        "project_id": f.project_id,
        "widgets": len(gebaut["schema"]["widgets"]),
        "actions": len(gebaut["schema"]["actions"]),
        "reiter": len(gebaut["schema"]["result_tabs"]),
        "uebersprungen": gebaut["uebersprungen"],
    }


@router.get("/selection/{form_id}")
def selection(form_id: int, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    """Die Bauteil-Auswahl eines Reports, um den Baukasten damit zu öffnen."""
    _check_editor(user)
    f = _lade_form(form_id, user, db)
    bau = (f.schema or {}).get("report_builder") or {}
    zeitraum = next((fd.get("config", {}).get("default")
                     for fd in (f.schema or {}).get("fields") or []
                     if fd.get("type") == "daterange"), None)
    return {
        "form_id": f.id, "name": f.name, "project_id": f.project_id,
        # Ohne Bauzettel ist es ein von Hand gebautes Formular. Der Baukasten
        # darf es dann nicht anfassen – er würde alles überschreiben.
        "gebaut": bool(bau),
        "entries": [{"form_id": e.get("form_id"), "widget_id": e.get("widget_id")}
                    for e in (bau.get("entries") or [])],
        "zeitraum_preset": zeitraum or bau.get("zeitraum_preset") or "this_month",
    }


@router.put("/build/{form_id}")
def rebuild(form_id: int, data: BuildRequest, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    """Ändert die Bausteine eines bestehenden Reports.

    Name, Adresse, Veröffentlichung und Zeitplan des Reports bleiben, damit ein
    verschickter Link und ein laufender Zustellplan nicht ins Leere zeigen.
    """
    _check_editor(user)
    f = _lade_form(form_id, user, db, schreiben=True)
    _quellen_pruefen(data.entries, user, db)
    if not ((f.schema or {}).get("report_builder")):
        raise HTTPException(400, "Dieses Formular wurde nicht mit dem Baukasten "
                                 "gebaut und lässt sich hier nicht ändern.")

    try:
        gebaut = report_catalog.assemble(
            db, data.name or f.name,
            [e.model_dump() for e in data.entries],
            zeitraum_preset=data.zeitraum_preset or "this_month",
            project_id=f.project_id,
            bestehend=f.schema or {},
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    f.schema = gebaut["schema"]
    if (data.name or "").strip():
        f.name = data.name.strip()
    f.version = (f.version or 1) + 1
    safe_commit(db)

    return {
        "id": f.id, "name": f.name, "project_id": f.project_id,
        "widgets": len(gebaut["schema"]["widgets"]),
        "actions": len(gebaut["schema"]["actions"]),
        "reiter": len(gebaut["schema"]["result_tabs"]),
        "uebersprungen": gebaut["uebersprungen"],
    }


# ── Zeitpläne ────────────────────────────────────────────────────────────────

class ScheduleIn(BaseModel):
    name: Optional[str] = None
    form_id: Optional[int] = None
    project_id: Optional[int] = None
    mandant_id: Optional[int] = None
    cron_expr: Optional[str] = None
    active: Optional[bool] = None
    zeitraum_preset: Optional[str] = None
    params: Optional[dict] = None
    sections: Optional[List[str]] = None
    email_to: Optional[str] = None
    email_subject: Optional[str] = None


def _schedule_pruefen(s, user, db, schreiben: bool = True) -> None:
    """Ein Zeitplan gehört zum Projekt seines Formulars. Fehlt das Formular,
    zählt das im Plan hinterlegte Projekt."""
    f = db.query(Form).filter(Form.id == s.form_id).first() if s.form_id else None
    pid = f.project_id if f else s.project_id
    if schreiben:
        schreiben_pruefen(pid, user, db)
    else:
        lesen_pruefen(pid, user, db)


def _schedule_out(s) -> dict:
    return {
        "id": s.id, "name": s.name, "form_id": s.form_id,
        "project_id": s.project_id, "mandant_id": s.mandant_id,
        "cron_expr": s.cron_expr, "active": bool(s.active),
        "zeitraum_preset": s.zeitraum_preset, "params": s.params or {},
        "sections": s.sections or [], "email_to": s.email_to,
        "email_subject": s.email_subject,
        "last_run_at": str(s.last_run_at or ""), "last_status": s.last_status,
        "last_message": s.last_message,
    }


@router.get("/schedules")
def list_schedules(form_id: Optional[int] = None, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    _check_editor(user)
    from app.models.report import ReportSchedule
    q = db.query(ReportSchedule)
    if form_id is not None:
        q = q.filter(ReportSchedule.form_id == form_id)
    plaene = q.order_by(ReportSchedule.id.desc()).all()
    if not ist_admin(user):
        # Pläne tragen Empfänger und Mandant – nur die eigener Projekte zeigen.
        from app.api.projects import can_read_project
        projekt_je_form = {f.id: f.project_id for f in db.query(Form).filter(
            Form.id.in_({s.form_id for s in plaene if s.form_id})).all()} if plaene else {}
        plaene = [s for s in plaene if can_read_project(
            projekt_je_form.get(s.form_id, s.project_id), user, db)]
    return [_schedule_out(s) for s in plaene]


@router.post("/schedules")
def create_schedule(data: ScheduleIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    _check_editor(user)
    from app.models.report import ReportSchedule
    from app.services.scheduler_service import register_report_job

    if not data.form_id:
        raise HTTPException(400, "form_id fehlt")
    f = _lade_form(data.form_id, user, db, schreiben=True,
                   meldung="Report-Formular nicht gefunden")
    # Der Plan läuft mit dem Projekt des Formulars; ein anderes Projekt hieße,
    # fremde Zahlen über das eigene Formular zu verschicken.
    if data.project_id is not None and data.project_id != f.project_id:
        raise HTTPException(403, "Der Zeitplan muss im Projekt des Formulars liegen")

    # Ohne ausdrückliche Wahl gilt der Mandant, den der Anlegende gerade offen
    # hat. Sonst fiele der Plan stumm auf den Projekt-Standard zurück und
    # verschickte Woche für Woche die Zahlen des falschen Betriebs — die
    # Zahlen wären in sich korrekt und der Fehler damit praktisch unsichtbar.
    pid = data.project_id if data.project_id is not None else f.project_id
    mandant_id = data.mandant_id
    if mandant_id is None:
        from app.services import mandant_service
        mandant_id = mandant_service.aktiver(pid, user, db)
    else:
        verbindung_pruefen(mandant_id, user, db)

    s = ReportSchedule(
        name=(data.name or f.name), form_id=data.form_id,
        project_id=pid,
        mandant_id=mandant_id,
        cron_expr=data.cron_expr or "0 6 * * 1",
        active=bool(data.active),
        zeitraum_preset=data.zeitraum_preset or "this_month",
        params=data.params or {}, sections=data.sections or [],
        email_to=data.email_to, email_subject=data.email_subject,
        created_by=user.id,
    )
    db.add(s)
    safe_commit(db)
    db.refresh(s)
    if s.active:
        register_report_job(s.id, s.cron_expr)
    return _schedule_out(s)


@router.put("/schedules/{schedule_id}")
def update_schedule(schedule_id: int, data: ScheduleIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    _check_editor(user)
    from app.models.report import ReportSchedule
    from app.services.scheduler_service import register_report_job, unregister_report_job

    s = db.query(ReportSchedule).filter(ReportSchedule.id == schedule_id).first()
    if not s:
        raise HTTPException(404, "Zeitplan nicht gefunden")
    _schedule_pruefen(s, user, db)
    if data.project_id is not None:
        f = db.query(Form).filter(Form.id == s.form_id).first() if s.form_id else None
        if data.project_id != (f.project_id if f else s.project_id):
            raise HTTPException(403, "Der Zeitplan muss im Projekt des Formulars liegen")
    if data.mandant_id is not None:
        verbindung_pruefen(data.mandant_id, user, db)

    for feld in ("name", "cron_expr", "active", "zeitraum_preset", "params",
                 "sections", "email_to", "email_subject", "mandant_id", "project_id"):
        wert = getattr(data, feld)
        if wert is not None:
            setattr(s, feld, wert)
    safe_commit(db)

    # Immer erst abmelden: eine geänderte Cron-Angabe darf nicht zusätzlich zur
    # alten laufen, und ein deaktivierter Plan muss wirklich still sein.
    unregister_report_job(s.id)
    if s.active:
        register_report_job(s.id, s.cron_expr)
    return _schedule_out(s)


@router.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: int, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    _check_editor(user)
    from app.models.report import ReportSchedule
    from app.services.scheduler_service import unregister_report_job

    s = db.query(ReportSchedule).filter(ReportSchedule.id == schedule_id).first()
    if not s:
        raise HTTPException(404, "Zeitplan nicht gefunden")
    _schedule_pruefen(s, user, db)
    unregister_report_job(s.id)
    db.delete(s)
    safe_commit(db)
    return {"ok": True}


@router.post("/schedules/{schedule_id}/run-now")
def run_schedule_now(schedule_id: int, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """„Jetzt testen" – rechnet und stellt sofort zu, im Hintergrund."""
    _check_editor(user)
    from app.models.report import ReportSchedule
    from app.services.scheduler_service import trigger_report_now
    from app.services.email_service import get_email_config

    s = db.query(ReportSchedule).filter(ReportSchedule.id == schedule_id).first()
    if not s:
        raise HTTPException(404, "Zeitplan nicht gefunden")
    # Sofortlauf verschickt Mails – das ist eine Änderung, kein Lesen.
    _schedule_pruefen(s, user, db)

    # Ein fehlender SMTP-Server ist der wahrscheinlichste Grund, warum keine Mail
    # ankommt. Das gehört als klare Ansage nach vorn, nicht als stiller Fehlschlag
    # ins Protokoll.
    hinweis = None
    if (s.email_to or "").strip():
        try:
            cfg = get_email_config(db) or {}
        except Exception:
            cfg = {}
        if not cfg.get("host"):
            hinweis = ("Kein SMTP-Server hinterlegt (Systemeinstellungen → E-Mail). "
                       "Der Report wird gerechnet, aber nicht zugestellt.")

    trigger_report_now(schedule_id)
    return {"gestartet": True, "hinweis": hinweis}
