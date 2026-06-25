from abc import ABC, abstractmethod
from typing import List


class PluginBase(ABC):
    id: str = ""
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    license: str = "free"       # free | professional | business | enterprise
    capabilities: List[str] = []
    config_schema: List[dict] = []

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
        }


class SourcePlugin(PluginBase):
    """Tier-1 Plugin: Datenquelle (lesen). Wird als Dataset-Typ registriert."""
    source_type_id: str = ""      # z.B. "mongodb" → file_type im Dataset
    source_type_label: str = ""   # z.B. "MongoDB"
    source_type_icon: str = "database"
    source_category: str = "data"  # "data" | "document" | "web" – für UI-Gruppierung

    @abstractmethod
    def test_connection(self, config: dict) -> dict:
        """Verbindung testen. Returns: {"ok": bool, "message": str}"""
        ...

    @abstractmethod
    def get_columns(self, config: dict) -> List[str]:
        """Schema abrufen – verfügbare Felder/Spalten."""
        ...

    @abstractmethod
    def fetch(self, config: dict) -> List[dict]:
        """Alle Daten abrufen. Returns: list of row dicts."""
        ...

    def fetch_preview(self, config: dict, limit: int = 50) -> List[dict]:
        """Vorschau – Standard: fetch() mit limit aus config."""
        preview_config = dict(config, limit=limit)
        rows = self.fetch(preview_config)
        return rows[:limit]


class TargetPlugin(PluginBase):
    """Tier-1 Plugin: Datenziel (schreiben)."""
    target_type_id: str = ""
    target_type_label: str = ""

    @abstractmethod
    def test_connection(self, config: dict) -> dict:
        ...

    @abstractmethod
    def write(self, rows: List[dict], config: dict) -> dict:
        """Daten schreiben. Returns: {"written": int, "errors": list}"""
        ...


class ConnectorPlugin(SourcePlugin, TargetPlugin):
    """Tier-1 Plugin: Bidirektionaler Konnektor (Quelle + Ziel)."""
    pass
