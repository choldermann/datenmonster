"""
Ein Bericht, wie ihn ein Anwender im visuellen Editor baut – ohne eine Zeile SQL –
einmal durch die echte API: Dateien hochladen, Mapping speichern, wieder laden,
Vorschau, Export als Excel und CSV, Lauf wie aus Formular oder Zeitplan.

test_mapping_knoten.py prüft die Rechenlogik je Knoten. Dieser Test prüft den
Weg drumherum: ob jede Knotenart gespeichert und wieder geladen wird, ob die
Vorschau dieselben Zahlen zeigt wie der Export und ob Excel/CSV die Werte
(Wahrheitswerte, Lücken, Ganzzahlen) richtig schreiben.

Bericht „Umsatz je Kunde“:
  Kunden.csv ⟕ Rechnungen.csv (LEFT JOIN) → Aggregation je Kunde (Summe, Anzahl)
  → Formel Brutto → Ausdruck Kategorie → Konstante Stand → Parameter Jahr
  → Qualitätsprüfung E-Mail → Ziel Excel bzw. CSV, absteigend nach Umsatz

Lauf (gegen das laufende Backend im Container, räumt hinterher auf):
  docker exec -w /app datenmonster-backend python tests/test_mapping_szenario.py
"""
import io
import sys
sys.path.insert(0, "/app")

import httpx  # noqa: E402
import pandas as pd  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.core.security import token_fuer  # noqa: E402
from app.models.user import User  # noqa: E402

BASIS = "http://localhost:8000"
FEHLER = []


def pruefe(name, bedingung, extra=""):
    print(("  OK   " if bedingung else "  FAIL ") + name + (f"  [{str(extra)[:300]}]" if not bedingung else ""))
    if not bedingung:
        FEHLER.append(name)


db = SessionLocal()
admin = db.query(User).filter(User.is_admin == True).order_by(User.id).first()  # noqa: E712
H = {"Authorization": f"Bearer {token_fuer(admin)}"}
c = httpx.Client(base_url=BASIS, headers=H, timeout=120)

ANGELEGT = {"mapping": None, "datasets": [], "projekt": None}

KUNDEN_CSV = (
    "kKunde,cName,cMail\n"
    "1,Müller GmbH,info@mueller.de\n"
    "2,Schmidt KG,kaputt\n"
    "3,Ohne Umsatz AG,a@b.de\n"
)
RECHNUNGEN_CSV = (
    "kRechnung,kKunde,fBetrag\n"
    "10,1,100.00\n"
    "11,1,50.00\n"
    "12,2,30.00\n"
)


def v(quelle, feld, ziel=None):
    return {"source_dataset_id": quelle, "source_field": feld, "target_field": ziel or feld,
            "transformer": {"type": "direct", "source_field": feld}}


