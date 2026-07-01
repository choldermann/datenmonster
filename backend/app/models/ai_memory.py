from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.sql import func
from app.core.database import Base


class AiMemoryKnowledge(Base):
    __tablename__ = "ai_memory_knowledge"

    id         = Column(Integer, primary_key=True, index=True)
    scope      = Column(String(20), nullable=False, default="global")   # global | datasource | project
    scope_id   = Column(String(100), nullable=True)                     # NULL / datasource-name / project-id
    category   = Column(String(50), default="rule")                     # rule | field_mapping | table | format | other
    title      = Column(Text, nullable=False)
    content    = Column(Text, nullable=False)
    enabled    = Column(Boolean, default=True)
    use_count  = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AiMemorySolution(Base):
    __tablename__ = "ai_memory_solutions"

    id           = Column(Integer, primary_key=True, index=True)
    project_id   = Column(Integer, nullable=True)
    category     = Column(String(50), default="other")   # sql | python | expression | mapping | ai_transform | other
    title        = Column(Text, nullable=False)
    prompt       = Column(Text, nullable=True)
    response     = Column(Text, nullable=False)
    use_count    = Column(Integer, default=1)
    rating       = Column(Integer, default=0)
    created_at   = Column(DateTime, server_default=func.now())
    last_used_at = Column(DateTime, nullable=True)


class AiMemoryCorrection(Base):
    __tablename__ = "ai_memory_corrections"

    id               = Column(Integer, primary_key=True, index=True)
    project_id       = Column(Integer, nullable=True)
    original_prompt  = Column(Text, nullable=True)
    ai_response      = Column(Text, nullable=False)
    user_correction  = Column(Text, nullable=False)
    category         = Column(String(50), default="other")
    applied_count    = Column(Integer, default=0)
    created_at       = Column(DateTime, server_default=func.now())


class AiPromptCache(Base):
    __tablename__ = "ai_prompt_cache"

    id          = Column(Integer, primary_key=True, index=True)
    cache_key   = Column(String(64), unique=True, nullable=False, index=True)
    prompt      = Column(Text, nullable=False)
    response    = Column(Text, nullable=False)
    model       = Column(String(100), nullable=True)
    project_id  = Column(Integer, nullable=True)
    hit_count   = Column(Integer, default=0)
    created_at  = Column(DateTime, server_default=func.now())
    last_hit_at = Column(DateTime, nullable=True)
