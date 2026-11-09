"""
Spielt jede Knotenart des visuellen Mapping-Editors einmal von vorn bis hinten durch.

Hintergrund (09.11.2026): Alle 297 Mappings der JTL-Vorlagen sind reine
SQL-Mappings. Die visuellen Knoten – Join, Aggregation, Nachschlagen, Formel,
Konstante, Weiche, Qualität … – nutzt keines unserer Produkte. Zwei davon (REST
und Nachschlagen) liefen bis September nie, ohne dass es jemand bemerkte. Dieser
Test baut jede Knotenart so auf, wie der Editor sie speichert, und prüft das
Ergebnis. Er läuft ohne Netz und ohne echte Datenbank: Datasets sind
DataFrames, die SQL-Verbindung ist SQLite im Speicher.

Lauf:  docker compose exec -T backend python tests/test_mapping_knoten.py
"""
import sys
sys.path.insert(0, "/app")

import pandas as pd  # noqa: E402
import sqlalchemy as sa  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.services import mapping_service  # noqa: E402

FEHLER = []


def pruefe(name, bedingung, extra=""):
    print(("  OK   " if bedingung else "  FAIL ") + name + (f"  [{extra}]" if not bedingung else ""))
    if not bedingung:
        FEHLER.append(name)


# ── Testdaten ──────────────────────────────────────────────────────────────────

KUNDEN = pd.DataFrame([
    {"kKunde": 1, "cName": "Müller GmbH", "cPLZ": "40210", "cMail": "info@mueller.de"},
    {"kKunde": 2, "cName": "Schmidt KG", "cPLZ": "1234", "cMail": "kaputt"},
    {"kKunde": 3, "cName": "Ohne Umsatz AG", "cPLZ": "80331", "cMail": "a@b.de"},
])
RECHNUNGEN = pd.DataFrame([
    {"kRechnung": 10, "kKunde": 1, "fBetrag": 100.0, "dDatum": "2026-01-15"},
    {"kRechnung": 11, "kKunde": 1, "fBetrag": 50.0, "dDatum": "2026-02-01"},
    {"kRechnung": 12, "kKunde": 2, "fBetrag": 30.0, "dDatum": "2026-02-10"},
    {"kRechnung": 13, "kKunde": 9, "fBetrag": 7.0, "dDatum": "2026-03-01"},   # Kunde fehlt
])
LEER = pd.DataFrame(columns=["x"])

DATASETS = {1: KUNDEN, 2: RECHNUNGEN, 3: LEER}
NAMEN = {1: "Kunden", 2: "Rechnungen", 3: "Leer"}


class _Connector:
    def __init__(self, df):
        self.df = df

    def supports_pushdown(self):
        return False

    def fetch_full(self):
        return self.df.copy()

    def fetch_preview(self, limit=50):
        return self.df.head(limit).copy()


mapping_service.get_connector = lambda ds_id: _Connector(DATASETS[ds_id])

ENGINE = sa.create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
with ENGINE.begin() as con:
    con.execute(sa.text("CREATE TABLE bonus (kKunde INTEGER, fBonus REAL, cStufe TEXT)"))
    con.execute(sa.text("INSERT INTO bonus VALUES (1, 5.0, 'Gold'), (2, 1.0, 'Silber')"))
mapping_service._get_sql_engine = lambda conn_id: ENGINE


def canvas(*ids):
    return [{"id": f"ds_{i}", "dataset_id": i, "dataset_name": NAMEN[i]} for i in ids]


def v(quelle, feld, ziel=None, **transformer):
    """Verbindung, wie der Editor sie speichert."""
    t = {"type": "direct", "source_field": feld}
    t.update(transformer)
    return {"source_dataset_id": quelle, "source_field": feld, "target_field": ziel or feld, "transformer": t}


def lauf(**kw):
    kw.setdefault("joins", [])
    kw.setdefault("preview_rows", 50)
    return mapping_service.execute_mapping(**kw)


# ── 1. Ein Dataset, direkte Zuordnung ─────────────────────────────────────────
print("1. Ein Dataset")
r = lauf(canvas_nodes=canvas(1), connections=[v(1, "kKunde"), v(1, "cName", "Name")])
pruefe("keine Fehler", not r["errors"], r["errors"])
pruefe("Spalten", r["columns"] == ["kKunde", "Name"], r["columns"])
pruefe("3 Zeilen", len(r["rows"]) == 3, len(r["rows"]))
pruefe("Umbenennung greift", r["rows"][0]["Name"] == "Müller GmbH", r["rows"][0])

