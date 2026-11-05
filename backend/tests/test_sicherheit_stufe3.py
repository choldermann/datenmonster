"""
Sicherheitsreview 2, Stufe 3 (28.09.2026): Infrastruktur, risikolose Teile.

- Login-Sperre zählt die IP des Browsers, nicht die des nginx davor – aber
  X-Real-IP wird nur geglaubt, wenn die Anfrage wirklich vom nginx kommt.
- Keine öffentliche API-Doku (/docs, /redoc, /openapi.json).

Lauf:  docker compose exec -T backend python tests/test_sicherheit_stufe3.py
"""
import socket
import sys
from types import SimpleNamespace
sys.path.insert(0, "/app")

from fastapi.testclient import TestClient  # noqa: E402

from app.auth import _client_ip  # noqa: E402
from app.main import app  # noqa: E402

FEHLER = []


def pruefe(name, bedingung, extra=""):
    print(("  OK   " if bedingung else "  FAIL ") + name + (f"  [{extra}]" if extra and not bedingung else ""))
    if not bedingung:
        FEHLER.append(name)


def anfrage(absender, real_ip=None):
    kopf = {"x-real-ip": real_ip} if real_ip else {}
    return SimpleNamespace(client=SimpleNamespace(host=absender), headers=kopf)


print("Login-Sperre: Client-IP")
nginx = socket.getaddrinfo("frontend", None)[0][4][0]
pruefe("über nginx → IP des Browsers", _client_ip(anfrage(nginx, "203.0.113.7")) == "203.0.113.7")
pruefe("über nginx ohne Kopfzeile → nginx-IP", _client_ip(anfrage(nginx)) == nginx)
pruefe("direkt mit erfundener Kopfzeile → echte Absender-IP",
       _client_ip(anfrage("198.51.100.9", "10.0.0.1")) == "198.51.100.9")

print("API-Doku abgeschaltet")
client = TestClient(app)
for pfad in ("/docs", "/redoc", "/openapi.json"):
    pruefe(f"{pfad} → 404", client.get(pfad).status_code == 404)

print("Teil 2: Docker nur noch über den Updater, mit Schlüssel")
import os  # noqa: E402
import httpx  # noqa: E402
from app.core import dienst_token  # noqa: E402
from app.api import monitoring  # noqa: E402

dienst_token.DIENST_TOKEN = "probe-schluessel"
pruefe("Kopfzeile trägt den Schlüssel",
       dienst_token.dienst_header() == {"X-Dienst-Token": "probe-schluessel"})
dienst_token.DIENST_TOKEN = ""
pruefe("ohne Schlüssel keine Kopfzeile", dienst_token.dienst_header() == {})
dienst_token.DIENST_TOKEN = "probe-schluessel"

gesehen = {}


class _Antwort:
    def __init__(self, daten):
        self._d = daten

    def json(self):
        return self._d


def _falsch_request(methode, url, headers=None, **kw):
    gesehen.update(methode=methode, url=url, headers=headers or {})
    if url.endswith("/docker/fremd/stop"):
        return _Antwort({"ok": False, "error": "Dieser Container gehört nicht zu Datenmonster"})
    return _Antwort({"containers": [{"name": "datenmonster-backend"}]})


echt = httpx.request
httpx.request = _falsch_request
os.environ["UPDATER_URL"] = "http://updater:9000"
ADMIN = SimpleNamespace(is_admin=True, is_portal_only=False, id=1)
try:
    erg = monitoring.get_docker_containers(user=ADMIN)
    pruefe("Liste kommt vom Updater", gesehen.get("url") == "http://updater:9000/docker/containers"
           and erg["containers"][0]["name"] == "datenmonster-backend")
    pruefe("Anfrage an den Updater trägt den Schlüssel",
           gesehen["headers"].get("X-Dienst-Token") == "probe-schluessel")
    try:
        monitoring.docker_stop("fremd", user=ADMIN)
        pruefe("fremder Container → 403", False)
    except Exception as e:
        pruefe("fremder Container → 403", getattr(e, "status_code", None) == 403)
    os.environ["UPDATER_URL"] = ""
    erg = monitoring.get_docker_containers(user=ADMIN)
    pruefe("Updater aus → saubere Meldung", erg["containers"] == [] and "abgeschaltet" in erg["error"])
finally:
    httpx.request = echt

import inspect  # noqa: E402
quelle = inspect.getsource(monitoring)
pruefe("Monitoring nutzt kein Docker-SDK mehr", "docker_sdk" not in quelle and "from_env" not in quelle)

print()
print("FEHLER: " + ", ".join(FEHLER) if FEHLER else "Alles grün.")
sys.exit(1 if FEHLER else 0)
