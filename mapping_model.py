from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.sql import func
from app.core.database import Base


class Mapping(Base):
    __tablename__ = "mappings"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    canvas_nodes = Column(JSON, default=list)
    joins = Column(JSON, default=list)
    # Legacy single-target fields (kept for migration compat)
    fields = Column(JSON, default=list)
    transform_nodes = Column(JSON, default=list)
    constant_nodes = Column(JSON, default=list)
    sql_nodes = Column(JSON, default=list)   # [{id, connection_id, sql, mode, output_field}]
    agg_nodes    = Column(JSON, default=list)
    rest_nodes   = Column(JSON, default=list)
    lookup_nodes = Column(JSON, default=list)
    calc_nodes   = Column(JSON, default=list)
    switch_nodes = Column(JSON, default=list)   # [{id, x, y, fields}]
    sort_nodes   = Column(JSON, default=list)   # [{id, x, y, sort_fields: [{field, dir}]}]
    target_type = Column(String, nullable=True)
    target_connection_id = Column(Integer, nullable=True)
    target_table = Column(String, nullable=True)
    target_write_mode = Column(String, default="insert")
    target_options = Column(JSON, default=dict)
    # Multi-target: list of target objects, each with own fields
    # [{ id, name, target_type, target_connection_id, target_table,
    #    target_write_mode, target_options, fields: [...] }]
    targets = Column(JSON, default=list)
    project_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
