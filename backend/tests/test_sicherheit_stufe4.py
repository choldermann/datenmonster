"""
Sicherheitsreview 2, Stufe 4 (05.11.2026): die Restpunkte.

Mail-Empfänger, CSV-Formeln, SSRF-Guard, Verschlüsselung, Vorlagen-Pipelines,
Datenpflege, API-Studio-Verlauf, Sicherungs-Archive, widerrufbare Anmeldung.
Testbenutzer/-objekte werden über ihre IDs aufgeräumt (nie über Namen).

Lauf:  docker compose exec -T backend python tests/test_sicherheit_stufe4.py
"""
import io
import os
import shutil
import socket
import sys
import tarfile
import tempfile
import uuid
import warnings
from types import SimpleNamespace
sys.path.insert(0, "/app")
warnings.filterwarnings("ignore")

from fastapi import HTTPException  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402

FEHLER = []


def pruefe(name, bedingung, extra=""):
    print(("  OK   " if bedingung else "  FAIL ") + name + (f"  [{extra}]" if extra and not bedingung else ""))
    if not bedingung:
        FEHLER.append(name)


def status(fn):
    try:
        fn()
        return 200
    except HTTPException as e:
        return e.status_code


db = SessionLocal()
ADMIN = SimpleNamespace(id=1, is_admin=True, is_portal_only=False, username="admin")
EDITOR = SimpleNamespace(id=999001, is_admin=False, is_portal_only=False, username="t4-editor")

# ── 1. Mail-Empfänger ──────────────────────────────────────────────────────
print("1. Mail nur an erlaubte Domains")
from app.core import mail_empfaenger as me  # noqa: E402
me.erlaubte_domains = lambda _db: {"firma.de", "partner.de"}
pruefe("Editor → eigene Domain", status(lambda: me.pruefe_empfaenger(db, EDITOR, "a@firma.de")) == 200)
pruefe("Editor → freigegebene Domain", status(lambda: me.pruefe_empfaenger(db, EDITOR, "b@partner.de")) == 200)
pruefe("Editor → fremde Domain = 403", status(lambda: me.pruefe_empfaenger(db, EDITOR, "x@gmail.com")) == 403)
pruefe("Subdomain-Trick = 403", status(lambda: me.pruefe_empfaenger(db, EDITOR, "x@firma.de.evil.com")) == 403)
pruefe("Admin → fremde Domain frei", status(lambda: me.pruefe_empfaenger(db, ADMIN, "x@gmail.com")) == 200)
pruefe("ungültige Adresse = 400", status(lambda: me.pruefe_empfaenger(db, EDITOR, "kaputt")) == 400)
viele = ",".join(f"p{i}@firma.de" for i in range(11))
pruefe("11 Empfänger sofort = 400", status(lambda: me.pruefe_empfaenger(db, EDITOR, viele, sofort=True)) == 400)
pruefe("bestehende Fremdadresse bleibt beim Ändern",
       status(lambda: me.pruefe_neue(db, EDITOR, "x@gmail.com, a@firma.de", "x@gmail.com")) == 200)
pruefe("neu hinzugefügte Fremdadresse = 403",
       status(lambda: me.pruefe_neue(db, EDITOR, "x@gmail.com, y@gmx.de", "x@gmail.com")) == 403)
me._verlauf.clear()
codes = [status(lambda: me.pruefe_empfaenger(db, EDITOR, "a@firma.de", sofort=True))
         for _ in range(me.MAX_MAILS_PRO_STUNDE + 1)]
pruefe("Stundengrenze = 429", codes[-1] == 429 and codes[-2] == 200)
me._verlauf.clear()

from app.api import forms  # noqa: E402
import app.services.email_service as es  # noqa: E402
gesendet = []
es.get_email_config = lambda _db: {"host": "smtp.test"}
es.send_email = lambda **kw: gesendet.append(kw)
anfrage = forms.EmailTableRequest(recipients="boese@gmail.com", rows=[{"a": "=HYPERLINK(1)"}])
pruefe("email-table: Editor an fremde Adresse = 403",
       status(lambda: forms.email_table(anfrage, db=db, user=EDITOR)) == 403 and not gesendet)
anfrage = forms.EmailTableRequest(recipients="kollege@firma.de", rows=[{"a": "=HYPERLINK(1)"}])
pruefe("email-table: an Kollegen geht raus", status(lambda: forms.email_table(anfrage, db=db, user=EDITOR)) == 200)
csv = gesendet[-1]["attachments"][0]["data"].decode("utf-8") if gesendet else ""
pruefe("email-table: CSV-Anhang ohne ausführbare Formel", "'=HYPERLINK(1)" in csv, csv[:80])
me._verlauf.clear()

