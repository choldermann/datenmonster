"""
Prüft, welche Verbindungen ein Formular-Lauf beim Mandantenwechsel umbiegt.

Bis 2026-09 galt jede Verbindung aus dem Herkunftsprojekt als austauschbar. Die
Hilfsdatenbank DXBackup (HyDa) lief deshalb im Portal gegen die WaWi des Mandanten
und scheiterte mit „Ungültiger Objektname dbo.infox“. Neu: `folgt_mandant` an der
Verbindung. Die alte WaWi-Verbindung der Cockpits muss weiter umschalten, sonst
zeigte das Cockpit still die Zahlen des falschen Betriebs.

Seit 2026-09-16 zusaetzlich der Fall, der beim Kunden auftrat: zentral verwaltete
Verbindungen haengen ueber `projekt_verbindungen` am Projekt und haben ein anderes
(oder gar kein) `db_connections.project_id`. `austauschbare_ids` kannte nur das
Eigentum, die Menge war leer, der Tausch ein No-Op - beide Mandanten zeigten
dieselben Zahlen, ohne dass irgendetwas knallte.

Lauf:  docker compose exec -T backend python tests/test_mandant_tausch.py
"""
import sys
sys.path.insert(0, "/app")

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models.dataset import DbConnection, ProjektVerbindung  # noqa: E402
from app.services import mandant_service  # noqa: E402
from app.services.mapping_service import MappingContext  # noqa: E402

FEHLER = []


def pruefe(name, bedingung, extra=""):
    print(("  OK   " if bedingung else "  FAIL ") + name + (f"  [{extra}]" if not bedingung else ""))
    if not bedingung:
        FEHLER.append(name)


ENGINE = sa.create_engine("sqlite://")
DbConnection.__table__.create(ENGINE)
ProjektVerbindung.__table__.create(ENGINE)
db = sessionmaker(bind=ENGINE)()


def verbindung(id, project_id, database, is_mandant=False, folgt_mandant=None):
    c = DbConnection(id=id, name=f"V{id}", db_type="mssql", host="h", port=1433,
                     database=database, username="u", password="p",
                     project_id=project_id, is_mandant=is_mandant)
    if folgt_mandant is not None:
        c.folgt_mandant = folgt_mandant
    db.add(c)


verbindung(1, 1, "eazybusiness")                       # alte Cockpit-WaWi, kein Mandant
verbindung(7, 1, "eazybusiness", is_mandant=True)      # Mandant
verbindung(5, 4, "eazybusiness", is_mandant=True)      # HyDa-WaWi
verbindung(9, 8, "DXBackup", folgt_mandant=False)      # Hilfsdatenbank
verbindung(10, 8, "eazybusiness")                      # normale Verbindung ohne Angabe
verbindung(11, 8, "eazybusiness", is_mandant=True, folgt_mandant=False)
db.commit()


def lauf(project_id, quelle, mandant):
    ctx = MappingContext(sql_nodes=[{"id": "sql1", "connection_id": quelle, "sql": "SELECT 1"}],
                         lookup_nodes=[{"id": "lk1", "connection_id": quelle}])
    mandant_service.verbindung_ersetzen(ctx, mandant, db, project_id)
    return ctx.sql_nodes[0]["connection_id"], ctx.lookup_nodes[0]["connection_id"]


print("Austauschbare Verbindungen")
pruefe("Standard beim Anlegen: folgt dem Mandanten", db.get(DbConnection, 10).folgt_mandant is True)
pruefe("Projekt 1: alte WaWi und Mandant", mandant_service.austauschbare_ids(1, db) == {1, 7},
       mandant_service.austauschbare_ids(1, db))
pruefe("Projekt 8: DXBackup nicht, Mandant trotz Schalter aus schon",
       mandant_service.austauschbare_ids(8, db) == {10, 11}, mandant_service.austauschbare_ids(8, db))

print("Lauf")
pruefe("Cockpit auf alter WaWi schaltet weiter um", lauf(1, 1, 7) == (7, 7), lauf(1, 1, 7))
pruefe("DXBackup bleibt DXBackup", lauf(8, 9, 5) == (9, 9), lauf(8, 9, 5))
pruefe("normale Projektverbindung schaltet um", lauf(8, 10, 5) == (5, 5), lauf(8, 10, 5))

# ── Zentral verwaltete Verbindungen (Zuordnung statt Eigentum) ───────────────
# Projekt 20 besitzt KEINE Verbindung; zwei fremde WaWis sind ihm nur zugeordnet.
# Genau so sieht eine Kundeninstallation aus, in der Verbindungen zentral gepflegt
# und den Projekten zugewiesen werden.
verbindung(30, None, "eazybusiness", is_mandant=True)   # Mandant A, ohne Eigentuemer
verbindung(31, 99,   "eazybusiness", is_mandant=True)   # Mandant B, fremdes Projekt
db.add(ProjektVerbindung(project_id=20, connection_id=30))
db.add(ProjektVerbindung(project_id=20, connection_id=31))
db.commit()

print("Zentral verwaltete Verbindungen")
pruefe("Zuordnung zaehlt, nicht das Eigentum",
       mandant_service.austauschbare_ids(20, db) == {30, 31},
       mandant_service.austauschbare_ids(20, db))
pruefe("Umschalten auf den zweiten Mandanten wirkt wirklich",
       lauf(20, 30, 31) == (31, 31), lauf(20, 30, 31))
pruefe("und wieder zurueck", lauf(20, 31, 30) == (30, 30), lauf(20, 31, 30))
pruefe("beide stehen im Umschalter",
       {m["connection_id"] for m in mandant_service.mandanten(20, db)} == {30, 31},
       mandant_service.mandanten(20, db))
# Die Zuordnung darf nicht zu weit greifen: Projekt 99 besitzt 31, hat aber keine
# Zuordnungen - dort gilt weiterhin das Eigentum.
pruefe("Projekt ohne Zuordnung faellt auf das Eigentum zurueck",
       mandant_service.austauschbare_ids(99, db) == {31},
       mandant_service.austauschbare_ids(99, db))

# Der Fall, der bei der Korrektur fast verlorengegangen waere: ein Projekt hat
# Zuordnungen UND eine eigene Altverbindung, auf die die Cockpit-Knoten zeigen.
# "Zuordnung ersetzt Eigentum" haette sie herausgeworfen - die Cockpits haetten
# still die Zahlen des Standardbetriebs gezeigt. Beide Mengen muessen gelten.
verbindung(40, 21, "eazybusiness")                      # alte Projektverbindung
verbindung(41, None, "eazybusiness", is_mandant=True)   # zentral, nur zugeordnet
db.add(ProjektVerbindung(project_id=21, connection_id=41))
db.commit()

print("Zuordnung UND Eigentum nebeneinander")
pruefe("beide Mengen gelten", mandant_service.austauschbare_ids(21, db) == {40, 41},
       mandant_service.austauschbare_ids(21, db))
pruefe("Cockpit auf der Altverbindung schaltet um", lauf(21, 40, 41) == (41, 41), lauf(21, 40, 41))

print("Schreibziel")
pruefe("DXBackup bleibt Schreibziel", mandant_service.schreibziel(9, 8, None, db) == 9)

if FEHLER:
    print(f"\n{len(FEHLER)} Fehler")
    sys.exit(1)
print("\nAlle Prüfungen bestanden")
