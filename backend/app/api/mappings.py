from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Any
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.mapping import Mapping
from app.models.dataset import Dataset
from app.api.projects import require_editor

router = APIRouter(prefix="/api/mappings", tags=["mappings"])


# ─── Pydantic Schemas ─────────────────────────────────────────────────────────

class MappingCreate(BaseModel):
    name: str
    canvas_nodes:    Optional[List[Any]] = []
    joins:           Optional[List[Any]] = []
    transform_nodes: Optional[List[Any]] = []
    constant_nodes:  Optional[List[Any]] = []
    sql_nodes:       Optional[List[Any]] = []
    agg_nodes:       Optional[List[Any]] = []
    rest_nodes:      Optional[List[Any]] = []
    lookup_nodes:    Optional[List[Any]] = []
    calc_nodes:      Optional[List[Any]] = []
    switch_nodes:    Optional[List[Any]] = []
    targets:         Optional[List[Any]] = []
    # Legacy-Felder (werden in targets migriert)
    fields:                  Optional[List[Any]] = []
    target_type:             Optional[str] = None
    target_connection_id:    Optional[int] = None
    target_table:            Optional[str] = None
    target_write_mode:       Optional[str] = "insert"
    target_options:          Optional[dict] = {}
    project_id:              Optional[int] = None


class PreviewRequest(BaseModel):
    canvas_nodes:    Optional[List[Any]] = []
    fields:          Optional[List[Any]] = []   # Verbindungen des aktiven Targets
    joins:           Optional[List[Any]] = []
    transform_nodes: Optional[List[Any]] = []
    constant_nodes:  Optional[List[Any]] = []
    sql_nodes:       Optional[List[Any]] = []
    agg_nodes:       Optional[List[Any]] = []
    rest_nodes:      Optional[List[Any]] = []
    lookup_nodes:    Optional[List[Any]] = []
    calc_nodes:      Optional[List[Any]] = []
    switch_nodes:    Optional[List[Any]] = []
    targets:         Optional[List[Any]] = []   # vollständige Targets (bevorzugt)
    preview_rows:    Optional[int] = 50


class ExecuteRequest(BaseModel):
    # Vollständige Mapping-Daten
    canvas_nodes:    Optional[List[Any]] = []
    joins:           Optional[List[Any]] = []
    transform_nodes: Optional[List[Any]] = []
    constant_nodes:  Optional[List[Any]] = []
    sql_nodes:       Optional[List[Any]] = []
    agg_nodes:       Optional[List[Any]] = []
    rest_nodes:      Optional[List[Any]] = []
    lookup_nodes:    Optional[List[Any]] = []
    calc_nodes:      Optional[List[Any]] = []
    switch_nodes:    Optional[List[Any]] = []
    targets:         Optional[List[Any]] = []
    # Legacy
    fields:                  Optional[List[Any]] = []
    target_type:             Optional[str] = "csv"
    target_connection_id:    Optional[int] = None
    target_table:            Optional[str] = None
    target_write_mode:       Optional[str] = "insert"
    target_options:          Optional[dict] = {}
    target_name:             Optional[str] = "export"
    # Kontext
    mapping_id:   Optional[int] = None
    mapping_name: Optional[str] = None
    project_id:   Optional[int] = None
    project_name: Optional[str] = None
    save_as_dataset: Optional[bool] = False


# ─── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _migrate_legacy_targets(m: Mapping) -> list:
    """Konvertiert alte Einzel-Felder in das targets-Format."""
    if m.targets:
        return m.targets
    if m.fields or m.target_type:
        return [{
            "id": "legacy",
            "name": m.target_table or m.target_type or "Ziel",
            "target_type": m.target_type or "csv",
            "target_connection_id": m.target_connection_id,
            "target_table": m.target_table or "",
            "target_write_mode": m.target_write_mode or "insert",
            "target_options": m.target_options or {},
            "fields": m.fields or [],
        }]
    return []