# ── 2. Join ────────────────────────────────────────────────────────────────────
print("2. Join Kunden ⋈ Rechnungen")
join = {"left_dataset_id": 1, "right_dataset_id": 2, "left_field": "kKunde", "right_field": "kKunde"}
r = lauf(canvas_nodes=canvas(1, 2), joins=[dict(join, join_type="INNER JOIN")],
         connections=[v(1, "cName"), v(2, "kRechnung"), v(2, "fBetrag")])
pruefe("INNER: keine Fehler", not r["errors"], r["errors"])
pruefe("INNER: 3 Zeilen", len(r["rows"]) == 3, len(r["rows"]))
pruefe("INNER: Werte beider Seiten",
       {(z["cName"], z["kRechnung"]) for z in r["rows"]} == {("Müller GmbH", 10), ("Müller GmbH", 11), ("Schmidt KG", 12)},
       r["rows"])
r = lauf(canvas_nodes=canvas(1, 2), joins=[dict(join, join_type="LEFT JOIN")],
         connections=[v(1, "cName"), v(2, "kRechnung")])
pruefe("LEFT: Kunde ohne Rechnung bleibt, Lücke ist leer (nicht NaN)",
       any(z["cName"] == "Ohne Umsatz AG" and z["kRechnung"] is None for z in r["rows"]), r["rows"])
pruefe("LEFT: Ganzzahl bleibt Ganzzahl", r["rows"][0]["kRechnung"] == 10 and not isinstance(r["rows"][0]["kRechnung"], float),
       repr(r["rows"][0]["kRechnung"]))

r = lauf(canvas_nodes=canvas(1, 2), joins=[dict(join, join_type="LEFT ANTI JOIN")],
         connections=[v(1, "kKunde"), v(1, "cName")])
pruefe("LEFT ANTI: nur Kunde ohne Rechnung", [z["cName"] for z in r["rows"]] == ["Ohne Umsatz AG"], r["rows"])
r = lauf(canvas_nodes=canvas(1, 2), joins=[dict(join, join_type="RIGHT ANTI JOIN")],
         connections=[v(2, "kRechnung")])
pruefe("RIGHT ANTI: nur Rechnung ohne Kunde", [z["kRechnung"] for z in r["rows"]] == [13], r["rows"])

# ── 3. Filter und Sortierung am Dataset ───────────────────────────────────────
print("3. Filter und Sortierung")
cn = canvas(2)
cn[0]["filters"] = {"fBetrag": "> 20"}
cn[0]["sorts"] = [{"field": "fBetrag", "dir": "asc"}]
r = lauf(canvas_nodes=cn, connections=[v(2, "kRechnung"), v(2, "fBetrag")])
pruefe("keine Fehler", not r["errors"], r["errors"])
pruefe("Filter > 20", [z["fBetrag"] for z in r["rows"]] == [30.0, 50.0, 100.0], r["rows"])

# ── 4. Konstante und Formular-Parameter ───────────────────────────────────────
print("4. Konstante und Parameter")
r = lauf(canvas_nodes=canvas(1), connections=[v(1, "kKunde"), v("__const__k1", "Quelle"), v("__params__p1", "Jahr")],
         constant_nodes=[{"id": "k1", "const_type": "static_text", "const_value": "Wawi", "output_field": "Quelle"}],
         param_nodes=[{"id": "p1", "fields": [{"name": "Jahr", "type": "number", "default": "2025"}]}],
         run_params={"Jahr": "2026"})
pruefe("keine Fehler", not r["errors"], r["errors"])
pruefe("Konstante", r["rows"][0].get("Quelle") == "Wawi", r["rows"][0])
pruefe("Parameter aus dem Lauf", r["rows"][0].get("Jahr") == 2026.0, r["rows"][0])

# ── 5. Transform-Knoten (Zahl formatieren) ────────────────────────────────────
print("5. Transform-Knoten")
r = lauf(canvas_nodes=canvas(2), connections=[v(2, "kRechnung"), v("__transform__t1", "BetragText")],
         transform_nodes=[{"id": "t1", "type": "number_format", "inputs": [{"source_field": "fBetrag"}],
                           "config": {"decimals": 2}, "output_field": "BetragText"}])
pruefe("keine Fehler", not r["errors"], r["errors"])
pruefe("100 → '100,00'", r["rows"][0].get("BetragText") == "100,00", r["rows"][0])

