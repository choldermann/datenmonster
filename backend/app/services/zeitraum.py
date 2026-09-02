"""Zeitraum-Vorgaben, serverseitig.

Python-Zwilling von `computeDatePreset` in
`frontend/src/components/forms/FormFields.tsx`. Die IDs müssen zwischen beiden
Seiten identisch bleiben: derselbe Report, einmal im Browser geöffnet und einmal
vom Zeitplan ausgelöst, muss denselben Zeitraum abdecken – sonst weichen die
Zahlen der Montagsmail von denen ab, die der Anwender am Bildschirm sieht, und
niemand kann sagen, welche stimmt.

Alle Rückgaben sind ISO-Datumsangaben (yyyy-mm-dd). Das ist auch das Format, das
die Oberfläche liefert; MSSQL liest reine Datumstexte in anderer Schreibweise
stumm falsch.
"""
import calendar
from datetime import date


def _letzter_tag(jahr: int, monat: int) -> date:
    """Letzter Tag des Monats."""
    return date(jahr, monat, calendar.monthrange(jahr, monat)[1])


PRESETS = {
    "this_month": "Dieser Monat",
    "last_month": "Letzter Monat",
    "this_year":  "Dieses Jahr",
    "last_year":  "Letztes Jahr",
    "days_30":    "Letzte 30 Tage",
    "months_12":  "Letzte 12 Monate",
}


def berechne(preset: str, heute: date = None) -> dict:
    """Gibt {"von": iso, "bis": iso} für eine Preset-ID zurück.

    Unbekannte oder fehlende IDs fallen auf den laufenden Monat zurück – denselben
    Standard, den das Monitor-Formular verwendet.
    """
    heute = heute or date.today()
    y, m = heute.year, heute.month

    if preset == "last_month":
        vm_jahr, vm_monat = (y - 1, 12) if m == 1 else (y, m - 1)
        von, bis = date(vm_jahr, vm_monat, 1), _letzter_tag(vm_jahr, vm_monat)
    elif preset == "this_year":
        # Jahresanfang bis Auslösedatum – der Fall aus dem Kundengespräch.
        von, bis = date(y, 1, 1), heute
    elif preset == "last_year":
        von, bis = date(y - 1, 1, 1), date(y - 1, 12, 31)
    elif preset == "days_30":
        von, bis = date.fromordinal(heute.toordinal() - 29), heute
    elif preset == "months_12":
        vj_jahr = y - 1
        try:
            start = date(vj_jahr, m, heute.day)
        except ValueError:            # 29.02. im Nicht-Schaltjahr
            start = _letzter_tag(vj_jahr, m)
        von, bis = date.fromordinal(start.toordinal() + 1), heute
    else:                              # "this_month" und alles Unbekannte
        von, bis = date(y, m, 1), heute

    return {"von": von.isoformat(), "bis": bis.isoformat()}


def klartext(preset: str, zeitraum: dict) -> str:
    """Für Betreffzeile und Mailtext: »Dieses Jahr (01.01.2026 – 02.09.2026)«."""
    def de(iso):
        try:
            return date.fromisoformat(iso).strftime("%d.%m.%Y")
        except Exception:
            return iso or "?"
    name = PRESETS.get(preset or "", "Zeitraum")
    return f"{name} ({de(zeitraum.get('von'))} – {de(zeitraum.get('bis'))})"
