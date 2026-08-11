"""
API Studio – REST-APIs testen, verstehen und in Datenflüsse verwandeln.

Datenmodell-Grundsatz: ein Studio-„Request" IST eine RestSource. Was hier
dazukommt, sind nur die Klammern drumherum:

  Sammlung (ApiCollection)  – gemeinsame Basis-URL, Header und Auth
  Umgebung (ApiEnvironment) – {{variablen}} für Test/Produktion
  Verlauf  (ApiRequestHistory) – was wurde wann mit welchem Ergebnis geschickt

Ein gespeicherter Request ist damit sofort ein planbarer Connector – ohne Export.
"""

import json
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Any

from app.core.database import get_db
from app.core.security import get_current_user, encrypt_credential, decrypt_credential
from app.models.user import User
from app.models.rest_source import RestSource
from app.models.api_studio import ApiCollection, ApiEnvironment, ApiRequestHistory
from app.api.projects import require_editor, can_read_project, get_accessible_project_ids
from app.services.rest_service import (
    execute_request, join_url, _SENSITIVE_AUTH_KEYS, _mask_headers, HTTP_METHODS,
)
from app.core.net_guard import guarded_request
from app.services.openapi_import import (
    lade_spec, parse_spec, request_aus_endpunkt, platzhalter_sammeln,
)
from app.services.api_studio_analyse import analysiere, redigiere, variablen_vorschlaege
from app.services.ai_service import build_ai_service

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


# ══ KI-Assistent ══════════════════════════════════════════════════════════════
#
# Aufteilung nach dem Grundsatz „erst rechnen, dann fragen":
# Struktur, Datenpfade und Paginierung kommen aus der deterministischen Analyse –
# exakt, sofort und kostenlos. Das Sprachmodell bekommt nur das verdichtete,
# maskierte Inventar und beantwortet die Fragen, die Rechnen nicht beantwortet:
# Was ist das fachlich? Wie heißen die Felder auf Deutsch? Warum klemmt es?

class AnalyseIn(BaseModel):
    body: Any = None                      # geparste Antwort (aus dem Response-Viewer)
    response_headers: Optional[dict] = {}
    status_code: Optional[int] = None
    url: Optional[str] = None
    method: Optional[str] = "GET"
    data_path: Optional[str] = None
    mit_ki: bool = False                  # Standard aus: erst rechnen, KI auf Wunsch
    echte_werte: bool = False             # Beispielwerte unmaskiert an die KI geben
    project_id: Optional[int] = None


class DebugIn(BaseModel):
    url: Optional[str] = None
    method: Optional[str] = "GET"
    headers: Optional[dict] = {}
    query_params: Optional[dict] = {}
    body_type: Optional[str] = None
    body_content: Optional[str] = None
    auth_type: Optional[str] = None
    status_code: Optional[int] = None
    reason: Optional[str] = None
    response_body: Optional[str] = None
    error: Optional[str] = None
    project_id: Optional[int] = None


class VariablenIn(BaseModel):
    url: Optional[str] = None
    headers: Optional[dict] = {}
    query_params: Optional[dict] = {}
    project_id: Optional[int] = None


def _modus(echte_werte: bool) -> str:
    return "vollstaendig" if echte_werte else "sicher"


