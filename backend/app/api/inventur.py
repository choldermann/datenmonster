"""Inventur-API – Stichtagsbestände einfrieren, bewerten, dokumentieren.

Rechte wie bei den übrigen Cockpit-Widgets: Lesen darf, wer das Projekt lesen
oder ein veröffentlichtes Formular des Projekts sehen darf; Ändern braucht
Editor-Rechte (oder einen Portal-Nutzer mit Zugang zum Formular). Eine
abgeschlossene Inventur ist der Beleg und wird vom Service selbst geschützt.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from datetime import date, datetime
from decimal import Decimal
import csv
import io

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.inventur import InventurLauf, InventurPosition, STANDARD_STUFEN
from app.services import inventur_service
from app.api.projects import can_read_project, require_editor
from app.api.portal import user_can_access_portal_project

router = APIRouter(prefix="/api/inventur", tags=["inventur"])


def _darf_lesen(project_id, user, db):
    if not (can_read_project(project_id, user, db)
            or user_can_access_portal_project(project_id, user, db)):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")


def _darf_aendern(project_id, user, db):
    # Gleiche Regel wie bei der Ausschlussliste: ein Portal-Nutzer, dem das
    # Formular freigegeben ist, darf die Inventur pflegen – sonst könnte der
    # Lagerverantwortliche seine eigene Liste nicht bewerten.
    if not (getattr(user, "is_portal_only", False)
            and user_can_access_portal_project(project_id, user, db)):
        require_editor(project_id, user, db)


def _lauf(db, lauf_id: int) -> InventurLauf:
    lauf = db.query(InventurLauf).filter(InventurLauf.id == lauf_id).first()
    if not lauf:
        raise HTTPException(404, "Inventur nicht gefunden")
    return lauf


def _out_lauf(l: InventurLauf) -> dict:
    return {
        "id": l.id,
        "project_id": l.project_id,
        "connection_id": l.connection_id,
        "name": l.name,
        "stichtag": l.stichtag.isoformat() if l.stichtag else None,
        "status": l.status,
        "notiz": l.notiz,
        "quelle_mapping": l.quelle_mapping,
        "positionen_anzahl": l.positionen_anzahl,
        "bestand_wert": l.bestand_wert,
        "abwertung_summe": l.abwertung_summe,
        "wert_nach_abwertung": l.wert_nach_abwertung,
        "bewertete_positionen": l.bewertete_positionen,
        "hinweise": l.hinweise or [],
        # Die Staffel, nach der diese Inventur vorschlägt – gehört zum Beleg.
        "abwertung_stufen": inventur_service.stufen_des_laufs(l),
        "stufen_eigene": bool(l.abwertung_stufen),
        "erstellt_von": l.erstellt_von,
        "created_at": l.created_at.isoformat() if l.created_at else None,
        "abgeschlossen_am": l.abgeschlossen_am.isoformat() if l.abgeschlossen_am else None,
        "abgeschlossen_von": l.abgeschlossen_von,
    }


def _out_pos(p: InventurPosition) -> dict:
    return {
        "id": p.id,
        "k_artikel": p.k_artikel,
        "art_nr": p.c_artnr,
        "artikel": p.artikelname,
        "warengruppe": p.warengruppe,
        "hersteller": p.hersteller,
        "bestand": p.bestand,
        "ek": p.ek,
        "wert": p.wert,
        "mhd": p.mhd_frueh.isoformat() if p.mhd_frueh else None,
        "resttage": p.resttage,
        "menge_abgelaufen": p.menge_abgelaufen,
        "wert_abgelaufen": p.wert_abgelaufen,
        "abgang_12m": p.abgang_12m,
        "reichweite_tage": p.reichweite_tage,
        "letzter_abgang": p.letzter_abgang.isoformat() if p.letzter_abgang else None,
        "menge_ohne_partie": p.menge_ohne_partie,
        "chargen": p.chargen or [],
        "bewertung_art": p.bewertung_art,
        "bewertung_wert": p.bewertung_wert,
        "abwertung_betrag": p.abwertung_betrag,
        # Unbewertet heißt: voller Wert. Die Oberfläche soll keine Lücke zeigen,
        # in der eine Summe zu klein aussieht.
        "wert_neu": p.wert_neu if p.wert_neu is not None else p.wert,
        "grund": p.grund,
        "vorschlag": bool(p.vorschlag),
        "bewertung_quelle": p.bewertung_quelle,   # staffel | hand | None
        "bewertet_am": p.bewertet_am.isoformat() if p.bewertet_am else None,
        "bewertet_von": p.bewertet_von,
    }


# ─── Läufe ────────────────────────────────────────────────────────────────────

@router.get("/laeufe")
def list_laeufe(project_id: Optional[int] = None,
                db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    _darf_lesen(project_id, user, db)
    q = db.query(InventurLauf)
    if project_id is not None:
        q = q.filter(InventurLauf.project_id == project_id)
    else:
        q = q.filter(InventurLauf.project_id.is_(None))
    # Nur die Inventuren des aktiven Mandanten – die Bestände des einen Betriebs
    # haben in der Liste des anderen nichts zu suchen.
    from app.services import mandant_service
    aktiv = mandant_service.aktiver(project_id, user, db)
    rows = q.order_by(InventurLauf.stichtag.desc(), InventurLauf.id.desc()).all()
    if aktiv is not None:
        rows = [l for l in rows if l.connection_id == aktiv]
    return [_out_lauf(l) for l in rows]


class LaufIn(BaseModel):
    project_id: Optional[int] = None
    connection_id: Optional[int] = None
    name: Optional[str] = None
    stichtag: date
    notiz: Optional[str] = None
    quelle_mapping: Optional[str] = None


@router.post("/laeufe")
def create_lauf(data: LaufIn,
                db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    _darf_aendern(data.project_id, user, db)
    from app.services import mandant_service
    conn_id = data.connection_id or mandant_service.aktiver(data.project_id, user, db)
    if not conn_id:
        raise HTTPException(400, "Keine Datenbankverbindung (Mandant) bestimmbar.")
    name = (data.name or "").strip() or f"Inventur zum {data.stichtag.strftime('%d.%m.%Y')}"
    lauf = inventur_service.anlegen(
        db, data.project_id, conn_id, name, data.stichtag,
        notiz=data.notiz, quelle_mapping=data.quelle_mapping,
        benutzer=getattr(user, "username", None),
    )
    return _out_lauf(lauf)


@router.post("/laeufe/{lauf_id}/befuellen")
def befuellen(lauf_id: int,
              db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    lauf = _lauf(db, lauf_id)
    _darf_aendern(lauf.project_id, user, db)
    try:
        zeilen = inventur_service.bestandsliste_laden(db, lauf)
        ergebnis = inventur_service.befuellen(db, lauf, zeilen,
                                              benutzer=getattr(user, "username", None))
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.refresh(lauf)
    return {"ok": True, **ergebnis, "lauf": _out_lauf(lauf)}


@router.patch("/laeufe/{lauf_id}")
def update_lauf(lauf_id: int, data: dict,
                db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    lauf = _lauf(db, lauf_id)
    _darf_aendern(lauf.project_id, user, db)
    if lauf.status == "abgeschlossen":
        raise HTTPException(400, "Die Inventur ist abgeschlossen.")
    for feld in ("name", "notiz", "quelle_mapping"):
        if feld in data:
            setattr(lauf, feld, data[feld])
    db.commit()
    db.refresh(lauf)
    return _out_lauf(lauf)


@router.delete("/laeufe/{lauf_id}")
def delete_lauf(lauf_id: int,
                db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    lauf = _lauf(db, lauf_id)
    _darf_aendern(lauf.project_id, user, db)
    db.query(InventurPosition).filter(InventurPosition.lauf_id == lauf.id).delete()
    db.delete(lauf)
    db.commit()
    return {"ok": True}


@router.post("/laeufe/{lauf_id}/abschliessen")
def abschliessen(lauf_id: int,
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    lauf = _lauf(db, lauf_id)
    _darf_aendern(lauf.project_id, user, db)
    lauf = inventur_service.abschliessen(db, lauf, benutzer=getattr(user, "username", None))
    return _out_lauf(lauf)


@router.post("/laeufe/{lauf_id}/oeffnen")
def oeffnen(lauf_id: int,
            db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    lauf = _lauf(db, lauf_id)
    # Einen Beleg wieder aufzumachen ist keine Portal-Handlung.
    require_editor(lauf.project_id, user, db)
    return _out_lauf(inventur_service.wieder_oeffnen(db, lauf))


# ─── Positionen ───────────────────────────────────────────────────────────────

@router.get("/laeufe/{lauf_id}/positionen")
def list_positionen(lauf_id: int,
                    nur_bewertet: bool = False,
                    nur_mhd: bool = False,
                    suche: Optional[str] = None,
                    db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    lauf = _lauf(db, lauf_id)
    _darf_lesen(lauf.project_id, user, db)
    q = db.query(InventurPosition).filter(InventurPosition.lauf_id == lauf_id)
    if nur_bewertet:
        q = q.filter(InventurPosition.bewertung_art.isnot(None))
    if nur_mhd:
        q = q.filter(InventurPosition.resttage.isnot(None))
    if suche:
        like = f"%{suche.strip()}%"
        q = q.filter((InventurPosition.c_artnr.ilike(like))
                     | (InventurPosition.artikelname.ilike(like)))
    rows = q.order_by(InventurPosition.wert.desc()).all()
    return {"lauf": _out_lauf(lauf), "positionen": [_out_pos(p) for p in rows]}


class BewertungIn(BaseModel):
    # prozent            – Prozentsatz auf den ganzen Positionswert
    # prozent_abgelaufen – Prozentsatz nur auf den Wert der abgelaufenen Partien
    # stueckwert         – neuer Wert je Stück
    # betrag             – fester Abwertungsbetrag
    art: str
    wert: float
    grund: Optional[str] = None


@router.put("/positionen/{pos_id}/bewertung")
def set_bewertung(pos_id: int, data: BewertungIn,
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    pos = db.query(InventurPosition).filter(InventurPosition.id == pos_id).first()
    if not pos:
        raise HTTPException(404, "Position nicht gefunden")
    lauf = _lauf(db, pos.lauf_id)
    _darf_aendern(lauf.project_id, user, db)
    if lauf.status == "abgeschlossen":
        raise HTTPException(400, "Die Inventur ist abgeschlossen.")
    try:
        inventur_service.bewerten(db, pos, data.art, data.wert, data.grund,
                                  benutzer=getattr(user, "username", None))
    except ValueError as e:
        raise HTTPException(400, str(e))
    lauf = inventur_service.summen_neu_rechnen(db, lauf)
    return {"position": _out_pos(pos), "lauf": _out_lauf(lauf)}


@router.delete("/positionen/{pos_id}/bewertung")
def del_bewertung(pos_id: int,
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    pos = db.query(InventurPosition).filter(InventurPosition.id == pos_id).first()
    if not pos:
        raise HTTPException(404, "Position nicht gefunden")
    lauf = _lauf(db, pos.lauf_id)
    _darf_aendern(lauf.project_id, user, db)
    if lauf.status == "abgeschlossen":
        raise HTTPException(400, "Die Inventur ist abgeschlossen.")
    inventur_service.bewertung_loeschen(db, pos)
    lauf = inventur_service.summen_neu_rechnen(db, lauf)
    return {"position": _out_pos(pos), "lauf": _out_lauf(lauf)}


class VorschlagIn(BaseModel):
    stufen: Optional[List[dict]] = None
    nur_unbewertete: bool = True


@router.post("/laeufe/{lauf_id}/vorschlag")
def vorschlag(lauf_id: int, data: VorschlagIn,
              db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    lauf = _lauf(db, lauf_id)
    _darf_aendern(lauf.project_id, user, db)
    try:
        res = inventur_service.vorschlag_anwenden(
            db, lauf, data.stufen, data.nur_unbewertete,
            benutzer=getattr(user, "username", None))
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.refresh(lauf)
    return {**res, "lauf": _out_lauf(lauf)}


@router.post("/laeufe/{lauf_id}/vorschlaege-bestaetigen")
def bestaetigen(lauf_id: int,
                db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    lauf = _lauf(db, lauf_id)
    _darf_aendern(lauf.project_id, user, db)
    try:
        res = inventur_service.vorschlaege_bestaetigen(
            db, lauf, benutzer=getattr(user, "username", None))
    except ValueError as e:
        raise HTTPException(400, str(e))
    lauf = inventur_service.summen_neu_rechnen(db, lauf)
    return {**res, "lauf": _out_lauf(lauf)}


@router.get("/stufen")
def stufen():
    """Die Standard-Abwertungsstufen, damit die Oberfläche sie vorbelegen kann."""
    return STANDARD_STUFEN


class StufenIn(BaseModel):
    stufen: List[dict]
    neu_vorschlagen: bool = False


@router.put("/laeufe/{lauf_id}/stufen")
def stufen_setzen(lauf_id: int, data: StufenIn,
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """Legt fest, ab welcher Restlaufzeit wie viel abgewertet wird – für DIESE
    Inventur. Auf Wunsch werden die Vorschläge gleich neu gerechnet;
    Handbewertungen bleiben dabei unberührt."""
    lauf = _lauf(db, lauf_id)
    _darf_aendern(lauf.project_id, user, db)
    res = {}
    try:
        lauf = inventur_service.stufen_setzen(db, lauf, data.stufen)
        if data.neu_vorschlagen:
            res = inventur_service.vorschlag_anwenden(
                db, lauf, None, True, benutzer=getattr(user, "username", None))
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.refresh(lauf)
    return {**res, "lauf": _out_lauf(lauf)}


# ─── Export für den Steuerberater ─────────────────────────────────────────────

@router.get("/laeufe/{lauf_id}/export.csv")
def export_csv(lauf_id: int,
               db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    lauf = _lauf(db, lauf_id)
    _darf_lesen(lauf.project_id, user, db)
    zeilen = inventur_service.export_zeilen(db, lauf)
    spalten = [label for _, label in inventur_service.EXPORT_SPALTEN]

    puffer = io.StringIO()
    # Semikolon und BOM: Die Datei geht an einen Steuerberater und wird dort in
    # Excel geöffnet – ohne BOM zerlegt Excel die Umlaute.
    puffer.write("﻿")
    # JEDES Feld in Anführungszeichen: Hat das Tabellenprogramm beim Import auch
    # das Komma als Trenner eingestellt (LibreOffice merkt sich das), zerfielen
    # sonst alle Zeilen mit Komma im Artikelnamen – bei PPS 410 von 688.
    schreiber = csv.DictWriter(puffer, fieldnames=spalten, delimiter=";",
                               extrasaction="ignore", quoting=csv.QUOTE_ALL)
    schreiber.writeheader()
    for z in zeilen:
        schreiber.writerow({k: _csv_wert(v) for k, v in z.items()})
    # Summenzeile: der Empfänger soll nicht selbst addieren müssen.
    schreiber.writerow({
        spalten[0]: "SUMME",
        "Wert zum EK": _csv_wert(round(lauf.bestand_wert or 0, 2)),
        "Abwertung": _csv_wert(round(lauf.abwertung_summe or 0, 2)),
        "Wert nach Abwertung": _csv_wert(round(lauf.wert_nach_abwertung or 0, 2)),
    })

    dateiname = f"Inventur_{(lauf.stichtag or date.today()).strftime('%Y-%m-%d')}.csv"
    return StreamingResponse(
        io.BytesIO(puffer.getvalue().encode("utf-8")),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{dateiname}"'},
    )


def _csv_wert(v):
    """Zahlen mit Dezimalkomma: ein deutsches Excel/LibreOffice liest „3.281" als
    3281 – der EK stünde tausendfach zu hoch in der Liste."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "ja" if v else "nein"
    if isinstance(v, (int, float, Decimal)):
        s = str(v)
        if "e" in s.lower():
            s = f"{v:.10f}".rstrip("0").rstrip(".")
        return s.replace(".", ",")
    return v


