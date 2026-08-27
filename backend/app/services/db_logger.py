"""
db_logger – zentraler Logging-Helper für Datenmonster.
Schreibt strukturierte Logs in system_logs Tabelle.
Alle Felder die zum Debuggen wichtig sind werden erfasst.
"""
import traceback
import logging
from datetime import datetime, timezone
from typing import Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


def log(
    db: Session,
    level: str,                          # "info" | "success" | "warning" | "error"
    module: str,                         # z.B. "pipeline_service", "mapping_service"
    action: str,                         # z.B. "pipeline_run", "node_execute", "ftp_sync"
    message: str,                        # Lesbare Kurzbeschreibung
    entity_id: Optional[int] = None,     # Pipeline-ID, Mapping-ID etc.
    entity_name: Optional[str] = None,   # Pipeline-Name, Mapping-Name etc.
    project_id: Optional[int] = None,
    details: Optional[dict] = None,      # Zusatz-Kontext (Node-Typ, Config, Traceback...)
    rows_processed: Optional[int] = None,
    rows_before: Optional[int] = None,
    rows_after: Optional[int] = None,
    duration_ms: Optional[int] = None,
    exc: Optional[Exception] = None,     # Exception-Objekt → Traceback wird extrahiert
) -> None:
    """Schreibt einen Log-Eintrag in system_logs."""

    # Traceback aus Exception extrahieren
    if exc is not None:
        tb = traceback.format_exc()
        if details is None:
            details = {}
        details["exception_type"] = type(exc).__name__
        details["exception_message"] = str(exc)
        details["traceback"] = tb
        # Auch auf stderr loggen damit docker logs weiterhin funktioniert
        logger.error(f"[{module}] {action}: {message} – {exc}", exc_info=True)
    elif level == "error":
        logger.error(f"[{module}] {action}: {message}")
    elif level == "warning":
        logger.warning(f"[{module}] {action}: {message}")
    else:
        logger.info(f"[{module}] {action}: {message}")

    try:
        import json
        db.execute(text("""
            INSERT INTO system_logs
                (level, module, action, message, entity_id, entity_name,
                 project_id, details, rows_processed, rows_before, rows_after,
                 duration_ms, created_at)
            VALUES
                (:level, :module, :action, :message, :entity_id, :entity_name,
                 :project_id, :details, :rows_processed, :rows_before, :rows_after,
                 :duration_ms, :created_at)
        """), {
            "level": level,
            "module": module,
            "action": action,
            "message": message[:500],
            "entity_id": entity_id,
            "entity_name": entity_name,
            "project_id": project_id,
            "details": json.dumps(details, ensure_ascii=False, default=str) if details else None,
            "rows_processed": rows_processed,
            "rows_before": rows_before,
            "rows_after": rows_after,
            "duration_ms": duration_ms,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        db.commit()
    except Exception as log_exc:
        # Logging darf niemals die eigentliche Ausführung unterbrechen
        logger.error(f"db_logger Fehler: {log_exc}")


def log_pipeline_start(db, pipeline, triggered_by: str = "manual") -> datetime:
    """Loggt den Start einer Pipeline und gibt Startzeit zurück."""
    start = datetime.now(timezone.utc)
    log(db,
        level="info",
        module="pipeline_service",
        action="pipeline_start",
        message=f"Pipeline gestartet ({triggered_by})",
        entity_id=pipeline.id,
        entity_name=pipeline.name,
        project_id=getattr(pipeline, "project_id", None),
        details={"triggered_by": triggered_by, "node_count": len(pipeline.nodes or [])},
    )
    return start


def log_pipeline_end(db, pipeline, result: dict, start: datetime,
                     exc: Optional[Exception] = None) -> None:
    """Loggt das Ende einer Pipeline mit Ergebnis und Dauer."""
    duration_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
    errors = result.get("errors", []) if result else []
    nodes_executed = result.get("nodes_executed", 0) if result else 0

    if exc is not None:
        level = "error"
        message = f"Pipeline fehlgeschlagen: {str(exc)[:200]}"
    elif errors:
        level = "warning"
        message = f"Pipeline mit Warnungen abgeschlossen ({len(errors)} Fehler)"
    else:
        level = "success"
        message = f"Pipeline erfolgreich – {nodes_executed} Nodes ausgeführt"

    details = {
        "nodes_executed": nodes_executed,
        "errors": errors,
        "duration_ms": duration_ms,
    }
    # Kompakte Node-Zusammenfassung für die Lauf-Historie (B3); Debug/Dry-Run markieren,
    # damit die Historie sie herausfiltern kann.
    if result:
        if result.get("node_summary") is not None:
            details["node_summary"] = result["node_summary"]
        if result.get("debug"):
            details["debug"] = True
        if result.get("dry_run"):
            details["dry_run"] = True
    if exc:
        details["exception_type"] = type(exc).__name__
        details["exception_message"] = str(exc)
        details["traceback"] = traceback.format_exc()

    log(db,
        level=level,
        module="pipeline_service",
        action="pipeline_end",
        message=message,
        entity_id=pipeline.id,
        entity_name=pipeline.name,
        project_id=getattr(pipeline, "project_id", None),
        details=details,
        duration_ms=duration_ms,
    )


def log_node_error(db, pipeline, node: dict, exc: Exception) -> None:
    """Loggt einen Node-Fehler mit vollem Kontext."""
    ntype = node.get("type", "unknown")
    nid = node.get("id", "?")
    config = {k: v for k, v in node.get("config", {}).items()
              if k not in ("password", "api_key", "apikey", "secret")}  # Secrets rausfiltern

    log(db,
        level="error",
        module="pipeline_service",
        action=f"node_error_{ntype}",
        message=f"Node [{ntype}] fehlgeschlagen: {str(exc)[:200]}",
        entity_id=pipeline.id,
        entity_name=pipeline.name,
        project_id=getattr(pipeline, "project_id", None),
        details={
            "node_id": nid,
            "node_type": ntype,
            "node_config": config,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "traceback": traceback.format_exc(),
        },
        exc=None,  # exc schon manuell verarbeitet
    )


def log_mapping_error(db, mapping_name: str, mapping_id: int,
                      project_id: int, exc: Exception, context: dict = None) -> None:
    """Loggt einen Mapping-Fehler mit vollem Kontext."""
    details = {
        "exception_type": type(exc).__name__,
        "exception_message": str(exc),
        "traceback": traceback.format_exc(),
    }
    if context:
        details.update(context)

    log(db,
        level="error",
        module="mapping_service",
        action="mapping_error",
        message=f"Mapping-Fehler: {str(exc)[:200]}",
        entity_id=mapping_id,
        entity_name=mapping_name,
        project_id=project_id,
        details=details,
    )


# ── Ausgehende REST-Aufrufe ───────────────────────────────────────────────────
#
# Ausgehende Aufrufe waren bisher nur im API-Studio nachvollziehbar. In Mapping
# und Pipeline fehlten Statuscode und Antwort vollständig – bei einer Gegenstelle,
# deren Fehlerobjekte nicht dokumentiert sind, ist die Fehlersuche damit blind.
#
# Zwei Regeln halten das Protokoll benutzbar:
#   * Kopfdaten immer, Antwortkörper nur auf ausdrücklichen Wunsch. Antworten
#     können personenbezogene Daten enthalten; die Entscheidung trifft der
#     Anwender am Knoten, nicht das System.
#   * Ein Lauf mit 500 Zeilen erzeugt keine 500 Einträge, sondern eine
#     Zusammenfassung plus die ersten Fehlschläge.

REST_LOG_MAX_FEHLER = 20      # Einzeleinträge je Knoten und Lauf
_REST_BODY_MAX      = 2000    # Zeichen, die von einer Antwort aufgehoben werden


def _eigene_session():
    """Eigene Session – der Mapping-Lauf läuft teils in Threads, und eine
    SQLAlchemy-Session darf nicht zwischen Threads geteilt werden."""
    from app.core.database import SessionLocal
    return SessionLocal()


def _sichere_url(ergebnis: dict) -> str:
    """URL ohne Abfrageteil. Ein API-Schlüssel kann als Abfrageparameter
    übergeben werden – der gehört nicht ins Protokoll."""
    url = (ergebnis.get("request") or {}).get("url") or ""
    return url.split("?", 1)[0]


def rest_aufruf_details(ergebnis: dict, antwort_aufheben: bool = False) -> dict:
    """Die protokollwürdigen Teile einer execute_request-Antwort."""
    anfrage = ergebnis.get("request") or {}
    details = {
        "method":        anfrage.get("method"),
        "url":           _sichere_url(ergebnis),
        "params":        anfrage.get("params") or {},      # bereits maskiert
        "status_code":   ergebnis.get("status_code"),
        "reason":        ergebnis.get("reason"),
        "duration_ms":   ergebnis.get("duration_ms"),
        "size_bytes":    ergebnis.get("size_bytes"),
        "content_type":  ergebnis.get("content_type"),
    }
    if ergebnis.get("error"):
        details["error"] = str(ergebnis["error"])[:500]
    if antwort_aufheben and ergebnis.get("body_text"):
        text = ergebnis["body_text"]
        details["response_body"] = text[:_REST_BODY_MAX]
        details["response_truncated"] = len(text) > _REST_BODY_MAX
    return details


def log_rest_aufruf(ergebnis: dict, *, module: str, action: str = "rest_call",
                    entity_id=None, entity_name=None, project_id=None,
                    knoten: str = None, antwort_aufheben: bool = False,
                    zusatz: dict = None) -> None:
    """Einen einzelnen ausgehenden Aufruf protokollieren (i. d. R. einen Fehlschlag)."""
    details = rest_aufruf_details(ergebnis, antwort_aufheben)
    if knoten:
        details["node"] = knoten
    if zusatz:
        details.update(zusatz)

    status = ergebnis.get("status_code")
    ok = bool(ergebnis.get("ok"))
    kurz = ergebnis.get("error") or f"HTTP {status} {ergebnis.get('reason') or ''}".strip()

    db = _eigene_session()
    try:
        log(db,
            level="success" if ok else "error",
            module=module, action=action,
            message=(f"{details.get('method')} {details.get('url')} → "
                     + (f"{status}" if ok else kurz[:180])),
            entity_id=entity_id, entity_name=entity_name, project_id=project_id,
            details=details, duration_ms=ergebnis.get("duration_ms"))
    finally:
        db.close()


def log_rest_zusammenfassung(*, module: str, action: str = "rest_calls",
                             entity_id=None, entity_name=None, project_id=None,
                             knoten: str = None, aufrufe: int = 0, fehler: int = 0,
                             dauer_ms: int = None, zusatz: dict = None) -> None:
    """Ein Eintrag je Knoten und Lauf – damit ein Lauf über viele Zeilen das
    Protokoll nicht flutet."""
    details = {"node": knoten, "aufrufe": aufrufe, "fehler": fehler}
    if zusatz:
        details.update(zusatz)
    db = _eigene_session()
    try:
        log(db,
            level="warning" if fehler else "success",
            module=module, action=action,
            message=(f"REST-Knoten: {aufrufe} Aufrufe"
                     + (f", davon {fehler} fehlgeschlagen" if fehler else " – alle erfolgreich")),
            entity_id=entity_id, entity_name=entity_name, project_id=project_id,
            details=details, duration_ms=dauer_ms, rows_processed=aufrufe)
    finally:
        db.close()
