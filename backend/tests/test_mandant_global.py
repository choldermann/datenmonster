"""
Mandantenwahl gilt für alle Cockpits (Büro mit Rubriken, 2026-11-06).

Vorher galt die Wahl je Projekt: GF und Versand (Projekt 1) zeigten HyDa, Intrastat
(Projekt 2) und DATEV (Projekt 6) blieben auf dem alten Betrieb. Jetzt zieht ein
Wechsel alle Projekte mit, die denselben Mandanten kennen und freigeben.

Lauf:  docker compose exec -T backend python tests/test_mandant_global.py
"""
import sys
sys.path.insert(0, "/app")

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models.dataset import DbConnection, ProjektVerbindung  # noqa: E402
from app.models.mandant import MandantAuswahl, MandantFreigabe  # noqa: E402
from app.services import mandant_service as ms  # noqa: E402

FEHLER = []


def pruefe(name, bedingung, extra=""):
    print(("  OK   " if bedingung else "  FAIL ") + name + (f"  [{extra}]" if not bedingung else ""))
    if not bedingung:
        FEHLER.append(name)


ENGINE = sa.create_engine("sqlite://")
for t in (DbConnection, ProjektVerbindung, MandantAuswahl, MandantFreigabe):
    t.__table__.create(ENGINE)
with ENGINE.begin() as c:   # projects nur mit id: das Modell verweist per FK auf users
    c.execute(sa.text("CREATE TABLE projects (id INTEGER PRIMARY KEY)"))
db = sessionmaker(bind=ENGINE)()


class U:  # schlanker Benutzer
    def __init__(self, id, admin=False):
        self.id, self.is_admin = id, admin


def verbindung(id, database="eazybusiness", is_mandant=True):
    db.add(DbConnection(id=id, name=f"V{id}", db_type="mssql", host="h", port=1433, database=database,
                        username="u", password="p", project_id=None, is_mandant=is_mandant))


for pid in (1, 2, 6, 7):
    db.execute(sa.text("INSERT INTO projects (id) VALUES (:i)"), {"i": pid})
verbindung(3); verbindung(5); verbindung(7)               # PPS, HyDa, HaKo
for pid, cids in {1: (3, 5, 7), 2: (7,), 6: (3, 7), 7: (3, 5, 7)}.items():
    for c in cids:
        db.add(ProjektVerbindung(project_id=pid, connection_id=c))
db.commit()

admin = U(1, admin=True)
print("Wechsel zieht mit")
ms.waehlen(1, admin, 5, db)                               # HyDa im GF-Projekt
pruefe("Projekt 1 = HyDa", ms.aktiver(1, admin, db) == 5)
pruefe("Projekt 7 (kennt HyDa) = HyDa", ms.aktiver(7, admin, db) == 5)
pruefe("Projekt 2 (nur HaKo) bleibt HaKo", ms.aktiver(2, admin, db) == 7)
pruefe("Projekt 6 (ohne HyDa) bleibt beim Standard", ms.aktiver(6, admin, db) == 3)

ms.waehlen(2, admin, 7, db)                               # HaKo in Intrastat
pruefe("Wechsel in Projekt 2 zieht Projekt 1 mit", ms.aktiver(1, admin, db) == 7)
pruefe("und Projekt 6", ms.aktiver(6, admin, db) == 7)
pruefe("und Projekt 7", ms.aktiver(7, admin, db) == 7)

print("Freigaben")
bob = U(2)
db.add(MandantFreigabe(user_id=2, project_id=1, connection_id=5))
db.add(MandantFreigabe(user_id=2, project_id=1, connection_id=7))
db.add(MandantFreigabe(user_id=2, project_id=7, connection_id=7))
db.commit()
ms.waehlen(1, bob, 5, db)
pruefe("bob: Projekt 1 = HyDa", ms.aktiver(1, bob, db) == 5)
pruefe("bob: Projekt 7 ohne HyDa-Freigabe bleibt HaKo", ms.aktiver(7, bob, db) == 7)
pruefe("bob: keine Auswahl ohne Freigabe angelegt",
       db.query(MandantAuswahl).filter_by(user_id=2, project_id=7).first() is None)
pruefe("admin unberührt", ms.aktiver(1, admin, db) == 7)

print()
print("FEHLER: " + ", ".join(FEHLER) if FEHLER else "Alle Prüfungen bestanden.")
sys.exit(1 if FEHLER else 0)
