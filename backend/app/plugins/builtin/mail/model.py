from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict


@dataclass
class Attachment:
    filename: str
    mime_type: str
    size: int
    content: bytes
    content_id: str = ""

    def to_dict(self) -> dict:
        return {
            "filename":   self.filename,
            "mime_type":  self.mime_type,
            "size":       self.size,
            "content_id": self.content_id,
        }


@dataclass
class MailMessage:
    message_id: str
    uid: str
    subject: str
    from_addr: str
    to_addrs: List[str] = field(default_factory=list)
    cc_addrs: List[str] = field(default_factory=list)
    bcc_addrs: List[str] = field(default_factory=list)
    date: Optional[datetime] = None
    body_text: str = ""
    body_html: str = ""
    headers: Dict[str, str] = field(default_factory=dict)
    attachments: List[Attachment] = field(default_factory=list)
    folder: str = "INBOX"
    account_id: str = ""
    size: int = 0
    is_seen: bool = False

    def to_row(self, full: bool = False) -> dict:
        row = {
            "message_id":       self.message_id,
            "uid":              self.uid,
            "subject":          self.subject,
            "from":             self.from_addr,
            "to":               "; ".join(self.to_addrs),
            "cc":               "; ".join(self.cc_addrs),
            "date":             self.date.isoformat() if self.date else "",
            "has_attachments":  len(self.attachments) > 0,
            "attachment_count": len(self.attachments),
            "attachment_names": "; ".join(a.filename for a in self.attachments),
            "size":             self.size,
            "folder":           self.folder,
        }
        if full:
            row["body_text"] = self.body_text[:5000]
            row["body_html"] = self.body_html[:5000]
        return row
