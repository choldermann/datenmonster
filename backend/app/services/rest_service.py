"""
REST API Connector Service

Features:
- Template-Variablen in URL, Headern, Body: {{heute}}, {{gestern}}, {{timestamp}}, {{iso_heute}}
- Auth: none, basic, bearer, apikey (header/query), oauth2_cc (mit Token-Cache)
- Paginierung: none, page, offset, cursor, link_header
- JSONPath-Extraktion verschachtelter Daten
- Automatisches Flach-Machen von Nested-Objects
- Timeout & Retry-Logik
"""

import re
import json
import time
import hashlib
from datetime import date, datetime, timedelta
from typing import Optional
import pandas as pd
import requests
from requests.auth import HTTPBasicAuth


# ── OAuth2 Token Cache (In-Memory, reicht für einen Container) ────────────────
_oauth2_cache: dict[str, tuple[str, float]] = {}  # key → (token, expires_at)


# ── Template-Variablen auflösen ───────────────────────────────────────────────
def _resolve_templates(text: str) -> str:
    """
    Ersetzt {{variable}} Platzhalter in URLs, Headern und Bodies.

    Verfügbare Variablen:
        {{heute}}       → 2025-03-10
        {{gestern}}     → 2025-03-09
        {{morgen}}      → 2025-03-11
        {{timestamp}}   → Unix-Timestamp (Sekunden)
        {{iso_heute}}   → 2025-03-10T00:00:00
        {{monat}}       → 2025-03
        {{jahr}}        → 2025
        {{epoch_ms}}    → Unix-Timestamp (Millisekunden)
    """
    if not text:
        return text
    today = date.today()
    now = datetime.now()
    mapping = {
        "heute":     today.isoformat(),
        "gestern":   (today - timedelta(days=1)).isoformat(),
        "morgen":    (today + timedelta(days=1)).isoformat(),
        "timestamp": str(int(time.time())),
        "epoch_ms":  str(int(time.time() * 1000)),
        "iso_heute": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "monat":     today.strftime("%Y-%m"),
        "jahr":      str(today.year),
    }
    def replace(m):
        key = m.group(1).strip()
        return mapping.get(key, m.group(0))  # unbekannte Variablen unverändert lassen
    return re.sub(r"\{\{(.+?)\}\}", replace, text)


def _resolve_dict(d: dict) -> dict:
    return {k: _resolve_templates(str(v)) for k, v in d.items()}


# ── JSONPath-Extraktion ───────────────────────────────────────────────────────
def _extract_path(data, path: str):
    """
    Navigiert durch verschachtelte Dicts/Listen mit Punkt-Notation.
    Beispiel: "data.items" → data["data"]["items"]
    """
    if not path:
        return data
    for key in path.split("."):
        if isinstance(data, dict):
            data = data.get(key)
        elif isinstance(data, list) and key.isdigit():
            data = data[int(key)]
        else:
            return None
        if data is None:
            return None
    return data


# ── Objekte flach machen ──────────────────────────────────────────────────────
def _flatten(obj: dict, prefix: str = "", sep: str = ".") -> dict:
    """Rekursiv verschachtelte Dicts zu flachen Schlüsseln ausrollen."""
    items = {}
    for k, v in obj.items():
        new_key = f"{prefix}{sep}{k}" if prefix else k
        if isinstance(v, dict):
            items.update(_flatten(v, new_key, sep))
        elif isinstance(v, list):
            # Listen als JSON-String speichern (für einfache Handhabung)
            items[new_key] = json.dumps(v, ensure_ascii=False)
        else:
            items[new_key] = v
    return items


# ── Auth ──────────────────────────────────────────────────────────────────────
def _get_oauth2_token(cfg: dict) -> str:
    """OAuth2 Client Credentials Flow mit In-Memory-Cache."""
    cache_key = hashlib.md5(
        f"{cfg.get('token_url')}{cfg.get('client_id')}".encode()
    ).hexdigest()

    cached = _oauth2_cache.get(cache_key)
    if cached and time.time() < cached[1] - 30:  # 30s Puffer
        return cached[0]

    resp = requests.post(
        cfg["token_url"],
        data={
            "grant_type": "client_credentials",
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "scope": cfg.get("scope", ""),
        },
        timeout=15,
    )
    resp.raise_for_status()
    token_data = resp.json()
    token = token_data["access_token"]
    expires_in = token_data.get("expires_in", 3600)
    _oauth2_cache[cache_key] = (token, time.time() + expires_in)
    return token


