"""
Mapping Execution Service
Lädt Datasets via Connector-Factory, wendet Joins + Transformer an.
"""
import re
import logging
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from app.connectors import get_connector


# ─── Sicherer Formel-Evaluator ────────────────────────────────────────────────
# Ersetzt eval() – erlaubt nur arithmetische Ausdrücke und Vergleiche.
# Kein Attributzugriff, keine Funktionsaufrufe, kein Import möglich.

import ast as _ast
import ast  # für Window-Formel-Validierung
import operator as _op

_SAFE_OPS_BIN = {
    _ast.Add:      _op.add,
    _ast.Sub:      _op.sub,
    _ast.Mult:     _op.mul,
    _ast.Div:      _op.truediv,
    _ast.FloorDiv: _op.floordiv,
    _ast.Mod:      _op.mod,
    _ast.Pow:      _op.pow,
}
_SAFE_OPS_UNARY = {_ast.USub: _op.neg, _ast.UAdd: _op.pos, _ast.Not: _op.not_}
_SAFE_OPS_CMP   = {_ast.Eq: _op.eq, _ast.NotEq: _op.ne,
                   _ast.Lt: _op.lt, _ast.LtE: _op.le,
                   _ast.Gt: _op.gt, _ast.GtE: _op.ge}


def _eval_node(node, g: dict):
    if isinstance(node, _ast.Expression):
        return _eval_node(node.body, g)
    if isinstance(node, _ast.Constant):
        if not isinstance(node.value, (int, float, bool, str, type(None))):
            raise ValueError(f"Unerlaubter Typ: {type(node.value)}")
        return node.value
    if isinstance(node, _ast.Name):
        name = node.id
        if name in g:
            return g[name]
        if name in ("True", "true"):   return True
        if name in ("False", "false"): return False
        if name in ("None", "null"):   return None
        raise ValueError(f"Unbekannte Variable: {name!r}")
    if isinstance(node, _ast.UnaryOp):
        fn = _SAFE_OPS_UNARY.get(type(node.op))
        if fn is None: raise ValueError(f"Unerlaubter Operator: {type(node.op).__name__}")
        return fn(_eval_node(node.operand, g))
    if isinstance(node, _ast.BinOp):
        fn = _SAFE_OPS_BIN.get(type(node.op))
        if fn is None: raise ValueError(f"Unerlaubter Operator: {type(node.op).__name__}")
        return fn(_eval_node(node.left, g), _eval_node(node.right, g))
    if isinstance(node, _ast.BoolOp):
        vals = [_eval_node(v, g) for v in node.values]
        if isinstance(node.op, _ast.And):
            r = vals[0]
            for v in vals[1:]: r = r and v
            return r
        if isinstance(node.op, _ast.Or):
            r = vals[0]
            for v in vals[1:]: r = r or v
            return r
        raise ValueError("Unbekannter Bool-Op")
    if isinstance(node, _ast.Compare):
        left = _eval_node(node.left, g)
        for op, comp in zip(node.ops, node.comparators):
            fn = _SAFE_OPS_CMP.get(type(op))
            if fn is None: raise ValueError(f"Unerlaubter Vergleich: {type(op).__name__}")
            right = _eval_node(comp, g)
            if not fn(left, right): return False
            left = right
        return True
    if isinstance(node, _ast.IfExp):
        return _eval_node(node.body, g) if _eval_node(node.test, g) else _eval_node(node.orelse, g)
    raise ValueError(f"Unerlaubter Ausdruckstyp: {type(node).__name__} – nur Arithmetik/Vergleiche erlaubt")


