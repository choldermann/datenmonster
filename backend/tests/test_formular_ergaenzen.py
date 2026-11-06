"""Vorlagen-Update ergänzt installierte Formulare – neue Ampelzeilen, geänderte Bausteine.

Eine neue Prüfung im Health-Check bringt eine neue Zeile in der Ampel (kommt über
das Mapping) und einen neuen Eintrag in der Detailkarte der Tasklist. Das Widget
selbst gibt es beim Kunden schon; ohne Ergänzung der Karte öffnet der Klick auf
die neue Zeile nichts. Geprüft wird die reine Ergänzungslogik, ohne Datenbank.

Lauf:  docker compose exec -T backend python tests/test_formular_ergaenzen.py
"""
import copy
import sys
import traceback
sys.path.insert(0, "/app")

from app.api.templates import (_bausteine, _formular_ergaenzen,  # noqa: E402
                               _bausteine_aktualisieren, _stand_ergaenzen)


def _tasklist(eintraege: dict) -> dict:
    return {"id": "w_ampel", "type": "tasklist", "action_id": "act_summary",
            "config": {"row_detail": {"key_column": "check_key", "map": eintraege}}}


ALT = {"mapping_id": 100, "title": "VK unter EK"}
NEU = {"mapping_id": 776, "title": "Lieferanten-EK unplausibel"}


def _formulare():
    installiert = {
        "actions": [{"id": "act_summary"}, {"id": "act_vk"}],
        "widgets": [_tasklist({"artikel_vk_unter_ek": dict(ALT)})],
        "result_tabs": [{"id": "tab_preise", "action_ids": ["act_vk"]}],
    }
    vorlage = {
        "actions": [{"id": "act_summary"}, {"id": "act_vk"}, {"id": "act_ek_lief"}],
        "widgets": [_tasklist({"artikel_vk_unter_ek": dict(ALT),
                               "ek_lieferant_unplausibel": dict(NEU)}),
                    {"id": "w_tbl_ek_lief", "type": "table", "action_id": "act_ek_lief"}],
        "result_tabs": [{"id": "tab_preise", "action_ids": ["act_vk", "act_ek_lief"]}],
    }
    return installiert, vorlage


def test_neue_ampelzeile_kommt_beim_update_an():
    installiert, vorlage = _formulare()
    bisher = _bausteine(copy.deepcopy(installiert))  # Stand der letzten Installation
    neu = _formular_ergaenzen(installiert, vorlage, bisher)

    karte = installiert["widgets"][0]["config"]["row_detail"]["map"]
    assert karte["ek_lieferant_unplausibel"] == NEU
    assert neu["row_detail"] == ["w_ampel::ek_lieferant_unplausibel"]
    # Die übrigen Bausteine wie bisher: Aktion, Liste, Reiter-Eintrag.
    assert neu["actions"] == ["act_ek_lief"]
    assert neu["widgets"] == ["w_tbl_ek_lief"]
    assert installiert["result_tabs"][0]["action_ids"] == ["act_vk", "act_ek_lief"]


def test_vorhandene_eintraege_bleiben_unangetastet():
    installiert, vorlage = _formulare()
    # Im Betrieb angepasster Titel und eine eigene Zeile des Kunden.
    karte = installiert["widgets"][0]["config"]["row_detail"]["map"]
    karte["artikel_vk_unter_ek"]["title"] = "Verlustartikel (eigener Titel)"
    karte["eigene_pruefung"] = {"mapping_id": 999, "title": "Eigenbau"}
    _formular_ergaenzen(installiert, vorlage, _bausteine(copy.deepcopy(installiert)))

    assert karte["artikel_vk_unter_ek"]["title"] == "Verlustartikel (eigener Titel)"
    assert karte["eigene_pruefung"]["mapping_id"] == 999
    assert "ek_lieferant_unplausibel" in karte