def _build_context_from_request(data) -> "MappingContext":
    """Erstellt MappingContext aus einem API-Request-Objekt."""
    from app.services.mapping_service import MappingContext

    # Targets bevorzugen; Fallback: Legacy-Felder
    targets = getattr(data, "targets", None) or []
    if not targets:
        fields = getattr(data, "fields", []) or []
        t_type = getattr(data, "target_type", "csv") or "csv"
        t_name = getattr(data, "target_name", None) or getattr(data, "target_table", None) or t_type
        if fields or t_type:
            targets = [{
                "id": "req",
                "name": t_name,
                "target_type": t_type,
                "target_connection_id": getattr(data, "target_connection_id", None),
                "target_table": getattr(data, "target_table", None) or "",
                "target_write_mode": getattr(data, "target_write_mode", "insert") or "insert",
                "target_options": getattr(data, "target_options", {}) or {},
                "fields": fields,
                "save_as_dataset": getattr(data, "save_as_dataset", False),
            }]

    return MappingContext(
        canvas_nodes    = getattr(data, "canvas_nodes",    None) or [],
        joins           = getattr(data, "joins",           None) or [],
        transform_nodes = getattr(data, "transform_nodes", None) or [],
        constant_nodes  = getattr(data, "constant_nodes",  None) or [],
        sql_nodes       = getattr(data, "sql_nodes",       None) or [],
        agg_nodes       = getattr(data, "agg_nodes",       None) or [],
        rest_nodes      = getattr(data, "rest_nodes",      None) or [],
        lookup_nodes    = getattr(data, "lookup_nodes",    None) or [],
        calc_nodes      = getattr(data, "calc_nodes",      None) or [],
        switch_nodes    = getattr(data, "switch_nodes",    None) or [],
        targets         = targets,
    )


def mapping_out(m: Mapping, db: Session) -> dict:
    nodes = []
    for node in (m.canvas_nodes or []):
        ds = db.query(Dataset).filter(Dataset.id == node.get("dataset_id")).first()
        nodes.append({
            **node,
            "dataset_name":       ds.name      if ds else "?",
            "dataset_columns":    ds.columns   if ds else [],
            "dataset_column_types": ds.column_types if ds else {},
            "dataset_file_type":  ds.file_type if ds else "csv",
            "dataset_row_count":  ds.row_count if ds else 0,
        })
    return {
        "id":             m.id,
        "name":           m.name,
        "canvas_nodes":   nodes,
        "joins":          m.joins           or [],
        "transform_nodes":m.transform_nodes or [],
        "constant_nodes": m.constant_nodes  or [],
        "sql_nodes":      m.sql_nodes       or [],
        "agg_nodes":      m.agg_nodes       or [],
        "rest_nodes":     getattr(m, "rest_nodes",   None) or [],
        "lookup_nodes":   getattr(m, "lookup_nodes", None) or [],
        "calc_nodes":     getattr(m, "calc_nodes",   None) or [],
        "switch_nodes":   getattr(m, "switch_nodes", None) or [],
        "targets":        _migrate_legacy_targets(m),
        "project_id":     m.project_id,
        "created_at":     m.created_at.isoformat() if m.created_at else None,
        "updated_at":     m.updated_at.isoformat() if m.updated_at else None,
    }


def mapping_list_out(m: Mapping) -> dict:
    targets = _migrate_legacy_targets(m)
    total_fields = sum(len(t.get("fields", [])) for t in targets)
    return {
        "id":           m.id,
        "name":         m.name,
        "field_count":  total_fields,
        "join_count":   len(m.joins or []),
        "target_count": len(targets),
        "target_type":  targets[0]["target_type"] if targets else None,
        "target_table": targets[0].get("target_table") if targets else None,
        "project_id":   m.project_id,
        "created_at":   m.created_at.isoformat() if m.created_at else None,
    }


# ─── CRUD Endpunkte ───────────────────────────────────────────────────────────

