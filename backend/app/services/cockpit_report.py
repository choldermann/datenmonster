# -*- coding: utf-8 -*-
"""Erzeugt aus einem Dashboard-Formular (z.B. GF-Cockpit) einen PDF-Report:
Deckblatt (Firma aus JTL tFirma, Datum, Zeitraum, gewählte Filter) + je Ergebnis-
Reiter die Widgets (KPIs, Tabellen, Diagramme) sowie eine KI-Management-Summary.
Rein serverseitig: xhtml2pdf (HTML→PDF) + matplotlib (Charts als PNG)."""
import io
import re
import asyncio
import base64
import datetime
import html as _html
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

# Die KI-Management-Summary wird zeitlich begrenzt, damit der (synchrone) Report
# schnell zurückkommt. Die Text-Generierung selbst dauert auf CPU auch bei WARMEM
# Modell ~20–25 s (nicht nur der Kaltstart). Damit die Analyse zuverlässig in den
# Report kommt, ist das Limit großzügig (Report bleibt mit den nun parallelen
# Mappings trotzdem unter dem ~60 s-Proxy-Timeout). Ist das Modell kalt, reicht es
# evtl. nicht → Summary wird übersprungen; deshalb Modelle in den Einstellungen
# vorwärmen (Warmup, keep_alive) – dann ist sie zuverlässig dabei.
_SUMMARY_TIMEOUT_S = 90

# Cockpit-Reports lösen dieselben ~28 read-only Mapping-Abfragen aus wie der
# Form-Run. Nacheinander summieren die sich zu >60 s und laufen in einen Timeout.
# Daher gedrosselt PARALLEL (analog zum Form-Run, s. app/api/forms.py). 5 =
# Kompromiss aus Tempo und Last auf der Quell-DB (z.B. produktive JTL-WaWi).
_REPORT_RUN_CONCURRENCY = 5

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
from sqlalchemy import text
from xhtml2pdf import pisa

from app.services.sql_helpers import _get_sql_engine
from app.services.mapping_service import MappingContext, execute_mapping
from app.models.mapping import Mapping

ACCENT = "#b8860b"
DARK = "#222222"
MUTED = "#666666"
CHART_COLORS = ["#c9a227", "#3c8f6e", "#7a5cc0", "#c0504d", "#4a7fb5", "#d38a3c",
                "#2f9e8f", "#b5508f", "#c7ac2b", "#3aa5b5"]


# ── Formatierung ──────────────────────────────────────────────────────────────
def _fmt(v, decimals=2) -> str:
    if v is None or v == "":
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    s = f"{f:,.{decimals}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def _esc(v) -> str:
    return _html.escape("" if v is None else str(v))


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# ── Datenbeschaffung ──────────────────────────────────────────────────────────
def _resolve_conn_id(schema: dict, db) -> Optional[int]:
    for a in schema.get("actions", []):
        if a.get("type") == "run_mapping" and a.get("mapping_id"):
            m = db.query(Mapping).filter(Mapping.id == a["mapping_id"]).first()
            if m and m.sql_nodes:
                cid = m.sql_nodes[0].get("connection_id")
                if isinstance(cid, int):
                    return cid
    return None


def _fetch_company(conn_id: Optional[int]) -> dict:
    if not conn_id:
        return {}
    q = ("SELECT TOP 1 cName, cUnternehmer, cStrasse, cPLZ, cOrt, cLand, cTel, cEMail, "
         "cWWW, cSteuerNr, cIBAN, cBIC, cBank FROM dbo.tFirma "
         "WHERE cAktiv = 'Y' AND ISNULL(cName,'') <> '' ORDER BY kFirma")
    try:
        eng = _get_sql_engine(conn_id)
        with eng.connect() as cx:
            r = cx.execute(text(q)).fetchone()
        return dict(r._mapping) if r else {}
    except Exception:
        return {}


def _run_one_action(action: dict, params: dict, row_cap: int = None) -> dict:
    """Führt EINE run_mapping-Action read-only aus – mit EIGENER DB-Session, damit
    die Funktion gefahrlos parallel laufen kann (SQLAlchemy-Sessions sind nicht
    thread-sicher). Gibt das Ergebnis-Dict für results[action_id] zurück.
    row_cap: bei full_rows-Tabellen die volle Zeilenzahl laden, damit der Report die
    Fußzeile »… und N weitere Zeilen« korrekt berechnen kann."""
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        m = db.query(Mapping).filter(Mapping.id == action["mapping_id"]).first()
        if not m or not m.targets:
            return {"columns": [], "rows": []}
        ctx = MappingContext.from_orm(m)
        ctx.run_params = dict(params)  # eigene Kopie je Thread (keine geteilte Mutation)
        res = execute_mapping(**ctx.to_execute_kwargs(ctx.targets[0].get("fields") or [], 500),
                              row_cap=row_cap)
        return {"columns": res.get("columns", []), "rows": res.get("rows", [])}
    except Exception:
        return {"columns": [], "rows": []}
    finally:
        db.close()


def _run_actions(schema: dict, params: dict, db, only_ids: Optional[set] = None) -> dict:
    """Mapping-Actions des Reports read-only ausführen. Gedrosselt PARALLEL, damit
    ~28 Cockpit-Abfragen nicht in einen Timeout laufen (analog Form-Run).
    only_ids: nur diese Action-IDs ausführen (Abschnittsauswahl im Report-Dialog) –
    abgewählte Reiter kosten so auch keine Laufzeit mehr."""
    from app.api.forms import _expandable_action_ids, FULL_ROWS_CAP
    expandable = _expandable_action_ids(schema)
    actions = [a for a in schema.get("actions", [])
               if a.get("type") == "run_mapping" and a.get("mapping_id")
               and (only_ids is None or a.get("id") in only_ids)]
    def _cap(a):
        return FULL_ROWS_CAP if a.get("id") in expandable else None
    results = {}
    if len(actions) == 1:
        results[actions[0]["id"]] = _run_one_action(actions[0], params, _cap(actions[0]))
    elif actions:
        with ThreadPoolExecutor(max_workers=_REPORT_RUN_CONCURRENCY) as ex:
            futs = {ex.submit(_run_one_action, a, params, _cap(a)): a["id"] for a in actions}
            for fut in as_completed(futs):
                results[futs[fut]] = fut.result()
    return results


def _lookup_labels(conn_id: Optional[int], kind: str, values: list) -> list:
    from app.api.lookup import LOOKUP_QUERIES
    sql = LOOKUP_QUERIES.get(kind)
    if not sql or not conn_id:
        return [str(v) for v in values]
    try:
        eng = _get_sql_engine(conn_id)
        with eng.connect() as cx:
            m = {str(r[0]): str(r[1]) for r in cx.execute(text(sql))}
        return [m.get(str(v), str(v)) for v in values]
    except Exception:
        return [str(v) for v in values]