# ── 6. Berechnung: Formel je Zeile und Fenster ────────────────────────────────
print("6. Berechnung")
r = lauf(canvas_nodes=canvas(2), connections=[v(2, "kRechnung"), v(2, "fBetrag"), v("__calc__c1", "Brutto")],
         calc_nodes=[{"id": "c1", "calc_type": "formula", "output_field": "Brutto",
                      "formula_parts": [{"type": "field", "value": "fBetrag"}, {"op": "*"}, {"type": "number", "value": "1.19"}]}])
pruefe("Formel: keine Fehler", not r["errors"], r["errors"])
pruefe("Formel: 100 × 1,19", abs((r["rows"][0].get("Brutto") or 0) - 119.0) < 1e-6, r["rows"][0])
r = lauf(canvas_nodes=canvas(2), connections=[v(2, "kRechnung"), v(2, "fBetrag")],
         calc_nodes=[{"id": "c2", "calc_type": "cumsum", "input_field": "fBetrag", "output_field": "Laufend",
                      "order_field": "kRechnung"}])
pruefe("Fenster: keine Fehler", not r["errors"], r["errors"])
pruefe("Fenster: kumulierte Summe", [z.get("Laufend") for z in r["rows"]] == [100.0, 150.0, 180.0, 187.0], r["rows"])
pruefe("Fenster: Ergebnisspalte steht in columns", "Laufend" in r["columns"], r["columns"])

# ── 7. Ausdruck ────────────────────────────────────────────────────────────────
print("7. Ausdruck")
r = lauf(canvas_nodes=canvas(1), connections=[v(1, "kKunde"), v("__expr__e1", "NameGross")],
         expr_nodes=[{"id": "e1", "output_fields": [{"name": "NameGross", "expr": "UPPER({cName})"}]}])
pruefe("keine Fehler", not r["errors"], r["errors"])
pruefe("UPPER (groß geschrieben)", r["rows"][0].get("NameGross") == "MÜLLER GMBH", r["rows"][0])
r = lauf(canvas_nodes=canvas(1), connections=[v(1, "kKunde"), v("__expr__e1", "Kurz")],
         expr_nodes=[{"id": "e1", "output_fields": [{"name": "Kurz", "expr": "substr(lower({cName}), 0, 3)"}]}])
pruefe("klein geschrieben, verschachtelt", r["rows"][0].get("Kurz") == "mül", r["rows"][0])
r = lauf(canvas_nodes=canvas(1), connections=[v(1, "kKunde"), v("__expr__e1", "X")],
         expr_nodes=[{"id": "e1", "output_fields": [{"name": "X", "expr": "gibtsnicht({cName})"}]}])
pruefe("unbekannte Funktion: Meldung nennt die verfügbaren", r["errors"] and "Verfügbar: " in r["errors"][0], r["errors"])

# ── 8. Datenqualität ───────────────────────────────────────────────────────────
print("8. Datenqualität")
r = lauf(canvas_nodes=canvas(1), connections=[v(1, "kKunde"), v(1, "cPLZ"),
                                             v("__quality__q1", "__dq_valid__", "Gueltig"),
                                             v("__quality__q1", "__dq_errors__", "Pruefung")],
         quality_nodes=[{"id": "q1", "rules": [{"field": "cPLZ", "type": "plz_de"},
                                               {"field": "cMail", "type": "email", "message": "Mail ungültig"}]}])
pruefe("keine Fehler", not r["errors"], r["errors"])
z2 = next((z for z in r["rows"] if z.get("kKunde") == 2), {})
pruefe("Ergebnis der Prüfung kommt in der Ausgabe an",
       z2.get("Gueltig") is False and "Mail ungültig" in (z2.get("Pruefung") or ""), z2)
pruefe("gültige Zeile", r["rows"][0].get("Gueltig") is True and not r["rows"][0].get("Pruefung"), r["rows"][0])

# ── 9. Aggregation ─────────────────────────────────────────────────────────────
print("9. Aggregation")
agg = [{"id": "g1", "fields": [{"func": "group_by", "input_field": "kKunde", "output_field": "kKunde"},
                               {"func": "sum", "input_field": "fBetrag", "output_field": "Umsatz"},
                               {"func": "count", "input_field": "kRechnung", "output_field": "Anzahl"}]}]
