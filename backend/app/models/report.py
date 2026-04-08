from sqlalchemy import Column, Integer, String, JSON, DateTime
from datetime import datetime, timezone
from app.core.database import Base

class Report(Base):
    __tablename__ = "reports"
    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String, nullable=False)
    project_id = Column(Integer, nullable=True)
    widgets    = Column(JSON, default=list)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
