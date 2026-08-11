"""
REST API Connector Service

Features:
- Template-Variablen in URL, Headern, Body: {{heute}}, {{gestern}}, {{timestamp}}, {{iso_heute}}
  sowie freie Variablen aus einer API-Studio-Umgebung
- Auth: none, basic, bearer, apikey (header/query), oauth2_cc (mit Token-Cache),
  oauth2_refresh (Refresh-Token-Grant)
- Methoden: GET POST PUT PATCH DELETE HEAD OPTIONS
- Body: none, json, form, multipart, xml, raw
- Paginierung: none, page, offset, cursor, link_header
- JSONPath-Extraktion verschachtelter Daten
- Automatisches Flach-Machen von Nested-Objects
- Timeout & Retry-Logik
- execute_request(): Einzel-Request mit vollständiger Antwort (für den API-Tester)
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

from app.core.net_guard import assert_url_allowed, guarded_request
from app.core.security import decrypt_credential

# Sensible Felder in auth_config, die verschlüsselt gespeichert werden.
_SENSITIVE_AUTH_KEYS = ("password", "token", "value", "client_secret", "refresh_token")

# Header, deren Wert nie zurückgegeben oder im Verlauf gespeichert wird.
_SENSITIVE_HEADERS = {
    "authorization", "proxy-authorization", "cookie", "set-cookie",
    "x-api-key", "api-key", "apikey", "x-auth-token", "x-access-token",
}

# Alle unterstützten HTTP-Methoden.
HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")

# Antwortkörper werden für die Anzeige gedeckelt (sonst blockiert eine 50-MB-Antwort das UI).
MAX_BODY_CHARS = 200_000


def _decrypt_auth_config(auth_config: dict) -> dict:
    """auth_config-Kopie mit entschlüsselten Secrets. Legacy-Klartext (unverschlüsselt
    gespeichert) läuft dank decrypt_credential-Fallback unverändert durch – ebenso die
    Klartextwerte aus dem Test-Dialog."""
    if not auth_config:
        return {}
    out = dict(auth_config)
    for k in _SENSITIVE_AUTH_KEYS:
        if out.get(k):
            out[k] = decrypt_credential(out[k])
    return out


# ── OAuth2 Token Cache (In-Memory, reicht für einen Container) ────────────────
_oauth2_cache: dict[str, tuple[str, float]] = {}  # key → (token, expires_at)


# ── Template-Variablen auflösen ───────────────────────────────────────────────
def _builtin_vars() -> dict:
    """Die fest eingebauten Datums-/Zeit-Variablen."""
    today = date.today()
    now = datetime.now()
    return {
        "heute":     today.isoformat(),
        "gestern":   (today - timedelta(days=1)).isoformat(),
        "morgen":    (today + timedelta(days=1)).isoformat(),
        "timestamp": str(int(time.time())),
        "epoch_ms":  str(int(time.time() * 1000)),
        "iso_heute": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "monat":     today.strftime("%Y-%m"),
        "jahr":      str(today.year),
    }


def _resolve_templates(text: str, variables: Optional[dict] = None) -> str:
    """
    Ersetzt {{variable}} Platzhalter in URLs, Headern und Bodies.

    Eingebaute Variablen:
        {{heute}}       → 2025-03-10
        {{gestern}}     → 2025-03-09
        {{morgen}}      → 2025-03-11
        {{timestamp}}   → Unix-Timestamp (Sekunden)
        {{iso_heute}}   → 2025-03-10T00:00:00
        {{monat}}       → 2025-03
        {{jahr}}        → 2025
        {{epoch_ms}}    → Unix-Timestamp (Millisekunden)

    `variables` sind zusätzliche Werte aus einer API-Studio-Umgebung. Die eingebauten
    Variablen haben Vorrang – so ändert das Auswählen einer Umgebung nie das Verhalten
    bestehender Connectors.
    """
    if not text:
        return text
    mapping = {**(variables or {}), **_builtin_vars()}
    def replace(m):
        key = m.group(1).strip()
        val = mapping.get(key)
        return m.group(0) if val is None else str(val)  # unbekannte Variablen unverändert lassen
    return re.sub(r"\{\{(.+?)\}\}", replace, text)


def _resolve_dict(d: dict, variables: Optional[dict] = None) -> dict:
    return {k: _resolve_templates(str(v), variables) for k, v in d.items()}


def _mask_headers(headers: dict) -> dict:
    """Header-Kopie, in der sensible Werte durch *** ersetzt sind."""
    return {
        k: ("***" if k.lower() in _SENSITIVE_HEADERS else v)
        for k, v in (headers or {}).items()
    }


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
def _get_oauth2_token(
    cfg: dict,
    grant: str = "client_credentials",
    on_new_refresh_token=None,
) -> str:
    """
    Holt ein Access-Token per Client-Credentials- oder Refresh-Token-Grant.
    Access-Tokens werden im Speicher gecacht (reicht für einen Container).

    Manche Anbieter geben bei jedem Refresh ein NEUES Refresh-Token zurück und
    entwerten das alte. `on_new_refresh_token` wird dann aufgerufen, damit der
    Aufrufer es speichern kann – sonst schlägt der nächste Lauf fehl.
    """
    cache_seed = f"{grant}{cfg.get('token_url')}{cfg.get('client_id')}"
    if grant == "refresh_token":
        cache_seed += cfg.get("refresh_token", "")
    cache_key = hashlib.md5(cache_seed.encode()).hexdigest()

    cached = _oauth2_cache.get(cache_key)
    if cached and time.time() < cached[1] - 30:  # 30s Puffer
        return cached[0]

    if grant == "refresh_token":
        data = {
            "grant_type": "refresh_token",
            "refresh_token": cfg.get("refresh_token", ""),
            "client_id": cfg.get("client_id", ""),
        }
        if cfg.get("client_secret"):
            data["client_secret"] = cfg["client_secret"]
    else:
        data = {
            "grant_type": "client_credentials",
            "client_id": cfg.get("client_id", ""),
            "client_secret": cfg.get("client_secret", ""),
        }
    if cfg.get("scope"):
        data["scope"] = cfg["scope"]

    assert_url_allowed(cfg["token_url"])  # SSRF-Schutz auch für den Token-Endpoint
    resp = requests.post(cfg["token_url"], data=data, timeout=15)
    resp.raise_for_status()
    token_data = resp.json()
    token = token_data["access_token"]
    expires_in = token_data.get("expires_in", 3600)
    _oauth2_cache[cache_key] = (token, time.time() + expires_in)

    # Rotiertes Refresh-Token durchreichen, damit es persistiert werden kann.
    new_refresh = token_data.get("refresh_token")
    if grant == "refresh_token" and new_refresh and new_refresh != cfg.get("refresh_token"):
        # Cache auch unter dem neuen Token ablegen – der nächste Aufruf sucht dort.
        new_key = hashlib.md5(
            f"{grant}{cfg.get('token_url')}{cfg.get('client_id')}{new_refresh}".encode()
        ).hexdigest()
        _oauth2_cache[new_key] = (token, time.time() + expires_in)
        if on_new_refresh_token:
            try:
                on_new_refresh_token(new_refresh)
            except Exception:
                pass  # Speichern darf den laufenden Request nicht kippen

    return token


def _build_session(
    auth_type: str,
    auth_config: dict,
    variables: Optional[dict] = None,
    on_new_refresh_token=None,
) -> tuple[requests.Session, dict, dict]:
    """
    Baut eine requests.Session mit Auth.
    Gibt (session, extra_headers, extra_params) zurück.
    """
    session = requests.Session()
    extra_headers = {}
    extra_params = {}

    if auth_type == "basic":
        session.auth = HTTPBasicAuth(
            _resolve_templates(auth_config.get("username", ""), variables),
            _resolve_templates(auth_config.get("password", ""), variables),
        )
    elif auth_type == "bearer":
        token = _resolve_templates(auth_config.get("token", ""), variables)
        extra_headers["Authorization"] = f"Bearer {token}"
    elif auth_type == "apikey":
        key   = auth_config.get("key", "X-Api-Key")
        value = _resolve_templates(auth_config.get("value", ""), variables)
        if auth_config.get("location", "header") == "query":
            extra_params[key] = value
        else:
            extra_headers[key] = value
    elif auth_type == "oauth2_cc":
        token = _get_oauth2_token(auth_config, "client_credentials")
        extra_headers["Authorization"] = f"Bearer {token}"
    elif auth_type == "oauth2_refresh":
        token = _get_oauth2_token(auth_config, "refresh_token", on_new_refresh_token)
        extra_headers["Authorization"] = f"Bearer {token}"

    return session, extra_headers, extra_params


# ── Einzelner Request ─────────────────────────────────────────────────────────
def _parse_kv_lines(text: str, variables: Optional[dict] = None) -> dict:
    """Zeilenformat `key=value` in ein Dict wandeln (Kommentarzeilen mit # ignorieren)."""
    out = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = _resolve_templates(v.strip(), variables)
    return out


def _body_kwargs(
    body_type: str,
    body_content: Optional[str],
    headers: dict,
    variables: Optional[dict] = None,
) -> dict:
    """
    Baut die requests-Argumente für den Body. Setzt bei Bedarf einen passenden
    Content-Type, überschreibt aber nie einen selbst gesetzten Header.
    """
    if not body_content or body_type in (None, "none"):
        return {}
    has_ct = any(k.lower() == "content-type" for k in (headers or {}))

    if body_type == "json":
        try:
            return {"json": json.loads(_resolve_templates(body_content, variables))}
        except json.JSONDecodeError as e:
            raise ValueError(f"Ungültiger JSON-Body: {e}")
    if body_type == "form":
        return {"data": _parse_kv_lines(body_content, variables)}
    if body_type == "multipart":
        # requests erzeugt aus `files` einen multipart/form-data-Body inkl. Boundary.
        fields = _parse_kv_lines(body_content, variables)
        return {"files": {k: (None, v) for k, v in fields.items()}}
    if body_type == "xml":
        kw = {"data": _resolve_templates(body_content, variables).encode("utf-8")}
        if not has_ct:
            kw["_content_type"] = "application/xml"
        return kw
    # raw
    return {"data": _resolve_templates(body_content, variables).encode("utf-8")}


def _apply_body(kwargs: dict, body_kw: dict) -> dict:
    """`_content_type` aus _body_kwargs in die Header übernehmen."""
    ct = body_kw.pop("_content_type", None)
    kwargs.update(body_kw)
    if ct:
        kwargs["headers"] = {**kwargs.get("headers", {}), "Content-Type": ct}
    return kwargs


def _do_request(
    session: requests.Session,
    method: str,
    url: str,
    headers: dict,
    params: dict,
    body_type: str,
    body_content: Optional[str],
    timeout: int = 30,
    variables: Optional[dict] = None,
) -> dict:
    """Führt einen einzelnen HTTP-Request aus und gibt den Response-Body zurück."""
    kwargs = dict(headers=headers, params=params, timeout=timeout)
    _apply_body(kwargs, _body_kwargs(body_type, body_content, headers, variables))

    resp = guarded_request(session, method, url, **kwargs)  # SSRF-geprüft (inkl. Redirects)
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
    variables: Optional[dict] = None,
) -> list:
    """
    Holt alle Seiten und gibt eine kombinierte Liste von Records zurück.
    """
    pag_type = (pagination or {}).get("type", "none")
    all_records = []
    page_count = 0

    if pag_type == "none":
        body, _ = _do_request(session, method, base_url, headers, base_params, body_type, body_content, variables=variables)
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
            body, _ = _do_request(session, method, base_url, headers, params, body_type, body_content, variables=variables)
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
            body, _ = _do_request(session, method, base_url, headers, params, body_type, body_content, variables=variables)
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
            body, _ = _do_request(session, method, base_url, headers, params, body_type, body_content, variables=variables)
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
            body, resp_headers = _do_request(session, method, url, headers, params, body_type, body_content, variables=variables)
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


