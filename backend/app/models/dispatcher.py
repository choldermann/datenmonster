from sqlalchemy import Column, Integer, String, Boolean, JSON, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.core.database import Base

class DispatcherRule(Base):
    __tablename__ = "dispatcher_rules"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String, nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    ftp_source_id = Column(Integer, ForeignKey("ftp_sources.id"), nullable=True)
    active     = Column(Boolean, default=True)
    priority   = Column(Integer, default=0)  # niedrigere = höhere Priorität
    condition_mode = Column(String, default="AND")  # AND / OR
    conditions = Column(JSON, default=list)   # [{type, pattern, column, value}]
    mapping_id = Column(Integer, ForeignKey("mappings.id"), nullable=True)
    post_actions = Column(JSON, default=list) # [{type, ...}]
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
