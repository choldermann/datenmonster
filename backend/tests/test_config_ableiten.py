"""Store-Update alter Installationen: Einstellungen aus den installierten Objekten ablesen.

Ältere Installationen haben ihre Einstellungen nicht protokolliert. Ein Update
installiert die neue Vorlagen-Fassung darüber – fehlt dabei ein Wert, landet der
Platzhalter selbst im Mapping (Intrastat: "{{idev_login_name}}" statt Kennnummer).

Lauf:  docker compose exec -T backend python tests/test_config_ableiten.py
"""
import sys
import traceback
sys.path.insert(0, "/app")

from app.api.templates import _einstellungen_ableiten  # noqa: E402


def _ablesen(vorlage, installiert, keys):
    gefunden = {}
    _einstellungen_ableiten(vorlage, installiert, set(keys), gefunden)
    return gefunden


def test_ganzer_wert():
    v = {"targets": [{"target_options": {"idev_config": {"login_name": "{{idev_login_name}}",
                                                         "bundesland": "{{idev_bundesland}}"}}}]}
    i = {"targets": [{"target_options": {"idev_config": {"login_name": "w3s81881", "bundesland": "05"}}}]}
    assert _ablesen(v, i, ["idev_login_name", "idev_bundesland"]) == {
        "idev_login_name": "w3s81881", "idev_bundesland": "05"}


def test_wert_mitten_im_sql_auch_wenn_sich_die_vorlage_geaendert_hat():
    v = {"sql_nodes": [{"sql": "SELECT A, B FROM X\nWHERE neu = 1 AND LV.LetzterVerkauf < DATEADD(DAY, -{{ladenhueter_tage}}, GETDATE())"}]}
    i = {"sql_nodes": [{"sql": "SELECT A FROM X\nWHERE LV.LetzterVerkauf < DATEADD(DAY, -90, GETDATE()) ORDER BY A"}]}
    assert _ablesen(v, i, ["ladenhueter_tage"]) == {"ladenhueter_tage": "90"}


def test_platzhalter_im_installierten_wird_nicht_als_wert_genommen():
    v = {"x": "{{idev_login_name}}"}
    i = {"x": "{{idev_login_name}}"}  # wurde nie gesetzt
    assert _ablesen(v, i, ["idev_login_name"]) == {}


def test_nur_gesuchte_schluessel():
    v = {"x": "a {{eins}} b {{zwei}} c"}
    i = {"x": "a 1 b 2 c"}
    assert _ablesen(v, i, ["zwei"]) == {"zwei": "2"}
    assert _ablesen(v, i, ["eins", "zwei"]) == {"eins": "1", "zwei": "2"}


def test_listen_ueber_id_zugeordnet():
    v = {"targets": [{"id": "t1", "o": "{{k}}"}, {"id": "t2", "o": "fest"}]}
    i = {"targets": [{"id": "t2", "o": "fest"}, {"id": "t1", "o": "WERT"}]}
    assert _ablesen(v, i, ["k"]) == {"k": "WERT"}


if __name__ == "__main__":
    fehler = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("  OK   " + name)
            except Exception:
                fehler += 1
                print("  FAIL " + name)
                traceback.print_exc()
    print(f"\n{fehler} Fehler" if fehler else "\nAlle Tests bestanden")
    sys.exit(1 if fehler else 0)
