"""
Update-Check Endpoint
Prüft ob eine neue Version auf dem Update-Server verfügbar ist.
Update-Server: https://datenmonster.com/updates/latest.json
"""
from fastapi import APIRouter, Depends, BackgroundTasks
from app.api.auth import get_current_user
from app.models.user import User
import os, subprocess

router = APIRouter(prefix="/api/update", tags=["update"])

UPDATE_URL = "https://datenmonster.com/updates/latest.json"
VERSION_FILE = os.path.join(os.path.dirname(__file__), "../../VERSION")


def _get_local_version() -> str:
    try:
        path = os.path.abspath(VERSION_FILE)
        with open(path, "r") as f:
            return f.read().strip()
    except Exception:
        return "0.0.0"


def _parse_version(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.lstrip("v").split(".")[:3])
    except Exception:
        return (0, 0, 0)


@router.get("/check")
def check_update(user: User = Depends(get_current_user)):
    """Prüft ob eine neue Version verfügbar ist."""
    import httpx

    local_version = _get_local_version()

    try:
        resp = httpx.get(UPDATE_URL, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        remote_version = data.get("version", "0.0.0")
        changelog = data.get("changelog", "")
        released = data.get("released", "")

        local_tuple  = _parse_version(local_version)
        remote_tuple = _parse_version(remote_version)
        update_available = remote_tuple > local_tuple

        return {
            "local_version":    local_version,
            "remote_version":   remote_version,
            "update_available": update_available,
            "changelog":        changelog,
            "released":         released,
        }
    except Exception as e:
        return {
            "local_version":    local_version,
            "remote_version":   None,
            "update_available": False,
            "changelog":        "",
            "released":         "",
            "error":            str(e)[:200],
        }


@router.post("/install")
def install_update(user: User = Depends(get_current_user)):
    """Führt git pull + docker compose up aus."""
    if not getattr(user, "is_admin", False):
        from fastapi import HTTPException
        raise HTTPException(403, "Nur Administratoren können Updates installieren")

    try:
        # Projektverzeichnis ermitteln (zwei Ebenen über app/)
        project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))

        result = subprocess.run(
            ["git", "pull"],
            cwd=project_dir,
            capture_output=True, text=True, timeout=60
        )
        git_output = result.stdout + result.stderr

        # Docker Compose neu starten
        compose_result = subprocess.run(
            ["docker", "compose", "up", "-d", "--build"],
            cwd=project_dir,
            capture_output=True, text=True, timeout=300
        )
        compose_output = compose_result.stdout + compose_result.stderr

        return {
            "ok": True,
            "git_output": git_output[:500],
            "compose_output": compose_output[:500],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}
