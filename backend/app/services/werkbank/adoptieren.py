"""Vorhandene Auswertungen und Reports nachträglich unter die Werkbank nehmen.

Wer den Abfrage-Generator oder den Report-Baukasten schon benutzt hat, hat
Objekte im Bestand, die von der Werkbank nichts wissen. Sie bekommen hier
rückwirkend einen Herkunftsstempel – und damit dieselbe Rückbau-Sicherheit wie
alles Neugebaute: eine Liste dessen, was zusammengehört, und die Prüfung, ob
inzwischen jemand anders daran hängt.

**Zwei Regeln:**

1. **Nichts zweimal.** Was schon zu einem Vorhaben gehört, taucht nicht wieder
   auf. Zwei Vorhaben auf dasselbe Mapping wären zwei Rückbauten, von denen der
   zweite ins Leere greift.
2. **Der Mandant wird hergeleitet, nicht geraten.** Er steckt in der Verbindung
   des SQL-Knotens bzw. im Zustellplan. Ohne ihn liefe eine spätere Vorschau
   gegen den Projekt-Standard – bei Projekt 1 also HaKo, auch wenn die
   Auswertung für PPS gebaut wurde.
"""
import logging
from datetime import datetime, timezone

from app.core.database import safe_commit
from app.models.form import Form
from app.models.mapping import Mapping
from app.models.report import AdHocQuery, ReportSchedule
from app.models.vorhaben import Vorhaben, VorhabenArtefakt

from . import werkzeuge

logger = logging.getLogger(__name__)


def _schon_vergeben(db) -> dict:
    """Was bereits zu einem Vorhaben gehört, nach Art gebündelt."""
    vergeben = {}
    for a in db.query(VorhabenArtefakt).all():
        vergeben.setdefault(a.art, set()).add(a.ziel_id)
    return vergeben


def _mandant_aus_mapping(db, mapping_id) -> int | None:
    """Die Verbindung des SQL-Knotens – dort steht, gegen welche WaWi gerechnet wird."""
    if not mapping_id:
        return None
    m = db.query(Mapping).filter(Mapping.id == mapping_id).first()
    if not m:
        return None
    for n in (m.sql_nodes or []):
        if n.get("connection_id"):
            return n["connection_id"]
    return None


def finden(db, project_id=None) -> list:
    """Alles, was sich übernehmen ließe – ohne etwas zu ändern."""
    vergeben = _schon_vergeben(db)
    raus = []

    # ── Gespeicherte Auswertungen des Abfrage-Generators ────────────────────
    q = db.query(AdHocQuery)
    if project_id is not None:
        q = q.filter(AdHocQuery.project_id == project_id)
    for a in q.order_by(AdHocQuery.id).all():
        if a.id in vergeben.get("adhoc_query", set()):
            continue
        raus.append({
            "art": "adhoc_query", "id": a.id, "name": a.name,
            "beschreibung": a.beschreibung or f"Auswertung „{a.name}“",
            "mandant_id": _mandant_aus_mapping(db, a.mapping_id),
            "teile": [f"{len(a.widget_ids or [])} Baustein(e)",
                      "Verlauf" if a.verlauf_mapping_id else None],
        })

    # ── Mit dem Baukasten gebaute Reports ───────────────────────────────────
    f_q = db.query(Form)
    if project_id is not None:
        f_q = f_q.filter(Form.project_id == project_id)
    for f in f_q.order_by(Form.id).all():
        bau = (f.schema or {}).get("report_builder") or {}
        if not bau or f.id in vergeben.get("form", set()):
            continue
        plaene = db.query(ReportSchedule).filter(ReportSchedule.form_id == f.id).all()
        mandant = next((s.mandant_id for s in plaene if s.mandant_id), None)
        raus.append({
            "art": "report", "id": f.id, "name": f.name,
            "beschreibung": f"Report „{f.name}“ aus dem Baukasten",
            "mandant_id": mandant,
            "teile": [f"{len((f.schema or {}).get('widgets') or [])} Baustein(e)",
                      f"{len(plaene)} Zustellplan" if plaene else None,
                      "veröffentlicht" if f.published else None],
        })

    for e in raus:
        e["teile"] = [t for t in e["teile"] if t]
    return raus


def _vorhaben(db, name, beschreibung, project_id, mandant_id, bauplan, user_id):
    v = Vorhaben(name=name[:80], beschreibung=beschreibung,
                 project_id=project_id, mandant_id=mandant_id,
                 status="installiert", bauplan=bauplan,
                 hinweise=["Aus dem Bestand übernommen – der Bauzettel ist "
                           "nachgezeichnet, nicht von der KI geplant."],
                 verlauf=[], created_by=user_id,
                 gebaut_am=datetime.now(timezone.utc))
    db.add(v)
    db.flush()
    return v


def _schritt(werkzeug: str, eingabe: dict) -> dict:
    return {"werkzeug": werkzeug, "aktiv": True,
            "titel": werkzeuge.WERKZEUGE[werkzeug]["label"], "warum": "",
            "eingabe": eingabe,
            "zusammenfassung": werkzeuge.zusammenfassen(werkzeug, eingabe)}


