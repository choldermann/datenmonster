from abc import abstractmethod
from typing import List

import pandas as pd

from app.plugins.base import SourcePlugin


class DocumentSourcePlugin(SourcePlugin):
    """
    Basis für alle Dokument- und Web-Datenquellen.

    Jede Unterklasse implementiert `read(url, config) → DataFrame`.
    Das Framework übernimmt get_columns / fetch / fetch_preview / test_connection.

    Gemeinsame Config-Felder (Unterklassen ergänzen format-spezifische Felder):
      url           – URL oder Dateipfad (required)
      render_mode   – static | browser (default: static; browser = Playwright, future)
      timeout       – HTTP-Timeout in Sekunden (default: 30)
      user_agent    – Custom User-Agent-String
      extra_headers – Zusätzliche HTTP-Header als JSON-String (optional)
      visual_selector_config – JSON-Konfiguration des visuellen Selektors (hidden, future)
    """

    source_category = "document"

    # Gemeinsame Config-Felder für alle Dokument-Reader
    _COMMON_CONFIG: List[dict] = [
        {
            "key": "url",
            "label": "URL / Pfad",
            "type": "string",
            "required": True,
            "placeholder": "https://example.com/data.html",
        },
        {
            "key": "render_mode",
            "label": "Render-Modus",
            "type": "select",
            "options": ["static", "browser"],
            "default": "static",
            "description": "static = direkter HTTP-Abruf; browser = Playwright (v2, noch nicht verfügbar)",
        },
        {
            "key": "timeout",
            "label": "Timeout (Sek.)",
            "type": "number",
            "default": 30,
        },
        {
            "key": "user_agent",
            "label": "User-Agent",
            "type": "string",
            "placeholder": "Datenmonster/1.0",
            "default": "",
        },
        {
            "key": "extra_headers",
            "label": "Zusätzliche Header (JSON)",
            "type": "code",
            "placeholder": '{"Authorization": "Bearer ..."}',
            "default": "",
        },
        # Hidden: wird durch den visuellen Selektor (v2) befüllt
        {
            "key": "visual_selector_config",
            "label": "Visual-Selektor-Konfiguration",
            "type": "json",
            "hidden": True,
            "default": None,
        },
    ]

    @abstractmethod
    def read(self, url: str, config: dict) -> pd.DataFrame:
        """
        Dokument laden und als DataFrame zurückgeben.
        Muss von jeder Unterklasse implementiert werden.
        """
        ...

    # ── Framework-Methoden ────────────────────────────────────────────────────

    def _get_url(self, config: dict) -> str:
        url = (config.get("url") or "").strip()
        if not url:
            raise ValueError("Kein URL angegeben")
        return url

    def _build_headers(self, config: dict) -> dict:
        import json
        headers = {"User-Agent": config.get("user_agent") or "Datenmonster/1.0"}
        extra = config.get("extra_headers") or ""
        if extra:
            try:
                headers.update(json.loads(extra))
            except Exception:
                pass
        return headers

    def _timeout(self, config: dict) -> int:
        try:
            return int(config.get("timeout") or 30)
        except (ValueError, TypeError):
            return 30

    def test_connection(self, config: dict) -> dict:
        import requests as _req
        url = self._get_url(config)
        if config.get("render_mode") == "browser":
            return {"ok": False, "message": "Browser-Modus (Playwright) ist in v1 noch nicht verfügbar."}
        try:
            resp = _req.head(url, headers=self._build_headers(config),
                             timeout=self._timeout(config), allow_redirects=True)
            resp.raise_for_status()
            return {"ok": True, "message": f"HTTP {resp.status_code} – erreichbar"}
        except Exception as e:
            # HEAD schlägt manchmal fehl – mit GET bestätigen
            try:
                resp = _req.get(url, headers=self._build_headers(config),
                                timeout=self._timeout(config), stream=True)
                resp.raise_for_status()
                return {"ok": True, "message": f"HTTP {resp.status_code} – erreichbar (GET)"}
            except Exception as e2:
                return {"ok": False, "message": str(e2)}

    def fetch(self, config: dict) -> List[dict]:
        if config.get("render_mode") == "browser":
            raise NotImplementedError("Browser-Modus (Playwright) ist in v1 noch nicht verfügbar.")
        url = self._get_url(config)
        df = self.read(url, config)
        limit = config.get("limit")
        if limit:
            df = df.head(int(limit))
        # Alle Werte als String – verhindert JSON-Serialisierungsprobleme
        df = df.astype(str).replace("nan", "").replace("None", "")
        return df.to_dict("records")

    def get_columns(self, config: dict) -> List[str]:
        rows = self.fetch(dict(config, limit=5))
        if not rows:
            return []
        return list(rows[0].keys())

    def fetch_preview(self, config: dict, limit: int = 50) -> List[dict]:
        return self.fetch(dict(config, limit=limit))
