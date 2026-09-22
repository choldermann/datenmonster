"""
Prueft den Trockenlauf der JTL-Kompatibilitaetspruefung.

Anlass: JTL-Wawi 2.0.5 fuehrt `fWertNettoGesamtFixiert` nicht mehr. Die Tabelle
`Rechnung.tRechnungPosition` gibt es weiter - die Objektpruefung sah deshalb alles
gruen, waehrend der Reiter „Kunden & Rabatte" in „Ungueltiger Spaltenname" lief.
`_trockenlauf` laesst die Datenbank die Abfrage uebersetzen (SET NOEXEC ON), statt
das SQL selbst zu zerlegen.

Das Wichtigste hier ist die Gegenrichtung: ein Fehlalarm ist teurer als keine
Pruefung (das DHL-Cockpit meldete einmal faelschlich „passt nicht zur JTL-Version").
Alles, was kein Objekt-/Spaltenfehler ist - Timeout, Rechte, unser eigener
Syntaxfehler -, muss deshalb still bleiben.

Lauf:  docker compose exec -T backend python tests/test_kompatibilitaet_trockenlauf.py
"""
import sys
sys.path.insert(0, "/app")

from app.services import jtl_kompatibilitaet as K  # noqa: E402

FEHLER = []


def pruefe(name, bedingung, extra=""):
    print(("  OK   " if bedingung else "  FAIL ") + name + (f"  [{extra}]" if not bedingung else ""))
    if not bedingung:
        FEHLER.append(name)


class _Verbindung:
    def __init__(self, db_type="mssql"):
        self.db_type = db_type


class _Engine:
    """Tut so, als waere sie SQL Server: merkt sich den Batch, wirft auf Wunsch."""
    def __init__(self, fehler=None):
        self.fehler = fehler
        self.batches = []

    def connect(self):
        engine = self

        class _Conn:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

            def exec_driver_sql(self_inner, sql):
                return None

            def execute(self_inner, stmt):
                engine.batches.append(str(stmt))
                if engine.fehler:
                    raise RuntimeError(engine.fehler)
                return None

        return _Conn()


def _aufbau(fehler=None, db_type="mssql"):
    """Haengt Verbindung und Engine um - ohne echte Datenbank."""
    engine = _Engine(fehler)

    class _Query:
        def filter(self, *a): return self
        def first(self): return _Verbindung(db_type)

    class _Session:
        def query(self, *a): return _Query()
        def close(self): pass

    import app.core.database as database
    import app.services.sql_helpers as sql_helpers
    database.SessionLocal = lambda: _Session()
    sql_helpers._get_sql_engine = lambda cid: engine
    K.cache_leeren()
    return engine


SQL = "SELECT SUM(P.fWertNettoGesamtFixiert) FROM Rechnung.tRechnungPosition P WHERE P.nType = :typ AND P.dErstellt >= :von"

print("\n── Trockenlauf ──")

e = _aufbau('Ungültiger Spaltenname "fWertNettoGesamtFixiert".')
pruefe("fehlende Spalte wird gemeldet", K._trockenlauf(1, SQL) == ("spalte", "fWertNettoGesamtFixiert"))

e = _aufbau('Ungültiger Objektname "dbo.vArtikelHistorie".')
pruefe("fehlendes Objekt wird gemeldet", K._trockenlauf(1, SQL) == ("objekt", "dbo.vArtikelHistorie"))

e = _aufbau("Login timeout expired")
pruefe("Timeout meldet NICHTS", K._trockenlauf(1, SQL) is None)

e = _aufbau("Incorrect syntax near ')'")
pruefe("Syntaxfehler meldet NICHTS", K._trockenlauf(1, SQL) is None)

e = _aufbau()
pruefe("gesunde Abfrage meldet nichts", K._trockenlauf(1, SQL) is None)
batch = e.batches[0] if e.batches else ""
pruefe("Batch schaltet NOEXEC ein und wieder aus",
       "SET NOEXEC ON" in batch and batch.rstrip().endswith("SET NOEXEC OFF;"), batch[:60])
pruefe("keine Platzhalter mehr im Batch", ":typ" not in batch and ":von" not in batch, batch[-80:])

e = _aufbau(db_type="mysql")
pruefe("nicht-SQL-Server wird uebersprungen", K._trockenlauf(1, SQL) is None and not e.batches)

e = _aufbau('Ungültiger Spaltenname "fX".')
K._trockenlauf(1, SQL)
anzahl = len(e.batches)
K._trockenlauf(1, SQL)
pruefe("zweiter Aufruf kommt aus dem Zwischenspeicher", len(e.batches) == anzahl)

e = _aufbau()
pruefe("leeres SQL fragt die Datenbank gar nicht erst",
       K._trockenlauf(1, "   ") is None and not e.batches)
pruefe("ohne Verbindung kein Trockenlauf", K._trockenlauf(None, SQL) is None)

print()
if FEHLER:
    print(f"{len(FEHLER)} Pruefung(en) fehlgeschlagen: {', '.join(FEHLER)}")
    sys.exit(1)
print("Alle Pruefungen bestanden.")
