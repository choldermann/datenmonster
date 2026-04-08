"""
Export Service – schreibt das Mapping-Ergebnis in verschiedene Formate.
Unterstützt: CSV, XLSX, JSON, XML (template-basiert), DB (MSSQL/MySQL)
"""
import io
import csv
import json
import re
import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import List, Dict, Any, Optional
import pandas as pd


# ─── CSV ──────────────────────────────────────────────────────────────────────

def export_csv(df: pd.DataFrame, delimiter: str = ";", encoding: str = "utf-8-sig") -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False, sep=delimiter)
    return buf.getvalue().encode(encoding)


# ─── XLSX ─────────────────────────────────────────────────────────────────────

def export_xlsx(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Export")
        ws = writer.sheets["Export"]
        # Auto-fit column widths
        for col_cells in ws.columns:
            max_len = max((len(str(c.value or "")) for c in col_cells), default=10)
            ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 2, 50)
    return buf.getvalue()


# ─── JSON ─────────────────────────────────────────────────────────────────────

def export_json(df: pd.DataFrame, orient: str = "records", indent: int = 2) -> bytes:
    data = json.loads(df.to_json(orient=orient, force_ascii=False))
    return json.dumps(data, ensure_ascii=False, indent=indent).encode("utf-8")


# ─── XML (template-basiert) ───────────────────────────────────────────────────

def export_xml(df: pd.DataFrame, template: dict) -> bytes:
    """
    Renders XML from a tree template (new node-based format).
    template = { tree: { id, tag, attributes, children, fieldBinding, staticValue, isRepeating } }
    Falls back to simple flat format if no tree is present.
    """
    tree = template.get("tree")
    if not tree:
        return _export_xml_flat(df, template)

    records = df.to_dict(orient="records")

    def esc(s):
        return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    def render_node(node, row):
        tag = node.get("tag", "element")
        children = node.get("children", [])
        field_binding = node.get("fieldBinding")
        static_value = node.get("staticValue")

        attr_str = ""
        for a in node.get("attributes", []):
            val = str(row.get(a["fieldBinding"], "") or "") if a.get("fieldBinding") else str(a.get("staticValue", "") or "")
            attr_str += f' {a["name"]}="{esc(val)}"'

        if children:
            inner = "".join(render_node(c, row) for c in children)
            return f"<{tag}{attr_str}>{inner}</{tag}>"
        elif field_binding:
            return f"<{tag}{attr_str}>{esc(str(row.get(field_binding, '') or ''))}</{tag}>"
        elif static_value is not None:
            return f"<{tag}{attr_str}>{esc(str(static_value))}</{tag}>"
        else:
            return f"<{tag}{attr_str}/>"

    def find_repeating(node):
        if node.get("isRepeating"):
            return node
        for c in node.get("children", []):
            found = find_repeating(c)
            if found:
                return found
        return None

    repeating = find_repeating(tree)
    row_tag_id = repeating["id"] if repeating else None

    if repeating and row_tag_id != tree["id"]:
        row_xmls = [render_node(repeating, row) for row in records]
        rows_joined = "\n  ".join(row_xmls)

        def build_outer(node):
            tag = node.get("tag", "element")
            attr_str = ""
            for a in node.get("attributes", []):
                val = str(a.get("staticValue", "") or "")
                attr_str += f' {a["name"]}="{esc(val)}"'
            if node["id"] == row_tag_id:
                return rows_joined
            children = node.get("children", [])
            if children:
                inner = "\n  ".join(build_outer(c) for c in children)
                return f"<{tag}{attr_str}>\n  {inner}\n</{tag}>"
            return f"<{tag}{attr_str}/>"

        body = build_outer(tree)
    else:
        row_xmls = [render_node(tree, row) for row in records]
        body = "\n".join(row_xmls)

    xml_str = f'<?xml version="1.0" encoding="UTF-8"?>\n{body}'
    try:
        from xml.dom import minidom
        pretty = minidom.parseString(xml_str.encode("utf-8")).toprettyxml(indent="  ")
        # Fix double XML declaration
        pretty_lines = pretty.split("\n")
        if pretty_lines[0].startswith("<?xml") and pretty_lines[1].startswith("<?xml"):
            pretty_lines = pretty_lines[1:]
        return "\n".join(pretty_lines).encode("utf-8")
    except Exception:
        return xml_str.encode("utf-8")


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _indent_xml(xml_str: str) -> str:
    try:
        from xml.dom import minidom
        return minidom.parseString(xml_str.encode("utf-8")).toprettyxml(indent="  ")
    except Exception:
        return xml_str


def _export_xml_flat(df: pd.DataFrame, template: dict) -> bytes:
    """Legacy flat XML export."""
    root_tag = template.get("root", "root")
    row_tag = template.get("row", "row")
    fields_cfg = template.get("fields", [])

    root_el = ET.Element(root_tag)
    for _, record in df.iterrows():
        row_el = ET.SubElement(root_el, row_tag)
        sub_elements: Dict[str, ET.Element] = {}
        for fc in fields_cfg:
            src_field = fc.get("field")
            xml_path = fc.get("xmlPath", src_field)
            is_attr = fc.get("isAttribute", False)
            val = str(record.get(src_field, "") or "")
            if not xml_path:
                continue
            if is_attr:
                if "/@" in xml_path:
                    elem_name, attr_name = xml_path.split("/@", 1)
                    if elem_name not in sub_elements:
                        sub_elements[elem_name] = ET.SubElement(row_el, elem_name)
                    sub_elements[elem_name].set(attr_name, val)
                elif xml_path.startswith("@"):
                    row_el.set(xml_path[1:], val)
                else:
                    row_el.set(xml_path, val)
            else:
                parts = xml_path.split("/")
                parent = row_el
                for part in parts[:-1]:
                    if part not in sub_elements:
                        sub_elements[part] = ET.SubElement(parent, part)
                    parent = sub_elements[part]
                child = ET.SubElement(parent, parts[-1])
                child.text = val

    raw = ET.tostring(root_el, encoding="unicode")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ")
    pretty_lines = pretty.split("\n")
    if pretty_lines[0].startswith("<?xml"):
        pretty_lines[0] = '<?xml version="1.0" encoding="UTF-8"?>'
    return "\n".join(pretty_lines).encode("utf-8")


