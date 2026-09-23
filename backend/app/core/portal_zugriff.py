"""
Was ein reiner Portal-Benutzer (is_portal_only) im Backend erreichen darf.

Bisher sperrte nur das Frontend-Routing (EditorRoute) den Editor. Die API selbst
liess Portal-Benutzer an Verbindungen, Datasets, Mappings, Vorlagen und das
Systemprotokoll — und ueber die Regel "project_id None = owner" sogar an
projektlose Mappings. Deshalb gilt jetzt im Zweifel: gesperrt.

Die Liste unten ist aus dem Frontend abgeleitet: alle Aufrufe, die von
PortalHome/PortalRunner aus erreichbar sind (Formularlauf, Widgets, Kopfzeile,
KI-Assistent im Formular). Wer einem Portal-Widget einen neuen Endpunkt gibt,
muss ihn hier eintragen — sonst antwortet er dem Portal mit 403.
Die fachlichen Pruefungen in den einzelnen Routern bleiben davon unberuehrt.
"""
import re

ALLE = None  # jede Methode

_REGELN = [
    (ALLE,               r"/api/auth/(me|change-password)"),
    (ALLE,               r"/api/portal(/.*)?"),
    ({"GET"},            r"/api/license(/kontingent)?"),
    ({"GET"},            r"/api/mandanten"),
    ({"GET", "PUT"},     r"/api/mandanten/aktiv"),
    ({"GET"},            r"/api/templates/berechtigung"),
    ({"POST"},           r"/api/templates/berechtigung/pruefen"),
    ({"GET"},            r"/api/ai/(status|credits)"),
    ({"POST"},           r"/api/ai/(summarize-data|recommend-action|chat)"),
    ({"POST"},           r"/api/forms/(drilldown|email-table)"),
    ({"GET"},            r"/api/exports/\d+/download"),
    # Verbindungsauswahl im Intrastat-Ausschluss-Widget (nur die Liste)
    ({"GET"},            r"/api/connections"),
    # Fach-Widgets mit eigenen Portal-Pruefungen im jeweiligen Router
    (ALLE, r"/api/(business-config|datenpflege|datev|eingangsrechnung|er-posteingang|intrastat|inventur"
           r"|kunden-ausschluss|lookup|preisregeln|research|stammdaten)(/.*)?"),
]
_KOMPILIERT = [(m, re.compile(muster)) for m, muster in _REGELN]


def portal_darf(methode: str, pfad: str) -> bool:
    pfad = pfad.rstrip("/") or "/"
    methode = methode.upper()
    if methode in ("HEAD", "OPTIONS"):
        methode = "GET"
    for erlaubt, muster in _KOMPILIERT:
        if muster.fullmatch(pfad) and (erlaubt is ALLE or methode in erlaubt):
            return True
    return False
