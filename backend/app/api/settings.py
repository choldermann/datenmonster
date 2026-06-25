from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.models.setting import SystemSetting


def _require_admin(user: User):
    if not getattr(user, "is_admin", False):
        raise HTTPException(403, "Nur Administratoren können System-Einstellungen ändern")

router = APIRouter(prefix="/api/settings", tags=["settings"])

EMAIL_KEYS = ["smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from", "smtp_from_name", "smtp_tls"]


def get_setting(db, key: str, default=None):
    s = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    return s.value if s else default


def set_setting(db, key: str, value: str):
    s = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if s:
        s.value = value
    else:
        s = SystemSetting(key=key, value=value)
        db.add(s)
    db.commit()


@router.get("/email")
def get_email_settings(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_admin(user)
    result = {}
    for key in EMAIL_KEYS:
        short = key.replace("smtp_", "")
        val = get_setting(db, key, "")
        # Passwort maskieren
        if short == "password" and val:
            val = "••••••••"
        result[key] = val
    return result


class EmailConfig(BaseModel):
    smtp_host: str = ""
    smtp_port: str = "587"
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_from_name: str = "Datenmonster"
    smtp_tls: bool = True


@router.post("/email")
def save_email_settings(body: EmailConfig, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_admin(user)
    data = body.dict()
    for key, value in data.items():
        # Passwort nicht überschreiben wenn maskiert
        if key == "smtp_password" and value == "••••••••":
            continue
        set_setting(db, key, str(value))
    return {"ok": True}


@router.post("/email/test")
def test_email(body: EmailConfig, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_admin(user)
    from app.services.email_service import send_email

    # Echtes Passwort laden wenn maskiert
    password = body.smtp_password
    if password == "••••••••":
        password = get_setting(db, "smtp_password", "")

    config = {
        "host": body.smtp_host,
        "port": body.smtp_port,
        "user": body.smtp_user,
        "password": password,
        "from": body.smtp_from or body.smtp_user,
        "from_name": body.smtp_from_name,
        "tls": str(body.smtp_tls),
    }

    to = body.smtp_user or body.smtp_from
    if not to:
        from fastapi import HTTPException
        raise HTTPException(400, "Keine Empfänger-Adresse – bitte Benutzername oder Absender-Adresse eingeben")

    send_email(
        to=to,
        subject="Datenmonster – Test E-Mail",
        body="Diese Test-E-Mail wurde erfolgreich vom Datenmonster E-Mail-Service gesendet.",
        config=config,
    )
    return {"ok": True, "message": f"Test-E-Mail erfolgreich an {to} gesendet"}


# ── KI / Claude API ───────────────────────────────────────────────────────────

class AiConfig(BaseModel):
    claude_api_key: str = ""

@router.get("/ai")
def get_ai_settings(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_admin(user)
    key = get_setting(db, "claude_api_key", "")
    return {"claude_api_key": "••••••••" if key else ""}

@router.post("/ai")
def save_ai_settings(body: AiConfig, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_admin(user)
    if body.claude_api_key and body.claude_api_key != "••••••••":
        set_setting(db, "claude_api_key", body.claude_api_key)
    return {"ok": True}
