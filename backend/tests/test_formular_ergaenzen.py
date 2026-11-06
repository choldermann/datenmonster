"""Vorlagen-Update ergänzt installierte Formulare – auch neue Ampelzeilen.

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

from app.api.templates import _bausteine, _formular_ergaenzen  # noqa: E402


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
