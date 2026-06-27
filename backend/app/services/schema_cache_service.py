"""
Persistent schema cache for DB connections.
Builds a structured JSON snapshot of a DB schema and stores it in DbConnection.schema_cache.
The AI context builder reads from this cache to avoid live DB queries and to filter
relevant tables by keyword before sending to the model.
"""
import json
import logging
from datetime import datetime, timezone

log = logging.getLogger("datenmonster")

SKIP_SCHEMAS = {
    "sys", "INFORMATION_SCHEMA", "guest", "db_owner",
    "db_accessadmin", "db_securityadmin", "db_ddladmin",
    "db_backupoperator", "db_datareader", "db_datawriter",
    "db_denydatareader", "db_denydatawriter",
}


def build_schema_json(conn, timeout_sec: int = 90) -> dict:
    """
    Queries the live DB and returns a structured schema dict:
    {db_type, database, tables: [{schema, name, full_name, columns: [{name, type, pk, fk}]}]}
    Raises TimeoutError if the operation takes longer than timeout_sec.
    """
    import concurrent.futures as _cf

    with _cf.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_build_schema_json_inner, conn)
        try:
            return future.result(timeout=timeout_sec)
        except _cf.TimeoutError:
            raise TimeoutError(f"Schema-Build hat nach {timeout_sec}s abgebrochen (DB zu groß oder nicht erreichbar)")


def _build_schema_json_inner(conn) -> dict:
    """Inner (blocking) schema build — call via build_schema_json for timeout protection."""
    from sqlalchemy import create_engine, text
    from app.services.db_service import get_engine_str

    db_type = conn.db_type
    # Use raw SQL for schema discovery — much faster than SQLAlchemy inspector on large MSSQL DBs
    engine = create_engine(
        get_engine_str(conn),
        connect_args={"timeout": 15, "login_timeout": 10} if db_type == "mssql" else {"connect_timeout": 10},
    )

    tables = []
    try:
        with engine.connect() as con:
            if db_type == "mssql":
                # Single query: all schemas, tables, columns, PKs in one shot
                rows = con.execute(text("""
                    SELECT
                        s.name  AS schema_name,
                        t.name  AS table_name,
                        c.name  AS col_name,
                        tp.name AS col_type,
                        CASE WHEN pk.column_name IS NOT NULL THEN 1 ELSE 0 END AS is_pk,
                        CASE WHEN fk.parent_column_id IS NOT NULL THEN 1 ELSE 0 END AS is_fk,
                        fk_ref.name AS fk_ref_table,
                        fk_ref_s.name AS fk_ref_schema,
                        fkc_ref.name AS fk_ref_col
                    FROM sys.tables t
                    JOIN sys.schemas s ON t.schema_id = s.schema_id
                    JOIN sys.columns c ON c.object_id = t.object_id
                    JOIN sys.types tp  ON c.user_type_id = tp.user_type_id
                    LEFT JOIN (
                        SELECT ku.TABLE_SCHEMA, ku.TABLE_NAME, ku.COLUMN_NAME
                        FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                        JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE ku
                          ON tc.CONSTRAINT_NAME = ku.CONSTRAINT_NAME
                         AND tc.TABLE_SCHEMA = ku.TABLE_SCHEMA
                        WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
                    ) pk ON pk.TABLE_SCHEMA = s.name
                         AND pk.TABLE_NAME  = t.name
                         AND pk.COLUMN_NAME = c.name
                    LEFT JOIN sys.foreign_key_columns fk
                           ON fk.parent_object_id = c.object_id
                          AND fk.parent_column_id  = c.column_id
                    LEFT JOIN sys.tables   fk_ref   ON fk_ref.object_id   = fk.referenced_object_id
                    LEFT JOIN sys.schemas  fk_ref_s ON fk_ref_s.schema_id = fk_ref.schema_id
                    LEFT JOIN sys.columns  fkc_ref  ON fkc_ref.object_id  = fk.referenced_object_id
                                                    AND fkc_ref.column_id = fk.referenced_column_id
                    WHERE s.name NOT IN (
                        'sys','INFORMATION_SCHEMA','guest','db_owner',
                        'db_accessadmin','db_securityadmin','db_ddladmin',
                        'db_backupoperator','db_datareader','db_datawriter',
                        'db_denydatareader','db_denydatawriter'
                    )
                    ORDER BY s.name, t.name, c.column_id
                """)).fetchall()

                cur_table = None
                for row in rows:
                    key = f"{row.schema_name}.{row.table_name}"
                    if key != cur_table:
                        cur_table = key
                        tables.append({
                            "schema":    row.schema_name,
                            "name":      row.table_name,
                            "full_name": key,
                            "columns":   [],
                        })
                    col: dict = {"name": row.col_name, "type": row.col_type}
                    if row.is_pk:
                        col["pk"] = True
                    if row.is_fk and row.fk_ref_table:
                        ref = f"{row.fk_ref_schema}.{row.fk_ref_table}.{row.fk_ref_col}" if row.fk_ref_schema else f"{row.fk_ref_table}.{row.fk_ref_col}"
                        col["fk"] = ref
                    tables[-1]["columns"].append(col)

            else:
                # MySQL / PostgreSQL: use inspector (faster than MSSQL)
                from sqlalchemy import inspect as _inspect
                inspector = _inspect(engine)
                for tname in inspector.get_table_names():
                    try:
                        cols_raw = inspector.get_columns(tname)
                        pk_cols = set(inspector.get_pk_constraint(tname).get("constrained_columns", []))
                    except Exception:
                        continue
                    columns = []
                    for c in cols_raw:
                        col_type = str(c["type"]).split("(")[0]
                        entry = {"name": c["name"], "type": col_type}
                        if c["name"] in pk_cols:
                            entry["pk"] = True
                        columns.append(entry)
                    tables.append({
                        "schema": "", "name": tname, "full_name": tname, "columns": columns,
                    })
    finally:
        engine.dispose()

    return {
        "db_type":  db_type,
        "database": conn.database,
        "tables":   tables,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }


