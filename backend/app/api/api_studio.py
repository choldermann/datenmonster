"""
API Studio – REST-APIs testen, verstehen und in Datenflüsse verwandeln.

Datenmodell-Grundsatz: ein Studio-„Request" IST eine RestSource. Was hier
dazukommt, sind nur die Klammern drumherum:

  Sammlung (ApiCollection)  – gemeinsame Basis-URL, Header und Auth
  Umgebung (ApiEnvironment) – {{variablen}} für Test/Produktion
  Verlauf  (ApiRequestHistory) – was wurde wann mit welchem Ergebnis geschickt

Ein gespeicherter Request ist damit sofort ein planbarer Connector – ohne Export.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from app.core.database import get_db
from app.core.security import get_current_user, encrypt_credential, decrypt_credential
from app.models.user import User
from app.models.rest_source import RestSource
from app.models.api_studio import ApiCollection, ApiEnvironment, ApiRequestHistory
from app.api.projects import require_editor, can_read_project, get_accessible_project_ids
from app.services.rest_service import (
    execute_request, join_url, _SENSITIVE_AUTH_KEYS, _mask_headers, HTTP_METHODS,
)

router = APIRouter(prefix="/api/api-studio", tags=["api-studio"])

_SECRET_MASK = "***"

# Wie viele Verlaufseinträge pro Projekt aufgehoben werden, bevor alte wegfallen.
HISTORY_LIMIT_PER_PROJECT = 200


# ── Zugriff ───────────────────────────────────────────────────────────────────

def _deny_portal(user: User):
    """Reine Portal-Benutzer haben im API Studio nichts zu suchen."""
    if getattr(user, "is_portal_only", False) and not getattr(user, "is_admin", False):
        raise HTTPException(403, "Kein Zugriff auf das API Studio")


def _check_read(project_id: Optional[int], user: User, db: Session):
    _deny_portal(user)
    if project_id is not None:
        if not can_read_project(project_id, user, db):
            raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    elif not getattr(user, "is_admin", False):
        raise HTTPException(403, "Nur Administratoren können projektlose Ressourcen sehen")


def _check_write(project_id: Optional[int], user: User, db: Session):
    _deny_portal(user)
    if project_id is None and not getattr(user, "is_admin", False):
        raise HTTPException(403, "Nur Administratoren können projektlose Ressourcen anlegen")
    require_editor(project_id, user, db)


def _scope_query(q, model, project_id: Optional[int], user: User, db: Session):
    """Query auf die für den Benutzer sichtbaren Projekte einschränken."""
    if project_id is not None:
        if not can_read_project(project_id, user, db):
            raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
        return q.filter(model.project_id == project_id)
    accessible = get_accessible_project_ids(user, db)
    if accessible is None:
        return q
    return q.filter(model.project_id.in_(accessible))


# ── Secrets ───────────────────────────────────────────────────────────────────

def _encrypt_auth(auth_config: dict) -> dict:
    ac = dict(auth_config or {})
    for k in _SENSITIVE_AUTH_KEYS:
        if ac.get(k) and ac[k] != _SECRET_MASK:
            ac[k] = encrypt_credential(ac[k])
    return ac


def _merge_auth(new: dict, existing: dict) -> dict:
    """Maske = unverändert (gespeicherten Wert behalten), sonst neu verschlüsseln."""
    new = dict(new or {})
    existing = existing or {}
    for k in _SENSITIVE_AUTH_KEYS:
        if new.get(k) == _SECRET_MASK:
            if existing.get(k):
                new[k] = existing[k]
            else:
                new.pop(k, None)
        elif new.get(k):
            new[k] = encrypt_credential(new[k])
    return new


def _mask_auth(auth_config: dict) -> dict:
    ac = dict(auth_config or {})
    for k in _SENSITIVE_AUTH_KEYS:
        if ac.get(k):
            ac[k] = _SECRET_MASK
    return ac


def _mask_variables(variables) -> list:
    """Geheime Variablen für die Ausgabe maskieren."""
    out = []
    for v in (variables or []):
        v = dict(v)
        if v.get("secret") and v.get("value"):
            v["value"] = _SECRET_MASK
        out.append(v)
    return out


def _encrypt_variables(new_vars, existing_vars=None) -> list:
    """
    Geheime Variablenwerte verschlüsseln. Die Maske bedeutet „unverändert" –
    dann bleibt der gespeicherte Wert stehen.
    """
    alt = {v.get("key"): v for v in (existing_vars or [])}
    out = []
    for v in (new_vars or []):
        v = dict(v)
        if v.get("secret"):
            if v.get("value") == _SECRET_MASK:
                v["value"] = (alt.get(v.get("key")) or {}).get("value", "")
            elif v.get("value"):
                v["value"] = encrypt_credential(v["value"])
        out.append(v)
    return out


def _variables_dict(env: Optional[ApiEnvironment]) -> dict:
    """Umgebung in ein {{name}} → Wert-Dict wandeln (Secrets entschlüsselt)."""
    if not env:
        return {}
    out = {}
    for v in (env.variables or []):
        key = v.get("key")
        if not key:
            continue
        val = v.get("value", "")
        out[key] = decrypt_credential(val) if v.get("secret") and val else val
    return out


# ── Ausgabe ───────────────────────────────────────────────────────────────────

def collection_out(c: ApiCollection) -> dict:
    return {
        "id": c.id, "name": c.name, "project_id": c.project_id,
        "description": c.description, "base_url": c.base_url,
        "default_headers": c.default_headers or {},
        "auth_type": c.auth_type or "none",
        "auth_config": _mask_auth(c.auth_config or {}),
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def environment_out(e: ApiEnvironment) -> dict:
    return {
        "id": e.id, "name": e.name, "project_id": e.project_id,
        "collection_id": e.collection_id,
        "variables": _mask_variables(e.variables),
        "is_default": e.is_default or 0,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def history_out(h: ApiRequestHistory, mit_body: bool = False) -> dict:
    d = {
        "id": h.id, "project_id": h.project_id, "rest_source_id": h.rest_source_id,
        "name": h.name, "method": h.method, "url": h.url,
        "status_code": h.status_code, "ok": bool(h.ok),
        "duration_ms": h.duration_ms, "response_size": h.response_size,
        "error": h.error,
        "created_at": h.created_at.isoformat() if h.created_at else None,
    }
    if mit_body:
        d["request_snapshot"] = h.request_snapshot or {}
        d["response_body"] = h.response_body
    return d


# ── Schemas ───────────────────────────────────────────────────────────────────

class CollectionIn(BaseModel):
    name: str
    project_id: Optional[int] = None
    description: Optional[str] = None
    base_url: Optional[str] = None
    default_headers: Optional[dict] = {}
    auth_type: str = "none"
    auth_config: Optional[dict] = {}


class EnvironmentIn(BaseModel):
    name: str
    project_id: Optional[int] = None
    collection_id: Optional[int] = None
    variables: Optional[List[dict]] = []
    is_default: int = 0


class SendIn(BaseModel):
    """
    Einen Request abschicken – entweder ad-hoc (URL & Co. direkt mitgeben)
    oder gespeichert (rest_source_id). Bei gespeicherten Requests dürfen
    einzelne Felder überschrieben werden, ohne dass gespeichert wird.
    """
    rest_source_id: Optional[int] = None
    collection_id: Optional[int] = None
    environment_id: Optional[int] = None
    project_id: Optional[int] = None

    name: Optional[str] = None
    url: Optional[str] = None
    method: Optional[str] = None
    headers: Optional[dict] = None
    query_params: Optional[dict] = None
    body_type: Optional[str] = None
    body_content: Optional[str] = None
    auth_type: Optional[str] = None
    auth_config: Optional[dict] = None
    data_path: Optional[str] = None
    flatten: Optional[int] = None

    timeout: int = 30
    save_history: bool = True


# ── Sammlungen ────────────────────────────────────────────────────────────────

@router.get("/collections")
def list_collections(
    project_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _deny_portal(user)
    q = _scope_query(db.query(ApiCollection), ApiCollection, project_id, user, db)
    return [collection_out(c) for c in q.order_by(ApiCollection.name).all()]


@router.post("/collections")
def create_collection(
    payload: CollectionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _check_write(payload.project_id, user, db)
    data = payload.model_dump()
    data["auth_config"] = _encrypt_auth(data.get("auth_config") or {})
    c = ApiCollection(**data)
    db.add(c); db.commit(); db.refresh(c)
    return collection_out(c)


@router.put("/collections/{collection_id}")
def update_collection(
    collection_id: int,
    payload: CollectionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    c = db.query(ApiCollection).filter(ApiCollection.id == collection_id).first()
    if not c:
        raise HTTPException(404, "Sammlung nicht gefunden")
    _check_write(c.project_id, user, db)
    if payload.project_id != c.project_id:
        _check_write(payload.project_id, user, db)
    data = payload.model_dump()
    data["auth_config"] = _merge_auth(data.get("auth_config") or {}, c.auth_config or {})
    for k, v in data.items():
        setattr(c, k, v)
    db.commit(); db.refresh(c)
    return collection_out(c)


@router.delete("/collections/{collection_id}")
def delete_collection(
    collection_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Die Sammlung fällt weg, die Requests bleiben – sie rutschen nur heraus."""
    c = db.query(ApiCollection).filter(ApiCollection.id == collection_id).first()
    if not c:
        raise HTTPException(404, "Sammlung nicht gefunden")
    _check_write(c.project_id, user, db)
    verwaist = db.query(RestSource).filter(RestSource.collection_id == collection_id).all()
    for s in verwaist:
        s.collection_id = None
    db.query(ApiEnvironment).filter(ApiEnvironment.collection_id == collection_id).update(
        {ApiEnvironment.collection_id: None})
    db.delete(c); db.commit()
    return {"ok": True, "requests_freigegeben": len(verwaist)}


