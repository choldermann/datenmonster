"""Mapping-Baukasten: Kette rechnen (Zähler je Stein, Vorschau) und als Mapping speichern."""
from __future__ import annotations

import logging
import time
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.orm.attributes import flag_modified

from .uebersetzer import BaukastenFehler, Schema, uebersetzen, vorschau_begrenzen

logger = logging.getLogger(__name__)

VORSCHAU_ZEILEN = 50
ZAEHL_BUDGET_S = 25          # danach keine weiteren Zähler mehr (große Tabellen)


def verbindung(db, connection_id: int, user):
    """Verbindung samt Schema; prüft, ob der Benutzer sie nutzen darf."""
    from app.core.zugriff import lade_verbindung
    from app.services.schema_cache_service import get_cached_schema, rebuild_cache
    conn = lade_verbindung(connection_id, user, db)        # 404/403 wie überall (app/core/zugriff.py)
    schema_json = get_cached_schema(conn)
    if not schema_json:
        rebuild_cache(connection_id, db)          # einmalig: Tabellen und Spalten der Datenbank lesen
        db.refresh(conn)
        schema_json = get_cached_schema(conn) or {}
    return conn, Schema(schema_json)


def tabellen(db, connection_id: int, user) -> list[dict]:
    conn, schema = verbindung(db, connection_id, user)
    return [{"name": t, "spalten": [{"name": s.name, "typ": s.typ} for s in sp]}
            for t, sp in sorted(schema.tabellen.items(), key=lambda kv: kv[0].lower())]


def verknuepfung(db, connection_id: int, user, von: str, zu: str) -> dict | None:
    """Vorschlag für „Dazuholen … über …“ aus den Schlüsseln (wie der Schema-Katalog)."""
    from app.services.schema_cache_service import beziehungen_ableiten, get_cached_schema
    conn, _schema = verbindung(db, connection_id, user)
    sj = get_cached_schema(conn) or {}
    for b in beziehungen_ableiten(sj, von_tabellen=[von, zu], grenze=400):
        if b["from_table"] == von and b["to_table"] == zu:
            return {"links": b["from_col"], "rechts": b["to_col"], "quelle": b["quelle"]}
        if b["from_table"] == zu and b["to_table"] == von:
            return {"links": b["to_col"], "rechts": b["from_col"], "quelle": b["quelle"]}
    return None


def rechnen(db, user, connection_id: int, kette: list, zeige: str | None = None,
            von: str | None = None, bis: str | None = None) -> dict:
    """Zähler je Stein und Vorschau an einer Stelle. Liest nur."""
    from app.services.sql_helpers import _get_sql_engine
    conn, schema = verbindung(db, connection_id, user)
    erg = uebersetzen(kette, schema, conn.db_type, literal=False)
    bis = bis or date.today().isoformat()
    von = von or (date.today() - timedelta(days=365)).isoformat()
    if conn.db_type == "mssql":
        von, bis = von.replace("-", ""), bis.replace("-", "")
    params = {**erg.params, "von": von, "bis": bis}

    def gebunden(sql: str) -> dict:
        return {k: v for k, v in params.items() if f":{k}" in sql}

    eng = _get_sql_engine(connection_id)
    zaehler, fehler = {}, {}
    start = time.monotonic()
    with eng.connect() as con:
        for bid, sql in erg.zaehl_sql.items():
            if time.monotonic() - start > ZAEHL_BUDGET_S:
                fehler[bid] = "übersprungen (Zeitbudget)"
                continue
            try:
                zaehler[bid] = int(con.execute(text(sql), gebunden(sql)).scalar() or 0)
            except Exception as e:
                fehler[bid] = str(e).split("\n")[0][:240]
                logger.info("Baukasten-Zähler %s: %s", bid, fehler[bid])
        ziel = zeige if zeige in erg.vorschau_sql else next(reversed(erg.vorschau_sql))
        vsql = vorschau_begrenzen(erg.vorschau_sql[ziel], VORSCHAU_ZEILEN, conn.db_type)
        try:
            res = con.execute(text(vsql), gebunden(vsql))
            spalten = list(res.keys())
            zeilen = [dict(zip(spalten, r)) for r in res.fetchmany(VORSCHAU_ZEILEN)]
            vorschau = {"block": ziel, "spalten": spalten, "zeilen": zeilen}
        except Exception as e:
            vorschau = {"block": ziel, "spalten": [], "zeilen": [], "fehler": str(e).split("\n")[0][:300]}
    gespeichert = uebersetzen(kette, schema, conn.db_type, literal=True)
    return {
        "zaehler": zaehler, "fehler": fehler, "vorschau": vorschau, "warnungen": warnungen(kette, zaehler),
        "spalten_je_block": erg.spalten_je_block,
        "spalten": [{"name": s.name, "typ": s.typ} for s in erg.spalten],
        "sql": gespeichert.sql, "nutzt_zeitraum": erg.nutzt_zeitraum,
        "zeitraum": {"von": von, "bis": bis},
    }


