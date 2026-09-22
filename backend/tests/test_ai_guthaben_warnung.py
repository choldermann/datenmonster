"""
Prueft, dass ein leeres KI-Guthaben nicht mehr still ausfaellt.

Zwei Haelften:
  * Der Cockpit-Report sagt, WARUM die Management-Summary fehlt (vorher kam er
    einfach duenner, und niemand erfuhr, ob Modell, Gateway oder Guthaben schuld war).
  * Die Warnung meldet den ZUSTANDSWECHSEL, nicht jede Nacht dasselbe - eine
    Warnung, die taeglich kommt, wird weggeklickt.

Ohne SMTP und ohne Gateway: beides wird untergeschoben.

Lauf:  docker compose exec -T backend python tests/test_ai_guthaben_warnung.py
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from app.services import ai_guthaben as G            # noqa: E402
from app.services import cockpit_report as R         # noqa: E402
from app.services.ai_gateway import GatewayError     # noqa: E402

FEHLER = []


def pruefe(name, bedingung, extra=""):
    print(("  OK   " if bedingung else "  FAIL ") + name + (f"  [{extra}]" if not bedingung else ""))
    if not bedingung:
        FEHLER.append(name)


# ── Report: Grund statt Schweigen ────────────────────────────────────────────
print("\n── Warum fehlt die Summary? ──")

class _Dienst:
    def __init__(self, exc): self.exc = exc
    async def complete_with_context(self, *a, **k): raise self.exc

def _summary_mit(exc):
    import app.api.ai as ai_api
    import app.services.ai_service as ai_service
    echt, echt_modell = ai_api._require_ai, ai_service.resolve_prose_model
    ai_api._require_ai = lambda db, provider=None: _Dienst(exc)
    async def _modell(db, svc): return "egal"      # braucht sonst die Einstellungen
    ai_service.resolve_prose_model = _modell
    try:
        schema = {"widgets": [{"type": "ai_summary", "action_id": "a1"}]}
        results = {"a1": {"rows": [{"Umsatz": 100}], "columns": ["Umsatz"]}}
        return asyncio.run(R._ai_summary(schema, results, db=None))
    finally:
        ai_api._require_ai = echt
        ai_service.resolve_prose_model = echt_modell

pruefe("leeres Guthaben wird als solches erkannt",
       _summary_mit(GatewayError("insufficient_credits", "leer")) == ("", "kein_guthaben"),
       _summary_mit(GatewayError("insufficient_credits", "leer")))
pruefe("Gateway weg ist etwas anderes",
       _summary_mit(GatewayError("gateway_error", "weg"))[1] == "nicht_erreichbar")
pruefe("jeder andere Fehler bleibt 'fehler'",
       _summary_mit(RuntimeError("irgendwas"))[1] == "fehler")
pruefe("ohne ai_summary-Widget kein Grund (keine Entschuldigung im Report)",
       asyncio.run(R._ai_summary({"widgets": []}, {}, db=None)) == ("", ""))
pruefe("fuer jeden Grund gibt es einen Klartext",
       all(g in R.AI_GRUND_TEXT for g in ("kein_guthaben", "nicht_erreichbar", "zeit_abgelaufen", "fehler")))
pruefe("der Klartext nennt das Guthaben beim Namen",
       "Guthaben" in R.AI_GRUND_TEXT["kein_guthaben"])

# ── Warnung: nur beim Zustandswechsel ────────────────────────────────────────
print("\n── Wann geht eine Mail raus? ──")

gesendet = []
class _DB:
    """Einstellungen im Speicher - der Dienst liest und schreibt nur ueber get/set."""
    werte = {}

import app.api.settings as settings_api
settings_api.get_setting = lambda db, key, default=None: _DB.werte.get(key, default)
settings_api.set_setting = lambda db, key, value: _DB.werte.__setitem__(key, value)
import app.services.email_service as mail
mail.send_email = lambda **kw: gesendet.append(kw)

_DB.werte.update({G.SCHLUESSEL_AKTIV: "1", G.SCHLUESSEL_EMPFAENGER: "wer@example.org",
                  G.SCHLUESSEL_SCHWELLE: "150", "ai_provider": "datenmonster"})

lage = {"guthaben": 90}
G.stand = lambda db: {"zutreffend": True, "provider": "datenmonster", "schwelle": 150,
                      "guthaben": lage["guthaben"], "monat": {"credits_used": 12},
                      "knapp": lage["guthaben"] <= 150}

r1 = G.pruefen_und_melden(None)
pruefe("erste Unterschreitung meldet sich", r1["gesendet"] is True, r1.get("grund"))
pruefe("Betreff nennt den Stand", "90" in gesendet[-1]["subject"], gesendet[-1]["subject"])
r2 = G.pruefen_und_melden(None)
pruefe("zweite Nacht schweigt", r2["gesendet"] is False and "unveraendert" in r2["grund"], r2.get("grund"))

lage["guthaben"] = 900
r3 = G.pruefen_und_melden(None)
pruefe("Entwarnung nach dem Aufladen", r3["gesendet"] is True and "ausreichend" in gesendet[-1]["subject"],
       gesendet[-1]["subject"])
r4 = G.pruefen_und_melden(None)
pruefe("danach wieder Ruhe", r4["gesendet"] is False)

_DB.werte[G.SCHLUESSEL_EMPFAENGER] = ""
lage["guthaben"] = 10
r5 = G.pruefen_und_melden(None)
pruefe("ohne Empfaenger keine Mail, aber auch kein Fehler",
       r5["gesendet"] is False and "Empfaenger" in r5["grund"], r5.get("grund"))

print()
if FEHLER:
    print(f"{len(FEHLER)} Pruefung(en) fehlgeschlagen: {', '.join(FEHLER)}")
    sys.exit(1)
print("Alle Pruefungen bestanden.")
