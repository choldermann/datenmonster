"""
AI Context Builder — assembles relevant context from Datenmonster's database
before forwarding a request to the AI service.

Architecture: Frontend → Backend Endpoint → AIContextBuilder → AIService → LLM
The builder decides what context is needed, loads it from DB, and returns
a ready-to-use (system_prompt, context_text) tuple.
"""

import re
import time
import logging
from sqlalchemy.orm import Session
from typing import Optional

log = logging.getLogger("datenmonster")

# ── In-memory schema cache (per connection_id, 5-min TTL) ────────────────────

_schema_cache: dict[int, dict] = {}
_SCHEMA_TTL = 300  # seconds


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_tables_from_sql(sql: str) -> list[str]:
    """Rough extraction of table/view names referenced in a SQL query."""
    pattern = re.compile(
        r'\b(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+\[?([a-zA-Z0-9_]+)\]?\.?\[?([a-zA-Z0-9_]*)\]?',
        re.IGNORECASE,
    )
    tables = []
    for m in pattern.finditer(sql):
        schema_part, table_part = m.group(1), m.group(2)
        if table_part:
            tables.append(f"{schema_part}.{table_part}")
        elif schema_part:
            tables.append(schema_part)
    return list(dict.fromkeys(tables))  # deduplicate, preserve order


def _load_schema_from_connection(conn) -> str:
    """
    Loads tables, columns, PKs, and FKs from a DB connection via SQLAlchemy
    inspector. Returns a compact text representation for the LLM prompt.
    Results are cached per connection_id for 5 minutes.
    """
    conn_id = conn.id
    now = time.time()
    if conn_id in _schema_cache and now - _schema_cache[conn_id]["ts"] < _SCHEMA_TTL:
        return _schema_cache[conn_id]["text"]

    try:
        from sqlalchemy import create_engine, inspect
        from app.services.db_service import get_engine_str

        engine = create_engine(get_engine_str(conn))
        inspector = inspect(engine)
        db_type = conn.db_type

        SKIP_SCHEMAS = {"sys", "INFORMATION_SCHEMA", "guest", "db_owner",
                        "db_accessadmin", "db_securityadmin", "db_ddladmin",
                        "db_backupoperator", "db_datareader", "db_datawriter",
                        "db_denydatareader", "db_denydatawriter"}

        if db_type == "mssql":
            try:
                schemas = [s for s in inspector.get_schema_names() if s not in SKIP_SCHEMAS]
            except Exception:
                schemas = ["dbo"]
            table_pairs = []
            for schema in schemas:
                try:
                    for t in inspector.get_table_names(schema=schema):
                        table_pairs.append((schema, t))
                except Exception:
                    pass
                try:
                    for v in inspector.get_view_names(schema=schema):
                        table_pairs.append((schema, v))
                except Exception:
                    pass
        else:
            schema = None
            table_pairs = []
            try:
                for t in inspector.get_table_names():
                    table_pairs.append((schema, t))
            except Exception:
                pass
            try:
                for v in inspector.get_view_names():
                    table_pairs.append((schema, v))
            except Exception:
                pass

        lines = [f"Datenbank: {conn.name} ({db_type}), Datenbank: {conn.database}"]

        for schema, tname in table_pairs[:80]:  # cap at 80 tables to control prompt size
            full = f"{schema}.{tname}" if schema else tname
            try:
                cols = inspector.get_columns(tname, schema=schema)
            except Exception:
                continue
            try:
                pk_info = inspector.get_pk_constraint(tname, schema=schema)
                pk_cols = set(pk_info.get("constrained_columns", []))
            except Exception:
                pk_cols = set()
            try:
                fks = inspector.get_foreign_keys(tname, schema=schema)
            except Exception:
                fks = []

            col_parts = []
            for c in cols:
                col_name = c["name"]
                col_type = str(c["type"]).split("(")[0]
                flags = []
                if col_name in pk_cols:
                    flags.append("PK")
                col_parts.append(f"  {col_name} {col_type}{'  [' + ','.join(flags) + ']' if flags else ''}")

            fk_parts = []
            for fk in fks:
                ref_table = fk.get("referred_table", "?")
                ref_schema = fk.get("referred_schema")
                ref_full = f"{ref_schema}.{ref_table}" if ref_schema else ref_table
                for local_col, ref_col in zip(fk.get("constrained_columns", []), fk.get("referred_columns", [])):
                    fk_parts.append(f"  FK: {local_col} → {ref_full}.{ref_col}")

            lines.append(f"\nTabelle {full}:")
            lines.extend(col_parts)
            lines.extend(fk_parts)

        text = "\n".join(lines)
        _schema_cache[conn_id] = {"ts": now, "text": text}
        return text

    except Exception as e:
        log.warning(f"AI Context Builder: Schema-Laden fehlgeschlagen für conn {conn.id}: {e}")
        return f"Schema konnte nicht geladen werden: {e}"


