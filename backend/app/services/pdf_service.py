"""
pdf_service – generiert PDF aus Report-Widgets mit echten Matplotlib-Charts.
"""
import base64
import io
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Farbpalette passend zum Frontend (Recharts-Farben)
_COLORS = ["#6ee7b7", "#38bdf8", "#fbbf24", "#f472b6", "#a78bfa",
           "#f97316", "#34d399", "#60a5fa", "#fb923c", "#e879f9"]

_PAGE_CSS = """
@page {
  size: A4 landscape;
  margin: 15mm 12mm 15mm 12mm;
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
.widget-grid { width: 100%; }
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
.kpi-label { font-size: 8pt; color: #888; text-align: center; }
table { width: 100%; border-collapse: collapse; font-size: 9pt; }
th {
  background: #f7f7f7;
  font-weight: 700;
  text-align: left;
  padding: 5px 8px;
  border-bottom: 2px solid #e0e0e0;
  white-space: nowrap;
}
td { padding: 4px 8px; border-bottom: 1px solid #f0f0f0; }
tr:nth-child(even) td { background: #fafafa; }
.chart-img { width: 100%; display: block; }
.chart-placeholder {
  background: #f7f7f7;
  border-radius: 4px;
  color: #aaa;
  font-size: 9pt;
  min-height: 80px;
  text-align: center;
  padding: 16px;
}
.footer { font-size: 7pt; color: #aaa; text-align: right; margin-top: 8px; }
"""


