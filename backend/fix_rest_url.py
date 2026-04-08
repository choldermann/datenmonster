"""
Fix-Script: Ersetzt unaufgelöste Platzhalter in RestSource-URLs mit Defaults.
Im Backend-Container ausführen: python /app/fix_rest_url.py
"""
import sys, re
sys.path.insert(0, '/app')

from app.core.database import SessionLocal
from app.models.rest_source import RestSource

# Defaults für häufige Tankerkoenig-Platzhalter
DEFAULTS = {
    "kraftstoff": "all",
    "sortierung": "price",
    "type":       "all",
    "sort":       "price",
    "radius":     "10",
    "rad":        "10",
}

db = SessionLocal()
try:
    sources = db.query(RestSource).all()
    for src in sources:
        url = src.url or ""
        placeholders = re.findall(r'\{\{(\w+)\}\}', url)
        if not placeholders:
            continue
        
        print(f"\nRestSource #{src.id}: {src.name}")
        print(f"  Unaufgelöste Platzhalter: {placeholders}")
        
        new_url = url
        for p in placeholders:
            if p in DEFAULTS:
                new_url = new_url.replace("{{" + p + "}}", DEFAULTS[p])
                print(f"  ✓ {{{{  {p}  }}}} → {DEFAULTS[p]}")
            else:
                print(f"  ⚠ {{{{{p}}}}} → kein Default bekannt, manuell setzen!")
        
        if new_url != url:
            src.url = new_url
            db.commit()
            print(f"  URL aktualisiert: {new_url}")

    print("\nFertig. Bitte Mapping erneut ausführen.")
finally:
    db.close()