def test_vom_kunden_entfernter_eintrag_kommt_nicht_zurueck():
    installiert, vorlage = _formulare()
    _formular_ergaenzen(installiert, vorlage, {})
    protokoll = _bausteine(vorlage)  # so legt der Installer es ab
    # Kunde entfernt die neue Zeile wieder aus der Karte.
    del installiert["widgets"][0]["config"]["row_detail"]["map"]["ek_lieferant_unplausibel"]

    neu = _formular_ergaenzen(installiert, vorlage, protokoll)
    assert "row_detail" not in neu
    assert "ek_lieferant_unplausibel" not in installiert["widgets"][0]["config"]["row_detail"]["map"]


def test_zweites_update_ist_ohne_wirkung():
    installiert, vorlage = _formulare()
    _formular_ergaenzen(installiert, vorlage, {})
    vorher = copy.deepcopy(installiert)
    assert _formular_ergaenzen(installiert, vorlage, _bausteine(vorlage)) == {}
    assert installiert == vorher


def test_altinstallation_ohne_protokoll_bekommt_die_zeile():
    installiert, vorlage = _formulare()
    # Protokoll von vor dieser Änderung: Listen ja, Detailkarten nein.
    alt = {k: v for k, v in _bausteine(copy.deepcopy(installiert)).items() if k != "row_detail"}
    neu = _formular_ergaenzen(installiert, vorlage, alt)
    assert neu["row_detail"] == ["w_ampel::ek_lieferant_unplausibel"]


def test_umgebautes_widget_ohne_karte_bleibt_wie_es_ist():
    installiert, vorlage = _formulare()
    installiert["widgets"][0]["config"].pop("row_detail")
    neu = _formular_ergaenzen(installiert, vorlage, _bausteine(copy.deepcopy(installiert)))
    assert "row_detail" not in neu
    assert "row_detail" not in installiert["widgets"][0]["config"]


def test_neues_widget_wird_nicht_doppelt_gezaehlt():
    """Ein komplett neues Widget bringt seine Karte selbst mit – kein row_detail-Eintrag."""
    installiert, vorlage = _formulare()
    installiert["widgets"] = []
    neu = _formular_ergaenzen(installiert, vorlage, {})
    assert "w_ampel" in neu["widgets"]
    assert "row_detail" not in neu


# ── Geänderte Bausteine: nur nachziehen, was niemand im Betrieb angepasst hat ──

def _mit_info(text, conn=7):
    return {"id": "w_tbl", "type": "table", "action_id": "act_vk",
            "config": {"info": text, "connection_id": conn}}


def _update(installiert, vorlage, stand):
    """Ablauf wie im Installer: aktualisieren, ergänzen, Stand fortschreiben."""
    akt, geschuetzt, neuer_stand = _bausteine_aktualisieren(installiert, vorlage, stand)
    erg = _formular_ergaenzen(installiert, vorlage, {})
    _stand_ergaenzen(neuer_stand, installiert, erg)
    return akt, geschuetzt, neuer_stand


def test_unveraenderter_baustein_bekommt_neue_fassung():
    alt = {"widgets": [_mit_info("alter Text")], "doku": {"intro": "alt"}}
    installiert = copy.deepcopy(alt)
    stand = _stand_ergaenzen({}, alt)             # so bei der Erstinstallation protokolliert
    vorlage = {"widgets": [_mit_info("neuer Text")], "doku": {"intro": "neu"}}
    akt, geschuetzt, neuer_stand = _update(installiert, vorlage, stand)
    assert sorted(akt) == ["doku", "widgets::w_tbl"]
    assert geschuetzt == []
    assert installiert["widgets"][0]["config"]["info"] == "neuer Text"
    assert installiert["doku"]["intro"] == "neu"
    # Nächstes Update ohne Änderung: nichts mehr zu tun.
    assert _update(installiert, vorlage, neuer_stand)[:2] == ([], [])


