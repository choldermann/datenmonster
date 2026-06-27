import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime, timezone

from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.models.form import Form
from app.models.mapping import Mapping

router = APIRouter(prefix="/api/forms", tags=["forms"])


# ── Pydantic Schemas ─────────────────────────────────────────────────────────

class FormCreate(BaseModel):
    name: str
    project_id: Optional[int] = None
    schema: Optional[dict] = None


class FormUpdate(BaseModel):
    name: Optional[str] = None
    project_id: Optional[int] = None
    schema: Optional[dict] = None
    slug: Optional[str] = None
    published: Optional[bool] = None
    portal_config: Optional[dict] = None


class FormRunRequest(BaseModel):
    params: Optional[dict] = {}
    action_ids: Optional[List[str]] = None
    preview_rows: Optional[int] = 500


# ── Helpers ──────────────────────────────────────────────────────────────────

def form_out(f: Form) -> dict:
    return {
        "id":            f.id,
        "name":          f.name,
        "project_id":    f.project_id,
        "schema":        f.schema or {},
        "version":       f.version or 1,
        "slug":          f.slug,
        "published":     bool(f.published),
        "portal_config": f.portal_config or {},
        "created_at":    str(f.created_at or ""),
        "updated_at":    str(f.updated_at or ""),
        "created_by":    f.created_by,
    }


def _empty_schema() -> dict:
    return {
        "fields":  [],
        "layout":  [],
        "actions": [],
        "widgets": [],
    }


def _slugify(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[äöüß ]", lambda m: {"ä":"ae","ö":"oe","ü":"ue","ß":"ss"," ":"-"}.get(m.group(), "-"), s)
    s = re.sub(r"[^a-z0-9-]", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "formular"


def _check_editor(user: User):
    if getattr(user, "is_portal_only", False):
        raise HTTPException(403, "Nur Admins und Editoren können Formulare bearbeiten")


# ── CRUD ─────────────────────────────────────────────────────────────────────

@router.get("/")
def list_forms(project_id: Optional[int] = None, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    _check_editor(user)
    q = db.query(Form)
    if project_id is not None:
        q = q.filter(Form.project_id == project_id)
    return [form_out(f) for f in q.order_by(Form.updated_at.desc()).all()]


@router.post("/")
def create_form(data: FormCreate, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    _check_editor(user)
    slug = _slugify(data.name)
    # Eindeutigkeit sicherstellen
    base, n = slug, 1
    while db.query(Form).filter(Form.slug == slug).first():
        slug = f"{base}-{n}"; n += 1
    f = Form(
        name=data.name,
        project_id=data.project_id,
        schema=data.schema or _empty_schema(),
        version=1,
        slug=slug,
        published=False,
        portal_config={},
        created_by=user.id,
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return form_out(f)


@router.get("/{form_id}")
def get_form(form_id: int, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    _check_editor(user)
    f = db.query(Form).filter(Form.id == form_id).first()
    if not f:
        raise HTTPException(404, "Formular nicht gefunden")
    return form_out(f)


@router.put("/{form_id}")
def update_form(form_id: int, data: FormUpdate, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    _check_editor(user)
    f = db.query(Form).filter(Form.id == form_id).first()
    if not f:
        raise HTTPException(404, "Formular nicht gefunden")

    if data.name is not None:
        f.name = data.name
    if data.project_id is not None:
        f.project_id = data.project_id
    if data.schema is not None:
        f.schema = data.schema
        f.version = (f.version or 1) + 1
    if data.slug is not None:
        slug = _slugify(data.slug) or _slugify(f.name)
        # Eindeutigkeit: anderes Formular mit diesem Slug?
        existing = db.query(Form).filter(Form.slug == slug, Form.id != form_id).first()
        if existing:
            raise HTTPException(409, f"Slug '{slug}' ist bereits vergeben")
        f.slug = slug
    if data.published is not None:
        f.published = data.published
    if data.portal_config is not None:
        f.portal_config = data.portal_config

    f.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(f)
    return form_out(f)


@router.delete("/{form_id}")
def delete_form(form_id: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    _check_editor(user)
    f = db.query(Form).filter(Form.id == form_id).first()
    if not f:
        raise HTTPException(404, "Formular nicht gefunden")
    db.delete(f)
    db.commit()
    return {"ok": True}


# ── Run (Editor-Kontext, voller Zugriff) ─────────────────────────────────────

@router.post("/{form_id}/run")
def run_form(form_id: int, data: FormRunRequest,
             db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    _check_editor(user)
    f = db.query(Form).filter(Form.id == form_id).first()
    if not f:
        raise HTTPException(404, "Formular nicht gefunden")
    return _execute_form(f, data, db)


# ── Shared execution logic ────────────────────────────────────────────────────

def _execute_form(f: Form, data: FormRunRequest, db: Session) -> dict:
    schema = f.schema or {}
    actions = schema.get("actions") or []
    if data.action_ids:
        actions = [a for a in actions if a.get("id") in data.action_ids]

    run_params = data.params or {}
    preview_rows = data.preview_rows or 500
    results = {}

    for action in actions:
        action_id  = action.get("id")
        action_type = action.get("type")

        if action_type == "run_mapping":
            mapping_id = action.get("mapping_id")
            if not mapping_id:
                results[action_id] = {"columns": [], "rows": [], "total": 0,
                                      "error": "mapping_id fehlt"}
                continue
            m = db.query(Mapping).filter(Mapping.id == mapping_id).first()
            if not m:
                results[action_id] = {"columns": [], "rows": [], "total": 0,
                                      "error": f"Mapping {mapping_id} nicht gefunden"}
                continue
            try:
                from app.services.mapping_service import MappingContext, execute_mapping
                ctx = MappingContext.from_orm(m)
                ctx.run_params = run_params
                if not ctx.targets:
                    results[action_id] = {"columns": [], "rows": [], "total": 0,
                                          "error": "Mapping hat keine Ziele"}
                    continue
                t_fields = ctx.targets[0].get("fields") or []
                result = execute_mapping(**ctx.to_execute_kwargs(t_fields, preview_rows))
                results[action_id] = {
                    "columns":      result.get("columns", []),
                    "rows":         result.get("rows", []),
                    "total":        result.get("total", 0),
                    "column_types": result.get("column_types", {}),
                    "error":        None,
                }
            except Exception as e:
                results[action_id] = {"columns": [], "rows": [], "total": 0,
                                      "error": str(e)[:300]}
        else:
            results[action_id] = {"error": f"Unbekannter Action-Typ: {action_type}"}

    return {"form_id": f.id, "results": results}
