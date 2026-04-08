"""
Exports API – list, download, delete user export files.
All endpoints are scoped to the current user (no cross-user access).
"""
import os
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional, List
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.export_file import ExportFile

router = APIRouter(prefix="/api/exports", tags=["exports"])


def _out(f: ExportFile) -> dict:
    return {
        "id": f.id,
        "file_name": f.file_name,
        "file_ext": f.file_ext,
        "file_size": f.file_size,
        "project_id": f.project_id,
        "project_name": f.project_name,
        "mapping_name": f.mapping_name,
        "target_name": f.target_name,
        "job_id": f.job_id,
        "triggered_by": f.triggered_by,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


@router.get("/")
def list_exports(
    project_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(ExportFile).filter(ExportFile.user_id == user.id)
    if project_id is not None:
        q = q.filter(ExportFile.project_id == project_id)
    files = q.order_by(ExportFile.created_at.desc()).all()
    return [_out(f) for f in files]


@router.get("/{export_id}/download")
def download_export(
    export_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    f = db.query(ExportFile).filter(
        ExportFile.id == export_id,
        ExportFile.user_id == user.id,
    ).first()
    if not f:
        raise HTTPException(404, "Export nicht gefunden")
    if not os.path.exists(f.file_path):
        raise HTTPException(410, "Datei nicht mehr auf dem Server vorhanden")
    return FileResponse(
        path=f.file_path,
        filename=f.file_name,
        media_type="application/octet-stream",
    )


@router.delete("/{export_id}")
def delete_export(
    export_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    f = db.query(ExportFile).filter(
        ExportFile.id == export_id,
        ExportFile.user_id == user.id,
    ).first()
    if not f:
        raise HTTPException(404, "Export nicht gefunden")
    # Delete file from disk (ignore if already gone)
    try:
        if os.path.exists(f.file_path):
            os.remove(f.file_path)
            # Remove empty parent dirs up to base
            parent = os.path.dirname(f.file_path)
            for _ in range(3):  # max 3 levels up
                if os.path.isdir(parent) and not os.listdir(parent):
                    os.rmdir(parent)
                parent = os.path.dirname(parent)
    except OSError:
        pass
    db.delete(f)
    db.commit()
    return {"ok": True}


@router.delete("/")
def delete_exports_bulk(
    ids: List[int],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    deleted = 0
    for export_id in ids:
        f = db.query(ExportFile).filter(
            ExportFile.id == export_id,
            ExportFile.user_id == user.id,
        ).first()
        if f:
            try:
                if os.path.exists(f.file_path):
                    os.remove(f.file_path)
            except OSError:
                pass
            db.delete(f)
            deleted += 1
    db.commit()
    return {"ok": True, "deleted": deleted}
