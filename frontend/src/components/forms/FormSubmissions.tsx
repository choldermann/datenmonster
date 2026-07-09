import { useState, useEffect, useCallback } from "react";
import { X, Loader2, AlertCircle, Trash2, Inbox } from "lucide-react";
import api from "../../api/client";

const S = {
  bgMain: "var(--bg-main)", bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)",
  border: "var(--border)", textMain: "var(--text-main)", textDim: "var(--text-dim)",
  textBright: "var(--text-bright)", accent: "var(--accent)",
};

function fmtValue(v) {
  if (v === null || v === undefined || v === "") return "—";
  if (Array.isArray(v)) return v.join(", ");
  if (v === true) return "✓";
  if (v === false) return "✗";
  return String(v);
}

function fmtDate(s) {
  if (!s) return "";
  const d = new Date(s);
  return isNaN(d.getTime()) ? s : d.toLocaleString("de-DE");
}

export default function FormSubmissions({ formId, onClose }) {
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  const [fields, setFields]   = useState([]);
  const [subs, setSubs]       = useState([]);

  const load = useCallback(() => {
    setLoading(true); setError(null);
    api.get(`/api/forms/${formId}/submissions`)
      .then(({ data }) => { setFields(data.fields || []); setSubs(data.submissions || []); })
      .catch(e => setError(e.response?.data?.detail || e.message))
      .finally(() => setLoading(false));
  }, [formId]);

  useEffect(() => { load(); }, [load]);

  const clearAll = async () => {
    if (!window.confirm("Alle protokollierten Einträge dieses Formulars löschen?")) return;
    try { await api.delete(`/api/forms/${formId}/submissions`); load(); }
    catch (e) { setError(e.response?.data?.detail || e.message); }
  };

  const th = { padding: "7px 12px", textAlign: "left", borderBottom: `1px solid ${S.border}`,
    color: S.textDim, fontWeight: 600, whiteSpace: "nowrap", fontSize: 10,
    textTransform: "uppercase", letterSpacing: "0.04em", position: "sticky", top: 0,
    backgroundColor: S.bgEl };
  const td = { padding: "6px 12px", color: S.textMain, whiteSpace: "nowrap", fontSize: 12 };

  return (
    <div style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.7)", zIndex: 100,
      display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}
      onClick={onClose}>
      <div onClick={e => e.stopPropagation()}
        style={{ backgroundColor: S.bgMain, borderRadius: 12, border: `1px solid ${S.border}`,
          width: "100%", maxWidth: 1000, maxHeight: "88vh", display: "flex", flexDirection: "column",
          overflow: "hidden", boxShadow: "0 20px 60px rgba(0,0,0,0.6)" }}>

        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "12px 20px", borderBottom: `1px solid ${S.border}`, flexShrink: 0 }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: S.textBright }}>
            Einträge {subs.length > 0 && <span style={{ color: S.textDim, fontWeight: 400 }}>({subs.length})</span>}
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {subs.length > 0 && (
              <button onClick={clearAll}
                style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11,
                  color: "#e07070", background: "none", border: `1px solid ${S.border}`,
                  borderRadius: 5, padding: "4px 10px", cursor: "pointer" }}>
                <Trash2 size={12} /> Leeren
              </button>
            )}
            <button onClick={onClose} style={{ background: "none", border: "none", color: S.textDim,
              cursor: "pointer", display: "flex" }}>
              <X size={16} />
            </button>
          </div>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflow: "auto", scrollbarWidth: "thin" }}>
          {loading ? (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center",
              gap: 8, padding: 60, color: S.textDim, fontSize: 12 }}>
              <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} /> Lädt…
            </div>
          ) : error ? (
            <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "16px 20px",
              color: "#e07070", fontSize: 12 }}>
              <AlertCircle size={14} /> {error}
            </div>
          ) : subs.length === 0 ? (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center",
              justifyContent: "center", gap: 10, padding: 60, color: S.textDim }}>
              <Inbox size={28} style={{ opacity: 0.4 }} />
              <p style={{ fontSize: 12 }}>Noch keine Einträge. Jeder Formular-Lauf wird hier protokolliert.</p>
            </div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={th}>Zeitpunkt</th>
                  <th style={th}>Status</th>
                  {fields.map(f => <th key={f.name} style={th}>{f.label}</th>)}
                  <th style={th}>Zeilen</th>
                </tr>
              </thead>
              <tbody>
                {subs.map(s => {
                  const totalRows = Object.values(s.row_counts || {}).reduce((a, b) => a + (Number(b) || 0), 0);
                  return (
                    <tr key={s.id} style={{ borderBottom: `1px solid ${S.border}` }}
                      onMouseEnter={e => e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.02)"}
                      onMouseLeave={e => e.currentTarget.style.backgroundColor = ""}>
                      <td style={{ ...td, color: S.textDim }}>{fmtDate(s.submitted_at)}</td>
                      <td style={td}>
                        <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 4,
                          color: s.status === "error" ? "#e07070" : "#6ee7b7",
                          backgroundColor: s.status === "error" ? "rgba(224,112,112,0.12)" : "rgba(110,231,183,0.12)" }}
                          title={s.error || ""}>
                          {s.status === "error" ? "Fehler" : "OK"}
                        </span>
                      </td>
                      {fields.map(f => <td key={f.name} style={td}>{fmtValue(s.params?.[f.name])}</td>)}
                      <td style={{ ...td, color: S.textDim }}>{totalRows}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
