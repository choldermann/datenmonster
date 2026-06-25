from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import requests
from app.core.database import get_db
from app.core.config import PLUGIN_MANAGER_URL
from app.api.auth import get_current_user
from app.models.user import User
from app.plugins.registry import registry

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


def _pm(path: str) -> str:
    if not PLUGIN_MANAGER_URL:
        raise HTTPException(503, "Plugin Manager nicht konfiguriert (PLUGIN_MANAGER_URL fehlt)")
    return f"{PLUGIN_MANAGER_URL.rstrip('/')}{path}"


def _pm_get(path: str) -> dict:
    try:
        resp = requests.get(_pm(path), timeout=10.0)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        raise HTTPException(e.response.status_code, e.response.text)
    except Exception as e:
        raise HTTPException(502, f"Plugin Manager nicht erreichbar: {e}")


def _pm_post(path: str, body: dict = None) -> dict:
    try:
        resp = requests.post(_pm(path), json=body or {}, timeout=60.0)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        raise HTTPException(e.response.status_code, e.response.text)
    except Exception as e:
        raise HTTPException(502, f"Plugin Manager nicht erreichbar: {e}")


def _pm_delete(path: str) -> dict:
    try:
        resp = requests.delete(_pm(path), timeout=10.0)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        raise HTTPException(e.response.status_code, e.response.text)
    except Exception as e:
        raise HTTPException(502, f"Plugin Manager nicht erreichbar: {e}")


@router.get("/")
def list_plugins(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Alle registrierten Plugins mit Status aus der DB."""
    from app.models.plugin import Plugin
    db_map = {p.plugin_id: p for p in db.query(Plugin).all()}
    result = []
    for p in registry.list_plugins():
        db_p = db_map.get(p["id"])
        result.append({
            **p,
            "status": db_p.status if db_p else "active",
            "installed_at": str(db_p.installed_at) if db_p and db_p.installed_at else None,
        })
    return result


@router.get("/capabilities")
def list_capabilities(user: User = Depends(get_current_user)):
    """Alle Capabilities: Quell-Typen, Ziel-Typen, Plugins."""
    return registry.list_all_capabilities()


@router.get("/source-types")
def list_source_types(user: User = Depends(get_current_user)):
    """Plugin-Quell-Typen für Dataset-Wizard."""
    return registry.list_source_types()


@router.get("/target-types")
def list_target_types(user: User = Depends(get_current_user)):
    """Plugin-Ziel-Typen für Mapping-Editor."""
    return registry.list_target_types()


@router.get("/{plugin_id}")
def get_plugin(plugin_id: str, user: User = Depends(get_current_user)):
    plugin = registry.get_plugin(plugin_id)
    if not plugin:
        raise HTTPException(404, "Plugin nicht gefunden")
    return plugin.manifest()


class TestBody(BaseModel):
    config: Optional[dict] = {}


@router.post("/{plugin_id}/test")
def test_connection(plugin_id: str, body: TestBody, user: User = Depends(get_current_user)):
    """Verbindungstest für ein Plugin mit gegebener Konfiguration."""
    from app.plugins.base import SourcePlugin, TargetPlugin
    plugin = registry.get_plugin(plugin_id)
    if not plugin:
        raise HTTPException(404, "Plugin nicht gefunden")
    if not isinstance(plugin, (SourcePlugin, TargetPlugin)):
        raise HTTPException(400, "Plugin unterstützt keinen Verbindungstest")
    try:
        return plugin.test_connection(body.config or {})
    except Exception as e:
        return {"ok": False, "message": str(e)}


@router.post("/{plugin_id}/schema")
def get_schema(plugin_id: str, body: TestBody, user: User = Depends(get_current_user)):
    """Schema (Spalten) einer Plugin-Quelle abrufen."""
    from app.plugins.base import SourcePlugin
    plugin = registry.get_plugin(plugin_id)
    if not plugin or not isinstance(plugin, SourcePlugin):
        raise HTTPException(404, "Plugin oder Quelle nicht gefunden")
    try:
        columns = plugin.get_columns(body.config or {})
        return {"columns": columns}
    except Exception as e:
        raise HTTPException(400, str(e))


# ── Tier-2 Plugin Manager Endpunkte ──────────────────────────────────────────

@router.get("/tier2")
def list_tier2_plugins(user: User = Depends(get_current_user)):
    """Alle beim Plugin Manager registrierten Tier-2 Plugins (mit Container-Status)."""
    return _pm_get("/plugins")


class Tier2RegisterBody(BaseModel):
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


@router.post("/tier2", status_code=201)
def register_tier2_plugin(body: Tier2RegisterBody, user: User = Depends(get_current_user)):
    """Tier-2 Plugin beim Plugin Manager registrieren."""
    result = _pm_post("/plugins", body.model_dump())
    # Direkt in Capability Registry eintragen ohne Backend-Neustart
    from app.plugins.tier2_proxy import Tier2Plugin
    plugin = Tier2Plugin(body.model_dump(), PLUGIN_MANAGER_URL)
    registry.register(plugin)
    return result


@router.delete("/tier2/{plugin_id}")
def unregister_tier2_plugin(plugin_id: str, user: User = Depends(get_current_user)):
    """Tier-2 Plugin entfernen (stoppt und löscht den Container)."""
    return _pm_delete(f"/plugins/{plugin_id}")


@router.post("/tier2/{plugin_id}/start")
def start_tier2_plugin(plugin_id: str, user: User = Depends(get_current_user)):
    """Container für ein Tier-2 Plugin starten."""
    return _pm_post(f"/plugins/{plugin_id}/start")


@router.post("/tier2/{plugin_id}/stop")
def stop_tier2_plugin(plugin_id: str, user: User = Depends(get_current_user)):
    """Container für ein Tier-2 Plugin stoppen."""
    return _pm_post(f"/plugins/{plugin_id}/stop")


@router.get("/tier2/{plugin_id}/status")
def tier2_plugin_status(plugin_id: str, user: User = Depends(get_current_user)):
    """Container-Status eines Tier-2 Plugins abfragen."""
    return _pm_get(f"/plugins/{plugin_id}/status")


@router.get("/manager/health")
def plugin_manager_health(user: User = Depends(get_current_user)):
    """Plugin Manager Health-Check."""
    return _pm_get("/health")
