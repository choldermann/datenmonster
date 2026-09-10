"""
Läuft die Berechtigung für die installierten Vorlagen noch?

Der Kauf wird bisher nur EINMAL geprüft — beim Holen aus dem Store. Danach lief eine
Vorlage für immer weiter, auch wenn die Testphase ohne Kauf endete. Dieses Modul holt
die Auskunft nach: einmal am Tag fragt die Installation bei monstersuite nach, was von
dem, was hier installiert ist, noch berechtigt ist.

Vertrag: POST {LICENSE_SERVER}/api/v1/templates/entitlements
  Request : { license_key, email, machine_id, hostname, product, version, template_ids }
  Response: { "templates": { "<template_id>": {...} }, "geprueft_am": iso }
            je Vorlage: { bekannt, name, entitled, art, gueltig_bis, angebote[] }
            `bekannt: false` = der Server kennt die Vorlage nicht (Eigenbau, fremde
            Quelle) → ausdrücklich KEIN Urteil, die Vorlage läuft weiter.

Zwei Regeln, die hier wichtiger sind als die Sperre selbst:

1. **Schweigen ist kein Nein.** Ein nicht erreichbarer Server, ein Zeitüberlauf, ein
   Fehler — nichts davon sperrt etwas. Gesperrt wird nur, was der Server ausdrücklich
   als nicht berechtigt bezeichnet, oder was nach Ablauf der Karenzzeit ohne jede
   Auskunft dasteht.
2. **Höchstens ein Netzaufruf pro Tag** (nach einem Fehler frühestens in 30 Minuten
   wieder). Die Abfrage hängt am Lauf einer Auswertung — sie darf ihn nicht bremsen.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

TTL_STUNDEN         = 24     # so lange gilt eine erfolgreiche Auskunft als frisch
FEHLER_PAUSE_MIN    = 30     # nach einem Fehlversuch nicht sofort wieder anklopfen
ZEITLIMIT_SEKUNDEN  = 6      # ein hängender Server darf keinen Cockpit-Lauf blockieren
MAX_VORLAGEN        = 200

S_DATEN   = "vorlagen_berechtigung_json"
S_STAND   = "vorlagen_berechtigung_at"        # letzte ERFOLGREICHE Auskunft
S_VERSUCH = "vorlagen_berechtigung_versuch"   # letzter Versuch (auch fehlgeschlagen)
S_ERSTER  = "vorlagen_berechtigung_erster"    # allererster Versuch dieser Installation


# ─── Einstellungen lesen/schreiben ────────────────────────────────────────────
def _get(db: Session, key: str) -> str:
    from app.models.setting import SystemSetting
    s = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    return s.value if s else ""


def _set(db: Session, key: str, value: str) -> None:
    from app.models.setting import SystemSetting
    s = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if s:
        s.value = value
    else:
        db.add(SystemSetting(key=key, value=value))


def _merken(*paare) -> bool:
    """Einstellungen in einer eigenen Sitzung schreiben (Schlüssel, Wert, Schlüssel, Wert)."""
    from app.core.database import SessionLocal
    eigene = SessionLocal()
    try:
        for key, value in zip(paare[0::2], paare[1::2]):
            _set(eigene, key, value)
        eigene.commit()
        return True
    except Exception as e:
        eigene.rollback()
        logger.warning(f"Vorlagen-Berechtigung: Stand nicht speicherbar ({e})")
        return False
    finally:
        eigene.close()


def _jetzt() -> datetime:
    return datetime.now(timezone.utc)


def _zeit(iso: str) -> Optional[datetime]:
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(iso)
    except Exception:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def alter_stunden(db: Session) -> Optional[float]:
    """Wie alt ist die letzte erfolgreiche Auskunft? None = es gab noch nie eine."""
    stand = _zeit(_get(db, S_STAND))
    if not stand:
        return None
    return (_jetzt() - stand).total_seconds() / 3600.0


def karenz_beginn(db: Session) -> Optional[datetime]:
    """Ab wann läuft die Karenzzeit, wenn es noch NIE eine Auskunft gab?

    Ab dem ersten Versuch — nicht ab dem Installationsdatum der Vorlage. Der
    Unterschied ist der Unterschied zwischen einer sanften Einführung und einem
    Fehlstart: bei einer bestehenden Installation sind die Vorlagen längst älter als
    die Karenzzeit, und ein Server, der diesen Endpunkt noch nicht kennt, würde jedes
    gekaufte Cockpit sofort sperren.
    """
    return _zeit(_get(db, S_ERSTER))


def gespeicherte_auskunft(db: Session) -> dict:
    try:
        daten = json.loads(_get(db, S_DATEN) or "{}")
        return daten if isinstance(daten, dict) else {}
    except Exception:
        return {}


# ─── Abruf ────────────────────────────────────────────────────────────────────
def _installierte_vorlagen(db: Session) -> list:
    """template_ids, die hier tatsächlich installiert sind.

    Bewusst ALLE und nicht nur die bekannten kostenpflichtigen: so entscheidet der
    Server, was Ware ist. Eine künftig verkaufte Vorlage ist damit ohne Änderung an
    dieser Installation abgedeckt — und selbstgeschriebenes JSON mit der Kennung einer
    verkauften Vorlage fällt ebenfalls auf.
    """
    from app.models.template import Template
    ids = []
    for t in db.query(Template).all():
        if t.installations and t.template_id:
            ids.append(t.template_id)
    return ids[:MAX_VORLAGEN]


def abrufen(db: Session, erzwingen: bool = False) -> dict:
    """Holt die Auskunft vom Lizenzserver, wenn sie fällig ist. Gibt das Ergebnis zurück.

    Wirft nie: jeder Fehler endet mit der zuletzt bekannten Auskunft.

    Geschrieben wird in einer EIGENEN Sitzung: der Aufrufer ist meist ein laufendes
    Cockpit, dessen Sitzung offene Änderungen tragen kann — ein commit von hier würde
    die mit festschreiben.
    """
    from app.api.license import LICENSE_SERVER, license_auth_body, get_license_credentials

    vorhanden = gespeicherte_auskunft(db)

    # Startpunkt der Karenzuhr, einmalig und vor jedem Abbruchgrund: erst ab hier zählt
    # das Tor die Tage ohne Auskunft. Stünde es weiter unten, liefe eine Installation,
    # die nie zum Fragen kommt (kein Schlüssel, Pause), ohne laufende Uhr.
    if not _get(db, S_ERSTER):
        _merken(S_ERSTER, _jetzt().isoformat(timespec="seconds"))

    if not erzwingen:
        alt = alter_stunden(db)
        if alt is not None and alt < TTL_STUNDEN:
            return vorhanden
        versuch = _zeit(_get(db, S_VERSUCH))
        if versuch and (_jetzt() - versuch).total_seconds() < FEHLER_PAUSE_MIN * 60:
            return vorhanden

    _merken(S_VERSUCH, _jetzt().isoformat(timespec="seconds"))

    key, _email = get_license_credentials(db)
    if not key:
        # Ohne Lizenzschlüssel gibt es niemanden zu fragen. Kein Urteil — die
        # Karenzregel im Tor entscheidet.
        return vorhanden

    ids = _installierte_vorlagen(db)
    if not ids:
        return vorhanden

    try:
        import httpx
        with httpx.Client(timeout=ZEITLIMIT_SEKUNDEN) as c:
            r = c.post(f"{LICENSE_SERVER}/api/v1/templates/entitlements",
                       json={**license_auth_body(db), "template_ids": ids})
        antwort = r.json()
    except Exception as e:
        logger.warning(f"Vorlagen-Berechtigung nicht abrufbar: {e}")
        return vorhanden

    if not isinstance(antwort, dict) or not isinstance(antwort.get("templates"), dict):
        logger.warning(f"Vorlagen-Berechtigung: unerwartete Antwort ({str(antwort)[:200]})")
        return vorhanden
    if antwort.get("error"):
        # Lizenzfehler ist kein Vorlagen-Urteil (siehe Modulkopf).
        logger.warning(f"Vorlagen-Berechtigung: {antwort.get('error')} — {antwort.get('message')}")
        return vorhanden

    ergebnis = antwort["templates"]
    if not _merken(S_DATEN, json.dumps(ergebnis, ensure_ascii=False),
                   S_STAND, _jetzt().isoformat(timespec="seconds")):
        return vorhanden

    gesperrt = [tid for tid, e in ergebnis.items()
                if isinstance(e, dict) and e.get("bekannt") and not e.get("entitled")]
    if gesperrt:
        logger.info(f"Vorlagen ohne laufende Berechtigung: {', '.join(gesperrt)}")
    return ergebnis
