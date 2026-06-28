"""
SQL-Hilfsfunktionen für das Mapping-System.
Engine-Cache, Parameter-Auflösung, Aggregation.
"""

_sql_engine_cache: dict = {}


def _resolve_sql_params(sql: str, flat_row: dict):
    """
    Ersetzt {Feldname} Platzhalter im SQL mit parametrisierten Werten.
    Gibt (sql_with_placeholders, params_dict) zurück statt direkter String-Interpolation.
    Das verhindert SQL-Injection: Werte werden nie direkt in den SQL-String eingebaut.
    """
    import re
    params = {}
    counter = [0]

    def replacer(m):
        field = m.group(1)
        safe_field = re.sub(r"[^a-zA-Z0-9_]", "_", field)
        counter[0] += 1
        param_name = f"param_{safe_field}_{counter[0]}"
        val = flat_row.get(field)
        params[param_name] = val
        return f":{param_name}"

    resolved = re.sub(r"\{([^}]+)\}", replacer, sql)
    return resolved, params


def _resolve_sql_lookup_params(sql: str, param_mappings: list, flat_row: dict):
    """
    Ersetzt :param_name Platzhalter im SQL für den Lookup-Modus.
    param_mappings: [{param: "kArtikel", source_field: "kArtikel"}, ...]
    Gibt (resolved_sql, params_dict) zurück — SQL-Injection-sicher.
    """
    import re as _re_lk
    params = {}

    def replacer(m):
        param_name = m.group(1)
        source_field = param_name
        for pm in (param_mappings or []):
            if pm.get("param") == param_name:
                source_field = pm.get("source_field") or param_name
                break
        safe = _re_lk.sub(r"[^a-zA-Z0-9_]", "_", param_name)
        key = f"lkp_{safe}"
        params[key] = flat_row.get(source_field)
        return f":{key}"

    resolved = _re_lk.sub(r":([a-zA-Z_][a-zA-Z0-9_]*)", replacer, sql)
    return resolved, params


def _get_sql_engine(connection_id: int):
    """Holt oder erstellt eine SQLAlchemy-Engine für eine DB-Verbindung."""
    global _sql_engine_cache
    if connection_id in _sql_engine_cache:
        return _sql_engine_cache[connection_id]
    from app.core.database import SessionLocal
    from app.models.dataset import DbConnection
    from app.services.db_service import get_engine_str
    from sqlalchemy import create_engine
    db = SessionLocal()
    try:
        conn_obj = db.query(DbConnection).filter(DbConnection.id == connection_id).first()
        if not conn_obj:
            raise ValueError(f"DB-Verbindung #{connection_id} nicht gefunden")
        engine = create_engine(get_engine_str(conn_obj))
        _sql_engine_cache[connection_id] = engine
        return engine
    finally:
        db.close()
