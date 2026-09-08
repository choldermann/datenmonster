import os
import httpx
from fastapi import APIRouter, Depends, HTTPException
from app.api.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/update", tags=["update"])

# Leere UPDATER_URL schaltet den Update-Weg ab. Gedacht fuer Entwicklungsrechner:
# der Updater ersetzt den lokalen Build durch die GHCR-Images und macht damit den
# gerade bearbeiteten Stand unwirksam – ein Fehlklick reicht.
UPDATER_URL = os.getenv("UPDATER_URL", "http://updater:9000").strip()
UPDATER_AUS = not UPDATER_URL
AUS_TEXT = ("In dieser Installation ist die Update-Funktion abgeschaltet "
            "(UPDATER_URL ist leer).")


@router.get("/check")
def check_update(user: User = Depends(get_current_user)):
    """Vergleicht lokales Image mit aktuellem GHCR-Image."""
    if UPDATER_AUS:
        # up_to_date=True, damit die Oberflaeche keinen Update-Hinweis einblendet.
        return {"current": "—", "latest": "—", "up_to_date": True, "behind": 0,
                "disabled": True, "detail": AUS_TEXT}
    try:
        r = httpx.get(f"{UPDATER_URL}/version", timeout=10)
        return r.json()
    except Exception as e:
        return {
            "current": "—",
            "latest": "—",
            "up_to_date": True,
            "behind": 0,
            "error": str(e)[:200],
        }


@router.get("/changelog")
def get_changelog(user: User = Depends(get_current_user)):
    """Gibt die Commit-Liste zwischen aktuellem und neuestem Image zurück."""
    if UPDATER_AUS:
        return []
    try:
        r = httpx.get(f"{UPDATER_URL}/changelog", timeout=10)
        return r.json()
    except Exception:
        return []


@router.post("/install")
def install_update(user: User = Depends(get_current_user)):
    """Startet den Update-Prozess (Pull neue Images, Neustart)."""
    if not getattr(user, "is_admin", False):
        raise HTTPException(403, "Nur Administratoren können Updates installieren")
    if UPDATER_AUS:
        raise HTTPException(409, AUS_TEXT)
    try:
        r = httpx.post(f"{UPDATER_URL}/update/start", timeout=10)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@router.get("/status")
def update_status(user: User = Depends(get_current_user)):
    """Aktueller Fortschritt eines laufenden Updates."""
    if UPDATER_AUS:
        return {"step": None, "msg": AUS_TEXT, "done": True, "error": False,
                "disabled": True, "detail": ""}
    try:
        r = httpx.get(f"{UPDATER_URL}/update/status", timeout=5)
        return r.json()
    except Exception as e:
        return {"step": None, "msg": "", "done": False, "error": True, "detail": str(e)[:200]}
