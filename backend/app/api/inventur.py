"""Inventur-API – Stichtagsbestände einfrieren, bewerten, dokumentieren.

Rechte wie bei den übrigen Cockpit-Widgets: Lesen darf, wer das Projekt lesen
oder ein veröffentlichtes Formular des Projekts sehen darf; Ändern braucht
Editor-Rechte (oder einen Portal-Nutzer mit Zugang zum Formular). Eine
abgeschlossene Inventur ist der Beleg und wird vom Service selbst geschützt.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
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
        "protokoll": l.protokoll or [],
        "zaehltag": l.zaehltag.isoformat() if l.zaehltag else None,
        "gezaehlte_positionen": l.gezaehlte_positionen or 0,
        "differenz_wert": l.differenz_wert or 0.0,
        "abweichungen_ohne_grund": l.abweichungen_ohne_grund or 0,
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
        # Zählung: bestand/wert oben sind die GÜLTIGEN Werte (Ist, wo gezählt).
        "bestand_soll": p.bestand_soll if p.bestand_soll is not None else p.bestand,
        "wert_soll": p.wert_soll if p.wert_soll is not None else p.wert,
        "soll_zaehltag": p.soll_zaehltag,
        "ist_gezaehlt": p.ist_gezaehlt,
        "zaehlung_ebene": p.zaehlung_ebene,
        "differenz": p.differenz,
        "differenz_wert": (round((p.wert or 0.0) - p.wert_soll, 2)
                           if p.zaehlung_ebene and p.wert_soll is not None else None),
        "differenz_grund": p.differenz_grund,
        "differenz_notiz": p.differenz_notiz,
        "gezaehlt_am": p.gezaehlt_am.isoformat() if p.gezaehlt_am else None,
        "gezaehlt_von": p.gezaehlt_von,
        "menge_ohne_partie_soll": (p.menge_ohne_partie_soll if p.menge_ohne_partie_soll is not None
                                   else p.menge_ohne_partie),
        "ist_ohne_partie": p.ist_ohne_partie,
        "rest_soll_zaehltag": p.rest_soll_zaehltag,
        "ist_quelle": p.ist_quelle,
        "ist_ohne_partie_quelle": p.ist_ohne_partie_quelle,
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
    # Eine abgeschlossene Inventur ist ein Beleg. Löschen geht nur über den
    # bewussten Umweg „wieder öffnen" – und der steht im Verlauf.
    if lauf.status == "abgeschlossen":
        raise HTTPException(400, "Eine abgeschlossene Inventur kann nicht gelöscht werden. "
                                 "Falls sie wirklich weg soll: erst wieder öffnen.")
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
    try:
        lauf = inventur_service.abschliessen(db, lauf, benutzer=getattr(user, "username", None))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _out_lauf(lauf)


@router.post("/laeufe/{lauf_id}/oeffnen")
def oeffnen(lauf_id: int,
            db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    lauf = _lauf(db, lauf_id)
    # Einen Beleg wieder aufzumachen ist keine Portal-Handlung.
    require_editor(lauf.project_id, user, db)
    return _out_lauf(inventur_service.wieder_oeffnen(
        db, lauf, benutzer=getattr(user, "username", None)))


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


# ─── Zählung (Soll/Ist) ───────────────────────────────────────────────────────

ZAEHLLISTE_MAX_BYTES = 10 * 1024 * 1024


@router.get("/laeufe/{lauf_id}/zaehlliste.xlsx")
def zaehlliste(lauf_id: int, mit_soll: bool = False, aufteilen: str = "",
               nach: str = "warengruppe",
               db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """Zählliste zum Ausdrucken und Zurückspielen: je Charge eine Zeile, druckfertig
    A4 quer. `mit_soll=false` (Vorgabe) = Blindzählung.

    `aufteilen`: leer = eine Liste · `blatt` = ein Blatt je Gruppe in einer Datei ·
    `dateien` = eine Datei je Gruppe als ZIP. `nach`: warengruppe | hersteller.
    Zurückgespielt wird jede Datei und jedes Blatt einzeln oder zusammen."""
    import re
    import zipfile
    from app.services.export_service import export_xlsx_tabelle, export_xlsx_mappe
    if aufteilen not in ("", "blatt", "dateien") or nach not in ("warengruppe", "hersteller"):
        raise HTTPException(400, "Unbekannte Aufteilung.")
    lauf = _lauf(db, lauf_id)
    _darf_lesen(lauf.project_id, user, db)
    zeilen = inventur_service.zaehlliste_zeilen(db, lauf, mit_soll)
    gruppenspalte = "Hersteller" if (aufteilen and nach == "hersteller") else "Warengruppe"
    kopf = (["Schlüssel", gruppenspalte, "Artikelnummer", "Artikel", "Charge", "MHD"]
            + (["Soll"] if mit_soll else []) + ["Ist", "Grund", "Notiz"])
    tag = lauf.zaehltag or lauf.stichtag
    tag_text = tag.strftime("%d.%m.%Y")

    def info_fuer(gruppe=None, anzahl=0):
        return [
            ("Inventur", lauf.name or ""),
            ("Stichtag", lauf.stichtag.strftime("%d.%m.%Y")),
            ("Zähltag", tag_text),
            *([(gruppenspalte, gruppe)] if gruppe else []),
            ("Zeilen", anzahl),
            ("Sollmenge", "angezeigt" if mit_soll else "nicht angezeigt (Blindzählung)"),
            ("So wird gezählt", "Ist = gezählte Menge am Zähltag. Nicht Gezähltes leer lassen."),
            ("", "Grund nur bei einer Abweichung eintragen, bei „Sonstiges“ bitte eine Notiz."),
            ("", "Danach über „Zählliste zurückspielen“ hochladen – jede Teilliste einzeln "
                 "oder alles in einer Datei. Die versteckte Spalte „Schlüssel“ nicht verändern."),
        ]

    def optionen(gruppe=None):
        titel = f"Zählliste – {lauf.name} – Zähltag {tag_text}" + (f" – {gruppe}" if gruppe else "")
        return dict(
            formate={"MHD": "DD.MM.YYYY"}, feste_spalten=4,
            versteckt=["Schlüssel"], eingabe=["Ist", "Grund", "Notiz"],
            auswahl={"Grund": list(inventur_service.DIFFERENZ_GRUENDE.values())},
            breiten={"Artikel": 40, "Charge": 20, "Ist": 12, "Grund": 24, "Notiz": 30},
            druck={"titel": titel,
                   "fusszeile": "Gezählt von: ________________   Datum: __________   "
                                "Unterschrift: ________________"},
        )

    xlsx = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if not aufteilen:
        inhalt = export_xlsx_tabelle(kopf, zeilen, blatt=inventur_service.ZAEHLLISTE_BLATT,
                                     info=info_fuer(anzahl=len(zeilen)), **optionen())
        return StreamingResponse(io.BytesIO(inhalt), media_type=xlsx, headers={
            "Content-Disposition": f'attachment; filename="Zaehlliste_{tag.isoformat()}.xlsx"'})

    ohne = f"ohne {gruppenspalte}"
    gruppen = {}
    for z in zeilen:
        gruppen.setdefault((z.get(gruppenspalte) or "").strip() or ohne, []).append(z)
    # Alphabetisch, „ohne …" ans Ende
    namen = sorted(gruppen, key=lambda g: (g == ohne, g.lower()))

    if aufteilen == "blatt":
        inhalt = export_xlsx_mappe(
            [{"blatt": g, "kopf": kopf, "zeilen": gruppen[g], **optionen(g)} for g in namen],
            info=info_fuer(anzahl=len(zeilen)) + [("Blätter", " · ".join(namen))])
        return StreamingResponse(io.BytesIO(inhalt), media_type=xlsx, headers={
            "Content-Disposition": f'attachment; filename="Zaehlliste_{tag.isoformat()}_je_{nach}.xlsx"'})

    puffer = io.BytesIO()
    vergeben = set()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for g in namen:
            teil = re.sub(r"[^\w\-]+", "_", g).strip("_")[:40] or "Gruppe"
            name, n = teil, 2
            while name.lower() in vergeben:
                name, n = f"{teil}_{n}", n + 1
            vergeben.add(name.lower())
            zf.writestr(f"Zaehlliste_{tag.isoformat()}_{name}.xlsx", export_xlsx_tabelle(
                kopf, gruppen[g], blatt=inventur_service.ZAEHLLISTE_BLATT,
                info=info_fuer(g, len(gruppen[g])), **optionen(g)))
    return StreamingResponse(io.BytesIO(puffer.getvalue()), media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="Zaehllisten_{tag.isoformat()}_je_{nach}.zip"'})


@router.post("/laeufe/{lauf_id}/zaehlliste")
async def zaehlliste_zurueckspielen(lauf_id: int, datei: UploadFile = File(...),
                                    db: Session = Depends(get_db),
                                    user: User = Depends(get_current_user)):
    """Ausgefüllte Zählliste hochladen. Leere Ist-Zellen ändern nichts."""
    lauf = _lauf(db, lauf_id)
    _darf_aendern(lauf.project_id, user, db)
    inhalt = await datei.read(ZAEHLLISTE_MAX_BYTES + 1)
    if len(inhalt) > ZAEHLLISTE_MAX_BYTES:
        raise HTTPException(413, "Die Datei ist zu groß (höchstens 10 MB).")
    try:
        res = inventur_service.zaehlliste_importieren(
            db, lauf, inhalt, benutzer=getattr(user, "username", None),
            dateiname=datei.filename)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.refresh(lauf)
    return {**res, "lauf": _out_lauf(lauf)}


class ZaehlungIn(BaseModel):
    # Nur mitgeschickte Felder werden geändert: `ist: null` setzt die Zählung zurück,
    # ein fehlendes `ist` lässt sie stehen (z.B. wenn nur der Grund kommt).
    ist: Optional[float] = None
    charge_index: Optional[int] = None
    charge_ist: Optional[float] = None
    ohne_partie_ist: Optional[float] = None
    grund: Optional[str] = None
    notiz: Optional[str] = None


@router.put("/positionen/{pos_id}/zaehlung")
def zaehlung(pos_id: int, data: ZaehlungIn,
             db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    pos = db.query(InventurPosition).filter(InventurPosition.id == pos_id).first()
    if not pos:
        raise HTTPException(404, "Position nicht gefunden")
    lauf = _lauf(db, pos.lauf_id)
    _darf_aendern(lauf.project_id, user, db)
    gesetzt = (data.model_fields_set if hasattr(data, "model_fields_set")
               else data.__fields_set__)
    felder = {k: getattr(data, k) for k in gesetzt}
    if "charge_index" in felder:
        felder.setdefault("charge_ist", None)
    try:
        inventur_service.zaehlung_setzen(db, lauf, pos, felder,
                                         benutzer=getattr(user, "username", None))
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.refresh(pos)
    db.refresh(lauf)
    return {"position": _out_pos(pos), "lauf": _out_lauf(lauf)}


class ZaehltagIn(BaseModel):
    zaehltag: Optional[date] = None


@router.put("/laeufe/{lauf_id}/zaehltag")
def zaehltag(lauf_id: int, data: ZaehltagIn,
             db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    """Zähltag setzen (leer = am Stichtag). Holt die Buchmengen dieses Tages aus
    der Wawi, damit Ist gegen das richtige Soll steht."""
    lauf = _lauf(db, lauf_id)
    _darf_aendern(lauf.project_id, user, db)
    try:
        res = inventur_service.zaehltag_setzen(db, lauf, data.zaehltag,
                                               benutzer=getattr(user, "username", None))
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.refresh(lauf)
    return {**res, "lauf": _out_lauf(lauf)}


@router.get("/differenzgruende")
def differenzgruende():
    return [{"id": k, "label": v} for k, v in inventur_service.DIFFERENZ_GRUENDE.items()]


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

    from zoneinfo import ZoneInfo
    from datetime import timezone
    try:
        ort = ZoneInfo("Europe/Berlin")
    except Exception:
        ort = timezone.utc   # ohne Zeitzonendaten lieber UTC als eine falsche Uhrzeit

    def _text_datum(d, mit_zeit=False):
        if not d:
            return ""
        if isinstance(d, str):
            try:
                d = datetime.fromisoformat(d)
            except ValueError:
                return d
        if mit_zeit and isinstance(d, datetime):
            # Gespeichert wird in UTC; SQLite gibt es ohne Zeitzone zurück.
            d = (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(ort)
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
        ("Zähltag", _text_datum(lauf.zaehltag) if lauf.zaehltag else "am Stichtag"),
        ("Gezählt", f"{lauf.gezaehlte_positionen or 0} von {len(zeilen)} Positionen "
                    "(ungezählte mit der Buchmenge)"),
        ("Inventurdifferenz", round(lauf.differenz_wert or 0, 2)),
        ("Abwertungsstaffel", " · ".join(
            f"{s.get('label')}: {float(s.get('prozent') or 0):g} %"
            for s in inventur_service.stufen_des_laufs(lauf))),
        ("Abgeschlossen am", _text_datum(lauf.abgeschlossen_am, mit_zeit=True)),
        ("Abgeschlossen von", lauf.abgeschlossen_von or ""),
        ("Exportiert am", datetime.now().strftime("%d.%m.%Y %H:%M")),
    ]
    # Der Verlauf gehört zum Beleg: wer wann eingelesen, abgeschlossen und wieder
    # geöffnet hat.
    aktionen = {"angelegt": "angelegt", "eingelesen": "Bestände eingelesen",
                "abgeschlossen": "abgeschlossen", "wieder_geoeffnet": "wieder geöffnet",
                "zaehltag": "Zähltag gesetzt", "zaehlliste": "Zählliste zurückgespielt"}
    for i, e in enumerate(lauf.protokoll or []):
        teile = []
        if e.get("positionen") is not None:
            teile.append(f"{e['positionen']} Positionen")
        if e.get("bewertungen_verworfen"):
            teile.append(f"{e['bewertungen_verworfen']} Bewertungen verworfen")
        if e.get("vorschlaege_bestaetigt"):
            teile.append(f"{e['vorschlaege_bestaetigt']} Vorschläge bestätigt")
        if e.get("abwertung") is not None:
            teile.append("Abwertung " + f"{float(e['abwertung']):,.2f} €"
                         .replace(",", "X").replace(".", ",").replace("X", "."))
        text = f"{_text_datum(e.get('am'), mit_zeit=True)} {aktionen.get(e.get('aktion'), e.get('aktion'))}"
        if e.get("von"):
            text += f" von {e['von']}"
        if teile:
            text += " (" + ", ".join(teile) + ")"
        info.append(("Verlauf" if i == 0 else "", text))

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
