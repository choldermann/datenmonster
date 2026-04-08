"""
RestApiConnector – liest Daten von einer RestSource via rest_service.
Implementiert BaseConnector damit mapping_service es transparent nutzen kann.
"""
import pandas as pd
from app.connectors.base import BaseConnector


class RestApiConnector(BaseConnector):

    def __init__(self, source):
        """source ist ein RestSource ORM-Objekt."""
        self._source = source

    @property
    def connector_type(self) -> str:
        return "rest_api"

    def get_columns(self):
        try:
            df = self.fetch_preview(limit=1)
            return list(df.columns)
        except Exception:
            return []

    def fetch_preview(self, limit: int = 50) -> pd.DataFrame:
        from app.services.rest_service import fetch_rest_source
        df = fetch_rest_source(self._source)
        return df.head(limit)

    def fetch_full(self) -> pd.DataFrame:
        from app.services.rest_service import fetch_rest_source
        return fetch_rest_source(self._source)

    def get_row_count(self):
        return None  # Unbekannt bis Fetch
