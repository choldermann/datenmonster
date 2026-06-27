import { useState, useEffect, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Play, Loader2, Pencil, AlertCircle } from "lucide-react";
import api from "../api/client";

const S = {
  bgMain: "var(--bg-main)", bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)",
  border: "var(--border)", textMain: "var(--text-main)", textBright: "var(--text-bright)",
  textDim: "var(--text-dim)", accent: "var(--accent)",
};

const FIELD_TYPE_INPUT = {
  text:     (f, val, set) => <input value={val} onChange={e => set(e.target.value)} placeholder={f.label} style={inputStyle} />,
  number:   (f, val, set) => <input type="number" value={val} onChange={e => set(e.target.value)} placeholder={f.label} style={inputStyle} />,
  date:     (f, val, set) => <input type="date" value={val} onChange={e => set(e.target.value)} style={inputStyle} />,
  textarea: (f, val, set) => <textarea value={val} onChange={e => set(e.target.value)} rows={3} placeholder={f.label} style={{ ...inputStyle, resize: "vertical" }} />,
  checkbox: (f, val, set) => <input type="checkbox" checked={!!val} onChange={e => set(e.target.checked)} style={{ width: 16, height: 16, cursor: "pointer" }} />,
};

const inputStyle = {
  width: "100%", backgroundColor: "var(--bg-elevated)", border: "1px solid var(--border)",
  borderRadius: 5, color: "var(--text-main)", fontSize: 12, padding: "6px 10px", outline: "none",
  boxSizing: "border-box",
};

