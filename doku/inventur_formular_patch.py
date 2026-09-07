# -*- coding: utf-8 -*-
"""Ergänzt das installierte Lager-Cockpit (Formular 7) um die Reiter „Inventur
zum Stichtag" und „Abflüsse je Artikel".

Der Template-Installer fasst bestehende Formulare bewusst nicht an – ein
installiertes Dashboard ist oft nachgepflegt, und das Template-Schema trägt noch
Platzhalter statt echter IDs. Deshalb wird hier gezielt ergänzt: vorhandene
Widgets und Reiter bleiben unangetastet, die mapping_id der neuen Actions wird
über den Mapping-NAMEN auf die echte DB-ID aufgelöst.
"""
import json
import sys

sys.path.insert(0, "/app")
from sqlalchemy.orm.attributes import flag_modified      # noqa: E402
from app.core.database import SessionLocal              # noqa: E402
from app.models.form import Form                        # noqa: E402
from app.models.mapping import Mapping                  # noqa: E402
from app.models.template import Template                # noqa: E402

FORM_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 7
TEMPLATE_ID = "jtl_lager_cockpit"

# Was aus dem Template übernommen wird – alles andere bleibt, wie es ist.
NEUE_FELDER = {"artikel_suche", "ohne_verbundene", ""}
NEUE_FELD_IDS = {"f_artikel_suche", "f_ohne_verbundene", "f_ab_start"}
NEUE_ACTIONS = {"act_inv_kpi", "act_inv_mhd", "act_ab_kpi", "act_ab_artikel",
                "act_ab_kunden", "act_ab_monat", "act_ab_arten"}
NEUE_WIDGETS = {"w_inv_wert", "w_inv_abgelaufen", "w_inv_unter3", "w_inv_ohne_abgang",
                "w_inv_mhd", "w_inv_mhd_tab", "w_inventur",
                "w_ab_fremd", "w_ab_verbunden", "w_ab_ohne_re", "w_ab_ohne_kunde",
                "w_ab_artikel", "w_ab_kunden", "w_ab_monat", "w_ab_arten",
                "w_ab_ausschluss"}
NEUE_TABS = {"tab_inventur", "tab_abfluesse"}


def main():
    db = SessionLocal()
    form = db.query(Form).filter(Form.id == FORM_ID).first()
    if not form:
        print(f"Formular {FORM_ID} nicht gefunden")
        return 1
    tpl = db.query(Template).filter(Template.template_id == TEMPLATE_ID).first()
    inhalt = tpl.content if isinstance(tpl.content, dict) else json.loads(tpl.content)
    vorlage = inhalt["forms"][0]["schema"]

    # Template-Mapping-Referenz („m_inv_kpi") → echte DB-ID über den Namen.
    namen = {m["id"]: m["name"] for m in inhalt["mappings"]}
    db_ids = {m.name: m.id for m in db.query(Mapping)
              .filter(Mapping.project_id == form.project_id).all()}
    ref_zu_id = {ref: db_ids[name] for ref, name in namen.items() if name in db_ids}

    schema = dict(form.schema or {})
    fehlend = [ref for ref in ("m_inv_kpi", "m_inv_mhd", "m_ab_kpi", "m_ab_artikel",
                               "m_ab_kunden", "m_ab_monat", "m_ab_arten", "m_ab_belege")
               if ref not in ref_zu_id]
    if fehlend:
        print("Diese Auswertungen fehlen in der Datenbank:", ", ".join(fehlend))
        return 1

    def ersetzen(liste, neue, schluessel="id"):
        vorhanden = {e.get(schluessel): i for i, e in enumerate(liste)}
        for n in neue:
            k = n.get(schluessel)
            if k in vorhanden:
                liste[vorhanden[k]] = n
            else:
                liste.append(n)

    # ── Felder ───────────────────────────────────────────────────────────────
    felder = list(schema.get("fields") or [])
    ersetzen(felder, [f for f in vorlage["fields"] if f.get("id") in NEUE_FELD_IDS])
    schema["fields"] = felder

    # ── Actions: mapping_id auf die echte ID auflösen ────────────────────────
    actions = list(schema.get("actions") or [])
    neu_actions = []
    for a in vorlage["actions"]:
        if a["id"] not in NEUE_ACTIONS:
            continue
        a = dict(a)
        a["mapping_id"] = ref_zu_id[a["mapping_id"]]
        neu_actions.append(a)
    ersetzen(actions, neu_actions)
    schema["actions"] = actions

    # ── Widgets: Drilldown-Referenzen ebenfalls auflösen ─────────────────────
    def drill_aufloesen(cfg):
        if not isinstance(cfg, dict):
            return cfg
        cfg = dict(cfg)
        d = cfg.get("drilldown")
        if isinstance(d, dict):
            d = dict(d)
            if d.get("mapping_id") in ref_zu_id:
                d["mapping_id"] = ref_zu_id[d["mapping_id"]]
            d["levels"] = [
                {**lv, "mapping_id": ref_zu_id.get(lv.get("mapping_id"), lv.get("mapping_id"))}
                for lv in (d.get("levels") or [])
            ]
            if not d["levels"]:
                d.pop("levels")
            cfg["drilldown"] = d
        return cfg

    widgets = list(schema.get("widgets") or [])
    neu_widgets = []
    for w in vorlage["widgets"]:
        if w["id"] not in NEUE_WIDGETS:
            continue
        w = dict(w)
        w["config"] = drill_aufloesen(w.get("config"))
        neu_widgets.append(w)
    ersetzen(widgets, neu_widgets)
    schema["widgets"] = widgets

    # ── Reiter: neue ergänzen, Reihenfolge und Umbenennung aus dem Template ──
    tabs = list(schema.get("result_tabs") or [])
    ersetzen(tabs, [t for t in vorlage["result_tabs"] if t["id"] in NEUE_TABS])
    vorlagen_label = {t["id"]: t["label"] for t in vorlage["result_tabs"]}
    for t in tabs:
        if t["id"] == "tab_lg_schwund" and t["id"] in vorlagen_label:
            t["label"] = vorlagen_label[t["id"]]
    reihenfolge = [t["id"] for t in vorlage["result_tabs"]]
    tabs.sort(key=lambda t: reihenfolge.index(t["id"]) if t["id"] in reihenfolge else 99)
    schema["result_tabs"] = tabs

    form.schema = schema
    flag_modified(form, "schema")
    db.commit()

    print(f"Formular {FORM_ID} „{form.name}“ ergänzt:")
    print("  Reiter:  " + " · ".join(t["label"] for t in tabs))
    print(f"  Felder:  {len(felder)}   Actions: {len(actions)}   Widgets: {len(widgets)}")
    print("  Neue Auswertungen: " + ", ".join(
        f"{ref}={ref_zu_id[ref]}" for ref in sorted(ref_zu_id) if ref.startswith(("m_inv", "m_ab"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
