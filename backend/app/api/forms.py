import re
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    # Beim PDF-Report: bereits im Formular erzeugte KI-Analyse mitgeben, damit der
    # Report den (langsamen, timeout-gefährdeten) KI-Aufruf überspringen kann.
    ai_summary: Optional[str] = None
    # Beim PDF-Report: Auswahl der Abschnitte (Reiter-IDs sowie die Pseudo-IDs
    # "__summary__" / "__assessment__"). None = alles wie bisher.
    sections: Optional[List[str]] = None


class DrilldownRequest(BaseModel):
    mapping_id: int
    params:     Optional[dict] = {}
    max_rows:   Optional[int] = 200


class EmailTableRequest(BaseModel):
    recipients: str                      # Komma-/Semikolon-getrennt
    subject:    Optional[str] = None
    message:    Optional[str] = None
    title:      Optional[str] = None
    columns:    Optional[List[str]] = None
    rows:       List[dict]
    filename:   Optional[str] = None


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
    from app.services.article_exclusion_service import apply_article_exclusions
    ctx.run_params = apply_article_exclusions(body.params or {}, m.project_id, db)
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


@router.post("/email-table")
def email_table(body: EmailTableRequest, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    """
    Verschickt eine (im Modal angezeigte) Tabelle per E-Mail an Mitarbeiter –
    als HTML-Vorschau im Body plus CSV-Anhang zum Bearbeiten (z.B. Artikel-
    beschreibungen). Nutzt die SMTP-Konfiguration aus den Systemeinstellungen.
    """
    from app.services.email_service import send_email, get_email_config

    recipients = [r.strip() for r in re.split(r"[,;]", body.recipients or "") if r.strip()]
    if not recipients:
        raise HTTPException(400, "Keine Empfänger angegeben")
    if not all(re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", r) for r in recipients):
        raise HTTPException(400, "Mindestens eine E-Mail-Adresse ist ungültig")
    if not get_email_config(db).get("host"):
        raise HTTPException(400, "SMTP ist nicht konfiguriert (Systemeinstellungen → E-Mail)")

    rows = body.rows or []
    cols = body.columns or (list(rows[0].keys()) if rows else [])
    title = body.title or "Tabelle"

    # CSV (RFC-4180, ';' als Trenner, BOM für Excel)
    def _csv(v):
        s = "" if v is None else str(v)
        return '"' + s.replace('"', '""') + '"' if re.search(r'[";\n]', s) else s
    csv_lines = [";".join(_csv(c) for c in cols)]
    csv_lines += [";".join(_csv(r.get(c)) for c in cols) for r in rows]
    csv_bytes = ("﻿" + "\n".join(csv_lines)).encode("utf-8")

    # HTML-Vorschau
    def _h(v):
        s = "" if v is None else str(v)
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    thead = "".join(f"<th style='text-align:left;padding:6px 10px;border-bottom:2px solid #ccc;'>{_h(c)}</th>" for c in cols)
    tbody = "".join("<tr>" + "".join(f"<td style='padding:5px 10px;border-bottom:1px solid #eee;'>{_h(r.get(c))}</td>" for c in cols) + "</tr>" for r in rows)
    intro = _h(body.message).replace("\n", "<br>") if body.message else ""
    sender = getattr(user, "username", None) or getattr(user, "email", None) or "Cockpit"
    html = (
        "<div style=\"font-family:Arial,sans-serif;font-size:13px;color:#222;\">"
        + (f"<p>{intro}</p>" if intro else "")
        + f"<p><b>{_h(title)}</b> – {len(rows)} Zeilen (Tabelle auch als CSV im Anhang zum Bearbeiten)</p>"
        + f"<table style=\"border-collapse:collapse;font-size:12px;\"><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>"
        + f"<p style=\"color:#888;font-size:11px;margin-top:14px;\">Gesendet aus dem Datenmonster GF-Cockpit von {_h(sender)}.</p></div>"
    )
    plain = (f"{body.message}\n\n" if body.message else "") + f"{title} – {len(rows)} Zeilen. Details siehe CSV-Anhang."
    fname = (body.filename or re.sub(r"[^a-zA-Z0-9]+", "_", title)[:40] or "tabelle") + ".csv"

    try:
        send_email(
            to=recipients[0],
            cc=",".join(recipients[1:]) if len(recipients) > 1 else None,
            subject=body.subject or f"Cockpit: {title}",
            body=plain, html_body=html, db=db,
            attachments=[{"filename": fname, "data": csv_bytes, "mime": "text/csv"}],
        )
    except Exception as e:
        raise HTTPException(500, f"E-Mail-Versand fehlgeschlagen: {str(e)[:200]}")
    return {"ok": True, "recipients": recipients, "rows": len(rows)}


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


@router.post("/{form_id}/report")
async def form_report(form_id: int, data: FormRunRequest,
                      db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """Erzeugt aus einem Dashboard-Formular einen PDF-Report (Deckblatt + Reiter)."""
    from fastapi.responses import Response
    from app.services.cockpit_report import generate_report
    _check_editor(user)
    f = db.query(Form).filter(Form.id == form_id).first()
    if not f:
        raise HTTPException(404, "Formular nicht gefunden")
    try:
        pdf = await generate_report(f, data.params or {}, db,
                                    precomputed_summary=data.ai_summary,
                                    sections=data.sections)
    except Exception as e:
        import traceback as _tb
        raise HTTPException(500, f"Report-Fehler: {str(e)[:200]}\n{_tb.format_exc()[-400:]}")
    _umlaut = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe",
                             "Ü": "Ue", "ß": "ss"})
    fname = _slugify((f.name or "report").translate(_umlaut)) + "_" + datetime.now().strftime("%Y%m%d") + ".pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


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


# Cockpit-artige Formulare lösen mit EINEM Klick viele unabhängige, read-only
# Mapping-Abfragen aus. Nacheinander summieren die sich zu >60 s und laufen dann in
# Proxy-/Client-Timeouts (»Network Error«). Da es reine Lese-Abfragen sind, führen
# wir sie gedrosselt PARALLEL aus – 5 = Kompromiss aus Tempo und Last auf der
# Quell-DB (z.B. produktive JTL-WaWi). Viele Cockpit-Abfragen sind zudem
# zeitraum-unabhängig (Lagerbestand), daher hilft ein kleinerer Zeitraum allein nicht.
_FORM_RUN_CONCURRENCY = 5

# Obergrenze für als "full_rows" markierte Tabellen-Widgets (z.B. Cockpit-Listen).
# Hebt die hartkodierten TOP N der Mapping-SQLs an (via _apply_row_cap) und den
# 50er-Preview-Cap auf, sodass die Tabelle möglichst vollständig geladen wird
# (UI-Anzeige = Basis für E-Mail-/CSV-Export). Bewusst begrenzt, damit sehr große
# Abfragen die Quell-WaWi und das Browser-Rendering nicht überlasten.
FULL_ROWS_CAP = 2000


def _expandable_action_ids(schema: dict) -> set:
    """Action-IDs, deren Tabellen-Widget vollständig (bis FULL_ROWS_CAP) laden soll
    – markiert per config.full_rows am table-Widget. Rankings/Charts/KPIs bleiben
    dadurch unberührt."""
    out = set()
    for w in (schema.get("widgets") or []):
        if w.get("type") == "table" and (w.get("config") or {}).get("full_rows"):
            aid = w.get("action_id")
            if aid:
                out.add(aid)
    return out


def _run_mapping_preview(action: dict, run_params: dict, preview_rows: int,
                         row_cap: int = None) -> dict:
    """Führt EINE run_mapping-Action read-only aus. Öffnet eine EIGENE DB-Session
    (SQLAlchemy-Sessions sind nicht thread-sicher), damit die Funktion gefahrlos
    parallel laufen kann. Gibt das fertige Ergebnis-Dict für results[action_id] zurück."""
    from app.core.database import SessionLocal
    from app.services.mapping_service import MappingContext, execute_mapping
    mapping_id = action.get("mapping_id")
    if not mapping_id:
        return {"columns": [], "rows": [], "total": 0, "error": "mapping_id fehlt"}
    db = SessionLocal()
    try:
        m = db.query(Mapping).filter(Mapping.id == mapping_id).first()
        if not m:
            return {"columns": [], "rows": [], "total": 0,
                    "error": f"Mapping {mapping_id} nicht gefunden"}
        ctx = MappingContext.from_orm(m)
        ctx.run_params = dict(run_params)  # eigene Kopie je Thread (keine geteilte Mutation)
        if not ctx.targets:
            return {"columns": [], "rows": [], "total": 0, "error": "Mapping hat keine Ziele"}
        t_fields = ctx.targets[0].get("fields") or []
        result = execute_mapping(**ctx.to_execute_kwargs(t_fields, preview_rows), row_cap=row_cap)
        _rows = result.get("rows", [])
        # Fehler (z.B. SQL-Transform-Fehler) nur zeigen, wenn keine Zeilen kamen –
        # harmlose Warnungen sollen die Ergebnistabelle nicht verdecken.
        _errs = [str(e) for e in (result.get("errors") or []) if str(e).strip()]
        return {
            "columns":      result.get("columns", []),
            "rows":         _rows,
            "total":        result.get("total", 0),
            "column_types": result.get("column_types", {}),
            "error":        ("; ".join(_errs) if (_errs and not _rows) else None),
        }
    except Exception as e:
        return {"columns": [], "rows": [], "total": 0, "error": str(e)[:300]}
    finally:
        db.close()


def _execute_form(f: Form, data: FormRunRequest, db: Session,
                  user_id: Optional[int] = None) -> dict:
    schema = f.schema or {}
    run_params = data.params or {}
    _validate_required(schema, run_params)

    from app.services.article_exclusion_service import apply_article_exclusions
    run_params = apply_article_exclusions(run_params, f.project_id, db)

    actions = schema.get("actions") or []
    if data.action_ids:
        actions = [a for a in actions if a.get("id") in data.action_ids]

    preview_rows = data.preview_rows or 500
    results = {}

    # Als full_rows markierte Tabellen (z.B. Cockpit-Listen) vollständig laden.
    expandable = _expandable_action_ids(schema)
    def _cap_for(a):
        return FULL_ROWS_CAP if a.get("id") in expandable else None

    # Read-only Mapping-Vorschauen gedrosselt parallel (der große Zeitgewinn bei
    # Cockpit-Formularen). Übrige Action-Typen laufen danach sequenziell weiter.
    mapping_actions = [a for a in actions if a.get("type") == "run_mapping"]
    if len(mapping_actions) == 1:
        a0 = mapping_actions[0]
        results[a0.get("id")] = _run_mapping_preview(a0, run_params, preview_rows, _cap_for(a0))
    elif mapping_actions:
        with ThreadPoolExecutor(max_workers=_FORM_RUN_CONCURRENCY) as ex:
            futs = {ex.submit(_run_mapping_preview, a, run_params, preview_rows, _cap_for(a)): a.get("id")
                    for a in mapping_actions}
            for fut in as_completed(futs):
                results[futs[fut]] = fut.result()

    for action in actions:
        action_id  = action.get("id")
        action_type = action.get("type")

        if action_type == "run_mapping":
            continue  # bereits parallel oben erledigt

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

        elif action_type == "export_mapping":
            # Schreib-Lauf: führt das Mapping aus und schreibt seine Datei-Ziele
            # (z.B. .idev + CSV) – im Gegensatz zu run_mapping (nur Vorschau).
            mapping_id = action.get("mapping_id")
            m = db.query(Mapping).filter(Mapping.id == mapping_id).first() if mapping_id else None
            if not m:
                results[action_id] = {"kind": "export", "targets": [], "files": [],
                                      "total": 0, "error": f"Mapping {mapping_id} nicht gefunden"}
                continue
            try:
                from app.services.mapping_service import MappingContext, run_mapping_object
                from app.models.export_file import ExportFile
                from app.models.project import Project
                ctx = MappingContext.from_orm(m)
                ctx.run_params = run_params
                _proj = db.query(Project).filter(Project.id == m.project_id).first() if m.project_id else None
                result = run_mapping_object(
                    ctx, preview_rows=999999, db=db,
                    mapping_id=m.id, mapping_name=m.name,
                    project_id=m.project_id,
                    project_name=(_proj.name if _proj else None),
                    user_id=(user_id or 1),
                    triggered_by="form",
                )
                tr = result.get("targets_results") or []
                _errs = [str(e) for e in (result.get("errors") or []) if str(e).strip()]
                # Die soeben erzeugten Datei-Exporte holen (neueste zuerst → für Download-Links)
                _recent = (db.query(ExportFile)
                           .filter(ExportFile.mapping_id == m.id)
                           .order_by(ExportFile.id.desc())
                           .limit(max(len(tr), 1)).all())
                files = [{"id": ef.id, "file_name": ef.file_name, "target_name": ef.target_name}
                         for ef in reversed(_recent)]
                results[action_id] = {
                    "kind":    "export",
                    "targets": tr,
                    "total":   result.get("total_rows_written", 0),
                    "files":   files,
                    "error":   ("; ".join(_errs) if (_errs and not tr) else None),
                }
            except Exception as e:
                results[action_id] = {"kind": "export", "targets": [], "files": [],
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
