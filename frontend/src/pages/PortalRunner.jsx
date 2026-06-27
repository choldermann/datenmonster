import { useState, useEffect, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Play, Loader2, Download, AlertCircle, LogOut } from "lucide-react";
import api from "../api/client";
import { useAuth } from "../context/AuthContext";

const S = {
  bgMain: "var(--bg-main)", bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)",
  border: "var(--border)", textMain: "var(--text-main)", textBright: "var(--text-bright)",
  textDim: "var(--text-dim)", accent: "var(--accent)",
};

const inputStyle = {
  width: "100%", backgroundColor: "var(--bg-elevated)", border: "1px solid var(--border)",
  borderRadius: 6, color: "var(--text-main)", fontSize: 13, padding: "8px 12px",
  outline: "none", boxSizing: "border-box",
};

function FieldInput({ field, value, onChange }) {
  switch (field.type) {
    case "number":
      return <input type="number" value={value} onChange={e => onChange(e.target.value)} style={inputStyle} />;
    case "date":
      return <input type="date" value={value} onChange={e => onChange(e.target.value)} style={inputStyle} />;
    case "textarea":
      return <textarea value={value} onChange={e => onChange(e.target.value)} rows={3}
        placeholder={field.label} style={{ ...inputStyle, resize: "vertical" }} />;
    case "checkbox":
      return (
        <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
          <input type="checkbox" checked={!!value} onChange={e => onChange(e.target.checked)}
            style={{ width: 16, height: 16 }} />
          <span style={{ fontSize: 13, color: S.textMain }}>{field.label}</span>
        </label>
      );
    default:
      return <input type="text" value={value} onChange={e => onChange(e.target.value)}
        placeholder={field.label} style={inputStyle} />;
  }
}