try:
    # ── 1. Projekt und Dateien ────────────────────────────────────────────────
    print("1. Projekt und Dateien")
    r = c.post("/api/projects/", json={"name": "Szenario-Test visueller Editor", "description": "wird gelöscht"})
    pruefe("Projekt angelegt", r.status_code == 200, r.text)
    pid = r.json()["id"]
    ANGELEGT["projekt"] = pid

    ids = {}
    for name, inhalt in (("Kunden", KUNDEN_CSV), ("Rechnungen", RECHNUNGEN_CSV)):
        r = c.post("/api/datasets/upload", data={"name": name, "project_id": str(pid)},
                   files={"file": (f"{name}.csv", inhalt.encode(), "text/csv")})
        pruefe(f"{name}.csv hochgeladen", r.status_code == 200, r.text)
        ids[name] = r.json()["id"]
        ANGELEGT["datasets"].append(ids[name])
    K, R = ids["Kunden"], ids["Rechnungen"]

    # ── 2. Mapping so speichern, wie der Editor es tut ────────────────────────
    print("2. Mapping speichern und wieder laden")
    felder = [
        v(f"__agg__g1", "kKunde", "Kundennr"),
        v(f"__agg__g1", "cName", "Kunde"),
        v(f"__agg__g1", "Umsatz"),
        v(f"__agg__g1", "Anzahl"),
        v("__calc__c1", "Brutto"),
        v("__expr__e1", "Kategorie"),
        v("__const__k1", "Stand"),
        v("__params__p1", "Jahr"),
        v("__quality__q1", "__dq_valid__", "MailOk"),
    ]
    knoten = {
        "canvas_nodes": [{"id": f"ds_{K}", "dataset_id": K, "dataset_name": "Kunden", "x": 40, "y": 40},
                         {"id": f"ds_{R}", "dataset_id": R, "dataset_name": "Rechnungen", "x": 40, "y": 300}],
        "joins": [{"left_dataset_id": K, "right_dataset_id": R, "left_field": "kKunde",
                   "right_field": "kKunde", "join_type": "LEFT JOIN"}],
        "agg_nodes": [{"id": "g1", "x": 400, "y": 40, "fields": [
            {"func": "group_by", "input_field": "kKunde", "output_field": "kKunde"},
            {"func": "group_by", "input_field": "cName", "output_field": "cName"},
            {"func": "sum", "input_field": "fBetrag", "output_field": "Umsatz"},
            {"func": "count", "input_field": "kRechnung", "output_field": "Anzahl"}]}],
        "calc_nodes": [{"id": "c1", "x": 700, "y": 40, "calc_type": "formula", "output_field": "Brutto",
                        "formula_parts": [{"type": "field", "value": "Umsatz"}, {"op": "*"},
                                          {"type": "number", "value": "1.19"}]}],
        "expr_nodes": [{"id": "e1", "x": 700, "y": 200, "label": "Expression", "output_fields": [
            {"name": "Kategorie", "expr": "if_({Umsatz} >= 100, 'A-Kunde', 'B-Kunde')"}]}],
        "constant_nodes": [{"id": "k1", "x": 700, "y": 350, "const_type": "static_text",
                            "const_value": "Bericht", "output_field": "Stand"}],
        "param_nodes": [{"id": "p1", "x": 700, "y": 450, "label": "Formular-Parameter",
                         "fields": [{"name": "Jahr", "type": "number", "default": "2026"}]}],
        "quality_nodes": [{"id": "q1", "x": 700, "y": 550, "label": "Datenqualität",
                           "rules": [{"field": "cMail", "type": "email", "message": "E-Mail ungültig"}]}],
    }
    ziel = {"id": "t1", "name": "Umsatz je Kunde", "target_type": "xlsx", "fields": felder,
            "target_options": {"sort_fields": [{"field": "Umsatz", "dir": "desc"}]}}
    r = c.post("/api/mappings/", json={"name": "Szenario: Umsatz je Kunde", "project_id": pid,
                                       "targets": [ziel], **knoten})
    pruefe("Mapping angelegt", r.status_code == 200, r.text)
    mid = r.json()["id"]
    ANGELEGT["mapping"] = mid

    geladen = c.get(f"/api/mappings/{mid}").json()
    def gleich(art, gespeichert, erwartet):
        # Datasets ergänzt der Server um Spalteninfos – verglichen wird, was der Editor schickt
        if art == "canvas_nodes":
            return [{k: n.get(k) for k in e} for n, e in zip(gespeichert or [], erwartet)] == erwartet
        return gespeichert == erwartet

    for art, liste in knoten.items():
        pruefe(f"{art} gespeichert", gleich(art, geladen.get(art), liste), geladen.get(art))
    pruefe("Ziel gespeichert", (geladen.get("targets") or [{}])[0].get("fields") == felder, geladen.get("targets"))

    # Zweites Speichern (PUT) – der Editor speichert danach immer per PUT
    r = c.put(f"/api/mappings/{mid}", json={"name": "Szenario: Umsatz je Kunde", "project_id": pid,
                                            "targets": [ziel], **knoten})
    pruefe("erneut gespeichert", r.status_code == 200, r.text)
    geladen = c.get(f"/api/mappings/{mid}").json()
    pruefe("nach PUT alle Knoten noch da", all(gleich(a, geladen.get(a), l) for a, l in knoten.items()),
           [a for a, l in knoten.items() if not gleich(a, geladen.get(a), l)])

    # ── 3. Vorschau ───────────────────────────────────────────────────────────
    print("3. Vorschau")
    anfrage = {**{a: geladen.get(a) for a in knoten}, "mapping_id": mid, "targets": geladen["targets"],
               "run_params": {"Jahr": "2025"}}
    r = c.post("/api/mappings/preview", json=anfrage)
    pruefe("Vorschau antwortet", r.status_code == 200, r.text)
    vs = r.json()
    pruefe("keine Fehler", not vs.get("errors"), vs.get("errors"))
    pruefe("keine Hinweise", not vs.get("warnings"), vs.get("warnings"))
    zeilen = {z["Kundennr"]: z for z in vs.get("rows", [])}
    pruefe("drei Kunden", len(zeilen) == 3, vs.get("rows"))
    m = zeilen.get(1, {})
    pruefe("Müller: Umsatz 150, 2 Rechnungen", m.get("Umsatz") == 150 and m.get("Anzahl") == 2, m)
    pruefe("Müller: Brutto 178,50", abs((m.get("Brutto") or 0) - 178.5) < 1e-6, m)
    pruefe("Müller: A-Kunde", m.get("Kategorie") == "A-Kunde", m)
    pruefe("Konstante und Parameter", m.get("Stand") == "Bericht" and m.get("Jahr") == 2025, m)
    pruefe("Schmidt: E-Mail ungültig erkannt", zeilen.get(2, {}).get("MailOk") is False, zeilen.get(2))
    o = zeilen.get(3, {})
    pruefe("Kunde ohne Rechnung: Umsatz 0, 0 Rechnungen", o.get("Umsatz") == 0 and o.get("Anzahl") == 0, o)
    pruefe("absteigend nach Umsatz", [z["Kundennr"] for z in vs.get("rows", [])] == [1, 2, 3], vs.get("rows"))
    pruefe("Schmidt: Brutto 35,7 ohne Rundungsreste", zeilen.get(2, {}).get("Brutto") == 35.7, zeilen.get(2))
    # Vorschau ohne Laufwerte, wie im Editor: Parameter nimmt seinen Standardwert
    r = c.post("/api/mappings/preview", json={k: v for k, v in anfrage.items() if k != "run_params"})
    pruefe("ohne Laufwert gilt der Standardwert", (r.json().get("rows") or [{}])[0].get("Jahr") == 2026, r.json().get("rows", [None])[0])

    # ── 4. Export als Excel und CSV ───────────────────────────────────────────
    print("4. Export")
    from app.models.export_file import ExportFile
    for typ in ("xlsx", "csv"):
        z = dict(geladen["targets"][0], target_type=typ)
        r = c.post("/api/mappings/execute-download",
                   json={**{a: geladen.get(a) for a in knoten}, "mapping_id": mid, "targets": [z],
                         "run_params": {"Jahr": "2025"}})
        pruefe(f"{typ}: Export läuft", r.status_code == 200, r.text)
        if r.status_code != 200:
            continue
        ef = db.query(ExportFile).filter(ExportFile.id == r.json()["export_id"]).first()
        df = pd.read_excel(ef.file_path) if typ == "xlsx" else pd.read_csv(ef.file_path, sep=None, engine="python", encoding="utf-8-sig")
        pruefe(f"{typ}: Spalten wie in der Vorschau", list(df.columns) == vs["columns"], list(df.columns))
        pruefe(f"{typ}: drei Zeilen", len(df) == 3, len(df))
        erste = df.iloc[0].to_dict()
        pruefe(f"{typ}: Umsatz Müller", float(str(erste.get("Umsatz")).replace(",", ".")) == 150.0, erste)
        pruefe(f"{typ}: Kundennr ist Ganzzahl (nicht 1.0)", str(erste.get("Kundennr")) == "1", erste)
        ef_pfad = ef.file_path
        db.delete(ef); db.commit()
        import os
        if os.path.exists(ef_pfad):
            os.remove(ef_pfad)

    # ── 5. Lauf wie aus Formular, Pipeline oder Zeitplan ──────────────────────
    print("5. Lauf über das gespeicherte Mapping")
    from app.models.mapping import Mapping
    from app.services.mapping_service import MappingContext, run_mapping_object
    db.expire_all()
    ctx = MappingContext.from_orm(db.get(Mapping, mid))
    ctx.run_params = {"Jahr": "2024"}
    erg = run_mapping_object(ctx, preview_rows=50)
    pruefe("keine Fehler", not erg.get("errors"), erg.get("errors"))
    ez = {z["Kundennr"]: z for z in erg.get("rows", [])}
    pruefe("gleiche Zahlen wie Vorschau", ez.get(1, {}).get("Umsatz") == 150 and ez.get(1, {}).get("Jahr") == 2024, ez.get(1))

finally:
    if "--behalten" in sys.argv:
        print(f"Behalten: Projekt {ANGELEGT['projekt']}, Mapping {ANGELEGT['mapping']} – Editor: /mappings/{ANGELEGT['mapping']}")
        ANGELEGT = {"mapping": None, "datasets": [], "projekt": None}
    print("Aufräumen")
    if ANGELEGT["mapping"]:
        c.delete(f"/api/mappings/{ANGELEGT['mapping']}")
    for d in ANGELEGT["datasets"]:
        c.delete(f"/api/datasets/{d}")
    if ANGELEGT["projekt"]:
        c.delete(f"/api/projects/{ANGELEGT['projekt']}")

print()
print(f"{len(FEHLER)} Fehler" if FEHLER else "Alle Prüfungen bestanden")
sys.exit(1 if FEHLER else 0)
