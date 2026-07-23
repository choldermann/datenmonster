from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import requests
from app.core.database import get_db
from app.core.config import PLUGIN_MANAGER_URL
from app.api.auth import get_current_user
from app.api.license import require_feature
from app.models.user import User
from app.plugins.registry import registry

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


def _pm(path: str) -> str:
    if not PLUGIN_MANAGER_URL:
        raise HTTPException(503, "Plugin Manager nicht konfiguriert (PLUGIN_MANAGER_URL fehlt)")
    return f"{PLUGIN_MANAGER_URL.rstrip('/')}{path}"


def _pm_get(path: str) -> dict:
    try:
        resp = requests.get(_pm(path), timeout=10.0)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        raise HTTPException(e.response.status_code, e.response.text)
    except Exception as e:
        raise HTTPException(502, f"Plugin Manager nicht erreichbar: {e}")


def _pm_post(path: str, body: dict = None) -> dict:
    try:
        resp = requests.post(_pm(path), json=body or {}, timeout=60.0)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        raise HTTPException(e.response.status_code, e.response.text)
    except Exception as e:
        raise HTTPException(502, f"Plugin Manager nicht erreichbar: {e}")


def _pm_delete(path: str) -> dict:
    try:
        resp = requests.delete(_pm(path), timeout=10.0)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        raise HTTPException(e.response.status_code, e.response.text)
    except Exception as e:
        raise HTTPException(502, f"Plugin Manager nicht erreichbar: {e}")


# ── Tier-1 Endpunkte (statische Pfade VOR /{plugin_id}) ──────────────────────

