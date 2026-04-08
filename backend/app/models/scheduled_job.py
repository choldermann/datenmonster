from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text, Date
from sqlalchemy.sql import func
from app.core.database import Base


class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    mapping_id = Column(Integer, nullable=False)
    cron_expr = Column(String, nullable=False)
    active = Column(Boolean, default=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    project_id = Column(Integer, nullable=True)
    created_by = Column(Integer, nullable=True)   # user_id who created the job
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class JobRun(Base):
    __tablename__ = "job_runs"

    id = Column(Integer, primary_key=True, index=True)
    scheduled_job_id = Column(Integer, nullable=False, index=True)
    mapping_id = Column(Integer, nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
    duration_sec = Column(Float, nullable=True)
    status = Column(String, default="running")   # running, success, error
    rows_processed = Column(Integer, nullable=True)
    error_msg = Column(Text, nullable=True)
    triggered_by = Column(String, default="scheduler")  # scheduler, manual
