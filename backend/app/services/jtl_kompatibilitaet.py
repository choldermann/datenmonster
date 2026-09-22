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

Drei Stufen, weil sie verschiedene Faelle erwischen:
  * `pruefe_formular()` - VORHER. Liest die Tabellen/Sichten aus den Mappings und
    fragt die Datenbank, welche davon fehlen. Faengt den Lager-Fall als Ganzes ab.
  * `_trockenlauf()` - VORHER, eine Stufe genauer. Laesst die Datenbank die Abfrage
    UEBERSETZEN, ohne sie auszufuehren (`SET NOEXEC ON`). Damit fallen auch fehlende
    SPALTEN auf, und zwar ohne dass wir SQL selbst zerlegen muessten: Aliase,
    Unterabfragen und CTEs loest der Server ohnehin besser auf als jede Regex.
    Anlass war JTL-Wawi 2.0: `fWertNettoGesamtFixiert` ist dort weg, die Tabelle
    gibt es aber weiter - die Objektpruefung sah alles gruen, der Reiter lief in
    einen Fehler.
  * `erklaere_sql_fehler()` - NACHHER. Uebersetzt „Ungültiger Objektname/Spaltenname"
    in Klartext, fuer alles, was die beiden Vorab-Stufen nicht sehen konnten.
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
        # Alles, was an dieser Verbindung haengt - auch die Trockenlauf-Befunde,
        # deren Schluessel die Abfrage mitfuehrt.
        for k in [k for k in _CACHE if isinstance(k, tuple) and len(k) > 1 and k[1] == connection_id]:
            _CACHE.pop(k, None)


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

    conn = _verbindung(connection_id, db)
    eigene_db = (getattr(conn, "database", "") or "").strip().lower()

    fehlt = set()
    for name in benoetigt:
        teile = [t.strip().strip("[]") for t in str(name).split(".")]
        # Dreiteilig = Verweis in eine ANDERE Datenbank (eazybusiness.Verkauf.tAuftrag,
        # abgesetzt von einer Hilfs-DB aus). sys.objects kennt nur die eigene; ein
        # "fehlt" waere hier schlicht falsch. Nur pruefen, wenn es die eigene ist.
        if len(teile) == 3 and teile[0].lower() != eigene_db:
            continue
        kurz = teile[-1].lower()
        if kurz and kurz not in vorhanden:
            fehlt.add(name)
    return fehlt


_PARAM = re.compile(r":([a-zA-Z_][a-zA-Z0-9_]*)")


def _trockenlauf(connection_id: Optional[int], sql: str) -> Optional[tuple]:
    """Laesst die Datenbank die Abfrage uebersetzen, ohne sie auszufuehren.

    Rueckgabe: ("spalte"|"objekt", Name) beim ersten Schema-Fehler, sonst None.

    Warum ueber die Datenbank und nicht ueber einen eigenen Parser: welche Spalte
    zu welcher Tabelle gehoert, entscheidet der Alias - ueber Unterabfragen, CTEs
    und JOINs hinweg. Eine Regex raet das bestenfalls; ein Fehlalarm ist hier aber
    teurer als gar keine Pruefung (siehe DHL-Cockpit, ece84ad).

    `SET NOEXEC ON` laesst den Server den Batch uebersetzen und dann verwerfen.
    Scheitert die Uebersetzung, lief NICHTS davon - auch das SET nicht, die
    Verbindung bleibt also unveraendert. Gelingt sie, schaltet das SET am Ende
    wieder ab (SET-Anweisungen laufen auch unter NOEXEC).

    Parameter werden durch NULL ersetzt statt typisiert deklariert: fuer die
    Uebersetzung reicht das, und geratene Typen wuerden Fehler melden, die im
    echten Lauf keine sind.
    """
    if connection_id is None or not (sql or "").strip():
        return None

    def pruefe():
        from app.core.database import SessionLocal
        from app.models.dataset import DbConnection
        from app.services.sql_helpers import _get_sql_engine
        from sqlalchemy import text

        sitzung = SessionLocal()
        try:
            conn = sitzung.query(DbConnection).filter(DbConnection.id == connection_id).first()
            if conn is None or conn.db_type != "mssql":
                return None          # nur SQL Server kennt NOEXEC
        finally:
            sitzung.close()

        rumpf = _PARAM.sub("NULL", sql).strip().rstrip(";")
        batch = "SET NOEXEC ON;\n" + rumpf + "\n;SET NOEXEC OFF;"
        try:
            engine = _get_sql_engine(connection_id)
            with engine.connect() as c:
                c.exec_driver_sql("SET NOEXEC OFF")   # falls eine Verbindung aus dem Pool haengt
                c.execute(text(batch))
            return None
        except Exception as ex:
            fehler = str(ex)
            m = _SPALTE.search(fehler)
            if m:
                return ("spalte", m.group(1) or m.group(2))
            m = _OBJEKT.search(fehler)
            if m:
                return ("objekt", m.group(1) or m.group(2))
            # Alles andere (Syntax, Rechte, Timeout) ist KEIN Versionsbefund.
            # Lieber schweigen als etwas behaupten, was der echte Lauf widerlegt.
            return None

    return _cached(("sql", connection_id, hash(sql)), pruefe)


