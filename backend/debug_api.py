"""Simuliert den API-Aufruf /api/pipelines/20/run direkt"""
import sys, traceback
sys.path.insert(0, '/app')
from app.core.database import SessionLocal
from app.models.pipeline import Pipeline
from datetime import datetime, timezone

db = SessionLocal()
try:
    p = db.query(Pipeline).filter(Pipeline.id == 20).first()
    from app.services.pipeline_service import run_pipeline as _run
    result = _run(p, db)
    
    # Genau was der API-Endpoint macht:
    p.last_run_at = datetime.now(timezone.utc)
    p.last_run_status = "success" if not result.get("errors") else "warning"
    db.commit()
    
    print("API würde zurückgeben:")
    import json
    # Das ist der kritische Teil - kann das serialisiert werden?
    try:
        serialized = json.dumps(result, default=str)
        print(f"JSON OK, Länge: {len(serialized)}")
        print(f"results keys: {list(result.get('results', {}).keys())}")
        for nid, r in result.get('results', {}).items():
            # df im result? Das kann nicht serialisiert werden!
            for k, v in r.items():
                try:
                    json.dumps(v, default=str)
                except Exception as e:
                    print(f"  NICHT SERIALISIERBAR: {nid}.{k} = {type(v)} – {e}")
    except Exception as e:
        print(f"JSON-Serialisierung FEHLER: {e}")
        traceback.print_exc()
except Exception as e:
    traceback.print_exc()
finally:
    db.close()