# ── Vorgaben einer API-Studio-Sammlung ────────────────────────────────────────
def join_url(base_url: Optional[str], url: str) -> str:
    """
    Basis-URL einer Sammlung mit dem Request-Pfad verbinden.
    Eine absolute URL im Request gewinnt immer – so bleibt ein einzelner
    Fremd-Endpunkt innerhalb einer Sammlung möglich.
    """
    url = (url or "").strip()
    if not base_url or url.lower().startswith(("http://", "https://")):
        return url
    from urllib.parse import urljoin
    return urljoin(base_url.rstrip("/") + "/", url.lstrip("/"))


def sammlungs_vorgaben(collection_id) -> dict:
    """
    Basis-URL, Standard-Header und Auth der Sammlung als einfaches Dict.

    Wird auch beim geplanten Lauf gebraucht: ein im API Studio gespeicherter Request
    kann eine relative URL und geerbte Auth haben – ohne diese Auflösung liefe der
    Scheduler gegen eine unvollständige URL und ganz ohne Anmeldung.
    """
    if not collection_id:
        return {}
    from app.core.database import SessionLocal
    from app.models.api_studio import ApiCollection
    db = SessionLocal()
    try:
        c = db.query(ApiCollection).filter(ApiCollection.id == collection_id).first()
        if not c:
            return {}
        # Werte herauskopieren, solange die Session noch offen ist.
        return {
            "base_url": c.base_url,
            "default_headers": dict(c.default_headers or {}),
            "auth_type": c.auth_type or "none",
            "auth_config": dict(c.auth_config or {}),
        }
    finally:
        db.close()