def test_im_betrieb_angepasster_baustein_bleibt():
    alt = {"widgets": [_mit_info("alter Text")]}
    installiert = copy.deepcopy(alt)
    stand = _stand_ergaenzen({}, alt)
    installiert["widgets"][0]["config"]["width"] = 12      # Kunde hat umgebaut
    vorlage = {"widgets": [_mit_info("neuer Text")]}
    akt, geschuetzt, neuer_stand = _update(installiert, vorlage, stand)
    assert akt == [] and geschuetzt == ["widgets::w_tbl"]
    assert installiert["widgets"][0]["config"] == {"info": "alter Text", "connection_id": 7, "width": 12}
    # Bleibt auch beim übernächsten Update geschützt.
    vorlage2 = {"widgets": [_mit_info("noch neuerer Text")]}
    assert _update(installiert, vorlage2, neuer_stand)[:2] == ([], ["widgets::w_tbl"])


def test_andere_verbindung_gilt_nicht_als_anpassung():
    alt = {"widgets": [_mit_info("alter Text", conn=7)]}
    installiert = copy.deepcopy(alt)
    stand = _stand_ergaenzen({}, alt)
    installiert["widgets"][0]["config"]["connection_id"] = 12   # Mandant gewechselt
    vorlage = {"widgets": [_mit_info("neuer Text", conn=12)]}
    akt, geschuetzt, _ = _update(installiert, vorlage, stand)
    assert akt == ["widgets::w_tbl"] and geschuetzt == []
    assert installiert["widgets"][0]["config"]["connection_id"] == 12


def test_altinstallation_ohne_fingerabdruck_aendert_erst_beim_naechsten_update():
    installiert = {"widgets": [_mit_info("alter Text")]}
    vorlage = {"widgets": [_mit_info("neuer Text")]}
    akt, geschuetzt, stand = _update(installiert, vorlage, None)
    assert akt == [] and geschuetzt == []
    assert installiert["widgets"][0]["config"]["info"] == "alter Text"
    # Heutiger Stand ist jetzt der Ausgangspunkt → beim nächsten Update kommt die neue Fassung.
    akt, _, _ = _update(installiert, vorlage, stand)
    assert akt == ["widgets::w_tbl"]
    assert installiert["widgets"][0]["config"]["info"] == "neuer Text"


def test_eigene_bausteine_des_kunden_bleiben_unberuehrt():
    installiert = {"widgets": [_mit_info("x"), {"id": "w_eigenbau", "type": "kpi"}]}
    vorlage = {"widgets": [_mit_info("x")]}
    akt, geschuetzt, stand = _update(installiert, vorlage, {})
    assert "widgets::w_eigenbau" not in stand
    assert installiert["widgets"][1] == {"id": "w_eigenbau", "type": "kpi"}


def test_neue_ampelzeile_und_geaenderter_info_text_zusammen():
    """Der echte Fall: Health-Check 1.14 → 1.15 mit unangetasteter Ampel."""
    installiert, vorlage = _formulare()
    stand = _stand_ergaenzen({}, installiert)
    akt, geschuetzt, _ = _update(installiert, vorlage, stand)
    assert "widgets::w_ampel" in akt and "result_tabs::tab_preise" in akt
    karte = installiert["widgets"][0]["config"]["row_detail"]["map"]
    assert karte["ek_lieferant_unplausibel"] == NEU
    assert installiert["result_tabs"][0]["action_ids"] == ["act_vk", "act_ek_lief"]



def test_rubrik_kommt_beim_update_an_eigene_bleibt():
    from app.api.templates import _rubrik_uebernehmen
    ohne = {"widgets": []}
    assert _rubrik_uebernehmen(ohne, {"rubrik": {"id": "lager"}}) is True
    assert ohne["rubrik"] == {"id": "lager"}
    eigen = {"rubrik": {"id": "vertrieb"}}
    assert _rubrik_uebernehmen(eigen, {"rubrik": {"id": "lager"}}) is False
    assert eigen["rubrik"] == {"id": "vertrieb"}
    assert _rubrik_uebernehmen({}, {}) is False


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
