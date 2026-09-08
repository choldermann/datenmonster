# -*- coding: utf-8 -*-
"""Baut templates/jtl_preis_cockpit.json aus den SQL-Bausteinen.

Die Ausgabespalten werden NICHT von Hand gepflegt, sondern durch einen echten
Lauf gegen eine WaWi ermittelt. Grund: eine SQL-Spalte, die nicht in
targets.fields steht, kommt in der Oberflaeche nie an - der haeufigste stille
Fehler beim Templatebau.

    docker cp doku/sql_preis_cockpit.py datenmonster-backend:/tmp/
    docker cp doku/preis_cockpit_gen.py  datenmonster-backend:/tmp/
    docker exec -e PYTHONPATH=/app -w /app datenmonster-backend \
        python /tmp/preis_cockpit_gen.py --verbindung 3 --ziel /tmp/jtl_preis_cockpit.json
    docker cp datenmonster-backend:/tmp/jtl_preis_cockpit.json templates/
"""
import argparse
import json
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/tmp")

from sql_preis_cockpit import SQL                                  # noqa: E402

VERSION = "1.0"

# Feste Werte fuer den Spaltenlauf. Sie bestimmen nur, WELCHE Spalten
# zurueckkommen, nicht was spaeter angezeigt wird.
PROBE = {
    # Als Text laege MS SQL Server das unter deutscher Spracheinstellung als
    # yyyy-dd-mm aus - der Spaltenlauf liefe stumm auf einem anderen Zeitraum.
    ":von": "CAST('2025-09-08' AS DATE)", ":bis": "CAST('2026-09-08' AS DATE)",
    ":cfg_marge_min_prozent": "15", ":cfg_ek_anstieg_prozent": "5",
    ":cfg_marge_verfall_punkte": "5",
    # Echte Schluessel, nicht -1: bei einem leeren Ergebnis kaeme jede Spalte
    # als Text zurueck und die Zahlenformate im Drilldown waeren hin.
    ":artnr": "'10191'", ":kKunde": "4269", ":band": "'10 bis 20 %'",
    ":monat": "'2026-03'",
}

NAMEN = {
    "m_pr_kpi":         "Preise – Margen-Kennzahlen",
    "m_pr_monat":       "Preise – Marge je Monat",
    "m_pr_band":        "Preise – Umsatz je Margenband",
    "m_pr_verfall":     "Preise – Artikel mit Margenverfall",
    "m_pr_unter_ek":    "Preise – unter Einkaufspreis verkauft",
    "m_pr_kalk":        "Preise – Kalkulation unter Mindestmarge",
    "m_pr_kalk_kpi":    "Preise – Kalkulations-Kennzahlen",
    "m_pr_ek_anstieg":  "Preise – gestiegene Einkaufspreise",
    "m_pr_rabatt_kpi":  "Preise – Rabatt-Kennzahlen",
    "m_pr_kunde_marge": "Preise – Marge je Kunde",
    "m_pr_pos_artikel": "Preise – Positionen eines Artikels (Detail)",
    "m_pr_pos_kunde":   "Preise – Positionen eines Kunden (Detail)",
    "m_pr_band_detail": "Preise – Artikel eines Margenbands (Detail)",
    "m_pr_monat_detail": "Preise – Artikel eines Monats (Detail)",
}

VERSTECKT = ["kArtikel", "kKunde", "Sortierung", "Schluessel", "sort"]


# Zaehlspalten und Schluessel. Alles andere Numerische wird float - eine als
# int deklarierte Menge wuerde bei einem Kunden mit Teilmengen abgeschnitten.
INT_SPALTEN = {
    "kArtikel", "kKunde", "Sortierung", "Positionen", "Rechnungen", "Preise",
    "ArtikelMitPreis", "Artikelzahl", "PosOhneEK", "PosGratis", "ArtikelUnterMinMarge", "MitRabatt",
    "UnterMindestmarge", "UnterEinkaufspreis", "PreisNull", "OhneEK",
}


# Spalten, die immer Text bleiben muessen. Artikelnummern sehen bei PPS wie
# Zahlen aus ("30058") und wuerden sonst als float gefuehrt - bei HaKo lauten
# sie "001547-0376/13007-L", und fuehrende Nullen waeren weg.
TEXT_SPALTEN = {"ArtNr", "Rechnungsnr", "Monat"}


