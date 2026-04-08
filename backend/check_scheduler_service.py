import sys
sys.path.insert(0, '/app')
import inspect
from app.services import scheduler_service
src = inspect.getsource(scheduler_service)
# Welche Funktionen gibt es?
import re
funcs = re.findall(r'^def (\w+)', src, re.MULTILINE)
print("Funktionen:", funcs)
# Wie wird ein Job registriert?
idx = src.find('def register_job')
print(src[idx:idx+300])
