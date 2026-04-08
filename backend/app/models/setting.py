from sqlalchemy import Column, String, DateTime
from datetime import datetime, timezone
from app.core.database import Base

class SystemSetting(Base):
    __tablename__ = "system_settings"
    key        = Column(String, primary_key=True)
    value      = Column(String, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
