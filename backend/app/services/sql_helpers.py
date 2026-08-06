"""
SQL-Hilfsfunktionen für das Mapping-System.
Engine-Cache, Parameter-Auflösung, Aggregation.
"""

_sql_engine_cache: dict = {}

import re as _re_mod
_ISO_DATE_RE = _re_mod.compile(r"^\d{4}-\d{2}-\d{2}$")


def _coerce_param(val):
    """Wandelt reine ISO-Datumsstrings (YYYY-MM-DD) in echte date-Objekte um, damit
    der DB-Treiber sie als DATE bindet statt als nvarchar. Sonst interpretiert z.B.
    MS SQL Server unter deutscher Spracheinstellung »2026-07-31« als Tag/Monat-
    vertauscht → »Monat 31« → Fehler 242 (22007, out of range). Andere Werte bleiben
    unverändert."""
    if isinstance(val, str) and _ISO_DATE_RE.match(val):
        import datetime
        try:
            return datetime.date.fromisoformat(val)
        except ValueError:
            return val
    return val


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


def _resolve_sql_run_params(sql: str, run_params: dict):
    """
    Löst :name Platzhalter im SQL-Text des Transform-Modus über run_params auf
    (z.B. aus einem Formular). Gibt (sql, params_dict) zurück, params_dict wird
    read_sql()/text() als gebundene Parameter übergeben – SQL-Injection-sicher,
    da nie String-Interpolation in den SQL-Text erfolgt.

    Fallback für :year/:month falls nicht in run_params enthalten: letzter voller
    Kalendermonat (bisheriges automatisches Verhalten bleibt so für Pipeline-Läufe
    ohne Formular erhalten).
    """
    import re as _re
    run_params = run_params or {}
    referenced = set(_re.findall(r":([a-zA-Z_][a-zA-Z0-9_]*)", sql))
    if not referenced:
        return sql, {}

    default_year = default_month = None
    if ("year" in referenced or "month" in referenced) and not ("year" in run_params and "month" in run_params):
        import datetime
        prev_month_last_day = datetime.date.today().replace(day=1) - datetime.timedelta(days=1)
        default_year, default_month = prev_month_last_day.year, prev_month_last_day.month

    params = {}
    for name in referenced:
        if name in run_params:
            val = run_params[name]
            # Listen-Parameter (z.B. Ausschlussartikel für NOT IN) werden in einzelne
            # gebundene Skalar-Parameter :name__0, :name__1 … expandiert. Leere Liste →
            # NULL, damit "x NOT IN (NULL)" nicht ungewollt alle Zeilen filtert (die
            # aufrufenden SQLs kombinieren das mit einer :name_empty=1-Kurzschluss-Klausel).
            if isinstance(val, (list, tuple, set)):
                items = list(val)
                # Begleit-Flag :name_empty automatisch binden, falls im SQL referenziert
                # (empty-sicheres Muster »(:name_empty = 1 OR col IN (:name))« – so muss
                # der Aufrufer nur die Liste liefern, nicht zusätzlich das Flag).
                empty_key = f"{name}_empty"
                if empty_key in referenced and empty_key not in run_params:
                    params[empty_key] = 1 if not items else 0
                pattern = _re.compile(r":" + _re.escape(name) + r"(?![A-Za-z0-9_])")
                if not items:
                    sql = pattern.sub("NULL", sql)
                else:
                    placeholders = []
                    for i, item in enumerate(items):
                        pname = f"{name}__{i}"
                        params[pname] = item
                        placeholders.append(":" + pname)
                    repl = ", ".join(placeholders)
                    sql = pattern.sub(lambda _m: repl, sql)
            else:
                params[name] = int(val) if name in ("year", "month") else _coerce_param(val)
        elif name == "year":
            params[name] = default_year
        elif name == "month":
            params[name] = default_month
    return sql, params


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
        # Pool-Härtung gegen flatterhafte Remote-Server (z.B. SQL Express hinter
        # DSL/NAT-DDNS): tote Leerlauf-Verbindungen erkennen & transparent neu
        # aufbauen, Verbindungen vor dem NAT-Idle-Timeout recyceln und dem
        # Login-Handshake über langsame Leitungen mehr Zeit geben. Ohne diese
        # Optionen liefert der Cache-Pool sporadisch tote Verbindungen aus →
        # sporadische Login-/Verbindungsfehler, die beim nächsten Versuch weg sind.
        db_type = getattr(conn_obj, "db_type", None)
        connect_args = {}
        if db_type == "mssql":
            connect_args = {"timeout": 10, "login_timeout": 10}
        elif db_type in ("mysql", "postgresql"):
            connect_args = {"connect_timeout": 10}
        engine = create_engine(
            get_engine_str(conn_obj),
            pool_pre_ping=True,
            pool_recycle=1800,
            connect_args=connect_args,
        )
        _sql_engine_cache[connection_id] = engine
        return engine
    finally:
        db.close()


# Fehler-Marker, die auf einen transienten Verbindungsaussetzer hindeuten (kein
# echter SQL-/Datenfehler): 08S01 = Communication link failure, 10060/0x274C =
# TCP-Timeout, 08001 = Verbindungsaufbau fehlgeschlagen, HYT00/HYT01 = Timeout
# expired. Bei diesen ist ein kurzer Retry sinnvoll – beim nächsten Versuch ist
# der Server über DSL/NAT/VPN oft wieder erreichbar.
_TRANSIENT_DB_MARKERS = (
    "08S01", "08001", "10060", "0x274C", "0x274c",
    "HYT00", "HYT01", "Communication link failure",
    "TCP Provider", "Login timeout", "server was not found",
)


def _is_transient_db_error(exc) -> bool:
    msg = str(exc)
    return any(m in msg for m in _TRANSIENT_DB_MARKERS)


def run_sql_with_retry(fn, *, retries: int = 2, delay: float = 0.8):
    """Führt fn() aus und wiederholt bei transienten Verbindungsfehlern (TCP-
    Timeout / Communication link failure) mit kurzer, ansteigender Pause. Echte
    SQL-/Datenfehler werden sofort weitergereicht. fn kapselt die eigentliche
    read_sql/execute-Operation und baut die Connection frisch aus dem Pool auf,
    damit der Retry nicht dieselbe tote Verbindung erwischt (pool_pre_ping)."""
    import time as _time
    last = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 – bewusst breit, danach gefiltert
            last = e
            if attempt < retries and _is_transient_db_error(e):
                _time.sleep(delay * (attempt + 1))
                continue
            raise
    raise last  # pragma: no cover – defensiv, Schleife raised bereits
