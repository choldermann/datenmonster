"""Aus einer Abfrage-Definition ein Mapping und Bausteine machen.

Kein neues Format: das Ergebnis ist ein ganz normales Mapping mit SQL-Knoten und
ein Tabellen- plus Kachel-Widget in einem Sammelformular „Eigene Auswertungen".
Damit erscheint die Abfrage automatisch als Quelle im Report-Baukasten und erbt
Zustellplan, PDF, Portal und Drilldown.
"""
import logging
import re

from sqlalchemy.orm.attributes import flag_modified

from app.models.form import Form
from app.models.mapping import Mapping
from . import katalog, sql_bauer

logger = logging.getLogger(__name__)

SAMMELFORMULAR = "Eigene Auswertungen"

# Der SQL-Knoten trägt eine Verbindung, aber sie ist nur die Vorbelegung:
# beim Lauf ersetzt mandant_service.verbindung_ersetzen() sie durch die des
# aktiven Mandanten. Ohne diesen Umstand wäre eine Abfrage an einen Betrieb
# gefesselt.
_TYP_ZU_ZIEL = {"zahl": "int", "geld": "float", "datum": "string", "text": "string"}


def _schluessel(name: str) -> str:
    """Aus einem Namen eine ID-taugliche Form machen."""
    s = (name or "abfrage").lower()
    s = s.translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}))
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s[:40] or "abfrage"


def _mapping_bauen(db, name: str, project_id, connection_id: int,
                   gebaut: dict, vorhandenes: Mapping | None = None) -> Mapping:
    """Legt das Mapping an oder aktualisiert es."""
    spalten = gebaut["spalten"]

    sql_node = {
        "id": "sql1", "x": 120, "y": 40, "width": 420, "height": 280,
        "connection_id": connection_id,
        "sql": gebaut["sql"],
        # Ohne mode "transform" gilt der Knoten nicht als Datenquelle.
        "mode": "transform",
        "output_field": "sql_1",
        "output_fields": [s["name"] for s in spalten],
    }

    # Eine Spalte ohne Eintrag in targets.fields erreicht die Oberfläche NIE.
    felder = [{
        "source_field": s["name"],
        "target_field": s["name"],
        "target_type": _TYP_ZU_ZIEL.get(s.get("typ"), "string"),
        "source_dataset_id": "__sql__sql1",
    } for s in spalten]

    targets = [{
        "id": "t1", "name": name, "target_type": "dataset",
        "target_connection_id": None, "target_table": "",
        "target_write_mode": "replace", "target_options": {},
        "fields": felder,
    }]

    m = vorhandenes or Mapping(name=name, project_id=project_id)
    m.name = name
    m.project_id = project_id
    m.sql_nodes = [sql_node]
    m.targets = targets
    for leer in ("canvas_nodes", "joins", "fields", "transform_nodes", "constant_nodes",
                 "agg_nodes", "rest_nodes", "lookup_nodes", "calc_nodes", "switch_nodes",
                 "sort_nodes", "python_nodes", "ai_nodes", "expr_nodes", "quality_nodes",
                 "param_nodes"):
        if getattr(m, leer, None) is None:
            setattr(m, leer, [])
    if vorhandenes is None:
        db.add(m)
    else:
        flag_modified(m, "sql_nodes")
        flag_modified(m, "targets")
    return m


def _sammelformular(db, project_id) -> Form:
    """Das Formular, in dem die eigenen Abfragen als Bausteine liegen.

    Bewusst ein normales Formular ohne `report_builder` – so bleibt es im
    Report-Baukasten eine gültige Quelle neben den Cockpits.
    """
    f = (db.query(Form)
           .filter(Form.name == SAMMELFORMULAR, Form.project_id == project_id)
           .first())
    if f:
        return f
    f = Form(name=SAMMELFORMULAR, project_id=project_id, schema={
        "fields": [{
            "id": "f_zeitraum", "type": "daterange", "row": 0, "colSpan": 12,
            "label": "Zeitraum", "name": "zeitraum", "action_ids": [],
            "config": {"param_from": "von", "param_to": "bis",
                       "default": "months_12", "auto_run": False},
        }],
        "layout": [], "actions": [], "widgets": [], "result_tabs": [],
        "show_ai_assistant": False,
    })
    db.add(f)
    db.flush()
    return f


