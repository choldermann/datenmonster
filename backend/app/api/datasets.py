import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Any
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.dataset import Dataset
from app.services.file_service import (
    parse_file, dataframe_to_storage, read_dataset,
    analyze_xml_structure, get_node_fields, parse_xml_with_config,
    infer_column_types,
)
from app.core.config import UPLOAD_DIR
from app.api.projects import require_editor
import pandas as pd



# ─── Temporäre Datei-Verwaltung (Access-Upload) ───────────────────────────────
import threading as _threading
import os as _os

_tmp_file_registry: dict = {}   # { tmp_path: expires_at (float) }
_tmp_registry_lock = _threading.Lock()
_TMP_TTL_SECONDS = 600          # 10 Minuten


def _register_tmp_file(path: str):
    """Registriert eine tmp-Datei mit Ablaufzeit."""
    import time
    with _tmp_registry_lock:
        _tmp_file_registry[path] = time.time() + _TMP_TTL_SECONDS


def _cleanup_tmp_files():
    """Löscht abgelaufene tmp-Dateien. Wird nach jedem Upload aufgerufen."""
    import time
    now = time.time()
    with _tmp_registry_lock:
        expired = [p for p, exp in _tmp_file_registry.items() if now > exp]
        for path in expired:
            try:
                if _os.path.exists(path):
                    _os.unlink(path)
            except Exception:
                pass
            del _tmp_file_registry[path]


def _unregister_tmp_file(path: str):
    """Entfernt eine tmp-Datei aus der Registry (nach erfolgreichem Import)."""
    with _tmp_registry_lock:
        _tmp_file_registry.pop(path, None)


router = APIRouter(prefix="/api/datasets", tags=["datasets"])

# ─── Upload-Limits ────────────────────────────────────────────────────────────
MAX_UPLOAD_BYTES = 100 * 1024 * 1024   # 100 MB
MAX_UPLOAD_MB    = MAX_UPLOAD_BYTES // (1024 * 1024)


async def _read_limited(file) -> bytes:
    """Liest UploadFile mit Größenlimit. Wirft HTTPException 413 wenn überschritten."""
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413,
            f"Datei zu groß: {len(content) // (1024*1024)} MB "
            f"(Maximum: {MAX_UPLOAD_MB} MB)"
        )
    return content



def dataset_out(ds: Dataset) -> dict:
    return {
        "id": ds.id,
        "name": ds.name,
        "original_filename": ds.original_filename or "",
        "file_type": ds.file_type,
        "row_count": ds.row_count,
        "columns": ds.columns or [],
        "xml_configured": ds.xml_configured,
        "xml_target_node": ds.xml_target_node,
        "xml_ref_fields": ds.xml_ref_fields or [],
        "source_connection_id": ds.source_connection_id,
        "source_sql": ds.source_sql,
        "query_config": ds.query_config,
        "source_mapping_id": ds.source_mapping_id,
        "project_id": ds.project_id,
        "column_types": ds.column_types or {},
        "cron_expr": ds.cron_expr or "",
        "auto_refresh": ds.auto_refresh or 0,
        "last_refresh_at": ds.last_refresh_at.isoformat() if ds.last_refresh_at else None,
        "last_refresh_status": ds.last_refresh_status or "",
        "last_refresh_msg": ds.last_refresh_msg or "",
        "created_at": ds.created_at.isoformat() if ds.created_at else None,
        "updated_at": ds.updated_at.isoformat() if ds.updated_at else (ds.created_at.isoformat() if ds.created_at else None),
    }


# ─── Manuell anlegen ──────────────────────────────────────────────────────────

class DatasetColumnDef(BaseModel):
    name: str
    type: str = "string"  # string | integer | decimal | date | boolean
    is_primary: bool = False
    autoincrement: bool = False

class DatasetCreateManual(BaseModel):
    name: str
    columns: List[DatasetColumnDef] = []
    project_id: Optional[int] = None

