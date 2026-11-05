"""Verbindung zum Testserver (über Datenmonster-Verbindung 8) mit frei
wählbarer Datenbank. Läuft im Backend-Container:

    docker compose exec -T backend python -m tools.demo_daten.<skript>
"""
import re
from urllib.parse import unquote_plus

import pyodbc

VERBINDUNG = "Demo (synthetisch)"  # Datenmonster-Verbindung zu 192.168.20.185\JTLTEST
QUELLE = "eazybusiness_demo"    # alte anonymisierte Demo – am 05.11.2026 gelöscht,
                                # Sicherung: DATA\eazybusiness_synth_quelle.bak
ZIEL = "eazybusiness_synth"     # synthetische Demo


def odbc(datenbank: str) -> str:
    from app.core.database import SessionLocal
    from app.models.dataset import DbConnection
    from app.services import db_service
    db = SessionLocal()
    try:
        c = db.query(DbConnection).filter(DbConnection.name == VERBINDUNG).first()
        if c is None:
            raise RuntimeError(f"Datenmonster-Verbindung „{VERBINDUNG}“ fehlt")
        roh = unquote_plus(db_service.get_engine_str(c).split("odbc_connect=", 1)[1])
    finally:
        db.close()
    return re.sub(r"DATABASE=[^;]*;", f"DATABASE={datenbank};", roh)


def verbinden(datenbank: str, autocommit: bool = True) -> pyodbc.Connection:
    return pyodbc.connect(odbc(datenbank), autocommit=autocommit, timeout=30)


def ausfuehren_leeren(cur, sql: str):
    """BACKUP/RESTORE liefern Fortschritts-Resultsets; pyodbc bricht ab, wenn
    man sie nicht abholt (Falle aus der ersten Demo-DB)."""
    cur.execute(sql)
    while True:
        try:
            if not cur.nextset():
                break
        except pyodbc.ProgrammingError:
            break
