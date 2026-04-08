import traceback
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List, Any
from pydantic import BaseModel
import json
from datetime import datetime, timezone
from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.models.report import Report

router = APIRouter(prefix="/api/reports", tags=["reports"])


def report_out(r):
    return {
        "id": r.id, "name": r.name, "project_id": r.project_id,
        "widgets": r.widgets or [],
        "created_at": str(r.created_at or ""),
        "updated_at": str(r.updated_at or ""),
    }


class ReportBody(BaseModel):
    name: str
    project_id: Optional[int] = None
    widgets: Optional[List[Any]] = []


@router.get("/")
def list_reports(project_id: Optional[int] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Report)
    if project_id:
        q = q.filter(Report.project_id == project_id)
    return [report_out(r) for r in q.order_by(Report.id.desc()).all()]


@router.post("/")
def create_report(body: ReportBody, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    r = Report(**body.dict())
    db.add(r); db.commit(); db.refresh(r)
    return report_out(r)


@router.get("/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    r = db.query(Report).filter(Report.id == report_id).first()
    if not r: raise HTTPException(404, "Nicht gefunden")
    return report_out(r)


@router.put("/{report_id}")
def update_report(report_id: int, body: ReportBody, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    r = db.query(Report).filter(Report.id == report_id).first()
    if not r: raise HTTPException(404, "Nicht gefunden")
    for k, v in body.dict().items():
        setattr(r, k, v)
    r.updated_at = datetime.now(timezone.utc)
    db.commit(); db.refresh(r)
    return report_out(r)


@router.delete("/{report_id}")
def delete_report(report_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    r = db.query(Report).filter(Report.id == report_id).first()
    if not r: raise HTTPException(404, "Nicht gefunden")
    db.delete(r); db.commit()
    return {"ok": True}


class WidgetDataRequest(BaseModel):
    widget_id: Optional[str] = None
    dataset_id: Optional[int] = None
    sql: Optional[str] = None
    connection_id: Optional[int] = None
    filters: Optional[str] = "{}"
    filter_fields: Optional[str] = "[]"


@router.post("/widget-data")
def get_widget_data(body: WidgetDataRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Liefert Daten für ein Widget mit aktiven Filtern."""
    import pandas as pd
    from app.services.file_service import read_dataset
    from app.models.dataset import Dataset

    try:
        active_filters = json.loads(body.filters or "{}")
        filter_fields = json.loads(body.filter_fields or "[]")
    except Exception:
        active_filters = {}
        filter_fields = []

    df = None

    if body.dataset_id:
        ds = db.query(Dataset).filter(Dataset.id == body.dataset_id).first()
        if not ds:
            raise HTTPException(404, "Dataset nicht gefunden")
        try:
            from app.services.file_service import read_dataset as _read_ds
            import pandas as pd
            result = _read_ds(ds.id, page=0, page_size=99999)
            df = pd.DataFrame(result.get("preview", []))
        except Exception as e:
            raise HTTPException(500, f"Fehler beim Laden: {str(e)[:200]}")

    elif body.sql and body.connection_id:
        try:
            from app.services.db_service import execute_query
            rows = execute_query(body.connection_id, body.sql, db)
            df = pd.DataFrame(rows)
        except Exception as e:
            try:
                from app.services.db_logger import log as _dblog
                _dblog(db, "error", "reports", "sql_error",
                    f"SQL Fehler: {str(e)[:300]}",
                    details={"exception_type": type(e).__name__,
                             "exception_message": str(e),
                             "traceback": __import__('traceback').format_exc()})
            except Exception:
                pass
            raise HTTPException(500, f"SQL Fehler: {str(e)[:200]}")

    if df is None or df.empty:
        return {"rows": [], "columns": []}

    # Filter anwenden
    for ff in filter_fields:
        field = ff.get("field") if isinstance(ff, dict) else ff
        val = active_filters.get(field)
        if not val or field not in df.columns:
            continue

        if isinstance(val, dict):
            # Datumsbereich
            if val.get("from"):
                try:
                    df[field] = pd.to_datetime(df[field], errors="coerce")
                    df = df[df[field] >= pd.to_datetime(val["from"])]
                except Exception as _fe:
                    import logging as _l; _l.getLogger("datenmonster").debug(f"Filter '{field}' von: {_fe}")
            if val.get("to"):
                try:
                    df = df[df[field] <= pd.to_datetime(val["to"])]
                except Exception as _fe:
                    import logging as _l; _l.getLogger("datenmonster").debug(f"Filter '{field}' bis: {_fe}")
        elif val:
            # Exakter Match oder Textsuche
            try:
                df = df[df[field].astype(str).str.contains(str(val), case=False, na=False)]
            except Exception as _fe:
                import logging as _l; _l.getLogger("datenmonster").debug(f"Filter '{field}' text: {_fe}")

    # NaN bereinigen
    df = df.where(df.notna(), other=None)
    rows = df.to_dict("records")

    return {"rows": rows[:5000], "columns": list(df.columns), "total": len(df)}


@router.get("/filter-options")
def get_filter_options(dataset_id: int, field: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Liefert DISTINCT-Werte einer Spalte für Filter-Dropdowns."""
    from app.services.file_service import read_dataset
    from app.models.dataset import Dataset

    ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not ds:
        raise HTTPException(404, "Dataset nicht gefunden")

    try:
        from app.services.file_service import read_dataset as _read_ds
        df = _read_ds(ds)
        if field not in df.columns:
            return {"values": []}
        values = sorted([str(v) for v in df[field].dropna().unique() if v is not None])[:200]
        return {"values": values}
    except Exception as e:
        return {"values": []}


@router.post("/sql-columns")
def get_sql_columns(body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Gibt die Spalten einer SQL-Abfrage zurück."""
    sql = body.get("sql", "")
    connection_id = body.get("connection_id")
    if not sql or not connection_id:
        return {"columns": []}
    try:
        from app.services.db_service import execute_query
        rows = execute_query(connection_id, f"SELECT TOP 1 * FROM ({sql}) AS _q", db)
        return {"columns": list(rows[0].keys()) if rows else []}
    except Exception as e:
        return {"columns": [], "error": str(e)[:200]}


class PdfExportRequest(BaseModel):
    widget_ids: Optional[List[str]] = None   # None = alle Widgets
    filters:    Optional[str] = "{}"         # aktive Filter als JSON-String


@router.post("/{report_id}/pdf")
def export_report_pdf(
    report_id: int,
    body: PdfExportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generiert ein PDF des Reports und gibt es als Download zurück."""
    from fastapi.responses import Response
    from app.services.pdf_service import generate_report_pdf
    import json as _json

    r = db.query(Report).filter(Report.id == report_id).first()
    if not r:
        raise HTTPException(404, "Report nicht gefunden")

    widgets = r.widgets or []
    if body.widget_ids:
        widgets = [w for w in widgets if w.get("id") in body.widget_ids]

    try:
        active_filters = _json.loads(body.filters or "{}")
    except Exception:
        active_filters = {}

    # Daten für alle Widgets laden (gleiche Logik wie widget-data Endpoint)
    import pandas as pd
    widget_data = {}
    for widget in widgets:
        wid    = widget.get("id", "")
        config = widget.get("config", {})
        df     = None

        try:
            if config.get("dataset_id"):
                from app.models.dataset import Dataset
                from app.services.file_service import read_dataset as _read_ds
                ds = db.query(Dataset).filter(Dataset.id == config["dataset_id"]).first()
                if ds:
                    result = _read_ds(ds.id, page=0, page_size=99999)
                    df = pd.DataFrame(result.get("preview", []))

            elif config.get("sql") and config.get("connection_id"):
                from app.services.db_service import execute_query
                rows = execute_query(config["connection_id"], config["sql"], db)
                df = pd.DataFrame(rows)

            if df is not None and not df.empty:
                # Filter anwenden
                filter_fields = config.get("filter_fields") or []
                for ff in filter_fields:
                    field = ff.get("field") if isinstance(ff, dict) else ff
                    val   = active_filters.get(field)
                    if not val or field not in df.columns:
                        continue
                    try:
                        df = df[df[field].astype(str).str.contains(str(val), case=False, na=False)]
                    except Exception:
                        pass

                df = df.where(df.notna(), other=None)
                widget_data[wid] = df.to_dict("records")
            else:
                widget_data[wid] = []
        except Exception as e:
            widget_data[wid] = []

    try:
        pdf_bytes = generate_report_pdf(
            report_name  = r.name,
            widgets      = widgets,
            widget_data  = widget_data,
            created_at   = str(r.updated_at or r.created_at or ""),
        )
    except Exception as e:
        try:
            from app.services.db_logger import log as _dblog
            _dblog(db, "error", "reports", "pdf_error",
                f"PDF-Generierung fehlgeschlagen: {str(e)[:300]}",
                details={"exception_type": type(e).__name__,
                         "exception_message": str(e),
                         "traceback": traceback.format_exc()})
        except Exception:
            pass
        raise HTTPException(500, f"PDF-Generierung fehlgeschlagen: {str(e)[:300]}")

    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in r.name)
    return Response(
        content     = pdf_bytes,
        media_type  = "application/pdf",
        headers     = {"Content-Disposition": f"attachment; filename={safe_name}.pdf"},
    )


class EmailReportRequest(BaseModel):
    to:      str
    cc:      Optional[str] = None
    subject: Optional[str] = None
    body:    Optional[str] = None
    filters: Optional[str] = "{}"


@router.post("/{report_id}/email")
def email_report_pdf(
    report_id: int,
    body: EmailReportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generiert Report-PDF und verschickt es per E-Mail."""
    from app.services.pdf_service import generate_report_pdf
    from app.services.email_service import send_email, get_email_config
    import json as _json
    import pandas as pd

    r = db.query(Report).filter(Report.id == report_id).first()
    if not r:
        raise HTTPException(404, "Report nicht gefunden")

    config = get_email_config(db)
    if not config.get("host"):
        raise HTTPException(400, "E-Mail nicht konfiguriert – bitte SMTP-Einstellungen prüfen")

    # Gleiche Datenlade-Logik wie PDF-Export
    widgets = r.widgets or []
    try:
        active_filters = _json.loads(body.filters or "{}")
    except Exception:
        active_filters = {}

    widget_data = {}
    for widget in widgets:
        wid    = widget.get("id", "")
        config_w = widget.get("config", {})
        df     = None
        try:
            if config_w.get("dataset_id"):
                from app.models.dataset import Dataset
                from app.services.file_service import read_dataset as _read_ds
                ds = db.query(Dataset).filter(Dataset.id == config_w["dataset_id"]).first()
                if ds:
                    result = _read_ds(ds.id, page=0, page_size=99999)
                    df = pd.DataFrame(result.get("preview", []))
            elif config_w.get("sql") and config_w.get("connection_id"):
                from app.services.db_service import execute_query
                rows = execute_query(config_w["connection_id"], config_w["sql"], db)
                df = pd.DataFrame(rows)
            if df is not None and not df.empty:
                df = df.where(df.notna(), other=None)
                widget_data[wid] = df.to_dict("records")
            else:
                widget_data[wid] = []
        except Exception:
            widget_data[wid] = []

    try:
        pdf_bytes = generate_report_pdf(
            report_name = r.name,
            widgets     = widgets,
            widget_data = widget_data,
        )
    except Exception as e:
        try:
            from app.services.db_logger import log as _dblog
            _dblog(db, "error", "reports", "pdf_error",
                f"PDF-Generierung fehlgeschlagen: {str(e)[:300]}",
                details={"exception_type": type(e).__name__,
                         "exception_message": str(e),
                         "traceback": traceback.format_exc()})
        except Exception:
            pass
        raise HTTPException(500, f"PDF-Generierung fehlgeschlagen: {str(e)[:300]}")

    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in r.name)
    subject = body.subject or f"Report: {r.name}"
    mail_body = body.body or f'Im Anhang findest Du den Report "{r.name}".'

    try:
        send_email(
            to      = body.to,
            cc      = body.cc or None,
            subject = subject,
            body    = mail_body,
            db      = db,
            attachments = [{
                "filename": f"{safe_name}.pdf",
                "data":     pdf_bytes,
                "mime":     "application/pdf",
            }],
        )
    except Exception as e:
        try:
            from app.services.db_logger import log as _dblog
            _dblog(db, "error", "reports", "email_error",
                f"E-Mail-Versand fehlgeschlagen: {str(e)[:300]}",
                details={"exception_type": type(e).__name__,
                         "exception_message": str(e),
                         "traceback": traceback.format_exc()})
        except Exception:
            pass
        raise HTTPException(500, f"E-Mail-Versand fehlgeschlagen: {str(e)[:300]}")

    return {"ok": True, "to": body.to, "subject": subject, "pdf_size": len(pdf_bytes)}



