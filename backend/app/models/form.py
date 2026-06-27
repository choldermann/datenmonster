from sqlalchemy import Column, Integer, String, JSON, DateTime, Boolean
from datetime import datetime, timezone
from app.core.database import Base


class Form(Base):
    __tablename__ = "forms"
    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String, nullable=False)
    project_id    = Column(Integer, nullable=True)
    schema        = Column(JSON, default=dict)    # { fields, layout, actions, widgets }
    version       = Column(Integer, default=1)
    # Portal / Veröffentlichung
    slug          = Column(String, unique=True, nullable=True)   # /app/<slug>
    published     = Column(Boolean, default=False)
    portal_config = Column(JSON, default=dict)   # { allowed_users, allow_download,
                                                 #   allow_manual_run, allow_save_params,
                                                 #   is_homepage, description, icon }
    created_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))
    created_by    = Column(Integer, nullable=True)
