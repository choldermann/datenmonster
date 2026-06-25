import logging
from typing import Optional
from app.plugins.base import PluginBase, SourcePlugin, TargetPlugin

logger = logging.getLogger(__name__)


class CapabilityRegistry:
    def __init__(self):
        self._plugins: dict[str, PluginBase] = {}
        self._sources: dict[str, SourcePlugin] = {}
        self._targets: dict[str, TargetPlugin] = {}

    def register(self, plugin: PluginBase, db=None):
        self._plugins[plugin.id] = plugin
        if isinstance(plugin, SourcePlugin) and plugin.source_type_id:
            self._sources[plugin.source_type_id] = plugin
        if isinstance(plugin, TargetPlugin) and plugin.target_type_id:
            self._targets[plugin.target_type_id] = plugin

        if db is not None:
            self._upsert_db(plugin, db)

        logger.info(f"Plugin registriert: {plugin.name} v{plugin.version} (caps: {plugin.capabilities})")

    def _upsert_db(self, plugin: PluginBase, db):
        try:
            from app.models.plugin import Plugin as PluginModel
            existing = db.query(PluginModel).filter(PluginModel.plugin_id == plugin.id).first()
            if existing:
                existing.version = plugin.version
                existing.status = "active"
                existing.manifest = plugin.manifest()
            else:
                db.add(PluginModel(
                    plugin_id=plugin.id,
                    name=plugin.name,
                    version=plugin.version,
                    tier=getattr(plugin, "tier", 1),
                    status="active",
                    capabilities=plugin.capabilities,
                    manifest=plugin.manifest(),
                ))
            db.commit()
        except Exception as e:
            logger.warning(f"Plugin DB-Eintrag konnte nicht gespeichert werden: {e}")

    # ── Abfrage ──────────────────────────────────────────────────────────────

    def get_source(self, source_type_id: str) -> Optional[SourcePlugin]:
        return self._sources.get(source_type_id)

    def get_target(self, target_type_id: str) -> Optional[TargetPlugin]:
        return self._targets.get(target_type_id)

    def get_plugin(self, plugin_id: str) -> Optional[PluginBase]:
        return self._plugins.get(plugin_id)

    def is_plugin_source(self, file_type: str) -> bool:
        return file_type in self._sources

    def is_plugin_target(self, target_type: str) -> bool:
        return target_type in self._targets

    def list_plugins(self) -> list:
        return [p.manifest() for p in self._plugins.values()]

    def list_source_types(self, category: str = None) -> list:
        result = [
            {
                "id": p.source_type_id,
                "label": p.source_type_label,
                "icon": p.source_type_icon,
                "category": getattr(p, "source_category", "data"),
                "plugin_id": p.id,
                "config_schema": p.config_schema,
            }
            for p in self._sources.values()
        ]
        if category:
            result = [s for s in result if s["category"] == category]
        return result

    def list_target_types(self) -> list:
        return [
            {
                "id": p.target_type_id,
                "label": p.target_type_label,
                "plugin_id": p.id,
                "config_schema": p.config_schema,
            }
            for p in self._targets.values()
        ]

    def list_all_capabilities(self) -> dict:
        return {
            "sources": self.list_source_types(),
            "targets": self.list_target_types(),
            "plugins": self.list_plugins(),
        }


# Globale Singleton-Instanz
registry = CapabilityRegistry()
