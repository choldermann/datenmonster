"""
Prüft die REST- und Lookup-Knoten im Mapping.

Beide liefen bis 2026-09 nie: sie arbeiteten auf `output_rows`, die an ihrer
Stelle noch leer war. Kein Fehler, kein Hinweis – das Mapping lieferte still
Zeilen ohne ihre Felder. Die Tests laufen ohne Netz und ohne Datenbank: Quelle,
HTTP-Aufruf, Protokoll und Warten sind ersetzt.

Lauf:  docker compose exec -T backend python tests/test_rest_knoten.py
"""
import sys
import time
from urllib.parse import urlparse, parse_qs
sys.path.insert(0, "/app")

import pandas as pd  # noqa: E402

from app.services import mapping_service, rest_service, db_logger  # noqa: E402

FEHLER = []


def pruefe(name, bedingung, extra=""):
    print(("  OK   " if bedingung else "  FAIL ") + name + (f"  [{extra}]" if not bedingung else ""))
    if not bedingung:
        FEHLER.append(name)


def leer(wert):
    return wert is None or (isinstance(wert, float) and wert != wert)


# ── Ersatz für Quelle, HTTP, Protokoll und Warten ─────────────────────────────

class Quelle:
    """Dataset-Ersatz: liefert immer denselben DataFrame."""
    def __init__(self, df):
        self.df = df

    def supports_pushdown(self):
        return False

    def fetch_preview(self, limit=None):
        return self.df.head(limit).copy()

    def fetch_full(self):
        return self.df.copy()


DATEN = {
    1: pd.DataFrame({
        "Auftrag":        ["A1", "A2", "A3", "A4"],
        "Trackingnummer": ["111", "222", "111", None],
    }),
    2: pd.DataFrame({
        "Auftrag": ["A1", "A2", "A3"],
        "Kunde":   ["Meyer", "Schulz", "Braun"],
    }),
}
mapping_service.get_connector = lambda ds_id: Quelle(DATEN[ds_id])

ANTWORT = {"111": {"status": "delivered", "returnFlag": True},
           "222": {"status": "delivered", "returnFlag": False}}
AUFRUFE, PAUSEN, FEHLER_BEI = [], [], set()


def falscher_aufruf(cfg, timeout=30, wiederholen=False):
    AUFRUFE.append(cfg)
    abfrage = parse_qs(urlparse(cfg["url"]).query)
    if "nummern" in abfrage:
        nummern = abfrage["nummern"][0].split(",")
        return {"ok": True, "status_code": 200,
                "json": {"shipments": [{"nr": n, **ANTWORT[n]} for n in nummern]}}
    nr = abfrage["trackingNumber"][0]
    if nr in FEHLER_BEI:
        return {"ok": False, "status_code": 429, "reason": "Too Many Requests", "json": None}
    return {"ok": True, "status_code": 200, "json": ANTWORT[nr]}


rest_service.execute_request = falscher_aufruf
db_logger.log_rest_aufruf = lambda *a, **k: None
db_logger.log_rest_zusammenfassung = lambda *a, **k: None
time.sleep = lambda sekunden: PAUSEN.append(sekunden)


VERBINDUNGEN = [
    {"source_dataset_id": 1,            "source_field": "Auftrag",     "target_field": "auftrag"},
    {"source_dataset_id": "__rest__r1", "source_field": "dhl_status",  "target_field": "status"},
    {"source_dataset_id": "__rest__r1", "source_field": "dhl_retoure", "target_field": "retoure"},
]


def knoten(**abweichend):
    k = {
        "id": "r1", "method": "GET", "mode": "single",
        "url": "https://api.test/track?trackingNumber={{Trackingnummer}}",
        "input_fields": [{"field": "Trackingnummer"}],
        "auth": {"type": "apikey", "key_name": "DHL-API-Key", "key_value": "geheim"},
        "response_mappings": [{"json_path": "status",     "output_field": "dhl_status"},
                              {"json_path": "returnFlag", "output_field": "dhl_retoure"}],
    }
    k.update(abweichend)
    return k


def lauf(rest_nodes=None, lookup_nodes=None, verbindungen=None, **extra):
    AUFRUFE.clear()
    PAUSEN.clear()
    res = mapping_service.execute_mapping(
        canvas_nodes=[{"dataset_id": 1, "dataset_name": "Sendungen"}],
        connections=verbindungen or VERBINDUNGEN, joins=[],
        rest_nodes=rest_nodes, lookup_nodes=lookup_nodes, **extra)
    return res, {r.get("auftrag"): r for r in res["rows"]}


print("\n── Einzeln: ein Aufruf je Wert, Ergebnis landet im Zielfeld ─")
res, z = lauf([knoten()])
pruefe("alle vier Zeilen kommen an", len(res["rows"]) == 4, res["rows"])
pruefe("A1 bekommt den Status", z["A1"]["status"] == "delivered", z["A1"])
pruefe("A1 bekommt das Retouren-Kennzeichen", z["A1"]["retoure"] == True, z["A1"])   # noqa: E712
pruefe("A2 ist keine Retoure", z["A2"]["retoure"] == False, z["A2"])                  # noqa: E712
pruefe("gleiche Nummer nur einmal abgefragt (2 statt 3 Aufrufe)", len(AUFRUFE) == 2, len(AUFRUFE))
pruefe("A3 nutzt die Antwort von A1", z["A3"]["retoure"] == True, z["A3"])            # noqa: E712
pruefe("ohne Trackingnummer kein Wert", leer(z["A4"]["status"]), z["A4"])
pruefe("keine Fehler", not res["errors"], res["errors"])

