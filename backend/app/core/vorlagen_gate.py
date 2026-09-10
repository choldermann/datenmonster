"""
Laufzeit-Sperre für Vorlagen ohne laufende Berechtigung.

Das Lizenzmodell sagt: gesperrt wird der Editor, nicht die Maschine ([[lizenz_gate]]).
Für eine GEKAUFTE Vorlage gilt das weiter. Hier geht es um den anderen Fall: eine
Vorlage, für die nie bezahlt wurde — die Testphase ist abgelaufen, das Abo beendet.
Die lief bisher unverändert weiter, weil der Kauf nur beim Herunterladen geprüft wurde.

Zwei Wege führen zur Sperre, und sie decken unterschiedliche Löcher ab:

1. **Signiertes Ablaufdatum.** Testlieferungen tragen es im Signaturblock
   (`gueltig_bis`). Es ist mitsigniert, lässt sich also nicht herausschneiden, und
   greift OHNE Netz — genau der Fall, den eine reine Online-Prüfung verfehlt: Instanz
   herunterladen, Stecker ziehen, ewig testen.
2. **Tägliche Auskunft des Lizenzservers** (`vorlagen_berechtigung`). Sie deckt alles
   ab, was kein Datum haben darf: beendete Abos, zurückgegebene Käufe — und auch
   selbstgeschriebenes JSON mit der Kennung einer verkauften Vorlage, denn gefragt
   wird nach template_id, nicht nach Signatur.

Und drei Regeln, die verhindern, dass die Sperre den falschen trifft:

- **Ein zahlender Kunde wird nie durch Schweigen gesperrt.** Sagt der Server nichts
  (nicht erreichbar, Zeitüberlauf), gilt die letzte Auskunft weiter; erst nach der
  Karenzzeit von `GRACE_DAYS` ohne jede Auskunft wird zugemacht — dieselbe Frist, die
  die Lizenzprüfung selbst benutzt.
- **Der Server ist aktueller als die Signatur.** Wer während der Testphase kauft, hat
  eine Datei mit abgelaufenem Datum auf der Platte. Sagt der Server "berechtigt",
  gewinnt das.
- **Eigenbau und fremde Vorlagen bleiben unberührt.** Gesperrt wird nur, was der
  Server ausdrücklich als nicht berechtigt bezeichnet, plus die hier bekannten
  kostenpflichtigen Vorlagen nach abgelaufener Karenz.
"""
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Objektarten, die aus einer Vorlage stammen können (Schlüssel in Template.installations)
ARTEN = ("forms", "mappings", "datasets", "pipelines", "reports", "alert_rules", "rest_sources")

_CACHE: dict = {"zeit": 0.0, "zustand": None, "index": None}
_CACHE_SEKUNDEN = 60


def cache_leeren() -> None:
    """Nach Installieren/Entfernen einer Vorlage oder Lizenzwechsel."""
    _CACHE.update({"zeit": 0.0, "zustand": None, "index": None})


def _jetzt() -> datetime:
    return datetime.now(timezone.utc)


# ─── Zustand je Vorlage ───────────────────────────────────────────────────────
def _zustand_einer(t, eintrag: Optional[dict], auskunft_alter: Optional[float],
                   lizenz: str, karenz_beginn=None) -> dict:
    """Beurteilt EINE installierte Vorlage. Rückgabe mit status frei|gesperrt."""
    from app.api.license import GRACE_DAYS
    from app.services.template_signatur import (braucht_signatur, pruefe,
                                                signiertes_ablaufdatum, _ist_abgelaufen)

    tid = t.template_id or ""
    name = t.name or tid
    basis = {"template_id": tid, "name": name, "status": "frei", "grund": "",
             "art": None, "gueltig_bis": None, "angebote": []}

    # 1. Ausdrückliche Auskunft des Servers
    if isinstance(eintrag, dict) and eintrag.get("bekannt"):
        basis["art"] = eintrag.get("art")
        basis["gueltig_bis"] = eintrag.get("gueltig_bis")
        basis["angebote"] = eintrag.get("angebote") or []
        if not eintrag.get("entitled"):
            return {**basis, "status": "gesperrt", "grund": _grund_ohne_berechtigung(eintrag)}
        # Ein "berechtigt" gilt nicht über sein eigenes Ende hinaus. Sonst hebelt eine
        # einzige Auskunft während der Testphase alles aus: danach die Verbindung kappen,
        # und die gespeicherte Zusage liefe ewig — genau das Loch, das das signierte
        # Datum schließen soll. Ein Abo bleibt davon ausgenommen: sein Periodenende
        # verlängert sich mit der nächsten Auskunft, Schweigen sperrt es nicht.
        if eintrag.get("art") == "test" and _ist_abgelaufen(eintrag.get("gueltig_bis")):
            return {**basis, "status": "gesperrt", "grund": _grund_ohne_berechtigung(eintrag)}
        # Eine Zusage, die älter als die Karenzzeit ist, trägt nicht mehr: dann zählt
        # sie wie keine Auskunft (Schritt 2 und 3).
        if auskunft_alter is None or auskunft_alter <= GRACE_DAYS * 24:
            return basis

    # 2. Keine Auskunft → das signierte Ablaufdatum entscheidet, wenn es eins gibt
    inhalt = t.content if isinstance(t.content, dict) else {}
    ablauf = signiertes_ablaufdatum(inhalt)
    if ablauf and _ist_abgelaufen(ablauf):
        # Erst die Signaturprüfung belegt, dass das Datum echt ist — sie schlägt bei
        # abgelaufener Frist ebenso fehl wie bei einer veränderten Datei. Beides sperrt:
        # ein Datum tragen nur befristete Lieferungen, und die sind ohne gültige
        # Signatur ohnehin nichts wert.
        ok, _grund = pruefe(inhalt, lizenz or "")
        if not ok:
            return {**basis, "status": "gesperrt", "art": "test",
                    "gueltig_bis": ablauf,
                    "grund": (f"Die Testphase für „{name}“ ist am {ablauf[:10]} abgelaufen. "
                              "Nach dem Kauf läuft die Auswertung sofort weiter — "
                              "die installierten Daten bleiben erhalten.")}

    # 3. Gar keine Auskunft und kein Datum: Karenz. Nur bekannte kostenpflichtige
    #    Vorlagen laufen überhaupt in eine Sperre — alles andere bleibt frei.
    if not braucht_signatur(tid):
        return basis

    if auskunft_alter is not None:
        if auskunft_alter <= GRACE_DAYS * 24:
            return basis
        tage = int(auskunft_alter / 24)
    else:
        # Noch nie eine Auskunft bekommen: Frist ab dem ersten Frageversuch. Eine
        # bestehende Installation bekommt damit ihre vollen Karenztage, statt beim
        # ersten Start nach dem Update alles zu sperren.
        if not karenz_beginn:
            return basis
        tage = (_jetzt() - karenz_beginn).days
        if tage <= GRACE_DAYS:
            return basis
    return {**basis, "status": "gesperrt",
            "grund": (f"Für „{name}“ ließ sich die Berechtigung seit {tage} Tagen nicht "
                      "prüfen — der Lizenzserver ist nicht erreichbar. Sobald die "
                      "Verbindung wieder steht, läuft die Auswertung weiter.")}


