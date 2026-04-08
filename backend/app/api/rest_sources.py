from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.rest_source import RestSource
from app.models.dataset import Dataset
from app.api.projects import (
    require_editor, can_read_project,
    get_accessible_project_ids, get_project_role,
)
from app.services.rest_service import fetch_rest_source, test_rest_source
from app.services.file_service import dataframe_to_storage, infer_column_types

router = APIRouter(prefix="/api/rest-sources", tags=["rest-sources"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class RestSourceCreate(BaseModel):
    name: str
    project_id: Optional[int] = None
    url: str
    method: str = "GET"
    headers: Optional[dict] = {}
    query_params: Optional[dict] = {}
    body_type: str = "none"
    body_content: Optional[str] = None
    auth_type: str = "none"
    auth_config: Optional[dict] = {}
    data_path: Optional[str] = None
    flatten: int = 1
    pagination: Optional[dict] = {}
    dataset_id: Optional[int] = None
    dataset_mode: str = "replace"
    cron_expr: Optional[str] = None
    active: int = 1


class RestSourceUpdate(RestSourceCreate):
    pass


class TestRequest(BaseModel):
    url: str
    method: str = "GET"
    headers: Optional[dict] = {}
    query_params: Optional[dict] = {}
    body_type: str = "none"
    body_content: Optional[str] = None
    auth_type: str = "none"
    auth_config: Optional[dict] = {}
    data_path: Optional[str] = None
    flatten: int = 1
    pagination: Optional[dict] = {}


class ImportRequest(BaseModel):
    dataset_name: str
    project_id: Optional[int] = None
    dataset_mode: str = "replace"
    dataset_id: Optional[int] = None


# ── Output ────────────────────────────────────────────────────────────────────

def source_out(s: RestSource) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "project_id": s.project_id,
        "url": s.url,
        "method": s.method,
        "headers": s.headers or {},
        "query_params": s.query_params or {},
        "body_type": s.body_type,
        "body_content": s.body_content,
        "auth_type": s.auth_type,
        "auth_config": s.auth_config or {},
        "data_path": s.data_path,
        "flatten": s.flatten,
        "pagination": s.pagination or {},
        "dataset_id": s.dataset_id,
        "dataset_mode": s.dataset_mode,
        "cron_expr": s.cron_expr,
        "active": s.active,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
        "last_run_status": s.last_run_status,
        "last_run_msg": s.last_run_msg,
        "last_rows": s.last_rows,
    }


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _get(source_id: int, db: Session) -> RestSource:
    s = db.query(RestSource).filter(RestSource.id == source_id).first()
    if not s:
        raise HTTPException(404, "REST-Source nicht gefunden")
    return s


def _check_read_access(s: RestSource, user: User, db: Session):
    """
    Prüft Lesezugriff:
    - Sources mit Projekt: User muss Mitglied sein (jede Rolle reicht)
    - Sources ohne Projekt (project_id=None): nur Admins
    """
    if s.project_id is not None:
        if not can_read_project(s.project_id, user, db):
            raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    else:
        # Kein Projekt → nur Admins
        if not getattr(user, "is_admin", False):
            raise HTTPException(403, "Nur Administratoren können projektlose Ressourcen sehen")


def _update_run_status(s: RestSource, db: Session, status: str, msg: str, rows: int):
    s.last_run_at = datetime.utcnow()
    s.last_run_status = status
    s.last_run_msg = msg
    s.last_rows = rows
    db.commit()


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("/")
def list_rest_sources(
    project_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Gibt nur REST-Sources zurück auf die der User Zugriff hat:
    - Mit project_id-Filter: nur wenn User Mitglied ist
    - Ohne Filter: alle zugänglichen Projekte des Users + projektlose nur für Admins
    """
    is_admin = getattr(user, "is_admin", False)
    q = db.query(RestSource)

    if project_id is not None:
        # Expliziter Filter: Zugriff auf dieses Projekt prüfen
        if not can_read_project(project_id, user, db):
            raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
        q = q.filter(RestSource.project_id == project_id)
    else:
        # Kein Filter → nur eigene Projekte + geteilte Projekte
        accessible_ids = get_accessible_project_ids(user, db)
        if accessible_ids is None:
            # Admin: alles sichtbar, kein Filter nötig
            pass
        else:
            # Normaler User: nur eigene Projektquellen
            # Projektlose Sources (project_id=None) bleiben ausgeblendet
            q = q.filter(RestSource.project_id.in_(accessible_ids))

    return [source_out(s) for s in q.order_by(RestSource.id.desc()).all()]


@router.post("/")
def create_rest_source(
    payload: RestSourceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Projektlose Sources nur für Admins
    if payload.project_id is None and not getattr(user, "is_admin", False):
        raise HTTPException(403, "Nur Administratoren können projektlose REST-Sources anlegen")
    require_editor(payload.project_id, user, db)
    s = RestSource(**payload.model_dump())
    db.add(s); db.commit(); db.refresh(s)
    return source_out(s)


@router.get("/{source_id}")
def get_rest_source(
    source_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    s = _get(source_id, db)
    _check_read_access(s, user, db)
    return source_out(s)


@router.put("/{source_id}")
def update_rest_source(
    source_id: int,
    payload: RestSourceUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    s = _get(source_id, db)
    # Schreibzugriff auf aktuelles Projekt prüfen
    require_editor(s.project_id, user, db)
    # Falls Projekt gewechselt wird: auch Zugriff auf neues Projekt prüfen
    if payload.project_id != s.project_id:
        if payload.project_id is None and not getattr(user, "is_admin", False):
            raise HTTPException(403, "Nur Administratoren können Sources aus Projekten entfernen")
        require_editor(payload.project_id, user, db)
    for k, v in payload.model_dump().items():
        setattr(s, k, v)
    db.commit(); db.refresh(s)
    return source_out(s)


@router.delete("/{source_id}")
def delete_rest_source(
    source_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    s = _get(source_id, db)
    require_editor(s.project_id, user, db)
    db.delete(s); db.commit()
    return {"ok": True}


# ── Test ──────────────────────────────────────────────────────────────────────

@router.post("/test")
def test_endpoint(
    payload: TestRequest,
    user: User = Depends(get_current_user),  # Authentifizierung reicht, kein Projektzugriff nötig
):
    """Testet einen Connector ohne zu speichern. Gibt max. 10 Zeilen Vorschau zurück."""
    result = test_rest_source(payload.model_dump())
    return result


@router.post("/{source_id}/test")
def test_saved_source(
    source_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Testet einen gespeicherten Connector – Lesezugriff reicht."""
    s = _get(source_id, db)
    _check_read_access(s, user, db)
    result = test_rest_source({
        "url": s.url, "method": s.method, "headers": s.headers,
        "query_params": s.query_params, "body_type": s.body_type,
        "body_content": s.body_content, "auth_type": s.auth_type,
        "auth_config": s.auth_config, "data_path": s.data_path,
        "flatten": s.flatten, "pagination": s.pagination,
    })
    return result


# ── Import (vollständig, mit Paginierung) ─────────────────────────────────────

@router.post("/{source_id}/import")
def import_rest_source(
    source_id: int,
    payload: ImportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Importiert alle Daten als Dataset.
    Erfordert Editor-Zugriff auf das Quell-Projekt UND (falls angegeben) das Ziel-Projekt.
    """
    s = _get(source_id, db)
    # Lesezugriff auf Source
    _check_read_access(s, user, db)
    # Schreibzugriff auf Ziel-Projekt
    target_project_id = payload.project_id or s.project_id
    require_editor(target_project_id, user, db)

    try:
        df = fetch_rest_source(s)
    except Exception as e:
        _update_run_status(s, db, "error", str(e)[:500], 0)
        raise HTTPException(502, f"API-Fehler: {str(e)[:400]}")

    if df.empty:
        _update_run_status(s, db, "ok", "Leere Antwort", 0)
        raise HTTPException(204, "API lieferte keine Daten")

    col_types = infer_column_types(df)
    target_ds_id = payload.dataset_id or s.dataset_id
    mode = payload.dataset_mode or s.dataset_mode or "replace"

    if target_ds_id and mode == "append":
        existing = db.query(Dataset).filter(Dataset.id == target_ds_id).first()
        if existing:
            # Auch Schreibzugriff auf das Ziel-Dataset-Projekt prüfen
            require_editor(existing.project_id, user, db)
            import pandas as _pd
            from app.services.file_service import read_dataset
            old_df = read_dataset(existing)
            combined = _pd.concat([old_df, df], ignore_index=True)
            dataframe_to_storage(combined, existing.id)
            existing.row_count = len(combined)
            existing.columns = list(combined.columns)
            existing.column_types = infer_column_types(combined)
            db.commit(); db.refresh(existing)
            _update_run_status(s, db, "ok", f"+{len(df)} Zeilen angehängt", len(df))
            from app.api.datasets import dataset_out
            return dataset_out(existing)

    ds_name = payload.dataset_name or s.name
    if target_ds_id and mode == "replace":
        ds = db.query(Dataset).filter(Dataset.id == target_ds_id).first()
        if ds:
            require_editor(ds.project_id, user, db)
            ds.name = ds_name
            ds.row_count = len(df)
            ds.columns = list(df.columns)
            ds.column_types = col_types
            ds.file_type = "csv"
            db.commit(); db.refresh(ds)
            dataframe_to_storage(df, ds.id)
            _update_run_status(s, db, "ok", f"{len(df)} Zeilen importiert (replace)", len(df))
            from app.api.datasets import dataset_out
            return dataset_out(ds)

    ds = Dataset(
        name=ds_name,
        original_filename=f"{s.name}.json",
        file_type="csv",
        xml_configured=1,
        row_count=len(df),
        columns=list(df.columns),
        column_types=col_types,
        project_id=target_project_id,
    )
    db.add(ds); db.commit(); db.refresh(ds)
    dataframe_to_storage(df, ds.id)
    s.dataset_id = ds.id
    _update_run_status(s, db, "ok", f"{len(df)} Zeilen importiert", len(df))
    from app.api.datasets import dataset_out
    return dataset_out(ds)


# ── Trigger (Hintergrund-Import) ──────────────────────────────────────────────

@router.post("/{source_id}/trigger")
def trigger_rest_source(
    source_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Startet einen manuellen Import im Hintergrund.
    Erfordert Editor-Zugriff – kein Viewer-Trigger möglich.
    """
    s = _get(source_id, db)
    require_editor(s.project_id, user, db)  # ← Fix: war vorher nicht geprüft

    def run():
        from app.core.database import SessionLocal
        _db = SessionLocal()
        try:
            src = _db.query(RestSource).filter(RestSource.id == source_id).first()
            if not src:
                return
            df = fetch_rest_source(src)
            if df.empty:
                _update_run_status(src, _db, "ok", "Leere Antwort", 0)
                return
            col_types = infer_column_types(df)
            if src.dataset_id:
                ds = _db.query(Dataset).filter(Dataset.id == src.dataset_id).first()
                if ds:
                    if src.dataset_mode == "append":
                        from app.services.file_service import read_dataset
                        import pandas as _pd
                        old = read_dataset(ds)
                        combined = _pd.concat([old, df], ignore_index=True)
                        dataframe_to_storage(combined, ds.id)
                        ds.row_count = len(combined)
                        ds.columns = list(combined.columns)
                    else:
                        dataframe_to_storage(df, ds.id)
                        ds.row_count = len(df)
                        ds.columns = list(df.columns)
                    ds.column_types = col_types
                    _db.commit()
            else:
                ds = Dataset(
                    name=src.name, original_filename=f"{src.name}.json",
                    file_type="csv", xml_configured=1, row_count=len(df),
                    columns=list(df.columns), column_types=col_types,
                    project_id=src.project_id,
                )
                _db.add(ds); _db.commit(); _db.refresh(ds)
                dataframe_to_storage(df, ds.id)
                src.dataset_id = ds.id
            _update_run_status(src, _db, "ok", f"{len(df)} Zeilen", len(df))
        except Exception as e:
            try:
                src = _db.query(RestSource).filter(RestSource.id == source_id).first()
                if src:
                    _update_run_status(src, _db, "error", str(e)[:400], 0)
            except Exception:
                pass
        finally:
            _db.close()

    background_tasks.add_task(run)
    return {"ok": True, "message": "Import gestartet"}
