from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from datetime import datetime, timezone
from app.core.database import Base

class SystemLog(Base):
    __tablename__ = "system_logs"

    id         = Column(Integer, primary_key=True, index=True)
    level      = Column(String, default="info")   # info | warning | error
    module     = Column(String, nullable=False)    # mapping | scheduler | ftp | dispatcher | rest | import
    action     = Column(String, nullable=False)    # execute | import | trigger | ...
    message    = Column(Text, nullable=False)
    details    = Column(JSON, nullable=True)       # Zeilendetails, Diff, etc.
    entity_id  = Column(Integer, nullable=True)    # mapping_id, ftp_source_id, etc.
    entity_name = Column(String, nullable=True)    # Name des Mappings, FTP-Quelle, etc.
    project_id = Column(Integer, nullable=True)
    user_id    = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)  # Laufzeit in ms
    rows_processed = Column(Integer, nullable=True)
    rows_before = Column(Integer, nullable=True)  # für Diff
    rows_after  = Column(Integer, nullable=True)  # für Diff
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
