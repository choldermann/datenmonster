"""
SqlConnector – MSSQL, MySQL, PostgreSQL via SQLAlchemy.
Unterstützt Pushdown: Filter, Joins und einfache Transforms
werden als SQL auf dem Server ausgeführt.
"""
from typing import List, Optional, Iterator
import pandas as pd

from app.connectors.base import BaseConnector


def _decode_value(v):
    """Bytes sicher zu String – für pymssql-Rückgaben."""
    if v is None:
        return None
    if isinstance(v, bytes):
        for enc in ("utf-8", "cp1252", "latin-1"):
            try:
                return v.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return v.decode("latin-1", errors="replace")
    return v


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Konvertiert alle Werte zu Strings/None – einheitlich wie JSON-Datasets.
    Ganzzahlen werden ohne Nachkommastelle ausgegeben (1 statt 1.0).
    """
    import math
    def _convert(v):
        if v is None:
            return None
        if hasattr(v, '__class__') and v.__class__.__name__ == 'NaTType':
            return None
        if isinstance(v, float):
            if math.isnan(v):
                return None
            # Ganzzahlige Floats ohne .0 ausgeben
            if v == int(v):
                return str(int(v))
            return str(v)
        if isinstance(v, bytes):
            return _decode_value(v)
        if isinstance(v, str):
            return v
        # int, Decimal, numpy-Typen etc.
        # Prüfe ob Wert ganzzahlig ist
        try:
            iv = int(v)
            if iv == v:
                return str(iv)
        except (ValueError, TypeError, OverflowError):
            pass
        return str(v)

    for col in df.columns:
        df[col] = df[col].apply(_convert)
    return df


class SqlConnector(BaseConnector):

    def __init__(self, db_type: str, connection_string: str, sql: str):
        """
        db_type:           'mssql' | 'mysql' | 'postgresql'
        connection_string: SQLAlchemy connection URL
        sql:               Source SQL (z.B. 'SELECT * FROM tArtikel')
        """
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
                # Connection pooling für wiederholte Abfragen
                pool_size=2,
                max_overflow=3,
                pool_timeout=30,
            )
        return self._engine

    def _limit_sql(self, limit: int) -> str:
        """Dialect-agnostisches LIMIT/TOP – kein Subquery-Wrap um doppelte Spalten zu vermeiden."""
        if self.db_type == "mssql":
            # TOP direkt in das SELECT injizieren statt Subquery-Wrap
            sql_stripped = self.sql.strip()
            upper = sql_stripped.upper().lstrip()
            if upper.startswith("SELECT DISTINCT "):
                return sql_stripped[:16] + f"TOP {limit} " + sql_stripped[16:]
            elif upper.startswith("SELECT "):
                return sql_stripped[:7] + f"TOP {limit} " + sql_stripped[7:]
            else:
                # Fallback: Subquery (z.B. bei CTEs)
                return f"SELECT TOP {limit} * FROM ({self.sql}) AS _preview"
        else:
            return f"SELECT * FROM ({self.sql}) AS _preview LIMIT {limit}"

    def get_columns(self) -> List[str]:
        return list(self.fetch_preview(limit=1).columns)

    def get_row_count(self) -> Optional[int]:
        from sqlalchemy import text
        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                if self.db_type == "mssql":
                    # MSSQL: doppelte Spalten im Subquery verboten → rowcount via @@ROWCOUNT trick
                    count_sql = f"SELECT COUNT(1) FROM ({self.sql}) AS _cw"
                else:
                    count_sql = f"SELECT COUNT(*) FROM ({self.sql}) AS _cw"
                return conn.execute(text(count_sql)).scalar()
        except Exception:
            return None

    def fetch_preview(self, limit: int = 50) -> pd.DataFrame:
        from sqlalchemy import text
        engine = self._get_engine()
        with engine.connect() as conn:
            result = conn.execute(text(self._limit_sql(limit)))
            cols = list(result.keys())
            rows = [dict(zip(cols, row)) for row in result.fetchall()]
        df = pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)
        return _normalize_df(df)

    def fetch_full(self) -> pd.DataFrame:
        from sqlalchemy import text
        engine = self._get_engine()
        with engine.connect() as conn:
            result = conn.execute(text(self.sql))
            cols = list(result.keys())
            rows = [dict(zip(cols, row)) for row in result.fetchall()]
        df = pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)
        return _normalize_df(df)

    def fetch_chunks(self, chunk_size: int = 10000) -> Iterator[pd.DataFrame]:
        """Stream-basiertes Laden für große Tabellen."""
        from sqlalchemy import text
        engine = self._get_engine()
        with engine.connect() as conn:
            result = conn.execution_options(stream_results=True).execute(text(self.sql))
            cols = list(result.keys())
            while True:
                batch = result.fetchmany(chunk_size)
                if not batch:
                    break
                rows = [dict(zip(cols, row)) for row in batch]
                df = pd.DataFrame(rows, columns=cols)
                yield _normalize_df(df)

    def _build_where(self, filters: dict):
        """Übersetzt {field: expr}-Dict in (WHERE-Klausel, params-Dict) für SQLAlchemy text()."""
        if not filters:
            return "", {}

        def quote(name):
            if self.db_type == "mssql":    return f"[{name}]"
            elif self.db_type == "mysql":  return f"`{name}`"
            else:                           return f'"{name}"'

        def cast_text(col_expr):
            if self.db_type == "mssql":   return f"CAST({col_expr} AS NVARCHAR(MAX))"
            elif self.db_type == "mysql": return f"CAST({col_expr} AS CHAR)"
            else:                          return f"CAST({col_expr} AS TEXT)"

        parts, params = [], {}
        for i, (field, expr) in enumerate(filters.items()):
            if not expr:
                continue
            expr = expr.strip()
            col = quote(field)
            pname = f"_f{i}"
            if expr.upper().startswith("LIKE "):
                pattern = expr[5:].strip().strip('"').strip("'")
                params[pname] = pattern
                parts.append(f"{cast_text(col)} LIKE :{pname}")
            else:
                for op in (">=", "<=", "!=", "=", ">", "<"):
                    if expr.startswith(op):
                        raw = expr[len(op):].strip().strip('"').strip("'")
                        params[pname] = raw
                        sql_op = "<>" if op == "!=" else op
                        parts.append(f"{col} {sql_op} :{pname}")
                        break

        return (" AND ".join(parts), params) if parts else ("", {})

    def fetch_filtered(self, filters: dict, limit: int = None) -> pd.DataFrame:
        """Lädt Daten mit WHERE-Filter direkt auf dem DB-Server."""
        from sqlalchemy import text
        where, params = self._build_where(filters)
        if self.db_type == "mssql":
            top = f"TOP {limit} " if limit else ""
            sql = f"SELECT {top}* FROM ({self.sql}) AS _f"
        else:
            sql = f"SELECT * FROM ({self.sql}) AS _f"
        if where:
            sql += f" WHERE {where}"
        if limit and self.db_type != "mssql":
            sql += f" LIMIT {limit}"
        engine = self._get_engine()
        with engine.connect() as conn:
            result = conn.execute(text(sql), params)
            cols = list(result.keys())
            rows = [dict(zip(cols, row)) for row in result.fetchall()]
        df = pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)
        return _normalize_df(df)

    def supports_pushdown(self) -> bool:
        return True

    @property
    def connector_type(self) -> str:
        return f"sql_{self.db_type}"

    def build_connection_string(db_type: str, host: str, port: int,
                                database: str, username: str, password: str) -> str:
        """Hilfsfunktion: baut Connection-String aus Einzelteilen."""
        if db_type == "mssql":
            return (f"mssql+pymssql://{username}:{password}@{host}:{port}/{database}")
        elif db_type == "mysql":
            return (f"mysql+pymysql://{username}:{password}@{host}:{port}/{database}?charset=utf8mb4")
        elif db_type == "postgresql":
            return (f"postgresql+psycopg2://{username}:{password}@{host}:{port}/{database}")
        raise ValueError(f"Unbekannter db_type: {db_type}")
