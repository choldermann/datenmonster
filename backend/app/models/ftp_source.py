from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.sql import func
from app.core.database import Base


class FtpSource(Base):
    __tablename__ = "ftp_sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    protocol = Column(String, default="ftp")       # ftp | sftp
    host = Column(String, nullable=False)
    port = Column(Integer, nullable=True)           # None → default (21/22)
    username = Column(String, nullable=False)
    password = Column(String, nullable=False)
    remote_dir = Column(String, default="/")        # remote directory to scan
    filename_filter = Column(String, default="*")  # glob pattern, e.g. "*.csv"
    file_type = Column(String, default="csv")       # csv | xlsx | xml
    csv_delimiter = Column(String, default=";")

    # After-import action
    after_import = Column(String, default="nothing")  # nothing | move | delete
    move_dir = Column(String, nullable=True)          # target dir if after_import=move

    # Dataset target
    dataset_id = Column(Integer, nullable=True)       # existing dataset to write into; None → create new each run
    dataset_mode = Column(String, default="replace")  # replace | append
    dataset_name_tpl = Column(String, nullable=True)  # e.g. "Kunden_FTP" – used when creating new dataset

    # Scheduling (cron expr, same format as ScheduledJob)
    cron_expr = Column(String, nullable=True)
    active = Column(Boolean, default=True)
    start_date = Column(String, nullable=True)
    end_date = Column(String, nullable=True)

    project_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    last_run_status = Column(String, nullable=True)  # success | error
    last_run_msg = Column(Text, nullable=True)
    last_rows = Column(Integer, nullable=True)
    skip_rows = Column(Integer, default=0, nullable=True)   # Zeilen überspringen beim Import