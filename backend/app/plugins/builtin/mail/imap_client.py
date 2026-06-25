import email
import email.header
import imaplib
import logging
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import List, Optional

from .model import Attachment, MailMessage

logger = logging.getLogger(__name__)


def _decode_header(value: str) -> str:
    if not value:
        return ""
    parts = email.header.decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(str(part))
    return "".join(decoded)


class IMAPClient:
    def __init__(self, host: str, port: int, user: str, password: str, ssl: bool = True):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.ssl = ssl
        self._conn: Optional[imaplib.IMAP4] = None

    def connect(self):
        if self.ssl:
            self._conn = imaplib.IMAP4_SSL(self.host, self.port)
        else:
            self._conn = imaplib.IMAP4(self.host, self.port)
        self._conn.login(self.user, self.password)
        logger.debug(f"IMAP verbunden: {self.user}@{self.host}:{self.port}")

    def disconnect(self):
        try:
            if self._conn:
                self._conn.logout()
        except Exception:
            pass
        finally:
            self._conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()

    def test_connection(self) -> dict:
        try:
            self.connect()
            _, caps = self._conn.capability()
            folders = self.list_folders()
            self.disconnect()
            return {
                "ok":      True,
                "message": f"Verbunden mit {self.host}:{self.port} als {self.user}",
                "folders": folders[:20],
            }
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def list_folders(self) -> List[str]:
        if not self._conn:
            return []
        _, raw = self._conn.list()
        result = []
        for item in raw:
            if not item:
                continue
            decoded = item.decode() if isinstance(item, bytes) else item
            # Format: (\HasNoChildren) "/" "INBOX"
            parts = decoded.split('"/"') if '"/"' in decoded else decoded.split("NIL ")
            name = parts[-1].strip().strip('"') if parts else decoded
            result.append(name)
        return result

    def select_folder(self, folder: str = "INBOX") -> int:
        status, data = self._conn.select(f'"{folder}"')
        if status != "OK":
            raise ValueError(f"Ordner '{folder}' nicht gefunden oder nicht zugänglich")
        return int(data[0]) if data[0] else 0

    def fetch_unseen_uids(self, folder: str = "INBOX") -> List[bytes]:
        self.select_folder(folder)
        _, data = self._conn.search(None, "UNSEEN")
        if not data or not data[0]:
            return []
        return data[0].split()

    def fetch_recent_uids(self, folder: str = "INBOX", limit: int = 50) -> List[bytes]:
        total = self.select_folder(folder)
        if total == 0:
            return []
        start = max(1, total - limit + 1)
        _, data = self._conn.search(None, f"{start}:{total}")
        return data[0].split() if data and data[0] else []

    def fetch_message_by_uid(self, uid: bytes, folder: str = "INBOX") -> Optional[MailMessage]:
        try:
            _, data = self._conn.fetch(uid, "(RFC822 FLAGS)")
            if not data or data[0] is None:
                return None
            raw_email = data[0][1]
            flags_str = str(data[0][0]) if data[0][0] else ""
            msg = email.message_from_bytes(raw_email)
            return self._parse(msg, uid.decode(), flags_str, folder)
        except Exception as e:
            logger.warning(f"Fehler beim Lesen von UID {uid}: {e}")
            return None

    def mark_seen(self, uid: bytes, folder: str = "INBOX"):
        self.select_folder(folder)
        self._conn.store(uid, "+FLAGS", "\\Seen")

    def move_message(self, uid: bytes, target_folder: str, folder: str = "INBOX"):
        self.select_folder(folder)
        self._conn.copy(uid, f'"{target_folder}"')
        self._conn.store(uid, "+FLAGS", "\\Deleted")
        self._conn.expunge()

    def _parse(self, msg: email.message.Message, uid: str, flags_str: str, folder: str) -> MailMessage:
        subject    = _decode_header(msg.get("Subject", ""))
        from_addr  = _decode_header(msg.get("From", ""))
        to_raw     = msg.get("To", "")
        cc_raw     = msg.get("Cc", "")
        bcc_raw    = msg.get("Bcc", "")
        message_id = msg.get("Message-ID", uid).strip()

        date_val: Optional[datetime] = None
        try:
            date_val = parsedate_to_datetime(msg.get("Date", ""))
        except Exception:
            pass

        body_text = ""
        body_html = ""
        attachments: List[Attachment] = []

        for part in msg.walk():
            ct = part.get_content_type()
            fn = part.get_filename()

            if fn:
                fn_decoded = _decode_header(fn)
                payload = part.get_payload(decode=True) or b""
                attachments.append(Attachment(
                    filename=fn_decoded,
                    mime_type=ct,
                    size=len(payload),
                    content=payload,
                    content_id=part.get("Content-ID", "").strip("<>"),
                ))
            elif ct == "text/plain" and not body_text:
                charset = part.get_content_charset() or "utf-8"
                body_text = (part.get_payload(decode=True) or b"").decode(charset, errors="replace")
            elif ct == "text/html" and not body_html:
                charset = part.get_content_charset() or "utf-8"
                body_html = (part.get_payload(decode=True) or b"").decode(charset, errors="replace")

        headers = {k: _decode_header(v) for k, v in msg.items()}

        def _split(raw: str) -> List[str]:
            return [a.strip() for a in raw.split(",") if a.strip()]

        return MailMessage(
            message_id=message_id,
            uid=uid,
            subject=subject,
            from_addr=from_addr,
            to_addrs=_split(to_raw),
            cc_addrs=_split(cc_raw),
            bcc_addrs=_split(bcc_raw),
            date=date_val,
            body_text=body_text,
            body_html=body_html,
            headers=headers,
            attachments=attachments,
            folder=folder,
            is_seen="\\Seen" in flags_str,
        )