@router.post("/analyze")
async def analyze_response(
    payload: AnalyseIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Antwort untersuchen: Felder, Typen, Füllgrade, Datenpfad und Paginierung.

    Der deterministische Teil läuft immer. `mit_ki=true` legt eine fachliche
    Einordnung darüber – dann verlässt das (maskierte) Inventar diese Maschine,
    falls der Gateway-Provider aktiv ist.
    """
    _check_read(payload.project_id, user, db)
    if payload.body is None:
        raise HTTPException(400, "Keine Antwort zum Analysieren übergeben")

    modus = _modus(payload.echte_werte)
    ergebnis = analysiere(payload.body, payload.response_headers,
                          payload.data_path, modus)
    ergebnis["ki"] = None

    if not payload.mit_ki:
        return ergebnis

    svc = build_ai_service(db)
    if svc is None:
        ergebnis["ki_fehler"] = "KI-Integration ist nicht aktiviert"
        return ergebnis

    # Nur das Inventar geht raus – nie die rohe Antwort.
    felder = "\n".join(
        f"- {f['pfad']} ({f['typ']}, gefüllt {int(f['anteil_gefuellt'] * 100)}%"
        + (", eindeutig" if f["wirkt_wie_schluessel"] else "")
        + f", Beispiel: {f['beispiel']})"
        for f in ergebnis["inventar"][:60]
    )
    frage = (
        f"Endpunkt: {payload.method} {(payload.url or '').split('?')[0]}\n"
        f"Datenpfad zur Liste: {ergebnis['datenpfad'] or '(Antwort ist direkt die Liste)'}\n"
        f"Datensätze in dieser Antwort: {ergebnis['zeilen']}\n\n"
        f"Felder:\n{felder}\n"
    )
    system = (
        "Du hilfst dabei, eine unbekannte REST-Schnittstelle zu verstehen. "
        "Du bekommst ein Feld-Inventar, keine echten Daten – Beispielwerte in "
        "spitzen Klammern wie <email> oder <text:12> sind absichtlich maskiert; "
        "kommentiere die Maskierung nicht. "
        "Antworte auf Deutsch, sachlich und knapp. Erfinde keine Felder, die "
        "nicht in der Liste stehen."
    )
    schema = {
        "type": "object",
        "properties": {
            "zusammenfassung": {"type": "string"},
            "vorgeschlagener_dataset_name": {"type": "string"},
            "felder": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "pfad": {"type": "string"},
                        "bedeutung": {"type": "string"},
                    },
                    "required": ["pfad", "bedeutung"],
                },
            },
            "hinweise": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["zusammenfassung", "vorgeschlagener_dataset_name", "felder", "hinweise"],
    }
    auftrag = (
        frage
        + "\nAufgaben:\n"
        "1. zusammenfassung: 2-3 Sätze, was dieser Endpunkt fachlich liefert.\n"
        "2. vorgeschlagener_dataset_name: kurzer deutscher Name für ein Dataset.\n"
        "3. felder: für die maximal 12 wichtigsten Felder je eine kurze deutsche "
        "Bedeutung (Pfad exakt übernehmen).\n"
        "4. hinweise: auffällige Punkte, z.B. schlecht gefüllte Felder, "
        "vermutliche Schlüssel oder Datumsfelder für einen Zeitfilter."
    )
    try:
        ergebnis["ki"] = await svc.complete_json(
            [{"role": "system", "content": system}, {"role": "user", "content": auftrag}],
            schema, temperature=0.2, request_type="DATA_ANALYSIS")
    except Exception as e:
        ergebnis["ki_fehler"] = f"KI-Analyse fehlgeschlagen: {str(e)[:200]}"
    return ergebnis


@router.post("/debug")
async def debug_request(
    payload: DebugIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Fehler-Debugger: warum antwortet die API nicht so wie erwartet?

    Bekommt die Anfrage (Header maskiert) und den Fehler bzw. Statuscode und
    schlägt konkrete Änderungen vor, die das Frontend zur Bestätigung anbietet –
    nie automatisch anwendet.
    """
    _check_read(payload.project_id, user, db)
    svc = build_ai_service(db)
    if svc is None:
        raise HTTPException(400, "KI-Integration ist nicht aktiviert")

    # Auch der Fehlertext der Gegenstelle kann Daten enthalten → maskieren.
    antwort_auszug = payload.response_body or ""
    if antwort_auszug:
        try:
            antwort_auszug = json.dumps(
                redigiere(json.loads(antwort_auszug), "sicher"), ensure_ascii=False)[:1500]
        except (json.JSONDecodeError, ValueError):
            antwort_auszug = antwort_auszug[:800]

    beschreibung = (
        f"Anfrage: {payload.method} {(payload.url or '').split('?')[0]}\n"
        f"Auth-Verfahren: {payload.auth_type or 'keines'}\n"
        f"Header: {', '.join(_mask_headers(payload.headers or {}).keys()) or '(keine)'}\n"
        f"Query-Parameter: {', '.join((payload.query_params or {}).keys()) or '(keine)'}\n"
        f"Body-Typ: {payload.body_type or 'keiner'}\n"
        f"Status: {payload.status_code or '–'} {payload.reason or ''}\n"
        f"Transportfehler: {payload.error or '(keiner)'}\n"
        f"Antwort (maskiert): {antwort_auszug or '(leer)'}"
    )
    system = (
        "Du bist erfahren im Debuggen von REST-Schnittstellen. Werte sind teils "
        "maskiert (***, <email>); das ist Absicht und kein Fehler. "
        "Antworte auf Deutsch. Nenne die wahrscheinlichste Ursache zuerst und "
        "bleibe bei dem, was aus den Angaben hervorgeht – rate nicht ins Blaue."
    )
    schema = {
        "type": "object",
        "properties": {
            "diagnose": {"type": "string"},
            "pruefpunkte": {"type": "array", "items": {"type": "string"}},
            "vorschlaege": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "feld": {"type": "string"},
                        "neuer_wert": {"type": "string"},
                        "begruendung": {"type": "string"},
                    },
                    "required": ["feld", "neuer_wert", "begruendung"],
                },
            },
        },
        "required": ["diagnose", "pruefpunkte", "vorschlaege"],
    }
    auftrag = (
        beschreibung
        + "\n\nAufgaben:\n"
        "1. diagnose: 2-3 Sätze zur wahrscheinlichsten Ursache.\n"
        "2. pruefpunkte: 2-5 konkrete Dinge zum Nachsehen, absteigend nach Wahrscheinlichkeit.\n"
        "3. vorschlaege: konkrete Änderungen an der Anfrage. `feld` ist einer von "
        "url, method, auth_type, header:<Name>, query:<Name>, body_type, body_content. "
        "Nennt die Antwort der Gegenstelle einen bestimmten Header, Parameter oder "
        "Auth-Typ, MUSS dazu ein Vorschlag entstehen. Sonst nur Vorschläge, bei denen "
        "du dir sicher bist – im Zweifel eine leere Liste."
    )
    try:
        return await svc.complete_json(
            [{"role": "system", "content": system}, {"role": "user", "content": auftrag}],
            schema, temperature=0.2, request_type="TRANSFORMATION")
    except Exception as e:
        raise HTTPException(502, f"KI-Fehler: {str(e)[:200]}")


