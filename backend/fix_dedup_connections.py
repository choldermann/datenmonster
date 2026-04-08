"""Doppelte Connections entfernen"""
import sys
sys.path.insert(0, '/app')
from app.core.database import SessionLocal
from app.models.pipeline import Pipeline

db = SessionLocal()
try:
    p = db.query(Pipeline).filter(Pipeline.id == 20).first()
    seen = set()
    unique = []
    for c in (p.connections or []):
        key = (c["from_node"], c["to_node"])
        if key not in seen:
            seen.add(key)
            unique.append(c)
    p.connections = unique
    db.commit()
    print(f"Bereinigt: {len(unique)} Connections")
    for c in unique:
        print(f"  {c['from_node']} → {c['to_node']}")
finally:
    db.close()
