"""Lauf im Updater-Image:  DIENST_TOKEN=probe python test_dienst_token.py"""
import os
import sys

os.environ.setdefault("DIENST_TOKEN", "probe")
import updater  # noqa: E402

c = updater.app.test_client()
fehler = []


def pruefe(name, ok):
    print(("  OK   " if ok else "  FAIL ") + name)
    if not ok:
        fehler.append(name)


pruefe("/health ohne Schlüssel frei", c.get("/health").status_code == 200)
for methode, pfad in [("post", "/update/start"), ("get", "/version"), ("get", "/docker/containers"),
                      ("post", "/docker/x/restart"), ("get", "/docker/x/logs"), ("get", "/compose/status")]:
    pruefe(f"{methode.upper()} {pfad} ohne Schlüssel → 401", getattr(c, methode)(pfad).status_code == 401)
pruefe("falscher Schlüssel → 401",
       c.post("/update/start", headers={"X-Dienst-Token": "falsch"}).status_code == 401)
pruefe("richtiger Schlüssel → durch",
       c.get("/compose/status", headers={"X-Dienst-Token": "probe"}).status_code == 200)
pruefe("unbekannte Docker-Aktion abgelehnt",
       c.post("/docker/x/kill", headers={"X-Dienst-Token": "probe"}).status_code == 400)
print("FEHLER: " + ", ".join(fehler) if fehler else "Alles grün.")
sys.exit(1 if fehler else 0)