@router.post("/suggest-variables")
def suggest_variables(
    payload: VariablenIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Was aus dieser Anfrage gehört in eine Umgebung? Rein deterministisch –
    Host und alles, was nach Zugangsdaten aussieht.
    """
    _check_read(payload.project_id, user, db)
    return {"vorschlaege": variablen_vorschlaege(payload.model_dump())}


# ══ Integration: vom Request zum laufenden Datenfluss ═════════════════════════
#
# Hier entsteht nichts Neues – es werden nur vorhandene Bausteine verdrahtet:
# der Import aus rest_sources legt das Dataset an, das Mapping ist ein ganz
# normales Mapping mit Dataset-Quelle und Dataset-Ziel, und die Pipeline
# benutzt den bestehenden rest_fetch-Node.

_TYP_ZU_MAPPING = {
    "ganzzahl": "integer", "kommazahl": "float", "ja/nein": "boolean",
    "datum": "date", "datumzeit": "datetime", "email": "string",
    "url": "string", "uuid": "string", "text": "string",
    "liste": "string", "objekt": "string", "leer": "string",
}


def _feldname(pfad: str) -> str:
    """
    Aus einem Antwort-Pfad einen brauchbaren Spaltennamen machen:
    `customer.first_name` → `customer_first_name`, `items[].sku` → `items_sku`.
    """
    name = re.sub(r"\[\]", "", pfad or "")
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    name = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()
    return name or "feld"


class IntegrationPreviewIn(BaseModel):
    rest_source_id: Optional[int] = None
    body: Any = None
    url: Optional[str] = None
    method: Optional[str] = "GET"
    data_path: Optional[str] = None
    name: Optional[str] = None
    project_id: Optional[int] = None
    mit_ki: bool = False


class IntegrationFeld(BaseModel):
    quelle: str
    ziel: str
    typ: str = "string"
    uebernehmen: bool = True


class IntegrationCreateIn(BaseModel):
    rest_source_id: int
    dataset_name: str
    felder: List[IntegrationFeld] = []
    mit_mapping: bool = False
    mit_pipeline: bool = False
    cron: Optional[str] = None
    environment_id: Optional[int] = None
    project_id: Optional[int] = None


@router.post("/integration/preview")
async def integration_preview(
    payload: IntegrationPreviewIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Vorschlag, wie aus dieser Antwort ein Datenfluss wird: Dataset-Name und
    Spaltenliste. Namen werden deterministisch abgeleitet; `mit_ki=true` lässt
    zusätzlich sprechende deutsche Spaltennamen vorschlagen.
    """
    _check_read(payload.project_id, user, db)
    if payload.body is None:
        raise HTTPException(400, "Keine Antwort übergeben – bitte zuerst senden")

    a = analysiere(payload.body, None, payload.data_path, "sicher")
    if not a["inventar"]:
        raise HTTPException(400, "In dieser Antwort sind keine Felder erkennbar")

    basis = payload.name or (payload.url or "").rstrip("/").split("/")[-1].split("?")[0] or "API-Daten"
    felder = [{
        "quelle": f["pfad"],
        "ziel": _feldname(f["pfad"]),
        "typ": _TYP_ZU_MAPPING.get(f["typ"], "string"),
        # Felder, die fast nie gefüllt sind, standardmäßig weglassen –
        # sie blähen das Ziel nur auf.
        "uebernehmen": f["anteil_gefuellt"] >= 0.1,
        "anteil_gefuellt": f["anteil_gefuellt"],
        "wirkt_wie_schluessel": f["wirkt_wie_schluessel"],
        "hinweis": "",
    } for f in a["inventar"]]

    ergebnis = {
        "dataset_name": basis,
        "pipeline_name": f"{basis} abrufen",
        "mapping_name": f"{basis} aufbereiten",
        "datenpfad": a["datenpfad"],
        "zeilen": a["zeilen"],
        "paginierung": a["paginierung"],
        "felder": felder,
    }

    if not payload.mit_ki:
        return ergebnis

    svc = build_ai_service(db)
    if svc is None:
        ergebnis["ki_fehler"] = "KI-Integration ist nicht aktiviert"
        return ergebnis

    liste = "\n".join(f"- {f['quelle']} ({f['typ']})" for f in felder[:60])
    schema = {
        "type": "object",
        "properties": {
            "dataset_name": {"type": "string"},
            "felder": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "quelle": {"type": "string"},
                        "ziel": {"type": "string"},
                    },
                    "required": ["quelle", "ziel"],
                },
            },
        },
        "required": ["dataset_name", "felder"],
    }
    auftrag = (
        f"Endpunkt: {payload.method} {(payload.url or '').split('?')[0]}\n"
        f"Felder der Antwort:\n{liste}\n\n"
        "Schlage deutsche Spaltennamen vor: kleingeschrieben, Wörter mit Unterstrich "
        "getrennt, ohne Umlaute-Ersatz-Zirkus (ae/oe/ue ist in Ordnung), keine Leerzeichen. "
        "Übernimm `quelle` exakt. Schlage außerdem einen kurzen deutschen Namen für das "
        "Dataset vor."
    )
    try:
        ki = await svc.complete_json(
            [{"role": "system", "content": "Du benennst Datenfelder klar und knapp auf Deutsch."},
             {"role": "user", "content": auftrag}],
            schema, temperature=0.2, request_type="TRANSFORMATION")
        umbenennung = {f["quelle"]: _feldname(f["ziel"]) for f in ki.get("felder", [])}
        for f in ergebnis["felder"]:
            if umbenennung.get(f["quelle"]):
                f["hinweis"] = f"deterministisch wäre: {f['ziel']}"
                f["ziel"] = umbenennung[f["quelle"]]
        if ki.get("dataset_name"):
            ergebnis["dataset_name"] = ki["dataset_name"]
            ergebnis["pipeline_name"] = f"{ki['dataset_name']} abrufen"
            ergebnis["mapping_name"] = f"{ki['dataset_name']} aufbereiten"
    except Exception as e:
        ergebnis["ki_fehler"] = f"KI-Vorschlag fehlgeschlagen: {str(e)[:200]}"
    return ergebnis


