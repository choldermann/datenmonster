import os
import json
import pandas as pd
import xml.etree.ElementTree as ET
from io import BytesIO
from typing import Tuple, List, Dict, Any, Optional
from app.core.config import UPLOAD_DIR


# ─── CSV / XLSX ───────────────────────────────────────────────────────────────

def parse_file(filepath: str, file_type: str, xml_target_node: Optional[str] = None,
               csv_delimiter: str = None, skip_rows: int = 0) -> pd.DataFrame:
    if file_type == "csv":
        sep = csv_delimiter if csv_delimiter else ","
        for enc in ["utf-8", "latin-1", "cp1252"]:
            try:
                return pd.read_csv(filepath, encoding=enc, sep=sep, low_memory=False)
            except UnicodeDecodeError:
                continue
        return pd.read_csv(filepath, encoding="utf-8", errors="replace", sep=sep, skiprows=skip_rows if skip_rows else None)
    elif file_type in ("xlsx", "xls"):
        return pd.read_excel(filepath, skiprows=skip_rows if skip_rows else None)
    elif file_type == "ods":
        return pd.read_excel(filepath, engine="odf", skiprows=skip_rows if skip_rows else None)
    raise ValueError(f"Unsupported file_type: {file_type}")


# ─── XML Struktur-Analyse ─────────────────────────────────────────────────────

def analyze_xml_structure(content: bytes) -> Dict:
    root = ET.fromstring(content)
    return {
        "root": root.tag,
        "tree": _build_tree(root, max_depth=6)
    }


def _build_tree(el: ET.Element, depth: int = 0, max_depth: int = 6) -> Dict:
    if depth > max_depth:
        return {}
    children_tags = list({c.tag for c in el})
    result = {
        "tag": el.tag,
        "attributes": list(el.attrib.keys()),
        "has_text": bool(el.text and el.text.strip()),
        "children": []
    }
    for tag in children_tags:
        child = el.find(tag)
        if child is not None:
            result["children"].append(_build_tree(child, depth + 1, max_depth))
    return result


# ─── Referenzfelder ───────────────────────────────────────────────────────────

def get_node_fields(content: bytes, node_path: str) -> List[str]:
    root = ET.fromstring(content)
    parts = node_path.split("/")
    fields = []

    if len(parts) == 1:
        _collect_fields(root, "", skip_tag=parts[0], fields=fields)
    else:
        for depth, part in enumerate(parts[:-1]):
            ancestor = root.find(f".//{part}")
            if ancestor is None:
                continue
            skip = parts[depth + 1]
            prefix = f"{part}." if depth > 0 else ""
            _collect_fields(ancestor, prefix, skip_tag=skip, fields=fields)

    return sorted(set(f for f in fields if f))


def _collect_fields(el: ET.Element, prefix: str, skip_tag: str, fields: list):
    for attr in el.attrib:
        fields.append(f"{prefix}@{attr}")
    for child in el:
        if child.tag == skip_tag:
            continue
        sub_children = list(child)
        if not sub_children:
            fields.append(f"{prefix}{child.tag}")
        else:
            _collect_fields(child, f"{prefix}{child.tag}.", skip_tag="", fields=fields)


# ─── XML parsen mit Zielknoten + Referenzfelder ───────────────────────────────

def parse_xml_with_config(
    content: bytes,
    target_node: str,
    ref_fields: List[str]
) -> Tuple[List[str], List[Dict[str, Any]]]:
    root = ET.fromstring(content)
    parts = target_node.split("/")

    if len(parts) == 1:
        target_elements = [(None, el) for el in root.iter(parts[0])]
    else:
        parent_tag = parts[-2]
        target_tag = parts[-1]
        target_elements = []
        for parent_el in root.iter(parent_tag):
            for child_el in parent_el.findall(target_tag):
                target_elements.append((parent_el, child_el))

    if not target_elements:
        raise ValueError(f"Keine Knoten '{target_node}' gefunden")

    all_columns = set()
    for _, el in target_elements:
        all_columns.update(_flatten_element(el).keys())
        for attr in el.attrib:
            all_columns.add(f"@{attr}")

    ref_col_names = [f"_ref_{f.replace('.', '_').replace('@', '')}" for f in ref_fields]
    columns = ref_col_names + sorted(all_columns)

    rows = []
    for parent_el, el in target_elements:
        row = _flatten_element(el)
        for attr, val in el.attrib.items():
            row[f"@{attr}"] = val
        for rf, col_name in zip(ref_fields, ref_col_names):
            val = _resolve_ref_field(root, target_node, el, rf)
            row[col_name] = val
        for col in columns:
            if col not in row:
                row[col] = None
        rows.append(row)

    return columns, rows


