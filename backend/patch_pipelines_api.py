"""
Patcht pipelines.py:
- create_pipeline: Trigger-Node Cron → APScheduler registrieren
- update_pipeline: dto.
"""
import sys, re
sys.path.insert(0, '/app')

api_file = '/app/app/api/pipelines.py'
with open(api_file) as f:
    content = f.read()

print("Aktuelle Datei:")
print(content[:3000])
