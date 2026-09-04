"""
Stammdaten-Übernahme nach JTL: Vorschau (Dry-Run) und Schreiben.

Die eigentliche Logik steht in services/jtl_artikel_writer.py — dort auch die an
der Wawi geprüften Fakten (Trigger, bRowversion, Weißliste der sechs Spalten).
Dieser Router ist nur die Klappe davor: Zugriff prüfen, Verbindung auflösen,
Plan bauen, protokollieren.

Zwei Stufen, absichtlich getrennt:
  POST /plan   baut den Plan und führt NICHTS aus. Zeigt je Wert alt → neu und
               warum eine Zeile nicht geschrieben würde.
  POST /write  führt aus, aber nur mit bestaetigt=true und nur, was in einer
               frischen Vorschau als „bereit\" gilt. Kollisionen (bRowversion)
               werden dabei übersprungen, nicht überschrieben.

Reine Portal-Benutzer kommen hier grundsätzlich nicht durch: in eine Wawi
schreiben ist kein Portal-Vorgang.
"""
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.dataset import Dataset, DbConnection
from app.models.mapping import Mapping
from app.models.user import User
from app.services.jtl_artikel_writer import FELDER, MAX_AENDERUNGEN, ArtikelWriter

router = APIRouter(prefix="/api/stammdaten", tags=["stammdaten"])
logger = logging.getLogger(__name__)


# ── Ein- und Ausgaben ───────────────────────────────────────────────────────────

class Aenderung(BaseModel):
    kArtikel: int
    feld: str
    wert: Any = None
    quelle: Optional[str] = None
    # Hebt `ersetzen` des Stapels für genau diesen Wert auf (None = Stapel gilt).
    # Gedacht für die Beschreibung: dort ist Überschreiben der Zweck der Übung.
    ersetzen: Optional[bool] = None


class PlanRequest(BaseModel):
    aenderungen: list[Aenderung]
    connection_id: Optional[int] = None   # entweder direkt …
    mapping_id: Optional[int] = None      # … oder die Verbindung des Mappings
    ersetzen: bool = False                # gefüllte Felder überschreiben?


class WriteRequest(PlanRequest):
    bestaetigt: bool = False              # ohne Häkchen wird nicht geschrieben
    ueberspringe_fehler: bool = False     # fehlerhafte Zeilen auslassen statt blockieren


# ── Verbindung auflösen und Zugriff prüfen ──────────────────────────────────────

