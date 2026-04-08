import pandas as pd
import logging
from app.models.dataset import DbConnection
from app.core.security import decrypt_credential


# Reihenfolge: erstmal latin-1 (decodes alles ohne Fehler),
# dann als String weiterverarbeiten
MSSQL_DECODE_ORDER = ["utf-8", "cp1252", "latin-1"]


def _decode_value(v):
    """Bytes sicher zu String konvertieren – probiert mehrere Encodings."""
    if v is None:
        return None
    if isinstance(v, bytes):
        for enc in MSSQL_DECODE_ORDER:
            try:
                return v.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return v.decode("latin-1", errors="replace")  # absoluter Fallback
    return v


def _clean_value(v):
    """Wert zu JSON-serialisierbarem Typ – Ganzzahlen ohne .0."""
    import math
    if v is None:
        return None
    if isinstance(v, bytes):
        return _decode_value(v)
    if isinstance(v, str):
        return v
    if isinstance(v, float):
        if math.isnan(v):
            return None
        if v == int(v):
            return int(v)
        return v
    # Decimal, numpy int64 etc. – prüfe ob ganzzahlig
    try:
        iv = int(v)
        if iv == v:
            return iv
    except (ValueError, TypeError, OverflowError):
        pass
    return str(v)


def _clean_row(cols, row):
    return {k: _clean_value(v) for k, v in zip(cols, row)}


def get_engine_str(conn: DbConnection) -> str:
    if conn.db_type == "mssql":
        from urllib.parse import quote_plus
        params = quote_plus(
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={conn.host},{conn.port};"
            f"DATABASE={conn.database};"
            f"UID={conn.username};PWD={decrypt_credential(conn.password)};"
            f"TrustServerCertificate=yes"
        )
        return f"mssql+pyodbc:///?odbc_connect={params}"
    elif conn.db_type == "mysql":
        return (
            f"mysql+pymysql://{conn.username}:{decrypt_credential(conn.password)}@"
            f"{conn.host}:{conn.port}/{conn.database}"
            f"?charset=utf8mb4"
        )
    elif conn.db_type == "postgresql":
        return (
            f"postgresql+psycopg2://{conn.username}:{decrypt_credential(conn.password)}@"
            f"{conn.host}:{conn.port}/{conn.database}"
        )
    raise ValueError(f"Unsupported db_type: {conn.db_type}")


def test_connection(conn: DbConnection) -> dict:
    try:
        from sqlalchemy import create_engine, text
        connect_args = {}
        if conn.db_type == "mssql":
            connect_args = {"timeout": 5, "login_timeout": 5}
        elif conn.db_type in ("mysql", "postgresql"):
            connect_args = {"connect_timeout": 5}
        engine = create_engine(get_engine_str(conn), connect_args=connect_args)
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        return {"success": True, "message": "Verbindung erfolgreich"}
    except Exception as e:
        return {"success": False, "message": str(e)[:300]}


def get_tables(conn: DbConnection) -> list[str]:
    from sqlalchemy import create_engine, inspect, text
    engine = create_engine(get_engine_str(conn))
    inspector = inspect(engine)

    all_entries = []

    if conn.db_type == "mssql":
        # MSSQL: alle Schemas abfragen, Schema.Tabelle zurückgeben
        # Systemschemas ausschließen
        SKIP_SCHEMAS = {"sys", "INFORMATION_SCHEMA", "guest", "db_owner",
                        "db_accessadmin", "db_securityadmin", "db_ddladmin",
                        "db_backupoperator", "db_datareader", "db_datawriter",
                        "db_denydatareader", "db_denydatawriter"}
        try:
            schemas = [s for s in inspector.get_schema_names() if s not in SKIP_SCHEMAS]
        except Exception:
            schemas = ["dbo"]

        for schema in schemas:
            try:
                for t in inspector.get_table_names(schema=schema):
                    prefix = f"{schema}." if schema != "dbo" else ""
                    all_entries.append(f"{prefix}{t}")
            except Exception:
                pass
            try:
                for v in inspector.get_view_names(schema=schema):
                    prefix = f"{schema}." if schema != "dbo" else ""
                    all_entries.append(f"{prefix}{v}")
            except Exception:
                pass

    else:
        # MySQL / PostgreSQL: einfache Abfrage reicht
        try:
            all_entries += inspector.get_table_names()
        except Exception:
            pass
        try:
            all_entries += inspector.get_view_names()
        except Exception:
            pass

    return sorted(set(all_entries))


def query_preview(conn: DbConnection, sql: str, limit: int = 50) -> dict:
    from sqlalchemy import create_engine, text
    engine = create_engine(get_engine_str(conn))
    with engine.connect() as c:
        result = c.execute(text(sql))
        cols = list(result.keys())
        rows = [_clean_row(cols, row) for row in result.fetchmany(limit)]
        try:
            count_sql = f"SELECT COUNT(*) FROM ({sql}) AS _sub"
            total = c.execute(text(count_sql)).scalar()
        except Exception:
            total = len(rows)
    return {"columns": cols, "rows": rows, "total_rows": total}


def query_full(conn: DbConnection, sql: str) -> pd.DataFrame:
    from sqlalchemy import create_engine, text
    engine = create_engine(get_engine_str(conn))
    with engine.connect() as c:
        result = c.execute(text(sql))
        cols = list(result.keys())
        rows = [_clean_row(cols, row) for row in result.fetchall()]
    return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)


def query_full_with_types(conn: DbConnection, sql: str):
    """Gibt (DataFrame, {col: raw_db_type_string}) zurück."""
    from sqlalchemy import create_engine, text
    engine = create_engine(get_engine_str(conn))
    with engine.connect() as c:
        result = c.execute(text(sql))
        cols = list(result.keys())
        # Rohe DB-Typen aus Cursor-Beschreibung
        raw_types = {}
        if result.cursor and result.cursor.description:
            for desc in result.cursor.description:
                col_name = desc[0]
                try:
                    raw_types[col_name] = str(desc[1].__name__) if hasattr(desc[1], "__name__") else str(desc[1])
                except Exception:
                    raw_types[col_name] = "unknown"
        rows = [_clean_row(cols, row) for row in result.fetchall()]
    df = pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)
    return df, raw_types