def safe_eval_expr(expr: str, extra_globals: dict = None) -> object:
    """
    Sicherer Ersatz für eval() bei Formeln und Bedingungen.
    Erlaubt: +, -, *, /, //, %, **, Vergleiche, and/or/not, Konstanten, Variablen.
    Blockt: Attributzugriff (.x), Funktionsaufrufe, Import, Klassen, Subscript.
    """
    try:
        tree = _ast.parse(expr.strip(), mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Syntaxfehler in Formel: {e}")
    return _eval_node(tree, extra_globals or {})


logger = logging.getLogger(__name__)


# ─── MappingContext ────────────────────────────────────────────────────────────
# Einheitliche Datenstruktur für alle Aufrufer (Preview, Execute, Export,
# Scheduler, Pipeline). Verhindert, dass einzelne Node-Typen vergessen werden.

@dataclass
class MappingContext:
    """Vollständiger Kontext eines Mappings – wird von allen Ausführungspfaden genutzt."""
    canvas_nodes:    List[Dict] = field(default_factory=list)
    joins:           List[Dict] = field(default_factory=list)
    transform_nodes: List[Dict] = field(default_factory=list)
    constant_nodes:  List[Dict] = field(default_factory=list)
    sql_nodes:       List[Dict] = field(default_factory=list)
    agg_nodes:       List[Dict] = field(default_factory=list)
    rest_nodes:      List[Dict] = field(default_factory=list)
    lookup_nodes:    List[Dict] = field(default_factory=list)
    calc_nodes:      List[Dict] = field(default_factory=list)
    switch_nodes:    List[Dict] = field(default_factory=list)
    targets:         List[Dict] = field(default_factory=list)

    @classmethod
    def from_orm(cls, mapping) -> "MappingContext":
        """Erstellt einen MappingContext aus einem Mapping-ORM-Objekt."""
        from app.api.mappings import _migrate_legacy_targets
        return cls(
            canvas_nodes    = mapping.canvas_nodes    or [],
            joins           = mapping.joins           or [],
            transform_nodes = mapping.transform_nodes or [],
            constant_nodes  = mapping.constant_nodes  or [],
            sql_nodes       = mapping.sql_nodes       or [],
            agg_nodes       = mapping.agg_nodes       or [],
            rest_nodes      = getattr(mapping, "rest_nodes",   None) or [],
            lookup_nodes    = getattr(mapping, "lookup_nodes", None) or [],
            calc_nodes      = getattr(mapping, "calc_nodes",   None) or [],
            switch_nodes    = getattr(mapping, "switch_nodes", None) or [],
            targets         = _migrate_legacy_targets(mapping),
        )

    def to_execute_kwargs(self, connections: List[Dict], preview_rows: int = 999999) -> Dict:
        """Gibt alle Kwargs für execute_mapping() zurück."""
        return dict(
            canvas_nodes    = self.canvas_nodes,
            connections     = connections,
            joins           = self.joins,
            transform_nodes = self.transform_nodes,
            constant_nodes  = self.constant_nodes,
            sql_nodes       = self.sql_nodes,
            agg_nodes       = self.agg_nodes,
            rest_nodes      = self.rest_nodes,
            lookup_nodes    = self.lookup_nodes,
            calc_nodes      = self.calc_nodes,
            switch_nodes    = self.switch_nodes,
            preview_rows    = preview_rows,
        )


# ─── Typ-Casting für Zielfelder ───────────────────────────────────────────────

# Zulässige target_type-Werte pro Connection:
#   string | integer | decimal | date | datetime | boolean
# Wird in execute_mapping als letzter Schritt auf den output DataFrame angewendet.

TARGET_TYPES = ("string", "integer", "decimal", "date", "datetime", "boolean")

def _apply_target_types(df: pd.DataFrame, connections: List[Dict]) -> tuple:
    """
    Wendet target_type-Casts auf den fertigen Output-DataFrame an.
    Unterstützt dieselben Optionen wie _apply_cast_rules:
      - date_format   (für date/datetime)
      - decimal_sep   (für decimal: "." oder ",")
      - on_error      (null | skip | error)
    Gibt (df, errors) zurück.
    """
    errors = []
    skip_mask = pd.Series([False] * len(df), index=df.index)

    for conn in connections:
        col    = conn.get("target_field")
        ttype  = conn.get("target_type")
        if not col or not ttype or ttype not in TARGET_TYPES:
            continue
        if col not in df.columns:
            continue

        on_error   = conn.get("on_error",    "null")   # null | skip | error
        date_fmt   = conn.get("date_format", "")       # z.B. "%d.%m.%Y"
        decimal_sep = conn.get("decimal_sep", ".")     # "." oder ","

        try:
            if ttype == "integer":
                converted = pd.to_numeric(df[col], errors="coerce").astype("Int64")
                if on_error == "skip":
                    bad = converted.isna() & df[col].notna() & (df[col].astype(str).str.strip() != "")
                    skip_mask = skip_mask | bad
                elif on_error == "error":
                    bad_vals = df[col][converted.isna() & df[col].notna() & (df[col].astype(str).str.strip() != "")]
                    if not bad_vals.empty:
                        errors.append(f"Zieltyp INT '{col}': {len(bad_vals)} nicht konvertierbare Werte")
                df[col] = converted

            elif ttype == "decimal":
                s = df[col].astype(str).str.strip()
                if decimal_sep == ",":
                    # "1.234,56" → "1234.56"
                    s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
                else:
                    # "1,234.56" → "1234.56"
                    s = s.str.replace(",", "", regex=False)
                converted = pd.to_numeric(s, errors="coerce")
                if on_error == "skip":
                    bad = converted.isna() & df[col].notna() & (df[col].astype(str).str.strip() != "")
                    skip_mask = skip_mask | bad
                elif on_error == "error":
                    bad_vals = df[col][converted.isna() & df[col].notna() & (df[col].astype(str).str.strip() != "")]
                    if not bad_vals.empty:
                        errors.append(f"Zieltyp DEC '{col}': {len(bad_vals)} nicht konvertierbare Werte")
                df[col] = converted

            elif ttype in ("date", "datetime"):
                if date_fmt:
                    converted = pd.to_datetime(df[col], format=date_fmt, errors="coerce")
                else:
                    converted = pd.to_datetime(df[col], infer_datetime_format=True, errors="coerce")
                if on_error == "skip":
                    bad = converted.isna() & df[col].notna() & (df[col].astype(str).str.strip() != "")
                    skip_mask = skip_mask | bad
                elif on_error == "error":
                    bad_vals = df[col][converted.isna() & df[col].notna() & (df[col].astype(str).str.strip() != "")]
                    if not bad_vals.empty:
                        errors.append(f"Zieltyp DATE '{col}': {len(bad_vals)} nicht konvertierbare Werte")
                out_fmt = "%Y-%m-%d %H:%M:%S" if ttype == "datetime" else "%Y-%m-%d"
                df[col] = converted.dt.strftime(out_fmt).where(converted.notna(), other=None)

            elif ttype == "boolean":
                true_vals = {"true", "1", "yes", "ja", "wahr", "y"}
                df[col] = df[col].astype(str).str.lower().str.strip().isin(true_vals)

            elif ttype == "string":
                df[col] = df[col].astype(str).replace("nan", "").replace("None", "")

        except Exception as e:
            if on_error == "error":
                errors.append(f"Zieltyp-Cast '{col}' → {ttype}: {str(e)[:100]}")
            # bei null/skip: Spalte unverändert lassen

    if skip_mask.any():
        df = df[~skip_mask]

    return df, errors


# ─── Zentrale Ausführungsfunktion ─────────────────────────────────────────────

def run_mapping_object(
    ctx: "MappingContext",
    target_index: Optional[int] = None,
    preview_rows: int = 50,
    db=None,
    mapping_id: Optional[int] = None,
    mapping_name: Optional[str] = None,
    project_id: Optional[int] = None,
    project_name: Optional[str] = None,
    user_id: int = 1,
    triggered_by: str = "manual",
    scheduled_job_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    EINHEITLICHER Einstiegspunkt für ALLE Ausführungspfade:
      - Preview (preview_rows <= 500, kein db nötig)
      - Execute / save_as_dataset
      - Export (CSV, XLSX, JSON, XML, DB)
      - Scheduler
      - Pipeline

    Gibt immer zurück:
      {
        columns, rows, total, errors,
        column_types,          # immer befüllt
        targets_executed,      # Anzahl ausgeführter Targets
        targets_results,       # [{ name, type, rows, status, error }]
      }

    Bei preview_rows <= 500 werden keine Targets geschrieben.
    Bei preview_rows > 500 (typisch 999999) werden alle Targets ausgeführt,
    sofern targets vorhanden sind.
    """
    is_preview = preview_rows <= 500
    targets = ctx.targets

    # ── Welche Targets sollen ausgeführt werden? ────────────────────────────
    if target_index is not None:
        active_targets = [targets[target_index]] if 0 <= target_index < len(targets) else []
    else:
        active_targets = targets

    # Für Preview: erstes Target für Vorschau-Felder nutzen
    preview_connections = []
    if active_targets:
        preview_connections = active_targets[0].get("fields") or []
    # Fallback: alle connections aus allen targets sammeln
    if not preview_connections:
        for t in active_targets:
            preview_connections = t.get("fields") or []
            if preview_connections:
                break

    # ── Daten berechnen (execute_mapping ist die reine Engine) ─────────────
    result = execute_mapping(
        **ctx.to_execute_kwargs(preview_connections, preview_rows)
    )

    errors = result.get("errors") or []

    # ── target_type-Casts auf Ergebnis anwenden ─────────────────────────────
    if result.get("rows") and result.get("columns"):
        import pandas as _pd
        df_out = _pd.DataFrame(result["rows"], columns=result["columns"])
        df_out, cast_errors = _apply_target_types(df_out, preview_connections)
        errors.extend(cast_errors)
        result["rows"] = df_out.where(df_out.notna(), other=None).to_dict("records")

    # ── column_types immer berechnen ────────────────────────────────────────
    column_types = {}
    if result.get("rows") and result.get("columns"):
        import pandas as _pd
        from app.services.file_service import infer_column_types
        df_types = _pd.DataFrame(result["rows"], columns=result["columns"])
        # cast_rules aus canvas_nodes als forced_types berücksichtigen
        forced = {}
        for node in ctx.canvas_nodes:
            for f, rule in (node.get("cast_rules") or {}).items():
                forced[f] = rule.get("type", "string")
        column_types = infer_column_types(df_types)
        # target_type aus connections überschreibt inferred type
        for conn in preview_connections:
            col = conn.get("target_field")
            ttype = conn.get("target_type")
            if col and ttype and ttype in TARGET_TYPES:
                column_types[col] = {"type": ttype, "raw": column_types.get(col, {}).get("raw", "")}
        # forced_types aus cast_rules überschreiben alles
        for col, t in forced.items():
            if col in column_types:
                column_types[col]["type"] = t

    result["column_types"] = column_types
    result["errors"] = errors

    # ── Bei Preview: fertig, keine Targets schreiben ────────────────────────
    if is_preview:
        result["targets_executed"] = 0
        result["targets_results"] = []
        return result

    # ── Targets ausführen (Export / Scheduler / Pipeline / Execute) ─────────
    targets_results = []
    total_rows = 0

    for target in active_targets:
        t_name = target.get("name") or target.get("target_type") or "Ziel"
        t_type = target.get("target_type", "csv")
        t_fields = target.get("fields") or []

        if not t_fields:
            logger.warning(f"Target '{t_name}' hat keine Felder – übersprungen")
            targets_results.append({"name": t_name, "type": t_type, "rows": 0,
                                     "status": "skipped", "error": "Keine Felder"})
            continue

        try:
            # Eigene execute_mapping Ausführung pro Target (eigene Verbindungen)
            t_result = execute_mapping(
                **ctx.to_execute_kwargs(t_fields, 999999)
            )
            t_errors = t_result.get("errors") or []

            if t_errors and not t_result.get("rows"):
                raise ValueError("; ".join(t_errors[:2]))

            import pandas as _pd
            df = _pd.DataFrame(t_result["rows"], columns=t_result["columns"])

            # target_type-Casts anwenden
            df, cast_errors = _apply_target_types(df, t_fields)
            t_errors.extend(cast_errors)

            opts = target.get("target_options") or {}

            # Pflichtfeld-Validierung
            required_fields = opts.get("required_fields") or []
            if required_fields:
                missing_vals = []
                for f in required_fields:
                    if f in df.columns:
                        null_count = int(df[f].isna().sum()) + int((df[f].astype(str).str.strip() == "").sum())
                        if null_count > 0:
                            missing_vals.append(f"{f} ({null_count} leere Werte)")
                if missing_vals:
                    raise ValueError(f"Pflichtfeld-Fehler: {', '.join(missing_vals)}")

            # Duplikat-Entfernung
            if opts.get("deduplicate_enabled"):
                dedup_fields = opts.get("deduplicate_fields") or []
                subset = [f for f in dedup_fields if f in df.columns] or None
                before = len(df)
                df = df.drop_duplicates(subset=subset, keep="first")
                logger.info(f"  → {before - len(df)} Duplikate entfernt")

            # ── Ziel schreiben ──────────────────────────────────────────────
            _write_target(
                df=df, target=target, t_type=t_type, opts=opts,
                db=db, mapping_id=mapping_id, mapping_name=mapping_name,
                project_id=project_id, project_name=project_name,
                user_id=user_id, triggered_by=triggered_by,
                scheduled_job_id=scheduled_job_id,
            )

            total_rows += len(df)
            targets_results.append({"name": t_name, "type": t_type,
                                     "rows": len(df), "status": "ok",
                                     "warnings": t_errors or []})
            logger.info(f"  ✓ Target '{t_name}' ({t_type}): {len(df)} Zeilen")

        except Exception as e:
            logger.error(f"  ✗ Target '{t_name}': {e}")
            targets_results.append({"name": t_name, "type": t_type, "rows": 0,
                                     "status": "error", "error": str(e)[:300]})
            errors.append(f"Target '{t_name}': {str(e)[:200]}")

    result["targets_executed"] = len([t for t in targets_results if t["status"] == "ok"])
    result["targets_results"] = targets_results
    result["total_rows_written"] = total_rows
    result["errors"] = errors

    # ── Zentrales Log ────────────────────────────────────────────────────────
    if db and mapping_id:
        try:
            from app.services.log_service import write_log
            write_log(
                module="mapping", action=triggered_by,
                message=f"Mapping '{mapping_name or mapping_id}' – {total_rows} Zeilen, {len(active_targets)} Ziele",
                entity_id=mapping_id, entity_name=mapping_name,
                project_id=project_id, rows_processed=total_rows,
                level="info", db=db,
            )
        except Exception as le:
            logger.warning(f"Log-Fehler: {le}")

    return result


def _write_target(df, target, t_type, opts, db, mapping_id, mapping_name,
                  project_id, project_name, user_id, triggered_by, scheduled_job_id):
    """Schreibt einen DataFrame in das angegebene Ziel."""
    from app.core.database import SessionLocal

    if target.get("save_as_dataset") or t_type == "dataset":
        from app.models.dataset import Dataset
        from app.services.file_service import dataframe_to_storage, infer_column_types
        from datetime import datetime, timezone
        thread_db = SessionLocal()
        try:
            write_mode = opts.get("dataset_write_mode", "replace")
            ds = None
            if mapping_id:
                ds = thread_db.query(Dataset).filter(Dataset.source_mapping_id == mapping_id).first()
            if ds:
                col_types = ds.column_types or {}

                if write_mode == "append" and getattr(ds, "file_path", None):
                    # Autoincrement-Felder befüllen beim Anhängen
                    import json, os as _os
                    auto_cols = [col for col, info in col_types.items()
                                 if info.get("is_primary") and info.get("autoincrement")]
                    existing = []
                    try:
                        if _os.path.exists(ds.file_path):
                            with open(ds.file_path, "r", encoding="utf-8") as ef:
                                existing = json.load(ef)
                    except Exception:
                        existing = []
                    new_records = df.to_dict("records")
                    for auto_col in auto_cols:
                        all_vals = []
                        for er in existing:
                            try:
                                all_vals.append(int(er.get(auto_col, 0) or 0))
                            except (ValueError, TypeError):
                                pass
                        for nr in new_records:
                            try:
                                all_vals.append(int(nr.get(auto_col, 0) or 0))
                            except (ValueError, TypeError):
                                pass
                        next_id = (max(all_vals) + 1) if all_vals else 1
                        for row in new_records:
                            val = row.get(auto_col)
                            if val is None or str(val).strip() == "" or str(val) == "0":
                                row[auto_col] = str(next_id)
                                next_id += 1
                    import pandas as _pd
                    df = _pd.DataFrame(existing + new_records)

                elif write_mode == "upsert" and getattr(ds, "file_path", None):
                    # Upsert: Key-Felder aus column_types lesen
                    import json, os as _os
                    key_cols = [col for col, info in col_types.items()
                                if info.get("is_primary") and not info.get("autoincrement")]
                    if not key_cols:
                        # Fallback: alle is_primary Felder als Keys
                        key_cols = [col for col, info in col_types.items()
                                    if info.get("is_primary")]
                    existing = []
                    try:
                        if _os.path.exists(ds.file_path):
                            with open(ds.file_path, "r", encoding="utf-8") as ef:
                                existing = json.load(ef)
                    except Exception:
                        existing = []

                    if key_cols:
                        import pandas as _pd
                        new_records = df.to_dict("records")
                        # Index existing by key
                        existing_by_key = {}
                        for row in existing:
                            k = tuple(str(row.get(c, "")) for c in key_cols)
                            existing_by_key[k] = row
                        # Apply new records: update or insert
                        for row in new_records:
                            k = tuple(str(row.get(c, "")) for c in key_cols)
                            existing_by_key[k] = row  # überschreibt oder fügt hinzu
                        df = _pd.DataFrame(list(existing_by_key.values()))
                    else:
                        # Keine Keys definiert → wie replace
                        logger.warning("Upsert ohne Primary Keys – fallback auf replace")

                ds.row_count = len(df)
                ds.columns = list(df.columns)
                # column_types: is_primary/autoincrement behalten
                inferred = infer_column_types(df)
                merged = dict(col_types)
                for col, info in inferred.items():
                    if col not in merged:
                        merged[col] = info
                    else:
                        merged[col] = {**merged[col], "type": info["type"], "raw": info["raw"]}
                ds.column_types = merged
                ds.updated_at = datetime.now(timezone.utc)
                thread_db.commit()
                dataframe_to_storage(df, ds.id)
            else:
                ds = Dataset(
                    name=target.get("name") or "Mapping-Output",
                    file_type="csv", row_count=len(df),
                    columns=list(df.columns),
                    column_types=infer_column_types(df),
                    xml_configured=1,
                    source_mapping_id=mapping_id,
                    project_id=project_id,
                )
                thread_db.add(ds); thread_db.commit(); thread_db.refresh(ds)
                path = dataframe_to_storage(df, ds.id)
                ds.file_path = path
                thread_db.commit()
        finally:
            thread_db.close()

    elif t_type == "db":
        from app.models.dataset import DbConnection
        from app.services.export_service import export_to_db
        conn_id = target.get("target_connection_id")
        table = target.get("target_table")
        if not conn_id or not table:
            raise ValueError("Verbindung oder Tabelle fehlt")
        thread_db = SessionLocal()
        try:
            conn_obj = thread_db.query(DbConnection).filter(DbConnection.id == conn_id).first()
            if not conn_obj:
                raise ValueError(f"Verbindung #{conn_id} nicht gefunden")
            export_to_db(df, conn_obj, table,
                         target.get("target_write_mode", "insert"),
                         key_columns=opts.get("key_columns", []))
        finally:
            thread_db.close()

    else:
        # CSV / XLSX / JSON / XML → Datei speichern
        from app.services.file_export_service import save_export_file
        thread_db = SessionLocal()
        try:
            save_export_file(
                df,
                user_id=user_id,
                project_id=project_id,
                project_name=project_name,
                job_id=scheduled_job_id,
                mapping_id=mapping_id,
                mapping_name=mapping_name,
                target_name=target.get("name") or t_type,
                target_type=t_type,
                target_options=opts,
                db=thread_db,
                triggered_by=triggered_by,
            )
        finally:
            thread_db.close()


# ─── Transformer anwenden ─────────────────────────────────────────────────────

def _apply_transformer(row: dict, conn: dict, dataset_names: dict = None) -> Any:
    t = conn.get("transformer") or {}
    ttype = t.get("type", "direct")
    src = t.get("source_field") or conn.get("source_field")
    src_ds_id = conn.get("source_dataset_id")

    def _resolve_field(field_name):
        """
        Löst ein Quellfeld auf – berücksichtigt source_dataset_id für eindeutige Zuordnung
        bei mehreren Datasets mit gleichen Feldnamen.
        """
        if field_name is None:
            return None
        # 1. source_dataset_id bekannt → ZUERST Prefix-Suche mit Dataset-Namen
        #    Priorität vor kurzem Namen um Mehrdeutigkeiten aufzulösen
        if src_ds_id is not None and dataset_names:
            ds_name = dataset_names.get(src_ds_id)
            if ds_name:
                full_key = f"{ds_name}.{field_name}"
                if full_key in row:
                    return row[full_key]
                # Auch verschachtelt: "X.DatasetName.Feldname"
                for k, v in row.items():
                    if k.endswith(f".{ds_name}.{field_name}"):
                        return v
        # 2. Fallback: direkt vorhanden (voller Prefix oder eindeutiger Name)
        return row.get(field_name)

    if ttype == "direct":
        return _resolve_field(src)

    elif ttype == "constant":
        return t.get("constant_value", "")

    elif ttype == "formula":
        formula = t.get("formula", "")
        def replace_field(m):
            field = m.group(1)
            val = row.get(field, "")
            try:
                return str(float(val)) if val not in (None, "") else "0"
            except (ValueError, TypeError):
                return f'"{val}"'
        expr = re.sub(r"\{([^}]+)\}", replace_field, formula)
        try:
            return safe_eval_expr(expr)
        except Exception:
            return expr

    elif ttype == "date":
        val = row.get(src)
        if not val:
            return val
        in_fmt = t.get("date_input_format", "YYYY-MM-DD")
        out_fmt = t.get("date_output_format", "DD.MM.YYYY")
        # Convert format strings to Python strptime/strftime
        fmt_map = {
            "YYYY": "%Y", "MM": "%m", "DD": "%d",
        }
        def to_py_fmt(f):
            for k, v in fmt_map.items():
                f = f.replace(k, v)
            return f
        try:
            dt = pd.to_datetime(str(val), format=to_py_fmt(in_fmt), errors="coerce")
            if pd.isna(dt):
                dt = pd.to_datetime(str(val), errors="coerce")
            if pd.isna(dt):
                return val
            return dt.strftime(to_py_fmt(out_fmt))
        except Exception:
            return val

    elif ttype == "condition":
        condition = t.get("condition", "")
        def replace_field(m):
            field = m.group(1)
            val = row.get(field, "")
            try:
                return str(float(val)) if val not in (None, "") else "0"
            except (ValueError, TypeError):
                return f'"{val}"'
        expr = re.sub(r"\{([^}]+)\}", replace_field, condition)
        try:
            result = safe_eval_expr(expr)
            return t.get("condition_true", "") if result else t.get("condition_false", "")
        except Exception:
            return t.get("condition_false", "")

    return row.get(src)


# ─── Filter anwenden ──────────────────────────────────────────────────────────

def _apply_filter(df: pd.DataFrame, field: str, expr: str) -> pd.DataFrame:
    """
    Parst Ausdrücke wie: > 100  |  = "aktiv"  |  != ""  |  LIKE %GmbH%  |  >= 2024-01-01
    """
    expr = expr.strip()

    # LIKE operator
    if expr.upper().startswith("LIKE "):
        pattern = expr[5:].strip().strip('"').strip("'")
        # Convert SQL LIKE % to regex .*
        regex = re.escape(pattern).replace(r"\%", ".*").replace(r"\_", ".")
        return df[df[field].astype(str).str.match(f"^{regex}$", case=False, na=False)]

    # Comparison operators: >= <= != = > <
    for op in (">=", "<=", "!=", "=", ">", "<"):
        if expr.startswith(op):
            raw_val = expr[len(op):].strip().strip('"').strip("'")
            col = df[field]
            # Try numeric comparison
            try:
                num_val = float(raw_val)
                col_num = pd.to_numeric(col, errors="coerce")
                ops = {">=": col_num.__ge__, "<=": col_num.__le__, "!=": col_num.__ne__,
                       "=": col_num.__eq__, ">": col_num.__gt__, "<": col_num.__lt__}
                return df[ops[op](num_val)]
            except ValueError:
                pass
            # String comparison
            col_str = col.astype(str)
            ops_str = {"=": col_str.__eq__, "!=": col_str.__ne__,
                       ">=": col_str.__ge__, "<=": col_str.__le__,
                       ">": col_str.__gt__, "<": col_str.__lt__}
            return df[ops_str[op](raw_val)]

    return df  # no-op if unrecognized


# ─── Datasets laden ───────────────────────────────────────────────────────────

def _load_dataset(dataset_id: int) -> pd.DataFrame:
    """Lädt ein Dataset über die Connector-Factory."""
    connector = get_connector(dataset_id)
    return connector.fetch_full()


# ─── Join anwenden ────────────────────────────────────────────────────────────

def _apply_join(left_df: pd.DataFrame, right_df: pd.DataFrame,
                left_field: str, right_field: str,
                join_type: str, left_name: str, right_name: str) -> pd.DataFrame:
    # Rename columns to avoid conflicts: dataset_name.field
    left_renamed = {c: f"{left_name}.{c}" if "." not in c else c for c in left_df.columns}
    right_renamed = {c: f"{right_name}.{c}" if "." not in c else c for c in right_df.columns}
    left_df = left_df.rename(columns=left_renamed)
    right_df = right_df.rename(columns=right_renamed)

    left_key = left_renamed.get(left_field, left_field)
    right_key = right_renamed.get(right_field, right_field)

    how_map = {
        "INNER JOIN": "inner",
        "LEFT JOIN": "left",
        "RIGHT JOIN": "right",
        "FULL OUTER JOIN": "outer",
    }
    how = how_map.get(join_type, "inner")

    try:
        merged = pd.merge(left_df, right_df, left_on=left_key, right_on=right_key, how=how, suffixes=("", "_r"))
    except Exception as e:
        raise ValueError(f"Join fehlgeschlagen: {e}")

    return merged


# ─── Mapping ausführen ────────────────────────────────────────────────────────

def _resolve_sql_params(sql: str, flat_row: dict):
    """
    Ersetzt {Feldname} Platzhalter im SQL mit parametrisierten Werten.
    Gibt (sql_with_placeholders, params_dict) zurück statt direkter String-Interpolation.
    Das verhindert SQL-Injection: Werte werden nie direkt in den SQL-String eingebaut.

    Beispiel:
      sql_in  = "SELECT * FROM t WHERE id = {kID}"
      returns = ("SELECT * FROM t WHERE id = :param_kID", {"param_kID": 42})
    """
    import re
    params = {}
    counter = [0]

    def replacer(m):
        field = m.group(1)
        # Feldname sanieren: nur alphanumerisch + Unterstrich
        safe_field = re.sub(r"[^a-zA-Z0-9_]", "_", field)
        counter[0] += 1
        param_name = f"param_{safe_field}_{counter[0]}"
        val = flat_row.get(field)
        params[param_name] = val
        return f":{param_name}"

    resolved = re.sub(r"\{([^}]+)\}", replacer, sql)
    return resolved, params


def _build_sql_engine_cache():
    """Gibt einen dict zurück der als Cache für SQLAlchemy-Engines dient."""
    return {}

_sql_engine_cache: dict = {}


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



def _to_numeric(v):
    """Versucht einen Wert zu float zu konvertieren."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None

def _to_numeric(v):
    if v is None: return None
    if isinstance(v, (int, float)): return float(v)
    try: return float(str(v).replace(",", ".").strip())
    except: return None


def _to_numeric_loose(v):
    """Numeric parsing tolerant to common thousands/decimal separators."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("\u00a0", "")
    if not s:
        return None
    # If it contains a comma, assume comma is decimal separator and dots are thousands separators.
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        # Otherwise, treat commas as thousands separators.
        s = s.replace(",", "")
    try:
        return float(s)
    except Exception:
        return None

def _agg_calc(func: str, all_rows: list, input_field: str):
    """Berechnet einen Aggregationswert über alle Zeilen."""
    import statistics
    try:
        all_vals = [row.get(input_field) for row in all_rows]
        non_null = [v for v in all_vals if v is not None and str(v).strip() != ""]
        nv = [n for n in (_to_numeric(v) for v in non_null) if n is not None]

        if func == "sum":
            return round(sum(nv), 10) if nv else 0
        elif func == "count":
            return len(non_null)
        elif func == "count_distinct":
            return len(set(str(v) for v in non_null))
        elif func == "avg":
            return round(sum(nv) / len(nv), 10) if nv else None
        elif func == "min":
            if nv: return min(nv)
            return min(str(v) for v in non_null) if non_null else None
        elif func == "max":
            if nv: return max(nv)
            return max(str(v) for v in non_null) if non_null else None
        elif func == "stddev":
            return round(statistics.stdev(nv), 10) if len(nv) >= 2 else 0
        elif func == "median":
            return statistics.median(nv) if nv else None
        elif func == "first":
            return non_null[0] if non_null else None
        elif func == "last":
            return non_null[-1] if non_null else None
        else:
            return None
    except Exception as e:
        return f"[Agg-Fehler: {e}]"



def _apply_cast_rules(df, cast_rules: dict) -> tuple:
    """Wendet Typ-Konvertierungen auf einen DataFrame an. Gibt (df, errors) zurück."""
    if not cast_rules:
        return df, []
    import pandas as pd
    errors = []
    skip_mask = pd.Series([False] * len(df), index=df.index)

    for field, rule in cast_rules.items():
        if field not in df.columns:
            continue
        cast_type = rule.get("type", "")
        on_error = rule.get("on_error", "null")
        try:
            if cast_type == "integer":
                df[field] = pd.to_numeric(df[field], errors="coerce").astype("Int64")
            elif cast_type == "decimal":
                sep = rule.get("decimal_sep", ".")
                if sep == ",":
                    df[field] = df[field].astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
                df[field] = pd.to_numeric(df[field], errors="coerce")
            elif cast_type in ("date", "datetime"):
                fmt = rule.get("date_format", "%d.%m.%Y")
                converted = pd.to_datetime(df[field], format=fmt, errors="coerce")
                if on_error == "skip":
                    bad = converted.isna() & df[field].notna() & (df[field].astype(str).str.strip() != "")
                    skip_mask = skip_mask | bad
                if cast_type == "date":
                    df[field] = converted.dt.strftime("%Y-%m-%d")
                else:
                    df[field] = converted.dt.strftime("%Y-%m-%d %H:%M:%S")
            elif cast_type == "string":
                df[field] = df[field].astype(str).replace("nan", "").replace("None", "")
            elif cast_type == "boolean":
                true_vals = {"true", "1", "yes", "ja", "wahr", "y"}
                df[field] = df[field].astype(str).str.lower().str.strip().isin(true_vals)
        except Exception as e:
            if on_error == "error":
                errors.append(f"Konvertierung '{field}' → {cast_type}: {str(e)[:100]}")
            # else: null lassen

    if skip_mask.any():
        df = df[~skip_mask]

    return df, errors

def execute_mapping(
    canvas_nodes: List[Dict],
    connections: List[Dict],
    joins: List[Dict],
    transform_nodes: List[Dict] = None,
    constant_nodes: List[Dict] = None,
    sql_nodes: List[Dict] = None,
    agg_nodes: List[Dict] = None,
    rest_nodes: List[Dict] = None,
    lookup_nodes: List[Dict] = None,
    calc_nodes: List[Dict] = None,
    switch_nodes: List[Dict] = None,
    preview_rows: int = 50,
) -> Dict[str, Any]:
    """
    Führt das Mapping aus und gibt Vorschau-Daten zurück.
    Returns: { columns, rows, total, errors }
    """
    errors = []

    if not canvas_nodes:
        return {"columns": [], "rows": [], "total": 0, "errors": ["Keine Datasets auf dem Canvas"]}

    if not connections and not agg_nodes:
        return {"columns": [], "rows": [], "total": 0, "errors": ["Keine Zielfelder definiert"]}

    # 1. Alle Datasets laden + Filter anwenden
    # Bei Vorschau (preview_rows <= 500): fetch_preview() für schnelle Antwort
    # Bei Export (preview_rows > 500 / 999999): fetch_full()
    is_preview = preview_rows <= 500
    dfs: Dict[int, pd.DataFrame] = {}
    names: Dict[int, str] = {}
    for node in canvas_nodes:
        ds_id = node["dataset_id"]
        ds_name = node.get("dataset_name", str(ds_id))
        try:
            connector = get_connector(ds_id)
            if is_preview and not (node.get("filters")) and not agg_nodes:
                # Für reine Vorschau ohne Filter und ohne Aggregation: nur preview_rows laden
                df = connector.fetch_preview(limit=preview_rows * 3)
            else:
                # Bei Aggregation immer alle Daten laden für korrekte Ergebnisse
                df = connector.fetch_full()
            # Apply cast rules
            cast_rules = node.get("cast_rules") or {}
            if cast_rules:
                df, cast_errors = _apply_cast_rules(df, cast_rules)
                errors.extend(cast_errors)

            # Apply field filters
            filters = node.get("filters") or {}
            for field, expr in filters.items():
                if not expr or field not in df.columns:
                    continue
                try:
                    df = _apply_filter(df, field, expr)
                except Exception as fe:
                    errors.append(f"Filter '{field} {expr}' fehlgeschlagen: {fe}")
            dfs[ds_id] = df
            names[ds_id] = ds_name
        except Exception as e:
            errors.append(f"Dataset {ds_name} konnte nicht geladen werden: {e}")

    if not dfs:
        return {"columns": [], "rows": [], "total": 0, "errors": errors}

    # 2. Joins anwenden (verkette alle Datasets)
    if joins:
        # Baue Join-Kette
        result_df = None
        joined_ids = set()

        for join in joins:
            l_id = join["left_dataset_id"]
            r_id = join["right_dataset_id"]
            l_field = join["left_field"]
            r_field = join["right_field"]
            join_type = join.get("join_type", "INNER JOIN")

            l_df = dfs.get(l_id)
            r_df = dfs.get(r_id)
            if l_df is None or r_df is None:
                errors.append(f"Join-Dataset nicht gefunden")
                continue

            l_name = names.get(l_id, str(l_id))
            r_name = names.get(r_id, str(r_id))

            if result_df is None:
                try:
                    result_df = _apply_join(l_df, r_df, l_field, r_field, join_type, l_name, r_name)
                    joined_ids.add(l_id)
                    joined_ids.add(r_id)
                except Exception as e:
                    errors.append(str(e))
                    result_df = l_df.copy()
            else:
                # Weiterer Join auf bestehendes Ergebnis
                try:
                    left_key = f"{l_name}.{l_field}" if l_id in joined_ids else l_field
                    result_df = _apply_join(result_df, r_df, left_key, r_field, join_type, "", r_name)
                    joined_ids.add(r_id)
                except Exception as e:
                    errors.append(str(e))

        # Nicht-gejointen Datasets einfach nebeneinander (cross join, falls nur 1 Dataset)
        for ds_id, df in dfs.items():
            if ds_id not in joined_ids:
                if result_df is None:
                    result_df = df.copy()
                    # prefix columns
                    n = names.get(ds_id, str(ds_id))
                    result_df = result_df.rename(columns={c: f"{n}.{c}" for c in df.columns})
    else:
        # Kein Join: erstes Dataset verwenden, Spalten mit Dataset-Name prefixen
        first_id = canvas_nodes[0]["dataset_id"]
        first_name = names.get(first_id, str(first_id))
        result_df = dfs[first_id].copy()
        result_df = result_df.rename(columns={c: f"{first_name}.{c}" for c in result_df.columns})

    if result_df is None or result_df.empty:
        return {"columns": [], "rows": [], "total": 0, "errors": errors + ["Keine Daten nach Join"]}

    # 3. Transform-Nodes anwenden (fügen neue Felder zum flat_row hinzu)
    def apply_transform_nodes(flat: dict) -> dict:
        def get_val(field):
            """Robust field lookup: exact, then prefix-stripped."""
            if field is None:
                return None
            v = flat.get(field)
            if v is not None:
                return v
            for k, val in flat.items():
                if k.endswith("." + field) or k.endswith("_" + field):
                    return val
            return None
        for tn in (transform_nodes or []):
            tn_type = tn.get("type", "number_format")
            cfg = tn.get("config", {})
            inputs = tn.get("inputs", [])
            out_field = tn.get("output_field", f"transform_{tn.get('id','')}")
            try:
                if tn_type == "number_format":
                    src = inputs[0]["source_field"] if inputs else None
                    val = get_val(src) if src else ""
                    val = "" if val is None else val
                    try:
                        num = float(str(val).replace(",", "."))
                        decimals = int(cfg.get("decimals", 2))
                        dec_sep = cfg.get("decimal_sep", ",")
                        thou_sep = cfg.get("thousands_sep", ".")
                        formatted = f"{num:,.{decimals}f}"
                        # swap separators: replace . with placeholder, , with dec_sep, placeholder with thou_sep
                        formatted = formatted.replace(",", "THOU").replace(".", dec_sep).replace("THOU", thou_sep)
                        flat[out_field] = formatted
                    except (ValueError, TypeError):
                        flat[out_field] = str(val)

                elif tn_type == "date_format":
                    from datetime import datetime
                    src = inputs[0]["source_field"] if inputs else None
                    val = get_val(src) if src else None
                    val = str(val).strip() if val is not None else ""
                    out_fmt = cfg.get("output_format", "%d.%m.%Y")
                    in_fmt  = cfg.get("input_format", "%Y-%m-%d")
                    if not val:
                        flat[out_field] = ""
                    else:
                        dt = None
                        attempts = [
                            in_fmt,
                            "%Y-%m-%d %H:%M:%S.%f",
                            "%Y-%m-%d %H:%M:%S",
                            "%Y-%m-%dT%H:%M:%S.%f",
                            "%Y-%m-%dT%H:%M:%S",
                            "%Y-%m-%d",
                            "%d.%m.%Y %H:%M:%S",
                            "%d.%m.%Y",
                            "%d/%m/%Y",
                            "%m/%d/%Y",
                        ]
                        for fmt in dict.fromkeys(attempts):
                            try:
                                dt = datetime.strptime(val, fmt)
                                break
                            except (ValueError, TypeError):
                                continue
                        if dt:
                            flat[out_field] = dt.strftime(out_fmt)
                        else:
                            try:
                                import pandas as pd
                                flat[out_field] = pd.to_datetime(val).strftime(out_fmt)
                            except Exception:
                                flat[out_field] = val

                elif tn_type == "text":
                    src = inputs[0]["source_field"] if inputs else None
                    val = str(get_val(src) or "") if src else ""
                    op = cfg.get("operation", "trim")
                    if op == "trim":    flat[out_field] = val.strip()
                    elif op == "upper": flat[out_field] = val.upper()
                    elif op == "lower": flat[out_field] = val.lower()
                    elif op == "replace": flat[out_field] = val.replace(cfg.get("find", ""), cfg.get("replace", ""))
                    elif op == "prefix": flat[out_field] = cfg.get("affix", "") + val
                    elif op == "suffix": flat[out_field] = val + cfg.get("affix", "")
                    elif op == "substr":
                        start = int(cfg.get("start", 0))
                        length = cfg.get("length")
                        flat[out_field] = val[start:start + int(length)] if length else val[start:]
                    else: flat[out_field] = val

                elif tn_type == "concat":
                    sep = cfg.get("separator", " ")
                    template = cfg.get("template", "")
                    parts = [str(get_val(inp["source_field"]) or "") for inp in inputs]
                    if template:
                        try:
                            flat[out_field] = template.format(*parts)
                        except Exception:
                            flat[out_field] = sep.join(parts)
                    else:
                        flat[out_field] = sep.join(parts)
            except Exception as te:
                flat[out_field] = f"[Transform-Fehler: {te}]"
        return flat

    total = len(result_df)

    # ─── SQL-Nodes: Spalten-Modus vorab berechnen ─────────────────────────────
    # mode="column": Abfrage einmalig ausführen, Ergebnis per Zeilenindex joinen
    sql_column_data: Dict[str, list] = {}   # output_field → list of values
    for sn in (sql_nodes or []):
        if sn.get("mode", "scalar") != "column":
            continue
        out_field = sn.get("output_field") or f"sql_{sn.get('id','')}"
        conn_id = sn.get("connection_id")
        sql_text = (sn.get("sql") or "").strip()
        if not conn_id or not sql_text:
            sql_column_data[out_field] = []
            continue
        try:
            from sqlalchemy import text as sa_text
            # Sicherstellen dass die Connection zum selben Projekt gehört
            if db:
                from app.models.dataset import DbConnection as _DBC
                _conn_obj = db.query(_DBC).filter(_DBC.id == conn_id).first()
                if not _conn_obj:
                    errors.append(f"SQL-Node '{out_field}': Verbindung {conn_id} nicht gefunden")
                    sql_column_data[out_field] = []
                    continue
            engine = _get_sql_engine(conn_id)
            with engine.connect() as con:
                result = con.execute(sa_text(sql_text))
                rows_fetched = result.fetchall()
                sql_column_data[out_field] = [row[0] for row in rows_fetched]
        except Exception as e:
            errors.append(f"SQL-Node '{out_field}' (Spalte) fehlgeschlagen: {str(e)[:200]}")
            sql_column_data[out_field] = []

    # 4. Transformer auf jede Zeile anwenden
    # ─── Sortierung aus canvas_nodes anwenden ────────────────────────────────────
    if result_df is not None and not result_df.empty:
        sort_cols = []
        sort_asc = []
        for node in canvas_nodes:
            for s in (node.get("sorts") or []):
                field = s.get("field")
                direction = s.get("dir", "asc")
                if not field:
                    continue
                # Finde Spalte mit oder ohne Prefix
                match = None
                if field in result_df.columns:
                    match = field
                else:
                    for col in result_df.columns:
                        if col.split(".")[-1] == field:
                            match = col
                            break
                if match:
                    sort_cols.append(match)
                    sort_asc.append(direction == "asc")
        if sort_cols:
            try:
                result_df = result_df.sort_values(by=sort_cols, ascending=sort_asc, na_position="last")
            except Exception as e:
                errors.append(f"Sortierung fehlgeschlagen: {str(e)[:100]}")

    # ─── Agg-Nodes VOR Connection-Loop: result_df aggregieren ──────────────────
    if agg_nodes:
        import statistics as _stats
        from collections import defaultdict as _dd

        def _to_num(v):
            if v is None: return None
            if isinstance(v, (int, float)): return float(v)
            try: return float(str(v).replace(",", ".").strip())
            except: return None

        def _agg(func, rows, field):
            vals = [r.get(field) for r in rows]
            non_null = [v for v in vals if v is not None and str(v).strip() != ""]
            nv = [n for n in (_to_num(v) for v in non_null) if n is not None]
            try:
                if func == "sum": return round(sum(nv), 10) if nv else 0
                elif func == "count": return len(non_null)
                elif func == "count_distinct": return len(set(str(v) for v in non_null))
                elif func == "avg": return round(sum(nv)/len(nv), 10) if nv else None
                elif func == "min": return min(nv) if nv else (min(str(v) for v in non_null) if non_null else None)
                elif func == "max": return max(nv) if nv else (max(str(v) for v in non_null) if non_null else None)
                elif func == "stddev": return round(_stats.stdev(nv), 10) if len(nv) >= 2 else 0
                elif func == "median": return _stats.median(nv) if nv else None
                elif func == "first": return non_null[0] if non_null else None
                elif func == "last": return non_null[-1] if non_null else None
            except Exception as e: return f"[Fehler: {e}]"

        # Alle Zeilen aus result_df flach laden (mit Prefix-Strip)
        all_flat = []
        for _, raw in result_df.iterrows():
            flat = {}
            for k, v in dict(raw).items():
                flat[k] = v
                short = k.split(".")[-1]
                flat[short] = v  # immer überschreiben damit short-key immer gesetzt
            all_flat.append(flat)

        for an in agg_nodes:
            fields = an.get("fields") or []
            group_fields = [f for f in fields if f.get("func") == "group_by" and f.get("input_field")]
            agg_fields  = [f for f in fields if f.get("func") != "group_by" and f.get("input_field") and f.get("output_field")]
            if not agg_fields:
                continue

            if group_fields:
                groups = _dd(list)
                for row in all_flat:
                    key = tuple(str(row.get(gf["input_field"], "")) for gf in group_fields)
                    groups[key].append(row)
                agg_rows = []
                for key, rows in groups.items():
                    new_row = dict(rows[0])  # alle original-felder übernehmen
                    for i, gf in enumerate(group_fields):
                        out = gf.get("output_field") or gf["input_field"]
                        new_row[out] = key[i]
                    for af in agg_fields:
                        new_row[af["output_field"]] = _agg(af["func"], rows, af["input_field"])
                    agg_rows.append(new_row)
                all_flat = agg_rows
            else:
                base = dict(all_flat[0]) if all_flat else {}
                for af in agg_fields:
                    base[af["output_field"]] = _agg(af["func"], all_flat, af["input_field"])
                all_flat = [base]

        # all_flat zurück in result_df schreiben
        import pandas as _pd
        result_df = _pd.DataFrame(all_flat) if all_flat else result_df.iloc[0:0]
        total = len(result_df)


    # ─── REST API Nodes: pro Zeile API-Call ────────────────────────────────────
    if rest_nodes and output_rows:
        import requests as _req
        from urllib.parse import quote

        def _get_nested(obj, path):
            """JSON-Pfad wie 'data.result.price' auflösen."""
            if not path:
                return obj
            for key in path.split("."):
                if isinstance(obj, dict):
                    obj = obj.get(key)
                elif isinstance(obj, list) and key.isdigit():
                    obj = obj[int(key)]
                else:
                    return None
            return obj

        def _build_headers(auth):
            headers = {}
            if not auth:
                return headers
            atype = auth.get("type", "none")
            if atype == "bearer":
                headers["Authorization"] = f"Bearer {auth.get('token','')}"
            elif atype == "apikey":
                headers[auth.get("key_name","X-API-Key")] = auth.get("key_value","")
            elif atype == "basic":
                import base64
                creds = base64.b64encode(f"{auth.get('username','')}:{auth.get('password','')}".encode()).decode()
                headers["Authorization"] = f"Basic {creds}"
            return headers

        for rn in rest_nodes:
            input_field  = rn.get("input_field", "")
            url_template = rn.get("url", "")
            method       = rn.get("method", "GET").upper()
            auth         = rn.get("auth", {})
            data_path    = rn.get("data_path", "")
            mappings     = rn.get("response_mappings", [])
            mode         = rn.get("mode", "single")        # "single" | "batch"
            join_sep     = rn.get("join_separator", ",")   # Batch: Trennzeichen
            join_key     = rn.get("join_key", input_field) # Batch: Key-Feld in Response
            batch_placeholder = rn.get("batch_placeholder", "{{" + input_field + "s}}")

            if not url_template:
                continue

            headers = _build_headers(auth)

            # ── BATCH-Modus ───────────────────────────────────────────────────
            # Alle Werte aus input_field sammeln → einen API-Call → Ergebnis joinen
            if mode == "batch":
                # 1. Alle Werte sammeln (eindeutig, nicht leer)
                all_vals = []
                seen_vals = set()
                for row in output_rows:
                    v = str(row.get(input_field, "")).strip()
                    if v and v not in seen_vals:
                        seen_vals.add(v)
                        all_vals.append(v)

                if not all_vals:
                    continue

                # 2. URL bauen: {{station_ids}} oder {{input_fields}} ersetzen
                joined = join_sep.join(all_vals)
                url = url_template
                # Generische Platzhalter ersetzen
                for ph in [batch_placeholder,
                           "{{" + input_field + "s}}",
                           "{{" + input_field + "_ids}}",
                           "{{ids}}",
                           "{{values}}"]:
                    url = url.replace(ph, joined)
                # Auch {{station_ids}} etc. ersetzen (häufig in Tankerkönig-Templates)
                import re as _re
                url = _re.sub(r"\{\{\w+\}\}", joined, url)

                # 3. API-Call
                try:
                    if method == "GET":
                        resp = _req.get(url, headers=headers, timeout=30)
                    else:
                        resp = _req.post(url, headers=headers, timeout=30)
                    resp.raise_for_status()
                    raw = resp.json()
                    batch_data = _get_nested(raw, data_path) if data_path else raw
                except Exception as e:
                    errors.append(f"REST Batch-Fehler: {str(e)[:200]}")
                    continue

                # 4. Response-Format erkennen und normalisieren
                # Format A: Dict mit ID als Key → {"uuid1": {e5, e10, diesel}, ...}
                # Format B: Liste mit Key-Feld → [{station_id: "uuid1", e5: 1.89}, ...]
                lookup = {}  # id → data-dict

                if isinstance(batch_data, dict):
                    # Format A (Tankerkönig prices.php)
                    lookup = batch_data
                elif isinstance(batch_data, list):
                    # Format B: Liste mit join_key als Schlüssel
                    for item in batch_data:
                        if isinstance(item, dict):
                            key_val = str(item.get(join_key, ""))
                            if key_val:
                                lookup[key_val] = item

                # 5. Ergebnis in output_rows einjoinen
                if not mappings:
                    # Kein response_mappings: alle Felder aus der Response einfügen
                    for row in output_rows:
                        row_key = str(row.get(input_field, "")).strip()
                        item = lookup.get(row_key, {})
                        if isinstance(item, dict):
                            for k, v in item.items():
                                row[k] = v
                else:
                    for row in output_rows:
                        row_key = str(row.get(input_field, "")).strip()
                        item = lookup.get(row_key)
                        for m in mappings:
                            out_field = m.get("output_field")
                            json_path = m.get("json_path", "")
                            if not out_field:
                                continue
                            if item is None:
                                row[out_field] = None
                            elif isinstance(item, dict):
                                val = _get_nested(item, json_path) if json_path else item.get(out_field)
                                row[out_field] = val
                            else:
                                row[out_field] = item

            # ── SINGLE-Modus (bestehend, pro Zeile) ──────────────────────────
            else:
                if not mappings:
                    continue

                cache = {}  # input_value → response_data

                for row in output_rows:
                    input_val = str(row.get(input_field, "")) if input_field else ""
                    if not input_val:
                        for m in mappings:
                            if m.get("output_field"):
                                row[m["output_field"]] = None
                        continue

                    # Cache-Lookup
                    if input_val not in cache:
                        url = url_template.replace(f"{{{input_field}}}", quote(str(input_val), safe=""))
                        url = url.replace("{value}", quote(str(input_val), safe=""))
                        try:
                            if method == "GET":
                                resp = _req.get(url, headers=headers, timeout=10)
                            else:
                                resp = _req.post(url, headers=headers, timeout=10)
                            resp.raise_for_status()
                            data = resp.json()
                            cache[input_val] = _get_nested(data, data_path) if data_path else data
                        except Exception as e:
                            cache[input_val] = {"__error__": str(e)[:100]}

                    response_data = cache[input_val]

                    for m in mappings:
                        out_field = m.get("output_field")
                        json_path = m.get("json_path", "")
                        if not out_field:
                            continue
                        if "__error__" in (response_data or {}):
                            row[out_field] = f"[API-Fehler: {response_data['__error__']}]"
                        else:
                            val = _get_nested(response_data, json_path) if json_path else response_data
                            row[out_field] = str(val) if val is not None else None


    # ─── Lookup Nodes: Werte aus anderem Dataset nachschlagen ─────────────────────
    if lookup_nodes and output_rows:
        for ln in lookup_nodes:
            input_field = ln.get("input_field", "")
            lookup_ds_id = ln.get("lookup_dataset_id")
            lookup_key_col = ln.get("lookup_key_col", "")
            on_missing = ln.get("on_missing", "null")
            output_mappings = ln.get("output_mappings", [])

            if not input_field or not lookup_ds_id or not lookup_key_col or not output_mappings:
                continue

            # Lookup-Dataset laden (einmalig)
            try:
                connector = get_connector(lookup_ds_id)
                lookup_df = connector.fetch_full()
            except Exception as e:
                errors.append(f"Lookup-Dataset {lookup_ds_id} konnte nicht geladen werden: {str(e)[:100]}")
                continue

            if lookup_key_col not in lookup_df.columns:
                errors.append(f"Lookup-Schlüsselspalte '{lookup_key_col}' nicht gefunden")
                continue

            # Index aufbauen: key → row
            lookup_index = {}
            for _, row in lookup_df.iterrows():
                key = str(row[lookup_key_col]) if row[lookup_key_col] is not None else ""
                if key not in lookup_index:
                    lookup_index[key] = row

            skip_rows = []
            for i, row in enumerate(output_rows):
                input_val = str(row.get(input_field, "")) if row.get(input_field) is not None else ""
                lookup_row = lookup_index.get(input_val)

                if lookup_row is None:
                    if on_missing == "skip":
                        skip_rows.append(i)
                    elif on_missing == "error":
                        errors.append(f"Lookup: Kein Treffer für '{input_val}' in {input_field}")
                    else:  # null
                        for m in output_mappings:
                            if m.get("output_field"):
                                row[m["output_field"]] = None
                else:
                    for m in output_mappings:
                        lookup_col = m.get("lookup_col", "")
                        out_field = m.get("output_field", "")
                        if lookup_col and out_field and lookup_col in lookup_df.columns:
                            val = lookup_row[lookup_col]
                            row[out_field] = None if (val is None or (isinstance(val, float) and str(val) == "nan")) else val

            # Zeilen überspringen wenn on_missing = skip
            if skip_rows:
                output_rows = [r for i, r in enumerate(output_rows) if i not in skip_rows]



    # ─── Switch Nodes: Bedingte Verzweigung ──────────────────────────────────────
    if switch_nodes:
        for sn in switch_nodes:
            output_field = sn.get("output_field", "")
            branches = sn.get("branches", [])
            if not output_field or not branches:
                continue

            chosen_ds_id = None
            for branch in branches:
                condition = branch.get("condition", "always")
                ds_id = branch.get("dataset_id")
                threshold = int(branch.get("threshold") or 0)

                if condition == "always":
                    chosen_ds_id = branch.get("source_dataset_id")
                    break
                elif condition in ("has_rows", "no_rows", "row_count_gt", "row_count_lt") and ds_id:
                    try:
                        check_connector = get_connector(ds_id)
                        check_df = check_connector.fetch_full()
                        row_count = len(check_df)
                        match = False
                        if condition == "has_rows":
                            match = row_count > 0
                        elif condition == "no_rows":
                            match = row_count == 0
                        elif condition == "row_count_gt":
                            match = row_count > threshold
                        elif condition == "row_count_lt":
                            match = row_count < threshold
                        if match:
                            chosen_ds_id = branch.get("source_dataset_id")
                            break
                    except Exception as e:
                        errors.append(f"Switch-Node Bedingung fehlgeschlagen: {str(e)[:100]}")
                        continue

            if chosen_ds_id:
                try:
                    switch_connector = get_connector(chosen_ds_id)
                    switch_df = switch_connector.fetch_full()
                    # Spalten als Felder in output_rows verfügbar machen
                    for col in switch_df.columns:
                        field_name = f"{output_field}__{col}"
                        for i, row in enumerate(output_rows):
                            row[field_name] = switch_df.iloc[i][col] if i < len(switch_df) else None
                    # Metafeld: welcher Zweig gewählt wurde
                    for row in output_rows:
                        row[output_field] = str(chosen_ds_id)
                except Exception as e:
                    errors.append(f"Switch-Node Ausgabe fehlgeschlagen: {str(e)[:100]}")

    target_columns = [c["target_field"] for c in connections if c.get("target_field")]
    output_rows = []

    # Wenn keine Connections aber agg_nodes: Spalten aus result_df
    if not connections and agg_nodes:
        for _, raw_row in result_df.iterrows():
            flat = {}
            for k, v in dict(raw_row).items():
                flat[k] = v
            output_rows.append(flat)
        total = len(output_rows)

    # Flatten result_df rows to dicts (without prefix for direct lookup)
    # Also build a flat lookup without prefix for transformer source_field matching
    for _, raw_row in result_df.head(preview_rows).iterrows():
        flat = dict(raw_row)
        flat_no_prefix = {}
        for k, v in flat.items():
            flat_no_prefix[k] = v
            # Strip dataset prefix: "Rechnung.tRechnung.cRechnungsnr" → "cRechnungsnr"
            # Also handle simple "tArtikel.cArtNr" → "cArtNr"
            # Strategy: try all suffixes after each dot
            parts = k.split(".")
            for i in range(1, len(parts)):
                short = ".".join(parts[i:])
                if short not in flat_no_prefix:
                    flat_no_prefix[short] = v

        # Apply constant nodes (inject static/dynamic values)
        for cn in (constant_nodes or []):
            out_field = cn.get("output_field") or "value"
            ct = cn.get("const_type", "static_text")
            val = cn.get("const_value", "")
            if ct == "static_text":
                flat_no_prefix[out_field] = str(val) if val is not None else ""
            elif ct == "static_number":
                try:
                    flat_no_prefix[out_field] = float(val) if val not in (None, "") else 0
                except (ValueError, TypeError):
                    flat_no_prefix[out_field] = 0
            elif ct == "current_date":
                from datetime import date
                flat_no_prefix[out_field] = date.today().strftime("%d.%m.%Y")
            elif ct == "current_datetime":
                from datetime import datetime
                flat_no_prefix[out_field] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            elif ct == "current_year":
                from datetime import date
                flat_no_prefix[out_field] = str(date.today().year)
            elif ct == "uuid":
                import uuid
                flat_no_prefix[out_field] = str(uuid.uuid4())
            elif ct == "static_bool_true":
                flat_no_prefix[out_field] = "true"
            elif ct == "static_bool_false":
                flat_no_prefix[out_field] = "false"

        # Apply transform nodes (adds new virtual fields)
        flat_no_prefix = apply_transform_nodes(flat_no_prefix)

        # Apply calc_nodes (formula) as row-level derived fields so they can be mapped via connections.
        # Window-based calc types are handled later on the output table.
        for cn in (calc_nodes or []):
            if (cn.get("calc_type") or "formula") != "formula":
                continue
            out_field = cn.get("output_field") or ""
            if not out_field:
                continue
            parts = cn.get("formula_parts") or []
            if not parts:
                flat_no_prefix[out_field] = None
                continue
            expr = []
            for p in parts:
                if "op" in p:
                    expr.append(p.get("op") or "+")
                elif p.get("type") == "number":
                    expr.append(str(_to_numeric_loose(p.get("value")) or 0.0))
                else:
                    field = p.get("value") or ""
                    val = None
                    if field:
                        if field in flat_no_prefix:
                            val = flat_no_prefix.get(field)
                        else:
                            # Try suffix match for joined columns like "Ds.Col"
                            matches = [k for k in flat_no_prefix.keys() if k == field or k.endswith("." + field)]
                            if matches:
                                val = flat_no_prefix.get(matches[0])
                    num = _to_numeric_loose(val)
                    expr.append(str(num if num is not None else 0.0))
            try:
                flat_no_prefix[out_field] = safe_eval_expr(" ".join(expr))
            except Exception as ce:
                errors.append(f"Formel-Fehler: {str(ce)[:100]}")
                flat_no_prefix[out_field] = None

        # Apply SQL nodes
        for sn in (sql_nodes or []):
            out_field = sn.get("output_field") or f"sql_{sn.get('id','')}"
            mode = sn.get("mode", "scalar")
            conn_id = sn.get("connection_id")
            sql_text = (sn.get("sql") or "").strip()
            try:
                if mode == "column":
                    # Wert aus vorberechneter Spalte per Zeilenindex
                    col_values = sql_column_data.get(out_field, [])
                    row_idx = len(output_rows)  # aktueller Index
                    flat_no_prefix[out_field] = col_values[row_idx] if row_idx < len(col_values) else None
                else:
                    # Scalar: SQL pro Zeile mit Feldwerten ausführen
                    if not conn_id or not sql_text:
                        flat_no_prefix[out_field] = None
                        continue
                    resolved_sql, sql_params = _resolve_sql_params(sql_text, flat_no_prefix)
                    from sqlalchemy import text as sa_text
                    engine = _get_sql_engine(conn_id)
                    with engine.connect() as con:
                        result = con.execute(sa_text(resolved_sql), sql_params)
                        row_result = result.fetchone()
                        flat_no_prefix[out_field] = row_result[0] if row_result else None
            except Exception as e:
                flat_no_prefix[out_field] = f"[SQL-Fehler: {str(e)[:80]}]"
        out_row = {}
        for conn in connections:
            target = conn.get("target_field")
            if not target:
                continue
            try:
                val = _apply_transformer(flat_no_prefix, conn, dataset_names=names)
                # Nativen Typ beibehalten – kein blindes str()-Cast mehr.
                # None bleibt None, alles andere bleibt wie es ist.
                # Strings die "nan"/"None" enthalten → None normalisieren.
                if val is None:
                    out_row[target] = None
                elif isinstance(val, str) and val.strip().lower() in ("nan", "none", ""):
                    out_row[target] = None
                else:
                    out_row[target] = val
            except Exception as e:
                out_row[target] = f"[Fehler: {e}]"

        output_rows.append(out_row)

    # ─── Berechnungs-Nodes: Window-Funktionen ─────────────────────────────────────
    if calc_nodes and output_rows:
        import pandas as pd
        df_calc = pd.DataFrame(output_rows)

        def _num_series(col: str):
            """
            Best-effort numeric parsing for preview/export formulas.
            Handles common locale formats like:
              - "1,23" (decimal comma)
              - "1.234,56" (thousands dot, decimal comma)
              - "1,234.56" (thousands comma, decimal dot)
            """
            if not col or col not in df_calc.columns:
                return 0
            s = df_calc[col]
            # Normalize to string for consistent cleaning
            try:
                st = s.astype(str)
            except Exception:
                st = s
            st = st.str.replace("\u00a0", "", regex=False).str.strip()
            has_comma = st.str.contains(",", na=False)
            # If comma exists anywhere, assume comma is decimal separator and dots are thousands separators
            st = st.where(~has_comma, st.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
            # Otherwise, treat comma as thousands separator
            st = st.where(has_comma, st.str.replace(",", "", regex=False))
            return pd.to_numeric(st, errors="coerce")

        for cn in calc_nodes:
            calc_type = cn.get("calc_type") or "formula"
            input_field = cn.get("input_field", "")
            output_field = cn.get("output_field", "")
            order_field = cn.get("order_field", "")
            order_dir = cn.get("order_dir", "asc")
            group_field = cn.get("group_field", "")
            window_size = int(cn.get("window_size") or 3)

            if not output_field:
                continue
            # "formula" is computed row-wise earlier so connections can use it.
            # Skip here to avoid overwriting the already-derived values with NaNs/None.
            if calc_type == "formula":
                continue
            if calc_type not in ("row_number", "formula") and input_field not in df_calc.columns:
                errors.append(f"Berechnungs-Node: Feld '{input_field}' nicht gefunden")
                continue

            try:
                # Sortierung
                if order_field and order_field in df_calc.columns:
                    df_calc = df_calc.sort_values(order_field, ascending=(order_dir != "desc"))

                # Gruppe
                grp = df_calc.groupby(group_field)[input_field] if group_field and group_field in df_calc.columns else (df_calc[input_field] if calc_type != "row_number" else df_calc)

                if calc_type == "cumsum":
                    df_calc[output_field] = grp.cumsum() if group_field else df_calc[input_field].cumsum()
                elif calc_type == "rolling_avg":
                    df_calc[output_field] = grp.transform(lambda x: x.rolling(window_size, min_periods=1).mean()) if group_field else df_calc[input_field].rolling(window_size, min_periods=1).mean()
                elif calc_type == "rolling_sum":
                    df_calc[output_field] = grp.transform(lambda x: x.rolling(window_size, min_periods=1).sum()) if group_field else df_calc[input_field].rolling(window_size, min_periods=1).sum()
                elif calc_type == "rolling_min":
                    df_calc[output_field] = grp.transform(lambda x: x.rolling(window_size, min_periods=1).min()) if group_field else df_calc[input_field].rolling(window_size, min_periods=1).min()
                elif calc_type == "rolling_max":
                    df_calc[output_field] = grp.transform(lambda x: x.rolling(window_size, min_periods=1).max()) if group_field else df_calc[input_field].rolling(window_size, min_periods=1).max()
                elif calc_type == "rank":
                    df_calc[output_field] = grp.rank(method="dense") if group_field else df_calc[input_field].rank(method="dense")
                elif calc_type == "row_number":
                    if group_field and group_field in df_calc.columns:
                        df_calc[output_field] = df_calc.groupby(group_field).cumcount() + 1
                    else:
                        df_calc[output_field] = range(1, len(df_calc) + 1)
                elif calc_type == "pct_change":
                    df_calc[output_field] = grp.pct_change() if group_field else df_calc[input_field].pct_change()
                elif calc_type == "diff":
                    df_calc[output_field] = grp.diff() if group_field else df_calc[input_field].diff()
                elif calc_type == "lag":
                    df_calc[output_field] = grp.transform(lambda x: x.shift(window_size)) if group_field else df_calc[input_field].shift(window_size)
                elif calc_type == "lead":
                    df_calc[output_field] = grp.transform(lambda x: x.shift(-window_size)) if group_field else df_calc[input_field].shift(-window_size)
                elif calc_type == "pct_of_total":
                    if group_field and group_field in df_calc.columns:
                        df_calc[output_field] = df_calc[input_field] / df_calc.groupby(group_field)[input_field].transform("sum") * 100
                    else:
                        total = df_calc[input_field].sum()
                        df_calc[output_field] = df_calc[input_field] / total * 100 if total else 0

                elif calc_type == "formula":
                    formula_parts = cn.get("formula_parts", [])
                    if formula_parts:
                        expr_parts = []
                        for part in formula_parts:
                            if "op" in part:
                                expr_parts.append(part["op"])
                            elif part.get("type") == "number":
                                expr_parts.append(str(float(part.get("value") or 0)))
                            else:
                                field = part.get("value", "")
                                # Suche zuerst exakt, dann als Suffix in Spalten
                                actual_col = None
                                if field and field in df_calc.columns:
                                    actual_col = field
                                elif field:
                                    matches = [c for c in df_calc.columns if c == field or c.endswith("." + field)]
                                    if matches:
                                        actual_col = matches[0]
                                if actual_col:
                                    expr_parts.append("_num_series(" + repr(actual_col) + ")")
                                else:
                                    expr_parts.append("0")
                        expr = " ".join(expr_parts)
                        try:
                            # Window-Formeln mit pandas Series – safe_eval_expr unterstützt keine Series-Operationen.
                                # Hier ist eval() technisch nötig, aber die Formel wird vom Frontend
                                # nur aus validierten Feldern + Operatoren zusammengesetzt (keine freien Strings).
                                # Zusätzliche Absicherung: nur Zahlen, Felder und Operatoren erlaubt.
                                # Sichere Auswertung von pandas-Series-Ausdrücken
                                # Nur explizit erlaubte Namen + keine Attributketten
                                _allowed_names = {"df_calc", "pd", "_num_series"}
                                try:
                                    _tree = _ast.parse(expr, mode="eval")
                                except SyntaxError as _se:
                                    raise ValueError(f"Syntaxfehler in Window-Formel: {_se}")
                                for _node in _ast.walk(_tree):
                                    if isinstance(_node, _ast.Name) and _node.id not in _allowed_names:
                                        raise ValueError(f"Unerlaubter Name in Formel: {_node.id!r}")
                                    if isinstance(_node, _ast.Attribute):
                                        # Erlaube nur: pd.to_numeric, df_calc["col"] etc.
                                        if isinstance(_node.value, _ast.Name) and _node.value.id not in _allowed_names:
                                            raise ValueError(f"Unerlaubter Attributzugriff in Formel")
                                    if isinstance(_node, (_ast.Import, _ast.ImportFrom, _ast.Call)):
                                        # Funktionsaufrufe nur von erlaubten Objekten
                                        if isinstance(_node, _ast.Call):
                                            fn = _node.func
                                            if isinstance(fn, _ast.Name) and fn.id not in _allowed_names:
                                                raise ValueError(f"Unerlaubter Funktionsaufruf: {fn.id!r}")
                                df_calc[output_field] = eval(
                                    expr,
                                    {"df_calc": df_calc, "pd": pd, "_num_series": _num_series,
                                     "__builtins__": {}, "__import__": None, "__builtins__": {}},
                                )
                        except Exception as fe:
                            errors.append(f"Formel-Fehler: {str(fe)[:100]}")
                            # Ensure column exists so later NaN->None conversion doesn't crash
                            df_calc[output_field] = None

                # NaN → None
                df_calc[output_field] = df_calc[output_field].where(df_calc[output_field].notna(), other=None)

            except Exception as e:
                errors.append(f"Berechnungs-Node '{calc_type}': {str(e)[:100]}")

        output_rows = df_calc.to_dict("records")


    return {
        "columns": target_columns,
        "rows": output_rows,
        "total": total,
        "errors": errors,
    }
