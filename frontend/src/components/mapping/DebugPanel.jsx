import { useState } from "react";
import { X, ChevronDown, ChevronRight, Database, GitMerge, Layers, Calculator, Wand2, Code, Check, ArrowRight, ArrowLeft } from "lucide-react";
import { S } from "./constants";

const STAGE_COLORS = {
  dataset:   "#38bdf8",
  join:      "#f97316",
  agg:       "#f59e0b",
  transform: "#818cf8",
  lookup:    "#34d399",
  rest:      "#14b8a6",
  calc:      "#fb7185",
  python:    "#22c55e",
  output:    "#6ee7b7",
};

const STAGE_ICONS = {
  dataset:   Database,
  join:      GitMerge,
  agg:       Layers,
  transform: Wand2,
  calc:      Calculator,
  python:    Code,
  output:    Check,
};

function FieldTooltip({ field, values }) {
  return (
    <div style={{
      position: "absolute", left: "calc(100% + 8px)", top: "50%", transform: "translateY(-50%)",
      zIndex: 200, backgroundColor: "#1a1a2e", border: "1px solid rgba(255,255,255,0.15)",
      borderRadius: 6, padding: "6px 10px", minWidth: 140, maxWidth: 240,
      boxShadow: "0 8px 24px rgba(0,0,0,0.7)", pointerEvents: "none",
    }}>
      <p style={{ fontSize: 9, fontWeight: 700, color: S.textDim, marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.08em" }}>{field}</p>
      {values.map((v, i) => (
        <p key={i} style={{ fontSize: 10, color: v === null ? S.textDim : S.textMain, fontFamily: "monospace", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontStyle: v === null ? "italic" : "normal" }}>
          {v === null ? "null" : String(v)}
        </p>
      ))}
    </div>
  );
}

function SampleTable({ stage, selectedRowIdx, onRowSelect }) {
  const color = STAGE_COLORS[stage.type] || "#94a3b8";
  const [hoveredField, setHoveredField] = useState(null);

  if (!stage.sample?.length) return null;
  const cols = Object.keys(stage.sample[0]).slice(0, 7);

  return (
    <div style={{ marginTop: 4, backgroundColor: "rgba(0,0,0,0.3)", border: `1px solid ${color}33`, borderRadius: 6, overflow: "auto", maxHeight: 220 }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10 }}>
        <thead>
          <tr style={{ backgroundColor: color + "12" }}>
            <th style={{ padding: "4px 6px", width: 20, borderBottom: `1px solid ${color}22` }} />
            {cols.map(k => (
              <th key={k} style={{ padding: "4px 8px", textAlign: "left", color: S.textDim, fontWeight: 700, whiteSpace: "nowrap", borderBottom: `1px solid ${color}22`, fontFamily: "monospace" }}>{k}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {stage.sample.map((row, i) => {
            const isSelected = selectedRowIdx === i;
            return (
              <tr
                key={i}
                onClick={() => onRowSelect(isSelected ? null : i)}
                style={{
                  borderBottom: "1px solid rgba(255,255,255,0.04)",
                  backgroundColor: isSelected ? color + "22" : "transparent",
                  cursor: "pointer",
                  outline: isSelected ? `1px solid ${color}66` : "none",
                }}
                onMouseEnter={e => { if (!isSelected) e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.04)"; }}
                onMouseLeave={e => { if (!isSelected) e.currentTarget.style.backgroundColor = "transparent"; }}
              >
                <td style={{ padding: "3px 6px", color: isSelected ? color : S.textDim, fontSize: 9, fontWeight: 700, textAlign: "center" }}>
                  {isSelected ? "▶" : i + 1}
                </td>
                {cols.map(k => (
                  <td key={k} style={{ padding: "3px 8px", color: isSelected ? S.textBright : S.textMain, maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {row[k] === null ? <span style={{ color: S.textDim, fontStyle: "italic" }}>null</span> : String(row[k])}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RowInspector({ trace, selectedRowIdx, activeStageIdx, onStageStep }) {
  const color = STAGE_COLORS[trace[activeStageIdx]?.type] || "#94a3b8";
  const stage = trace[activeStageIdx];
  const row = stage?.sample?.[selectedRowIdx];

  if (!stage || !row) return null;

  return (
    <div style={{
      margin: "0 16px 12px",
      borderRadius: 8,
      border: `1px solid ${color}55`,
      backgroundColor: color + "0a",
      overflow: "hidden",
    }}>
      {/* Navigator */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 12px", borderBottom: `1px solid ${color}33`, backgroundColor: color + "10" }}>
        <button
          onClick={() => onStageStep(-1)}
          disabled={activeStageIdx === 0}
          style={{ background: "none", border: "none", cursor: activeStageIdx === 0 ? "not-allowed" : "pointer", color: activeStageIdx === 0 ? S.textDim + "55" : color, padding: 2, borderRadius: 3, lineHeight: 1 }}>
          <ArrowLeft size={12} />
        </button>
        <div style={{ flex: 1, textAlign: "center" }}>
          <span style={{ fontSize: 10, fontWeight: 700, color }}>
            {stage.label}
          </span>
          <span style={{ fontSize: 9, color: S.textDim, marginLeft: 6 }}>
            {activeStageIdx + 1} / {trace.length}
          </span>
        </div>
        <button
          onClick={() => onStageStep(1)}
          disabled={activeStageIdx === trace.length - 1}
          style={{ background: "none", border: "none", cursor: activeStageIdx === trace.length - 1 ? "not-allowed" : "pointer", color: activeStageIdx === trace.length - 1 ? S.textDim + "55" : color, padding: 2, borderRadius: 3, lineHeight: 1 }}>
          <ArrowRight size={12} />
        </button>
      </div>

      {/* Stage breadcrumb dots */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 4, padding: "5px 12px" }}>
        {trace.map((s, i) => {
          const c = STAGE_COLORS[s.type] || "#94a3b8";
          const hasRow = s.sample && s.sample[selectedRowIdx] !== undefined;
          return (
            <button
              key={i}
              onClick={() => onStageStep(i - activeStageIdx)}
              title={s.label}
              style={{
                width: i === activeStageIdx ? 20 : 8,
                height: 8,
                borderRadius: 4,
                backgroundColor: i === activeStageIdx ? c : hasRow ? c + "55" : S.border,
                border: "none",
                cursor: "pointer",
                padding: 0,
                transition: "all 0.2s",
                flexShrink: 0,
              }}
            />
          );
        })}
      </div>

      {/* Row fields */}
      <div style={{ padding: "6px 12px 10px", display: "flex", flexDirection: "column", gap: 3 }}>
        {Object.entries(row).map(([k, v]) => (
          <div key={k} style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
            <span style={{ fontSize: 9, fontFamily: "monospace", color: S.textDim, flexShrink: 0, minWidth: 100, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{k}</span>
            <span style={{ fontSize: 10, color: v === null ? S.textDim : S.textMain, fontFamily: "monospace", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontStyle: v === null ? "italic" : "normal", flex: 1 }}>
              {v === null ? "null" : String(v)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function StageCard({ stage, isLast, isActive, onSelect, selectedRowIdx, onRowSelect }) {
  const [open, setOpen] = useState(false);
  const color = STAGE_COLORS[stage.type] || "#94a3b8";
  const Icon = STAGE_ICONS[stage.type] || Database;
  const dropped = stage.rows_in !== null && stage.rows_out !== null
    ? stage.rows_in - stage.rows_out : 0;

  const handleHeaderClick = () => {
    onSelect();
    if (stage.sample?.length > 0) setOpen(o => !o);
  };

  const showOpen = open || isActive;

  return (
    <div>
      <div
        onClick={handleHeaderClick}
        style={{
          backgroundColor: isActive ? color + "12" : S.bgCard,
          border: `1.5px solid ${isActive ? color + "88" : color + "44"}`,
          borderRadius: 8,
          padding: "10px 14px",
          cursor: "pointer",
          transition: "border-color 0.15s, background-color 0.15s",
          position: "relative",
          boxShadow: isActive ? `0 0 12px ${color}33` : "none",
        }}
        onMouseEnter={e => { if (!isActive) { e.currentTarget.style.borderColor = color + "88"; e.currentTarget.style.backgroundColor = color + "0a"; } }}
        onMouseLeave={e => { if (!isActive) { e.currentTarget.style.borderColor = color + "44"; e.currentTarget.style.backgroundColor = S.bgCard; } }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ width: 28, height: 28, borderRadius: 6, backgroundColor: isActive ? color + "30" : color + "20", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <Icon size={13} color={color} />
          </div>
          <span style={{ fontSize: 12, fontWeight: 600, color: isActive ? S.textBright : S.textMain, flex: 1 }}>{stage.label}</span>

          <span style={{ fontSize: 11, fontWeight: 700, color, backgroundColor: color + "18", padding: "2px 8px", borderRadius: 10, border: `1px solid ${color}33` }}>
            {stage.rows_out ?? "–"} Zeilen
          </span>

          {stage.errors > 0 && (
            <span style={{ fontSize: 10, fontWeight: 700, color: "#f87171", backgroundColor: "#f8717118", padding: "2px 6px", borderRadius: 10, border: "1px solid #f8717133" }}>
              ⚠ {stage.errors}
            </span>
          )}

          {stage.sample?.length > 0 && (
            showOpen ? <ChevronDown size={12} color={S.textDim} /> : <ChevronRight size={12} color={S.textDim} />
          )}
        </div>
      </div>

      {showOpen && stage.sample?.length > 0 && (
        <SampleTable stage={stage} selectedRowIdx={selectedRowIdx} onRowSelect={onRowSelect} />
      )}

      {!isLast && (
        <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 14px", color: S.textDim, fontSize: 10 }}>
          <div style={{ width: 2, height: 16, backgroundColor: S.border, margin: "0 13px" }} />
          {dropped > 0 && (
            <span style={{ color: "#f87171" }}>↓ {dropped} ausgeschieden</span>
          )}
        </div>
      )}
    </div>
  );
}

export default function DebugPanel({ trace = [], totalDurationMs = 0, errors = [], activeStageId, onStageSelect, selectedRowIdx, onRowSelect, onClose }) {
  const totalOut = trace[trace.length - 1]?.rows_out ?? 0;
  const totalErrors = trace.reduce((s, t) => s + (t.errors || 0), 0);

  // Index des aktiven Stage für den Row Inspector
  const activeStageIdx = trace.findIndex(s => s.id === activeStageId);
  const rowInspectorIdx = selectedRowIdx !== null && selectedRowIdx !== undefined
    ? (activeStageIdx >= 0 ? activeStageIdx : 0)
    : -1;

  const handleStageStep = (delta) => {
    const newIdx = Math.max(0, Math.min(trace.length - 1, rowInspectorIdx + delta));
    if (trace[newIdx]) onStageSelect(trace[newIdx].id);
  };

  return (
    <div style={{
      position: "absolute", bottom: 0, left: 0, right: 0,
      backgroundColor: S.bgCard,
      borderTop: `1px solid ${S.border}`,
      zIndex: 50,
      display: "flex", flexDirection: "column",
      maxHeight: "70%",
    }}>
      {/* Panel header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 16px", borderBottom: `1px solid ${S.border}`, flexShrink: 0 }}>
        <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: S.accent }}>
          Debug-Trace
        </span>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ fontSize: 10, color: "#6ee7b7", backgroundColor: "rgba(110,231,183,0.12)", padding: "2px 8px", borderRadius: 10, border: "1px solid rgba(110,231,183,0.25)" }}>
            {totalOut} Datensätze
          </span>
          <span style={{ fontSize: 10, color: S.textDim }}>
            {totalDurationMs}ms gesamt
          </span>
          {totalErrors > 0 && (
            <span style={{ fontSize: 10, color: "#f87171", backgroundColor: "rgba(248,113,113,0.12)", padding: "2px 8px", borderRadius: 10, border: "1px solid rgba(248,113,113,0.25)" }}>
              ⚠ {totalErrors} Fehler
            </span>
          )}
        </div>

        {/* Zeile-verfolgen Badge */}
        {selectedRowIdx !== null && selectedRowIdx !== undefined && (
          <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "2px 8px", borderRadius: 10, backgroundColor: "rgba(129,140,248,0.12)", border: "1px solid rgba(129,140,248,0.3)" }}>
            <span style={{ fontSize: 10, color: "#818cf8", fontWeight: 700 }}>Zeile {selectedRowIdx + 1} verfolgen</span>
            <button onClick={() => onRowSelect(null)}
              style={{ background: "none", border: "none", cursor: "pointer", color: "#818cf8", padding: 0, lineHeight: 1, opacity: 0.7 }}
              onMouseEnter={e => e.currentTarget.style.opacity = 1}
              onMouseLeave={e => e.currentTarget.style.opacity = 0.7}>
              <X size={10} />
            </button>
          </div>
        )}

        <div style={{ flex: 1 }} />
        <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: S.textDim, padding: 4, borderRadius: 4 }}
          onMouseEnter={e => e.currentTarget.style.color = S.textBright}
          onMouseLeave={e => e.currentTarget.style.color = S.textDim}>
          <X size={14} />
        </button>
      </div>

      {/* Row Inspector (wenn Zeile ausgewählt) */}
      {rowInspectorIdx >= 0 && (
        <div style={{ flexShrink: 0, borderBottom: `1px solid ${S.border}`, paddingTop: 10 }}>
          <RowInspector
            trace={trace}
            selectedRowIdx={selectedRowIdx}
            activeStageIdx={rowInspectorIdx}
            onStageStep={handleStageStep}
          />
        </div>
      )}

      {/* Trace stages */}
      <div style={{ overflowY: "auto", padding: "12px 16px", display: "flex", flexDirection: "column", gap: 0 }}>
        {trace.length === 0 && (
          <p style={{ fontSize: 12, color: S.textDim, textAlign: "center", padding: "20px 0" }}>
            Keine Debug-Daten vorhanden.
          </p>
        )}
        {trace.map((stage, i) => (
          <StageCard
            key={stage.id || i}
            stage={stage}
            isLast={i === trace.length - 1}
            isActive={activeStageId === stage.id}
            onSelect={() => onStageSelect(activeStageId === stage.id ? null : stage.id)}
            selectedRowIdx={selectedRowIdx}
            onRowSelect={onRowSelect}
          />
        ))}

        {errors.length > 0 && (
          <div style={{ marginTop: 12, padding: "10px 12px", borderRadius: 6, backgroundColor: "rgba(248,113,113,0.08)", border: "1px solid rgba(248,113,113,0.25)" }}>
            <p style={{ fontSize: 10, fontWeight: 700, color: "#f87171", marginBottom: 6 }}>Fehler</p>
            {errors.slice(0, 5).map((e, i) => (
              <p key={i} style={{ fontSize: 10, color: "#fca5a5", fontFamily: "monospace" }}>{e}</p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
