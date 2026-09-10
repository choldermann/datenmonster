# -*- coding: utf-8 -*-
"""Erweitert templates/jtl_lager_cockpit.json um die Reiter „Inventur zum
Stichtag" und „Abflüsse je Artikel". Idempotent: vorhandene Einträge werden
ersetzt, alles andere bleibt unangetastet.

    python3 doku/inventur_template_gen.py

Danach reseeden, installieren und das installierte Formular patchen – siehe
doku/inventur.md. Das SQL steht in doku/sql_inventur.py."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import sql_inventur as S                                    # noqa: E402

PFAD = str(Path(__file__).parent.parent / "templates" / "jtl_lager_cockpit.json")

TEXT = "text"
ZAHL = "float"
GANZ = "int"


def feld(name, typ=ZAHL):
    return {"source_field": name, "target_field": name, "target_type": typ,
            "source_dataset_id": "__sql__sql1",
            "transformer": {"type": "direct", "source_field": name}}


def mapping(mid, name, sql, spalten):
    return {
        "id": mid, "name": name,
        "canvas_nodes": [], "joins": [], "agg_nodes": [], "constant_nodes": [],
        "rest_nodes": [], "lookup_nodes": [], "calc_nodes": [], "switch_nodes": [],
        "sort_nodes": [],
        "sql_nodes": [{"id": "sql1", "x": 120, "y": 40, "width": 380, "height": 260,
                       "connection_id": "{{connection_jtl}}", "sql": sql,
                       "mode": "transform"}],
        "targets": [{"id": "t1", "name": name, "target_type": "dataset",
                     "target_connection_id": None, "target_table": "",
                     "target_write_mode": "replace", "target_options": {},
                     "fields": [feld(n, t) for n, t in spalten]}],
    }


NEUE_MAPPINGS = [
    mapping("m_inv_bestand", "Inventur – Bestand zum Stichtag", S.INV_BESTAND, [
        ("kArtikel", GANZ), ("ArtNr", TEXT), ("Artikel", TEXT),
        ("Warengruppe", TEXT), ("Hersteller", TEXT),
        ("Bestand", ZAHL), ("EK", ZAHL), ("Wert", ZAHL),
        ("MHD", TEXT), ("Resttage", GANZ),
        ("Menge abgelaufen", ZAHL), ("Wert abgelaufen", ZAHL),
        ("Abgang 12M", ZAHL), ("Reichweite Tage", GANZ), ("Letzter Abgang", TEXT),
        ("Menge ohne Charge", ZAHL), ("Chargen", TEXT),
    ]),
    mapping("m_inv_kpi", "Inventur – Kennzahlen zum Stichtag", S.INV_KPI, [
        ("Artikel", GANZ), ("Stueck", ZAHL), ("Bestandswert", ZAHL),
        ("WertAbgelaufen", ZAHL), ("WertUnter3Monate", ZAHL),
        ("OhneAbgang12M", GANZ), ("WertOhneAbgang", ZAHL),
        ("OhneGebuchtenEK", GANZ), ("MengeOhneCharge", ZAHL),
    ]),
    mapping("m_inv_mhd", "Inventur – Bestandswert nach Restlaufzeit", S.INV_MHD, [
        ("Restlaufzeit", TEXT), ("Artikel", GANZ), ("Stueck", ZAHL), ("Wert", ZAHL),
    ]),
    mapping("m_ab_kpi", "Abflüsse – Kennzahlen", S.AB_KPI, [
        ("AbgangGesamt", ZAHL), ("AnKunden", ZAHL), ("AnVerbundene", ZAHL),
        ("AnFremdkunden", ZAHL), ("OhneBerechnung", ZAHL), ("OhneKundenbezug", ZAHL),
        ("UmsatzNetto", ZAHL), ("Fremdkunden", GANZ), ("Artikel", GANZ),
    ]),
    mapping("m_ab_kunden", "Abflüsse – je Kunde", S.AB_KUNDEN, [
        ("Kunde", TEXT), ("kKunde", GANZ), ("Menge", ZAHL),
        ("davon berechnet", ZAHL), ("davon zum Preis 0", ZAHL),
        ("Umsatz netto", ZAHL), ("Preis je Stueck", ZAHL), ("Hinweis", TEXT),
    ]),
    mapping("m_ab_artikel", "Abflüsse – je Artikel und Größe", S.AB_ARTIKEL, [
        ("ArtNr", TEXT), ("Artikel", TEXT), ("Menge", ZAHL),
        ("davon berechnet", ZAHL), ("davon zum Preis 0", ZAHL),
        ("ohne Kundenbezug", ZAHL), ("Kunden", GANZ), ("Umsatz netto", ZAHL),
    ]),
    mapping("m_ab_monat", "Abflüsse – je Monat", S.AB_MONAT, [
        ("Monat", TEXT), ("Fremdkunden", ZAHL), ("Verbundene", ZAHL),
        ("ohne Kundenbezug", ZAHL),
    ]),
    mapping("m_ab_arten", "Abflüsse – nach Buchungsart", S.AB_ARTEN, [
        ("Buchungsart", TEXT), ("Zuordnung", TEXT), ("Menge", ZAHL), ("Buchungen", GANZ),
    ]),
    mapping("m_ab_belege", "Abflüsse – Belege eines Kunden", S.AB_BELEGE, [
        ("Datum", TEXT), ("Lieferschein", TEXT), ("ArtNr", TEXT), ("Artikel", TEXT),
        ("Menge", ZAHL), ("Preis netto", ZAHL), ("Wert", ZAHL), ("Buchungsart", TEXT),
    ]),
]


AB_ACTIONS = ["act_ab_kpi", "act_ab_artikel", "act_ab_kunden",
              "act_ab_monat", "act_ab_arten"]

# visible_tabs hält die Filter auf ihrem Reiter – sonst stünde die
# Artikelsuche auch über der Inventur, wo sie nichts steuert.
NEUE_FELDER = [
    {"id": "f_artikel_suche", "name": "artikel_suche", "type": "text",
     "label": "Artikel (Nummer oder Name)", "row": 1, "colSpan": 5,
     "required": False, "action_ids": AB_ACTIONS,
     # Textfelder lesen den Platzhalter auf oberster Ebene; config.placeholder
     # gilt nur für DB-Dropdowns und blieb hier wirkungslos.
     "placeholder": "leer = alle Artikel · z. B. VAR80215 oder 80218",
     "config": {"auto_run": False,
                "visible_tabs": ["tab_abfluesse"]}},
    {"id": "f_ohne_verbundene", "name": "ohne_verbundene", "type": "dropdown",
     "label": "Verbundene Unternehmen", "row": 1, "colSpan": 4,
     "default": "1", "action_ids": AB_ACTIONS,
     "options": [{"value": "1", "label": "ausblenden"},
                 {"value": "0", "label": "mit anzeigen"}],
     "config": {"auto_run": True, "visible_tabs": ["tab_abfluesse"]}},
    {"id": "f_ab_start", "name": "", "type": "button",
     "label": "Abflüsse auswerten", "row": 1, "colSpan": 3,
     "action_ids": AB_ACTIONS,
     "config": {"visible_tabs": ["tab_abfluesse"]}},
]


NEUE_ACTIONS = [
    ("act_inv_kpi",     "Inventur – Kennzahlen zum Stichtag"),
    ("act_inv_mhd",     "Inventur – Bestandswert nach Restlaufzeit"),
    ("act_ab_kpi",      "Abflüsse – Kennzahlen"),
    ("act_ab_artikel",  "Abflüsse – je Artikel und Größe"),
    ("act_ab_kunden",   "Abflüsse – je Kunde"),
    ("act_ab_monat",    "Abflüsse – je Monat"),
    ("act_ab_arten",    "Abflüsse – nach Buchungsart"),
]


def kpi(wid, action, label, spalte, cfg=None):
    c = {"width": 3, "column": spalte, "aggregation": "first",
         "prefix": "", "suffix": "", "decimals": 0}
    c.update(cfg or {})
    return {"id": wid, "type": "kpi", "label": label, "action_id": action, "config": c}


NEUE_WIDGETS = [
    # ── Reiter Inventur ──────────────────────────────────────────────────────
    kpi("w_inv_wert", "act_inv_kpi", "Bestandswert zum Stichtag", "Bestandswert",
        {"suffix": " €", "decimals": 2}),
    kpi("w_inv_abgelaufen", "act_inv_kpi", "davon MHD überschritten", "WertAbgelaufen",
        {"suffix": " €", "decimals": 2,
         "info": "Wert der Chargen, deren Mindesthaltbarkeit am Stichtag abgelaufen war."}),
    kpi("w_inv_unter3", "act_inv_kpi", "läuft in unter 3 Monaten ab", "WertUnter3Monate",
        {"suffix": " €", "decimals": 2}),
    kpi("w_inv_ohne_abgang", "act_inv_kpi", "ohne Abgang seit 12 Monaten", "WertOhneAbgang",
        {"suffix": " €", "decimals": 2, "breakdown": [
            {"label": "Artikel", "column": "OhneAbgang12M", "decimals": 0, "suffix": ""}]}),
    {"id": "w_inv_mhd", "type": "bar", "label": "Bestandswert nach Restlaufzeit",
     "action_id": "act_inv_mhd",
     "config": {"width": 6, "x_column": "Restlaufzeit", "y_columns": ["Wert"],
                "suffix": " €"}},
    {"id": "w_inv_mhd_tab", "type": "table", "label": "Restlaufzeit im Überblick",
     "action_id": "act_inv_mhd", "config": {"width": 6}},
    {"id": "w_inventur", "type": "inventur", "label": "Inventur zum Stichtag",
     # Standalone-Widgets ohne action_id erscheinen in JEDEM Reiter – die
     # action_id bindet es an diesen einen. Das Ergebnis nutzt es nicht.
     "action_id": "act_inv_kpi",
     "config": {"width": 12,
                "info": "Bestände einfrieren, bewerten und als Liste an den "
                        "Steuerberater geben. Eine abgeschlossene Inventur "
                        "bleibt unverändert."}},

    # ── Reiter Abflüsse ──────────────────────────────────────────────────────
    kpi("w_ab_fremd", "act_ab_kpi", "Abgang an Fremdkunden", "AnFremdkunden",
        {"decimals": 0, "breakdown": [
            {"label": "Kunden", "column": "Fremdkunden", "decimals": 0, "suffix": ""},
            {"label": "Umsatz netto", "column": "UmsatzNetto", "suffix": " €", "decimals": 2}]}),
    kpi("w_ab_verbunden", "act_ab_kpi", "an verbundene Unternehmen", "AnVerbundene",
        {"decimals": 0,
         "info": "Menge an die Kunden aus der Ausschlussliste – hier bewusst "
                 "sichtbar, in den Listen unten ausgeblendet."}),
    kpi("w_ab_ohne_re", "act_ab_kpi", "geliefert zum Preis 0", "OhneBerechnung",
        {"decimals": 0,
         "info": "Ware, die einem Kunden zugeordnet ist, aber ohne Wert "
                 "berechnet wurde – der Preis wird außerhalb der WaWi geregelt."}),
    kpi("w_ab_ohne_kunde", "act_ab_kpi", "ohne Kundenbezug", "OhneKundenbezug",
        {"decimals": 0,
         "info": "Korrektur- und Umlagerungsbuchungen. Kein Abverkauf – wer sie "
                 "als Verkauf liest, plant am Bedarf vorbei."}),
    {"id": "w_ab_artikel", "type": "table", "label": "Abgang je Artikel und Größe",
     "action_id": "act_ab_artikel", "config": {"width": 12, "full_rows": True}},
    {"id": "w_ab_kunden", "type": "table", "label": "Wer die Ware bekommen hat",
     "action_id": "act_ab_kunden",
     "config": {"width": 12, "full_rows": True, "hidden_columns": ["kKunde"],
                "drilldown": {"mapping_id": "m_ab_belege", "param": "kunde",
                              "key_column": "kKunde", "title": "Belege des Kunden"}}},
    {"id": "w_ab_monat", "type": "bar", "label": "Abgang je Monat",
     "action_id": "act_ab_monat",
     "config": {"width": 6, "x_column": "Monat",
                "y_columns": ["Fremdkunden", "Verbundene", "ohne Kundenbezug"]}},
    {"id": "w_ab_arten", "type": "table", "label": "Woher die Abgänge stammen",
     "action_id": "act_ab_arten", "config": {"width": 6}},
    {"id": "w_ab_ausschluss", "type": "kunden_ausschluss",
     "label": "Verbundene Unternehmen", "action_id": "act_ab_kpi",
     "config": {"width": 12,
                "info": "Diese Kunden werden aus den Listen oben ausgeblendet. "
                        "Achtung: Ist ein Betrieb doppelt in der WaWi angelegt, "
                        "gehören beide Datensätze hier hinein."}},
]


# Der bestehende Reiter „Inventur & Schwund" zeigt Korrekturbuchungen, nicht
# die Inventur – mit einem echten Inventur-Reiter daneben wäre der Name eine
# Verwechslungsfalle.
UMBENENNEN = {"tab_lg_schwund": "Schwund & Korrekturen"}

# Reihenfolge der Reiter, damit die neuen nicht hinten anstehen.
REIHENFOLGE = ["tab_lg_wert", "tab_lg_dispo", "tab_lg_umschlag", "tab_abfluesse",
               "tab_lg_ladenhueter", "tab_inventur", "tab_lg_schwund",
               "tab_lg_preise", "tab_lg_lager"]

NEUE_TABS = [
    {"id": "tab_inventur", "label": "Inventur zum Stichtag",
     "action_ids": ["act_inv_kpi", "act_inv_mhd"]},
    {"id": "tab_abfluesse", "label": "Abflüsse je Artikel",
     "action_ids": ["act_ab_kpi", "act_ab_artikel", "act_ab_kunden",
                    "act_ab_monat", "act_ab_arten"]},
]


def ersetzen(liste, neue, schluessel="id"):
    """Fügt ein oder ersetzt vorhandene Einträge – der Generator muss mehrfach
    laufen können, ohne Dubletten zu hinterlassen."""
    index = {e[schluessel]: i for i, e in enumerate(liste) if schluessel in e}
    for n in neue:
        if n[schluessel] in index:
            liste[index[n[schluessel]]] = n
        else:
            liste.append(n)
    return liste


def main():
    d = json.load(open(PFAD, encoding="utf-8"))
    ersetzen(d["mappings"], NEUE_MAPPINGS)

    s = d["forms"][0]["schema"]
    ersetzen(s["fields"], NEUE_FELDER, "name")
    for f in s["fields"]:
        f.setdefault("config", {})
    ersetzen(s["actions"], [{"id": aid, "label": label, "type": "run_mapping",
                             "mapping_id": next(m["id"] for m in NEUE_MAPPINGS
                                                if m["name"] == label)}
                            for aid, label in NEUE_ACTIONS])
    ersetzen(s["widgets"], NEUE_WIDGETS)
    ersetzen(s["result_tabs"], NEUE_TABS)
    for t in s["result_tabs"]:
        if t["id"] in UMBENENNEN:
            t["label"] = UMBENENNEN[t["id"]]
    s["result_tabs"].sort(key=lambda t: REIHENFOLGE.index(t["id"])
                          if t["id"] in REIHENFOLGE else 99)

    d["version"] = "1.7"
    # Überholte Hinweise früherer Läufe entfernen, sonst stünden alt und neu nebeneinander.
    veraltet = {"Der Reiter „Abflüsse je Artikel“ braucht eine Artikelnummer als "
                "Eingabe. Eine Vater-Artikelnummer (VAR…) findet alle Größen darunter."}
    hinweise = [h for h in (d.get("hinweise") or []) if h not in veraltet]
    for h in ("Der Reiter „Inventur“ friert Bestände zum Stichtag ein, bewertet sie "
              "und gibt eine dokumentierte Liste für den Steuerberater aus. Der "
              "Bestandswert wird NICHT in die WaWi zurückgeschrieben – JTL kennt "
              "keinen Abwertungswert.",
              "Im Reiter „Abflüsse je Artikel“ filtert das Artikelfeld: leer zeigt "
              "alle Artikel nach Menge, eine Vater-Artikelnummer (VAR…) alle Größen darunter."):
        if h not in hinweise:
            hinweise.append(h)
    d["hinweise"] = hinweise

    json.dump(d, open(PFAD, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"Template geschrieben: {len(d['mappings'])} Mappings, "
          f"{len(s['result_tabs'])} Reiter, {len(s['widgets'])} Widgets")


if __name__ == "__main__":
    main()
