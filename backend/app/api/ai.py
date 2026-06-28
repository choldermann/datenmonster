import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import json

from app.core.database import get_db

log = logging.getLogger("datenmonster")
from app.api.auth import get_current_user
from app.models.user import User
from app.services.ai_service import build_ai_service, PRESET_MODELS, MODE_PARAMS, select_auto_model, AIParams, get_model_caps
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


# ── Modell-Verwaltung ─────────────────────────────────────────────────────────

@router.get("/models")
async def list_models(user: User = Depends(get_current_user)):
    """Return list of locally installed Ollama models with details."""
    from app.api.settings import get_setting
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        base_url = get_setting(db, "ai_base_url", "http://ollama:11434")
    finally:
        db.close()
    try:
        async with __import__("httpx").AsyncClient(timeout=10) as c:
            r = await c.get(f"{base_url}/api/tags")
            data = r.json()
            return {"models": data.get("models", [])}
    except Exception as e:
        return {"models": [], "error": str(e)}


class DeleteModelRequest(BaseModel):
    model: str

@router.post("/models/delete")
async def delete_model(body: DeleteModelRequest, user: User = Depends(get_current_user)):
    """Delete a locally installed Ollama model."""
    from app.api.settings import get_setting
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        base_url = get_setting(db, "ai_base_url", "http://ollama:11434")
    finally:
        db.close()
    try:
        async with __import__("httpx").AsyncClient(timeout=30) as c:
            r = await c.delete(f"{base_url}/api/delete", json={"name": body.model})
            if r.status_code in (200, 204):
                return {"ok": True}
            return {"ok": False, "error": r.text[:200]}
    except Exception as e:
        raise HTTPException(500, str(e))


class PullModelRequest(BaseModel):
    model: str

@router.post("/pull-model")
async def pull_model(
    body: PullModelRequest,
    user: User = Depends(get_current_user),
):
    """Stream Ollama pull progress as SSE."""
    from app.api.settings import get_setting
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        base_url = get_setting(db, "ai_base_url", "http://ollama:11434")
    finally:
        db.close()

    async def generate():
        import httpx, json as _json
        try:
            async with httpx.AsyncClient(timeout=None) as c:
                async with c.stream(
                    "POST", f"{base_url}/api/pull",
                    json={"name": body.model, "stream": True},
                ) as resp:
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = _json.loads(line)
                            yield f"data: {_json.dumps(chunk)}\n\n"
                            if chunk.get("status") == "success":
                                break
                        except Exception:
                            pass
        except Exception as e:
            yield f"data: {_json.dumps({'status': 'error', 'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


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


class TestConnectionRequest(BaseModel):
    base_url: str = "http://ollama:11434"
    model: str = "qwen2.5-coder:3b"

@router.post("/test-connection")
async def test_connection(
    body: TestConnectionRequest,
    user: User = Depends(get_current_user),
):
    """Tests a given Ollama URL and model without requiring ai_enabled=true."""
    from app.services.ai_service import AIService
    svc = AIService(base_url=body.base_url, model=body.model)
    status = await svc.check_status()
    return status


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
    system, context = ctx.sql_explain_context(body.sql, body.connection_id, body.mapping_id)
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
    system, context = ctx.sql_generate_context(body.description, body.connection_id, body.mapping_id)
    full_msg = f"{context}\n\nAufgabe: {body.description}" if context else f"Aufgabe: {body.description}"
    print(f"[AI generate-sql] mapping_id={body.mapping_id} conn_id={body.connection_id} context_len={len(context)}", flush=True)
    print(f"[AI generate-sql] MSG:\n{full_msg[:600]}", flush=True)
    return _sse_stream(svc.stream_with_context(full_msg, system))


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


# ── Dataset-Vorschlag ────────────────────────────────────────────────────────

class TableContextRequest(BaseModel):
    connection_id: int
    description: str

