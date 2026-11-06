"""
Eigene Ereignisse (06.11.2026): Anlegen, Liste je Mandant, Ändern, Löschen, Prüfungen.

Reine Logik auf einer SQLite-Speicherdatenbank; Rechte und Mandantenwahl werden
ersetzt, damit nur die Ereignis-Regeln geprüft werden.

Lauf:  docker compose exec -T backend python tests/test_ereignisse.py
"""
import sys
sys.path.insert(0, "/app")

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.models.business_config import BusinessConfig  # noqa: E402
import app.api.business_config as bc  # noqa: E402

FEHLER = []


def pruefe(name, bedingung, extra=""):
    print(("  OK   " if bedingung else "  FAIL ") + name + (f"  [{extra}]" if not bedingung else ""))
    if not bedingung:
        FEHLER.append(name)


ENGINE = sa.create_engine("sqlite://")
with ENGINE.begin() as c:   # FK-Ziele nur mit id
    c.execute(sa.text("CREATE TABLE projects (id INTEGER PRIMARY KEY)"))
    c.execute(sa.text("CREATE TABLE db_connections (id INTEGER PRIMARY KEY)"))
BusinessConfig.__table__.create(ENGINE)
db = sessionmaker(bind=ENGINE)()


class U:
    username = "tester"


MANDANT = {"id": 7}
bc.can_read_project = lambda pid, user, db: True
bc.require_editor = lambda pid, user, db: None
bc.mandant_service.aktiver = lambda pid, user, db: MANDANT["id"]
bc.mandant_service.name_von = lambda mid, db: f"M{mid}"


def fehler_bei(fn):
    try:
        fn(); return None
    except HTTPException as e:
        return e.detail


u = U()
print("Anlegen und Liste")
a = bc.add_ereignis(bc.EreignisIn(project_id=1, datum="2026-03-10", bis="2026-03-20", titel=" Frühjahrsaktion ",
                                  kategorie="Aktion"), db, u)
b = bc.add_ereignis(bc.EreignisIn(project_id=1, datum="2026-02-01", titel="Messe Interhygiene",
                                  kategorie="gibt-es-nicht", bis="2026-02-01"), db, u)
liste = bc.list_ereignisse(1, db, u)["ereignisse"]
pruefe("nach Datum sortiert", [e["titel"] for e in liste] == ["Messe Interhygiene", "Frühjahrsaktion"], liste)
pruefe("Titel getrimmt, Zeitraum bleibt", a["titel"] == "Frühjahrsaktion" and a["bis"] == "2026-03-20")
pruefe("bis = Beginn wird eintägig", b["bis"] is None)
pruefe("unbekannte Kategorie -> Sonstiges", b["kategorie"] == "Sonstiges")

print("Mandanten getrennt")
MANDANT["id"] = 5
pruefe("anderer Mandant sieht nichts", bc.list_ereignisse(1, db, u)["ereignisse"] == [])
pruefe("fremdes Ereignis nicht änderbar",
       fehler_bei(lambda: bc.update_ereignis(a["id"], bc.EreignisIn(project_id=1, datum="2026-01-01", titel="x"), db, u))
       == "Ereignis nicht gefunden")
pruefe("fremdes Ereignis nicht löschbar", fehler_bei(lambda: bc.delete_ereignis(a["id"], 1, db, u)) == "Ereignis nicht gefunden")
MANDANT["id"] = 7

print("Ändern und Löschen")
neu = bc.update_ereignis(a["id"], bc.EreignisIn(project_id=1, datum="2026-03-12", titel="Frühjahrsaktion -10 %",
                                                kategorie="Aktion", notiz="Newsletter"), db, u)
pruefe("geändert", neu["datum"] == "2026-03-12" and neu["bis"] is None and neu["notiz"] == "Newsletter")
bc.delete_ereignis(b["id"], 1, db, u)
pruefe("gelöscht", [e["id"] for e in bc.list_ereignisse(1, db, u)["ereignisse"]] == [a["id"]])

print("Prüfungen")
pruefe("Ende vor Beginn", fehler_bei(lambda: bc.add_ereignis(
    bc.EreignisIn(project_id=1, datum="2026-03-10", bis="2026-03-01", titel="x"), db, u)) == "Das Enddatum liegt vor dem Beginn")
pruefe("ohne Titel", fehler_bei(lambda: bc.add_ereignis(bc.EreignisIn(project_id=1, datum="2026-03-10", titel="  "), db, u))
       == "Bezeichnung fehlt")
pruefe("kaputtes Datum", (fehler_bei(lambda: bc.add_ereignis(bc.EreignisIn(project_id=1, datum="morgen", titel="x"), db, u))
                         or "").startswith("Ungültiges Datum"))

print("\n" + (f"{len(FEHLER)} Fehler: {', '.join(FEHLER)}" if FEHLER else "Alle Prüfungen bestanden."))
sys.exit(1 if FEHLER else 0)
