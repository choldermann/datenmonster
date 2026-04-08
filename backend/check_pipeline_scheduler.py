import sys
sys.path.insert(0, '/app')
import inspect

# Wie wird Pipeline gespeichert? Registriert der API-Endpoint den Scheduler?
from app.api import pipelines as pipelines_api
src = inspect.getsource(pipelines_api)
import re
# update_pipeline und create_pipeline zeigen
idx = src.find('def update_pipeline')
print("=== update_pipeline ===")
print(src[idx:idx+400])
idx2 = src.find('def create_pipeline')
print("\n=== create_pipeline ===")
print(src[idx2:idx2+300])
