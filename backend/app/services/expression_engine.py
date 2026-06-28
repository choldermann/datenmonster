"""
Formel- und Ausdrucks-Auswertung für das Mapping-System.
Stellt einen sicheren Ersatz für eval() bereit und implementiert
alle transformer-Typen und die Expression-Node-Logik.
"""
import re
import ast as _ast
import ast
import operator as _op
import pandas as pd
from typing import Any

from app.services.mapping_utils import _to_numeric_loose


# ─── Sicherer Formel-Evaluator ────────────────────────────────────────────────
# Ersetzt eval() – erlaubt nur arithmetische Ausdrücke und Vergleiche.
# Kein Attributzugriff, keine Funktionsaufrufe, kein Import möglich.

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


def _apply_transformer(row: dict, conn: dict, dataset_names: dict = None) -> Any:
    t = conn.get("transformer") or {}
    ttype = t.get("type", "direct")
    src = t.get("source_field") or conn.get("source_field")
    src_ds_id = conn.get("source_dataset_id")

    def _resolve_field(field_name):
        if field_name is None:
            return None
        if src_ds_id is not None and dataset_names:
            ds_name = dataset_names.get(src_ds_id)
            if ds_name:
                full_key = f"{ds_name}.{field_name}"
                if full_key in row:
                    return row[full_key]
                for k, v in row.items():
                    if k.endswith(f".{ds_name}.{field_name}"):
                        return v
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
        fmt_map = {"YYYY": "%Y", "MM": "%m", "DD": "%d"}
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


def _exec_python_script(script: str, row: dict, timeout_sec: int = 3) -> tuple:
    """
    Führt ein User-Python-Skript sicher aus.
    Wraps the script in a function so `return row` works.
    Returns (new_row_dict, None) on success, (None, error_str) on failure.
    """
    import threading
    import math as _math, re as _re, json as _json
    import decimal as _decimal, statistics as _statistics, string as _string
    from datetime import datetime as _datetime, date as _date, timedelta as _timedelta

    _allowed_builtins = {
        "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
        "enumerate": enumerate, "filter": filter, "float": float, "format": format,
        "getattr": getattr, "hasattr": hasattr, "int": int, "isinstance": isinstance,
        "iter": iter, "len": len, "list": list, "map": map, "max": max, "min": min,
        "next": next, "range": range, "repr": repr, "reversed": reversed, "round": round,
        "set": set, "sorted": sorted, "str": str, "sum": sum, "tuple": tuple,
        "type": type, "zip": zip, "None": None, "True": True, "False": False,
        "print": lambda *a, **kw: None,
    }
    _globs = {
        "__builtins__": _allowed_builtins,
        "math": _math, "re": _re, "json": _json,
        "decimal": _decimal, "statistics": _statistics, "string": _string,
        "datetime": _datetime, "date": _date, "timedelta": _timedelta,
    }

    _result = {"value": None, "error": None}

    def _run():
        try:
            indented = "\n".join("    " + line for line in script.splitlines()) or "    pass"
            wrapped = f"def __fn__(row):\n{indented}\n__ret__ = __fn__(row)"
            local_ns = {"row": dict(row)}
            exec(wrapped, dict(_globs), local_ns)
            ret = local_ns.get("__ret__")
            if ret is None:
                _result["error"] = "Kein Rückgabewert (return row vergessen?)"
            elif not isinstance(ret, dict):
                _result["error"] = f"Skript muss ein dict zurückgeben, nicht {type(ret).__name__}"
            else:
                _result["value"] = ret
        except Exception as _e:
            import traceback as _tb
            lines = [l for l in _tb.format_exc().strip().splitlines() if l.strip()]
            _result["error"] = (lines[-1] if lines else str(_e))[:300]

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout_sec)
    if t.is_alive():
        return None, f"Timeout nach {timeout_sec}s"
    return _result["value"], _result["error"]


