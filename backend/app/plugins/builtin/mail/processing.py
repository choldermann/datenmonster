"""
Mail-Verarbeitungslogik: Duplikat-Check, Regel-Engine, EventBus, Mapping-Trigger.

Wird vom IMAPPoller-Thread aufgerufen – erzeugt eine eigene DB-Session pro Mail.
"""
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text

from .model import MailMessage
from .rules import RuleEngine

logger = logging.getLogger(__name__)

# ─── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _account_hash(config: dict) -> str:
    key = f"{config.get('host')}:{config.get('port')}:{config.get('user')}:{config.get('folder', 'INBOX')}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _is_already_processed(db, account_hash: str, uid: str) -> bool:
    row = db.execute(
        text("SELECT id FROM mail_processing_log WHERE account_hash=:h AND uid=:u LIMIT 1"),
        {"h": account_hash, "u": uid},
    ).fetchone()
    return row is not None


def _upsert_log(db, account_hash: str, mail: MailMessage, status: str,
                rule_name: str = "", mapping_id: Optional[int] = None, error: str = ""):
    db.execute(text("""
        INSERT INTO mail_processing_log
            (account_hash, message_id, uid, subject, from_addr,
             received_at, processed_at, status, rule_name, mapping_id, error)
        VALUES (:h, :mid, :uid, :subj, :fr, :recv, :proc, :st, :rn, :mapid, :err)
        ON CONFLICT(account_hash, uid) DO UPDATE SET
            status=excluded.status,
            processed_at=excluded.processed_at,
            rule_name=excluded.rule_name,
            mapping_id=excluded.mapping_id,
            error=excluded.error
    """), {
        "h":     account_hash,
        "mid":   (mail.message_id or "")[:512],
        "uid":   uid[:128] if (uid := mail.uid) else "",
        "subj":  (mail.subject or "")[:255],
        "fr":    (mail.from_addr or "")[:255],
        "recv":  mail.date.isoformat() if mail.date else "",
        "proc":  datetime.now(timezone.utc).isoformat(),
        "st":    status,
        "rn":    (rule_name or "")[:255],
        "mapid": mapping_id,
        "err":   (error or "")[:500],
    })
    db.commit()


# ─── Haupt-Verarbeitungsroutine ───────────────────────────────────────────────

def process_mail(mail: MailMessage, config: dict, imap_client):
    """
    Verarbeitet eine erkannte E-Mail:
      1. Duplikat-Check (UID + account_hash)
      2. Regel-Auswertung
      3. EventBus-Event dm.mail.received
      4. Regel-Aktionen ausführen (run_mapping, publish_event)
      5. Post-Aktion (mark_read, ...)
      6. Status in mail_processing_log schreiben
    """
    from app.core.database import SessionLocal

    account_hash = _account_hash(config)
    db = SessionLocal()
    try:
        if _is_already_processed(db, account_hash, mail.uid):
            logger.debug(f"[mail] UID {mail.uid} bereits verarbeitet – übersprungen")
            return

        _publish("dm.mail.received", mail, config)

        engine = RuleEngine.from_config(config)
        matched = engine.evaluate(mail)

        if not matched:
            _upsert_log(db, account_hash, mail, "ignored")
            return

        rule_names = "; ".join(r.name for r in matched)
        _upsert_log(db, account_hash, mail, "matched", rule_name=rule_names)

        for rule in matched:
            _publish("dm.mail.matched", mail, config, rule_name=rule.name)
            for action in rule.actions:
                _execute_action(action, mail, config)

        # Post-Aktion
        post_action = config.get("post_action", "none")
        if post_action == "mark_read":
            try:
                imap_client.mark_seen(mail.uid.encode(), config.get("folder", "INBOX"))
            except Exception as e:
                logger.warning(f"[mail] mark_seen fehlgeschlagen: {e}")
        elif post_action == "move":
            target_folder = config.get("post_action_folder", "Processed")
            try:
                imap_client.move_message(
                    mail.uid.encode(), target_folder, config.get("folder", "INBOX")
                )
            except Exception as e:
                logger.warning(f"[mail] Verschieben nach '{target_folder}' fehlgeschlagen: {e}")

        _upsert_log(db, account_hash, mail, "processed", rule_name=rule_names)
        _publish("dm.mail.processed", mail, config)

    except Exception as e:
        logger.error(f"[mail] Verarbeitungsfehler für '{mail.subject}': {e}", exc_info=True)
        try:
            _upsert_log(db, account_hash, mail, "failed", error=str(e))
        except Exception:
            pass
        _publish("dm.mail.failed", mail, config, error=str(e))
    finally:
        db.close()


# ─── Aktionen ─────────────────────────────────────────────────────────────────

def _execute_action(action: dict, mail: MailMessage, config: dict):
    action_type = action.get("type", "")

    if action_type == "run_mapping":
        mapping_id = action.get("mapping_id")
        if not mapping_id:
            logger.warning("[mail] run_mapping ohne mapping_id – übersprungen")
            return
        try:
            from app.core.database import SessionLocal
            from app.models.mapping import Mapping
            from app.services.mapping_service import MappingContext, run_mapping_object
            db = SessionLocal()
            try:
                mapping = db.query(Mapping).filter(Mapping.id == int(mapping_id)).first()
                if not mapping:
                    logger.warning(f"[mail] Mapping {mapping_id} nicht gefunden")
                    return
                ctx = MappingContext.from_orm(mapping)
                result = run_mapping_object(
                    ctx,
                    preview_rows=999999,
                    db=db,
                    mapping_id=mapping.id,
                    mapping_name=mapping.name,
                    project_id=mapping.project_id,
                    triggered_by=f"mail:{mail.message_id[:64]}",
                )
                logger.info(
                    f"[mail] Mapping {mapping_id} ausgeführt – "
                    f"{result.get('total', 0)} Zeilen"
                )
            finally:
                db.close()
        except Exception as e:
            logger.error(f"[mail] Mapping {mapping_id} fehlgeschlagen: {e}", exc_info=True)

    elif action_type == "publish_event":
        channel = action.get("channel", "dm.mail.action")
        _publish(channel, mail, config)

    else:
        logger.warning(f"[mail] Unbekannte Aktion '{action_type}' – übersprungen")


# ─── EventBus ─────────────────────────────────────────────────────────────────

def _publish(channel: str, mail: MailMessage, config: dict,
             rule_name: str = "", error: str = ""):
    try:
        from app.services.eventbus import publish
        payload: dict = {
            "channel":        channel,
            "plugin_id":      "mail_imap",
            "source_type_id": "mail_imap",
            "message_id":     mail.message_id,
            "uid":            mail.uid,
            "subject":        mail.subject,
            "from":           mail.from_addr,
            "date":           mail.date.isoformat() if mail.date else "",
            "account":        f"{config.get('user')}@{config.get('host')}",
            "folder":         config.get("folder", "INBOX"),
        }
        if rule_name:
            payload["rule_name"] = rule_name
        if error:
            payload["error"] = error
        publish(channel, payload)
    except Exception as e:
        logger.warning(f"[mail] EventBus publish fehlgeschlagen ({channel}): {e}")
