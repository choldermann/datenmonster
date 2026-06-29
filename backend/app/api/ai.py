import logging
import httpx
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
        "Du hilfst beim Erstellen von Transformationen, SQL-Abfragen und Python-Skripten. "
        "Falls der Kontext ein 'Aktives Element' enthält, hat der Benutzer genau dieses Element im Canvas angeklickt – "
        "beziehe dich in deiner Antwort gezielt darauf. "
        "WICHTIG: Du siehst nur Spaltennamen, keine semantischen Beschreibungen. "
        "Erfinde KEINE Bedeutungen oder Beschreibungen aus Feldnamen (z.B. 'enthält Rechnungsdaten'). "
        "Falls Tabellenbeziehungen im Kontext vorhanden sind, nutze diese für JOIN-Empfehlungen. "
        "Falls keine Beziehungen bekannt sind, sag das ehrlich statt zu raten. "
        "Falls der Kontext ein 'lastRunError' enthält, analysiere diesen Fehler: "
        "erkläre die Ursache verständlich, zeige die kritische Stelle im Stack-Trace, "
        "und gib konkrete Lösungsschritte. Halte die Antwort strukturiert (Ursache / Lösung)."
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
    # Längerer Timeout wenn Schema-Kontext vorhanden (großer Prompt)
    _cd = body.page_context.get("currentData", {})
    if isinstance(_cd, dict) and _cd.get("schemaContext"):
        svc.timeout = 300

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
        if isinstance(current_data, dict):
            active_node = current_data.get("activeNode")
            last_run_error = current_data.get("lastRunError")
            table_rels = current_data.get("tableRelationships", [])
            schema_ctx = current_data.get("schemaContext", "")
            # connectionIds ist frontend-intern, nicht für die KI bestimmt
            _strip = {"activeNode", "tableRelationships", "schemaContext", "connectionIds", "lastRunError"}
            rest_data = {k: v for k, v in current_data.items() if k not in _strip}
        else:
            active_node = None
            last_run_error = None
            table_rels = []
            schema_ctx = ""
            rest_data = current_data
        if active_node:
            node_str = _j.dumps(active_node, ensure_ascii=False, default=str)
            system_sections.append({"label": "Aktives Element", "content": f"Der Benutzer hat dieses Element im Canvas angeklickt:\n{node_str}"})
        if last_run_error:
            err_msg = last_run_error.get("message", str(last_run_error))
            system_sections.append({"label": "Letzter Mapping-Fehler", "content": f"Beim letzten Mapping-Run ist folgender Fehler aufgetreten:\n{err_msg}"})
        if schema_ctx:
            system_sections.append({"label": "Schema-Wissensdatenbank", "content": f"Verfügbares Datenbankschema (alle verbundenen Tabellen + Beziehungen):\n{schema_ctx}"})
        if table_rels:
            rel_lines = [
                f"  {r['from_table']}.{r['from_col']} = {r['to_table']}.{r['to_col']}"
                for r in table_rels
            ]
            content = (
                "Diese JOIN-Bedingungen verbinden die Canvas-Tabellen miteinander "
                "(ermittelt aus Primär-/Fremdschlüsseln des Datenbankschemas):\n"
                + "\n".join(rel_lines)
                + "\n\nNutze diese Informationen wenn der Benutzer nach Verknüpfungen, JOINs oder "
                  "Beziehungen zwischen den Tabellen fragt. Nenne alle aufgelisteten Beziehungen vollständig."
            )
            system_sections.append({"label": "JOIN-Beziehungen", "content": content})
        if rest_data:
            data_str = _j.dumps(rest_data, ensure_ascii=False, default=str)[:4000]
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
        try:
            async for token in svc._stream(messages, system, params=params, model=model_used):
                yield f"data: {json.dumps({'token': token})}\n\n"
        except httpx.ReadTimeout:
            yield f"data: {json.dumps({'error': 'Ollama Timeout – Modell antwortet nicht rechtzeitig (Anfrage zu groß oder Modell überlastet)'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': f'Modell-Fehler: {e}'})}\n\n"
        yield "data: [DONE]\n\n"

    from fastapi.responses import StreamingResponse as _SR
    return _SR(generate(), media_type="text/event-stream")


# ── Mapping-Kontext (FK-Beziehungen für Canvas-Datasets) ─────────────────────

