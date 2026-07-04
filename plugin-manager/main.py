import json
import logging
import os
from pathlib import Path
from typing import List, Optional

import docker
import httpx
import redis
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Datenmonster Plugin Manager", version="1.0.0")

REGISTRY_FILE = Path(os.getenv("REGISTRY_FILE", "/data/plugins.json"))
PLUGIN_NETWORK = os.getenv("PLUGIN_NETWORK", "datenmonster")
PLUGIN_PORT = int(os.getenv("PLUGIN_PORT", "8080"))
REDIS_URL = os.getenv("REDIS_URL", "")
PLUGIN_MANAGER_SELF_URL = os.getenv("PLUGIN_MANAGER_SELF_URL", "http://plugin-manager:9001")
CHANNEL_PLUGIN_TRIGGER = "dm.plugin.trigger"


def _redis_publish(payload: dict):
    if not REDIS_URL:
        logger.warning("REDIS_URL nicht gesetzt – Event wird nicht veröffentlicht.")
        return
    try:
        r = redis.from_url(REDIS_URL, decode_responses=True)
        r.publish(CHANNEL_PLUGIN_TRIGGER, json.dumps(payload))
        logger.info(f"EventBus published → {CHANNEL_PLUGIN_TRIGGER}: {payload}")
    except Exception as e:
        logger.warning(f"Redis publish fehlgeschlagen: {e}")


# ── Registry ─────────────────────────────────────────────────────────────────

def load_reg() -> dict:
    try:
        return json.loads(REGISTRY_FILE.read_text()) if REGISTRY_FILE.exists() else {}
    except Exception:
        return {}


def save_reg(data: dict):
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_FILE.write_text(json.dumps(data, indent=2))


def cname(plugin_id: str) -> str:
    safe = plugin_id.replace("/", "-").replace(":", "-").replace(".", "-")
    return f"dm-plugin-{safe}"


# ── Docker ───────────────────────────────────────────────────────────────────

def _dc() -> docker.DockerClient:
    return docker.from_env()


def _container_status(plugin_id: str) -> str:
    try:
        c = _dc().containers.get(cname(plugin_id))
        return c.status  # running | exited | created | ...
    except docker.errors.NotFound:
        return "stopped"
    except Exception as e:
        logger.warning(f"Docker-Status für {plugin_id} nicht abrufbar: {e}")
        return "unknown"


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    try:
        _dc().ping()
        docker_ok = True
    except Exception:
        docker_ok = False
    return {"status": "ok", "docker": docker_ok}


# ── Plugin Registry API ───────────────────────────────────────────────────────

@app.get("/plugins")
def list_plugins():
    reg = load_reg()
    result = []
    for pid, p in reg.items():
        result.append({**p, "status": _container_status(pid)})
    return result


class RegisterBody(BaseModel):
    id: str
    name: str
    docker_image: str
    description: str = ""
    author: str = ""
    license: str = "professional"
    capabilities: List[str] = []
    config_schema: List[dict] = []
    source_type_id: str = ""
    source_type_label: str = ""
    source_type_icon: str = "container"
    target_type_id: str = ""
    target_type_label: str = ""


@app.post("/plugins", status_code=201)
def register_plugin(body: RegisterBody):
    reg = load_reg()
    reg[body.id] = body.model_dump()
    save_reg(reg)
    logger.info(f"Tier-2 Plugin registriert: {body.id} ({body.docker_image})")
    return {"ok": True, "id": body.id}


@app.get("/plugins/{plugin_id}")
def get_plugin(plugin_id: str):
    reg = load_reg()
    if plugin_id not in reg:
        raise HTTPException(404, "Plugin nicht gefunden")
    return {**reg[plugin_id], "status": _container_status(plugin_id)}


@app.delete("/plugins/{plugin_id}")
def unregister_plugin(plugin_id: str):
    reg = load_reg()
    if plugin_id not in reg:
        raise HTTPException(404, "Plugin nicht gefunden")
    try:
        c = _dc().containers.get(cname(plugin_id))
        if c.status == "running":
            c.stop(timeout=10)
        c.remove()
    except docker.errors.NotFound:
        pass
    except Exception as e:
        logger.warning(f"Container-Cleanup für {plugin_id}: {e}")
    del reg[plugin_id]
    save_reg(reg)
    return {"ok": True}


# ── Container-Lifecycle ───────────────────────────────────────────────────────

def _ensure_container_started(plugin_id: str) -> str:
    """
    Startet den Plugin-Container falls er nicht läuft. Idempotent.
    Gibt "already_running" oder "starting" zurück.
    Wird sowohl vom /start-Endpunkt als auch vom Proxy (On-Demand) genutzt.
    """
    reg = load_reg()
    if plugin_id not in reg:
        raise HTTPException(404, "Plugin nicht gefunden")
    p = reg[plugin_id]
    dc = _dc()

    try:
        c = dc.containers.get(cname(plugin_id))
        if c.status == "running":
            return "already_running"
        # Gestoppter/abgestürzter Container → entfernen und neu starten
        c.remove(force=True)
    except docker.errors.NotFound:
        pass

    try:
        logger.info(f"Pulling {p['docker_image']}...")
        dc.images.pull(p["docker_image"])
    except Exception as e:
        logger.warning(f"Pull fehlgeschlagen, versuche lokales Image: {e}")

    dc.containers.run(
        p["docker_image"],
        name=cname(plugin_id),
        network=PLUGIN_NETWORK,
        detach=True,
        # Überlebt Host-Neustart und Abstürze, damit Plugin-Writes nicht ins Leere laufen
        restart_policy={"Name": "unless-stopped"},
        labels={"dm.plugin": "tier2", "dm.plugin.id": plugin_id},
        environment={
            "PLUGIN_ID": plugin_id,
            "PLUGIN_MANAGER_URL": PLUGIN_MANAGER_SELF_URL,
        },
    )
    logger.info(f"Tier-2 Plugin gestartet: {cname(plugin_id)}")
    return "starting"