def aufgeloeste_config(source) -> dict:
    """
    Request-Konfiguration inklusive der Vorgaben seiner Sammlung.
    Request-eigene Werte gewinnen gegen die Vorgaben.
    """
    vorgaben = sammlungs_vorgaben(getattr(source, "collection_id", None))

    auth_type   = getattr(source, "auth_type", None) or "none"
    auth_config = getattr(source, "auth_config", None) or {}
    if auth_type == "inherit":
        auth_type   = vorgaben.get("auth_type", "none")
        auth_config = vorgaben.get("auth_config", {})
    if auth_type == "inherit":          # keine Sammlung dahinter
        auth_type = "none"

    return {
        "url": join_url(vorgaben.get("base_url"), getattr(source, "url", "") or ""),
        "headers": {**vorgaben.get("default_headers", {}), **(getattr(source, "headers", None) or {})},
        "auth_type": auth_type,
        "auth_config": auth_config,
    }


# ── Haupt-Fetch-Funktion ──────────────────────────────────────────────────────
def fetch_rest_source(source, variables: Optional[dict] = None) -> pd.DataFrame:
    """
    Holt Daten von einem REST-Endpoint und gibt einen DataFrame zurück.
    `source` ist ein RestSource-ORM-Objekt.
    `variables` sind optionale Umgebungs-Variablen aus dem API Studio.
    """
    cfg = aufgeloeste_config(source)

    # Templates in URL auflösen
    url = _resolve_templates(cfg["url"], variables)

    # Headers zusammensetzen
    headers = _resolve_dict(cfg["headers"], variables)
    params  = _resolve_dict(source.query_params or {}, variables)

    # Auth (Secrets vor Gebrauch entschlüsseln – stored=verschlüsselt, Test=Klartext)
    session, extra_headers, extra_params = _build_session(
        cfg["auth_type"],
        _decrypt_auth_config(cfg["auth_config"]),
        variables,
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
        variables=variables,
    )

    if not records:
        return pd.DataFrame()

    # Flatten
    if source.flatten:
        records = [_flatten(r) if isinstance(r, dict) else {"value": r} for r in records]
    else:
        records = [r if isinstance(r, dict) else {"value": r} for r in records]

    return pd.DataFrame(records)