def _grund_ohne_berechtigung(eintrag: dict) -> str:
    name = eintrag.get("name") or "Diese Vorlage"
    bis = (eintrag.get("gueltig_bis") or "")[:10]
    if eintrag.get("art") == "test":
        return (f"Die Testphase für „{name}“ ist{f' am {bis}' if bis else ''} abgelaufen. "
                "Nach dem Kauf läuft die Auswertung sofort weiter — die installierten "
                "Daten bleiben erhalten.")
    return (f"Für „{name}“ besteht keine laufende Lizenz mehr. Nach dem Kauf läuft die "
            "Auswertung sofort weiter — die installierten Daten bleiben erhalten.")


def zustand(db: Session, frisch: bool = False) -> dict:
    """template_id → Zustand, für alle installierten Vorlagen."""
    jetzt = time.time()
    if not frisch and _CACHE["zustand"] is not None and jetzt - _CACHE["zeit"] < _CACHE_SEKUNDEN:
        return _CACHE["zustand"]

    from app.models.template import Template
    from app.services import vorlagen_berechtigung as vb
    from app.api.license import get_license_credentials

    try:
        auskunft = vb.abrufen(db, erzwingen=frisch)
        alter = vb.alter_stunden(db)
        karenz = vb.karenz_beginn(db)
        lizenz, _ = get_license_credentials(db)
    except Exception as e:
        logger.warning(f"Vorlagen-Zustand: Auskunft nicht verfügbar ({e})")
        auskunft, alter, karenz, lizenz = {}, None, None, ""

    ergebnis, index = {}, {art: {} for art in ARTEN}
    for t in db.query(Template).all():
        if not t.installations:
            continue
        z = _zustand_einer(t, auskunft.get(t.template_id), alter, lizenz, karenz)
        ergebnis[t.template_id] = z
        for inst in (t.installations or []):
            for art, ids in ((inst.get("objects") or {}).items()):
                if art in index:
                    for oid in (ids or []):
                        if isinstance(oid, int):
                            index[art][oid] = t.template_id

    _CACHE.update({"zeit": jetzt, "zustand": ergebnis, "index": index})
    return ergebnis


def _index(db: Session) -> dict:
    zustand(db)
    return _CACHE["index"] or {}


# ─── Abfrage und Sperre ───────────────────────────────────────────────────────
def sperre_fuer_vorlage(db: Session, template_id: str) -> Optional[dict]:
    z = zustand(db).get(template_id)
    return z if z and z["status"] == "gesperrt" else None


def sperre_fuer_objekt(db: Session, art: str, obj_id) -> Optional[dict]:
    """Gehört dieses Objekt zu einer gesperrten Vorlage? Sonst None."""
    if not isinstance(obj_id, int):
        return None
    tid = _index(db).get(art, {}).get(obj_id)
    if not tid:
        return None           # Eigenbau oder fremde Herkunft → nie gesperrt
    return sperre_fuer_vorlage(db, tid)


def als_fehler(sperre: dict) -> HTTPException:
    """402 mit maschinenlesbarem Inhalt — das Frontend zeigt daraus den Kauf-Hinweis."""
    return HTTPException(402, detail={
        "code":        "vorlage_gesperrt",
        "template_id": sperre.get("template_id"),
        "vorlage":     sperre.get("name"),
        "art":         sperre.get("art"),
        "gueltig_bis": sperre.get("gueltig_bis"),
        "angebote":    sperre.get("angebote") or [],
        "message":     sperre.get("grund"),
    })


def pruefe_objekt(db: Session, art: str, obj_id) -> None:
    sperre = sperre_fuer_objekt(db, art, obj_id)
    if sperre:
        raise als_fehler(sperre)


def pruefe_formular(db: Session, form) -> None:
    pruefe_objekt(db, "forms", getattr(form, "id", None))


def darf_laufen(db: Session, art: str, obj_id) -> bool:
    """Für Hintergrundläufe (Zeitplan, Warnungen): kein Fehler, nur ja/nein."""
    try:
        return sperre_fuer_objekt(db, art, obj_id) is None
    except Exception:
        return True
