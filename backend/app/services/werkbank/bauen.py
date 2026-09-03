"""Einen Bauplan ausführen und jedes entstandene Objekt stempeln.

**Atomar, nicht schrittweise.** Ein Vorhaben ist ganz gebaut oder gar nicht.
Scheitert Schritt 3, werden 1 und 2 zurückgerollt – sonst bleiben genau die
Waisen zurück, gegen die der Rückbau antritt. Deshalb steht hier ein einziger
`safe_commit` am Ende und in jedem Schritt nur `db.flush()`.
"""
import logging
from datetime import datetime, timezone

from app.core.database import safe_commit
from app.models.vorhaben import Vorhaben, VorhabenArtefakt

from . import werkzeuge
from .werkzeuge import WerkzeugFehler

logger = logging.getLogger(__name__)


def kontext(v: Vorhaben, user_id: int | None = None) -> dict:
    """Was jedes Werkzeug über das Vorhaben wissen muss."""
    return {
        "vorhaben_id": v.id,
        "project_id": v.project_id,
        "mandant_id": v.mandant_id,
        "user_id": user_id,
        "beschreibung": v.beschreibung or "",
    }


def aktive_schritte(v: Vorhaben) -> list:
    """Die angehakten Schritte, in lauffähiger Reihenfolge."""
    schritte = [s for s in (v.bauplan or []) if s.get("aktiv", True) and s.get("werkzeug")]
    return werkzeuge.sortiert(schritte)


def vorschau(db, v: Vorhaben, user_id: int | None = None) -> list:
    """Führt die Vorschau aller Schritte aus, ohne irgendetwas zu speichern.

    Die Vorschau ist das Gegenmittel gegen den Fehler, den man einer erzeugten
    Auswertung nicht ansieht: Sie rechnet mit echten Zahlen gegen die echte
    WaWi des Mandanten.
    """
    if not v.mandant_id:
        raise WerkzeugFehler("Dem Vorhaben fehlt der Mandant – es ist unklar, gegen "
                             "welche Warenwirtschaft gerechnet werden soll.")
    ctx = kontext(v, user_id)
    bisher: dict = {}
    raus = []
    for i, s in enumerate(aktive_schritte(v)):
        w = werkzeuge.get(s["werkzeug"])
        eintrag = {
            "werkzeug": w["key"], "label": w["label"],
            "zusammenfassung": werkzeuge.zusammenfassen(w["key"], s.get("eingabe") or {}),
        }
        fn = w.get("vorschau")
        if fn:
            try:
                eintrag["ergebnis"] = fn(db, ctx, s.get("eingabe") or {}, bisher)
            except WerkzeugFehler as e:
                eintrag["fehler"] = str(e)
            except Exception as e:                      # nie den ganzen Lauf reißen
                logger.exception("Vorschau %s fehlgeschlagen", w["key"])
                eintrag["fehler"] = f"Vorschau fehlgeschlagen: {str(e)[:200]}"
        else:
            eintrag["ergebnis"] = None
        raus.append(eintrag)

        # Die Vorschau darf nichts anlegen; die Folgeschritte brauchen aber die
        # Bausteine des Abfrage-Schritts. Wir tun so, als gäbe es sie schon.
        if w["key"] == "abfrage" and "fehler" not in eintrag:
            bisher.setdefault("bausteine", []).append({"form_id": 0, "widget_id": "vorschau"})
            bisher.setdefault("mapping_namen", []).append(
                (s.get("eingabe") or {}).get("name") or "")
    return raus


def ausfuehren(db, v: Vorhaben, user_id: int | None = None) -> dict:
    """Baut das Vorhaben und stempelt jedes erzeugte Objekt.

    Der Aufrufer muss bei einer Ausnahme `db.rollback()` machen – dann ist
    nichts entstanden.
    """
    if not v.mandant_id:
        raise WerkzeugFehler("Dem Vorhaben fehlt der Mandant. Ohne ihn würde später "
                             "stumm gegen den falschen Betrieb gerechnet.")
    schritte = aktive_schritte(v)
    if not schritte:
        raise WerkzeugFehler("Im Bauplan ist kein Schritt angehakt.")

    ctx = kontext(v, user_id)
    bisher: dict = {}
    artefakte: list = []

    for i, s in enumerate(schritte):
        w = werkzeuge.get(s["werkzeug"])
        eingabe = s.get("eingabe") or {}
        try:
            neu = w["bauen"](db, ctx, eingabe, bisher) or []
        except WerkzeugFehler:
            raise
        except Exception as e:
            logger.exception("Bauschritt %s fehlgeschlagen", w["key"])
            raise WerkzeugFehler(f"Schritt „{w['label']}“ fehlgeschlagen: {str(e)[:200]}")

        for a in neu:
            art = VorhabenArtefakt(
                vorhaben_id=v.id, schritt=i, werkzeug=w["key"],
                art=a["art"], ziel_id=a.get("ziel_id"), ziel_key=a.get("ziel_key"),
                label=a.get("label"), erzeugt=bool(a.get("erzeugt", True)),
                vorher=a.get("vorher"),
            )
            db.add(art)
            artefakte.append(art)

    v.status = "installiert"
    v.gebaut_am = datetime.now(timezone.utc)
    v.zurueckgebaut_am = None
    safe_commit(db)

    return {
        "vorhaben_id": v.id,
        "artefakte": len(artefakte),
        "erzeugt": sum(1 for a in artefakte if a.erzeugt),
        "ergaenzt": sum(1 for a in artefakte if not a.erzeugt),
        "portal_slug": bisher.get("portal_slug"),
        "report_form_id": bisher.get("report_form_id"),
    }


def neu_bauen(db, v: Vorhaben, user_id: int | None = None) -> dict:
    """Ein installiertes Vorhaben mit geändertem Bauplan erneut bauen.

    Erst vollständig zurückbauen, dann neu – **nicht patchen**. Beim Patchen
    ändern sich die aus dem Namen abgeleiteten IDs, und die alte Aktion bliebe
    als Waise zurück: Sie liefe bei jedem Formularlauf weiter mit, ohne dass
    etwas davon zu sehen wäre. Genau dieser Fehler ist im Abfrage-Generator
    schon einmal aufgetreten.
    """
    from . import rueckbau

    if v.status == "installiert":
        rueckbau.ausfuehren(db, v, nur_ungenutzte=False, endgueltig=False)
    return ausfuehren(db, v, user_id)
