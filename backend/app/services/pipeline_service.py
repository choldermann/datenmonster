"""
pipeline_service – führt eine Pipeline sequenziell aus.
"""
import logging
import traceback
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _enrich_debug_step(result: dict, node: dict, ntype: str, node_start) -> None:
    """Ergänzt ein Node-Ergebnis um einheitliche Trace-Felder (Typ, Label, Dauer)."""
    result.setdefault("type", ntype)
    lbl = node.get("label") or (node.get("config") or {}).get("label") or ntype
    result.setdefault("label", lbl)
    result["duration_ms"] = int((datetime.now(timezone.utc) - node_start).total_seconds() * 1000)


def run_pipeline(pipeline, db, debug: bool = False, dry_run: bool = False) -> dict:
    """
    Führt alle Nodes der Pipeline in topologischer Reihenfolge aus.

    debug=True:   reiche Trace-Erfassung (Dauer, Sample, Mapping-Sub-Trace, order).
    dry_run=True: Nodes mit echten Seiteneffekten (Mapping-Write, E-Mail, FTP,
                  REST/Insights-Persistenz) werden simuliert statt ausgeführt;
                  Mappings laufen im Preview ohne Schreiben.
    """
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

            # Dry-Run: Nodes mit echten Seiteneffekten simulieren statt ausführen.
            # (Mapping wird NICHT hier abgekürzt – es läuft weiter unten im Preview ohne Schreiben.)
            if dry_run and ntype in ("email", "ftp", "ftp_upload", "rest_fetch", "business_insights"):
                results[nid] = {"status": "ok", "dry_run": True,
                                "message": f"{ntype}: im Dry-Run simuliert (nicht ausgeführt)"}
                _enrich_debug_step(results[nid], node, ntype, node_start)
                continue

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
                                _sub_trace = [] if debug else None
                                result = run_mapping_object(
                                    ctx, preview_rows=(100 if dry_run else 999999), db=db,
                                    mapping_id=mapping_id, mapping_name=mapping.name,
                                    project_id=mapping.project_id,
                                    triggered_by="pipeline-debug" if dry_run else "pipeline",
                                    _debug_trace=_sub_trace,
                                )
                                if dry_run:
                                    # Preview schreibt nicht: Zeilen aus 'total', Fehler aus 'errors'
                                    rows = result.get("total", len(result.get("rows", [])))
                                    t_errors = result.get("errors", [])
                                else:
                                    rows = result.get("total_rows_written", 0)
                                    t_errors = [t["error"] for t in result.get("targets_results", [])
                                                if t.get("status") == "error" and t.get("error")]
                                status = "ok" if not t_errors else "warning"
                                results[nid] = {"status": status, "rows": rows, "errors": t_errors}
                                if _sub_trace is not None:
                                    results[nid]["sub_trace"] = _sub_trace
                                if dry_run:
                                    results[nid]["dry_run"] = True
                                duration_ms = int((datetime.now(timezone.utc) - node_start).total_seconds() * 1000)
                                _verb = "im Preview (Dry-Run, nicht geschrieben)" if dry_run else "geschrieben"
                                log(db, "success" if not t_errors else "warning",
                                    "pipeline_service", "node_mapping",
                                    f"Mapping '{mapping.name}': {rows} Zeilen {_verb}" +
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
                        import pandas as _pd

                        # „Für jede Zeile": bei einer Kette Liste → Detail wird der
                        # Request einmal pro Zeile des Vorgängers ausgeführt. Ohne das
                        # bliebe es bei der ersten Zeile – für den häufigsten Fall
                        # (Liste holen, dann Details je Element) unbrauchbar.
                        for_each = bool(config.get("for_each"))
                        max_zeilen = int(config.get("for_each_max") or 100)

                        try:
                            if for_each and prev_df is not None and not prev_df.empty:
                                zeilen = prev_df.head(max_zeilen).to_dict("records")
                                teile, fehler_zeilen = [], []
                                for i, row in enumerate(zeilen):
                                    patched, benutzt = _mit_zeilenwerten(src, row)
                                    try:
                                        teil = fetch_rest_source(patched)
                                    except Exception as e:
                                        # Ein einzelner Ausreißer darf den Lauf nicht
                                        # beenden – bei 100 Aufrufen ist einer, der
                                        # scheitert, der Normalfall und kein Abbruch.
                                        fehler_zeilen.append(f"Zeile {i + 1}: {str(e)[:120]}")
                                        continue
                                    # Die eingesetzten Werte als Spalten mitführen, sonst
                                    # lässt sich hinterher nicht sagen, zu welchem Element
                                    # der Liste ein Detailsatz gehört.
                                    for k in benutzt:
                                        if k not in teil.columns:
                                            teil[k] = row.get(k)
                                    teile.append(teil)
                                df = _pd.concat(teile, ignore_index=True) if teile else _pd.DataFrame()
                                if fehler_zeilen:
                                    log(db, "warning", "pipeline_service", "node_rest_fetch",
                                        f"REST-Fetch '{src.name}': {len(fehler_zeilen)} von "
                                        f"{len(zeilen)} Aufrufen fehlgeschlagen",
                                        entity_id=pipeline.id, entity_name=pipeline.name,
                                        project_id=getattr(pipeline, "project_id", None),
                                        details={"fehler": fehler_zeilen[:20]})
                                if not teile:
                                    raise RuntimeError(
                                        "Kein einziger Aufruf war erfolgreich: "
                                        + "; ".join(fehler_zeilen[:3]))
                            else:
                                src_to_use = src
                                if prev_df is not None and not prev_df.empty:
                                    src_to_use, _ = _mit_zeilenwerten(
                                        src, prev_df.iloc[0].to_dict())
                                df = fetch_rest_source(src_to_use)
                        except Exception as e:
                            results[nid] = {"status": "error", "message": str(e)[:200]}
                            log(db, "error", "pipeline_service", "node_rest_fetch",
                                f"REST-Fetch fehlgeschlagen: {str(e)[:200]}",
                                entity_id=pipeline.id, entity_name=pipeline.name,
                                project_id=getattr(pipeline, "project_id", None),
                                details={"rest_source": src.name, "url": getattr(src, "url", ""),
                                         "for_each": for_each,
                                         "exception_type": type(e).__name__,
                                         "exception_message": str(e),
                                         "traceback": traceback.format_exc()})
                            continue
                        src_to_use = src
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

            if nid in results:
                _enrich_debug_step(results[nid], node, ntype, node_start)

        # Pipeline-Ende loggen
        # df wird vor der Rückgabe entfernt; im Debug-Modus stattdessen ein Sample + rows_out mitgeben
        from app.services.mapping_service import _rows_to_json
        clean_results = {}
        for nid, r in results.items():
            cr = {k: v for k, v in r.items() if k != "df"}
            if debug and r.get("df") is not None and hasattr(r["df"], "head"):
                try:
                    cr.setdefault("rows_out", len(r["df"]))
                    cr["sample"] = _rows_to_json(r["df"].head(5).to_dict("records"))
                except Exception:
                    pass
            clean_results[nid] = cr

        # Kompakte Node-Zusammenfassung (ohne Sample/Sub-Trace) für die Lauf-Historie
        node_summary = [{
            "id": nid,
            "type": results[nid].get("type"),
            "label": results[nid].get("label"),
            "status": results[nid].get("status"),
            "rows": results[nid].get("rows"),
            "duration_ms": results[nid].get("duration_ms"),
            "message": results[nid].get("message"),
            "dry_run": results[nid].get("dry_run", False),
        } for nid in order if nid in results]

        final_result = {"results": clean_results, "errors": errors,
                        "nodes_executed": len(results), "order": order,
                        "node_summary": node_summary, "debug": debug, "dry_run": dry_run}
        log_pipeline_end(db, pipeline, final_result, start_time)
        return final_result

    except Exception as e:
        # Unerwarteter Fehler ausserhalb der Node-Schleife
        log_pipeline_end(db, pipeline, {}, start_time, exc=e)
        raise


# Attribute, die eine Ersatz-Quelle mitbringen MUSS. collection_id und
# environment_id gehören zwingend dazu: ohne sie verliert der Request die
# Basis-URL der Sammlung, die geerbte Auth und seine Umgebungs-Variablen.
_QUELL_ATTRIBUTE = [
    "id", "name", "url", "method", "headers", "query_params", "body_type",
    "body_content", "auth_type", "auth_config", "data_path", "flatten",
    "pagination", "dataset_id", "dataset_mode", "collection_id", "environment_id",
]


class _ErsatzQuelle:
    """Eine RestSource-Kopie mit eingesetzten Werten – das Original bleibt unberührt."""
    pass


def _mit_zeilenwerten(src, row: dict):
    """
    Kopie der Quelle, in der {{spalte}} durch die Werte einer Zeile des
    Vorgänger-Nodes ersetzt ist. Gibt (kopie, benutzte_spalten) zurück –
    welche Spalten wirklich eingesetzt wurden, weiß nur diese Stelle, und der
    Aufrufer braucht es, um die Herkunft einer Zeile festhalten zu können.
    """
    benutzt = set()

    def _inject(text):
        if not isinstance(text, str):
            return text
        for k, v in row.items():
            marke = "{{" + str(k) + "}}"
            if marke in text:
                benutzt.add(k)
                text = text.replace(marke, str(v))
        return text

    kopie = _ErsatzQuelle()
    for attr in _QUELL_ATTRIBUTE:
        val = getattr(src, attr, None)
        if isinstance(val, str):
            val = _inject(val)
        elif isinstance(val, dict):
            val = {k: _inject(v) for k, v in val.items()}
        setattr(kopie, attr, val)
    return kopie, benutzt


def _get_prev_data(node_id, connections, results):
    """Gibt Daten des vorherigen Nodes zurück."""
    import pandas as pd
    for c in connections:
        if c["to_node"] == node_id:
            return results.get(c["from_node"], {})
    return {}