def test_rest_source(source_dict: dict, variables: Optional[dict] = None) -> dict:
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
        df = fetch_rest_source(src, variables)
        if df.empty:
            return {"success": True, "rows": 0, "columns": [], "preview": [], "warning": "Leere Antwort"}
        # json_safe statt where(notnull, None): bei float-Spalten bliebe sonst NaN
        # stehen und die Antwort wäre kein gültiges JSON.
        preview = json_safe(df.head(10).to_dict(orient="records"))
        return {
            "success": True,
            "rows": len(df),
            "columns": [str(c) for c in df.columns],
            "preview": preview,
        }
    except Exception as e:
        return {"success": False, "error": str(e)[:500]}


# ── Einzel-Request für den API-Tester ─────────────────────────────────────────
def json_safe(wert):
    """
    NaN/Infinity aus Pandas in None wandeln und alles Übrige JSON-tauglich machen.

    Nötig, weil `df.where(notnull, None)` bei float-Spalten wirkungslos ist (None
    wird sofort wieder zu NaN) und json.dumps daraus das Literal `NaN` schreibt –
    daran scheitert jedes JSON.parse im Browser.
    """
    if isinstance(wert, dict):
        return {str(k): json_safe(v) for k, v in wert.items()}
    if isinstance(wert, (list, tuple)):
        return [json_safe(v) for v in wert]
    if isinstance(wert, float):
        return None if (wert != wert or wert in (float("inf"), float("-inf"))) else wert
    if wert is None or isinstance(wert, (str, int, bool)):
        return wert
    if pd.isna(wert) is True:      # pd.NaT, pd.NA
        return None
    return str(wert)


