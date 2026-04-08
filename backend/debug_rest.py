"""
Debug-Script: Zeigt die URL der angelegten RestSource und testet den API-Call.
Im Backend-Container ausführen: python /app/debug_rest.py
"""
import sys
sys.path.insert(0, '/app')

from app.core.database import SessionLocal
from app.models.rest_source import RestSource

db = SessionLocal()
try:
    sources = db.query(RestSource).all()
    for src in sources:
        print(f"\n=== RestSource #{src.id}: {src.name} ===")
        print(f"URL: {src.url}")
        print(f"data_path: {src.data_path}")
        
        # Testen
        try:
            from app.services.rest_service import fetch_rest_source
            df = fetch_rest_source(src)
            print(f"Ergebnis: {len(df)} Zeilen, Spalten: {list(df.columns)[:5]}")
            if len(df) > 0:
                print(f"Erste Zeile: {df.iloc[0].to_dict()}")
        except Exception as e:
            print(f"FEHLER: {e}")
finally:
    db.close()
