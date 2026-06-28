"""
Schreibt Mapping-Ergebnisse in verschiedene Zieltypen:
Dataset, DB, Plugin, CSV/XLSX/JSON/XML.
"""
import logging

logger = logging.getLogger(__name__)

_BUILTIN_TARGET_TYPES = {"csv", "xlsx", "json", "xml", "db", "dataset"}


def _is_plugin_target(t_type: str) -> bool:
    """True wenn t_type kein eingebauter Typ ist und in der CapabilityRegistry als Ziel registriert."""
    if t_type in _BUILTIN_TARGET_TYPES:
        return False
    from app.plugins.registry import registry as _registry
    return _registry.is_plugin_target(t_type)


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
            target_name = target.get("name") or "Mapping-Output"
            existing_name = thread_db.query(Dataset).filter(Dataset.name == target_name).first()
            if existing_name:
                if existing_name.source_mapping_id == mapping_id:
                    ds = existing_name
                else:
                    raise ValueError(f"Ein Dataset mit dem Namen '{target_name}' existiert bereits. Bitte anderen Namen wählen.")
            elif mapping_id and not existing_name:
                pass
            if ds:
                col_types = ds.column_types or {}

                if write_mode == "append" and getattr(ds, "file_path", None):
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
                    import json, os as _os
                    key_cols = [col for col, info in col_types.items()
                                if info.get("is_primary") and not info.get("autoincrement")]
                    if not key_cols:
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
                        existing_by_key = {}
                        for row in existing:
                            k = tuple(str(row.get(c, "")) for c in key_cols)
                            existing_by_key[k] = row
                        for row in new_records:
                            k = tuple(str(row.get(c, "")) for c in key_cols)
                            existing_by_key[k] = row
                        df = _pd.DataFrame(list(existing_by_key.values()))
                    else:
                        logger.warning("Upsert ohne Primary Keys – fallback auf replace")

                ds.row_count = len(df)
                ds.columns = list(df.columns)
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

    elif _is_plugin_target(t_type):
        from app.plugins.registry import registry as _registry
        plugin = _registry.get_target(t_type)
        if not plugin:
            raise ValueError(f"Plugin-Ziel '{t_type}' nicht in Registry")
        plugin_config = opts.get("plugin_config") or {}
        rows = df.to_dict("records")
        result = plugin.write(rows, plugin_config)
        errors = result.get("errors") or []
        if errors and not result.get("written"):
            raise ValueError(f"Plugin-Schreibfehler: {'; '.join(str(e) for e in errors)}")
        logger.info(f"  Plugin-Ziel '{t_type}': {result.get('written', len(rows))} Zeilen, "
                    f"entry_stamp={result.get('entry_stamp', '-')}, mode={result.get('mode', '-')}")

    else:
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
