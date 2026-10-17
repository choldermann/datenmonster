"""Händler-Ansicht: die einfache Startseite für JTL-Kunden.

Die Händler-Ansicht ist eine neue Schale über der vorhandenen Maschine. Die
Endpunkte hier bündeln nur, was die Startseite in einem Aufruf braucht –
Cockpits, Warnungen, Kennzahl-Kacheln, persönliche Einstellungen. Ausgeführt
wird weiterhin über die bekannten Wege (FormRunner/PortalRunner, Alerts,
Zustellpläne). Plan: ~/.claude/plans/haendler-ansicht.md, Phase 1.

Projekte kommen hier bewusst nicht vor: der Händler sieht alle Cockpits, die er
lesen darf, nebeneinander.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db, safe_commit
from app.core.zugriff import ist_admin, projekte_mit_rolle, schreiben_pruefen
from app.models.form import Form
from app.models.user import User

router = APIRouter(prefix="/api/start", tags=["start"])

# Kennzeichen des versteckten Formulars mit den Kennzahl-Kacheln der Übersicht.
ROLLE_STARTSEITE = "startseite"

# Vorgabe für die Kacheln: aus dem Reiter „Unternehmensübersicht“ des GF-Cockpits.
KENNZAHLEN_VORGABE = ["w_kpi_umsatz_netto", "w_kpi_rohertrag", "w_kpi_marge", "w_kpi_kunden"]

SEVERITY_RANG = {"kritisch": 0, "warnung": 1, "hinweis": 2, "info": 3}


def _portal(user) -> bool:
    return bool(getattr(user, "is_portal_only", False)) and not ist_admin(user)


def _sichtbare_formulare(user, db) -> List[Form]:
    """Alle Formulare, die dieser Benutzer öffnen darf.

    Portal-Benutzer: veröffentlichte Formulare mit Freigabe (wie /api/portal/forms).
    Editoren: alle Formulare ihrer Projekte, Admins alle.
    """
    if _portal(user):
        from app.api.portal import _check_portal_access
        erlaubt = []
        for f in db.query(Form).filter(Form.published == True).all():  # noqa: E712
            try:
                _check_portal_access(f, user)
                erlaubt.append(f)
            except HTTPException:
                continue
        return erlaubt
    q = db.query(Form)
    if not ist_admin(user):
        projekte = projekte_mit_rolle(user, db)
        q = q.filter(Form.project_id.in_(projekte)) if projekte else q.filter(False)
    return q.all()


def _ist_startseite(f: Form) -> bool:
    return (f.schema or {}).get("rolle") == ROLLE_STARTSEITE


def _cockpit_out(f: Form, projektnamen: dict, db) -> dict:
    schema = f.schema or {}
    gesperrt = None
    try:
        from app.core import vorlagen_gate
        gesperrt = vorlagen_gate.sperre_fuer_objekt(db, "forms", f.id)
    except Exception:
        gesperrt = None
    return {
        "id": f.id,
        "name": f.name,
        "slug": f.slug,
        "project_id": f.project_id,
        "projekt": projektnamen.get(f.project_id),
        "intro": ((schema.get("doku") or {}).get("intro") or "").strip(),
        "reiter": len(schema.get("result_tabs") or []),
        # Aus dem Report-Baukasten = selbst zusammengestellt, sonst aus einer Vorlage.
        "art": "bericht" if schema.get("report_builder") else "cockpit",
        "gesperrt": gesperrt,
        "kopie_von": (schema.get("kopie_von") or {}).get("name"),
    }


def _projektnamen(db) -> dict:
    from app.models.project import Project
    return {p.id: p.name for p in db.query(Project).all()}


@router.get("/cockpits")
def cockpits(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Alle Dashboards, die der Benutzer öffnen darf – ohne reine Eingabeformulare
    und ohne das versteckte Startseiten-Formular."""
    namen = _projektnamen(db)
    liste = [f for f in _sichtbare_formulare(user, db)
             if (f.schema or {}).get("widgets") and not _ist_startseite(f)]
    liste.sort(key=lambda f: (f.name or "").lower())
    aus = [_cockpit_out(f, namen, db) for f in liste]
    # Dasselbe Cockpit in zwei Projekten sähe sonst doppelt aus: dann den
    # Projektnamen als Zusatz zeigen, sonst nicht.
    zaehler: dict = {}
    for c in aus:
        zaehler[c["name"]] = zaehler.get(c["name"], 0) + 1
    for c in aus:
        c["zusatz"] = c["projekt"] if zaehler[c["name"]] > 1 else None
    return aus


