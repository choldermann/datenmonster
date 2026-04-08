from datetime import datetime, timedelta
from typing import Optional
import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
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


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
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
    if user is None:
        raise credentials_exception
    return user

# ─── Credential-Verschlüsselung ───────────────────────────────────────────────
def encrypt_credential(plaintext: str) -> str:
    """Verschlüsselt ein Passwort/Credential für DB-Speicherung."""
    if not plaintext:
        return plaintext
    try:
        from cryptography.fernet import Fernet
        from app.core.config import get_fernet_key
        f = Fernet(get_fernet_key())
        return f.encrypt(plaintext.encode()).decode()
    except ImportError:
        # cryptography nicht installiert - Warnung loggen, Plaintext speichern
        import logging
        logging.getLogger("datenmonster").warning(
            "cryptography-Paket nicht installiert - Credentials werden unverschlüsselt gespeichert. "
            "Installiere: pip install cryptography"
        )
        return plaintext
    except Exception as e:
        import logging
        logging.getLogger("datenmonster").error(f"Verschlüsselung fehlgeschlagen: {e}")
        return plaintext


def decrypt_credential(ciphertext: str) -> str:
    """Entschlüsselt ein gespeichertes Passwort/Credential."""
    if not ciphertext:
        return ciphertext
    try:
        from cryptography.fernet import Fernet, InvalidToken
        from app.core.config import get_fernet_key
        f = Fernet(get_fernet_key())
        return f.decrypt(ciphertext.encode()).decode()
    except ImportError:
        return ciphertext  # Plaintext-Fallback
    except Exception:
        # Nicht verschlüsselt (Legacy/Migration) → as-is zurückgeben
        return ciphertext
