"""Führt Pipeline #20 direkt aus und zeigt den vollen Traceback"""
import sys, traceback
sys.path.insert(0, '/app')
from app.core.database import SessionLocal
from app.models.pipeline import Pipeline

db = SessionLocal()
try:
    p = db.query(Pipeline).filter(Pipeline.id == 20).first()
    from app.services.pipeline_service import run_pipeline
    result = run_pipeline(p, db)
    print("Results:")
    for nid, r in result.get("results", {}).items():
        print(f"  {nid}: {r.get('status')} – rows={r.get('rows')} msg={r.get('message','')}")
    print("Errors:", result.get("errors"))
except Exception as e:
    traceback.print_exc()
finally:
    db.close()
