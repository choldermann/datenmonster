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
    id: Optional[int] = None
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
        "password": "••••••••" if c.password else "",
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
    require_editor(data.project_id, user, db)
    d = data.model_dump()
    if d.get("password"):
        d["password"] = encrypt_credential(d["password"])
    conn = DbConnection(**d)
    db.add(conn); db.commit(); db.refresh(conn)
    return conn_out(conn)


@router.post("/test")
def test_conn_form(data: ConnectionTest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Auth erforderlich – verhindert anonymes Port-Scanning / Credential-Testing
    d = {k: v for k, v in data.model_dump().items() if k != "name"}
    # Maskiertes Passwort: echtes PW aus DB laden wenn id vorhanden
    if d.get("password") == "••••••••" and getattr(data, "id", None):
        existing = db.query(DbConnection).filter(DbConnection.id == data.id).first()
        if existing and existing.password:
            d["password"] = decrypt_credential(existing.password)
    conn = DbConnection(**d, name=data.name or "test")
    return test_connection(conn)


@router.get("/{conn_id}/test")
def test_conn_by_id(conn_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conn = _require_read_conn(conn_id, user, db)
    return test_connection(conn)


@router.get("/{conn_id}/tables")
def list_tables(conn_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conn = _require_read_conn(conn_id, user, db)
    try:
        return {"tables": get_tables(conn)}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/{conn_id}/tables-only")
def list_tables_only(conn_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Gibt Tabellen und Views zurück – für Whitelist-Auswahl im DatabaseAnalyzer."""
    conn = _require_read_conn(conn_id, user, db)
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
                        tables.append(f"{schema}.{t}")
                except Exception:
                    pass
                try:
                    for v in inspector.get_view_names(schema=schema):
                        tables.append(f"{schema}.{v}")
                except Exception:
                    pass
        else:
            try:
                tables += inspector.get_table_names()
            except Exception as e:
                import logging as _l; _l.getLogger("datenmonster").warning(f"Tabellen abrufen fehlgeschlagen: {e}")
            try:
                tables += inspector.get_view_names()
            except Exception:
                pass
        return {"tables": sorted(set(tables))}
    except Exception as e:
        raise HTTPException(400, str(e)[:500])


@router.get("/{conn_id}/columns")
def list_columns(conn_id: int, table: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conn = _require_read_conn(conn_id, user, db)
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


@router.get("/{conn_id}/analyze")
def analyze_schema(
    conn_id: int,
    include_row_counts: bool = False,
    table_limit: int = 25,
    schema_filter: Optional[str] = None,
    table_filter: Optional[str] = None,
    include_related: bool = False,
    implicit_limit: int = 200,
    timeout: int = 30,
    start_table: Optional[str] = None,
    depth: int = 2,
    selected_tables: Optional[str] = None,
    path_from: Optional[str] = None,
    path_to: Optional[str] = None,
    path_via: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Analysiert das Schema einer Datenbankverbindung.
    - table_limit: max. Anzahl Tabellen (default 25)
    - schema_filter: nur ein bestimmtes Schema analysieren (z.B. 'dbo')
    - table_filter: nur Tabellen laden deren Name diesen String enthält
    - include_related: auch per FK verknüpfte Tabellen einbeziehen
    - implicit_limit: max. implizite Beziehungen (default 200)
    - timeout: max. Sekunden pro Tabellen-Analyse (default 30)
    - start_table: Starttabelle für FK-Traversierung (z.B. 'dbo.tRechnung' oder 'tRechnung')
    - depth: Traversierungstiefe ab Starttabelle (1-3, default 2)
    - selected_tables: Kommagetrennte Whitelist von Tabellen-Keys – lädt nur diese exakt
    - path_from / path_to: Pfadfinder – findet kürzesten Weg zwischen zwei Tabellen
    """
    conn = _require_read_conn(conn_id, user, db)
    try:
        from sqlalchemy import create_engine, inspect, text
        from app.services.db_service import get_engine_str
        import signal, threading
        engine = create_engine(get_engine_str(conn), connect_args={"timeout": timeout} if conn.db_type != "mssql" else {})
        inspector = inspect(engine)

        SKIP_SCHEMAS = {"sys", "INFORMATION_SCHEMA", "guest", "db_owner",
                        "db_accessadmin", "db_securityadmin", "db_ddladmin",
                        "db_backupoperator", "db_datareader", "db_datawriter",
                        "db_denydatareader", "db_denydatawriter"}

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

        # ── Alle Tabellen ermitteln ───────────────────────────────────────────
        all_table_names = []
        available_schemas = []
        if conn.db_type == "mssql":
            schemas = [s for s in inspector.get_schema_names() if s not in SKIP_SCHEMAS]
            available_schemas = schemas
            if schema_filter:
                schemas = [s for s in schemas if s == schema_filter]
            for schema in schemas:
                try:
                    for t in inspector.get_table_names(schema=schema):
                        all_table_names.append((schema, t, f"{schema}.{t}"))
                except Exception:
                    pass
                try:
                    for v in inspector.get_view_names(schema=schema):
                        all_table_names.append((schema, v, f"{schema}.{v}"))
                except Exception:
                    pass
        else:
            available_schemas = ["public"]
            for t in inspector.get_table_names():
                all_table_names.append((None, t, t))
            try:
                for v in inspector.get_view_names():
                    all_table_names.append((None, v, v))
            except Exception:
                pass

        total_tables = len(all_table_names)

        # ── Pfadfinder: kürzester Weg zwischen zwei Tabellen ───────────────────
        if path_from and path_to and path_from.strip() and path_to.strip():

            # Lookups für schnellen Zugriff
            # tname_lower → canonical key  (z.B. "tbestellung" → "dbo.tBestellung")
            tname_to_key = {}
            for e in all_table_names:
                tname_to_key[e[1].lower()] = e[2]   # nur tabellenname
                tname_to_key[e[2].lower()] = e[2]   # schema.tabellenname
            # canonical key → entry tuple
            key_to_entry = {e[2]: e for e in all_table_names}

            # Tabelle finden (exakt oder partial, case-insensitiv)
            def find_table(name):
                name_l = name.strip().lower()
                resolved = tname_to_key.get(name_l)
                if resolved:
                    return resolved
                for e in all_table_names:
                    if name_l in e[1].lower():
                        return e[2]
                return None

            pf_from = find_table(path_from)
            pf_to   = find_table(path_to)

            # ── Lazy BFS mit Rückwärts-Kanten ────────────────────────────────
            import re as _re
            _reverse_edges = {}

            def _get_neighbors(table_key):
                entry = key_to_entry.get(table_key)
                if not entry:
                    return set()
                neighbors = set()
                s, tn, _ = entry
                # Echte FKs
                try:
                    for fk in inspector.get_foreign_keys(tn, schema=s):
                        ref_schema = fk.get("referred_schema") or s or ""
                        ref_table  = fk.get("referred_table", "")
                        ref_key    = f"{ref_schema}.{ref_table}" if ref_schema else ref_table
                        resolved   = tname_to_key.get(ref_key.lower())
                        if resolved and resolved != table_key:
                            neighbors.add(resolved)
                            _reverse_edges.setdefault(resolved, set()).add(table_key)
                except Exception:
                    pass
                # k-Feld Konvention via Spalten
                try:
                    for c in inspector.get_columns(tn, schema=s):
                        cn = c["name"]
                        if "_" in cn:
                            resolved = tname_to_key.get(cn.split("_", 1)[0].lower())
                            if resolved and resolved != table_key:
                                neighbors.add(resolved)
                                _reverse_edges.setdefault(resolved, set()).add(table_key)
                        if _re.match(r'^k[A-Z]', cn):
                            resolved = tname_to_key.get(("t" + cn[1:]).lower())
                            if resolved and resolved != table_key:
                                neighbors.add(resolved)
                                _reverse_edges.setdefault(resolved, set()).add(table_key)
                except Exception:
                    pass
                return neighbors

            _nb_cache = {}
            def get_neighbors(table_key):
                if table_key not in _nb_cache:
                    _nb_cache[table_key] = _get_neighbors(table_key)
                return _nb_cache[table_key] | _reverse_edges.get(table_key, set())

            # Zwischenstationen auflösen
            via_keys = []
            if path_via and path_via.strip():
                for v in path_via.split(","):
                    v = v.strip()
                    if v:
                        rv = find_table(v)
                        if rv:
                            via_keys.append(rv)

            # Pre-scan: Ziel zuerst → via rückwärts → Start
            # Rückwärts-Kanten müssen bekannt sein bevor BFS startet
            for _wp in (([pf_to] if pf_to else []) + list(reversed(via_keys)) + ([pf_from] if pf_from else [])):
                get_neighbors(_wp)


            def bidi_bfs(start, end, max_depth=6):
                """Bidirektionaler BFS. Gibt Pfad oder None zurück."""
                if start == end:
                    return [start]
                front_a = {start: [start]}
                front_b = {end:   [end]}
                visited_a = {start}
                visited_b = {end}
                for _ in range(max_depth):
                    new_a = {}
                    for node, path in front_a.items():
                        for nb in get_neighbors(node):
                            if nb in visited_b:
                                return path + list(reversed(front_b[nb]))
                            if nb not in visited_a:
                                visited_a.add(nb)
                                new_a[nb] = path + [nb]
                    front_a = new_a
                    new_b = {}
                    for node, path in front_b.items():
                        for nb in get_neighbors(node):
                            if nb in visited_a:
                                pa = front_a.get(nb, [nb])
                                return pa + list(reversed(path))
                            if nb not in visited_b:
                                visited_b.add(nb)
                                new_b[nb] = path + [nb]
                    front_b = new_b
                    if not front_a and not front_b:
                        break
                return None

            if pf_from and pf_to and pf_from != pf_to:
                # Segment-BFS: jeden Abschnitt zwischen Waypoints separat lösen
                waypoints = [pf_from] + via_keys + [pf_to]
                full_path = []
                all_found = True
                for i in range(len(waypoints) - 1):
                    seg = bidi_bfs(waypoints[i], waypoints[i + 1])
                    if seg is None:
                        all_found = False
                        break
                    full_path = full_path + (seg if not full_path else seg[1:])

                if all_found and full_path:
                    seen = set(); deduped = []
                    for k in full_path:
                        if k not in seen:
                            seen.add(k); deduped.append(k)
                    path_keys = set(deduped)
                    table_names = [e for e in all_table_names if e[2] in path_keys]
                    order = {k: i for i, k in enumerate(deduped)}
                    table_names.sort(key=lambda e: order.get(e[2], 99))
                else:
                    # Kein vollständiger Pfad → alle Waypoints anzeigen
                    fallback = {pf_from, pf_to} | set(via_keys)
                    table_names = [e for e in all_table_names if e[2] in fallback]
            else:
                table_names = [e for e in all_table_names if e[2] in {pf_from, pf_to} if e[2]]


        # ── Whitelist: exakt gewählte Tabellen ───────────────────────────────────
        elif selected_tables and selected_tables.strip():
            requested = [t.strip() for t in selected_tables.split(",") if t.strip()]
            # Case-insensitive Match auf table_key oder tname
            selected_set = set(t.lower() for t in requested)
            table_names = [
                e for e in all_table_names
                if e[2].lower() in selected_set or e[1].lower() in selected_set
            ]

        # ── Starttabelle: FK-Graphen-Traversierung ────────────────────────────
        elif start_table and start_table.strip():
            st = start_table.strip()

            # Starttabelle im all_table_names-Index finden (case-insensitive, mit/ohne Schema)
            start_entry = None
            for entry in all_table_names:
                schema_s, tname_s, key_s = entry
                # Exakter Match auf key (z.B. "dbo.tRechnung") oder nur Tabellenname
                if key_s.lower() == st.lower() or tname_s.lower() == st.lower():
                    start_entry = entry
                    break
                # Partial match: "Rechnung" findet "dbo.tRechnung"
                if st.lower() in tname_s.lower():
                    start_entry = entry
                    # Kein break – weiter suchen für exakteren Match

            if start_entry:
                # FK-Graph aufbauen: { table_key: set(verbundene table_keys) }
                # Vorwärts: diese Tabelle hat FK → andere Tabelle
                # Rückwärts: andere Tabelle hat FK → diese Tabelle
                fk_graph = {}  # table_key → set of connected table_keys

                for schema_g, tname_g, key_g in all_table_names:
                    try:
                        fks = inspector.get_foreign_keys(tname_g, schema=schema_g)
                        for fk in fks:
                            ref_schema = fk.get("referred_schema") or schema_g or ""
                            ref_table = fk.get("referred_table", "")
                            ref_key = f"{ref_schema}.{ref_table}" if ref_schema else ref_table
                            # Vorwärts: key_g → ref_key
                            fk_graph.setdefault(key_g, set()).add(ref_key)
                            # Rückwärts: ref_key → key_g
                            fk_graph.setdefault(ref_key, set()).add(key_g)
                    except Exception:
                        pass

                # BFS ab Starttabelle bis zur gewünschten Tiefe
                start_key = start_entry[2]
                visited = {start_key}
                frontier = {start_key}
                for _ in range(max(1, min(depth, 5))):
                    next_frontier = set()
                    for k in frontier:
                        for neighbor in fk_graph.get(k, set()):
                            if neighbor not in visited:
                                visited.add(neighbor)
                                next_frontier.add(neighbor)
                    frontier = next_frontier
                    if not frontier:
                        break

                # Nur Tabellen die im visited-Set sind – Starttabelle immer an erster Stelle
                table_names = [e for e in all_table_names if e[2] in visited]
                # Starttabelle nach vorne sortieren
                table_names.sort(key=lambda e: (0 if e[2] == start_key else 1, e[2]))
            else:
                # Starttabelle nicht gefunden → normaler Lauf mit Hinweis
                table_names = all_table_names

        # ── Tabellenfilter (nur wenn kein anderer Modus aktiv) ─────────────────
        elif not selected_tables and table_filter and table_filter.strip():
            tf = table_filter.strip().lower()
            matched = [t for t in all_table_names if tf in t[2].lower()]

            if include_related and matched:
                matched_keys = {t[2] for t in matched}
                related_keys = set(matched_keys)
                try:
                    for schema, tname, table_key in matched:
                        try:
                            fks = inspector.get_foreign_keys(tname, schema=schema)
                            for fk in fks:
                                ref_schema = fk.get("referred_schema") or schema or ""
                                ref_table = fk.get("referred_table", "")
                                ref_key = f"{ref_schema}.{ref_table}" if ref_schema else ref_table
                                related_keys.add(ref_key)
                        except Exception:
                            pass
                    # Auch Tabellen die auf matched Tabellen zeigen
                    for other_schema, other_tname, other_key in all_table_names:
                        if other_key in related_keys:
                            continue
                        try:
                            other_fks = inspector.get_foreign_keys(other_tname, schema=other_schema)
                            for fk in other_fks:
                                ref_schema = fk.get("referred_schema") or other_schema or ""
                                ref_table = fk.get("referred_table", "")
                                ref_key = f"{ref_schema}.{ref_table}" if ref_schema else ref_table
                                if ref_key in matched_keys:
                                    related_keys.add(other_key)
                        except Exception:
                            pass
                except Exception:
                    pass
                table_names = [t for t in all_table_names if t[2] in related_keys]
            else:
                table_names = matched
        elif not selected_tables:
            table_names = all_table_names

        # ── Max. Tabellen (harter Stopp) ──────────────────────────────────────
        truncated = len(table_names) > table_limit
        table_names = table_names[:table_limit]

        # ── Pro Tabelle: Spalten, PKs, FKs ───────────────────────────────────
        tables = []
        field_index = {}

        for schema, tname, table_key in table_names:
            try:
                cols = inspector.get_columns(tname, schema=schema)
                pk_info = inspector.get_pk_constraint(tname, schema=schema)
                pk_cols = set(pk_info.get("constrained_columns", []))

                # Foreign Keys
                fks = []
                try:
                    for fk in inspector.get_foreign_keys(tname, schema=schema):
                        for col, ref_col in zip(
                            fk.get("constrained_columns", []),
                            fk.get("referred_columns", [])
                        ):
                            ref_schema = fk.get("referred_schema") or schema or ""
                            ref_table = fk.get("referred_table", "")
                            ref_key = f"{ref_schema}.{ref_table}" if ref_schema else ref_table
                            fks.append({
                                "from_col": col,
                                "to_table": ref_key,
                                "to_col": ref_col,
                            })
                except Exception:
                    pass

                # Zeilenanzahl (optional)
                row_count = None
                if include_row_counts:
                    try:
                        with engine.connect() as c:
                            q = f"SELECT COUNT(*) FROM [{tname}]" if conn.db_type == "mssql" else f"SELECT COUNT(*) FROM `{tname}`"
                            row_count = c.execute(text(q)).scalar()
                    except Exception:
                        pass

                columns = []
                for c in cols:
                    col_name = c["name"]
                    columns.append({
                        "name": col_name,
                        "type": _simple_type(c["type"]),
                        "raw": str(c["type"]),
                        "is_primary": col_name in pk_cols,
                        "nullable": c.get("nullable", True),
                    })
                    if col_name not in field_index:
                        field_index[col_name] = []
                    field_index[col_name].append(table_key)

                tables.append({
                    "key": table_key,
                    "name": tname,
                    "schema": schema or "dbo",
                    "columns": columns,
                    "foreign_keys": fks,
                    "row_count": row_count,
                    "pk_columns": list(pk_cols),
                })
            except Exception as e:
                tables.append({
                    "key": table_key,
                    "name": tname,
                    "schema": schema or "dbo",
                    "columns": [],
                    "foreign_keys": [],
                    "row_count": None,
                    "pk_columns": [],
                    "error": str(e)[:200],
                })

        # ── Beziehungen sammeln ───────────────────────────────────────────────
        explicit_rels = []
        for t in tables:
            for fk in t["foreign_keys"]:
                explicit_rels.append({
                    "from_table": t["key"],
                    "from_col": fk["from_col"],
                    "to_table": fk["to_table"],
                    "to_col": fk["to_col"],
                    "type": "foreign_key",
                })

        import re
        implicit_rels = []
        seen_pairs = set()
        key_pattern = re.compile(r'^(k[A-Z]|.*[Ii]d$|.*_id$|.*ID$)')
        k_prefix_pattern = re.compile(r'^k[A-Z]')
        for field_name, table_keys in field_index.items():
            if len(table_keys) < 2:
                continue
            if not key_pattern.match(field_name):
                continue
            is_pk_somewhere = any(
                field_name in next((t["pk_columns"] for t in tables if t["key"] == tk), [])
                for tk in table_keys
            )
            # k-Prefix Felder auch ohne PK erlauben (Views haben keine PKs) → Typ "inferred"
            is_k_prefix = bool(k_prefix_pattern.match(field_name))
            if not is_pk_somewhere and not is_k_prefix:
                continue
            rel_type = "implicit" if is_pk_somewhere else "inferred"
            for i, tk1 in enumerate(table_keys):
                for tk2 in table_keys[i+1:]:
                    pair = tuple(sorted([tk1, tk2, field_name]))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    already_explicit = any(
                        (r["from_table"] == tk1 and r["to_table"] == tk2) or
                        (r["from_table"] == tk2 and r["to_table"] == tk1)
                        for r in explicit_rels
                    )
                    if not already_explicit:
                        implicit_rels.append({
                            "from_table": tk1,
                            "from_col": field_name,
                            "to_table": tk2,
                            "to_col": field_name,
                            "type": rel_type,
                        })

        implicit_rels = implicit_rels[:implicit_limit]

        # ── JTL-Namenskonvention: tTabelle_kFeld → tTabelle.kFeld ────────────
        # Felder wie "tRechnung_kRechnung" in Tabelle A deuten auf tRechnung.kRechnung
        jtl_rels = []
        seen_jtl = set()
        # Lookup: tabellenname (lower) → table_key
        tname_lookup = {t["name"].lower(): t["key"] for t in tables}
        pk_lookup = {t["key"]: set(t["pk_columns"]) for t in tables}

        for t in tables:
            for col in t["columns"]:
                col_name = col["name"]
                # Pattern: tXxx_kYyy oder tXxx_nYyy etc. – enthält Unterstrich nach erstem Wort
                if "_" not in col_name:
                    continue
                parts = col_name.split("_", 1)
                ref_tname = parts[0].lower()   # z.B. "trechnung"
                ref_col   = parts[1]            # z.B. "kRechnung"
                # Ziel-Tabelle muss in unserer Tabellenliste vorhanden sein
                if ref_tname not in tname_lookup:
                    continue
                ref_key = tname_lookup[ref_tname]
                # Ziel-Spalte muss in Ziel-Tabelle als PK vorhanden sein
                if ref_col not in pk_lookup.get(ref_key, set()):
                    continue
                # Nicht auf sich selbst verweisen
                if ref_key == t["key"]:
                    continue
                # Nicht doppelt mit expliziten FKs
                already = any(
                    (r["from_table"] == t["key"] and r["to_table"] == ref_key) or
                    (r["from_table"] == ref_key and r["to_table"] == t["key"])
                    for r in explicit_rels
                )
                if already:
                    continue
                pair = tuple(sorted([t["key"], ref_key, col_name]))
                if pair in seen_jtl:
                    continue
                seen_jtl.add(pair)
                jtl_rels.append({
                    "from_table": t["key"],
                    "from_col": col_name,
                    "to_table": ref_key,
                    "to_col": ref_col,
                    "type": "inferred",
                })

        # Starttabelle in Response mitgeben (für Frontend-Info)
        start_table_key = None
        if start_table and start_table.strip() and tables:
            start_table_key = tables[0]["key"]  # Starttabelle ist immer erste

        return {
            "connection_id": conn_id,
            "connection_name": conn.name,
            "db_type": conn.db_type,
            "table_count": len(tables),
            "total_tables": total_tables,
            "truncated": truncated,
            "truncated_msg": f"Nur {table_limit} von {total_tables} Tabellen geladen. Schema-Filter oder höheres Limit verwenden." if truncated else None,
            "available_schemas": available_schemas,
            "tables": tables,
            "relationships": explicit_rels + implicit_rels + jtl_rels,
            "explicit_count": len(explicit_rels),
            "implicit_count": len([r for r in implicit_rels if r["type"] == "implicit"]),
            "inferred_count": len([r for r in implicit_rels if r["type"] == "inferred"]) + len(jtl_rels),
            "start_table_key": start_table_key,
        }

    except Exception as e:
        raise HTTPException(400, str(e)[:500])


@router.put("/{conn_id}")
@router.patch("/{conn_id}")
def update_connection(conn_id: int, data: ConnectionCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conn = db.query(DbConnection).filter(DbConnection.id == conn_id).first()
    if not conn:
        raise HTTPException(404, "Verbindung nicht gefunden")
    require_editor(conn.project_id, user, db)
    for k, v in data.model_dump().items():
        if k == "password":
            if v and v != "••••••••":
                setattr(conn, k, encrypt_credential(v))
        else:
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
