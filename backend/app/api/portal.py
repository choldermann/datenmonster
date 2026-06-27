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
from app.api.forms import _execute_form, FormRunRequest

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
        "description":      pc.get("description", ""),
        "icon":             pc.get("icon", ""),
        "is_homepage":      pc.get("is_homepage", False),
        "allow_download":   pc.get("allow_download", False),
        "allow_manual_run": pc.get("allow_manual_run", True),
        # Schema ohne interne Details — nur Felder und Widgets
        "fields":           schema.get("fields", []),
        "widgets":          schema.get("widgets", []),
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
    pc = f.portal_config or {}
    allowed = pc.get("allowed_users") or []   # [] = alle authentifizierten Benutzer
    if allowed and user.username not in allowed and str(user.id) not in [str(u) for u in allowed]:
        raise HTTPException(403, "Kein Zugriff auf dieses Formular")


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

    result = _execute_form(f, data, db)

    # Download-Recht prüfen: wenn nicht erlaubt, Zeilen auf 100 begrenzen
    if not pc.get("allow_download", False):
        for action_id, r in result.get("results", {}).items():
            if isinstance(r, dict) and r.get("rows"):
                r["rows"] = r["rows"][:500]
                r["download_disabled"] = True

    return result
