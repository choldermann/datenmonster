"""
Datenmonster — Lizenz-Client

Ablauf:
  1. Aktivierung → POST monstersuite.de/api/v1/licenses/activate
  2. Antwort wird lokal gecacht (system_settings-Tabelle)
  3. Alle 24h: Neuvalidierung gegen Server
  4. Server nicht erreichbar → Grace Period (Standard: 14 Tage)
  5. Grace Period abgelaufen → Basis-Plan

Offline-Fallback (nur wenn LICENSE_SECRET gesetzt):
  Signierte HMAC-Keys funktionieren auch ohne Server (Entwicklung / Demo).

monstersuite.de API-Vertrag (POST /api/v1/licenses/activate + /validate):
  Request:
    { license_key, email, machine_id, hostname, product, version }
  Response (Erfolg):
    { valid: true, plan, email, valid_until, features: [...], activation_id }
  Response (Fehler):
    { valid: false, error: "invalid_key|expired|max_activations|suspended", message }
"""
import os, hmac as _hmac, hashlib, base64, json, socket, logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import httpx
from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.setting import SystemSetting
from app.models.user import User

router = APIRouter(prefix="/api/license", tags=["license"])
logger = logging.getLogger(__name__)

LICENSE_SERVER  = os.getenv("LICENSE_SERVER_URL", "https://monstersuite.de")
LICENSE_SECRET  = os.getenv("LICENSE_SECRET", "")
GRACE_DAYS      = int(os.getenv("LICENSE_GRACE_DAYS", "14"))
LICENSE_OFFLINE = os.getenv("LICENSE_OFFLINE", "").lower() in ("1", "true", "yes")
CACHE_TTL_HOURS = 24
PRODUCT_SLUG    = "datenmonster"
VERSION         = os.getenv("APP_VERSION", "dev")

