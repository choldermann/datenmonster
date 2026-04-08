from sqlalchemy import Column, Integer, String, DateTime, BigInteger, JSON
from sqlalchemy.sql import func
from app.core.database import Base


class ExportFile(Base):
    __tablename__ = "export_files"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    project_id = Column(Integer, nullable=True, index=True)
    project_name = Column(String, nullable=True)
    job_id = Column(Integer, nullable=True)       # scheduled job id, or None for manual
    mapping_id = Column(Integer, nullable=True)
    mapping_name = Column(String, nullable=True)
    target_name = Column(String, nullable=True)   # name of the target block
    file_path = Column(String, nullable=False)    # absolute path on disk
    file_name = Column(String, nullable=False)    # display name
    file_ext = Column(String, nullable=False)
    file_size = Column(BigInteger, default=0)
    triggered_by = Column(String, default="manual")  # manual | scheduler
    created_at = Column(DateTime(timezone=True), server_default=func.now())