r = lauf(canvas_nodes=canvas(2), agg_nodes=agg,
         connections=[v("__agg__g1", "kKunde"), v("__agg__g1", "Umsatz"), v("__agg__g1", "Anzahl")])
pruefe("keine Fehler", not r["errors"], r["errors"])
pruefe("3 Gruppen", len(r["rows"]) == 3, r["rows"])
k1 = next((z for z in r["rows"] if str(z.get("kKunde")) == "1"), {})
pruefe("Summe Kunde 1", k1.get("Umsatz") == 150.0 and k1.get("Anzahl") == 2, k1)
pruefe("Gruppenschlüssel bleibt Zahl", k1.get("kKunde") == 1, repr(k1.get("kKunde")))

# ── 10. Nachschlagen in einem anderen Dataset ─────────────────────────────────
print("10. Nachschlagen")
lk = [{"id": "l1", "input_field": "kKunde", "lookup_dataset_id": 1, "lookup_key_col": "kKunde", "on_missing": "null",
       "output_mappings": [{"lookup_col": "cName", "output_field": "Kunde"}]}]
r = lauf(canvas_nodes=canvas(2), connections=[v(2, "kRechnung"), v("__lookup__l1", "Kunde")], lookup_nodes=lk)
pruefe("keine Fehler", not r["errors"], r["errors"])
pruefe("Treffer", r["rows"][0].get("Kunde") == "Müller GmbH", r["rows"][0])
pruefe("kein Treffer → leer", r["rows"][3].get("Kunde") is None, r["rows"][3])

# ── 11. SQL je Zeile (Skalar, Nachschlagen, Sammel-IN) ────────────────────────
print("11. SQL-Knoten je Zeile")
r = lauf(canvas_nodes=canvas(1), connections=[v(1, "kKunde"), v("__sql__s1", "Bonus")],
         sql_nodes=[{"id": "s1", "mode": "scalar", "connection_id": 1, "output_field": "Bonus",
                     "sql": "SELECT fBonus FROM bonus WHERE kKunde = {kKunde}"}])
pruefe("Skalar: keine Fehler", not r["errors"], r["errors"])
pruefe("Skalar: Wert", r["rows"][0].get("Bonus") == 5.0, r["rows"][0])
for sub in ("row_by_row", "batch_in"):
    r = lauf(canvas_nodes=canvas(1), connections=[v(1, "kKunde"), v("__sql__s2", "cStufe")],
             sql_nodes=[{"id": "s2", "mode": "lookup", "lookup_sub_mode": sub, "connection_id": 1,
                         "sql": "SELECT kKunde, cStufe FROM bonus WHERE kKunde " + ("IN :k" if sub == "batch_in" else "= :k"),
                         "param_mappings": [{"param": "k", "source_field": "kKunde"}], "output_fields": ["cStufe"]}])
    pruefe(f"Lookup {sub}: keine Fehler", not r["errors"], r["errors"])
    pruefe(f"Lookup {sub}: Gold/Silber/leer", [z.get("cStufe") for z in r["rows"]] == ["Gold", "Silber", None], r["rows"])

# ── 12. Weiche (Switch) ────────────────────────────────────────────────────────
print("12. Weiche")
sw = [{"id": "w1", "output_field": "Zweig", "branches": [
    {"condition": "has_rows", "dataset_id": 3, "source_dataset_id": 3, "label": "Wenn Daten vorhanden"},
    {"condition": "always", "source_dataset_id": 2, "label": "Sonst"}]}]
r = lauf(canvas_nodes=canvas(1), connections=[v(1, "kKunde"), v("__switch__w1", "Zweig"), v("__switch__w1", "Zweig__fBetrag")],
         switch_nodes=sw)
pruefe("keine Fehler", not r["errors"], r["errors"])
pruefe("Zweig gewählt (Fallback, weil Dataset 3 leer)", r["rows"][0].get("Zweig") == "Sonst", r["rows"][0])
pruefe("Zweig-Spalte kommt an", r["rows"][0].get("Zweig__fBetrag") == 100.0, r["rows"][0])

# ── 13. Python ─────────────────────────────────────────────────────────────────
print("13. Python")
r = lauf(canvas_nodes=canvas(2), connections=[v(2, "kRechnung"), v(2, "fBetrag"), v("__python__py1", "Klasse")],
         python_nodes=[{"id": "py1", "output_fields": [{"name": "Klasse"}],
                        "script": "row['Klasse'] = 'A' if row.get('fBetrag', 0) >= 50 else 'B'\nreturn row"}])
