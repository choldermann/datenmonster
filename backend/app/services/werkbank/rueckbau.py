"""Ein Vorhaben spurlos zurückbauen – ohne fremde Arbeit mitzureißen.

Zwei Regeln tragen dieses Modul:

**1. Rückwärts abbauen.** Zustellplan vor Report, Report vor Abfrage. Sonst
zeigt ein Zeitplan kurzzeitig auf ein gelöschtes Formular.

**2. Vor jedem Löschen auf Fremdnutzung prüfen.** In dieser Plattform
referenzieren Warnungen und Preisregeln Mappings **über den Namen**, nicht über
die ID – und ein weggelöschtes Mapping macht die Regel nicht kaputt, sondern
stumm „nicht verfügbar". Genau daran würde ein naiver Rückbau hier Schaden
anrichten, ohne eine einzige Fehlermeldung zu erzeugen.

Was `erzeugt=False` trägt, wird niemals gelöscht: dort haben wir ein
vorgefundenes Objekt nur ergänzt und nehmen ausschließlich unsere Zutat zurück.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm.attributes import flag_modified

from app.core.database import safe_commit
from app.models.vorhaben import Vorhaben, VorhabenArtefakt

logger = logging.getLogger(__name__)

# Beim Abbau zuerst das Äußere, dann das Tragende. Innerhalb eines Schritts
# entscheidet diese Reihenfolge; über Schritte hinweg gilt „rückwärts".
_ABBAU_RANG = {
    "portal": 6, "report_schedule": 5, "alert_rule": 4,
    "form": 3, "adhoc_query": 2, "mapping": 1, "widget": 0,
}


def _artefakte(db, v: Vorhaben) -> list:
    """Alle Artefakte des Vorhabens in Abbau-Reihenfolge."""
    rows = (db.query(VorhabenArtefakt)
              .filter(VorhabenArtefakt.vorhaben_id == v.id).all())
    return sorted(rows, key=lambda a: (-(a.schritt or 0), -_ABBAU_RANG.get(a.art, 0)))


# ─────────────────────────────────────────────────────────────────────────────
# Fremdnutzung
# ─────────────────────────────────────────────────────────────────────────────

def _mappings_eines_artefakts(db, a: VorhabenArtefakt) -> list:
    """Die Mappings, die beim Abbau dieses Artefakts verschwinden würden."""
    from app.models.mapping import Mapping
    from app.models.report import AdHocQuery

    ids = []
    if a.art == "adhoc_query":
        q = db.query(AdHocQuery).filter(AdHocQuery.id == a.ziel_id).first()
        if q:
            ids = [i for i in (q.mapping_id, q.verlauf_mapping_id) if i]
    elif a.art == "mapping" and a.erzeugt:
        ids = [a.ziel_id]
    if not ids:
        return []
    return db.query(Mapping).filter(Mapping.id.in_(ids)).all()


def _mapping_verwender(db, m, eigene_form_ids: set, eigene_regel_ids: set) -> list:
    """Wer benutzt dieses Mapping – außer uns selbst?"""
    from app.models.alert import AlertRule
    from app.models.form import Form
    from app.models.pipeline import Pipeline
    from app.models.preisregel import PriceRuleset
    from app.models.scheduled_job import ScheduledJob

    treffer = []

    # Warnungen: der Regelfall ist der NAME, weil dieselbe Regel in jeder
    # Installation eine andere Mapping-ID trifft.
    for r in db.query(AlertRule).all():
        if r.id in eigene_regel_ids:
            continue
        if (r.mapping_id and r.mapping_id == m.id) or \
           (r.mapping_name and r.mapping_name == m.name):
            treffer.append({"art": "Warnung", "name": r.name, "id": r.id})

    # Preisautomatik hält den Namen ihrer Kandidatenabfrage als Text.
    for p in db.query(PriceRuleset).all():
        if p.kandidaten_mapping and p.kandidaten_mapping == m.name:
            treffer.append({"art": "Preisregelwerk", "name": p.name, "id": p.id})

    for j in db.query(ScheduledJob).filter(ScheduledJob.mapping_id == m.id).all():
        treffer.append({"art": "Zeitplan", "name": j.name, "id": j.id})

    for pl in db.query(Pipeline).all():
        if _pipeline_nutzt(pl, m.id):
            treffer.append({"art": "Pipeline", "name": pl.name, "id": pl.id})

    # Aktionen fremder Formulare – ein Cockpit oder ein von Hand gebauter Report.
    for f in db.query(Form).all():
        if f.id in eigene_form_ids:
            continue
        for a in ((f.schema or {}).get("actions") or []):
            if a.get("mapping_id") == m.id:
                treffer.append({"art": "Formular", "name": f.name, "id": f.id})
                break
    return treffer


def _pipeline_nutzt(pl, mapping_id: int) -> bool:
    """Sucht die Mapping-ID irgendwo in den Knoten der Pipeline."""
    def suche(x) -> bool:
        if isinstance(x, dict):
            if x.get("mapping_id") == mapping_id:
                return True
            return any(suche(v) for v in x.values())
        if isinstance(x, list):
            return any(suche(v) for v in x)
        return False
    return suche(pl.nodes or [])


def _form_verwender(db, form_id: int, eigene_form_ids: set,
                    eigene_schedule_ids: set) -> list:
    """Wer hängt an diesem Formular – außer uns selbst?"""
    from app.models.form import Form
    from app.models.report import ReportSchedule

    treffer = []
    for s in db.query(ReportSchedule).filter(ReportSchedule.form_id == form_id).all():
        if s.id in eigene_schedule_ids:
            continue
        treffer.append({"art": "Zustellplan", "name": s.name, "id": s.id})

    # Ein fremder Report, der Bausteine aus diesem Formular übernommen hat.
    for f in db.query(Form).all():
        if f.id in eigene_form_ids or f.id == form_id:
            continue
        bau = (f.schema or {}).get("report_builder") or {}
        if any(int(e.get("form_id") or 0) == form_id for e in (bau.get("entries") or [])):
            treffer.append({"art": "Report", "name": f.name, "id": f.id})
    return treffer


def _widget_verwender(db, form_id: int, widget_ids: list, eigene_form_ids: set) -> list:
    """Fremde Reports, die genau unsere Bausteine übernommen haben.

    Das ist der wahrscheinlichste Fall überhaupt: Die Abfrage legt ihre
    Bausteine im Sammelformular ab, und der Report-Baukasten zeigt sie dort als
    wählbare Quelle an. Wer sie in einen eigenen Report übernommen hat, verlöre
    beim Rückbau eine Kachel – ohne Fehlermeldung, sie wäre einfach leer.
    """
    from app.models.form import Form

    if not widget_ids:
        return []
    gesucht = set(widget_ids)
    treffer = []
    for f in db.query(Form).all():
        if f.id in eigene_form_ids:
            continue
        bau = (f.schema or {}).get("report_builder") or {}
        for e in (bau.get("entries") or []):
            if int(e.get("form_id") or 0) == form_id and e.get("widget_id") in gesucht:
                treffer.append({"art": "Report", "name": f.name, "id": f.id})
                break
    return treffer


def pruefen(db, v: Vorhaben) -> dict:
    """Was der Rückbau tun würde – ohne etwas zu tun.

    Die Vorschau ist Pflicht, nicht Zierde: Sie ist die einzige Stelle, an der
    ein Anwender sieht, dass an seiner Auswertung inzwischen eine Warnung hängt.
    """
    from app.models.report import AdHocQuery

    rows = _artefakte(db, v)
    eigene_form_ids = {a.ziel_id for a in rows if a.art in ("form", "portal") and a.ziel_id}
    eigene_regel_ids = {a.ziel_id for a in rows if a.art == "alert_rule" and a.ziel_id}
    eigene_schedule_ids = {a.ziel_id for a in rows
                           if a.art == "report_schedule" and a.ziel_id}
    eigene_abfrage_ids = [a.ziel_id for a in rows
                          if a.art == "adhoc_query" and a.ziel_id]

    # Die Bausteine, die dieses Vorhaben im Sammelformular abgelegt hat.
    unsere_bausteine = {}
    if eigene_abfrage_ids:
        for q in db.query(AdHocQuery).filter(AdHocQuery.id.in_(eigene_abfrage_ids)).all():
            unsere_bausteine.setdefault(q.form_id, []).extend(q.widget_ids or [])
            # Das Sammelformular gehört zu uns, auch wenn seine Artefaktzeile
            # nach einem Teilrückbau schon weg ist. Ohne diese Zeile zählte seine
            # eigene Aktion auf unser Mapping als FREMDE Nutzung – der Rückbau
            # blockierte sich selbst und ließe sich nie zu Ende führen.
            eigene_form_ids.add(q.form_id)

    loeschen, bereinigen, blockiert = [], [], []

    for a in rows:
        eintrag = {"artefakt_id": a.id, "art": a.art, "ziel_id": a.ziel_id,
                   "label": a.label, "verwender": []}

        if not a.erzeugt:
            eintrag["hinweis"] = ("Vorgefunden – bleibt stehen, nur unsere Ergänzung "
                                  "wird zurückgenommen.")
            bereinigen.append(eintrag)
            continue

        # Was hängt daran?
        for m in _mappings_eines_artefakts(db, a):
            eintrag["verwender"].extend(
                _mapping_verwender(db, m, eigene_form_ids, eigene_regel_ids))
        if a.art == "adhoc_query":
            # Die Prüfung gehört an DIESES Artefakt, nicht an das Sammelformular:
            # hier werden die Bausteine tatsächlich entfernt. Ein fremder Report,
            # der eine davon übernommen hat, zeigte danach eine leere Kachel –
            # ohne Fehlermeldung.
            q = next((x for x in db.query(AdHocQuery)
                        .filter(AdHocQuery.id == a.ziel_id).all()), None)
            if q:
                eintrag["verwender"].extend(_widget_verwender(
                    db, q.form_id, q.widget_ids or [], eigene_form_ids))
        if a.art == "form":
            eintrag["verwender"].extend(
                _form_verwender(db, a.ziel_id, eigene_form_ids, eigene_schedule_ids))

        (blockiert if eintrag["verwender"] else loeschen).append(eintrag)

    return {
        "vorhaben_id": v.id, "name": v.name, "status": v.status,
        "loeschen": loeschen, "bereinigen": bereinigen, "blockiert": blockiert,
        "zusammenfassung": _satz(loeschen, bereinigen, blockiert),
    }


def _satz(loeschen: list, bereinigen: list, blockiert: list) -> str:
    teile = []
    if loeschen:
        teile.append(f"{len(loeschen)} Objekt(e) werden gelöscht")
    if bereinigen:
        teile.append(f"{len(bereinigen)} bleiben stehen und werden nur bereinigt")
    if blockiert:
        teile.append(f"{len(blockiert)} werden benutzt und bleiben unangetastet")
    return "; ".join(teile) or "Es gibt nichts zurückzubauen."


# ─────────────────────────────────────────────────────────────────────────────
# Ausführen
# ─────────────────────────────────────────────────────────────────────────────

def _abbauen(db, a: VorhabenArtefakt) -> None:
    """Ein einzelnes Artefakt zurückbauen."""
    from app.models.alert import AlertRule
    from app.models.form import Form
    from app.models.mapping import Mapping
    from app.models.report import AdHocQuery, ReportSchedule
    from app.services.query_builder import erzeugen

    if a.art == "adhoc_query":
        q = db.query(AdHocQuery).filter(AdHocQuery.id == a.ziel_id).first()
        if q:
            # Räumt Bausteine, Aktionen, Reiter-Verweise und Mappings – und lässt
            # das Sammelformular ausdrücklich stehen. Der Rückbau der Werkbank
            # macht hier nichts eigenes, sondern benutzt genau diese Funktion.
            erzeugen.entfernen(db, q)

    elif a.art == "form" and a.erzeugt:
        f = db.query(Form).filter(Form.id == a.ziel_id).first()
        if f:
            db.delete(f)

    elif a.art == "report_schedule":
        s = db.query(ReportSchedule).filter(ReportSchedule.id == a.ziel_id).first()
        if s:
            db.delete(s)

    elif a.art == "alert_rule":
        r = db.query(AlertRule).filter(AlertRule.id == a.ziel_id).first()
        if r:
            db.delete(r)

    elif a.art == "portal":
        # Zurück auf den Zustand vor der Veröffentlichung. Das Formular kann
        # vorher schon veröffentlicht gewesen sein – dann darf der Rückbau es
        # nicht unsichtbar machen.
        f = db.query(Form).filter(Form.id == a.ziel_id).first()
        if f and a.vorher:
            f.published = bool(a.vorher.get("published"))
            f.slug = a.vorher.get("slug")
            f.portal_config = a.vorher.get("portal_config") or {}
            flag_modified(f, "portal_config")

    elif a.art == "mapping" and a.erzeugt:
        m = db.query(Mapping).filter(Mapping.id == a.ziel_id).first()
        if m:
            db.delete(m)


def ausfuehren(db, v: Vorhaben, nur_ungenutzte: bool = True,
               endgueltig: bool = True) -> dict:
    """Baut das Vorhaben zurück.

    `nur_ungenutzte=True` überspringt alles, woran noch etwas hängt – das ist
    die Voreinstellung und der einzige Weg, der niemandem etwas kaputt macht.
    Nur wenn der Anwender ausdrücklich „trotzdem löschen" wählt, steht hier
    False.

    `endgueltig=False` wird beim Neubau benutzt: dann bleibt der Bauplan als
    Entwurf stehen, statt als zurückgebaut zu gelten.
    """
    plan = pruefen(db, v)
    ids_blockiert = {e["artefakt_id"] for e in plan["blockiert"]}

    # Bleibt etwas stehen, bleibt auch der Zusammenhang stehen: die Zeilen der
    # nur ergänzten Objekte sind keine Arbeit, sondern Kontext. Ohne sie wüsste
    # ein zweiter Anlauf nicht mehr, welches Formular zu diesem Vorhaben gehört.
    kontext_behalten = nur_ungenutzte and bool(ids_blockiert)

    abgebaut, uebersprungen = 0, 0
    for a in _artefakte(db, v):
        if nur_ungenutzte and a.id in ids_blockiert:
            # Die Artefaktzeile bleibt bewusst stehen. Sonst überlebte das Objekt
            # als Waise, von der niemand mehr weiß, dass sie zu diesem Vorhaben
            # gehört – und ein zweiter Versuch, wenn der Verweis weg ist, wäre
            # nicht mehr möglich.
            uebersprungen += 1
            continue
        try:
            _abbauen(db, a)
        except Exception as e:
            logger.exception("Rückbau von %s %s fehlgeschlagen", a.art, a.ziel_id)
            raise RuntimeError(f"Rückbau von „{a.label or a.art}“ fehlgeschlagen: "
                               f"{str(e)[:200]}")
        if a.erzeugt:
            abgebaut += 1
        # Reine Kontextzeilen (nichts zu löschen, nichts wiederherzustellen)
        # bleiben stehen, solange noch etwas blockiert ist.
        if kontext_behalten and not a.erzeugt and not a.vorher:
            continue
        db.delete(a)

    if not endgueltig:
        v.status = "entwurf"
    elif uebersprungen:
        # Ehrlich benennen: Es ist nicht alles weg, und der Anwender muss sehen,
        # was noch steht und warum.
        v.status = "teilrueckbau"
    else:
        # Das Vorhaben selbst bleibt stehen – mit seinem Bauplan. Nur so lässt
        # sich dasselbe später noch einmal bauen.
        v.status = "zurueckgebaut"
        v.zurueckgebaut_am = datetime.now(timezone.utc)
    safe_commit(db)

    return {"abgebaut": abgebaut, "uebersprungen": uebersprungen,
            "status": v.status, "blockiert": plan["blockiert"]}
