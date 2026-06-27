import { AlertCircle } from "lucide-react";
import TableWidget from "./widgets/TableWidget";
import KpiWidget   from "./widgets/KpiWidget";
import BarWidget   from "./widgets/BarWidget";
import LineWidget  from "./widgets/LineWidget";
import PieWidget   from "./widgets/PieWidget";

const S = {
  bgCard: "var(--bg-card)", border: "var(--border)",
  textBright: "var(--text-bright)", textDim: "var(--text-dim)",
};

const WIDGET_LABELS = {
  table: "Tabelle", kpi: "KPI", bar: "Balkendiagramm",
  line: "Liniendiagramm", pie: "Kreisdiagramm",
};

function WidgetBody({ widget, result, allowDownload }) {
  if (result.error) return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "14px 16px",
      color: "#e07070", fontSize: 12 }}>
      <AlertCircle size={12} /> {result.error}
    </div>
  );

  switch (widget.type) {
    case "table": return <TableWidget widget={widget} result={result} allowDownload={allowDownload} />;
    case "kpi":   return <KpiWidget   widget={widget} result={result} />;
    case "bar":   return <BarWidget   widget={widget} result={result} />;
    case "line":  return <LineWidget  widget={widget} result={result} />;
    case "pie":   return <PieWidget   widget={widget} result={result} />;
    default:      return <p style={{ padding: 14, color: S.textDim, fontSize: 12 }}>Unbekannter Widget-Typ: {widget.type}</p>;
  }
}

export default function WidgetRenderer({ widgets = [], results = {}, allowDownload = false }) {
  if (!widgets.length) return null;

  // Group widgets into rows of up to width=12
  // Each widget has config.width (1-12), default 12
  const rows = [];
  let currentRow = [], currentWidth = 0;
  for (const w of widgets) {
    const ww = Number(w.config?.width) || 12;
    if (currentWidth + ww > 12 && currentRow.length > 0) {
      rows.push(currentRow);
      currentRow = []; currentWidth = 0;
    }
    currentRow.push(w); currentWidth += ww;
  }
  if (currentRow.length) rows.push(currentRow);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {rows.map((rowWidgets, ri) => (
        <div key={ri} style={{ display: "flex", gap: 16, alignItems: "stretch" }}>
          {rowWidgets.map(widget => {
            const ww = Number(widget.config?.width) || 12;
            const flex = `0 0 calc(${(ww / 12) * 100}% - ${16 * (rowWidgets.length - 1) / rowWidgets.length}px)`;
            const result = results[widget.action_id] || { columns: [], rows: [], total: 0 };
            const title  = widget.label || WIDGET_LABELS[widget.type] || widget.type;
            const showHeader = widget.type !== "kpi";

            return (
              <div key={widget.id} style={{ flex, backgroundColor: S.bgCard,
                border: `1px solid ${S.border}`, borderRadius: 12, overflow: "hidden",
                minWidth: 0 }}>
                {showHeader && (
                  <div style={{ padding: "12px 16px", borderBottom: `1px solid ${S.border}`,
                    display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: S.textBright }}>{title}</span>
                    {result.total !== undefined && widget.type !== "table" && (
                      <span style={{ fontSize: 10, color: S.textDim }}>{result.total} Zeilen</span>
                    )}
                  </div>
                )}
                <WidgetBody widget={widget} result={result} allowDownload={allowDownload} />
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}
