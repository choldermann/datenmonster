import json
from typing import List
from app.plugins.base import ConnectorPlugin


class Plugin(ConnectorPlugin):
    id = "mongodb-connector"
    name = "MongoDB Connector"
    version = "1.0.0"
    description = "MongoDB Collections als Datenquelle und Datenziel nutzen."
    author = "Holdermann IT"
    license = "free"
    capabilities = ["source", "target"]
    source_type_id = "mongodb"
    source_type_label = "MongoDB"
    source_type_icon = "database"
    target_type_id = "mongodb"
    target_type_label = "MongoDB"
    config_schema = [
        {"key": "uri",        "label": "MongoDB URI",   "type": "string", "required": True, "placeholder": "mongodb://user:pass@host:27017"},
        {"key": "database",   "label": "Datenbank",     "type": "string", "required": True},
        {"key": "collection", "label": "Collection",    "type": "string", "required": True},
        {"key": "query",      "label": "Filter (JSON)", "type": "code",   "default": "{}"},
        {"key": "limit",      "label": "Max. Zeilen",   "type": "number", "default": 10000},
        {"key": "write_mode", "label": "Schreibmodus",  "type": "select", "default": "insert",
         "options": ["insert", "replace_collection"]},
    ]

    def _client(self, config: dict):
        try:
            from pymongo import MongoClient
        except ImportError:
            raise RuntimeError("pymongo nicht installiert. Bitte 'pip install pymongo' ausführen.")
        return MongoClient(config["uri"], serverSelectionTimeoutMS=5000)

    def test_connection(self, config: dict) -> dict:
        try:
            client = self._client(config)
            client.admin.command("ping")
            db = client[config["database"]]
            collections = db.list_collection_names()
            return {"ok": True, "message": f"Verbindung erfolgreich. Collections: {', '.join(collections[:5]) or '(leer)'}"}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def get_columns(self, config: dict) -> List[str]:
        client = self._client(config)
        col = client[config["database"]][config["collection"]]
        sample = col.find_one({}, {"_id": 0})
        if not sample:
            return []
        return list(sample.keys())

    def fetch(self, config: dict) -> List[dict]:
        client = self._client(config)
        col = client[config["database"]][config["collection"]]
        query = json.loads(config.get("query") or "{}")
        limit = int(config.get("limit") or 10000)
        return list(col.find(query, {"_id": 0}).limit(limit))

    def fetch_preview(self, config: dict, limit: int = 50) -> List[dict]:
        client = self._client(config)
        col = client[config["database"]][config["collection"]]
        query = json.loads(config.get("query") or "{}")
        return list(col.find(query, {"_id": 0}).limit(limit))

    def write(self, rows: List[dict], config: dict) -> dict:
        client = self._client(config)
        col = client[config["database"]][config["collection"]]
        if not rows:
            return {"written": 0, "errors": []}
        write_mode = config.get("write_mode", "insert")
        if write_mode == "replace_collection":
            col.drop()
        result = col.insert_many(rows, ordered=False)
        return {"written": len(result.inserted_ids), "errors": []}
