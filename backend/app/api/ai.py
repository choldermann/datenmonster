from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import json

from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.services.ai_service import build_ai_service, PRESET_MODELS
from app.services.ai_context_builder import AIContextBuilder

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _require_ai(db):
    svc = build_ai_service(db)
    if svc is None:
        raise HTTPException(400, "KI-Integration ist nicht aktiviert")
    return svc


def _sse_stream(async_gen):
    async def generator():
        async for token in async_gen:
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(generator(), media_type="text/event-stream")


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/status")
async def ai_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.api.settings import get_setting
    enabled  = get_setting(db, "ai_enabled",  "false") == "true"
    base_url = get_setting(db, "ai_base_url", "http://ollama:11434")
    model    = get_setting(db, "ai_model",    "qwen2.5-coder:3b")

    result = {"enabled": enabled, "model": model, "preset_models": PRESET_MODELS}

    if enabled:
        from app.services.ai_service import AIService
        svc = AIService(base_url=base_url, model=model)
        status = await svc.check_status()
        result.update(status)
    else:
        result.update({"ollama_reachable": False, "model_loaded": False})

    return result


# ── SQL ───────────────────────────────────────────────────────────────────────

class ExplainSqlRequest(BaseModel):
    sql: str
    connection_id: Optional[int] = None
    mapping_id: Optional[int] = None

@router.post("/explain-sql")
async def explain_sql(
    body: ExplainSqlRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    svc = _require_ai(db)
    ctx = AIContextBuilder(db)
    system, context = ctx.sql_explain_context(body.sql, body.connection_id)
    return _sse_stream(svc.stream_with_context(context, system))


class GenerateSqlRequest(BaseModel):
    description: str
    connection_id: Optional[int] = None
    mapping_id: Optional[int] = None

@router.post("/generate-sql")
async def generate_sql(
    body: GenerateSqlRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    svc = _require_ai(db)
    ctx = AIContextBuilder(db)
    system, context = ctx.sql_generate_context(body.description, body.connection_id)
    return _sse_stream(svc.stream_with_context(f"{context}\n\nAufgabe: {body.description}", system))


# ── Python ────────────────────────────────────────────────────────────────────

class GeneratePythonRequest(BaseModel):
    description: str
    mapping_id: Optional[int] = None
    node_id: Optional[str] = None
    current_script: str = ""

@router.post("/generate-python")
async def generate_python(
    body: GeneratePythonRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    svc = _require_ai(db)
    ctx = AIContextBuilder(db)
    system, context = ctx.python_generate_context(body.mapping_id, body.node_id, body.current_script)
    user_msg = f"{context}\n\nAufgabe: {body.description}" if context else f"Aufgabe: {body.description}"
    return _sse_stream(svc.stream_with_context(user_msg, system))


# ── Error explanation ─────────────────────────────────────────────────────────

class ExplainErrorRequest(BaseModel):
    error: str
    node_type: str = ""
    code: str = ""
    mapping_id: Optional[int] = None
    node_id: Optional[str] = None

@router.post("/explain-error")
async def explain_error(
    body: ExplainErrorRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    svc = _require_ai(db)
    ctx = AIContextBuilder(db)
    system, context = ctx.error_explain_context(body.error, body.node_type, body.code, body.mapping_id)
    return _sse_stream(svc.stream_with_context(context, system))


# ── Expression ────────────────────────────────────────────────────────────────

class GenerateExpressionRequest(BaseModel):
    description: str
    mapping_id: Optional[int] = None
    node_id: Optional[str] = None
    field_name: str = ""

@router.post("/generate-expression")
async def generate_expression(
    body: GenerateExpressionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    svc = _require_ai(db)
    ctx = AIContextBuilder(db)
    system, context = ctx.expression_generate_context(body.mapping_id, body.node_id, body.field_name)
    user_msg = f"{context}\n\nAufgabe: {body.description}" if context else f"Aufgabe: {body.description}"
    return _sse_stream(svc.stream_with_context(user_msg, system))


# ── Mapping-Vorschlag ────────────────────────────────────────────────────────

class SuggestMappingRequest(BaseModel):
    mapping_id: int

@router.post("/suggest-mapping")
async def suggest_mapping(
    body: SuggestMappingRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    svc = _require_ai(db)
    ctx = AIContextBuilder(db)
    system, context, source_fields, target_fields = ctx.mapping_suggest_context(body.mapping_id)
    if not source_fields:
        raise HTTPException(400, "Keine Quellfelder im Mapping gefunden")
    import json as _json
    msg = (
        f"{context}\n"
        f"Quellfelder: {_json.dumps(source_fields)}\n"
        f"Zielfelder: {_json.dumps(target_fields)}"
    )
    return _sse_stream(svc.stream_with_context(msg, system))
