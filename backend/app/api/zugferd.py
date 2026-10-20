"""API für den ZUGFeRD-Ausgang (Widget „zugferd“).

Rechte, wie beim Posteingang der Eingangsrechnungen:
  - Ziel und Tabellen (mit FTP-Zugangsdaten) pflegt nur ein Admin.
  - Firmendaten pflegt, wer im Projekt Editor ist.
  - Protokoll ansehen, Lauf anstoßen, abgewiesene Rechnung erneut einreihen darf
    jeder, der die Verbindung nutzen darf - im Portal über die Freigabe des
    Formulars, in dem das Widget steckt.
"""
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.api.eingangsrechnung import _check_connection_access
from app.api.projects import require_editor
from app.core.database import get_db
from app.core.security import encrypt_credential
from app.core.zugriff import lade_verbindung, nur_admin
from app.models.dataset import DbConnection
from app.models.user import User
from app.models.zugferd import ZugferdAusgang, ZugferdBeleg
from app.services import business_config_service as cfg
from app.services import zugferd_service as dienst
from app.services.scheduler_service import register_zugferd_job, unregister_zugferd_job

router = APIRouter(prefix="/api/zugferd", tags=["zugferd"])

GEHEIM = "********"


def _verbindung(connection_id: int, user: User, db: Session) -> DbConnection:
    if getattr(user, "is_portal_only", False) and not getattr(user, "is_admin", False):
        _check_connection_access(connection_id, user, db, widget_types=("zugferd",))
        conn = db.query(DbConnection).filter(DbConnection.id == connection_id).first()
        if not conn:
            raise HTTPException(404, "Verbindung nicht gefunden")
        return conn
    return lade_verbindung(connection_id, user, db)


def _ausgang(connection_id: int, db: Session) -> Optional[ZugferdAusgang]:
    return db.query(ZugferdAusgang).filter(ZugferdAusgang.connection_id == connection_id).first()


def _raus(a: Optional[ZugferdAusgang]) -> Optional[dict]:
    if a is None:
        return None
    return {
        "id": a.id, "connection_id": a.connection_id,
        "tabelle_kopf": a.tabelle_kopf, "tabelle_positionen": a.tabelle_positionen,
        "protokoll": a.protokoll, "host": a.host, "port": a.port, "username": a.username,
        "password": GEHEIM if a.password else "", "verzeichnis": a.verzeichnis,
        "dateiname_muster": a.dateiname_muster, "aktiv": bool(a.aktiv),
        "hat_schluessel": bool(a.ausloese_hash),
        "cron_expr": a.cron_expr,
        "letzter_lauf": a.letzter_lauf.isoformat() if a.letzter_lauf else None,
        "letzter_status": a.letzter_status, "letzter_fehler": a.letzter_fehler,
    }


