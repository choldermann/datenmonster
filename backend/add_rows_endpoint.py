"""Fügt /api/datasets/{id}/rows GET+PUT Endpoints hinzu"""
import sys
sys.path.insert(0, '/app')
import inspect
from app.api import datasets as ds_module
src = inspect.getsource(ds_module)
import re
routes = re.findall(r'@router\.(get|post|put|patch|delete)\(["\']([^"\']+)', src)
for m, p in routes:
    print(f"{m.upper():7} /api/datasets{p}")