def _einstellungen(user) -> dict:
    e = getattr(user, "einstellungen", None)
    return dict(e) if isinstance(e, dict) else {}


def _warnungen(user, formulare: List[Form], db) -> list:
    """Neueste Warnungen aller Projekte, die der Benutzer sieht – schlimmste zuerst."""
    from app.services import alert_service, mandant_service
    projekte = {f.project_id for f in formulare if f.project_id is not None}
    if not _portal(user):
        projekte |= ({p for p in _projektnamen(db)} if ist_admin(user)
                     else projekte_mit_rolle(user, db))
    aus = []
    for pid in sorted(projekte):
        try:
            lauf = alert_service.latest_run(db, pid, mandant_service.aktiver(pid, user, db))
        except Exception:
            continue
        for a in (lauf or {}).get("alerts") or []:
            if a.get("status") != "alert":
                continue
            aus.append({
                "project_id": pid,
                "rule_key": a.get("rule_key"),
                "titel": a.get("titel") or a.get("name"),
                "untertitel": a.get("untertitel") or "",
                "severity": a.get("severity"),
                "ampel": a.get("Ampel"),
                "cockpit": a.get("cockpit"),
                "neu": bool(a.get("neu")),
            })
    # Bei Warnungen aus mehreren Projekten (z. B. Echtbetrieb und Demo) muss
    # dabeistehen, woher sie kommen – sonst stehen zwei verschiedene Zahlen
    # zum selben Thema nebeneinander.
    if len({a["project_id"] for a in aus}) > 1:
        namen = _projektnamen(db)
        for a in aus:
            a["projekt"] = namen.get(a["project_id"])
    aus.sort(key=lambda a: (SEVERITY_RANG.get(a["severity"], 9), a["titel"] or ""))
    return aus


