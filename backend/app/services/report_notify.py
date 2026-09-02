"""Zustellung eines geplanten Reports: Kurzfassung im Mailtext, PDF im Anhang.

Warum die Kurzfassung: Eine Mail, die nur „Anhang siehe PDF" sagt, wird auf dem
Telefon nicht geöffnet. Die wichtigsten Kacheln direkt im Text machen die
Montagsmail auf einen Blick lesbar; das vollständige Layout liegt daneben.
"""
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

MAX_KACHELN = 12


def _zahl(v, decimals: int = 2) -> str:
    """Deutsche Schreibweise: 1.234.567,89"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v) if v is not None else "–"
    s = f"{f:,.{decimals}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _kachelwerte(schema: dict, results: dict) -> list:
    """Die KPI-Kacheln des Reports als (Beschriftung, Wert)-Liste.

    Liest genau so, wie das KPI-Widget im Browser liest: Spalte aus config,
    erste Zeile des Ergebnisses. Weicht das ab, stünde in der Mail eine andere
    Zahl als im Report – der schlimmste denkbare Fehler dieser Funktion.
    """
    raus = []
    for w in schema.get("widgets") or []:
        if w.get("type") != "kpi":
            continue
        cfg = w.get("config") or {}
        spalte = cfg.get("column")
        erg = results.get(w.get("action_id")) or {}
        zeilen = erg.get("rows") or []
        if not spalte or not zeilen:
            continue
        wert = zeilen[0].get(spalte)
        if wert is None:
            continue
        text = (f"{cfg.get('prefix', '')}"
                f"{_zahl(wert, int(cfg.get('decimals', 2) or 0))}"
                f"{cfg.get('suffix', '')}").strip()
        raus.append((w.get("label") or spalte, text))
        if len(raus) >= MAX_KACHELN:
            break
    return raus


def _tabellen(schema: dict, results: dict) -> list:
    """(Beschriftung, Zeilenzahl) je Tabellen-Widget – als Inhaltsverzeichnis."""
    raus = []
    for w in schema.get("widgets") or []:
        if w.get("type") != "table":
            continue
        erg = results.get(w.get("action_id")) or {}
        raus.append((w.get("label") or "Tabelle", len(erg.get("rows") or [])))
    return raus


def _esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def build_email(report_name: str, zeitraum_text: str, schema: dict, results: dict,
                projekt_name: Optional[str] = None,
                betreff: Optional[str] = None) -> dict:
    """Baut Betreff, Text- und HTML-Fassung. Der PDF-Anhang kommt vom Aufrufer."""
    kacheln = _kachelwerte(schema, results)
    tabellen = _tabellen(schema, results)

    subject = (betreff or "").strip() or (
        f"{report_name} – {zeitraum_text}"
        + (f" ({projekt_name})" if projekt_name else ""))

    zeilen = [report_name, zeitraum_text, ""]
    if projekt_name:
        zeilen.insert(2, projekt_name)
    if kacheln:
        zeilen.append("Kennzahlen")
        breite = max(len(k) for k, _ in kacheln)
        zeilen += [f"  {k.ljust(breite)}   {v}" for k, v in kacheln]
        zeilen.append("")
    if tabellen:
        zeilen.append("Enthaltene Tabellen")
        zeilen += [f"  {n} ({z} Zeilen)" for n, z in tabellen]
        zeilen.append("")
    zeilen.append("Der vollständige Report liegt als PDF im Anhang.")
    text = "\n".join(zeilen)

    kachel_html = "".join(
        f'<tr><td style="padding:5px 14px 5px 0;color:#555;font-size:13px">{_esc(k)}</td>'
        f'<td style="padding:5px 0;font-weight:600;font-size:13px;text-align:right">{_esc(v)}</td></tr>'
        for k, v in kacheln)
    tab_html = "".join(
        f'<li style="margin-bottom:3px">{_esc(n)} '
        f'<span style="color:#888">({z} Zeilen)</span></li>'
        for n, z in tabellen)

    html = f"""<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;
  max-width:560px;color:#1a1a1a;line-height:1.5">
  <h2 style="margin:0 0 2px;font-size:18px">{_esc(report_name)}</h2>
  <p style="margin:0 0 18px;color:#666;font-size:13px">{_esc(zeitraum_text)}
    {f'&middot; {_esc(projekt_name)}' if projekt_name else ''}</p>
  {f'<table style="border-collapse:collapse;margin-bottom:18px">{kachel_html}</table>' if kacheln else ''}
  {f'<p style="margin:0 0 6px;font-size:13px;font-weight:600">Enthaltene Tabellen</p><ul style="margin:0 0 18px;padding-left:18px;font-size:13px">{tab_html}</ul>' if tabellen else ''}
  <p style="margin:0;color:#666;font-size:12px">
    Der vollständige Report liegt als PDF im Anhang.</p>
</div>"""

    return {"subject": subject[:240], "text": text, "html": html,
            "kacheln": len(kacheln), "tabellen": len(tabellen)}


def _dateiname(report_name: str, bis: str) -> str:
    umlaut = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue",
                            "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"})
    s = (report_name or "report").translate(umlaut).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "report"
    return f"{s}_{(bis or '').replace('-', '')}.pdf"


def send_report_email(db, empfaenger: str, report_name: str, zeitraum_text: str,
                      schema: dict, results: dict, pdf: bytes,
                      projekt_name: Optional[str] = None,
                      betreff: Optional[str] = None,
                      bis: str = "") -> dict:
    """Verschickt den Report. Gibt zurück, was tatsächlich passiert ist.

    Ohne Empfänger wird nichts verschickt, und das ist kein Fehler: ein Zeitplan
    darf auch nur dazu da sein, den Report regelmäßig durchzurechnen.
    """
    from app.services.email_service import send_email

    ziele = [e.strip() for e in (empfaenger or "").replace(";", ",").split(",") if e.strip()]
    if not ziele:
        return {"sent": False, "grund": "keine Empfänger"}

    mail = build_email(report_name, zeitraum_text, schema, results,
                       projekt_name, betreff)
    send_email(
        to=", ".join(ziele), subject=mail["subject"], body=mail["text"],
        html_body=mail["html"], db=db,
        attachments=[{"filename": _dateiname(report_name, bis),
                      "data": pdf, "mime": "application/pdf"}] if pdf else None,
    )
    return {"sent": True, "empfaenger": ziele,
            "kacheln": mail["kacheln"], "tabellen": mail["tabellen"]}
