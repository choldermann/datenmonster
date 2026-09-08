"""
Lizenz-Sperren fuer die bauenden Endpunkte.

Leitsatz des Lizenzmodells: **gesperrt wird der Editor, nicht die Maschine.**
Eine gekaufte Vorlage darf alles tun, was ihr Manifest vorsieht — ausfuehren,
schreiben, verschicken, nachts laufen. Wer selbst baut, braucht Pro.

Warum eine Tabelle und keine Dekoratoren: es gibt rund 290 schreibende Endpunkte.
Einzeln dekoriert waere nach dem dritten neuen Router einer vergessen, und man
saehe nirgends im Ganzen, was eigentlich gesperrt ist. Hier steht es auf einer
Seite und ist als Tabelle pruefbar.

Zwei Listen, in dieser Reihenfolge ausgewertet:
  1. FREI  — Pfade, die trotz Treffer in REGELN immer durchgehen (der Lauf-Weg)
  2. REGELN — Pfad + Methode verlangen ein Recht

Was sich nicht als Pfadregel ausdruecken laesst (Mengenbegrenzungen, das
DB-Ziel eines Mappings), sitzt in `app/core/kontingent.py`.
"""
import re
import time
from typing import Optional

# ─── Immer frei: der Lauf-Weg ─────────────────────────────────────────────────
# Diese Pfade duerfen NIE gesperrt werden, sonst legt die Sperre eine gekaufte
# Vorlage von innen lahm. Jede Zeile hier ist eine bewusste Entscheidung.
FREI = [
    r"^/api/forms/[^/]+/run$",              # Auswertung ausfuehren
    r"^/api/forms/[^/]+/report$",           # PDF-Report
    r"^/api/forms/drilldown$",              # Klick in eine Tabelle
    r"^/api/forms/email-table$",            # Tabelle per Mail
    r"^/api/forms/[^/]+/submissions$",      # Eingaenge eines Formulars aufraeumen
    r"^/api/portal/",                       # Kunden-Portal
    r"^/api/pipelines/[^/]+/run$",
    r"^/api/pipelines/[^/]+/debug-run$",
    r"^/api/pipelines/[^/]+/toggle$",       # Zeitplan an/aus ist Bedienen
    r"^/api/scheduler/",                    # Nachtlaeufe einer Vorlage einstellen
    r"^/api/reports/schedules",             # Zustellplan eines gekauften Reports
    r"^/api/mappings/(execute|execute-download|preview|debug-run|sql-schema)$",
    r"^/api/query/preview$",                # nur lesend
    r"^/api/(rest-sources|ftp-sources)/[^/]+/(test|trigger|import)$",
    r"^/api/ai/(summarize-data|recommend-action|warmup|test-connection|models|pull-model|purchase)",
    r"^/api/ai-memory/solutions/[^/]+/use$",
    r"^/api/(stammdaten|research)/",        # KI-Recherche im Health-Check
    r"^/api/license/",
    r"^/api/auth/(token|me|change-password)$",
    r"^/api/mandanten/aktiv$",              # Mandant umschalten
]

# ─── Rechte je Pfad ───────────────────────────────────────────────────────────
# (Recht, Methoden, Pfadmuster)
SCHREIBEND = ("POST", "PUT", "PATCH", "DELETE")
REGELN = [
    # Eigene Formulare und Dashboards bauen
    ("form_build",     SCHREIBEND, r"^/api/forms/?$"),
    ("form_build",     SCHREIBEND, r"^/api/forms/[^/]+$"),

    # Eigene Pipelines bauen
    ("pipeline_build", SCHREIBEND, r"^/api/pipelines/?$"),
    ("pipeline_build", SCHREIBEND, r"^/api/pipelines/[^/]+$"),

    # Abfrage-Generator und Report-Baukasten
    ("query_build",    SCHREIBEND, r"^/api/query/(save|[^/]+)$"),
    ("query_build",    SCHREIBEND, r"^/api/reports/build"),

    # API Studio als Ganzes
    ("api_studio",     SCHREIBEND, r"^/api/api-studio/"),

    # Datenuebertragung
    ("ftp_sftp",       SCHREIBEND, r"^/api/ftp-sources/?$"),
    ("ftp_sftp",       SCHREIBEND, r"^/api/ftp-sources/[^/]+$"),
    ("rest_sources",   SCHREIBEND, r"^/api/rest-sources/?$"),
    ("rest_sources",   SCHREIBEND, r"^/api/rest-sources/[^/]+$"),
    ("mail_connector", SCHREIBEND, r"^/api/mail/pollers/"),

    # KI, die baut (KI, die auswertet, steht oben unter FREI)
    ("ai_build",       SCHREIBEND, r"^/api/werkbank/"),
    ("ai_build",       SCHREIBEND, r"^/api/smart-mapping/"),
    ("ai_build",       SCHREIBEND, r"^/api/ai/(chat|generate-|suggest-|explain-|schema-search|"
                                   r"mapping-context|table-context|transform-preview)"),
    ("ai_memory",      SCHREIBEND, r"^/api/ai-memory/"),
    ("schema_catalog", SCHREIBEND, r"^/api/schema-catalog/"),

    # Verwaltung
    ("multi_tenant",   SCHREIBEND, r"^/api/mandanten/(verwaltung|freigaben)$"),
]