def pruefe_formular(form, connection_id: Optional[int], db) -> dict:
    """Prueft ein Formular gegen die Datenbank des aktiven Mandanten.

    Gibt zurueck: {version, fehlend[], felder[], reiter[], aktionen_gesamt,
    aktionen_betroffen}. `fehlend` sind fehlende Tabellen/Sichten, `felder` fehlende
    Spalten aus dem Trockenlauf. Beide leer heisst: alles da (oder nicht pruefbar)
    - dann nichts anzeigen.
    """
    from app.services.form_doku import _tables_from_sql, _nodes
    from app.models.mapping import Mapping

    schema = form.schema or {}
    leer = {"version": jtl_version(connection_id, db), "fehlend": [], "felder": [], "reiter": [],
            "aktionen_gesamt": 0, "aktionen_betroffen": 0}
    if connection_id is None:
        return leer

    # Welche Verbindungen tauscht der Mandantenwechsel ueberhaupt aus? Ein SQL-Knoten
    # auf einer Hilfsdatenbank (DXBackup, folgt_mandant=false) laeuft weiterhin dort -
    # seine Tabellen gegen die WaWi des Mandanten zu pruefen, meldet Unsinn: das
    # DHL-Cockpit galt so als "passt nicht zur JTL-Version", obwohl es laeuft.
    from app.services.mandant_service import austauschbare_ids
    austauschbar = austauschbare_ids(getattr(form, "project_id", None), db)

    # Tabellen je Action UND je tatsaechlich verwendeter Verbindung.
    je_action = {}
    sql_je_action = {}
    for a in schema.get("actions") or []:
        mid = a.get("mapping_id")
        if not mid:
            continue
        m = db.query(Mapping).filter(Mapping.id == mid).first()
        if not m:
            continue
        paare = set()
        abfragen = []
        for n in _nodes(m, "sql_nodes"):
            if not isinstance(n, dict):
                continue
            quelle = n.get("connection_id")
            ziel = connection_id if quelle in austauschbar else quelle
            sql = n.get("sql") or ""
            for t in _tables_from_sql(sql):
                paare.add((ziel, t))
            if sql.strip():
                abfragen.append((ziel, sql))
        if paare:
            je_action[a.get("id")] = paare
        if abfragen:
            sql_je_action[a.get("id")] = abfragen

    je_verbindung = {}
    for paare in je_action.values():
        for cid, t in paare:
            je_verbindung.setdefault(cid, set()).add(t)

    fehlt = set()
    for cid, tabellen in je_verbindung.items():
        fehlt |= {(cid, t) for t in fehlende_objekte(cid, tabellen, db)}

    betroffene_actions = {aid for aid, paare in je_action.items() if paare & fehlt}

    # Zweite Stufe: Abfragen uebersetzen lassen. Nur fuer Actions, die nicht schon
    # an einem fehlenden Objekt haengen - dort waere der Befund nur eine Wiederholung.
    fehlende_felder = set()
    for aid, abfragen in sql_je_action.items():
        if aid in betroffene_actions:
            continue
        for cid, sql in abfragen:
            befund = _trockenlauf(cid, sql)
            if not befund:
                continue
            art, name = befund
            if art == "spalte":
                fehlende_felder.add(name)
            else:
                fehlt.add((cid, name))
            betroffene_actions.add(aid)
            break            # ein Befund je Auswertung genuegt

    if not fehlt and not fehlende_felder:
        return {**leer, "aktionen_gesamt": len(je_action)}

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
        "fehlend": sorted({t for _cid, t in fehlt}),
        "felder": sorted(fehlende_felder),
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
