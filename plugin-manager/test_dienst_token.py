"""Lauf im Plugin-Manager-Image:  DIENST_TOKEN=probe python test_dienst_token.py"""
import os
import sys

os.environ.setdefault("DIENST_TOKEN", "probe")
os.environ.setdefault("REGISTRY_FILE", "/tmp/plugins.json")
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

c = TestClient(main.app)
fehler = []


def pruefe(name, ok):
    print(("  OK   " if ok else "  FAIL ") + name)
    if not ok:
        fehler.append(name)


pruefe("/health ohne Schlüssel frei", c.get("/health").status_code == 200)
pruefe("Plugin-Event ohne Schlüssel nicht abgewiesen", c.post("/plugins/x/event", json={}).status_code != 401)
for methode, pfad in [("get", "/plugins"), ("post", "/plugins/x/start"), ("post", "/plugins/x/load-image"),
                      ("delete", "/plugins/x"), ("post", "/plugins/x/proxy/fetch")]:
    pruefe(f"{methode.upper()} {pfad} ohne Schlüssel → 401", getattr(c, methode)(pfad).status_code == 401)
pruefe("/docs aus", c.get("/docs", headers={"X-Dienst-Token": "probe"}).status_code == 404)
pruefe("richtiger Schlüssel → durch", c.get("/plugins", headers={"X-Dienst-Token": "probe"}).status_code == 200)
print("FEHLER: " + ", ".join(fehler) if fehler else "Alles grün.")
sys.exit(1 if fehler else 0)