def _tabelle_aus_json(body, data_path: Optional[str], flatten: int) -> dict:
    """
    Versucht, aus einer geparsten JSON-Antwort eine Tabellen-Vorschau abzuleiten –
    dieselbe Logik, die der Import später benutzt. Schlägt das fehl, bleibt es beim
    reinen Antwort-Text; das ist kein Fehler, sondern nur „nicht tabellarisch".

    `table_hint` nennt den Pfad, unter dem die eigentliche Liste steckt – der übliche
    Griff bei unbekannten APIs. Er wird immer mitgeliefert, solange kein data_path
    gesetzt ist: auch eine Antwort, die als Einzelobjekt „irgendwie" tabellarisch
    aussieht, meint fast nie die gewünschte Tabelle.
    """
    leer = {"rows": 0, "columns": [], "preview": [], "table_hint": None}
    hinweis = None if data_path else _tabellen_pfad_vorschlag(body)
    try:
        records = _extract_path(body, data_path) if data_path else body
        if isinstance(records, dict):
            records = [records]
        if not isinstance(records, list) or not records:
            return {**leer, "table_hint": hinweis}
        if flatten:
            records = [_flatten(r) if isinstance(r, dict) else {"value": r} for r in records]
        else:
            records = [r if isinstance(r, dict) else {"value": r} for r in records]
        df = pd.DataFrame(records)
        preview = df.head(25).to_dict(orient="records")
        return {
            "rows": len(df),
            "columns": [str(c) for c in df.columns],
            "preview": json_safe(preview),
            "table_hint": hinweis,
        }
    except Exception:
        return {**leer, "table_hint": hinweis}


def _tabellen_pfad_vorschlag(body, prefix: str = "", tiefe: int = 0) -> Optional[str]:
    """
    Sucht in einer JSON-Antwort den ersten Pfad, unter dem eine Liste von Objekten
    liegt – der übliche „wo stecken die Daten?"-Griff bei unbekannten APIs.
    """
    if tiefe > 4 or not isinstance(body, dict):
        return None
    for k, v in body.items():
        pfad = f"{prefix}.{k}" if prefix else k
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return pfad
    for k, v in body.items():
        if isinstance(v, dict):
            treffer = _tabellen_pfad_vorschlag(v, f"{prefix}.{k}" if prefix else k, tiefe + 1)
            if treffer:
                return treffer
    return None


