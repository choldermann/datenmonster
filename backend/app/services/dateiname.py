"""
Dateinamen aus Mustern bauen – für Mapping-Ziele, „Datei ablegen“ und Regeln.

Platzhalter:
  {datum} 20261112   {zeit} 143005   {jahr} {monat} {tag}
  {ziel} {mapping} {gruppe}
  {Spaltenname}  Wert dieser Spalte in der ersten Zeile (bei „eine Datei je …“
                 also der Wert der Gruppe, z.B. {Lieferant})
Unbekannte Platzhalter bleiben stehen – so fällt ein Tippfehler im Namen auf.
"""
import re
from datetime import datetime
from typing import Optional

_PLATZHALTER = re.compile(r"\{([^{}]+)\}")


def sicher(text: str, laenge: int = 120) -> str:
    """Nur Zeichen, die jedes Dateisystem verträgt; keine Pfadbestandteile."""
    t = re.sub(r"[^\w\-.]", "_", str(text if text is not None else ""), flags=re.UNICODE)
    t = re.sub(r"_+", "_", t).strip(" ._")
    return t[:laenge] or "leer"


def dateiname_bauen(muster: str, werte: Optional[dict] = None, zeile: Optional[dict] = None,
                    endung: Optional[str] = None) -> str:
    jetzt = datetime.now()
    basis = {"datum": jetzt.strftime("%Y%m%d"), "zeit": jetzt.strftime("%H%M%S"),
             "jahr": jetzt.strftime("%Y"), "monat": jetzt.strftime("%m"), "tag": jetzt.strftime("%d")}
    basis.update({k: v for k, v in (werte or {}).items() if v is not None})
    zeile = zeile or {}

    def ersetzen(m):
        name = m.group(1)
        if name in basis:
            return sicher(basis[name])
        if name in zeile:
            return sicher(zeile[name])
        return m.group(0)

    name = _PLATZHALTER.sub(ersetzen, muster or "")
    # Pfadtrenner und Steuerzeichen raus, Platzhalter-Klammern dürfen bleiben
    name = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", name).strip(" .")
    if endung and not name.lower().endswith("." + endung.lower()):
        name = f"{name}.{endung}"
    return name or f"export.{endung or 'dat'}"