# ─── DB Write ─────────────────────────────────────────────────────────────────

def export_to_db(
    df: pd.DataFrame,
    conn_obj,
    table: str,
    write_mode: str,
    key_columns: Optional[List[str]] = None,
) -> Dict[str, Any]:
    from sqlalchemy import create_engine, text, inspect
    from app.services.db_service import get_engine_str
    import logging
    log = logging.getLogger(__name__)

    rows_affected = 0

    try:
        connect_args = {}
        if conn_obj.db_type == "mssql":
            connect_args = {"timeout": 30, "login_timeout": 10}
        elif conn_obj.db_type in ("mysql", "postgresql"):
            connect_args = {"connect_timeout": 10}

        engine = create_engine(get_engine_str(conn_obj), connect_args=connect_args)
        log.info(f"export_to_db: engine={engine.url}, table={table}, mode={write_mode}, rows={len(df)}, cols={list(df.columns)}")

        # Spalten gegen Zieltabelle abgleichen
        try:
            # Schema-Namen trennen: "dbo.Tabelle" → schema="dbo", table_name="Tabelle"
            schema, tname = (table.split(".", 1) + [None])[:2]
            if tname is None:
                schema, tname = None, schema
            insp = inspect(engine)
            db_cols = {c["name"] for c in insp.get_columns(tname, schema=schema)}
            log.info(f"export_to_db: DB-Spalten={db_cols}")
            common_cols = [c for c in df.columns if c in db_cols]
            log.info(f"export_to_db: gemeinsame Spalten={common_cols}")
            if not common_cols:
                raise ValueError(f"Keine übereinstimmenden Spalten. DataFrame: {list(df.columns)}, Tabelle: {db_cols}")
            df = df[common_cols]
        except ValueError:
            raise
        except Exception as col_err:
            log.warning(f"export_to_db: Spalten-Abgleich fehlgeschlagen ({col_err}), verwende alle DataFrame-Spalten")

        with engine.begin() as con:
            if write_mode == "truncate_insert":
                con.execute(text(f"DELETE FROM {table}"))

            if write_mode in ("insert", "truncate_insert"):
                if conn_obj.db_type == "mssql":
                    # Direktes INSERT via parameterisiertes SQL – kein to_sql
                    cols = list(df.columns)
                    col_list = ", ".join(f"[{c}]" for c in cols)
                    param_list = ", ".join(f":{c}" for c in cols)
                    sql = text(f"INSERT INTO {table} ({col_list}) VALUES ({param_list})")
                    records = df.where(df.notna(), other=None).to_dict(orient="records")
                    for chunk_start in range(0, len(records), 500):
                        chunk = records[chunk_start:chunk_start + 500]
                        con.execute(sql, chunk)
                    rows_affected = len(df)
                else:
                    df.to_sql(table, con=con, if_exists="append", index=False,
                              method="multi", chunksize=200)
                    rows_affected = len(df)

            elif write_mode in ("update", "upsert") and key_columns:
                insp2 = inspect(engine)
                schema2, tname2 = (table.split(".", 1) + [None])[:2]
                if tname2 is None: schema2, tname2 = None, schema2
                db_cols2 = [c["name"] for c in insp2.get_columns(tname2, schema=schema2)]
                non_key_cols = [c for c in df.columns if c in db_cols2 and c not in key_columns]

                for _, row in df.iterrows():
                    row_dict = {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()}
                    where_clause = " AND ".join([f"[{k}] = :{k}" for k in key_columns])

                    if write_mode == "update":
                        set_clause = ", ".join([f"[{c}] = :set_{c}" for c in non_key_cols])
                        params = {f"set_{c}": row_dict.get(c) for c in non_key_cols}
                        params.update({k: row_dict.get(k) for k in key_columns})
                        result = con.execute(text(f"UPDATE {table} SET {set_clause} WHERE {where_clause}"), params)
                        rows_affected += result.rowcount
                    elif write_mode == "upsert":
                        check_params = {k: row_dict.get(k) for k in key_columns}
                        exists = con.execute(text(f"SELECT 1 FROM {table} WHERE {where_clause}"), check_params).fetchone()
                        if exists:
                            if non_key_cols:
                                set_clause = ", ".join([f"[{c}] = :set_{c}" for c in non_key_cols])
                                params = {f"set_{c}": row_dict.get(c) for c in non_key_cols}
                                params.update(check_params)
                                con.execute(text(f"UPDATE {table} SET {set_clause} WHERE {where_clause}"), params)
                        else:
                            col_list = ", ".join(f"[{k}]" for k in row_dict)
                            val_list = ", ".join(f":{k}" for k in row_dict)
                            con.execute(text(f"INSERT INTO {table} ({col_list}) VALUES ({val_list})"), row_dict)
                        rows_affected += 1
            else:
                raise ValueError(f"Unbekannter write_mode oder fehlende key_columns: {write_mode}")

        log.info(f"export_to_db: ✓ {rows_affected} Zeilen geschrieben")

    except Exception as e:
        log.error(f"export_to_db: FEHLER: {e}")
        raise RuntimeError(f"DB-Export fehlgeschlagen ({table}): {str(e)[:800]}")

    return {"rows_affected": rows_affected, "mode": write_mode, "table": table, "errors": []}
