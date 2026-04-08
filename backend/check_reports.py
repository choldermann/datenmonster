import sys; sys.path.insert(0, '/app')
from app.core.database import SessionLocal
from app.models.report import Report
import json

db = SessionLocal()
reports = db.query(Report).all()
print(f'{len(reports)} Reports gefunden')
for r in reports[:3]:
    print(f'#{r.id}: {r.name}')
    widgets = r.widgets or []
    print(f'  {len(widgets)} Widgets')
    if widgets:
        print('  Widget-Typen:', [w.get('type') for w in widgets])
        print('  Erstes Widget:', json.dumps(widgets[0], indent=2, ensure_ascii=False)[:400])
db.close()