print("\n── Eingabefeld mit Dataset-Präfix ────────────────────────────")
res, z = lauf([knoten(input_fields=[{"field": "Sendungen.Trackingnummer"}],
                      url="https://api.test/track?trackingNumber={value}")])
pruefe("Präfix-Feld wird gefunden", z["A2"]["status"] == "delivered", z["A2"])

print("\n── Drosselung ───────────────────────────────────────────────")
res, z = lauf([knoten(pause_ms=5000)])
pruefe("Pause zwischen den Aufrufen, nicht davor (1 Pause bei 2 Aufrufen)", PAUSEN == [5.0], PAUSEN)

res, z = lauf([knoten(max_calls=1)])
pruefe("höchstens ein Aufruf", len(AUFRUFE) == 1, len(AUFRUFE))
pruefe("A1 ist abgefragt", z["A1"]["status"] == "delivered", z["A1"])
pruefe("A2 bleibt ohne Antwort", leer(z["A2"]["status"]), z["A2"])
pruefe("A3 bekommt die schon geholte Antwort trotzdem", z["A3"]["retoure"] == True, z["A3"])  # noqa: E712
pruefe("eine selbst gesetzte Grenze ist kein Fehler", not res["errors"], res["errors"])

res, z = lauf([knoten()], preview_rows=1)
pruefe("nur ausgegebene Zeilen lösen Aufrufe aus", len(AUFRUFE) == 1, len(AUFRUFE))

print("\n── Fehlerantwort ────────────────────────────────────────────")
FEHLER_BEI.add("222")
res, z = lauf([knoten(error_field="dhl_fehler")], verbindungen=VERBINDUNGEN + [
    {"source_dataset_id": "__rest__r1", "source_field": "dhl_fehler", "target_field": "fehler"}])
FEHLER_BEI.clear()
pruefe("Fehlertext im Fehlerfeld", "429" in str(z["A2"]["fehler"]), z["A2"])
pruefe("Status bleibt leer", leer(z["A2"]["status"]), z["A2"])
pruefe("Fehler im Laufprotokoll", any("REST-Knoten" in e for e in res["errors"]), res["errors"])
pruefe("die gute Zeile ist unberührt", z["A1"]["status"] == "delivered" and leer(z["A1"]["fehler"]), z["A1"])

print("\n── Gebündelt: ein Aufruf für alle Werte ─────────────────────")
res, z = lauf([knoten(mode="batch", url="https://api.test/sammel?nummern={{ids}}",
                      data_path="shipments", join_key="nr")])
pruefe("genau ein Sammelaufruf", len(AUFRUFE) == 1, len(AUFRUFE))
pruefe("A2 aus der Sammelantwort", z["A2"]["retoure"] == False, z["A2"])              # noqa: E712
pruefe("A3 aus der Sammelantwort", z["A3"]["retoure"] == True, z["A3"])               # noqa: E712

print("\n── Lookup-Knoten ────────────────────────────────────────────")
res, z = lauf(lookup_nodes=[{
    "id": "l1", "input_field": "Auftrag", "lookup_dataset_id": 2, "lookup_key_col": "Auftrag",
    "on_missing": "skip", "output_mappings": [{"lookup_col": "Kunde", "output_field": "kunde"}]}],
    verbindungen=[{"source_dataset_id": 1, "source_field": "Auftrag", "target_field": "auftrag"},
                  {"source_dataset_id": "__lookup__l1", "source_field": "kunde", "target_field": "kunde"}])
pruefe("Lookup-Wert kommt an", z.get("A2", {}).get("kunde") == "Schulz", res["rows"])
pruefe("on_missing=skip entfernt A4", "A4" not in z and len(res["rows"]) == 3, res["rows"])

print("\n── Ohne Knoten bleibt alles wie es war ──────────────────────")
res, z = lauf(verbindungen=[{"source_dataset_id": 1, "source_field": "Auftrag", "target_field": "auftrag"},
                            {"source_dataset_id": 1, "source_field": "Trackingnummer", "target_field": "nr"}])
pruefe("Quellfelder unverändert", [r["nr"] for r in res["rows"]][:3] == ["111", "222", "111"], res["rows"])
pruefe("kein Aufruf", not AUFRUFE, len(AUFRUFE))

print("\n── Anmeldung ────────────────────────────────────────────────")
cfg = rest_service.knoten_config({"url": "x", "auth": {
    "type": "apikey", "key_name": "k", "key_value": "v", "location": "query"}})
pruefe("API-Key als Abfrageparameter bleibt erhalten", cfg["auth_config"]["location"] == "query", cfg)

print(f"\n{len(FEHLER)} Fehler" if FEHLER else "\nAlles grün")
sys.exit(1 if FEHLER else 0)