def _build_session(auth_type: str, auth_config: dict) -> tuple[requests.Session, dict, dict]:
    """
    Baut eine requests.Session mit Auth.
    Gibt (session, extra_headers, extra_params) zurück.
    """
    session = requests.Session()
    extra_headers = {}
    extra_params = {}

    if auth_type == "basic":
        session.auth = HTTPBasicAuth(
            auth_config.get("username", ""),
            auth_config.get("password", ""),
        )
    elif auth_type == "bearer":
        token = _resolve_templates(auth_config.get("token", ""))
        extra_headers["Authorization"] = f"Bearer {token}"
    elif auth_type == "apikey":
        key   = auth_config.get("key", "X-Api-Key")
        value = _resolve_templates(auth_config.get("value", ""))
        if auth_config.get("location", "header") == "query":
            extra_params[key] = value
        else:
            extra_headers[key] = value
    elif auth_type == "oauth2_cc":
        token = _get_oauth2_token(auth_config)
        extra_headers["Authorization"] = f"Bearer {token}"

    return session, extra_headers, extra_params


# ── Einzelner Request ─────────────────────────────────────────────────────────
def _do_request(
    session: requests.Session,
    method: str,
    url: str,
    headers: dict,
    params: dict,
    body_type: str,
    body_content: Optional[str],
    timeout: int = 30,
) -> dict:
    """Führt einen einzelnen HTTP-Request aus und gibt den Response-Body zurück."""
    kwargs = dict(headers=headers, params=params, timeout=timeout)

    if body_type == "json" and body_content:
        try:
            kwargs["json"] = json.loads(_resolve_templates(body_content))
        except json.JSONDecodeError as e:
            raise ValueError(f"Ungültiger JSON-Body: {e}")
    elif body_type == "form" and body_content:
        # Key=Value Zeilenformat
        form_data = {}
        for line in body_content.splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                form_data[k.strip()] = _resolve_templates(v.strip())
        kwargs["data"] = form_data
    elif body_type == "raw" and body_content:
        kwargs["data"] = _resolve_templates(body_content).encode("utf-8")

    resp = session.request(method.upper(), url, **kwargs)
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "")
    if "json" in content_type:
        return resp.json(), resp.headers
    elif "text" in content_type:
        # Versuche JSON zu parsen, sonst als Text zurückgeben
        try:
            return resp.json(), resp.headers
        except Exception:
            return {"_text": resp.text}, resp.headers
    else:
        try:
            return resp.json(), resp.headers
        except Exception:
            return {"_raw": resp.text}, resp.headers