@router.get("/")
def list_mappings(
    project_id: Optional[int] = None,
    page: int = 0,
    page_size: int = 200,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.api.projects import get_accessible_project_ids, can_read_project
    if project_id is not None:
        if not can_read_project(project_id, user, db):
            raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    q = db.query(Mapping)
    if project_id is not None:
        q = q.filter(Mapping.project_id == project_id)
    else:
        accessible = get_accessible_project_ids(user, db)
        if accessible is not None:
            q = q.filter((Mapping.project_id.in_(accessible)) | (Mapping.project_id.is_(None)))
    if search:
        q = q.filter(Mapping.name.ilike(f"%{search}%"))
    total = q.count()
    items = q.order_by(Mapping.id.desc()).offset(page * page_size).limit(page_size).all()
    from fastapi.responses import JSONResponse
    return JSONResponse(
        content=[mapping_list_out(m) for m in items],
        headers={
            "X-Total-Count": str(total),
            "X-Page": str(page),
            "X-Pages": str((total + page_size - 1) // page_size),
        }
    )


@router.post("/")
def create_mapping(data: MappingCreate, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    require_editor(data.project_id, user, db)
    m = Mapping(
        name=data.name,
        canvas_nodes=data.canvas_nodes,   joins=data.joins,
        transform_nodes=data.transform_nodes, constant_nodes=data.constant_nodes,
        sql_nodes=data.sql_nodes,         agg_nodes=data.agg_nodes,
        rest_nodes=data.rest_nodes or [], lookup_nodes=data.lookup_nodes or [],
        calc_nodes=data.calc_nodes or [], switch_nodes=data.switch_nodes or [],
        targets=data.targets,             project_id=data.project_id,
    )
    db.add(m); db.commit(); db.refresh(m)
    return mapping_out(m, db)


@router.get("/{mapping_id}")
def get_mapping(mapping_id: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    from app.api.projects import can_read_project
    m = db.query(Mapping).filter(Mapping.id == mapping_id).first()
    if not m:
        raise HTTPException(404, "Mapping nicht gefunden")
    if not can_read_project(m.project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf dieses Mapping")
    return mapping_out(m, db)


@router.put("/{mapping_id}")
def update_mapping(mapping_id: int, data: MappingCreate, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    m = db.query(Mapping).filter(Mapping.id == mapping_id).first()
    if not m:
        raise HTTPException(404, "Mapping nicht gefunden")
    require_editor(m.project_id, user, db)
    m.name            = data.name
    m.canvas_nodes    = data.canvas_nodes
    m.joins           = data.joins
    m.transform_nodes = data.transform_nodes
    m.constant_nodes  = data.constant_nodes
    m.sql_nodes       = data.sql_nodes
    m.agg_nodes       = data.agg_nodes
    m.rest_nodes      = data.rest_nodes   or []
    m.lookup_nodes    = data.lookup_nodes or []
    m.calc_nodes      = data.calc_nodes   or []
    m.switch_nodes    = data.switch_nodes or []
    m.targets         = data.targets
    m.project_id      = data.project_id
    db.commit(); db.refresh(m)
    return mapping_out(m, db)


@router.delete("/{mapping_id}")
def delete_mapping(mapping_id: int, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    m = db.query(Mapping).filter(Mapping.id == mapping_id).first()
    if not m:
        raise HTTPException(404, "Mapping nicht gefunden")
    require_editor(m.project_id, user, db)
    db.delete(m); db.commit()
    return {"ok": True}


# ─── Preview ──────────────────────────────────────────────────────────────────

@router.post("/preview")
def preview_mapping(data: PreviewRequest, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    from app.services.mapping_service import MappingContext, run_mapping_object
    try:
        ctx = _build_context_from_request(data)
        # Wenn targets übergeben wurden, nutze diese direkt
        if data.targets:
            ctx.targets = data.targets
        elif data.fields:
            # Legacy: einzelne Felder-Liste
            ctx.targets = [{"id": "preview", "name": "Vorschau",
                            "target_type": "preview", "fields": data.fields}]

        result = run_mapping_object(ctx, preview_rows=data.preview_rows or 50)
        return result
    except Exception as e:
        import traceback, logging
        logging.error("Preview error: " + traceback.format_exc())
        try:
            from app.services.db_logger import log as _dblog
            _dblog(db, "error", "mappings", "preview_error",
                f"Preview-Fehler: {str(e)[:300]}",
                details={"exception_type": type(e).__name__,
                         "exception_message": str(e),
                         "traceback": traceback.format_exc()})
        except Exception:
            pass
        raise HTTPException(500, f"Vorschau-Fehler: {str(e)[:300]}")


# ─── Execute ──────────────────────────────────────────────────────────────────

@router.post("/execute")
def execute_mapping_endpoint(data: ExecuteRequest, db: Session = Depends(get_db),
                              user: User = Depends(get_current_user)):
    from app.services.mapping_service import MappingContext, run_mapping_object

    ctx = _build_context_from_request(data)

    # save_as_dataset Flag in Target eintragen falls gesetzt
    if data.save_as_dataset and ctx.targets:
        for t in ctx.targets:
            t["save_as_dataset"] = True

    try:
        result = run_mapping_object(
            ctx,
            preview_rows=999999,
            db=db,
            mapping_id=data.mapping_id,
            mapping_name=data.mapping_name,
            project_id=data.project_id,
            project_name=data.project_name,
            triggered_by="execute",
        )
    except Exception as e:
        try:
            from app.services.db_logger import log as _dblog
            _dblog(db, "error", "mappings", "mapping_run_error",
                f"Mapping-Fehler: {str(e)[:300]}",
                details={"exception_type": type(e).__name__,
                         "exception_message": str(e),
                         "traceback": traceback.format_exc()})
        except Exception:
            pass
        raise HTTPException(500, f"Mapping-Fehler: {str(e)[:300]}")

    if result.get("errors") and not result.get("rows") and result.get("targets_executed", 0) == 0:
        raise HTTPException(400, f"Mapping-Fehler: {'; '.join(result['errors'][:3])}")

    # Wenn save_as_dataset: Dataset-ID zurückgeben
    if data.save_as_dataset:
        # Dataset-ID aus DB holen
        if data.mapping_id:
            ds = db.query(Dataset).filter(Dataset.source_mapping_id == data.mapping_id).first()
            if ds:
                return {"saved_as_dataset": True, "dataset_id": ds.id,
                        "dataset_name": ds.name, "rows": result.get("total_rows_written", 0)}

    # Für direkten File-Download: ersten target-Typ aus Ergebnis prüfen
    targets_results = result.get("targets_results") or []
    if targets_results and targets_results[0].get("status") == "ok":
        return {
            "ok": True,
            "rows": result.get("total_rows_written", 0),
            "targets": targets_results,
            "errors": result.get("errors") or [],
        }

    return result


# ─── Execute single target (direkter File-Download) ──────────────────────────



@router.get("/{mapping_id}/schema")
def get_mapping_schema(
    mapping_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Schema-Preview: Welche Spalten + Typen kommen aus diesem Mapping raus?
    Führt das Mapping mit 50 Preview-Zeilen aus und gibt nur column_types zurück.
    Unabhängig vom konfigurierten Ziel (DB, CSV etc.).
    """
    from app.services.mapping_service import MappingContext, run_mapping_object

    from app.api.projects import can_read_project
    m = db.query(Mapping).filter(Mapping.id == mapping_id).first()
    if not m:
        raise HTTPException(404, "Mapping nicht gefunden")
    if not can_read_project(m.project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf dieses Mapping")

    ctx = MappingContext.from_orm(m)
    if not ctx.targets:
        return {"mapping_id": mapping_id, "columns": [], "column_types": {},
                "errors": ["Keine Ziele konfiguriert"]}

    try:
        result = run_mapping_object(ctx, preview_rows=50)
        return {
            "mapping_id":   mapping_id,
            "mapping_name": m.name,
            "columns":      result.get("columns", []),
            "column_types": result.get("column_types", {}),
            "total":        result.get("total", 0),
            "errors":       result.get("errors", []),
        }
    except Exception as e:
        try:
            from app.services.db_logger import log as _dblog
            _dblog(db, "error", "mappings", "schema_error",
                f"Schema-Berechnung fehlgeschlagen: {str(e)[:300]}",
                details={"exception_type": type(e).__name__,
                         "exception_message": str(e),
                         "traceback": __import__('traceback').format_exc()})
        except Exception:
            pass
        raise HTTPException(500, f"Schema-Berechnung fehlgeschlagen: {str(e)[:300]}")

@router.post("/execute-download")
def execute_download(data: ExecuteRequest, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """
    Führt ein einzelnes Target aus und gibt die Datei direkt als Download zurück.
    Wird vom Frontend für den direkten CSV/XLSX/JSON/XML-Download genutzt.
    """
    from fastapi.responses import Response
    from app.services.mapping_service import MappingContext, run_mapping_object, execute_mapping, _apply_target_types
    from app.services.export_service import export_csv, export_xlsx, export_json, export_xml, export_to_db
    import pandas as pd

    ctx = _build_context_from_request(data)
    if not ctx.targets:
        raise HTTPException(400, "Kein Ziel definiert")

    target = ctx.targets[0]
    t_fields = target.get("fields") or []
    t_type   = target.get("target_type", "csv")
    opts     = target.get("target_options") or {}

    try:
        result = execute_mapping(**ctx.to_execute_kwargs(t_fields, 999999))
    except Exception as e:
        try:
            from app.services.db_logger import log as _dblog
            _dblog(db, "error", "mappings", "mapping_run_error",
                f"Mapping-Fehler: {str(e)[:300]}",
                details={"exception_type": type(e).__name__,
                         "exception_message": str(e),
                         "traceback": traceback.format_exc()})
        except Exception:
            pass
        raise HTTPException(500, f"Mapping-Fehler: {str(e)[:300]}")

    if not result["rows"] and result.get("errors"):
        raise HTTPException(400, f"Mapping-Fehler: {'; '.join(result['errors'][:3])}")

    df = pd.DataFrame(result["rows"], columns=result["columns"])
    df, _ = _apply_target_types(df, t_fields)

    # Pflichtfeld-Validierung
    required_fields = opts.get("required_fields") or []
    if required_fields:
        missing_vals = []
        for f in required_fields:
            if f in df.columns:
                null_count = int(df[f].isna().sum()) + int((df[f].astype(str).str.strip() == "").sum())
                if null_count > 0:
                    missing_vals.append(f"{f} ({null_count} leere Werte)")
        if missing_vals:
            raise HTTPException(400, f"Pflichtfeld-Fehler: {', '.join(missing_vals)}")

    # Duplikat-Entfernung
    if opts.get("deduplicate_enabled"):
        subset = [f for f in (opts.get("deduplicate_fields") or []) if f in df.columns] or None
        df = df.drop_duplicates(subset=subset, keep="first")

    if t_type == "csv":
        content = export_csv(df, delimiter=opts.get("delimiter", ";"),
                             encoding=opts.get("encoding", "utf-8-sig"))
        return Response(content=content, media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=export.csv"})
    elif t_type == "xlsx":
        content = export_xlsx(df)
        return Response(content=content,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": "attachment; filename=export.xlsx"})
    elif t_type == "json":
        content = export_json(df, orient=opts.get("orient", "records"), indent=opts.get("indent", 2))
        return Response(content=content, media_type="application/json",
                        headers={"Content-Disposition": "attachment; filename=export.json"})
    elif t_type == "xml":
        content = export_xml(df, opts.get("xml_template", {}))
        return Response(content=content, media_type="application/xml",
                        headers={"Content-Disposition": "attachment; filename=export.xml"})
    elif t_type == "db":
        conn_id = target.get("target_connection_id")
        table   = target.get("target_table")
        if not conn_id or not table:
            raise HTTPException(400, "DB-Export: connection_id und target_table erforderlich")
        from app.models.dataset import DbConnection
        conn_obj = db.query(DbConnection).filter(DbConnection.id == conn_id).first()
        if not conn_obj:
            raise HTTPException(404, "Verbindung nicht gefunden")
        return export_to_db(df, conn_obj, table,
                            target.get("target_write_mode", "insert"),
                            key_columns=opts.get("key_columns", []))
    else:
        raise HTTPException(400, f"Unbekannter target_type: {t_type}")



