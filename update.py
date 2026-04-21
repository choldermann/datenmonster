"""
Update-Check Endpoint
Prüft ob eine neue Version auf dem Update-Server verfügbar ist.
Update-Server: https://datenmonster.com/updates/latest.json
"""
from fastapi import APIRouter, Depends
from app.api.auth import get_current_user
from app.models.user import User
import os, subprocess

router = APIRouter(prefix="/api/update", tags=["update"])

UPDATE_URL    = "https://datenmonster.com/updates/latest.json"
ZIP_URL       = "https://datenmonster.com/install/datenmonster.zip"
VERSION_FILE  = os.path.join(os.path.dirname(__file__), "../../VERSION")


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
        changelog      = data.get("changelog", "")
        released       = data.get("released", "")
        update_available = _parse_version(remote_version) > _parse_version(local_version)
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
    """
    Aktualisiert Datenmonster:
    1. Neue ZIP von datenmonster.com herunterladen
    2. Dateien entpacken (ohne .env und uploads)
    3. Docker Container neu bauen und starten
    """
    if not getattr(user, "is_admin", False):
        from fastapi import HTTPException
        raise HTTPException(403, "Nur Administratoren können Updates installieren")

    import tempfile, zipfile, shutil

    try:
        # Projektverzeichnis: zwei Ebenen über api/
        project_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../../..")
        )

        # 1. ZIP herunterladen
        import httpx
        tmp_zip = os.path.join(tempfile.gettempdir(), "datenmonster_update.zip")
        with httpx.stream("GET", ZIP_URL, timeout=60, follow_redirects=True) as r:
            r.raise_for_status()
            with open(tmp_zip, "wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)

        # 2. ZIP entpacken – .env und uploads NICHT überschreiben
        protected = {".env", ".env.example", ".admin_password", "uploads", "data"}
        tmp_extract = os.path.join(tempfile.gettempdir(), "datenmonster_update_extract")
        if os.path.exists(tmp_extract):
            shutil.rmtree(tmp_extract)

        with zipfile.ZipFile(tmp_zip, "r") as zf:
            zf.extractall(tmp_extract)

        # Prüfen ob ZIP Unterordner hat
        entries = os.listdir(tmp_extract)
        if len(entries) == 1 and os.path.isdir(os.path.join(tmp_extract, entries[0])):
            src_dir = os.path.join(tmp_extract, entries[0])
        else:
            src_dir = tmp_extract

        # Dateien kopieren (geschützte Dateien überspringen)
        for item in os.listdir(src_dir):
            if item in protected:
                continue
            src  = os.path.join(src_dir, item)
            dest = os.path.join(project_dir, item)
            if os.path.isdir(src):
                if os.path.exists(dest):
                    shutil.rmtree(dest)
                shutil.copytree(src, dest)
            else:
                shutil.copy2(src, dest)

        # Aufräumen
        os.remove(tmp_zip)
        shutil.rmtree(tmp_extract)

        # 3. Docker Container neu bauen
        compose_result = subprocess.run(
            ["docker", "compose", "up", "-d", "--build"],
            cwd=project_dir,
            capture_output=True, text=True, timeout=300
        )
        compose_output = compose_result.stdout + compose_result.stderr

        return {
            "ok": True,
            "message": "Update erfolgreich – Container werden neu gestartet",
            "compose_output": compose_output[:500],
        }

    except Exception as e:
        import traceback
        return {
            "ok": False,
            "error": str(e)[:300],
            "traceback": traceback.format_exc()[:500],
        }
