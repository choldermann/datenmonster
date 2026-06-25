from app.plugins.builtin.mail.connector import MailConnector

ALL_PLUGINS = [MailConnector]


def get_instance() -> MailConnector:
    """Gibt die registrierte MailConnector-Instanz aus der CapabilityRegistry zurück."""
    from app.plugins.registry import registry
    return registry.get_source("mail_imap")
