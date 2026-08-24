"""Zustellung der Unternehmenswarnungen per E-Mail.

Bewusst getrennt vom `alert_service`: der wertet aus, dieser hier stellt zu.
Der Text formuliert nichts und rundet nichts – er ordnet nur, was die Regeln
geliefert haben. Es geht keine KI-Formulierung raus, denn eine Warnung, die
jemand um 5 Uhr morgens ungeprüft liest, muss wörtlich das sagen, was in der
Datenbank steht.
"""
import logging
from typing import Optional

from app.services.alert_service import SEVERITY_ORDER

logger = logging.getLogger(__name__)

_AMPEL_EMOJI = {"kritisch": "🔴", "warnung": "🟠", "hinweis": "🟡",
                "info": "🔵", "positiv": "🟢"}
_AMPEL_HTML = {"kritisch": "#dc2626", "warnung": "#ea580c", "hinweis": "#ca8a04",
               "info": "#2563eb", "positiv": "#16a34a"}


def filter_alerts(alerts: list, min_severity: str = "warnung") -> list:
    """Nur Warnungen ab der eingestellten Dringlichkeit."""
    grenze = SEVERITY_ORDER.get(min_severity, 1)
    return [a for a in (alerts or [])
            if SEVERITY_ORDER.get(a.get("severity"), 9) <= grenze]


def _zahl(v) -> str:
    if v is None or v == "":
        return "–"
    try:
        f = float(v)
        return f"{int(f):,}".replace(",", ".") if f == int(f) else f"{f:,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")
    except (TypeError, ValueError):
        return str(v)


def _marke(a: dict) -> str:
    """Kurzer Zusatz, der die Veränderung gegenüber dem Vortag benennt."""
    if a.get("neu") is True:
        return "NEU"
    d = a.get("delta")
    if d is None:
        return ""
    try:
        d = float(d)
    except (TypeError, ValueError):
        return ""
    if d > 0:
        return f"+{_zahl(d)} gegenüber Vortag"
    if d < 0:
        return f"{_zahl(d)} gegenüber Vortag"
    tage = a.get("seit_tagen")
    return f"unverändert seit {tage} Tagen" if tage else "unverändert"


