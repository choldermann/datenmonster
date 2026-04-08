"""
pdf_service – generiert PDF aus Report-Widgets.

Nutzt xhtml2pdf (reine Python, keine System-Deps).
Fallback auf ReportLab wenn xhtml2pdf nicht verfügbar.
"""
import io
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# ─── HTML-Template für den Report-PDF ─────────────────────────────────────────

_PAGE_CSS = """
@page {
  size: A4 landscape;
  margin: 15mm 12mm 15mm 12mm;
  @top-center {
    content: element(header);
  }
}
body {
  font-family: Helvetica, Arial, sans-serif;
  font-size: 10pt;
  color: #1a1a1a;
  background: #ffffff;
  margin: 0; padding: 0;
}
h1 {
  font-size: 16pt;
  font-weight: 800;
  color: #1a1a1a;
  margin: 0 0 4px 0;
}
.meta {
  font-size: 8pt;
  color: #888;
  margin: 0 0 16px 0;
}
.widget-grid {
  width: 100%;
}
.widget {
  display: inline-block;
  vertical-align: top;
  margin: 0 8px 16px 0;
  border: 1px solid #e5e5e5;
  border-radius: 6px;
  padding: 12px;
  background: #fff;
  box-sizing: border-box;
}
.widget-title {
  font-size: 9pt;
  font-weight: 700;
  color: #555;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin: 0 0 10px 0;
  border-bottom: 1px solid #f0f0f0;
  padding-bottom: 6px;
}
.kpi-value {
  font-size: 28pt;
  font-weight: 800;
  color: #d4af37;
  text-align: center;
  margin: 8px 0 4px 0;
}
.kpi-label {
  font-size: 8pt;
  color: #888;
  text-align: center;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 9pt;
}
th {
  background: #f7f7f7;
  font-weight: 700;
  text-align: left;
  padding: 5px 8px;
  border-bottom: 2px solid #e0e0e0;
  white-space: nowrap;
}
td {
  padding: 4px 8px;
  border-bottom: 1px solid #f0f0f0;
}
tr:nth-child(even) td {
  background: #fafafa;
}
.footer {
  font-size: 7pt;
  color: #aaa;
  text-align: right;
  margin-top: 8px;
}
.chart-placeholder {
  background: #f7f7f7;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #aaa;
  font-size: 9pt;
  min-height: 80px;
  text-align: center;
  padding: 16px;
}
"""


def _widget_to_html(widget: Dict, data: List[Dict]) -> str:
    """Rendert ein einzelnes Widget als HTML-Block."""
    wtype  = widget.get("type", "")
    title  = widget.get("title", "")
    config = widget.get("config", {})
    rows   = data or []

    html = f'<div class="widget" style="width:48%;">\n'
    if title:
        html += f'  <div class="widget-title">{title}</div>\n'

    if wtype == "kpi":
        value_field = config.get("value_field", "")
        agg         = config.get("agg", "SUM")
        fmt         = config.get("format", "")
        unit        = config.get("unit", "")
        label       = config.get("label", "")

        if rows and value_field:
            vals = [float(r.get(value_field) or 0) for r in rows]
            if agg == "SUM":    val = sum(vals)
            elif agg == "COUNT": val = len(vals)
            elif agg == "AVG":  val = sum(vals) / len(vals) if vals else 0
            elif agg == "MIN":  val = min(vals) if vals else 0
            elif agg == "MAX":  val = max(vals) if vals else 0
            else:               val = vals[0] if vals else 0

            if fmt == "currency":
                formatted = f"{val:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
            elif fmt == "percent":
                formatted = f"{val:.1f}%"
            else:
                formatted = f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        else:
            formatted = "–"

        if label:
            html += f'  <div class="kpi-label">{label}</div>\n'
        html += f'  <div class="kpi-value">{formatted}</div>\n'
        if unit:
            html += f'  <div class="kpi-label">{unit}</div>\n'

    elif wtype == "table":
        cols = config.get("columns") or (list(rows[0].keys()) if rows else [])
        max_rows = min(len(rows), 50)  # PDF: max 50 Zeilen pro Tabelle

        html += '  <table>\n    <thead><tr>\n'
        for c in cols:
            html += f'      <th>{c}</th>\n'
        html += '    </tr></thead>\n    <tbody>\n'
        for row in rows[:max_rows]:
            html += '    <tr>'
            for c in cols:
                val = row.get(c, "")
                html += f'<td>{val if val is not None else ""}</td>'
            html += '</tr>\n'
        if len(rows) > max_rows:
            html += f'    <tr><td colspan="{len(cols)}" style="color:#888;font-style:italic;">... {len(rows) - max_rows} weitere Zeilen</td></tr>\n'
        html += '    </tbody>\n  </table>\n'

    elif wtype in ("bar", "line", "pie", "heatmap"):
        # Charts werden als Tabelle gerendert (Charts brauchen JS)
        x_field      = config.get("x_field", "")
        value_fields = config.get("value_fields", [])
        if not value_fields and config.get("value_field"):
            value_fields = [config["value_field"]]

        if rows and (x_field or value_fields):
            show_cols = ([x_field] if x_field else []) + value_fields
            show_cols = [c for c in show_cols if c and c in (rows[0] if rows else {})]
            if not show_cols:
                show_cols = list(rows[0].keys())[:4]
            max_rows = min(len(rows), 30)

            html += f'  <div style="font-size:8pt;color:#888;margin-bottom:4px;">{'Balken' if wtype=='bar' else 'Linie' if wtype=='line' else 'Torte' if wtype=='pie' else 'Heatmap'}-Diagramm (Tabelle)</div>\n'
            html += '  <table>\n    <thead><tr>\n'
            for c in show_cols:
                html += f'      <th>{c}</th>\n'
            html += '    </tr></thead>\n    <tbody>\n'
            for row in rows[:max_rows]:
                html += '    <tr>'
                for c in show_cols:
                    val = row.get(c, "")
                    html += f'<td>{val if val is not None else ""}</td>'
                html += '</tr>\n'
            html += '    </tbody>\n  </table>\n'
        else:
            html += '  <div class="chart-placeholder">Keine Daten</div>\n'
    else:
        html += '  <div class="chart-placeholder">–</div>\n'

    html += '</div>\n'
    return html


