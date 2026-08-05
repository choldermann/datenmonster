import { useState, useRef } from "react";
import { AlertCircle } from "lucide-react";
import api from "../../api/client";
import DrilldownModal from "./DrilldownModal";
import TableWidget from "./widgets/TableWidget";
import KpiWidget   from "./widgets/KpiWidget";
import BarWidget   from "./widgets/BarWidget";
import LineWidget  from "./widgets/LineWidget";
import PieWidget   from "./widgets/PieWidget";
import EingangsrechnungWidget from "./widgets/EingangsrechnungWidget";
import AiSummaryWidget from "./widgets/AiSummaryWidget";

const S = {
  bgCard: "var(--bg-card)", border: "var(--border)",
  textBright: "var(--text-bright)", textDim: "var(--text-dim)",
};

const WIDGET_LABELS = {
  table: "Tabelle", kpi: "KPI", bar: "Balkendiagramm",
  line: "Liniendiagramm", pie: "Kreisdiagramm",
  eingangsrechnung: "Eingangsrechnungs-Freigabe", ai_summary: "KI-Analyse",
};

// Eigenständige Widgets brauchen kein Action-Ergebnis (rendern sofort).
// Exportiert, damit die Runner (FormRunner/PortalRunner) sie ohne Result anzeigen.
export const STANDALONE_WIDGET_TYPES = new Set(["eingangsrechnung"]);

function WidgetBody({ widget, result, allowDownload, onDrilldown }) {
  // Eigenständige, interaktive Widgets (kein result nötig)
  if (widget.type === "eingangsrechnung") return <EingangsrechnungWidget widget={widget} />;

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
    case "table": return <TableWidget widget={widget} result={result} allowDownload={allowDownload} onDrilldown={drill} />;
    case "kpi":   return <KpiWidget   widget={widget} result={result} />;
    case "bar":   return <BarWidget   widget={widget} result={result} onDrilldown={drill} />;
    case "line":  return <LineWidget  widget={widget} result={result} onDrilldown={drill} />;
    case "pie":   return <PieWidget   widget={widget} result={result} onDrilldown={drill} />;
    case "ai_summary": return <AiSummaryWidget widget={widget} result={result} />;
    default:      return <p style={{ padding: 14, color: S.textDim, fontSize: 12 }}>Unbekannter Widget-Typ: {widget.type}</p>;
  }
}

export default function WidgetRenderer({ widgets = [], results = {}, allowDownload = false, baseParams = {} }) {
  // Mehrstufiger Drilldown als Navigations-Stack: jede Ebene ist ein "Frame" mit
  // Titel + Detailzeilen. Klick auf eine Zeile öffnet – sofern eine tiefere Ebene
  // (config.drilldown.levels[]) konfiguriert ist – die nächste Ebene.
  const [stack, setStack] = useState([]);
  const cfgRef = useRef({ dd: null, base: {} });
  const seqRef = useRef(0);

  // Führt ein Detail-Mapping aus und legt/ersetzt den Frame auf Tiefe `depth`.
  const openLevel = async ({ mapping_id, param, value, title, field, depth }) => {
    const base = cfgRef.current.base || {};
    const id = ++seqRef.current;
    setStack(prev => [...prev.slice(0, depth), { id, title, field, value, rows: [], loading: true, error: null }]);
    try {
      const params = { ...base, [param]: value };
      const { data } = await api.post("/api/forms/drilldown", { mapping_id, params });
      setStack(prev => prev.map(f => f.id === id ? { ...f, rows: data.rows || [], loading: false } : f));
    } catch (e) {
      setStack(prev => prev.map(f => f.id === id
        ? { ...f, loading: false, error: e.response?.data?.detail || e.message } : f));
    }
  };

  // Einstieg aus einem Widget (Chart-Segment oder Tabellenzeile).
  const handleDrilldown = (widget, field, value) => {
    const dd = widget.config?.drilldown;
    if (!dd?.mapping_id) return;
    cfgRef.current = { dd, base: baseParams || {} };
    openLevel({ mapping_id: dd.mapping_id, param: dd.param || field, value,
      title: dd.title || widget.label || "Drilldown", field, depth: 0 });
  };

  // Klick auf eine Zeile im Modal → nächste Ebene (levels[depth]).
  const handleRowDrill = (row) => {
    const dd = cfgRef.current.dd;
    const depth = stack.length; // nächster Frame-Index
    const next = dd?.levels?.[depth - 1];
    if (!next?.mapping_id) return;
    const val = row[next.key_column];
    if (val === null || val === undefined || val === "") return;
    openLevel({ mapping_id: next.mapping_id, param: next.param || next.key_column, value: val,
      title: next.title || `Ebene ${depth + 1}`, field: next.key_column, depth });
  };

  // Ist die aktuell oberste Ebene weiter aufklappbar?
  const topFrame = stack[stack.length - 1] || null;
  const canDrillDeeper = !!(cfgRef.current.dd?.levels?.[stack.length - 1]?.mapping_id);
  const closeDrill = () => setStack([]);
  const backDrill = () => setStack(prev => prev.slice(0, -1));

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
                    {result.total !== undefined && widget.type !== "table" && widget.type !== "ai_summary" && !STANDALONE_WIDGET_TYPES.has(widget.type) && (
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
    {topFrame && (
      <DrilldownModal
        title={topFrame.title}
        field={topFrame.field}
        value={topFrame.value}
        rows={topFrame.rows}
        loading={topFrame.loading}
        error={topFrame.error}
        trail={stack.map(f => ({ title: f.title, value: f.value }))}
        canDrillDeeper={canDrillDeeper}
        onRowClick={handleRowDrill}
        onBack={stack.length > 1 ? backDrill : null}
        onClose={closeDrill}
      />
    )}
    </>
  );
}
