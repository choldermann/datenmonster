"""
RestApiConnector – liest Daten einer RestSource.

**Abgelegte Zeilen haben Vorrang vor einem neuen Abruf.** Wer eine REST-Quelle
in ein Dataset importiert, hat sich ausdrücklich für eine Kopie entschieden –
sie liegt als Parquet bereit. Wurde sie trotzdem bei jedem Lesen ignoriert und
die Schnittstelle erneut befragt, hatte das zwei Folgen: Ein Cockpit mit zehn
Kacheln löste zehn vollständige Abrufe aus, und bei Anbietern mit Tempolimit
(Lexware Office: zwei Anfragen je Sekunde) lief das sofort in HTTP 429.

Live gelesen wird weiterhin, wenn es nichts Abgelegtes gibt – so verhalten sich
REST-Datasets ohne Import unverändert – oder wenn `query_config.live` das
ausdrücklich verlangt.
"""
import logging

import pandas as pd

from app.connectors.base import BaseConnector

log = logging.getLogger("datenmonster")


class RestApiConnector(BaseConnector):

    def __init__(self, source, dataset_id: int | None = None, live: bool = False):
        """`source` ist ein RestSource-ORM-Objekt."""
        self._source = source
        self._dataset_id = dataset_id
        self._live = live

    @property
    def connector_type(self) -> str:
        return "rest_api"

    def _abgelegt(self) -> pd.DataFrame | None:
        """Die importierte Kopie – oder None, wenn es keine gibt."""
        if self._live or not self._dataset_id:
            return None
        try:
            from app.services.file_service import _load_parquet
            return _load_parquet(self._dataset_id)
        except FileNotFoundError:
            return None
        except Exception as e:
            log.warning(f"Dataset {self._dataset_id}: abgelegte Kopie nicht lesbar ({e}) "
                        f"– hole live von der Schnittstelle")
            return None

    def get_columns(self):
        df = self._abgelegt()
        if df is not None:
            return list(df.columns)
        try:
            return list(self.fetch_preview(limit=1).columns)
        except Exception:
            return []

    def fetch_preview(self, limit: int = 50) -> pd.DataFrame:
        df = self._abgelegt()
        if df is not None:
            return df.head(limit)
        from app.services.rest_service import fetch_rest_source
        return fetch_rest_source(self._source).head(limit)

    def fetch_full(self) -> pd.DataFrame:
        df = self._abgelegt()
        if df is not None:
            return df
        from app.services.rest_service import fetch_rest_source
        return fetch_rest_source(self._source)

    def get_row_count(self):
        df = self._abgelegt()
        return len(df) if df is not None else None
