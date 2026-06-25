from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.plugins.registry import registry

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


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
