"""
Portal-API — öffentliche Schicht für veröffentlichte Formulare.

Alle Endpunkte hier:
- erfordern Authentifizierung (selbe JWT wie Editor)
- geben KEINE Mapping- oder SQL-Details zurück
- prüfen ob der Benutzer Zugriff auf das konkrete Formular hat
- sind auch für is_portal_only-Benutzer zugänglich
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel

from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.models.form import Form
from app.api.forms import _execute_form, FormRunRequest, _slugify

router = APIRouter(prefix="/api/portal", tags=["portal"])


# ── Helpers ──────────────────────────────────────────────────────────────────

def _portal_form_out(f: Form) -> dict:
    """Gibt nur die für den Portal-Benutzer relevanten Felder zurück."""
    pc = f.portal_config or {}
    schema = f.schema or {}
    return {
        "id":               f.id,
        "name":             f.name,
        "slug":             f.slug,
        "project_id":       f.project_id,
        "description":      pc.get("description", ""),
        "icon":             pc.get("icon", ""),
        "is_homepage":      pc.get("is_homepage", False),
        "allow_download":   pc.get("allow_download", False),
        "allow_manual_run": pc.get("allow_manual_run", True),
        "show_ai_assistant": schema.get("show_ai_assistant", False),
        # Schema ohne interne Details — nur Felder, Widgets und Ergebnis-Register
        "fields":           schema.get("fields", []),
        "widgets":          schema.get("widgets", []),
        "result_tabs":      schema.get("result_tabs", []),
        # Actions: nur label und id, kein mapping_id
        "actions":          [
            {"id": a.get("id"), "label": a.get("label", "Ausführen"), "type": a.get("type")}
            for a in schema.get("actions", [])
        ],
    }


def _check_portal_access(f: Form, user: User) -> None:
    """Prüft ob der Benutzer Zugriff auf dieses veröffentlichte Formular hat."""
    if not f.published:
        raise HTTPException(404, "Formular nicht gefunden")
    if getattr(user, "is_admin", False):
        return  # Admins sehen/nutzen immer alle veröffentlichten Formulare
    pc = f.portal_config or {}
    allowed = pc.get("allowed_users") or []   # [] = alle authentifizierten Benutzer
    if allowed and user.username not in allowed and str(user.id) not in [str(u) for u in allowed]:
        raise HTTPException(403, "Kein Zugriff auf dieses Formular")


def user_can_access_portal_project(project_id: Optional[int], user: User, db: Session) -> bool:
    """True, wenn der User über mind. ein veröffentlichtes Formular Zugriff auf dieses
    Projekt hat. Erlaubt Portal-(Only-)Nutzern, für ein freigegebenes Formular die
    zugehörigen Projekt-Ressourcen zu nutzen (z.B. Artikel-Suche + Ausschlussartikel),
    ohne ihnen echten Projekt-Mitgliedsstatus zu geben."""
    if project_id is None:
        return False
    forms = (db.query(Form)
             .filter(Form.published == True, Form.project_id == project_id)
             .all())
    for f in forms:
        try:
            _check_portal_access(f, user)
            return True
        except HTTPException:
            continue
    return False


# ── Endpunkte ─────────────────────────────────────────────────────────────────

@router.get("/me")
def portal_me(user: User = Depends(get_current_user)):
    """Gibt zurück ob der Benutzer ein Portal-Only-Benutzer ist."""
    return {
        "id":             user.id,
        "username":       user.username,
        "is_admin":       bool(getattr(user, "is_admin", False)),
        "is_portal_only": bool(getattr(user, "is_portal_only", False)),
    }


@router.get("/forms")
def list_portal_forms(db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """Listet alle veröffentlichten Formulare auf, auf die der Benutzer Zugriff hat."""
    forms = db.query(Form).filter(Form.published == True).all()
    accessible = []
    for f in forms:
        try:
            _check_portal_access(f, user)
            accessible.append(_portal_form_out(f))
        except HTTPException:
            pass
    return accessible


@router.get("/forms/{slug}")
def get_portal_form(slug: str, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """Gibt ein veröffentlichtes Formular per Slug zurück."""
    f = db.query(Form).filter(Form.slug == slug).first()
    if not f:
        raise HTTPException(404, "Formular nicht gefunden")
    _check_portal_access(f, user)
    return _portal_form_out(f)


@router.post("/forms/{slug}/run")
def run_portal_form(slug: str, data: FormRunRequest,
                    db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """
    Führt ein veröffentlichtes Formular aus.
    Gibt Ergebnisse zurück, aber keine Mapping- oder SQL-Details.
    """
    f = db.query(Form).filter(Form.slug == slug).first()
    if not f:
        raise HTTPException(404, "Formular nicht gefunden")
    _check_portal_access(f, user)

    pc = f.portal_config or {}
    if not pc.get("allow_manual_run", True) and data.action_ids:
        raise HTTPException(403, "Manueller Start nicht erlaubt")

    result = _execute_form(f, data, db, user_id=user.id, user=user)

    # Download-Recht prüfen: wenn nicht erlaubt, Zeilen auf 100 begrenzen
    if not pc.get("allow_download", False):
        for action_id, r in result.get("results", {}).items():
            if isinstance(r, dict) and r.get("rows"):
                r["rows"] = r["rows"][:500]
                r["download_disabled"] = True

    return result


@router.post("/forms/{slug}/report")
async def portal_form_report(slug: str, data: FormRunRequest,
                             db: Session = Depends(get_db),
                             user: User = Depends(get_current_user)):
    """PDF-Report eines veröffentlichten Formulars – dasselbe Dokument wie im Editor.

    Zugriff wie beim Ausführen (veröffentlicht + allowed_users); zusätzlich gilt das
    Download-Recht des Formulars: wer die Daten nicht herunterladen darf, bekommt sie
    auch nicht als PDF.
    """
    from fastapi.responses import Response
    from datetime import datetime as _dt
    from app.services.cockpit_report import generate_report

    f = db.query(Form).filter(Form.slug == slug).first()
    if not f:
        raise HTTPException(404, "Formular nicht gefunden")
    _check_portal_access(f, user)

    pc = f.portal_config or {}
    if not pc.get("allow_download", False):
        raise HTTPException(403, "Für dieses Formular ist kein Download freigegeben")

    try:
        pdf = await generate_report(f, data.params or {}, db,
                                    precomputed_summary=data.ai_summary,
                                    sections=data.sections,
                                    provider=data.ai_provider,
                                    user=user)
    except Exception as e:
        raise HTTPException(500, f"Report-Fehler: {str(e)[:200]}")

    _umlaut = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe",
                             "Ü": "Ue", "ß": "ss"})
    fname = _slugify((f.name or "report").translate(_umlaut)) + "_" + _dt.now().strftime("%Y%m%d") + ".pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})
