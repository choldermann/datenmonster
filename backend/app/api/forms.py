import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime, timezone

from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.models.form import Form, FormSubmission
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


class DrilldownRequest(BaseModel):
    mapping_id: int
    params:     Optional[dict] = {}
    max_rows:   Optional[int] = 200


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


@router.post("/drilldown")
def drilldown(body: DrilldownRequest, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    """
    Mapping-basierter Drilldown (Stufe B): führt ein gespeichertes Mapping mit
    Laufzeit-Parametern (run_params) aus und gibt die Detailzeilen zurück – ohne
    ins Ziel zu schreiben. Nutzt denselben Preview-Lauf wie die run_mapping-Action
    (execute_mapping berechnet nur, _write_target wird nicht aufgerufen).
    """
    from app.api.projects import can_read_project
    from app.services.mapping_service import MappingContext, execute_mapping

    m = db.query(Mapping).filter(Mapping.id == body.mapping_id).first()
    if not m:
        raise HTTPException(404, "Mapping nicht gefunden")
    if not can_read_project(m.project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf dieses Mapping")

    ctx = MappingContext.from_orm(m)
    ctx.run_params = body.params or {}
    if not ctx.targets:
        return {"rows": [], "columns": [], "total": 0, "error": "Mapping hat keine Ziele"}

    # preview_rows <= 500 hält die Engine im Lese-/Vorschaumodus (kein Ziel-Write)
    rows_cap = min(max(body.max_rows or 200, 1), 500)
    t_fields = ctx.targets[0].get("fields") or []
    try:
        result = execute_mapping(**ctx.to_execute_kwargs(t_fields, rows_cap))
    except Exception as e:
        import traceback as _tb
        try:
            from app.services.db_logger import log as _dblog
            _dblog(db, "error", "forms", "drilldown_error",
                f"Drilldown-Fehler (Mapping {body.mapping_id}): {str(e)[:300]}",
                details={"exception_type": type(e).__name__,
                         "exception_message": str(e),
                         "traceback": _tb.format_exc()})
        except Exception:
            pass
        raise HTTPException(500, f"Drilldown-Fehler: {str(e)[:200]}")

    return {
        "columns": result.get("columns", []),
        "rows":    result.get("rows", []),
        "total":   result.get("total", 0),
    }


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
    return _execute_form(f, data, db, user_id=user.id)


# ── Submissions (protokollierte Formular-Läufe) ──────────────────────────────

@router.get("/{form_id}/submissions")
def list_submissions(form_id: int, limit: int = 100, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    _check_editor(user)
    f = db.query(Form).filter(Form.id == form_id).first()
    if not f:
        raise HTTPException(404, "Formular nicht gefunden")
    limit = max(1, min(limit, 500))
    subs = (db.query(FormSubmission)
            .filter(FormSubmission.form_id == form_id)
            .order_by(FormSubmission.submitted_at.desc())
            .limit(limit).all())
    # Feld-Reihenfolge/Labels aus dem Schema für die Anzeige
    fields = [
        {"name": fld.get("name"), "label": fld.get("label") or fld.get("name")}
        for fld in ((f.schema or {}).get("fields") or [])
        if fld.get("name") and fld.get("type") not in _LAYOUT_FIELD_TYPES and fld.get("type") != "button"
    ]
    return {
        "form_id": form_id,
        "fields": fields,
        "submissions": [{
            "id":           s.id,
            "params":       s.params or {},
            "action_ids":   s.action_ids,
            "status":       s.status,
            "error":        s.error,
            "row_counts":   s.row_counts or {},
            "submitted_by": s.submitted_by,
            "submitted_at": str(s.submitted_at or ""),
        } for s in subs],
    }


@router.delete("/{form_id}/submissions")
def clear_submissions(form_id: int, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    _check_editor(user)
    n = db.query(FormSubmission).filter(FormSubmission.form_id == form_id).delete()
    db.commit()
    return {"deleted": n}


# ── Shared execution logic ────────────────────────────────────────────────────

_LAYOUT_FIELD_TYPES = {"heading", "label", "divider", "container"}


def _validate_required(schema: dict, run_params: dict) -> None:
    """Wirft 422, wenn Pflichtfelder leer sind. Server-seitige Absicherung
    (der Client prüft ebenfalls, aber Portal-Aufrufe dürfen nicht darauf vertrauen)."""
    missing = []
    for fld in (schema.get("fields") or []):
        if not fld.get("required") or fld.get("type") == "button" or fld.get("type") in _LAYOUT_FIELD_TYPES:
            continue
        name = fld.get("name")
        if not name:
            continue
        v = run_params.get(name)
        if v is None or v == "" or v is False or (isinstance(v, list) and len(v) == 0):
            missing.append(fld.get("label") or name)
    if missing:
        raise HTTPException(422, f"Pflichtfelder fehlen: {', '.join(missing)}")


def _execute_form(f: Form, data: FormRunRequest, db: Session,
                  user_id: Optional[int] = None) -> dict:
    schema = f.schema or {}
    run_params = data.params or {}
    _validate_required(schema, run_params)

    actions = schema.get("actions") or []
    if data.action_ids:
        actions = [a for a in actions if a.get("id") in data.action_ids]

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

        elif action_type == "run_pipeline":
            pipeline_id = action.get("pipeline_id")
            if not pipeline_id:
                results[action_id] = {"kind": "pipeline", "error": "pipeline_id fehlt"}
                continue
            from app.models.pipeline import Pipeline
            p = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
            if not p:
                results[action_id] = {"kind": "pipeline",
                                      "error": f"Pipeline {pipeline_id} nicht gefunden"}
                continue
            try:
                from app.services.pipeline_service import run_pipeline as _run_pipeline
                pres = _run_pipeline(p, db)
                p.last_run_at = datetime.now(timezone.utc)
                p.last_run_status = "success" if not pres.get("errors") else "warning"
                db.commit()
                perrors = pres.get("errors") or []
                results[action_id] = {
                    "kind":           "pipeline",
                    "pipeline_name":  p.name,
                    "nodes_executed": pres.get("nodes_executed", 0),
                    "errors":         perrors,
                    "error":          perrors[0] if perrors else None,
                    "columns": [], "rows": [], "total": 0,
                }
            except Exception as e:
                results[action_id] = {"kind": "pipeline", "columns": [], "rows": [],
                                      "total": 0, "error": str(e)[:300]}

        else:
            results[action_id] = {"error": f"Unbekannter Action-Typ: {action_type}"}

    # Lauf als Submission protokollieren (nur die Eingaben + Zusammenfassung, nicht die vollen Daten)
    has_error = any((r or {}).get("error") for r in results.values())
    first_error = next((r["error"] for r in results.values() if (r or {}).get("error")), None)
    row_counts = {aid: (r or {}).get("total", 0) for aid, r in results.items()}
    try:
        db.add(FormSubmission(
            form_id=f.id,
            params=run_params,
            action_ids=data.action_ids,
            status="error" if has_error else "success",
            error=first_error,
            row_counts=row_counts,
            submitted_by=user_id,
        ))
        db.commit()
    except Exception:
        db.rollback()

    return {"form_id": f.id, "results": results}