# ── 2. CSV ─────────────────────────────────────────────────────────────────
print("2. CSV-Formeln")
from app.core.csv_sicher import zelle  # noqa: E402
pruefe("=, @ entschärft", zelle("=1+1") == "'=1+1" and zelle("@SUM(A1)") == "'@SUM(A1)")
pruefe("DDE mit - entschärft", zelle("-2+3*cmd|' /c calc'!A0").startswith("'"))
pruefe("-5, +49 …, '- Text' unverändert",
       zelle("-5") == "-5" and zelle("+49 711 1") == "+49 711 1" and zelle("- Sonderposten") == "- Sonderposten")
pruefe("Zahlen bleiben Zahlen", zelle(12) == 12 and zelle(None) is None)

# ── 3./4. SSRF ─────────────────────────────────────────────────────────────
print("3./4. SSRF-Guard")
from app.core import net_guard as g  # noqa: E402
import requests  # noqa: E402
g._load_policy = lambda: {"allow": [], "block": [], "allow_loopback": False}
for u in ("http://0.0.0.0:8000/", "http://[::ffff:127.0.0.1]:8000/", "http://[::ffff:169.254.169.254]/"):
    try:
        g.assert_url_allowed(u)
        pruefe(f"{u} blockiert", False)
    except g.EgressBlocked:
        pruefe(f"{u} blockiert", True)
echt = socket.getaddrinfo
zaehler = {"n": 0}


def _rebind(host, port, *a, **k):
    if host == "rebind.test":
        zaehler["n"] += 1
        ip = "93.184.216.34" if zaehler["n"] == 1 else "127.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]
    return echt(host, port, *a, **k)


socket.getaddrinfo = _rebind
try:
    g.guarded_request(requests.Session(), "GET", "http://rebind.test:8000/", timeout=5)
    pruefe("DNS-Rebinding blockiert", False)
except g.EgressBlocked:
    pruefe("DNS-Rebinding blockiert", True)
finally:
    socket.getaddrinfo = echt
import inspect  # noqa: E402
from app.plugins.builtin.web import html_reader  # noqa: E402
from app.services import product_research  # noqa: E402
pruefe("html_reader nutzt den Guard", "guarded_request" in inspect.getsource(html_reader.HtmlReader._download)
       if hasattr(html_reader, "HtmlReader") else "guarded_request" in inspect.getsource(html_reader))
pruefe("Produkt-Recherche nutzt den Guard", "requests.get(" not in inspect.getsource(product_research))

# ── 5. Verschlüsselung ─────────────────────────────────────────────────────
print("5. Verschlüsselung schlägt fehl statt Klartext")
import app.core.config as cfg  # noqa: E402
from app.core.security import encrypt_credential, decrypt_credential  # noqa: E402
pruefe("normal verschlüsselt", decrypt_credential(encrypt_credential("geheim")) == "geheim")
alt_key = cfg.get_fernet_key
cfg.get_fernet_key = lambda: b"kaputt"
try:
    encrypt_credential("geheim")
    pruefe("kaputter Schlüssel → Fehler", False)
except RuntimeError:
    pruefe("kaputter Schlüssel → Fehler", True)
finally:
    cfg.get_fernet_key = alt_key

# ── 6. Vorlagen-Pipelines ──────────────────────────────────────────────────
print("6. Pipelines aus Vorlagen ohne Store-Herkunft starten inaktiv")
from app.api.templates import _install_pipeline  # noqa: E402
from app.models.pipeline import Pipeline  # noqa: E402
ids = []
try:
    tag = uuid.uuid4().hex[:6]
    for herkunft, erwartet in (("upload", False), ("store", True)):
        p = _install_pipeline({"name": f"t4-{herkunft}-{tag}", "nodes": [], "connections": [],
                               "scheduler": {"cron": "0 3 * * *"}},
                              {}, {}, {}, {"_dm_herkunft": herkunft}, db, None, "t4")
        ids.append(p.id)
        pruefe(f"Herkunft {herkunft} → aktiv={erwartet}", bool(p.active) is erwartet)
finally:
    for pid in ids:
        db.query(Pipeline).filter(Pipeline.id == pid).delete()
    db.commit()

