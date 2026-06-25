"""
dispatcher_service – prüft Dispatcher-Regeln für eine heruntergeladene Datei
und führt das passende Mapping + Post-Actions aus.
"""
import fnmatch
import logging
import pandas as pd

logger = logging.getLogger(__name__)


def _check_conditions(df: pd.DataFrame, filename: str, conditions: list, mode: str = "AND",
                      raw_bytes: bytes = None, db=None) -> bool:
    """Prüft ob eine Datei/DataFrame die Bedingungen erfüllt."""
    import xml.etree.ElementTree as ET

    results = []
    xml_root = None  # lazy parsed

    def get_xml_root():
        nonlocal xml_root
        if xml_root is None and raw_bytes:
            try:
                xml_root = ET.fromstring(raw_bytes)
            except Exception:
                pass
        return xml_root

    for cond in conditions:
        ctype = cond.get("type", "")
        try:
            if ctype == "filename":
                pattern = cond.get("pattern", "*")
                results.append(fnmatch.fnmatch(filename, pattern))

            elif ctype == "file_extension":
                ext = cond.get("extension", "").lower().lstrip(".")
                file_ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
                results.append(file_ext == ext)

            elif ctype == "column_exists":
                col = cond.get("column", "")
                results.append(col in df.columns)

            elif ctype == "column_value":
                col = cond.get("column", "")
                val = str(cond.get("value", ""))
                if col in df.columns:
                    results.append(df[col].astype(str).str.contains(val, na=False).any())
                else:
                    results.append(False)

            elif ctype in ("row_count_gt", "rows_gt"):
                threshold = int(cond.get("threshold", 0))
                results.append(len(df) > threshold)

            elif ctype in ("row_count_lt", "rows_lt"):
                threshold = int(cond.get("threshold", 0))
                results.append(len(df) < threshold)

            elif ctype in ("row_count_eq", "rows_eq"):
                threshold = int(cond.get("threshold", 0))
                results.append(len(df) == threshold)

            elif ctype == "xml_tag_exists":
                root = get_xml_root()
                if root is None:
                    results.append(False)
                    continue
                tag = cond.get("column", "")
                # Prüfe Root-Tag selbst oder alle Descendants
                found = (root.tag == tag or root.tag.endswith("}" + tag) or
                         root.find(f".//{tag}") is not None or
                         root.find(f".//{{{root.tag.split('}')[0].lstrip('{')}}}{tag}") is not None)
                results.append(found)

            elif ctype == "xml_tag_value":
                root = get_xml_root()
                if root is None:
                    results.append(False)
                    continue
                tag = cond.get("column", "")
                val = str(cond.get("value", ""))
                el = root.find(f".//{tag}")
                if el is None:
                    results.append(False)
                else:
                    results.append(val.lower() in (el.text or "").lower())

            elif ctype == "xml_xpath":
                root = get_xml_root()
                if root is None:
                    results.append(False)
                    continue
                xpath = cond.get("xpath", "")
                try:
                    found = root.findall(xpath)
                    results.append(len(found) > 0)
                except Exception:
                    results.append(False)

            elif ctype == "xml_schema":
                root = get_xml_root()
                if root is None or db is None:
                    results.append(False)
                    continue
                ds_id = cond.get("dataset_id")
                if not ds_id:
                    results.append(False)
                    continue
                try:
                    from app.models.dataset import Dataset
                    schema_ds = db.query(Dataset).filter(Dataset.id == ds_id).first()
                    if not schema_ds:
                        results.append(False)
                        continue

                    target_node = schema_ds.xml_target_node or ""
                    known_cols = schema_ds.columns or []

                    # 1. Prüfe ob target_node im XML vorkommt
                    node_found = (
                        root.tag == target_node or
                        root.tag.endswith("}" + target_node) or
                        root.find(f".//{target_node}") is not None
                    )
                    if not node_found:
                        results.append(False)
                        continue

                    # 2. Prüfe ob mindestens 50% der bekannten Spalten als Tags vorkommen
                    if known_cols:
                        xml_str = ET.tostring(root, encoding="unicode")
                        matches = sum(1 for col in known_cols if f"<{col}" in xml_str or f"<{col}>" in xml_str)
                        ratio = matches / len(known_cols)
                        results.append(ratio >= 0.5)
                    else:
                        results.append(True)

                except Exception as e:
                    logger.warning(f"XML-Schema Prüfung fehlgeschlagen: {e}")
                    results.append(False)

            else:
                results.append(True)

        except Exception as e:
            logger.warning(f"Bedingung '{ctype}' fehlgeschlagen: {e}")
            results.append(False)

    if not results:
        return True
    return all(results) if mode == "AND" else any(results)