@router.get("/laeufe/{lauf_id}/export.xlsx")
def export_xlsx(lauf_id: int,
                db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    """Dieselbe Liste als Excel: Kopfzeile und Artikelspalten fixiert, Autofilter,
    echte Zahlen und Datumswerte, Summen der sichtbaren Zeilen, Info-Blatt."""
    from app.services.export_service import export_xlsx_tabelle
    lauf = _lauf(db, lauf_id)
    _darf_lesen(lauf.project_id, user, db)
    zeilen = inventur_service.export_zeilen(db, lauf, datum_als_text=False)
    spalten = [label for _, label in inventur_service.EXPORT_SPALTEN]

    def _text_datum(d, mit_zeit=False):
        if not d:
            return ""
        return d.strftime("%d.%m.%Y %H:%M" if mit_zeit else "%d.%m.%Y")

    # Als Text: openpyxl lehnt Zeitstempel mit Zeitzone ab, und im Info-Blatt
    # wird nicht gerechnet.
    info = [
        ("Inventur", lauf.name or ""),
        ("Stichtag", _text_datum(lauf.stichtag)),
        ("Status", lauf.status or ""),
        ("Positionen", len(zeilen)),
        ("Wert zum EK", round(lauf.bestand_wert or 0, 2)),
        ("Abwertung", round(lauf.abwertung_summe or 0, 2)),
        ("Wert nach Abwertung", round(lauf.wert_nach_abwertung or 0, 2)),
        ("Abwertungsstaffel", " · ".join(
            f"{s.get('label')}: {float(s.get('prozent') or 0):g} %"
            for s in inventur_service.stufen_des_laufs(lauf))),
        ("Abgeschlossen am", _text_datum(lauf.abgeschlossen_am, mit_zeit=True)),
        ("Abgeschlossen von", lauf.abgeschlossen_von or ""),
        ("Exportiert am", datetime.now().strftime("%d.%m.%Y %H:%M")),
    ]
    inhalt = export_xlsx_tabelle(
        spalten, zeilen,
        formate=inventur_service.EXPORT_FORMATE,
        summen=inventur_service.EXPORT_SUMMEN,
        blatt="Inventur", info=info, feste_spalten=2,
    )
    dateiname = f"Inventur_{(lauf.stichtag or date.today()).strftime('%Y-%m-%d')}.xlsx"
    return StreamingResponse(
        io.BytesIO(inhalt),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{dateiname}"'},
    )