class MappingContextRequest(BaseModel):
    dataset_ids: list[int]

@router.post("/mapping-context")
def get_mapping_context(
    body: MappingContextRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Gibt FK-Beziehungen zwischen Canvas-Datasets zurück (aus Schema-Cache)."""
    if not body.dataset_ids:
        return {"relationships": []}

    from app.models.dataset import Dataset, DbConnection

    datasets = db.query(Dataset).filter(Dataset.id.in_(body.dataset_ids)).all()

    # Gruppieren nach Connection
    conn_to_ds: dict[int, list] = {}
    for ds in datasets:
        if ds.source_connection_id:
            conn_to_ds.setdefault(ds.source_connection_id, []).append(ds)

    relationships = []
    for conn_id, ds_list in conn_to_ds.items():
        conn = db.query(DbConnection).filter(DbConnection.id == conn_id).first()
        if not conn or not conn.schema_cache:
            continue
        try:
            schema = json.loads(conn.schema_cache)
        except Exception:
            continue

        ds_names = {ds.name for ds in ds_list}
        canvas_tables = {full_name: tbl for full_name, tbl in
                         {t["full_name"]: t for t in schema.get("tables", [])}.items()
                         if full_name in ds_names}

        # PK-Index über alle Canvas-Tabellen: col_name → (full_name, col_name)
        pk_index: dict[str, str] = {}
        for full_name, tbl in canvas_tables.items():
            for col in tbl.get("columns", []):
                if col.get("pk"):
                    pk_index[col["name"]] = full_name

        seen = set()

        def add_rel(from_t, from_c, to_t, to_c):
            key = (from_t, from_c, to_t, to_c)
            if key not in seen:
                seen.add(key)
                relationships.append({"from_table": from_t, "from_col": from_c, "to_table": to_t, "to_col": to_c})

        for full_name, tbl in canvas_tables.items():
            for col in tbl.get("columns", []):
                col_name = col["name"]

                # 1. Explizite DB-FK
                fk_str = col.get("fk")
                if fk_str:
                    parts = fk_str.split(".")
                    if len(parts) >= 3:
                        ref_col, ref_full = parts[-1], ".".join(parts[:-1])
                    elif len(parts) == 2:
                        ref_col, ref_full = parts[1], parts[0]
                    else:
                        ref_col = ref_full = None
                    if ref_full and ref_full in ds_names:
                        add_rel(full_name, col_name, ref_full, ref_col)
                    continue  # keine implizite Prüfung wenn explizite FK vorhanden

                # 2. Implizite FK: Spaltenname ist PK einer anderen Canvas-Tabelle
                if col.get("pk"):
                    continue  # PKs selbst nicht als FK
                if col_name in pk_index:
                    ref_full = pk_index[col_name]
                    if ref_full != full_name:
                        add_rel(full_name, col_name, ref_full, col_name)

    return {"relationships": relationships}


# ── Schema-Suche (Wissensdatenbank für KI-Chat) ───────────────────────────────

class SchemaSearchRequest(BaseModel):
    connection_ids: list[int]
    canvas_table_names: list[str] = []

@router.post("/schema-search")
def schema_search(
    body: SchemaSearchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Schema-Wissensdatenbank: Canvas-Tabellen + implizite FK-Nachbarn (Tiefe 1)."""
    if not body.connection_ids:
        return {"schema_text": "", "table_count": 0}

    from app.models.dataset import DbConnection

    parts = []
    total = 0
    for conn_id in body.connection_ids:
        conn = db.query(DbConnection).filter(DbConnection.id == conn_id).first()
        if not conn or not conn.schema_cache:
            continue
        try:
            schema = json.loads(conn.schema_cache)
        except Exception:
            continue

        all_tables = schema.get("tables", [])
        tables_by_key = {t["full_name"]: t for t in all_tables}

        # 1. Canvas-Tabellen direkt holen
        canvas_names = set(body.canvas_table_names)
        # Auch Short-Name-Match (z.B. "tArtikel" trifft "dbo.tArtikel")
        short_names = {n.split(".")[-1] for n in canvas_names}
        canvas_tables = {
            t["full_name"]: t for t in all_tables
            if t["full_name"] in canvas_names or t["name"] in short_names
        }

        # 2. PK-Index der Canvas-Tabellen aufbauen
        canvas_pk_names: set[str] = set()
        canvas_col_names: set[str] = set()
        for tbl in canvas_tables.values():
            for col in tbl.get("columns", []):
                canvas_col_names.add(col["name"])
                if col.get("pk"):
                    canvas_pk_names.add(col["name"])

        # 3. Implizite FK-Expansion (Tiefe 1, beide Richtungen):
        #    a) Tabellen die Canvas-PKs als Spalte haben (referenzieren Canvas-Tabellen)
        #    b) Tabellen deren PK in den Canvas-Spalten vorkommt (werden von Canvas referenziert)
        neighbor_tables: dict[str, dict] = {}
        for tbl in all_tables:
            full_name = tbl["full_name"]
            if full_name in canvas_tables:
                continue
            tbl_cols = tbl.get("columns", [])
            tbl_col_names = {c["name"] for c in tbl_cols}
            tbl_pk_names  = {c["name"] for c in tbl_cols if c.get("pk")}

            # a) Hat eine Spalte die einem Canvas-PK entspricht
            if canvas_pk_names & tbl_col_names:
                neighbor_tables[full_name] = tbl
            # b) Hat einen PK der in Canvas-Spalten vorkommt
            elif tbl_pk_names & canvas_col_names:
                neighbor_tables[full_name] = tbl

        # Katalog-Beschreibungen + Wichtig-Flag laden
        from app.models.schema_catalog import SchemaTableMeta, SchemaRelationMeta
        table_metas: dict[str, SchemaTableMeta] = {
            m.table_full_name: m
            for m in db.query(SchemaTableMeta).filter_by(connection_id=conn_id).all()
        }
        manual_rels = db.query(SchemaRelationMeta).filter_by(connection_id=conn_id).all()

        # Wichtige Tabellen (⭐) immer einschließen – auch wenn nicht auf Canvas
        important_tables: dict[str, dict] = {
            name: tables_by_key[name]
            for name, m in table_metas.items()
            if m.is_important and name in tables_by_key
            and name not in canvas_tables and name not in neighbor_tables
        }

        # Detaillierte Liste: Canvas + Nachbarn + Wichtige (max 60)
        selected_list = (
            list(canvas_tables.values()) +
            list(neighbor_tables.values()) +
            list(important_tables.values())
        )[:60]
        selected_names = {t["full_name"] for t in selected_list}

        db_type  = schema.get("db_type", "")
        database = schema.get("database", "")
        canvas_pk_index = {c["name"]: tbl["full_name"]
                           for tbl in canvas_tables.values()
                           for c in tbl.get("columns", []) if c.get("pk")}

        def _meta_desc(tbl_name: str, include_category: bool = True) -> str:
            meta = table_metas.get(tbl_name)
            if not meta:
                return ""
            p = []
            if meta.business_name: p.append(meta.business_name)
            if meta.description:   p.append(meta.description)
            if include_category and meta.category: p.append(f"[{meta.category}]")
            return (" — " + ", ".join(p)) if p else ""

        def _render_table(tbl: dict, tag: str) -> str:
            is_canvas = tbl["full_name"] in canvas_tables
            cols = tbl.get("columns", [])
            col_parts = []
            for col in cols:
                name = col["name"]
                if col.get("pk"):
                    col_parts.append(f"{name}(PK)")
                elif col.get("fk"):
                    col_parts.append(f"{name}(FK→{col['fk']})")
                elif name in canvas_pk_index and not is_canvas:
                    col_parts.append(f"{name}(→{canvas_pk_index[name].split('.')[-1]})")
                else:
                    col_parts.append(name)
            if not is_canvas:
                key_cols = [c for c in col_parts if "(" in c]
                rest     = [c for c in col_parts if "(" not in c]
                col_parts = key_cols + rest[:max(0, 15 - len(key_cols))]
            desc = _meta_desc(tbl["full_name"])
            return f"{tbl['full_name']}{tag}{desc}: {', '.join(col_parts)}"

        lines = [f"DB: {database} ({db_type})", "", "## Canvas-Tabellen"]
        canvas_count = len(canvas_tables)
        neighbor_written = False
        important_written = False
        for idx, tbl in enumerate(selected_list):
            name = tbl["full_name"]
            if name in canvas_tables:
                tag = " [Canvas]"
                if idx == canvas_count - 1 and neighbor_tables:
                    lines.append(_render_table(tbl, tag))
                    lines.append(""); lines.append("## Verwandte Tabellen")
                    neighbor_written = True
                    continue
            elif name in important_tables:
                if not important_written:
                    lines.append(""); lines.append("## Wichtige Tabellen (⭐)")
                    important_written = True
                tag = " [⭐]"
            else:
                tag = ""
            lines.append(_render_table(tbl, tag))

        # Manuelle FK-Relationen
        if manual_rels:
            lines.append(""); lines.append("## Manuelle FK-Beziehungen")
            for r in manual_rels:
                rd = f" ({r.description})" if r.description else ""
                lines.append(f"  {r.from_table}.{r.from_col} → {r.to_table}.{r.to_col}{rd}")

        # Katalog-Übersicht: alle Tabellen mit Beschreibung (kompakt, 1 Zeile)
        catalog_lines = []
        by_category: dict[str, list[str]] = {}
        for name, meta in sorted(table_metas.items()):
            if not meta.description:
                continue
            if name in selected_names:
                continue  # bereits detailliert oben
            cat = meta.category or "Sonstige"
            label = f"{meta.business_name} — " if meta.business_name else ""
            by_category.setdefault(cat, []).append(f"  {name}: {label}{meta.description}")

        if by_category:
            lines.append(""); lines.append("## Katalog-Übersicht (weitere Tabellen)")
            for cat, entries in sorted(by_category.items()):
                lines.append(f"[{cat}]")
                lines.extend(entries)

        text = "\n".join(lines)
        parts.append(text)
        total += len(selected_list)

    return {"schema_text": "\n\n".join(parts), "table_count": total}


# ── Tabellen-Vorschlag (KI analysiert Schema und schlägt Canvas-Tabellen vor) ─

_SUGGEST_TABLES_SYSTEM = """\
Du bist ein Datenbankexperte für Datenmonster (ETL-Plattform).
Der Benutzer hat eine Datenbank verbunden und möchte ein Mapping erstellen.

AUFGABE: Analysiere das bereitgestellte Datenbankschema und schlage sinnvolle Tabellen vor,
die der Benutzer zum Canvas hinzufügen sollte, um sein Ziel zu erreichen.

WICHTIG: Antworte NUR mit einem JSON-Objekt. Kein Text davor oder danach, kein Markdown.

FORMAT:
{
  "tables": [
    {"name": "tabellenname", "schema": "schemaname", "reason": "Kurze Begründung warum diese Tabelle sinnvoll ist"}
  ],
  "joins": [
    {"from_table": "schema.tabelle1", "from_col": "spalte1", "to_table": "schema.tabelle2", "to_col": "spalte2"}
  ],
  "explanation": "Kurze Gesamterklärung in 1-2 Sätzen"
}

Schlage nur Tabellen vor die noch NICHT auf dem Canvas sind.
Nutze ausschließlich Tabellen und Spalten die im Schema vorhanden sind.
"""

class SuggestTablesRequest(BaseModel):
    connection_ids: list[int]
    canvas_tables: list[str] = []
    description: str = ""

@router.post("/suggest-tables")
async def suggest_tables(
    body: SuggestTablesRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """KI analysiert DB-Schema und schlägt passende Canvas-Tabellen vor (SSE)."""
    from app.api.settings import get_setting
    from app.models.dataset import Dataset, DbConnection
    from app.services.schema_cache_service import filter_schema_by_keywords, schema_json_to_text

    svc = _require_ai(db)
    base_url = get_setting(db, "ai_base_url", "http://ollama:11434")
    default_model = get_setting(db, "ai_model", "qwen2.5-coder:3b")
    model_used, _ = await select_auto_model("komplex schema analyse", base_url, default_model)
    params = MODE_PARAMS["analyse"]
    caps = get_model_caps(model_used)

    # Schema für alle Connections aufbauen
    schema_parts = []
    conn_datasets: dict[int, list] = {}
    for conn_id in body.connection_ids:
        conn = db.query(DbConnection).filter(DbConnection.id == conn_id).first()
        if not conn or not conn.schema_cache:
            continue
        try:
            schema = json.loads(conn.schema_cache)
        except Exception:
            continue
        keywords = [n.split(".")[-1] for n in body.canvas_tables] + body.canvas_tables
        filtered = filter_schema_by_keywords(schema, keywords, max_tables=50)
        conn_datasets[conn_id] = db.query(Dataset).filter(Dataset.source_connection_id == conn_id).all()
        schema_parts.append(schema_json_to_text(filtered, max_tables=50))

    schema_text = "\n\n".join(schema_parts) or "Kein Schema verfügbar."
    canvas_list = "\n".join(f"  - {t}" for t in body.canvas_tables) or "  (leer)"
    goal_line = f"\nZiel des Benutzers: {body.description}" if body.description.strip() else ""

    system = (
        _SUGGEST_TABLES_SYSTEM
        + f"\n\nDATENBANKSCHEMA:\n{schema_text}"
        + f"\n\nBEREITS AUF DEM CANVAS:\n{canvas_list}"
        + goal_line
    )
    messages = [{"role": "user", "content": "Schlage passende Tabellen für das Mapping vor."}]

    raw_chunks = []

    async def generate():
        async for token in svc._stream(messages, system, params=params, model=model_used):
            raw_chunks.append(token)
            yield f"data: {json.dumps({'token': token})}\n\n"

        raw = "".join(raw_chunks)
        # Markdown-Cleanup
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

        try:
            result = json.loads(raw)
        except Exception:
            yield f"data: {json.dumps({'error': 'JSON-Parsing fehlgeschlagen'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        # Tabellen anreichern: already_exists + dataset_id + connection_id
        enriched_tables = []
        for t in result.get("tables", []):
            full_name = f"{t.get('schema', 'dbo')}.{t['name']}"
            found_ds = None
            found_conn_id = None
            for cid, ds_list in conn_datasets.items():
                for ds in ds_list:
                    if ds.name in (full_name, t["name"]):
                        found_ds = ds
                        found_conn_id = cid
                        break
                if found_ds:
                    break
            if not found_conn_id and body.connection_ids:
                found_conn_id = body.connection_ids[0]
            enriched_tables.append({
                **t,
                "full_name": full_name,
                "key": full_name,
                "connection_id": found_conn_id,
                "already_exists": found_ds is not None,
                "dataset_id": found_ds.id if found_ds else None,
            })

        enriched = {**result, "tables": enriched_tables}
        yield f"data: {json.dumps({'result': enriched})}\n\n"
        yield "data: [DONE]\n\n"

    from fastapi.responses import StreamingResponse as _SR2
    return _SR2(generate(), media_type="text/event-stream")


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


# ── KI-Transform-Node Preview ─────────────────────────────────────────────────

class TransformPreviewRequest(BaseModel):
    prompt_template: str
    output_fields: list
    model: Optional[str] = None


@router.post("/transform-preview")
async def transform_preview(
    body: TransformPreviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Call Ollama once with the prompt template filled with dummy values."""
    svc = _require_ai(db)
    model = body.model or svc.model

    # Build a dummy row from output field names to demonstrate template filling
    dummy_row = {f["name"]: f"<{f['name']}>" for f in body.output_fields}

    # Build JSON schema for structured output
    properties = {}
    for f in body.output_fields:
        t = f.get("type", "string")
        json_t = {"string": "string", "integer": "integer", "float": "number", "boolean": "boolean"}.get(t, "string")
        properties[f["name"]] = {"type": json_t}
    json_schema = {
        "type": "object",
        "properties": properties,
        "required": list(properties.keys()),
    }

    # Fill template with placeholder values
    prompt = body.prompt_template
    # Provide example values for each field mentioned in the template
    all_fields = {f["name"]: f"Beispielwert für {f['name']}" for f in body.output_fields}
    import re
    for field, val in all_fields.items():
        prompt = prompt.replace(f"{{{{{field}}}}}", str(val))

    messages = [{"role": "user", "content": prompt + "\n\nAntworte ausschließlich als JSON."}]

    try:
        resp = httpx.post(
            f"{svc.base_url}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "format": {"type": "json_schema", "json_schema": {"name": "result", "strict": True, "schema": json_schema}},
                "options": {"temperature": 0.2},
            },
            timeout=60,
        )
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "{}")
        result = json.loads(content)
        return {"result": result}
    except httpx.ReadTimeout:
        raise HTTPException(504, "Ollama Timeout – Modell antwortet nicht")
    except Exception as e:
        raise HTTPException(500, f"KI-Fehler: {e}")
