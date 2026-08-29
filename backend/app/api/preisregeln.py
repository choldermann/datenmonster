"""Preisautomatik: Regelwerke pflegen, Läufe starten, Vorschläge freigeben,
Ameise-Datei erzeugen und den Erfolg kontrollieren.

Es wird hier NICHTS in die Wawi geschrieben. Der Export erzeugt eine Datei, den
Import macht der Anwender mit der Ameise, und die Kontrolle liest anschließend
die echten Preise zurück. Der Direktschreib-Weg kommt als zweite Rückseite
derselben Schnittstelle dazu.
"""
from typing import Optional, List, Any
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.preisregel import PriceRuleset, PriceRule, PriceRun, PriceChange
from app.api.projects import can_read_project, require_editor
from app.services import preisregel_service as dienst
from app.services import mandant_service

router = APIRouter(prefix="/api/preisregeln", tags=["preisregeln"])


# ── Ein-/Ausgabeformate ──────────────────────────────────────────────────────

class RegelwerkIn(BaseModel):
    project_id: Optional[int] = None
    connection_id: Optional[int] = None       # None → aktiver Mandant
    name: str
    description: Optional[str] = None
    active: bool = False
    scope: dict = {}
    kundengruppen: List[int] = []
    shops: List[int] = [0]
    nie_unter_ek: bool = True
    min_marge_prozent: Optional[float] = None
    max_rabatt_prozent: Optional[float] = None
    laufzeit_tage: int = 30
    ende_bei_verkauf: bool = False
    ende_ab_menge: Optional[float] = None
    preisendung: Optional[str] = None
    auto_freigabe: bool = False
    kandidaten_mapping: Optional[str] = None
    zeitplan_aktiv: bool = False
    cron_expr: Optional[str] = None
    email_to: Optional[str] = None


class RegelIn(BaseModel):
    sort: int = 100
    active: bool = True
    label: Optional[str] = None
    kind: str = "ladenhueter"
    condition: dict = {}
    action: dict = {}


class IdsIn(BaseModel):
    ids: List[int] = []
    zustand: Optional[str] = None


class LaufIn(BaseModel):
    stichtag: Optional[date] = None


