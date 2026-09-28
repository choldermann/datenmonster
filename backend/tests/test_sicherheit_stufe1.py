"""
Sicherheitsreview 2, Stufe 1 (28.09.2026): die Wege zur Übernahme des Servers
und zum Abgreifen gespeicherter Zugangsdaten.

Lauf:  docker compose exec -T backend python tests/test_sicherheit_stufe1.py
"""
import sys
from types import SimpleNamespace
sys.path.insert(0, "/app")

from fastapi import HTTPException  # noqa: E402

FEHLER = []


def pruefe(name, bedingung, extra=""):
    print(("  OK   " if bedingung else "  FAIL ") + name + (f"  [{extra}]" if extra and not bedingung else ""))
    if not bedingung:
        FEHLER.append(name)


def wirft(fn, status=None, typ=HTTPException):
    try:
        fn()
    except typ as e:
        return status is None or getattr(e, "status_code", None) == status
    except Exception:
        return False
    return False


ADMIN  = SimpleNamespace(id=-1, username="t-admin", is_admin=True, is_portal_only=False)
EDITOR = SimpleNamespace(id=-2, username="t-editor", is_admin=False, is_portal_only=False)

print("\n── Formeln: kein Ausbruch aus eval ───────────────────────────")
from app.services.expression_engine import _eval_expression, pruefe_ausdruck  # noqa: E402
pruefe("normale Formel rechnet",
       _eval_expression('concat(upper({a}), "-", round({b} * 2, 1))', {"a": "x", "b": 1.25}) == "X-2.5")
pruefe("Bedingung mit if_",
       _eval_expression('if_({b} > 1, "gross", "klein")', {"b": 3}) == "gross")
for boese in ('().__class__.__base__.__subclasses__()',
              '{a}.__class__',
              'upper.__globals__',
              '(lambda: 1)()',
              '[c for c in (1, 2)]',
              '__import__("os")',
              '9 ** 9 ** 9'):
    pruefe(f"abgelehnt: {boese}",
           wirft(lambda b=boese: _eval_expression(b, {"a": "x"}), typ=ValueError))

print("\n── Fensterformel ─────────────────────────────────────────────")
pruefe("Spaltenformel erlaubt",
       not wirft(lambda: pruefe_ausdruck("_num_series('a') + _num_series('b') * 2.0",
                                         set(), platzhalter=("_num_series",)), typ=ValueError))
pruefe("pd.io.common.os.system abgelehnt",
       wirft(lambda: pruefe_ausdruck("pd.io.common.os.system('id')", set(),
                                     platzhalter=("_num_series",)), typ=ValueError))
pruefe("Attribut an Platzhalter abgelehnt",
       wirft(lambda: pruefe_ausdruck("_num_series.__globals__", set(),
                                     platzhalter=("_num_series",)), typ=ValueError))
from app.services.mapping_service import _FORMEL_OPS  # noqa: E402
pruefe("nur Rechenzeichen als op", _FORMEL_OPS == {"+", "-", "*", "/", "(", ")", "%"})

print("\n── Python-Knoten nur für Admins ──────────────────────────────")
from app.api.mappings import python_nodes_pruefen, _gleiches_rest_ziel  # noqa: E402
neu = [{"id": "p1", "script": "return row"}]
pruefe("Admin darf neues Skript", not wirft(lambda: python_nodes_pruefen(neu, [], ADMIN)))
pruefe("Editor: neues Skript → 403", wirft(lambda: python_nodes_pruefen(neu, [], EDITOR), 403))
pruefe("Editor: unverändertes Skript ok", not wirft(lambda: python_nodes_pruefen(neu, neu, EDITOR)))
pruefe("Editor: geändertes Skript → 403",
       wirft(lambda: python_nodes_pruefen([{"id": "p1", "script": "import os"}], neu, EDITOR), 403))
pruefe("Editor: fremde Knoten-ID → 403",
       wirft(lambda: python_nodes_pruefen([{"id": "p2", "script": "return row"}], neu, EDITOR), 403))
pruefe("Editor: leerer Knoten ok",
       not wirft(lambda: python_nodes_pruefen([{"id": "p9", "script": "  "}], [], EDITOR)))

print("\n── REST-Geheimnisse nur ans gespeicherte Ziel ────────────────")
alt = {"url": "https://api.example.com/v1/items/{id}", "auth_config": {"token_url": "https://auth.example.com/t"}}
pruefe("anderer Pfad, gleicher Host → entmasken",
       _gleiches_rest_ziel({"url": "https://api.example.com/v2/x", "auth_config": alt["auth_config"]}, alt))
