"""Passt dieses Cockpit zur JTL-Version dieses Mandanten?

Anlass: HyDa laeuft auf JTL-Wawi 1.8, die uebrigen Mandanten auf 1.11. Die
Cockpits sind gegen das neuere Schema gebaut. Unter HyDa scheiterten dadurch 24
von 27 Abfragen des Lager-Cockpits mit `Ungültiger Objektname "dbo.vArtikelHistorie"`
- fuer den Anwender 24 rohe SQL-Fehler statt einer verstaendlichen Aussage.

**Geprueft wird gegen die vorhandenen OBJEKTE, nicht gegen eine Versionsnummer.**
Das ist der Kern: eine gepflegte Tabelle "Cockpit X braucht JTL >= Y" waere beim
naechsten JTL-Release schon wieder falsch, und niemand merkt es. Existiert die
Sicht dagegen nach einem Update, faellt die Meldung von selbst weg - ohne dass
hier irgendetwas nachgezogen werden muss.

Zwei Stufen, weil sie verschiedene Faelle erwischen:
  * `pruefe_formular()` - VORHER. Liest die Tabellen/Sichten aus den Mappings und
    fragt die Datenbank, welche davon fehlen. Faengt den Lager-Fall als Ganzes ab.
  * `erklaere_sql_fehler()` - NACHHER. Uebersetzt „Ungültiger Objektname/Spaltenname"
    in Klartext. Noetig, weil fehlende SPALTEN (HyDa: `nLieferstatus` auf
    `dbo.tAuftragEckdaten`) sich nicht zuverlaessig aus dem SQL ablesen lassen.
"""
import re
import time
from typing import Optional

# Zwischenspeicher je Verbindung. Kurze Haltbarkeit, damit ein JTL-Update
# spaetestens nach dieser Zeit von selbst wirkt, ohne Neustart und ohne dass
# jemand daran denken muss. Der Mandantenwechsel leert zusaetzlich gezielt.
_CACHE: dict = {}
_HALTBAR_S = 300


def cache_leeren(connection_id: Optional[int] = None) -> None:
    """Nach einem JTL-Update oder Mandantenwechsel den Befund verwerfen."""
    if connection_id is None:
        _CACHE.clear()
    else:
        _CACHE.pop(("objekte", connection_id), None)
        _CACHE.pop(("version", connection_id), None)


def _cached(schluessel, erzeuge):
    eintrag = _CACHE.get(schluessel)
    if eintrag and (time.time() - eintrag[0]) < _HALTBAR_S:
        return eintrag[1]
    wert = erzeuge()
    _CACHE[schluessel] = (time.time(), wert)
    return wert


def _verbindung(connection_id, db):
    from app.models.dataset import DbConnection
    return db.query(DbConnection).filter(DbConnection.id == connection_id).first()


def jtl_version(connection_id: Optional[int], db) -> Optional[str]:
    """JTL-Wawi-Version dieser Datenbank, z.B. "1.8.10.0". None wenn nicht lesbar."""
    if connection_id is None or db is None:
        return None

    def lies():
        from app.services.db_service import query_preview
        conn = _verbindung(connection_id, db)
        if conn is None:
            return None
        try:
            r = query_preview(conn, "SELECT TOP 1 cVersion FROM dbo.tVersion ORDER BY cVersion DESC", limit=1)
            zeilen = r.get("rows") or []
            return str(zeilen[0].get("cVersion")) if zeilen else None
        except Exception:
            return None      # keine JTL-Datenbank oder nicht erreichbar - kein Grund zu scheitern

    return _cached(("version", connection_id), lies)


def fehlende_objekte(connection_id: Optional[int], benoetigt: set, db) -> set:
    """Welche der benoetigten Tabellen/Sichten gibt es in dieser Datenbank nicht?

    Fragt gezielt nach den benoetigten Namen statt den ganzen Katalog zu laden.

    ACHTUNG: `sys.objects` ist rechtegefiltert - ein fehlendes Recht sieht aus wie
    ein fehlendes Objekt. Der Aufrufer sollte die Meldung deshalb als "nicht
    verfuegbar" formulieren, nicht als "existiert nicht".
    """
    if not benoetigt or connection_id is None or db is None:
        return set()

    def lies():
        from app.services.db_service import query_preview
        conn = _verbindung(connection_id, db)
        if conn is None:
            return None
        try:
            r = query_preview(conn, "SELECT name FROM sys.objects WHERE type IN ('U','V')", limit=100000)
            return {str(z.get("name")).lower() for z in (r.get("rows") or [])}
        except Exception:
            return None      # nicht pruefbar -> lieber nichts behaupten

    vorhanden = _cached(("objekte", connection_id), lies)
    if vorhanden is None:
        return set()

    fehlt = set()
    for name in benoetigt:
        kurz = str(name).split(".")[-1].strip().lower()
        if kurz and kurz not in vorhanden:
            fehlt.add(name)
    return fehlt


