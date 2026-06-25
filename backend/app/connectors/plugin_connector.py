"""
PluginConnector – Brücke zwischen einem Tier-1 SourcePlugin und dem BaseConnector-Interface.

Die ConnectorFactory instanziiert diesen Connector wenn file_type in der
CapabilityRegistry als Plugin-Quelle registriert ist.
"""
from typing import List, Optional, Iterator
import pandas as pd
from app.connectors.base import BaseConnector


class PluginConnector(BaseConnector):
    def __init__(self, plugin, config: dict):
        self._plugin = plugin
        self._config = config

    @property
    def connector_type(self) -> str:
        return f"plugin_{self._plugin.source_type_id}"

    def get_columns(self) -> List[str]:
        return self._plugin.get_columns(self._config)

    def fetch_preview(self, limit: int = 50) -> pd.DataFrame:
        rows = self._plugin.fetch_preview(self._config, limit=limit)
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    def fetch_full(self) -> pd.DataFrame:
        rows = self._plugin.fetch(self._config)
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    def fetch_chunks(self, chunk_size: int = 10000) -> Iterator[pd.DataFrame]:
        df = self.fetch_full()
        for i in range(0, max(1, len(df)), chunk_size):
            yield df.iloc[i:i + chunk_size]

    def get_row_count(self) -> Optional[int]:
        try:
            return len(self.fetch_full())
        except Exception:
            return None
