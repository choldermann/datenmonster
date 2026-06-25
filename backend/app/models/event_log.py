from sqlalchemy import Column, Integer, String, DateTime, JSON, Text
from sqlalchemy.sql import func
from app.core.database import Base


class EventLog(Base):
    __tablename__ = "event_log"

    id = Column(Integer, primary_key=True, index=True)
    received_at = Column(DateTime, server_default=func.now())
    channel = Column(String, nullable=False)
    plugin_id = Column(String)
    source_type_id = Column(String)
    payload = Column(JSON, default=dict)
    triggered_mappings = Column(JSON, default=list)
    status = Column(String, default="received")  # processing | processed | error
    error = Column(Text)