def _typ(name: str, reihe) -> str:
    """Ermittelt den Zieltyp einer Spalte aus ihren Werten.

    query_full liefert Dezimalwerte je nach Treiber als Text oder als int
    zurueck - der Python-Typ allein taugt deshalb nicht als Kennzeichen.
    Entschieden wird ueber die Umwandelbarkeit in eine Zahl.
    """
    import pandas as pd
    if name in TEXT_SPALTEN:
        return "string"
    werte = reihe.dropna()
    if werte.empty:
        return "string"
    zahlen = pd.to_numeric(werte, errors="coerce")
    if zahlen.isna().any():
        return "string"
    return "int" if name in INT_SPALTEN else "float"


def spalten(conn, sql: str):
    """Fuehrt die Abfrage mit Probewerten aus und liefert (Name, Typ)."""
    from app.services import db_service
    gefuellt = sql
    for k in sorted(PROBE, key=len, reverse=True):
        gefuellt = gefuellt.replace(k, PROBE[k])
    df = db_service.query_full(conn, gefuellt)
    return [(c, _typ(c, df[c].head(200))) for c in df.columns]


def mapping(mid: str, sql: str, spalten_liste) -> dict:
    felder = [{
        "source_field": name, "target_field": name, "target_type": typ,
        "source_dataset_id": "__sql__sql1",
        "transformer": {"type": "direct", "source_field": name},
    } for name, typ in spalten_liste]
    return {
        "id": mid, "name": NAMEN[mid],
        "canvas_nodes": [], "joins": [], "agg_nodes": [], "transform_nodes": [],
        "constant_nodes": [], "rest_nodes": [], "lookup_nodes": [],
        "calc_nodes": [], "switch_nodes": [], "sort_nodes": [],
        "sql_nodes": [{
            "id": "sql1", "x": "120", "y": "40", "width": "380", "height": "260",
            "connection_id": "{{connection_jtl}}", "mode": "transform",
            "sql": sql, "output_field": "sql_1",
            "output_fields": [n for n, _ in spalten_liste],
        }],
        "targets": [{
            "id": "t1", "name": NAMEN[mid], "target_type": "dataset",
            "target_connection_id": None, "target_table": "",
            "target_write_mode": "replace", "target_options": {},
            "fields": felder,
        }],
    }


def kpi(wid, label, action, spalte, breite=3, praefix="", suffix="",
        stellen=2, vergleich=None, vergleich_label="Vorjahr", invers=False):
    cfg = {"width": breite, "column": spalte, "aggregation": "first",
           "prefix": praefix, "suffix": suffix, "decimals": stellen,
           "invert_delta": invers}
    if vergleich:
        cfg["compare_column"] = vergleich
        cfg["compare_label"] = vergleich_label
    return {"id": wid, "type": "kpi", "label": label, "action_id": action,
            "config": cfg}


def tabelle(wid, label, action, breite=12, drill=None):
    cfg = {"width": breite, "full_rows": True}
    if drill:
        cfg["drilldown"] = drill
    return {"id": wid, "type": "table", "label": label, "action_id": action,
            "config": cfg}


def drill_artikel(titel="Rechnungspositionen des Artikels"):
    """Schluessel ist die Artikelnummer, nicht kArtikel.

    Die Listen gruppieren nach cArtNr. Bei HaKo tragen Positionen derselben
    Nummer zwei verschiedene kArtikel - ueber kArtikel gefiltert zeigte der
    Drilldown einen anderen Artikel als die angeklickte Zeile.
    """
    return {"mapping_id": "m_pr_pos_artikel", "key_column": "ArtNr",
            "param": "artnr", "title": titel, "hidden_columns": VERSTECKT}


