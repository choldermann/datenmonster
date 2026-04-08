from sqlalchemy import Column, Integer, String, Boolean, JSON, DateTime, ForeignKey
from datetime import datetime, timezone
from app.core.database import Base

class Pipeline(Base):
    __tablename__ = "pipelines"
    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String, nullable=False)
    project_id = Column(Integer, nullable=True)
    active     = Column(Boolean, default=True)
    nodes      = Column(JSON, default=list)
    connections = Column(JSON, default=list)
    last_run_at = Column(DateTime, nullable=True)
    last_run_status = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
