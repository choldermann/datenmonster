"""Zeigt ScheduledJob Model und wie man einen anlegt"""
import sys
sys.path.insert(0, '/app')
from app.core.database import SessionLocal
from app.models.scheduled_job import ScheduledJob
from sqlalchemy import inspect as sa_inspect

db = SessionLocal()
try:
    # Spalten des ScheduledJob Models
    cols = [c.key for c in ScheduledJob.__table__.columns]
    print("ScheduledJob Spalten:", cols)
    
    # Bestehende Jobs anzeigen
    jobs = db.query(ScheduledJob).all()
    print(f"\nBestehende Jobs ({len(jobs)}):")
    for j in jobs:
        print(f"  #{j.id}: {j.name} cron={j.cron_expr} active={j.active} pipeline_id={getattr(j,'pipeline_id',None)}")
finally:
    db.close()