def speichern(db, name: str, definition: dict, project_id, connection_id: int,
              vorhandene=None) -> dict:
    """Legt Mapping und Bausteine an (oder aktualisiert sie).

    `vorhandene` ist ein AdHocQuery-Datensatz beim Nachbearbeiten.
    """
    name = (name or "").strip()
    if not name:
        raise sql_bauer.AbfrageFehler("Bitte einen Namen für die Auswertung angeben.")

    # Im Report zählt nicht die Vorschau-Obergrenze, sondern die volle Liste.
    definition = dict(definition or {})
    definition.pop("limit", None)
    # literal=True: der Report gibt später nur :von/:bis mit. Ein verbliebenes
    # :p0 bliebe ungebunden und die Auswertung wäre stumm leer.
    koernung = definition.get("koernung") or "kunde"
    gebaut = sql_bauer.bauen(definition, literal=True)

    alt_mapping = None
    if vorhandene and vorhandene.mapping_id:
        alt_mapping = db.query(Mapping).filter(Mapping.id == vorhandene.mapping_id).first()
    m = _mapping_bauen(db, name, project_id, connection_id, gebaut, alt_mapping)
    db.flush()

    f = _sammelformular(db, project_id)
    schema = dict(f.schema or {})
    schema.setdefault("actions", [])
    schema.setdefault("widgets", [])
    schema.setdefault("result_tabs", [])

    basis = _schluessel(name)
    aid = f"act_q_{basis}"
    w_tab, w_kpi = f"w_q_{basis}_tab", f"w_q_{basis}_kpi"
    # Beim Nachbearbeiten die alten Bausteine ersetzen statt danebenzulegen.
    alte = set((vorhandene.widget_ids if vorhandene else []) or []) | {w_tab, w_kpi}
    schema["widgets"] = [w for w in schema["widgets"] if w.get("id") not in alte]
    schema["actions"] = [a for a in schema["actions"] if a.get("id") != aid]

    schema["actions"].append({
        "id": aid, "type": "run_mapping", "mapping_id": m.id,
        "pipeline_id": None, "label": name,
    })

    schluessel_spalte = next((s["name"] for s in gebaut["spalten"] if s.get("schluessel")), None)
    schema["widgets"].append({
        "id": w_kpi, "type": "kpi", "label": f"{name} – Treffer",
        "action_id": aid,
        "config": {"width": 3, "column": schluessel_spalte, "aggregation": "count",
                   "decimals": 0,
                   "hint": "Zahl der Zeilen, die die Bedingungen erfüllen."},
    })
    schema["widgets"].append({
        "id": w_tab, "type": "table", "label": name, "action_id": aid,
        "config": {"width": 12, "full_rows": True,
                   "hidden_columns": [schluessel_spalte] if schluessel_spalte else []},
    })

    # ── Zeitverlauf ──────────────────────────────────────────────────────────
    # Dieselbe Abfrage, nur „je Monat" verdichtet. Bei der Körnung „Kunde" gibt es
    # ihn nicht: ein Kunde hat kein Datum, und „wie viele Kunden hatten in Monat X
    # keine Rechnung" wäre eine rollierende Neuberechnung – eine andere Frage.
    verlauf_gruppe = next((g["key"] for g in (katalog.KOERNUNGEN[koernung].get("gruppierungen") or [])
                           if g.get("verlauf")), None)
    verlauf_mapping_id = None
    w_verlauf = f"w_q_{basis}_verlauf"
    aid_verlauf = f"act_q_{basis}_verlauf"
    schema["widgets"] = [w for w in schema["widgets"] if w.get("id") != w_verlauf]
    schema["actions"] = [a for a in schema["actions"] if a.get("id") != aid_verlauf]

    if verlauf_gruppe:
        v_def = dict(definition)
        v_def["gruppierung"] = verlauf_gruppe
        # Ohne Kennzahl gäbe es nichts zu zeichnen; die erste des Katalogs ist
        # immer eine Zählung und damit die sinnvollste Vorgabe.
        if not v_def.get("kennzahlen"):
            v_def["kennzahlen"] = [katalog.KOERNUNGEN[koernung]["kennzahlen"][0]["key"]]
        v_def["kennzahlfilter"] = definition.get("kennzahlfilter") or {}
        v_def["sortierung"] = {"key": "Monat", "richtung": "asc"}
        try:
            v_gebaut = sql_bauer.bauen(v_def, literal=True)
        except sql_bauer.AbfrageFehler:
            v_gebaut = None
        if v_gebaut:
            alt_v = None
            if vorhandene and (vorhandene.widget_ids or []) and vorhandene.verlauf_mapping_id:
                alt_v = db.query(Mapping).filter(
                    Mapping.id == vorhandene.verlauf_mapping_id).first()
            mv = _mapping_bauen(db, f"{name} – Verlauf", project_id, connection_id,
                                v_gebaut, alt_v)
            db.flush()
            verlauf_mapping_id = mv.id
            schema["actions"].append({
                "id": aid_verlauf, "type": "run_mapping", "mapping_id": mv.id,
                "pipeline_id": None, "label": f"{name} – Verlauf",
            })
            wert_spalte = next((s["name"] for s in v_gebaut["spalten"]
                                if s["name"] != "Monat"), None)
            schema["widgets"].append({
                "id": w_verlauf, "type": "line", "label": f"{name} – Verlauf",
                "action_id": aid_verlauf,
                "config": {"width": 12, "x_column": "Monat", "curved": True,
                           "y_columns": [wert_spalte] if wert_spalte else []},
            })

    tab = next((t for t in schema["result_tabs"] if t.get("id") == "tab_eigene"), None)
    if not tab:
        tab = {"id": "tab_eigene", "label": SAMMELFORMULAR, "action_ids": []}
        schema["result_tabs"].append(tab)
    for a in (aid, aid_verlauf):
        if any(x["id"] == a for x in schema["actions"]) and a not in tab["action_ids"]:
            tab["action_ids"].append(a)

    f.schema = schema
    flag_modified(f, "schema")

    widgets = [w_kpi, w_tab]
    if any(w["id"] == w_verlauf for w in schema["widgets"]):
        widgets.append(w_verlauf)
    return {"mapping": m, "form": f, "action_id": aid,
            "verlauf_mapping_id": verlauf_mapping_id,
            "widget_ids": widgets, "spalten": gebaut["spalten"]}
