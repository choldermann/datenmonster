"""
FileConnector – CSV, XLSX, XML, Parquet Datenquellen.
Liest aus dem Parquet-File das beim Import erstellt wird.
Fällt auf JSON zurück für alte Datasets (Migration).
"""
import os
import json
from typing import List, Optional, Iterator
import pandas as pd

from app.connectors.base import BaseConnector

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")


class FileConnector(BaseConnector):

    def __init__(self, dataset_id: int):
        self.dataset_id = dataset_id
        self._parquet_path = os.path.join(UPLOAD_DIR, f"dataset_{dataset_id}.parquet")
        self._json_path    = os.path.join(UPLOAD_DIR, f"dataset_{dataset_id}.json")
        self._df: Optional[pd.DataFrame] = None

    def _load(self) -> pd.DataFrame:
        """Lädt Dataset – Parquet bevorzugt, JSON als Fallback."""
        if self._df is not None:
            return self._df

        if os.path.exists(self._parquet_path):
            self._df = pd.read_parquet(self._parquet_path, engine="pyarrow")
            return self._df

        # JSON-Fallback (alte Datasets)
        if os.path.exists(self._json_path):
            with open(self._json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            df = pd.DataFrame(data) if data else pd.DataFrame()
            # Typen inferieren für konsistentes Verhalten
            for col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="ignore")
            self._df = df
            return self._df

        raise FileNotFoundError(
            f"Dataset {self.dataset_id} nicht gefunden "
            f"(weder {self._parquet_path} noch {self._json_path})"
        )

    def get_columns(self) -> List[str]:
        return list(self._load().columns)

    def get_row_count(self) -> Optional[int]:
        return len(self._load())

    def fetch_preview(self, limit: int = 50) -> pd.DataFrame:
        return self._load().head(limit).copy()

    def fetch_full(self) -> pd.DataFrame:
        return self._load().copy()

    def fetch_chunks(self, chunk_size: int = 10000) -> Iterator[pd.DataFrame]:
        df = self._load()
        for i in range(0, len(df), chunk_size):
            yield df.iloc[i:i + chunk_size].copy()

    @property
    def connector_type(self) -> str:
        return "file"
