"""
Farbschema im Benutzerkonto (users.theme, PUT /api/auth/theme).

Der teure Fehler: Portal-Benutzer bekommen beim Speichern ein 403, weil der
Endpunkt in der Portal-Freigabeliste fehlt – als Admin getestet fällt das nie auf.

Lauf:  docker compose exec -T backend python tests/test_theme_konto.py
"""
import sys
import uuid
sys.path.insert(0, "/app")

from fastapi import HTTPException  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.portal_zugriff import portal_darf  # noqa: E402
from app.core.lizenz_gate import benoetigtes_recht  # noqa: E402
from app.auth import set_theme, me, ThemeWahl  # noqa: E402
from app.models.user import User  # noqa: E402

FEHLER = []


def pruefe(name, bedingung, extra=""):
    print(("  OK   " if bedingung else "  FAIL ") + name + (f"  [{extra}]" if extra and not bedingung else ""))
    if not bedingung:
        FEHLER.append(name)


print("\n── Freigaben ─────────────────────────────────────────────────")
pruefe("Portal darf PUT /api/auth/theme", portal_darf("PUT", "/api/auth/theme"))
pruefe("Portal darf GET /api/auth/me", portal_darf("GET", "/api/auth/me"))
r = benoetigtes_recht("PUT", "/api/auth/theme")
pruefe("Lizenz verlangt nichts für PUT /api/auth/theme", r is None, f"verlangt {r}")

print("\n── Login-Antwort ─────────────────────────────────────────────")
# /api/auth/token hat response_model=Token: ein Feld, das dort fehlt, filtert
# FastAPI stillschweigend aus der Antwort – das Theme käme nach dem Login nie an.
from app.auth import Token  # noqa: E402
pruefe("Token-Modell enthält theme", "theme" in Token.model_fields)

print("\n── Speichern im Konto ────────────────────────────────────────")
db = SessionLocal()
user = User(username=f"theme-test-{uuid.uuid4().hex[:8]}", hashed_password="x", is_portal_only=True)
db.add(user)
db.commit()
db.refresh(user)
try:
    pruefe("neuer Benutzer hat kein Theme", me(user)["theme"] is None)

    set_theme(ThemeWahl(theme="amiga"), db=db, user=user)
    db.refresh(user)
    pruefe("amiga gespeichert", user.theme == "amiga", user.theme)
    pruefe("/me liefert amiga", me(user)["theme"] == "amiga")

    set_theme(ThemeWahl(theme="system"), db=db, user=user)
    db.refresh(user)
    pruefe("system gespeichert", user.theme == "system", user.theme)

    try:
        set_theme(ThemeWahl(theme="<script>"), db=db, user=user)
        pruefe("ungültiger Wert abgelehnt", False, "kein Fehler")
    except HTTPException as e:
        pruefe("ungültiger Wert abgelehnt (400)", e.status_code == 400, e.status_code)
    db.refresh(user)
    pruefe("ungültiger Wert ändert nichts", user.theme == "system", user.theme)

    set_theme(ThemeWahl(theme=""), db=db, user=user)
    db.refresh(user)
    pruefe("leer = zurück auf Standard (None)", user.theme is None, user.theme)
finally:
    # Aufräumen über die ID, nie über den Namen
    db.query(User).filter(User.id == user.id).delete()
    db.commit()
    db.close()

print()
if FEHLER:
    print(f"{len(FEHLER)} Fehler: {FEHLER}")
    sys.exit(1)
print("Alles OK")