# ── Charts ────────────────────────────────────────────────────────────────────
def _de_axis(ax):
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: _fmt(x, 0)))
    ax.tick_params(labelsize=8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def _fig_to_uri(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _render_chart(widget: dict, result: dict) -> Optional[str]:
    cfg = widget.get("config", {})
    rows = result.get("rows", [])
    if not rows:
        return None
    wtype = widget.get("type")
    try:
        if wtype == "pie":
            lc, vc = cfg.get("label_column"), cfg.get("value_column")
            if not lc or not vc:
                return None
            labels = [str(r.get(lc)) for r in rows][:8]
            vals = [float(r.get(vc) or 0) for r in rows][:8]
            fig, ax = plt.subplots(figsize=(5.5, 3.2))
            ax.pie(vals, labels=labels, autopct="%1.0f%%", colors=CHART_COLORS, textprops={"fontsize": 8})
            return _fig_to_uri(fig)

        x = cfg.get("x_column")
        if not x:
            return None
        fig, ax = plt.subplots(figsize=(7.2, 3.0))
        if wtype == "bar" and cfg.get("series_column") and cfg.get("value_column"):
            sc, vc = cfg["series_column"], cfg["value_column"]
            xs, seen = [], set()
            series = {}
            for r in rows:
                xv = r.get(x)
                if xv is None:
                    continue
                if xv not in seen:
                    seen.add(xv); xs.append(xv)
                s = str(r.get(sc) or "Unbekannt")
                series.setdefault(s, {})[xv] = series.get(s, {}).get(xv, 0) + float(r.get(vc) or 0)
            bottoms = {xv: 0 for xv in xs}
            for i, (s, m) in enumerate(series.items()):
                vals = [m.get(xv, 0) for xv in xs]
                ax.bar([str(xv) for xv in xs], vals, bottom=[bottoms[xv] for xv in xs],
                       label=s, color=CHART_COLORS[i % len(CHART_COLORS)])
                for xv in xs:
                    bottoms[xv] += m.get(xv, 0)
            ax.legend(fontsize=7)
        else:
            ycols = cfg.get("y_columns", [])
            if not ycols:
                return None
            xs = [str(r.get(x)) for r in rows]
            for i, yc in enumerate(ycols):
                vals = [float(r.get(yc) or 0) for r in rows]
                col = CHART_COLORS[i % len(CHART_COLORS)]
                if wtype == "line":
                    ax.plot(xs, vals, marker="o", markersize=3, label=yc, color=col)
                else:
                    off = (i - (len(ycols) - 1) / 2) * 0.8 / max(len(ycols), 1)
                    import numpy as _np
                    ax.bar(_np.arange(len(xs)) + off, vals, width=0.8 / max(len(ycols), 1), label=yc, color=col)
            if wtype != "line":
                import numpy as _np
                ax.set_xticks(_np.arange(len(xs))); ax.set_xticklabels(xs)
            if len(ycols) > 1:
                ax.legend(fontsize=7)
        ax.tick_params(axis="x", labelrotation=0, labelsize=7)
        _de_axis(ax)
        return _fig_to_uri(fig)
    except Exception:
        return None


# ── Widget-HTML ───────────────────────────────────────────────────────────────
def _kpi_cell(widget: dict, result: dict) -> str:
    cfg = widget.get("config", {})
    rows = result.get("rows", [])
    col = cfg.get("column")
    val = rows[0].get(col) if rows and col else None
    dec = int(cfg.get("decimals", 0))
    txt = f"{cfg.get('prefix','')}{_fmt(val, dec)}{cfg.get('suffix','')}" if val is not None else "–"
    delta = ""
    cc = cfg.get("compare_column")
    if cc and rows and rows[0].get(cc) not in (None, 0, "") and val is not None:
        try:
            base = float(rows[0][cc]); cur = float(val)
            pct = 100.0 * (cur - base) / base if base else 0
            up = pct >= 0
            good = up != bool(cfg.get("invert_delta"))
            color = "#2f8f5b" if good else "#c0504d"
            arrow = "▲" if up else "▼"
            delta = (f'<div style="font-size:8pt;color:{color}">{arrow} {_fmt(abs(pct),1)} % '
                     f'<span style="color:{MUTED}">{_esc(cfg.get("compare_label","VJ"))}</span></div>')
        except (TypeError, ValueError):
            pass
    return (f'<td style="width:33%;padding:6px;border:1px solid #ddd;background:#fafafa">'
            f'<div style="font-size:8pt;color:{MUTED}">{_esc(widget.get("label",""))}</div>'
            f'<div style="font-size:14pt;font-weight:bold;color:{DARK}">{_esc(txt)}</div>{delta}</td>')


def _spaltenkopf(c: str) -> str:
    """CamelCase-Spaltennamen umbruchfähig machen: "TageOhneAbgang" → "Tage Ohne Abgang".
    Reportlab bricht nur an Leerzeichen – ein langer Kopf zwingt die Spalte sonst so
    breit, dass die ganze Tabelle über den Seitenrand läuft."""
    c = str(c)
    c = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", c)      # Tage|Ohne|Abgang
    c = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", c)    # EK|Netto
    # Bleibt ein einzelnes langes Wort übrig (Mindestbestand, Bestellnummer), passt es
    # in keine schmale Spalte und läuft über den Nachbarn. \u00AD markiert die Stelle,
    # an der die Kopfzelle später "-<br/>" einsetzt.
    teile = []
    for w in c.split(" "):
        if len(w) > 11:
            mitte = len(w) // 2
            # Möglichst an einer Konsonantengrenze trennen ("Bestell-nummer" statt
            # "Bestel-lnummer"); sonst schlicht in der Mitte.
            vokale = set("aeiouäöüAEIOUÄÖÜ")
            def ist_silbengrenze(i):
                # Konsonant | Konsonant + Vokal → dort beginnt eine neue Silbe.
                return (w[i - 1] not in vokale and w[i] not in vokale
                        and i + 1 < len(w) and w[i + 1] in vokale)
            kandidaten = [i for i in range(max(1, mitte - 3), min(len(w) - 1, mitte + 5))
                          if ist_silbengrenze(i)]
            stelle = min(kandidaten, key=lambda i: abs(i - mitte)) if kandidaten else mitte
            w = w[:stelle] + "\u00AD" + w[stelle:]
        teile.append(w)
    return " ".join(teile)


def _table_html(widget: dict, result: dict) -> str:
    cfg = widget.get("config", {})
    hidden = set(cfg.get("hidden_columns", []))
    cols = [c for c in result.get("columns", []) if c not in hidden]
    rows = result.get("rows", [])
    if not cols or not rows:
        return '<p style="font-size:9pt;color:#999">Keine Daten.</p>'
    info = cfg.get("info")
    # Spaltenbreiten selbst vorgeben: xhtml2pdf richtet sich sonst nach dem Inhalt und
    # schiebt breite Tabellen (Artikel-Listen mit 8 Spalten) über den Seitenrand hinaus.
    # Zahlenspalten brauchen wenig Platz, Textspalten viel – daraus die Prozentbreiten.
    num_cols = {c for c in cols if any(_is_num(r.get(c)) for r in rows)}
    gewicht = {c: (1.0 if c in num_cols else 2.2) for c in cols}
    summe = sum(gewicht.values()) or 1
    breite = {c: max(6, round(100 * gewicht[c] / summe)) for c in cols}
    # Ab 6 Spalten kleiner setzen, sonst wird jede Zelle zur Buchstabensäule.
    fs = 8 if len(cols) <= 5 else 7 if len(cols) <= 8 else 6
    head = "".join(f'<th width="{breite[c]}%" style="padding:4px 5px;border:1px solid #ddd;background:#eee;'
                   f'font-size:{fs}pt;text-align:{"right" if c in num_cols else "left"}">'
                   f'{_esc(_spaltenkopf(c)).replace(chr(0xAD), "-<br/>")}</th>' for c in cols)
    # Report bewusst gekürzt: max. 25 Zeilen, Rest als Hinweis-Fußzeile (die volle
    # Tabelle steckt im Cockpit / im E-Mail- und CSV-Export).
    REPORT_MAX = 25
    body = ""
    for r in rows[:REPORT_MAX]:
        tds = ""
        for c in cols:
            v = r.get(c)
            num = _is_num(v)
            tds += (f'<td width="{breite[c]}%" style="padding:3px 5px;border:1px solid #eee;font-size:{fs}pt;'
                    f'text-align:{"right" if num else "left"}">{_esc(_fmt(v) if num else v)}</td>')
        body += f"<tr>{tds}</tr>"
    if len(rows) > REPORT_MAX:
        rest = len(rows) - REPORT_MAX
        body += (f'<tr><td colspan="{len(cols)}" style="padding:4px 6px;border:1px solid #eee;'
                 f'font-size:{fs}pt;font-style:italic;color:{MUTED};text-align:center">'
                 f'… und {rest} weitere Zeilen (gesamt {len(rows)}) – vollständig im Cockpit / CSV-Export</td></tr>')
    info_html = (f'<div style="font-size:8pt;color:{MUTED};margin:2px 0 4px">{_esc(info)}</div>' if info else "")
    return (info_html + '<table style="width:100%;border-collapse:collapse;margin-bottom:6px">'
            f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")


def _tasklist_html(widget: dict, result: dict) -> str:
    """Aufgabenliste (Ampel + Anzahl + Text) für den PDF-Report."""
    AMPEL = {"rot": "#c0392b", "orange": "#d97b1f", "gelb": "#c9a71f", "gruen": "#3f8f45"}
    order = {"rot": 0, "orange": 1, "gelb": 2, "gruen": 3}
    rows = sorted(result.get("rows", []),
                  key=lambda r: (order.get(str(r.get("Ampel", "")).lower(), 9), r.get("sort", 99)))
    if not rows:
        return ""
    items = []
    for r in rows:
        col = AMPEL.get(str(r.get("Ampel", "")).lower(), "#999999")
        anz = r.get("Anzahl")
        anz_s = f"<b>{_esc(anz)}</b> &nbsp;" if anz not in (None, "") else ""
        items.append(f'<tr><td style="width:14px;color:{col};font-size:12pt">&#9679;</td>'
                     f'<td style="font-size:9pt;color:{DARK};padding:2px 0">{anz_s}{_esc(r.get("Aufgabe", ""))}</td></tr>')
    return (f'<div style="font-size:9pt;font-weight:bold;margin:4px 0 2px;color:{DARK}">{_esc(widget.get("label", ""))}</div>'
            f'<table style="width:100%;border-collapse:collapse;margin-bottom:8px">{"".join(items)}</table>')


def _alerts_html(widget: dict, result: dict) -> str:
    """Unternehmenswarnungen für den PDF-Report: Ampel, Titel, Fakten.
    Die Fakten stehen bewusst mit im Bericht – eine Warnung ohne ihre Grundlage
    ist im Papierausdruck nicht überprüfbar."""
    AMPEL = {"rot": "#c0392b", "orange": "#d97b1f", "gelb": "#c9a71f", "gruen": "#3f8f45"}
    rows = result.get("rows", []) or []
    if not rows:
        return ('<div style="font-size:9pt;color:#3f8f45;margin-bottom:6px">'
                'Keine offenen Warnungen – alle Prüfungen im grünen Bereich.</div>')
    items = []
    for r in rows:
        col = AMPEL.get(str(r.get("Ampel", "")).lower(), "#999999")
        fakten = "; ".join(f'{f.get("label")}: {f.get("wert")}{(" " + f.get("einheit")) if f.get("einheit") else ""}'
                           for f in (r.get("fakten") or []))
        unter = r.get("untertitel") or ""
        zusatz = " · ".join(x for x in (unter, fakten) if x)
        items.append(
            f'<tr><td style="width:14px;color:{col};font-size:12pt;vertical-align:top">&#9679;</td>'
            f'<td style="font-size:9pt;color:{DARK};padding:2px 0">'
            f'<b>{_esc(r.get("titel") or r.get("name", ""))}</b>'
            + (f'<div style="font-size:8pt;color:{MUTED}">{_esc(zusatz)}</div>' if zusatz else "")
            + '</td></tr>')
    return (f'<div style="font-size:9pt;font-weight:bold;margin:4px 0 2px;color:{DARK}">{_esc(widget.get("label", ""))}</div>'
            f'<table style="width:100%;border-collapse:collapse;margin-bottom:8px">{"".join(items)}</table>')


def _widgets_for_tab(schema: dict, action_ids: set) -> list:
    return [w for w in schema.get("widgets", [])
            if not action_ids or w.get("action_id") in action_ids]


def _render_tab(schema: dict, tab: dict, results: dict) -> str:
    aids = set(tab.get("action_ids") or [])
    widgets = _widgets_for_tab(schema, aids)
    parts = [f'<h2 style="color:{ACCENT};font-size:13pt;border-bottom:2px solid {ACCENT};'
             f'padding-bottom:3px">{_esc(tab.get("label",""))}</h2>']
    kpi_buffer = []

    def flush_kpis():
        if not kpi_buffer:
            return ""
        cells = "".join(kpi_buffer)
        kpi_buffer.clear()
        return f'<table style="width:100%;border-collapse:collapse;margin-bottom:8px"><tr>{cells}</tr></table>'

    for w in widgets:
        res = results.get(w.get("action_id"), {"columns": [], "rows": []})
        wt = w.get("type")
        if wt == "kpi":
            kpi_buffer.append(_kpi_cell(w, res))
            if len(kpi_buffer) == 3:
                parts.append(flush_kpis())
            continue
        parts.append(flush_kpis())
        if wt == "tasklist":
            parts.append(_tasklist_html(w, res))
        elif wt == "alerts":
            parts.append(_alerts_html(w, res))
        elif wt == "table":
            parts.append(f'<div style="font-size:9pt;font-weight:bold;margin:4px 0 2px;color:{DARK}">{_esc(w.get("label",""))}</div>')
            parts.append(_table_html(w, res))
        elif wt in ("bar", "line", "pie"):
            uri = _render_chart(w, res)
            if uri:
                parts.append(f'<div style="font-size:9pt;font-weight:bold;margin:4px 0 2px;color:{DARK}">{_esc(w.get("label",""))}</div>')
                parts.append(f'<img src="{uri}" width="470" />')
    parts.append(flush_kpis())
    return "".join(parts)


def _cover_filters(schema: dict, params: dict, conn_id: Optional[int]) -> str:
    lines = []
    for f in schema.get("fields", []):
        t = f.get("type"); cfg = f.get("config", {})
        if t == "daterange":
            pf = cfg.get("param_from", "von"); pt = cfg.get("param_to", "bis")
            v, b = params.get(pf), params.get(pt)
            if v or b:
                lines.append(("Zeitraum", f"{_esc(v)} – {_esc(b)}"))
        elif t == "db_dropdown":
            vals = params.get(f.get("name")) or []
            if not isinstance(vals, list):
                vals = [vals] if vals else []
            # Ohne Auswahl gar nicht aufführen – ein Feld, das nur einen Reiter steuert
            # (config.visible_tabs), gehört sonst als "alle" auf jedes Deckblatt.
            if not vals:
                continue
            labels = _lookup_labels(conn_id, cfg.get("kind", ""), vals)
            lines.append((_esc(f.get("label", f.get("name"))), ", ".join(labels) if labels else "alle"))
        elif t == "dropdown":
            v = params.get(f.get("name"))
            if v:
                lines.append((_esc(f.get("label", f.get("name"))), _esc(v)))
    rows = "".join(f'<tr><td style="padding:2px 8px 2px 0;color:{MUTED}">{k}</td>'
                   f'<td style="padding:2px 0;color:{DARK}"><b>{val}</b></td></tr>' for k, val in lines)
    return f'<table style="margin-top:10px">{rows}</table>'


def _report_kicker(form_name: str) -> str:
    """Zeile über dem Firmennamen: aus dem Formularnamen, damit im Lager-Report nicht
    "GESCHÄFTSFÜHRER-REPORT" steht. "Lager-Cockpit" → "LAGER-REPORT"."""
    name = (form_name or "").strip()
    if not name:
        return "REPORT"
    basis = re.sub(r"[-\s]*cockpit\s*$", "", name, flags=re.I).strip(" -–")
    return (basis or name).upper() + "-REPORT"


def _cover_html(company: dict, schema: dict, params: dict, conn_id: Optional[int], form_name: str) -> str:
    now = datetime.datetime.now().strftime("%d.%m.%Y")
    c = company or {}
    addr = "<br/>".join(filter(None, [
        _esc(c.get("cName")),
        _esc(c.get("cStrasse")),
        " ".join(filter(None, [_esc(c.get("cPLZ")), _esc(c.get("cOrt"))])),
        _esc(c.get("cLand")),
    ]))
    contact = "<br/>".join(filter(None, [
        (f'Tel.: {_esc(c.get("cTel"))}' if c.get("cTel") else ""),
        (f'{_esc(c.get("cEMail"))}' if c.get("cEMail") else ""),
        (f'{_esc(c.get("cWWW"))}' if c.get("cWWW") else ""),
        (f'St.-Nr.: {_esc(c.get("cSteuerNr"))}' if c.get("cSteuerNr") else ""),
    ]))
    return (
        f'<div style="margin-top:120px;text-align:center">'
        f'<div style="font-size:11pt;color:{MUTED};letter-spacing:2px">{_esc(_report_kicker(form_name))}</div>'
        f'<div style="font-size:24pt;font-weight:bold;color:{DARK};margin:8px 0">{_esc(c.get("cName") or form_name)}</div>'
        f'<div style="font-size:10pt;color:{MUTED}">{addr}</div>'
        f'<div style="font-size:9pt;color:{MUTED};margin-top:6px">{contact}</div>'
        f'<div style="margin:30px auto 0;width:60%">'
        f'<table style="width:100%;border-top:1px solid #ccc;border-bottom:1px solid #ccc;padding:8px 0">'
        f'<tr><td style="padding:4px 8px 4px 0;color:{MUTED}">Erstellt am</td><td style="padding:4px 0"><b>{now}</b></td></tr>'
        f'</table>'
        f'{_cover_filters(schema, params, conn_id)}'
        f'</div></div>'
    )


async def _ai_summary(schema: dict, results: dict, db, provider: Optional[str] = None) -> str:
    """Best-effort KI-Management-Summary aus dem Übersichts-KPI-Ergebnis."""
    try:
        ai_widget = next((w for w in schema.get("widgets", []) if w.get("type") == "ai_summary"), None)
        if not ai_widget:
            return ""
        res = results.get(ai_widget.get("action_id"))
        if not res or not res.get("rows"):
            return ""
        from app.api.ai import _require_ai
        # Anbieterwahl des Aufrufers durchreichen: über den Gateway ist die Analyse in
        # Sekunden fertig, das lokale Modell braucht auf CPU eine gute Minute.
        svc = _require_ai(db, provider)
        row = res["rows"][0]
        # Kennzahlen sauber mit Label, Einheit und Vorjahresvergleich aufbereiten,
        # damit die KID guten Fließtext schreibt (keine rohen Feldnamen).
        LABELS = {"Umsatz": ("Umsatz", "€"), "Rohertrag": ("Rohertrag (DB I)", "€"),
                  "DB2": ("Deckungsbeitrag II", "€"), "Marge": ("Marge", "%"),
                  "DB2Marge": ("DB-II-Marge", "%"), "Rechnungen": ("Rechnungen", ""),
                  "AktiveKunden": ("Aktive Kunden", ""), "AvgAuftrag": ("Ø Auftragswert", "€")}
        lines = []
        # Andere Cockpits (Lager, Einkauf …) haben ganz andere Kennzahlen – dort die
        # Zeile generisch aufbereiten statt eine leere Liste zu schicken.
        if not any(k in row for k in LABELS):
            LABELS = {k: (k, "") for k in row.keys() if not k.upper().endswith("VJ")}
        for key, (label, unit) in LABELS.items():
            if key not in row or row.get(key) is None:
                continue
            cur = row[key]
            line = f"{label}: {_fmt(cur, 0 if unit != '%' else 1)}{(' ' + unit) if unit else ''}"
            vj = row.get(key + "VJ")
            try:
                if vj not in (None, 0, ""):
                    pct = 100.0 * (float(cur) - float(vj)) / float(vj)
                    line += f" (Vorjahr {_fmt(vj, 0 if unit != '%' else 1)}{(' ' + unit) if unit else ''}, {pct:+.1f} %)"
            except (TypeError, ValueError):
                pass
            lines.append(line)

        # Zusatzbereiche des Widgets (config.extra_sections) mitgeben – dieselben, die
        # das Cockpit an die KI schickt. Ohne sie beurteilt der Report-Fallback nur die
        # Haupt-KPI-Zeile und ließe z.B. Einkauf und Verbindlichkeiten unter den Tisch.
        for sek in ((ai_widget.get("config") or {}).get("extra_sections") or []):
            srows = (results.get(sek.get("action_id")) or {}).get("rows") or []
            if not srows:
                continue
            if sek.get("kind") == "kpi":
                inhalt = ", ".join(f"{k}: {_fmt(v, 1) if _is_num(v) else v}"
                                   for k, v in srows[0].items() if v is not None)
            else:
                inhalt = f"{len(srows)} Einträge, größter: " + ", ".join(
                    f"{k}: {_fmt(v, 1) if _is_num(v) else v}"
                    for k, v in list(srows[0].items())[:4] if v is not None)
            lines.append(f"{sek.get('label') or sek.get('action_id')} – {inhalt}")

        # Die fachliche Vorgabe des Widgets (config.instruction) mitgeben – sie sagt,
        # worauf es im jeweiligen Cockpit ankommt (Lagerlage, Einkauf, …).
        anweisung = ((ai_widget.get("config") or {}).get("instruction") or "").strip()
        system = ("Du bist ein nüchterner Business-Analyst für einen Geschäftsführer. Schreibe eine "
                  "zusammenhängende Analyse in 4-6 vollständigen deutschen Sätzen (KEINE Aufzählung, "
                  "KEINE bloße Wiederholung der Zahlenliste): interpretiere die wichtigsten Werte, die "
                  "Entwicklung zum Vorjahr (mit dem angegebenen Prozentwert), die Ertragslage inkl. "
                  "Deckungsbeitrag und – falls erkennbar – den Handlungsbedarf. Nutze die Werte exakt, "
                  "rechne nichts neu. € = Euro, % = Prozent. Schreibe Zahlen deutsch: Dezimaltrennzeichen "
                  "ist das KOMMA, Tausender mit Punkt (6,6 %, nicht 6.6 %). Beginne direkt mit der Analyse – KEINE "
                  "Anrede, KEINE Briefformel, keine Grußformel. Gehe auf ALLE gelieferten Bereiche "
                  "ein – auch Einkauf/Verbindlichkeiten, Lager und Retouren – und nenne zu jedem "
                  "mindestens eine konkrete Zahl; überspringe nur Bereiche ohne Daten.")
        if anweisung:
            system += " Fachlicher Auftrag: " + anweisung
        # Textmodell wählen: beim lokalen Ollama das gewählte `ai_prose_model` (bzw. ein
        # bewährtes Instruct-Modell, aber IMMER installiert – sonst still Fehler), beim
        # Gateway-Provider dessen eigenes Modell.
        from app.services.ai_service import AIParams, resolve_prose_model
        chosen = await resolve_prose_model(db, svc)
        txt = await svc.complete_with_context(
            "Analysiere diese bereits berechneten Kennzahlen:\n" + "\n".join(lines), system,
            params=AIParams(think=False, temperature=0.4, top_p=0.9, max_tokens=420, num_ctx=8192),
            model=chosen)
        return (txt or "").strip()
    except Exception:
        return ""


# ── Report-Layout: Summary-Prosa + deterministische Bewertungstabelle ───────────

# Bewertungsmarker der KI: {+ erfreulich +} / {- kritisch -} (siehe Prompt in ai.py).
# Nur ein sauber geschlossenes Paar färbt ({+…+} / {-…-}); bei {+…-} wäre die Farbe
# geraten – dann bleiben nur die Klammern weg.
_MARKER_RE = re.compile(r"\{([+-])([\s\S]*?)\1\}")
_MARKER_REST_RE = re.compile(r"\{[+-]|[+-]\}")
GUT_FARBE, SCHLECHT_FARBE = "#3f8f45", "#c0392b"


def _fett_html(s: str) -> str:
    out = []
    for p in re.split(r"(\*\*[^*]+\*\*)", s):
        m = re.match(r"^\*\*([^*]+)\*\*$", p)
        out.append(f"<strong>{_esc(m.group(1))}</strong>"
                   if m else _esc(_MARKER_REST_RE.sub("", p)))
    return "".join(out)


def _inline_html(s: str) -> str:
    """**fett** → <strong>, {+…+}/{-…-} → grün/rot, Rest escapen. Halb geschriebene
    Marker werden entfernt statt als Text ausgegeben."""
    out, pos = [], 0
    for m in _MARKER_RE.finditer(s):
        if m.start() > pos:
            out.append(_fett_html(s[pos:m.start()]))
        farbe = GUT_FARBE if m.group(1) == "+" else SCHLECHT_FARBE
        out.append(f'<span style="color:{farbe};font-weight:bold">{_fett_html(m.group(2))}</span>')
        pos = m.end()
    out.append(_fett_html(s[pos:]))
    return "".join(out)


_LIST_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
_INLINE_NUM_RE = re.compile(r"(?:^|\s)(\d+)[.)]\s+")


def _inline_liste(text: str):
    """Aufzählung, die das Modell in EINEN Absatz gepackt hat, in Vorspann + Punkte
    zerlegen ("… Handlungsbedarf: 1. Erstens … 2. Zweitens …"). Nur bei mindestens
    zwei fortlaufenden Nummern, sonst zerfiele ein Satz mit Zahlenangaben."""
    treffer = [m for i, m in enumerate(_INLINE_NUM_RE.finditer(text))]
    folge = [m for idx, m in enumerate(t for t in treffer) if int(m.group(1)) == idx + 1]
    if len(folge) < 2:
        return None
    vorspann = text[:folge[0].start()].strip()
    punkte = []
    for idx, m in enumerate(folge):
        ende = folge[idx + 1].start() if idx + 1 < len(folge) else len(text)
        punkte.append(text[m.end():ende].strip())
    return vorspann, punkte


def _absatz_html(text: str) -> str:
    return (f'<p style="font-size:10pt;line-height:1.5;color:{DARK};margin:0 0 5pt">'
            f'{_inline_html(text)}</p>')


def _liste_html(punkte: list) -> str:
    lis = "".join(f'<li style="margin:0 0 3pt">{_inline_html(p)}</li>' for p in punkte)
    return (f'<ul style="font-size:10pt;line-height:1.5;color:{DARK};margin:0 0 6pt 12pt">'
            f'{lis}</ul>')


def _summary_to_html(summary: str) -> str:
    """Report-Prosa in echte HTML-Absätze und Listen wandeln (Zeilenumbrüche +
    **fett** bleiben erhalten – im PDF war zuvor alles zu einem Block zusammengelaufen,
    und Maßnahmenlisten standen als eine Textwurst da)."""
    zeilen = [ln.strip() for ln in re.split(r"\n+", summary or "") if ln.strip()]
    out, punkte = [], []
    for ln in zeilen:
        if _LIST_RE.match(ln):
            punkte.append(_LIST_RE.sub("", ln).strip())
            continue
        if punkte:
            out.append(_liste_html(punkte)); punkte = []
        zerlegt = _inline_liste(ln)
        if zerlegt:
            vorspann, items = zerlegt
            if vorspann:
                out.append(_absatz_html(vorspann))
            out.append(_liste_html(items))
        else:
            out.append(_absatz_html(ln))
    if punkte:
        out.append(_liste_html(punkte))
    return "".join(out)


def _asnum(v):
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _apct(cur, vj):
    c, v = _asnum(cur), _asnum(vj)
    return None if (c is None or v is None or v == 0) else 100.0 * (c - v) / v


def _spct(p):
    return "–" if p is None else f"{p:+.1f} %".replace(".", ",")


def _eur(v):
    return "–" if _asnum(v) is None else _fmt(v, 0) + " €"


def _pctval(v):
    return "–" if _asnum(v) is None else _fmt(v, 1) + " %"


# Action-IDs, die die Bewertungstabelle auswertet. Wird die Bewertung angefordert,
# müssen diese Abfragen auch dann laufen, wenn ihr Reiter abgewählt wurde.
_ASSESSMENT_ACTION_IDS = {
    # GF-Cockpit
    "act_overview_kpi", "act_kunden_kpi", "act_kunden_rueckgang", "act_zm_kpi",
    "act_op_kpi", "act_kapital_kpi", "act_klumpen_kpi", "act_forecast",
    "act_churn", "act_retouren_kpi",
    # Lager-Cockpit
    "act_lg_kpi", "act_lg_dispo_kpi", "act_lg_umschlag_kpi", "act_lg_lh_kpi",
    "act_lg_schwund_kpi",
    # Vertriebs-Cockpit
    "act_ve_kpi", "act_ve_angebot_kpi", "act_ve_rueckgang", "act_ve_churn",
    # Einkaufs-Cockpit
    "act_ek_kpi", "act_ek_termintreue_kpi", "act_ek_offen_kpi", "act_ek_er_kpi",
    # Versand-Cockpit
    "act_vs_kpi", "act_vs_dauer_kpi", "act_vs_tracking_kpi",
    # Stammdaten-Health-Check
    "act_hc_kpi", "act_hc_summary", "act_hc_luecken",
}


def _assessment_rows(results: dict) -> list:
    """Deterministische Bewertung je Cockpit-Bereich – identisch zur Frontend-Logik
    (buildAssessment in AiSummaryWidget.tsx). Gibt (Bereich, gut?, Kommentar)-Tupel."""
    def rows_of(aid):
        return (results.get(aid) or {}).get("rows") or []

    def one(aid):
        rs = rows_of(aid)
        return rs[0] if rs else None

    out = []
    ov = one("act_overview_kpi")
    if ov:
        p = _apct(ov.get("Umsatz"), ov.get("UmsatzVJ"))
        out.append(("Ertragslage", p is None or p >= 0,
                    f"Umsatz {_spct(p)} ggü. Vorjahr, DB II-Marge {_pctval(ov.get('DB2Marge'))}"))
    kk = one("act_kunden_kpi")
    decl = rows_of("act_kunden_rueckgang")
    if kk or decl:
        ap = _apct(ov.get("AktiveKunden"), ov.get("AktiveKundenVJ")) if ov else None
        decl_sum = sum((_asnum(r.get("Rueckgang")) or 0) for r in decl)
        good = (ap is None or ap >= 0) and len(decl) <= 5
        neu = f"{_fmt(kk.get('Neukunden'), 0)} Neukunden, " if kk and kk.get("Neukunden") is not None else ""
        out.append(("Kunden", good, f"{neu}{len(decl)} Kunden rückläufig (−{_eur(decl_sum)})"))
    zm = one("act_zm_kpi")
    op = one("act_op_kpi")
    if zm or op:
        zd = _asnum(zm.get("ZahldauerTage")) if zm else None
        zdv = _asnum(zm.get("ZahldauerTageVJ")) if zm else None
        uq = _asnum(op.get("UeberfaelligQuote")) if op else None
        good = (zd is None or zdv is None or zd <= zdv) and (uq is None or uq < 25)
        parts = []
        if op:
            parts.append(f"überfällig {_pctval(op.get('UeberfaelligQuote'))}")
            if op.get("DSO") is not None:
                parts.append(f"DSO {_fmt(op.get('DSO'), 1)}")
        if zm:
            parts.append(f"Zahldauer {_fmt(zm.get('ZahldauerTage'), 1)} Tage")
        out.append(("Liquidität", good, ", ".join(parts)))
    kap = one("act_kapital_kpi")
    if kap:
        bind = _asnum(kap.get("Kapitalbindung"))
        lh = _asnum(kap.get("LadenhueterKapital"))
        share = (lh / bind) if (bind and lh is not None) else None
        out.append(("Kapital & Lager", share is None or share < 0.15,
                    f"{_eur(kap.get('Kapitalbindung'))} gebunden, davon {_eur(kap.get('LadenhueterKapital'))} Ladenhüter"))
    kl = one("act_klumpen_kpi")
    if kl:
        t5 = _asnum(kl.get("Top5KundenAnteil"))
        out.append(("Risiko", t5 is None or t5 < 30,
                    f"Top-5-Kunden {_pctval(kl.get('Top5KundenAnteil'))}, Top-10 {_pctval(kl.get('Top10KundenAnteil'))}"))
    fc = one("act_forecast")
    churn_n = len(rows_of("act_churn"))
    if fc:
        pv = _asnum(fc.get("Prognose vs VJ %"))
        out.append(("Ausblick", pv is None or pv >= 0,
                    f"Prognose {_spct(pv)} ggü. Vorjahr" + (f", {churn_n} schlafende Kunden" if churn_n else "")))
    # ── Lager-Cockpit ──────────────────────────────────────────────────────────
    # Schwellen identisch zu buildAssessment in AiSummaryWidget.tsx.
    lg = one("act_lg_kpi")
    if lg:
        p = _apct(lg.get("Lagerwert"), lg.get("LagerwertVJ"))
        ohne_ek = _asnum(lg.get("OhneHistorischenEK")) or 0
        out.append(("Lagerbestand", p is None or p <= 10,
                    f"{_eur(lg.get('Lagerwert'))} zum historischen EK ({_spct(p)} ggü. Vorjahr)"
                    + (f", {_fmt(ohne_ek, 0)} Artikel ohne gebuchten EK" if ohne_ek else "")))
    dp = one("act_lg_dispo_kpi")
    if dp:
        fehl = _asnum(dp.get("ArtikelFehlmenge")) or 0
        basis = _asnum(lg.get("ArtikelMitBestand")) if lg else None
        quote = (100.0 * fehl / basis) if basis else None
        neg = _asnum(dp.get("NegativerBestand")) or 0
        good = neg == 0 and (quote is None or quote < 5)
        out.append(("Disposition", good,
                    f"{_fmt(fehl, 0)} Artikel mit Fehlmenge ({_eur(dp.get('WertFehlmenge'))})"
                    + (f", {_fmt(neg, 0)} mit negativem Bestand" if neg else "")))
    um = one("act_lg_umschlag_kpi")
    if um:
        rw = _asnum(um.get("ReichweiteTage"))
        out.append(("Umschlag", rw is None or rw <= 180,
                    f"Ø {_fmt(um.get('UmschlagDurchschnitt'), 1)} Umschläge/Jahr, "
                    f"Reichweite {_fmt(um.get('ReichweiteTage'), 0)} Tage, "
                    f"{_fmt(um.get('OhneAbgang12M'), 0)} Artikel ohne Abgang ({_eur(um.get('KapitalOhneAbgang'))})"))
    lh = one("act_lg_lh_kpi")
    if lh:
        anteil = _asnum(lh.get("Anteil am Lagerwert %"))
        out.append(("Ladenhüter", anteil is None or anteil < 15,
                    f"{_fmt(lh.get('Ladenhueter'), 0)} Ladenhüter, {_eur(lh.get('GebundenesKapital'))} gebunden "
                    f"({_pctval(lh.get('Anteil am Lagerwert %'))} des Lagerwerts)"))
    sw = one("act_lg_schwund_kpi")
    if sw:
        wert = abs(_asnum(sw.get("WertNetto")) or 0)
        basis = _asnum(lg.get("Lagerwert")) if lg else None
        good = (not basis) or (wert / basis < 0.01)
        betroffen = _asnum(sw.get("BetroffeneArtikel")) or 0
        out.append(("Inventur & Schwund", good,
                    f"{_fmt(sw.get('Buchungen'), 0)} Korrekturbuchungen, netto {_eur(sw.get('WertNetto'))}"
                    + (f", {_fmt(betroffen, 0)} Artikel betroffen" if betroffen else "")))

    # ── Vertriebs-Cockpit ──────────────────────────────────────────────────────
    ve = one("act_ve_kpi")
    if ve:
        p = _apct(ve.get("Auftragseingang"), ve.get("AuftragseingangVJ"))
        st = _asnum(ve.get("StornoQuote"))
        out.append(("Auftragseingang", p is None or p >= 0,
                    f"{_eur(ve.get('Auftragseingang'))} ({_spct(p)} ggü. Vorjahr), "
                    f"Ø Auftrag {_eur(ve.get('AvgAuftrag'))}"
                    + (f", Storno {_pctval(st)}" if st is not None else "")))
    ag = one("act_ve_angebot_kpi")
    if ag:
        cq = _asnum(ag.get("ConversionQuote"))
        # Unter einem Drittel gewonnener Angebote lohnt der Blick auf die Nachfassliste.
        out.append(("Angebote", cq is None or cq >= 33,
                    f"{_fmt(ag.get('Angebote'), 0)} Angebote über {_eur(ag.get('Angebotsvolumen'))}, "
                    f"Conversion {_pctval(ag.get('ConversionQuote'))}"))
    ve_decl = rows_of("act_ve_rueckgang")
    ve_churn = rows_of("act_ve_churn")
    if ve_decl or ve_churn:
        summe = sum((_asnum(r.get("Rueckgang")) or 0) for r in ve_decl)
        out.append(("Kundenbindung", len(ve_decl) <= 5,
                    f"{len(ve_decl)} Kunden rückläufig (−{_eur(summe)})"
                    + (f", {len(ve_churn)} schlafende Kunden" if ve_churn else "")))

    # ── Einkaufs-Cockpit ───────────────────────────────────────────────────────
    ek = one("act_ek_kpi")
    if ek:
        p = _apct(ek.get("Bestellvolumen"), ek.get("BestellvolumenVJ"))
        out.append(("Einkaufsvolumen", p is None or p <= 10,
                    f"{_eur(ek.get('Bestellvolumen'))} ({_spct(p)} ggü. Vorjahr) bei "
                    f"{_fmt(ek.get('Lieferanten'), 0)} Lieferanten"))
    tt = one("act_ek_termintreue_kpi")
    if tt:
        q = _asnum(tt.get("TermintreueQuote"))
        out.append(("Termintreue", q is None or q >= 80,
                    f"{_pctval(tt.get('TermintreueQuote'))} pünktlich bei "
                    f"{_fmt(tt.get('Lieferungen'), 0)} Lieferungen, Ø Verzug "
                    f"{_fmt(tt.get('AvgVerzugTage'), 1)} Tage"))
    eo = one("act_ek_offen_kpi")
    if eo:
        offen = _asnum(eo.get("OffeneBestellungen")) or 0
        ueber = _asnum(eo.get("Ueberfaellig")) or 0
        anteil = (100.0 * ueber / offen) if offen else None
        out.append(("Offene Bestellungen", anteil is None or anteil < 20,
                    f"{_fmt(offen, 0)} offen ({_eur(eo.get('OffenerWert'))}), davon "
                    f"{_fmt(ueber, 0)} überfällig"))
    er = one("act_ek_er_kpi")
    if er:
        offen_n = _asnum(er.get("OffeneRechnungen")) or 0
        ueber_n = _asnum(er.get("Ueberfaellig")) or 0
        anteil = (100.0 * ueber_n / offen_n) if offen_n else None
        out.append(("Verbindlichkeiten", anteil is None or anteil < 10,
                    f"{_eur(er.get('OffeneVerbindlichkeiten'))} offen "
                    f"({_fmt(offen_n, 0)} Rechnungen), davon {_fmt(ueber_n, 0)} überfällig"))

    # ── Versand-Cockpit ────────────────────────────────────────────────────────
    vs = one("act_vs_kpi")
    if vs:
        d, dvj = _asnum(vs.get("AvgDauerStunden")), _asnum(vs.get("AvgDauerStundenVJ"))
        # Schneller als im Vorjahr oder unter zwei Tagen = in Ordnung.
        good = d is None or (dvj is not None and d <= dvj) or d <= 48
        p = _apct(vs.get("Sendungen"), vs.get("SendungenVJ"))
        out.append(("Versandvolumen", good,
                    f"{_fmt(vs.get('Sendungen'), 0)} Sendungen ({_spct(p)} ggü. Vorjahr), "
                    f"Ø Laufzeit {_fmt(d, 1)} h"
                    + (f" (VJ {_fmt(dvj, 1)} h)" if dvj is not None else "")))
    vd = one("act_vs_dauer_kpi")
    if vd:
        q48 = _asnum(vd.get("Bis48hQuote"))
        ueber72 = _asnum(vd.get("Ueber72h")) or 0
        out.append(("Lieferzeit", q48 is None or q48 >= 80,
                    f"{_pctval(vd.get('SelberTagQuote'))} am selben Tag, "
                    f"{_pctval(vd.get('Bis48hQuote'))} binnen 48 h, "
                    f"{_fmt(ueber72, 0)} Sendungen über 72 h"))
    vt = one("act_vs_tracking_kpi")
    if vt:
        q = _asnum(vt.get("TrackingQuote"))
        out.append(("Sendungsverfolgung", q is None or q >= 90,
                    f"Tracking bei {_pctval(vt.get('TrackingQuote'))} der Sendungen, "
                    f"{_fmt(vt.get('OhneTracking'), 0)} ohne Nummer"))

    # ── Stammdaten-Health-Check ────────────────────────────────────────────────
    # Momentaufnahme ohne Vorjahresvergleich: bewertet werden Lückenquoten, nicht
    # Veränderungen. Schwellen identisch zu buildAssessment in AiSummaryWidget.tsx.
    hc = one("act_hc_kpi")
    if hc:
        chk = {}                                     # check_key → Anzahl (Ampel-Übersicht)
        for r in rows_of("act_hc_summary"):
            chk[r.get("check_key")] = _asnum(r.get("Anzahl")) or 0
        gap = {}                                     # Feld → Lückenanteil in %
        for r in rows_of("act_hc_luecken"):
            gap[r.get("Feld")] = _asnum(r.get("Anteil"))
        LUECKE_OK = 5.0                              # bis 5 % fehlende Werte je Feld

        voll = _asnum(hc.get("Vollstaendigkeit"))
        out.append(("Vollständigkeit", voll is None or voll >= 90,
                    f"{_pctval(hc.get('Vollstaendigkeit'))} der Artikel ohne Lücke "
                    f"({_fmt(hc.get('ArtikelMitLuecke'), 0)} von "
                    f"{_fmt(hc.get('AktiveArtikel'), 0)} unvollständig)"))

        ean_anteil, ean_dop = gap.get("EAN/Barcode"), chk.get("ean_doppelt") or 0
        out.append(("EAN & Eindeutigkeit",
                    (ean_anteil is None or ean_anteil <= LUECKE_OK) and not ean_dop,
                    f"{_fmt(chk.get('artikel_ohne_ean'), 0)} Artikel ohne EAN "
                    f"({_pctval(ean_anteil)})"
                    + (f", {_fmt(ean_dop, 0)} mehrfach vergebene EAN" if ean_dop else "")))

        ek_anteil, verlust = gap.get("Einkaufspreis"), chk.get("artikel_vk_unter_ek") or 0
        # VK unter EK ist kein Lückenproblem, sondern ein Verlustgeschäft – jeder Fall zählt.
        out.append(("Preise & Marge",
                    (ek_anteil is None or ek_anteil <= LUECKE_OK) and verlust == 0,
                    f"{_fmt(chk.get('artikel_ohne_ek'), 0)} Artikel ohne Einkaufspreis "
                    f"({_pctval(ek_anteil)}), {_fmt(verlust, 0)} mit VK unter EK"))

        taric, herk = gap.get("Warentarifnummer"), gap.get("Herkunftsland")
        out.append(("Außenhandel",
                    (taric is None or taric <= LUECKE_OK) and (herk is None or herk <= LUECKE_OK),
                    f"{_fmt(chk.get('artikel_ohne_taric'), 0)} ohne Warentarifnummer "
                    f"({_pctval(taric)}), {_fmt(chk.get('artikel_ohne_herkunftsland'), 0)} "
                    f"ohne Herkunftsland ({_pctval(herk)})"))

        gew, ohne_name = gap.get("Gewicht"), chk.get("artikel_ohne_name") or 0
        out.append(("Logistik & Struktur",
                    (gew is None or gew <= LUECKE_OK) and ohne_name == 0,
                    f"{_fmt(chk.get('artikel_ohne_gewicht'), 0)} Artikel ohne Gewicht "
                    f"({_pctval(gew)}), {_fmt(chk.get('artikel_ohne_warengruppe'), 0)} "
                    f"ohne Warengruppe"
                    + (f", {_fmt(ohne_name, 0)} ohne Bezeichnung" if ohne_name else "")))

        kunden = _asnum(hc.get("AktiveKunden"))
        ohne_mail = _asnum(hc.get("KundenOhneMail")) or 0
        mail_quote = (100.0 * ohne_mail / kunden) if kunden else None
        # Ohne E-Mail keine Versandbenachrichtigung und keine digitale Rechnung –
        # bis zu einem Fünftel der Kunden ist im B2B-Bestand aber üblich.
        out.append(("Kundenstamm", mail_quote is None or mail_quote <= 20,
                    f"{_fmt(ohne_mail, 0)} von {_fmt(kunden, 0)} Kunden ohne E-Mail "
                    f"({_pctval(mail_quote)})"
                    + (f", {_fmt(chk.get('kunden_dubletten'), 0)} mögliche Dubletten"
                       if chk.get("kunden_dubletten") else "")))

    rt = one("act_retouren_kpi")
    if rt:
        q, qvj = _asnum(rt.get("Quote")), _asnum(rt.get("QuoteVJ"))
        # Niedrige Retourenquote (< 5 %) ist generell gut; erst darüber zählt zusätzlich
        # der Vorjahresvergleich (nicht gestiegen).
        RET_QUOTE_OK = 5.0
        good = q is None or q < RET_QUOTE_OK or (qvj is not None and q <= qvj)
        chg = _apct(q, qvj)
        out.append(("Retouren", good,
                    f"Retourenquote {_pctval(rt.get('Quote'))} (VJ {_pctval(rt.get('QuoteVJ'))}"
                    + (f", {_spct(chg)}" if chg is not None else "") + f"), Wert {_eur(rt.get('Wert'))}"))
    return out


def _assessment_html(rows: list) -> str:
    if not rows:
        return ""
    th = (f'style="padding:3pt 5pt;border-bottom:1.5px solid {ACCENT};font-size:9pt;'
          f'text-align:left;color:{ACCENT}"')
    head = (f'<h2 style="color:{ACCENT};font-size:12pt;border-bottom:1px solid {ACCENT};'
            f'padding-bottom:2px;margin-top:12pt">Bewertung</h2>'
            f'<table style="width:100%;border-collapse:collapse;margin-top:4pt">'
            f'<tr><th {th}>Bereich</th><th {th}>Status</th><th {th}>Kommentar</th></tr>')
    trs = []
    for bereich, good, kommentar in rows:
        color = "#2e7d32" if good else "#c98a1c"
        status = "gut" if good else "verbesserungswürdig"
        trs.append(
            f'<tr><td style="padding:3pt 5pt;border-bottom:0.5px solid #ddd;font-size:9pt;'
            f'font-weight:bold;color:{DARK}">{_esc(bereich)}</td>'
            f'<td style="padding:3pt 5pt;border-bottom:0.5px solid #ddd;font-size:9pt;'
            f'font-weight:bold;color:{color}">{_esc(status)}</td>'
            f'<td style="padding:3pt 5pt;border-bottom:0.5px solid #ddd;font-size:9pt;'
            f'color:{DARK}">{_esc(kommentar)}</td></tr>')
    return head + "".join(trs) + "</table>"


SECTION_SUMMARY = "__summary__"
SECTION_ASSESSMENT = "__assessment__"


async def generate_report(form, params: dict, db, precomputed_summary: str | None = None,
                          sections: Optional[list] = None,
                          provider: Optional[str] = None) -> bytes:
    """sections: Auswahl aus dem Report-Dialog – Reiter-IDs plus die Pseudo-IDs
    SECTION_SUMMARY / SECTION_ASSESSMENT. None = kompletter Report (wie bisher)."""
    schema = form.schema or {}
    conn_id = _resolve_conn_id(schema, db)
    company = _fetch_company(conn_id)

    # Projektbezogene Schwellwerte als :cfg_<key> mitgeben – sonst liefen Mappings,
    # die einen Schwellwert referenzieren, im Report ohne gebundenen Parameter.
    from app.services.business_config_service import apply_config as _apply_cfg
    params = _apply_cfg(params or {}, getattr(form, "project_id", None), db)

    tabs = schema.get("result_tabs") or []
    if not tabs:  # ohne Reiter: ein einziger Block über alle Actions
        tabs = [{"id": "all", "label": form.name or "Bericht",
                 "action_ids": [a.get("id") for a in schema.get("actions", [])]}]

    ai_widget = next((w for w in schema.get("widgets", []) if w.get("type") == "ai_summary"), None)
    is_report = bool((ai_widget or {}).get("config", {}).get("report_layout"))

    # Abschnittsauswahl auswerten: Reiter filtern, KI-Summary/Bewertung ein-/ausschalten
    # und daraus die wirklich benötigten Mapping-Actions ableiten.
    sel = set(sections) if sections is not None else None
    want_summary = SECTION_SUMMARY in sel if sel is not None else True
    want_assessment = (SECTION_ASSESSMENT in sel if sel is not None else True) and is_report
    if sel is not None:
        tabs = [t for t in tabs if t.get("id") in sel]

    only_ids = None
    if sel is not None:
        only_ids = set()
        for t in tabs:
            only_ids.update(t.get("action_ids") or [])
        if want_assessment:
            only_ids |= _ASSESSMENT_ACTION_IDS
        if want_summary and ai_widget and ai_widget.get("action_id"):
            only_ids.add(ai_widget["action_id"])

    results = _run_actions(schema, params, db, only_ids)

    # Unternehmenswarnungen (Action-Typ run_alerts) laufen nicht über _run_actions,
    # weil sie selbst mehrere Mappings auswerten. persist=False: ein Report soll den
    # Verlauf der Warnungs-Läufe nicht verfälschen.
    for _a in schema.get("actions", []):
        if _a.get("type") != "run_alerts":
            continue
        if only_ids is not None and _a.get("id") not in only_ids:
            continue
        try:
            from app.services import alert_service as _alert_service
            _o = _a.get("options") or {}
            _lauf = _alert_service.evaluate(db, getattr(form, "project_id", None),
                                            params, persist=False,
                                            rule_keys=_o.get("rule_keys") or None,
                                            cockpits=_o.get("cockpits") or None)
            results[_a["id"]] = {"columns": [], "rows": _lauf.get("alerts") or []}
        except Exception:
            results[_a["id"]] = {"columns": [], "rows": []}
    # Wenn das Formular seine KI-Analyse schon erzeugt hat (Client), diese direkt
    # übernehmen – spart den langsamen, timeout-gefährdeten KI-Aufruf im Report.
    if not want_summary:
        summary = ""
    elif precomputed_summary and precomputed_summary.strip():
        summary = precomputed_summary.strip()
    else:
        try:
            summary = await asyncio.wait_for(_ai_summary(schema, results, db, provider),
                                             timeout=_SUMMARY_TIMEOUT_S)
        except Exception:
            summary = ""  # KI zu langsam/nicht verfügbar → Report ohne Summary

    body = [_cover_html(company, schema, params, conn_id, form.name or "Report")]
    if summary or want_assessment:
        body.append(
            f'<div style="page-break-before:always"></div>'
            f'<h2 style="color:{ACCENT};font-size:13pt;border-bottom:2px solid {ACCENT};padding-bottom:3px">'
            f'Management-Summary</h2>')
        if summary:
            # Report-Prosa als Absätze (mit **fett**); sonst einfacher Fließtext.
            # Der ausführliche Detailgrad liefert auch ohne report_layout **fette Labels** –
            # daher am Text erkennen statt nur an der Widget-Konfiguration.
            body.append(_summary_to_html(summary) if (is_report or "**" in summary)
                        else f'<p style="font-size:10pt;line-height:1.5;color:{DARK}">'
                             f'{_inline_html(summary)}</p>')
        if want_assessment:
            body.append(_assessment_html(_assessment_rows(results)))
    for tab in tabs:
        body.append(f'<div style="page-break-before:always"></div>')
        body.append(_render_tab(schema, tab, results))

    now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    html_doc = (
        '<html><head><meta charset="utf-8"><style>'
        '@page { size: A4; margin: 1.6cm; @frame footer { -pdf-frame-content: footerContent; '
        'bottom: 0.8cm; margin-left: 1.6cm; margin-right: 1.6cm; height: 1cm; } }'
        'body { font-family: Helvetica, Arial, sans-serif; color: #222; }'
        '</style></head><body>'
        + "".join(body)
        + f'<div id="footerContent" style="font-size:7pt;color:#999;text-align:center">'
          f'{_esc(company.get("cName") or "")} · Report erstellt {now} · Seite <pdf:pagenumber> von <pdf:pagecount></div>'
        + '</body></html>'
    )
    out = io.BytesIO()
    pisa.CreatePDF(io.StringIO(html_doc), dest=out, encoding="utf-8")
    return out.getvalue()