# ── Paginierung ───────────────────────────────────────────────────────────────
def _fetch_all_pages(
    session: requests.Session,
    method: str,
    base_url: str,
    headers: dict,
    base_params: dict,
    body_type: str,
    body_content: Optional[str],
    data_path: Optional[str],
    pagination: dict,
    max_pages: int = 500,
) -> list:
    """
    Holt alle Seiten und gibt eine kombinierte Liste von Records zurück.
    """
    pag_type = (pagination or {}).get("type", "none")
    all_records = []
    page_count = 0

    if pag_type == "none":
        body, _ = _do_request(session, method, base_url, headers, base_params, body_type, body_content)
        records = _extract_path(body, data_path) if data_path else body
        if isinstance(records, list):
            return records
        elif isinstance(records, dict):
            return [records]
        return []

    elif pag_type == "page":
        page_param  = pagination.get("page_param",  "page")
        limit_param = pagination.get("limit_param", "per_page")
        limit       = pagination.get("limit",       100)
        start_page  = pagination.get("start_page",  1)
        page = start_page

        while page_count < max_pages:
            params = {**base_params, page_param: page, limit_param: limit}
            body, _ = _do_request(session, method, base_url, headers, params, body_type, body_content)
            records = _extract_path(body, data_path) if data_path else body
            if not isinstance(records, list) or len(records) == 0:
                break
            all_records.extend(records)
            if len(records) < limit:
                break
            page += 1
            page_count += 1

    elif pag_type == "offset":
        offset_param = pagination.get("offset_param", "skip")
        limit_param  = pagination.get("limit_param",  "take")
        limit        = pagination.get("limit",        100)
        offset = 0

        while page_count < max_pages:
            params = {**base_params, offset_param: offset, limit_param: limit}
            body, _ = _do_request(session, method, base_url, headers, params, body_type, body_content)
            records = _extract_path(body, data_path) if data_path else body
            if not isinstance(records, list) or len(records) == 0:
                break
            all_records.extend(records)
            if len(records) < limit:
                break
            offset += limit
            page_count += 1

    elif pag_type == "cursor":
        cursor_param = pagination.get("cursor_param", "cursor")
        cursor_path  = pagination.get("cursor_path",  "meta.next_cursor")
        limit_param  = pagination.get("limit_param",  None)
        limit        = pagination.get("limit",        None)
        cursor = None

        while page_count < max_pages:
            params = {**base_params}
            if cursor:
                params[cursor_param] = cursor
            if limit_param and limit:
                params[limit_param] = limit
            body, _ = _do_request(session, method, base_url, headers, params, body_type, body_content)
            records = _extract_path(body, data_path) if data_path else body
            if not isinstance(records, list) or len(records) == 0:
                break
            all_records.extend(records)
            next_cursor = _extract_path(body, cursor_path)
            if not next_cursor:
                break
            cursor = next_cursor
            page_count += 1

    elif pag_type == "link_header":
        # RFC 5988: Link: <https://api.example.com/next>; rel="next"
        import re as _re
        url = base_url
        params = {**base_params}

        while page_count < max_pages:
            body, resp_headers = _do_request(session, method, url, headers, params, body_type, body_content)
            records = _extract_path(body, data_path) if data_path else body
            if not isinstance(records, list) or len(records) == 0:
                break
            all_records.extend(records)
            link_header = resp_headers.get("Link", "")
            next_url = None
            for part in link_header.split(","):
                part = part.strip()
                if 'rel="next"' in part:
                    m = _re.search(r"<(.+?)>", part)
                    if m:
                        next_url = m.group(1)
                        break
            if not next_url:
                break
            url = next_url
            params = {}  # Next-URL enthält bereits alle Params
            page_count += 1

    return all_records


# ── Haupt-Fetch-Funktion ──────────────────────────────────────────────────────
def fetch_rest_source(source) -> pd.DataFrame:
    """
    Holt Daten von einem REST-Endpoint und gibt einen DataFrame zurück.
    `source` ist ein RestSource-ORM-Objekt.
    """
    # Templates in URL auflösen
    url = _resolve_templates(source.url)

    # Headers zusammensetzen
    headers = _resolve_dict(source.headers or {})
    params  = _resolve_dict(source.query_params or {})

    # Auth
    session, extra_headers, extra_params = _build_session(
        source.auth_type or "none",
        source.auth_config or {},
    )
    headers.update(extra_headers)
    params.update(extra_params)

    # Alle Seiten holen
    records = _fetch_all_pages(
        session=session,
        method=source.method or "GET",
        base_url=url,
        headers=headers,
        base_params=params,
        body_type=source.body_type or "none",
        body_content=source.body_content,
        data_path=source.data_path,
        pagination=source.pagination or {},
    )

    if not records:
        return pd.DataFrame()

    # Flatten
    if source.flatten:
        records = [_flatten(r) if isinstance(r, dict) else {"value": r} for r in records]
    else:
        records = [r if isinstance(r, dict) else {"value": r} for r in records]

    return pd.DataFrame(records)


def test_rest_source(source_dict: dict) -> dict:
    """
    Testet einen REST-Connector (ohne DB-Objekt) und gibt Vorschau zurück.
    Holt maximal 1 Seite / 10 Einträge.
    """
    class Obj:
        pass
    src = Obj()
    for k, v in source_dict.items():
        setattr(src, k, v)
    # Defaults
    for k, default in [
        ("headers", {}), ("query_params", {}), ("body_type", "none"),
        ("body_content", None), ("auth_type", "none"), ("auth_config", {}),
        ("data_path", None), ("flatten", 1), ("pagination", {}), ("method", "GET"),
    ]:
        if not hasattr(src, k):
            setattr(src, k, default)

    # Für den Test: Paginierung auf "none" setzen → nur 1 Request
    src.pagination = {}

    try:
        df = fetch_rest_source(src)
        if df.empty:
            return {"success": True, "rows": 0, "columns": [], "preview": [], "warning": "Leere Antwort"}
        preview = df.head(10).where(pd.notnull(df), None).to_dict(orient="records")
        return {
            "success": True,
            "rows": len(df),
            "columns": list(df.columns),
            "preview": preview,
        }
    except Exception as e:
        return {"success": False, "error": str(e)[:500]}
