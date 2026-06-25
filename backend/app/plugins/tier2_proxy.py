import logging
from typing import List

import requests

from app.plugins.base import SourcePlugin, TargetPlugin

logger = logging.getLogger(__name__)


class Tier2Plugin(SourcePlugin, TargetPlugin):
    """Tier-2 Plugin – Container-basiert, alle Calls via Plugin Manager proxied."""

    tier = 2
    source_type_icon = "container"

    def __init__(self, pm_data: dict, pm_url: str):
        self.id = pm_data["id"]
        self.name = pm_data["name"]
        self.version = pm_data.get("version", "1.0.0")
        self.description = pm_data.get("description", "")
        self.author = pm_data.get("author", "")
        self.license = pm_data.get("license", "professional")
        self.capabilities = pm_data.get("capabilities", [])
        self.config_schema = pm_data.get("config_schema", [])
        self.source_type_id = pm_data.get("source_type_id", "")
        self.source_type_label = pm_data.get("source_type_label", "")
        self.source_type_icon = pm_data.get("source_type_icon", "container")
        self.target_type_id = pm_data.get("target_type_id", "")
        self.target_type_label = pm_data.get("target_type_label", "")
        self._pm_url = pm_url.rstrip("/")

    def manifest(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "license": self.license,
            "capabilities": self.capabilities,
            "config_schema": self.config_schema,
            "tier": 2,
            "source_type_id": self.source_type_id,
            "source_type_label": self.source_type_label,
            "target_type_id": self.target_type_id,
            "target_type_label": self.target_type_label,
        }

    def _proxy(self, endpoint: str, body: dict) -> dict:
        url = f"{self._pm_url}/plugins/{self.id}/proxy/{endpoint}"
        try:
            resp = requests.post(url, json=body, timeout=120.0)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            raise RuntimeError(f"Tier-2 Plugin '{self.id}' Proxy-Fehler ({endpoint}): {e}")

    def test_connection(self, config: dict) -> dict:
        try:
            return self._proxy("test", {"config": config})
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def get_columns(self, config: dict) -> List[str]:
        result = self._proxy("schema", {"config": config})
        return result.get("columns", [])

    def fetch(self, config: dict) -> List[dict]:
        result = self._proxy("fetch", {"config": config})
        return result.get("rows", [])

    def fetch_preview(self, config: dict, limit: int = 50) -> List[dict]:
        return self.fetch(dict(config, limit=limit))[:limit]

    def write(self, rows: List[dict], config: dict) -> dict:
        return self._proxy("write", {"config": config, "rows": rows})
