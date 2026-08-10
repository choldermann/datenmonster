import { useState, useRef } from "react";
import { AlertCircle, Info } from "lucide-react";
import api from "../../api/client";
import DrilldownModal from "./DrilldownModal";
import AiActionModal from "./AiActionModal";
import TableWidget from "./widgets/TableWidget";
import KpiWidget   from "./widgets/KpiWidget";
import BarWidget   from "./widgets/BarWidget";
import LineWidget  from "./widgets/LineWidget";
import PieWidget   from "./widgets/PieWidget";
import EingangsrechnungWidget from "./widgets/EingangsrechnungWidget";
import EanResearchWidget from "./widgets/EanResearchWidget";
import HerstellerNavigator from "./widgets/HerstellerNavigator";
import AiSummaryWidget from "./widgets/AiSummaryWidget";
import TaskListWidget from "./widgets/TaskListWidget";

const S = {
  bgCard: "var(--bg-card)", border: "var(--border)",
  textBright: "var(--text-bright)", textDim: "var(--text-dim)",
};

const WIDGET_LABELS = {
  table: "Tabelle", kpi: "KPI", bar: "Balkendiagramm",
  line: "Liniendiagramm", pie: "Kreisdiagramm",
  eingangsrechnung: "Eingangsrechnungs-Freigabe", ai_summary: "KI-Analyse",
  tasklist: "Aufgabenliste",
};

// Eigenständige Widgets brauchen kein Action-Ergebnis (rendern sofort).
// Exportiert, damit die Runner (FormRunner/PortalRunner) sie ohne Result anzeigen.
export const STANDALONE_WIDGET_TYPES = new Set(["eingangsrechnung", "ean_research"]);

function WidgetBody({ widget, result, results, allowDownload, onDrilldown, onAiAction, onTaskClick, onAiText }) {
  // Eigenständige, interaktive Widgets (kein result nötig)
  if (widget.type === "eingangsrechnung") return <EingangsrechnungWidget widget={widget} />;
  if (widget.type === "ean_research") return <EanResearchWidget widget={widget} />;

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
  // KI-Handlungsempfehlung pro Zeile, wenn config.ai_action gesetzt ist.
  const aiAct = onAiAction && widget.config?.ai_action?.mapping_id
    ? (row) => onAiAction(widget, row)
    : undefined;

  switch (widget.type) {
    case "table": return <TableWidget widget={widget} result={result} allowDownload={allowDownload} onDrilldown={drill} onAiAction={aiAct} />;
    case "kpi":   return <KpiWidget   widget={widget} result={result} />;
    case "bar":   return <BarWidget   widget={widget} result={result} onDrilldown={drill} />;
    case "line":  return <LineWidget  widget={widget} result={result} onDrilldown={drill} />;
    case "pie":   return <PieWidget   widget={widget} result={result} onDrilldown={drill} />;
    case "ai_summary": return <AiSummaryWidget widget={widget} result={result} results={results} onAiText={onAiText} />;
    case "tasklist": return <TaskListWidget widget={widget} result={result} onTaskClick={onTaskClick} />;
    case "hersteller_navigator": return <HerstellerNavigator widget={widget} result={result} />;
    default:      return <p style={{ padding: 14, color: S.textDim, fontSize: 12 }}>Unbekannter Widget-Typ: {widget.type}</p>;
  }
}