# ── 7. Datenpflege ─────────────────────────────────────────────────────────
print("7. Datenpflege gibt ausgeblendete Spalten nicht heraus")
from app.api.datenpflege import _lesbare_spalten  # noqa: E402
meta = {"aktiv_spalte": "aktiv", "spalten": [
    {"name": "id", "ausgeblendet": True, "schluessel": True},
    {"name": "name", "ausgeblendet": False, "schluessel": False},
    {"name": "ek_preis", "ausgeblendet": True, "schluessel": False},
    {"name": "aktiv", "ausgeblendet": True, "schluessel": False},
]}
pruefe("ausgeblendet nicht gelesen, Schlüssel/Aktiv schon", _lesbare_spalten(meta) == ["id", "name", "aktiv"])
src = inspect.getsource(__import__("app.api.datenpflege", fromlist=["_meta"])._meta)
pruefe("ausgeblendet nicht schreibbar", "name not in ausgeblendet" in src)

# ── 8. API-Studio ──────────────────────────────────────────────────────────
print("8. Geheimnisse in URLs geschwärzt")
from app.services.rest_service import mask_url, mask_params  # noqa: E402
pruefe("api_key in URL", mask_url("https://h/x?api_key=GEHEIM&page=2") == "https://h/x?api_key=***&page=2")
pruefe("user:pw@ in URL", "pw@" not in mask_url("https://user:pw@h/x"))
pruefe("eigener Auth-Parameter", "Z" not in mask_url("https://h/x?myauth=Z", ["myauth"]))
pruefe("Query-Parameter", mask_params({"token": "t", "q": "1"}) == {"token": "***", "q": "1"})

# ── 9. Sicherungs-Archiv ───────────────────────────────────────────────────
print("9. Sicherung einspielen: kein Ausbrechen")
from app.api import backup  # noqa: E402
tmp = tempfile.mkdtemp()


def archiv(name, typ=tarfile.REGTYPE):
    pfad = os.path.join(tmp, f"{uuid.uuid4().hex}.tar.gz")
    with tarfile.open(pfad, "w:gz") as t:
        ti = tarfile.TarInfo(name)
        ti.type = typ
        ti.size = 1 if typ == tarfile.REGTYPE else 0
        t.addfile(ti, io.BytesIO(b"x") if typ == tarfile.REGTYPE else None)
    return pfad


nachbar = "../" + os.path.basename(tempfile.gettempdir()) + "x/y"
for name in ("../raus.txt", "/etc/x", nachbar):
    pruefe(f"{name} abgelehnt", status(lambda: backup._pruefe_archiv(archiv(name))) == 400)
pruefe("Gerätedatei abgelehnt", status(lambda: backup._pruefe_archiv(archiv("d", tarfile.CHRTYPE))) == 400)
shutil.rmtree(tmp, ignore_errors=True)

# ── 10. Anmeldung widerrufen ───────────────────────────────────────────────
print("10. Anmeldungen widerrufbar")
from app.models.user import User  # noqa: E402
from app.core.security import token_fuer, tokens_widerrufen, get_current_user, create_access_token  # noqa: E402
req = SimpleNamespace(method="GET", url=SimpleNamespace(path="/api/auth/me"))
u = User(username=f"t4-user-{uuid.uuid4().hex[:6]}", hashed_password="x")
db.add(u)
db.commit()
db.refresh(u)
try:
    tok = token_fuer(u)
    pruefe("frisches Token gilt", status(lambda: get_current_user(req, tok, db)) == 200)
    alt_ohne_tv = create_access_token({"sub": u.username})
    pruefe("altes Token ohne Stand gilt (Übergang)", status(lambda: get_current_user(req, alt_ohne_tv, db)) == 200)
    tokens_widerrufen(u)
    db.commit()
    pruefe("nach Widerruf ungültig", status(lambda: get_current_user(req, tok, db)) == 401)
    pruefe("auch das alte ohne Stand", status(lambda: get_current_user(req, alt_ohne_tv, db)) == 401)
    pruefe("neues Token gilt wieder", status(lambda: get_current_user(req, token_fuer(u), db)) == 200)
    fremd = create_access_token({"sub": u.username, "uid": u.id + 100000, "tv": u.token_version})
    pruefe("Token eines gelöschten Namensvetters ungültig", status(lambda: get_current_user(req, fremd, db)) == 401)
finally:
    db.query(User).filter(User.id == u.id).delete()
    db.commit()
    db.close()

print()
print("FEHLER: " + ", ".join(FEHLER) if FEHLER else "Alles grün.")
sys.exit(1 if FEHLER else 0)