def schema_json_to_text(schema_json: dict, max_tables: int = 120) -> str:
    """Renders a schema JSON dict to the compact text format used by the AI prompt."""
    db_type  = schema_json.get("db_type", "")
    database = schema_json.get("database", "")
    tables   = schema_json.get("tables", [])

    lines = [f"Datenbank: {database} ({db_type})"]
    for tbl in tables[:max_tables]:
        lines.append(f"\nTabelle {tbl['full_name']}:")
        for c in tbl["columns"]:
            flags = []
            if c.get("pk"):
                flags.append("PK")
            flag_str = f"  [{','.join(flags)}]" if flags else ""
            lines.append(f"  {c['name']} {c['type']}{flag_str}")
            if c.get("fk"):
                lines.append(f"    → FK: {c['fk']}")
    return "\n".join(lines)


def filter_schema_by_keywords(schema_json: dict, keywords: list[str], max_tables: int = 30) -> dict:
    """
    Returns a copy of schema_json with only tables relevant to the given keywords.
    Matches against table names and column names (case-insensitive).
    Falls back to first max_tables tables if no match found.
    """
    if not keywords:
        filtered = schema_json.get("tables", [])[:max_tables]
        return {**schema_json, "tables": filtered}

    kw_lower = [k.lower() for k in keywords if len(k) > 2]
    scored = []
    for tbl in schema_json.get("tables", []):
        score = 0
        tname_lower = tbl["full_name"].lower()
        for kw in kw_lower:
            if kw in tname_lower:
                score += 3  # table name match weights more
        col_names_lower = " ".join(c["name"].lower() for c in tbl.get("columns", []))
        for kw in kw_lower:
            if kw in col_names_lower:
                score += 1
        if score > 0:
            scored.append((score, tbl))

    if scored:
        scored.sort(key=lambda x: -x[0])
        filtered = [t for _, t in scored[:max_tables]]
    else:
        filtered = schema_json.get("tables", [])[:max_tables]

    return {**schema_json, "tables": filtered}


def extract_keywords(text: str) -> list[str]:
    """Extract meaningful words from a description for schema filtering."""
    import re
    # Split on whitespace and punctuation, keep words >= 3 chars
    words = re.split(r"[\s,;.()\[\]{}\"'/\\|+\-=<>!?@#$%^&*]+", text)
    # Deduplicate, lowercase, filter short/stop words
    STOP = {"und", "oder", "die", "der", "das", "mit", "für", "von", "aus", "alle",
            "the", "and", "for", "with", "from", "all", "bitte", "nach", "eine", "einen"}
    seen = set()
    result = []
    for w in words:
        wl = w.lower()
        if len(wl) >= 3 and wl not in STOP and wl not in seen:
            seen.add(wl)
            result.append(wl)
    return result


def rebuild_cache(conn_id: int, db) -> dict:
    """
    Builds a fresh schema JSON for the given connection and saves it to DB.
    Returns the schema dict on success, raises on error.
    """
    from app.models.dataset import DbConnection
    conn = db.query(DbConnection).filter(DbConnection.id == conn_id).first()
    if not conn:
        raise ValueError(f"Connection {conn_id} not found")

    schema = build_schema_json(conn)
    conn.schema_cache     = json.dumps(schema, ensure_ascii=False)
    conn.schema_cached_at = datetime.now(timezone.utc)
    db.commit()
    log.info(f"Schema cache rebuilt for connection {conn_id} ({len(schema['tables'])} tables)")
    return schema


def get_cached_schema(conn) -> dict | None:
    """Returns the parsed schema JSON from conn.schema_cache, or None if not cached."""
    if not getattr(conn, "schema_cache", None):
        return None
    try:
        return json.loads(conn.schema_cache)
    except Exception:
        return None
