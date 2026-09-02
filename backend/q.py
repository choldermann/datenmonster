import sys
from app.core.database import SessionLocal
from app.models.dataset import DbConnection
from app.services import db_service
import pandas as pd
conn_id = int(sys.argv[1]); sql = sys.stdin.read()
db = SessionLocal(); c = db.query(DbConnection).filter(DbConnection.id == conn_id).first()
try:
    df = db_service.query_full(c, sql)
except Exception as e:
    print("FEHLER:", str(e).split("\n")[0][:400]); sys.exit(1)
pd.set_option("display.width", 220); pd.set_option("display.max_rows", 120)
print(df.to_string(index=False)); print(f"\n[{len(df)} Zeilen]")
