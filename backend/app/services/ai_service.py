import httpx
import json
import time
from dataclasses import dataclass
from typing import AsyncIterator, Optional


PRESET_MODELS = [
    {"id": "qwen2.5-coder:1.5b", "label": "Qwen 2.5 Coder 1.5B (minimal, schnell, ~2 GB)"},
    {"id": "qwen2.5-coder:3b",   "label": "Qwen 2.5 Coder 3B (Mittelweg, ~4 GB) [Standard]"},
    {"id": "qwen2.5-coder:7b",   "label": "Qwen 2.5 Coder 7B (beste Code-Qualität, ~8 GB)"},
    {"id": "llama3.2:3b",        "label": "Llama 3.2 3B (Erklärungen, Deutsch, ~2 GB)"},
    {"id": "phi4-mini",          "label": "Phi-4 Mini (Reasoning, Allrounder, ~2.5 GB)"},
]

DEFAULT_MODEL    = "qwen2.5-coder:3b"
DEFAULT_BASE_URL = "http://ollama:11434"
DEFAULT_TIMEOUT  = 120


@dataclass
class AIParams:
    think:       bool  = False
    temperature: float = 0.4
    max_tokens:  int   = 1000
    num_ctx:     int   = 8192


MODE_PARAMS: dict[str, AIParams] = {
    "schnell": AIParams(think=False, temperature=0.2, max_tokens=300,  num_ctx=2048),
    "auto":    AIParams(think=False, temperature=0.4, max_tokens=1000, num_ctx=8192),
    "analyse": AIParams(think=True,  temperature=0.5, max_tokens=4000, num_ctx=16384),
}

# Preferred model candidates per query category (ordered by preference)
_AUTO_PREFERENCE: dict[str, list[str]] = {
    "simple":  ["qwen3.5:0.9b", "qwen3.5:0.8b", "qwen3:1.7b", "qwen3.5:2b"],
    "medium":  ["qwen3.5:4b",   "qwen3:4b",     "qwen3.5:2b", "qwen3.5:0.9b"],
    "complex": ["qwen3.5:9b",   "qwen3:8b",     "qwen3.5:4b", "qwen3:4b"],
    "agent":   ["qwen3.5:9b",   "qwen3:8b",     "qwen3.5:4b"],
}

_model_cache: dict = {}


async def get_installed_models(base_url: str) -> list[str]:
    global _model_cache
    now = time.time()
    if _model_cache.get("ts", 0) + 60 > now:
        return _model_cache.get("models", [])
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get(f"{base_url}/api/tags")
            models = [m["name"] for m in r.json().get("models", [])]
            _model_cache = {"models": models, "ts": now}
            return models
    except Exception:
        return []


def classify_query(message: str) -> str:
    msg = message.lower()
    if any(w in msg for w in ["agent", "architektur", "konzept", "design", "strategie", "planung", "system design"]):
        return "agent" if "agent" in msg else "complex"
    if any(w in msg for w in ["python", "skript", "script", "funktion", "def ", "import ", "klasse"]):
        return "medium"
    if any(w in msg for w in ["sql", "select ", "join ", "where ", "query", "abfrage", "tabelle"]):
        return "simple" if len(message) < 100 else "medium"
    if len(message.strip()) < 80:
        return "simple"
    return "medium"


async def select_auto_model(message: str, base_url: str, default_model: str) -> tuple[str, str]:
    """Returns (model_name, category)."""
    category = classify_query(message)
    candidates = _AUTO_PREFERENCE.get(category, _AUTO_PREFERENCE["medium"])
    installed = await get_installed_models(base_url)
    installed_set = set(installed)
    for candidate in candidates:
        if candidate in installed_set:
            return candidate, category
        # Accept any installed variant of the same base model
        base = candidate.split(":")[0]
        for inst in installed:
            if inst.startswith(base + ":"):
                return inst, category
    return default_model, category


class AIService:
    def __init__(self, base_url: str, model: str, timeout: int = DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.model    = model
        self.timeout  = timeout

    # ── low-level ────────────────────────────────────────────────────────────

    async def _stream(
        self,
        messages: list[dict],
        system: str = "",
        json_mode: bool = False,
        params: AIParams | None = None,
        model: str | None = None,
    ) -> AsyncIterator[str]:
        payload_messages = []
        if system:
            payload_messages.append({"role": "system", "content": system})
        payload_messages.extend(messages)

        payload: dict = {
            "model":    model or self.model,
            "messages": payload_messages,
            "stream":   True,
        }
        if params is not None:
            payload["think"] = params.think
            payload["options"] = {
                "temperature": params.temperature,
                "num_predict": params.max_tokens,
                "num_ctx":     params.num_ctx,
            }
        if json_mode:
            payload["format"] = "json"

        timeout = 300 if (params and params.think) else self.timeout

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                        if chunk.get("done"):
                            break
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            yield content
                    except Exception:
                        continue

    async def _complete(self, messages: list[dict], system: str = "", json_mode: bool = False) -> str:
        result = []
        async for token in self._stream(messages, system, json_mode=json_mode):
            result.append(token)
        return "".join(result)

    async def complete_with_context(self, user_message: str, system: str = "") -> str:
        """Single-shot completion (non-streaming) — for structured JSON output."""
        return await self._complete([{"role": "user", "content": user_message}], system)

    async def stream_with_context(self, user_message: str, system: str = "", json_mode: bool = False):
        """Generic streaming entry-point used by the Context Builder."""
        async for token in self._stream([{"role": "user", "content": user_message}], system, json_mode=json_mode):
            yield token

    # ── status ───────────────────────────────────────────────────────────────

    async def check_status(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                r.raise_for_status()
                tags = r.json()
                models = [m["name"] for m in tags.get("models", [])]
                model_loaded = any(
                    m == self.model or m.startswith(self.model.split(":")[0])
                    for m in models
                )
                return {
                    "ollama_reachable": True,
                    "model_loaded": model_loaded,
                    "available_models": models,
                }
        except Exception as e:
            return {"ollama_reachable": False, "model_loaded": False, "available_models": [], "error": str(e)}


def build_ai_service(db) -> Optional["AIService"]:
    from app.api.settings import get_setting
    enabled = get_setting(db, "ai_enabled", "false")
    if enabled != "true":
        return None
    base_url = get_setting(db, "ai_base_url", DEFAULT_BASE_URL)
    model    = get_setting(db, "ai_model",    DEFAULT_MODEL)
    timeout  = int(get_setting(db, "ai_timeout", str(DEFAULT_TIMEOUT)))
    return AIService(base_url=base_url, model=model, timeout=timeout)
