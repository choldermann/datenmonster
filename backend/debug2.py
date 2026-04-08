"""Debug: URL + direkter API-Test"""
import sys, re
sys.path.insert(0, '/app')
from app.core.database import SessionLocal
from app.models.rest_source import RestSource

db = SessionLocal()
try:
    for src in db.query(RestSource).all():
        print(f"\n=== RestSource #{src.id}: {src.name} ===")
        print(f"URL: {src.url}")
        placeholders = re.findall(r'\{\{(\w+)\}\}', src.url or "")
        if placeholders:
            print(f"NOCH UNAUFGELÖST: {placeholders}")
        else:
            # Direkter Test
            from app.services.rest_service import fetch_rest_source
            try:
                df = fetch_rest_source(src)
                print(f"Zeilen: {len(df)}")
                if not df.empty:
                    print(f"Spalten: {list(df.columns[:5])}")
                else:
                    # Rohantwort testen
                    import requests
                    r = requests.get(src.url, timeout=10)
                    data = r.json()
                    print(f"API-Antwort: ok={data.get('ok')}, status={data.get('status')}")
                    print(f"stations count: {len(data.get('stations', []))}")
                    if not data.get('ok'):
                        print(f"API-Message: {data.get('message', data.get('description', ''))}")
            except Exception as e:
                print(f"FEHLER: {e}")
finally:
    db.close()