def formular() -> dict:
    widgets = []
    aktionen = []

    def akt(aid, mid, label):
        aktionen.append({"id": aid, "type": "run_mapping", "mapping_id": mid,
                         "pipeline_id": None, "label": label})

    akt("act_pr_kpi", "m_pr_kpi", "Margen-Kennzahlen")
    akt("act_pr_band", "m_pr_band", "Umsatz je Margenband")
    akt("act_pr_monat", "m_pr_monat", "Marge je Monat")
    akt("act_pr_verfall", "m_pr_verfall", "Artikel mit Margenverfall")
    akt("act_pr_unter_ek", "m_pr_unter_ek", "Unter Einkaufspreis verkauft")
    akt("act_pr_kalk_kpi", "m_pr_kalk_kpi", "Kalkulations-Kennzahlen")
    akt("act_pr_kalk", "m_pr_kalk", "Kalkulation unter Mindestmarge")
    akt("act_pr_ek", "m_pr_ek_anstieg", "Gestiegene Einkaufspreise")
    akt("act_pr_rabatt_kpi", "m_pr_rabatt_kpi", "Rabatt-Kennzahlen")
    akt("act_pr_kunde", "m_pr_kunde_marge", "Marge je Kunde")

    # ── Reiter 1: Überblick ─────────────────────────────────────────────────
    widgets += [
        kpi("w_pr_umsatz", "Umsatz netto", "act_pr_kpi", "Umsatz",
            praefix="€ ", vergleich="UmsatzVJ"),
        kpi("w_pr_einsatz", "Wareneinsatz", "act_pr_kpi", "Wareneinsatz",
            praefix="€ ", invers=True),
        kpi("w_pr_rohertrag", "Rohertrag", "act_pr_kpi", "Rohertrag",
            praefix="€ ", vergleich="RohertragVJ"),
        kpi("w_pr_marge", "Rohertragsmarge", "act_pr_kpi", "Marge",
            suffix=" %", vergleich="MargeVJ"),
        kpi("w_pr_untermarge_u", "Umsatz unter Mindestmarge", "act_pr_kpi",
            "UmsatzUnterMinMarge", praefix="€ ", invers=True),
        kpi("w_pr_untermarge_a", "Artikel unter Mindestmarge", "act_pr_kpi",
            "ArtikelUnterMinMarge", stellen=0, invers=True),
        kpi("w_pr_gratis", "Gratisware (Wareneinsatz)", "act_pr_kpi",
            "EinsatzGratis", praefix="€ ", invers=True),
        kpi("w_pr_ohne_ek", "Positionen ohne Einkaufspreis", "act_pr_kpi",
            "PosOhneEK", stellen=0, invers=True),
        {"id": "w_pr_bar_band", "type": "bar",
         "label": "Umsatz je Margenband", "action_id": "act_pr_band",
         "config": {"width": 6, "x_column": "Margenband",
                    "y_columns": ["Umsatz"],
                    "drilldown": {"mapping_id": "m_pr_band_detail",
                                  "key_column": "Margenband", "param": "band",
                                  "title": "Artikel dieses Margenbands",
                                  "hidden_columns": VERSTECKT,
                                  "levels": [drill_artikel()]}}},
        {"id": "w_pr_line_monat", "type": "line",
         "label": "Rohertragsmarge je Monat (aktuell vs. Vorjahr)",
         "action_id": "act_pr_monat",
         "config": {"width": 6, "x_column": "Monat",
                    "y_columns": ["Marge", "Vorjahr"], "curved": True,
                    "drilldown": {"mapping_id": "m_pr_monat_detail",
                                  "key_column": "Monat", "param": "monat",
                                  "title": "Artikel dieses Monats",
                                  "hidden_columns": VERSTECKT,
                                  "levels": [drill_artikel()]}}},
        {"id": "w_pr_ai", "type": "ai_summary",
         "label": "KI-Kurzanalyse Preise & Marge", "action_id": "act_pr_kpi",
         "config": {"width": 12, "report_layout": True,
                    "instruction": (
                        "Bewerte die Ertragslage aus Preissicht: Rohertragsmarge "
                        "gegenüber Vorjahr, Umsatzanteil unter der Mindestmarge, "
                        "verschenkte Ware und Positionen ohne Einkaufspreis. "
                        "Nenne die Artikel mit dem größten Margenverfall und sage "
                        "konkret, ob der Preis oder der Einkauf die Ursache ist."),
                    "extra_sections": [
                        {"action_id": "act_pr_verfall", "label": "Margenverfall",
                         "kind": "table"},
                        {"action_id": "act_pr_kalk_kpi", "label": "Kalkulation",
                         "kind": "kpi"}]}},
    ]

    # ── Reiter 2: Margenverfall ─────────────────────────────────────────────
    widgets += [
        tabelle("w_pr_tbl_verfall", "Artikel mit sinkender Marge (gegen Vorjahr)",
                "act_pr_verfall", drill=drill_artikel()),
        tabelle("w_pr_tbl_unter_ek", "Unter Einkaufspreis verkauft",
                "act_pr_unter_ek", drill=drill_artikel()),
    ]

    # ── Reiter 3: Kalkulation ───────────────────────────────────────────────
    widgets += [
        kpi("w_pr_k_preise", "Gepflegte Preise", "act_pr_kalk_kpi", "Preise",
            stellen=0),
        kpi("w_pr_k_marge", "Ø kalkulierte Marge", "act_pr_kalk_kpi",
            "MargeDurchschnitt", suffix=" %"),
        kpi("w_pr_k_unter", "Unter Mindestmarge", "act_pr_kalk_kpi",
            "UnterMindestmarge", stellen=0, invers=True),
        kpi("w_pr_k_unter_ek", "Unter Einkaufspreis", "act_pr_kalk_kpi",
            "UnterEinkaufspreis", stellen=0, invers=True),
        kpi("w_pr_k_null", "Preis nicht gepflegt", "act_pr_kalk_kpi",
            "PreisNull", stellen=0, invers=True),
        kpi("w_pr_k_ohne_ek", "Ohne Einkaufspreis", "act_pr_kalk_kpi", "OhneEK",
            stellen=0, invers=True),
        tabelle("w_pr_tbl_kalk", "Preise unter der Mindestmarge", "act_pr_kalk",
                drill=drill_artikel()),
    ]

    # ── Reiter 4: Einkaufspreise ────────────────────────────────────────────
    widgets += [
        tabelle("w_pr_tbl_ek", "Artikel mit gestiegenem Einkaufspreis",
                "act_pr_ek", drill=drill_artikel()),
    ]

    # ── Reiter 5: Kunden & Rabatte ──────────────────────────────────────────
    widgets += [
        kpi("w_pr_r_betrag", "Gewährte Rabatte", "act_pr_rabatt_kpi",
            "Rabattbetrag", praefix="€ ", invers=True),
        kpi("w_pr_r_quote", "Rabattquote", "act_pr_rabatt_kpi", "Rabattquote",
            suffix=" %", invers=True),
        kpi("w_pr_r_pos", "Positionen mit Rabatt", "act_pr_rabatt_kpi",
            "MitRabatt", stellen=0),
        kpi("w_pr_r_hoechst", "Höchster Einzelrabatt", "act_pr_rabatt_kpi",
            "HoechsterRabatt", suffix=" %", invers=True),
        tabelle("w_pr_tbl_kunde", "Marge je Kunde", "act_pr_kunde",
                drill={"mapping_id": "m_pr_pos_kunde", "key_column": "kKunde",
                       "param": "kKunde", "title": "Positionen dieses Kunden",
                       "hidden_columns": VERSTECKT}),
    ]

    return {
        "fields": [{
            "id": "f_zeitraum", "type": "daterange", "row": 0, "colSpan": 12,
            "label": "Zeitraum", "name": "zeitraum", "action_ids": [],
            "config": {"param_from": "von", "param_to": "bis",
                       "default": "this_year", "auto_run": True},
        }],
        "layout": [],
        "actions": aktionen,
        "widgets": widgets,
        "result_tabs": [
            {"id": "tab_pr_ueberblick", "label": "Überblick",
             "action_ids": ["act_pr_kpi", "act_pr_band", "act_pr_monat"]},
            {"id": "tab_pr_verfall", "label": "Margenverfall",
             "action_ids": ["act_pr_verfall", "act_pr_unter_ek"]},
            {"id": "tab_pr_kalk", "label": "Kalkulation",
             "action_ids": ["act_pr_kalk_kpi", "act_pr_kalk"]},
            {"id": "tab_pr_ek", "label": "Einkaufspreise",
             "action_ids": ["act_pr_ek"]},
            {"id": "tab_pr_kunden", "label": "Kunden & Rabatte",
             "action_ids": ["act_pr_rabatt_kpi", "act_pr_kunde"]},
        ],
        "show_ai_assistant": False,
    }