export default function WidgetRenderer({ widgets = [], results = {}, allowDownload = false, baseParams = {}, onAiText }) {
  // Mehrstufiger Drilldown als Navigations-Stack: jede Ebene ist ein "Frame" mit
  // Titel + Detailzeilen. Klick auf eine Zeile öffnet – sofern eine tiefere Ebene
  // (config.drilldown.levels[]) konfiguriert ist – die nächste Ebene.
  const [stack, setStack] = useState([]);
  const [aiAction, setAiAction] = useState(null);
  const cfgRef = useRef({ dd: null, base: {} });
  const seqRef = useRef(0);

  // Klick auf eine Zeile eines Widgets mit config.ai_action → KI-Empfehlungs-Modal.
  const handleAiAction = (widget, row) => {
    const cfg = widget.config?.ai_action;
    if (!cfg?.mapping_id || !cfg?.key_column) return;
    const keyValue = row[cfg.key_column];
    if (keyValue === null || keyValue === undefined || keyValue === "") return;
    setAiAction({
      kind: cfg.kind,
      label: cfg.label_column ? row[cfg.label_column] : String(keyValue),
      title: cfg.title || widget.label || "KI-Handlungsempfehlung",
      factsMapping: cfg.mapping_id,
      keyParam: cfg.param || cfg.key_column,
      keyValue,
      baseParams: baseParams || {},
      // manual: Text erst auf Knopfdruck erzeugen (z.B. Artikelbeschreibung),
      // statt beim Öffnen automatisch loszulaufen.
      manual: !!cfg.manual,
      buttonLabel: cfg.button_label,
    });
  };

  // Führt ein Detail-Mapping aus und legt/ersetzt den Frame auf Tiefe `depth`.
  const openLevel = async ({ mapping_id, param, value, title, field, depth, hidden }) => {
    const base = cfgRef.current.base || {};
    const id = ++seqRef.current;
    setStack(prev => [...prev.slice(0, depth), { id, title, field, value, rows: [], loading: true, error: null, hidden: hidden || [] }]);
    try {
      // param kann fehlen (z.B. Aufgabenlisten-Detail nutzt nur die Basis-Filter).
      const params = param ? { ...base, [param]: value } : { ...base };
      const { data } = await api.post("/api/forms/drilldown", { mapping_id, params });
      setStack(prev => prev.map(f => f.id === id ? { ...f, rows: data.rows || [], loading: false } : f));
    } catch (e) {
      setStack(prev => prev.map(f => f.id === id
        ? { ...f, loading: false, error: e.response?.data?.detail || e.message } : f));
    }
  };

  // Klick auf eine Aufgabenzeile (tasklist) → Detailliste des jeweiligen Checks.
  const handleTaskClick = (widget, row, detail) => {
    if (!detail?.mapping_id) return;
    // detail als "dd" merken → falls detail.levels[] gesetzt ist, kann in der
    // Detailliste per Zeilenklick eine weitere Ebene geöffnet werden (z.B.
    // Artikelbeschreibungen → aktuelle Beschreibung des Artikels).
    cfgRef.current = { dd: detail, base: baseParams || {} };
    openLevel({ mapping_id: detail.mapping_id, param: detail.param || null, value: null,
      title: detail.title || row.Aufgabe || "Detail", field: "", depth: 0,
      hidden: detail.hidden_columns || [] });
  };

  // Einstieg aus einem Widget (Chart-Segment oder Tabellenzeile).
  const handleDrilldown = (widget, field, value) => {
    const dd = widget.config?.drilldown;
    if (!dd?.mapping_id) return;
    cfgRef.current = { dd, base: baseParams || {} };
    openLevel({ mapping_id: dd.mapping_id, param: dd.param || field, value,
      title: dd.title || widget.label || "Drilldown", field, depth: 0, hidden: dd.hidden_columns });
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
      title: next.title || `Ebene ${depth + 1}`, field: next.key_column, depth, hidden: next.hidden_columns });
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
                    {result.total !== undefined && widget.type !== "table" && widget.type !== "ai_summary" && widget.type !== "tasklist" && !STANDALONE_WIDGET_TYPES.has(widget.type) && (
                      <span style={{ fontSize: 10, color: S.textDim }}>{result.total} Zeilen</span>
                    )}
                  </div>
                )}
                {widget.config?.info && (
                  <div style={{ display: "flex", alignItems: "flex-start", gap: 7, padding: "9px 16px",
                    borderBottom: `1px solid ${S.border}`, fontSize: 11, lineHeight: 1.5,
                    color: S.textDim, backgroundColor: "rgba(255,255,255,0.02)" }}>
                    <Info size={13} style={{ flexShrink: 0, marginTop: 1, color: S.textDim }} />
                    <span>{widget.config.info}</span>
                  </div>
                )}
                <WidgetBody widget={widget} result={result} results={results} allowDownload={allowDownload} onDrilldown={handleDrilldown} onAiAction={handleAiAction} onTaskClick={(row, detail) => handleTaskClick(widget, row, detail)} onAiText={onAiText} />
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
        hiddenColumns={topFrame.hidden || []}
        canDrillDeeper={canDrillDeeper}
        onRowClick={handleRowDrill}
        onBack={stack.length > 1 ? backDrill : null}
        onClose={closeDrill}
        emailEnabled={allowDownload}
      />
    )}
    {aiAction && (
      <AiActionModal {...aiAction} onClose={() => setAiAction(null)} />
    )}
    </>
  );
}
