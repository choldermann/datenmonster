"""
MailConnector – IMAP-E-Mail als Datenquelle und Ereignisquelle.

Capabilities:
  source            – fetch() liefert E-Mails als DataFrame-Zeilen
  trigger           – start_poller() überwacht Postfach im Hintergrund
  attachment_source – fetch() mit extract_mode=attachment_* gibt Anhaltsdaten zurück
"""
import io
import json
import logging
import threading
from typing import List, Optional

from app.plugins.base import SourcePlugin
from .imap_client import IMAPClient
from .model import Attachment, MailMessage
from .poller import IMAPPoller

logger = logging.getLogger(__name__)

_POLLERS: dict = {}
_LOCK = threading.Lock()


class MailConnector(SourcePlugin):
    id      = "datenmonster-plugin-mail"
    name    = "Mail / IMAP"
    version = "1.0.0"
    description = (
        "E-Mail-Postfächer (IMAP/SSL) als Datenquelle und Trigger für Verarbeitungs-Pipelines. "
        "Unterstützt Regel-Engine, Anhang-Extraktion und EventBus-Integration."
    )
    author      = "Datenmonster"
    license     = "professional"
    capabilities = ["source", "trigger", "attachment_source"]

    source_type_id    = "mail_imap"
    source_type_label = "Mail / IMAP"
    source_type_icon  = "mail"
    source_category   = "mail"

    config_schema: List[dict] = [
        {
            "key": "host",  "label": "IMAP-Server",  "type": "string",  "required": True,
            "placeholder": "imap.beispiel.de",
        },
        {
            "key": "port",  "label": "Port",  "type": "number",  "default": 993,
        },
        {
            "key": "user",  "label": "Benutzer / E-Mail-Adresse",  "type": "string",
            "required": True,  "placeholder": "user@beispiel.de",
        },
        {
            "key": "password",  "label": "Passwort",  "type": "password",  "required": True,
        },
        {
            "key": "ssl",  "label": "SSL/TLS",  "type": "select",
            "options": ["true", "false"],  "default": "true",
        },
        {
            "key": "folder",  "label": "Ordner",  "type": "string",
            "default": "INBOX",  "placeholder": "INBOX",
        },
        {
            "key": "poll_interval",  "label": "Poll-Intervall (Sekunden)",
            "type": "number",  "default": 60,
        },
        {
            "key": "fetch_limit",  "label": "Max. Mails pro Abruf",
            "type": "number",  "default": 50,
        },
        {
            "key": "extract_mode",  "label": "Extraktionsmodus",  "type": "select",
            "options": ["headers", "full", "attachment_csv", "attachment_xlsx", "attachment_xml"],
            "default": "headers",
            "description": (
                "headers = nur Metadaten | full = + Body | "
                "attachment_* = Anhänge als strukturierte Daten"
            ),
        },
        {
            "key": "post_action",  "label": "Aktion nach Verarbeitung",  "type": "select",
            "options": ["none", "mark_read", "move"],  "default": "none",
        },
        {
            "key": "post_action_folder",  "label": "Zielordner (für 'move')",
            "type": "string",  "default": "Processed",  "placeholder": "Processed",
        },
        {
            "key": "rules",  "label": "Regeln (JSON)",  "type": "code",  "default": "[]",
            "description": (
                "Array von Regel-Objekten.\n"
                "Beispiel:\n"
                '[{"id":"r1","name":"Rechnungen","combine":"all",'
                '"conditions":[{"field":"subject","operator":"contains","value":"Rechnung"}],'
                '"actions":[{"type":"run_mapping","mapping_id":1}]}]'
            ),
        },
    ]

    # ── SourcePlugin Interface ──────────────────────────────────────────────────

    def test_connection(self, config: dict) -> dict:
        return self._make_client(config).test_connection()

    def get_columns(self, config: dict) -> List[str]:
        mode = config.get("extract_mode", "headers")
        if mode == "full":
            return [
                "message_id", "uid", "subject", "from", "to", "cc",
                "date", "body_text", "body_html",
                "has_attachments", "attachment_count", "attachment_names", "size", "folder",
            ]
        if mode.startswith("attachment_"):
            sample = self.fetch(dict(config, fetch_limit=1))
            return list(sample[0].keys()) if sample else []
        return [
            "message_id", "uid", "subject", "from", "to", "cc",
            "date", "has_attachments", "attachment_count", "attachment_names", "size", "folder",
        ]

    def fetch(self, config: dict) -> List[dict]:
        mode   = config.get("extract_mode", "headers")
        limit  = int(config.get("fetch_limit") or config.get("limit") or 50)
        folder = config.get("folder", "INBOX")

        with self._make_client(config) as client:
            uids     = client.fetch_recent_uids(folder, limit)
            messages = []
            for uid in uids[-limit:]:
                msg = client.fetch_message_by_uid(uid, folder)
                if msg:
                    messages.append(msg)

        if mode.startswith("attachment_"):
            return self._extract_attachments(messages, mode)

        full = (mode == "full")
        return [m.to_row(full=full) for m in messages]

    def fetch_preview(self, config: dict, limit: int = 20) -> List[dict]:
        return self.fetch(dict(config, fetch_limit=limit, limit=limit))

    # ── Poller-Management ──────────────────────────────────────────────────────

    def start_poller(self, dataset_id: str, config: dict):
        with _LOCK:
            existing = _POLLERS.get(dataset_id)
            if existing and existing.is_alive():
                logger.info(f"[mail] Poller für Dataset {dataset_id} läuft bereits")
                return
            poller = IMAPPoller(dataset_id, config, self._on_new_mail)
            _POLLERS[dataset_id] = poller
            poller.start()

    def stop_poller(self, dataset_id: str):
        with _LOCK:
            poller = _POLLERS.pop(dataset_id, None)
        if poller:
            poller.stop()
            logger.info(f"[mail] Poller für Dataset {dataset_id} gestoppt")

    def get_poller_status(self, dataset_id: str) -> Optional[dict]:
        p = _POLLERS.get(dataset_id)
        return p.status if p else None

    def list_pollers(self) -> List[dict]:
        return [p.status for p in _POLLERS.values()]

    def start_pollers_from_db(self, db):
        """Startet Poller für alle bestehenden Mail-Datasets beim Backend-Start."""
        try:
            from app.models.dataset import Dataset
            datasets = db.query(Dataset).filter(Dataset.file_type == "mail_imap").all()
            started = 0
            for ds in datasets:
                try:
                    cfg = json.loads(ds.query_config or "{}")
                    if cfg.get("host") and cfg.get("user") and cfg.get("password"):
                        self.start_poller(str(ds.id), cfg)
                        started += 1
                except Exception as e:
                    logger.warning(
                        f"[mail] Poller für Dataset {ds.id} konnte nicht gestartet werden: {e}"
                    )
            if started:
                logger.info(f"[mail] {started} Mail-Poller gestartet")
        except Exception as e:
            logger.warning(f"[mail] start_pollers_from_db fehlgeschlagen: {e}")

    # ── Callback für Poller ────────────────────────────────────────────────────

    def _on_new_mail(self, mail: MailMessage, config: dict, imap_client):
        from app.plugins.builtin.mail.processing import process_mail
        process_mail(mail, config, imap_client)

    # ── Hilfsmethoden ─────────────────────────────────────────────────────────

    def _make_client(self, config: dict) -> IMAPClient:
        ssl = str(config.get("ssl", "true")).lower() not in ("false", "0", "no")
        return IMAPClient(
            host=config.get("host", ""),
            port=int(config.get("port") or 993),
            user=config.get("user", ""),
            password=config.get("password", ""),
            ssl=ssl,
        )

    def _extract_attachments(self, messages: List[MailMessage], mode: str) -> List[dict]:
        ext_map = {
            "attachment_csv":  (".csv",),
            "attachment_xlsx": (".xlsx", ".xls"),
            "attachment_xml":  (".xml",),
        }
        allowed_exts = ext_map.get(mode, ())
        all_rows: List[dict] = []

        for mail in messages:
            for att in mail.attachments:
                fn_lower = att.filename.lower()
                if not any(fn_lower.endswith(e) for e in allowed_exts):
                    continue
                try:
                    df = self._parse_attachment(att, mode)
                    if df is not None and not df.empty:
                        df["_mail_subject"]  = mail.subject
                        df["_mail_from"]     = mail.from_addr
                        df["_mail_date"]     = mail.date.isoformat() if mail.date else ""
                        df["_attachment"]    = att.filename
                        all_rows.extend(df.to_dict("records"))
                except Exception as e:
                    logger.warning(f"[mail] Anhang '{att.filename}' konnte nicht gelesen werden: {e}")

        return all_rows

    def _parse_attachment(self, att: Attachment, mode: str):
        import pandas as pd
        buf = io.BytesIO(att.content)
        if mode == "attachment_csv":
            for enc in ("utf-8", "latin-1", "cp1252"):
                try:
                    return pd.read_csv(buf, encoding=enc)
                except Exception:
                    buf.seek(0)
        elif mode == "attachment_xlsx":
            return pd.read_excel(buf)
        elif mode == "attachment_xml":
            return pd.read_xml(buf)
        return None
