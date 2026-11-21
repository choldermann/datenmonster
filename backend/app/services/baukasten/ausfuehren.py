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


def _wert(x):
    """Vorschauwert JSON-fähig machen (Binärspalten wie bRowversion, Decimal, Datum)."""
    from decimal import Decimal
    from datetime import date as _d, datetime as _dt, time as _t
    if isinstance(x, (bytes, bytearray, memoryview)):
        return "0x" + bytes(x).hex()[:32]
    if isinstance(x, Decimal):
        return float(x)
    if isinstance(x, (_dt, _d, _t)):
        return x.isoformat()
    return x


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
    # von = eine oder mehrere (kommagetrennt) schon vorhandene Tabellen – Haupttabelle zuerst
    for v in [t.strip() for t in von.split(",") if t.strip()]:
        for b in beziehungen_ableiten(sj, von_tabellen=[v, zu], grenze=400):
            if b["from_table"] == v and b["to_table"] == zu:
                return {"links": b["from_col"], "rechts": b["to_col"], "quelle": b["quelle"], "von": v}
            if b["from_table"] == zu and b["to_table"] == v:
                return {"links": b["to_col"], "rechts": b["from_col"], "quelle": b["quelle"], "von": v}
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
            zeilen = [{k: _wert(x) for k, x in zip(spalten, r)} for r in res.fetchmany(VORSCHAU_ZEILEN)]
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
            if x.get("type") == "join" and x.get("ohne"):
                if n == 0 and vorher:
                    aus[bid] = "Zu jeder Zeile gibt es einen Treffer – „nur ohne Treffer“ lässt deshalb nichts übrig."
            elif x.get("type") == "join" and x.get("alle") and any(f.get("type") == "filter" and f.get("col") for f in x.get("inner") or []):
                aus[bid] = ("„Auch ohne Treffer behalten“ ist an: „Nur wenn“ in diesem Winkel filtert dann keine Zeilen weg, "
                            "sondern lässt nur die dazugeholten Spalten leer. Soll nur gezählt werden, was passt – Haken herausnehmen.")
            elif x.get("type") == "join" and vorher is not None and n is not None:
                if n > vorher:
                    aus[bid] = (f"Aus {vorher:,} werden {n:,} Zeilen: zu einer Zeile passen mehrere Einträge aus "
                                f"„{x.get('table')}“. Summen über Spalten der bisherigen Tabelle wären danach zu hoch. "
                                f"Gewollt (z. B. Positionen je Rechnung)? Dann ist alles gut – sonst im Winkel „Dazuholen“ "
                                f"mit „Nur wenn“ auf genau einen Eintrag eingrenzen.").replace(",", ".")
                elif n == 0 and vorher > 0:
                    bed = [f"{f.get('col')} {f.get('op')} {f.get('val') or ''}".strip() for f in x.get("inner") or []
                           if f.get("type") == "filter" and f.get("col")]
                    aus[bid] = (f"Nach dem Dazuholen bleibt keine Zeile übrig – passt die Verknüpfung über „{x.get('links')}“"
                                + (f" oder der Wert in „Nur wenn {'; '.join(bed)}“?" if bed else "?"))
            elif x.get("type") == "filter" and n == 0 and vorher:
                aus[bid] = (f"„Nur wenn {x.get('col')} {x.get('op')} {x.get('val') or ''}“ lässt keine Zeile übrig – "
                            f"passt der Wert so, wie er in der Spalte steht?")
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


# ── Ausgabe „… im Cockpit“ ─────────────────────────────────────────────────
ZIELE = {"Tabelle im Cockpit": "table", "Balken im Cockpit": "bar", "Linie im Cockpit": "line",
         "Kachel im Cockpit": "kpi"}
NUR_SPEICHERN = "Nur als Auswertung speichern"
EIGENER_REITER = "Eigene Auswertungen"


def _widget_config(art: str, ausgabe: dict, spalten: list) -> dict:
    """Spalten fürs Diagramm/Kachel: aus dem Stein, sonst sinnvoll vorbelegt (erste Text-/Datumsspalte als
    Achse, Zahlenspalten als Werte)."""
    namen = [s.name for s in spalten]
    zahlen = [s.name for s in spalten if s.typ == "zahl"]
    achse = next((s.name for s in spalten if s.typ in ("text", "datum")), namen[0] if namen else "")
    if art == "table":
        return {"width": 12}
    if art in ("bar", "line"):
        x = ausgabe.get("x") if ausgabe.get("x") in namen else achse
        y = [c for c in (ausgabe.get("y") or []) if c in namen and c != x] or [c for c in zahlen if c != x][:4]
        if not y:
            raise BaukastenFehler("Für ein Diagramm braucht das Ergebnis mindestens eine Zahlenspalte.")
        cfg = {"width": 12, "x_column": x, "y_columns": y}
        if art == "line":
            cfg["curved"] = True
        return cfg
    wert = ausgabe.get("wert") if ausgabe.get("wert") in zahlen else (zahlen[0] if zahlen else None)
    if not wert:
        raise BaukastenFehler("Für eine Kachel braucht das Ergebnis eine Zahlenspalte.")
    return {"width": 3, "column": wert, "aggregation": "sum", "decimals": 2}


