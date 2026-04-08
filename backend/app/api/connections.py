from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.dataset import DbConnection, Dataset
from app.services.db_service import test_connection, get_tables, query_preview, query_full, query_full_with_types
from app.services.file_service import dataframe_to_storage, infer_column_types
from app.api.projects import require_editor
from app.core.security import encrypt_credential, decrypt_credential

router = APIRouter(prefix="/api/connections", tags=["connections"])


class ConnectionCreate(BaseModel):
    name: str
    db_type: str
    host: str
    port: int
    database: str
    username: str
    password: str
    project_id: Optional[int] = None


class ConnectionTest(BaseModel):
    name: str = ""
    db_type: str
    host: str
    port: int
    database: str
    username: str
    password: str


class ImportRequest(BaseModel):
    sql: str
    dataset_name: str
    query_config: Optional[dict] = None
    project_id: Optional[int] = None


class PreviewRequest(BaseModel):
    sql: str


def conn_out(c: DbConnection) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "db_type": c.db_type,
        "host": c.host,
        "port": c.port,
        "database": c.database,
        "username": c.username,
        "project_id": c.project_id,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _require_read_conn(conn_id: int, user, db) -> "DbConnection":
    """Lädt eine Verbindung und prüft Lesezugriff."""
    from app.api.projects import can_read_project
    conn = db.query(DbConnection).filter(DbConnection.id == conn_id).first()
    if not conn:
        raise HTTPException(404, "Verbindung nicht gefunden")
    if not can_read_project(conn.project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf diese Verbindung")
    return conn


@router.get("/")
def list_connections(project_id: Optional[int] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.api.projects import get_accessible_project_ids, can_read_project
    if project_id is not None and not can_read_project(project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    q = db.query(DbConnection)
    if project_id is not None:
        q = q.filter(DbConnection.project_id == project_id)
    else:
        accessible = get_accessible_project_ids(user, db)
        if accessible is not None:
            q = q.filter((DbConnection.project_id.in_(accessible)) | (DbConnection.project_id.is_(None)))
    return [conn_out(c) for c in q.order_by(DbConnection.id).all()]


@router.post("/")
def create_connection(data: ConnectionCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_editor(data.project_id, user, db)
    d = data.model_dump()
    if d.get("password"):
        d["password"] = encrypt_credential(d["password"])
    conn = DbConnection(**d)
    db.add(conn); db.commit(); db.refresh(conn)
    return conn_out(conn)


# Import einer Verbindung aus einem anderen Projekt (Verbindungsdaten kopieren)
@router.post("/import-connection")
def import_connection(data: ConnectionCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Kopiert eine bestehende Verbindungskonfiguration in ein neues Projekt."""
    conn = DbConnection(**data.model_dump())
    db.add(conn); db.commit(); db.refresh(conn)
    return conn_out(conn)


@router.post("/test")
def test_conn_form(data: ConnectionTest, user: User = Depends(get_current_user)):
    # Auth erforderlich – verhindert anonymes Port-Scanning / Credential-Testing
    conn = DbConnection(**{k: v for k, v in data.model_dump().items() if k != "name"}, name=data.name or "test")
    return test_connection(conn)


@router.get("/{conn_id}/test")
def test_conn_by_id(conn_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conn = _require_read_conn(conn_id, user, db)
    return test_connection(conn)


@router.get("/{conn_id}/tables")
def list_tables(conn_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conn = db.query(DbConnection).filter(DbConnection.id == conn_id).first()
    if not conn:
        raise HTTPException(404, "Verbindung nicht gefunden")
    try:
        return {"tables": get_tables(conn)}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/{conn_id}/tables-only")
def list_tables_only(conn_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Gibt nur echte Tabellen zurück (keine Views) – für Ziel-Auswahl im Mapping Editor."""
    conn = db.query(DbConnection).filter(DbConnection.id == conn_id).first()
    if not conn:
        raise HTTPException(404, "Verbindung nicht gefunden")
    try:
        from sqlalchemy import create_engine, inspect
        from app.services.db_service import get_engine_str
        engine = create_engine(get_engine_str(conn))
        inspector = inspect(engine)
        tables = []
        if conn.db_type == "mssql":
            SKIP_SCHEMAS = {"sys", "INFORMATION_SCHEMA", "guest", "db_owner",
                            "db_accessadmin", "db_securityadmin", "db_ddladmin",
                            "db_backupoperator", "db_datareader", "db_datawriter",
                            "db_denydatareader", "db_denydatawriter"}
            try:
                schemas = [s for s in inspector.get_schema_names() if s not in SKIP_SCHEMAS]
            except Exception as e:
                import logging as _l; _l.getLogger("datenmonster").warning(f"Schema-Namen Fehler: {e}")
                schemas = ["dbo"]
            for schema in schemas:
                try:
                    for t in inspector.get_table_names(schema=schema):
                        prefix = f"{schema}." if schema != "dbo" else ""
                        tables.append(f"{prefix}{t}")
                except Exception:
                    pass
        else:
            try:
                tables += inspector.get_table_names()
            except Exception as e:
                import logging as _l; _l.getLogger("datenmonster").warning(f"Tabellen abrufen fehlgeschlagen: {e}")
        return {"tables": sorted(set(tables))}
    except Exception as e:
        raise HTTPException(400, str(e)[:500])


@router.get("/{conn_id}/columns")
def list_columns(conn_id: int, table: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conn = db.query(DbConnection).filter(DbConnection.id == conn_id).first()
    if not conn:
        raise HTTPException(404, "Verbindung nicht gefunden")
    try:
        from sqlalchemy import create_engine, inspect
        from app.services.db_service import get_engine_str
        engine = create_engine(get_engine_str(conn))
        if "." in table:
            schema, tname = table.split(".", 1)
        else:
            schema, tname = None, table
        inspector = inspect(engine)
        cols = inspector.get_columns(tname, schema=schema)

        # Primary Keys ermitteln
        try:
            pk_info = inspector.get_pk_constraint(tname, schema=schema)
            pk_cols = set(pk_info.get("constrained_columns", []))
        except Exception:
            pk_cols = set()

        # Typ-Mapping: SQLAlchemy-Typen → einfache Labels
        def _simple_type(col_type) -> str:
            t = str(col_type).upper()
            if any(x in t for x in ("INT", "SERIAL", "BIGINT", "SMALLINT", "TINYINT")):
                return "integer"
            if any(x in t for x in ("FLOAT", "DOUBLE", "REAL", "NUMERIC", "DECIMAL", "MONEY")):
                return "decimal"
            if any(x in t for x in ("DATE", "TIME", "TIMESTAMP")):
                return "date"
            if any(x in t for x in ("BOOL", "BIT")):
                return "boolean"
            return "string"

        result = []
        for c in cols:
            result.append({
                "name": c["name"],
                "type": _simple_type(c["type"]),
                "raw": str(c["type"]),
                "is_primary": c["name"] in pk_cols,
                "nullable": c.get("nullable", True),
            })

        return {"columns": [c["name"] for c in cols], "column_details": result}
    except Exception as e:
        raise HTTPException(400, str(e)[:500])


@router.post("/{conn_id}/preview")
def preview_query(conn_id: int, req: PreviewRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conn = db.query(DbConnection).filter(DbConnection.id == conn_id).first()
    if not conn:
        raise HTTPException(404, "Verbindung nicht gefunden")
    try:
        return query_preview(conn, req.sql)
    except Exception as e:
        raise HTTPException(400, str(e)[:500])


@router.post("/{conn_id}/import")
def import_query(conn_id: int, req: ImportRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conn = db.query(DbConnection).filter(DbConnection.id == conn_id).first()
    if not conn:
        raise HTTPException(404, "Verbindung nicht gefunden")
    require_editor(req.project_id, user, db)
    try:
        df, raw_types = query_full_with_types(conn, req.sql)
        file_type = f"db_{conn.db_type}"
        ds = Dataset(
            name=req.dataset_name,
            original_filename=f"{conn.name} – SQL",
            file_type=file_type,
            xml_configured=1,
            row_count=len(df),
            columns=df.columns.tolist(),
            column_types=infer_column_types(df, raw_types),
            source_connection_id=conn.id,
            source_sql=req.sql,
            query_config=req.query_config,
            project_id=req.project_id,
        )
        db.add(ds)
        db.commit()
        db.refresh(ds)
        dataframe_to_storage(df, ds.id)
        return {"id": ds.id, "name": ds.name}
    except Exception as e:
        raise HTTPException(400, str(e)[:500])


class ReimportRequest(BaseModel):
    sql: str
    dataset_name: str
    query_config: Optional[dict] = None


@router.post("/{conn_id}/reimport/{dataset_id}")
def reimport_query(conn_id: int, dataset_id: int, req: ReimportRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conn = db.query(DbConnection).filter(DbConnection.id == conn_id).first()
    if not conn:
        raise HTTPException(404, "Verbindung nicht gefunden")
    ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not ds:
        raise HTTPException(404, "Dataset nicht gefunden")
    require_editor(ds.project_id, user, db)
    try:
        df, raw_types = query_full_with_types(conn, req.sql)
        ds.name = req.dataset_name
        ds.source_sql = req.sql
        ds.query_config = req.query_config
        ds.row_count = len(df)
        ds.columns = df.columns.tolist()
        ds.column_types = infer_column_types(df, raw_types)
        db.commit()
        dataframe_to_storage(df, ds.id)
        return {"id": ds.id, "name": ds.name}
    except Exception as e:
        raise HTTPException(400, str(e)[:500])


@router.patch("/{conn_id}")
def update_connection(conn_id: int, data: ConnectionCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conn = db.query(DbConnection).filter(DbConnection.id == conn_id).first()
    if not conn:
        raise HTTPException(404, "Verbindung nicht gefunden")
    require_editor(conn.project_id, user, db)
    for k, v in data.model_dump().items():
        setattr(conn, k, v)
    db.commit()
    return conn_out(conn)


@router.delete("/{conn_id}")
def delete_connection(conn_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conn = db.query(DbConnection).filter(DbConnection.id == conn_id).first()
    if not conn:
        raise HTTPException(404, "Verbindung nicht gefunden")
    require_editor(conn.project_id, user, db)
    db.delete(conn)
    db.commit()
    return {"ok": True}
