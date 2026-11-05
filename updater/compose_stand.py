"""Compose-Datei und .env beim Kunden auf den Stand des Images bringen.

Der Updater tauscht nur Images. Ohne diesen Abgleich erreichen Änderungen an
docker-compose.yml und .env die Bestandsinstallationen nie (Beispiel: fester
hostname für die Lizenz seit 05.07.).

Reine Funktionen ohne Docker, damit sie sich testen lassen. Wird auch in der CI
als Skript aufgerufen, um die Liste der veröffentlichten Stände zu erzeugen:

    git show <commit>:docker-compose.yml | python3 updater/compose_stand.py
"""
import hashlib
import re
import secrets
import sys

# Ports dürfen beim Kunden abweichen (install.sh hat sie früher per sed in die
# Datei geschrieben, manche stellen sie von Hand um). Für den Vergleich zählt
# jede Schreibweise der Frontend-/Backend-Portzeile gleich; der tatsächliche
# Port wird vor dem Ersetzen in die .env übernommen.
_PORT_MUSTER = [
    (re.compile(r'"[^"\n]*:80"'), '"PORT:80"'),
    (re.compile(r'"[^"\n]*:8000"'), '"PORT:8000"'),
]

# Dienst → (Container-Port, Variable in .env)
PORT_VARIABLEN = {
    "frontend": (80, "FRONTEND_PORT"),
    "backend": (8000, "BACKEND_PORT"),
}

# Variablen, die jede Installation braucht. Fehlt eine, wird sie mit dem
# erzeugten Wert ergänzt. Vorhandene Werte werden nie verändert.
ENV_PFLICHT: dict = {
    # "UPDATER_TOKEN": lambda: secrets.token_urlsafe(32),
}


def normalisieren(text: str) -> str:
    text = text.replace("\r\n", "\n")
    for muster, ersatz in _PORT_MUSTER:
        text = muster.sub(ersatz, text)
    return text.strip() + "\n"


def fingerabdruck(text: str) -> str:
    return hashlib.sha256(normalisieren(text).encode("utf-8")).hexdigest()


def bekannte_staende(text: str) -> set:
    return {z.strip() for z in text.splitlines() if z.strip() and not z.startswith("#")}


def env_lesen(text: str) -> dict:
    werte = {}
    for zeile in text.splitlines():
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#") or "=" not in zeile:
            continue
        k, v = zeile.split("=", 1)
        werte[k.strip()] = v.strip()
    return werte


def env_ergaenzen(text: str, neu: dict) -> tuple[str, list]:
    """Hängt fehlende Variablen an. Gibt (neuer Text, Liste der ergänzten Namen)."""
    vorhanden = env_lesen(text)
    zeilen = [f"{k}={v}" for k, v in neu.items() if k not in vorhanden]
    if not zeilen:
        return text, []
    if text and not text.endswith("\n"):
        text += "\n"
    text += "\n# Ergänzt vom Updater\n" + "\n".join(zeilen) + "\n"
    return text, [k for k in neu if k not in vorhanden]


def env_setzen(text: str, werte: dict) -> str:
    """Setzt Variablen: vorhandene Zeile ersetzen, sonst anhängen."""
    offen = dict(werte)
    zeilen = text.splitlines()
    for i, zeile in enumerate(zeilen):
        k = zeile.split("=", 1)[0].strip()
        if "=" in zeile and not zeile.lstrip().startswith("#") and k in offen:
            zeilen[i] = f"{k}={offen.pop(k)}"
    neu = "\n".join(zeilen) + ("\n" if zeilen else "")
    if offen:
        neu, _ = env_ergaenzen(neu, offen)
    return neu


def veroeffentlichte_ports(config: dict) -> dict:
    """Aus `docker compose config --format json`: Dienst → Host-Port des Hauptports."""
    ports = {}
    for dienst, (ziel, _) in PORT_VARIABLEN.items():
        for p in (config.get("services", {}).get(dienst, {}) or {}).get("ports", []) or []:
            if isinstance(p, dict) and int(p.get("target", 0)) == ziel and p.get("published"):
                ports[dienst] = str(p["published"])
    return ports


def port_variablen(alt: dict, neu: dict) -> dict:
    """Welche .env-Variablen gesetzt werden müssen, damit die Ports gleich bleiben."""
    return {
        PORT_VARIABLEN[d][1]: port
        for d, port in alt.items()
        # nur wenn der neue Stand den Port noch veröffentlicht
        if d in PORT_VARIABLEN and d in neu and neu[d] != port
    }


def pflicht_variablen() -> dict:
    return {k: erzeuge() for k, erzeuge in ENV_PFLICHT.items()}


if __name__ == "__main__":
    print(fingerabdruck(sys.stdin.read()))
