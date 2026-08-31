# -*- coding: utf-8 -*-
"""Spielt die Template-Dateien aus templates/ in die laufende Datenbank.

Templates leben in der Datenbank, nicht im Dateisystem — es gibt keinen
Auto-Seeder. Nach einer Änderung an templates/*.json muss dieses Skript laufen,
sonst sieht die Anwendung weiter die alte Fassung.

Der Ordner templates/ ist nicht in den Container gemountet, deshalb zweistufig:

    docker compose cp templates backend:/tmp/templates
    docker compose cp doku/jtl_template_reseed.py backend:/tmp/reseed.py
    docker compose exec backend python /tmp/reseed.py /tmp/templates

Bestehende Installationen bleiben erhalten: `installations` wird nicht angefasst,
damit ein späteres Deinstallieren weiterhin die richtigen Objekte trifft.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
from sqlalchemy.orm.attributes import flag_modified          # noqa: E402
from app.core.database import SessionLocal                   # noqa: E402
from app.models.template import Template                     # noqa: E402


def main() -> int:
    ordner = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/templates")
    dateien = sorted(ordner.glob("*.json"))
    if not dateien:
        print(f"Keine Template-Dateien in {ordner}", file=sys.stderr)
        return 1

    db = SessionLocal()
    neu = akt = 0
    try:
        for datei in dateien:
            tpl = json.loads(datei.read_text(encoding="utf-8"))
            tid = tpl.get("template_id")
            if not tid:
                print(f"  ⚠ {datei.name}: keine template_id – übersprungen")
                continue

            name = tpl.get("template_name") or tpl.get("name") or tid
            row = db.query(Template).filter(Template.template_id == tid).first()
            if row:
                alt_v = row.version
                row.content = tpl
                row.name = name
                row.description = tpl.get("description")
                row.category = tpl.get("category", row.category)
                row.version = tpl.get("version", row.version)
                # JSON-Spalte: ohne das merkt SQLAlchemy die Änderung nicht.
                flag_modified(row, "content")
                akt += 1
                wissen = len(tpl.get("knowledge") or [])
                print(f"  ✓ {tid:24} v{alt_v} → v{row.version}"
                      + (f"  ({wissen} Wissensregeln)" if wissen else ""))
            else:
                db.add(Template(
                    template_id=tid, name=name, description=tpl.get("description"),
                    category=tpl.get("category", "general"),
                    version=tpl.get("version", "1.0"),
                    author=tpl.get("author"), content=tpl, installations=[],
                ))
                neu += 1
                print(f"  + {tid:24} v{tpl.get('version')} (neu)")
        db.commit()
    finally:
        db.close()

    print(f"\n{neu} neu, {akt} aktualisiert")
    return 0


if __name__ == "__main__":
    sys.exit(main())
