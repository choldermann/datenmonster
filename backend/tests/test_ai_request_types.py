"""
Prueft, dass jeder KI-Aufruf sagt, WOFUER er die Credits verbraucht.

Der Gateway rechnet je Anfrage ab und schreibt `request_type` mit. Bis
2026-09-22 setzte ihn fast kein Endpunkt - im Verbrauchsbericht stand deshalb
"OTHER", und die automatische Modellwahl (schwere Aufgaben -> gpt-4o) konnte gar
nicht greifen. Beides haengt an diesem einen Argument.

Der Test liest `api/ai.py` mit dem AST und besteht darauf, dass jeder Aufruf an
den KI-Dienst einen Typ mitgibt. Damit faellt ein neuer Endpunkt auf, der ihn
vergisst - und nicht erst die Rechnung drei Monate spaeter.

Lauf:  docker compose exec -T backend python tests/test_ai_request_types.py
"""
import ast
import sys

sys.path.insert(0, "/app")

# Vertrag §7 (docs/monstersuite-ai-gateway-api.md)
ERLAUBT = {
    "CHAT", "SQL_GENERATION", "SQL_ANALYSIS", "SQL_EXPLAIN", "DATA_ANALYSIS",
    "ARTICLE_DESCRIPTION", "CLASSIFICATION", "MAPPING_ASSISTANT", "TRANSFORMATION",
    "EXPRESSION", "ERROR_EXPLAIN", "SUMMARY", "OTHER",
}
# complete_json traegt den Typ als Vorgabe (TRANSFORMATION) - dort ist er optional.
STREAM_METHODEN = {"stream_with_context", "complete_with_context", "_stream"}

FEHLER = []


def pruefe(name, bedingung, extra=""):
    print(("  OK   " if bedingung else "  FAIL ") + name + (f"  [{extra}]" if not bedingung else ""))
    if not bedingung:
        FEHLER.append(name)


quelle = open("/app/app/api/ai.py", encoding="utf-8").read()
baum = ast.parse(quelle)

ohne_typ, typen = [], {}
for knoten in ast.walk(baum):
    if not isinstance(knoten, ast.Call) or not isinstance(knoten.func, ast.Attribute):
        continue
    if knoten.func.attr not in STREAM_METHODEN:
        continue
    empfaenger = getattr(knoten.func.value, "id", "")
    if empfaenger not in ("svc", "service", "ai"):
        continue                      # anderer Empfaenger, kein KI-Dienst
    arg = next((k for k in knoten.keywords if k.arg == "request_type"), None)
    if arg is None:
        ohne_typ.append(knoten.lineno)
        continue
    for literal in ast.walk(arg.value):
        if isinstance(literal, ast.Constant) and isinstance(literal.value, str):
            typen.setdefault(literal.value, []).append(knoten.lineno)

print("\n── Verdrahtung ──")
pruefe("jeder Stream-Aufruf nennt seinen request_type", not ohne_typ,
       f"ohne Typ in Zeile {ohne_typ}")
unbekannt = {t: z for t, z in typen.items() if t not in ERLAUBT}
pruefe("nur Typen aus dem Vertrag (§7)", not unbekannt, unbekannt)
pruefe("mehr als nur OTHER", len(set(typen) - {"OTHER"}) >= 6, sorted(typen))

print("\n── Was wohin zeigt ──")
for typ in sorted(typen):
    print(f"   {typ:20} {len(typen[typ])}x  (Zeilen {', '.join(str(z) for z in typen[typ])})")

erwartet = {"SQL_GENERATION", "SQL_EXPLAIN", "ERROR_EXPLAIN", "DATA_ANALYSIS",
            "CHAT", "MAPPING_ASSISTANT", "EXPRESSION", "TRANSFORMATION", "SUMMARY"}
fehlend = erwartet - set(typen)
pruefe("die tragenden Aufgaben sind vergeben", not fehlend, fehlend)

print()
if FEHLER:
    print(f"{len(FEHLER)} Pruefung(en) fehlgeschlagen: {', '.join(FEHLER)}")
    sys.exit(1)
print("Alle Pruefungen bestanden.")