def build_email(lauf: dict, projekt_name: Optional[str] = None,
                min_severity: str = "warnung") -> Optional[dict]:
    """Baut Betreff, Text- und HTML-Fassung. None, wenn nichts zu melden ist."""
    alerts = filter_alerts(lauf.get("alerts") or [], min_severity)
    erledigt = lauf.get("erledigt") or []
    if not alerts and not erledigt:
        return None

    neue = [a for a in alerts if a.get("neu") is True]
    kritisch = [a for a in alerts if a.get("severity") == "kritisch"]

    titel = projekt_name or "Unternehmensmonitor"
    if neue:
        betreff = f"{titel}: {len(neue)} neue von {len(alerts)} Warnungen"
    else:
        betreff = f"{titel}: {len(alerts)} Warnungen"
    if kritisch:
        betreff += f" – {len(kritisch)} kritisch"

    verg = lauf.get("vergleich") or {}
    if verg.get("tag"):
        basis_hinweis = (f"Verglichen mit dem Lauf vom {verg['tag']} "
                         f"({verg.get('regeln_verglichen')} Regeln in beiden Läufen geprüft).")
    else:
        # Warum kein Vergleich möglich war, gehört in die Mail: sonst liest sich
        # eine Liste ohne „NEU\u201c-Marken wie „nichts hat sich verändert\u201c.
        grund = verg.get("grund") or "kein früherer Lauf vorhanden"
        basis_hinweis = (f"Kein Vergleich mit dem Vortag möglich ({grund}) – "
                         f"\u201eneu\u201c und Veränderungen bleiben deshalb offen.")

    # ---- Textfassung ------------------------------------------------------
    z = [betreff, "=" * len(betreff), "", basis_hinweis, ""]
    for a in alerts:
        marke = _marke(a)
        kopf = f"{_AMPEL_EMOJI.get(a.get('severity'), '•')} {a.get('titel') or a.get('name')}"
        if marke:
            kopf += f"   [{marke}]"
        z.append(kopf)
        if a.get("untertitel"):
            z.append(f"   {a['untertitel']}")
        fakten = [f"{f.get('label')}: {f.get('wert')}{(' ' + f['einheit']) if f.get('einheit') else ''}"
                  for f in (a.get("fakten") or [])]
        if fakten:
            z.append("   " + " | ".join(fakten))
        z.append("")
    if erledigt:
        z.append(f"Weggefallen seit dem letzten Lauf ({len(erledigt)}):")
        for e in erledigt:
            z.append(f"  ✓ {e.get('titel') or e.get('name')}")
        z.append("")
    z.append(f"Geprüft: {lauf.get('checked')} Regeln, ausgelöst: {lauf.get('triggered')}.")
    if lauf.get("errors"):
        z.append(f"Nicht auswertbar: {len(lauf['errors'])} Regel(n).")
    z.append("Schwellwerte und Regeln stehen im Dashboard-Reiter „Warnungen“.")
    text = "\n".join(z)

    # ---- HTML-Fassung -----------------------------------------------------
    h = [f'<div style="font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:720px">',
         f'<h2 style="margin:0 0 4px">{betreff}</h2>',
         f'<p style="color:#666;font-size:13px;margin:0 0 16px">{basis_hinweis}</p>']
    for a in alerts:
        farbe = _AMPEL_HTML.get(a.get("severity"), "#666")
        marke = _marke(a)
        badge = (f'<span style="background:{farbe};color:#fff;border-radius:3px;'
                 f'padding:1px 6px;font-size:11px;margin-left:8px">{marke}</span>') if marke else ""
        h.append(f'<div style="border-left:4px solid {farbe};padding:8px 12px;margin:0 0 10px;background:#fafafa">')
        h.append(f'<div style="font-weight:600">{a.get("titel") or a.get("name")}{badge}</div>')
        if a.get("untertitel"):
            h.append(f'<div style="color:#555;font-size:13px">{a["untertitel"]}</div>')
        fakten = a.get("fakten") or []
        if fakten:
            teile = [f'{f.get("label")}: <b>{f.get("wert")}</b>'
                     f'{(" " + f["einheit"]) if f.get("einheit") else ""}' for f in fakten]
            h.append(f'<div style="color:#333;font-size:12px;margin-top:4px">{" &nbsp;|&nbsp; ".join(teile)}</div>')
        h.append('</div>')
    if erledigt:
        h.append(f'<p style="margin:16px 0 4px"><b>Weggefallen seit dem letzten Lauf ({len(erledigt)})</b></p><ul style="margin:0;color:#16a34a">')
        for e in erledigt:
            h.append(f'<li>{e.get("titel") or e.get("name")}</li>')
        h.append('</ul>')
    h.append(f'<p style="color:#666;font-size:12px;margin-top:20px">'
             f'Geprüft: {lauf.get("checked")} Regeln, ausgelöst: {lauf.get("triggered")}.'
             + (f' Nicht auswertbar: {len(lauf["errors"])}.' if lauf.get("errors") else "")
             + '<br>Schwellwerte und Regeln stehen im Dashboard-Reiter „Warnungen“.</p></div>')

    return {"subject": betreff, "text": text, "html": "".join(h),
            "anzahl": len(alerts), "neu": len(neue)}


def send_alert_email(db, empfaenger: str, lauf: dict, projekt_name: Optional[str] = None,
                     min_severity: str = "warnung", only_new: bool = False) -> dict:
    """Verschickt die Warnungen. Gibt zurück, was tatsächlich passiert ist.

    Ohne Empfänger wird nichts verschickt – und das ist kein Fehler, sondern der
    Normalfall eines Zeitplans, der nur die Grundlinie schreiben soll.
    """
    from app.services.email_service import send_email

    ziele = [e.strip() for e in (empfaenger or "").replace(";", ",").split(",") if e.strip()]
    if not ziele:
        return {"sent": False, "grund": "keine Empfänger"}

    if only_new and not [a for a in filter_alerts(lauf.get("alerts") or [], min_severity)
                         if a.get("neu") is True]:
        return {"sent": False, "grund": "nichts Neues"}

    mail = build_email(lauf, projekt_name, min_severity)
    if not mail:
        return {"sent": False, "grund": "keine Warnung über der Schwelle"}

    send_email(to=", ".join(ziele), subject=mail["subject"], body=mail["text"],
               html_body=mail["html"], db=db)
    return {"sent": True, "empfaenger": ziele, "anzahl": mail["anzahl"], "neu": mail["neu"]}
