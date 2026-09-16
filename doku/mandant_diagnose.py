"""Warum zeigt der Mandantenwechsel dieselben Zahlen? Nur lesend.

  docker compose exec -T backend python /tmp/mandant_diagnose.py <project_id>
"""
import sys
sys.path.insert(0, "/app")
from app.core.database import SessionLocal
from app.models.dataset import DbConnection, ProjektVerbindung
from app.models.form import Form
from app.models.mapping import Mapping
from app.services import mandant_service
import json

pid = int(sys.argv[1]) if len(sys.argv) > 1 else 1
db = SessionLocal()

print(f"=== Projekt {pid} ===\n")

zuo = {r.connection_id for r in db.query(ProjektVerbindung).filter(ProjektVerbindung.project_id == pid).all()}
eig = {c.id for c in db.query(DbConnection).filter(DbConnection.project_id == pid).all()}
print(f"Zugeordnet (projekt_verbindungen): {sorted(zuo) or 'KEINE'}")
print(f"Eigentum   (db_connections):       {sorted(eig) or 'KEINE'}")

mand = mandant_service.mandanten(pid, db)
print(f"\nMandanten im Umschalter: {[(m['connection_id'], m['name']) for m in mand] or 'KEINE'}")

aus = mandant_service.austauschbare_ids(pid, db)
print(f"Austauschbare Verbindungen: {sorted(aus) or 'LEER  <-- dann passiert beim Wechsel NICHTS'}")

# Worauf zeigen die Mappings der Formulare dieses Projekts?
zeigt_auf = {}
for f in db.query(Form).filter(Form.project_id == pid).all():
    for a in (f.schema or {}).get("actions") or []:
        mid = a.get("mapping_id")
        if not mid:
            continue
        m = db.query(Mapping).filter(Mapping.id == mid).first()
        if not m:
            continue
        raw = m.sql_nodes
        nodes = json.loads(raw) if isinstance(raw, str) else (raw or [])
        for n in nodes:
            if isinstance(n, dict) and n.get("connection_id"):
                zeigt_auf.setdefault(n["connection_id"], set()).add(f.name)

print("\nVerbindungen, auf die die Cockpit-Abfragen zeigen:")
if not zeigt_auf:
    print("  (keine gefunden)")
for cid, formulare in sorted(zeigt_auf.items()):
    c = db.query(DbConnection).filter(DbConnection.id == cid).first()
    ok = "wird umgebogen" if cid in aus else "WIRD NICHT UMGEBOGEN"
    name = f"{c.name} / {c.database}" if c else "??? Verbindung fehlt"
    print(f"  {cid:>3}  {name:<38} {ok}")
    print(f"       Formulare: {', '.join(sorted(formulare))[:70]}")

# Zeigen zwei Mandanten evtl. schlicht auf dieselbe Datenbank?
print("\nDatenbanken der Mandanten:")
for m in mand:
    c = db.query(DbConnection).filter(DbConnection.id == m["connection_id"]).first()
    print(f"  {m['connection_id']:>3}  {m['name']:<24} {c.host}:{c.port}/{c.database}")
ziele = {(db.query(DbConnection).filter(DbConnection.id == m["connection_id"]).first().host,
          db.query(DbConnection).filter(DbConnection.id == m["connection_id"]).first().database)
         for m in mand}
if len(ziele) < len(mand):
    print("  !! Zwei Mandanten zeigen auf dieselbe Datenbank - dann sind gleiche Zahlen korrekt.")