@router.get("/")
def list_plugins(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Alle registrierten Plugins mit Status aus der DB."""
    from app.models.plugin import Plugin
    db_map = {p.plugin_id: p for p in db.query(Plugin).all()}
    result = []
    for p in registry.list_plugins():
        db_p = db_map.get(p["id"])
        result.append({
            **p,
            "status": db_p.status if db_p else "active",
            "installed_at": str(db_p.installed_at) if db_p and db_p.installed_at else None,
        })
    return result


@router.get("/capabilities")
def list_capabilities(user: User = Depends(get_current_user)):
    return registry.list_all_capabilities()


@router.get("/source-types")
def list_source_types(user: User = Depends(get_current_user)):
    return registry.list_source_types()


@router.get("/target-types")
def list_target_types(user: User = Depends(get_current_user)):
    return registry.list_target_types()


@router.get("/target-schema/{target_type_id}")
def get_target_schema(target_type_id: str, user: User = Depends(get_current_user)):
    """Zielfelder eines Plugin-Ziels abfragen."""
    plugin = registry.get_target(target_type_id)
    if not plugin:
        raise HTTPException(404, f"Ziel-Plugin '{target_type_id}' nicht gefunden")
    try:
        columns = plugin.get_columns({})
        return {"columns": columns}
    except Exception as e:
        raise HTTPException(502, f"Schema-Abruf fehlgeschlagen: {e}")


@router.get("/manager/health")
def plugin_manager_health(user: User = Depends(get_current_user)):
    """Plugin Manager Health-Check."""
    return _pm_get("/health")


# ── Tier-2 Endpunkte (statische Pfade VOR /{plugin_id}) ──────────────────────

@router.get("/tier2")
def list_tier2_plugins(user: User = Depends(get_current_user)):
    """Alle beim Plugin Manager registrierten Tier-2 Plugins (mit Container-Status)."""
    return _pm_get("/plugins")


class Tier2RegisterBody(BaseModel):
    id: str
    name: str
    docker_image: str
    description: str = ""
    author: str = ""
    license: str = "professional"
    capabilities: List[str] = []
    config_schema: List[dict] = []
    source_type_id: str = ""
    source_type_label: str = ""
    source_type_icon: str = "container"
    target_type_id: str = ""
    target_type_label: str = ""


@router.post("/tier2", status_code=201)
def register_tier2_plugin(body: Tier2RegisterBody, user: User = Depends(get_current_user)):
    """Tier-2 Plugin beim Plugin Manager registrieren."""
    result = _pm_post("/plugins", body.model_dump())
    from app.plugins.tier2_proxy import Tier2Plugin
    plugin = Tier2Plugin(body.model_dump(), PLUGIN_MANAGER_URL)
    registry.register(plugin)
    return result


@router.delete("/tier2/{plugin_id}")
def unregister_tier2_plugin(plugin_id: str, user: User = Depends(get_current_user)):
    """Tier-2 Plugin entfernen (stoppt und löscht den Container)."""
    return _pm_delete(f"/plugins/{plugin_id}")


@router.post("/tier2/{plugin_id}/start")
def start_tier2_plugin(plugin_id: str, user: User = Depends(get_current_user)):
    """Container für ein Tier-2 Plugin starten."""
    return _pm_post(f"/plugins/{plugin_id}/start")


@router.post("/tier2/{plugin_id}/stop")
def stop_tier2_plugin(plugin_id: str, user: User = Depends(get_current_user)):
    """Container für ein Tier-2 Plugin stoppen."""
    return _pm_post(f"/plugins/{plugin_id}/stop")


@router.get("/tier2/{plugin_id}/status")
def tier2_plugin_status(plugin_id: str, user: User = Depends(get_current_user)):
    """Container-Status eines Tier-2 Plugins abfragen."""
    return _pm_get(f"/plugins/{plugin_id}/status")


# ── Plugin-Store (lizenzgeprüfte Auslieferung über monstersuite) ──────────────

def _catalog_plugins(catalog) -> list:
    """Normalisiert die Katalog-Antwort (Liste ODER {plugins:[...]}) auf eine Liste."""
    if isinstance(catalog, dict):
        return catalog.get("plugins") or []
    return catalog or []


def _fetch_store(db) -> dict:
    """
    Holt den Katalog installierbarer Tier-2 Plugins von monstersuite (lizenzgeprüft)
    und markiert je Plugin, ob es lokal bereits installiert ist.
    Returns {"licensed": bool, "plugins": [...], "error": str | None}.
    Wirft nie – bei fehlender Lizenz / unerreichbarem Katalog kommt "error" zurück.
    """
    import httpx
    from app.api.license import license_auth_body, get_license_credentials, LICENSE_SERVER, _resolve_license

    lic = _resolve_license(db)
    licensed = "plugin_tier2" in (lic.get("active_features") or [])
    key, _ = get_license_credentials(db)
    if not key:
        return {"licensed": licensed, "plugins": [], "error": "no_license"}

    try:
        with httpx.Client(timeout=15) as c:
            r = c.post(f"{LICENSE_SERVER}/api/v1/plugins/catalog", json=license_auth_body(db))
            r.raise_for_status()
            catalog = r.json()
    except Exception as e:
        return {"licensed": licensed, "plugins": [], "error": f"catalog_unreachable: {e}"}

    plugins = _catalog_plugins(catalog)
    try:
        installed_ids = {p.get("id") for p in _pm_get("/plugins")}
    except Exception:
        installed_ids = set()
    for p in plugins:
        p["installed"] = p.get("id") in installed_ids
    return {"licensed": licensed, "plugins": plugins}


def _fetch_public_catalog() -> list:
    """
    Öffentlicher Discovery-Katalog aller für Datenmonster angebotenen Plugins
    (GET {monstersuite}/api/shop/plugins, OHNE Lizenz). So sieht auch eine Instanz
    ohne (passende) Lizenz, welche Plugins es gibt. Wirft nie – [] bei Fehler.
    """
    import httpx
    from app.api.license import LICENSE_SERVER
    try:
        with httpx.Client(timeout=10) as c:
            r = c.get(f"{LICENSE_SERVER}/api/shop/plugins")
            r.raise_for_status()
            data = r.json()
        return data if isinstance(data, list) else (data.get("plugins") or [])
    except Exception:
        return []


@router.get("/store")
def plugin_store(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Katalog installierbarer Tier-2 Plugins von monstersuite (lizenzgeprüft)."""
    return _fetch_store(db)


@router.get("/catalog")
def plugin_catalog(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Vereinter Plugin-Katalog fürs UI: führt geladene Plugins (in-process + Container),
    Container-Status und installierbare Store-Plugins zu EINER normalisierten Liste
    zusammen. Der Nutzer muss nicht mehr zwischen Tier-1/Tier-2 unterscheiden.

    Jeder Eintrag hat: kind (builtin|container), state (active|running|stopped|available),
    action (none|start|install) und needs_license. Degradiert graceful: fehlender
    Plugin-Manager oder Store führt nie zu 5xx, die übrigen Einträge bleiben erhalten.
    """
    from app.models.plugin import Plugin

    db_map = {p.plugin_id: p for p in db.query(Plugin).all()}
    src_map = {s["plugin_id"]: s for s in registry.list_source_types()}
    tgt_map = {t["plugin_id"]: t for t in registry.list_target_types()}

    # Container-Status der Tier-2 Plugins (per id) – PM optional
    pm_status = {}
    try:
        for p in _pm_get("/plugins"):
            pm_status[p.get("id")] = (p.get("status") or "").lower()
    except Exception:
        pm_status = {}

    catalog = []
    seen = set()

    # 1. Geladene Plugins (in-process + registrierte Container)
    for m in registry.list_plugins():
        pid = m["id"]
        seen.add(pid)
        db_p = db_map.get(pid)
        tier = m.get("tier") or (db_p.tier if db_p else 1)
        kind = "container" if tier == 2 else "builtin"
        src = src_map.get(pid, {})
        tgt = tgt_map.get(pid, {})

        if kind == "container":
            cstatus = pm_status.get(pid, "")
            if cstatus in ("running", "up", "healthy", "starting"):
                state, action = "running", "none"
            else:
                state, action = "stopped", "start"
        else:
            state, action = "active", "none"

        catalog.append({
            "id": pid,
            "name": m.get("name"),
            "version": m.get("version", ""),
            "description": m.get("description", ""),
            "author": m.get("author", ""),
            "license": m.get("license", "free"),
            "capabilities": m.get("capabilities", []),
            "config_schema": m.get("config_schema", []),
            "source_type_id": src.get("id", m.get("source_type_id", "")),
            "source_type_label": src.get("label", m.get("source_type_label", "")),
            "source_type_icon": src.get("icon", "database"),
            "target_type_id": tgt.get("id", m.get("target_type_id", "")),
            "target_type_label": tgt.get("label", m.get("target_type_label", "")),
            "kind": kind,
            "state": state,
            "action": action,
            "installed": True,
            "needs_license": False,
        })

    # 2. Discovery: ALLE von monstersuite angebotenen Plugins (öffentlicher Katalog).
    #    Der lizenzgeprüfte Store bestimmt nur, welche jetzt installierbar (entitled) sind.
    entitled = {}
    for p in _fetch_store(db).get("plugins", []):
        if p.get("id"):
            entitled[p["id"]] = p  # volles Manifest + installed-Flag

    for p in _fetch_public_catalog():
        pid = p.get("id")
        if not pid or pid in seen:
            continue
        ent = entitled.get(pid)
        if ent and ent.get("installed"):
            continue  # bereits installiert → schon als geladen/aktiv abgedeckt
        seen.add(pid)
        m = ent or {}  # reicheres Manifest, falls berechtigt (config_schema etc.)
        catalog.append({
            "id": pid,
            "name": p.get("name") or m.get("name") or pid,
            "version": p.get("version") or m.get("version", ""),
            "description": p.get("description") or m.get("description", ""),
            "author": p.get("author") or m.get("author", ""),
            "license": m.get("license", "professional"),
            "capabilities": p.get("capabilities") or m.get("capabilities", []),
            "config_schema": m.get("config_schema", []),
            "source_type_id": m.get("source_type_id", ""),
            "source_type_label": p.get("source_type_label") or m.get("source_type_label", ""),
            "source_type_icon": m.get("source_type_icon", "container"),
            "target_type_id": m.get("target_type_id", ""),
            "target_type_label": p.get("target_type_label") or m.get("target_type_label", ""),
            "kind": "container",
            "state": "available",
            "action": "install",
            "installed": False,
            "needs_license": pid not in entitled,
            "required_feature_name": p.get("required_feature_name", ""),
            "included_plans": p.get("included_plans", []),
        })

    return catalog


@router.post("/tier2/{plugin_id}/install", status_code=201)
def install_tier2_plugin(plugin_id: str, db: Session = Depends(get_db),
                         _feat=Depends(require_feature("plugin_tier2")),
                         user: User = Depends(get_current_user)):
    """
    Installiert ein Tier-2 Plugin lizenzgeprüft von monstersuite:
    Katalog/Manifest holen → Image-Tarball streamen → Plugin-Manager `docker load`
    → Plugin registrieren. Gated mit Feature `plugin_tier2`.
    """
    import os, tempfile
    import httpx
    from app.api.license import license_auth_body, get_license_credentials, LICENSE_SERVER

    key, _ = get_license_credentials(db)
    if not key:
        raise HTTPException(402, "Keine Lizenz aktiviert — Tier-2 Plugins erfordern eine gültige Lizenz.")
    auth = license_auth_body(db)

    # 1. Katalog → Manifest des gewünschten Plugins
    try:
        with httpx.Client(timeout=15) as c:
            r = c.post(f"{LICENSE_SERVER}/api/v1/plugins/catalog", json=auth)
            r.raise_for_status()
            catalog = r.json()
    except Exception as e:
        raise HTTPException(502, f"Plugin-Katalog nicht erreichbar: {e}")
    manifest = next((p for p in _catalog_plugins(catalog) if p.get("id") == plugin_id), None)
    if not manifest:
        raise HTTPException(404, f"Plugin '{plugin_id}' nicht im Lizenz-Katalog verfügbar")

    # 2. Image-Tarball streamen → Temp-Datei (kein Buffern im RAM)
    tmp = tempfile.NamedTemporaryFile(prefix=f"dm-plugin-{plugin_id}-", suffix=".tar.gz", delete=False)
    try:
        try:
            with httpx.Client(timeout=None) as c:
                with c.stream("POST", f"{LICENSE_SERVER}/api/v1/plugins/download",
                              json={**auth, "plugin_id": plugin_id}) as resp:
                    if resp.status_code >= 400:
                        detail = resp.read().decode(errors="replace")[:300]
                        raise HTTPException(resp.status_code,
                                            f"Download abgelehnt ({resp.status_code}): {detail}")
                    for chunk in resp.iter_bytes():
                        tmp.write(chunk)
            tmp.flush(); tmp.close()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(502, f"Image-Download von monstersuite fehlgeschlagen: {e}")

        # 3. Tarball an Plugin-Manager streamen → docker load
        try:
            with open(tmp.name, "rb") as fh:
                r = requests.post(_pm(f"/plugins/{plugin_id}/load-image"), data=fh,
                                  headers={"Content-Type": "application/octet-stream"}, timeout=600)
            r.raise_for_status()
            load_result = r.json()
        except requests.HTTPError as e:
            raise HTTPException(502, f"docker load im Plugin-Manager fehlgeschlagen: {e.response.text[:300]}")
        except Exception as e:
            raise HTTPException(502, f"Plugin-Manager nicht erreichbar (load-image): {e}")
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass

    # 4. Registrieren (Manifest → Plugin-Manager + Backend-Registry)
    reg_body = {k: manifest.get(k) for k in Tier2RegisterBody.model_fields if manifest.get(k) is not None}
    reg_body["id"] = plugin_id
    _pm_post("/plugins", reg_body)
    from app.plugins.tier2_proxy import Tier2Plugin
    registry.register(Tier2Plugin(manifest, PLUGIN_MANAGER_URL))
    return {"ok": True, "plugin_id": plugin_id, "loaded": load_result}


# ── Wildcard-Routen ZULETZT ───────────────────────────────────────────────────

@router.get("/{plugin_id}")
def get_plugin(plugin_id: str, user: User = Depends(get_current_user)):
    plugin = registry.get_plugin(plugin_id)
    if not plugin:
        raise HTTPException(404, "Plugin nicht gefunden")
    return plugin.manifest()


class TestBody(BaseModel):
    config: Optional[dict] = {}


@router.post("/{plugin_id}/test")
def test_connection(plugin_id: str, body: TestBody, user: User = Depends(get_current_user)):
    """Verbindungstest für ein Plugin mit gegebener Konfiguration."""
    from app.plugins.base import SourcePlugin, TargetPlugin
    plugin = registry.get_plugin(plugin_id)
    if not plugin:
        raise HTTPException(404, "Plugin nicht gefunden")
    if not isinstance(plugin, (SourcePlugin, TargetPlugin)):
        raise HTTPException(400, "Plugin unterstützt keinen Verbindungstest")
    try:
        return plugin.test_connection(body.config or {})
    except Exception as e:
        return {"ok": False, "message": str(e)}


@router.post("/{plugin_id}/schema")
def get_schema(plugin_id: str, body: TestBody, user: User = Depends(get_current_user)):
    """Schema (Spalten) einer Plugin-Quelle abrufen."""
    from app.plugins.base import SourcePlugin
    plugin = registry.get_plugin(plugin_id)
    if not plugin or not isinstance(plugin, SourcePlugin):
        raise HTTPException(404, "Plugin oder Quelle nicht gefunden")
    try:
        columns = plugin.get_columns(body.config or {})
        return {"columns": columns}
    except Exception as e:
        raise HTTPException(400, str(e))