# Leitsatz des Lizenzmodells: gesperrt wird der EDITOR, nicht die MASCHINE. Eine gekaufte
# Vorlage darf alles tun, was ihr Manifest vorsieht — schreiben, verschicken, nachts laufen.
# Darum sind die frueheren Sammelrechte in Lauf/Bau-Paare geteilt: ein Recht auf "pipelines"
# haette in der kostenlosen Stufe die Nachtlaeufe gekaufter Cockpits stillgelegt.
# Die IDs muessen 1:1 zu DM_FEATURES in monstersuite backend/main.py passen.
ALL_FEATURES = [
    # ── Kostenlos: gekaufte Vorlagen benutzen ─────────────────────────────────────
    {"id": "basic_etl",         "name": "Basis-ETL",               "description": "Eigene Mappings und Datasets im Rahmen des Kontingents",             "category": "ETL",             "free": True},
    {"id": "basic_export",      "name": "Basis-Export",            "description": "CSV und Excel Export",                                                "category": "ETL",             "free": True},
    {"id": "template_install",  "name": "Vorlagen installieren",   "description": "Gekaufte Vorlagen unbegrenzt einspielen und einrichten",              "category": "Vorlagen",        "free": True},
    {"id": "form_run",          "name": "Auswertungen ausführen",  "description": "Formulare und Cockpits bedienen, Drilldown, PDF-Report",              "category": "Portal",          "free": True},
    {"id": "pipeline_run",      "name": "Zeitpläne ausführen",     "description": "Nachtläufe und Zeitpläne aus installierten Vorlagen",                 "category": "Automatisierung", "free": True},
    {"id": "mail_send",         "name": "Versand aus Vorlagen",    "description": "Zustellpläne und Warnungen per E-Mail verschicken",                   "category": "Konnektoren",     "free": True},
    {"id": "db_write_template", "name": "Schreiben aus Vorlagen",  "description": "In die Ziel-Datenbank schreiben, soweit die Vorlage es vorsieht",     "category": "ETL",             "free": True},
    {"id": "portal_users",      "name": "Portal-Benutzer",         "description": "Lesende Zugänge für Kollegen im Kunden-Portal",                       "category": "Portal",          "free": True},
    {"id": "ai_use",            "name": "KI in Vorlagen",          "description": "KI-Analyse und Empfehlungen in Auswertungen (über Credits)",          "category": "KI",              "free": True},

    # ── Pro: selbst bauen ─────────────────────────────────────────────────────────
    {"id": "unlimited",         "name": "Unbegrenzter Eigenbau",   "description": "Beliebig viele Projekte, Datasets und Mappings",                      "category": "ETL",             "free": False},
    {"id": "form_build",        "name": "Formular-Editor",         "description": "Eigene Formulare und Dashboards bauen",                               "category": "Portal",          "free": False},
    {"id": "pipeline_build",    "name": "Pipeline-Editor",         "description": "Eigene Pipelines bauen und einplanen",                                "category": "Automatisierung", "free": False},
    {"id": "query_build",       "name": "Abfragen & Bausteine",    "description": "Abfrage-Generator und Report-Baukasten",                              "category": "Automatisierung", "free": False},
    {"id": "api_studio",        "name": "API Studio",              "description": "REST-Schnittstellen erkunden, testen und einbinden",                  "category": "Konnektoren",     "free": False},
    {"id": "db_write",          "name": "Freies DB-Schreiben",     "description": "Datenbank als Ziel eigener Mappings (Insert, Update, Upsert)",        "category": "ETL",             "free": False},
    {"id": "ftp_sftp",          "name": "FTP / SFTP",              "description": "Dateiübertragung via FTP und SFTP",                                   "category": "Konnektoren",     "free": False},
    {"id": "rest_sources",      "name": "REST API Quellen",        "description": "Externe REST APIs als Datenquellen einbinden",                        "category": "Konnektoren",     "free": False},
    {"id": "mail_connector",    "name": "Mail-Anbindung",          "description": "E-Mails als Datenquelle und eigene Versandwege",                      "category": "Konnektoren",     "free": False},
    {"id": "ai_build",          "name": "KI-Werkbank",             "description": "Bauaufträge per Chat, KI-Assistent, Text-zu-SQL",                     "category": "KI",              "free": False},
    {"id": "ai_memory",         "name": "KI-Wissensdatenbank",     "description": "Projektbezogenes KI-Gedächtnis & Lösungsarchiv",                      "category": "KI",              "free": False},
    {"id": "schema_catalog",    "name": "Schema-Katalog",          "description": "KI-gestützte Datenbankdokumentation & Beschreibung",                  "category": "KI",              "free": False},
    {"id": "multi_tenant",      "name": "Mehrere Mandanten",       "description": "Mehr als eine Ziel-Verbindung im Mandanten-Umschalter",               "category": "Verwaltung",      "free": False},
    {"id": "multi_user",        "name": "Mehrere Administratoren", "description": "Team-Verwaltung mit Rollen und Rechten",                              "category": "Verwaltung",      "free": False},
    {"id": "plugin_tier2",      "name": "Erweiterte Plugins",      "description": "Zusatz-Plugins für Branchen-Integrationen (JTL etc.)",                "category": "Plugins",         "free": False},
    {"id": "monitoring",        "name": "Erweitertes Monitoring",  "description": "Detaillierte Logs, Metriken und Fehleranalyse",                       "category": "Verwaltung",      "free": False},
]
FREE_FEATURES = {f["id"] for f in ALL_FEATURES if f["free"]}

CATEGORY_ORDER = ["Vorlagen", "Portal", "ETL", "Automatisierung", "Konnektoren", "KI", "Verwaltung", "Plugins"]

# ─── Machine-ID ───────────────────────────────────────────────────────────────
def _machine_id() -> str:
    try:
        raw = f"{socket.gethostname()}-{PRODUCT_SLUG}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]
    except Exception:
        return hashlib.sha256(PRODUCT_SLUG.encode()).hexdigest()[:32]