_FREI_RX   = [re.compile(m) for m in FREI]
_REGELN_RX = [(recht, methoden, re.compile(muster)) for recht, methoden, muster in REGELN]


def benoetigtes_recht(methode: str, pfad: str) -> Optional[str]:
    """Welches Recht verlangt dieser Aufruf? None = frei."""
    if any(rx.match(pfad) for rx in _FREI_RX):
        return None
    for recht, methoden, rx in _REGELN_RX:
        if methode.upper() in methoden and rx.match(pfad):
            return recht
    return None


# ─── Rechte-Auskunft mit kurzem Gedaechtnis ───────────────────────────────────
# _resolve_license liest bei jedem Aufruf Einstellungen aus der Datenbank. Bei
# einem Formular-Editor, der im Sekundentakt speichert, waere das unnoetige Last.
_CACHE: dict = {"zeit": 0.0, "rechte": None}
_CACHE_SEKUNDEN = 30


def aktive_rechte(db, frisch: bool = False) -> set:
    jetzt = time.time()
    if not frisch and _CACHE["rechte"] is not None and jetzt - _CACHE["zeit"] < _CACHE_SEKUNDEN:
        return _CACHE["rechte"]
    from app.api.license import _resolve_license
    rechte = set(_resolve_license(db).get("active_features") or [])
    _CACHE.update({"zeit": jetzt, "rechte": rechte})
    return rechte


def cache_leeren() -> None:
    """Nach Aktivierung/Entfernen einer Lizenz — sonst gilt die alte Auskunft
    noch bis zu 30 Sekunden weiter."""
    _CACHE.update({"zeit": 0.0, "rechte": None})


def hat_recht(db, recht: str) -> bool:
    return recht in aktive_rechte(db)


# ─── Meldung ──────────────────────────────────────────────────────────────────
# Der Kunde soll lesen, was ihm fehlt und was er tun kann — nicht eine Kennung.
_KLARTEXT = {
    "form_build":     "Eigene Formulare und Dashboards bauen",
    "pipeline_build": "Eigene Pipelines bauen",
    "query_build":    "Abfrage-Generator und Report-Baukasten",
    "api_studio":     "API Studio",
    "ftp_sftp":       "FTP- und SFTP-Verbindungen",
    "rest_sources":   "Eigene REST-Schnittstellen als Datenquelle",
    "mail_connector": "E-Mails als Datenquelle",
    "ai_build":       "KI-Werkbank und KI-Assistent",
    "ai_memory":      "KI-Wissensdatenbank",
    "schema_catalog": "Schema-Katalog",
    "multi_tenant":   "Mehrere Mandanten",
    "multi_user":     "Weitere Administratoren",
    "db_write":       "Eigene Mappings in eine Datenbank schreiben lassen",
    "unlimited":      "Unbegrenzter Eigenbau",
    "plugin_tier2":   "Erweiterte Plugins",
}


def meldung(recht: str) -> str:
    was = _KLARTEXT.get(recht, recht)
    return (f"„{was}“ gehört zur Pro-Version. "
            f"Gekaufte Vorlagen laufen davon unberührt weiter — gesperrt ist nur das "
            f"Selbst-Bauen. Freischalten unter monstersuite.de.")