def _regelwerk(db, rid: int, user, schreibend=False) -> PriceRuleset:
    rs = db.query(PriceRuleset).filter(PriceRuleset.id == rid).first()
    if not rs:
        raise HTTPException(404, "Regelwerk nicht gefunden")
    if schreibend:
        require_editor(rs.project_id, user, db)
    elif not can_read_project(rs.project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    return rs


def _zeitplan_uebernehmen(rs: PriceRuleset):
    """Der Nachtlauf folgt dem Regelwerk: ein inaktives Regelwerk läuft nicht,
    auch wenn ein Zeitplan hinterlegt ist."""
    from app.services.scheduler_service import register_price_job, unregister_price_job
    if rs.active and rs.zeitplan_aktiv:
        register_price_job(rs.id, rs.cron_expr or "15 5 * * *")
    else:
        unregister_price_job(rs.id)


def _rw_out(rs: PriceRuleset, db) -> dict:
    return {
        "id": rs.id, "project_id": rs.project_id, "connection_id": rs.connection_id,
        "mandant_name": mandant_service.name_von(rs.connection_id, db),
        "name": rs.name, "description": rs.description, "active": rs.active,
        "scope": rs.scope or {}, "kundengruppen": rs.kundengruppen or [],
        "shops": rs.shops or [0], "nie_unter_ek": rs.nie_unter_ek,
        "min_marge_prozent": rs.min_marge_prozent,
        "max_rabatt_prozent": rs.max_rabatt_prozent,
        "laufzeit_tage": rs.laufzeit_tage, "preisendung": rs.preisendung,
        "ende_bei_verkauf": rs.ende_bei_verkauf, "ende_ab_menge": rs.ende_ab_menge,
        "auto_freigabe": rs.auto_freigabe,
        "kandidaten_mapping": rs.kandidaten_mapping,
        "zeitplan_aktiv": rs.zeitplan_aktiv, "cron_expr": rs.cron_expr,
        "email_to": rs.email_to,
        "last_run_at": rs.last_run_at.strftime("%d.%m.%Y %H:%M") if rs.last_run_at else "",
        "last_status": rs.last_status, "last_message": rs.last_message,
        "offen": dienst.offene_zahlen(db, rs.id),
        "regeln": [_regel_out(r) for r in
                   db.query(PriceRule).filter(PriceRule.ruleset_id == rs.id)
                   .order_by(PriceRule.sort.desc()).all()],
    }


def _regel_out(r: PriceRule) -> dict:
    return {"id": r.id, "ruleset_id": r.ruleset_id, "sort": r.sort,
            "active": r.active, "label": r.label, "kind": r.kind,
            "condition": r.condition or {}, "action": r.action or {}}


def _aenderung_out(c: PriceChange) -> dict:
    rabatt = None
    if c.preis_alt and c.preis_neu is not None and c.preis_alt > 0:
        rabatt = round((1 - c.preis_neu / c.preis_alt) * 100, 1)
    return {
        "id": c.id, "run_id": c.run_id, "rule_id": c.rule_id,
        "ArtNr": c.c_artnr, "Artikel": c.artikelname,
        "kArtikel": c.k_artikel, "kKundenGruppe": c.k_kundengruppe,
        "Kundengruppe": c.kundengruppe or str(c.k_kundengruppe),
        "kShop": c.k_shop, "Ruecknahme": bool(c.ruecknahme_von),
        "PreisAlt": c.preis_alt, "PreisNeu": c.preis_neu, "RabattProzent": rabatt,
        "EKNetto": c.ek_netto,
        "GueltigVon": c.gueltig_von.strftime("%d.%m.%Y") if c.gueltig_von else "",
        "GueltigBis": c.gueltig_bis.strftime("%d.%m.%Y") if c.gueltig_bis else "",
        "Zustand": c.zustand, "Weg": c.weg, "IstPreis": c.ist_preis,
        "Abweichung": c.abweichung,
        "Kontrolliert": c.kontrolliert_am.strftime("%d.%m.%Y %H:%M") if c.kontrolliert_am else "",
        "Begruendung": c.begruendung,
    }


# ── Regelwerke ───────────────────────────────────────────────────────────────

@router.get("/regelwerke")
def liste(project_id: Optional[int] = None, db: Session = Depends(get_db),
          user: User = Depends(get_current_user)):
    if not can_read_project(project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    q = db.query(PriceRuleset)
    if project_id is not None:
        q = q.filter(PriceRuleset.project_id == project_id)
    return {"regelwerke": [_rw_out(rs, db) for rs in q.order_by(PriceRuleset.name).all()]}


@router.post("/regelwerke")
def anlegen(body: RegelwerkIn, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    require_editor(body.project_id, user, db)
    conn = body.connection_id or mandant_service.aktiver(body.project_id, user, db)
    if not conn:
        raise HTTPException(400, "Kein Mandant gewählt – ein Regelwerk gehört zu "
                                 "genau einer JTL-Verbindung.")
    daten = body.model_dump(exclude_none=True)
    daten.pop("connection_id", None)
    rs = PriceRuleset(connection_id=conn, **daten)
    db.add(rs)
    db.commit()
    _zeitplan_uebernehmen(rs)
    return _rw_out(rs, db)


@router.put("/regelwerke/{rid}")
def aendern(rid: int, body: RegelwerkIn, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    rs = _regelwerk(db, rid, user, schreibend=True)
    for feld, wert in body.model_dump(exclude_unset=True).items():
        if feld in ("project_id",):
            continue
        if feld == "connection_id" and not wert:
            continue
        setattr(rs, feld, wert)
    db.commit()
    _zeitplan_uebernehmen(rs)
    return _rw_out(rs, db)


@router.delete("/regelwerke/{rid}")
def loeschen(rid: int, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    rs = _regelwerk(db, rid, user, schreibend=True)
    angewandt = db.query(PriceChange).filter(
        PriceChange.ruleset_id == rs.id, PriceChange.zustand == "angewandt").count()
    if angewandt:
        raise HTTPException(400, f"{angewandt} angewandte Preisänderungen hängen an "
                                 "diesem Regelwerk. Erst zurücknehmen, dann löschen.")
    db.query(PriceRule).filter(PriceRule.ruleset_id == rs.id).delete()
    db.query(PriceChange).filter(PriceChange.ruleset_id == rs.id).delete()
    db.query(PriceRun).filter(PriceRun.ruleset_id == rs.id).delete()
    from app.services.scheduler_service import unregister_price_job
    unregister_price_job(rs.id)
    db.delete(rs)
    db.commit()
    return {"ok": True}


# ── Stufen ───────────────────────────────────────────────────────────────────

@router.post("/regelwerke/{rid}/regeln")
def regel_anlegen(rid: int, body: RegelIn, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    rs = _regelwerk(db, rid, user, schreibend=True)
    r = PriceRule(ruleset_id=rs.id, **body.model_dump())
    db.add(r)
    db.commit()
    return _regel_out(r)


@router.put("/regeln/{regel_id}")
def regel_aendern(regel_id: int, body: RegelIn, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    r = db.query(PriceRule).filter(PriceRule.id == regel_id).first()
    if not r:
        raise HTTPException(404, "Regel nicht gefunden")
    _regelwerk(db, r.ruleset_id, user, schreibend=True)
    for feld, wert in body.model_dump(exclude_unset=True).items():
        setattr(r, feld, wert)
    db.commit()
    return _regel_out(r)


@router.delete("/regeln/{regel_id}")
def regel_loeschen(regel_id: int, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    r = db.query(PriceRule).filter(PriceRule.id == regel_id).first()
    if not r:
        raise HTTPException(404, "Regel nicht gefunden")
    _regelwerk(db, r.ruleset_id, user, schreibend=True)
    db.delete(r)
    db.commit()
    return {"ok": True}


# ── Lauf, Vorschläge, Export, Kontrolle ──────────────────────────────────────

@router.post("/regelwerke/{rid}/lauf")
def starten(rid: int, body: LaufIn = LaufIn(), db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    rs = _regelwerk(db, rid, user, schreibend=True)
    try:
        return dienst.lauf(db, rs.id, user=user, triggered_by="manuell",
                           stichtag=body.stichtag)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/regelwerke/{rid}/wiederverkauf")
def wiederverkauf_pruefen(rid: int, db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)):
    """Prüft laufende Rabatte auf Wiederverkauf und beendet sie – dasselbe, was
    der Nachtlauf tut, nur auf Knopfdruck."""
    rs = _regelwerk(db, rid, user, schreibend=True)
    try:
        return dienst.wiederverkauf(db, rs.id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/regelwerke/{rid}/kundengruppen")
def kundengruppen(rid: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """Kundengruppen der Wawi DIESES Regelwerks – bewusst nicht über
    /api/lookup/options: Das tauscht die Verbindung gegen den gerade aktiven
    Mandanten und lieferte dann die Gruppen eines fremden Betriebs."""
    rs = _regelwerk(db, rid, user)
    from app.services.mapping_service import _get_sql_engine
    import sqlalchemy as sa
    # Eigene Abfrage statt LOOKUP_QUERIES["kundengruppe"]: Dort gilt der Vertrag
    # value/label für Auswahlfelder, hier wird zusätzlich der Gruppenrabatt
    # (tkundenGruppe.fRabatt) gebraucht. Der ist wichtig genug, um ihn zu sehen –
    # er wirkt auf den Preis und damit auf die Marge, die das Sicherheitsnetz prüft.
    SQL = ("SELECT kKundenGruppe, cName, ISNULL(fRabatt, 0) "
           "FROM dbo.tkundenGruppe ORDER BY kKundenGruppe")
    try:
        with _get_sql_engine(rs.connection_id).connect() as con:
            zeilen = con.execute(sa.text(SQL)).fetchall()
    except Exception as e:
        raise HTTPException(400, f"Kundengruppen nicht lesbar: {str(e)[:200]}")
    # Nach Nummer sortiert, nicht alphabetisch: Die Gruppen sind in der Wawi in
    # einer gewachsenen Reihenfolge angelegt (Basis, Händler, Bronze, Silver,
    # Gold …), und in der wiedererkennt man sie.
    return {"optionen": [{"value": int(r[0]), "label": r[1], "rabatt": float(r[2] or 0)}
                         for r in zeilen]}


@router.post("/regelwerke/{rid}/nachtlauf")
def nachtlauf_jetzt(rid: int, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """Führt den Nachtlauf sofort aus – kontrollieren, dann neu vorschlagen.
    Nützlich zum Ausprobieren des Zeitplans, ohne bis morgen früh zu warten."""
    rs = _regelwerk(db, rid, user, schreibend=True)
    try:
        return dienst.nachtlauf(db, rs.id, triggered_by="manuell")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/regelwerke/{rid}/laeufe")
def laeufe(rid: int, limit: int = 20, db: Session = Depends(get_db),
           user: User = Depends(get_current_user)):
    rs = _regelwerk(db, rid, user)
    rows = (db.query(PriceRun).filter(PriceRun.ruleset_id == rs.id)
            .order_by(PriceRun.id.desc()).limit(min(limit, 100)).all())
    return {"laeufe": [{
        "id": r.id, "gestartet": r.started_at.strftime("%d.%m.%Y %H:%M") if r.started_at else "",
        "status": r.status, "ausgeloest_von": r.triggered_by,
        "Kandidaten": r.kandidaten, "Vorschlaege": r.vorschlaege,
        "Verworfen": r.verworfen, "error": r.error} for r in rows]}


@router.get("/regelwerke/{rid}/aenderungen")
def aenderungen(rid: int, zustand: Optional[str] = None, limit: int = 500,
                db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    rs = _regelwerk(db, rid, user)
    q = db.query(PriceChange).filter(PriceChange.ruleset_id == rs.id)
    if zustand:
        q = q.filter(PriceChange.zustand.in_([z.strip() for z in zustand.split(",")]))
    rows = q.order_by(PriceChange.id.desc()).limit(min(limit, 2000)).all()
    zaehler = {}
    for z, n in (db.query(PriceChange.zustand, __import__("sqlalchemy").func.count())
                 .filter(PriceChange.ruleset_id == rs.id)
                 .group_by(PriceChange.zustand).all()):
        zaehler[z] = n
    return {"rows": [_aenderung_out(c) for c in rows], "zaehler": zaehler}


@router.post("/aenderungen/zustand")
def zustand(body: IdsIn, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    if body.zustand not in ("freigegeben", "verworfen", "vorgeschlagen"):
        raise HTTPException(400, "Nur freigegeben, verworfen oder vorgeschlagen "
                                 "sind hier erlaubt – „angewandt“ vergibt allein "
                                 "die Kontrolle.")
    if not body.ids:
        raise HTTPException(400, "Keine Änderungen ausgewählt")
    erste = db.query(PriceChange).filter(PriceChange.id == body.ids[0]).first()
    if not erste:
        raise HTTPException(404, "Änderung nicht gefunden")
    _regelwerk(db, erste.ruleset_id, user, schreibend=True)
    return {"geaendert": dienst.zustand_setzen(db, body.ids, body.zustand, user)}


@router.post("/regelwerke/{rid}/ameise-csv")
def ameise(rid: int, body: IdsIn = IdsIn(), db: Session = Depends(get_db),
           user: User = Depends(get_current_user)):
    rs = _regelwerk(db, rid, user, schreibend=True)
    try:
        return dienst.ameise_csv(db, rs.id, body.ids or None, user)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/regelwerke/{rid}/kontrolle")
def kontrolle(rid: int, body: IdsIn = IdsIn(), db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    rs = _regelwerk(db, rid, user, schreibend=True)
    try:
        return dienst.kontrolle(db, rs.id, body.ids or None)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/aenderungen/ruecknahme")
def ruecknahme(body: IdsIn, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    if not body.ids:
        raise HTTPException(400, "Keine Änderungen ausgewählt")
    erste = db.query(PriceChange).filter(PriceChange.id == body.ids[0]).first()
    if not erste:
        raise HTTPException(404, "Änderung nicht gefunden")
    _regelwerk(db, erste.ruleset_id, user, schreibend=True)
    return dienst.ruecknahme(db, body.ids, user)
