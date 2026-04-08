"""
FileConnector – CSV, XLSX, XML Datenquellen.
Liest aus dem gecachten JSON-File das beim Upload erstellt wird.
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
        self._path = os.path.join(UPLOAD_DIR, f"dataset_{dataset_id}.json")
        self._data: Optional[List[dict]] = None

    def _load(self) -> List[dict]:
        if self._data is None:
            if not os.path.exists(self._path):
                raise FileNotFoundError(f"Dataset-Datei nicht gefunden: {self._path}")
            with open(self._path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        return self._data

    def get_columns(self) -> List[str]:
        data = self._load()
        return list(data[0].keys()) if data else []

    def get_row_count(self) -> Optional[int]:
        return len(self._load())

    def fetch_preview(self, limit: int = 50) -> pd.DataFrame:
        data = self._load()
        return pd.DataFrame(data[:limit])

    def fetch_full(self) -> pd.DataFrame:
        return pd.DataFrame(self._load())

    def fetch_chunks(self, chunk_size: int = 10000) -> Iterator[pd.DataFrame]:
        data = self._load()
        for i in range(0, len(data), chunk_size):
            yield pd.DataFrame(data[i:i + chunk_size])

    @property
    def connector_type(self) -> str:
        return "file"
