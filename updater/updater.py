import subprocess, os, logging, json, threading, re, time
import requests
import docker as docker_sdk

from flask import Flask, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

COMPOSE_FILE    = os.getenv("COMPOSE_FILE", "/project/docker-compose.yml")
COMPOSE_PROJECT = os.getenv("COMPOSE_PROJECT_NAME", "datenmonster")
GITHUB_REPO     = os.getenv("GITHUB_REPO", "choldermann/datenmonster")
GITHUB_TOKEN    = os.getenv("GITHUB_TOKEN", "")
REGISTRY        = "ghcr.io"
OWNER           = GITHUB_REPO.split("/")[0]
REF_IMAGE       = f"{REGISTRY}/{OWNER}/datenmonster-backend"
REF_CONTAINER   = "datenmonster-backend"

STATUS_FILE = os.getenv("UPDATE_STATUS_FILE", "/project/data/update-status.json")
_update_status = {"step": None, "msg": "", "detail": "", "done": False, "error": False, "log": []}


def _log(msg: str):
    logger.info(msg)
    entry = f"[{time.strftime('%H:%M:%S')}] {msg}"
    _update_status.setdefault("log", []).append(entry)
    _update_status["log"] = _update_status["log"][-60:]
    _write_status()


def _write_status():
    try:
        os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(_update_status, f)
    except Exception as exc:
        logger.warning("Status-Datei nicht schreibbar: %s", exc)


