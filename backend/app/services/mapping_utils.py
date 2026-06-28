"""
Gemeinsame Daten-Utilities für das Mapping-System.
Kein Business-Logik – nur reine Daten-Transformationen.
"""
import re
import math
import pandas as pd
from typing import List, Dict, Any
from app.connectors import get_connector


def _rows_to_json(rows: list) -> list:
    """Konvertiert DataFrame-Rows zu JSON-kompatiblen Werten ohne Locale-Effekte."""
    result = []
    for row in rows:
        clean = {}
        for k, v in row.items():
            if isinstance(v, float):
                if math.isnan(v) or math.isinf(v):
                    clean[k] = None
                else:
                    clean[k] = v
            elif hasattr(v, "item"):
                # numpy scalar → Python
                try:
                    clean[k] = v.item()
                except Exception:
                    clean[k] = str(v)
            elif hasattr(v, "isoformat"):
                clean[k] = v.isoformat()
            else:
                clean[k] = v
        result.append(clean)
    return result


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

        on_error   = conn.get("on_error",    "null")
        date_fmt   = conn.get("date_format", "")
        decimal_sep = conn.get("decimal_sep", ".")

        try:
            if ttype == "integer":
                converted = pd.to_numeric(df[col], errors="coerce").astype("Int64")
                bad = converted.isna() & df[col].notna() & (df[col].astype(str).str.strip() != "")
                if on_error == "skip":
                    skip_mask = skip_mask | bad
                elif on_error == "error":
                    if bad.any():
                        errors.append(f"Zieltyp INT '{col}': {bad.sum()} nicht konvertierbare Werte")
                        continue
                df[col] = converted

            elif ttype == "decimal":
                s = df[col].astype(str).str.strip()
                if decimal_sep == ",":
                    s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
                else:
                    s = s.str.replace(",", "", regex=False)
                converted = pd.to_numeric(s, errors="coerce")
                bad = converted.isna() & df[col].notna() & (df[col].astype(str).str.strip() != "")
                if on_error == "skip":
                    skip_mask = skip_mask | bad
                elif on_error == "error":
                    if bad.any():
                        errors.append(f"Zieltyp DEC '{col}': {bad.sum()} nicht konvertierbare Werte")
                        continue
                df[col] = converted

            elif ttype in ("date", "datetime"):
                if date_fmt:
                    converted = pd.to_datetime(df[col], format=date_fmt, errors="coerce")
                else:
                    converted = pd.to_datetime(df[col], infer_datetime_format=True, errors="coerce")
                bad = converted.isna() & df[col].notna() & (df[col].astype(str).str.strip() != "")
                if on_error == "skip":
                    skip_mask = skip_mask | bad
                elif on_error == "error":
                    if bad.any():
                        errors.append(f"Zieltyp DATE '{col}': {bad.sum()} nicht konvertierbare Werte")
                        continue
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

    if skip_mask.any():
        df = df[~skip_mask]

    return df, errors


def _apply_filter(df: pd.DataFrame, field: str, expr: str) -> pd.DataFrame:
    """
    Parst Ausdrücke wie: > 100  |  = "aktiv"  |  != ""  |  LIKE %GmbH%  |  >= 2024-01-01
                         IS NULL  |  IS NOT NULL
    """
    expr = expr.strip()
    expr_upper = expr.upper()
    col = df[field]

    if expr_upper == "IS NULL":
        return df[col.isna()]
    if expr_upper == "IS NOT NULL":
        return df[col.notna()]

    if expr_upper.startswith("LIKE "):
        pattern = expr[5:].strip().strip('"').strip("'")
        regex = "".join(
            ".*" if c == "%" else "." if c == "_" else re.escape(c)
            for c in pattern
        )
        return df[col.astype(str).str.match(f"^{regex}$", case=False, na=False)]

    for op in (">=", "<=", "!=", "=", ">", "<"):
        if expr.startswith(op):
            raw_val = expr[len(op):].strip().strip('"').strip("'")

            if raw_val == "":
                if op == "!=":
                    return df[col.notna() & (col.astype(str) != "")]
                else:
                    return df[col.isna() | (col.astype(str) == "")]

            try:
                num_val = float(raw_val)
                col_num = pd.to_numeric(col, errors="coerce")
                ops = {">=": col_num.__ge__, "<=": col_num.__le__, "!=": col_num.__ne__,
                       "=": col_num.__eq__, ">": col_num.__gt__, "<": col_num.__lt__}
                return df[ops[op](num_val)]
            except ValueError:
                pass

            col_str = col.where(col.notna(), other=None).astype(str)
            ops_str = {"=": col_str.__eq__, "!=": col_str.__ne__,
                       ">=": col_str.__ge__, "<=": col_str.__le__,
                       ">": col_str.__gt__, "<": col_str.__lt__}
            mask = ops_str[op](raw_val)
            return df[mask & col.notna()]

    return df