def ins_cockpit(db, user, project_id, mapping, kette: list, spalten: list, nutzt_zeitraum: bool) -> dict | None:
    """Widget für das Mapping in ein Cockpit (Formular) stellen – vorhandenes aktualisieren statt doppeln.

    Ausgabe-Stein: {"target": "Balken im Cockpit", "cockpit": <form_id>|"neu", "cockpit_name": "…",
                    "reiter": "<tab-id>"|None, "x": "…", "y": [...], "wert": "…"}
    """
    from app.api.forms import unique_slug
    from app.models.form import Form
    ausgabe = next((b for b in reversed(kette) if b.get("type") == "ausgabe"), None)
    art = ZIELE.get((ausgabe or {}).get("target") or "")
    if not ausgabe or not art or not ausgabe.get("cockpit"):
        return None
    cfg = _widget_config(art, ausgabe, spalten)

    if ausgabe["cockpit"] == "neu":
        name = (ausgabe.get("cockpit_name") or "").strip() or mapping.name
        form = Form(name=name, project_id=project_id, version=1, slug=unique_slug(db, name), published=False,
                    schema={"fields": [], "layout": [], "actions": [], "widgets": []},
                    portal_config={"icon": "🧱"}, created_by=getattr(user, "id", None))
        db.add(form)
        db.flush()
    else:
        try:
            form = db.get(Form, int(ausgabe["cockpit"]))
        except (TypeError, ValueError):
            form = None
        if form is None or form.project_id != project_id:
            raise BaukastenFehler("Das gewählte Cockpit gibt es in diesem Projekt nicht (mehr).")

    schema = dict(form.schema or {})
    for k in ("fields", "layout", "actions", "widgets"):
        schema[k] = list(schema.get(k) or [])
    # Zeitraum des Cockpits: braucht die Kette „im Zeitraum“, bekommt ein Cockpit ohne Zeitraumfeld eins
    if nutzt_zeitraum and not any(f.get("type") == "daterange" for f in schema["fields"]):
        schema["fields"].insert(0, {"id": "f_zeitraum", "type": "daterange", "row": 0, "colSpan": 12,
                                    "label": "Zeitraum", "name": "zeitraum", "action_ids": [],
                                    "config": {"param_from": "von", "param_to": "bis", "default": "this_year",
                                               "auto_run": True}})
    aktion = next((a for a in schema["actions"] if a.get("type") == "run_mapping" and a.get("mapping_id") == mapping.id), None)
    if aktion is None:
        aktion = {"id": f"act_bk_{mapping.id}", "type": "run_mapping", "mapping_id": mapping.id,
                  "pipeline_id": None, "label": mapping.name}
        schema["actions"].append(aktion)
    widget = next((w for w in schema["widgets"] if w.get("action_id") == aktion["id"] and w.get("bk")), None)
    if widget is None:
        widget = {"id": f"w_bk_{mapping.id}", "action_id": aktion["id"], "bk": True}
        schema["widgets"].append(widget)
    # Breite bleibt, wenn sie im Cockpit-Editor angepasst wurde und die Art gleich bleibt; sonst frisch
    alt = widget.get("config") or {}
    if widget.get("type") == art and alt.get("width"):
        cfg["width"] = alt["width"]
    widget.update(type=art, label=mapping.name, config=cfg)

    # Reiter: hat das Cockpit welche, kommt die Auswertung in den gewählten oder in „Eigene Auswertungen“
    tabs = list(schema.get("result_tabs") or [])
    if tabs:
        tabs = [dict(t, action_ids=[a for a in (t.get("action_ids") or []) if a != aktion["id"]]) for t in tabs]
        ziel = next((t for t in tabs if t.get("id") == ausgabe.get("reiter")), None)
        if ziel is None:
            ziel = next((t for t in tabs if t.get("label") == EIGENER_REITER), None)
        if ziel is None:
            ziel = {"id": "tab_bk_eigene", "label": EIGENER_REITER, "action_ids": []}
            tabs.append(ziel)
        ziel["action_ids"].append(aktion["id"])
        # selbst angelegten Reiter wieder entfernen, wenn nichts mehr darin steht
        tabs = [t for t in tabs if t.get("id") != "tab_bk_eigene" or t["action_ids"]]
        schema["result_tabs"] = tabs
    form.schema = schema
    flag_modified(form, "schema")
    db.commit()
    return {"form_id": form.id, "name": form.name, "reiter": (ziel["label"] if tabs else None), "art": art}