def _resolve_ref_field(root, target_node, target_el, field_path):
    parts = target_node.split("/")
    for ancestor_tag in reversed(parts[:-1]):
        for ancestor in root.iter(ancestor_tag):
            if not _is_descendant(ancestor, target_el):
                continue
            lookup = field_path
            if lookup.startswith(ancestor_tag + "."):
                lookup = lookup[len(ancestor_tag) + 1:]
            val = _get_nested_value(ancestor, lookup)
            if val is not None:
                return val
    return None


def _is_descendant(ancestor, target):
    for child in ancestor.iter():
        if child is target:
            return True
    return False


def _flatten_element(el, prefix=""):
    result = {}
    children = list(el)
    if el.text and el.text.strip():
        key = (prefix.rstrip(".") + "._text") if prefix else "_text"
        result[key] = el.text.strip()
    if not children:
        key = prefix.rstrip(".")
        val = el.text.strip() if el.text and el.text.strip() else None
        if key:
            result[key] = val
    else:
        for child in children:
            result.update(_flatten_element(child, f"{prefix}{child.tag}."))
    for attr, val in el.attrib.items():
        result[f"{prefix}@{attr}"] = val
    return result


def _get_nested_value(el, field_path):
    parts = field_path.split(".")
    current = el
    for part in parts:
        if current is None:
            return None
        if part.startswith("@"):
            return current.attrib.get(part[1:])
        found = current.find(part)
        if found is None:
            found = next(current.iter(part), None)
        current = found
    if current is not None and current.text:
        return current.text.strip() or None
    return None


# ─── Typinferenz ─────────────────────────────────────────────────────────────

# Datumsformate die wir sicher erkennen wollen – bewusst eng gehalten
_DATE_FORMATS = [
    "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f", "%d.%m.%Y", "%d.%m.%Y %H:%M:%S",
    "%d/%m/%Y", "%m/%d/%Y", "%Y%m%d",
]

def _looks_like_date(sample: "pd.Series") -> bool:
    """
    Konservative Datumserkennung:
    - Mindestens 5 nicht-leere Werte nötig
    - Muss gegen eines der expliziten Formate matchen
    - Mindestens 80% der Werte müssen konvertierbar sein
    - Wert muss mindestens 6 Zeichen lang sein (verhindert "May", "3" etc.)
    """
    # Nur nicht-leere Strings
    vals = sample.dropna().astype(str)
    vals = vals[vals.str.strip() != ""]

    # Zu wenig Daten → nicht als Datum klassifizieren
    if len(vals) < 5:
        return False

    # Zu kurze Werte → sicher kein Datum (z.B. Namen, einzelne Zahlen)
    if vals.str.len().median() < 6:
        return False

    # Gegen bekannte Formate testen
    for fmt in _DATE_FORMATS:
        try:
            converted = pd.to_datetime(vals, format=fmt, errors="coerce")
            hit_rate = converted.notna().mean()
            if hit_rate >= 0.8:
                return True
        except Exception:
            continue

    return False


