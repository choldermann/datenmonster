"""Warnt, BEVOR das KI-Guthaben leer ist.

Anlass: Laeuft das Guthaben aus, faellt die KI still aus. Der naechtliche
Cockpit-Report kam bis 2026-09-23 einfach ohne Management-Summary - kein Hinweis,
kein Fehler, nichts. Wer den Report morgens ueberfliegt, haelt die duennere Fassung
fuer das normale Ergebnis. Seit heute nennt der Report den Grund; hier kommt die
andere Haelfte: eine Mail, bevor es soweit ist.

Bewusst nur EINE Mail je Zustandswechsel. Eine Warnung, die jede Nacht erneut
kommt, wird nach drei Tagen weggeklickt - und genau dann faellt die vierte auf,
die gezaehlt haette.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

SCHLUESSEL_AKTIV = "ai_guthaben_warnung_aktiv"
SCHLUESSEL_SCHWELLE = "ai_guthaben_schwelle"
SCHLUESSEL_EMPFAENGER = "ai_guthaben_empfaenger"
SCHLUESSEL_STAND = "ai_guthaben_stand"

STANDARD_SCHWELLE = 150          # Credits


def stand(db) -> dict:
    """Guthaben, Schwelle und Urteil. Fehler sind hier kein Drama, nur ein Feld."""
    from app.api.settings import get_setting
    from app.api.license import license_auth_body, LICENSE_SERVER
    import httpx

    provider = get_setting(db, "ai_provider", "ollama")
    try:
        schwelle = int(get_setting(db, SCHLUESSEL_SCHWELLE, STANDARD_SCHWELLE) or STANDARD_SCHWELLE)
    except ValueError:
        schwelle = STANDARD_SCHWELLE

    if provider != "datenmonster":
        # Ollama kostet nichts - eine Guthabenwarnung waere hier nur Rauschen.
        return {"zutreffend": False, "provider": provider, "schwelle": schwelle}

    try:
        with httpx.Client(timeout=10) as c:
            r = c.post(f"{LICENSE_SERVER}/api/v1/ai/balance", json=license_auth_body(db))
            r.raise_for_status()
            d = r.json()
    except Exception as e:
        return {"zutreffend": True, "provider": provider, "schwelle": schwelle,
                "fehler": str(e)[:160]}

    guthaben = int(d.get("balance") or 0)
    monat = d.get("month") or {}
    return {
        "zutreffend": True, "provider": provider, "schwelle": schwelle,
        "guthaben": guthaben, "monat": monat,
        # `low_balance` kommt vom Gateway (dessen eigene Schwelle); unsere eigene
        # Schwelle gilt zusaetzlich - wer viel verbraucht, will frueher Bescheid wissen.
        "knapp": guthaben <= schwelle or bool(d.get("low_balance")),
    }


def _stand_lesen(db) -> dict:
    from app.api.settings import get_setting
    try:
        return json.loads(get_setting(db, SCHLUESSEL_STAND) or "{}")
    except Exception:
        return {}


def _stand_schreiben(db, knapp: bool, guthaben: Optional[int]) -> None:
    from app.api.settings import set_setting
    set_setting(db, SCHLUESSEL_STAND, json.dumps({
        "knapp": knapp, "guthaben": guthaben,
        "zeit": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False))


def pruefen_und_melden(db, immer_senden: bool = False) -> dict:
    """Ein Durchgang. Mail nur beim Wechsel in den knappen Zustand (oder erzwungen)."""
    from app.api.settings import get_setting
    from app.services.email_service import send_email

    lage = stand(db)
    if not lage.get("zutreffend") or lage.get("fehler"):
        return {**lage, "gesendet": False,
                "grund": lage.get("fehler") or "Datenmonster AI ist nicht der Anbieter"}

    vorher = _stand_lesen(db)
    wechsel = bool(lage["knapp"]) and not vorher.get("knapp")
    erholt = (not lage["knapp"]) and vorher.get("knapp")

    ziele = (get_setting(db, SCHLUESSEL_EMPFAENGER, "") or "")
    ziele = ", ".join(e.strip() for e in ziele.replace(";", ",").split(",") if e.strip())
    aktiv = (get_setting(db, SCHLUESSEL_AKTIV, "0") or "0") == "1"

    gesendet, grund = False, ""
    if not aktiv and not immer_senden:
        grund = "Warnung ist abgeschaltet"
    elif not ziele:
        grund = "keine Empfaenger hinterlegt"
    elif not (wechsel or erholt or immer_senden):
        grund = "unveraendert seit der letzten Pruefung"
    else:
        verbrauch = lage.get("monat", {}).get("credits_used")
        if lage["knapp"] or immer_senden:
            betreff = f"KI-Guthaben knapp: noch {lage['guthaben']} Credits"
            text = (f"Das Guthaben fuer Datenmonster AI liegt bei {lage['guthaben']} Credits "
                    f"(Warnschwelle {lage['schwelle']}).\n"
                    f"Verbrauch diesen Monat: {verbrauch if verbrauch is not None else '?'} Credits.\n\n"
                    "Laeuft es leer, faellt die KI aus: Cockpit-Reports kommen dann ohne "
                    "Management-Summary, der KI-Assistent antwortet nicht mehr. Die Auswertungen "
                    "selbst laufen weiter.\n\n"
                    "Aufladen in Datenmonster unter Einstellungen → KI → Guthaben aufladen.")
        else:
            betreff = f"KI-Guthaben wieder ausreichend: {lage['guthaben']} Credits"
            text = (f"Das Guthaben liegt wieder bei {lage['guthaben']} Credits "
                    f"(Warnschwelle {lage['schwelle']}).")
        try:
            send_email(to=ziele, subject=betreff, body=text, db=db)
            gesendet = True
        except Exception as e:                       # Zustellung darf nichts kippen
            logger.error(f"KI-Guthabenwarnung nicht zugestellt: {e}")
            grund = str(e)[:160]

    _stand_schreiben(db, bool(lage["knapp"]), lage.get("guthaben"))
    return {**lage, "gesendet": gesendet, "grund": grund}
