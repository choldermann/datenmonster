import { useState } from "react";
import { X, ChevronDown, ChevronRight, Check, AlertTriangle, XCircle, MinusCircle, Terminal } from "lucide-react";
import { S } from "./constants";

const STATUS = {
  ok:      { color: "#6ee7b7", Icon: Check },
  warning: { color: "#fbbf24", Icon: AlertTriangle },
  error:   { color: "#e07070", Icon: XCircle },
  skipped: { color: "#94a3b8", Icon: MinusCircle },
};

function MiniSample({ sample, color }) {
  if (!sample?.length) return null;
  const cols = Object.keys(sample[0]).slice(0, 7);
  return (
    <div style={{ overflowX: "auto", margin: "6px 0 2px" }}>
      <table style={{ borderCollapse: "collapse", fontSize: 10, fontFamily: "monospace" }}>
        <thead>
          <tr>{cols.map(c => (
            <th key={c} style={{ textAlign: "left", padding: "2px 8px", color, borderBottom: `1px solid ${color}33`, whiteSpace: "nowrap" }}>{c}</th>
          ))}</tr>
        </thead>
        <tbody>
          {sample.map((row, i) => (
            <tr key={i}>{cols.map(c => (
              <td key={c} style={{ padding: "2px 8px", color: row[c] == null ? S.textDim : S.textMain, fontStyle: row[c] == null ? "italic" : "normal", whiteSpace: "nowrap", maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis" }}>
                {row[c] == null ? "null" : String(row[c])}
              </td>
            ))}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Kompakte Darstellung des B1-Sub-Trace eines Mapping-Nodes (Drill-in)
function SubTrace({ trace }) {
  return (
    <div style={{ marginTop: 8, paddingLeft: 10, borderLeft: `2px solid ${S.border}`, display: "flex", flexDirection: "column", gap: 6 }}>
      <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: S.textDim }}>
        Mapping-Trace ({trace.length} Stufen)
      </span>
      {trace.map((s, i) => (
        <div key={s.id || i} style={{ fontSize: 11 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {s.type === "sql" && <Terminal size={11} color="#a78bfa" />}
            <span style={{ color: S.textMain, flex: 1 }}>{s.label}</span>
            {s.errors > 0 && <span style={{ fontSize: 9, color: "#f87171" }}>⚠ {s.errors}</span>}
            <span style={{ fontSize: 10, color: S.textDim }}>{s.rows_out ?? "–"} Z.</span>
          </div>
          {s.meta?.sql && (
            <pre style={{ margin: "3px 0 0", padding: "6px 8px", backgroundColor: "#0f0f1e", border: "1px solid #a78bfa33", borderRadius: 4, fontSize: 9, color: S.textMain, whiteSpace: "pre-wrap", wordBreak: "break-word", maxHeight: 120, overflow: "auto" }}>
              {s.meta.sql}
            </pre>
          )}
        </div>
      ))}
    </div>
  );
}

function NodeStep({ step, isLast }) {
  const [open, setOpen] = useState(false);
  const st = STATUS[step.status] || STATUS.skipped;
  const canExpand = step.sample?.length > 0 || step.sub_trace?.length > 0 || !!step.message;
  return (
    <div>
      <div
        onClick={() => canExpand && setOpen(o => !o)}
        style={{
          backgroundColor: S.bgCard, border: `1.5px solid ${st.color}44`, borderRadius: 8,
          padding: "10px 14px", cursor: canExpand ? "pointer" : "default", position: "relative",
        }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ width: 26, height: 26, borderRadius: 6, backgroundColor: st.color + "20", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <st.Icon size={13} color={st.color} />
          </div>
          <span style={{ fontSize: 12, fontWeight: 600, color: S.textMain }}>{step.label || step.type}</span>
          <span style={{ fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em" }}>{step.type}</span>
          {step.dry_run && (
            <span style={{ fontSize: 9, color: "#38bdf8", backgroundColor: "rgba(56,189,248,0.12)", padding: "1px 6px", borderRadius: 8, border: "1px solid rgba(56,189,248,0.3)" }}>Dry-Run</span>
          )}
          <div style={{ flex: 1 }} />
          {step.rows != null && (
            <span style={{ fontSize: 11, fontWeight: 700, color: st.color, backgroundColor: st.color + "18", padding: "2px 8px", borderRadius: 10 }}>{step.rows} Zeilen</span>
          )}
          {step.duration_ms != null && (
            <span style={{ fontSize: 10, color: S.textDim }}>{step.duration_ms}ms</span>
          )}
          {canExpand && (open ? <ChevronDown size={12} color={S.textDim} /> : <ChevronRight size={12} color={S.textDim} />)}
        </div>
      </div>

      {open && (
        <div style={{ padding: "6px 14px 2px" }}>
          {step.message && <p style={{ fontSize: 11, color: step.status === "error" ? "#e07070" : S.textDim, margin: "2px 0" }}>{step.message}</p>}
          {step.errors?.length > 0 && step.errors.map((e, i) => (
            <p key={i} style={{ fontSize: 11, color: "#e07070", margin: "2px 0" }}>✗ {e}</p>
          ))}
          {step.sample?.length > 0 && <MiniSample sample={step.sample} color={st.color} />}
          {step.sub_trace?.length > 0 && <SubTrace trace={step.sub_trace} />}
        </div>
      )}

      {!isLast && <div style={{ width: 2, height: 14, backgroundColor: S.border, margin: "0 27px" }} />}
    </div>
  );
}

export default function PipelineRunPanel({ data, nodes = [], onClose }) {
  const results = data?.results || {};
  const order = data?.order || Object.keys(results);
  const errors = data?.errors || [];
  const nodeLabel = (nid) => {
    const n = nodes.find(x => x.id === nid);
    return n?.label || n?.config?.label || null;
  };
  const steps = order.map(nid => ({ id: nid, ...results[nid], label: results[nid]?.label || nodeLabel(nid) }));
  const totalMs = steps.reduce((s, x) => s + (x.duration_ms || 0), 0);
  const anyDry = steps.some(s => s.dry_run);

  return (
    <div style={{
      position: "absolute", bottom: 0, left: 0, right: 0,
      backgroundColor: S.bgCard, borderTop: `1px solid ${S.border}`, zIndex: 50,
      display: "flex", flexDirection: "column", maxHeight: "70%",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 16px", borderBottom: `1px solid ${S.border}`, flexShrink: 0 }}>
        <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: S.accent }}>Pipeline-Trace</span>
        {anyDry && (
          <span style={{ fontSize: 10, color: "#38bdf8", backgroundColor: "rgba(56,189,248,0.12)", padding: "2px 8px", borderRadius: 10, border: "1px solid rgba(56,189,248,0.25)" }}>Dry-Run (Seiteneffekte simuliert)</span>
        )}
        <span style={{ fontSize: 10, color: S.textDim }}>{steps.length} Nodes · {totalMs}ms</span>
        {errors.length > 0 && (
          <span style={{ fontSize: 10, color: "#f87171", backgroundColor: "rgba(248,113,113,0.12)", padding: "2px 8px", borderRadius: 10, border: "1px solid rgba(248,113,113,0.25)" }}>⚠ {errors.length} Fehler</span>
        )}
        <div style={{ flex: 1 }} />
        <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: S.textDim, padding: 4 }}>
          <X size={14} />
        </button>
      </div>

      <div style={{ overflowY: "auto", padding: "12px 16px" }}>
        {steps.length === 0 && (
          <p style={{ fontSize: 12, color: S.textDim, textAlign: "center", padding: "20px 0" }}>Keine Trace-Daten.</p>
        )}
        {steps.map((step, i) => (
          <NodeStep key={step.id || i} step={step} isLast={i === steps.length - 1} />
        ))}
      </div>
    </div>
  );
}