pruefe("keine Fehler", not r["errors"], r["errors"])
pruefe("Klasse A/B", [z.get("Klasse") for z in r["rows"]] == ["A", "A", "B", "B"], r["rows"])

# ── 14. Transformer an der Verbindung ─────────────────────────────────────────
print("14. Transformer an der Verbindung")
r = lauf(canvas_nodes=canvas(2), connections=[
    v(2, "kRechnung"),
    v(2, "dDatum", "Datum", type="date", date_input_format="YYYY-MM-DD", date_output_format="DD.MM.YYYY"),
    v(2, "fBetrag", "Netto2", type="formula", formula="{fBetrag} * 2"),
    v(2, "fBetrag", "Fest", type="constant", constant_value="X")])
pruefe("keine Fehler", not r["errors"], r["errors"])
pruefe("Datum umformatiert", r["rows"][0].get("Datum") == "15.01.2026", r["rows"][0])
pruefe("Formel", r["rows"][0].get("Netto2") == 200.0, r["rows"][0])
pruefe("Konstante", r["rows"][0].get("Fest") == "X", r["rows"][0])

# ── 15. Sortierung und Limit am Ziel ───────────────────────────────────────────
print("15. Sortierung und Limit am Ziel")
r = lauf(canvas_nodes=canvas(2), connections=[v(2, "kRechnung"), v(2, "fBetrag")],
         target_options={"sort_fields": [{"field": "fBetrag", "dir": "desc"}], "row_limit": 2})
pruefe("keine Fehler", not r["errors"], r["errors"])
pruefe("absteigend, 2 Zeilen", [z["fBetrag"] for z in r["rows"]] == [100.0, 50.0], r["rows"])

# ── 16. Alles zusammen ─────────────────────────────────────────────────────────
print("16. Kette: Join → Aggregation → Nachschlagen → Ausdruck → Qualität")
r = lauf(canvas_nodes=canvas(1, 2), joins=[dict(join, join_type="INNER JOIN")],
         agg_nodes=[{"id": "g1", "fields": [{"func": "group_by", "input_field": "kKunde", "output_field": "kKunde"},
                                            {"func": "sum", "input_field": "fBetrag", "output_field": "Umsatz"}]}],
         lookup_nodes=lk,
         expr_nodes=[{"id": "e1", "output_fields": [{"name": "Zeile", "expr": "CONCAT({Kunde}, ': ', {Umsatz})"}]}],
         connections=[v("__agg__g1", "kKunde"), v("__agg__g1", "Umsatz"), v("__lookup__l1", "Kunde"), v("__expr__e1", "Zeile")])
pruefe("keine Fehler", not r["errors"], r["errors"])
pruefe("2 Kunden mit Umsatz", len(r["rows"]) == 2, r["rows"])
pruefe("Text zusammengesetzt", any(z.get("Zeile") == "Müller GmbH: 150.0" for z in r["rows"]), r["rows"])

# ── 17. Hinweise statt stiller Fallen ─────────────────────────────────────────
print("17. Hinweise")
SQLK = [{"id": "sq", "mode": "transform", "connection_id": 1, "sql": "SELECT kKunde, fBonus FROM bonus"}]
r = lauf(canvas_nodes=[], sql_nodes=SQLK, connections=[v("__sql__sq", "kKunde"), v("__sql__sq", "fBonsu", "Bonus")])
pruefe("Tippfehler in der Quellspalte → Hinweis", any("fBonsu" in w for w in r.get("warnings", [])), r.get("warnings"))
pruefe("… aber kein Fehler (Cockpit läuft weiter)", not r["errors"], r["errors"])
r = lauf(canvas_nodes=[], sql_nodes=[dict(SQLK[0], mode="scalar")], connections=[v("__sql__sq", "kKunde")])
pruefe("SQL-Knoten im falschen Modus → sagt, was zu tun ist", r["errors"] and "Transform" in r["errors"][0], r["errors"])
r = lauf(canvas_nodes=canvas(2), agg_nodes=[{"id": "g9", "fields": [{"func": "group_by", "input_field": "kKunde"}]}],
         connections=[v("__agg__g9", "kKunde")])
pruefe("Aggregation ohne Rechenfeld → Hinweis", any("g9" in w for w in r.get("warnings", [])), r.get("warnings"))

print()
print(f"{len(FEHLER)} Fehler" if FEHLER else "Alle Prüfungen bestanden")
sys.exit(1 if FEHLER else 0)