def _make_chart_png(wtype: str, config: dict, rows: list) -> Optional[str]:
    """
    Rendert ein Widget als Matplotlib-Chart und gibt einen base64-PNG-String zurück.
    Gibt None zurück wenn keine Daten vorhanden oder ein Fehler auftritt.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.ticker as mticker
        import numpy as np

        fig, ax = plt.subplots(figsize=(5.6, 2.8), dpi=110)
        fig.patch.set_facecolor("#ffffff")
        ax.set_facecolor("#fafafa")
        for spine in ax.spines.values():
            spine.set_color("#e0e0e0")
            spine.set_linewidth(0.5)
        ax.tick_params(colors="#555555", labelsize=7)

        rendered = False

        if wtype == "bar":
            x_field = config.get("x_field", "")
            value_fields = config.get("value_fields") or (
                [config["value_field"]] if config.get("value_field") else []
            )
            display = rows[:20]
            if not display or not value_fields:
                plt.close(fig); return None

            labels = [str(r.get(x_field, i))[:14] for i, r in enumerate(display)]
            n_series = min(len(value_fields), 4)
            x = np.arange(len(labels))
            bar_w = 0.65 / n_series

            for i, vf in enumerate(value_fields[:4]):
                vals = [float(r.get(vf) or 0) for r in display]
                offset = (i - (n_series - 1) / 2) * bar_w
                ax.bar(x + offset, vals, bar_w * 0.92, label=vf,
                       color=_COLORS[i % len(_COLORS)], alpha=0.88)

            ax.set_xticks(x)
            ax.set_xticklabels(labels, rotation=28, ha="right", fontsize=6.5)
            ax.yaxis.set_major_formatter(
                mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
            ax.grid(axis="y", alpha=0.35, color="#cccccc", linewidth=0.5)
            if n_series > 1:
                ax.legend(fontsize=6.5, framealpha=0.7, loc="upper right")
            rendered = True

        elif wtype == "line":
            x_field = config.get("x_field", "")
            value_fields = config.get("value_fields") or (
                [config["value_field"]] if config.get("value_field") else []
            )
            display = rows[:60]
            if not display or not value_fields:
                plt.close(fig); return None

            x = np.arange(len(display))
            labels = [str(r.get(x_field, i))[:10] for i, r in enumerate(display)]
            for i, vf in enumerate(value_fields[:4]):
                vals = [float(r.get(vf) or 0) for r in display]
                ax.plot(x, vals, label=vf, color=_COLORS[i % len(_COLORS)],
                        marker="o", markersize=2.5, linewidth=1.6, alpha=0.9)

            step = max(1, len(labels) // 8)
            ax.set_xticks(x[::step])
            ax.set_xticklabels(labels[::step], rotation=28, ha="right", fontsize=6.5)
            ax.yaxis.set_major_formatter(
                mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
            ax.grid(alpha=0.3, color="#cccccc", linewidth=0.5)
            if len(value_fields) > 1:
                ax.legend(fontsize=6.5, framealpha=0.7, loc="upper right")
            rendered = True

        elif wtype == "pie":
            label_field = config.get("label_field", "")
            value_field = config.get("value_field", "")
            is_donut = config.get("donut", False)
            display = rows[:8]
            if not display or not label_field or not value_field:
                plt.close(fig); return None

            labels = [str(r.get(label_field, ""))[:16] for r in display]
            values = [abs(float(r.get(value_field) or 0)) for r in display]
            if sum(values) == 0:
                plt.close(fig); return None

            wedgeprops = ({"width": 0.52, "edgecolor": "white", "linewidth": 1.5}
                          if is_donut else {"edgecolor": "white", "linewidth": 1.5})
            _, texts, autotexts = ax.pie(
                values, labels=labels,
                colors=[_COLORS[i % len(_COLORS)] for i in range(len(values))],
                autopct="%1.1f%%",
                pctdistance=0.72 if is_donut else 0.6,
                wedgeprops=wedgeprops, startangle=90,
            )
            for t in texts:     t.set_fontsize(6.5)
            for t in autotexts: t.set_fontsize(6); t.set_color("white")
            ax.set_aspect("equal")
            rendered = True

        elif wtype == "heatmap":
            import pandas as pd
            date_field  = config.get("date_field", "")
            value_field = config.get("value_field", "")
            if not rows or not date_field:
                plt.close(fig); return None

            df = pd.DataFrame(rows)
            if date_field not in df.columns:
                plt.close(fig); return None

            df[date_field] = pd.to_datetime(df[date_field], errors="coerce")
            df = df.dropna(subset=[date_field])
            if df.empty:
                plt.close(fig); return None

            df["_month"] = df[date_field].dt.to_period("M")
            if value_field and value_field in df.columns:
                df[value_field] = pd.to_numeric(df[value_field], errors="coerce").fillna(0)
                agg = df.groupby("_month")[value_field].sum()
            else:
                agg = df.groupby("_month").size()

            agg = agg.sort_index().tail(12)
            vals = agg.values.astype(float)
            x = np.arange(len(agg))
            labels = [str(p) for p in agg.index]

            vmin, vmax = vals.min(), vals.max()
            norm = (vals - vmin) / (vmax - vmin + 1e-9)
            bar_colors = [plt.cm.YlOrRd(0.2 + 0.75 * v) for v in norm]  # type: ignore[attr-defined]

            ax.bar(x, vals, color=bar_colors, alpha=0.9)
            ax.set_xticks(x)
            ax.set_xticklabels(labels, rotation=28, ha="right", fontsize=6.5)
            ax.yaxis.set_major_formatter(
                mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
            ax.grid(axis="y", alpha=0.35, color="#cccccc", linewidth=0.5)
            rendered = True

        if not rendered:
            plt.close(fig)
            return None

        plt.tight_layout(pad=0.4)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=110, bbox_inches="tight",
                    facecolor="white", edgecolor="none")
        buf.seek(0)
        return base64.b64encode(buf.read()).decode("utf-8")

    except Exception as e:
        logger.warning(f"Chart-Rendering fehlgeschlagen ({wtype}): {e}")
        return None
    finally:
        try:
            plt.close("all")
        except Exception:
            pass


def _widget_to_html(widget: Dict, data: List[Dict]) -> str:
    """Rendert ein einzelnes Widget als HTML-Block."""
    wtype  = widget.get("type", "")
    title  = widget.get("title", "")
    config = widget.get("config", {})
    rows   = data or []

    html = '<div class="widget" style="width:48%;">\n'
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
            if agg == "SUM":     val = sum(vals)
            elif agg == "COUNT": val = len(vals)
            elif agg == "AVG":   val = sum(vals) / len(vals) if vals else 0
            elif agg == "MIN":   val = min(vals) if vals else 0
            elif agg == "MAX":   val = max(vals) if vals else 0
            else:                val = vals[0] if vals else 0

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
        cols     = config.get("columns") or (list(rows[0].keys()) if rows else [])
        max_rows = min(len(rows), 50)

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
            html += (f'    <tr><td colspan="{len(cols)}" '
                     f'style="color:#888;font-style:italic;">'
                     f'… {len(rows) - max_rows} weitere Zeilen</td></tr>\n')
        html += '    </tbody>\n  </table>\n'

    elif wtype in ("bar", "line", "pie", "heatmap"):
        png_b64 = _make_chart_png(wtype, config, rows)
        if png_b64:
            html += (f'  <img class="chart-img" '
                     f'src="data:image/png;base64,{png_b64}" />\n')
        elif rows:
            # Fallback: Datentabelle wenn Chart-Rendering fehlschlägt
            x_field      = config.get("x_field") or config.get("label_field") or config.get("date_field", "")
            value_fields  = config.get("value_fields") or ([config["value_field"]] if config.get("value_field") else [])
            show_cols     = ([x_field] if x_field else []) + value_fields
            show_cols     = [c for c in show_cols if c and c in rows[0]] or list(rows[0].keys())[:4]
            html += '  <table>\n    <thead><tr>\n'
            for c in show_cols:
                html += f'      <th>{c}</th>\n'
            html += '    </tr></thead>\n    <tbody>\n'
            for row in rows[:25]:
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
    KPI und Tabelle werden direkt als HTML gerendert.
    Bar, Line, Pie, Heatmap werden als Matplotlib-PNG eingebettet.
    """
    from datetime import datetime

    ts = created_at or datetime.now().strftime("%d.%m.%Y %H:%M")

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
    """ReportLab-Fallback falls xhtml2pdf nicht verfügbar."""
    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
        from reportlab.lib import colors
        from reportlab.lib.units import mm

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                                leftMargin=15*mm, rightMargin=15*mm,
                                topMargin=15*mm, bottomMargin=15*mm)
        styles = getSampleStyleSheet()
        story  = []

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
                story.append(Paragraph(f"<font size='20'><b>{val:,.2f}</b></font>",
                                       styles["Normal"]))

            elif wtype in ("bar", "line", "pie", "heatmap"):
                png_b64 = _make_chart_png(wtype, config, rows)
                if png_b64:
                    img_buf = io.BytesIO(base64.b64decode(png_b64))
                    img = Image(img_buf, width=180*mm, height=80*mm)
                    story.append(img)
                elif rows:
                    cols = list(rows[0].keys())[:6]
                    tdata = [cols] + [[str(r.get(c, "")) for c in cols] for r in rows[:30]]
                    t = Table(tdata, repeatRows=1)
                    t.setStyle(TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
                        ("FONTSIZE",   (0, 0), (-1, -1), 8),
                        ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
                    ]))
                    story.append(t)

            elif rows:
                cols = list(rows[0].keys())[:8]
                tdata = [cols] + [[str(r.get(c, "")) for c in cols] for r in rows[:40]]
                t = Table(tdata, repeatRows=1)
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
