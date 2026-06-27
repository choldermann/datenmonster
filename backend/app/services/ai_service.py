import httpx
import json
from typing import AsyncIterator, Optional


PRESET_MODELS = [
    {"id": "qwen2.5-coder:1.5b", "label": "Qwen 2.5 Coder 1.5B (minimal, schnell, ~2 GB)"},
    {"id": "qwen2.5-coder:3b",   "label": "Qwen 2.5 Coder 3B (Mittelweg, ~4 GB) [Standard]"},
    {"id": "qwen2.5-coder:7b",   "label": "Qwen 2.5 Coder 7B (beste Code-Qualität, ~8 GB)"},
    {"id": "llama3.2:3b",        "label": "Llama 3.2 3B (Erklärungen, Deutsch, ~2 GB)"},
    {"id": "phi4-mini",          "label": "Phi-4 Mini (Reasoning, Allrounder, ~2.5 GB)"},
]

DEFAULT_MODEL  = "qwen2.5-coder:3b"
DEFAULT_BASE_URL = "http://ollama:11434"
DEFAULT_TIMEOUT  = 120


class AIService:
    def __init__(self, base_url: str, model: str, timeout: int = DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.model    = model
        self.timeout  = timeout

    # ── low-level ────────────────────────────────────────────────────────────

    async def _stream(self, messages: list[dict], system: str = "") -> AsyncIterator[str]:
        payload_messages = []
        if system:
            payload_messages.append({"role": "system", "content": system})
        payload_messages.extend(messages)

        payload = {
            "model":  self.model,
            "messages": payload_messages,
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/v1/chat/completions",
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        chunk = json.loads(raw)
                        delta = chunk["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except Exception:
                        continue

    async def _complete(self, messages: list[dict], system: str = "") -> str:
        result = []
        async for token in self._stream(messages, system):
            result.append(token)
        return "".join(result)

    async def stream_with_context(self, user_message: str, system: str = ""):
        """Generic streaming entry-point used by the Context Builder."""
        async for token in self._stream([{"role": "user", "content": user_message}], system):
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
