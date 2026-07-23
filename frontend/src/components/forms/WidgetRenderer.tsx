import { useState } from "react";
import { AlertCircle } from "lucide-react";
import api from "../../api/client";
import DrilldownModal from "./DrilldownModal";
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

function WidgetBody({ widget, result, allowDownload, onDrilldown }) {
  if (result.error) return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "14px 16px",
      color: "#e07070", fontSize: 12 }}>
      <AlertCircle size={12} /> {result.error}
    </div>
  );

  // Drilldown nur, wenn das Widget ein Detail-Mapping konfiguriert hat
  const drill = onDrilldown && widget.config?.drilldown?.mapping_id
    ? (field, value) => onDrilldown(widget, field, value)
    : undefined;

  switch (widget.type) {
    case "table": return <TableWidget widget={widget} result={result} allowDownload={allowDownload} />;
    case "kpi":   return <KpiWidget   widget={widget} result={result} />;
    case "bar":   return <BarWidget   widget={widget} result={result} onDrilldown={drill} />;
    case "line":  return <LineWidget  widget={widget} result={result} onDrilldown={drill} />;
    case "pie":   return <PieWidget   widget={widget} result={result} onDrilldown={drill} />;
    default:      return <p style={{ padding: 14, color: S.textDim, fontSize: 12 }}>Unbekannter Widget-Typ: {widget.type}</p>;
  }
}

export default function WidgetRenderer({ widgets = [], results = {}, allowDownload = false }) {
  const [drilldown, setDrilldown] = useState(null);

  // Mapping-Drilldown (Stufe B): parametrisiertes Detail-Mapping ausführen.
  const handleDrilldown = async (widget, field, value) => {
    const dd = widget.config?.drilldown;
    if (!dd?.mapping_id) return;
    const title = widget.label || "Drilldown";
    setDrilldown({ title, field, value, rows: [], loading: true });
    try {
      const params = { [dd.param || field]: value };
      const { data } = await api.post("/api/forms/drilldown", { mapping_id: dd.mapping_id, params });
      setDrilldown({ title, field, value, rows: data.rows || [], loading: false });
    } catch (e) {
      setDrilldown({ title, field, value, rows: [], loading: false,
        error: e.response?.data?.detail || e.message });
    }
  };

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
    <>
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
                <WidgetBody widget={widget} result={result} allowDownload={allowDownload} onDrilldown={handleDrilldown} />
              </div>
            );
          })}
        </div>
      ))}
    </div>
    {drilldown && (
      <DrilldownModal
        title={drilldown.title}
        field={drilldown.field}
        value={drilldown.value}
        rows={drilldown.rows}
        loading={drilldown.loading}
        error={drilldown.error}
        onClose={() => setDrilldown(null)}
      />
    )}
    </>
  );
}