def _artefakt(db, v, schritt, werkzeug, art, ziel_id, label,
              erzeugt=True, ziel_key=None, vorher=None):
    db.add(VorhabenArtefakt(
        vorhaben_id=v.id, schritt=schritt, werkzeug=werkzeug, art=art,
        ziel_id=ziel_id, ziel_key=ziel_key, label=label,
        erzeugt=erzeugt, vorher=vorher))


def _abfrage_uebernehmen(db, a: AdHocQuery, standard_mandant, user_id) -> Vorhaben:
    mandant = _mandant_aus_mapping(db, a.mapping_id) or standard_mandant
    eingabe = {"name": a.name, "beschreibung": a.beschreibung or "",
               "zeitraum_preset": "months_12", "definition": a.definition or {}}
    v = _vorhaben(db, a.name, a.beschreibung or f"Auswertung „{a.name}“",
                  a.project_id, mandant, [_schritt("abfrage", eingabe)], user_id)
    _artefakt(db, v, 0, "abfrage", "adhoc_query", a.id,
              f"Auswertung „{a.name}“ mit {len(a.widget_ids or [])} Baustein(en)")
    if a.form_id:
        f = db.query(Form).filter(Form.id == a.form_id).first()
        # Das Sammelformular ist geteilte Infrastruktur, nicht Eigentum dieses
        # Vorhabens – erzeugt=False, damit der Rückbau es stehen lässt.
        _artefakt(db, v, 0, "abfrage", "form", a.form_id,
                  f"Sammelformular „{f.name if f else a.form_id}“ (bleibt stehen)",
                  erzeugt=False)
    return v


def _report_uebernehmen(db, f: Form, standard_mandant, user_id) -> Vorhaben:
    bau = (f.schema or {}).get("report_builder") or {}
    plaene = db.query(ReportSchedule).filter(ReportSchedule.form_id == f.id).all()
    mandant = next((s.mandant_id for s in plaene if s.mandant_id), None) or standard_mandant

    bauplan = [_schritt("report", {
        "name": f.name,
        "zeitraum_preset": bau.get("zeitraum_preset") or "months_12",
        "bausteine": [{"form_id": e.get("form_id"), "widget_id": e.get("widget_id")}
                      for e in (bau.get("entries") or [])],
    })]
    for s in plaene:
        bauplan.append(_schritt("zustellplan", {
            "name": s.name, "cron_expr": s.cron_expr,
            "zeitraum_preset": s.zeitraum_preset, "email_to": s.email_to or "",
            "aktiv": bool(s.active), "form_id": f.id}))

    v = _vorhaben(db, f.name, f"Report „{f.name}“ aus dem Baukasten",
                  f.project_id, mandant, bauplan, user_id)
    _artefakt(db, v, 0, "report", "form", f.id,
              f"Report „{f.name}“ mit {len((f.schema or {}).get('widgets') or [])} "
              f"Baustein(en)")
    for i, s in enumerate(plaene, start=1):
        _artefakt(db, v, i, "zustellplan", "report_schedule", s.id,
                  f"Zustellplan „{s.name}“")
    return v


def uebernehmen(db, auswahl: list, project_id=None, user_id=None) -> dict:
    """Übernimmt die gewählten Objekte. `auswahl`: [{art, id}, …]."""
    from app.services import mandant_service

    standard = mandant_service.standard(project_id, db)
    vergeben = _schon_vergeben(db)
    angelegt, uebersprungen = [], []

    for e in auswahl or []:
        art, ziel = e.get("art"), int(e.get("id"))
        if art == "adhoc_query":
            if ziel in vergeben.get("adhoc_query", set()):
                uebersprungen.append({"art": art, "id": ziel,
                                      "grund": "gehört schon zu einem Vorhaben"})
                continue
            a = db.query(AdHocQuery).filter(AdHocQuery.id == ziel).first()
            if not a:
                uebersprungen.append({"art": art, "id": ziel, "grund": "nicht gefunden"})
                continue
            v = _abfrage_uebernehmen(db, a, standard, user_id)
        elif art == "report":
            if ziel in vergeben.get("form", set()):
                uebersprungen.append({"art": art, "id": ziel,
                                      "grund": "gehört schon zu einem Vorhaben"})
                continue
            f = db.query(Form).filter(Form.id == ziel).first()
            if not f or not (f.schema or {}).get("report_builder"):
                uebersprungen.append({"art": art, "id": ziel,
                                      "grund": "kein mit dem Baukasten gebauter Report"})
                continue
            v = _report_uebernehmen(db, f, standard, user_id)
        else:
            uebersprungen.append({"art": art, "id": ziel, "grund": "unbekannte Art"})
            continue
        angelegt.append({"vorhaben_id": v.id, "name": v.name})

    safe_commit(db)
    return {"angelegt": angelegt, "uebersprungen": uebersprungen}