def _eval_expression(expr: str, row: dict):
    """Wertet einen Formelausdruck aus. {feldname} wird durch row["feldname"] ersetzt."""
    import re as _re, datetime as _dt, math as _math
    expr_py = _re.sub(r'\{(\w+)\}', r'__r__["\1"]', expr)

    def _upper(s):   return str(s).upper()  if s is not None else None
    def _lower(s):   return str(s).lower()  if s is not None else None
    def _trim(s):    return str(s).strip()  if s is not None else None
    def _concat(*a): return "".join(str(x) for x in a if x is not None)
    def _replace(s, old, new): return str(s).replace(str(old), str(new)) if s is not None else None
    def _substr(s, start, length=None):
        s2 = str(s) if s is not None else ""
        return s2[int(start):int(start)+int(length)] if length is not None else s2[int(start):]
    def _len(s):     return len(str(s)) if s is not None else 0
    def _coalesce(*a):
        for x in a:
            if x is not None and str(x) != "": return x
        return None
    def _if_(cond, then, else_=None): return then if cond else else_
    def _round_(n, d=0): return round(float(n), int(d)) if n is not None else None
    def _int_(s):    return int(float(str(s))) if s is not None else None
    def _float_(s):  return float(str(s))      if s is not None else None
    def _str_(s):    return str(s)             if s is not None else None
    def _now():      return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    def _today():    return _dt.date.today().strftime("%Y-%m-%d")
    def _pad(s, w, ch=" "): return str(s).ljust(int(w), ch[0]) if s is not None else None
    def _regex_match(s, pat):
        import re as _r2
        return bool(_r2.search(pat, str(s))) if s is not None else False

    ns = {
        "__r__": row, "__builtins__": {},
        "upper": _upper, "lower": _lower, "trim": _trim,
        "concat": _concat, "replace": _replace, "substr": _substr,
        "len": _len, "coalesce": _coalesce, "if_": _if_,
        "round": _round_, "int": _int_, "float": _float_, "str": _str_,
        "now": _now, "today": _today, "pad": _pad,
        "regex_match": _regex_match,
        "abs": abs, "max": max, "min": min,
        "sqrt": _math.sqrt, "floor": _math.floor, "ceil": _math.ceil,
        "True": True, "False": False, "None": None,
    }
    return eval(expr_py, ns)  # noqa: S307


def _validate_date(v) -> bool:
    if v is None: return False
    import datetime as _dt2
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            _dt2.datetime.strptime(str(v).strip(), fmt)
            return True
        except ValueError:
            pass
    return False


_DQ_VALIDATORS = {
    "required":  lambda v, _: v is not None and str(v).strip() != "",
    "number":    lambda v, _: (lambda s: s.lstrip("-").replace(".", "", 1).isdigit())(str(v).strip()) if v is not None else False,
    "email":     lambda v, _: bool(__import__("re").fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", str(v).strip())) if v is not None else False,
    "plz_de":    lambda v, _: bool(__import__("re").fullmatch(r"\d{5}", str(v).strip())) if v is not None else False,
    "phone":     lambda v, _: bool(__import__("re").fullmatch(r"[\d\s\+\-\(\)\/]{7,20}", str(v).strip())) if v is not None else False,
    "iban":      lambda v, _: bool(__import__("re").fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", str(v).replace(" ", "").upper())) if v is not None else False,
    "ean":       lambda v, _: bool(__import__("re").fullmatch(r"\d{8}|\d{13}", str(v).strip())) if v is not None else False,
    "vat_id":    lambda v, _: bool(__import__("re").fullmatch(r"[A-Z]{2}[A-Z0-9]{2,12}", str(v).replace(" ", "").upper())) if v is not None else False,
    "regex":     lambda v, rule: bool(__import__("re").search(rule.get("pattern", ".*"), str(v))) if v is not None else False,
    "date":      lambda v, _: _validate_date(v),
    "url":       lambda v, _: bool(__import__("re").match(r"https?://\S+", str(v).strip())) if v is not None else False,
}
