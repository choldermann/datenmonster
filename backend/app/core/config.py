import os
from dotenv import load_dotenv

load_dotenv()

_raw_secret = os.getenv("SECRET_KEY", "")
if not _raw_secret or _raw_secret == "dev-secret-key-change-in-prod":
    import logging as _log
    _log.getLogger("datenmonster").critical(
        "⚠ SICHERHEIT: SECRET_KEY ist nicht gesetzt oder nutzt den Standardwert! "
        "Setze SECRET_KEY in der .env / docker-compose.yml auf einen langen Zufallswert. "
        "Beispiel: openssl rand -hex 32"
    )
    _raw_secret = "dev-secret-key-change-in-prod"
SECRET_KEY = _raw_secret

# ─── Credential-Verschlüsselung ───────────────────────────────────────────────
# Fernet-Key wird aus SECRET_KEY abgeleitet - kein separater Key nötig
import base64 as _base64
import hashlib as _hashlib

def get_fernet_key() -> bytes:
    """Leitet einen Fernet-kompatiblen Key aus SECRET_KEY ab."""
    # SHA256 → 32 Bytes → Base64url → Fernet-Key
    digest = _hashlib.sha256(SECRET_KEY.encode()).digest()
    return _base64.urlsafe_b64encode(digest)
ALGORITHM = "HS256"
# Token-Expiry: Standard 24h, via Env überschreibbar
_expire_str = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "")
try:
    ACCESS_TOKEN_EXPIRE_MINUTES = int(_expire_str) if _expire_str else 60 * 24 * 7  # 7 Tage Default
except ValueError:
    ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./datenmonster.db")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

PLUGIN_MANAGER_URL = os.getenv("PLUGIN_MANAGER_URL", "")
