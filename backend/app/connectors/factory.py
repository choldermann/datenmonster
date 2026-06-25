"""
ConnectorFactory – wählt den richtigen Connector für ein Dataset.

Neue Connector-Typen (REST, MongoDB, ...) werden hier registriert.
mapping_service.py kennt nur die Factory – nie die konkreten Connector-Klassen.
"""
from app.connectors.base import BaseConnector
from app.core.security import decrypt_credential


def get_connector(dataset_id: int) -> BaseConnector:
    """
    Gibt den passenden Connector für ein Dataset zurück.
    Lädt das Dataset aus der DB und entscheidet anhand von file_type.
    """
    from app.core.database import SessionLocal
    from app.models.dataset import Dataset, DbConnection

    db = SessionLocal()
    try:
        ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not ds:
            raise ValueError(f"Dataset {dataset_id} nicht gefunden")

        # ── SQL-Datenbanken ───────────────────────────────────────────────────
        if ds.file_type in ("db_mssql", "db_mysql", "db_postgresql"):
            if not ds.source_connection_id or not ds.source_sql:
                raise ValueError(f"Dataset {dataset_id}: SQL-Verbindung oder Query fehlt")

            conn_obj = db.query(DbConnection).filter(
                DbConnection.id == ds.source_connection_id
            ).first()
            if not conn_obj:
                raise ValueError(f"DB-Verbindung {ds.source_connection_id} nicht gefunden")

            from app.connectors.sql import SqlConnector
            db_type = ds.file_type.replace("db_", "")  # "db_mssql" → "mssql"

            # Build connection string
            if db_type == "mssql":
                from urllib.parse import quote_plus
                params = quote_plus(
                    f"DRIVER={{ODBC Driver 18 for SQL Server}};"
                    f"SERVER={conn_obj.host},{conn_obj.port};"
                    f"DATABASE={conn_obj.database};"
                    f"UID={conn_obj.username};PWD={decrypt_credential(conn_obj.password)};"
                    f"TrustServerCertificate=yes"
                )
                conn_str = f"mssql+pyodbc:///?odbc_connect={params}"
            elif db_type == "mysql":
                conn_str = (
                    f"mysql+pymysql://{conn_obj.username}:{decrypt_credential(conn_obj.password)}@"
                    f"{conn_obj.host}:{conn_obj.port}/{conn_obj.database}?charset=utf8mb4"
                )
            elif db_type == "postgresql":
                conn_str = (
                    f"postgresql+psycopg2://{conn_obj.username}:{decrypt_credential(conn_obj.password)}@"
                    f"{conn_obj.host}:{conn_obj.port}/{conn_obj.database}"
                )
            else:
                raise ValueError(f"Unbekannter DB-Typ: {db_type}")

            return SqlConnector(db_type=db_type, connection_string=conn_str, sql=ds.source_sql)

        # ── Datei-basierte Datasets (CSV, XLSX, XML, ODS, Static) ────────────
        elif ds.file_type in ("csv", "xlsx", "xls", "xml", "json", "ods", "static"):
            from app.connectors.file import FileConnector
            return FileConnector(dataset_id=dataset_id)

        # ── REST-API Datasets ─────────────────────────────────────────────────
        elif ds.file_type == "rest_api":
            from app.models.rest_source import RestSource
            query_config = ds.query_config or {}
            if isinstance(query_config, str):
                import json as _json
                query_config = _json.loads(query_config)
            rest_source_id = query_config.get("rest_source_id")
            if not rest_source_id:
                raise ValueError(f"Dataset {dataset_id}: rest_source_id fehlt in query_config")
            src = db.query(RestSource).filter(RestSource.id == rest_source_id).first()
            if not src:
                raise ValueError(f"RestSource {rest_source_id} nicht gefunden")
            from app.connectors.rest import RestApiConnector
            return RestApiConnector(source=src)

        # ── Plugin-Quellen (Tier-1 Plugins) ──────────────────────────────────────
        else:
            from app.plugins.registry import registry
            plugin = registry.get_source(ds.file_type)
            if plugin:
                query_config = ds.query_config or {}
                if isinstance(query_config, str):
                    import json as _json
                    query_config = _json.loads(query_config)
                from app.connectors.plugin_connector import PluginConnector
                return PluginConnector(plugin=plugin, config=query_config)

            raise ValueError(f"Kein Connector für file_type='{ds.file_type}' verfügbar")

    finally:
        db.close()


def get_all_connectors(dataset_ids: list) -> dict:
    """Lädt mehrere Connectors auf einmal. Gibt {dataset_id: connector} zurück."""
    return {ds_id: get_connector(ds_id) for ds_id in dataset_ids}
