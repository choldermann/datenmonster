from sqlalchemy import Column, Integer, String, JSON, DateTime, Text
from datetime import datetime, timezone
from app.core.database import Base

class Template(Base):
    __tablename__ = "templates"
    id          = Column(Integer, primary_key=True, index=True)
    template_id = Column(String, unique=True, nullable=False)
    name        = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    category    = Column(String, default="general")
    version     = Column(String, default="1.0")
    author      = Column(String, nullable=True)
    content     = Column(JSON, nullable=False)
    # Liste der Installationen mit den dabei erzeugten Objekt-IDs, damit delete_template
    # gezielt per ID löschen kann (statt fehleranfällig nach Namen). Siehe delete_template.
    # [{ "project_id": int, "at": iso, "objects": {"datasets":[..], "mappings":[..], ...} }]
    installations = Column(JSON, default=list)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