# ── Umgebungen ────────────────────────────────────────────────────────────────

@router.get("/environments")
def list_environments(
    project_id: Optional[int] = None,
    collection_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _deny_portal(user)
    q = _scope_query(db.query(ApiEnvironment), ApiEnvironment, project_id, user, db)
    if collection_id is not None:
        # Projektweite Umgebungen (collection_id=None) gelten überall mit.
        q = q.filter(
            (ApiEnvironment.collection_id == collection_id)
            | (ApiEnvironment.collection_id.is_(None))
        )
    return [environment_out(e) for e in q.order_by(ApiEnvironment.name).all()]


@router.post("/environments")
def create_environment(
    payload: EnvironmentIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _check_write(payload.project_id, user, db)
    data = payload.model_dump()
    data["variables"] = _encrypt_variables(data.get("variables"))
    e = ApiEnvironment(**data)
    db.add(e); db.commit(); db.refresh(e)
    return environment_out(e)


@router.put("/environments/{env_id}")
def update_environment(
    env_id: int,
    payload: EnvironmentIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    e = db.query(ApiEnvironment).filter(ApiEnvironment.id == env_id).first()
    if not e:
        raise HTTPException(404, "Umgebung nicht gefunden")
    _check_write(e.project_id, user, db)
    if payload.project_id != e.project_id:
        _check_write(payload.project_id, user, db)
    data = payload.model_dump()
    data["variables"] = _encrypt_variables(data.get("variables"), e.variables)
    for k, v in data.items():
        setattr(e, k, v)
    db.commit(); db.refresh(e)
    return environment_out(e)


@router.delete("/environments/{env_id}")
def delete_environment(
    env_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    e = db.query(ApiEnvironment).filter(ApiEnvironment.id == env_id).first()
    if not e:
        raise HTTPException(404, "Umgebung nicht gefunden")
    _check_write(e.project_id, user, db)
    db.delete(e); db.commit()
    return {"ok": True}


# ── Request zusammenbauen ─────────────────────────────────────────────────────

def _build_config(payload: SendIn, db: Session, user: User) -> tuple[dict, Optional[RestSource], Optional[int]]:
    """
    Baut die endgültige Request-Konfiguration aus (in dieser Reihenfolge):
    gespeicherter Request → Vorgaben der Sammlung → Überschreibungen aus dem Aufruf.
    Gibt (config, source, project_id) zurück.
    """
    source = None
    cfg = {
        "url": "", "method": "GET", "headers": {}, "query_params": {},
        "body_type": "none", "body_content": None,
        "auth_type": "none", "auth_config": {},
        "data_path": None, "flatten": 1,
    }
    project_id = payload.project_id
    collection_id = payload.collection_id

    if payload.rest_source_id:
        source = db.query(RestSource).filter(RestSource.id == payload.rest_source_id).first()
        if not source:
            raise HTTPException(404, "Request nicht gefunden")
        _check_read(source.project_id, user, db)
        project_id = source.project_id
        collection_id = collection_id or source.collection_id
        cfg.update({
            "url": source.url or "", "method": source.method or "GET",
            "headers": dict(source.headers or {}),
            "query_params": dict(source.query_params or {}),
            "body_type": source.body_type or "none",
            "body_content": source.body_content,
            "auth_type": source.auth_type or "none",
            "auth_config": dict(source.auth_config or {}),
            "data_path": source.data_path, "flatten": source.flatten,
        })
    else:
        _check_read(project_id, user, db)

    # Felder aus dem Aufruf überschreiben den gespeicherten Stand.
    for feld in ("url", "method", "headers", "query_params", "body_type",
                 "body_content", "auth_type", "data_path", "flatten"):
        wert = getattr(payload, feld)
        if wert is not None:
            cfg[feld] = wert
    if payload.auth_config is not None:
        # Maskierte Secrets aus dem Frontend meinen „unverändert" → gespeicherten Wert nehmen.
        cfg["auth_config"] = _restore_masked(payload.auth_config, cfg["auth_config"])

    # Vorgaben der Sammlung anwenden.
    collection = None
    if collection_id:
        collection = db.query(ApiCollection).filter(ApiCollection.id == collection_id).first()
    if collection:
        _check_read(collection.project_id, user, db)
        cfg["url"] = join_url(collection.base_url, cfg["url"])
        # Request-Header gewinnen gegen die Standard-Header der Sammlung.
        cfg["headers"] = {**(collection.default_headers or {}), **cfg["headers"]}
        if cfg["auth_type"] in ("inherit", None, ""):
            cfg["auth_type"] = collection.auth_type or "none"
            cfg["auth_config"] = dict(collection.auth_config or {})

    if cfg["auth_type"] == "inherit":   # keine Sammlung dahinter
        cfg["auth_type"] = "none"

    if not cfg["url"]:
        raise HTTPException(400, "Keine URL angegeben")
    if (cfg["method"] or "").upper() not in HTTP_METHODS:
        raise HTTPException(400, f"Nicht unterstützte HTTP-Methode: {cfg['method']}")

    return cfg, source, project_id


def _restore_masked(neu: dict, gespeichert: dict) -> dict:
    """Maskierte Werte aus dem Frontend durch die gespeicherten ersetzen."""
    out = dict(neu or {})
    for k in _SENSITIVE_AUTH_KEYS:
        if out.get(k) == _SECRET_MASK:
            if (gespeichert or {}).get(k):
                out[k] = gespeichert[k]
            else:
                out.pop(k, None)
    return out


# ── Senden ────────────────────────────────────────────────────────────────────

@router.post("/send")
def send_request(
    payload: SendIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Führt einen einzelnen Request aus und gibt die vollständige Antwort zurück.
    Ein 404 der Ziel-API ist ein Ergebnis, kein Fehler – deshalb kommt hier
    HTTP 200 mit `status_code: 404` zurück.
    """
    cfg, source, project_id = _build_config(payload, db, user)

    env = None
    if payload.environment_id:
        env = db.query(ApiEnvironment).filter(
            ApiEnvironment.id == payload.environment_id).first()
        if not env:
            raise HTTPException(404, "Umgebung nicht gefunden")
        _check_read(env.project_id, user, db)
    variables = _variables_dict(env)

    # Rotiertes Refresh-Token direkt am Request festhalten, sonst ist der nächste Lauf tot.
    def _refresh_token_speichern(neues_token: str):
        if not source:
            return
        ac = dict(source.auth_config or {})
        ac["refresh_token"] = encrypt_credential(neues_token)
        source.auth_config = ac
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(source, "auth_config")
        db.commit()

    ergebnis = execute_request(
        cfg, variables,
        timeout=min(max(payload.timeout, 1), 120),
        on_new_refresh_token=_refresh_token_speichern,
    )

    if payload.save_history:
        _verlauf_schreiben(db, user, payload, cfg, source, project_id, ergebnis)

    return ergebnis


def _verlauf_schreiben(db, user, payload, cfg, source, project_id, ergebnis):
    """Einen Verlaufseintrag anlegen – Metadaten immer, Antwortkörper nur auf Wunsch."""
    körper = None
    if source is not None and getattr(source, "store_response", 0):
        körper = (ergebnis.get("body_text") or "")[:100_000]

    schnappschuss = {
        "method": cfg.get("method"),
        "url": cfg.get("url"),
        "headers": _mask_headers(cfg.get("headers") or {}),
        "query_params": cfg.get("query_params") or {},
        "body_type": cfg.get("body_type"),
        "body_content": (cfg.get("body_content") or "")[:10_000] or None,
        "auth_type": cfg.get("auth_type"),
        "environment_id": payload.environment_id,
    }

    h = ApiRequestHistory(
        project_id=project_id,
        rest_source_id=source.id if source else None,
        user_id=user.id,
        name=payload.name or (source.name if source else None),
        method=cfg.get("method"),
        url=(ergebnis.get("request") or {}).get("url") or cfg.get("url"),
        status_code=ergebnis.get("status_code"),
        ok=1 if ergebnis.get("ok") else 0,
        duration_ms=ergebnis.get("duration_ms"),
        response_size=ergebnis.get("size_bytes"),
        error=(ergebnis.get("error") or None),
        request_snapshot=schnappschuss,
        response_body=körper,
    )
    db.add(h); db.commit()
    _verlauf_kuerzen(db, project_id)


def _verlauf_kuerzen(db, project_id):
    """Alte Einträge wegräumen, damit der Verlauf nicht unbegrenzt wächst."""
    q = db.query(ApiRequestHistory).filter(ApiRequestHistory.project_id == project_id)
    anzahl = q.count()
    if anzahl <= HISTORY_LIMIT_PER_PROJECT:
        return
    alte = (q.order_by(ApiRequestHistory.id.desc())
             .offset(HISTORY_LIMIT_PER_PROJECT).all())
    for e in alte:
        db.delete(e)
    db.commit()


# ── Verlauf ───────────────────────────────────────────────────────────────────

@router.get("/history")
def list_history(
    project_id: Optional[int] = None,
    rest_source_id: Optional[int] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _deny_portal(user)
    q = _scope_query(db.query(ApiRequestHistory), ApiRequestHistory, project_id, user, db)
    if rest_source_id is not None:
        q = q.filter(ApiRequestHistory.rest_source_id == rest_source_id)
    eintraege = q.order_by(ApiRequestHistory.id.desc()).limit(min(limit, 500)).all()
    return [history_out(h) for h in eintraege]


@router.get("/history/{history_id}")
def get_history_entry(
    history_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    h = db.query(ApiRequestHistory).filter(ApiRequestHistory.id == history_id).first()
    if not h:
        raise HTTPException(404, "Verlaufseintrag nicht gefunden")
    _check_read(h.project_id, user, db)
    return history_out(h, mit_body=True)


@router.delete("/history/{history_id}")
def delete_history_entry(
    history_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    h = db.query(ApiRequestHistory).filter(ApiRequestHistory.id == history_id).first()
    if not h:
        raise HTTPException(404, "Verlaufseintrag nicht gefunden")
    _check_write(h.project_id, user, db)
    db.delete(h); db.commit()
    return {"ok": True}


@router.delete("/history")
def clear_history(
    project_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _check_write(project_id, user, db)
    geloescht = (db.query(ApiRequestHistory)
                   .filter(ApiRequestHistory.project_id == project_id)
                   .delete(synchronize_session=False))
    db.commit()
    return {"ok": True, "geloescht": geloescht}
