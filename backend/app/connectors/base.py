"""
BaseConnector – Interface für alle Datenquellen in Datenmonster.

Jede neue Datenquelle (REST, MongoDB, S3, ...) implementiert dieses Interface.
execute_mapping() kennt nur dieses Interface – nie die konkrete Implementierung.
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Iterator
import pandas as pd


class BaseConnector(ABC):

    # ─── Pflicht-Interface ────────────────────────────────────────────────────

    @abstractmethod
    def get_columns(self) -> List[str]:
        """Gibt alle verfügbaren Spaltennamen zurück."""
        ...

    @abstractmethod
    def fetch_preview(self, limit: int = 50) -> pd.DataFrame:
        """Lädt maximal `limit` Zeilen für die Vorschau."""
        ...

    @abstractmethod
    def fetch_full(self) -> pd.DataFrame:
        """
        Lädt alle Daten als DataFrame.
        Bei großen Quellen: fetch_chunks() bevorzugen.
        """
        ...

    # ─── Optionale Capabilities ───────────────────────────────────────────────

    def supports_pushdown(self) -> bool:
        """
        True wenn der Connector Filter/Joins/Transforms selbst ausführen kann
        (z.B. SQL auf dem Server). Dann übernimmt der SQL-Generator die Arbeit.
        False = Pandas-Pfad wird verwendet.
        """
        return False

    def fetch_chunks(self, chunk_size: int = 10000) -> Iterator[pd.DataFrame]:
        """
        Liefert Daten in Chunks – für Quellen die kein vollständiges
        In-Memory-Laden unterstützen. Default: fetch_full() in einem Chunk.
        """
        yield self.fetch_full()

    def get_row_count(self) -> Optional[int]:
        """Gibt die Gesamtzeilenzahl zurück wenn bekannt, sonst None."""
        return None

    # ─── Connector-Metadaten ──────────────────────────────────────────────────

    @property
    def connector_type(self) -> str:
        """z.B. 'sql_mssql', 'sql_mysql', 'file_csv', 'rest', 'mongo'"""
        return self.__class__.__name__

    def __repr__(self):
        return f"<{self.connector_type}>"