@router.post("/integration/create")
def integration_create(
    payload: IntegrationCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Legt den Datenfluss an: Dataset immer, Mapping und Pipeline auf Wunsch.

    Das Dataset entsteht über den bestehenden Import aus rest_sources – inklusive
    Paginierung, Auth und Sammlungs-Vorgaben. Es wird also mit echten Daten
    gefüllt, nicht mit einem geratenen Schema.
    """
    from app.api.rest_sources import import_rest_source, ImportRequest
    from app.models.mapping import Mapping
    from app.models.pipeline import Pipeline

    quelle = db.query(RestSource).filter(RestSource.id == payload.rest_source_id).first()
    if not quelle:
        raise HTTPException(404, "Request nicht gefunden")
    project_id = payload.project_id if payload.project_id is not None else quelle.project_id
    _check_write(project_id, user, db)

    # Umgebung am Request festhalten, damit geplante Läufe dieselben Variablen sehen.
    if payload.environment_id is not None and quelle.environment_id != payload.environment_id:
        quelle.environment_id = payload.environment_id
        db.commit()

    angelegt = {"dataset": None, "mapping": None, "pipeline": None}

    # ── 1. Dataset (echte Daten über den vorhandenen Import) ──
    try:
        ds = import_rest_source(
            quelle.id,
            ImportRequest(dataset_name=payload.dataset_name, project_id=project_id,
                          dataset_mode="replace", dataset_id=None),
            db, user)
    except HTTPException as e:
        if e.status_code == 204:
            raise HTTPException(400, "Die API lieferte keine Daten – Integration nicht angelegt")
        raise
    angelegt["dataset"] = {"id": ds["id"], "name": ds["name"], "zeilen": ds["row_count"]}

    felder = [f for f in payload.felder if f.uebernehmen]

    # ── 2. Mapping (Rohdataset → aufbereitetes Dataset) ──
    if payload.mit_mapping and felder:
        ziel_name = f"{payload.dataset_name} aufbereitet"
        m = Mapping(
            name=f"{payload.dataset_name} aufbereiten",
            project_id=project_id,
            canvas_nodes=[{"id": f"ds{ds['id']}", "dataset_id": ds["id"],
                           "dataset_name": ds["name"], "x": 80, "y": 80}],
            targets=[{
                "id": "t1", "name": ziel_name, "target_type": "dataset",
                "target_connection_id": None, "target_table": "",
                "target_write_mode": "replace",
                "target_options": {"dataset_write_mode": "replace"},
                "fields": [{
                    "source_field": f.quelle,
                    "target_field": f.ziel,
                    "target_type": f.typ,
                    "source_dataset_id": ds["id"],
                    "transformer": {"type": "direct", "source_field": f.quelle},
                } for f in felder],
            }],
        )
        db.add(m); db.commit(); db.refresh(m)
        angelegt["mapping"] = {"id": m.id, "name": m.name, "ziel_dataset": ziel_name}

    # ── 3. Pipeline (Auslöser → REST holen → Mapping) ──
    if payload.mit_pipeline:
        nodes = [
            {"id": "trg", "type": "trigger", "x": 100, "y": 140,
             "config": ({"trigger_mode": "schedule", "cron": payload.cron}
                        if payload.cron else {"trigger_mode": "manual"})},
            {"id": "rest", "type": "rest_fetch", "x": 400, "y": 140,
             "config": {"rest_source_id": quelle.id, "dataset_name": quelle.name}},
        ]
        verbindungen = [{"from_node": "trg", "from_port": "out",
                         "to_node": "rest", "to_port": "in"}]
        if angelegt["mapping"]:
            nodes.append({"id": "map", "type": "mapping", "x": 700, "y": 140,
                          "config": {"mapping_id": angelegt["mapping"]["id"], "on_error": "stop"}})
            verbindungen.append({"from_node": "rest", "from_port": "out",
                                 "to_node": "map", "to_port": "in"})
        p = Pipeline(name=f"{payload.dataset_name} abrufen", project_id=project_id,
                     active=True, nodes=nodes, connections=verbindungen)
        db.add(p); db.commit(); db.refresh(p)
        angelegt["pipeline"] = {"id": p.id, "name": p.name, "cron": payload.cron}

    return angelegt


# ══ OpenAPI-Import ════════════════════════════════════════════════════════════
#
# Aus einer Beschreibungsdatei wird eine Sammlung mit fertigen Requests. Die
# Datei wird über den Egress-Guard geholt (keine Umgehung des SSRF-Schutzes),
# und $ref-Verweise werden nur innerhalb des Dokuments aufgelöst.

MAX_SPEC_BYTES = 8 * 1024 * 1024


class OpenApiImportIn(BaseModel):
    url: Optional[str] = None
    inhalt: Optional[str] = None       # eingefügte oder hochgeladene Datei
    project_id: Optional[int] = None


class OpenApiCollectionIn(BaseModel):
    project_id: Optional[int] = None
    name: str
    basis_url: Optional[str] = None
    beschreibung: Optional[str] = None
    auth_type: str = "none"
    auth_config: Optional[dict] = {}
    endpunkte: List[dict] = []          # die vom Nutzer gewählten Endpunkte
    umgebung_anlegen: bool = False
    umgebung_name: Optional[str] = None
    variablen: List[dict] = []


@router.post("/openapi/import")
def openapi_import(
    payload: OpenApiImportIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Eine OpenAPI-/Swagger-Datei einlesen und als Sammlungs-Vorschlag zurückgeben.
    Es wird noch nichts gespeichert – der Nutzer wählt erst die Endpunkte aus.
    """
    _check_read(payload.project_id, user, db)

    inhalt = payload.inhalt
    if not inhalt:
        if not payload.url:
            raise HTTPException(400, "Weder URL noch Dateiinhalt übergeben")
        try:
            import requests as _requests
            sitzung = _requests.Session()
            resp = guarded_request(sitzung, "GET", payload.url, timeout=30)
            resp.raise_for_status()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(502, f"Datei konnte nicht geladen werden: {str(e)[:250]}")
        if len(resp.content or b"") > MAX_SPEC_BYTES:
            raise HTTPException(413, "Die Beschreibung ist größer als 8 MB")
        inhalt = resp.text

    if len(inhalt) > MAX_SPEC_BYTES:
        raise HTTPException(413, "Die Beschreibung ist größer als 8 MB")

    try:
        ergebnis = parse_spec(lade_spec(inhalt), payload.url)
    except ValueError as e:
        raise HTTPException(400, str(e))

    ergebnis["variablen_vorschlag"] = platzhalter_sammeln(ergebnis["endpunkte"])
    return ergebnis


@router.post("/openapi/create-collection")
def openapi_create_collection(
    payload: OpenApiCollectionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Sammlung, Requests und optional eine Umgebung aus dem Import anlegen."""
    _check_write(payload.project_id, user, db)
    if not payload.endpunkte:
        raise HTTPException(400, "Keine Endpunkte ausgewählt")

    sammlung = ApiCollection(
        name=payload.name,
        project_id=payload.project_id,
        description=payload.beschreibung,
        base_url=payload.basis_url,
        default_headers={"Accept": "application/json"},
        auth_type=payload.auth_type or "none",
        auth_config=_encrypt_auth(payload.auth_config or {}),
    )
    db.add(sammlung); db.commit(); db.refresh(sammlung)

    umgebung = None
    if payload.umgebung_anlegen and payload.variablen:
        umgebung = ApiEnvironment(
            name=payload.umgebung_name or "Standard",
            project_id=payload.project_id,
            collection_id=sammlung.id,
            variables=_encrypt_variables(payload.variablen),
        )
        db.add(umgebung); db.commit(); db.refresh(umgebung)

    angelegt = []
    for i, ep in enumerate(payload.endpunkte):
        felder = request_aus_endpunkt(ep)
        s = RestSource(
            project_id=payload.project_id,
            collection_id=sammlung.id,
            environment_id=umgebung.id if umgebung else None,
            sort_order=i,
            pagination={"type": "none"},
            dataset_mode="replace",
            active=1,
            **felder,
        )
        db.add(s)
        angelegt.append(s)
    db.commit()

    return {
        "sammlung": collection_out(sammlung),
        "umgebung": environment_out(umgebung) if umgebung else None,
        "requests": len(angelegt),
    }
