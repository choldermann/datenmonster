import sys
sys.path.insert(0, '/app')
from app.services import scheduler_service
import inspect
src = inspect.getsource(scheduler_service)
# get_scheduler Funktion zeigen
idx = src.find('def get_scheduler')
print(src[idx:idx+200])
print("---")
# start_scheduler zeigen  
idx2 = src.find('def start_scheduler')
print(src[idx2:idx2+200])