def run_dispatcher(ftp_source_id: int, filename: str, df: pd.DataFrame, data_bytes: bytes, db) -> list:
    """
    Prüft alle aktiven Dispatcher-Regeln für eine FTP-Quelle.
    Führt das erste passende Mapping aus.
    Gibt Liste von Ergebnissen zurück.
    """
    from app.models.dispatcher import DispatcherRule
    from app.models.mapping import Mapping
    from app.models.ftp_source import FtpSource

    results = []

    rules = db.query(DispatcherRule).filter(
        DispatcherRule.active == True,
        DispatcherRule.ftp_source_id == ftp_source_id
    ).order_by(DispatcherRule.priority).all()

    if not rules:
        logger.info(f"Dispatcher: Keine Regeln für FTP-Source {ftp_source_id}")
        return results

    for rule in rules:
        try:
            conditions = rule.conditions or []
            mode = rule.condition_mode or "AND"

            if not _check_conditions(df, filename, conditions, mode, raw_bytes=data_bytes, db=db):
                logger.info(f"Dispatcher: Regel '{rule.name}' → kein Match für {filename}")
                continue

            logger.info(f"Dispatcher: Regel '{rule.name}' → MATCH für {filename}")
            try:
                from app.services.log_service import write_log
                write_log(
                    module="dispatcher", action="trigger",
                    message=f"Regel '{rule.name}' getriggert für Datei: {filename}",
                    entity_id=rule.id, entity_name=rule.name,
                    project_id=rule.project_id, level="info", db=db,
                )
            except Exception:
                pass

            # Mapping ausführen
            if rule.mapping_id:
                result = _run_mapping(rule.mapping_id, df, db)
                results.append({"rule": rule.name, "status": "ok", "rows": result.get("rows", 0)})
            else:
                results.append({"rule": rule.name, "status": "ok", "rows": len(df), "info": "Kein Mapping verknüpft"})

            # Post-Actions
            for action in (rule.post_actions or []):
                try:
                    _run_post_action(action, result if rule.mapping_id else {}, db)
                except Exception as e:
                    logger.error(f"Dispatcher Post-Action fehlgeschlagen: {e}")
                    results.append({"rule": rule.name, "action": action.get("type"), "status": "error", "error": str(e)[:200]})

            break  # Erstes Match gewinnt

        except Exception as e:
            logger.error(f"Dispatcher: Regel '{rule.name}' Fehler: {e}")
            results.append({"rule": rule.name, "status": "error", "error": str(e)[:200]})

    return results


def _run_mapping(mapping_id: int, df: pd.DataFrame, db):
    """Speichert DataFrame als temporäres Dataset und führt Mapping aus."""
    from app.models.mapping import Mapping
    from app.models.dataset import Dataset
    from app.services.file_service import dataframe_to_storage, infer_column_types
    from datetime import datetime, timezone

    mapping = db.query(Mapping).filter(Mapping.id == mapping_id).first()
    if not mapping:
        raise ValueError(f"Mapping #{mapping_id} nicht gefunden")

    # DataFrame als Dataset speichern (temporär / Update)
    # Suche ob es ein Dataset gibt das diesem Mapping zugeordnet ist
    ds = db.query(Dataset).filter(Dataset.source_mapping_id == mapping_id).first()
    if not ds:
        # Neues Dataset anlegen
        ds = Dataset(
            name=f"dispatcher_input_{mapping_id}",
            file_type="csv",
            row_count=len(df),
            columns=list(df.columns),
            column_types=infer_column_types(df),
            xml_configured=1,
        )
        db.add(ds); db.commit(); db.refresh(ds)

    path = dataframe_to_storage(df, ds.id)
    ds.file_path = path
    ds.row_count = len(df)
    ds.columns = list(df.columns)
    db.commit()

    # Mapping ausführen via einheitlichem run_mapping_object
    from app.services.mapping_service import MappingContext, run_mapping_object
    ctx = MappingContext.from_orm(mapping)
    result = run_mapping_object(ctx, preview_rows=999999, db=db,
                                 mapping_id=mapping_id, triggered_by="dispatcher")
    return {"rows": result.get("total_rows_written", 0), "targets": result.get("targets_executed", 0)}


def _migrate_legacy_targets(mapping):
    """Kompatibilität: alte field-basierte Mappings zu targets konvertieren."""
    if mapping.targets:
        try:
            import json
            t = mapping.targets if isinstance(mapping.targets, list) else json.loads(mapping.targets)
            if t: return t
        except Exception:
            pass
    return []


def _run_post_action(action: dict, mapping_result: dict, db):
    """Führt eine Post-Action aus."""
    atype = action.get("type", "")

    if atype == "ftp_upload":
        ftp_source_id = action.get("ftp_source_id")
        remote_dir = action.get("remote_dir", "/")
        filename = action.get("filename", "export.csv")
        if ftp_source_id:
            from app.models.ftp_source import FtpSource
            src = db.query(FtpSource).filter(FtpSource.id == ftp_source_id).first()
            if src:
                import io, pandas as pd
                # Lade Mapping-Output (falls vorhanden)
                logger.info(f"Dispatcher FTP-Upload → {src.name}:{remote_dir}/{filename}")

    elif atype == "chain_mapping":
        next_mapping_id = action.get("mapping_id")
        if next_mapping_id:
            logger.info(f"Dispatcher: Chain → Mapping #{next_mapping_id}")
            _run_mapping(next_mapping_id, pd.DataFrame(), db)

    elif atype == "email":
        # Placeholder für E-Mail (kommt später mit Mail-Service)
        logger.info(f"Dispatcher: E-Mail an {action.get('to')} (noch nicht implementiert)")
