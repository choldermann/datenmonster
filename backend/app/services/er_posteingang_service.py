"""Belege aus einem Postfach oder Ordner in den Posteingang holen.

Das Abholen ist bewusst dumm: Es entscheidet nichts über den Inhalt, sondern
legt nur ab, was nach einem Beleg aussieht. Gelesen, geprüft und gebucht wird
erst in der Vorschau, von einem Menschen — genau wie bei einer von Hand
gezogenen Datei. So kann hier nichts schiefgehen, was Geld kostet.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.core.security import decrypt_credential
from app.models.er_posteingang import ErPosteingangBeleg, ErPosteingangQuelle

logger = logging.getLogger(__name__)

ABLAGE = Path("/app/uploads/er_posteingang")
# Ein Beleg, der groesser ist, ist keiner. Der Deckel schuetzt davor, dass ein
# versehentlich mitgeschicktes Archiv das Volume fuellt.
MAX_BYTES = 20 * 1024 * 1024


def _endungen(quelle: ErPosteingangQuelle) -> list[str]:
    roh = (quelle.endungen or ".xml,.pdf").lower()
    return [e.strip() for e in roh.split(",") if e.strip()]


def _passt(name: str, endungen: list[str]) -> bool:
    n = (name or "").lower()
    return any(n.endswith(e) for e in endungen)


def _ablegen(db: Session, quelle: Optional[ErPosteingangQuelle], mandant_id: int,
             dateiname: str, inhalt: bytes, absender: str = "",
             betreff: str = "") -> Optional[ErPosteingangBeleg]:
    """Einen Beleg ablegen – oder None, wenn es ihn schon gibt."""
    if not inhalt or len(inhalt) > MAX_BYTES:
        return None
    fingerabdruck = hashlib.sha256(inhalt).hexdigest()
    schon_da = (db.query(ErPosteingangBeleg)
                  .filter(ErPosteingangBeleg.hash == fingerabdruck,
                          ErPosteingangBeleg.mandant_id == mandant_id)
                  .first())
    if schon_da:
        return None

    ABLAGE.mkdir(parents=True, exist_ok=True)
    sicher = "".join(c for c in (dateiname or "beleg")
                     if c.isalnum() or c in "._- ")[:120] or "beleg"
    ziel = ABLAGE / f"{fingerabdruck[:16]}_{sicher}"
    ziel.write_bytes(inhalt)

    beleg = ErPosteingangBeleg(
        quelle_id=quelle.id if quelle else None, mandant_id=mandant_id,
        dateiname=dateiname or sicher, pfad=str(ziel), hash=fingerabdruck,
        groesse=len(inhalt), absender=absender[:200] or None,
        betreff=betreff[:300] or None, status="neu")
    db.add(beleg)
    db.flush()
    return beleg


def _hole_imap(db: Session, quelle: ErPosteingangQuelle) -> dict:
    from app.plugins.builtin.mail.imap_client import IMAPClient

    passwort = decrypt_credential(quelle.password or "")
    endungen = _endungen(quelle)
    neu, gesehen = 0, 0
    with IMAPClient(quelle.host, quelle.port or 993, quelle.username,
                    passwort, bool(quelle.ssl)) as client:
        ordner = quelle.ordner or "INBOX"
        for uid in client.fetch_unseen_uids(ordner):
            mail = client.fetch_message_by_uid(uid, ordner)
            if mail is None:
                continue
            gesehen += 1
            for anhang in mail.attachments:
                if not _passt(anhang.filename, endungen):
                    continue
                if _ablegen(db, quelle, quelle.mandant_id, anhang.filename,
                            anhang.content, mail.from_addr or "", mail.subject or ""):
                    neu += 1
            # Erst nach dem Ablegen anfassen: bricht etwas ab, wird die Mail
            # beim naechsten Lauf erneut geholt – doppelt abgelegt wird sie
            # wegen des Hashs trotzdem nicht.
            if quelle.nach_abholung == "verschieben" and quelle.ziel_ordner:
                client.move_message(uid, quelle.ziel_ordner, ordner)
            else:
                client.mark_seen(uid, ordner)
    return {"gesehen": gesehen, "neu": neu}


def _hole_ordner(db: Session, quelle: ErPosteingangQuelle) -> dict:
    wurzel = Path(quelle.pfad or "")
    if not wurzel.is_dir():
        raise ValueError(f"Ordner '{quelle.pfad}' gibt es nicht (im Container sichtbar?)")
    endungen = _endungen(quelle)
    neu, gesehen = 0, 0
    for datei in sorted(wurzel.iterdir()):
        if not datei.is_file() or not _passt(datei.name, endungen):
            continue
        gesehen += 1
        if _ablegen(db, quelle, quelle.mandant_id, datei.name,
                    datei.read_bytes(), betreff=str(datei)):
            neu += 1
    return {"gesehen": gesehen, "neu": neu}


def abholen(db: Session, quelle: ErPosteingangQuelle) -> dict:
    """Eine Quelle abfragen. Fehler landen an der Quelle, nicht in der Oberfläche."""
    try:
        ergebnis = _hole_imap(db, quelle) if quelle.art == "imap" else _hole_ordner(db, quelle)
        quelle.letzter_status = "ok"
        quelle.letzter_fehler = None
    except Exception as e:                                    # noqa: BLE001
        logger.exception("Posteingang %s: Abholen fehlgeschlagen", quelle.id)
        quelle.letzter_status = "fehler"
        quelle.letzter_fehler = str(e)[:500]
        ergebnis = {"gesehen": 0, "neu": 0, "fehler": str(e)[:300]}
    quelle.letzter_lauf = datetime.now(timezone.utc)
    db.commit()
    return ergebnis


def alle_abholen(db: Session, mandant_id: Optional[int] = None) -> list[dict]:
    q = db.query(ErPosteingangQuelle).filter(ErPosteingangQuelle.aktiv.is_(True))
    if mandant_id:
        q = q.filter(ErPosteingangQuelle.mandant_id == mandant_id)
    return [{"quelle_id": quelle.id, "name": quelle.name, **abholen(db, quelle)}
            for quelle in q.all()]
