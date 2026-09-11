"""
Prüft, dass ein echter Mapping-Lauf seine Knoten nur so oft wie nötig ausführt.

Bis 2026-09 rief `run_mapping_object` bei einem Lauf mit Zielen `execute_mapping`
einmal für das Ergebnis und dann noch einmal je Ziel auf. REST- und KI-Knoten
fragten dadurch doppelt ab – bei DHL mit 250 Aufrufen am Tag ein echtes Problem.
Das Ziel, dessen Felder der erste Lauf schon benutzt hat, übernimmt jetzt dessen
Ergebnis. Die Tests laufen ohne Netz und ohne Datenbank: die SQL-Verbindung ist
durch SQLite im Speicher ersetzt, das Schreiben wird abgefangen.

Lauf:  docker compose exec -T backend python tests/test_mapping_lauf_einmal.py
"""
import sys
sys.path.insert(0, "/app")

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.services import mapping_service, mapping_writer  # noqa: E402
from app.services.mapping_service import MappingContext, run_mapping_object  # noqa: E402

FEHLER = []


def pruefe(name, bedingung, extra=""):
    print(("  OK   " if bedingung else "  FAIL ") + name + (f"  [{extra}]" if not bedingung else ""))
    if not bedingung:
        FEHLER.append(name)


# ── Ersatz für SQL-Verbindung, Zählung der Läufe, Schreiben ──────────────────

ENGINE = sa.create_engine("sqlite://", poolclass=StaticPool,
                          connect_args={"check_same_thread": False})
with ENGINE.begin() as con:
    con.execute(sa.text("CREATE TABLE infox (kinfox INTEGER, Trackingnummer TEXT)"))
    con.execute(sa.text("INSERT INTO infox VALUES (:k, :t)"),
                [{"k": i, "t": f"1539616{i:05d}"} for i in range(1, 61)])
mapping_service._get_sql_engine = lambda conn_id: ENGINE

LAEUFE = []
_echter_lauf = mapping_service.execute_mapping


def gezaehlter_lauf(*args, **kwargs):
    LAEUFE.append(kwargs.get("connections"))
    return _echter_lauf(*args, **kwargs)


mapping_service.execute_mapping = gezaehlter_lauf

GESCHRIEBEN = []


def abfangen(df, target, **kwargs):
    GESCHRIEBEN.append((target["id"], df.copy()))


mapping_service._write_target = abfangen
mapping_writer._write_target = abfangen

SQL_NODES = [{"id": "sql1", "mode": "transform", "connection_id": 1,
              "sql": "SELECT kinfox, Trackingnummer FROM infox ORDER BY kinfox"}]


def feld(name, ttype=None):
    f = {"source_dataset_id": "__sql__sql1", "source_field": name, "target_field": name,
         "transformer": {"type": "direct", "source_field": name}}
    if ttype:
        f["target_type"] = ttype
    return f


def ziel(tid, felder, **optionen):
    return {"id": tid, "name": tid, "target_type": "csv", "fields": felder, "target_options": optionen}


def lauf(targets, preview_rows=999999, **knoten):
    LAEUFE.clear()
    GESCHRIEBEN.clear()
    ctx = MappingContext(sql_nodes=SQL_NODES, targets=targets, **knoten)
    return run_mapping_object(ctx, preview_rows=preview_rows)


# ── 1. Ein Ziel: ein Lauf ────────────────────────────────────────────────────
print("1. Ein Ziel")
r = lauf([ziel("t1", [feld("kinfox", "integer"), feld("Trackingnummer")])])
pruefe("execute_mapping genau einmal", len(LAEUFE) == 1, len(LAEUFE))
pruefe("einmal geschrieben", len(GESCHRIEBEN) == 1, len(GESCHRIEBEN))
df = GESCHRIEBEN[0][1] if GESCHRIEBEN else None
pruefe("alle 60 Zeilen", df is not None and len(df) == 60, None if df is None else len(df))
pruefe("Spalten", df is not None and list(df.columns) == ["kinfox", "Trackingnummer"],
       None if df is None else list(df.columns))
