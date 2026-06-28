"""
Mapping Execution Service – Orchestrierung.
Daten-Utilities → mapping_utils.py
Formel-Evaluierung → expression_engine.py
SQL-Helpers → sql_helpers.py
Ziel-Schreiben → mapping_writer.py
"""
import re
import logging
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from app.connectors import get_connector

# ── Sub-module imports (re-exportiert für Rückwärtskompatibilität) ─────────────
from app.services.mapping_utils import (
    _rows_to_json, _apply_target_types, _apply_filter,
    _load_dataset, _apply_join, _to_numeric, _to_numeric_loose,
    _apply_cast_rules, _agg_calc, TARGET_TYPES,
)
from app.services.expression_engine import (
    safe_eval_expr, _eval_node, _apply_transformer,
    _exec_python_script, _eval_expression, _validate_date, _DQ_VALIDATORS,
)
from app.services.sql_helpers import (
    _resolve_sql_params, _resolve_sql_lookup_params, _get_sql_engine,
)
from app.services.mapping_writer import _is_plugin_target, _write_target

logger = logging.getLogger(__name__)

import ast as _ast
import ast  # für Window-Formel-Validierung (direkt in execute_mapping genutzt)


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
    sort_nodes:      List[Dict] = field(default_factory=list)
    python_nodes:    List[Dict] = field(default_factory=list)
    expr_nodes:      List[Dict] = field(default_factory=list)
    quality_nodes:   List[Dict] = field(default_factory=list)
    param_nodes:     List[Dict] = field(default_factory=list)
    run_params:      Dict       = field(default_factory=dict)
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
            switch_nodes    = getattr(mapping, "switch_nodes",  None) or [],
            python_nodes    = getattr(mapping, "python_nodes",   None) or [],
            expr_nodes      = getattr(mapping, "expr_nodes",     None) or [],
            quality_nodes   = getattr(mapping, "quality_nodes",  None) or [],
            param_nodes     = getattr(mapping, "param_nodes",    None) or [],
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
            sort_nodes      = self.sort_nodes,
            python_nodes    = self.python_nodes,
            expr_nodes      = self.expr_nodes,
            quality_nodes   = self.quality_nodes,
            param_nodes     = self.param_nodes,
            run_params      = self.run_params,
            preview_rows    = preview_rows,
        )


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
    """
    is_preview = preview_rows <= 500
    targets = ctx.targets

    if target_index is not None:
        active_targets = [targets[target_index]] if 0 <= target_index < len(targets) else []
    else:
        active_targets = targets

    preview_connections = []
    if active_targets:
        preview_connections = active_targets[0].get("fields") or []
    if not preview_connections:
        for t in active_targets:
            preview_connections = t.get("fields") or []
            if preview_connections:
                break

    _preview_target_opts = None
    if active_targets:
        _preview_target_opts = (active_targets[0].get("target_options") or {}) if active_targets else None

    result = execute_mapping(
        **ctx.to_execute_kwargs(preview_connections, preview_rows),
        target_options=_preview_target_opts,
    )

    errors = result.get("errors") or []

    if result.get("rows") and result.get("columns"):
        import pandas as _pd
        df_out = _pd.DataFrame(result["rows"], columns=result["columns"])
        df_out, cast_errors = _apply_target_types(df_out, preview_connections)
        errors.extend(cast_errors)
        result["rows"] = _rows_to_json(df_out.where(df_out.notna(), other=None).to_dict("records"))

    column_types = {}
    if result.get("rows") and result.get("columns"):
        import pandas as _pd
        from app.services.file_service import infer_column_types
        df_types = _pd.DataFrame(result["rows"], columns=result["columns"])
        forced = {}
        for node in ctx.canvas_nodes:
            for f, rule in (node.get("cast_rules") or {}).items():
                forced[f] = rule.get("type", "string")
        column_types = infer_column_types(df_types)
        for conn in preview_connections:
            col = conn.get("target_field")
            ttype = conn.get("target_type")
            if col and ttype and ttype in TARGET_TYPES:
                column_types[col] = {"type": ttype, "raw": column_types.get(col, {}).get("raw", "")}
        for col, t in forced.items():
            if col in column_types:
                column_types[col]["type"] = t

    result["column_types"] = column_types
    result["errors"] = errors

    if is_preview:
        result["targets_executed"] = 0
        result["targets_results"] = []
        return result

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
            t_result = execute_mapping(**ctx.to_execute_kwargs(t_fields, 999999))
            t_errors = t_result.get("errors") or []

            if t_errors and not t_result.get("rows"):
                raise ValueError("; ".join(t_errors[:2]))

            import pandas as _pd
            df = _pd.DataFrame(t_result["rows"], columns=t_result["columns"])

            df, cast_errors = _apply_target_types(df, t_fields)
            t_errors.extend(cast_errors)

            opts = target.get("target_options") or {}

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

            if opts.get("deduplicate_enabled"):
                dedup_fields = opts.get("deduplicate_fields") or []
                subset = [f for f in dedup_fields if f in df.columns] or None
                before = len(df)
                df = df.drop_duplicates(subset=subset, keep="first")
                logger.info(f"  → {before - len(df)} Duplikate entfernt")

            _sort_fields = [sf for sf in (opts.get("sort_fields") or []) if sf.get("field")]
            _row_limit = opts.get("row_limit")
            if _sort_fields:
                try:
                    import pandas as _pd_sort
                    _temp_cols = {}
                    _sort_by = []
                    _ascending = []
                    for _sf in _sort_fields:
                        _fname = _sf["field"]
                        if _fname not in df.columns:
                            continue
                        _ascending.append(_sf.get("dir", "asc") == "asc")
                        _col = df[_fname]
                        _temp_name = f"__sort__{_fname}"
                        _num = _pd_sort.to_numeric(_col, errors="coerce")
                        if _num.notna().mean() >= 0.7:
                            df[_temp_name] = _num
                        else:
                            _converted = None
                            for _fmt in ["%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d",
                                         "%Y-%m-%dT%H:%M:%S.%f", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y"]:
                                try:
                                    _c = _pd_sort.to_datetime(_col, format=_fmt, errors="coerce")
                                    if _c.notna().mean() >= 0.7:
                                        _converted = _c
                                        break
                                except Exception:
                                    pass
                            if _converted is not None:
                                df[_temp_name] = _converted
                            else:
                                _temp_name = _fname
                        _temp_cols[_fname] = _temp_name
                        _sort_by.append(_temp_name)
                    if _sort_by:
                        df = df.sort_values(by=_sort_by, ascending=_ascending)
                        df = df.drop(columns=[v for v in _temp_cols.values() if v.startswith("__sort__")], errors="ignore")
                except Exception as _se:
                    logger.warning(f"Sortierung fehlgeschlagen: {_se}")
            if _row_limit and isinstance(_row_limit, int) and _row_limit > 0:
                df = df.head(_row_limit)

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


# ─── Mapping-Vorschau / Export-Engine ─────────────────────────────────────────


def _apply_transform_nodes(flat: dict, transform_nodes: list, _auto_id_counters: dict) -> dict:
    """Wendet Transform-Nodes zeilenweise an. _auto_id_counters wird in-place mutiert."""
    def get_val(field):
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
                elif op == "left":
                    n = int(cfg.get("n", 1))
                    flat[out_field] = val[:n]
                elif op == "right":
                    n = int(cfg.get("n", 1))
                    flat[out_field] = val[-n:] if n else ""
                elif op == "substr_range":
                    s = max(1, int(cfg.get("range_start", 1)))
                    e = max(s, int(cfg.get("range_end", s)))
                    flat[out_field] = val[s - 1:e]
                elif op == "split":
                    delim = cfg.get("delimiter", ";")
                    idx = max(1, int(cfg.get("part_index", 1)))
                    parts = val.split(delim)
                    flat[out_field] = parts[idx - 1] if idx <= len(parts) else ""
                elif op == "length":
                    flat[out_field] = len(val)
                elif op == "reverse":
                    flat[out_field] = val[::-1]
                elif op == "regex_extract":
                    import re as _re
                    pattern = cfg.get("pattern", "")
                    group = int(cfg.get("group", 0))
                    if pattern:
                        m = _re.search(pattern, val)
                        flat[out_field] = m.group(group) if m else ""
                    else:
                        flat[out_field] = ""
                elif op == "regex_replace":
                    import re as _re
                    pattern = cfg.get("pattern", "")
                    repl = cfg.get("repl", "")
                    flat[out_field] = _re.sub(pattern, repl, val) if pattern else val
                else: flat[out_field] = val

            elif tn_type == "number_calc":
                src = inputs[0]["source_field"] if inputs else None
                raw = get_val(src) if src else None
                op  = cfg.get("operation", "add")
                if op == "auto_id":
                    flat[out_field] = _auto_id_counters.get(out_field, cfg.get("start_at", 1) - 1) + 1
                    _auto_id_counters[out_field] = flat[out_field]
                else:
                    try:
                        num = float(str(raw).replace(",", ".")) if raw is not None else 0.0
                        val2 = float(cfg.get("value", 0))
                        if   op == "add":      flat[out_field] = num + val2
                        elif op == "subtract": flat[out_field] = num - val2
                        elif op == "multiply": flat[out_field] = num * val2
                        elif op == "divide":   flat[out_field] = num / val2 if val2 != 0 else None
                        elif op == "modulo":   flat[out_field] = num % val2 if val2 != 0 else None
                        elif op == "min":      flat[out_field] = min(num, val2)
                        elif op == "max":      flat[out_field] = max(num, val2)
                        else:                  flat[out_field] = num
                    except (ValueError, TypeError):
                        flat[out_field] = None

            elif tn_type == "date_calc":
                from datetime import datetime as _dt, timedelta as _td
                src = inputs[0]["source_field"] if inputs else None
                raw = str(get_val(src) or "").strip() if src else ""
                op  = cfg.get("operation", "day")
                fmt = cfg.get("input_format", "%Y-%m-%d")
                def _parse(s):
                    for f in [fmt, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S"]:
                        try: return _dt.strptime(s, f)
                        except: pass
                    return None
                if op == "now":
                    flat[out_field] = _dt.now().strftime(cfg.get("now_format", "%Y-%m-%d %H:%M:%S"))
                else:
                    dt = _parse(raw)
                    if dt is None:
                        flat[out_field] = None
                    elif op == "day":      flat[out_field] = dt.day
                    elif op == "month":    flat[out_field] = dt.month
                    elif op == "year":     flat[out_field] = dt.year
                    elif op == "hour":     flat[out_field] = dt.hour
                    elif op == "minute":   flat[out_field] = dt.minute
                    elif op == "second":   flat[out_field] = dt.second
                    elif op == "add_days":
                        flat[out_field] = (dt + _td(days=int(cfg.get("days", 0)))).strftime(fmt)
                    elif op == "days_diff":
                        src2 = inputs[1]["source_field"] if len(inputs) > 1 else None
                        raw2 = str(get_val(src2) or "").strip() if src2 else ""
                        dt2  = _parse(raw2)
                        flat[out_field] = (dt2 - dt).days if dt2 else None
                    else: flat[out_field] = None

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


def _run_window_calc_nodes(
    output_rows: list, calc_nodes: list, errors: list,
    _debug_trace, _dbg_err_idx: int,
) -> tuple:
    """Wendet fenster-basierte Calc-Nodes auf output_rows an. Gibt (output_rows, _dbg_err_idx) zurück."""
    if not calc_nodes or not output_rows:
        return output_rows, _dbg_err_idx
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
        try:
            st = s.astype(str)
        except Exception:
            st = s
        st = st.str.replace(" ", "", regex=False).str.strip()
        has_comma = st.str.contains(",", na=False)
        st = st.where(~has_comma, st.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
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
            if order_field and order_field in df_calc.columns:
                df_calc = df_calc.sort_values(order_field, ascending=(order_dir != "desc"))

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
                    _tot = df_calc[input_field].sum()
                    df_calc[output_field] = df_calc[input_field] / _tot * 100 if _tot else 0

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
                        _allowed_names = {"df_calc", "pd", "_num_series"}
                        try:
                            _tree = _ast.parse(expr, mode="eval")
                        except SyntaxError as _se:
                            raise ValueError(f"Syntaxfehler in Window-Formel: {_se}")
                        for _node in _ast.walk(_tree):
                            if isinstance(_node, _ast.Name) and _node.id not in _allowed_names:
                                raise ValueError(f"Unerlaubter Name in Formel: {_node.id!r}")
                            if isinstance(_node, _ast.Attribute):
                                if isinstance(_node.value, _ast.Name) and _node.value.id not in _allowed_names:
                                    raise ValueError(f"Unerlaubter Attributzugriff in Formel")
                            if isinstance(_node, (_ast.Import, _ast.ImportFrom, _ast.Call)):
                                if isinstance(_node, _ast.Call):
                                    fn = _node.func
                                    if isinstance(fn, _ast.Name) and fn.id not in _allowed_names:
                                        raise ValueError(f"Unerlaubter Funktionsaufruf: {fn.id!r}")
                        df_calc[output_field] = eval(
                            expr,
                            {"df_calc": df_calc, "pd": pd, "_num_series": _num_series,
                             "__builtins__": {}, "__import__": None},
                        )
                    except Exception as fe:
                        errors.append(f"Formel-Fehler: {str(fe)[:100]}")
                        df_calc[output_field] = None

            df_calc[output_field] = df_calc[output_field].where(df_calc[output_field].notna(), other=None)

        except Exception as e:
            errors.append(f"Berechnungs-Node '{calc_type}': {str(e)[:100]}")

    output_rows = _rows_to_json(df_calc.to_dict("records"))

    if _debug_trace is not None:
        _prev_r = _debug_trace[-1]["rows_out"] if _debug_trace else 0
        _debug_trace.append({
            "id": "calc",
            "label": f"Berechnung ({len(calc_nodes)} Node{'s' if len(calc_nodes)>1 else ''})",
            "type": "calc",
            "rows_in": _prev_r,
            "rows_out": len(output_rows),
            "errors": len(errors) - _dbg_err_idx,
            "duration_ms": 0,
            "sample": output_rows[:5],
            "icon": "calculator",
            "meta": {},
        })
        _dbg_err_idx = len(errors)

    return output_rows, _dbg_err_idx


def _run_final_sort_limit(
    output_rows: list, target_options: dict, is_preview: bool, errors: list,
) -> list:
    """Wendet Sortierung und Zeilenlimit aus target_options an."""
    if target_options and output_rows:
        _sort_fields = [sf for sf in (target_options.get("sort_fields") or []) if sf.get("field")]
        _row_limit = target_options.get("row_limit")
        if _sort_fields:
            try:
                import pandas as _pd2
                _sort_df = _pd2.DataFrame(output_rows)
                _valid = [sf for sf in _sort_fields if sf["field"] in _sort_df.columns]
                if _valid:
                    _by = [sf["field"] for sf in _valid]
                    _asc = [sf.get("dir", "asc") == "asc" for sf in _valid]
                    _temp_cols = {}
                    _sort_by_temp = []
                    for _sf in _valid:
                        _fname = _sf["field"]
                        _col = _sort_df[_fname]
                        _temp_name = f"__sort__{_fname}"
                        _converted = None
                        try:
                            _num = _pd2.to_numeric(_col, errors="coerce")
                            if _num.notna().mean() >= 0.7:
                                _converted = _num
                        except Exception:
                            pass
                        if _converted is None:
                            for _fmt in ["%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%d.%m.%Y %H:%M:%S.%f", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y", "%d/%m/%Y"]:
                                try:
                                    _conv = _pd2.to_datetime(_col, format=_fmt, errors="coerce")
                                    if _conv.notna().mean() >= 0.7:
                                        _converted = _conv
                                        break
                                except Exception:
                                    pass
                        if _converted is not None:
                            _sort_df[_temp_name] = _converted
                            _temp_cols[_fname] = _temp_name
                            _sort_by_temp.append(_temp_name)
                        else:
                            _sort_by_temp.append(_fname)
                    _sort_df = _sort_df.sort_values(by=_sort_by_temp, ascending=_asc)
                    _sort_df = _sort_df.drop(columns=list(_temp_cols.values()), errors="ignore")
                    output_rows = _rows_to_json(_sort_df.to_dict(orient="records"))
            except Exception as _e:
                errors.append(f"Sortierung fehlgeschlagen: {_e}")
        if _row_limit and isinstance(_row_limit, int) and _row_limit > 0:
            output_rows = output_rows[:_row_limit]
    if is_preview and len(output_rows) > 50:
        output_rows = output_rows[:50]
    return output_rows


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
    sort_nodes: List[Dict] = None,
    python_nodes: List[Dict] = None,
    expr_nodes: List[Dict] = None,
    quality_nodes: List[Dict] = None,
    param_nodes: List[Dict] = None,
    run_params: Dict = None,
    target_options: Dict = None,
    preview_rows: int = 50,
    _debug_trace: list = None,
) -> Dict[str, Any]:
    """
    Führt das Mapping aus und gibt Vorschau-Daten zurück.
    Returns: { columns, rows, total, errors }
    """
    errors = []
    output_rows = []   # initialized early to prevent NameError in REST/Lookup sections
    _dbg_t = __import__('time').perf_counter if _debug_trace is not None else None
    _dbg_err_idx = 0   # track error count per stage

    # Transform-SQL-Node kann ohne Canvas-Datasets laufen
    has_transform_sql = any(sn.get("mode") == "transform" for sn in (sql_nodes or []))
    if not canvas_nodes and not has_transform_sql:
        return {"columns": [], "rows": [], "total": 0, "errors": ["Keine Datasets auf dem Canvas"]}

    if not connections and not agg_nodes and not has_transform_sql:
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
            filters = node.get("filters") or {}
            pushdown_used = False

            if filters and connector.supports_pushdown() and hasattr(connector, "fetch_filtered"):
                # SQL-Pushdown: Filter direkt auf dem DB-Server ausführen.
                # Bei Joins kein Limit setzen – ein begrenzter Sample würde Join-Keys
                # aus der anderen Tabelle verfehlen und leere Ergebnisse liefern.
                limit = (preview_rows * 3) if (is_preview and not joins) else None
                df = connector.fetch_filtered(filters, limit=limit)
                pushdown_used = True
            elif is_preview and not filters and not agg_nodes and not joins:
                # Reine Vorschau ohne Filter/Agg/Join: nur Vorschauzeilen laden
                df = connector.fetch_preview(limit=preview_rows * 3)
            else:
                df = connector.fetch_full()

            # Apply cast rules
            cast_rules = node.get("cast_rules") or {}
            if cast_rules:
                df, cast_errors = _apply_cast_rules(df, cast_rules)
                errors.extend(cast_errors)

            # Pandas-Filter nur wenn kein Pushdown erfolgt ist
            if not pushdown_used:
                for field, expr in filters.items():
                    if not expr or field not in df.columns:
                        continue
                    try:
                        df = _apply_filter(df, field, expr)
                    except Exception as fe:
                        errors.append(f"Filter '{field} {expr}' fehlgeschlagen: {fe}")

            dfs[ds_id] = df
            names[ds_id] = ds_name
            if _debug_trace is not None:
                import time as _t_mod
                _debug_trace.append({
                    "id": f"dataset_{ds_id}",
                    "label": f"Dataset: {ds_name}",
                    "type": "dataset",
                    "rows_in": None,
                    "rows_out": len(df),
                    "errors": len(errors) - _dbg_err_idx,
                    "duration_ms": 0,
                    "sample": _rows_to_json(df.head(5).to_dict("records")),
                    "icon": "database",
                    "meta": {"has_filter": bool(node.get("filters"))},
                })
                _dbg_err_idx = len(errors)
        except Exception as e:
            errors.append(f"Dataset {ds_name} konnte nicht geladen werden: {e}")

    if not dfs and not has_transform_sql:
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
                    # Herausfinden welche Seite bereits im result_df ist
                    l_in_result = l_id in joined_ids
                    r_in_result = r_id in joined_ids

                    if r_in_result and not l_in_result:
                        # Rechte Seite ist bereits im result_df → tauschen
                        right_key = f"{r_name}.{r_field}" if r_in_result else r_field
                        result_df = _apply_join(result_df, l_df, right_key, l_field, join_type, "", l_name)
                        joined_ids.add(l_id)
                    else:
                        # Linke Seite ist bereits im result_df (Normalfall)
                        left_key = f"{l_name}.{l_field}" if l_in_result else l_field
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
    elif canvas_nodes and dfs:
        # Kein Join: erstes Dataset verwenden, Spalten mit Dataset-Name prefixen
        first_id = canvas_nodes[0]["dataset_id"]
        first_name = names.get(first_id, str(first_id))
        result_df = dfs[first_id].copy()
        result_df = result_df.rename(columns={c: f"{first_name}.{c}" for c in result_df.columns})
    else:
        # Keine Canvas-Datasets (z.B. reiner Transform-Node)
        import pandas as _pd_init
        result_df = _pd_init.DataFrame()

    if (result_df is None or result_df.empty) and not has_transform_sql:
        return {"columns": [], "rows": [], "total": 0, "errors": errors + ["Keine Daten nach Join"]}
    if result_df is None:
        import pandas as _pd_empty
        result_df = _pd_empty.DataFrame()

    if _debug_trace is not None and joins:
        _prev = sum(s["rows_out"] for s in _debug_trace if s["type"] == "dataset") or 0
        _sample = [] if result_df is None or result_df.empty else _rows_to_json(result_df.head(5).to_dict("records"))
        _debug_trace.append({
            "id": "join",
            "label": f"JOIN ({len(joins)} Verbindung{'en' if len(joins)>1 else ''})",
            "type": "join",
            "rows_in": _prev,
            "rows_out": 0 if result_df is None else len(result_df),
            "errors": len(errors) - _dbg_err_idx,
            "duration_ms": 0,
            "sample": _sample,
            "icon": "join",
            "meta": {},
        })
        _dbg_err_idx = len(errors)

    # 3. Transform-Nodes anwenden (fügen neue Felder zum flat_row hinzu)
    _auto_id_counters: dict = {}

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

    # mode="transform": SQL auf Canvas-Datasets + optionale externe Tabellen
    # Ergebnis ersetzt den bisherigen result_df komplett
    transform_sql_nodes = [sn for sn in (sql_nodes or []) if sn.get("mode") == "transform"]
    if transform_sql_nodes:
        sn = transform_sql_nodes[0]  # Nur erster Transform-Node
        sql_text = (sn.get("sql") or "").strip()
        conn_id = sn.get("connection_id")
        if sql_text:
            try:
                import sqlalchemy as _sa
                import pandas as _pd_t

                # 1. Temporäre SQLite-DB im Speicher
                tmp_engine = _sa.create_engine("sqlite:///:memory:")

                # 2. Canvas-Datasets als Tabellen laden
                for ds_id, df_src in dfs.items():
                    tbl_name = names.get(ds_id, f"ds_{ds_id}")
                    # Tabellenname bereinigen (nur Buchstaben/Zahlen/Unterstrich)
                    import re as _re
                    tbl_clean = _re.sub(r'[^a-zA-Z0-9_]', '_', tbl_name)
                    df_src.to_sql(tbl_clean, tmp_engine, if_exists="replace", index=False)

                # 3. Wenn result_df bereits vorhanden (nach JOINs): als "input" laden
                if result_df is not None and not result_df.empty:
                    result_df.to_sql("input", tmp_engine, if_exists="replace", index=False)

                # 4. Externe Tabellen per DB-Connection nachladen
                ext_tables = sn.get("external_tables") or []
                if conn_id and ext_tables:
                    ext_engine = _get_sql_engine(conn_id)
                    for ext in ext_tables:
                        tbl = ext.get("table")
                        alias = ext.get("alias") or tbl
                        if not tbl:
                            continue
                        try:
                            ext_df = _pd_t.read_sql(f"SELECT * FROM {tbl}", ext_engine)
                            alias_clean = _re.sub(r'[^a-zA-Z0-9_]', '_', alias)
                            ext_df.to_sql(alias_clean, tmp_engine, if_exists="replace", index=False)
                        except Exception as ext_e:
                            errors.append(f"Externe Tabelle '{tbl}' konnte nicht geladen werden: {str(ext_e)[:100]}")

                # 5. SQL ausführen
                # Wenn keine Canvas-Datasets: direkt auf DB-Connection
                if not dfs and conn_id:
                    ext_engine = _get_sql_engine(conn_id)
                    _exec_sql = sql_text
                    if is_preview:
                        import re as _re2
                        _dialect = ext_engine.dialect.name
                        _has_limit = bool(_re2.search(r'TOP\s+\d+|LIMIT\s+\d+', _exec_sql, _re2.IGNORECASE))
                        if not _has_limit:
                            if _dialect == 'mssql':
                                _exec_sql = 'SELECT TOP ' + str(preview_rows) + ' ' + _re2.sub(r'(?i)^\s*SELECT\s+', '', _exec_sql, count=1)
                            else:
                                _exec_sql = _exec_sql + ' LIMIT ' + str(preview_rows)
                    result_df = _pd_t.read_sql(_exec_sql, ext_engine)
                else:
                    with tmp_engine.connect() as con:
                        result_df = _pd_t.read_sql(_sa.text(sql_text), con)

                # 6. Output-Felder aus SQL-Node übernehmen
                sql_output_fields = sn.get("output_fields") or list(result_df.columns)

            except Exception as e:
                errors.append(f"SQL-Transform fehlgeschlagen: {str(e)[:300]}")

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

        if _debug_trace is not None and agg_nodes:
            _prev_r = _debug_trace[-1]["rows_out"] if _debug_trace else 0
            _sample = [] if result_df is None or result_df.empty else _rows_to_json(result_df.head(5).to_dict("records"))
            _debug_trace.append({
                "id": "agg",
                "label": f"Aggregation ({len(agg_nodes)} Node{'s' if len(agg_nodes)>1 else ''})",
                "type": "agg",
                "rows_in": _prev_r,
                "rows_out": len(result_df) if result_df is not None else 0,
                "errors": len(errors) - _dbg_err_idx,
                "duration_ms": 0,
                "sample": _sample,
                "icon": "agg",
                "meta": {},
            })
            _dbg_err_idx = len(errors)

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
    # Transform-Node: target_columns aus result_df Spalten wenn keine Connections
    if not target_columns and has_transform_sql and result_df is not None:
        target_columns = list(result_df.columns)
    output_rows = []

    # Wenn keine Connections aber agg_nodes oder transform_sql: Spalten aus result_df
    if not connections and has_transform_sql and result_df is not None:
        output_rows = _rows_to_json(result_df.to_dict(orient="records"))
        total = len(output_rows)
    elif not connections and agg_nodes:
        for _, raw_row in result_df.iterrows():
            flat = {}
            for k, v in dict(raw_row).items():
                flat[k] = v
            output_rows.append(flat)
        total = len(output_rows)

    # Transform-Node mit Connections: schneller Pfad ohne iterrows
    if has_transform_sql and connections and result_df is not None and not result_df.empty:
        import pandas as _pd_fast
        # Nur die gemappten Felder aus result_df selektieren
        mapped_fields = {c.get("source_field"): c.get("target_field") for c in connections if c.get("source_field") and c.get("target_field")}
        valid_fields = {src: tgt for src, tgt in mapped_fields.items() if src in result_df.columns}
        if valid_fields:
            df_mapped = result_df[list(valid_fields.keys())].rename(columns=valid_fields)
            output_rows = _rows_to_json(df_mapped.where(df_mapped.notna(), other=None).to_dict(orient="records"))
            total = len(output_rows)
            target_columns = list(valid_fields.values())
            # Sortierung + Limit
            if target_options:
                _sf = [sf for sf in (target_options.get("sort_fields") or []) if sf.get("field") and sf["field"] in df_mapped.columns]
                if _sf:
                    try:
                        _by = [sf["field"] for sf in _sf]
                        _asc = [sf.get("dir", "asc") == "asc" for sf in _sf]
                        df_mapped = df_mapped.sort_values(by=_by, ascending=_asc)
                        output_rows = _rows_to_json(df_mapped.where(df_mapped.notna(), other=None).to_dict(orient="records"))
                    except Exception:
                        pass
                _limit = target_options.get("row_limit")
                if _limit and isinstance(_limit, int) and _limit > 0:
                    output_rows = output_rows[:_limit]
            if is_preview and len(output_rows) > 50:
                output_rows = output_rows[:50]
            return {
                "columns": target_columns,
                "rows": output_rows,
                "total": total,
                "errors": errors,
            }

    # Lookup-Modus: Batch-IN Nodes vorverarbeiten (einmalige IN-Query vor der Row-Loop)
    sql_lookup_results: dict = {}  # node_id → {key_value: {col: value}}
    for _sn in (sql_nodes or []):
        if _sn.get("mode") != "lookup" or _sn.get("lookup_sub_mode", "row_by_row") != "batch_in":
            continue
        _nid = _sn.get("id")
        _conn_id = _sn.get("connection_id")
        _sql_text = (_sn.get("sql") or "").strip()
        _param_maps = _sn.get("param_mappings") or []
        if not _conn_id or not _sql_text or not _param_maps:
            sql_lookup_results[_nid] = {}
            continue
        _batch_pm = _param_maps[0]
        _batch_param = _batch_pm.get("param", "")
        _src_field = _batch_pm.get("source_field") or _batch_param
        # Unique-Werte aus result_df sammeln
        _unique_vals = set()
        if result_df is not None:
            for _col in result_df.columns:
                if _col == _src_field or _col.split(".")[-1] == _src_field:
                    _unique_vals.update(
                        str(v) for v in result_df[_col].dropna().unique() if v is not None
                    )
                    break
        if not _unique_vals:
            sql_lookup_results[_nid] = {}
            continue
        _ulist = list(_unique_vals)
        _in_params = {f"__bv_{i}__": v for i, v in enumerate(_ulist)}
        _in_clause = "(" + ", ".join(f":__bv_{i}__" for i in range(len(_ulist))) + ")"
        import re as _re_lk2
        _resolved_sql = _re_lk2.sub(
            r":" + _re_lk2.escape(_batch_param) + r"\b", _in_clause, _sql_text
        )
        try:
            from sqlalchemy import text as _sa_text_lk
            _lk_engine = _get_sql_engine(_conn_id)
            with _lk_engine.connect() as _lk_con:
                _lk_res = _lk_con.execute(_sa_text_lk(_resolved_sql), _in_params)
                _lk_rows = _lk_res.fetchall()
                _lk_cols = list(_lk_res.keys())
            # Lookup-Dict aufbauen: source_field_value → {col: value}
            _key_col = _src_field if _src_field in _lk_cols else (
                _batch_param if _batch_param in _lk_cols else (_lk_cols[0] if _lk_cols else None)
            )
            _lk_dict = {}
            if _key_col:
                for _lk_r in _lk_rows:
                    _lk_rd = dict(zip(_lk_cols, _lk_r))
                    _kv = str(_lk_rd.get(_key_col, ""))
                    if _kv and _kv not in _lk_dict:
                        _lk_dict[_kv] = _lk_rd
            sql_lookup_results[_nid] = _lk_dict
        except Exception as _lk_e:
            errors.append(f"SQL-Lookup '{_nid}' (batch_in): {str(_lk_e)[:200]}")
            sql_lookup_results[_nid] = {}

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

        # Apply param nodes (inject run-time parameter values from form/API)
        for pn in (param_nodes or []):
            for field_def in (pn.get("fields") or []):
                fname = (field_def.get("name") or "").strip()
                if not fname:
                    continue
                val = (run_params or {}).get(fname, field_def.get("default") or "")
                ftype = field_def.get("type", "text")
                if ftype == "number" and val not in (None, ""):
                    try:
                        val = float(val)
                    except (ValueError, TypeError):
                        pass
                flat_no_prefix[fname] = val

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
        flat_no_prefix = _apply_transform_nodes(flat_no_prefix, transform_nodes, _auto_id_counters)

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
                elif mode == "lookup":
                    sub_mode = sn.get("lookup_sub_mode", "row_by_row")
                    param_maps = sn.get("param_mappings") or []
                    out_fields_list = sn.get("output_fields") or []
                    node_id = sn.get("id")
                    if sub_mode == "batch_in":
                        # Wert aus vorberechneter Lookup-Tabelle
                        batch_pm = param_maps[0] if param_maps else {}
                        src_field = batch_pm.get("source_field") or batch_pm.get("param", "")
                        key_val = str(flat_no_prefix.get(src_field, ""))
                        row_result_lk = sql_lookup_results.get(node_id, {}).get(key_val, {})
                        for of in out_fields_list:
                            flat_no_prefix[of] = row_result_lk.get(of)
                    else:
                        # row_by_row: SQL pro Zeile mit :param Bindung
                        if not conn_id or not sql_text:
                            for of in out_fields_list:
                                flat_no_prefix[of] = None
                            continue
                        resolved_sql, sql_params = _resolve_sql_lookup_params(
                            sql_text, param_maps, flat_no_prefix
                        )
                        from sqlalchemy import text as sa_text
                        engine = _get_sql_engine(conn_id)
                        with engine.connect() as con:
                            _lkr = con.execute(sa_text(resolved_sql), sql_params)
                            _lk_row = _lkr.fetchone()
                            _lk_cols = list(_lkr.keys())
                        if _lk_row:
                            _lk_rd = dict(zip(_lk_cols, _lk_row))
                            for of in out_fields_list:
                                flat_no_prefix[of] = _lk_rd.get(of)
                        else:
                            for of in out_fields_list:
                                flat_no_prefix[of] = None
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
                if mode == "lookup":
                    for of in (sn.get("output_fields") or []):
                        flat_no_prefix[of] = f"[SQL-Fehler: {str(e)[:60]}]"
                else:
                    flat_no_prefix[out_field] = f"[SQL-Fehler: {str(e)[:80]}]"

        # Apply expr nodes (evaluated per row so connections can pick up outputs)
        for en in (expr_nodes or []):
            for field_def in (en.get("output_fields") or []):
                fname = (field_def.get("name") or "").strip()
                fexpr = (field_def.get("expr") or "").strip()
                if not fname or not fexpr:
                    continue
                try:
                    flat_no_prefix[fname] = _eval_expression(fexpr, flat_no_prefix)
                except Exception as _ee:
                    flat_no_prefix[fname] = None
                    errors.append(f"Expression '{fname}': {str(_ee)[:100]}")

        # Apply quality nodes (adds __dq_valid__ + __dq_errors__ per row)
        for qn in (quality_nodes or []):
            _rules = qn.get("rules") or []
            if not _rules:
                continue
            _row_errors = []
            for _rule in _rules:
                _field = _rule.get("field", "")
                _rtype = _rule.get("type", "required")
                _validator = _DQ_VALIDATORS.get(_rtype)
                if not _validator:
                    continue
                try:
                    _ok = _validator(flat_no_prefix.get(_field), _rule)
                except Exception:
                    _ok = False
                if not _ok:
                    _msg = _rule.get("message") or f"{_field}: {_rtype} Fehler"
                    _row_errors.append(_msg)
            flat_no_prefix["__dq_valid__"] = len(_row_errors) == 0
            flat_no_prefix["__dq_errors__"] = _row_errors

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
                    # Fallback auf default_value wenn kein source_field verbunden
                    if conn.get("source_field") is None and (conn.get("transformer") or {}).get("type", "direct") == "direct":
                        val = conn.get("default_value")
                if val is None:
                    out_row[target] = None
                elif isinstance(val, str) and val.strip().lower() in ("nan", "none", ""):
                    out_row[target] = None
                else:
                    out_row[target] = val
            except Exception as e:
                out_row[target] = f"[Fehler: {e}]"

        output_rows.append(out_row)

    if _debug_trace is not None:
        _prev_r = _debug_trace[-1]["rows_out"] if _debug_trace else 0
        _debug_trace.append({
            "id": "transform",
            "label": "Transform & Mapping",
            "type": "transform",
            "rows_in": _prev_r,
            "rows_out": len(output_rows),
            "errors": len(errors) - _dbg_err_idx,
            "duration_ms": 0,
            "sample": output_rows[:5],
            "icon": "wand",
            "meta": {"transform_nodes": len(transform_nodes or []), "constant_nodes": len(constant_nodes or [])},
        })
        _dbg_err_idx = len(errors)

    output_rows, _dbg_err_idx = _run_window_calc_nodes(
        output_rows, calc_nodes, errors, _debug_trace, _dbg_err_idx
    )

    # ── Python Script Nodes ────────────────────────────────────────────────────
    for pn in (python_nodes or []):
        script = (pn.get("script") or "").strip()
        if not script:
            continue
        node_errors = []
        new_rows = []
        for row in output_rows:
            new_row, err = _exec_python_script(script, row)
            if err:
                node_errors.append(err)
                new_rows.append(row)
            else:
                new_rows.append(new_row)
        output_rows = new_rows
        if node_errors:
            errors.append(f"Python-Node '{pn.get('id','?')}': {node_errors[0]}" +
                          (f" (+ {len(node_errors)-1} weitere)" if len(node_errors) > 1 else ""))

    if _debug_trace is not None and python_nodes:
        _prev_r = _debug_trace[-1]["rows_out"] if _debug_trace else 0
        _debug_trace.append({
            "id": "python",
            "label": f"Python Script ({len(python_nodes)} Node{'s' if len(python_nodes)>1 else ''})",
            "type": "python",
            "rows_in": _prev_r,
            "rows_out": len(output_rows),
            "errors": len(errors) - _dbg_err_idx,
            "duration_ms": 0,
            "sample": output_rows[:5],
            "icon": "code",
            "meta": {},
        })
        _dbg_err_idx = len(errors)

    # Expression nodes and quality nodes are processed per-row in Phase 1
    # (inside the result_df.iterrows() loop above) so connections can resolve their output fields.
    # Here we just add debug trace entries if needed.
    if _debug_trace is not None and expr_nodes:
        _prev_r = _debug_trace[-1]["rows_out"] if _debug_trace else 0
        _debug_trace.append({
            "id": "expr",
            "label": f"Formeln ({len(expr_nodes)} Node{'s' if len(expr_nodes)>1 else ''})",
            "type": "expr",
            "rows_in": _prev_r,
            "rows_out": len(output_rows),
            "errors": len(errors) - _dbg_err_idx,
            "duration_ms": 0,
            "sample": output_rows[:5],
            "icon": "function-square",
            "meta": {},
        })
        _dbg_err_idx = len(errors)

    if _debug_trace is not None and quality_nodes:
        _prev_r = _debug_trace[-1]["rows_out"] if _debug_trace else 0
        dq_invalid = sum(1 for r in output_rows if r.get("__dq_valid__") is False)
        _debug_trace.append({
            "id": "quality",
            "label": f"Datenqualität ({len(quality_nodes)} Node{'s' if len(quality_nodes)>1 else ''})",
            "type": "quality",
            "rows_in": _prev_r,
            "rows_out": len(output_rows),
            "errors": dq_invalid,
            "duration_ms": 0,
            "sample": output_rows[:5],
            "icon": "shield-check",
            "meta": {"invalid": dq_invalid},
        })
        _dbg_err_idx = len(errors)

    output_rows = _run_final_sort_limit(output_rows, target_options, is_preview, errors)


    if _debug_trace is not None:
        _prev_r = _debug_trace[-1]["rows_out"] if _debug_trace else 0
        _debug_trace.append({
            "id": "output",
            "label": "Ausgabe",
            "type": "output",
            "rows_in": _prev_r,
            "rows_out": len(output_rows),
            "errors": len(errors),
            "duration_ms": 0,
            "sample": output_rows[:5],
            "icon": "target",
            "meta": {"columns": len(target_columns) if 'target_columns' in dir() else 0},
        })

    return {
        "columns": target_columns,
        "rows": output_rows,
        "total": total,
        "errors": errors,
    }
