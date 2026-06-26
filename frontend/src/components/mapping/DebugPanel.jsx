import { useState } from "react";
import { X, ChevronDown, ChevronRight, Database, GitMerge, Layers, Calculator, Wand2, Code, Check } from "lucide-react";
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

function StageCard({ stage, isLast }) {
  const [open, setOpen] = useState(false);
  const color = STAGE_COLORS[stage.type] || "#94a3b8";
  const Icon = STAGE_ICONS[stage.type] || Database;
  const dropped = stage.rows_in !== null && stage.rows_out !== null
    ? stage.rows_in - stage.rows_out : 0;

  return (
    <div>
      <div
        onClick={() => stage.sample?.length > 0 && setOpen(o => !o)}
        style={{
          backgroundColor: S.bgCard,
          border: `1.5px solid ${color}44`,
          borderRadius: 8,
          padding: "10px 14px",
          cursor: stage.sample?.length > 0 ? "pointer" : "default",
          transition: "border-color 0.15s",
          position: "relative",
        }}
        onMouseEnter={e => { if (stage.sample?.length) e.currentTarget.style.borderColor = color + "88"; }}
        onMouseLeave={e => { if (stage.sample?.length) e.currentTarget.style.borderColor = color + "44"; }}
      >
        {/* Header row */}
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ width: 28, height: 28, borderRadius: 6, backgroundColor: color + "20", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <Icon size={13} color={color} />
          </div>
          <span style={{ fontSize: 12, fontWeight: 600, color: S.textBright, flex: 1 }}>{stage.label}</span>

          {/* Row count badge */}
          <span style={{ fontSize: 11, fontWeight: 700, color: color, backgroundColor: color + "18", padding: "2px 8px", borderRadius: 10, border: `1px solid ${color}33` }}>
            {stage.rows_out ?? "–"} Zeilen
          </span>

          {/* Error badge */}
          {stage.errors > 0 && (
            <span style={{ fontSize: 10, fontWeight: 700, color: "#f87171", backgroundColor: "#f8717118", padding: "2px 6px", borderRadius: 10, border: "1px solid #f8717133" }}>
              ⚠ {stage.errors}
            </span>
          )}

          {/* Expand indicator */}
          {stage.sample?.length > 0 && (
            open ? <ChevronDown size={12} color={S.textDim} /> : <ChevronRight size={12} color={S.textDim} />
          )}
        </div>
      </div>

      {/* Sample data table */}
      {open && stage.sample?.length > 0 && (
        <div style={{ marginTop: 4, backgroundColor: "rgba(0,0,0,0.3)", border: `1px solid ${color}33`, borderRadius: 6, overflow: "auto", maxHeight: 200 }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10 }}>
            <thead>
              <tr style={{ backgroundColor: color + "12" }}>
                {Object.keys(stage.sample[0]).slice(0, 6).map(k => (
                  <th key={k} style={{ padding: "4px 8px", textAlign: "left", color: S.textDim, fontWeight: 700, whiteSpace: "nowrap", borderBottom: `1px solid ${color}22` }}>{k}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {stage.sample.map((row, i) => (
                <tr key={i} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                  {Object.keys(stage.sample[0]).slice(0, 6).map(k => (
                    <td key={k} style={{ padding: "3px 8px", color: S.textMain, maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {row[k] === null ? <span style={{ color: S.textDim, fontStyle: "italic" }}>null</span> : String(row[k])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Arrow + delta to next stage */}
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

export default function DebugPanel({ trace = [], totalDurationMs = 0, errors = [], onClose }) {
  const totalOut = trace[trace.length - 1]?.rows_out ?? 0;
  const totalErrors = trace.reduce((s, t) => s + (t.errors || 0), 0);

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
        <div style={{ flex: 1 }} />
        <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: S.textDim, padding: 4, borderRadius: 4 }}
          onMouseEnter={e => e.currentTarget.style.color = S.textBright}
          onMouseLeave={e => e.currentTarget.style.color = S.textDim}>
          <X size={14} />
        </button>
      </div>

      {/* Trace stages */}
      <div style={{ overflowY: "auto", padding: "12px 16px", display: "flex", flexDirection: "column", gap: 0 }}>
        {trace.length === 0 && (
          <p style={{ fontSize: 12, color: S.textDim, textAlign: "center", padding: "20px 0" }}>
            Keine Debug-Daten vorhanden.
          </p>
        )}
        {trace.map((stage, i) => (
          <StageCard key={stage.id || i} stage={stage} isLast={i === trace.length - 1} />
        ))}

        {/* Errors */}
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
