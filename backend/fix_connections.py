"""Fix: fehlende from_port/to_port in Pipeline-Connections ergänzen"""
import sys
sys.path.insert(0, '/app')
from app.core.database import SessionLocal
from app.models.pipeline import Pipeline

db = SessionLocal()
try:
    p = db.query(Pipeline).filter(Pipeline.id == 20).first()
    conns = p.connections or []
    fixed = []
    for c in conns:
        fixed.append({
            "from_node": c.get("from_node", ""),
            "from_port": c.get("from_port", "out"),
            "to_node":   c.get("to_node", ""),
            "to_port":   c.get("to_port", "in"),
        })
    p.connections = fixed
    db.commit()
    print("Gefixt:")
    for c in fixed:
        print(f"  {c}")
finally:
    db.close()
