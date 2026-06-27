import { useState, useCallback } from "react";
import { Play, Loader2, AlertCircle, X } from "lucide-react";
import api from "../../api/client";
import WidgetRenderer from "./WidgetRenderer";

const S = {
  bgMain: "var(--bg-main)", bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)",
  border: "var(--border)", textMain: "var(--text-main)", textDim: "var(--text-dim)",
  textBright: "var(--text-bright)", accent: "var(--accent)",
};

const inputStyle = {
  width: "100%", backgroundColor: S.bgEl, border: `1px solid ${S.border}`,
  borderRadius: 5, color: S.textMain, fontSize: 12, padding: "7px 10px",
  outline: "none", boxSizing: "border-box",
};

function FieldInput({ field, value, onChange }) {
  const s = inputStyle;
  switch (field.type) {
    case "number":   return <input type="number" value={value} onChange={e => onChange(e.target.value)} style={s} />;
    case "date":     return <input type="date"   value={value} onChange={e => onChange(e.target.value)} style={s} />;
    case "time":     return <input type="time"   value={value} onChange={e => onChange(e.target.value)} style={s} />;
    case "textarea": return <textarea value={value} rows={3} onChange={e => onChange(e.target.value)} style={{ ...s, resize: "vertical" }} placeholder={field.placeholder} />;
    case "checkbox":
    case "switch":
      return (
        <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
          <input type="checkbox" checked={!!value} onChange={e => onChange(e.target.checked)} style={{ width: 15, height: 15 }} />
          <span style={{ fontSize: 12 }}>{field.label}</span>
        </label>
      );
    case "dropdown":
      return (
        <select value={value} onChange={e => onChange(e.target.value)} style={{ ...s, cursor: "pointer" }}>
          <option value="">— auswählen —</option>
          {(field.options || []).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      );
    case "multiselect":
      return (
        <select multiple value={Array.isArray(value) ? value : []} onChange={e => onChange([...e.target.selectedOptions].map(o => o.value))}
          style={{ ...s, height: 80, cursor: "pointer" }}>
          {(field.options || []).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      );
    case "radio":
      return (
        <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          {(field.options || []).map(o => (
            <label key={o.value} style={{ display: "flex", alignItems: "center", gap: 7, cursor: "pointer", fontSize: 12 }}>
              <input type="radio" name={field.id} value={o.value} checked={value === o.value}
                onChange={() => onChange(o.value)} style={{ width: 13, height: 13 }} />
              {o.label}
            </label>
          ))}
        </div>
      );
    case "file":
      return <input type="file" style={{ ...s, padding: "5px" }} />;
    case "button": return null; // rendered separately
    case "heading": return <h2 style={{ fontSize: 16, fontWeight: 700, color: S.textBright, margin: 0 }}>{field.content}</h2>;
    case "label":   return <p style={{ fontSize: 12, color: S.textDim, margin: 0, lineHeight: 1.6 }}>{field.content}</p>;
    case "divider": return <hr style={{ border: "none", borderTop: `1px solid ${S.border}`, margin: "4px 0" }} />;
    default:
      return <input type="text" value={value} onChange={e => onChange(e.target.value)}
        placeholder={field.placeholder || field.label} style={s} />;
  }
}

function groupByRow(fields) {
  const rowMap = {};
  for (const f of fields) {
    const r = f.row ?? 0;
    if (!rowMap[r]) rowMap[r] = [];
    rowMap[r].push(f);
  }
  return Object.entries(rowMap)
    .sort(([a], [b]) => Number(a) - Number(b))
    .map(([, items]) => items);
}

const LAYOUT_TYPES = new Set(["heading", "label", "divider", "container", "button"]);
const LABEL_SKIP   = new Set(["checkbox", "switch", "button", "heading", "label", "divider", "container"]);

export default function FormPreview({ schema, formId, onClose }) {
  const fields  = schema?.fields  || [];
  const actions = schema?.actions || [];
  const widgets = schema?.widgets || [];
  const widgetActionIds = new Set(widgets.map(w => w.action_id).filter(Boolean));
  const rawResultActions = actions.filter(a => !widgetActionIds.has(a.id));
  const [params, setParams] = useState(() => {
    const d = {};
    for (const f of fields) d[f.name] = f.default ?? "";
    return d;
  });
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError]     = useState(null);

  const setParam = useCallback((name, v) => setParams(p => ({ ...p, [name]: v })), []);

  const runAction = async (actionId) => {
    setRunning(true); setError(null);
    try {
      const ids = actionId ? [actionId] : null;
      const { data } = await api.post(`/api/forms/${formId}/run`, { params, action_ids: ids });
      setResults(data.results || {});
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally { setRunning(false); }
  };

  const rows = groupByRow(fields);

  return (
    <div style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.7)",
      zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
      <div style={{ backgroundColor: S.bgMain, borderRadius: 12, border: `1px solid ${S.border}`,
        width: "100%", maxWidth: 780, maxHeight: "90vh", display: "flex", flexDirection: "column",
        overflow: "hidden", boxShadow: "0 20px 60px rgba(0,0,0,0.6)" }}>

        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "12px 20px", borderBottom: `1px solid ${S.border}`, flexShrink: 0 }}>
          <span style={{ fontSize: 12, fontWeight: 700, color: S.textBright }}>
            Vorschau — so sehen Benutzer das Formular
          </span>
          <button onClick={onClose} style={{ background: "none", border: "none", color: S.textDim,
            cursor: "pointer", display: "flex" }}>
            <X size={16} />
          </button>
        </div>

        {/* Form */}
        <div style={{ flex: 1, overflowY: "auto", padding: "24px 28px", scrollbarWidth: "thin" }}>
          {error && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 14px",
              borderRadius: 6, backgroundColor: "rgba(224,112,112,0.1)",
              border: "1px solid rgba(224,112,112,0.3)", color: "#e07070", fontSize: 11, marginBottom: 16 }}>
              <AlertCircle size={12} /> {error}
            </div>
          )}

          {rows.map((rowFields, ri) => (
            <div key={ri} style={{ display: "flex", flexWrap: "wrap", margin: "0 -6px 12px" }}>
              {rowFields.map(f => {
                if (f.type === "button") {
                  const action = actions.find(a => a.id === f.action_id);
                  return (
                    <div key={f.id} style={{ flex: `0 0 ${(f.colSpan / 12) * 100}%`, padding: "0 6px" }}>
                      <button onClick={() => runAction(f.action_id || null)} disabled={running}
                        style={{ display: "inline-flex", alignItems: "center", gap: 7,
                          padding: "8px 20px", borderRadius: 6, fontSize: 12, fontWeight: 600,
                          backgroundColor: "rgba(110,231,183,0.12)", border: "1px solid rgba(110,231,183,0.4)",
                          color: "#6ee7b7", cursor: running ? "wait" : "pointer" }}>
                        {running ? <Loader2 size={12} /> : <Play size={12} />}
                        {f.label || "Ausführen"}
                      </button>
                    </div>
                  );
                }
                return (
                  <div key={f.id} style={{ flex: `0 0 ${(f.colSpan / 12) * 100}%`,
                    padding: "0 6px", marginBottom: 8, boxSizing: "border-box" }}>
                    {!LABEL_SKIP.has(f.type) && (
                      <label style={{ display: "block", fontSize: 10, fontWeight: 600,
                        color: S.textDim, marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                        {f.label || f.name}
                        {f.required && <span style={{ color: "#f87171", marginLeft: 3 }}>*</span>}
                      </label>
                    )}
                    <FieldInput field={f} value={params[f.name] ?? ""} onChange={v => setParam(f.name, v)} />
                  </div>
                );
              })}
            </div>
          ))}

          {/* Fallback run-button wenn kein Button-Feld vorhanden */}
          {!fields.some(f => f.type === "button") && actions.length > 0 && (
            <button onClick={() => runAction(null)} disabled={running}
              style={{ display: "inline-flex", alignItems: "center", gap: 7, marginTop: 8,
                padding: "8px 20px", borderRadius: 6, fontSize: 12, fontWeight: 600,
                backgroundColor: "rgba(110,231,183,0.12)", border: "1px solid rgba(110,231,183,0.4)",
                color: "#6ee7b7", cursor: running ? "wait" : "pointer" }}>
              {running ? <Loader2 size={12} /> : <Play size={12} />}
              Ausführen
            </button>
          )}

          {/* Widget-Ergebnisse */}
          {results && widgets.length > 0 && (
            <div style={{ marginTop: 20 }}>
              <WidgetRenderer widgets={widgets} results={results} allowDownload={false} />
            </div>
          )}

          {/* Rohtabellen für Aktionen ohne Widget */}
          {results && rawResultActions.map(action => {
            const result = results[action.id];
            if (!result) return null;
            const cols = result.columns || [];
            const rows = result.rows || [];
            return (
              <div key={action.id} style={{ marginTop: 20, border: `1px solid ${S.border}`,
                borderRadius: 8, overflow: "hidden" }}>
                <div style={{ padding: "8px 14px", borderBottom: `1px solid ${S.border}`,
                  display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 11, fontWeight: 600, color: S.textBright }}>
                    {action.label || "Ergebnis"}
                  </span>
                  {result.total !== undefined && (
                    <span style={{ fontSize: 10, color: S.textDim }}>{result.total} Zeilen</span>
                  )}
                </div>
                {result.error ? (
                  <div style={{ padding: 12, color: "#e07070", fontSize: 11 }}>{result.error}</div>
                ) : (
                  <div style={{ overflowX: "auto", maxHeight: 300 }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                      <thead>
                        <tr style={{ backgroundColor: S.bgEl }}>
                          {cols.map(c => (
                            <th key={c} style={{ padding: "6px 10px", textAlign: "left",
                              borderBottom: `1px solid ${S.border}`, color: S.textDim,
                              fontWeight: 600, whiteSpace: "nowrap" }}>{c}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((row, i) => (
                          <tr key={i} style={{ borderBottom: `1px solid ${S.border}` }}>
                            {cols.map(c => (
                              <td key={c} style={{ padding: "5px 10px" }}>{row[c] ?? ""}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
