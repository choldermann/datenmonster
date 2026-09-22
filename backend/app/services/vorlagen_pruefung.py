"""Laufen unsere Vorlagen noch auf allen JTL-Staenden, die wir bedienen?

Anlass: HaKo ist auf JTL-Wawi 2.0.5 gewechselt, dabei ist `fWertNettoGesamtFixiert`
verschwunden. Aufgefallen ist es beim Nachsehen von Hand - der Reiter "Kunden &
Rabatte" des Preis-Cockpits waere sonst beim Kunden in einen SQL-Fehler gelaufen.

Diese Pruefung dreht die Reihenfolge um: nicht der Anwender findet den Bruch,
sondern ein Nachtlauf. Geprueft werden die Vorlagen aus dem Katalog gegen die
JTL-Datenbanken, die diese Installation ohnehin kennt - mit demselben Trockenlauf
wie die Pruefung im Formular ([[jtl_kompatibilitaet]]).

**Je JTL-Version eine Datenbank.** Zwei Kopien desselben Standes zu pruefen kostet
Zeit und sagt zweimal dasselbe. Welche Verbindung eine Version vertritt, entscheidet
sich bei jedem Lauf neu: nach einem Wawi-Update wandert sie von selbst mit.

Verschickt wird nur, wenn sich etwas geaendert hat - ein Befund, der jede Nacht
unveraendert im Postfach liegt, wird nach drei Tagen nicht mehr gelesen. Wird eine
Vorlage repariert, kommt einmal die Entwarnung.
"""
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

SCHLUESSEL_CRON = "vorlagen_pruefung_cron"
SCHLUESSEL_EMPFAENGER = "vorlagen_pruefung_empfaenger"
SCHLUESSEL_AKTIV = "vorlagen_pruefung_aktiv"
SCHLUESSEL_STAND = "vorlagen_pruefung_stand"      # Fingerabdruck + Zeit des letzten Laufs

STANDARD_CRON = "40 3 * * *"

# Zahlwerte, die der Installer erst beim Einspielen setzt. Fuer die Uebersetzung
# genuegt eine 0 - NULL waere in `DATEADD(DAY, -{{tage}}, ...)` zwar erlaubt, aber
# 0 bleibt naeher am echten Ausdruck.
_PLATZHALTER = re.compile(r"\{\{[^}]+\}\}")


def _sql_knoten(inhalt: dict):
    """(Mapping-Name, SQL) aus einer Vorlagen-JSON."""
    for m in inhalt.get("mappings") or []:
        if not isinstance(m, dict):
            continue
        for n in m.get("sql_nodes") or []:
            sql = (n or {}).get("sql") or ""
            if sql.strip():
                yield (m.get("name") or m.get("id") or "?"), _PLATZHALTER.sub("0", sql)


def referenz_verbindungen(db) -> list:
    """Je JTL-Version eine Verbindung. Leer, wenn keine JTL-Datenbank erreichbar ist."""
    from app.models.dataset import DbConnection
    from app.services.jtl_kompatibilitaet import jtl_version

    gefunden = {}
    for c in db.query(DbConnection).filter(DbConnection.db_type == "mssql").order_by(DbConnection.id).all():
        version = jtl_version(c.id, db)
        if not version:
            continue                      # keine JTL-Datenbank oder nicht erreichbar
        kurz = ".".join(str(version).split(".")[:2])     # 1.8 / 1.11 / 2.0
        gefunden.setdefault(kurz, {"version": version, "kurz": kurz,
                                   "connection_id": c.id, "name": c.name})

    def sortierung(e):
        teile = [int(x) if x.isdigit() else 0 for x in str(e["version"]).split(".")]
        return teile + [0] * (4 - len(teile))

    return sorted(gefunden.values(), key=sortierung)


def pruefe_vorlage(inhalt: dict, connection_id: int, db) -> list:
    """Befunde einer Vorlage gegen EINE Datenbank: [{mapping, art, name}]."""
    from app.services.form_doku import _tables_from_sql
    from app.services.jtl_kompatibilitaet import _trockenlauf, fehlende_objekte

    befunde = []
    for mapping_name, sql in _sql_knoten(inhalt):
        fehlt = fehlende_objekte(connection_id, set(_tables_from_sql(sql)), db)
        if fehlt:
            # Fehlt schon die Tabelle, sagt der Trockenlauf nur dasselbe noch einmal.
            for t in sorted(fehlt):
                befunde.append({"mapping": mapping_name, "art": "objekt", "name": t})
            continue
        befund = _trockenlauf(connection_id, sql)
        if befund:
            befunde.append({"mapping": mapping_name, "art": befund[0], "name": befund[1]})
    return befunde


def pruefe_alle(db) -> dict:
    """Alle Vorlagen des Katalogs gegen je eine Datenbank pro JTL-Version."""
    from app.models.template import Template

    t0 = time.time()
    referenzen = referenz_verbindungen(db)
    vorlagen = db.query(Template).order_by(Template.name).all()

    befunde = []
    for t in vorlagen:
        inhalt = t.content if isinstance(t.content, dict) else {}
        if not inhalt:
            continue
        for ref in referenzen:
            for b in pruefe_vorlage(inhalt, ref["connection_id"], db):
                befunde.append({
                    "vorlage": t.name, "template_id": t.template_id, "version": t.version,
                    "jtl": ref["version"], "datenbank": ref["name"],
                    **b,
                })

    return {
        "zeit": datetime.now(timezone.utc).isoformat(),
        "dauer_s": round(time.time() - t0, 1),
        "referenzen": referenzen,
        "vorlagen": len(vorlagen),
        "befunde": befunde,
    }


