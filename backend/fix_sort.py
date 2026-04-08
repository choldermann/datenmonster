"""Fix: sort=dist wenn type=all"""
import sys, re
sys.path.insert(0, '/app')
from app.core.database import SessionLocal
from app.models.rest_source import RestSource

db = SessionLocal()
try:
    for src in db.query(RestSource).filter(RestSource.url.like('%tankerkoenig%')).all():
        url = src.url
        # Wenn type=all und sort=price → sort=dist
        if 'type=all' in url and 'sort=price' in url:
            src.url = url.replace('sort=price', 'sort=dist')
            db.commit()
            print(f"✓ Gefixt: {src.name}")
            print(f"  Neue URL: {src.url}")
        else:
            print(f"OK: {src.name} – kein Fix nötig")
finally:
    db.close()