def infer_column_types(df: pd.DataFrame, db_raw_types: dict = None) -> dict:
    """
    Leitet einfache Typinfos aus einem DataFrame ab.
    Gibt {col: {type: 'string'|'integer'|'decimal'|'date'|'bool', raw: '<dtype>'}} zurück.
    db_raw_types: optionales {col: 'varchar(255)'} aus DB-Inspektion.

    Datumserkennung ist bewusst konservativ um Fehlklassifikationen zu vermeiden:
    leere Spalten, kurze Strings und Monatsnamen werden NICHT als Datum erkannt.
    """
    result = {}
    for col in df.columns:
        dtype = df[col].dtype
        raw = (db_raw_types or {}).get(col, str(dtype))

        if pd.api.types.is_bool_dtype(dtype):
            simple = "bool"
        elif pd.api.types.is_integer_dtype(dtype):
            simple = "integer"
        elif pd.api.types.is_float_dtype(dtype):
            simple = "decimal"
        elif pd.api.types.is_datetime64_any_dtype(dtype):
            simple = "date"
        else:
            # Nur nicht-leere, nicht-None Werte betrachten
            sample = df[col].dropna()
            sample = sample[sample.astype(str).str.strip() != ""]

            if len(sample) == 0:
                # Leere Spalte → String (sicherer Default)
                simple = "string"
            else:
                # 0. Vorprüfung: Strings mit führenden Nullen oder nicht-numerischen Zeichen
                #    sind immer Strings – auch wenn sie rein aus Ziffern bestehen
                str_sample = sample.astype(str).str.strip()
                # Führende Nullen: "0010001378254", "007" etc.
                has_leading_zeros = str_sample.str.match(r"^0\d+$").any()
                # Nicht-numerische Zeichen (Bindestriche, Buchstaben etc.): "26301756-RI"
                has_non_numeric = str_sample.str.contains(r"[a-zA-Z\-/\\]", regex=True).any()
                if has_leading_zeros or has_non_numeric:
                    simple = "string"
                else:
                    # 1. Zahlen-Test (direkt)
                    try:
                        converted = pd.to_numeric(sample, errors="raise")
                        simple = "integer" if (converted == converted.astype("int64")).all() else "decimal"
                    except Exception:
                        # 1b. Zahlen-Test mit Komma als Dezimaltrennzeichen
                        # "1.234,56" → "1234.56" / "1,50" → "1.50"
                        try:
                            normalized = (
                                sample.astype(str)
                                .str.strip()
                                .str.replace(r"^\s*[+-]?\d{1,3}(\.\d{3})*(,\d+)?\s*$",
                                             lambda m: m.group(0).replace(".", "").replace(",", "."),
                                             regex=True)
                            )
                            converted2 = pd.to_numeric(normalized, errors="raise")
                            simple = "integer" if (converted2 == converted2.astype("int64")).all() else "decimal"
                        except Exception:
                            # 2. Konservativer Datums-Test
                            if _looks_like_date(sample):
                                simple = "date"
                            else:
                                simple = "string"

        result[col] = {"type": simple, "raw": raw}
    return result


# ─── JSON Storage (kein pyarrow nötig) ───────────────────────────────────────

def dataframe_to_storage(df: pd.DataFrame, dataset_id: int) -> str:
    """Speichert DataFrame als JSON - keine externe Abhängigkeit."""
    import math
    path = os.path.join(UPLOAD_DIR, f"dataset_{dataset_id}.json")

    # Doppelte Spaltennamen deduplizieren (z.B. bei JOINs: kBestellung → kBestellung_1)
    seen = {}
    new_cols = []
    for col in df.columns:
        if col in seen:
            seen[col] += 1
            new_cols.append(f"{col}_{seen[col]}")
        else:
            seen[col] = 0
            new_cols.append(col)
    df = df.copy()
    df.columns = new_cols

    def _clean(v):
        if v is None:
            return ""
        if isinstance(v, float):
            if math.isnan(v):
                return ""
            if v == int(v):
                return str(int(v))
            return str(v)
        try:
            iv = int(v)
            if iv == v:
                return str(iv)
        except (ValueError, TypeError, OverflowError):
            pass
        return str(v) if not isinstance(v, str) else v

    records = []
    for row in df.to_dict(orient="records"):
        records.append({k: _clean(val) for k, val in row.items()})

    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False)
    return path


def read_dataset(dataset_id: int, page: int = 0, page_size: int = 100) -> dict:
    path = os.path.join(UPLOAD_DIR, f"dataset_{dataset_id}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Dataset file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        all_rows = json.load(f)
    if not all_rows:
        # Spalten aus DB-Modell holen falls JSON leer
        try:
            from app.core.database import SessionLocal
            from app.models.dataset import Dataset
            _db = SessionLocal()
            _ds = _db.query(Dataset).filter(Dataset.id == dataset_id).first()
            _cols = _ds.columns or [] if _ds else []
            _db.close()
        except Exception:
            _cols = []
        return {"columns": _cols, "preview": [], "total": 0, "page": page, "page_size": page_size}
    cols = list(all_rows[0].keys())
    total = len(all_rows)
    start = page * page_size
    preview = all_rows[start:start + page_size]
    return {"columns": cols, "preview": preview, "total": total, "page": page, "page_size": page_size}

