"""python3 -m pytest updater/test_compose_stand.py"""
import compose_stand as stand

ALT = '''services:
  backend:
    ports:
      - "${BACKEND_PORT:-8000}:8000"
  frontend:
    ports:
      - "${FRONTEND_PORT:-5174}:80"
'''


def test_install_sh_portersetzung_gilt_als_unveraendert():
    gepatcht = ALT.replace("5174:80", "8080:80").replace("8000:8000", "9000:8000")
    assert stand.fingerabdruck(gepatcht) == stand.fingerabdruck(ALT)


def test_windows_zeilenenden_gelten_als_unveraendert():
    assert stand.fingerabdruck(ALT.replace("\n", "\r\n")) == stand.fingerabdruck(ALT)


def test_echte_aenderung_wird_erkannt():
    assert stand.fingerabdruck(ALT + "  extra:\n    image: x\n") != stand.fingerabdruck(ALT)


def test_bekannte_staende_ignoriert_leerzeilen_und_kommentare():
    assert stand.bekannte_staende("# x\n\nabc\n def \n") == {"abc", "def"}


def test_env_ergaenzen_ueberschreibt_nie():
    text, neu = stand.env_ergaenzen("A=1\nB=2", {"A": "9", "C": "3"})
    assert neu == ["C"]
    assert stand.env_lesen(text) == {"A": "1", "B": "2", "C": "3"}


def test_env_setzen_ersetzt_vorhandene_zeile():
    text = stand.env_setzen("# Ports\nFRONTEND_PORT=5174\nX=1\n", {"FRONTEND_PORT": "8080", "BACKEND_PORT": "9000"})
    assert stand.env_lesen(text) == {"FRONTEND_PORT": "8080", "X": "1", "BACKEND_PORT": "9000"}
    assert text.startswith("# Ports\nFRONTEND_PORT=8080\n")


def test_ports_bleiben_erhalten():
    def cfg(fe, be):
        return {"services": {
            "frontend": {"ports": [{"target": 80, "published": fe}]},
            "backend": {"ports": [{"target": 8000, "published": be}]},
            "ollama": {"ports": [{"target": 11434, "published": "11434"}]},
        }}
    alt = stand.veroeffentlichte_ports(cfg("8080", "8000"))
    neu = stand.veroeffentlichte_ports(cfg("5174", "8000"))
    assert stand.port_variablen(alt, neu) == {"FRONTEND_PORT": "8080"}


def test_wegfallender_port_wird_nicht_in_env_geschrieben():
    # Stufe 3 nimmt Port 8000 heraus – dann gibt es nichts zu merken
    assert stand.port_variablen({"backend": "8000"}, {}) == {}
