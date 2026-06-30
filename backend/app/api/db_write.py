"""
DB-Write API – Tabellen/Spalten auflisten + Sicherheitsprüfung vor dem Schreiben.
Die eigentliche Schreiblogik läuft im pipeline_service (db_write Node).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, text, inspect
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.dataset import DbConnection
from app.services.db_service import get_engine_str

router = APIRouter(prefix="/api/db-write", tags=["db-write"])


def _get_conn(connection_id: int, db: Session) -> DbConnection:
    conn = db.query(DbConnection).filter(DbConnection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Verbindung nicht gefunden")
    return conn


@router.get("/tables")
def list_tables(
    connection_id: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Gibt alle Tabellen der Verbindung zurück."""
    conn = _get_conn(connection_id, db)
    try:
        engine = create_engine(get_engine_str(conn))
        insp = inspect(engine)
        tables = sorted(insp.get_table_names())
        return {"tables": tables}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/columns")
def get_columns(
    connection_id: int = Query(...),
    table: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Gibt Spalten einer Tabelle zurück (Name, Typ, nullable, PK)."""
    conn = _get_conn(connection_id, db)
    try:
        engine = create_engine(get_engine_str(conn))
        insp = inspect(engine)
        pk_cols = set(insp.get_pk_constraint(table).get("constrained_columns", []))
        cols = []
        for c in insp.get_columns(table):
            cols.append({
                "name": c["name"],
                "type": str(c["type"]),
                "nullable": c.get("nullable", True),
                "is_pk": c["name"] in pk_cols,
            })
        return {"columns": cols}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CheckRequest(BaseModel):
    connection_id: int
    table_name: str
    write_mode: str = "append"   # append | upsert | replace
    key_columns: list[str] = []


@router.post("/check")
def check_write(
    body: CheckRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Führt Sicherheitsprüfungen durch OHNE zu schreiben.
    Gibt Prüfergebnisse und Zieltabellen-Schema zurück.
    """
    conn = _get_conn(body.connection_id, db)
    checks = []
    table_columns = []
    can_proceed = True

    # 1) Verbindung erreichbar?
    try:
        engine = create_engine(get_engine_str(conn))
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        checks.append({"id": "connection", "label": "Verbindung erreichbar",
                        "status": "ok", "message": f"{conn.name} antwortet"})
    except Exception as e:
        checks.append({"id": "connection", "label": "Verbindung erreichbar",
                        "status": "error", "message": str(e)[:200]})
        return {"checks": checks, "table_columns": [], "can_proceed": False}

    # 2) Schreibrechte (Test-INSERT in eine temporäre Tabelle / Rollback)
    try:
        with engine.begin() as c:
            tmp = f"__dm_write_test_{conn.id}__"
            db_type = (conn.type or "").lower()
            if "mssql" in db_type:
                c.execute(text(f"CREATE TABLE #{tmp} (id INT)"))
                c.execute(text(f"DROP TABLE #{tmp}"))
            elif "mysql" in db_type or "mariadb" in db_type:
                c.execute(text(f"CREATE TEMPORARY TABLE {tmp} (id INT)"))
                c.execute(text(f"DROP TEMPORARY TABLE {tmp}"))
            else:
                # PostgreSQL / SQLite
                c.execute(text(f"CREATE TEMP TABLE {tmp} (id INT)"))
                c.execute(text(f"DROP TABLE {tmp}"))
        checks.append({"id": "permissions", "label": "Schreibrechte vorhanden",
                        "status": "ok", "message": "Test-Transaktion erfolgreich"})
    except Exception as e:
        checks.append({"id": "permissions", "label": "Schreibrechte vorhanden",
                        "status": "error", "message": f"Kein Schreibrecht: {str(e)[:150]}"})
        can_proceed = False

    # 3) Tabelle vorhanden?
    table_exists = False
    try:
        insp = inspect(engine)
        table_exists = body.table_name in insp.get_table_names()
        if table_exists:
            pk_cols = set(insp.get_pk_constraint(body.table_name).get("constrained_columns", []))
            for col in insp.get_columns(body.table_name):
                table_columns.append({
                    "name": col["name"],
                    "type": str(col["type"]),
                    "nullable": col.get("nullable", True),
                    "is_pk": col["name"] in pk_cols,
                })
            checks.append({"id": "table", "label": f"Tabelle '{body.table_name}' vorhanden",
                            "status": "ok", "message": f"{len(table_columns)} Spalten gefunden"})
        else:
            checks.append({"id": "table", "label": f"Tabelle '{body.table_name}' vorhanden",
                            "status": "warn",
                            "message": "Tabelle existiert noch nicht — wird beim Schreiben angelegt"})
    except Exception as e:
        checks.append({"id": "table", "label": f"Tabelle '{body.table_name}' vorhanden",
                        "status": "error", "message": str(e)[:200]})
        can_proceed = False

    # 4) Upsert: Key-Spalten vorhanden?
    if body.write_mode == "upsert":
        if not body.key_columns:
            checks.append({"id": "upsert_key", "label": "Upsert-Schlüssel konfiguriert",
                            "status": "error", "message": "Kein Key-Feld angegeben — Upsert nicht möglich"})
            can_proceed = False
        elif table_exists:
            col_names = {c["name"] for c in table_columns}
            missing = [k for k in body.key_columns if k not in col_names]
            if missing:
                checks.append({"id": "upsert_key", "label": "Upsert-Schlüssel in Tabelle vorhanden",
                                "status": "error",
                                "message": f"Key-Spalten fehlen in Zieltabelle: {', '.join(missing)}"})
                can_proceed = False
            else:
                checks.append({"id": "upsert_key", "label": "Upsert-Schlüssel in Tabelle vorhanden",
                                "status": "ok",
                                "message": f"Key: {', '.join(body.key_columns)}"})

    # 5) Replace-Warnung
    if body.write_mode == "replace" and table_exists:
        checks.append({"id": "replace_warn", "label": "Replace-Modus",
                        "status": "warn",
                        "message": f"Alle vorhandenen Daten in '{body.table_name}' werden vor dem Schreiben gelöscht"})

    return {"checks": checks, "table_columns": table_columns, "can_proceed": can_proceed}
