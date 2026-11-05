import subprocess, os, logging, json, threading, re, time, shlex, shutil
import requests
import docker as docker_sdk

from flask import Flask, jsonify

import compose_stand as stand

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

PROJECT_DIR     = os.path.dirname(COMPOSE_FILE)
ENV_FILE        = os.path.join(PROJECT_DIR, ".env")
STAND_DIR       = os.getenv("COMPOSE_STAND_DIR", "/app/compose")
SELF_CONTAINER  = "datenmonster-updater"
ABGLEICH_FILE   = os.path.join(PROJECT_DIR, "data", "compose-abgleich.json")

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


_host_dir_cache = None


def _host_dir() -> str:
    """Installationsordner auf dem Host = Quelle unseres /project-Mounts.

    docker compose läuft hier im Container. Relative Pfade wie ./backups löst es
    gegen den Ordner der Compose-Datei auf – also /project – und reicht das als
    Host-Pfad an Docker weiter. Auf dem Host gibt es /project aber nicht: die
    Sicherungen landeten nach jedem Update im falschen Ordner, und der Updater
    konnte sich nie selbst erneuern."""
    global _host_dir_cache
    if _host_dir_cache:
        return _host_dir_cache
    try:
        raw = subprocess.check_output(
            ["docker", "inspect", "--format", "{{json .Mounts}}", SELF_CONTAINER],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        for m in json.loads(raw) or []:
            if m.get("Destination") == PROJECT_DIR and m.get("Source"):
                _host_dir_cache = m["Source"]
                return _host_dir_cache
    except Exception as exc:
        logger.warning("Host-Pfad nicht ermittelbar: %s", exc)
    return PROJECT_DIR


def _dc(*args, datei: str = COMPOSE_FILE):
    cmd = ["docker", "compose", "-p", COMPOSE_PROJECT, "-f", datei]
    host = _host_dir()
    if host != PROJECT_DIR:
        cmd += ["--project-directory", host]
        if os.path.exists(ENV_FILE):
            cmd += ["--env-file", ENV_FILE]
    return cmd + list(args)


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
        rc_r, out_r = _updater_neu_starten()
        _log(f"Restarter gestartet — RC={rc_r} {out_r[:120]}")

        _update_status.update(step="done", msg="Update abgeschlossen", done=True, error=False)
        _write_status()
        _log("done — Update abgeschlossen")

    except Exception as exc:
        _update_status.update(step="error", msg=str(exc), error=True)
        _write_status()


def _updater_neu_starten():
    """Erneuert den Updater-Container über einen kurzlebigen Helfer – aus dem
    eigenen Container heraus geht das nicht, er würde sich mittendrin beenden."""
    befehl = " ".join(shlex.quote(x) for x in
                      _dc("up", "-d", "--no-deps", "--force-recreate", "updater"))
    return _safe_run(["docker", "run", "--rm", "-d",
        "-v", "/var/run/docker.sock:/var/run/docker.sock",
        "-v", f"{_host_dir()}:{PROJECT_DIR}",
        "--entrypoint", "sh",
        f"ghcr.io/{OWNER}/datenmonster-updater:latest",
        "-c", f"sleep 6 && {befehl}"])


def _config(datei: str):
    r = subprocess.run(_dc("config", "--format", "json", datei=datei),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        raise RuntimeError(f"docker compose config: {r.stderr.decode(errors='replace')[-400:]}")
    return json.loads(r.stdout.decode("utf-8"))


def _lesen(pfad: str) -> str:
    with open(pfad, encoding="utf-8") as f:
        return f.read()


def _schreiben(pfad: str, text: str):
    """Schreibt atomar und behält Rechte und Besitzer – der Updater läuft als root,
    die Installation gehört oft einem normalen Benutzer."""
    vorlage = pfad if os.path.exists(pfad) else COMPOSE_FILE
    st = os.stat(vorlage) if os.path.exists(vorlage) else None
    tmp = pfad + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    if st is not None:
        os.chmod(tmp, st.st_mode & 0o777)
        try:
            os.chown(tmp, st.st_uid, st.st_gid)
        except OSError:
            pass
    os.replace(tmp, pfad)


def _besitzer_wie(vorlage: str, pfad: str):
    try:
        st = os.stat(vorlage)
        os.chown(pfad, st.st_uid, st.st_gid)
    except OSError:
        pass


def _compose_abgleichen() -> dict:
    """Bringt docker-compose.yml und .env auf den Stand dieses Images.

    Ersetzt wird nur eine Datei, die einem veröffentlichten Stand entspricht.
    Eine von Hand angepasste bleibt stehen; der neue Stand kommt als .neu daneben.
    Ports bleiben erhalten (install.sh hat sie früher direkt in die Datei
    geschrieben) – sie wandern dafür in die .env."""
    neu_pfad = os.path.join(STAND_DIR, "docker-compose.yml")
    liste_pfad = os.path.join(STAND_DIR, "bekannte_staende.txt")
    if not (os.path.exists(neu_pfad) and os.path.exists(liste_pfad) and os.path.exists(COMPOSE_FILE)):
        return {"ergebnis": "aus", "geaendert": False}

    neu = _lesen(neu_pfad)
    alt = _lesen(COMPOSE_FILE)
    env_alt = _lesen(ENV_FILE) if os.path.exists(ENV_FILE) else ""
    env_neu, ergaenzt = stand.env_ergaenzen(env_alt, stand.pflicht_variablen())
    ergebnis = {"ergebnis": "aktuell", "geaendert": False, "env_ergaenzt": ergaenzt}

    if alt.replace("\r\n", "\n") != neu:
        if stand.fingerabdruck(alt) not in stand.bekannte_staende(_lesen(liste_pfad)):
            _schreiben(COMPOSE_FILE + ".neu", neu)
            ergebnis.update(ergebnis="angepasst",
                            hinweis="docker-compose.yml wurde von Hand geändert und bleibt stehen. "
                                    "Der neue Stand liegt als docker-compose.yml.neu daneben.")
        else:
            tmp = os.path.join(PROJECT_DIR, ".docker-compose.pruefen.yml")
            _schreiben(tmp, neu)
            try:
                ports = stand.port_variablen(
                    stand.veroeffentlichte_ports(_config(COMPOSE_FILE)),
                    stand.veroeffentlichte_ports(_config(tmp)),
                )
            finally:
                os.remove(tmp)
            env_neu = stand.env_setzen(env_neu, ports)

            sicherung = f"{COMPOSE_FILE}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
            shutil.copy2(COMPOSE_FILE, sicherung)
            _besitzer_wie(COMPOSE_FILE, sicherung)
            _schreiben(COMPOSE_FILE, neu)
            ergebnis.update(ergebnis="ersetzt", geaendert=True,
                            sicherung=os.path.basename(sicherung), ports=ports)

    if env_neu != env_alt:
        if env_alt:
            env_sicherung = f"{ENV_FILE}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
            shutil.copy2(ENV_FILE, env_sicherung)
            _besitzer_wie(ENV_FILE, env_sicherung)
        _schreiben(ENV_FILE, env_neu)
        os.chmod(ENV_FILE, 0o600)
        ergebnis["geaendert"] = True

    if ergebnis["geaendert"]:
        try:
            _config(COMPOSE_FILE)
        except Exception as exc:
            # Neuer Stand lässt sich nicht lesen → alten zurück, nichts neu starten
            if ergebnis.get("sicherung"):
                shutil.copy2(os.path.join(PROJECT_DIR, ergebnis["sicherung"]), COMPOSE_FILE)
            ergebnis.update(ergebnis="fehler", geaendert=False, hinweis=str(exc)[:400])
    return ergebnis


def _ausgabe(cmd) -> tuple[int, str, str]:
    """Wie _safe_run, aber stdout und stderr getrennt – Warnungen von compose
    ("variable is not set" …) dürfen nicht in Listen landen, die wir auswerten."""
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return (r.returncode, r.stdout.decode("utf-8", errors="replace"),
                r.stderr.decode("utf-8", errors="replace"))
    except Exception as exc:
        return -1, "", str(exc)


def _veraltete_dienste() -> tuple[list, str]:
    """Dienste, deren laufender Container nicht zur Compose-Datei passt.

    Vergleicht den config-hash, den compose an jeden Container schreibt, mit
    dem, was die aktuelle Datei ergibt. Fehlender Container zählt auch."""
    rc, out, err = _ausgabe(_dc("config", "--hash", "*"))
    if rc != 0:
        return [], f"config --hash: {err[-300:]}"
    soll = {}
    for zeile in out.splitlines():
        teile = zeile.split()
        if len(teile) == 2:
            soll[teile[0]] = teile[1]
    rc, out, err = _ausgabe([
        "docker", "ps", "-a", "--filter", f"label=com.docker.compose.project={COMPOSE_PROJECT}",
        "--format", '{{.Label "com.docker.compose.service"}} {{.Label "com.docker.compose.config-hash"}}',
    ])
    ist = {}
    for zeile in out.splitlines():
        teile = zeile.split()
        if len(teile) == 2:
            ist[teile[0]] = teile[1]
    return [d for d, h in soll.items() if d != "updater" and ist.get(d) != h], ""


def _beim_start():
    """Compose-Stand nachziehen und Container angleichen.

    Läuft bei jedem Start: ersetzt ggf. die Datei und erneuert danach jeden
    Dienst, dessen Container nicht zur Datei passt. Hängt also nicht an einem
    einzigen Versuch – fällt einer aus, holt der nächste Start ihn nach. Kein
    Kreislauf: passt alles, passiert nichts."""
    time.sleep(5)
    try:
        erg = _compose_abgleichen()
    except Exception as exc:
        erg = {"ergebnis": "fehler", "geaendert": False, "hinweis": str(exc)[:400]}
    erg["zeit"] = time.strftime("%Y-%m-%d %H:%M:%S")
    erg["host_dir"] = _host_dir()

    if erg.get("ergebnis") not in ("aus", "fehler"):
        dienste, fehler = _veraltete_dienste()
        if fehler:
            erg["hinweis"] = fehler
        if dienste:
            rc, out, err = _ausgabe(_dc("up", "-d", "--pull", "missing", *dienste))
            erg["neu_erstellt"] = dienste if rc == 0 else []
            if rc != 0:
                erg["hinweis"] = f"docker compose up: {err[-400:]}"
        if erg.get("geaendert"):
            # eigene Definition kann sich geändert haben (Token, Mounts …)
            rc, _ = _updater_neu_starten()
            erg["updater_neustart"] = rc == 0
    logger.info("Compose-Abgleich: %s", erg)

    # Verlauf statt Überschreiben: der Lauf nach dem Selbst-Neustart soll den
    # davor nicht verdecken.
    verlauf = []
    try:
        with open(ABGLEICH_FILE, encoding="utf-8") as f:
            alt = json.load(f)
        verlauf = (alt.get("verlauf") or [])[-9:] + [{k: v for k, v in alt.items() if k != "verlauf"}]
    except Exception:
        pass
    erg["verlauf"] = verlauf
    try:
        os.makedirs(os.path.dirname(ABGLEICH_FILE), exist_ok=True)
        with open(ABGLEICH_FILE, "w", encoding="utf-8") as f:
            json.dump(erg, f, ensure_ascii=False, indent=1)
    except Exception as exc:
        logger.warning("Abgleich-Status nicht schreibbar: %s", exc)


@app.get("/compose/status")
def compose_status():
    try:
        with open(ABGLEICH_FILE, encoding="utf-8") as f:
            return jsonify(json.load(f))
    except Exception:
        return jsonify({"ergebnis": "unbekannt"})


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


def _env_absichern():
    """Bestehende Installationen: .env (SECRET_KEY, Admin-Passwort) war für alle
    Benutzer des Servers lesbar. Neue Installationen setzt install.sh selbst."""
    pfad = os.path.join(os.path.dirname(COMPOSE_FILE), ".env")
    try:
        if os.path.exists(pfad) and os.stat(pfad).st_mode & 0o077:
            os.chmod(pfad, 0o600)
            logger.info(".env auf 600 gesetzt")
    except OSError as e:
        logger.warning(f".env-Rechte nicht gesetzt: {e}")


if __name__ == "__main__":
    _env_absichern()
    threading.Thread(target=_beim_start, daemon=True).start()
    app.run(host="0.0.0.0", port=9000, threaded=True)