function ResultTable({ columns, rows }) {
  if (!columns?.length) return <p style={{ fontSize: 11, color: S.textDim, padding: 8 }}>Keine Daten</p>;
  return (
    <div style={{ overflowX: "auto", maxHeight: 400 }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
        <thead>
          <tr style={{ backgroundColor: "var(--bg-elevated)", position: "sticky", top: 0 }}>
            {columns.map(c => (
              <th key={c} style={{ padding: "6px 10px", textAlign: "left", borderBottom: "1px solid var(--border)",
                color: S.textDim, fontWeight: 600, whiteSpace: "nowrap" }}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}
              onMouseEnter={e => e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.03)"}
              onMouseLeave={e => e.currentTarget.style.backgroundColor = ""}>
              {columns.map(c => (
                <td key={c} style={{ padding: "5px 10px", color: S.textMain }}>{row[c] ?? ""}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function FormRunner() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [form, setForm] = useState(null);
  const [params, setParams] = useState({});
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.get(`/api/forms/${id}`).then(({ data }) => {
      setForm(data);
      // Standardwerte setzen
      const defaults = {};
      for (const f of (data.schema?.fields || [])) {
        defaults[f.name] = f.default ?? "";
      }
      setParams(defaults);
    }).catch(() => setError("Formular nicht gefunden"));
  }, [id]);

  const setParam = useCallback((name, value) => {
    setParams(prev => ({ ...prev, [name]: value }));
  }, []);

  const runForm = async () => {
    setRunning(true);
    setError(null);
    try {
      const { data } = await api.post(`/api/forms/${id}/run`, { params });
      setResults(data.results || {});
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setRunning(false);
    }
  };

  if (!form && !error) return (
    <div style={{ height: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
      backgroundColor: S.bgMain, color: S.textDim, fontSize: 12 }}>
      Lädt…
    </div>
  );

  const schema = form?.schema || {};
  const fields = schema.fields || [];
  const actions = schema.actions || [];
  const widgets = schema.widgets || [];

  return (
    <div style={{ minHeight: "100vh", backgroundColor: S.bgMain, color: S.textMain }}>

      {/* Toolbar */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 16px",
        borderBottom: `1px solid ${S.border}`, backgroundColor: S.bgCard }}>
        <button onClick={() => navigate("/dashboard")}
          style={{ display: "flex", alignItems: "center", gap: 5, background: "none", border: "none",
            color: S.textDim, cursor: "pointer", fontSize: 12 }}>
          <ArrowLeft size={14} /> Dashboard
        </button>
        <div style={{ width: 1, height: 20, backgroundColor: S.border }} />
        <span style={{ flex: 1, fontSize: 14, fontWeight: 600, color: S.textBright }}>{form?.name}</span>
        <button onClick={() => navigate(`/forms/${id}`)}
          style={{ display: "flex", alignItems: "center", gap: 5, background: "none", border: "none",
            color: S.textDim, cursor: "pointer", fontSize: 12 }}>
          <Pencil size={12} /> Bearbeiten
        </button>
      </div>

      <div style={{ maxWidth: 900, margin: "0 auto", padding: "32px 20px" }}>

        {error && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 14px", borderRadius: 6,
            backgroundColor: "rgba(224,112,112,0.1)", border: "1px solid rgba(224,112,112,0.3)",
            color: "#e07070", fontSize: 12, marginBottom: 20 }}>
            <AlertCircle size={14} /> {error}
          </div>
        )}

        {/* Form Fields */}
        {fields.length > 0 ? (
          <div style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`, borderRadius: 10,
            padding: "20px 24px", marginBottom: 24 }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 16 }}>
              {fields.map(f => {
                const renderInput = FIELD_TYPE_INPUT[f.type] || FIELD_TYPE_INPUT.text;
                return (
                  <div key={f.name}>
                    <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: S.textDim,
                      marginBottom: 5, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                      {f.label || f.name}
                    </label>
                    {renderInput(f, params[f.name] ?? "", (v) => setParam(f.name, v))}
                  </div>
                );
              })}
            </div>

            <div style={{ marginTop: 20, display: "flex", gap: 10 }}>
              {actions.length > 0 ? (
                actions.map(a => (
                  <button key={a.id} onClick={runForm} disabled={running}
                    style={{ display: "flex", alignItems: "center", gap: 7, padding: "8px 18px",
                      borderRadius: 6, backgroundColor: "rgba(110,231,183,0.12)",
                      border: "1px solid rgba(110,231,183,0.35)", color: "#6ee7b7",
                      cursor: running ? "wait" : "pointer", fontSize: 13, fontWeight: 600 }}>
                    {running ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
                    {a.label || "Ausführen"}
                  </button>
                ))
              ) : (
                <button onClick={runForm} disabled={running}
                  style={{ display: "flex", alignItems: "center", gap: 7, padding: "8px 18px",
                    borderRadius: 6, backgroundColor: "rgba(110,231,183,0.12)",
                    border: "1px solid rgba(110,231,183,0.35)", color: "#6ee7b7",
                    cursor: running ? "wait" : "pointer", fontSize: 13, fontWeight: 600 }}>
                  {running ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
                  Ausführen
                </button>
              )}
            </div>
          </div>
        ) : (
          // Kein Schema → trotzdem Run-Button für verknüpfte Mappings
          <div style={{ textAlign: "center", padding: "40px 0", marginBottom: 24 }}>
            <p style={{ color: S.textDim, fontSize: 12, marginBottom: 16 }}>
              Dieses Formular hat noch keine Eingabefelder.
            </p>
            <button onClick={runForm} disabled={running}
              style={{ display: "inline-flex", alignItems: "center", gap: 7, padding: "8px 20px",
                borderRadius: 6, backgroundColor: "rgba(110,231,183,0.12)",
                border: "1px solid rgba(110,231,183,0.35)", color: "#6ee7b7",
                cursor: running ? "wait" : "pointer", fontSize: 13, fontWeight: 600 }}>
              {running ? <Loader2 size={13} /> : <Play size={13} />}
              Mappings ausführen
            </button>
          </div>
        )}

        {/* Results */}
        {results && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {Object.entries(results).map(([actionId, result]) => {
              const action = actions.find(a => a.id === actionId);
              return (
                <div key={actionId} style={{ backgroundColor: S.bgCard,
                  border: `1px solid ${S.border}`, borderRadius: 10, overflow: "hidden" }}>
                  <div style={{ padding: "10px 16px", borderBottom: `1px solid ${S.border}`,
                    display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: S.textBright }}>
                      {action?.label || actionId}
                    </span>
                    {result.total !== undefined && (
                      <span style={{ fontSize: 10, color: S.textDim }}>
                        {result.total} Zeilen
                      </span>
                    )}
                  </div>
                  {result.error ? (
                    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: 14,
                      color: "#e07070", fontSize: 11 }}>
                      <AlertCircle size={13} /> {result.error}
                    </div>
                  ) : (
                    <ResultTable columns={result.columns} rows={result.rows} />
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Widgets (Phase 4) */}
        {widgets.length > 0 && !results && (
          <p style={{ fontSize: 11, color: S.textDim, textAlign: "center" }}>
            {widgets.length} Widget(s) — Formular ausführen um Daten zu laden
          </p>
        )}
      </div>
    </div>
  );
}