HINWEISE = [
    "Marge = (Umsatz − Wareneinsatz) / Umsatz auf Artikelpositionen "
    "(Rechnung.tRechnungPosition, nType = 1), Stornos ausgenommen. Der "
    "Wareneinsatz nimmt bevorzugt den historischen EK der Position "
    "(fEkNetto) und friert die Marge damit zum Verkaufszeitpunkt ein.",
    "Positionen ohne hinterlegten EK zählen als 100 % Marge und schönen die "
    "Zahl. Die Kachel „Positionen ohne Einkaufspreis\" weist das offen aus – "
    "gemessen: PPS 138 Positionen (0,1 % Umsatz), HaKo 1.613 (77.997 €).",
    "Gratisware (Verkaufspreis 0 bei echtem Wareneinsatz) drückt die Marge, "
    "taucht aber in keiner Umsatzzahl auf. Eigene Kachel, damit ein "
    "Margenrückgang nicht fälschlich dem Preis angelastet wird.",
    "Der Reiter „Margenverfall\" zeigt nur Artikel, die noch Ertrag bringen. "
    "Artikel, die aktuell unter EK laufen, stehen in der Tabelle darunter – "
    "sonst wären es zweimal dieselben Zeilen.",
    "Für den Vorjahresvergleich braucht es in BEIDEN Zeiträumen einen echten "
    "EK. Ohne das ergäbe ein fehlender EK im Vorjahr eine Scheinmarge von "
    "100 % und damit einen Verfall, den es nie gab.",
    "Die Reiter „Kalkulation\" und „Einkaufspreise\" sind Momentaufnahmen des "
    "Stammdatenstands und ignorieren den Zeitraumfilter.",
    "Kalkulation: Grundpreis aus Preisliste.vPreislisteNetto mit nAnzahlAb = 0 "
    "(nicht 1) und kShop = 0 – die Ansicht wiederholt jede Zeile je Shop, ohne "
    "kShop-Filter zählte jeder Preis mehrfach.",
    "Einkaufspreise: letzter gegen vorletzten Wareneingang je Artikel "
    "(tWarenLagerEingang). Eingänge unter 0,05 € und Sprünge über Faktor 5 "
    "bleiben außen vor – das sind Erfassungsfehler (Liter statt Gebinde), "
    "keine Preiserhöhungen.",
    "Schwellwerte kommen aus den Projekteinstellungen: Mindestmarge "
    "(marge_min_prozent), Margenverfall in Punkten (marge_verfall_punkte) und "
    "EK-Anstieg (ek_anstieg_prozent).",
    "„Marge nach Kanal\" ist bewusst nicht enthalten: Ohne Marktplatz- oder "
    "Shopanbindung gibt es nur einen Kanal. Bei einem Onlinehändler wäre das "
    "eine eigene Auswertung.",
    "Verbundene Unternehmen verzerren die Kundenmarge – im Test lief eine "
    "konzerninterne Lieferung mit −148 % Marge. Solche Kunden vor der "
    "Bewertung prüfen.",
    "SCHEMA-PRÜFUNG: genutzt werden Rechnung.vRechnung, "
    "Rechnung.tRechnungPosition, Rechnung.vRechnungRechnungsadresse, "
    "Preisliste.vPreislisteNetto, dbo.tArtikel, dbo.tArtikelBeschreibung, "
    "dbo.tKundenGruppe, dbo.tWarenLagerEingang, dbo.tlagerbestand.",
]