def pruefe_formular(form, connection_id: Optional[int], db) -> dict:
    """Prueft ein Formular gegen die Datenbank des aktiven Mandanten.

    Gibt zurueck: {version, fehlend[], reiter[], aktionen_gesamt, aktionen_betroffen}.
    `fehlend` leer heisst: alles da (oder nicht pruefbar) - dann nichts anzeigen.
    """
    from app.services.form_doku import _tables_from_sql, _nodes
    from app.models.mapping import Mapping

    schema = form.schema or {}
    leer = {"version": jtl_version(connection_id, db), "fehlend": [], "reiter": [],
            "aktionen_gesamt": 0, "aktionen_betroffen": 0}
    if connection_id is None:
        return leer

    # Tabellen je Action sammeln, damit wir hinterher sagen koennen, WAS ausfaellt.
    je_action = {}
    for a in schema.get("actions") or []:
        mid = a.get("mapping_id")
        if not mid:
            continue
        m = db.query(Mapping).filter(Mapping.id == mid).first()
        if not m:
            continue
        tabellen = set()
        for n in _nodes(m, "sql_nodes"):
            if isinstance(n, dict):
                tabellen |= _tables_from_sql(n.get("sql") or "")
        if tabellen:
            je_action[a.get("id")] = tabellen

    alle = set().union(*je_action.values()) if je_action else set()
    fehlt = fehlende_objekte(connection_id, alle, db)
    if not fehlt:
        return {**leer, "aktionen_gesamt": len(je_action)}

    betroffene_actions = {aid for aid, tab in je_action.items() if tab & fehlt}

    # Welche Reiter haengen daran? Das ist die Information, die der Anwender braucht.
    reiter = []
    for tab in schema.get("result_tabs") or []:
        ids = set(tab.get("action_ids") or [])
        if not ids:
            continue
        betroffen = ids & betroffene_actions
        if betroffen:
            reiter.append({
                "label": tab.get("label") or tab.get("id"),
                "betroffen": len(betroffen),
                "gesamt": len(ids),
                "ganz": len(betroffen) == len(ids),
            })

    return {
        "version": jtl_version(connection_id, db),
        "fehlend": sorted(fehlt),
        "reiter": reiter,
        "aktionen_gesamt": len(je_action),
        "aktionen_betroffen": len(betroffene_actions),
    }


# ── Nachtraegliche Uebersetzung ──────────────────────────────────────────────

_OBJEKT = re.compile(r'Ung.ltiger Objektname\s+["\']([^"\']+)["\']|Invalid object name\s+["\']([^"\']+)["\']', re.I)
_SPALTE = re.compile(r'Ung.ltiger Spaltenname\s+["\']([^"\']+)["\']|Invalid column name\s+["\']([^"\']+)["\']', re.I)


# Stabiler Teilsatz der uebersetzten Meldung. Wird gebraucht, weil der Fehler die
# Uebersetzung in mapping_service schon durchlaufen hat, wenn ihn spaetere Aufrufer
# (Warnregeln) zu sehen bekommen - dort greift kein SQL-Server-Muster mehr.
_UEBERSETZT = "gibt es in der Datenbank dieses Mandanten nicht"


def ist_versionsproblem(fehlertext: str) -> bool:
    """Liegt es an einem fehlenden Objekt/Feld - also an der JTL-Version?

    Erkennt den SQL-Server-Rohtext UND die bereits uebersetzte Fassung.
    """
    t = fehlertext or ""
    return bool(_OBJEKT.search(t) or _SPALTE.search(t) or _UEBERSETZT in t)


def erklaere_sql_fehler(fehlertext: str, version: Optional[str] = None) -> Optional[str]:
    """Macht aus einem SQL-Server-Fehler eine Aussage, mit der ein Anwender etwas anfangen kann.

    None, wenn es kein Schema-Fehler ist - dann bleibt die Originalmeldung stehen.
    Fehlende Spalten kommen nur hier an: sie lassen sich vorab nicht zuverlaessig
    aus dem SQL ablesen.
    """
    if not fehlertext:
        return None
    if _UEBERSETZT in fehlertext:
        return fehlertext          # schon uebersetzt (mapping_service) - so lassen
    # BEWUSST EINZEILIG. Diese Meldung erscheint in JEDER betroffenen Kachel - beim
    # Lager-Cockpit 24 Mal. Ein erklaerender Absatz, zwei Dutzend Mal wiederholt,
    # ist genauso unbrauchbar wie der ODBC-Rohtext davor, nur laenger. Das Warum und
    # das "loest sich nach dem Update von selbst" stehen einmal oben im Banner.
    v = f", JTL {version}" if version else ""
    m = _OBJEKT.search(fehlertext)
    if m:
        return f"„{m.group(1) or m.group(2)}“ gibt es in der Datenbank dieses Mandanten nicht{v}."
    m = _SPALTE.search(fehlertext)
    if m:
        return f"Das Feld „{m.group(1) or m.group(2)}“ gibt es in der Datenbank dieses Mandanten nicht{v}."
    return None
