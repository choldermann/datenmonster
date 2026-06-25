import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class IMAPPoller(threading.Thread):
    """
    Daemon-Thread: überwacht ein IMAP-Postfach und ruft on_mail für jede
    neue (ungelesene) Nachricht auf.

    on_mail(mail, config, client) wird pro Mail aufgerufen.
    """

    def __init__(self, dataset_id: str, config: dict, on_mail: Callable):
        super().__init__(
            daemon=True,
            name=f"dm-mail-poller-{dataset_id}",
        )
        self.dataset_id  = dataset_id
        self.config      = config
        self.on_mail     = on_mail
        self._stop       = threading.Event()
        self._last_error: Optional[str] = None
        self.poll_count  = 0

    def run(self):
        interval = max(10, int(self.config.get("poll_interval") or 60))
        logger.info(
            f"[mail-poller] gestartet – Dataset {self.dataset_id}, "
            f"Intervall {interval}s, {self.config.get('user')}@{self.config.get('host')}"
        )
        while not self._stop.is_set():
            try:
                self._poll()
                self._last_error = None
            except Exception as e:
                self._last_error = str(e)
                logger.error(f"[mail-poller] Fehler (Dataset {self.dataset_id}): {e}")
            self._stop.wait(interval)
        logger.info(f"[mail-poller] gestoppt – Dataset {self.dataset_id}")

    def _poll(self):
        from .imap_client import IMAPClient

        cfg = self.config
        ssl = str(cfg.get("ssl", "true")).lower() not in ("false", "0", "no")
        with IMAPClient(
            host=cfg.get("host", ""),
            port=int(cfg.get("port") or 993),
            user=cfg.get("user", ""),
            password=cfg.get("password", ""),
            ssl=ssl,
        ) as client:
            folder = cfg.get("folder", "INBOX")
            uids   = client.fetch_unseen_uids(folder)
            if not uids:
                return
            logger.info(
                f"[mail-poller] {len(uids)} neue E-Mail(s) in '{folder}' "
                f"(Dataset {self.dataset_id})"
            )
            for uid in uids:
                mail = client.fetch_message_by_uid(uid, folder)
                if mail:
                    mail.account_id = self.dataset_id
                    try:
                        self.on_mail(mail, cfg, client)
                    except Exception as e:
                        logger.error(f"[mail-poller] on_mail Fehler (UID={uid}): {e}")
            self.poll_count += 1

    def stop(self):
        self._stop.set()

    @property
    def status(self) -> dict:
        return {
            "running":    self.is_alive(),
            "poll_count": self.poll_count,
            "last_error": self._last_error,
            "dataset_id": self.dataset_id,
            "host":       self.config.get("host"),
            "user":       self.config.get("user"),
            "folder":     self.config.get("folder", "INBOX"),
        }
