"""
EventBus – Redis Pub/Sub Wrapper für Datenmonster.

Channels:
  dm.plugin.trigger  – Tier-2 Plugin signalisiert neue Daten
  dm.mapping.status  – Mapping-Lauf Status (für künftige WebSocket-Nutzung)
"""
import json
import logging
import os
import threading

logger = logging.getLogger(__name__)

CHANNEL_PLUGIN_TRIGGER = "dm.plugin.trigger"
CHANNEL_MAPPING_STATUS = "dm.mapping.status"

_client = None


def _redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://redis:6379")


def _get_client():
    global _client
    if _client is None:
        import redis
        _client = redis.from_url(_redis_url(), decode_responses=True)
    return _client


def publish(channel: str, payload: dict):
    try:
        _get_client().publish(channel, json.dumps(payload))
        logger.info(f"EventBus published → {channel}: {payload}")
    except Exception as e:
        logger.warning(f"EventBus publish fehlgeschlagen ({channel}): {e}")


def start_listener():
    """Startet einen Daemon-Thread der auf dm.plugin.trigger lauscht."""
    if not os.environ.get("REDIS_URL"):
        logger.info("REDIS_URL nicht gesetzt – EventBus-Listener deaktiviert.")
        return

    def _listen():
        import redis as _redis
        import time
        delay = 2
        while True:
            try:
                r = _redis.from_url(_redis_url(), decode_responses=True)
                sub = r.pubsub()
                sub.subscribe(CHANNEL_PLUGIN_TRIGGER)
                logger.info(f"EventBus: Listener aktiv auf {CHANNEL_PLUGIN_TRIGGER}")
                delay = 2  # reset nach erfolgreicher Verbindung
                for msg in sub.listen():
                    if msg["type"] != "message":
                        continue
                    try:
                        payload = json.loads(msg["data"])
                        _handle_plugin_trigger(msg["channel"], payload)
                    except Exception as e:
                        logger.error(f"EventBus handler error: {e}", exc_info=True)
            except Exception as e:
                logger.warning(f"EventBus Verbindungsfehler, retry in {delay}s: {e}")
                time.sleep(delay)
                delay = min(delay * 2, 60)

    t = threading.Thread(target=_listen, daemon=True, name="eventbus-listener")
    t.start()
    return t


def _handle_plugin_trigger(channel: str, payload: dict):
    from app.core.database import SessionLocal
    from app.models.mapping import Mapping
    from app.models.dataset import Dataset
    from app.models.event_log import EventLog
    from app.services.mapping_service import MappingContext, run_mapping_object

    plugin_id = payload.get("plugin_id", "")
    source_type_id = payload.get("source_type_id", "")

    db = SessionLocal()
    log_entry = None
    try:
        log_entry = EventLog(
            channel=channel,
            plugin_id=plugin_id,
            source_type_id=source_type_id,
            payload=payload,
            status="processing",
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)

        if not source_type_id:
            log_entry.status = "error"
            log_entry.error = "source_type_id fehlt im payload"
            db.commit()
            return

        datasets = db.query(Dataset).filter(Dataset.file_type == source_type_id).all()
        dataset_ids = {ds.id for ds in datasets}

        if not dataset_ids:
            log_entry.status = "processed"
            log_entry.triggered_mappings = []
            db.commit()
            logger.info(f"EventBus: Kein Dataset für source_type_id='{source_type_id}' gefunden.")
            return

        all_mappings = db.query(Mapping).all()
        triggered = []

        for mapping in all_mappings:
            nodes = mapping.canvas_nodes or []
            used_ids = {n.get("dataset_id") for n in nodes if n.get("dataset_id")}
            if not (used_ids & dataset_ids):
                continue
            try:
                ctx = MappingContext.from_orm(mapping)
                if not ctx.targets:
                    triggered.append({"id": mapping.id, "name": mapping.name, "status": "skipped", "reason": "keine Ziele"})
                    continue
                result = run_mapping_object(
                    ctx,
                    preview_rows=999999,
                    db=db,
                    mapping_id=mapping.id,
                    mapping_name=mapping.name,
                    project_id=mapping.project_id,
                    triggered_by="eventbus",
                )
                triggered.append({"id": mapping.id, "name": mapping.name, "status": "ok", "rows": result.get("total", 0)})
                logger.info(f"EventBus: Mapping '{mapping.name}' ({mapping.id}) ausgeführt – {result.get('total', 0)} Zeilen")
            except Exception as e:
                logger.error(f"EventBus: Mapping '{mapping.name}' fehlgeschlagen: {e}", exc_info=True)
                triggered.append({"id": mapping.id, "name": mapping.name, "status": "error", "error": str(e)})

        log_entry.triggered_mappings = triggered
        log_entry.status = "processed"
        db.commit()

    except Exception as e:
        logger.error(f"EventBus _handle_plugin_trigger error: {e}", exc_info=True)
        if log_entry:
            try:
                log_entry.status = "error"
                log_entry.error = str(e)
                db.commit()
            except Exception:
                pass
    finally:
        db.close()