function ResultTable({ columns, rows, downloadDisabled, formName, actionLabel }) {
  if (!columns?.length) return <p style={{ padding: 16, color: S.textDim, fontSize: 12 }}>Keine Daten</p>;

  const downloadCsv = () => {
    if (downloadDisabled) return;
    const header = columns.join(";");
    const body = rows.map(r => columns.map(c => `"${(r[c] ?? "").toString().replace(/"/g, '""')}"`).join(";")).join("\n");
    const blob = new Blob(["﻿" + header + "\n" + body], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = `${formName}-${actionLabel}.csv`; a.click();
  };

  return (
    <div>
      {!downloadDisabled && (
        <div style={{ display: "flex", justifyContent: "flex-end", padding: "8px 16px" }}>
          <button onClick={downloadCsv}
            style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11,
              color: S.accent, background: "none", border: `1px solid ${S.border}`,
              borderRadius: 5, padding: "4px 10px", cursor: "pointer" }}>
            <Download size={11} /> CSV
          </button>
        </div>
      )}
      <div style={{ overflowX: "auto", maxHeight: 500 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr style={{ position: "sticky", top: 0, backgroundColor: S.bgEl }}>
              {columns.map(c => (
                <th key={c} style={{ padding: "8px 12px", textAlign: "left",
                  borderBottom: `1px solid ${S.border}`, color: S.textDim,
                  fontWeight: 600, whiteSpace: "nowrap", fontSize: 11 }}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} style={{ borderBottom: `1px solid ${S.border}` }}
                onMouseEnter={e => e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.02)"}
                onMouseLeave={e => e.currentTarget.style.backgroundColor = ""}>
                {columns.map(c => (
                  <td key={c} style={{ padding: "7px 12px", color: S.textMain }}>{row[c] ?? ""}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function PortalRunner() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [form, setForm] = useState(null);
  const [params, setParams] = useState({});
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.get(`/api/portal/forms/${slug}`)
      .then(({ data }) => {
        setForm(data);
        const defaults = {};
        for (const f of (data.fields || [])) {
          defaults[f.name] = f.default ?? "";
        }
        setParams(defaults);
      })
      .catch(() => setError("Formular nicht gefunden oder kein Zugriff."));
  }, [slug]);

  const setParam = useCallback((name, value) => {
    setParams(prev => ({ ...prev, [name]: value }));
  }, []);

  const runForm = async () => {
    setRunning(true); setError(null);
    try {
      const { data } = await api.post(`/api/portal/forms/${slug}/run`, { params });
      setResults(data.results || {});
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally { setRunning(false); }
  };

  const handleLogout = () => { logout(); navigate("/login"); };

  if (!form && !error) return (
    <div style={{ height: "100vh", display: "flex", alignItems: "center",
      justifyContent: "center", backgroundColor: S.bgMain, color: S.textDim }}>
      Lädt…
    </div>
  );

  const fields  = form?.fields  || [];
  const actions = form?.actions || [];

  return (
    <div style={{ minHeight: "100vh", backgroundColor: S.bgMain, color: S.textMain }}>
      {/* Header */}
      <header style={{ borderBottom: `1px solid ${S.border}`, backgroundColor: S.bgCard }}>
        <div style={{ maxWidth: 1100, margin: "0 auto", padding: "12px 24px",
          display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <button onClick={() => navigate("/portal")}
              style={{ display: "flex", alignItems: "center", gap: 5, background: "none",
                border: "none", color: S.textDim, cursor: "pointer", fontSize: 12 }}>
              <ArrowLeft size={13} /> Übersicht
            </button>
            <span style={{ color: S.border }}>|</span>
            <span style={{ fontSize: 14, fontWeight: 600, color: S.textBright }}>{form?.name}</span>
          </div>
          <button onClick={handleLogout}
            style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11,
              color: S.textDim, background: "none", border: "none", cursor: "pointer" }}>
            <LogOut size={12} /> Abmelden
          </button>
        </div>
      </header>

      <main style={{ maxWidth: 1100, margin: "0 auto", padding: "32px 24px" }}>
        {error && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "12px 16px",
            borderRadius: 8, backgroundColor: "rgba(224,112,112,0.1)",
            border: "1px solid rgba(224,112,112,0.3)", color: "#e07070", fontSize: 12, marginBottom: 24 }}>
            <AlertCircle size={14} /> {error}
          </div>
        )}

        {/* Input-Bereich */}
        {fields.length > 0 && (
          <div style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`,
            borderRadius: 12, padding: "24px 28px", marginBottom: 28 }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 18 }}>
              {fields.map(f => (
                <div key={f.name}>
                  {f.type !== "checkbox" && (
                    <label style={{ display: "block", fontSize: 11, fontWeight: 600,
                      color: S.textDim, marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                      {f.label || f.name}
                    </label>
                  )}
                  <FieldInput field={f} value={params[f.name] ?? ""} onChange={v => setParam(f.name, v)} />
                </div>
              ))}
            </div>
            <div style={{ marginTop: 22, display: "flex", gap: 10, flexWrap: "wrap" }}>
              {(actions.length > 0 ? actions : [{ id: "_default", label: "Ausführen" }]).map(a => (
                <button key={a.id} onClick={runForm} disabled={running}
                  style={{ display: "inline-flex", alignItems: "center", gap: 8,
                    padding: "10px 22px", borderRadius: 8, fontSize: 13, fontWeight: 600,
                    backgroundColor: "rgba(110,231,183,0.12)", border: "1px solid rgba(110,231,183,0.4)",
                    color: "#6ee7b7", cursor: running ? "wait" : "pointer" }}>
                  {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
                  {a.label || "Ausführen"}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Ergebnisse */}
        {results && Object.entries(results).map(([actionId, result]) => {
          const action = actions.find(a => a.id === actionId);
          return (
            <div key={actionId} style={{ backgroundColor: S.bgCard,
              border: `1px solid ${S.border}`, borderRadius: 12, overflow: "hidden", marginBottom: 16 }}>
              <div style={{ padding: "12px 16px", borderBottom: `1px solid ${S.border}`,
                display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: S.textBright }}>
                  {action?.label || "Ergebnis"}
                </span>
                {result.total !== undefined && (
                  <span style={{ fontSize: 11, color: S.textDim }}>{result.total} Zeilen</span>
                )}
              </div>
              {result.error ? (
                <div style={{ padding: 16, color: "#e07070", fontSize: 12, display: "flex", gap: 8 }}>
                  <AlertCircle size={13} /> {result.error}
                </div>
              ) : (
                <ResultTable
                  columns={result.columns}
                  rows={result.rows}
                  downloadDisabled={result.download_disabled || !form?.allow_download}
                  formName={form?.name || "export"}
                  actionLabel={action?.label || actionId}
                />
              )}
            </div>
          );
        })}
      </main>
    </div>
  );
}
