"""
Prüft, dass Zeilen-Knoten auch hinter einer SQL-Quelle laufen.

Bis 2026-09 kehrte `execute_mapping` bei SQL-Transform mit Zuordnungen im
schnellen Pfad sofort zurück. Ausdrucks-, Python-, Qualitäts- und KI-Knoten
liefen dort nie – ohne Fehler, ohne Hinweis. Die Tests laufen ohne Netz und
ohne Datenbank: die SQL-Verbindung ist durch SQLite im Speicher ersetzt.

Lauf:  docker compose exec -T backend python tests/test_mapping_zeilenpfad.py
"""
import sys
sys.path.insert(0, "/app")

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.services import mapping_service  # noqa: E402

FEHLER = []


def pruefe(name, bedingung, extra=""):
    print(("  OK   " if bedingung else "  FAIL ") + name + (f"  [{extra}]" if not bedingung else ""))
    if not bedingung:
        FEHLER.append(name)


# ── Ersatz für die SQL-Verbindung ─────────────────────────────────────────────

ENGINE = sa.create_engine("sqlite://", poolclass=StaticPool,
                          connect_args={"check_same_thread": False})
with ENGINE.begin() as con:
    con.execute(sa.text("CREATE TABLE infox (kinfox INTEGER, Trackingnummer TEXT)"))
    con.execute(sa.text("INSERT INTO infox VALUES (:k, :t)"),
                [{"k": i, "t": f"1539616{i:05d}"} for i in range(1, 61)])
mapping_service._get_sql_engine = lambda conn_id: ENGINE

SQL_NODES = [{"id": "sql1", "mode": "transform", "connection_id": 1,
              "sql": "SELECT kinfox, Trackingnummer FROM infox ORDER BY kinfox"}]


def verbindung(feld, ziel=None, quelle="__sql__sql1"):
    return {"source_dataset_id": quelle, "source_field": feld, "target_field": ziel or feld,
            "transformer": {"type": "direct", "source_field": feld}}


def lauf(connections, **knoten):
    return mapping_service.execute_mapping(
        canvas_nodes=[], connections=connections, joins=[], sql_nodes=SQL_NODES,
        preview_rows=knoten.pop("preview_rows", 50), **knoten)


BASIS = [verbindung("kinfox"), verbindung("Trackingnummer")]

# ── 1. Ohne Zeilen-Knoten: schneller Pfad wie bisher ─────────────────────────
print("1. Ohne Zeilen-Knoten")
r = lauf(BASIS)
pruefe("keine Fehler", not r["errors"], r["errors"])
pruefe("Spalten unverändert", r["columns"] == ["kinfox", "Trackingnummer"], r["columns"])
pruefe("Vorschau auf 50 Zeilen", len(r["rows"]) == 50, len(r["rows"]))
pruefe("Werte kommen an", r["rows"][0] == {"kinfox": 1, "Trackingnummer": "153961600001"}, r["rows"][0])
schnell = r

# ── 2. Python-Knoten setzt ein Zielfeld ohne SQL-Quelle ──────────────────────
print("2. Python-Knoten")
skript = ("row['DHL_Status'] = 'ruecksendung' if row.get('kinfox') == 1 else 'zugestellt'\n"
          "return row")
r = lauf(BASIS + [verbindung("DHL_Status")],
         python_nodes=[{"id": "p1", "script": skript}])
pruefe("keine Fehler", not r["errors"], r["errors"])
pruefe("Zielfeld in den Spalten", "DHL_Status" in r["columns"], r["columns"])
pruefe("Skript lief für Zeile 1", r["rows"][0].get("DHL_Status") == "ruecksendung", r["rows"][0])
pruefe("Skript lief für Zeile 2", r["rows"][1].get("DHL_Status") == "zugestellt", r["rows"][1])
pruefe("Vorschau weiter 50 Zeilen", len(r["rows"]) == 50, len(r["rows"]))
pruefe("Quellwerte gleich wie im schnellen Pfad",
       [(z["kinfox"], z["Trackingnummer"]) for z in r["rows"]]
       == [(z["kinfox"], z["Trackingnummer"]) for z in schnell["rows"]])

# ── 3. Fehler im Skript wird gemeldet, Zeile bleibt erhalten ─────────────────
print("3. Fehler im Python-Knoten")
r = lauf(BASIS, python_nodes=[{"id": "p1", "script": "return 1 / 0"}])
pruefe("Fehler gemeldet", any("Python-Node 'p1'" in e for e in r["errors"]), r["errors"])
pruefe("Zeilen bleiben", len(r["rows"]) == 50, len(r["rows"]))

# ── 4. Ausdrucks-Knoten ─────────────────────────────────────────────────────
print("4. Ausdrucks-Knoten")
r = lauf(BASIS + [verbindung("doppelt", quelle="__expr__e1")],
         expr_nodes=[{"id": "e1", "output_fields": [{"name": "doppelt", "expr": "{kinfox} * 2"}]}])
pruefe("keine Fehler", not r["errors"], r["errors"])
pruefe("Ausdruck berechnet", [z.get("doppelt") for z in r["rows"][:3]] == [2, 4, 6],
       [z.get("doppelt") for z in r["rows"][:3]])

# ── 5. Ohne Vorschau-Grenze (Scheduler) alle Zeilen ──────────────────────────
print("5. Voller Lauf")
r = lauf(BASIS, python_nodes=[{"id": "p1", "script": "return row"}], preview_rows=999999)
pruefe("alle 60 Zeilen", len(r["rows"]) == 60, len(r["rows"]))

print()
if FEHLER:
    print(f"{len(FEHLER)} FEHLGESCHLAGEN: {FEHLER}")
    sys.exit(1)
print("Alle Prüfungen bestanden.")