def _load_dataset(dataset_id: int) -> pd.DataFrame:
    """Lädt ein Dataset über die Connector-Factory."""
    connector = get_connector(dataset_id)
    return connector.fetch_full()


def _apply_join(left_df: pd.DataFrame, right_df: pd.DataFrame,
                left_field: str, right_field: str,
                join_type: str, left_name: str, right_name: str) -> pd.DataFrame:
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


def _to_numeric(v) -> float:
    """Versucht einen Wert zu float zu konvertieren."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None


def _to_numeric_loose(v) -> float:
    """Numeric parsing tolerant to common thousands/decimal separators."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(" ", "")
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except Exception:
        return None


def _apply_cast_rules(df, cast_rules: dict) -> tuple:
    """Wendet Typ-Konvertierungen auf einen DataFrame an. Gibt (df, errors) zurück."""
    if not cast_rules:
        return df, []
    errors = []
    skip_mask = pd.Series([False] * len(df), index=df.index)

    for field, rule in cast_rules.items():
        if field not in df.columns:
            continue
        cast_type = rule.get("type", "")
        on_error = rule.get("on_error", "null")
        try:
            if cast_type == "integer":
                converted = pd.to_numeric(df[field], errors="coerce").astype("Int64")
                bad = converted.isna() & df[field].notna() & (df[field].astype(str).str.strip() != "")
                if on_error == "skip":
                    skip_mask = skip_mask | bad
                elif on_error == "error" and bad.any():
                    errors.append(f"Konvertierung INT '{field}': {bad.sum()} nicht konvertierbare Werte")
                    continue
                df[field] = converted
            elif cast_type == "decimal":
                sep = rule.get("decimal_sep", ".")
                s = df[field].astype(str).str.strip()
                if sep == ",":
                    s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
                else:
                    s = s.str.replace(",", "", regex=False)
                converted = pd.to_numeric(s, errors="coerce")
                bad = converted.isna() & df[field].notna() & (df[field].astype(str).str.strip() != "")
                if on_error == "skip":
                    skip_mask = skip_mask | bad
                elif on_error == "error" and bad.any():
                    errors.append(f"Konvertierung DEC '{field}': {bad.sum()} nicht konvertierbare Werte")
                    continue
                df[field] = converted
            elif cast_type in ("date", "datetime"):
                fmt = rule.get("date_format", "%d.%m.%Y")
                converted = pd.to_datetime(df[field], format=fmt, errors="coerce")
                bad = converted.isna() & df[field].notna() & (df[field].astype(str).str.strip() != "")
                if on_error == "skip":
                    skip_mask = skip_mask | bad
                elif on_error == "error" and bad.any():
                    errors.append(f"Konvertierung DATE '{field}': {bad.sum()} nicht konvertierbare Werte")
                    continue
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

    if skip_mask.any():
        df = df[~skip_mask]

    return df, errors


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
            return min(nv) if nv else None
        elif func == "max":
            return max(nv) if nv else None
        elif func == "median":
            return statistics.median(nv) if nv else None
        elif func == "stdev":
            return statistics.stdev(nv) if len(nv) >= 2 else None
        elif func == "first":
            return non_null[0] if non_null else None
        elif func == "last":
            return non_null[-1] if non_null else None
        elif func == "concat":
            return ", ".join(str(v) for v in non_null)
        else:
            return None
    except Exception:
        return None
