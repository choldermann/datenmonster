"""
file_export_service – schreibt Exports in strukturierte Verzeichnisse
und registriert sie in der DB.

Pfad: /app/exports/{user_id}/{project_slug}/{context}/{name}_{ts}.{ext}
context = "job_{job_id}" | "manual"
"""
import os
import re
from datetime import datetime
from typing import Optional
import pandas as pd

EXPORT_BASE = os.environ.get("EXPORT_BASE_DIR", "/app/exports")


def _slug(text: str) -> str:
    """Sanitize to filesystem-safe string."""
    return re.sub(r"[^\w\-]", "_", str(text or "unbekannt"))[:50]


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def build_export_path(
    user_id: int,
    project_name: Optional[str],
    context: str,        # "manual" or "job_123"
    target_name: str,
    ext: str,
) -> str:
    parts = [EXPORT_BASE, str(user_id), _slug(project_name or "kein_projekt"), context]
    os.makedirs(os.path.join(*parts), exist_ok=True)
    filename = f"{_slug(target_name)}_{_ts()}.{ext}"
    return os.path.join(*parts, filename)


def save_export_file(
    df: pd.DataFrame,
    *,
    user_id: int,
    project_id: Optional[int],
    project_name: Optional[str],
    job_id: Optional[int],
    mapping_id: Optional[int],
    mapping_name: Optional[str],
    target_name: str,
    target_type: str,        # csv | xlsx | json | xml | db
    target_options: dict,
    db,                      # SQLAlchemy Session
    triggered_by: str = "manual",
) -> dict:
    """
    Writes df to disk in the correct format, registers in export_files table.
    Returns { file_path, file_name, file_size, id }.
    Raises on error.
    """
    from app.models.export_file import ExportFile
    from app.services.export_service import (
        export_csv, export_xlsx, export_json, export_xml, export_destatis_csv,
    )

    context = f"job_{job_id}" if job_id else "manual"
    ext_map = {"csv": "csv", "xlsx": "xlsx", "json": "json", "xml": "xml", "destatis_csv": "csv"}
    ext = ext_map.get(target_type, "csv")

    path = build_export_path(user_id, project_name, context, target_name, ext)
    opts = target_options or {}

    if target_type == "csv":
        content = export_csv(df, delimiter=opts.get("delimiter", ";"), encoding=opts.get("encoding", "utf-8-sig"))
    elif target_type == "destatis_csv":
        content = export_destatis_csv(df, opts.get("destatis_config"))
    elif target_type == "xlsx":
        content = export_xlsx(df)
    elif target_type == "json":
        content = export_json(df, orient=opts.get("orient", "records"), indent=opts.get("indent", 2))
    elif target_type == "xml":
        content = export_xml(df, opts.get("xml_template", {}))
    else:
        raise ValueError(f"Unbekannter target_type für Datei-Export: {target_type}")

    with open(path, "wb") as f:
        f.write(content)

    file_size = os.path.getsize(path)
    file_name = os.path.basename(path)

    record = ExportFile(
        user_id=user_id,
        project_id=project_id,
        project_name=project_name,
        job_id=job_id,
        mapping_id=mapping_id,
        mapping_name=mapping_name,
        target_name=target_name,
        file_path=path,
        file_name=file_name,
        file_ext=ext,
        file_size=file_size,
        triggered_by=triggered_by,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "id": record.id,
        "file_path": path,
        "file_name": file_name,
        "file_size": file_size,
    }
