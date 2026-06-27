from sqlalchemy import Column, Integer, String, JSON, DateTime
from datetime import datetime, timezone
from app.core.database import Base


class Form(Base):
    __tablename__ = "forms"
    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String, nullable=False)
    project_id = Column(Integer, nullable=True)
    schema     = Column(JSON, default=dict)   # { fields, layout, actions, widgets }
    version    = Column(Integer, default=1)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer, nullable=True)
