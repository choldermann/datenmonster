import importlib.util
import json
import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Plugins liegen in backend/plugins/ → im Container /app/plugins/
PLUGIN_DIR = Path(__file__).parent.parent.parent / "plugins"


def load_all_plugins(db=None):
    """Scannt das Plugin-Verzeichnis und lädt alle Tier-1 Plugins."""
    from app.plugins.registry import registry

    if not PLUGIN_DIR.exists():
        logger.info(f"Plugin-Verzeichnis {PLUGIN_DIR} nicht vorhanden – keine Plugins.")
        return

    loaded = 0
    for manifest_path in sorted(PLUGIN_DIR.glob("*/manifest.json")):
        plugin_dir = manifest_path.parent
        try:
            _load_plugin(plugin_dir, registry, db)
            loaded += 1
        except Exception as e:
            logger.error(f"Plugin '{plugin_dir.name}' Ladefehler: {e}", exc_info=True)

    logger.info(f"Plugin-Loader: {loaded} Plugin(s) geladen aus {PLUGIN_DIR}")


def _load_plugin(plugin_dir: Path, registry, db):
    connector_path = plugin_dir / "connector.py"
    if not connector_path.exists():
        logger.warning(f"Kein connector.py in {plugin_dir} – überspringe.")
        return

    # Eindeutiger Modulname verhindert Namespace-Kollisionen
    module_name = f"dm_plugin_{plugin_dir.name}"

    spec = importlib.util.spec_from_file_location(module_name, connector_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    if not hasattr(module, "Plugin"):
        logger.warning(f"Keine 'Plugin'-Klasse in {connector_path}.")
        return

    plugin_instance = module.Plugin()
    registry.register(plugin_instance, db=db)
