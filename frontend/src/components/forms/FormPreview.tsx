import { useState, useCallback } from "react";
import { Play, Loader2, AlertCircle, X } from "lucide-react";
import api from "../../api/client";
import WidgetRenderer from "./WidgetRenderer";
import FormFields, { validateRequired } from "./FormFields";

const S = {
  bgMain: "var(--bg-main)", bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)",
  border: "var(--border)", textMain: "var(--text-main)", textDim: "var(--text-dim)",
  textBright: "var(--text-bright)", accent: "var(--accent)",
};

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
  const [missing, setMissing] = useState([]);

  const setParam = useCallback((name, v) => setParams(p => ({ ...p, [name]: v })), []);

  const runAction = async (actionIds) => {
    const miss = validateRequired(fields, params);
    if (miss.length) {
      setMissing(miss);
      setError("Bitte fülle die markierten Pflichtfelder aus.");
      return;
    }
    setMissing([]);
    setRunning(true); setError(null);
    try {
      const ids = (actionIds && actionIds.length) ? actionIds : null;
      const { data } = await api.post(`/api/forms/${formId}/run`, { params, action_ids: ids });
      setResults(data.results || {});
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally { setRunning(false); }
  };

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

          <FormFields
            fields={fields}
            params={params}
            setParam={setParam}
            onRunAction={runAction}
            running={running}
            compact
            errors={missing}
          />

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
