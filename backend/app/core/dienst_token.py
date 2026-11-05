"""Gemeinsamer Schlüssel zwischen Backend, Updater und Plugin-Manager.

Updater (:9000) und Plugin-Manager (:9001) sind nur im Docker-Netz erreichbar –
dort hängen aber auch Ollama, Redis und jedes Dienst-Plugin (fremde Images).
Ohne Schlüssel hätte jedes davon Updates auslösen oder Container starten können.

Der Wert steht in der .env (DIENST_TOKEN); der Updater ergänzt ihn bei
Bestandsinstallationen selbst. Leer = Prüfung aus (Übergang/Entwicklung).
"""
import os

DIENST_TOKEN = os.getenv("DIENST_TOKEN", "").strip()
HEADER = "X-Dienst-Token"


def dienst_header() -> dict:
    return {HEADER: DIENST_TOKEN} if DIENST_TOKEN else {}