@router.post("/table-context")
async def table_context(
    body: TableContextRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return keyword+FK filtered table list for the dataset wizard UI."""
    ctx = AIContextBuilder(db)
    return ctx.get_table_context(body.connection_id, body.description)


class SuggestDatasetsRequest(BaseModel):
    connection_id: int
    description: str
    selected_tables: Optional[list[str]] = None

@router.post("/suggest-datasets")
async def suggest_datasets(
    body: SuggestDatasetsRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Stream AI dataset suggestions as SSE; final event contains parsed JSON."""
    svc = _require_ai(db)
    ctx = AIContextBuilder(db)
    system, context = ctx.dataset_suggest_context(body.connection_id, body.description, body.selected_tables)

    async def generate():
        import re as _re
        tokens = []
        async for token in svc.stream_with_context(context, system):
            tokens.append(token)
            yield f"data: {json.dumps({'token': token})}\n\n"

        raw = "".join(tokens)
        cleaned = _re.sub(r"^```[a-zA-Z]*\s*", "", raw.strip(), flags=_re.MULTILINE)
        cleaned = _re.sub(r"```\s*$", "", cleaned, flags=_re.MULTILINE).strip()

        start = cleaned.find("[")
        end   = cleaned.rfind("]")
        if start == -1 or end == -1:
            yield f"data: {json.dumps({'error': f'KI hat kein gültiges JSON zurückgegeben: {raw[:200]}'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        try:
            suggestions = json.loads(cleaned[start:end+1])
        except Exception as e:
            yield f"data: {json.dumps({'error': f'JSON-Parsing fehlgeschlagen: {str(e)}'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        print(f"[AI suggest-datasets] raw={raw[:400]}", flush=True)
        result = []
        for s in suggestions:
            if not isinstance(s, dict):
                continue
            # Accept alternative key names models sometimes use
            name    = s.get("name") or s.get("dataset_name") or s.get("DatasetName") or s.get("title") or ""
            sql     = s.get("sql") or s.get("query") or s.get("SQL") or s.get("select") or ""
            purpose = s.get("purpose") or s.get("description") or s.get("Purpose") or s.get("desc") or ""
            if name and sql:
                result.append({
                    "name":    str(name).strip(),
                    "sql":     str(sql).strip(),
                    "purpose": str(purpose).strip(),
                })

        yield f"data: {json.dumps({'result': result})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── Globaler Assistent ────────────────────────────────────────────────────────

_PAGE_SYSTEM_PROMPTS = {
    "dashboard": (
        "Du bist der KI-Assistent für das Datenmonster Dashboard. "
        "Das Dashboard zeigt alle Projekte und deren Inhalte: Datasets (Datenquellen), "
        "Mappings (ETL-Transformationen), Pipelines (Ablaufsteuerung), Reports, Formulare "
        "und Scheduler (zeitgesteuerte Ausführung). "
        "Du hilfst Benutzern dabei, die Plattform effektiv zu nutzen."
    ),
    "mapping_editor": (
        "Du bist der KI-Assistent für den Mapping-Editor von Datenmonster. "
        "Der Mapping-Editor ermöglicht die visuelle Konfiguration von ETL-Prozessen. "
        "Datasets werden auf einem Canvas platziert und Felder über Verbindungen auf Zielfelder gemappt. "
        "Verfügbare Node-Typen: Transform-Nodes (Text, Datum, Zahl, Verkettung), "
        "Aggregations-Nodes, SQL-Nodes (Scalar/Spalte/Lookup/Transform), Calc-Nodes (Fensterfunktionen), "
        "REST-API-Nodes, Python-Nodes, Expression-Nodes, Datenqualitäts-Nodes, "
        "Konstanten-Nodes, Param-Nodes und Switch-Nodes. "
        "Du hilfst beim Erstellen von Transformationen, SQL-Abfragen und Python-Skripten."
    ),
    "pipeline_editor": (
        "Du bist der KI-Assistent für den Pipeline-Editor von Datenmonster. "
        "Pipelines steuern die Ausführungsreihenfolge von Mappings und können "
        "Bedingungen prüfen, E-Mails versenden, FTP-Aktionen ausführen, "
        "Mappings parametrisiert aufrufen und Verzweigungen enthalten."
    ),
    "report_editor": (
        "Du bist der KI-Assistent für den Report-Editor von Datenmonster. "
        "Reports visualisieren Daten aus Datasets als Diagramme (Balken, Linie, Kreis), "
        "Tabellen und KPI-Kacheln."
    ),
    "form_editor": (
        "Du bist der KI-Assistent für den Formular-Editor von Datenmonster. "
        "Formulare können Eingabefelder, Dropdowns, Datumswähler und Widgets enthalten, "
        "Mappings mit Parametern ausführen und Daten aus Datasets anzeigen."
    ),
}

_BASE_SYSTEM = (
    "Du bist der KI-Assistent von Datenmonster, einer ETL-Plattform für lokale Datenverarbeitung. "
    "Antworte auf Deutsch, präzise und hilfreich. "
    "Halte Antworten kompakt – keine unnötigen Aufzählungen. "
    "Wenn du Code-Beispiele gibst, nutze Markdown-Codeblöcke."
)


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str

class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []
    page_context: dict = {}
    mode: str = "auto"  # "schnell" | "auto" | "analyse"
    debug: bool = False

@router.post("/chat")
async def chat(
    body: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Globaler Assistent: multi-turn Chat mit Seitenkontext und Modus-Steuerung."""
    from app.api.settings import get_setting
    from datetime import datetime

    svc = _require_ai(db)
    base_url = get_setting(db, "ai_base_url", "http://ollama:11434")
    default_model = get_setting(db, "ai_model", "qwen2.5-coder:3b")

    # Modell + Parameter wählen
    model_used = default_model
    category = "medium"

    if body.mode == "auto":
        model_used, category = await select_auto_model(body.message, base_url, default_model)
        # Auto-Modus wählt auch Parameter basierend auf Komplexität
        if category == "simple":
            params: AIParams = MODE_PARAMS["schnell"]
        elif category in ("complex", "agent"):
            params = MODE_PARAMS["analyse"]
        else:
            params = MODE_PARAMS["auto"]
    else:
        params = MODE_PARAMS.get(body.mode, MODE_PARAMS["auto"])

    caps = get_model_caps(model_used)

    page = body.page_context.get("page", "")
    description = body.page_context.get("description", "")
    current_data = body.page_context.get("currentData", {})

    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    page_prompt = _PAGE_SYSTEM_PROMPTS.get(page, "")
    system_sections: list[dict] = [
        {"label": "Basis", "content": _BASE_SYSTEM},
        {"label": "Uhrzeit", "content": f"Aktuelle Uhrzeit: {now_str}"},
    ]
    if page_prompt:
        system_sections.append({"label": f"Seite: {page}", "content": page_prompt})
    elif description:
        system_sections.append({"label": "Seite", "content": description})
    if current_data:
        import json as _j
        data_str = _j.dumps(current_data, ensure_ascii=False, default=str)[:4000]
        system_sections.append({"label": "Kontext", "content": data_str})
    system = "\n\n".join(s["content"] for s in system_sections)

    messages = [{"role": m.role, "content": m.content} for m in body.history]
    messages.append({"role": "user", "content": body.message})

    async def generate():
        meta: dict = {
            "model":    model_used,
            "category": category,
            "mode":     body.mode,
            "caps":     caps,
            "params": {
                "think":       params.think and caps.get("supportsThinking", False),
                "temperature": params.temperature,
                "top_p":       params.top_p,
                "max_tokens":  params.max_tokens,
                "num_ctx":     params.num_ctx,
            },
        }
        if body.debug:
            meta["system_prompt"] = system
            meta["system_sections"] = system_sections
        yield f"data: {json.dumps({'meta': meta})}\n\n"
        async for token in svc._stream(messages, system, params=params, model=model_used):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"

    from fastapi.responses import StreamingResponse as _SR
    return _SR(generate(), media_type="text/event-stream")


# ── Node-Generierung ─────────────────────────────────────────────────────────

_GENERATE_NODES_SYSTEM = """\
Du bist ein ETL-Konfigurator für Datenmonster. Erstelle Mapping-Nodes aus einer Beschreibung.

WICHTIG: Antworte NUR mit einem JSON-Objekt. Kein erklärender Text davor oder danach, kein Markdown.

VERFÜGBARE NODE-TYPEN (node_type + Felder):

"transform" – ein Feld umwandeln
  transform_type: number_format | date_format | text_upper | text_lower | text_trim | text_replace | concat | substr
  input_field: Quellfeld  |  output_field: Ausgabefeld

"constant" – konstanter Wert
  const_type: static_text | static_number | today_date | row_number | uuid
  const_value: Wert (nur bei static_*)  |  output_field: Ausgabefeld

"agg" – Aggregation / GROUP BY
  fields: [{ func: SUM|AVG|COUNT|MIN|MAX|COUNT_DISTINCT|FIRST|LAST, input_field, output_field }]

"calc" – Fensterfunktion (ohne GROUP BY, über Partition)
  calc_type: cumsum | rank | row_number | moving_avg | lead | lag
  input_field  |  output_field  |  order_field  |  group_field (optional)  |  window_size (default 3)

"lookup" – Wert aus anderem Dataset nachschlagen
  input_field: Schlüsselfeld im Quell-Dataset
  lookup_dataset_name: Name des Lookup-Datasets
  lookup_key_col: Schlüsselspalte im Lookup-Dataset
  output_mappings: [{ lookup_col: Spalte im Lookup-Dataset, output_field: Ausgabefeld }]

"python" – freies Python-Skript pro Zeile
  script: "row['neu'] = row['alt'] * 2"
  output_fields: ["neu"]

"expr" – Formel/Ausdruck
  label: Bezeichnung
  output_fields: [{ name, expr: "row['a'] + row['b']", type: float|str|int|bool }]

"data_quality" – Datenqualitätsprüfung
  label: Bezeichnung
  rules: [{ field, type: not_null|email|regex|min_length|max_length|in_list, pattern (nur bei regex) }]

ANTWORT (genau dieses JSON, nichts anderes):
{"nodes":[...],"explanation":"Kurze Erklärung auf Deutsch was erstellt wurde"}\
"""


class GenerateNodesRequest(BaseModel):
    description: str
    available_datasets: list[dict] = []
    mapping_id: Optional[int] = None


@router.post("/generate-nodes")
async def generate_nodes(
    body: GenerateNodesRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generiert Mapping-Nodes aus einer natürlichsprachlichen Beschreibung (SSE)."""
    svc = _require_ai(db)

    ds_info = ""
    if body.available_datasets:
        ds_info = f"\nVerfügbare Datasets auf dem Canvas:\n{json.dumps(body.available_datasets[:8], ensure_ascii=False)}\n"
    user_msg = f"{ds_info}\nAufgabe: {body.description}"

    async def generate():
        import re as _re
        tokens = []
        async for token in svc.stream_with_context(user_msg, _GENERATE_NODES_SYSTEM):
            tokens.append(token)
            yield f"data: {json.dumps({'token': token})}\n\n"

        raw = "".join(tokens)
        cleaned = _re.sub(r"^```[a-zA-Z]*\s*", "", raw.strip(), flags=_re.MULTILINE)
        cleaned = _re.sub(r"```\s*$", "", cleaned, flags=_re.MULTILINE).strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1:
            yield f"data: {json.dumps({'error': 'KI hat kein gültiges JSON zurückgegeben'})}\n\n"
            yield "data: [DONE]\n\n"
            return
        try:
            parsed = json.loads(cleaned[start:end + 1])
            nodes = parsed.get("nodes", [])
            explanation = parsed.get("explanation", "")
            print(f"[AI generate-nodes] {len(nodes)} nodes, explanation={explanation[:80]}", flush=True)
            yield f"data: {json.dumps({'result': {'nodes': nodes, 'explanation': explanation}})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': f'JSON-Parsing fehlgeschlagen: {str(e)}'})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


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
