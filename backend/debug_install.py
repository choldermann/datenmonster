"""Simuliert den Template-Install direkt mit vollem Traceback"""
import sys, traceback
sys.path.insert(0, '/app')
from app.core.database import SessionLocal

db = SessionLocal()
try:
    from app.api.templates import install_template, InstallBody
    
    body = InstallBody(
        template_id="tankerkoenig_spritpreise_v3",
        project_id=None,
        config={
            "apikey": "test-key",
            "plz": "77880",
            "radius": "5",
            "kraftstoff": "all"
        }
    )
    
    result = install_template(body, db)
    print("Erfolg:", result)
except Exception as e:
    traceback.print_exc()
finally:
    db.close()
