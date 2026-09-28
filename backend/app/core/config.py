import os
from dotenv import load_dotenv

load_dotenv()

# ─── SECRET_KEY ───────────────────────────────────────────────────────────────
# Signiert die Anmelde-Tokens und ist die Grundlage für die Verschlüsselung der
# gespeicherten Zugangsdaten. Früher lief ohne SECRET_KEY still ein öffentlich
# bekannter Standardwert – damit konnte jeder Admin-Tokens fälschen und alle
# Zugangsdaten entschlüsseln. Jetzt: fehlt er, wird einmalig ein zufälliger
# Schlüssel erzeugt und im Daten-Volume abgelegt (übersteht Updates).
# Nicht einfach abbrechen: eine Installation ohne Eintrag stünde nach dem
# nächsten Update sonst still.
import secrets as _secrets

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

LEGACY_SECRET = "dev-secret-key-change-in-prod"  # nur noch zum Lesen alter Daten


def _secret_aus_datei() -> str:
    pfad = os.path.join(UPLOAD_DIR, ".secret_key")
    try:
        with open(pfad, encoding="utf-8") as f:
            wert = f.read().strip()
        if len(wert) >= 32:
            return wert
    except FileNotFoundError:
        pass
    wert = _secrets.token_hex(32)
    fd = os.open(pfad, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(wert)
    import logging as _log
    _log.getLogger("datenmonster").warning(
        "SECRET_KEY war nicht gesetzt – zufälligen Schlüssel erzeugt und in %s abgelegt. "
        "Alle Benutzer müssen sich einmal neu anmelden.", pfad)
    return wert


_raw_secret = os.getenv("SECRET_KEY", "").strip()
if not _raw_secret or _raw_secret == LEGACY_SECRET:
    _raw_secret = _secret_aus_datei()
SECRET_KEY = _raw_secret

# ─── Credential-Verschlüsselung ───────────────────────────────────────────────
# Fernet-Key wird aus SECRET_KEY abgeleitet - kein separater Key nötig
import base64 as _base64
import hashlib as _hashlib


def _fernet_aus(secret: str) -> bytes:
    # SHA256 → 32 Bytes → Base64url → Fernet-Key
    return _base64.urlsafe_b64encode(_hashlib.sha256(secret.encode()).digest())


def get_fernet_key() -> bytes:
    """Schlüssel zum Verschlüsseln (immer der aktuelle)."""
    return _fernet_aus(SECRET_KEY)


def get_fernet_keys() -> list:
    """Schlüssel zum Entschlüsseln: aktueller zuerst, dann der alte Standardwert –
    Zugangsdaten, die eine Installation ohne SECRET_KEY gespeichert hat, bleiben
    so lesbar und werden beim nächsten Speichern mit dem neuen Schlüssel abgelegt."""
    return [_fernet_aus(SECRET_KEY), _fernet_aus(LEGACY_SECRET)]
ALGORITHM = "HS256"
# Token-Expiry: Standard 24h, via Env überschreibbar
_expire_str = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "")
try:
    ACCESS_TOKEN_EXPIRE_MINUTES = int(_expire_str) if _expire_str else 60 * 24 * 7  # 7 Tage Default
except ValueError:
    ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./datenmonster.db")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")

PLUGIN_MANAGER_URL = os.getenv("PLUGIN_MANAGER_URL", "")
