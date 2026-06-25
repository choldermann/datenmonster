from sqlalchemy import Column, Integer, String, JSON, DateTime
from sqlalchemy.sql import func
from app.core.database import Base


class Plugin(Base):
    __tablename__ = "plugins"

    id = Column(Integer, primary_key=True)
    plugin_id = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    version = Column(String)
    tier = Column(Integer, default=1)        # 1 = Python-Modul, 2 = Container
    status = Column(String, default="active") # active | error | disabled
    capabilities = Column(JSON, default=list)
    manifest = Column(JSON, default=dict)
    config = Column(JSON, default=dict)
    installed_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
