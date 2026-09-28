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

print()
print("FEHLER: " + ", ".join(FEHLER) if FEHLER else "Alles grün.")
sys.exit(1 if FEHLER else 0)