def generate_report_pdf(
    report_name: str,
    widgets: List[Dict],
    widget_data: Dict[str, List[Dict]],
    created_at: Optional[str] = None,
) -> bytes:
    """
    Generiert einen PDF-Bericht aus Report-Widgets und deren Daten.

    widget_data: { widget_id: [{ col: val, ... }, ...] }
    Gibt PDF-Bytes zurück.
    """
    from datetime import datetime

    ts = created_at or datetime.now().strftime("%d.%m.%Y %H:%M")

    # HTML zusammenbauen
    body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>{_PAGE_CSS}</style>
</head>
<body>
  <h1>{report_name}</h1>
  <p class="meta">Erstellt: {ts} · {len(widgets)} Widget{'s' if len(widgets) != 1 else ''}</p>
  <div class="widget-grid">
"""
    for widget in widgets:
        wid  = widget.get("id", "")
        data = widget_data.get(wid, [])
        body += _widget_to_html(widget, data)

    body += """  </div>
  <div class="footer">Datenmonster ETL – automatisch generiert</div>
</body>
</html>"""

    # PDF rendern
    try:
        from xhtml2pdf import pisa
        buf = io.BytesIO()
        result = pisa.CreatePDF(body, dest=buf, encoding="utf-8")
        if result.err:
            raise RuntimeError(f"xhtml2pdf Fehler: {result.err}")
        return buf.getvalue()
    except ImportError:
        logger.warning("xhtml2pdf nicht installiert – Fallback auf ReportLab")
        return _reportlab_fallback(report_name, widgets, widget_data, ts)


def _reportlab_fallback(report_name, widgets, widget_data, ts) -> bytes:
    """Einfaches ReportLab-PDF falls xhtml2pdf nicht verfügbar."""
    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib import colors
        from reportlab.lib.units import mm

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                                leftMargin=15*mm, rightMargin=15*mm,
                                topMargin=15*mm, bottomMargin=15*mm)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph(report_name, styles["Title"]))
        story.append(Paragraph(f"Erstellt: {ts}", styles["Normal"]))
        story.append(Spacer(1, 12))

        for widget in widgets:
            wid    = widget.get("id", "")
            title  = widget.get("title", "")
            wtype  = widget.get("type", "")
            config = widget.get("config", {})
            rows   = widget_data.get(wid, [])

            if title:
                story.append(Paragraph(f"<b>{title}</b>", styles["Heading3"]))

            if wtype == "kpi":
                vf  = config.get("value_field", "")
                val = sum(float(r.get(vf) or 0) for r in rows) if rows and vf else 0
                story.append(Paragraph(f"<font size='20'><b>{val:,.2f}</b></font>", styles["Normal"]))

            elif rows:
                cols = list(rows[0].keys())[:8]
                data_table = [cols] + [[str(r.get(c, "")) for c in cols] for r in rows[:40]]
                t = Table(data_table, repeatRows=1)
                t.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
                    ("FONTSIZE",   (0, 0), (-1, -1), 8),
                    ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
                ]))
                story.append(t)

            story.append(Spacer(1, 12))

        doc.build(story)
        return buf.getvalue()

    except ImportError:
        raise RuntimeError(
            "Weder xhtml2pdf noch reportlab ist installiert. "
            "Bitte 'xhtml2pdf' oder 'reportlab' zu requirements.txt hinzufügen."
        )