def _read_status() -> dict:
    try:
        with open(STATUS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return _update_status


def _dc(*args):
    return ["docker", "compose", "-p", COMPOSE_PROJECT, "-f", COMPOSE_FILE] + list(args)


def _safe_run(cmd):
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return r.returncode, r.stdout.decode("utf-8", errors="replace").strip()
    except Exception as exc:
        return -1, str(exc)


def _anon_token(repo_path: str) -> str:
    r = requests.get(
        f"https://{REGISTRY}/token",
        params={"service": REGISTRY, "scope": f"repository:{repo_path}:pull"},
        timeout=10,
    )
    return r.json().get("token", "")


def _registry_labels(image: str, tag: str = "latest") -> dict:
    repo_path = image.removeprefix(f"{REGISTRY}/")
    token = _anon_token(repo_path)
    h = {
        "Authorization": f"Bearer {token}",
        "Accept": (
            "application/vnd.oci.image.index.v1+json,"
            "application/vnd.oci.image.manifest.v1+json,"
            "application/vnd.docker.distribution.manifest.v2+json,"
            "application/vnd.docker.distribution.manifest.list.v2+json"
        ),
    }
    manifest = requests.get(
        f"https://{REGISTRY}/v2/{repo_path}/manifests/{tag}", headers=h, timeout=10
    ).json()

    if "manifests" in manifest:
        platforms = manifest["manifests"]
        chosen = next(
            (m for m in platforms if (m.get("platform") or {}).get("os") != "unknown"),
            platforms[0],
        )
        sub = requests.get(
            f"https://{REGISTRY}/v2/{repo_path}/manifests/{chosen['digest']}",
            headers={**h, "Accept": "application/vnd.oci.image.manifest.v1+json,application/vnd.docker.distribution.manifest.v2+json"},
            timeout=10,
        ).json()
        manifest = sub

    digest = (manifest.get("config") or {}).get("digest", "")
    if not digest:
        return {}
    config = requests.get(
        f"https://{REGISTRY}/v2/{repo_path}/blobs/{digest}", headers=h, timeout=10
    ).json()
    return (config.get("config") or {}).get("Labels") or {}


def _local_labels(container: str) -> dict:
    try:
        raw = subprocess.check_output(
            ["docker", "inspect", "--format", "{{json .Config.Labels}}", container],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        return json.loads(raw) or {}
    except Exception:
        return {}


def _gh_headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


@app.get("/version")
def version():
    try:
        cur      = _local_labels(REF_CONTAINER)
        cur_sha  = (cur.get("org.opencontainers.image.revision") or "")[:7]
        cur_msg  = cur.get("git.commit.message", "")
        cur_date = (cur.get("org.opencontainers.image.created") or "")[:10]

        try:
            lat        = _registry_labels(REF_IMAGE, "latest")
            lat_sha    = (lat.get("org.opencontainers.image.revision") or "")[:7]
            lat_msg    = lat.get("git.commit.message", "")
            lat_date   = (lat.get("org.opencontainers.image.created") or "")[:10]
            up_to_date = bool(cur_sha and cur_sha == lat_sha)
        except Exception:
            lat_sha, lat_msg, lat_date = cur_sha, cur_msg, cur_date
            up_to_date = True

        behind = 0
        if not up_to_date and cur_sha and lat_sha:
            try:
                data = requests.get(
                    f"https://api.github.com/repos/{GITHUB_REPO}/compare/{cur_sha}...{lat_sha}",
                    headers=_gh_headers(), timeout=10,
                ).json()
                behind = data.get("ahead_by", 1)
            except Exception:
                behind = 1

        return jsonify({
            "current":         cur_sha  or "—",
            "current_message": cur_msg,
            "current_date":    cur_date,
            "latest":          lat_sha  or "—",
            "latest_message":  lat_msg,
            "latest_date":     lat_date,
            "up_to_date":      up_to_date,
            "behind":          behind,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/changelog")
def changelog():
    try:
        cur_sha = (_local_labels(REF_CONTAINER).get("org.opencontainers.image.revision") or "")[:7]
        lat_sha = (_registry_labels(REF_IMAGE, "latest").get("org.opencontainers.image.revision") or "")[:7]

        if not cur_sha or not lat_sha or cur_sha == lat_sha:
            return jsonify([])

        data = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/compare/{cur_sha}...{lat_sha}",
            headers=_gh_headers(), timeout=10,
        ).json()
        commits = data.get("commits", [])
        return jsonify([{
            "hash":    c["sha"][:7],
            "message": c["commit"]["message"].split("\n")[0],
            "date":    c["commit"]["committer"]["date"][:10],
        } for c in reversed(commits)])
    except Exception:
        return jsonify([])


def _fmt_bytes(b: int) -> str:
    if b >= 1_000_000_000:
        return f"{b / 1_000_000_000:.1f} GB"
    if b >= 1_000_000:
        return f"{b / 1_000_000:.0f} MB"
    return f"{b / 1_000:.0f} KB"


def _pull_with_progress(images: list) -> str:
    """Pulled Images via Docker SDK mit Layer-Fortschritt. Gibt '' zurück bei Erfolg, sonst Fehlermeldung."""
    try:
        client = docker_sdk.DockerClient(base_url="unix:///var/run/docker.sock")
    except Exception as e:
        return f"Docker-Socket nicht erreichbar: {e}"

    total = len(images)
    for idx, image in enumerate(images):
        short = image.split("/")[-1].replace(":latest", "")
        _log(f"Pull {idx+1}/{total}: {image}")
        layers: dict = {}  # layer_id → {current, total}
        try:
            for event in client.api.pull(image, stream=True, decode=True):
                detail = event.get("progressDetail") or {}
                layer_id = event.get("id", "")
                cur = detail.get("current", 0)
                tot = detail.get("total", 0)
                if layer_id and tot:
                    layers[layer_id] = {"current": cur, "total": tot}

                all_total   = sum(l["total"]   for l in layers.values())
                all_current = sum(l["current"] for l in layers.values())

                if all_total:
                    pct = int(all_current / all_total * 100)
                    msg = (
                        f"Image {idx+1}/{total}: {short} — "
                        f"{_fmt_bytes(all_current)} / {_fmt_bytes(all_total)} ({pct} %)"
                    )
                else:
                    msg = f"Image {idx+1}/{total}: {short} — {event.get('status', '')}"

                _update_status.update(step="pull", msg=msg)
                _write_status()

        except Exception as e:
            return f"Fehler beim Pull von {image}: {e}"

    return ""


def _run_update():
    global _update_status
    services        = ["backend", "frontend", "plugin-manager"]
    container_names = ["datenmonster-backend", "datenmonster-frontend", "datenmonster-plugin-manager"]

    def s(step, msg, detail=""):
        _update_status.update(step=step, msg=msg, detail=detail, done=False, error=False)
        _write_status()
        logger.info("%s: %s", step, msg)

    try:
        # Disk-Check und Prune
        _log("Starte docker system prune -af …")
        rc_prune, out_prune = _safe_run(["docker", "system", "prune", "-af"])
        _log(f"Prune RC={rc_prune}: {out_prune[:400]}")

        rc0, df0 = _safe_run(["df", "-BM", "--output=avail", "/"])
        try:
            free_mb = int([l for l in df0.splitlines() if l.strip().rstrip("M").isdigit()][0].strip().rstrip("M"))
        except Exception:
            free_mb = 9999
        if free_mb < 200:
            _update_status.update(step="error", msg=f"Nicht genug Speicherplatz ({free_mb} MB frei). Bitte manuell prüfen.", error=True)
            _write_status()
            return

        s("pull", "Lade neue Images von GitHub…")
        pull_images = [
            f"{REGISTRY}/{OWNER}/datenmonster-backend:latest",
            f"{REGISTRY}/{OWNER}/datenmonster-frontend:latest",
            f"{REGISTRY}/{OWNER}/datenmonster-plugin-manager:latest",
            f"{REGISTRY}/{OWNER}/datenmonster-updater:latest",
        ]
        pull_error = _pull_with_progress(pull_images)
        if pull_error:
            _update_status.update(step="error", msg="Pull fehlgeschlagen", detail=pull_error, error=True)
            _write_status()
            return
        s("pull_ok", "Images geladen")

        s("rm", "Stoppe und entferne alte Container…")
        for name in container_names:
            _safe_run(["docker", "rm", "-f", name])
        s("rm_ok", "Alte Container entfernt")

        s("up", "Starte neue Container…")
        for svc in services:
            rc2, o2 = _safe_run(_dc("up", "-d", "--no-deps", svc))
            if rc2 != 0:
                _update_status.update(step="error", msg=f"Fehler bei {svc}", detail=o2, error=True)
                _write_status()
                return
        s("up_ok", "Backend · Frontend · Plugin-Manager gestartet")

        s("self", "Starte Updater-Neustart…")
        restarter_cmd = (
            f"sleep 6 && docker compose"
            f" -p {COMPOSE_PROJECT}"
            f" -f {COMPOSE_FILE}"
            f" up -d --no-deps --force-recreate updater"
        )
        rc_r, out_r = _safe_run(["docker", "run", "--rm", "-d",
            "-v", "/var/run/docker.sock:/var/run/docker.sock",
            "-v", f"{os.path.dirname(COMPOSE_FILE)}:{os.path.dirname(COMPOSE_FILE)}",
            "--entrypoint", "sh",
            f"ghcr.io/{OWNER}/datenmonster-updater:latest",
            "-c", restarter_cmd])
        _log(f"Restarter gestartet — RC={rc_r} {out_r[:120]}")

        _update_status.update(step="done", msg="Update abgeschlossen", done=True, error=False)
        _write_status()
        _log("done — Update abgeschlossen")

    except Exception as exc:
        _update_status.update(step="error", msg=str(exc), error=True)
        _write_status()


@app.post("/update/start")
def update_start():
    global _update_status
    cur = _read_status()
    if cur.get("step") and not cur.get("done") and not cur.get("error"):
        return jsonify({"ok": False, "error": "Update läuft bereits"})
    _update_status = {"step": None, "msg": "", "detail": "", "done": False, "error": False, "log": []}
    _write_status()
    threading.Thread(target=_run_update, daemon=True).start()
    return jsonify({"ok": True})


@app.get("/update/status")
def update_status_endpoint():
    return jsonify(_read_status())


@app.get("/health")
def health():
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9000, threaded=True)