def warnungen(kette: list, zaehler: dict) -> dict:
    """Typische Einsteiger-Fallen an den Zählern erkennen.

    Hauptfall: nach „Dazuholen“ sind es MEHR Zeilen als vorher – zu einer Zeile passen mehrere Einträge der
    dazugeholten Tabelle (z. B. Rechnungs- und Lieferadresse je Kunde). Jede Summe danach wäre zu hoch.
    """
    aus = {}
    for i, b in enumerate(kette):
        if b.get("type") != "tabelle":
            continue
        vorher = zaehler.get(f":{i}:kopf")
        for j, x in enumerate(b.get("inner") or []):
            bid = f"{i}:{j}"
            n = zaehler.get(bid)
            if x.get("type") == "join" and vorher is not None and n is not None:
                if n > vorher:
                    aus[bid] = (f"Aus {vorher:,} werden {n:,} Zeilen: zu einer Zeile passen mehrere Einträge aus "
                                f"„{x.get('table')}“. Summen danach wären zu hoch – im Winkel „Dazuholen“ mit "
                                f"„Nur wenn“ auf genau einen Eintrag eingrenzen.").replace(",", ".")
                elif n == 0 and vorher > 0:
                    aus[bid] = f"Nach dem Dazuholen bleibt keine Zeile übrig – passt die Verknüpfung über „{x.get('links')}“?"
            if n is not None:
                vorher = n
    for i, b in enumerate(kette):
        if b.get("type") == "filter" and zaehler.get(f":{i}") == 0 and (zaehler.get(f":{i-1}") or 0) > 0:
            aus[f":{i}"] = "Diese Bedingung lässt nichts übrig."
    return aus


_TYP = {"zahl": "geld", "datum": "datum", "text": "text"}


def speichern(db, user, project_id, connection_id: int, name: str, kette: list, mapping_id: int | None = None):
    """Kette → normales Mapping (SQL-Knoten „transform“). Die Kette bleibt am Knoten für den Rückweg in den Baukasten."""
    from app.models.mapping import Mapping
    from app.services.query_builder.erzeugen import mapping_bauen
    name = (name or "").strip()
    if not name:
        raise BaukastenFehler("Bitte einen Namen für die Auswertung angeben.")
    conn, schema = verbindung(db, connection_id, user)
    erg = uebersetzen(kette, schema, conn.db_type, literal=True)
    vorhandenes = db.get(Mapping, mapping_id) if mapping_id else None
    if vorhandenes is not None and vorhandenes.project_id != project_id:
        raise BaukastenFehler("Das Mapping gehört zu einem anderen Projekt.")
    m = mapping_bauen(db, name, project_id, connection_id,
                      {"sql": erg.sql, "spalten": [{"name": s.name, "typ": _TYP[s.typ]} for s in erg.spalten]},
                      vorhandenes)
    # Kette und erzeugtes SQL am Knoten merken: weicht das SQL später ab (in der Profi-Ansicht geändert),
    # erkennt der Baukasten das und zeigt den Teil als Profi-Stein statt ihn zu überschreiben.
    knoten = dict(m.sql_nodes[0])
    knoten["baukasten"] = {"kette": kette, "sql": erg.sql, "version": 1}
    m.sql_nodes = [knoten]
    flag_modified(m, "sql_nodes")
    db.commit()
    db.refresh(m)
    return m
