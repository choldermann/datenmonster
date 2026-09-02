"""
SQL-Hilfsfunktionen für das Mapping-System.
Engine-Cache, Parameter-Auflösung, Aggregation.
"""

_sql_engine_cache: dict = {}

import re as _re_mod
_ISO_DATE_RE = _re_mod.compile(r"^\d{4}-\d{2}-\d{2}$")
# Datum mit Uhrzeit, ISO-Schreibweise: Trennzeichen T oder Leerzeichen, Sekunden
# und Bruchteile freiwillig, Zeitzone (Z oder ±hh:mm) freiwillig.
_ISO_DT_RE = _re_mod.compile(
    r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)"
    r"(Z|[+-]\d{2}:?\d{2})?$")
# Deutsche Schreibweise, mit oder ohne Uhrzeit: 31.07.2026, 31.07.2026 14:30
_DE_DATE_RE = _re_mod.compile(
    r"^(\d{1,2})\.(\d{1,2})\.(\d{4})(?:[ T](\d{2}:\d{2}(?::\d{2})?))?$")


def _coerce_param(val):
    """Wandelt Datumsangaben in echte date/datetime-Objekte um, damit der Treiber
    sie als DATE/DATETIME bindet statt als nvarchar.

    Warum das sein muss: bleibt der Wert Text, legt MS SQL Server ihn unter
    deutscher Spracheinstellung als »yyyy-dd-mm« aus. »2026-07-31« wird dann zu
    »Monat 31« → Fehler 242 (22007). Tückischer ist der Fall darunter: bei einem
    Tag ≤ 12 gibt es keinen Fehler, sondern stumm einen anderen Zeitraum —
    »2026-09-02« als von-Wert liest sich als 2. Februar, und die Auswertung zeigt
    eine plausible, aber falsche Zahl (gemessen: 464,27 € statt 3.526,72 €).

    Erkannt werden YYYY-MM-DD, ISO mit Uhrzeit (T oder Leerzeichen) und die
    deutsche Schreibweise TT.MM.JJJJ, jeweils mit oder ohne Uhrzeit. Eine
    Zeitzonenangabe wird abgeschnitten, nicht umgerechnet: die Zielspalten sind
    zeitzonenlos, und gemeint ist die Wanduhrzeit — »2026-01-01T00:00:00+01:00«
    soll der 1. Januar bleiben und nicht zum 31. Dezember werden. Alles andere
    bleibt unverändert."""
    if not isinstance(val, str):
        return val
    import datetime
    if _ISO_DATE_RE.match(val):
        try:
            return datetime.date.fromisoformat(val)
        except ValueError:
            return val
    m = _ISO_DT_RE.match(val)
    if m:
        try:
            return datetime.datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}")
        except ValueError:
            return val
    m = _DE_DATE_RE.match(val)
    if m:
        tag, monat, jahr, zeit = m.groups()
        try:
            d = datetime.date(int(jahr), int(monat), int(tag))
            if not zeit:
                return d
            std = [int(x) for x in zeit.split(":")]
            return datetime.datetime(d.year, d.month, d.day, *std)
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


def _apply_row_cap(sql: str, cap: int, dialect: str = "mssql") -> str:
    """Setzt/ersetzt im ÄUSSEREN (Ergebnis-)SELECT ein Zeilenlimit auf `cap`.
    Der äußere SELECT ist der LETZTE SELECT auf Klammer-Tiefe 0 – das deckt sowohl
    einfache Queries als auch CTEs (`WITH … SELECT …`) ab. Subquery-/CTE-INTERNE
    TOPs bleiben unangetastet, damit Korrelations-Subqueries (z.B. TOP 1) nicht
    kaputtgehen. Bei irgendeiner Unsicherheit wird das SQL UNVERÄNDERT
    zurückgegeben (Fail-safe – lieber altes Limit als kaputtes SQL).

    Dient dazu, die hartkodierten `TOP N` der Cockpit-Listen-Tabellen zur Laufzeit
    auf eine höhere, aufrufer-gesteuerte Obergrenze anzuheben, ohne die gespeicherten
    Mapping-SQLs zu editieren (wirkt so auch für künftige Template-Installationen)."""
    import re as _re_cap
    if not sql or not isinstance(cap, int) or cap <= 0:
        return sql
    try:
        # Klammer-Tiefe je Zeichen (Cockpit-SQLs enthalten keine Klammern in String-
        # Literalen, daher ist eine einfache Zählung ausreichend und robust).
        depth = 0
        depths = []
        for ch in sql:
            if ch == "(":
                depth += 1
            depths.append(depth)
            if ch == ")":
                depth -= 1
        sel_positions = [m.start() for m in _re_cap.finditer(r"(?is)\bselect\b", sql)
                         if depths[m.start()] == 0]
        if not sel_positions:
            return sql
        sel = sel_positions[-1]  # äußerer Ergebnis-SELECT
        from_positions = [m.start() for m in _re_cap.finditer(r"(?is)\bfrom\b", sql)
                          if depths[m.start()] == 0 and m.start() > sel]
        header_end = from_positions[0] if from_positions else len(sql)
        header = sql[sel:header_end]

        if dialect == "mssql":
            new_header, n = _re_cap.subn(
                r"(?is)^(\s*select\s+(distinct\s+)?)top\s*\(?\s*\d+\s*\)?\s+",
                lambda m: f"{m.group(1)}TOP ({cap}) ", header, count=1)
            if n == 0:
                new_header, n = _re_cap.subn(
                    r"(?is)^(\s*select\s+(distinct\s+)?)",
                    lambda m: f"{m.group(1)}TOP ({cap}) ", header, count=1)
            if n == 0:
                return sql
            return sql[:sel] + new_header + sql[header_end:]
        else:
            if _re_cap.search(r"(?is)\blimit\s+\d+", sql):
                return sql
            return sql.rstrip().rstrip(";") + f"\nLIMIT {cap}"
    except Exception:
        return sql


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


def invalidate_sql_engine(connection_id: int) -> bool:
    """Entfernt die gecachte Engine einer DB-Verbindung und gibt ihren Pool frei.
    Muss nach Update/Delete einer Verbindung aufgerufen werden, sonst nutzt das
    laufende Backend weiter die alte Engine (alte Credentials/Host) bis zum
    Neustart. Gibt True zurück, wenn ein Eintrag entfernt wurde."""
    global _sql_engine_cache
    engine = _sql_engine_cache.pop(connection_id, None)
    if engine is None:
        return False
    try:
        engine.dispose()
    except Exception:
        pass
    return True


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