pruefe("fremder Host → nicht entmasken",
       not _gleiches_rest_ziel({"url": "https://boese.example.net/v1", "auth_config": alt["auth_config"]}, alt))
pruefe("anderer Port → nicht entmasken",
       not _gleiches_rest_ziel({"url": "https://api.example.com:8443/v1", "auth_config": alt["auth_config"]}, alt))
pruefe("Platzhalter im Host → nicht entmasken",
       not _gleiches_rest_ziel({"url": "https://{host}/v1", "auth_config": alt["auth_config"]},
                               {"url": "https://{host}/v1", "auth_config": alt["auth_config"]}))
pruefe("andere token_url → nicht entmasken",
       not _gleiches_rest_ziel({"url": alt["url"], "auth_config": {"token_url": "https://boese.example.net/t"}}, alt))

print("\n── Docker, Protokoll, Dienst-Plugins nur für Admins ──────────")
from app.api import monitoring, plugins  # noqa: E402
for name, fn in [("docker list",    lambda: monitoring.get_docker_containers(user=EDITOR)),
                 ("docker start",   lambda: monitoring.docker_start("x", user=EDITOR)),
                 ("docker stop",    lambda: monitoring.docker_stop("x", user=EDITOR)),
                 ("docker restart", lambda: monitoring.docker_restart("x", user=EDITOR)),
                 ("docker logs",    lambda: monitoring.docker_logs("x", user=EDITOR)),
                 ("Log löschen",    lambda: monitoring.delete_log(1, db=None, user=EDITOR)),
                 ("alle Logs",      lambda: monitoring.delete_all_logs(db=None, user=EDITOR)),
                 ("Plugin registrieren", lambda: plugins.register_dienst_plugin(
                     plugins.DienstPluginBody(id="x", name="x", docker_image="boese/img"), user=EDITOR)),
                 ("Plugin starten", lambda: plugins.start_dienst_plugin("x", user=EDITOR)),
                 ("Plugin stoppen", lambda: plugins.stop_dienst_plugin("x", user=EDITOR)),
                 ("Plugin löschen", lambda: plugins.unregister_dienst_plugin("x", user=EDITOR))]:
    pruefe(f"Editor: {name} → 403", wirft(fn, 403))

print("\n── Verbindungstest leitet kein Passwort um ───────────────────")
from app.core.database import SessionLocal  # noqa: E402
from app.models.dataset import DbConnection  # noqa: E402
from app.api.connections import test_conn_form, ConnectionTest  # noqa: E402
db = SessionLocal()
try:
    c = db.query(DbConnection).filter(DbConnection.password.isnot(None)).first()
    if c is None:
        print("  (keine Verbindung mit Passwort vorhanden – übersprungen)")
    else:
        body = ConnectionTest(id=c.id, db_type=c.db_type or "mssql", host="boese.example.net",
                              port=c.port or 1433, database=c.database or "x",
                              username=c.username or "sa", password="••••••••")
        pruefe("fremder Host mit Maske → 400", wirft(lambda: test_conn_form(body, db=db, user=ADMIN), 400))
    pruefe("unbekannte id mit Maske → 404",
           wirft(lambda: test_conn_form(ConnectionTest(id=999999, db_type="mssql", host="h", port=1,
                                                       database="d", username="u", password="••••••••"),
                                        db=db, user=ADMIN), 404))
finally:
    db.close()

print("\n── SECRET_KEY ────────────────────────────────────────────────")
from app.core import config  # noqa: E402
from app.core.security import decrypt_credential, encrypt_credential  # noqa: E402
pruefe("kein bekannter Standardschlüssel", config.SECRET_KEY != config.LEGACY_SECRET and len(config.SECRET_KEY) >= 32)
from cryptography.fernet import Fernet  # noqa: E402
alt_geheim = Fernet(config._fernet_aus(config.LEGACY_SECRET)).encrypt(b"altes-pw").decode()
pruefe("mit altem Standardschlüssel gespeichert → weiter lesbar", decrypt_credential(alt_geheim) == "altes-pw")
neu_geheim = encrypt_credential("neues-pw")
pruefe("neu verschlüsselt → nicht mit Standardschlüssel lesbar",
       wirft(lambda: Fernet(config._fernet_aus(config.LEGACY_SECRET)).decrypt(neu_geheim.encode()),
             typ=Exception))
pruefe("neu verschlüsselt → lesbar", decrypt_credential(neu_geheim) == "neues-pw")

print()
if FEHLER:
    print(f"{len(FEHLER)} Fehler: {FEHLER}")
    sys.exit(1)
print("Alles OK")
