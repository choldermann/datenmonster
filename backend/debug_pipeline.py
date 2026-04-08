"""Debug: Pipeline-Nodes und Connections prüfen"""
import sys
sys.path.insert(0, '/app')
from app.core.database import SessionLocal
from app.models.pipeline import Pipeline
import json

db = SessionLocal()
try:
    for p in db.query(Pipeline).all():
        print(f"\n=== Pipeline #{p.id}: {p.name} ===")
        nodes = p.nodes or []
        conns = p.connections or []
        print(f"Nodes ({len(nodes)}):")
        for n in nodes:
            print(f"  {n.get('id')} → type={n.get('type')} config={n.get('config',{})}")
        print(f"Connections ({len(conns)}):")
        for c in conns:
            print(f"  {c}")
finally:
    db.close()
