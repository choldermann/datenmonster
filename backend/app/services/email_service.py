"""
email_service – sendet E-Mails über konfigurierten SMTP-Server.
"""
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List

logger = logging.getLogger(__name__)


def get_email_config(db) -> dict:
    """Lädt E-Mail-Konfiguration aus der DB."""
    try:
        from app.models.setting import SystemSetting
        settings = db.query(SystemSetting).filter(
            SystemSetting.key.like("smtp_%")
        ).all()
        return {s.key.replace("smtp_", "", 1): s.value for s in settings}
    except Exception:
        return {}


def send_email(
    to: str,
    subject: str,
    body: str,
    db=None,
    cc: str = None,
    bcc: str = None,
    config: dict = None,
    attachments: List[Dict] = None,  # [{ "filename": "x.pdf", "data": bytes, "mime": "application/pdf" }]
    html_body: str = None,
) -> dict:
    """
    Sendet eine E-Mail mit optionalem HTML-Body und Anhängen.
    config kann direkt übergeben werden oder wird aus DB geladen.
    attachments: Liste von { filename, data (bytes), mime }
    """
    if config is None and db is not None:
        config = get_email_config(db)

    if not config:
        raise ValueError("Keine E-Mail-Konfiguration vorhanden")

    host = config.get("host", "")
    port = int(config.get("port", 587))
    user = config.get("user", "")
    password = config.get("password", "")
    from_addr = config.get("from", user)
    from_name = config.get("from_name", "Datenmonster")
    use_tls = str(config.get("tls", "true")).lower() == "true"

    if not host:
        raise ValueError("SMTP-Server nicht konfiguriert")

    # mixed wenn Anhänge vorhanden, sonst alternative für HTML+Text
    if attachments:
        msg = MIMEMultipart("mixed")
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(body, "plain", "utf-8"))
        if html_body:
            alt.attach(MIMEText(html_body, "html", "utf-8"))
        msg.attach(alt)
    else:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "plain", "utf-8"))
        if html_body:
            msg.attach(MIMEText(html_body, "html", "utf-8"))

    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_addr}>" if from_name else from_addr
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    if bcc:
        msg["Bcc"] = bcc

    recipients = [to]
    if cc:
        recipients.extend([a.strip() for a in cc.split(",")])
    if bcc:
        recipients.extend([a.strip() for a in bcc.split(",")])

    try:
        if use_tls:
            server = smtplib.SMTP(host, port, timeout=15)
            server.ehlo()
            server.starttls()
            server.ehlo()
        else:
            server = smtplib.SMTP_SSL(host, port, timeout=15)

        if user and password:
            server.login(user, password)

        server.sendmail(from_addr, recipients, msg.as_string())
        server.quit()
        logger.info(f"E-Mail gesendet an {to}: {subject}")
        return {"ok": True, "to": to, "subject": subject}

    except Exception as e:
        logger.error(f"E-Mail-Fehler: {e}")
        raise