def _schema_for_sql(conn, sql: str) -> str:
    """
    Returns schema text, but filtered to tables mentioned in the SQL query.
    Falls back to full schema if no tables detected (e.g. for generate mode).
    """
    full_schema = _load_schema_from_connection(conn)
    mentioned = _extract_tables_from_sql(sql)
    if not mentioned:
        return full_schema

    # Keep only table blocks that mention one of the referenced table names
    lines = full_schema.split("\n")
    result_lines = [lines[0]]  # keep DB header
    include = False
    for line in lines[1:]:
        if line.startswith("\nTabelle ") or line.startswith("Tabelle "):
            tname = line.replace("\nTabelle ", "").replace("Tabelle ", "").strip().rstrip(":")
            include = any(tname.lower().endswith(m.lower()) or m.lower() in tname.lower() for m in mentioned)
        if include:
            result_lines.append(line)

    # If filtering removed everything, return full schema
    return "\n".join(result_lines) if len(result_lines) > 1 else full_schema


def _get_mapping_fields(db: Session, mapping_id: int) -> list[str]:
    """Collect all output field names available in a mapping (from all node types)."""
    from app.models.mapping import Mapping
    from app.models.dataset import Dataset

    mapping = db.query(Mapping).filter(Mapping.id == mapping_id).first()
    if not mapping:
        return []

    fields = []

    # Dataset columns from canvas_nodes
    for cn in (mapping.canvas_nodes or []):
        ds_id = cn.get("dataset_id")
        if ds_id:
            ds = db.query(Dataset).filter(Dataset.id == ds_id).first()
            if ds:
                for col in (ds.columns or []):
                    fields.append(col if isinstance(col, str) else col.get("name", ""))

    # Transform node output fields
    for n in (mapping.transform_nodes or []):
        if n.get("output_field"):
            fields.append(n["output_field"])

    # Constant node output fields
    for n in (mapping.constant_nodes or []):
        if n.get("output_field"):
            fields.append(n["output_field"])

    # SQL node output fields
    for n in (mapping.sql_nodes or []):
        if n.get("output_field"):
            fields.append(n["output_field"])
        for f in (n.get("output_fields") or []):
            if isinstance(f, str):
                fields.append(f)
            elif isinstance(f, dict):
                fields.append(f.get("name", ""))

    # Calc node output fields
    for n in (mapping.calc_nodes or []):
        if n.get("output_field"):
            fields.append(n["output_field"])

    # Python node output fields
    for n in (mapping.python_nodes or []):
        for f in (n.get("output_fields") or []):
            fields.append(f if isinstance(f, str) else f.get("name", ""))

    # Expression node output fields
    for n in (mapping.expr_nodes or []):
        for f in (n.get("output_fields") or []):
            fname = f if isinstance(f, str) else f.get("name", "")
            if fname:
                fields.append(fname)

    return [f for f in fields if f]


# ── Context profiles (system prompts) ────────────────────────────────────────

_SQL_SYSTEM = (
    "Du bist ein erfahrener SQL-Experte und hilfst in der ETL-Plattform Datenmonster. "
    "Du kennst MSSQL, MySQL und PostgreSQL. Halte SQL-Abfragen korrekt, lesbar und effizient. "
    "Wenn du SQL generierst, antworte NUR mit dem SQL-Code – kein Markdown, keine Erklärung. "
    "Wenn du SQL erklärst, antworte präzise auf Deutsch."
)

_PYTHON_SYSTEM = (
    "Du bist ein Python-Experte und hilfst in der ETL-Plattform Datenmonster beim Schreiben "
    "von Transformations-Skripten. Der Code wird pro Datensatz ausgeführt. "
    "Verfügbare Felder sind als lokale Variablen direkt nutzbar (z.B. `name`, `preis`). "
    "Ergebnisse müssen über `result['feldname'] = wert` zurückgegeben werden. "
    "Erlaubte Bibliotheken: re, math, datetime, decimal, unicodedata. "
    "Kein Import von externen Paketen. "
    "Antworte NUR mit Python-Code – kein Markdown, keine Erklärung."
)

_EXPR_SYSTEM = (
    "Du bist Experte für die Ausdrucks-Syntax der ETL-Plattform Datenmonster. "
    "Feldwerte werden mit {feldname} referenziert. "
    "Verfügbare Funktionen: upper(), lower(), trim(), concat(), replace(), substr(), len(), "
    "coalesce(), if_(bedingung, wert_wenn_wahr, wert_wenn_falsch), round(zahl, stellen), "
    "pad(text, laenge, zeichen), regex_match(text, muster), today(), now(), "
    "sqrt(), floor(), ceil(). "
    "Antworte NUR mit dem Ausdruck – kein Markdown, keine Erklärung."
)

_ERROR_SYSTEM = (
    "Du bist ein Fehleranalyse-Experte für die ETL-Plattform Datenmonster. "
    "Erkläre Fehlermeldungen verständlich auf Deutsch: nenne die wahrscheinliche Ursache "
    "und schlage 1-3 konkrete Lösungen vor. Sei präzise und praktisch."
)

