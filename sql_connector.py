"""
SqlConnector – MSSQL, MySQL, PostgreSQL via SQLAlchemy.
Liefert echte pandas-Typen (int64, float64, datetime64) statt alles als String.
Konsistent mit FileConnector der Parquet (typisiert) liest.
"""
from typing import List, Optional, Iterator
import pandas as pd

from app.connectors.base import BaseConnector


def _decode_bytes(df: pd.DataFrame) -> pd.DataFrame:
    """Konvertiert Bytes-Spalten zu Strings – für pymssql-Rückgaben."""
    for col in df.columns:
        sample = df[col].dropna()
        if len(sample) > 0 and isinstance(sample.iloc[0], bytes):
            df[col] = df[col].apply(
                lambda v: v.decode("utf-8", errors="replace") if isinstance(v, bytes) else v
            )
    return df


def _fix_types(df: pd.DataFrame) -> pd.DataFrame:
    """
    Bereinigt DataFrame nach DB-Fetch:
    - Bytes → String
    - Decimal → float64
    - Echte int/float/datetime Typen bleiben erhalten
    - None/NaT bleiben als pandas NA
    """
    df = _decode_bytes(df)
    for col in df.columns:
        sample = df[col].dropna()
        if len(sample) == 0:
            continue
        first = sample.iloc[0]
        # decimal.Decimal → float
        if hasattr(first, 'is_finite'):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _to_display(df: pd.DataFrame) -> pd.DataFrame:
    """
    Konvertiert DataFrame für API-Ausgabe zu Strings.
    Nur für Endpoints die JSON zurückgeben – NICHT für Mapping-Verarbeitung.
    """
    import math
    def _conv(v):
        if v is None:
            return None
        if hasattr(v, '__class__') and v.__class__.__name__ == 'NaTType':
            return None
        if isinstance(v, float):
            if math.isnan(v):
                return None
            if v == int(v):
                return str(int(v))
            return str(v)
        if isinstance(v, bytes):
            for enc in ("utf-8", "cp1252", "latin-1"):
                try:
                    return v.decode(enc)
                except Exception:
                    continue
            return v.decode("latin-1", errors="replace")
        if isinstance(v, str):
            return v
        try:
            iv = int(v)
            if iv == v:
                return str(iv)
        except (ValueError, TypeError, OverflowError):
            pass
        return str(v)

    result = df.copy()
    for col in result.columns:
        result[col] = result[col].apply(_conv)
    return result


class SqlConnector(BaseConnector):

    def __init__(self, db_type: str, connection_string: str, sql: str):
        self.db_type = db_type
        self.connection_string = connection_string
        self.sql = sql.strip().rstrip(";")
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            from sqlalchemy import create_engine
            connect_args = {}
            if self.db_type == "mssql":
                connect_args = {"timeout": 30, "login_timeout": 10}
            elif self.db_type == "mysql":
                connect_args = {"connect_timeout": 10}
            self._engine = create_engine(
                self.connection_string,
                connect_args=connect_args,
                pool_size=2,
                max_overflow=3,
                pool_timeout=30,
            )
        return self._engine

    def _limit_sql(self, limit: int) -> str:
        if self.db_type == "mssql":
            sql_stripped = self.sql.strip()
            upper = sql_stripped.upper().lstrip()
            if upper.startswith("SELECT DISTINCT "):
                return sql_stripped[:16] + f"TOP {limit} " + sql_stripped[16:]
            elif upper.startswith("SELECT "):
                return sql_stripped[:7] + f"TOP {limit} " + sql_stripped[7:]
            else:
                return f"SELECT TOP {limit} * FROM ({self.sql}) AS _preview"
        else:
            return f"SELECT * FROM ({self.sql}) AS _preview LIMIT {limit}"

    def _execute(self, sql: str) -> pd.DataFrame:
        """Führt SQL aus und gibt typisierten DataFrame zurück."""
        from sqlalchemy import text
        engine = self._get_engine()
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            cols = list(result.keys())
            rows = result.fetchall()
        if not rows:
            return pd.DataFrame(columns=cols)
        df = pd.DataFrame([dict(zip(cols, row)) for row in rows], columns=cols)
        return _fix_types(df)

    def get_columns(self) -> List[str]:
        return list(self._execute(self._limit_sql(1)).columns)

    def get_row_count(self) -> Optional[int]:
        from sqlalchemy import text
        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                count_sql = (f"SELECT COUNT(1) FROM ({self.sql}) AS _cw"
                             if self.db_type == "mssql"
                             else f"SELECT COUNT(*) FROM ({self.sql}) AS _cw")
                return conn.execute(text(count_sql)).scalar()
        except Exception:
            return None

    def fetch_preview(self, limit: int = 50) -> pd.DataFrame:
        """Für Mapping-Verarbeitung: echte Typen."""
        return self._execute(self._limit_sql(limit))

    def fetch_full(self) -> pd.DataFrame:
        """Für Mapping-Verarbeitung: echte Typen."""
        return self._execute(self.sql)

    def fetch_preview_display(self, limit: int = 50) -> pd.DataFrame:
        """Für API-Ausgabe: String-konvertiert."""
        return _to_display(self._execute(self._limit_sql(limit)))

    def fetch_full_display(self) -> pd.DataFrame:
        """Für API-Ausgabe: String-konvertiert."""
        return _to_display(self._execute(self.sql))

    def fetch_chunks(self, chunk_size: int = 10000) -> Iterator[pd.DataFrame]:
        from sqlalchemy import text
        engine = self._get_engine()
        with engine.connect() as conn:
            result = conn.execution_options(stream_results=True).execute(text(self.sql))
            cols = list(result.keys())
            while True:
                batch = result.fetchmany(chunk_size)
                if not batch:
                    break
                df = pd.DataFrame([dict(zip(cols, row)) for row in batch], columns=cols)
                yield _fix_types(df)

    def supports_pushdown(self) -> bool:
        return True

    @property
    def connector_type(self) -> str:
        return f"sql_{self.db_type}"
