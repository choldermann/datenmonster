from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

import time
import logging

_db_logger = logging.getLogger("datenmonster.db")


def db_retry(fn, *args, retries: int = 5, delay: float = 0.2, **kwargs):
    """
    Führt fn(*args, **kwargs) aus und wiederholt bei SQLite 'database is locked'.
    Exponentielles Backoff: 0.2s, 0.4s, 0.8s, 1.6s, 3.2s
    """
    last_exc = None
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            msg = str(e).lower()
            if "database is locked" in msg or "operationalerror" in msg and "locked" in msg:
                wait = delay * (2 ** attempt)
                _db_logger.warning(f"SQLite locked (Versuch {attempt+1}/{retries}), warte {wait:.1f}s …")
                time.sleep(wait)
                last_exc = e
            else:
                raise
    raise last_exc


def safe_commit(db, retries: int = 5):
    """db.commit() mit Retry bei SQLite-Lock."""
    db_retry(db.commit, retries=retries)


def safe_add_commit(db, obj, retries: int = 5):
    """db.add(obj) + commit() + refresh() mit Retry."""
    db.add(obj)
    db_retry(db.commit, retries=retries)
    db.refresh(obj)

