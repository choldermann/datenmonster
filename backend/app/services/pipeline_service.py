"""
pipeline_service – führt eine Pipeline sequenziell aus.
"""
import logging
import traceback
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def run_pipeline(pipeline, db) -> dict:
    """Führt alle Nodes der Pipeline in topologischer Reihenfolge aus."""
    from app.services.db_logger import log_pipeline_start, log_pipeline_end, log_node_error, log

    nodes = {n["id"]: n for n in (pipeline.nodes or [])}
    connections = pipeline.connections or []
    results = {}
    errors = []

    # Topologische Reihenfolge
    in_degree = {nid: 0 for nid in nodes}
    for c in connections:
        in_degree[c["to_node"]] = in_degree.get(c["to_node"], 0) + 1

    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    order = []
    while queue:
        nid = queue.pop(0)
        order.append(nid)
        for c in connections:
            if c["from_node"] == nid:
                in_degree[c["to_node"]] -= 1
                if in_degree[c["to_node"]] == 0:
                    queue.append(c["to_node"])

    # Pipeline-Start loggen
    start_time = log_pipeline_start(db, pipeline)
    logger.info(f"Pipeline '{pipeline.name}': {len(order)} Nodes in Reihenfolge")

    skipped = set()  # Node-IDs die wegen Dispatcher-Branch übersprungen werden

    try:
        for nid in order:
            node = nodes.get(nid)
            if not node:
                continue

            # Branch-Routing: Node überspringen wenn Dispatcher ihn ausgeschlossen hat
            if nid in skipped:
                results[nid] = {"status": "skipped", "message": "Übersprungen (Dispatcher-Bedingung nicht erfüllt)"}
                for c in connections:
                    if c["from_node"] == nid:
                        skipped.add(c["to_node"])
                continue

            ntype = node.get("type", "")
            config = node.get("config", {})
            node_start = datetime.now(timezone.utc)
            logger.info(f"  → Node [{ntype}] {nid}")

            try:
                if ntype == "trigger":
                    results[nid] = {"status": "ok", "output": "triggered"}
                    log(db, "info", "pipeline_service", "node_trigger",
                        "Trigger-Node ausgeführt",
                        entity_id=pipeline.id, entity_name=pipeline.name,
                        project_id=getattr(pipeline, "project_id", None))

                elif ntype == "ftp":
                    ftp_source_id = config.get("ftp_source_id")
                    if ftp_source_id:
                        from app.models.ftp_source import FtpSource
                        from app.services.ftp_service import run_ftp_sync
                        src = db.query(FtpSource).filter(FtpSource.id == ftp_source_id).first()
                        if src:
                            result = run_ftp_sync(src, db)
                            rows = result.get("rows", 0)
                            results[nid] = {"status": "ok", "rows": rows,
                                            "files": result.get("files_processed", [])}
                            log(db, "success", "pipeline_service", "node_ftp",
                                f"FTP-Sync: {rows} Zeilen importiert",
                                entity_id=pipeline.id, entity_name=pipeline.name,
                                project_id=getattr(pipeline, "project_id", None),
                                rows_processed=rows,
                                details={"ftp_source": src.name, "files": result.get("files_processed", [])})
                        else:
                            msg = f"FTP-Quelle {ftp_source_id} nicht gefunden"
                            results[nid] = {"status": "error", "message": msg}
                            log(db, "error", "pipeline_service", "node_ftp",
                                msg, entity_id=pipeline.id, entity_name=pipeline.name,
                                project_id=getattr(pipeline, "project_id", None),
                                details={"ftp_source_id": ftp_source_id})

                elif ntype == "dispatcher":
                    conditions = config.get("conditions", [])
                    mode = config.get("condition_mode", "AND")
                    import pandas as pd
                    from app.services.dispatcher_service import _check_conditions
                    prev_data = _get_prev_data(nid, connections, results)
                    if "rows" in prev_data and "df" not in prev_data:
                        df = pd.DataFrame(index=range(prev_data.get("rows", 0)))
                    else:
                        df = prev_data.get("df", pd.DataFrame())
                    filename = prev_data.get("filename", "")
                    match = _check_conditions(df, filename, conditions, mode, db=db)
                    results[nid] = {"status": "ok", "match": match,
                                    "message": f"Bedingung {'erfüllt' if match else 'nicht erfüllt'}"}
                    # Branch-Routing: Nodes auf dem nicht genommenen Pfad überspringen
                    dropped_port = "no_match" if match else "match"
                    for c in connections:
                        if c["from_node"] == nid and c.get("from_port") == dropped_port:
                            skipped.add(c["to_node"])

                elif ntype == "mapping":
                    mapping_id = config.get("mapping_id")
                    if mapping_id:
                        from app.models.mapping import Mapping
                        from app.services.mapping_service import MappingContext, run_mapping_object
                        mapping = db.query(Mapping).filter(Mapping.id == mapping_id).first()
                        if mapping:
                            ctx = MappingContext.from_orm(mapping)
                            if not ctx.targets:
                                results[nid] = {"status": "warning", "message": "Keine Ziele definiert"}
                                log(db, "warning", "pipeline_service", "node_mapping",
                                    f"Mapping '{mapping.name}': Keine Ziele definiert",
                                    entity_id=pipeline.id, entity_name=pipeline.name,
                                    project_id=getattr(pipeline, "project_id", None),
                                    details={"mapping_id": mapping_id, "mapping_name": mapping.name})
                            else:
                                result = run_mapping_object(
                                    ctx, preview_rows=999999, db=db,
                                    mapping_id=mapping_id, mapping_name=mapping.name,
                                    project_id=mapping.project_id, triggered_by="pipeline",
                                )
                                rows = result.get("total_rows_written", 0)
                                t_errors = [t["error"] for t in result.get("targets_results", [])
                                            if t.get("status") == "error" and t.get("error")]
                                status = "ok" if not t_errors else "warning"
                                results[nid] = {"status": status, "rows": rows, "errors": t_errors}
                                duration_ms = int((datetime.now(timezone.utc) - node_start).total_seconds() * 1000)
                                log(db, "success" if not t_errors else "warning",
                                    "pipeline_service", "node_mapping",
                                    f"Mapping '{mapping.name}': {rows} Zeilen geschrieben" +
                                    (f" ({len(t_errors)} Fehler)" if t_errors else ""),
                                    entity_id=pipeline.id, entity_name=pipeline.name,
                                    project_id=getattr(pipeline, "project_id", None),
                                    rows_processed=rows, duration_ms=duration_ms,
                                    details={"mapping_id": mapping_id, "mapping_name": mapping.name,
                                             "target_errors": t_errors})
                        else:
                            msg = f"Mapping {mapping_id} nicht gefunden"
                            results[nid] = {"status": "error", "message": msg}
                            log(db, "error", "pipeline_service", "node_mapping",
                                msg, entity_id=pipeline.id, entity_name=pipeline.name,
                                project_id=getattr(pipeline, "project_id", None),
                                details={"mapping_id": mapping_id})

                elif ntype == "email":
                    to = config.get("to", "")
                    subject = config.get("subject", "Pipeline abgeschlossen")
                    body = config.get("body", "")
                    send_on = config.get("send_on", "always")
                    prev_data = _get_prev_data(nid, connections, results)
                    prev_status = prev_data.get("status", "ok")
                    if not prev_data and results:
                        statuses = [r.get("status", "ok") for r in results.values()]
                        prev_status = "error" if "error" in statuses else "warning" if "warning" in statuses else "ok"
                    should_send = (
                        send_on == "always" or
                        (send_on == "success" and prev_status == "ok") or
                        (send_on == "error" and prev_status == "error")
                    )
                    if should_send and to:
                        from app.services.email_service import send_email
                        send_email(to=to, cc=config.get("cc") or None,
                                   bcc=config.get("bcc") or None,
                                   subject=subject, body=body, db=db)
                        results[nid] = {"status": "ok", "message": f"E-Mail an {to} gesendet"}
                        log(db, "success", "pipeline_service", "node_email",
                            f"E-Mail an {to} gesendet",
                            entity_id=pipeline.id, entity_name=pipeline.name,
                            project_id=getattr(pipeline, "project_id", None),
                            details={"to": to, "subject": subject})
                    else:
                        results[nid] = {"status": "ok", "message": "E-Mail übersprungen"}

                elif ntype == "condition":
                    operator = config.get("operator", "gt")
                    value = config.get("value", "0")
                    prev_data = _get_prev_data(nid, connections, results)
                    prev_rows = prev_data.get("rows", 0) if prev_data else 0
                    try:
                        v = float(value)
                        pv = float(prev_rows)
                        met = {"gt": pv > v, "lt": pv < v, "gte": pv >= v,
                               "lte": pv <= v, "eq": pv == v, "neq": pv != v}.get(operator, True)
                    except Exception:
                        met = bool(prev_rows)
                    results[nid] = {"status": "ok", "condition_met": met,
                                    "message": f"Bedingung {'erfüllt' if met else 'nicht erfüllt'}"}
                    # Branch-Routing: Nodes auf dem nicht genommenen Pfad überspringen
                    dropped_port = "no" if met else "yes"
                    for c in connections:
                        if c["from_node"] == nid and c.get("from_port") == dropped_port:
                            skipped.add(c["to_node"])

                elif ntype == "rest_fetch":
                    from app.models.rest_source import RestSource
                    from app.services.rest_service import fetch_rest_source
                    src_id = config.get("rest_source_id")
                    src_name = config.get("dataset_name", "")
                    src = None
                    if src_id:
                        src = db.query(RestSource).filter(RestSource.id == src_id).first()
                    elif src_name:
                        src = db.query(RestSource).filter(RestSource.name == src_name).first()
                    if not src:
                        msg = f"REST-Quelle '{src_id or src_name}' nicht gefunden"
                        results[nid] = {"status": "error", "message": msg}
                        log(db, "error", "pipeline_service", "node_rest_fetch",
                            msg, entity_id=pipeline.id, entity_name=pipeline.name,
                            project_id=getattr(pipeline, "project_id", None),
                            details={"rest_source_id": src_id, "rest_source_name": src_name})
                    else:
                        prev = _get_prev_data(nid, connections, results)
                        prev_df = prev.get("df")
                        src_to_use = src
                        if prev_df is not None and not prev_df.empty:
                            row = prev_df.iloc[0].to_dict()
                            def _inject(text):
                                if not isinstance(text, str):
                                    return text
                                for k, v in row.items():
                                    text = text.replace("{{" + str(k) + "}}", str(v))
                                return text
                            class _Patched:
                                pass
                            patched = _Patched()
                            for attr in ["url", "method", "headers", "query_params", "body_type",
                                         "body_content", "auth_type", "auth_config", "data_path",
                                         "flatten", "pagination", "dataset_id", "dataset_mode"]:
                                val = getattr(src, attr, None)
                                if isinstance(val, str):
                                    val = _inject(val)
                                elif isinstance(val, dict):
                                    val = {k: _inject(v) for k, v in val.items()}
                                setattr(patched, attr, val)
                            src_to_use = patched
                        import pandas as _pd
                        try:
                            df = fetch_rest_source(src_to_use)
                        except Exception as e:
                            results[nid] = {"status": "error", "message": str(e)[:200]}
                            log(db, "error", "pipeline_service", "node_rest_fetch",
                                f"REST-Fetch fehlgeschlagen: {str(e)[:200]}",
                                entity_id=pipeline.id, entity_name=pipeline.name,
                                project_id=getattr(pipeline, "project_id", None),
                                details={"rest_source": src.name, "url": getattr(src, "url", ""),
                                         "exception_type": type(e).__name__,
                                         "exception_message": str(e),
                                         "traceback": traceback.format_exc()})
                            continue
                        rows = len(df)
                        if getattr(src_to_use, "dataset_id", None) and not df.empty:
                            try:
                                from app.services.file_service import dataframe_to_storage
                                dataframe_to_storage(df, src_to_use.dataset_id)
                            except Exception as e:
                                logger.warning(f"Dataset-Schreiben fehlgeschlagen: {e}")
                        results[nid] = {"status": "ok", "rows": rows, "df": df}
                        log(db, "success", "pipeline_service", "node_rest_fetch",
                            f"REST-Fetch '{src.name}': {rows} Zeilen",
                            entity_id=pipeline.id, entity_name=pipeline.name,
                            project_id=getattr(pipeline, "project_id", None),
                            rows_processed=rows,
                            details={"rest_source": src.name})

                elif ntype == "business_insights":
                    dataset_id  = config.get("dataset_id")
                    semantic    = config.get("semantic", {})
                    comparison  = config.get("comparison", {"mode": "mom"})
                    modules     = config.get("modules")
                    out_name    = config.get("output_name", "Insights-Ergebnis")

                    import pandas as pd
                    from app.services.insight_engine import compute_insights
                    from app.services.file_service import _load_parquet, dataframe_to_storage
                    from app.models.dataset import Dataset

                    # DataFrame aus vorheriger Node ODER konfiguriertem Dataset
                    prev_data = _get_prev_data(nid, connections, results)
                    df = prev_data.get("df")
                    if df is None or df.empty:
                        if dataset_id:
                            try:
                                df = _load_parquet(dataset_id)
                            except Exception as e:
                                results[nid] = {"status": "error", "message": f"Dataset {dataset_id} nicht ladbar: {e}"}
                                log(db, "error", "pipeline_service", "node_business_insights",
                                    f"Dataset {dataset_id} nicht ladbar: {e}",
                                    entity_id=pipeline.id, entity_name=pipeline.name,
                                    project_id=getattr(pipeline, "project_id", None))
                                continue
                        else:
                            results[nid] = {"status": "error", "message": "Kein Dataset und kein Vorgänger-DataFrame verfügbar"}
                            continue

                    if not semantic:
                        results[nid] = {"status": "error", "message": "Kein Semantic-Mapping konfiguriert"}
                        continue

                    findings_df = compute_insights(df, semantic, comparison, modules)
                    rows = len(findings_df)

                    # Findings als neues Dataset speichern
                    out_ds = Dataset(
                        name=out_name,
                        file_type="insights_output",
                        project_id=getattr(pipeline, "project_id", None),
                        columns=findings_df.columns.tolist(),
                        column_types={},
                        row_count=rows,
                    )
                    db.add(out_ds)
                    db.commit()
                    db.refresh(out_ds)
                    dataframe_to_storage(findings_df, out_ds.id)

                    results[nid] = {"status": "ok", "rows": rows, "df": findings_df,
                                    "dataset_id": out_ds.id, "dataset_name": out_name}
                    log(db, "success", "pipeline_service", "node_business_insights",
                        f"Business Insights: {rows} Findings → Dataset '{out_name}' (ID {out_ds.id})",
                        entity_id=pipeline.id, entity_name=pipeline.name,
                        project_id=getattr(pipeline, "project_id", None),
                        rows_processed=rows,
                        details={"output_dataset_id": out_ds.id, "modules": modules})

                elif ntype == "ftp_upload":
                    ftp_source_id = config.get("ftp_source_id")
                    remote_dir = config.get("remote_dir", "/")
                    filename = config.get("filename", "export.csv")
                    filename = filename.replace("{datum}", datetime.now(timezone.utc).strftime("%Y%m%d"))
                    if not ftp_source_id:
                        results[nid] = {"status": "error", "message": "Kein FTP-Ziel konfiguriert"}
                    else:
                        from app.models.ftp_source import FtpSource
                        from app.services.ftp_service import upload_file_ftp_source
                        import pandas as pd
                        src = db.query(FtpSource).filter(FtpSource.id == ftp_source_id).first()
                        if not src:
                            results[nid] = {"status": "error", "message": f"FTP-Quelle {ftp_source_id} nicht gefunden"}
                        else:
                            prev_data = _get_prev_data(nid, connections, results)
                            df = prev_data.get("df")
                            if df is None:
                                df = pd.DataFrame(index=range(prev_data.get("rows", 0)))
                            row_count = upload_file_ftp_source(src, df, remote_dir, filename)
                            results[nid] = {"status": "ok", "message": f"{filename} hochgeladen ({row_count} Zeilen)"}
                            log(db, "success", "pipeline_service", "node_ftp_upload",
                                f"FTP-Upload: {filename} → {src.name}:{remote_dir}",
                                entity_id=pipeline.id, entity_name=pipeline.name,
                                project_id=getattr(pipeline, "project_id", None),
                                rows_processed=row_count,
                                details={"ftp_source": src.name, "remote_dir": remote_dir, "filename": filename})

            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f"  ✗ Node [{ntype}] {nid}: {e}\n{tb}")
                errors.append(f"Node {ntype}: {str(e)[:300]}")
                results[nid] = {"status": "error", "message": str(e)[:300]}
                # Strukturierter Fehler-Log mit vollem Stacktrace
                log_node_error(db, pipeline, node, e)
                if config.get("on_error") == "stop":
                    break

        # Pipeline-Ende loggen
        clean_results = {nid: {k: v for k, v in r.items() if k != "df"}
                         for nid, r in results.items()}
        final_result = {"results": clean_results, "errors": errors,
                        "nodes_executed": len(results)}
        log_pipeline_end(db, pipeline, final_result, start_time)
        return final_result

    except Exception as e:
        # Unerwarteter Fehler ausserhalb der Node-Schleife
        log_pipeline_end(db, pipeline, {}, start_time, exc=e)
        raise


def _get_prev_data(node_id, connections, results):
    """Gibt Daten des vorherigen Nodes zurück."""
    import pandas as pd
    for c in connections:
        if c["to_node"] == node_id:
            return results.get(c["from_node"], {})
    return {}
