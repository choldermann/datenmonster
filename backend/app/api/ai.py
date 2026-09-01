import logging
import re as _regex
import httpx
import time
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


# Anbieter, die eine Oberfläche pro Aufruf wählen darf (Schema-Katalog, Portal).
_ERLAUBTE_PROVIDER = {"ollama", "datenmonster"}


def _require_ai(db, provider: Optional[str] = None):
    """`provider` übersteuert die globale Einstellung für DIESEN Aufruf – für
    Oberflächen, die die Wahl selbst anbieten. Unbekannte Werte werden ignoriert,
    damit ein Client die Einstellung nicht umgehen oder kaputtmachen kann."""
    svc = build_ai_service(db, provider if provider in _ERLAUBTE_PROVIDER else None)
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


class WarmupRequest(BaseModel):
    # Optional gezielt EIN Modell aufwärmen; sonst Code- + Textmodell aus den Einstellungen.
    model: Optional[str] = None


@router.post("/warmup")
async def warmup(body: WarmupRequest, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """Lädt die konfigurierten Modelle vorab in den Speicher (Kaltstart vorziehen),
    damit spätere KI-Aufrufe – v.a. die Bericht-Summary – nicht in einen Timeout laufen.
    Nur für Ollama sinnvoll; beim Gateway (Datenmonster AI) ist das Modell remote und
    sofort bereit → No-op mit ready=true."""
    from app.api.settings import get_setting
    from app.services.ai_service import warmup_model
    provider = get_setting(db, "ai_provider", "ollama")
    if provider != "ollama":
        return {"provider": provider, "results": [], "ready": True}
    base_url = get_setting(db, "ai_base_url", "http://ollama:11434")
    if body.model:
        models = [body.model]
    else:
        code  = get_setting(db, "ai_model", "qwen2.5-coder:3b")
        prose = get_setting(db, "ai_prose_model", "") or code
        # Reihenfolge/Deduplizierung: erst Text- dann Code-Modell (Text ist für Berichte
        # kritisch), doppelte nur einmal aufwärmen.
        models = list(dict.fromkeys([prose, code]))
    results = []
    for m in models:
        results.append(await warmup_model(base_url, m))
    return {"provider": provider, "results": results,
            "ready": all(r.get("loaded") for r in results)}


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/status")
async def ai_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.api.settings import get_setting
    enabled  = get_setting(db, "ai_enabled",  "false") == "true"
    provider = get_setting(db, "ai_provider", "ollama")

    result = {"enabled": enabled, "provider": provider, "preset_models": PRESET_MODELS}

    if not enabled:
        result.update({"model": get_setting(db, "ai_model", "qwen2.5-coder:3b"),
                       "ollama_reachable": False, "model_loaded": False})
        return result

    if provider == "datenmonster":
        from app.services.ai_gateway import DatamonsterAIService
        model = get_setting(db, "ai_dm_model", "auto")
        svc = DatamonsterAIService(db=db, model=model)
        result["model"] = model
        result["prose_model"] = get_setting(db, "ai_prose_model", "") or model
        result.update(await svc.check_status())
        # Gateway-Modelle sind remote → immer „bereit" (kein Kaltstart).
        result["code_ready"] = result["prose_ready"] = result.get("reachable", True)
    else:
        from app.services.ai_service import AIService, get_installed_models, pick_prose_model, get_loaded_models
        base_url = get_setting(db, "ai_base_url", "http://ollama:11434")
        model    = get_setting(db, "ai_model",    "qwen2.5-coder:3b")
        svc = AIService(base_url=base_url, model=model)
        result["model"] = model
        result.update(await svc.check_status())
        # Echtes „im Speicher geladen" (warm) aus /api/ps – nicht nur „installiert".
        installed = await get_installed_models(base_url)
        prose = pick_prose_model(installed, model, explicit=get_setting(db, "ai_prose_model", "") or None)
        result["prose_model"] = prose
        loaded = set(await get_loaded_models(base_url))
        result["loaded_models"] = sorted(loaded)
        result["code_ready"]  = model in loaded
        result["prose_ready"] = prose in loaded if prose else False

    return result


# ── Datenmonster AI: Guthaben & Pakete (Proxy zum monstersuite-Gateway) ────────

# Guthaben kurz zwischenspeichern: die Auskunft wird an mehreren Stellen
# gebraucht (Portalkopf, Einstellungen, Schema-Katalog) und geht jedes Mal über
# das Netz zum Gateway.
_CREDITS_CACHE: dict = {"zeit": 0.0, "daten": None}
_CREDITS_TTL = 60


@router.get("/credits")
def ai_credits(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Aktuelles Guthaben + Monatsverbrauch der Lizenz.

    Wird AUCH beantwortet, wenn global Ollama eingestellt ist: nur so kann eine
    Oberfläche entscheiden, ob sie die Wahl „Datenmonster AI" überhaupt anbietet.
    `enabled` sagt weiterhin, ob der Gateway der eingestellte Anbieter ist —
    Portalkopf und Einstellungen hängen daran.
    """
    from app.api.settings import get_setting
    provider = get_setting(db, "ai_provider", "ollama")
    ist_gateway = provider == "datenmonster"

    if _CREDITS_CACHE["daten"] is not None and time.time() - _CREDITS_CACHE["zeit"] < _CREDITS_TTL:
        return {**_CREDITS_CACHE["daten"], "provider": provider, "enabled": ist_gateway}

    from app.api.license import license_auth_body, LICENSE_SERVER
    try:
        with httpx.Client(timeout=10) as c:
            r = c.post(f"{LICENSE_SERVER}/api/v1/ai/balance", json=license_auth_body(db))
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        from app.services.ai_gateway import describe_gateway_error
        data = {"error": describe_gateway_error(e)}

    _CREDITS_CACHE.update(zeit=time.time(), daten=data)
    return {**data, "provider": provider, "enabled": ist_gateway}


@router.get("/credit-packages")
def ai_credit_packages(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Kaufbare Credit-Pakete (S/M/L) vom Gateway."""
    from app.api.license import license_auth_body, LICENSE_SERVER
    try:
        with httpx.Client(timeout=10) as c:
            r = c.post(f"{LICENSE_SERVER}/api/v1/ai/packages", json=license_auth_body(db))
            r.raise_for_status()
            return r.json()
    except Exception as e:
        from app.services.ai_gateway import describe_gateway_error
        return {"packages": [], "error": describe_gateway_error(e)}


# ── Credit-Kauf: Rechnung anfordern (Proxy zum Gateway) ───────────────────────
class PurchaseInvoiceReq(BaseModel):
    package_code: str


def _gateway_post(db, path: str, extra: dict | None = None, timeout: int = 30):
    """Lizenz-authentifizierter POST an den monstersuite-Gateway."""
    from app.api.license import license_auth_body, LICENSE_SERVER
    body = license_auth_body(db)
    if extra:
        body.update(extra)
    with httpx.Client(timeout=timeout) as c:
        r = c.post(f"{LICENSE_SERVER}/api/v1/ai{path}", json=body)
        # Fehlerantworten (402/404/502) transparent durchreichen
        try:
            data = r.json()
        except Exception:
            data = {"error": "gateway_error", "message": r.text[:200]}
        return data, r.status_code


@router.post("/purchase/invoice")
def ai_purchase_invoice(req: PurchaseInvoiceReq, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    """Credit-Paket bestellen → Gateway erstellt eine Lexware-Rechnung. Credits
    werden erst nach Zahlungseingang manuell freigeschaltet."""
    try:
        data, status = _gateway_post(db, "/purchase/invoice", {"package_code": req.package_code})
    except Exception as e:
        raise HTTPException(502, f"Gateway nicht erreichbar: {e}")
    if status >= 400:
        raise HTTPException(status, data.get("message") or data.get("error") or "Bestellung fehlgeschlagen")
    return data


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
    from app.services.ai_service import params_fuer_prompt, timeout_fuer_prompt
    params = params_fuer_prompt(len(system) + len(context))
    svc.timeout = timeout_fuer_prompt(len(system) + len(context), svc.timeout)
    return _sse_stream(svc.stream_with_context(context, system, params=params))


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
    from app.services.ai_service import params_fuer_prompt, timeout_fuer_prompt
    params = params_fuer_prompt(len(system) + len(full_msg))
    svc.timeout = timeout_fuer_prompt(len(system) + len(full_msg), svc.timeout)
    return _sse_stream(svc.stream_with_context(full_msg, system, params=params))


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
    system, context = ctx.python_generate_context(body.mapping_id, body.node_id, body.current_script,
                                                  description=body.description)
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


# ── Kennzahlen-Zusammenfassung (Dashboard-Widget "ai_summary") ──────────────────

class SummarizeDataRequest(BaseModel):
    # Anbieter nur für diesen Aufruf (Portal-/Katalogwahl); None = globale Einstellung.
    provider: Optional[str] = None
    label: str = ""
    columns: list = []
    rows: list = []
    instruction: Optional[str] = ""
    # Optionale Zusatz-Sektionen: bereits fertig aufbereitete Kurztexte, die neben
    # den Haupt-Kennzahlen in die Analyse einfließen (z.B. Umsatz je Plattform,
    # Kundenrückgang, Ladenhüter). Jede: {"label": str, "text": str}. Der Client
    # aggregiert/formatiert vor – das Modell rechnet nicht, es webt nur zusammen.
    sections: list = []
    # Ausgabeform: "prose" (Standard, Fließtext) oder "report" – eine ausführlichere
    # Lagebeurteilung in logisch geordneten Themenblöcken plus eine Markdown-Tabelle
    # (Bereich | Status | Kommentar) mit gut/verbesserungswürdig. Nur sinnvoll, wenn
    # viele Zusatz-Sektionen mitgegeben werden (z.B. alle KPIs des Cockpits).
    layout: Optional[str] = "prose"
    # Detailgrad: "knapp" (Standard) oder "ausfuehrlich". Knapp ist auf kleine lokale
    # Modelle zugeschnitten – harte Satzdeckel, vorverdichtete Daten. Ausführlich löst
    # diese Fesseln: mehr Rohzeilen, anderer Auftrag (Ursachen/Zusammenhänge statt
    # Zahlen-Nacherzählung), mehr Tokens und request_type=DATA_ANALYSIS, damit die
    # Auto-Modellwahl im Gateway auf das große Modell hochschaltet.
    detail: Optional[str] = "knapp"

# Kleiner In-Process-Cache: gleiche Daten (z.B. Dashboard mit gleichem Zeitraum
# erneut geöffnet) liefern die Zusammenfassung sofort, statt das LLM neu laufen zu
# lassen. Key = Hash aus Label + aufbereitetem Datentext; TTL 1 Stunde.
_SUMMARY_CACHE: dict = {}
_SUMMARY_TTL = 3600

@router.post("/summarize-data")
async def summarize_data(
    body: SummarizeDataRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Formuliert aus einem Widget-/Mapping-Ergebnis (Spalten + Zeilen) eine kurze
    deutsche Management-Zusammenfassung. Nutzt das konfigurierte Ollama-Modell.
    Bewusst generisch, damit beliebige Dashboards das Widget wiederverwenden können."""
    svc = _require_ai(db, body.provider)
    is_deep = (body.detail or "knapp").lower().startswith("ausf")
    # Lokale Modelle sind für den ausführlichen Prompt zu langsam: gemessen ~290 s auf
    # CPU (62 s Prompt + 223 s für 1.700 Token), der Proxy gibt nach 300 s auf. Deshalb
    # gilt „ausführlich" nur über den Gateway; lokal fällt es still auf „knapp" zurück.
    if is_deep and not getattr(svc, "is_gateway", False):
        is_deep = False
    # Knapp: Prompt kompakt halten (kleine lokale Modelle). Ausführlich: mehr Rohzeilen –
    # große Modelle glänzen beim Mustererkennen über viele Zeilen, nicht beim Nacherzählen
    # von Summen (das ist der wirksamste Hebel für Qualität, noch vor dem Modellwechsel).
    rows = (body.rows or [])[:120 if is_deep else 30]
    cols = body.columns or (list(rows[0].keys()) if rows else [])

    def _fmt(v):
        try:
            fv = float(v)
        except (TypeError, ValueError):
            return "-" if v is None else str(v)
        s = f"{int(fv):,}" if fv == int(fv) else f"{fv:,.2f}"
        return s.replace(",", "§").replace(".", ",").replace("§", ".")  # de-DE Tausender/Dezimal

    # Interne Spaltennamen, die als Fachbegriff im Text nichts zu suchen haben. Sie
    # bleiben im Schema stehen (die Widgets binden daran), aber das Modell schreibt
    # sonst wörtlich „der DB2 fiel um 2 %" in die Lagebeurteilung – ein Kürzel, das
    # seit der Umbenennung auf „Rohertrag" nirgends mehr erklärt wird.
    _SPALTEN_LABEL = {
        "Rohertrag": "Rohertrag Ware",
        "DB2": "Rohertrag gesamt",
        "DB2VJ": "Rohertrag gesamtVJ",
        "DB2Marge": "Rohertragsmarge",
        "DB2MargeVJ": "RohertragsmargeVJ",
        "DB2Quote": "Rohertragsquote",
        "DB2QuoteVJ": "RohertragsquoteVJ",
    }

    def _label(c):
        return _SPALTEN_LABEL.get(c, c)

    # Kennzahlen aufbereiten. Bei EINER Zeile (KPI-Ergebnis) werden Vorjahres-Deltas
    # serverseitig berechnet und vorformatiert – das Modell muss dann nicht rechnen
    # (genauere Prozentwerte/Richtungen, schnelleres/kleineres Modell reicht).
    if len(rows) == 1:
        row = rows[0]
        lines = []
        for c in cols:
            if c.endswith("VJ") or c.endswith("Vorjahr"):
                continue
            v = row.get(c)
            vj = row.get(c + "VJ", row.get(c + "Vorjahr"))
            line = f"{_label(c)}: {_fmt(v)}"
            try:
                if vj is not None and float(vj) != 0:
                    pct = 100.0 * (float(v) - float(vj)) / float(vj)
                    line += f" (Vorjahr {_fmt(vj)}, {pct:+.1f} %)"
            except (TypeError, ValueError):
                pass
            lines.append(line)
        data_text = "\n".join(lines)
    else:
        data_text = "\n".join("; ".join(f"{_label(c)}: {_fmt(r.get(c))}" for c in cols)
                              for r in rows) or "(keine Daten)"

    # Zusatz-Sektionen (vom Client fertig aufbereitet) anhängen.
    sections = [s for s in (body.sections or [])
                if isinstance(s, dict) and str(s.get("text", "")).strip()]
    # Kleine lokale Modelle verlieren bei vielen Blöcken den Bezug und dichten Werte
    # dazu (beobachtet bei gemma3:4b: erfundener Rohertrag, DB II und ein Kundenname).
    # Weniger Blöcke und kürzere Texte = weniger Angriffsfläche.
    if not getattr(svc, "is_gateway", False):
        _LOKAL_MAX_BLOECKE, _LOKAL_MAX_ZEICHEN = 5, 600
        # Datenqualitäts-Befunde stehen konfigurationsseitig hinten, weil sie meist
        # gar nichts liefern. Wenn sie es doch tun, ist wirklich etwas im Argen –
        # dann wiegen sie schwerer als ein weiterer Fachbereich und dürfen nicht
        # ausgerechnet der Kürzung zum Opfer fallen.
        _vorrang = [s for s in sections if str(s.get("label", "")).startswith("Datenqualität")]
        _rest = [s for s in sections if s not in _vorrang]
        sections = _vorrang + _rest[:max(0, _LOKAL_MAX_BLOECKE - len(_vorrang))]
        sections = [{**s, "text": str(s["text"]).strip()[:_LOKAL_MAX_ZEICHEN]}
                    for s in sections]
    sections_text = "\n\n".join(
        f"{s.get('label', 'Weitere Kennzahlen')}:\n{str(s['text']).strip()}" for s in sections
    )

    is_report = (body.layout or "prose").lower() == "report" and bool(sections)

    # Markier-Regel nur für den Gateway: kleine lokale Modelle schreiben die Klammern
    # unsauber ({++6,6 %} statt {++6,6 %+}), dann bliebe die Farbe ohnehin aus – der
    # Prompt wäre nur länger und lenkte von der eigentlichen Aufgabe ab.
    # Die Markierung ist eine FARBE, kein Rechenzeichen. Das muss ausdrücklich dastehen:
    # aus der Beispielzeile »{++6,6 %+}« (wo das Plus zum gelieferten Wert gehört) hat das
    # Modell sonst geschlossen, das Vorzeichen gehöre generell in die Marke – und schrieb
    # »{--712.803,75 €-}« für einen ganz normalen Umsatz. Angezeigt wurde daraus
    # »-712.803,75 €«: ein erfundenes Minus an einer positiven Zahl, quer durch die Analyse.
    _MARKIER = ("ZAHLEN BEWERTEN: Hebe die KENNZAHL hervor, nicht deine Meinung dazu. Umschließe dafür "
                "den Zahlenwert (mit Einheit und, wenn vorhanden, direkt davorstehendem Bezugswort) "
                "mit {+ und +}, wenn er erfreulich ist, bzw. mit {- und -}, wenn er kritisch ist. "
                "Die Markierung ist NUR eine Farbe – sie verändert die Zahl nicht. Übernimm den Wert "
                "exakt so, wie er oben steht, und setze ihm KEIN Vorzeichen voran, das oben nicht "
                "dasteht: aus einem Umsatz von 712.803,75 € wird {-712.803,75 €-}, niemals "
                "{--712.803,75 €-} – das wäre eine erfundene Zahl. Ein Minus gehört nur dann zwischen "
                "die Klammern, wenn es oben bereits am Wert klebt (etwa bei -6,4 %). "
                "Beispiel: 'Der Umsatz stieg um {++6,6 %+} auf {+2.984.527 €+}, die Retourenquote "
                "verschlechterte sich auf {-0,4 %-}.' Schreibe die Klammern GENAU so, ohne Leerzeichen "
                "und ohne Auslassungspunkte dazwischen. Markiere nie ganze Sätze und hänge keine "
                "Wertungsfloskeln wie 'dies ist erfreulich' an – die Farbe sagt das bereits. Zahlen ohne "
                "klare Richtung bleiben unmarkiert. Die Farbe richtet sich nach der ENTWICKLUNG, nicht "
                "nach dem Vorzeichen des Betrags: ein gesunkener Umsatz ist kritisch, auch wenn der "
                "Betrag selbst positiv ist. Umgekehrt ist ein Plus nicht automatisch gut – steigende "
                "Retouren, Ladenhüter, Verzug oder Verbindlichkeiten sind kritisch. "
                ) if getattr(svc, "is_gateway", False) else ""

    # Einheiten-Hinweis, in allen Varianten identisch.
    _UNITS = ("Beachte Einheiten: Werte mit '€' sind Euro-Beträge, '%'-Kennzahlen sind bereits Prozent, "
              "'Tage' sind Tage. " + 'Schreibe Zahlen deutsch: Dezimaltrennzeichen ist das KOMMA, Tausender werden mit Punkt getrennt (6,6 %, nicht 6.6 %; 2.984.527 €). '
              "NUR GELIEFERTE ZAHLEN: Verwende ausschließlich Werte, die oben wörtlich stehen. Erfinde "
              "keine Kennzahl, keinen Namen und keinen Vorjahreswert und rechne nichts aus, was nicht "
              "dasteht. Fehlt eine Angabe, lass sie weg – schätze sie nicht. ")

    if is_deep and is_report:
        system = (
            "Du bist ein erfahrener Business-Analyst und schreibst einem Geschäftsführer eine ausführliche "
            "Lagebeurteilung des gesamten Cockpits. Du erhältst die Kennzahlen aller Bereiche (Ertragslage, "
            "Kunden, Zahlungsmoral, Offene Posten/Liquidität, Einkauf/Verbindlichkeiten, Kapitalbindung/Lager, "
            "Klumpenrisiko, Ausblick/Prognose, schlafende Kunden, Retouren) sowie Detailzeilen dazu. Alle Werte sind bereits "
            "fertig berechnet – inkl. Vorjahr und prozentualer Veränderung in Klammern. Rechne NICHTS nach und "
            "ändere keine Zahlen; nutze sie exakt so. Erfinde nichts zu Bereichen, zu denen keine Daten "
            "geliefert wurden.\n\n"
            "Gliedere in Themenblöcke mit fettem Vorspann-Label, in dieser Reihenfolge (Blöcke ohne Daten "
            "überspringen): **Ertragslage:**, **Kunden:**, **Liquidität:**, **Einkauf & Verbindlichkeiten:**, "
            "**Kapital & Lager:**, **Risiko:**, **Ausblick:**, **Retouren:**.\n"
            "Pro Block drei bis sechs Sätze: erst die Lage mit den wichtigsten Zahlen, dann was dahinter steckt – "
            "welche Kunden, Artikel, Plattformen oder Zeiträume den Wert treiben – und was das fürs Geschäft "
            "bedeutet. Nenne konkrete Namen und Beträge aus den gelieferten Zeilen statt allgemeiner Floskeln. "
            "Stelle Zusammenhänge zwischen den Bereichen her (z.B. Kundenrückgang und Prognose, Ladenhüter und "
            "Kapitalbindung, Zahlungsmoral und offene Posten). Wo du eine Ursache vermutest, die die Daten nicht "
            "belegen, kennzeichne sie ausdrücklich als Vermutung.\n"
            "Schließe mit **Handlungsbedarf:** – drei bis fünf priorisierte Maßnahmen, jede mit Begründung aus "
            "den Zahlen und, wo möglich, dem betroffenen Betrag. Die Maßnahmen als Liste: JEDE in einer "
            "EIGENEN Zeile, die mit \"- \" beginnt.\n\n"
            "FORMAT: Jeder Themenblock ist ein eigener Absatz – zwischen den Blöcken eine LEERZEILE. Setze "
            "niemals mehrere Blöcke oder Maßnahmen in dieselbe Zeile.\n"
            + _MARKIER + "\n"
            "Beginne direkt mit **Ertragslage:** – keine Überschrift, keine Einleitung. Keine Tabelle, keine "
            "vollständigen Ranglisten nacherzählen. " + _UNITS
        )
    elif is_deep:
        system = (
            "Du bist ein erfahrener Business-Analyst, der einem Geschäftsführer zuarbeitet. Alle Werte sind "
            "bereits fertig berechnet (inkl. Vorjahr und prozentualer Veränderung in Klammern). Rechne selbst "
            "NICHTS nach und ändere keine Zahlen; nutze die Werte exakt so und erfinde nichts hinzu.\n\n"
            "Schreibe eine ausführliche Analyse in drei Blöcken mit fettem Vorspann-Label:\n"
            "**Lage:** die wichtigsten Kennzahlen und ihre Entwicklung zum Vorjahr – eingeordnet, nicht nur "
            "aufgezählt: was ist gut, was nicht und wie deutlich.\n"
            "**Auffälligkeiten:** Muster in den Detailzeilen (Ausreißer, Konzentrationen, Trends, "
            "Größenverhältnisse) mit konkreten Namen und Beträgen; erklärend statt aufzählend. Vermutete "
            "Ursachen ausdrücklich als Vermutung kennzeichnen.\n"
            "**Handlungsbedarf:** zwei bis vier priorisierte Maßnahmen – JEDE in einer EIGENEN Zeile, die "
            "mit \"- \" beginnt.\n\n"
            "FORMAT: Jeder Block ist ein eigener Absatz, zwischen den Blöcken eine LEERZEILE. Nie mehrere "
            "Blöcke oder Maßnahmen in derselben Zeile.\n"
            + _MARKIER + "\n"
            "Keine vollständigen Ranglisten nacherzählen, keine Einleitungsfloskel, keine Tabelle. " + _UNITS
        )
    elif is_report:
        system = (
            "Du bist ein nüchterner Business-Analyst, der einem Geschäftsführer eine kompakte Lagebeurteilung "
            "des gesamten Cockpits schreibt. Du erhältst die Kennzahlen aller Bereiche (Ertragslage, Kunden, "
            "Zahlungsmoral, Offene Posten/Liquidität, Einkauf/Verbindlichkeiten, Kapitalbindung/Lager, "
            "Klumpenrisiko, Ausblick/Prognose, schlafende Kunden, Retouren). Alle Werte sind bereits fertig berechnet – inkl. Vorjahr und prozentualer "
            "Veränderung in Klammern. Rechne NICHTS nach und ändere keine Zahlen; nutze sie exakt so. "
            "Erfinde nichts zu Bereichen, zu denen keine Daten geliefert wurden.\n\n"
            "Schreibe die Lagebeurteilung als klar getrennte Themenblöcke – jeder mit fettem Vorspann-Label "
            "und in FESTER Reihenfolge (überspringe Blöcke ohne Daten). HÖCHSTENS ein bis zwei knappe Sätze "
            "pro Block, keine Wiederholungen zwischen den Blöcken, keine nummerierten Listen, keine Tabelle:\n"
            "**Ertragslage:** Umsatz, Rohertrag und Marge mit Entwicklung zum Vorjahr.\n"
            "**Kunden:** aktive/Neukunden, Umsatz je Kunde, Kunden mit Rückgang (Größenordnung, max. 1 Beispiel).\n"
            "**Liquidität:** offene/überfällige Forderungen, DSO, Zahlungsmoral.\n"
            "**Einkauf & Verbindlichkeiten:** offene Verbindlichkeiten und überfällige Eingangsrechnungen, "
            "offene Bestellungen samt Verzug, Termintreue der Lieferanten.\n"
            "**Kapital & Lager:** gebundenes Kapital, Ladenhüter (Größenordnung, max. 1 Beispiel).\n"
            "**Risiko:** Klumpenrisiko/ABC – Umsatzanteil der Top-Kunden/-Artikel.\n"
            "**Ausblick:** Umsatzprognose Jahresende vs. Vorjahr und schlafende Kunden (Anzahl, max. 1 Beispiel).\n"
            "**Retouren:** Retourenquote (Wert-basiert) und Retourenwert mit Entwicklung zum Vorjahr; "
            "eine sehr niedrige Quote ausdrücklich als gut einordnen.\n"
            "**Datenqualität:** nur wenn ein Block dazu geliefert wurde – benenne die Lücke, ihre Wirkung auf die Zahlen und die konkrete Abhilfe. Nicht erfinden, wenn nichts geliefert wurde.\n"
            "**Handlungsbedarf:** die zwei bis drei wichtigsten Maßnahmen in EINEM Satz.\n\n"
            "Beginne direkt mit **Ertragslage:** – keine Überschrift, keine Einleitung, kein Text danach. "
            + _MARKIER +
            "Beachte Einheiten: Werte mit '€' sind Euro-Beträge, '%'-Kennzahlen sind bereits Prozent, "
            "'Tage' sind Tage. " + 'Schreibe Zahlen deutsch: Dezimaltrennzeichen ist das KOMMA, Tausender werden mit Punkt getrennt (6,6 %, nicht 6.6 %; 2.984.527 €). '
              "NUR GELIEFERTE ZAHLEN: Verwende ausschließlich Werte, die oben wörtlich stehen. Erfinde "
              "keine Kennzahl, keinen Namen und keinen Vorjahreswert und rechne nichts aus, was nicht "
              "dasteht. Fehlt eine Angabe, lass sie weg – schätze sie nicht. "
        )
    elif sections:
        system = (
            "Du bist ein nüchterner Business-Analyst, der einem Geschäftsführer zuarbeitet. "
            "Alle Werte sind bereits fertig berechnet (inkl. Vorjahr und prozentualer Veränderung in Klammern). "
            "Rechne selbst NICHTS nach und ändere keine Zahlen; nutze die Werte exakt so. "
            "Du erhältst neben den Haupt-Kennzahlen mehrere thematische Blöcke (z.B. Umsatz je Plattform, "
            "Kunden mit Rückgang, Ladenhüter). Verwebe sie zu einer zusammenhängenden Lagebeurteilung in "
            "4 bis 6 kurzen, konkreten deutschen Sätzen: (1) Gesamtlage inkl. Entwicklung zum Vorjahr, "
            "(2) auffällige Plattform-Entwicklung, (3) Kundenrückgang und Ladenhüter als Themen mit ihrer "
            "Größenordnung und – wo genannt – ein bis zwei markanten Beispielen, (4) klarer Handlungsbedarf. "
            "Zähle KEINE vollständigen Ranglisten auf und nenne höchstens die genannten Beispiele. "
            "Reiner Fließtext, keine Aufzählung, keine Einleitungsfloskel. "
            "Beachte Einheiten: Werte mit '€' sind Euro-Beträge, '%'-Kennzahlen sind bereits Prozent. "
            + 'Schreibe Zahlen deutsch: Dezimaltrennzeichen ist das KOMMA, Tausender werden mit Punkt getrennt (6,6 %, nicht 6.6 %; 2.984.527 €). '
              "NUR GELIEFERTE ZAHLEN: Verwende ausschließlich Werte, die oben wörtlich stehen. Erfinde "
              "keine Kennzahl, keinen Namen und keinen Vorjahreswert und rechne nichts aus, was nicht "
              "dasteht. Fehlt eine Angabe, lass sie weg – schätze sie nicht. "
            + _MARKIER
        )
    else:
        system = (
            "Du bist ein nüchterner Business-Analyst, der einem Geschäftsführer zuarbeitet. "
            "Die Kennzahlen sind bereits fertig berechnet – inklusive Vorjahreswert und prozentualer "
            "Veränderung in Klammern. Rechne selbst NICHTS nach und ändere keine Zahlen; nutze die Werte exakt so. "
            "Fasse in 2 bis 4 kurzen, konkreten deutschen Sätzen zusammen: die wichtigsten Werte, die Entwicklung "
            "zum Vorjahr (gestiegen/gesunken mit dem angegebenen Prozentwert) und – falls erkennbar – einen klaren "
            "Hinweis auf Handlungsbedarf. Reiner Fließtext, keine Aufzählung, keine Einleitungsfloskel. "
            "Beachte Einheiten: Werte mit '€' sind Euro-Beträge, '%'-Kennzahlen sind bereits Prozent. "
            + 'Schreibe Zahlen deutsch: Dezimaltrennzeichen ist das KOMMA, Tausender werden mit Punkt getrennt (6,6 %, nicht 6.6 %; 2.984.527 €). '
              "NUR GELIEFERTE ZAHLEN: Verwende ausschließlich Werte, die oben wörtlich stehen. Erfinde "
              "keine Kennzahl, keinen Namen und keinen Vorjahreswert und rechne nichts aus, was nicht "
              "dasteht. Fehlt eine Angabe, lass sie weg – schätze sie nicht. "
            + _MARKIER
        )
    user_msg = f"Kennzahlen »{body.label or 'Dashboard'}«:\n{data_text}"
    if sections_text:
        user_msg += f"\n\n{sections_text}"
    if body.instruction:
        user_msg += f"\n\nZusätzliche Anweisung: {body.instruction}"

    # Textmodell passend zum aktiven Provider (beim Gateway gilt `ai_dm_model`).
    from app.services.ai_service import resolve_prose_model
    from app.api.settings import get_setting
    # Effektiver Anbieter: die Wahl des Aufrufers schlägt die globale Einstellung.
    # Muss stimmen, weil sie unten in den Cache-Key und ins meta-Event geht –
    # sonst bekäme ein Gateway-Lauf den zwischengespeicherten Ollama-Text.
    provider = (body.provider if body.provider in _ERLAUBTE_PROVIDER
                else get_setting(db, "ai_provider", "ollama"))
    chosen = await resolve_prose_model(db, svc)

    import hashlib, time as _t
    # Prompt-Version im Cache-Key: bei Änderungen an den System-Prompts hier hochzählen,
    # sonst würden alte (z.B. Retouren-lose) Analysen aus dem Cache weiter ausgeliefert.
    # Provider + Modell gehören ZWINGEND in den Key: sonst liefert ein Modellwechsel
    # innerhalb der TTL den Text des vorherigen Modells zurück (sieht aus, als würden
    # alle Modelle dasselbe schreiben).
    _PROMPT_VERSION = "4"   # 2026-08-22: Listen, Einkaufsblock, Zahlenmarker, Dezimalkomma
    ckey = hashlib.md5(
        f"{_PROMPT_VERSION}|{provider}|{chosen or svc.model}|{body.label}|{body.instruction}"
        f"|{data_text}|{sections_text}|{body.layout}|{'deep' if is_deep else 'short'}".encode("utf-8")
    ).hexdigest()

    # Mit Zusatz-Sektionen mehr Platz für Text und Kontext.
    if is_deep:
        # Ausführlich: die Längenfesseln fallen weg, entsprechend mehr Tokens und
        # Kontextfenster (die zusätzlichen Rohzeilen müssen hineinpassen).
        if is_report:
            params = AIParams(think=False, temperature=0.35, top_p=0.9, max_tokens=2400, num_ctx=24576)
        elif sections:
            params = AIParams(think=False, temperature=0.35, top_p=0.9, max_tokens=1600, num_ctx=16384)
        else:
            params = AIParams(think=False, temperature=0.35, top_p=0.9, max_tokens=1200, num_ctx=8192)
    elif is_report:
        # Report: Themenblöcke über alle Bereiche (Bewertungstabelle baut der Client
        # deterministisch) → mehr Platz für Text und Kontext.
        params = AIParams(think=False, temperature=0.3, top_p=0.9, max_tokens=900, num_ctx=12288)
    elif sections:
        params = AIParams(think=False, temperature=0.3, top_p=0.9, max_tokens=520, num_ctx=8192)
    else:
        params = AIParams(think=False, temperature=0.3, top_p=0.9, max_tokens=320, num_ctx=4096)

    # Als SSE-Stream ausliefern: die Response-Header gehen sofort raus (kein
    # "Network Error" bei langsamem Kaltstart), Text erscheint fortlaufend.
    # Vorab ein »meta«-Event mit dem tatsächlich verwendeten Modell – sonst ist von
    # außen nicht erkennbar, wer den Text geschrieben hat (bzw. ob er aus dem Cache kam).
    # Wählt der Aufrufer bewusst einen Anbieter (Portal-Umschalter), festhalten –
    # sonst lässt sich hinterher nicht klären, womit eine Analyse erzeugt wurde.
    if body.provider:
        print(f"[AI] summarize-data: Anbieterwahl des Aufrufers = {body.provider} "
              f"(effektiv {provider}, Modell {chosen or svc.model})", flush=True)

    async def gen():
        hit = _SUMMARY_CACHE.get(ckey)
        cached = bool(hit and hit[0] + _SUMMARY_TTL > _t.time())
        yield f"data: {json.dumps({'meta': {'model': chosen or svc.model, 'provider': provider, 'cached': cached}})}\n\n"
        if cached:
            yield f"data: {json.dumps({'token': hit[1]})}\n\n"
            yield "data: [DONE]\n\n"
            return
        parts = []
        try:
            # request_type nur bei "ausführlich" auf DATA_ANALYSIS: nur damit schaltet die
            # Auto-Modellwahl im Gateway (_pick_model) vom Mini- auf das große Modell hoch.
            async for tok in svc.stream_with_context(
                user_msg, system, params=params, model=chosen,
                request_type="DATA_ANALYSIS" if is_deep else "OTHER",
            ):
                parts.append(tok)
                yield f"data: {json.dumps({'token': tok})}\n\n"
        except Exception as e:
            # z.B. GatewayError (insufficient_credits, invalid_key, Modell nicht in der
            # Whitelist) – sichtbar machen statt den Stream stumm abbrechen zu lassen.
            yield f"data: {json.dumps({'error': str(e)[:300]})}\n\n"
        text = "".join(parts).strip()
        if text:
            _SUMMARY_CACHE[ckey] = (_t.time(), text, chosen or svc.model)
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


# ── KI-Handlungsempfehlung (Klick auf Widget-Zeile) ─────────────────────────────

class RecommendActionRequest(BaseModel):
    provider: Optional[str] = None
    kind: str                        # "customer_winback" | "article_liquidation" | "article_description"
    label: str = ""
    columns: list = []
    rows: list = []                  # Fakten aus dem Analyse-Mapping (i.d.R. 1 Zeile)
    instruction: Optional[str] = ""
    use_research: bool = False       # Herstellerdaten nachschlagen (article_description)


def _ra_num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _ra_de(v, unit=""):
    """Deutsche Zahlformatierung (Tausenderpunkt, Komma) mit optionaler Einheit."""
    f = _ra_num(v)
    if f is None:
        return "–"
    s = f"{int(f):,}" if f == int(f) else f"{f:,.2f}"
    s = s.replace(",", "§").replace(".", ",").replace("§", ".")
    return f"{s} {unit}".strip()


def _ra_clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def _winback_facts(row: dict) -> dict:
    """Nachvollziehbare Rückgewinnungs-Heuristik aus den SQL-Fakten.
    Score = 0.5·Recency + 0.3·Wert + 0.2·Treue, jeweils 0..1 → 0..100 %.
    Bewusst simpel/erklärbar: die Zahl muss gegenüber der GF verteidigbar sein."""
    tage_inaktiv = _ra_num(row.get("TageInaktiv"))
    intervall    = _ra_num(row.get("TageZwischenBestellungen"))
    bestellungen = _ra_num(row.get("BestellungenGesamt")) or 0
    rang         = _ra_num(row.get("RangHistorisch"))
    kunden_ges   = _ra_num(row.get("KundenGesamt"))

    # Recency: solange der Kunde im Rahmen seines üblichen Bestellrhythmus liegt,
    # ist Rückgewinnung wahrscheinlich; ab dem 6-fachen Intervall gilt er als verloren.
    ref = intervall if (intervall and intervall > 0) else 90.0
    if tage_inaktiv is None:
        recency = 0.3
    else:
        recency = _ra_clamp(1.0 - max(0.0, tage_inaktiv - 2 * ref) / (4 * ref))

    # Wert: historischer Umsatzrang als Perzentil (Top-Kunde → hoher Score).
    if rang and kunden_ges and kunden_ges > 1:
        value = _ra_clamp(1.0 - (rang - 1) / (kunden_ges - 1))
    else:
        value = 0.5

    # Treue: Anzahl Bestellungen (ab 10 Bestellungen voll gewertet).
    freq = _ra_clamp(bestellungen / 10.0)

    prob = round((0.5 * recency + 0.3 * value + 0.2 * freq) * 100)
    # Perzentil mit Untergrenze 1 %, damit Platz 1 nicht als "Top 0 %" erscheint.
    top_pct = max(1, round(100.0 * rang / kunden_ges)) if (rang and kunden_ges and kunden_ges > 0) else None

    return {"probability": prob, "top_percent": top_pct,
            "recency": round(recency, 2), "value": round(value, 2), "freq": round(freq, 2)}


def _description_facts(row: dict) -> dict:
    """Welche Stammdaten stehen für die Beschreibung zur Verfügung?

    Rein beschreibend – die Oberfläche zeigt daraus die Fakten-Kacheln und macht
    sichtbar, worauf die KI sich stützen kann. Je weniger Quellen, desto dünner
    fällt die Beschreibung aus; das soll der Anwender vorher sehen.
    """
    quellen = [name for name, key in (
        ("Hersteller", "Hersteller"), ("EAN", "EAN"), ("HAN", "HAN"),
        ("Warengruppe", "Warengruppe"), ("Kurzbeschreibung", "Kurzbeschreibung"),
    ) if str(row.get(key) or "").strip()]
    vorhanden = str(row.get("Beschreibung") or "").strip()
    return {
        "quellen":        quellen,
        "quellen_anzahl": len(quellen),
        "zeichen_vorher": len(vorhanden),
    }


def _liquidation_facts(row: dict) -> dict:
    """Rabatt- und Kapitalfreisetzungs-Heuristik für Ladenhüter."""
    bestand = _ra_num(row.get("Bestand")) or 0
    ek      = _ra_num(row.get("EK")) or 0
    marge   = _ra_num(row.get("MargeProzent"))
    reichw  = _ra_num(row.get("Lagerreichweite"))
    kapital = _ra_num(row.get("Kapitalbindung"))
    if kapital is None:
        kapital = bestand * ek

    # Rabatt aus Lagerreichweite abgeleitet (je träger, desto aggressiver),
    # aber nie so tief, dass die Marge negativ würde (max. Marge − 5 Punkte).
    if reichw is None:      base = 25    # kein Absatz → maximal drücken
    elif reichw > 730:      base = 20
    elif reichw > 365:      base = 15
    elif reichw > 180:      base = 10
    else:                   base = 5
    if marge is not None:
        base = min(base, max(0, int(marge) - 5))
    discount = int(round(base / 5.0) * 5)

    return {"capital_release": round(kapital, 2), "discount": discount,
            "reichweite": None if reichw is None else int(reichw)}


def _region_facts(row: dict) -> dict:
    """Kennzahlen zur Marktdurchdringung einer Region – deterministisch aus dem SQL.

    Marktdurchdringung = Umsatzanteil / Bevölkerungsanteil (1,0 = so stark vertreten
    wie das Bundesland groß ist). Das Zusatzpotenzial ist der Umsatz, der bei
    durchschnittlicher Durchdringung zusätzlich anfiele – bewusst als grobe
    Orientierung, nicht als Prognose."""
    md = _ra_num(row.get("Marktdurchdringung"))
    potenzial = _ra_num(row.get("Potenzial"))
    rueckgang = _ra_num(row.get("RueckgangSumme"))
    if md is None:
        stufe = "unbekannt"
    elif md < 0.5:
        stufe = "deutlich unterrepräsentiert"
    elif md < 0.8:
        stufe = "unterrepräsentiert"
    elif md > 1.2:
        stufe = "stark"
    else:
        stufe = "im Rahmen"
    return {
        "marktdurchdringung": None if md is None else round(md, 2),
        "bewertung": stufe,
        # Nur ausweisen, wenn wirklich Luft nach oben ist (negative Werte = überdurchschnittlich).
        "potenzial": None if potenzial is None or potenzial <= 0 else round(potenzial, 2),
        "rueckgang": None if rueckgang is None or rueckgang <= 0 else round(rueckgang, 2),
    }


@router.post("/recommend-action")
async def recommend_action(
    body: RecommendActionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """KI-Handlungsempfehlung für eine einzelne Widget-Zeile (Kunde bzw. Artikel).
    Kennzahlen wie Rückgewinnungswahrscheinlichkeit oder Rabatt werden serverseitig
    DETERMINISTISCH aus den übergebenen SQL-Fakten berechnet (nicht vom Modell geraten)
    und als »meta«-Event vorab gesendet; das Modell formuliert nur die Prosa drumherum."""
    svc = _require_ai(db, body.provider)
    row = (body.rows or [{}])[0] or {}

    if body.kind == "customer_winback":
        facts = _winback_facts(row)
        lines = [
            f"Kunde: {body.label or row.get('Kunde', '')}",
            f"Letzte Bestellung: {row.get('LetzteBestellung', '–')}",
            f"Tage inaktiv: {_ra_de(row.get('TageInaktiv'))}",
            f"Bestellungen gesamt: {_ra_de(row.get('BestellungenGesamt'))}",
            f"Umsatz gesamt (Lifetime): {_ra_de(row.get('UmsatzGesamt'), '€')}",
        ]
        if facts.get("top_percent") is not None:
            lines.append(f"Umsatzrang: Platz {_ra_de(row.get('RangHistorisch'))} von "
                         f"{_ra_de(row.get('KundenGesamt'))} (Top {facts['top_percent']} %)")
        if row.get("TopArtikel"):
            lines.append(f"Meistgekaufte Artikel: {row.get('TopArtikel')}")
        lines.append(f"Berechnete Rückgewinnungswahrscheinlichkeit: {facts['probability']} %")
        system = (
            "Du bist ein nüchterner Vertriebs-Analyst, der einem Geschäftsführer zuarbeitet. "
            "Du erhältst FERTIG BERECHNETE Fakten zu einem Kunden mit Umsatzrückgang, inklusive einer bereits "
            "berechneten Rückgewinnungswahrscheinlichkeit. Rechne NICHTS nach und ändere keine Zahlen – nutze die "
            "Werte exakt. Formuliere in 3–4 kurzen deutschen Sätzen: (1) die Situation (seit wann inaktiv, welcher "
            "Kundenwert), (2) eine konkrete Handlungsempfehlung (z. B. persönlicher/telefonischer Kontakt, passendes "
            "Angebot), (3) falls meistgekaufte Artikel genannt sind, empfiehl diese als Aufhänger fürs Gespräch. "
            "Nenne die Rückgewinnungswahrscheinlichkeit NICHT erneut als Zahl (die zeigt die Oberfläche bereits an). "
            "Reiner Fließtext, keine Aufzählung, keine Einleitungsfloskel."
        )
    elif body.kind == "article_liquidation":
        facts = _liquidation_facts(row)
        reich = "über 3 Jahre / praktisch kein Absatz" if facts["reichweite"] is None \
            else f"{_ra_de(facts['reichweite'])} Tage"
        lines = [
            f"Artikel: {body.label or row.get('Artikel', '')} (Nr. {row.get('ArtNr', '')})",
            f"Lagerbestand: {_ra_de(row.get('Bestand'))} Stück",
            f"Lagerreichweite: {reich}",
            f"Tage ohne Verkauf: {_ra_de(row.get('TageOhneVerkauf'))}",
            f"Gebundenes Kapital: {_ra_de(facts['capital_release'], '€')}",
            f"EK/VK netto: {_ra_de(row.get('EK'), '€')} / {_ra_de(row.get('VK') or row.get('VKNetto'), '€')}",
        ]
        if row.get("MargeProzent") is not None:
            lines.append(f"Marge: {_ra_de(row.get('MargeProzent'))} %")
        if row.get("BundleKandidat"):
            lines.append(f"Häufig zusammen gekaufter Artikel (Bundle-Kandidat): {row.get('BundleKandidat')}")
        lines.append(f"Empfohlener Rabatt: {facts['discount']} %")
        system = (
            "Du bist ein nüchterner Category-Manager, der einem Geschäftsführer zuarbeitet. "
            "Du erhältst FERTIG BERECHNETE Fakten zu einem Ladenhüter (hohe Lagerreichweite / gebundenes Kapital) "
            "inklusive eines bereits berechneten Rabattvorschlags. Rechne NICHTS nach und ändere keine Zahlen. "
            "Formuliere in 3–4 kurzen deutschen Sätzen eine konkrete Abverkaufs-Empfehlung: (1) den empfohlenen "
            "Rabatt in Prozent nennen, (2) falls ein Bundle-Kandidat genannt ist, ein Bündelangebot mit diesem "
            "Artikel vorschlagen, (3) den Nutzen (Freisetzung des gebundenen Kapitals) benennen. "
            "Reiner Fließtext, keine Aufzählung, keine Einleitungsfloskel."
        )
    elif body.kind == "region_potential":
        facts = _region_facts(row)
        lines = [
            f"Bundesland: {body.label or row.get('Bundesland', '')}",
            f"Auftragseingang im Zeitraum: {_ra_de(row.get('Umsatz'), '€')} "
            f"(Vorjahr {_ra_de(row.get('UmsatzVJ'), '€')})",
            f"Anteil am Inlands-Auftragseingang: {_ra_de(row.get('UmsatzAnteil'))} %",
            f"Bevölkerungsanteil des Bundeslands: {_ra_de(row.get('BevoelkerungsAnteil'))} %",
            # Faktor, KEIN Prozentwert – ohne diese Erklärung liest das Modell die Zahl
            # als Prozentangabe und formuliert Unsinn ("0,2 Prozent Marktdurchdringung").
            f"Marktdurchdringung: Faktor {_ra_de(row.get('Marktdurchdringung'))} "
            f"(Faktor 1,0 = Umsatzanteil entspricht genau dem Bevölkerungsanteil, "
            f"unter 1,0 = schwächer erschlossen, über 1,0 = stärker erschlossen)",
            f"Aktive Kunden im Bundesland: {_ra_de(row.get('Kunden'))}",
            f"Davon mit rückläufigem Umsatz: {_ra_de(row.get('KundenRueckgang'))} "
            f"(zusammen {_ra_de(row.get('RueckgangSumme'), '€')} weniger als im Vorjahr)",
        ]
        if facts.get("potenzial") is not None:
            lines.append(f"Rechnerisches Zusatzpotenzial bei durchschnittlicher Durchdringung: "
                         f"{_ra_de(facts['potenzial'], '€')}")
        if row.get("Kandidaten"):
            lines.append(f"Größte Rückgänge (Betrieb, Ort, Rückgang): {row.get('Kandidaten')}")
        system = (
            "Du bist ein nüchterner Vertriebsleiter, der einem Geschäftsführer zuarbeitet. Du erhältst "
            "FERTIG BERECHNETE Fakten zu EINEM Bundesland: Auftragseingang, Vorjahresvergleich, den "
            "Umsatzanteil im Vergleich zum Bevölkerungsanteil (= Marktdurchdringung) und eine Liste "
            "konkreter Betriebe mit Umsatzrückgang. Rechne NICHTS nach und ändere keine Zahlen. "
            "Formuliere in 4–5 kurzen deutschen Sätzen: (1) ob die Region gemessen an ihrer Größe "
            "unter- oder überdurchschnittlich erschlossen ist, (2) woran das laut Zahlen liegt "
            "(wenige Kunden insgesamt oder Rückgänge bei Bestandskunden), (3) NENNE die zwei bis drei "
            "wichtigsten Betriebe aus der Liste NAMENTLICH als konkrete Nachfass-Kandidaten, "
            "(4) einen realistischen nächsten Schritt (Besuchstour, Telefonaktion, Außendienst-Einsatz). "
            "Erfinde keine Firmennamen, die nicht in der Liste stehen. Reiner Fließtext, keine "
            "Aufzählung, keine Einleitungsfloskel."
        )
    elif body.kind == "article_description":
        facts = _description_facts(row)
        lines = [
            f"Artikelname: {row.get('Artikel') or body.label or ''}",
            f"Artikelnummer: {row.get('ArtNr', '')}",
            f"Hersteller: {row.get('Hersteller') or '– nicht hinterlegt –'}",
            f"EAN: {row.get('EAN') or '– nicht hinterlegt –'}",
            f"Hersteller-Artikelnummer: {row.get('HAN') or '– nicht hinterlegt –'}",
            f"Warengruppe: {row.get('Warengruppe') or '– nicht hinterlegt –'}",
        ]
        if row.get("Kurzbeschreibung"):
            lines.append("Technische Daten aus dem Artikelstamm (WÖRTLICH übernehmen, nichts umrechnen):\n"
                         f"{row['Kurzbeschreibung']}")
        if row.get("Beschreibung"):
            lines.append(f"Vorhandene (zu knappe) Beschreibung:\n{row['Beschreibung']}")

        # Herstellerdaten: exakt über die Hersteller-Artikelnummer nachgeschlagen,
        # deshalb belastbarer als alles andere im Faktenblock.
        if body.use_research:
            from app.services.product_research import recherchiere
            try:
                gefunden = recherchiere(row.get("Hersteller", ""), row.get("HAN", ""))
            except Exception as e:
                logger.warning("Herstellerrecherche fehlgeschlagen: %s", e)
                gefunden = None
            facts["research"] = gefunden
            if gefunden:
                daten = "\n".join(f"{k}: {v}" for k, v in gefunden["daten"].items())
                if gefunden.get("angaben"):
                    daten += "\n" + "\n".join(gefunden["angaben"])
                lines.append(
                    f"Offizielle Angaben des Herstellers ({gefunden['hersteller']}, "
                    f"nachgeschlagen über die Hersteller-Artikelnummer):\n{daten}")
        system = (
            "Du schreibst Produktbeschreibungen für den Onlineshop eines Großhändlers. "
            "Du bekommst die Stammdaten EINES Artikels. Schreibe eine deutsche Beschreibung von "
            "3 bis 5 Sätzen, sachlich, in ganzen Sätzen und ohne Aufzählung.\n"
            "Stehen offizielle Herstellerangaben in den Fakten, sind sie die verlässlichste Quelle. "
            "Nutze sie vorrangig und nimm daraus auf jeden Fall auf, was dort steht: Material, "
            "Rezyklat-/Regeneratanteil, Marke bzw. Produktlinie und Zertifizierungen (z. B. Blauer "
            "Engel). Genau diese Angaben fehlen im Artikelstamm und sind der Mehrwert der Recherche — "
            "widersprechen sie dem Artikelstamm, gilt die Herstellerangabe.\n"
            "REGEL 1 – nichts erfinden: Verwende ausschließlich Angaben aus den Fakten. Maße, Material, "
            "Farbe, Größe, Inhalt, Stärke und Verpackungseinheiten nur, wenn sie dort stehen (Artikelname "
            "und technische Daten enthalten sie oft). Keine erfundenen Zertifikate, Normen, Herkunfts- "
            "oder Haltbarkeitsangaben.\n"
            "REGEL 2 – keine Eigenschaftsbehauptungen: Schreibe NICHTS über Weichheit, Qualität, Komfort, "
            "Reißfestigkeit, Ergiebigkeit, Hygiene, Umweltfreundlichkeit oder Eignung, solange das nicht "
            "wörtlich in den Fakten steht. Keine Superlative, keine Preisangaben, keine Versprechen.\n"
            "REGEL 3 – Zahlen wörtlich: Übernimm jede Zahlenangabe genau so, wie sie dasteht, samt "
            "ihrer Bezugsgröße. Rechne nichts um, teile nichts und ordne keine Zahl einer anderen "
            "Einheit zu. JEDE ZEILE der technischen Daten ist eine eigenständige Angabe — verbinde "
            "niemals zwei Zeilen zu einer Aussage. Steht in einer Zeile nur eine Zahl mit Kürzel "
            "(z. B. '30 my' für die Materialstärke in Mikrometer), dann übernimm sie als eigene "
            "Angabe oder lass sie weg; hänge sie nie an eine andere Angabe an.\n"
            "REGEL 4 – Länge: Liegen wenige Angaben vor, schreibe lieber nur zwei kurze Sätze mit dem "
            "Gesicherten. Fülle nie mit allgemeinen Aussagen auf und hänge keinen Schlusssatz über "
            "fehlende Angaben an.\n"
            "Gib nur die Beschreibung aus, keine Überschrift, keine Einleitungsfloskel."
        )
    else:
        raise HTTPException(400, f"Unbekannte Aktion: {body.kind}")

    user_msg = "Fakten:\n" + "\n".join(lines)
    if body.instruction:
        user_msg += f"\n\nZusätzliche Anweisung: {body.instruction}"

    # Textmodell passend zum aktiven Provider (beim Gateway gilt `ai_dm_model`).
    from app.services.ai_service import resolve_prose_model
    chosen = await resolve_prose_model(db, svc)
    # Produktbeschreibungen brauchen mehr Raum als eine Handlungsempfehlung – und
    # weniger Temperatur: erfundene Produkteigenschaften sind hier ein echtes Risiko.
    beschreibung = body.kind == "article_description"
    params = AIParams(think=False, temperature=0.15 if beschreibung else 0.35, top_p=0.9,
                      max_tokens=500 if beschreibung else 360, num_ctx=4096)

    async def generate():
        # Berechnete Kennzahlen zuerst – die Oberfläche rendert sie als Chips.
        yield f"data: {json.dumps({'meta': facts})}\n\n"
        try:
            async for tok in svc.stream_with_context(user_msg, system, params=params, model=chosen):
                yield f"data: {json.dumps({'token': tok})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': f'Modell-Fehler: {e}'})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


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
    system, context = ctx.expression_generate_context(body.mapping_id, body.node_id, body.field_name,
                                                      description=body.description)
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
    "form_dashboard": (
        "Du bist der KI-Assistent für ein Datenmonster-Dashboard/Formular, das der Benutzer "
        "gerade ansieht. Im Kontext (Abschnitt »Kontext«) stehen die aktuell angezeigten "
        "Kennzahlen/Tabellen des aktiven Reiters sowie die gesetzten Filter (z.B. Zeitraum). "
        "Beantworte Fragen NUR anhand dieser real angezeigten Daten – erfinde keine Zahlen, "
        "rechne nicht ungefragt Werte neu und nenne nur Kennzahlen, die im Kontext vorkommen. "
        "Antworte knapp, konkret und auf Deutsch; weise auf Auffälligkeiten/Trends und ggf. "
        "Handlungsbedarf hin, wenn danach gefragt wird."
    ),
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
        "Datasets (Datenquellen) werden auf einem Canvas platziert und deren Felder über "
        "Verbindungen auf Zielfelder gemappt. Verarbeitungs-Nodes transformieren Daten on-the-fly.\n\n"
        "Im Kontext sind die aktuellen Canvas-Datasets (mit Spalten), die aktiven Verarbeitungs-Nodes "
        "und ggf. Tabellenbeziehungen vorhanden. Nutze diese um konkrete Vorschläge zu machen.\n\n"
        "VERFÜGBARE VERARBEITUNGS-NODES — was sie tun:\n\n"
        "• Transform-Node (transform): Transformiert ein einzelnes Feld. Untermodi:\n"
        "  - text_upper/lower: Groß-/Kleinschreibung\n"
        "  - text_trim: Leerzeichen entfernen\n"
        "  - text_replace: Text ersetzen (mit Regex-Option)\n"
        "  - text_substring: Teilstring extrahieren\n"
        "  - text_concat: Mehrere Felder verketten (mit Trennzeichen)\n"
        "  - date_format: Datum umformatieren (z.B. DD.MM.YYYY → YYYY-MM-DD)\n"
        "  - date_extract: Teil eines Datums extrahieren (Jahr, Monat, Tag, Wochentag)\n"
        "  - number_format: Zahl runden, als Integer casten\n"
        "  - number_abs: Absolutwert\n"
        "  Gut für: einfache Feldreinigung, Datumsformate anpassen, Text normalisieren.\n\n"
        "• Konstante (constant): Erzeugt ein neues Feld mit einem fixen Wert "
        "(statischer Text, Zahl, Datum, Boolean oder aktuelles Datum/Uhrzeit). "
        "Gut für: Herkunftsfelder, Standardwerte, Audit-Timestamps.\n\n"
        "• SQL-Node (sql): Führt SQL gegen eine Datenbankverbindung aus. Modi:\n"
        "  - scalar: Gibt einen einzelnen Wert zurück (z.B. SELECT max(id) FROM ...)\n"
        "  - column: Gibt eine Spalte zurück (Lookup-ähnlich per Row-Index)\n"
        "  - lookup: Sucht per Schlüsselfeld einen Wert in einer DB-Tabelle\n"
        "  - transform: Transformiert einen Wert per SQL-Ausdruck\n"
        "  Gut für: DB-Lookups, berechnete Werte aus Datenbank, komplexe Abfragen.\n\n"
        "• Aggregation (agg): Aggregiert mehrere Zeilen zu einer — SUM, COUNT, AVG, MIN, MAX, "
        "GROUP BY mit mehreren Feldern. Gibt das Ergebnis als neue Felder aus. "
        "Gut für: Umsatz summieren, Anzahl berechnen, Gruppierungen.\n\n"
        "• Berechnung (calc): Fensterfunktionen über das gesamte Dataset:\n"
        "  - cumsum: Kumulierte Summe\n"
        "  - rolling_avg: Gleitender Durchschnitt (mit Fenstergröße)\n"
        "  - rank: Rang innerhalb einer Gruppe\n"
        "  - pct_change: Prozentuale Veränderung zum Vorgänger\n"
        "  Gut für: Zeitreihen, Rankings, Trendberechnungen.\n\n"
        "• Lookup-Node (lookup): Schlägt einen Wert in einem anderen Dataset nach "
        "(kein DB-Zugriff nötig). Konfigurierbar was passiert wenn kein Treffer: null/leer/Fehler. "
        "Gut für: Artikelbezeichnungen nachschlagen, Ländercodes übersetzen.\n\n"
        "• Switch-Node (switch): Verzweigt per Bedingung auf verschiedene Ausgabefelder — "
        "ähnlich CASE WHEN in SQL. Branches mit Bedingungen (has_rows, threshold, always). "
        "Gut für: bedingte Werte, Fallback-Logik.\n\n"
        "• Python-Node (python): Freies Python-Skript das Zugriff auf das gesamte Dataset als "
        "pandas DataFrame hat. Kann beliebig viele neue Felder erzeugen. "
        "Gut für: komplexe Berechnungen, Regex, externe Bibliotheken.\n\n"
        "• KI-Transform (ai_transform): Lila Node — sendet Felder per {{feldname}}-Template an "
        "ein lokales KI-Modell (Ollama) und extrahiert strukturierte Ausgabefelder. "
        "Gut für: Kategorisierung, Zusammenfassung, NLP-Aufgaben.\n\n"
        "• Expression-Node (expr): Berechnet neue Felder über Python-ähnliche Ausdrücke "
        "(z.B. row['preis'] * row['menge'], if/else, String-Operationen). "
        "Gut für: einfache Berechnungen ohne vollständiges Python-Skript.\n\n"
        "• Datenqualitäts-Node (data_quality): Prüft Regeln (not_null, regex, range, unique) "
        "und markiert/filtert fehlerhafte Zeilen. Gut für: Validierung vor dem Schreiben.\n\n"
        "• Params-Node (params): Empfängt Parameter die beim Pipeline-Aufruf übergeben werden "
        "(z.B. Datum, Mandant-ID). Macht Mappings parametrisierbar. "
        "Gut für: wiederverwendbare Mappings mit variablen Werten.\n\n"
        "• REST-Node (rest): Ruft eine externe API pro Zeile ab und mappt die Antwort "
        "auf neue Felder. Gut für: Adressvalidierung, Geocoding, externe Anreicherung.\n\n"
        "WICHTIG: Du siehst nur Spaltennamen, keine semantischen Beschreibungen. "
        "Erfinde KEINE Bedeutungen aus Feldnamen. "
        "Falls der Kontext ein 'Aktives Element' enthält, hat der Benutzer genau dieses Element angeklickt — "
        "beziehe dich gezielt darauf. "
        "Falls Tabellenbeziehungen vorhanden sind, nutze diese für JOIN-Empfehlungen. "
        "Falls keine bekannt sind, sag das ehrlich. "
        "Falls 'lastRunError' im Kontext: erkläre Ursache, zeige kritische Stelle, gib Lösungsschritte.\n\n"
        "BAUAUFTRÄGE — WICHTIG:\n"
        "Will der Benutzer, dass etwas im Mapping ENTSTEHT (\"erstelle mir…\", \"ich brauche ein "
        "Mapping…\", \"ich benötige…\", \"füg eine Spalte hinzu…\"), dann erkläre es NICHT und "
        "schreibe KEIN SQL. Antworte in diesem Fall AUSSCHLIESSLICH mit einer einzigen Zeile:\n"
        "[[BAUEN]] <die Aufgabe in einem Satz, mit allen genannten Feldern und Filtern>\n"
        "Nichts davor, nichts danach. Datenmonster baut daraus die Nodes und zeigt sie dem "
        "Benutzer zur Bestätigung — dabei kennt es das Datenbankschema, du hier nicht.\n"
        "Beispiel Eingabe: \"Ich benötige ein Mapping der Kunden, die dieses Jahr nichts gekauft "
        "haben, aber letztes Jahr schon. Zielfelder Kundennummer, Nachname, Vorname, Datum letzter Kauf\"\n"
        "Beispiel Antwort: [[BAUEN]] Kunden mit Kauf im Vorjahr, aber ohne Kauf im laufenden Jahr; "
        "Ausgabe: Kundennummer, Nachname, Vorname, Datum des letzten Kaufs\n"
        "Bei echten FRAGEN (\"was ist…\", \"wie funktioniert…\", \"warum…\") antwortest du normal "
        "und benutzt den Marker NICHT."
    ),
    "pipeline_editor": (
        "Du bist der KI-Assistent für den Pipeline-Editor von Datenmonster. "
        "Pipelines steuern die Ausführungsreihenfolge von Mappings und können "
        "Bedingungen prüfen, E-Mails versenden, FTP-Aktionen ausführen, "
        "Mappings parametrisiert aufrufen und Verzweigungen enthalten.\n\n"
        "Im Kontext sind die aktuellen Nodes auf dem Canvas, die Verbindungen zwischen ihnen "
        "sowie die verfügbaren Node-Typen aufgelistet. Nutze diese Informationen um konkrete "
        "Verbesserungs- und Erweiterungsvorschläge zur aktuellen Pipeline zu machen.\n\n"
        "VERFÜGBARE NODE-TYPEN — was sie tun und wann man sie einsetzt:\n\n"
        "• Zeitplan-Trigger (trigger): Startet die Pipeline automatisch — täglich zu einer Uhrzeit, "
        "stündlich oder per benutzerdefiniertem Cron-Ausdruck. Jede automatisierte Pipeline braucht genau einen Trigger als Startpunkt.\n\n"
        "• FTP-Import (ftp): Lädt Dateien von einem FTP/SFTP-Server herunter und stellt sie als "
        "Dataset bereit. Konfigurierbar was nach dem Import passiert (nichts / löschen / archivieren). "
        "Typisch als erster Schritt nach dem Trigger wenn Quelldaten per FTP ankommen.\n\n"
        "• REST-Abruf (rest_fetch): Ruft eine externe REST-API ab und speichert das Ergebnis als "
        "Dataset. Gut für Stammdaten-Abgleiche, Wechselkurse, externe Kataloge o.ä.\n\n"
        "• Mapping-Ausführung (mapping): Führt ein gespeichertes Mapping aus — der Kern jeder Pipeline. "
        "Transformiert Daten, führt Joins aus, wendet alle konfigurierten Nodes (Transform, Python, SQL, "
        "KI-Transform usw.) an und schreibt das Ergebnis. on_error=stop bricht die Pipeline ab, "
        "on_error=continue macht weiter. Kann mit Parametern aufgerufen werden.\n\n"
        "• Verzweigung (dispatcher): Teilt den Flow in mehrere parallele Pfade auf. "
        "Sinnvoll wenn mehrere Mappings unabhängig voneinander ausgeführt werden sollen "
        "(z.B. Rechnungsexport UND Bestandsupdate parallel).\n\n"
        "• Bedingung (condition): Prüft einen Feldwert aus dem Kontext (==, !=, >, <, enthält) und "
        "verzweigt in einen true- oder false-Ausgang. Gut für 'führe E-Mail-Node nur aus wenn "
        "Mapping Fehler hatte' oder 'FTP-Upload nur wenn Datensätze vorhanden'.\n\n"
        "• FTP-Upload (ftp_upload): Lädt eine Ausgabedatei (CSV, XML o.ä.) auf einen FTP/SFTP-Server "
        "hoch. Typisch als letzter Schritt wenn das Ergebnis eines Mappings an einen Partner geliefert wird.\n\n"
        "• E-Mail-Versand (email): Sendet eine E-Mail mit optionalem Dataset-Anhang. "
        "send_on=always immer, send_on=on_error nur bei Fehler, send_on=on_success nur bei Erfolg. "
        "Gut für Benachrichtigungen, Fehler-Alerts oder automatische Reports als E-Mail-Anhang.\n\n"
        "• Business Insights (business_insights): Analysiert ein Dataset und erstellt "
        "Geschäftsauswertungen (Umsatzentwicklung, Länderanalyse, Top-Kunden, Lagerbestand). "
        "Berechnungen laufen lokal per pandas. Das Ergebnis ist ein neues Dataset, "
        "das z.B. direkt per E-Mail-Node verschickt werden kann.\n\n"
        "TYPISCHE PIPELINE-MUSTER:\n"
        "- Einfache ETL: Trigger → FTP-Import → Mapping → FTP-Upload\n"
        "- Mit Fehler-Alert: Trigger → Mapping → Bedingung(on_error) → E-Mail\n"
        "- Parallele Verarbeitung: Trigger → Mapping → Verzweigung → [Mapping A + Mapping B]\n"
        "- Report-Versand: Trigger → Mapping → Business Insights → E-Mail(mit Anhang)\n"
        "- API-Abgleich: Trigger → REST-Abruf → Mapping(mit Lookup auf API-Daten) → FTP-Upload"
    ),
    "report_editor": (
        "Du bist der KI-Assistent für den Report-Editor von Datenmonster. "
        "Reports visualisieren Daten aus Datasets als Diagramme (Balken, Linie, Kreis), "
        "Tabellen und KPI-Kacheln."
    ),
    "form_editor": (
        "Du bist der KI-Assistent für den Formular-Editor von Datenmonster. "
        "Formulare bestehen aus drei Bereichen: Eingabefelder (die der Benutzer ausfüllt), "
        "Aktionen (Buttons die ein Mapping auslösen) und Widgets (Ergebnis-Anzeige nach Mapping-Ausführung). "
        "Im Kontext sind die aktuellen Felder, Aktionen und Widgets aufgelistet. "
        "Beziehe dich darauf um konkrete Verbesserungsvorschläge zu machen.\n\n"
        "VERFÜGBARE FELD-TYPEN:\n\n"
        "Eingabe:\n"
        "• text — Einzeiliges Textfeld. Gut für Namen, Suchtexte, kurze Freitexte.\n"
        "• textarea — Mehrzeiliger Text. Gut für Bemerkungen, Beschreibungen.\n"
        "• number — Zahlenfeld. Gut für Mengen, Preise, IDs.\n"
        "• date — Datumswähler. Gut für Von/Bis-Filter, Abrechnungszeiträume.\n"
        "• time — Uhrzeitfeld.\n"
        "• file — Dateiauswahl. Gut für CSV/XML-Upload als Mapping-Input.\n\n"
        "Auswahl:\n"
        "• checkbox — Einzelne Ja/Nein-Option.\n"
        "• switch — Toggle-Schalter, optisch ansprechende Alternative zur Checkbox.\n"
        "• dropdown — Auswahl aus einer Liste (Einzelauswahl). Optionen können statisch oder "
        "aus einem Dataset geladen werden.\n"
        "• multiselect — Mehrfachauswahl aus einer Liste.\n"
        "• radio — Radio-Buttons für kleine Auswahllisten (2-5 Optionen).\n\n"
        "Aktionen:\n"
        "• button — Löst eine konfigurierte Aktion aus (z.B. run_mapping). "
        "Buttons sind mit einer Aktion verknüpft — ohne Aktion passiert nichts.\n\n"
        "Layout:\n"
        "• heading — Abschnittsüberschrift zur Strukturierung.\n"
        "• label — Statischer Infotext.\n"
        "• divider — Trennlinie.\n"
        "• container — Gruppenrahmen für zusammengehörige Felder.\n\n"
        "AKTIONEN:\n"
        "• run_mapping — Führt ein gespeichertes Mapping aus. Die Eingabefeldwerte werden als "
        "Parameter übergeben (der Params-Node im Mapping empfängt sie). "
        "Das Ergebnis-Dataset wird an die verknüpften Widgets weitergegeben.\n\n"
        "WIDGETS (Ergebnisanzeige nach Mapping-Ausführung):\n"
        "• table — Zeigt das Mapping-Ergebnis als scrollbare Tabelle mit optionalem CSV-Download.\n"
        "• kpi — Zeigt einen einzelnen Kennwert groß an (Summe, Durchschnitt, Anzahl etc.).\n"
        "• bar — Balkendiagramm für Kategorienvergleiche.\n"
        "• line — Liniendiagramm für Zeitreihen und Trends.\n"
        "• pie — Kreisdiagramm für Anteile.\n\n"
        "TYPISCHER AUFBAU EINES FORMULARS:\n"
        "1. Eingabefelder (date/dropdown/number) → 2. Button (löst run_mapping aus) → "
        "3. Widget (zeigt Ergebnis). "
        "Ein Formular kann mehrere Aktionen und Widgets haben — z.B. eine Tabelle + eine KPI-Kachel "
        "die beide vom selben Button-Klick befüllt werden.\n\n"
        "WIE PARAMETER (VARIABLEN) FUNKTIONIEREN:\n\n"
        "Der Datenfluss von Formular → Mapping läuft in drei Schritten:\n\n"
        "Schritt 1 — Params-Node im Mapping:\n"
        "Im Mapping-Editor einen Params-Node auf den Canvas ziehen. "
        "Dort für jede Variable einen Eintrag anlegen: 'Name' = interner Variablenname (z.B. 'von_datum'), "
        "'Typ' = text/zahl/datum, 'Default' = Fallbackwert wenn kein Formular aufruft. "
        "Der Params-Node macht die Variablen im gesamten Mapping verfügbar.\n\n"
        "Schritt 2 — Variable in Formular-Feld verknüpfen:\n"
        "Im Formular-Editor hat jedes Eingabefeld ein 'Name'-Attribut. "
        "Dieses Name-Attribut MUSS exakt mit dem Variablennamen im Params-Node übereinstimmen "
        "(z.B. Formularfeld name='von_datum' → Params-Node Variable name='von_datum'). "
        "Beim Button-Klick werden alle Feldwerte mit ihrem Namen als Parameter übergeben.\n\n"
        "Schritt 3 — Variable in Mapping-Nodes nutzen:\n"
        "Die Variable steht in allen Nodes als Feldname zur Verfügung:\n"
        "• SQL-Node: `WHERE datum >= {von_datum}` (geschweifte Klammern, SQL-Injection-sicher)\n"
        "• Expression-Node: `{von_datum}` oder `_if_({menge} > 0, {preis} * {menge}, 0)`\n"
        "• Python-Node: `row['von_datum']` — die Variable ist im `row`-Dictionary\n"
        "• Transform-Node: Den Params-Node-Output als Input-Feld wählen\n\n"
        "BEISPIEL — Umsatzauswertung nach Zeitraum:\n"
        "```\n"
        "Formular:\n"
        "  [date] name='von_datum'   → Params-Node: von_datum (datum)\n"
        "  [date] name='bis_datum'   → Params-Node: bis_datum (datum)\n"
        "  [button] → Aktion: run_mapping → Mapping 'Umsatzauswertung'\n"
        "  [table] Widget zeigt Ergebnis\n\n"
        "Mapping (Umsatzauswertung):\n"
        "  Params-Node: von_datum, bis_datum\n"
        "  SQL-Node (scalar): SELECT SUM(betrag) FROM tRechnung\n"
        "                     WHERE datum BETWEEN {von_datum} AND {bis_datum}\n"
        "```\n\n"
        "WICHTIG: Formular-Parameter können auch aus einer Pipeline kommen (Params-Übergabe "
        "beim Mapping-Ausführungs-Node). Das Mapping selbst merkt keinen Unterschied — "
        "es empfängt immer nur einen dict mit Variablenname → Wert."
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
    provider: Optional[str] = None
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

    svc = _require_ai(db, body.provider)
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

    # Beim Gateway zählt dessen eigenes Modell – ein Ollama-Name (qwen…, gemma…) liefe
    # an der Whitelist des Gateways vorbei. Die Fähigkeiten-Einschätzung unten bleibt am
    # zuvor gewählten Modell, sie steuert nur Kontextgröße und Parameter.
    if getattr(svc, "is_gateway", False):
        model_used = getattr(svc, "model", None) or "auto"

    caps = get_model_caps(model_used)

    # Memory-Kontext aufbauen
    project_id = body.page_context.get("project_id") or body.page_context.get("currentData", {}).get("project_id")
    memory_context = ""
    try:
        from app.services.ai_memory_service import build_memory_context
        from app.models.dataset import DbConnection

        _category_hint = None
        _page = body.page_context.get("page", "")
        if _page == "mapping_editor":
            _category_hint = "sql"

        # Verbindungsnamen für Datasource-Wissen ermitteln
        _conn_ids = (body.page_context.get("currentData") or {}).get("connectionIds", [])
        _ds_names: list[str] = []
        if _conn_ids:
            _conns = db.query(DbConnection).filter(DbConnection.id.in_(_conn_ids)).all()
            _ds_names = [c.name for c in _conns if c.name]

        # Woran die Auswahl das passende Wissen erkennt: die Frage selbst plus
        # das, was auf der Seite gerade offen ist. Ohne diese Hinweise landet
        # bei „welche Spalte nehme ich hier?" nichts Passendes im Kontext.
        _hinweis_teile: list[str] = [_page, body.page_context.get("description", "")]
        if isinstance(_cd, dict):
            _an = _cd.get("activeNode")
            if isinstance(_an, dict):
                _hinweis_teile += [str(_an.get(k)) for k in
                                   ("label", "type", "table", "tableName", "query", "sql")
                                   if _an.get(k)]
            for _n in (_cd.get("canvasNodes") or [])[:25]:
                if isinstance(_n, dict):
                    _hinweis_teile += [str(_n.get("label") or ""), str(_n.get("type") or "")]
            for _r in (_cd.get("tableRelationships") or [])[:25]:
                _hinweis_teile.append(str(_r)[:200])
            _sc = _cd.get("schemaContext")
            if isinstance(_sc, str) and _sc:
                # Der Schema-Kontext kann zehntausende Zeichen haben — für die
                # Stichwortsuche reicht der Anfang (dort stehen die Tabellen).
                _hinweis_teile.append(_sc[:1500])
        _hinweise = " ".join(t for t in _hinweis_teile if t)[:3000]

        # Nur so viel Wissen, wie neben Systemprompt, Seitendaten und Verlauf noch
        # ins Kontextfenster passt — sonst schneidet Ollama still ab, und zwar
        # nicht zwingend am Wissen.
        from app.services.ai_memory_service import budget_nach_platz
        _belegt = (len(_BASE_SYSTEM) + len(_PAGE_SYSTEM_PROMPTS.get(_page, ""))
                   + len(str(_cd)) + len(body.message)
                   + sum(len(m.content or "") for m in body.history))

        memory_context = build_memory_context(
            db,
            project_id=project_id,
            datasource_ids=_ds_names or None,
            category_hint=_category_hint,
            frage=body.message,
            hinweise=_hinweise,
            budget=budget_nach_platz(_belegt, params.num_ctx),
        )
    except Exception as _me:
        log.warning(f"[AI Memory] Kontext-Build fehlgeschlagen: {_me}")

    page = body.page_context.get("page", "")
    description = body.page_context.get("description", "")
    current_data = body.page_context.get("currentData", {})

    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    page_prompt = _PAGE_SYSTEM_PROMPTS.get(page, "")
    system_sections: list[dict] = [
        {"label": "Basis", "content": _BASE_SYSTEM},
        {"label": "Uhrzeit", "content": f"Aktuelle Uhrzeit: {now_str}"},
    ]
    if memory_context:
        system_sections.append({"label": "AI Memory", "content": memory_context})
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
            canvas_nodes = current_data.get("canvasNodes", [])
            connection_flow = current_data.get("connectionFlow", [])
            available_node_types = current_data.get("availableNodeTypes", [])
            processing_nodes = current_data.get("processingNodes", [])
            form_fields  = current_data.get("fields",   [])
            form_actions = current_data.get("actions",  [])
            form_widgets = current_data.get("widgets",  [])
            # frontend-interne Felder nicht roh an die KI weitergeben
            _strip = {"activeNode", "tableRelationships", "schemaContext", "connectionIds",
                      "lastRunError", "canvasNodes", "connectionFlow", "availableNodeTypes",
                      "processingNodes", "fields", "actions", "widgets"}
            rest_data = {k: v for k, v in current_data.items() if k not in _strip}
        else:
            active_node = None
            last_run_error = None
            table_rels = []
            schema_ctx = ""
            canvas_nodes = []
            connection_flow = []
            available_node_types = []
            processing_nodes = []
            form_fields  = []
            form_actions = []
            form_widgets = []
            rest_data = current_data
        if active_node:
            node_str = _j.dumps(active_node, ensure_ascii=False, default=str)
            system_sections.append({"label": "Aktives Element", "content": f"Der Benutzer hat dieses Element im Canvas angeklickt:\n{node_str}"})
        if canvas_nodes:
            def _fmt_node(n):
                parts = [f"  [{n.get('label', n.get('type', '?'))}]"]
                skip = {"id", "type", "label"}
                extras = {k: v for k, v in n.items() if k not in skip and v not in (None, [], {})}
                if extras:
                    parts.append("(" + ", ".join(f"{k}={v}" for k, v in extras.items()) + ")")
                return " ".join(parts)
            node_lines = [_fmt_node(n) for n in canvas_nodes]
            canvas_str = (
                f"ACHTUNG: Die folgenden Nodes sind EXAKT die Nodes auf dem Pipeline-Canvas. "
                f"Nenne NUR diese Nodes — erfinde keine weiteren.\n\n"
                f"Nodes auf dem Pipeline-Canvas ({len(canvas_nodes)} Stück):\n"
                + "\n".join(node_lines)
            )
            if connection_flow:
                flow_lines = [
                    f"  {c.get('from', '?')} → {c.get('to', '?')}"
                    + (f" (Port: {c['port']})" if c.get("port") else "")
                    for c in connection_flow
                ]
                canvas_str += "\n\nAusführungsreihenfolge (Verbindungen):\n" + "\n".join(flow_lines)
            else:
                canvas_str += "\n\n(Noch keine Verbindungen zwischen den Nodes.)"
            system_sections.append({"label": "Pipeline-Canvas", "content": canvas_str})
        if available_node_types:
            type_lines = [f"  {t['label']} (Typ: {t['type']})" for t in available_node_types]
            system_sections.append({"label": "Verfügbare Node-Typen", "content": "Folgende Node-Typen können zur Pipeline hinzugefügt werden:\n" + "\n".join(type_lines)})
        if processing_nodes:
            def _fmt_proc(n):
                ntype = n.get("type", "?")
                parts = [f"  [{ntype}]"]
                skip = {"type"}
                extras = {k: v for k, v in n.items() if k not in skip and v not in (None, [], {}, 0)}
                if extras:
                    parts.append("(" + ", ".join(f"{k}={v}" for k, v in extras.items()) + ")")
                return " ".join(parts)
            proc_lines = [_fmt_proc(n) for n in processing_nodes]
            system_sections.append({"label": "Verarbeitungs-Nodes", "content":
                f"Folgende Verarbeitungs-Nodes sind im Mapping aktiv ({len(processing_nodes)} Stück):\n"
                + "\n".join(proc_lines)
                + "\n\nNutze diese Information um zu erklären was das Mapping tut und konkrete Verbesserungsvorschläge zu machen."})
        if form_fields or form_actions or form_widgets:
            parts = []
            if form_fields:
                def _fmt_field(f):
                    extras = {k: v for k, v in f.items() if k not in {"type", "label"} and v not in (None, False, [], {})}
                    s = f"  [{f.get('type','?')}] {f.get('label','')}"
                    if extras:
                        s += " (" + ", ".join(f"{k}={v}" for k, v in extras.items()) + ")"
                    return s
                parts.append(f"Felder ({len(form_fields)}):\n" + "\n".join(_fmt_field(f) for f in form_fields))
            if form_actions:
                action_lines = [f"  [{a.get('type','?')}] {a.get('label','')} (id={a.get('id','?')}"
                                + (f", mapping_id={a['mapping_id']}" if a.get('mapping_id') else "") + ")"
                                for a in form_actions]
                parts.append(f"Aktionen ({len(form_actions)}):\n" + "\n".join(action_lines))
            if form_widgets:
                widget_lines = [f"  [{w.get('type','?')}] {w.get('label','')}"
                                + (f" (triggered_by={w['triggered_by_action']})" if w.get('triggered_by_action') else "")
                                for w in form_widgets]
                parts.append(f"Widgets ({len(form_widgets)}):\n" + "\n".join(widget_lines))
            system_sections.append({"label": "Formular-Inhalt", "content":
                "ACHTUNG: Nur diese Elemente sind im Formular vorhanden — erfinde keine weiteren.\n\n"
                + "\n\n".join(parts)})
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
            data_str = _j.dumps(rest_data, ensure_ascii=False, default=str)[:6000]
            system_sections.append({"label": "Kontext", "content": data_str})
    system = "\n\n".join(s["content"] for s in system_sections)

    messages = [{"role": m.role, "content": m.content} for m in body.history]
    messages.append({"role": "user", "content": body.message})

    # Prompt Cache: nur bei einfachen Single-Turn-Anfragen (kein History), Schnell/Auto-Modus
    _cache_key_str: str | None = None
    _enable_cache  = not body.history and body.mode in ("schnell", "auto")
    if _enable_cache:
        import hashlib as _hl, json as _jc
        _raw = _jc.dumps({
            "msg":     body.message,
            "system":  system[:800],
            "model":   model_used,
            "project": str(project_id or ""),
        }, ensure_ascii=False, sort_keys=True)
        _cache_key_str = _hl.sha256(_raw.encode()).hexdigest()[:32]
        try:
            from app.services.ai_memory_service import cache_lookup_by_key
            _cached = cache_lookup_by_key(db, _cache_key_str)
            if _cached:
                async def _cached_gen():
                    meta: dict = {
                        "model": model_used, "category": category, "mode": body.mode,
                        "caps": caps, "cached": True,
                        "params": {"think": False, "temperature": 0, "top_p": 0, "max_tokens": 0, "num_ctx": 0},
                    }
                    yield f"data: {json.dumps({'meta': meta})}\n\n"
                    yield f"data: {json.dumps({'token': _cached})}\n\n"
                    yield "data: [DONE]\n\n"
                from fastapi.responses import StreamingResponse as _SR0
                return _SR0(_cached_gen(), media_type="text/event-stream")
        except Exception as _ce:
            log.warning(f"[AI Cache] Lookup fehlgeschlagen: {_ce}")

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
        _tokens: list[str] = []
        try:
            async for token in svc._stream(messages, system, params=params, model=model_used):
                _tokens.append(token)
                yield f"data: {json.dumps({'token': token})}\n\n"
            # Cache speichern wenn aktiviert
            if _cache_key_str and _tokens:
                try:
                    from app.services.ai_memory_service import cache_store_by_key
                    from app.core.database import SessionLocal as _SL
                    _cdb = _SL()
                    try:
                        cache_store_by_key(_cdb, _cache_key_str, body.message, "".join(_tokens), model_used, project_id)
                    finally:
                        _cdb.close()
                except Exception as _se:
                    log.warning(f"[AI Cache] Store fehlgeschlagen: {_se}")
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
        # Nur Beziehungen, die eine der ausgewählten Tabellen berühren. Seit sie
        # sich aus den Schlüsseln ableiten lassen, können es hunderte sein — alle
        # in jeden Prompt zu schreiben wäre genau die Aufblähung, gegen die die
        # Kontext-Auswahl gebaut wurde.
        rels_relevant = [r for r in manual_rels
                         if r.from_table in selected_names or r.to_table in selected_names]
        if rels_relevant:
            lines.append(""); lines.append("## Bekannte FK-Beziehungen")
            for r in rels_relevant:
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
    # Beim Gateway zählt dessen eigenes Modell – ein Ollama-Name (qwen…, gemma…) liefe
    # an der Whitelist des Gateways vorbei. Die Fähigkeiten-Einschätzung unten bleibt am
    # zuvor gewählten Modell, sie steuert nur Kontextgröße und Parameter.
    if getattr(svc, "is_gateway", False):
        model_used = getattr(svc, "model", None) or "auto"

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


# ── Formularfeld-Vorschlag ───────────────────────────────────────────────────

_SUGGEST_FIELDS_SYSTEM = """\
Du bist ein Formular-Designer für Datenmonster.
Deine Aufgabe: Schlage passende Formularfelder für eine Eingabemaske vor.

VERFÜGBARE FELDTYPEN:
- text        – einzeiliges Textfeld
- textarea    – mehrzeiliger Text
- number      – Zahl
- date        – Datum
- time        – Uhrzeit
- file        – Dateiauswahl
- checkbox    – Ja/Nein-Checkbox
- switch      – Toggle-Schalter
- dropdown    – Dropdown (Optionen notwendig)
- multiselect – Mehrfachauswahl (Optionen notwendig)
- radio       – Radio-Buttons (Optionen notwendig)
- heading     – Überschrift (kein Eingabefeld, nur Layout)
- label       – Hinweistext (kein Eingabefeld, nur Layout)

REGELN:
- Antworte NUR mit einem JSON-Array. Kein Text davor oder danach, kein Markdown.
- name: snake_case, kurz, eindeutig
- required: true nur bei wirklich wichtigen Feldern
- options: nur bei dropdown/multiselect/radio, als [{"value":"...","label":"..."}]
- Gruppiere logisch: headings vor inhaltlichen Blöcken
- Maximal 12 Felder
- Felder die bereits existieren NICHT nochmals vorschlagen

BEISPIEL:
[
  {"type":"heading","label":"Kundendaten","name":"","required":false},
  {"type":"text","label":"Kundennummer","name":"kundennummer","required":true,"placeholder":"z.B. K-1234"},
  {"type":"dropdown","label":"Status","name":"status","required":true,"options":[{"value":"offen","label":"Offen"},{"value":"erledigt","label":"Erledigt"}]}
]
"""


class SuggestFieldsRequest(BaseModel):
    description: str
    existing_field_names: list[str] = []


@router.post("/suggest-fields")
async def suggest_fields(
    body: SuggestFieldsRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Schlägt Formularfelder aus einer Beschreibung vor (SSE)."""
    svc = _require_ai(db)

    existing = ""
    if body.existing_field_names:
        existing = f"\nBereits vorhandene Felder (nicht nochmals vorschlagen): {', '.join(body.existing_field_names)}"

    user_msg = f"Formular-Beschreibung: {body.description}{existing}"

    async def generate():
        import re as _re
        tokens = []
        async for token in svc.stream_with_context(user_msg, _SUGGEST_FIELDS_SYSTEM):
            tokens.append(token)
            yield f"data: {json.dumps({'token': token})}\n\n"

        raw = "".join(tokens)
        cleaned = _re.sub(r"^```[a-zA-Z]*\s*", "", raw.strip(), flags=_re.MULTILINE)
        cleaned = _re.sub(r"```\s*$", "", cleaned, flags=_re.MULTILINE).strip()

        start = cleaned.find("[")
        end   = cleaned.rfind("]")
        if start == -1 or end == -1:
            yield f"data: {json.dumps({'error': 'KI hat kein gültiges JSON zurückgegeben'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        try:
            fields = json.loads(cleaned[start:end + 1])
        except Exception as e:
            yield f"data: {json.dumps({'error': f'JSON-Parsing fehlgeschlagen: {str(e)}'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        valid = []
        allowed_types = {"text","textarea","number","date","time","file","checkbox","switch",
                         "dropdown","multiselect","radio","heading","label","divider","button"}
        for f in fields:
            if not isinstance(f, dict):
                continue
            t = f.get("type", "")
            if t not in allowed_types:
                continue
            valid.append({
                "type":        t,
                "label":       str(f.get("label", t)).strip(),
                "name":        str(f.get("name", "")).strip(),
                "required":    bool(f.get("required", False)),
                "placeholder": str(f.get("placeholder", "")).strip(),
                "options":     f.get("options", []) if isinstance(f.get("options"), list) else [],
            })

        print(f"[AI suggest-fields] {len(valid)} fields for: {body.description[:60]}", flush=True)
        yield f"data: {json.dumps({'result': valid})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


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

"sql" – SQL-Abfrage direkt gegen die Datenbank. Der mächtigste Node: liefert komplette
        Ergebnismengen (alle Zeilen einer Tabelle, Joins, Filter, Zeiträume, Gruppierungen).
  mode: "transform" (Standard – die Abfrage liefert die gesamte Datenmenge des Mappings)
        | "scalar" (ein Wert pro Zeile) | "column" | "lookup" | "exec"
  sql_description: EIN Satz auf Deutsch, WAS die Abfrage liefern soll – welche Tabelle(n),
        welcher Filter/Zeitraum, welche Spalten. Schreibe hier KEIN SQL!
        Das SQL erzeugt danach ein eigener Schritt, der das Datenbankschema kennt.
        ZEITANGABEN WÖRTLICH ÜBERNEHMEN: aus "dieses Jahr" wird "dieses Jahr",
        NICHT eine ausgerechnete Jahreszahl. Du weißt nicht, welches Jahr heute ist –
        der SQL-Schritt weiß es. Dasselbe gilt für "letzter Monat", "seit gestern" usw.
  output_field: Ausgabefeldname (nur bei mode "scalar"/"column")

REGELN:
- Sollen Daten AUS EINER DATENBANK kommen (z.B. "alle Eingangsrechnungen 2025",
  "Umsatz je Kunde", "Artikel ohne Bestand") und liegt kein passendes Dataset auf dem
  Canvas, dann nimm GENAU EINEN "sql"-Node mit mode "transform".
- Erfinde keine Feldnamen für Datenbankspalten – dafür ist die sql_description da.
- Lieber wenige, richtige Nodes als viele geratene.
- Die sql_description darf den Auftrag nur zerlegen, nie umdeuten: keine Zeiträume,
  Filter oder Spalten hinzufügen, die der Nutzer nicht genannt hat.

ANTWORT (genau dieses JSON, nichts anderes):
{"nodes":[...],"explanation":"Kurze Erklärung auf Deutsch was erstellt wurde"}\
"""


class GenerateNodesRequest(BaseModel):
    description: str
    available_datasets: list[dict] = []
    mapping_id: Optional[int] = None
    # Verbindung für SQL-Nodes: ohne sie kann das SQL weder mit Schemawissen
    # erzeugt noch geprüft werden.
    connection_id: Optional[int] = None
    canvas_nodes: list[dict] = []


def _sql_saeubern(text: str) -> str:
    """Markdown-Zaun und Geschwätz entfernen, das kleine Modelle um das SQL packen."""
    import re as _re
    t = (text or "").strip()
    fence = _re.search(r"```[a-zA-Z]*\s*(.+?)```", t, _re.DOTALL)
    if fence:
        t = fence.group(1)
    t = _re.sub(r"^```[a-zA-Z]*\s*", "", t, flags=_re.MULTILINE)
    t = _re.sub(r"```\s*$", "", t, flags=_re.MULTILINE)
    t = t.strip()
    # Vorspann wie "Hier ist die Abfrage:" abschneiden – ab dem ersten SELECT/WITH
    m = _re.search(r"\b(WITH|SELECT)\b", t, _re.IGNORECASE)
    if m and m.start() > 0:
        t = t[m.start():]
    return t.strip().rstrip(";").strip()


def _tabellen_aus_sql(sql_text: str) -> list[str]:
    """Tabellennamen hinter FROM/JOIN einsammeln (grob, aber gut genug für eine
    Leer-Diagnose). Unterabfragen und Aliase bleiben außen vor."""
    import re as _re
    namen = _re.findall(
        r"\b(?:FROM|JOIN)\s+((?:\[?[A-Za-z_][\w]*\]?\.){0,2}\[?[A-Za-z_][\w]*\]?)",
        sql_text or "", _re.IGNORECASE)
    raus, gesehen = [], set()
    for n in namen:
        n = n.strip()
        if n.lower() in ("select", "(") or n.lower() in gesehen:
            continue
        gesehen.add(n.lower())
        raus.append(n)
    return raus[:8]


def _leer_diagnose(con, sql_text: str) -> str:
    """Warum liefert eine syntaktisch gültige Abfrage keine Zeile? Zählt die
    beteiligten Tabellen einzeln. Eine leere Tabelle ist eine andere Geschichte
    als ein Join, der ins Leere greift – und das Modell braucht diesen
    Unterschied, sonst repariert es an der falschen Stelle."""
    import sqlalchemy as _sa
    zeilen = []
    leer_dabei = False
    for tab in _tabellen_aus_sql(sql_text):
        try:
            n = con.execute(_sa.text(f"SELECT COUNT(*) FROM {tab}")).scalar()
        except Exception:
            continue
        zeilen.append(f"  {tab}: {n} Zeilen")
        if not n:
            leer_dabei = True
    if not zeilen:
        return ""
    kopf = ("Eine der beteiligten Tabellen ist selbst leer:"
            if leer_dabei else
            "Alle beteiligten Tabellen sind gefüllt – es liegt also an einer "
            "JOIN-Bedingung (verknüpfte Schlüssel passen nicht zusammen) oder "
            "am WHERE-Filter:")
    return kopf + "\n" + "\n".join(zeilen)


def _spalten_nachschlag(connection_id: Optional[int], sql_text: str) -> str:
    """Die echten Spalten der im SQL verwendeten Tabellen, wörtlich aus dem
    Katalog. Bei "Ungültiger Spaltenname" ist das die zielgenaue Antwort: das
    stichwortbasierte Schema trifft die Tabelle vielleicht gar nicht, hier steht
    sie garantiert – samt dem Beweis, dass die gesuchte Spalte dort fehlt."""
    if not connection_id:
        return ""
    tabellen = _tabellen_aus_sql(sql_text)
    if not tabellen:
        return ""
    try:
        import sqlalchemy as _sa
        from app.services.mapping_service import _get_sql_engine
        engine = _get_sql_engine(connection_id)
        bloecke = []
        with engine.connect() as con:
            for tab in tabellen:
                teile = [t.strip("[]") for t in tab.split(".")]
                schema, name = (teile[-2], teile[-1]) if len(teile) > 1 else (None, teile[-1])
                sql = ("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                       "WHERE TABLE_NAME = :n" + (" AND TABLE_SCHEMA = :s" if schema else "")
                       + " ORDER BY ORDINAL_POSITION")
                werte = {"n": name} | ({"s": schema} if schema else {})
                try:
                    spalten = [r[0] for r in con.execute(_sa.text(sql), werte)]
                except Exception:
                    continue
                if spalten:
                    bloecke.append(f"  {tab}: {', '.join(spalten)}")
        if not bloecke:
            return ""
        return ("Die tatsächlichen Spalten der von dir verwendeten Tabellen:\n"
                + "\n".join(bloecke)
                + "\nSteht die gesuchte Spalte hier nicht, liegt sie in einer ANDEREN "
                  "Tabelle – suche sie im Schema, statt den Namen zu raten.")
    except Exception:
        return ""


# JTL benennt Schlüsselspalten nach der Entität: kArtikel, kKunde, kRechnung.
# Ein Join zwischen zwei VERSCHIEDENEN Entitäten ist deshalb fast immer erfunden
# — und die gefährlichste Sorte Fehler, weil er weder einen SQL-Fehler noch ein
# leeres Ergebnis erzeugt: ein Modell jointe tArtikelSonderpreis.kArtikel gegen
# tkunde.kKunde, und weil sich die Nummernkreise zufällig überlappen, kamen zwei
# Zeilen heraus und die Abfrage sah fertig aus.
#
# Zwei Paare sind in der JTL-DB trotz verschiedener Namen richtig: die
# Lieferschein-Tabellen tragen den Auftrag noch unter seinem alten Namen
# „Bestellung" (geprüft: alle 28.039 tLieferschein.kBestellung treffen einen
# kAuftrag). Gemessen an den 218 SQL-Nodes der laufenden Mappings schlägt die
# Prüfung mit diesen Ausnahmen bei keiner einzigen echten Abfrage an.
_SCHLUESSEL_SYNONYME = frozenset({
    frozenset({"auftrag", "bestellung"}),
    frozenset({"auftragposition", "bestellpos"}),
})

_JOIN_PAAR = _regex.compile(r"\b(\w+)\.(k\w+)\s*=\s*(\w+)\.(k\w+)", _regex.I)


def _verdaechtige_joins(sql_text: str) -> list[str]:
    """Joins, die zwei verschiedene Entitätsschlüssel gleichsetzen."""
    treffer: list[str] = []
    for a, sa, b, sb in _JOIN_PAAR.findall(sql_text or ""):
        x, y = sa.lower().lstrip("k"), sb.lower().lstrip("k")
        # kVaterArtikel = kArtikel ist in Ordnung: der eine Name steckt im anderen.
        if x == y or x in y or y in x:
            continue
        if frozenset({x, y}) in _SCHLUESSEL_SYNONYME:
            continue
        treffer.append(f"{a}.{sa} = {b}.{sb}")
    return treffer


def _joinbefund(sql_text: str) -> Optional[str]:
    """Der Verdacht als Satz — oder None, wenn die Joins plausibel sind."""
    treffer = _verdaechtige_joins(sql_text)
    if not treffer:
        return None
    return ("Die Abfrage verbindet Schlüssel verschiedener Entitäten: "
            + "; ".join(treffer))


def _sql_pruefen(db, sql_text: str, connection_id: Optional[int],
                 canvas_nodes: list[dict] | None = None) -> tuple[list[str], Optional[str], Optional[str]]:
    """Führt die Abfrage aus und liefert (Spalten, Fehlermeldung, Leer-Befund).

    Anders als /api/mappings/sql-schema wird hier NICHT auf ein Regex-Raten
    zurückgefallen: der Bauplan soll wissen, ob das SQL wirklich läuft.

    Geprüft wird zweierlei. Erstens, ob die Datenbank die Abfrage annimmt –
    das fängt erfundene Tabellen und Spalten. Zweitens, ob wirklich Zeilen
    herauskommen: eine Abfrage kann fehlerfrei durchlaufen und trotzdem nichts
    liefern, weil ein Join auf einen Schlüssel zeigt, der nie zusammenpasst.
    Genau dieser Fall sah für die alte Prüfung (SELECT TOP 0) aus wie ein
    Erfolg, und der leere Node landete unbemerkt im Mapping.
    """
    if not sql_text:
        return [], "Kein SQL erzeugt", None
    try:
        import sqlalchemy as _sa
        import re as _re
        # Platzhalter durch NULL ersetzen, damit die Probe läuft. Damit wird die
        # Zeilenzahl aber wertlos: :von/:bis sind dann NULL und jeder Vergleich
        # darauf ist unbekannt, die Abfrage MUSS leer bleiben. Also nur bei
        # parameterlosem SQL über leere Ergebnisse urteilen.
        hat_parameter = bool(_re.search(r":[a-zA-Z_][a-zA-Z0-9_]*", sql_text))
        probe = _re.sub(r":([a-zA-Z_][a-zA-Z0-9_]*)", "NULL", sql_text)
        if connection_id:
            from app.services.mapping_service import _get_sql_engine
            engine = _get_sql_engine(connection_id)
            grenze = ("SELECT TOP 5 * FROM ({q}) __q" if engine.dialect.name == "mssql"
                      else "SELECT * FROM ({q}) __q LIMIT 5")
            with engine.connect() as con:
                try:            # Probelauf soll keine Minuten fressen
                    con.connection.timeout = 30
                except Exception:
                    pass
                res = con.execute(_sa.text(grenze.format(q=probe)))
                spalten = list(res.keys())
                treffer = len(res.fetchall())
                if treffer or hat_parameter:
                    return spalten, None, None
                return spalten, None, (
                    "Die Abfrage läuft fehlerfrei, liefert aber KEINE EINZIGE ZEILE.\n"
                    + (_leer_diagnose(con, probe) or ""))
        # Ohne Verbindung: gegen die Canvas-Datasets in einer SQLite-Kopie prüfen.
        # Dort liegen nur 5 Beispielzeilen je Dataset, ein leeres Ergebnis sagt
        # deshalb nichts aus – hier wird ausschließlich die Syntax geprüft.
        import pandas as _pd
        from app.services.file_service import read_dataset
        from app.models.dataset import Dataset
        tmp = _sa.create_engine("sqlite:///:memory:")
        for n in (canvas_nodes or []):
            ds_id = n.get("dataset_id")
            if not ds_id:
                continue
            try:
                ds = db.query(Dataset).filter(Dataset.id == ds_id).first()
                if not ds:
                    continue
                data = read_dataset(ds_id, page=0, page_size=5)
                if data.get("preview"):
                    _pd.DataFrame(data["preview"]).to_sql(
                        _re.sub(r"[^a-zA-Z0-9_]", "_", ds.name), tmp,
                        if_exists="replace", index=False)
            except Exception:
                pass
        with tmp.connect() as con:
            res = con.execute(_sa.text(f"SELECT * FROM ({probe}) __q LIMIT 0"))
            return list(res.keys()), None, None
    except Exception as e:
        return [], str(e)[:400], None


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
    else:
        ds_info = "\nAuf dem Canvas liegt noch kein Dataset.\n"
    if body.connection_id:
        ds_info += ("Eine Datenbankverbindung ist eingerichtet – Daten aus der Datenbank "
                    "holst du mit einem \"sql\"-Node (mode \"transform\").\n")
    # Ohne Datum rät das Modell das Jahr aus seinen Trainingsdaten: aus "dieses Jahr"
    # wurde eine sql_description "für das Jahr 2023", und der SQL-Schritt baute
    # gehorsam YEAR(GETDATE()) - 3 daraus. Der Zeitbezug soll wörtlich durchgereicht
    # werden – das Datum steht hier nur als Sicherheitsnetz.
    from datetime import date as _date
    _heute = _date.today()
    ds_info += (f"Heutiges Datum: {_heute.strftime('%d.%m.%Y')} – \"dieses Jahr\" ist also "
                f"{_heute.year}. Trotzdem: Zeitangaben wörtlich weiterreichen, nicht ausrechnen.\n")
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
        except Exception as e:
            yield f"data: {json.dumps({'error': f'JSON-Parsing fehlgeschlagen: {str(e)}'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        # ── Stufe 2: für jeden SQL-Node echtes SQL erzeugen ───────────────────
        # Ein kleines Modell kann nicht gleichzeitig die JSON-Struktur UND
        # korrektes SQL treffen. Stufe 1 beschreibt nur, Stufe 2 schreibt das
        # SQL mit vollem Schema- und Projektwissen und prüft es gegen die DB.
        ctx = AIContextBuilder(db)
        for n in nodes:
            if not isinstance(n, dict) or n.get("node_type") != "sql":
                continue
            n.setdefault("mode", "transform")
            # Stufe 1 formuliert die Aufgabe um und kann sie dabei verfälschen (aus
            # "dieses Jahr" wurde schon "das Jahr 2023"). Der Wortlaut des Nutzers
            # bleibt deshalb immer dabei und hat im Zweifel Vorrang.
            praezisierung = (n.get("sql_description") or "").strip()
            original = (body.description or "").strip()
            if praezisierung and praezisierung.lower() != original.lower():
                # „gilt der Auftrag oben" hieß hier die Anweisung, das Wort landete
                # aber in der Stichwortsuche und zog Verkauf.tAuftrag, tAuftragAdresse
                # und die Regel „gekauft heißt Rechnung, nicht Auftrag" in einen
                # Prompt über Preise. Der Zusatz darf kein Fachwort enthalten.
                beschreibung = (f"{original}\n\nPräzisierung aus dem Bauplan (nachrangig – "
                                f"bei Widerspruch gilt der Wortlaut oben): {praezisierung}")
            else:
                beschreibung = praezisierung or original
            yield f"data: {json.dumps({'progress': f'SQL wird erzeugt: {(praezisierung or original)[:80]}'})}\n\n"

            sql_system, sql_ctx = ctx.sql_generate_context(
                beschreibung, body.connection_id, body.mapping_id)
            auftrag = f"{sql_ctx}\n\nAufgabe: {beschreibung}" if sql_ctx else f"Aufgabe: {beschreibung}"

            from app.services.ai_service import params_fuer_prompt, timeout_fuer_prompt
            sql_params = params_fuer_prompt(len(sql_system) + len(auftrag))
            svc.timeout = timeout_fuer_prompt(len(sql_system) + len(auftrag), svc.timeout)

            sql_text = _sql_saeubern(await svc.complete_with_context(
                auftrag, sql_system, params=sql_params))
            columns, fehler, leer = _sql_pruefen(db, sql_text, body.connection_id, body.canvas_nodes)
            verdacht = _joinbefund(sql_text) if not fehler else None

            # Reparaturläufe mit dem echten Befund der Datenbank. Drei Sorten
            # Befund: abgelehnt (erfundene Tabelle/Spalte), angenommen aber ohne
            # jede Zeile, oder angenommen mit Zeilen aus einem Join, der zwei
            # fremde Entitätsschlüssel gleichsetzt. Die letzten beiden sind die
            # heimtückischen – sie sehen bis zur Vorschau wie fertige Abfragen aus.
            # Ein Versuch reicht oft nicht: der zweite Anlauf bekommt zusätzlich
            # das Schema der bemängelten Tabelle nachgereicht.
            for versuch in (1, 2):
                if not fehler and not leer and not verdacht:
                    break
                befund = fehler or leer or verdacht
                lage = ("SQL-Fehler" if fehler
                        else "Abfrage bleibt leer" if leer
                        else "Join verbindet fremde Schlüssel")
                yield f"data: {json.dumps({'progress': f'{lage}, Reparaturversuch {versuch}: {befund[:110]}'})}\n\n"
                # Bei einem Spaltenfehler zählt Genauigkeit mehr als Sparsamkeit:
                # die echten Spalten der verwendeten Tabellen kommen sofort dazu,
                # dazu das passende Schema – die gesuchte Spalte liegt ja meist in
                # einer Tabelle, die im SQL noch gar nicht vorkommt.
                spaltenfehler = bool(fehler) and bool(_re.search(
                    r"Ungültiger Spaltenname|Invalid column name|Ungültiger Objektname|Invalid object name",
                    fehler))
                nachschlag = ""
                if spaltenfehler:
                    nachschlag = "\n\n" + _spalten_nachschlag(body.connection_id, sql_text)
                if (versuch == 2 or spaltenfehler) and body.connection_id:
                    conn_obj = ctx._get_conn(body.connection_id)
                    if conn_obj:
                        from app.services.ai_context_builder import _schema_fuer_aufgabe
                        nachschlag += "\n\n" + _schema_fuer_aufgabe(conn_obj, f"{beschreibung} {befund}")
                if fehler:
                    urteil = (f"Die Datenbank lehnt es ab:\n{fehler}\n\n"
                              "Korrigiere die Abfrage. Verwende ausschließlich Tabellen und "
                              "Spalten, die oben im Schema stehen.")
                elif verdacht and not leer:
                    urteil = (f"{verdacht}\n\n"
                              "In dieser Datenbank ist eine Schlüsselspalte nach ihrer Entität "
                              "benannt: kArtikel zeigt auf einen Artikel, kKunde auf einen Kunden. "
                              "Zwei verschiedene davon gleichzusetzen verbindet zusammenhanglose "
                              "Zeilen — die Abfrage liefert dann Treffer, die nur aus überlappenden "
                              "Nummernkreisen entstehen. Suche im Schema oben die Tabelle, die "
                              "beide Seiten wirklich verbindet, und schreibe die Abfrage neu. "
                              "Gibt es keine, gehört die Tabelle nicht in die Abfrage.")
                else:
                    urteil = (f"{leer}\n\n"
                              "Das ist fast immer ein Join über zwei Schlüssel, die nichts "
                              "miteinander zu tun haben – etwa eine Bestell-ID gegen eine "
                              "Rechnungs-ID, oder eine Schnittstellentabelle statt der "
                              "Belegtabelle. Prüfe jeden JOIN einzeln: verbinden die beiden "
                              "Spalten wirklich denselben Schlüssel? Suche im Schema oben "
                              "nach der passenden Tabelle und schreibe die Abfrage neu.")
                reparatur = (
                    f"{auftrag}{nachschlag}\n\nDieses SQL wurde erzeugt:\n{sql_text}\n\n"
                    f"{urteil}\n\nAntworte NUR mit dem korrigierten SQL."
                )
                sql_neu = _sql_saeubern(await svc.complete_with_context(
                    reparatur, sql_system, params=sql_params))
                columns_neu, fehler_neu, leer_neu = _sql_pruefen(
                    db, sql_neu, body.connection_id, body.canvas_nodes)
                # Eine Reparatur, die zwar läuft, aber weiterhin leer bleibt, ist
                # keine Verschlechterung – der neue Stand wird übernommen.
                sql_text, columns, fehler, leer = sql_neu, columns_neu, fehler_neu, leer_neu
                verdacht = _joinbefund(sql_text) if not fehler else None

            n["sql"] = sql_text
            n["columns"] = columns
            n["connection_id"] = body.connection_id
            if fehler:
                n["sql_error"] = fehler
            elif leer:
                # Kein Fehler, aber auch kein Ergebnis: der Nutzer soll das vor
                # dem Übernehmen sehen und entscheiden, statt einen leeren Node
                # ins Mapping zu bekommen.
                n["sql_leer"] = leer
            elif verdacht:
                # Läuft und liefert Zeilen, aber der Join ist nicht plausibel —
                # sichtbar machen statt stillschweigend übernehmen.
                n["sql_warnung"] = verdacht

        print(f"[AI generate-nodes] {len(nodes)} nodes, explanation={explanation[:80]}", flush=True)
        yield f"data: {json.dumps({'result': {'nodes': nodes, 'explanation': explanation}})}\n\n"
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
        result = await svc.complete_json(messages, json_schema, model=model, temperature=0.2)
        return {"result": result}
    except httpx.ReadTimeout:
        raise HTTPException(504, "KI-Timeout – Modell antwortet nicht")
    except Exception as e:
        raise HTTPException(500, f"KI-Fehler: {e}")
