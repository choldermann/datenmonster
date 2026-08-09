"""
Datenmonster AI — Gateway-Provider (»Datenmonster AI«)

Routet KI-Anfragen über den ZENTRALEN monstersuite-Gateway statt über das lokale
Ollama. Betreiber-OpenAI-Key, Credit-Ledger und Pricing liegen serverseitig in
monstersuite — die Instanz authentifiziert sich per Lizenzschlüssel (wie Plugin-Store
und Lizenz-Client). Vertrag: docs/monstersuite-ai-gateway-api.md.

Diese Klasse spiegelt bewusst die öffentliche Oberfläche von `AIService`
(`_stream` / `stream_with_context` / `complete_with_context` / `complete_json` /
`check_status` + Attribute `.model` / `.base_url`), damit die bestehenden
`ai.py`-Endpunkte unverändert funktionieren (Duck-Typing statt Big-Bang-Umbau).
"""
import json
import uuid
import logging
from typing import AsyncIterator, Optional

import httpx

from app.services.ai_service import AIParams

log = logging.getLogger("datenmonster")

GATEWAY_TIMEOUT = 180


class GatewayError(RuntimeError):
    """Fehler vom AI-Gateway (z.B. insufficient_credits, provider_error)."""
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message or code)


def describe_gateway_error(exc: Exception) -> str:
    """Gateway-Fehler in einen Satz übersetzen, der sagt, WAS zu tun ist.

    Wichtig: ein abgewiesener Aufruf ist NICHT dasselbe wie ein unerreichbarer
    Server. Der Gateway authentifiziert über die Lizenz — ohne aktivierte Lizenz
    kommt 401 zurück, und die pauschale Meldung »Gateway nicht erreichbar« schickt
    einen auf die Suche nach einem Netzwerkproblem, das es nicht gibt.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 401:
            return ("Lizenz nicht aktiviert oder ungültig — bitte im Reiter »Lizenz« "
                    "Schlüssel und E-Mail eintragen und aktivieren.")
        if code == 402:
            return "Guthaben aufgebraucht — bitte Credits aufladen."
        if code == 403:
            return "Diese Lizenz ist nicht für Datenmonster AI freigeschaltet."
        if code == 429:
            return "Zu viele Anfragen — bitte einen Moment warten."
        return f"Gateway meldet Fehler (HTTP {code})."
    if isinstance(exc, GatewayError):
        if exc.code == "insufficient_credits":
            return "Guthaben aufgebraucht — bitte Credits aufladen."
        if exc.code == "invalid_key":
            return "Lizenz nicht aktiviert oder ungültig — bitte im Reiter »Lizenz« aktivieren."
        return str(exc)
    return f"Gateway nicht erreichbar: {exc}"


class DatamonsterAIService:
    def __init__(self, db, model: str = "auto", timeout: int = GATEWAY_TIMEOUT):
        # `base_url` zeigt bewusst auf den Gateway-Namespace: Ollama-spezifische
        # Helfer (get_installed_models(svc.base_url)) laufen dann ins Leere und
        # degradieren sauber zu [] statt zu crashen.
        from app.api.license import LICENSE_SERVER
        self._db      = db
        self.model    = model or "auto"
        self.timeout  = timeout
        self.base_url = f"{LICENSE_SERVER}/api/v1/ai"
        self.last_usage: Optional[dict] = None

    # ── intern ────────────────────────────────────────────────────────────────
    def _generate_url(self) -> str:
        return f"{self.base_url}/generate"

    def _auth_body(self) -> dict:
        from app.api.license import license_auth_body
        return license_auth_body(self._db)

    def _payload(self, messages, system, params, model, json_mode, request_type,
                 json_schema=None) -> dict:
        msgs: list[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)

        options: dict = {
            "temperature":      params.temperature if params else 0.4,
            "max_output_tokens": params.max_tokens if params else 1000,
            "json":             bool(json_mode or json_schema),
        }
        if json_schema is not None:
            options["json_schema"] = json_schema

        body = dict(self._auth_body())
        body.update({
            "ai_request_id": str(uuid.uuid4()),   # Idempotenz-Anker (§23)
            "request_type":  request_type or "OTHER",
            "model":         model or self.model,
            "messages":      msgs,
            "options":       options,
        })
        return body

    async def _raise_for_error_response(self, resp: httpx.Response):
        """Vor dem Streamen: Nicht-2xx-Antworten (z.B. 402/429) als GatewayError werfen."""
        if resp.status_code < 400:
            return
        raw = await resp.aread()
        try:
            data = json.loads(raw)
            raise GatewayError(data.get("error", "gateway_error"),
                               data.get("message") or data.get("error") or "Gateway-Fehler")
        except (ValueError, TypeError):
            raise GatewayError("gateway_error", f"Gateway {resp.status_code}: {raw[:200]!r}")

    # ── Streaming (Kern) ──────────────────────────────────────────────────────
    async def _stream(
        self,
        messages: list[dict],
        system: str = "",
        json_mode: bool = False,
        params: AIParams | None = None,
        model: str | None = None,
        request_type: str = "OTHER",
    ) -> AsyncIterator[str]:
        payload = self._payload(messages, system, params, model, json_mode, request_type)
        self.last_usage = None
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", self._generate_url(), json=payload) as resp:
                await self._raise_for_error_response(resp)
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        evt = json.loads(data)
                    except Exception:
                        continue
                    etype = evt.get("type")
                    if etype == "token":
                        content = evt.get("content", "")
                        if content:
                            yield content
                    elif etype == "usage":
                        self.last_usage = evt
                    elif etype == "error":
                        raise GatewayError(evt.get("error", "gateway_error"),
                                           evt.get("message") or evt.get("error") or "Gateway-Fehler")
                    elif etype == "done":
                        break

    async def _complete(self, messages, system="", json_mode=False, params=None,
                        model=None, request_type="OTHER") -> str:
        out: list[str] = []
        async for tok in self._stream(messages, system, json_mode=json_mode, params=params,
                                      model=model, request_type=request_type):
            out.append(tok)
        return "".join(out)

    async def complete_with_context(self, user_message: str, system: str = "",
                                    params: AIParams | None = None, model: str | None = None,
                                    request_type: str = "OTHER") -> str:
        return await self._complete([{"role": "user", "content": user_message}], system,
                                    params=params, model=model, request_type=request_type)

    async def stream_with_context(self, user_message: str, system: str = "", json_mode: bool = False,
                                  params: AIParams | None = None, model: str | None = None,
                                  request_type: str = "OTHER"):
        async for tok in self._stream([{"role": "user", "content": user_message}], system,
                                      json_mode=json_mode, params=params, model=model,
                                      request_type=request_type):
            yield tok

    async def complete_json(self, messages: list[dict], json_schema: dict, model: str | None = None,
                            temperature: float = 0.2, request_type: str = "TRANSFORMATION") -> dict:
        """Single-shot strukturierte JSON-Ausgabe (für KI-Transform-Node-Preview)."""
        params = AIParams(temperature=temperature, max_tokens=1000)
        payload = self._payload(messages, "", params, model, True, request_type, json_schema=json_schema)
        out: list[str] = []
        self.last_usage = None
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", self._generate_url(), json=payload) as resp:
                await self._raise_for_error_response(resp)
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        evt = json.loads(data)
                    except Exception:
                        continue
                    if evt.get("type") == "token":
                        out.append(evt.get("content", ""))
                    elif evt.get("type") == "usage":
                        self.last_usage = evt
                    elif evt.get("type") == "error":
                        raise GatewayError(evt.get("error", "gateway_error"),
                                           evt.get("message") or "Gateway-Fehler")
        return json.loads("".join(out) or "{}")

    # ── Status / Guthaben ─────────────────────────────────────────────────────
    async def check_status(self) -> dict:
        """Erreichbarkeit + Guthaben. Mappt gateway_reachable auf ollama_reachable,
        damit die bestehende Status-UI (grüner Punkt) ohne Umbau weiterläuft."""
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.post(f"{self.base_url}/balance", json=self._auth_body())
                r.raise_for_status()
                data = r.json()
                return {
                    "ollama_reachable": True,
                    "gateway_reachable": True,
                    "model_loaded":     True,
                    "available_models": [],
                    "balance":          data.get("balance"),
                    "month":            data.get("month"),
                }
        except Exception as e:
            return {
                "ollama_reachable": False,
                "gateway_reachable": False,
                "model_loaded": False,
                "available_models": [],
                "error": describe_gateway_error(e),
            }