# ─── Offline-Validierung (HMAC, nur wenn LICENSE_SECRET gesetzt) ──────────────
def _validate_offline(key: str) -> Optional[dict]:
    if not LICENSE_SECRET:
        return None
    try:
        parts = key.strip().split(".")
        if len(parts) != 2:
            return None
        payload_b64, sig = parts
        expected = _hmac.new(LICENSE_SECRET.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
        if not _hmac.compare_digest(expected, sig):
            return None
        pad = (4 - len(payload_b64) % 4) % 4
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=" * pad).decode())
        if payload.get("expires") and datetime.fromisoformat(payload["expires"]) < datetime.utcnow():
            return {"valid": False, "error": "expired", "message": "Offline-Key abgelaufen"}
        return {
            "valid":       True,
            "plan":        payload.get("plan", "pro"),
            "email":       payload.get("email", ""),
            "valid_until": payload.get("expires"),
            "features":    payload.get("features", []),
            "_offline":    True,
        }
    except Exception:
        return None

# ─── Online-Validierung (monstersuite.de) ─────────────────────────────────────
def _validate_online(key: str, email: str, endpoint: str = "activate") -> Optional[dict]:
    try:
        import httpx
        with httpx.Client(timeout=8) as client:
            r = client.post(
                f"{LICENSE_SERVER}/api/v1/licenses/{endpoint}",
                json={
                    "license_key": key,
                    "email":       email,
                    "machine_id":  _machine_id(),
                    "hostname":    socket.gethostname(),
                    "product":     PRODUCT_SLUG,
                    "version":     VERSION,
                },
            )
            return r.json()
    except Exception as e:
        logger.warning(f"License server not reachable ({LICENSE_SERVER}): {e}")
        return None

# ─── DB-Helpers ───────────────────────────────────────────────────────────────
def _get(db: Session, key: str) -> str:
    s = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    return s.value if s else ""

def _set(db: Session, key: str, value: str):
    s = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if s:
        s.value = value
    else:
        db.add(SystemSetting(key=key, value=value))

def get_license_credentials(db: Session) -> tuple[str, str]:
    """Gespeicherten Lizenzschlüssel + E-Mail zurückgeben (für andere Module wie Plugin-Store)."""
    return _get(db, "license_key"), _get(db, "license_email")


def license_auth_body(db: Session) -> dict:
    """Standard-Auth-Body für monstersuite-Aufrufe (Lizenz-als-Credential)."""
    key, email = get_license_credentials(db)
    return {
        "license_key": key,
        "email":       email,
        "machine_id":  _machine_id(),
        "hostname":    socket.gethostname(),
        "product":     PRODUCT_SLUG,
        "version":     VERSION,
    }


def _load_cache(db: Session) -> Optional[dict]:
    raw = _get(db, "license_cache_json")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None

def _save_cache(db: Session, data: dict):
    _set(db, "license_cache_json", json.dumps(data))
    _set(db, "license_cache_at", datetime.utcnow().isoformat())

def _cache_age_hours(db: Session) -> Optional[float]:
    ts = _get(db, "license_cache_at")
    if not ts:
        return None
    try:
        return (datetime.utcnow() - datetime.fromisoformat(ts)).total_seconds() / 3600
    except Exception:
        return None

# ─── Kern-Logik: aktuellen Lizenzstatus ermitteln ─────────────────────────────
def _resolve_license(db: Session) -> dict:
    key   = _get(db, "license_key")
    email = _get(db, "license_email")

    free_response = {
        "status":          "free",
        "plan":            "Basis",
        "email":           None,
        "valid_until":     None,
        "last_check":      None,
        "grace_remaining": None,
        "validation_mode": "none",
        "machine_id":      _machine_id(),
        "active_features": sorted(FREE_FEATURES),
        "features":        ALL_FEATURES,
        "category_order":  CATEGORY_ORDER,
        # Kostenlos angefordert, aber noch nicht per E-Mail bestaetigt
        "free_pending":    bool(_get(db, "license_free_claim")),
        "free_email":      _get(db, "license_free_email") or None,
    }

    if not key:
        return free_response

    cache     = _load_cache(db)
    age_hours = _cache_age_hours(db)

    if LICENSE_OFFLINE and cache:
        return _build_response(cache, age_hours, "offline", email)

    if cache and age_hours is not None and age_hours < CACHE_TTL_HOURS:
        return _build_response(cache, age_hours, "cached", email)

    result = _validate_online(key, email, endpoint="validate")

    if result is None:
        if cache:
            grace_hours          = GRACE_DAYS * 24
            grace_used           = age_hours or 0
            grace_remaining_days = max(0, (grace_hours - grace_used) / 24)
            if grace_used < grace_hours:
                logger.warning(f"License server unreachable — grace period: {grace_remaining_days:.1f} days remaining")
                return _build_response(cache, age_hours, "grace", email,
                                       grace_remaining=round(grace_remaining_days, 1))
            logger.warning("License grace period expired — reverting to free plan")
            return {**free_response, "status": "grace_expired",
                    "plan": "Grace Period abgelaufen", "email": email}
        return {**free_response, "status": "invalid", "plan": "Ungültig", "email": email}

    if result.get("valid"):
        _save_cache(db, result)
        db.commit()
        return _build_response(result, 0, "online", email)

    if result.get("error") == "not_activated":
        logger.info("License not activated on this machine — attempting re-activation")
        result = _validate_online(key, email, endpoint="activate")
        if result and result.get("valid"):
            _save_cache(db, result)
            db.commit()
            return _build_response(result, 0, "online", email)

    error_msg = result.get("message") or result.get("error") or "Lizenz ungültig"
    logger.warning(f"License rejected by server: {error_msg}")
    return {**free_response, "status": "invalid", "plan": error_msg, "email": email}


def _build_response(server_data: dict, age_hours: Optional[float],
                    mode: str, stored_email: str,
                    grace_remaining: Optional[float] = None) -> dict:
    expired = False
    if server_data.get("valid_until"):
        try:
            expired = datetime.fromisoformat(server_data["valid_until"]) < datetime.utcnow()
        except Exception:
            pass

    active = set(FREE_FEATURES)
    if not expired:
        active.update(server_data.get("features", []))

    last_check = None
    if age_hours is not None:
        last_check = (datetime.utcnow() - timedelta(hours=age_hours)).isoformat(timespec="minutes")

    return {
        "status":          "expired" if expired else ("grace" if grace_remaining is not None else "active"),
        "plan":            server_data.get("plan", "Pro"),
        "email":           server_data.get("email", stored_email),
        "valid_until":     server_data.get("valid_until"),
        "last_check":      last_check,
        "grace_remaining": grace_remaining,
        "validation_mode": mode,
        "machine_id":      _machine_id(),
        "active_features": sorted(active),
        "features":        ALL_FEATURES,
        "category_order":  CATEGORY_ORDER,
        "_offline":        server_data.get("_offline", False),
    }

# ─── Feature-Gate-Dependency ──────────────────────────────────────────────────
def require_feature(feature_id: str):
    """FastAPI-Dependency-Factory: 402 wenn Feature nicht lizenziert."""
    def _check(db: Session = Depends(get_db)):
        lic = _resolve_license(db)
        if feature_id not in (lic.get("active_features") or []):
            raise HTTPException(
                status_code=402,
                detail=f"Feature '{feature_id}' nicht lizenziert — Upgrade: monstersuite.de",
            )
    return _check

# ─── Endpoints ────────────────────────────────────────────────────────────────
@router.get("/")
def get_license(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _resolve_license(db)

class ActivateRequest(BaseModel):
    key: str
    email: str

@router.post("/activate")
def activate(req: ActivateRequest, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    key   = req.key.strip()
    email = req.email.strip()

    if not key or not email:
        return {"ok": False, "error": "Bitte Key und E-Mail eingeben"}

    result = _validate_online(key, email, endpoint="activate")

    if result is None:
        offline = _validate_offline(key)
        if offline and offline.get("valid"):
            _set(db, "license_key",   key)
            _set(db, "license_email", email)
            _save_cache(db, offline)
            db.commit()
            return {"ok": True, "plan": offline.get("plan", "offline"),
                    "mode": "offline", "features": offline.get("features", [])}
        return {"ok": False, "error": f"Lizenzserver ({LICENSE_SERVER}) nicht erreichbar und kein gültiger Offline-Key"}

    if not result.get("valid"):
        return {"ok": False, "error": result.get("message") or result.get("error") or "Aktivierung fehlgeschlagen"}

    _speichere_lizenz(db, key, email, result)
    # Von Hand eingetragener Schluessel erledigt eine noch offene Frei-Anforderung
    _set(db, "license_free_claim", "")
    db.commit()
    return {"ok": True, "plan": result.get("plan"), "mode": "online",
            "features": result.get("features", []), "email": result.get("email")}

@router.get("/kontingent")
def kontingent_uebersicht(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Wie voll sind die Grenzen der kostenlosen Stufe? Fuer die Anzeige im
    Lizenz-Bereich — der Anwender soll nicht erst beim Speichern erfahren, dass
    er am Anschlag ist."""
    from app.core import kontingent as k
    beschriftung = {
        "mappings":     "Eigene Mappings",
        "datasets":     "Eigene Datasets",
        "projekte":     "Projekte",
        "verbindungen": "Mandanten (Verbindungen)",
        "benutzer":     "Administratoren",
    }
    posten = []
    for art, grenze in k.GRENZEN.items():
        unbegrenzt = k.hat_recht(db, k.RECHT_FUER[art])
        posten.append({
            "art":        art,
            "label":      beschriftung.get(art, art),
            "benutzt":    k.eigenbau_anzahl(db, art),
            "grenze":     None if unbegrenzt else grenze,
            "unbegrenzt": unbegrenzt,
        })
    return {"posten": posten,
            "hinweis": "Objekte aus installierten Vorlagen zählen nicht mit."}


# ─── Kostenlosen Zugang selbst holen ──────────────────────────────────────────
#
# Der Kunde soll den Lizenzserver nicht besuchen muessen: er tippt hier seine
# E-Mail ein, bestaetigt sie im Postfach, und diese Installation holt den
# Schluessel danach selbst ab. Zwischen beiden Schritten koennen Tage liegen —
# das Abholzeichen bleibt deshalb gespeichert, bis es eingeloest ist.

class FreeRequestBody(BaseModel):
    email: str

def _speichere_lizenz(db: Session, key: str, email: str, result: dict) -> None:
    _set(db, "license_key",   key)
    _set(db, "license_email", email)
    _save_cache(db, result)
    # Sonst gilt die alte Rechte-Auskunft noch bis zu 30 Sekunden weiter
    from app.core.lizenz_gate import cache_leeren
    cache_leeren()

@router.post("/free-request")
def free_request(req: FreeRequestBody, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Kostenlosen Zugang anfordern — verschickt die Bestaetigungsmail."""
    email = req.email.strip()
    if not email:
        return {"ok": False, "error": "Bitte E-Mail-Adresse eingeben"}
    if _get(db, "license_key"):
        return {"ok": False, "error": "Es ist bereits ein Lizenzschlüssel hinterlegt."}

    try:
        with httpx.Client(timeout=15) as client:
            r = client.post(f"{LICENSE_SERVER}/api/v1/licenses/free-request",
                            json={"email":      email,
                                  "product":    PRODUCT_SLUG,
                                  "machine_id": _machine_id(),
                                  "hostname":   socket.gethostname(),
                                  "version":    VERSION})
        data = r.json()
    except Exception as e:
        logger.warning(f"free-request fehlgeschlagen: {e}")
        return {"ok": False, "error": f"Lizenzserver ({LICENSE_SERVER}) nicht erreichbar"}

    if not data.get("ok"):
        return {"ok": False, "error": data.get("message") or "Anforderung wurde abgelehnt"}

    _set(db, "license_free_claim", data.get("claim_token", ""))
    _set(db, "license_free_email", email)
    db.commit()
    return {"ok": True, "pending": True, "email": email,
            "message": data.get("message") or f"Bestätigungsmail an {email} verschickt."}

@router.post("/free-claim")
def free_claim(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Nachsehen, ob die E-Mail bestaetigt wurde — und den Schluessel dann eintragen."""
    token = _get(db, "license_free_claim")
    if not token:
        return {"ok": False, "status": "none", "error": "Keine offene Anforderung"}

    try:
        with httpx.Client(timeout=15) as client:
            r = client.post(f"{LICENSE_SERVER}/api/v1/licenses/free-claim",
                            json={"claim_token": token})
        data = r.json()
    except Exception as e:
        logger.warning(f"free-claim fehlgeschlagen: {e}")
        return {"ok": False, "status": "error",
                "error": f"Lizenzserver ({LICENSE_SERVER}) nicht erreichbar"}

    status = data.get("status")
    if status == "pending":
        return {"ok": True, "status": "pending",
                "message": "Noch nicht bestätigt — bitte den Link in der E-Mail anklicken."}

    if status != "ready":
        # Abgelaufen oder zurueckgezogen: Anforderung verwerfen, damit die
        # Oberflaeche einen sauberen zweiten Versuch anbieten kann.
        _set(db, "license_free_claim", "")
        db.commit()
        return {"ok": False, "status": "invalid",
                "error": data.get("message") or "Die Anforderung ist nicht mehr gültig."}

    key   = data.get("license_key", "")
    email = data.get("email") or _get(db, "license_free_email")
    result = _validate_online(key, email, endpoint="activate")
    if result is None:
        return {"ok": False, "status": "error",
                "error": f"Lizenzserver ({LICENSE_SERVER}) nicht erreichbar"}
    if not result.get("valid"):
        return {"ok": False, "status": "error",
                "error": result.get("message") or result.get("error") or "Aktivierung fehlgeschlagen"}

    _speichere_lizenz(db, key, email, result)
    _set(db, "license_free_claim", "")
    db.commit()
    return {"ok": True, "status": "active", "plan": result.get("plan"),
            "email": email, "features": result.get("features", [])}

@router.delete("/free-request")
def free_request_abbrechen(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Offene Anforderung verwerfen (z.B. falsche E-Mail eingetippt)."""
    _set(db, "license_free_claim", "")
    _set(db, "license_free_email", "")
    db.commit()
    return {"ok": True}

@router.post("/refresh")
def refresh(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    key   = _get(db, "license_key")
    email = _get(db, "license_email")
    if not key:
        return {"ok": False, "error": "Kein Lizenzschlüssel gespeichert"}
    result = _validate_online(key, email, endpoint="validate")
    if result is None:
        return {"ok": False, "error": f"Lizenzserver ({LICENSE_SERVER}) nicht erreichbar"}
    if not result.get("valid") and result.get("error") == "not_activated":
        logger.info("Refresh: not_activated — attempting re-activation")
        result = _validate_online(key, email, endpoint="activate")
    if result and result.get("valid"):
        _save_cache(db, result)
        db.commit()
        return {"ok": True, "plan": result.get("plan"), "checked_at": datetime.utcnow().isoformat()}
    return {"ok": False, "error": (result or {}).get("message") or (result or {}).get("error") or "Lizenz ungültig"}

@router.delete("/")
def deactivate(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    for k in ("license_key", "license_email", "license_cache_json", "license_cache_at",
              "license_free_claim", "license_free_email"):
        _set(db, k, "")
    db.commit()
    from app.core.lizenz_gate import cache_leeren
    cache_leeren()
    return {"ok": True}

# ─── Offline-Key-Generator (Entwicklung / Demo) ───────────────────────────────
def generate_offline_key(email: str, features: list[str],
                         plan: str = "pro", expires: Optional[str] = None) -> str:
    if not LICENSE_SECRET:
        raise ValueError("LICENSE_SECRET ist nicht gesetzt")
    payload = {"email": email, "plan": plan, "features": features,
               "issued": datetime.utcnow().date().isoformat()}
    if expires:
        payload["expires"] = expires
    b64 = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()
    sig = _hmac.new(LICENSE_SECRET.encode(), b64.encode(), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"