_MAPPING_SUGGEST_SYSTEM = (
    "Du bist Experte für Daten-Mapping. Analysiere Quell- und Zielfelder und schlage "
    "sinnvolle Verknüpfungen vor. "
    'Antworte als JSON-Array: [{"source": "feldname", "target": "feldname", "confidence": 0.9, "reason": "kurze Begründung"}]. '
    "Nur wenn du dir sicher bist – keine Phantasie-Mappings."
)


# ── Public API ────────────────────────────────────────────────────────────────

class AIContextBuilder:
    def __init__(self, db: Session):
        self.db = db

    def _get_conn(self, connection_id: int):
        from app.models.dataset import DbConnection
        return self.db.query(DbConnection).filter(DbConnection.id == connection_id).first()

    # ── SQL ──────────────────────────────────────────────────────────────────

    def sql_explain_context(self, sql: str, connection_id: Optional[int]) -> tuple[str, str]:
        """Context for explaining an existing SQL query."""
        if connection_id:
            conn = self._get_conn(connection_id)
            schema_text = _schema_for_sql(conn, sql) if conn else ""
        else:
            schema_text = ""

        context = ""
        if schema_text:
            context = f"Datenbankschema:\n{schema_text}\n\n"
        context += f"SQL-Abfrage:\n{sql}"
        return _SQL_SYSTEM, context

    def sql_generate_context(self, description: str, connection_id: Optional[int]) -> tuple[str, str]:
        """Context for generating a new SQL query from a description."""
        if connection_id:
            conn = self._get_conn(connection_id)
            schema_text = _load_schema_from_connection(conn) if conn else ""
        else:
            schema_text = ""

        context = ""
        if schema_text:
            context = f"Datenbankschema (alle verfügbaren Tabellen/Views/Spalten):\n{schema_text}\n\n"
        context += f"Aufgabe: {description}"
        return _SQL_SYSTEM, context

    # ── Python ───────────────────────────────────────────────────────────────

    def python_generate_context(self, mapping_id: Optional[int], node_id: Optional[str], current_script: str = "") -> tuple[str, str]:
        """Context for generating Python code in a Python node."""
        fields = _get_mapping_fields(self.db, mapping_id) if mapping_id else []

        context_parts = []
        if fields:
            context_parts.append(f"Verfügbare Felder im Mapping:\n{', '.join(fields)}")
        if current_script and current_script.strip():
            context_parts.append(f"Vorhandener Code:\n{current_script}")

        return _PYTHON_SYSTEM, "\n\n".join(context_parts)

    # ── Expression ───────────────────────────────────────────────────────────

    def expression_generate_context(self, mapping_id: Optional[int], node_id: Optional[str], field_name: str = "") -> tuple[str, str]:
        """Context for generating an expression in an Expression node."""
        fields = _get_mapping_fields(self.db, mapping_id) if mapping_id else []

        context_parts = []
        if field_name:
            context_parts.append(f"Zielfeld: {field_name}")
        if fields:
            context_parts.append(f"Verfügbare Felder im Mapping:\n{', '.join(fields)}")

        return _EXPR_SYSTEM, "\n\n".join(context_parts)

    # ── Error explanation ────────────────────────────────────────────────────

    def error_explain_context(self, error: str, node_type: str = "", code: str = "", mapping_id: Optional[int] = None) -> tuple[str, str]:
        """Context for explaining a pipeline or node error."""
        context_parts = [f"Fehlermeldung:\n{error}"]

        if node_type:
            context_parts.append(f"Node-Typ: {node_type}")
        if code and code.strip():
            label = "SQL" if node_type == "sql" else "Python-Code" if node_type == "python" else "Ausdruck"
            context_parts.append(f"{label}:\n{code}")

        return _ERROR_SYSTEM, "\n\n".join(context_parts)

    # ── Mapping field suggestion ─────────────────────────────────────────────

    def mapping_suggest_context(self, mapping_id: int) -> tuple[str, str, list[str], list[str]]:
        """
        Context for suggesting field connections in a mapping.
        Returns (system, context_text, source_fields, target_fields).
        """
        import json
        from app.models.mapping import Mapping
        from app.models.dataset import Dataset

        mapping = self.db.query(Mapping).filter(Mapping.id == mapping_id).first()
        if not mapping:
            return _MAPPING_SUGGEST_SYSTEM, "", [], []

        source_fields = _get_mapping_fields(self.db, mapping_id)

        # Target fields: from mapping.fields (legacy) or from targets
        target_fields = []
        for f in (mapping.fields or []):
            if isinstance(f, dict) and f.get("target"):
                target_fields.append(f["target"])

        context = f"Mapping: {mapping.name}\n"
        if mapping.target_table:
            context += f"Zieltabelle: {mapping.target_table}\n"

        return _MAPPING_SUGGEST_SYSTEM, context, source_fields, target_fields
