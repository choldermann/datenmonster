"""Einmaliger Anstoß für Bestandsinstallationen: alten Updater-Container erneuern.

Bis 11/2026 lief `docker compose` im Updater mit /project als Projektordner.
Der Selbst-Neustart band deshalb den Host-Pfad /project ein, den es beim Kunden
nicht gibt – der Updater blieb auf dem Stand der Erstinstallation hängen und mit
ihm alles, was er beim Start erledigen soll (Compose-Abgleich).

Das Image liegt nach einem Update schon lokal (der alte Updater zieht es mit).
Hier wird nur noch der Container neu erstellt, mit dem richtigen Host-Pfad.
Sobald der Updater aktuell ist, tut diese Funktion nichts mehr.
"""
import logging
import os
import shlex
import threading
import time

import httpx

logger = logging.getLogger(__name__)

UPDATER = "datenmonster-updater"
PROJECT_DIR = "/project"


def _update_laeuft(url: str) -> bool:
    try:
        st = httpx.get(f"{url}/update/status", timeout=5).json()
        return bool(st.get("step")) and not st.get("done") and not st.get("error")
    except Exception:
        return False


def _anstossen():
    url = os.getenv("UPDATER_URL", "").strip()
    if not url:
        return  # Entwicklungsrechner: Updater bewusst aus
    try:
        import docker as docker_sdk
        client = docker_sdk.from_env()
        c = client.containers.get(UPDATER)
    except Exception:
        return
    bild = (c.attrs.get("Config") or {}).get("Image") or ""
    try:
        neu = client.images.get(bild)
    except Exception:
        return
    if c.image.id == neu.id:
        return
    quelle = next((m.get("Source") for m in c.attrs.get("Mounts", [])
                   if m.get("Destination") == PROJECT_DIR), None)
    if not quelle:
        return

    # Läuft gerade das Update, das dieses Backend gestartet hat? Dann warten, sonst
    # würde der alte Updater mitten im Starten von Frontend/Plugin-Manager beendet.
    for _ in range(90):
        if not _update_laeuft(url):
            break
        time.sleep(10)
    time.sleep(15)

    projekt = (c.labels or {}).get("com.docker.compose.project", "datenmonster")
    befehl = " ".join(shlex.quote(x) for x in [
        "docker", "compose", "-p", projekt, "-f", f"{PROJECT_DIR}/docker-compose.yml",
        "--project-directory", quelle, "--env-file", f"{PROJECT_DIR}/.env",
        "up", "-d", "--no-deps", "--force-recreate", "updater",
    ])
    try:
        client.containers.run(
            bild, entrypoint="sh", command=["-c", f"sleep 3 && {befehl}"],
            volumes={"/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "rw"},
                     quelle: {"bind": PROJECT_DIR, "mode": "rw"}},
            remove=True, detach=True,
        )
        logger.info("Updater wird auf das neue Image umgestellt (Host-Ordner %s)", quelle)
    except Exception as exc:
        logger.warning("Updater-Anstoß fehlgeschlagen: %s", exc)


def updater_nachziehen():
    threading.Thread(target=_anstossen, daemon=True, name="updater-anstoss").start()