def _connection_aus_mapping(mapping_id: int, user: User, db: Session) -> tuple[int, int]:
    """(connection_id, project_id) aus einem Mapping – SQL-Node zuerst, sonst Dataset."""
    from app.api.projects import can_read_project

    m = db.query(Mapping).filter(Mapping.id == mapping_id).first()
    if not m:
        raise HTTPException(404, "Mapping nicht gefunden")
    if not can_read_project(m.project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf dieses Mapping")

    for sn in (m.sql_nodes or []):
        if sn.get("connection_id"):
            return int(sn["connection_id"]), m.project_id
    for node in (m.canvas_nodes or []):
        ds = db.query(Dataset).filter(Dataset.id == node.get("dataset_id")).first()
        if ds and ds.source_connection_id:
            return int(ds.source_connection_id), m.project_id
    raise HTTPException(400, "Das Mapping hat keine Datenbank-Verbindung, aus der "
                             "sich die Wawi ableiten lässt")


def _mandant_beruecksichtigen(connection_id: int, project_id: Optional[int],
                              user: User, db: Session) -> int:
    """Schreibzugriff auf die WaWi lenken, die der Anwender gerade ansieht.

    Die Artikel-IDs der Oberfläche stammen aus der Datenbank des aktiven
    Mandanten; die Regel selbst steht in mandant_service.schreibziel, weil auch
    die Debitorenpflege des DATEV-Exports sie braucht.
    """
    from app.services import mandant_service
    return mandant_service.schreibziel(connection_id, project_id, user, db)


def _aufloesen(req: PlanRequest, user: User, db: Session) -> tuple[int, Optional[int]]:
    """Verbindung bestimmen und Zugriff prüfen. Gibt (connection_id, project_id)."""
    from app.api.projects import can_read_project
    from app.services import mandant_service

    if getattr(user, "is_portal_only", False) and not getattr(user, "is_admin", False):
        raise HTTPException(403, "Stammdaten-Übernahme ist Portal-Benutzern nicht erlaubt")

    if req.mapping_id and not req.connection_id:
        cid, pid = _connection_aus_mapping(req.mapping_id, user, db)
        return _mandant_beruecksichtigen(cid, pid, user, db), pid

    if not req.connection_id:
        raise HTTPException(400, "connection_id oder mapping_id angeben")

    conn = db.query(DbConnection).filter(DbConnection.id == req.connection_id).first()
    if not conn:
        raise HTTPException(404, f"DB-Verbindung #{req.connection_id} nicht gefunden")
    if not can_read_project(conn.project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf diese Verbindung")
    if not mandant_service.darf_nutzen(conn.id, user, db, conn.project_id):
        raise HTTPException(403, "Dieser Mandant ist für Sie nicht freigegeben")
    return _mandant_beruecksichtigen(int(conn.id), conn.project_id, user, db), conn.project_id


def _writer(connection_id: int) -> ArtikelWriter:
    try:
        return ArtikelWriter(connection_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


def _items(req: PlanRequest) -> list[dict]:
    if not req.aenderungen:
        raise HTTPException(400, "Keine Änderungen übergeben")
    if len(req.aenderungen) > MAX_AENDERUNGEN:
        raise HTTPException(413, f"{len(req.aenderungen)} Änderungen – erlaubt sind "
                                 f"{MAX_AENDERUNGEN} je Lauf")
    return [a.model_dump() for a in req.aenderungen]


# ── Endpunkte ───────────────────────────────────────────────────────────────────

@router.get("/felder")
def felder(user: User = Depends(get_current_user)):
    """Welche Felder lassen sich überhaupt schreiben? (Weißliste des Writers)"""
    return [{"feld": name, "label": f.label, "tabelle": f.tabelle, "spalte": f.spalte}
            for name, f in FELDER.items()]


class AbleitenRequest(BaseModel):
    kArtikel: list[int]
    connection_id: Optional[int] = None
    mapping_id: Optional[int] = None
    felder: list[str] = ["Warennummer", "Herkunftsland"]
    nur_fehlende: bool = True


@router.post("/ableiten")
def ableiten(req: AbleitenRequest, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    """Warennummer und Ursprungsland aus den eigenen gepflegten Artikeln ableiten.

    Zweite Quelle neben der Herstellerseite und für diese beiden Felder meist die
    einzige, die überhaupt etwas liefert. Liest nur, schreibt nichts.
    """
    from app.services.stammdaten_ableitung import FELDER, Ableitung

    # Für die Zugriffsprüfung dieselbe Mechanik wie beim Schreiben verwenden.
    connection_id, _ = _aufloesen(
        PlanRequest(aenderungen=[], connection_id=req.connection_id,
                    mapping_id=req.mapping_id), user, db)
    felder = tuple(f for f in req.felder if f in FELDER)
    if not felder:
        raise HTTPException(400, "Keine gültigen Felder angefragt")
    try:
        werke = Ableitung(connection_id).vorschlaege(
            req.kArtikel, felder, nur_fehlende=req.nur_fehlende)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"geprueft": len(req.kArtikel), "vorschlaege": werke,
            "connection_id": connection_id}


@router.post("/plan")
def plan(req: PlanRequest, user: User = Depends(get_current_user),
         db: Session = Depends(get_db)):
    """Vorschau: was würde geschrieben? Führt nichts aus."""
    connection_id, _ = _aufloesen(req, user, db)
    p = _writer(connection_id).build_plan(_items(req), dry_run=True, ersetzen=req.ersetzen)
    return {**p.to_dict(), "connection_id": connection_id}


@router.post("/write")
def write(req: WriteRequest, user: User = Depends(get_current_user),
          db: Session = Depends(get_db)):
    """Echtes Schreiben in die Wawi – nur mit bestaetigt=true.

    Vor dem Schreiben läuft immer eine frische Vorschau: gegen deren Ergebnis
    wird geschrieben, nicht gegen das, was die Oberfläche zu wissen glaubt.
    """
    if not req.bestaetigt:
        raise HTTPException(400, "Ohne ausdrückliche Bestätigung wird nicht geschrieben")

    connection_id, project_id = _aufloesen(req, user, db)
    items = _items(req)
    w = _writer(connection_id)

    vorschau = w.build_plan(items, dry_run=True, ersetzen=req.ersetzen)
    uebersprungen: list[dict] = []

    if req.ueberspringe_fehler:
        # Nur das schreiben, was die Vorschau als bereit meldet – ein einzelner
        # ungültiger Wert soll den ganzen Stapel nicht blockieren.
        bereit = {(a["kArtikel"], a["feld"]) for a in vorschau.bereit}
        uebersprungen = [a for a in vorschau.to_dict()["aenderungen"]
                         if (a["kArtikel"], a["feld"]) not in bereit]
        items = [i for i in items if (int(i["kArtikel"]), i["feld"]) in bereit]
        if not items:
            out = vorschau.to_dict()
            out["geschrieben"] = 0
            out["uebersprungen"] = len(uebersprungen)
            out["connection_id"] = connection_id
            return out

    p = w.build_plan(items, dry_run=False, ersetzen=req.ersetzen)
    out = p.to_dict()
    geschrieben = [a for a in out["aenderungen"] if a["status"] == "geschrieben"]
    out["aenderungen"] += uebersprungen
    out["geschrieben"] = len(geschrieben)
    out["uebersprungen"] = len(uebersprungen)
    out["connection_id"] = connection_id

    try:
        from app.services.db_logger import log as _dblog
        _dblog(db, "success" if geschrieben else "warning", "jtl_artikel_writer",
               "stammdaten_write",
               f"{len(geschrieben)} Werte in die Wawi geschrieben "
               f"({len({a['kArtikel'] for a in geschrieben})} Artikel)",
               entity_id=connection_id, project_id=project_id,
               rows_processed=len(geschrieben),
               details={
                   "benutzer": getattr(user, "username", None) or getattr(user, "email", None),
                   "ersetzen": req.ersetzen,
                   "uebersprungen": len(uebersprungen),
                   "kollisionen": len([a for a in out["aenderungen"]
                                       if a["status"] == "kollision"]),
                   "werte": [{k: a[k] for k in ("kArtikel", "ArtNr", "feld", "alt", "neu",
                                                "quelle", "status")}
                             for a in out["aenderungen"]][:MAX_AENDERUNGEN],
               })
    except Exception:  # Protokoll darf einen erfolgreichen Write nie kippen
        logger.exception("Schreibprotokoll konnte nicht gespeichert werden")

    return out


# ── Artikel neu anlegen ─────────────────────────────────────────────────────────
#
# Gedacht für den Fall, dass beim Buchen einer Lieferantenrechnung eine Zeile
# auftaucht, zu der es noch keinen Artikel gibt. Gleiche zwei Stufen wie oben:
# /artikel-pruefen schreibt nichts, /artikel-anlegen verlangt bestaetigt=true.

class NeuerArtikelRequest(BaseModel):
    connection_id: Optional[int] = None
    mapping_id: Optional[int] = None
    cArtNr: str
    cName: str
    cKurzBeschreibung: Optional[str] = None
    cBarcode: Optional[str] = None          # EAN
    cHAN: Optional[str] = None
    cTaric: Optional[str] = None            # Warentarifnummer
    cHerkunftsland: Optional[str] = None
    fGewicht: Optional[Any] = None
    fVKNetto: Optional[Any] = None
    lagerAktiv: bool = True
    # Lieferantenzuordnung – die Bestellnummer beim Lieferanten ist genau das,
    # wonach die nächste Rechnung dieses Lieferanten sucht.
    kLieferant: Optional[int] = None
    cLiefArtNr: Optional[str] = None
    cLiefName: Optional[str] = None
    fEKNetto: Optional[Any] = None
    bestaetigt: bool = False


def _anleger(req: NeuerArtikelRequest, user: User, db: Session):
    from app.services.jtl_artikel_writer import ArtikelAnleger
    connection_id, project_id = _aufloesen(
        PlanRequest(aenderungen=[], connection_id=req.connection_id,
                    mapping_id=req.mapping_id), user, db)
    try:
        return ArtikelAnleger(connection_id), connection_id, project_id
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/artikel-pruefen")
def artikel_pruefen(req: NeuerArtikelRequest, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """Vorschau: ließe sich dieser Artikel anlegen? Schreibt nichts."""
    a, connection_id, _ = _anleger(req, user, db)
    daten = req.model_dump(exclude={"connection_id", "mapping_id", "bestaetigt"})
    return {**a.pruefe(daten).to_dict(), "connection_id": connection_id}


@router.post("/artikel-anlegen")
def artikel_anlegen(req: NeuerArtikelRequest, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """Legt den Artikel wirklich an – nur mit bestaetigt=true.

    Prüft dabei erneut von vorn: geschrieben wird gegen den Zustand der Wawi im
    Moment des Schreibens, nicht gegen das, was die Oberfläche noch weiß. Ohne
    diese zweite Prüfung entstünde ein Doppel, wenn jemand die Artikelnummer
    zwischenzeitlich vergeben hat.
    """
    if not req.bestaetigt:
        raise HTTPException(400, "Ohne ausdrückliche Bestätigung wird nicht angelegt")

    a, connection_id, project_id = _anleger(req, user, db)
    daten = req.model_dump(exclude={"connection_id", "mapping_id", "bestaetigt"})
    try:
        plan = a.lege_an(daten)
    except Exception as e:
        logger.exception("Artikel anlegen fehlgeschlagen")
        raise HTTPException(400, f"Anlegen fehlgeschlagen: {str(e)[:300]}")

    out = {**plan.to_dict(), "connection_id": connection_id}
    if not plan.ok:
        return out

    try:
        from app.services.db_logger import log as _dblog
        _dblog(db, "success", "jtl_artikel_writer", "artikel_anlegen",
               f"Artikel {plan.werte.get('cArtNr')} in der Wawi angelegt "
               f"(kArtikel {plan.kArtikel})",
               entity_id=connection_id, project_id=project_id, rows_processed=1,
               details={"benutzer": getattr(user, "username", None)
                                    or getattr(user, "email", None),
                        "kArtikel": plan.kArtikel, "werte": plan.werte,
                        "beschreibung": plan.beschreibung,
                        "lieferant": plan.lieferant, "hinweise": plan.hinweise})
    except Exception:   # Protokoll darf ein erfolgreiches Anlegen nie kippen
        logger.exception("Schreibprotokoll konnte nicht gespeichert werden")

    return out
