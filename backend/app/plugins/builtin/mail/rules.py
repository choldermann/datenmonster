import logging
import re
from dataclasses import dataclass, field
from typing import List

from .model import MailMessage

logger = logging.getLogger(__name__)


@dataclass
class RuleCondition:
    """
    Einzelne Bedingung innerhalb einer Regel.

    field:    from | to | cc | bcc | subject | body_text | body_html |
              header_<Name> | filename | mime_type | folder | size
    operator: contains | not_contains | equals | startswith | endswith |
              regex | size_gt | size_lt
    """
    field: str
    operator: str
    value: str
    case_sensitive: bool = False

    def matches(self, mail: MailMessage) -> bool:
        val = self._get_field_value(mail)
        return self._evaluate(val, mail)

    def _get_field_value(self, mail: MailMessage) -> str:
        mapping = {
            "from":      mail.from_addr,
            "to":        "; ".join(mail.to_addrs),
            "cc":        "; ".join(mail.cc_addrs),
            "bcc":       "; ".join(mail.bcc_addrs),
            "subject":   mail.subject,
            "body_text": mail.body_text,
            "body_html": mail.body_html,
            "filename":  "; ".join(a.filename for a in mail.attachments),
            "mime_type": "; ".join(a.mime_type for a in mail.attachments),
            "folder":    mail.folder,
            "size":      str(mail.size),
        }
        if self.field.startswith("header_"):
            key = self.field[7:]
            return mail.headers.get(key, "")
        return mapping.get(self.field, "")

    def _evaluate(self, val: str, mail: MailMessage) -> bool:
        if self.operator in ("size_gt", "size_lt"):
            try:
                n = float(val or "0")
                t = float(self.value)
                return n > t if self.operator == "size_gt" else n < t
            except (ValueError, TypeError):
                return False

        src    = val if self.case_sensitive else val.lower()
        target = self.value if self.case_sensitive else self.value.lower()

        if self.operator == "contains":      return target in src
        if self.operator == "not_contains":  return target not in src
        if self.operator == "equals":        return src == target
        if self.operator == "startswith":    return src.startswith(target)
        if self.operator == "endswith":      return src.endswith(target)
        if self.operator == "regex":
            flags = 0 if self.case_sensitive else re.IGNORECASE
            try:
                return bool(re.search(self.value, val, flags))
            except re.error as e:
                logger.warning(f"Regex-Fehler: {e}")
                return False

        logger.warning(f"Unbekannter Operator: {self.operator}")
        return False


@dataclass
class Rule:
    id: str
    name: str
    conditions: List[RuleCondition] = field(default_factory=list)
    combine: str = "all"           # "all" = AND, "any" = OR
    actions: List[dict] = field(default_factory=list)
    enabled: bool = True

    @classmethod
    def from_dict(cls, d: dict) -> "Rule":
        conditions = []
        for c in d.get("conditions", []):
            try:
                conditions.append(RuleCondition(
                    field=c.get("field", "subject"),
                    operator=c.get("operator", "contains"),
                    value=str(c.get("value", "")),
                    case_sensitive=bool(c.get("case_sensitive", False)),
                ))
            except Exception as e:
                logger.warning(f"Ungültige Bedingung übersprungen: {e}")
        return cls(
            id=str(d.get("id", "")),
            name=str(d.get("name", "Unbenannte Regel")),
            conditions=conditions,
            combine=d.get("combine", "all"),
            actions=d.get("actions", []),
            enabled=bool(d.get("enabled", True)),
        )


class RuleEngine:
    def __init__(self, rules: List[Rule]):
        self.rules = [r for r in rules if r.enabled]

    @classmethod
    def from_config(cls, config: dict) -> "RuleEngine":
        import json
        raw = config.get("rules", "[]")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = []
        if not isinstance(raw, list):
            raw = []
        rules = []
        for r in raw:
            try:
                rules.append(Rule.from_dict(r))
            except Exception as e:
                logger.warning(f"Ungültige Regel übersprungen: {e}")
        return cls(rules)

    def evaluate(self, mail: MailMessage) -> List[Rule]:
        """Gibt alle zutreffenden Regeln zurück."""
        matched = []
        for rule in self.rules:
            if not rule.conditions:
                continue
            try:
                if rule.combine == "any":
                    hit = any(c.matches(mail) for c in rule.conditions)
                else:
                    hit = all(c.matches(mail) for c in rule.conditions)
                if hit:
                    matched.append(rule)
            except Exception as e:
                logger.warning(f"Regelauswertung fehlgeschlagen ({rule.name}): {e}")
        return matched
