"""
Fix: RestSource.dataset_id auf das richtige Dataset setzen
damit beim manuellen Ausführen kein neues Dataset angelegt wird.
"""
import sys
sys.path.insert(0, '/app')
from app.core.database import SessionLocal
from app.models.rest_source import RestSource
from app.models.dataset import Dataset

db = SessionLocal()
try:
    for src in db.query(RestSource).all():
        print(f"\nRestSource #{src.id}: {src.name}")
        print(f"  dataset_id: {src.dataset_id}")
        
        # Passendes Dataset suchen
        ds = db.query(Dataset).filter(Dataset.name == src.name).first()
        if ds:
            print(f"  Passendes Dataset gefunden: #{ds.id} '{ds.name}'")
            if src.dataset_id != ds.id:
                src.dataset_id = ds.id
                db.commit()
                print(f"  → dataset_id gesetzt auf {ds.id}")
            else:
                print(f"  → bereits korrekt gesetzt")
        else:
            print(f"  ⚠ Kein passendes Dataset gefunden")
finally:
    db.close()