@router.post("/create")
def create_dataset_manual(
    body: DatasetCreateManual,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Legt ein leeres Dataset mit definierten Spalten an."""
    import pandas as pd
    import traceback

    require_editor(body.project_id, user, db)

    # Spalten-Typen Mapping
    type_map = {
        "string":  "string",
        "integer": "Int64",
        "decimal": "float64",
        "date":    "string",
        "boolean": "boolean",
    }

    # Leeren DataFrame mit definierten Spalten erstellen
    col_names = [c.name for c in body.columns] if body.columns else []
    df = pd.DataFrame(columns=col_names)

    # Spaltentypen setzen
    col_types = {}
    for c in body.columns:
        col_types[c.name] = {
            "type": c.type,
            "raw": c.type,
            "is_primary": c.is_primary,
            "autoincrement": c.autoincrement,
        }
        try:
            df[c.name] = df[c.name].astype(type_map.get(c.type, "string"))
        except Exception:
            pass

    # Dataset anlegen
    ds = Dataset(
        name=body.name,
        original_filename=None,
        file_type="static",
        xml_configured=1,
        row_count=0,
        columns=col_names,
        column_types=col_types,
        project_id=body.project_id,
    )
    db.add(ds); db.commit(); db.refresh(ds)

    # Leere Parquet-Datei speichern
    try:
        storage_path = dataframe_to_storage(df, ds.id)
        ds.file_path = storage_path
        db.commit()
    except Exception as e:
        db.delete(ds); db.commit()
        raise HTTPException(400, f"Fehler beim Anlegen: {str(e)}")

    # Logging
    try:
        from app.services.db_logger import log as _dblog
        _dblog(db, "success", "datasets", "dataset_created_manual",
            f"Dataset '{body.name}' manuell angelegt ({len(col_names)} Spalten)",
            project_id=body.project_id,
            details={"columns": [{"name": c.name, "type": c.type} for c in body.columns]})
    except Exception:
        pass

    return dataset_out(ds)


# ─── Upload ───────────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    name: str = Form(...),
    project_id: Optional[int] = Form(None),
    csv_delimiter: Optional[str] = Form(None),
    skip_rows: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    file_type_map = {"csv": "csv", "xlsx": "xlsx", "xls": "xlsx", "xml": "xml", "ods": "ods"}
    file_type = file_type_map.get(ext)
    if not file_type:
        raise HTTPException(400, f"Nicht unterstütztes Format: {ext}")

    require_editor(project_id, user, db)
    content = await file.read()

    if file_type == "xml":
        ds = Dataset(name=name, original_filename=file.filename, file_type="xml",
                     xml_configured=0, row_count=0, columns=[], project_id=project_id)
        db.add(ds); db.commit(); db.refresh(ds)
        raw_path = os.path.join(UPLOAD_DIR, f"dataset_{ds.id}_raw.xml")
        with open(raw_path, "wb") as f:
            f.write(content)
        ds.file_path = raw_path; db.commit()
        return dataset_out(ds)

    ds = Dataset(name=name, original_filename=file.filename, file_type=file_type,
                 xml_configured=1, row_count=0, columns=[], project_id=project_id)
    db.add(ds); db.commit(); db.refresh(ds)

    tmp_path = os.path.join(UPLOAD_DIR, f"tmp_{ds.id}_{_safe_filename(file.filename)}")
    with open(tmp_path, "wb") as f:
        f.write(content)
    try:
        df = parse_file(tmp_path, file_type, csv_delimiter=csv_delimiter, skip_rows=skip_rows or 0)
        storage_path = dataframe_to_storage(df, ds.id)
        ds.file_path = storage_path
        ds.row_count = len(df)
        ds.columns = df.columns.tolist()
        ds.column_types = _merge_column_types(ds.column_types or {}, infer_column_types(df))
        db.commit()
    except Exception as e:
        db.delete(ds); db.commit()
        try:
            from app.services.db_logger import log as _dblog
            _dblog(db, "error", "datasets", "upload_error",
                f"Upload fehlgeschlagen: {str(e)[:300]}",
                project_id=project_id,
                details={"filename": file.filename, "file_type": file_type,
                         "skip_rows": skip_rows,
                         "exception_type": type(e).__name__,
                         "exception_message": str(e),
                         "traceback": __import__('traceback').format_exc()})
        except Exception:
            pass
        raise HTTPException(400, f"Fehler beim Verarbeiten: {str(e)}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    try:
        from app.services.db_logger import log as _dblog
        _dblog(db, "success", "datasets", "upload_success",
            f"Dataset hochgeladen: {ds.row_count} Zeilen" + (f" (übersprungen: {skip_rows})" if skip_rows else ""),
            project_id=project_id, rows_processed=ds.row_count,
            details={"filename": file.filename, "file_type": file_type, "skip_rows": skip_rows or 0})
    except Exception:
        pass
    return dataset_out(ds)


# ─── XML Struktur analysieren ─────────────────────────────────────────────────

@router.get("/{dataset_id}/xml-structure")
def xml_structure(
    dataset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.api.projects import can_read_project
    ds = _get_ds(dataset_id, db)
    if not can_read_project(ds.project_id, user, db):
        raise HTTPException(403, "Kein Zugriff")
    if ds.file_type != "xml" or not ds.file_path:
        raise HTTPException(400, "Kein XML-Dataset")
    try:
        with open(ds.file_path, "rb") as f:
            content = f.read()
        return analyze_xml_structure(content)
    except Exception as e:
        raise HTTPException(422, str(e))


# ─── Referenzfelder eines Knotens laden ──────────────────────────────────────

class NodeFieldsRequest(BaseModel):
    node_path: str


@router.post("/{dataset_id}/xml-node-fields")
def xml_node_fields(
    dataset_id: int,
    body: NodeFieldsRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ds = _get_ds(dataset_id, db)
    if ds.file_type != "xml" or not ds.file_path:
        raise HTTPException(400, "Kein XML-Dataset")
    with open(ds.file_path, "rb") as f:
        content = f.read()
    fields = get_node_fields(content, body.node_path)
    return {"fields": fields}


# ─── XML konfigurieren + importieren ─────────────────────────────────────────

class XmlConfigRequest(BaseModel):
    target_node: str
    ref_fields: List[str] = []


@router.post("/{dataset_id}/xml-configure")
def xml_configure(
    dataset_id: int,
    config: XmlConfigRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ds = _get_ds(dataset_id, db)
    if ds.file_type != "xml" or not ds.file_path:
        raise HTTPException(400, "Kein XML-Dataset")
    try:
        with open(ds.file_path, "rb") as f:
            content = f.read()
        columns, rows = parse_xml_with_config(content, config.target_node, config.ref_fields)
        df = pd.DataFrame(rows, columns=columns)
        storage_path = dataframe_to_storage(df, ds.id)
        ds.file_path = storage_path
        ds.xml_configured = 1
        ds.xml_target_node = config.target_node
        ds.xml_ref_fields = config.ref_fields
        ds.row_count = len(df)
        ds.columns = columns
        ds.column_types = _merge_column_types(ds.column_types or {}, infer_column_types(df))
        db.commit()
    except Exception as e:
        raise HTTPException(422, f"Fehler beim Parsen: {str(e)}")
    return dataset_out(ds)


# ─── Dataset-Daten lesen (Explorer) ──────────────────────────────────────────

@router.get("/{dataset_id}/data")
def get_dataset_data(
    dataset_id: int,
    page: int = 0,
    page_size: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ds = _get_ds(dataset_id, db)
    try:
        return read_dataset(dataset_id, page, page_size)
    except FileNotFoundError:
        raise HTTPException(404, "Datei nicht gefunden")


# ─── Liste ────────────────────────────────────────────────────────────────────

@router.get("/")
def list_datasets(
    project_id: Optional[int] = None,
    exclude_mapping_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Dataset)
    if project_id is not None:
        q = q.filter(Dataset.project_id == project_id)
    if exclude_mapping_id is not None:
        q = q.filter(
            (Dataset.source_mapping_id == None) |
            (Dataset.source_mapping_id != exclude_mapping_id)
        )
    return [dataset_out(ds) for ds in q.order_by(Dataset.id.desc()).all()]


# ─── Dataset aus Mapping-Output erstellen ────────────────────────────────────

class FromMappingRequest(BaseModel):
    mapping_id: Optional[int] = None
    target_name: str
    project_id: Optional[int] = None
    canvas_nodes: List[Any] = []
    fields: List[Any] = []
    joins: List[Any] = []
    transform_nodes: List[Any] = []
    constant_nodes: List[Any] = []


@router.post("/from-mapping")
def create_dataset_from_mapping(
    data: FromMappingRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.services.mapping_service import MappingContext, run_mapping_object
    from app.services.file_service import dataframe_to_storage

    require_editor(data.project_id, user, db)

    try:
        ctx = MappingContext(
            canvas_nodes    = data.canvas_nodes,
            joins           = data.joins,
            transform_nodes = data.transform_nodes,
            constant_nodes  = data.constant_nodes,
            targets=[{"id": "out", "name": data.target_name,
                      "target_type": "dataset", "fields": data.fields}],
        )
        result = run_mapping_object(ctx, preview_rows=999999)
    except Exception as e:
        raise HTTPException(500, f"Mapping-Fehler: {str(e)[:300]}")

    if not result["rows"] and result.get("errors"):
        raise HTTPException(400, f"Mapping-Fehler: {'; '.join(result['errors'][:3])}")

    import pandas as pd
    df = pd.DataFrame(result["rows"], columns=result["columns"])
    cols = list(df.columns)

    ds = Dataset(
        name=data.target_name,
        original_filename=None,
        file_type="csv",
        file_path=None,
        row_count=len(df),
        columns=cols,
        column_types=infer_column_types(df),
        xml_configured=1,
        source_mapping_id=data.mapping_id,
        project_id=data.project_id,
    )
    db.add(ds); db.commit(); db.refresh(ds)

    path = dataframe_to_storage(df, ds.id)
    ds.file_path = path
    db.commit(); db.refresh(ds)

    return dataset_out(ds)


# ─── Re-Query (DB-Dataset neu laden) ─────────────────────────────────────────

@router.post("/{dataset_id}/requery")
def requery_dataset(dataset_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Führt das gespeicherte SQL eines DB-Datasets erneut aus und aktualisiert die Daten."""
    from app.models.dataset import DbConnection
    from app.services.db_service import query_full

    ds = _get_ds(dataset_id, db)
    require_editor(ds.project_id, user, db)

    if not ds.source_connection_id or not ds.source_sql:
        raise HTTPException(400, "Dataset hat keine gespeicherte SQL-Abfrage")

    conn = db.query(DbConnection).filter(DbConnection.id == ds.source_connection_id).first()
    if not conn:
        raise HTTPException(404, f"Verbindung #{ds.source_connection_id} nicht gefunden")

    try:
        df = query_full(conn, ds.source_sql)
        from datetime import datetime, timezone
        ds.row_count = len(df)
        ds.columns = df.columns.tolist()
        ds.column_types = infer_column_types(df)
        ds.updated_at = datetime.now(timezone.utc)
        db.commit()
        dataframe_to_storage(df, ds.id)
        db.refresh(ds)
        return dataset_out(ds)
    except Exception as e:
        raise HTTPException(400, f"Re-Query fehlgeschlagen: {str(e)[:400]}")


# ─── Umbenennen ───────────────────────────────────────────────────────────────

class DatasetUpdate(BaseModel):
    name: Optional[str] = None
    cron_expr: Optional[str] = None
    auto_refresh: Optional[int] = None


@router.get("/{dataset_id}")
def get_dataset(dataset_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Gibt ein einzelnes Dataset zurück – inkl. aktueller column_types."""
    ds = _get_ds(dataset_id, db)
    return dataset_out(ds)


@router.patch("/{dataset_id}")
def update_dataset(dataset_id: int, data: DatasetUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ds = _get_ds(dataset_id, db)
    require_editor(ds.project_id, user, db)
    if data.name:
        ds.name = data.name
    if data.cron_expr is not None:
        ds.cron_expr = data.cron_expr or None
    if data.auto_refresh is not None:
        ds.auto_refresh = data.auto_refresh
    db.commit()

    # Scheduler-Job registrieren oder entfernen
    try:
        from app.services.scheduler_service import register_dataset_job, unregister_dataset_job
        if ds.auto_refresh and ds.cron_expr:
            register_dataset_job(ds.id, ds.cron_expr)
        else:
            unregister_dataset_job(ds.id)
    except Exception as e:
        import logging; logging.getLogger(__name__).warning(f"Scheduler-Update fehlgeschlagen: {e}")

    return dataset_out(ds)



@router.patch("/{dataset_id}/column_types")
def update_column_types(
    dataset_id: int,
    data: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Überschreibt einzelne Feldtypen in column_types.
    Body: { "col_name": "integer" | "decimal" | "string" | "date" | "datetime" | "bool" }
    Bereits vorhandene Typen bleiben erhalten, nur die übermittelten werden geändert.
    """
    ds = _get_ds(dataset_id, db)
    require_editor(ds.project_id, user, db)

    VALID_TYPES = {"string", "integer", "decimal", "date", "datetime", "bool", "boolean"}
    current = dict(ds.column_types or {})

    for col, new_type in data.items():
        if new_type not in VALID_TYPES:
            continue
        if col not in current:
            current[col] = {"type": new_type, "raw": "manual"}
        else:
            current[col] = {**current[col], "type": new_type, "raw": current[col].get("raw", "manual")}

    # Komplett neues Dict-Objekt zuweisen damit SQLAlchemy die Mutation
    # am JSON-Column sicher erkennt (flag_modified als zusätzliche Absicherung)
    ds.column_types = dict(current)
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(ds, "column_types")
    db.commit()
    db.refresh(ds)
    return {"ok": True, "column_types": ds.column_types}


@router.put("/{dataset_id}/column_types")
def put_column_types(
    dataset_id: int,
    data: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Vollständiges Ersetzen von column_types – inkl. is_primary und autoincrement.
    Body: { "col_name": { "type": "integer", "raw": "...", "is_primary": true, "autoincrement": true } }
    Wird vom EditDatasetModal und ManualDatasetModal verwendet.
    """
    ds = _get_ds(dataset_id, db)
    require_editor(ds.project_id, user, db)

    VALID_TYPES = {"string", "integer", "decimal", "date", "datetime", "bool", "boolean"}
    current = dict(ds.column_types or {})

    for col, info in data.items():
        if not isinstance(info, dict):
            continue
        col_type = info.get("type", "string")
        if col_type not in VALID_TYPES:
            col_type = "string"
        current[col] = {
            "type": col_type,
            "raw": info.get("raw", current.get(col, {}).get("raw", "manual")),
            "is_primary": bool(info.get("is_primary", False)),
            "autoincrement": bool(info.get("autoincrement", False)),
        }

    ds.column_types = dict(current)
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(ds, "column_types")
    db.commit()
    db.refresh(ds)
    return {"ok": True, "column_types": ds.column_types}


@router.delete("/{dataset_id}")
def delete_dataset(
    dataset_id: int,
    force: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ds = _get_ds(dataset_id, db)
    require_editor(ds.project_id, user, db)

    # Prüfen ob Dataset in Mappings verwendet wird
    from app.models.mapping import Mapping
    import json as _json
    usages = []
    for m in db.query(Mapping).filter(Mapping.project_id == ds.project_id).all():
        nodes = m.canvas_nodes or []
        if isinstance(nodes, str):
            try: nodes = _json.loads(nodes)
            except Exception: nodes = []
        if any(n.get("dataset_id") == dataset_id for n in nodes):
            usages.append({"id": m.id, "name": m.name})

    if usages and not force:
        raise HTTPException(
            409,
            f"Dataset wird in {len(usages)} Mapping(s) verwendet: "
            f"{', '.join(u['name'] for u in usages[:3])}. "
            f"Mit force=true trotzdem löschen."
        )

    # Dateien löschen (alle möglichen Formate)
    for suffix in ["_raw.xml", ".parquet", ".json"]:
        path = os.path.join(UPLOAD_DIR, f"dataset_{dataset_id}{suffix}")
        if os.path.exists(path):
            try: os.remove(path)
            except Exception: pass

    db.delete(ds)
    db.commit()
    return {"ok": True, "used_in_mappings": len(usages)}


# ─── Hilfsfunktion ───────────────────────────────────────────────────────────


def _merge_column_types(old_types: dict, new_types: dict) -> dict:
    """
    Merged neu inferierte column_types mit manuell gesetzten.
    Manuell gesetzte Typen (raw == "manual") bleiben erhalten,
    auto-inferierte werden überschrieben.
    """
    if not old_types:
        return new_types
    merged = dict(new_types)
    for col, info in old_types.items():
        if col in merged and info.get("raw") == "manual":
            # Manuell gesetzter Typ bleibt erhalten
            merged[col] = info
    return merged




def _safe_filename(filename: str) -> str:
    """Entfernt Pfadseparatoren und gefährliche Zeichen aus Dateinamen."""
    import re as _re
    # Nur Basename - keine Verzeichnisse
    basename = filename.replace("\\", "/").split("/")[-1]
    # Nur sichere Zeichen erlauben
    safe = _re.sub(r"[^a-zA-Z0-9._\-]", "_", basename)
    # Leerer Name oder nur Punkte → Fallback
    if not safe or safe.strip(".") == "":
        safe = "upload"
    return safe[:200]  # Max-Länge


def _sanitize_server_path(path: str) -> str:
    """
    Prüft ob ein Server-Pfad sicher ist.
    Verhindert Path Traversal und Zugriff auf Systemdateien.
    Erlaubt nur absolute Pfade mit .mdb/.accdb Endung.
    """
    import os as _os
    path = path.strip()
    # Muss absoluter Pfad sein
    if not _os.path.isabs(path):
        raise HTTPException(400, "Nur absolute Pfade erlaubt (z.B. /data/meine.accdb)")
    # Keine Path Traversal Sequenzen
    if ".." in path:
        raise HTTPException(400, "Ungültiger Pfad: '..' nicht erlaubt")
    # Nur .mdb und .accdb Dateien
    ext = _os.path.splitext(path)[1].lower()
    if ext not in (".mdb", ".accdb"):
        raise HTTPException(400, f"Nur .mdb und .accdb Dateien erlaubt, nicht '{ext}'")
    # Datei muss existieren
    if not _os.path.exists(path):
        raise HTTPException(404, f"Datei nicht gefunden: {path}")
    if not _os.path.isfile(path):
        raise HTTPException(400, "Pfad ist kein reguläres File")
    return path


def _get_ds(dataset_id: int, db: Session) -> Dataset:
    ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not ds:
        raise HTTPException(404, "Dataset nicht gefunden")
    return ds


# ─── Access Import ────────────────────────────────────────────────────────────

@router.get("/access/check-mdbtools")
def check_mdbtools(user: User = Depends(get_current_user)):
    """Prüft ob mdbtools auf dem Server verfügbar ist."""
    from app.services.access_service import check_mdbtools as _check
    return {"available": _check()}


@router.post("/access/tables-from-path")
def get_tables_from_path(
    payload: dict,
    user: User = Depends(get_current_user),
):
    """Liest Tabellenliste aus einer Access-Datei auf dem Server (per Pfad)."""
    from app.services.access_service import list_tables, check_mdbtools
    if not check_mdbtools():
        raise HTTPException(500, "mdbtools ist nicht installiert. Bitte 'apt install mdbtools' im Container ausführen.")
    path = payload.get("path", "").strip()
    if not path:
        raise HTTPException(400, "Kein Dateipfad angegeben")
    path = _sanitize_server_path(path)
    try:
        tables = list_tables(path)
        return {"tables": tables, "path": path}
    except FileNotFoundError:
        raise HTTPException(404, f"Datei nicht gefunden: {path}")
    except Exception as e:
        raise HTTPException(400, str(e)[:300])


# Access-Dateien können sehr groß sein (mehrere GB) – eigenes Limit
MAX_ACCESS_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024   # 2 GB
MAX_ACCESS_UPLOAD_MB    = MAX_ACCESS_UPLOAD_BYTES // (1024 * 1024)


async def _read_limited_access(file) -> bytes:
    """Liest Access-Upload mit großzügigem 2 GB Limit."""
    content = await file.read()
    if len(content) > MAX_ACCESS_UPLOAD_BYTES:
        raise HTTPException(
            413,
            f"Datei zu groß: {len(content) // (1024*1024)} MB "
            f"(Maximum: {MAX_ACCESS_UPLOAD_MB} MB). "
            f"Bitte nutze stattdessen den Serverpfad-Modus."
        )
    return content


@router.post("/access/tables-from-upload")
async def get_tables_from_upload(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """Liest Tabellenliste aus einem hochgeladenen Access-File."""
    from app.services.access_service import list_tables, check_mdbtools
    import tempfile
    if not check_mdbtools():
        raise HTTPException(500, "mdbtools ist nicht installiert.")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ("mdb", "accdb"):
        raise HTTPException(400, f"Ungültiges Format: .{ext} (erwartet .mdb oder .accdb)")

    # Streaming-Upload: direkt auf Disk schreiben statt alles in RAM laden
    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
        tmp_path = tmp.name
        total = 0
        chunk_size = 8 * 1024 * 1024  # 8 MB Chunks
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_ACCESS_UPLOAD_BYTES:
                import os; os.unlink(tmp_path)
                raise HTTPException(
                    413,
                    f"Datei zu groß – Maximum {MAX_ACCESS_UPLOAD_MB} MB. "
                    f"Bitte nutze den Serverpfad-Modus für sehr große Dateien."
                )
            tmp.write(chunk)

    try:
        tables = list_tables(tmp_path)
        _register_tmp_file(tmp_path)
        _cleanup_tmp_files()
        return {"tables": tables, "tmp_path": tmp_path, "filename": file.filename}
    except Exception as e:
        import os
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise HTTPException(400, str(e)[:500])


@router.post("/access/preview")
async def preview_access_table(
    payload: dict,
    user: User = Depends(get_current_user),
):
    """Liest Vorschau (5 Zeilen) einer Access-Tabelle."""
    from app.services.access_service import get_table_preview
    path = payload.get("path", "").strip()
    table = payload.get("table", "").strip()
    if not path or not table:
        raise HTTPException(400, "path und table sind erforderlich")
    path = _sanitize_server_path(path)
    try:
        preview = get_table_preview(path, table, limit=5)
        return preview
    except Exception as e:
        raise HTTPException(400, str(e)[:300])


@router.post("/access/import")
async def import_access_table(
    file: Optional[UploadFile] = File(None),
    name: str = Form(...),
    table: str = Form(...),
    server_path: Optional[str] = Form(None),
    tmp_path: Optional[str] = Form(None),
    project_id: Optional[int] = Form(None),
    csv_delimiter: Optional[str] = Form(None),
    skip_rows: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Importiert eine Access-Tabelle als Dataset.
    Entweder via Datei-Upload (file), Serverpfad (server_path) oder
    bereits hochgeladene Temp-Datei (tmp_path aus tables-from-upload).
    """
    from app.services.access_service import read_table, check_mdbtools
    import tempfile, os as _os

    if not check_mdbtools():
        raise HTTPException(500, "mdbtools ist nicht installiert.")

    require_editor(project_id, user, db)

    mdb_path = None
    cleanup_path = None

    try:
        if server_path:
            mdb_path = _sanitize_server_path(server_path)
        elif tmp_path and _os.path.exists(tmp_path):
            mdb_path = tmp_path
            _unregister_tmp_file(tmp_path)  # nicht mehr ablaufend löschen
        elif file:
            ext = file.filename.rsplit(".", 1)[-1].lower()
            # Streaming-Write: direkt auf Disk, kein RAM-Limit
            with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
                chunk_size = 8 * 1024 * 1024  # 8 MB Chunks
                total = 0
                while True:
                    chunk = await file.read(chunk_size)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_ACCESS_UPLOAD_BYTES:
                        tmp_name = tmp.name
                        import os as _rm; _rm.unlink(tmp_name)
                        raise HTTPException(413, f"Datei zu groß – nutze Serverpfad-Modus")
                    tmp.write(chunk)
                mdb_path = tmp.name
                cleanup_path = mdb_path
        else:
            raise HTTPException(400, "Keine Datei angegeben (weder Upload noch Serverpfad)")

        # DataFrame einlesen (kann bei großen Dateien etwas dauern)
        df = read_table(mdb_path, table)

        if df.empty:
            raise HTTPException(400, f"Tabelle '{table}' ist leer oder konnte nicht gelesen werden")

        # Als Dataset speichern
        from app.services.file_service import dataframe_to_storage, infer_column_types
        col_types = infer_column_types(df)

        ds = Dataset(
            name=name,
            original_filename=f"{table}.accdb",
            file_type="csv",
            xml_configured=1,
            row_count=len(df),
            columns=list(df.columns),
            column_types=col_types,
            project_id=project_id,
        )
        db.add(ds); db.commit(); db.refresh(ds)
        dataframe_to_storage(df, ds.id)
        return dataset_out(ds)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Import fehlgeschlagen: {str(e)[:400]}")
    finally:
        if cleanup_path and _os.path.exists(cleanup_path):
            _os.unlink(cleanup_path)



# ── Editierbare Dataset-Zeilen ────────────────────────────────────────────────

class RowsBody(BaseModel):
    rows: List[Any]


@router.get("/{dataset_id}/rows")
def get_rows(dataset_id: int, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    """Liest alle Zeilen eines Datasets."""
    ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not ds:
        raise HTTPException(404, "Dataset nicht gefunden")
    try:
        from app.services.file_service import read_dataset
        result = read_dataset(dataset_id, page=0, page_size=99999)
        return {"rows": result.get("preview", []), "columns": result.get("columns", [])}
    except FileNotFoundError:
        return {"rows": [], "columns": ds.columns or []}
    except Exception as e:
        raise HTTPException(500, str(e)[:200])


@router.put("/{dataset_id}/rows")
def save_rows(dataset_id: int, body: RowsBody, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    """Ersetzt alle Zeilen eines Datasets. Autoincrement-Felder werden automatisch befüllt."""
    ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not ds:
        raise HTTPException(404, "Dataset nicht gefunden")
    import json, os
    from app.services.file_service import UPLOAD_DIR, infer_column_types
    import pandas as pd
    from datetime import datetime, timezone
    rows = body.rows or []

    # ── Autoincrement-Felder befüllen ────────────────────────────────────────
    col_types = ds.column_types or {}
    auto_cols = [col for col, info in col_types.items()
                 if info.get("is_primary") and info.get("autoincrement")]

    if auto_cols and rows:
        # Bestehende Daten lesen um MAX-Wert zu ermitteln
        existing_path = os.path.join(UPLOAD_DIR, f"dataset_{dataset_id}.json")
        existing_rows = []
        if os.path.exists(existing_path):
            try:
                with open(existing_path, "r", encoding="utf-8") as ef:
                    existing_rows = json.load(ef)
            except Exception:
                existing_rows = []

        for auto_col in auto_cols:
            # MAX-Wert aus bestehenden Zeilen ermitteln
            all_existing_vals = []
            for er in existing_rows:
                try:
                    v = int(er.get(auto_col, 0) or 0)
                    all_existing_vals.append(v)
                except (ValueError, TypeError):
                    pass
            next_id = (max(all_existing_vals) + 1) if all_existing_vals else 1

            # Neue Zeilen (ohne gültige ID) mit Autoincrement befüllen
            for row in rows:
                val = row.get(auto_col)
                is_empty = val is None or str(val).strip() == "" or str(val) == "0"
                if is_empty:
                    row[auto_col] = str(next_id)
                    next_id += 1

    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    if not df.empty:
        ds.columns = list(df.columns)
        # column_types beibehalten (is_primary/autoincrement nicht überschreiben)
        merged = dict(col_types)
        inferred = infer_column_types(df)
        for col, info in inferred.items():
            if col not in merged:
                merged[col] = info
            else:
                # Nur type/raw aktualisieren, is_primary/autoincrement behalten
                merged[col] = {**merged[col], "type": info["type"], "raw": info["raw"]}
        ds.column_types = merged
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(ds, "column_types")
    ds.row_count = len(rows)
    ds.updated_at = datetime.now(timezone.utc)
    path = os.path.join(UPLOAD_DIR, f"dataset_{dataset_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2, default=str)
    ds.file_path = path
    db.commit()
    return {"ok": True, "rows": len(rows)}


