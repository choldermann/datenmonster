"""Nur noch Weiterleitung: viele Router importieren `get_current_user` von hier.

Der aktive Auth-Router ist `app/auth.py`. Hier stand frueher eine alte Kopie mit
einem /register ohne Anmeldung – nicht eingebunden, aber eine Falle, falls sie
jemand doch einbindet.
"""
from app.core.security import get_current_user  # noqa: F401