def execute_request(
    cfg: dict,
    variables: Optional[dict] = None,
    timeout: int = 30,
    on_new_refresh_token=None,
) -> dict:
    """
    Führt EINEN Request aus und gibt die vollständige Antwort zurück –
    Statuscode, Header, Rohtext, Dauer und Größe.

    Anders als fetch_rest_source wird bei 4xx/5xx NICHT geworfen: für einen Tester
    ist „404 Not Found" ein Ergebnis, kein Absturz. `success` sagt nur, ob der
    Request überhaupt zustande kam; `ok` steht für einen 2xx-Status.

    Secrets tauchen in der Rückgabe nur maskiert auf (siehe request.headers).
    """
    ergebnis = {
        "success": False, "ok": False, "error": None,
        "status_code": None, "reason": None,
        "duration_ms": 0, "size_bytes": 0,
        "request": {}, "response_headers": {},
        "content_type": None, "body_text": "", "truncated": False,
        "json": None, "rows": 0, "columns": [], "preview": [], "table_hint": None,
    }

    method = (cfg.get("method") or "GET").upper()
    if method not in HTTP_METHODS:
        ergebnis["error"] = f"Nicht unterstützte HTTP-Methode: {method}"
        return ergebnis

    try:
        url     = _resolve_templates(cfg.get("url") or "", variables)
        headers = _resolve_dict(cfg.get("headers") or {}, variables)
        params  = _resolve_dict(cfg.get("query_params") or {}, variables)

        session, extra_headers, extra_params = _build_session(
            cfg.get("auth_type") or "none",
            _decrypt_auth_config(cfg.get("auth_config") or {}),
            variables,
            on_new_refresh_token,
        )
        # Von Auth beigesteuerte Werte separat merken – sie werden nie zurückgespiegelt.
        auth_header_keys = set(extra_headers)
        auth_param_keys  = set(extra_params)
        headers.update(extra_headers)
        params.update(extra_params)

        kwargs = dict(headers=headers, params=params, timeout=timeout)
        _apply_body(kwargs, _body_kwargs(
            cfg.get("body_type") or "none", cfg.get("body_content"), headers, variables))

        start = time.perf_counter()
        resp = guarded_request(session, method, url, **kwargs)  # SSRF-geprüft (inkl. Redirects)
        ergebnis["duration_ms"] = int((time.perf_counter() - start) * 1000)
    except Exception as e:
        ergebnis["error"] = str(e)[:500]
        return ergebnis

    sichtbare_headers = _mask_headers({
        k: ("***" if k in auth_header_keys else v) for k, v in headers.items()
    })
    ergebnis["request"] = {
        "method": method,
        "url": resp.url,
        "headers": sichtbare_headers,
        "params": {k: ("***" if k in auth_param_keys else v) for k, v in params.items()},
        "body_type": cfg.get("body_type") or "none",
    }
    ergebnis["success"]          = True
    ergebnis["status_code"]      = resp.status_code
    ergebnis["reason"]           = resp.reason
    ergebnis["ok"]               = 200 <= resp.status_code < 300
    ergebnis["response_headers"] = _mask_headers(dict(resp.headers))
    ergebnis["content_type"]     = resp.headers.get("Content-Type")
    ergebnis["size_bytes"]       = len(resp.content or b"")

    text = resp.text or ""
    if len(text) > MAX_BODY_CHARS:
        ergebnis["body_text"] = text[:MAX_BODY_CHARS]
        ergebnis["truncated"] = True
    else:
        ergebnis["body_text"] = text

    # JSON parsen wir immer versuchsweise – viele APIs setzen den Content-Type falsch.
    if text and not ergebnis["truncated"]:
        try:
            body = json.loads(text)
            ergebnis["json"] = body
            ergebnis.update(_tabelle_aus_json(
                body, cfg.get("data_path"), cfg.get("flatten", 1)))
        except (json.JSONDecodeError, ValueError):
            pass

    return ergebnis