def _fingerabdruck(befunde: list) -> str:
    """Was als 'dasselbe wie gestern' gilt - ohne Laufzeit und Reihenfolge."""
    schluessel = sorted(
        f"{b.get('template_id')}|{b.get('jtl')}|{b.get('mapping')}|{b.get('art')}|{b.get('name')}"
        for b in (befunde or [])
    )
    return json.dumps(schluessel, ensure_ascii=False)


def bericht(ergebnis: dict) -> dict:
    """Betreff, Text und HTML. Nennt die Vorlage, den JTL-Stand und das fehlende Feld."""
    befunde = ergebnis.get("befunde") or []
    refs = ergebnis.get("referenzen") or []
    geprueft = ", ".join(f"JTL {r['version']} ({r['name']})" for r in refs) or "keine JTL-Datenbank erreichbar"

    if not befunde:
        betreff = f"Vorlagen-Pruefung: alle {ergebnis.get('vorlagen', 0)} Vorlagen laufen"
        text = (f"Geprueft gegen: {geprueft}.\n"
                f"{ergebnis.get('vorlagen', 0)} Vorlagen, keine Befunde ({ergebnis.get('dauer_s')} s).")
        html = f"<p>Geprüft gegen: {geprueft}.</p><p><strong>Keine Befunde.</strong></p>"
        return {"subject": betreff, "text": text, "html": html, "anzahl": 0}

    # Nach Vorlage und JTL-Stand buendeln: das ist die Einheit, in der man repariert.
    gruppen = {}
    for b in befunde:
        gruppen.setdefault((b["vorlage"], b["version"], b["jtl"]), []).append(b)

    vorlagen_betroffen = len({b["template_id"] for b in befunde})
    staende = sorted({b["jtl"] for b in befunde})
    betreff = (f"Vorlagen-Pruefung: {vorlagen_betroffen} Vorlage"
               f"{'n' if vorlagen_betroffen != 1 else ''} passt nicht zu JTL {', '.join(staende)}")

    zeilen = [f"Geprueft gegen: {geprueft}.", ""]
    html = [f"<p>Geprüft gegen: {geprueft}.</p>"]
    for (vorlage, vversion, jtl), liste in sorted(gruppen.items()):
        zeilen.append(f"{vorlage} {vversion} auf JTL {jtl}:")
        html.append(f"<p style='margin:14px 0 4px'><strong>{vorlage} {vversion}</strong> auf JTL {jtl}:</p><ul>")
        for b in liste:
            was = "Feld" if b["art"] == "spalte" else "Objekt"
            zeilen.append(f"  - {b['mapping']}: {was} \"{b['name']}\" nicht vorhanden")
            html.append(f"<li>{b['mapping']}: {was} <code>{b['name']}</code> nicht vorhanden</li>")
        html.append("</ul>")
    zeilen += ["", f"{ergebnis.get('vorlagen', 0)} Vorlagen geprueft in {ergebnis.get('dauer_s')} s."]
    return {"subject": betreff, "text": "\n".join(zeilen), "html": "".join(html), "anzahl": len(befunde)}


def _stand_lesen(db) -> dict:
    from app.api.settings import get_setting
    try:
        return json.loads(get_setting(db, SCHLUESSEL_STAND) or "{}")
    except Exception:
        return {}


def _stand_schreiben(db, fingerabdruck: str, gesendet: bool) -> None:
    from app.api.settings import set_setting
    set_setting(db, SCHLUESSEL_STAND, json.dumps({
        "fingerabdruck": fingerabdruck,
        "zeit": datetime.now(timezone.utc).isoformat(),
        "gesendet": gesendet,
    }, ensure_ascii=False))


def lauf(db, empfaenger: Optional[str] = None, immer_senden: bool = False) -> dict:
    """Ein kompletter Durchgang inklusive Zustellung. Gibt Ergebnis + Versandlage zurueck."""
    from app.api.settings import get_setting
    from app.services.email_service import send_email

    ergebnis = pruefe_alle(db)
    neuer_abdruck = _fingerabdruck(ergebnis["befunde"])
    vorher = _stand_lesen(db)
    unveraendert = vorher.get("fingerabdruck") == neuer_abdruck

    ziele = (empfaenger if empfaenger is not None else get_setting(db, SCHLUESSEL_EMPFAENGER, "")) or ""
    ziele = ", ".join(e.strip() for e in ziele.replace(";", ",").split(",") if e.strip())

    versand = {"gesendet": False, "grund": ""}
    if not ziele:
        versand["grund"] = "keine Empfaenger hinterlegt"
    elif unveraendert and not immer_senden:
        versand["grund"] = "unveraendert seit dem letzten Lauf"
    else:
        post = bericht(ergebnis)
        try:
            send_email(to=ziele, subject=post["subject"], body=post["text"],
                       html_body=post["html"], db=db)
            versand = {"gesendet": True, "empfaenger": ziele, "betreff": post["subject"]}
        except Exception as e:                        # Zustellung darf den Lauf nicht kippen
            logger.error(f"Vorlagen-Pruefung: Mail nicht zugestellt: {e}")
            versand = {"gesendet": False, "grund": str(e)[:200]}

    _stand_schreiben(db, neuer_abdruck, versand.get("gesendet", False))
    ergebnis["versand"] = versand
    ergebnis["unveraendert"] = unveraendert
    return ergebnis