WISSEN = [
    {"category": "rule", "title": "JTL – Marge und Wareneinsatz",
     "content": "Wareneinsatz je Rechnungsposition: COALESCE(NULLIF(POS.fEkNetto,0), "
                "A.fEKNetto, 0) * fAnzahl – erst der historische EK der Position, "
                "dann der aktuelle Artikel-EK. Marge = (Umsatz − Wareneinsatz) / "
                "Umsatz. Nur nType = 1, Stornos über ISNULL(nStorno,0)=0 raus.",
     "always_include": True, "scope": "global"},
    {"category": "rule", "title": "JTL – Verkaufspreise auflösen",
     "content": "Preise nicht selbst zusammenbauen: Preisliste.vPreislisteNetto löst "
                "Kundengruppe, Shop und den fVKNetto-Fallback fertig auf. Der "
                "Grundpreis steht auf nAnzahlAb = 0, höhere Werte sind Staffeln. "
                "Die Ansicht wiederholt jede Zeile je kShop – ohne kShop-Filter "
                "zählt jeder Preis mehrfach.",
     "always_include": False, "scope": "global"},
    {"category": "trap", "title": "JTL – fehlender EK schönt die Marge",
     "content": "Eine Rechnungsposition ohne fEkNetto und ohne Artikel-EK erscheint "
                "mit 100 % Marge. Solche Positionen immer getrennt ausweisen statt "
                "sie stillschweigend mitzurechnen – dieselbe Klasse wie "
                "Versandarten ohne hinterlegten EK.",
     "always_include": False, "scope": "global"},
    {"category": "trap", "title": "JTL – Gratisware im Rechnungslauf",
     "content": "Positionen mit fVkNetto = 0 und echtem Wareneinsatz sind Muster, "
                "Werbung oder MHD-Abverkauf. Sie senken die Marge, tauchen aber in "
                "keiner Umsatzzahl auf. Bei PPS 963 Positionen mit 10.261 € "
                "Wareneinsatz in zwölf Monaten.",
     "always_include": False, "scope": "global"},
    {"category": "trap", "title": "JTL – EK-Sprünge sind oft Erfassungsfehler",
     "content": "Wareneingänge tragen gelegentlich einen EK in der falschen Einheit "
                "(Liter statt Gebinde). Ein Vergleich zweier Eingänge muss Werte "
                "unter 0,05 € und Sprünge über Faktor 5 ausschließen, sonst steht "
                "ein Tippfehler mit 20.000 % an der Spitze der Liste.",
     "always_include": False, "scope": "global"},
]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--verbindung", type=int, required=True,
                   help="DbConnection-ID, gegen die die Spalten ermittelt werden")
    p.add_argument("--ziel", required=True)
    a = p.parse_args()

    from app.core.database import SessionLocal
    from app.models.dataset import DbConnection
    db = SessionLocal()
    conn = db.query(DbConnection).filter(DbConnection.id == a.verbindung).first()
    if conn is None:
        raise SystemExit(f"Verbindung {a.verbindung} gibt es nicht")
    print(f"Spaltenlauf gegen {conn.name}")

    mappings = []
    for mid, sql in SQL.items():
        sp = spalten(conn, sql)
        print(f"  {mid}: {len(sp)} Spalten")
        mappings.append(mapping(mid, sql, sp))

    vorlage = {
        "format_version": "1.0",
        "template_id": "jtl_preis_cockpit",
        "template_name": "JTL – Preis- & Marge-Cockpit",
        "description": ("Wo der Ertrag verloren geht: Rohertragsmarge im "
                        "Zeitverlauf, Artikel mit schleichendem Margenverfall "
                        "samt Ursache, Verkäufe unter Einkaufspreis, "
                        "Kalkulation gegen die Mindestmarge, gestiegene "
                        "Einkaufspreise und die Marge je Kunde."),
        "category": "jtl-reporting",
        "version": VERSION,
        "author": "Datenmonster",
        "hinweise": HINWEISE,
        "config_required": [{"key": "connection_jtl",
                             "label": "JTL-Datenbankverbindung (MS SQL Server)",
                             "type": "connection", "default": ""}],
        "datasets": [],
        "mappings": mappings,
        "pipelines": [],
        "forms": [{"name": "Preis- & Marge-Cockpit", "schema": formular(),
                   "portal_config": {}}],
        "knowledge": WISSEN,
    }
    with open(a.ziel, "w", encoding="utf-8") as f:
        json.dump(vorlage, f, ensure_ascii=False, indent=1)
    print(f"geschrieben: {a.ziel} ({len(mappings)} Mappings)")


if __name__ == "__main__":
    main()