@router.get("/uebersicht")
def uebersicht(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Alles für die Startseite in einem Aufruf."""
    formulare = _sichtbare_formulare(user, db)
    start = next((f for f in formulare if _ist_startseite(f)), None)
    namen = _projektnamen(db)
    nach_id = {f.id: f for f in formulare}

    pins = [i for i in (_einstellungen(user).get("pins") or []) if i in nach_id]
    angeheftet = [_cockpit_out(nach_id[i], namen, db) for i in pins]

    return {
        "kennzahlen": ({"id": start.id, "slug": start.slug, "project_id": start.project_id}
                       if start else None),
        # Kacheln einrichten kann nur, wer bauen darf, und nur wenn es ein GF-Cockpit gibt.
        "kennzahlen_moeglich": (start is None and not _portal(user)
                                and _gf_cockpit(formulare) is not None),
        "warnungen": _warnungen(user, formulare, db),
        "angeheftet": angeheftet,
    }


def _gf_cockpit(formulare: List[Form]) -> Optional[Form]:
    """Das erste Formular, das alle Vorgabe-Kacheln enthält (= GF-Cockpit)."""
    for f in formulare:
        ids = {w.get("id") for w in (f.schema or {}).get("widgets") or []}
        if all(k in ids for k in KENNZAHLEN_VORGABE):
            return f
    return None


@router.post("/kennzahlen")
def kennzahlen_einrichten(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Legt das versteckte Startseiten-Formular mit den Kennzahl-Kacheln an.

    Gebaut wird mit dem Report-Baukasten aus dem GF-Cockpit; das Ergebnis ist ein
    normales Formular, nur mit `rolle = startseite`. Veröffentlicht, damit es
    auch Portal-Benutzer auf ihrer Übersicht sehen.
    """
    if _portal(user):
        raise HTTPException(403, "Nur Admins und Editoren können die Übersicht einrichten")
    return kennzahlen_anlegen(db, user)


def kennzahlen_anlegen(db, user, project_id: Optional[int] = None) -> dict:
    """Wie oben; mit project_id nur innerhalb dieses Projekts (Einrichtungsassistent)."""
    formulare = [f for f in _sichtbare_formulare(user, db)
                 if project_id is None or f.project_id == project_id]
    vorhanden = next((f for f in formulare if _ist_startseite(f)), None)
    if vorhanden:
        return {"id": vorhanden.id, "slug": vorhanden.slug}
    gf = _gf_cockpit(formulare)
    if gf is None:
        raise HTTPException(400, "Für die Kennzahlen wird das Geschäftsführer-Cockpit gebraucht")
    schreiben_pruefen(gf.project_id, user, db)

    from app.services import report_catalog
    from app.api.forms import unique_slug
    gebaut = report_catalog.assemble(
        db, "Übersicht", [{"form_id": gf.id, "widget_id": w} for w in KENNZAHLEN_VORGABE],
        zeitraum_preset="this_month", project_id=gf.project_id)
    schema = gebaut["schema"]
    schema["rolle"] = ROLLE_STARTSEITE
    f = Form(name="Übersicht", project_id=gebaut["project_id"], schema=schema,
             created_by=user.id, slug=unique_slug(db, "uebersicht"), published=True,
             portal_config={"allowed_users": [], "allow_manual_run": True})
    db.add(f)
    safe_commit(db)
    db.refresh(f)
    return {"id": f.id, "slug": f.slug}


class EinstellungenIn(BaseModel):
    pins: Optional[List[int]] = None
    werkstatt_start: Optional[bool] = None


@router.get("/einstellungen")
def einstellungen_lesen(user: User = Depends(get_current_user)):
    e = _einstellungen(user)
    return {"pins": e.get("pins") or [], "werkstatt_start": bool(e.get("werkstatt_start"))}


@router.put("/einstellungen")
def einstellungen_speichern(data: EinstellungenIn, db: Session = Depends(get_db),
                            user: User = Depends(get_current_user)):
    e = _einstellungen(user)
    if data.pins is not None:
        # Nur Cockpits, die der Benutzer überhaupt sieht – sonst ließe sich über
        # die Pins herausfinden, welche Formular-IDs es gibt.
        sichtbar = {f.id for f in _sichtbare_formulare(user, db)}
        e["pins"] = [i for i in dict.fromkeys(data.pins) if i in sichtbar][:12]
    if data.werkstatt_start is not None:
        e["werkstatt_start"] = bool(data.werkstatt_start) and not _portal(user)
    user.einstellungen = e
    safe_commit(db)
    return {"pins": e.get("pins") or [], "werkstatt_start": bool(e.get("werkstatt_start"))}


@router.get("/status")
def status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Für „Einstellungen“: welche JTL-Verbindungen hängen an den eigenen Projekten,
    welche Version melden sie. Nur für Editoren und Admins."""
    if _portal(user):
        raise HTTPException(403, "Portal-Zugänge haben auf diesen Bereich keinen Zugriff.")
    from app.core.zugriff import erreichbare_verbindungen
    from app.models.dataset import DbConnection
    from app.services.jtl_kompatibilitaet import jtl_version

    erreichbar = erreichbare_verbindungen(user, db)
    q = db.query(DbConnection).filter(DbConnection.db_type == "mssql")
    if erreichbar is not None:
        q = q.filter(DbConnection.id.in_(erreichbar)) if erreichbar else q.filter(False)
    verbindungen = []
    for c in q.order_by(DbConnection.name).all():
        # Keine Version = keine JTL-Datenbank oder gerade nicht erreichbar. Beides
        # soll der Händler sehen, die Oberfläche sagt dann „nicht erreichbar“.
        verbindungen.append({"id": c.id, "name": c.mandant_label or c.name,
                             "server": c.host, "datenbank": c.database,
                             "jtl_version": jtl_version(c.id, db)})
    return {"verbindungen": verbindungen}


# ── Phase 3: Fertige Fragen ───────────────────────────────────────────────────
# Die Fragen sind fertige Bauzettel des Abfrage-Generators (services/query_builder/
# rezepte.py). Ausführen ist Bedienen und darum frei; Speichern legt eigene
# Objekte an und zählt aufs Kontingent der kostenlosen Version.

def _haendler_projekt(user, db) -> Optional[int]:
    """Das Projekt, in dem die meisten Cockpits des Benutzers liegen – dort wird
    gerechnet und gespeichert. Nach dem Einrichtungsassistenten das einzige."""
    zaehler: dict = {}
    for f in _sichtbare_formulare(user, db):
        if f.project_id is not None and (f.schema or {}).get("widgets"):
            zaehler[f.project_id] = zaehler.get(f.project_id, 0) + 1
    return max(zaehler, key=zaehler.get) if zaehler else None


def _wawi(projekt: Optional[int], user, db) -> int:
    """Gegen welche Wawi gerechnet wird: der aktive Mandant, sonst die erste
    JTL-Datenbank, die dem Projekt zugeordnet ist."""
    from app.services import mandant_service
    from app.services.db_service import verbundene_ids
    from app.services.jtl_kompatibilitaet import jtl_version
    if projekt is None:
        raise HTTPException(400, "Es ist noch kein Cockpit eingerichtet.")
    aktiv = mandant_service.aktiver(projekt, user, db)
    if aktiv:
        return aktiv
    for cid in sorted(verbundene_ids(projekt, db)):
        if jtl_version(cid, db):
            return cid
    raise HTTPException(400, "Für dieses Projekt ist keine erreichbare JTL-Wawi hinterlegt.")


def _zeitraum(art: Optional[str]):
    from datetime import date, timedelta
    heute = date.today()
    if art == "letzte_30":
        return (heute - timedelta(days=30)).isoformat(), heute.isoformat()
    if art == "dieses_jahr":
        return date(heute.year, 1, 1).isoformat(), heute.isoformat()
    return (heute - timedelta(days=365)).isoformat(), heute.isoformat()


@router.get("/fragen")
def fragen(user: User = Depends(get_current_user)):
    if _portal(user):
        raise HTTPException(403, "Portal-Zugänge haben auf diesen Bereich keinen Zugriff.")
    from app.services.query_builder import rezepte
    return [{"key": f["key"], "gruppe": f["gruppe"], "titel": f["titel"], "text": f["text"],
             "zeitraum": rezepte.ZEITRAEUME.get(f["zeitraum"]) if f.get("zeitraum") else None}
            for f in rezepte.FRAGEN]


def _frage_holen(key: str) -> dict:
    from app.services.query_builder import rezepte
    f = rezepte.frage(key)
    if not f:
        raise HTTPException(404, "Diese Frage gibt es nicht")
    return f


@router.post("/fragen/{key}/vorschau")
def frage_vorschau(key: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Rechnet eine fertige Frage gegen die Wawi des Händlers."""
    if _portal(user):
        raise HTTPException(403, "Portal-Zugänge haben auf diesen Bereich keinen Zugriff.")
    from app.services.query_builder import ausfuehren, sql_bauer
    f = _frage_holen(key)
    projekt = _haendler_projekt(user, db)
    from app.api.projects import can_read_project
    if not can_read_project(projekt, user, db):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    von, bis = _zeitraum(f.get("zeitraum"))
    try:
        erg = ausfuehren.rechnen(db, f["definition"], _wawi(projekt, user, db), von=von, bis=bis)
    except sql_bauer.AbfrageFehler as e:
        raise HTTPException(400, str(e))
    except ausfuehren.LaufFehler as e:
        raise HTTPException(500, str(e))
    erg.pop("sql", None)      # für Händler ohne Wert; im Abfrage-Generator sichtbar
    return {**erg, "titel": f["titel"], "project_id": projekt}


@router.post("/fragen/{key}/speichern")
def frage_speichern(key: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Legt die Frage als eigene Auswertung an (Mapping + Baustein in „Eigene
    Auswertungen“) – danach steht sie im Report-Baukasten und lässt sich mailen."""
    if _portal(user):
        raise HTTPException(403, "Portal-Zugänge haben auf diesen Bereich keinen Zugriff.")
    from app.core import kontingent
    from app.models.report import AdHocQuery
    from app.services.query_builder import erzeugen, sql_bauer
    f = _frage_holen(key)
    projekt = _haendler_projekt(user, db)
    schreiben_pruefen(projekt, user, db)
    kontingent.pruefe(db, "mappings")
    wawi = _wawi(projekt, user, db)
    try:
        gebaut = erzeugen.speichern(db, f["titel"], f["definition"], projekt, wawi)
    except sql_bauer.AbfrageFehler as e:
        raise HTTPException(400, str(e))
    q = AdHocQuery(name=f["titel"], beschreibung=f["text"], project_id=projekt,
                   koernung=f["definition"].get("koernung"), definition=f["definition"],
                   mapping_id=gebaut["mapping"].id,
                   verlauf_mapping_id=gebaut.get("verlauf_mapping_id"),
                   form_id=gebaut["form"].id, widget_ids=gebaut["widget_ids"], created_by=user.id)
    db.add(q)
    safe_commit(db)
    return {"form_id": gebaut["form"].id, "form_name": gebaut["form"].name, "abfrage_id": q.id}


# ── Phase 3: Kopie eines Cockpits mit eigenen Vorgaben ────────────────────────

class KopieIn(BaseModel):
    name: str
    vorgaben: dict = {}       # Feldname → Vorgabewert; daterange: config.default (Preset-ID)


@router.post("/cockpits/{form_id}/kopie")
def cockpit_kopieren(form_id: int, data: KopieIn, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """Eigene Fassung eines Cockpits: dasselbe Schema, andere Vorgaben.

    Die Kopie nutzt dieselben Abfragen wie das Original, sie ändert nur, womit
    das Cockpit startet (Zeitraum, Plattform …). Ein späteres Update der Vorlage
    erreicht die Kopie nicht – so wie installierte Formulare generell.
    """
    if _portal(user):
        raise HTTPException(403, "Portal-Zugänge haben auf diesen Bereich keinen Zugriff.")
    import copy
    from app.api.forms import unique_slug
    quelle = db.query(Form).filter(Form.id == form_id).first()
    if not quelle:
        raise HTTPException(404, "Cockpit nicht gefunden")
    schreiben_pruefen(quelle.project_id, user, db)
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(400, "Bitte einen Namen angeben")

    schema = copy.deepcopy(quelle.schema or {})
    schema.pop("rolle", None)
    felder = {f.get("name"): f for f in schema.get("fields") or [] if f.get("name")}
    for feld, wert in (data.vorgaben or {}).items():
        f = felder.get(feld)
        if f is None:
            continue                      # unbekannte Felder still übergehen
        if f.get("type") == "daterange":
            f.setdefault("config", {})["default"] = str(wert)
        else:
            f["default"] = wert
    schema["kopie_von"] = {"form_id": quelle.id, "name": quelle.name}

    neu = Form(name=name, project_id=quelle.project_id, schema=schema, created_by=user.id,
               slug=unique_slug(db, name), published=bool(quelle.published),
               portal_config=copy.deepcopy(quelle.portal_config or {}))
    db.add(neu)
    safe_commit(db)
    db.refresh(neu)
    # Das Laufzeit-Tor ordnet Formulare Vorlagen zu; eine Kopie gehört zu keiner.
    try:
        from app.core.vorlagen_gate import cache_leeren
        cache_leeren()
    except Exception:
        pass
    return {"id": neu.id, "name": neu.name, "slug": neu.slug}
