from datetime import datetime, timedelta
from typing import Optional
import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from app.core.database import get_db
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def token_fuer(user: User) -> str:
    """Anmelde-Token mit Benutzer-ID und Token-Stand – beides wird bei jeder
    Anfrage geprüft (siehe get_current_user)."""
    return create_access_token({"sub": user.username, "uid": user.id,
                                "tv": user.token_version or 0})


def tokens_widerrufen(user: User) -> None:
    """Alle bisherigen Anmeldungen dieses Benutzers ungültig machen.
    Aufrufer committet."""
    user.token_version = (user.token_version or 0) + 1


def ist_deaktiviert(user: User) -> bool:
    """NULL zaehlt als aktiv (Altbestand vor der Spalte)."""
    return getattr(user, "is_active", True) is False


def get_current_user(request: Request, token: str = Depends(oauth2_scheme),
                     db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Ungültiger Token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None or ist_deaktiviert(user):
        # Ein deaktivierter Benutzer verliert auch ein noch gueltiges Token.
        raise credentials_exception
    # Widerrufene Tokens (Passwort geändert, "überall abmelden") und Tokens eines
    # gelöschten Benutzers, dessen Name neu vergeben wurde. Ältere Tokens ohne
    # diese Angaben gelten bis zu ihrem Ablauf weiter (Stand 0).
    if (payload.get("tv") or 0) != (user.token_version or 0):
        raise credentials_exception
    if payload.get("uid") is not None and payload.get("uid") != user.id:
        raise credentials_exception

    # Portal-Zugaenge erreichen nur die Endpunkte des Portals (siehe portal_zugriff).
    if getattr(user, "is_portal_only", False) and not getattr(user, "is_admin", False):
        from app.core.portal_zugriff import portal_darf
        if not portal_darf(request.method, request.url.path):
            raise HTTPException(status_code=403,
                                detail="Portal-Zugänge haben auf diesen Bereich keinen Zugriff.")
    return user

# ─── Credential-Verschlüsselung ───────────────────────────────────────────────
def encrypt_credential(plaintext: str) -> str:
    """Verschlüsselt ein Passwort/Credential für DB-Speicherung.

    Schlägt fehl statt still Klartext zu speichern: früher landete bei jedem
    Fehler (fehlendes Paket, kaputter Schlüssel) das Passwort unverschlüsselt in
    der Datenbank – und damit auch in jeder Sicherung. Lieber eine klare
    Fehlermeldung beim Speichern."""
    if not plaintext:
        return plaintext
    from cryptography.fernet import Fernet
    from app.core.config import get_fernet_key
    try:
        return Fernet(get_fernet_key()).encrypt(plaintext.encode()).decode()
    except Exception as e:
        import logging
        logging.getLogger("datenmonster").error(f"Verschlüsselung fehlgeschlagen: {e}")
        raise RuntimeError("Zugangsdaten konnten nicht verschlüsselt werden – nicht gespeichert") from e


def decrypt_credential(ciphertext: str) -> str:
    """Entschlüsselt ein gespeichertes Passwort/Credential."""
    if not ciphertext:
        return ciphertext
    try:
        from cryptography.fernet import Fernet, MultiFernet
        from app.core.config import get_fernet_keys
        f = MultiFernet([Fernet(k) for k in get_fernet_keys()])
        return f.decrypt(ciphertext.encode()).decode()
    except ImportError:
        return ciphertext  # Plaintext-Fallback
    except Exception:
        # Nicht verschlüsselt (Legacy/Migration) → as-is zurückgeben
        return ciphertext