@router.get("/einstellungen")
def einstellungen(connection_id: int, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    conn = _verbindung(connection_id, user, db)
    werte = cfg.get_zugferd(conn.project_id, db, conn.id)
    felder = [{**m, "value": werte.get(m["key"], m["default"])} for m in cfg.zugferd_meta()]
    a = _ausgang(conn.id, db)
    return {
        "connection_id": conn.id, "connection_name": conn.name,
        "felder": felder, "fehlend": cfg.zugferd_unvollstaendig(werte),
        # Zugangsdaten nur für Admins - alle anderen sehen nur, ob und wann es lief.
        "ausgang": _raus(a) if getattr(user, "is_admin", False) else (
            {k: v for k, v in (_raus(a) or {}).items()
             if k in ("aktiv", "cron_expr", "letzter_lauf", "letzter_status", "hat_schluessel",
                      "letzter_fehler", "verzeichnis", "host")} if a else None),
        "darf_einrichten": bool(getattr(user, "is_admin", False)),
    }


class FeldIn(BaseModel):
    connection_id: int
    key: str
    value: str


@router.put("/firmendaten")
def firmendaten(body: FeldIn, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    conn = _verbindung(body.connection_id, user, db)
    require_editor(conn.project_id, user, db)
    meta = {m["key"]: m for m in cfg.zugferd_meta()}
    if body.key not in meta:
        raise HTTPException(400, f"Unbekanntes Feld: {body.key}")
    wert = (body.value or "").strip()
    if body.key == "land" and wert and (len(wert) != 2 or not wert.isalpha()):
        raise HTTPException(400, "Land als ISO-Code, z. B. DE")
    if body.key == "land":
        wert = wert.upper()
    if body.key == "iban" and wert:
        roh = wert.replace(" ", "").upper()
        # Prüfziffer nach ISO 13616 - ein Tippfehler in der IBAN geht sonst an
        # jeden Kunden raus.
        num = "".join(str(int(c, 36)) for c in roh[4:] + roh[:4]) if roh.isalnum() else ""
        if len(roh) < 15 or not num or int(num) % 97 != 1:
            raise HTTPException(400, "IBAN ist ungültig (Prüfziffer stimmt nicht)")
        wert = roh
    if body.key in ("ustid", "weitere_ustids") and wert:
        from app.services.zugferd_xml import ustid_liste, _ustid_ok
        nummern = ustid_liste(wert)
        falsch = [n for n in nummern if not _ustid_ok(n)]
        if falsch:
            raise HTTPException(400, f"Keine USt-IdNr.: {', '.join(falsch)} (Länderkürzel + Nummer)")
        if body.key == "ustid" and len(nummern) != 1:
            raise HTTPException(400, "Hier nur die Standard-USt-IdNr. – weitere ins Feld darunter")
        wert = ", ".join(nummern)
    if body.key == "zahlungsart" and wert and wert not in {o["value"] for o in cfg.ZAHLUNGSARTEN}:
        raise HTTPException(400, "Unbekannte Zahlungsart")
    if wert == "":
        cfg.reset_value(conn.project_id, db, "zugferd", body.key, conn.id)
    else:
        cfg.set_value(conn.project_id, db, "zugferd", body.key, wert, conn.id)
    return {"key": body.key, "value": wert}


class AusgangIn(BaseModel):
    connection_id: int
    tabelle_kopf: str = "dbo.tInvoice"
    tabelle_positionen: str = "dbo.tInvoicePositions"
    protokoll: str = "ftp"
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None           # GEHEIM = unverändert
    verzeichnis: str = "/"
    dateiname_muster: str = "{nummer}.pdf"
    aktiv: bool = False
    cron_expr: Optional[str] = "*/5 * * * *"


@router.put("/ausgang")
def ausgang_speichern(body: AusgangIn, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    nur_admin(user, "Nur Administratoren dürfen das Ziel einrichten")
    conn = lade_verbindung(body.connection_id, user, db)
    try:
        dienst.tabelle_pruefen(body.tabelle_kopf)
        dienst.tabelle_pruefen(body.tabelle_positionen)
    except dienst.LaufFehler as e:
        raise HTTPException(400, str(e))
    if body.protokoll not in ("ftp", "sftp"):
        raise HTTPException(400, "Protokoll ftp oder sftp")
    cron = (body.cron_expr or "").strip()
    if cron and len(cron.split()) != 5:
        raise HTTPException(400, "Zeitplan als Cron-Ausdruck mit 5 Feldern, z. B. */5 * * * *")

    a = _ausgang(conn.id, db) or ZugferdAusgang(connection_id=conn.id)
    daten = body.model_dump(exclude={"connection_id", "password"})
    for k, v in daten.items():
        setattr(a, k, v)
    a.cron_expr = cron or None
    a.project_id = conn.project_id
    if body.password and body.password != GEHEIM:
        a.password = encrypt_credential(body.password)
    db.add(a)
    db.commit()
    db.refresh(a)
    if a.aktiv and a.cron_expr:
        register_zugferd_job(a.id, a.cron_expr)
    else:
        unregister_zugferd_job(a.id)
    return _raus(a)


@router.post("/ausgang/test")
def ausgang_testen(connection_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """FTP schreiben + Tabellen und Spalten prüfen - alles, was einen Lauf scheitern ließe."""
    nur_admin(user, "Nur Administratoren")
    conn = lade_verbindung(connection_id, user, db)
    a = _ausgang(conn.id, db)
    if not a:
        raise HTTPException(404, "Noch nichts eingerichtet – erst speichern")
    ergebnis = {"ftp": None, "tabellen": None}
    if (a.host or "").strip():
        try:
            ergebnis["ftp"] = dienst.ziel_testen(a)
        except dienst.LaufFehler as e:
            ergebnis["ftp"] = {"ok": False, "meldung": str(e)}
    try:
        engine = dienst._engine(conn.id, db)
        try:
            fehlend = dienst.tabellen_pruefen(engine, dienst.tabelle_pruefen(a.tabelle_kopf),
                                              dienst.tabelle_pruefen(a.tabelle_positionen))
        finally:
            engine.dispose()
        if not fehlend:
            meldung = "Tabellen und Spalten vollständig"
        elif fehlend[0].startswith("Tabelle "):
            meldung = fehlend[0] + " – Tabellen mit dem SQL-Skript anlegen"
        else:
            meldung = "Spalten fehlen: " + ", ".join(fehlend[:12]) + (" …" if len(fehlend) > 12 else "")
        ergebnis["tabellen"] = {"ok": not fehlend, "meldung": meldung}
    except dienst.LaufFehler as e:
        ergebnis["tabellen"] = {"ok": False, "meldung": str(e)}
    return ergebnis


@router.post("/ausgang/schluessel")
def schluessel_erzeugen(connection_id: int, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """Neuen Auslöse-Schlüssel für Access erzeugen. Ein alter verliert seine Gültigkeit."""
    import secrets
    nur_admin(user, "Nur Administratoren")
    conn = lade_verbindung(connection_id, user, db)
    a = _ausgang(conn.id, db)
    if not a:
        raise HTTPException(404, "Noch nichts eingerichtet – erst speichern")
    schluessel = "zf_" + secrets.token_urlsafe(24)
    a.ausloese_hash = dienst.schluessel_hash(schluessel)
    db.commit()
    # Nur dieses eine Mal im Klartext - gespeichert wird der Hash.
    return {"schluessel": schluessel}


@router.post("/anstoss", status_code=202)
def anstoss(x_ausloese_schluessel: str = Header(default=""), db: Session = Depends(get_db)):
    """Access meldet „neue Rechnung da“. Ohne Benutzeranmeldung, nur mit dem Schlüssel.

    Der Schlüssel kann ausschließlich einen Lauf anstoßen: die Antwort verrät
    nichts über Rechnungen oder Einstellungen. Verarbeitet wird im Hintergrund,
    damit Access nicht auf den Lauf (oder einen langsamen VPN) warten muss.
    """
    if len(x_ausloese_schluessel) < 20:
        raise HTTPException(401, "Schlüssel fehlt")
    a = (db.query(ZugferdAusgang)
           .filter(ZugferdAusgang.ausloese_hash == dienst.schluessel_hash(x_ausloese_schluessel))
           .first())
    if not a:
        raise HTTPException(401, "Schlüssel ungültig")
    dienst.anstossen(a.id)
    return {"angenommen": True}


@router.post("/lauf")
def lauf(connection_id: int, user: User = Depends(get_current_user),
         db: Session = Depends(get_db)):
    conn = _verbindung(connection_id, user, db)
    a = _ausgang(conn.id, db)
    if not a:
        raise HTTPException(404, "Der ZUGFeRD-Ausgang ist noch nicht eingerichtet")
    return dienst.verarbeiten(db, a, ausloeser=user.username or "Benutzer")


@router.get("/statistik")
def statistik(connection_id: int, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    """Wie viele Rechnungen stehen in tInvoice auf welchem Status?"""
    conn = _verbindung(connection_id, user, db)
    a = _ausgang(conn.id, db)
    if not a:
        return {"status": {}}
    try:
        engine = dienst._engine(conn.id, db)
        try:
            return {"status": dienst.statistik(engine, dienst.tabelle_pruefen(a.tabelle_kopf))}
        finally:
            engine.dispose()
    except Exception as e:                                    # noqa: BLE001
        return {"status": {}, "fehler": str(e).splitlines()[0][:300]}


@router.get("/belege")
def belege(connection_id: int, status: str = "alle", suche: str = "", limit: int = 200,
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    conn = _verbindung(connection_id, user, db)
    q = db.query(ZugferdBeleg).filter(ZugferdBeleg.connection_id == conn.id)
    if status in ("ok", "fehler"):
        q = q.filter(ZugferdBeleg.status == status)
    if suche.strip():
        s = f"%{suche.strip()}%"
        q = q.filter((ZugferdBeleg.nummer.ilike(s)) | (ZugferdBeleg.kunde.ilike(s)))
    zeilen = q.order_by(ZugferdBeleg.id.desc()).limit(min(max(limit, 1), 1000)).all()
    return [{
        "id": b.id, "invoice_id": b.invoice_id, "nummer": b.nummer, "art": b.art,
        "kunde": b.kunde, "datum": b.datum,
        "brutto": float(b.brutto) if b.brutto is not None else None,
        "status": b.status, "meldung": b.meldung, "dateiname": b.dateiname,
        "hat_datei": bool(b.pfad and Path(b.pfad).is_file()),
        "ausgeloest_von": b.ausgeloest_von,
        "erstellt_am": b.erstellt_am.isoformat() if b.erstellt_am else None,
    } for b in zeilen]


def _beleg(beleg_id: int, user: User, db: Session) -> ZugferdBeleg:
    b = db.query(ZugferdBeleg).filter(ZugferdBeleg.id == beleg_id).first()
    if not b:
        raise HTTPException(404, "Eintrag gibt es nicht")
    _verbindung(b.connection_id, user, db)
    return b


@router.get("/belege/{beleg_id}/datei")
def beleg_datei(beleg_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    b = _beleg(beleg_id, user, db)
    if not b.pfad or not Path(b.pfad).is_file():
        raise HTTPException(410, "Die Datei liegt nicht mehr vor")
    return FileResponse(b.pfad, media_type="application/pdf", filename=b.dateiname or "rechnung.pdf")


@router.get("/belege/{beleg_id}/xml")
def beleg_xml(beleg_id: int, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    from app.services.zugferd_pdf import xml_aus_pdf
    b = _beleg(beleg_id, user, db)
    if not b.pfad or not Path(b.pfad).is_file():
        raise HTTPException(410, "Die Datei liegt nicht mehr vor")
    xml = xml_aus_pdf(Path(b.pfad).read_bytes())
    if xml is None:
        raise HTTPException(404, "Kein XML in der Datei")
    return Response(xml, media_type="application/xml")


@router.post("/belege/{beleg_id}/erneut")
def beleg_erneut(beleg_id: int, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """Rechnung in tInvoice wieder auf NEU setzen (nach einer Korrektur in Access)."""
    b = _beleg(beleg_id, user, db)
    a = db.query(ZugferdAusgang).filter(ZugferdAusgang.id == b.ausgang_id).first()
    if not a or not b.invoice_id:
        raise HTTPException(404, "Zu diesem Eintrag gibt es keine Rechnung mehr")
    engine = dienst._engine(a.connection_id, db)
    try:
        ok = dienst.erneut_einreihen(engine, dienst.tabelle_pruefen(a.tabelle_kopf), b.invoice_id)
    finally:
        engine.dispose()
    if not ok:
        raise HTTPException(409, "Die Rechnung steht nicht auf FEHLER oder OK (oder wurde gelöscht)")
    # Ohne Zeitplan käme sie sonst erst mit dem nächsten Anstoß aus Access dran.
    dienst.anstossen(a.id)
    return {"ok": True}


@router.get("/sql-skript")
def sql_skript(user: User = Depends(get_current_user)):
    from app.services.zugferd_sql import SKRIPT
    return Response(SKRIPT.encode("utf-8"), media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="zugferd_tabellen.sql"'})
