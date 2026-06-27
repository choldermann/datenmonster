from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.sql import func
from app.core.database import Base


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    original_filename = Column(String, nullable=True)
    file_type = Column(String, nullable=False)   # csv, xlsx, xml, db_mssql, db_mysql
    file_path = Column(String, nullable=True)    # parquet path (or raw xml path before configure)
    row_count = Column(Integer, default=0)
    columns = Column(JSON, default=list)
    column_types = Column(JSON, default=dict)  # {feldname: {type: "string"|"integer"|"decimal"|"date"|"bool", raw: "varchar(255)"}}
    xml_configured = Column(Integer, default=1)  # 0=pending, 1=done
    xml_target_node = Column(String, nullable=True)
    xml_ref_fields = Column(JSON, default=list)  # list of selected ref field paths
    source_connection_id = Column(Integer, nullable=True)
    source_sql = Column(Text, nullable=True)
    query_config = Column(JSON, nullable=True)
    source_mapping_id = Column(Integer, nullable=True)  # gesetzt wenn Dataset aus Mapping-Output stammt
    project_id = Column(Integer, nullable=True)
    cron_expr = Column(String, nullable=True)        # Zeitplan für automatisches Requery
    auto_refresh = Column(Integer, default=0)        # 0=aus, 1=ein
    last_refresh_at = Column(DateTime(timezone=True), nullable=True)
    last_refresh_status = Column(String, nullable=True)  # success | error
    last_refresh_msg = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class DbConnection(Base):
    __tablename__ = "db_connections"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    db_type = Column(String, nullable=False)  # mssql, mysql
    host = Column(String, nullable=False)
    port = Column(Integer, nullable=False)
    database = Column(String, nullable=False)
    username = Column(String, nullable=False)
    password = Column(String, nullable=False)
    project_id      = Column(Integer, nullable=True)
    schema_cache    = Column(Text, nullable=True)
    schema_cached_at = Column(DateTime(timezone=True), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