pruefe("Werte", df is not None and df.iloc[0]["Trackingnummer"] == "153961600001")
pruefe("Ergebnis meldet 60 geschriebene Zeilen", r.get("total_rows_written") == 60, r.get("total_rows_written"))
pruefe("Ziel ok", r.get("targets_executed") == 1, r.get("targets_results"))

# ── 2. Python-Knoten: Ergebnis kommt im geschriebenen Ziel an ────────────────
print("2. Python-Knoten")
skript = "row['DHL_Status'] = 'zugestellt' if row.get('kinfox') % 2 else 'offen'\nreturn row"
r = lauf([ziel("t1", [feld("kinfox"), feld("DHL_Status")])],
         python_nodes=[{"id": "p1", "script": skript}])
pruefe("execute_mapping genau einmal", len(LAEUFE) == 1, len(LAEUFE))
df = GESCHRIEBEN[0][1] if GESCHRIEBEN else None
pruefe("Skriptwerte geschrieben",
       df is not None and list(df["DHL_Status"][:2]) == ["zugestellt", "offen"],
       None if df is None else list(df["DHL_Status"][:2]))

# ── 3. Zwei Ziele mit verschiedenen Feldern: zweites läuft selbst ────────────
print("3. Zwei Ziele")
r = lauf([ziel("t1", [feld("kinfox")]), ziel("t2", [feld("Trackingnummer")])])
pruefe("execute_mapping zweimal (nicht dreimal)", len(LAEUFE) == 2, len(LAEUFE))
pruefe("beide geschrieben", [g[0] for g in GESCHRIEBEN] == ["t1", "t2"], [g[0] for g in GESCHRIEBEN])
pruefe("t1 hat nur kinfox", GESCHRIEBEN and list(GESCHRIEBEN[0][1].columns) == ["kinfox"])
pruefe("t2 hat nur Trackingnummer", len(GESCHRIEBEN) > 1 and list(GESCHRIEBEN[1][1].columns) == ["Trackingnummer"])

# ── 4. Sortierung und Limit wirken wie bisher ────────────────────────────────
print("4. Sortierung und Limit")
r = lauf([ziel("t1", [feld("kinfox"), feld("Trackingnummer")],
               sort_fields=[{"field": "kinfox", "dir": "desc"}], row_limit=5)])
df = GESCHRIEBEN[0][1] if GESCHRIEBEN else None
pruefe("5 Zeilen absteigend", df is not None and list(df["kinfox"]) == [60, 59, 58, 57, 56],
       None if df is None else list(df["kinfox"]))

# ── 5. Fehler des ersten Laufs landen als Warnung am Ziel ────────────────────
print("5. Fehler als Warnung")
r = lauf([ziel("t1", [feld("kinfox")])], python_nodes=[{"id": "p1", "script": "return 1 / 0"}])
warnungen = (r.get("targets_results") or [{}])[0].get("warnings") or []
pruefe("Python-Fehler als Warnung", any("Python-Node 'p1'" in w for w in warnungen), warnungen)
pruefe("Zeilen trotzdem geschrieben", GESCHRIEBEN and len(GESCHRIEBEN[0][1]) == 60)

# ── 6. Vorschau: ein Lauf, nichts geschrieben ────────────────────────────────
print("6. Vorschau")
r = lauf([ziel("t1", [feld("kinfox")])], preview_rows=50)
pruefe("execute_mapping genau einmal", len(LAEUFE) == 1, len(LAEUFE))
pruefe("nichts geschrieben", not GESCHRIEBEN, len(GESCHRIEBEN))

# ── 7. Erstes Ziel ohne Felder: das nächste übernimmt den Lauf ───────────────
print("7. Erstes Ziel ohne Felder")
r = lauf([ziel("t0", []), ziel("t1", [feld("kinfox")])])
pruefe("execute_mapping genau einmal", len(LAEUFE) == 1, len(LAEUFE))
pruefe("t1 geschrieben", [g[0] for g in GESCHRIEBEN] == ["t1"], [g[0] for g in GESCHRIEBEN])

print()
if FEHLER:
    print(f"{len(FEHLER)} FEHLGESCHLAGEN: {FEHLER}")
    sys.exit(1)
print("Alle Prüfungen bestanden.")
