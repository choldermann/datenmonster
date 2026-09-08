"""
Prüft die Lizenz-Sperren als Tabelle.

Der teure Fehler ist nicht eine vergessene Sperre, sondern eine zu viel: sperrt
man versehentlich den Lauf-Weg, steht bei einem Kunden das gekaufte Cockpit still
und niemand sieht sofort warum. Darum steht der Lauf-Weg hier zuerst.

Lauf:  docker compose exec -T backend python tests/test_lizenz_gate.py
"""
import sys
sys.path.insert(0, "/app")

from app.core.lizenz_gate import benoetigtes_recht, meldung, REGELN  # noqa: E402

FEHLER = []


def pruefe(name, bedingung, extra=""):
    print(("  OK   " if bedingung else "  FAIL ") + name + (f"  [{extra}]" if extra and not bedingung else ""))
    if not bedingung:
        FEHLER.append(name)


def frei(methode, pfad):
    r = benoetigtes_recht(methode, pfad)
    pruefe(f"{methode} {pfad}", r is None, f"verlangt {r}")


def verlangt(methode, pfad, recht):
    r = benoetigtes_recht(methode, pfad)
    pruefe(f"{methode} {pfad} → {recht}", r == recht, f"verlangt {r}")


print("\n── Der Lauf-Weg gekaufter Vorlagen muss frei bleiben ────────")
frei("POST",   "/api/forms/7/run")
frei("POST",   "/api/forms/7/report")
frei("POST",   "/api/forms/drilldown")
frei("POST",   "/api/forms/email-table")
frei("DELETE", "/api/forms/7/submissions")
frei("POST",   "/api/portal/forms/gf-cockpit/run")
frei("POST",   "/api/portal/forms/gf-cockpit/report")
frei("POST",   "/api/pipelines/3/run")
frei("POST",   "/api/pipelines/3/debug-run")
frei("POST",   "/api/pipelines/3/toggle")
frei("POST",   "/api/scheduler/jobs")
frei("PATCH",  "/api/scheduler/jobs/5")
frei("POST",   "/api/scheduler/jobs/5/trigger")
frei("POST",   "/api/reports/schedules")
frei("PUT",    "/api/reports/schedules/2")
frei("POST",   "/api/reports/schedules/2/run-now")
frei("POST",   "/api/mappings/execute")
frei("POST",   "/api/mappings/execute-download")
frei("POST",   "/api/mappings/preview")
frei("POST",   "/api/mappings/debug-run")
frei("POST",   "/api/rest-sources/4/trigger")
frei("POST",   "/api/rest-sources/4/import")
frei("POST",   "/api/ftp-sources/4/trigger")

print("\n── KI, die auswertet: frei (kostet Credits) ─────────────────")
frei("POST", "/api/ai/summarize-data")
frei("POST", "/api/ai/recommend-action")
frei("POST", "/api/ai/warmup")
frei("POST", "/api/ai/purchase/invoice")
frei("POST", "/api/stammdaten/beschreibung")
frei("POST", "/api/research/hersteller")

print("\n── Weiteres, das nie gesperrt sein darf ─────────────────────")
frei("POST",   "/api/license/free-request")
frei("POST",   "/api/license/activate")
frei("POST",   "/api/auth/token")
frei("PUT",    "/api/mandanten/aktiv")
frei("POST",   "/api/templates/install")
frei("POST",   "/api/templates/store/jtl_gf_cockpit/install")
frei("POST",   "/api/templates/upload")
frei("GET",    "/api/forms/")
frei("GET",    "/api/mappings/")
frei("GET",    "/api/api-studio/collections")
frei("POST",   "/api/query/preview")

print("\n── Selbst bauen: gesperrt ───────────────────────────────────")
verlangt("POST",   "/api/forms/",   "form_build")
verlangt("PUT",    "/api/forms/7",  "form_build")
verlangt("DELETE", "/api/forms/7",  "form_build")
verlangt("POST",   "/api/pipelines/",  "pipeline_build")
verlangt("PUT",    "/api/pipelines/3", "pipeline_build")
verlangt("POST",   "/api/query/save",  "query_build")
verlangt("DELETE", "/api/query/9",     "query_build")
verlangt("POST",   "/api/reports/build",   "query_build")
verlangt("PUT",    "/api/reports/build/7", "query_build")
verlangt("POST",   "/api/api-studio/collections",   "api_studio")
verlangt("POST",   "/api/api-studio/send",          "api_studio")
verlangt("DELETE", "/api/api-studio/history",       "api_studio")
verlangt("POST",   "/api/ftp-sources/",      "ftp_sftp")
verlangt("PUT",    "/api/ftp-sources/4",     "ftp_sftp")
verlangt("POST",   "/api/rest-sources/",     "rest_sources")
verlangt("DELETE", "/api/rest-sources/4",    "rest_sources")
verlangt("POST",   "/api/mail/pollers/3/start", "mail_connector")

print("\n── KI, die baut: gesperrt ───────────────────────────────────")
verlangt("POST", "/api/werkbank/vorhaben/2/bauen", "ai_build")
verlangt("POST", "/api/werkbank/verstehen",        "ai_build")
verlangt("POST", "/api/smart-mapping/suggest",     "ai_build")
verlangt("POST", "/api/ai/chat",                   "ai_build")
verlangt("POST", "/api/ai/generate-sql",           "ai_build")
verlangt("POST", "/api/ai/generate-nodes",         "ai_build")
verlangt("POST", "/api/ai/suggest-mapping",        "ai_build")
verlangt("POST", "/api/ai/explain-sql",            "ai_build")
verlangt("POST", "/api/ai/transform-preview",      "ai_build")
verlangt("POST", "/api/ai-memory/knowledge",       "ai_memory")
verlangt("PUT",  "/api/ai-memory/knowledge/4",     "ai_memory")
verlangt("POST", "/api/schema-catalog/2/ai-suggest", "schema_catalog")
verlangt("PUT",  "/api/schema-catalog/2/table",      "schema_catalog")
verlangt("PUT",  "/api/mandanten/verwaltung",        "multi_tenant")
verlangt("PUT",  "/api/mandanten/freigaben",         "multi_tenant")

print("\n── Die Meldung erklärt sich selbst ──────────────────────────")
m = meldung("form_build")
pruefe("nennt das Recht im Klartext", "Formulare" in m, m)
pruefe("sagt, dass Vorlagen weiterlaufen", "Vorlagen" in m, m)
pruefe("nennt den Weg zum Freischalten", "monstersuite.de" in m, m)
pruefe("keine rohe Kennung in der Meldung", "form_build" not in m, m)

print("\n── Jede Regel nennt ein bekanntes Recht ─────────────────────")
from app.api.license import ALL_FEATURES  # noqa: E402
bekannt = {f["id"] for f in ALL_FEATURES}
unbekannt = sorted({r for r, _, _ in REGELN} - bekannt)
pruefe("keine Regel auf ein unbekanntes Recht", not unbekannt, str(unbekannt))
frei_rechte = {f["id"] for f in ALL_FEATURES if f["free"]}
kostenlos_gesperrt = sorted({r for r, _, _ in REGELN} & frei_rechte)
pruefe("kein kostenloses Recht wird gesperrt", not kostenlos_gesperrt, str(kostenlos_gesperrt))

print("\n" + ("ALLE PRÜFUNGEN BESTANDEN" if not FEHLER else f"FEHLGESCHLAGEN: {FEHLER}"))
sys.exit(1 if FEHLER else 0)