async def _wait_until_ready(plugin_id: str, timeout: float = 40.0):
    """Pollt den /health-Endpunkt des Plugin-Containers bis er antwortet oder Timeout."""
    import asyncio
    url = f"{_container_url(plugin_id)}/health"
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    last_err = None
    async with httpx.AsyncClient(timeout=5.0) as client:
        while loop.time() < deadline:
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return True
            except Exception as e:
                last_err = e
            await asyncio.sleep(1.0)
    raise HTTPException(503, f"Plugin-Container '{plugin_id}' nicht bereit nach {int(timeout)}s: {last_err}")


@app.post("/plugins/{plugin_id}/start")
def start_plugin(plugin_id: str):
    try:
        status = _ensure_container_started(plugin_id)
        return {"ok": True, "status": status}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Container-Start fehlgeschlagen: {e}")


@app.post("/plugins/{plugin_id}/stop")
def stop_plugin(plugin_id: str):
    try:
        c = _dc().containers.get(cname(plugin_id))
        c.stop(timeout=15)
        logger.info(f"Tier-2 Plugin gestoppt: {cname(plugin_id)}")
        return {"ok": True}
    except docker.errors.NotFound:
        return {"ok": True, "status": "already_stopped"}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/plugins/{plugin_id}/status")
def plugin_status(plugin_id: str):
    return {"plugin_id": plugin_id, "status": _container_status(plugin_id)}


# ── Proxy ─────────────────────────────────────────────────────────────────────

def _container_url(plugin_id: str) -> str:
    return f"http://{cname(plugin_id)}:{PLUGIN_PORT}"


async def _proxy(plugin_id: str, endpoint: str, body: dict) -> dict:
    reg = load_reg()
    if plugin_id not in reg:
        raise HTTPException(404, "Plugin nicht gefunden")
    # On-Demand-Start: Container bei Bedarf hochfahren statt sofort 503 zu werfen
    if _container_status(plugin_id) != "running":
        logger.info(f"Plugin '{plugin_id}' nicht aktiv – starte on-demand für '{endpoint}'")
        _ensure_container_started(plugin_id)
        await _wait_until_ready(plugin_id)
    url = f"{_container_url(plugin_id)}/{endpoint}"
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"Plugin-Fehler: {e.response.text}")
    except Exception as e:
        raise HTTPException(502, f"Proxy-Fehler: {e}")


class ProxyBody(BaseModel):
    config: dict = {}
    rows: Optional[List[dict]] = None


@app.post("/plugins/{plugin_id}/proxy/test")
async def proxy_test(plugin_id: str, body: ProxyBody):
    return await _proxy(plugin_id, "test", {"config": body.config})


@app.post("/plugins/{plugin_id}/proxy/schema")
async def proxy_schema(plugin_id: str, body: ProxyBody):
    return await _proxy(plugin_id, "schema", {"config": body.config})


@app.post("/plugins/{plugin_id}/proxy/fetch")
async def proxy_fetch(plugin_id: str, body: ProxyBody):
    return await _proxy(plugin_id, "fetch", {"config": body.config})


@app.post("/plugins/{plugin_id}/proxy/write")
async def proxy_write(plugin_id: str, body: ProxyBody):
    return await _proxy(plugin_id, "write", {"config": body.config, "rows": body.rows or []})


# ── Generischer Proxy (für eigene Plugin-Endpunkte wie /api/v1/...) ───────────

@app.api_route("/plugins/{plugin_id}/proxy/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_generic(plugin_id: str, path: str, request: Request):
    """Leitet beliebige GET/POST-Anfragen an den Plugin-Container weiter."""
    reg = load_reg()
    if plugin_id not in reg:
        raise HTTPException(404, "Plugin nicht gefunden")
    # On-Demand-Start wie im typisierten Proxy
    if _container_status(plugin_id) != "running":
        logger.info(f"Plugin '{plugin_id}' nicht aktiv – starte on-demand für '{path}'")
        _ensure_container_started(plugin_id)
        await _wait_until_ready(plugin_id)
    url = f"{_container_url(plugin_id)}/{path}"
    body_bytes = await request.body()
    headers = {"Content-Type": request.headers.get("content-type", "application/json")}
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.request(
                method=request.method,
                url=url,
                content=body_bytes,
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"Plugin-Fehler: {e.response.text}")
    except Exception as e:
        raise HTTPException(502, f"Proxy-Fehler: {e}")


# ── EventBus ──────────────────────────────────────────────────────────────────

class EventBody(BaseModel):
    payload: dict = {}


@app.post("/plugins/{plugin_id}/event")
def plugin_event(plugin_id: str, body: EventBody):
    """Tier-2 Plugin feuert ein Event – wird auf dm.plugin.trigger publiziert."""
    reg = load_reg()
    if plugin_id not in reg:
        raise HTTPException(404, "Plugin nicht gefunden")
    p = reg[plugin_id]
    event_payload = {
        "plugin_id": plugin_id,
        "source_type_id": p.get("source_type_id", ""),
        **body.payload,
    }
    _redis_publish(event_payload)
    return {"ok": True, "channel": CHANNEL_PLUGIN_TRIGGER, "payload": event_payload}
