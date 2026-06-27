import { useState, useEffect, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Play, Loader2, Download, AlertCircle, LogOut, ChevronDown } from "lucide-react";
import api from "../api/client";
import { useAuth } from "../context/AuthContext";

const S = {
  bgMain: "var(--bg-main)", bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)",
  border: "var(--border)", textMain: "var(--text-main)", textBright: "var(--text-bright)",
  textDim: "var(--text-dim)", accent: "var(--accent)",
};

const inp = {
  width: "100%", backgroundColor: "var(--bg-elevated)", border: "1px solid var(--border)",
  borderRadius: 6, color: "var(--text-main)", fontSize: 14, padding: "9px 12px",
  outline: "none", boxSizing: "border-box",
};

// ── Field renderer ────────────────────────────────────────────────────────────

function FieldInput({ field, value, onChange, onButtonClick, running }) {
  switch (field.type) {
    case "number":
      return <input type="number" value={value ?? ""} onChange={e => onChange(e.target.value)} style={inp} placeholder={field.placeholder} />;
    case "date":
      return <input type="date" value={value ?? ""} onChange={e => onChange(e.target.value)} style={inp} />;
    case "time":
      return <input type="time" value={value ?? ""} onChange={e => onChange(e.target.value)} style={inp} />;
    case "textarea":
      return <textarea value={value ?? ""} onChange={e => onChange(e.target.value)} rows={3}
        placeholder={field.placeholder || field.label} style={{ ...inp, resize: "vertical" }} />;
    case "checkbox":
    case "switch":
      return (
        <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", padding: "9px 0" }}>
          <input type="checkbox" checked={!!value} onChange={e => onChange(e.target.checked)}
            style={{ width: 17, height: 17, cursor: "pointer" }} />
          <span style={{ fontSize: 14, color: S.textMain }}>{field.label}</span>
        </label>
      );
    case "dropdown":
      return (
        <div style={{ position: "relative" }}>
          <select value={value ?? ""} onChange={e => onChange(e.target.value)}
            style={{ ...inp, cursor: "pointer", appearance: "none", paddingRight: 32 }}>
            <option value="">— bitte auswählen —</option>
            {(field.options || []).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <ChevronDown size={14} style={{ position: "absolute", right: 10, top: "50%",
            transform: "translateY(-50%)", pointerEvents: "none", color: S.textDim }} />
        </div>
      );
    case "multiselect":
      return (
        <select multiple value={Array.isArray(value) ? value : []}
          onChange={e => onChange([...e.target.selectedOptions].map(o => o.value))}
          style={{ ...inp, height: 96, cursor: "pointer" }}>
          {(field.options || []).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      );
    case "radio":
      return (
        <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: "4px 0" }}>
          {(field.options || []).map(o => (
            <label key={o.value} style={{ display: "flex", alignItems: "center", gap: 9,
              cursor: "pointer", fontSize: 14 }}>
              <input type="radio" name={field.id} value={o.value} checked={value === o.value}
                onChange={() => onChange(o.value)} style={{ width: 15, height: 15 }} />
              {o.label}
            </label>
          ))}
        </div>
      );
    case "file":
      return <input type="file" style={{ ...inp, padding: "7px" }} />;
    case "heading":
      return <h2 style={{ fontSize: 22, fontWeight: 700, color: S.textBright, margin: "8px 0 4px" }}>
        {field.content || field.label}
      </h2>;
    case "label":
      return <p style={{ fontSize: 14, color: S.textDim, margin: "2px 0", lineHeight: 1.7 }}>
        {field.content || field.label}
      </p>;
    case "divider":
      return <hr style={{ border: "none", borderTop: `1px solid ${S.border}`, margin: "8px 0" }} />;
    case "button":
      return (
        <button onClick={() => onButtonClick(field.action_id)} disabled={running}
          style={{ display: "inline-flex", alignItems: "center", gap: 8,
            padding: "10px 24px", borderRadius: 8, fontSize: 14, fontWeight: 600,
            backgroundColor: "rgba(110,231,183,0.12)", border: "1px solid rgba(110,231,183,0.4)",
            color: "#6ee7b7", cursor: running ? "wait" : "pointer", marginTop: 4 }}>
          {running ? <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} /> : <Play size={14} />}
          {field.label || "Ausführen"}
        </button>
      );
    default:
      return <input type="text" value={value ?? ""} onChange={e => onChange(e.target.value)}
        placeholder={field.placeholder || field.label} style={inp} />;
  }
}

// ── Layout helpers ────────────────────────────────────────────────────────────

const LAYOUT_TYPES = new Set(["heading", "label", "divider"]);
const LABEL_SKIP   = new Set(["checkbox", "switch", "button", "heading", "label", "divider"]);

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

// ── Result table ──────────────────────────────────────────────────────────────

function ResultTable({ result, formName, actionLabel, allowDownload }) {
  const { columns = [], rows = [], total, error, download_disabled } = result;
  const canDownload = allowDownload && !download_disabled;

  const downloadCsv = () => {
    const header = columns.join(";");
    const body = rows.map(r =>
      columns.map(c => `"${(r[c] ?? "").toString().replace(/"/g, '""')}"`).join(";")
    ).join("\n");
    const blob = new Blob(["﻿" + header + "\n" + body], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${formName}-${actionLabel}.csv`;
    a.click();
  };

  if (error) return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "14px 18px",
      color: "#e07070", fontSize: 13 }}>
      <AlertCircle size={14} /> {error}
    </div>
  );

  if (!columns.length) return (
    <p style={{ padding: "16px 18px", color: S.textDim, fontSize: 13 }}>Keine Daten zurückgegeben.</p>
  );

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 18px", borderBottom: `1px solid ${S.border}` }}>
        {total !== undefined && <span style={{ fontSize: 12, color: S.textDim }}>{total} Zeilen</span>}
        {canDownload && (
          <button onClick={downloadCsv}
            style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11,
              color: S.accent, background: "none", border: `1px solid ${S.border}`,
              borderRadius: 5, padding: "4px 10px", cursor: "pointer" }}>
            <Download size={11} /> CSV
          </button>
        )}
      </div>
      <div style={{ overflowX: "auto", maxHeight: 520 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ position: "sticky", top: 0, backgroundColor: S.bgEl }}>
              {columns.map(c => (
                <th key={c} style={{ padding: "9px 14px", textAlign: "left",
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
                  <td key={c} style={{ padding: "8px 14px", color: S.textMain }}>{row[c] ?? ""}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function PortalRunner() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const { logout } = useAuth();

  const [form, setForm]       = useState(null);
  const [params, setParams]   = useState({});
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState(null);
  const [loadErr, setLoadErr] = useState(null);
  const [runErr, setRunErr]   = useState(null);

  useEffect(() => {
    api.get(`/api/portal/forms/${slug}`)
      .then(({ data }) => {
        setForm(data);
        const defaults = {};
        for (const f of (data.fields || [])) {
          if (f.name) defaults[f.name] = f.default ?? "";
        }
        setParams(defaults);
      })
      .catch(() => setLoadErr("Formular nicht gefunden oder kein Zugriff."));
  }, [slug]);

  const setParam = useCallback((name, value) => {
    setParams(prev => ({ ...prev, [name]: value }));
  }, []);

  const runAction = async (actionId) => {
    setRunning(true); setRunErr(null);
    try {
      const body = { params, action_ids: actionId ? [actionId] : null };
      const { data } = await api.post(`/api/portal/forms/${slug}/run`, body);
      setResults(data.results || {});
    } catch (e) {
      setRunErr(e.response?.data?.detail || e.message);
    } finally { setRunning(false); }
  };

  const handleLogout = () => { logout(); navigate("/login"); };

  // Loading
  if (!form && !loadErr) return (
    <div style={{ height: "100vh", display: "flex", alignItems: "center",
      justifyContent: "center", backgroundColor: S.bgMain, color: S.textDim, fontSize: 14 }}>
      Lädt…
    </div>
  );

  const fields  = form?.fields  || [];
  const actions = form?.actions || [];
  const hasButtonField = fields.some(f => f.type === "button");
  const allowDownload  = form?.allow_download || false;
  const rows = groupByRow(fields);

  return (
    <div style={{ minHeight: "100vh", backgroundColor: S.bgMain, color: S.textMain }}>

      {/* ── Header ── */}
      <header style={{ position: "sticky", top: 0, zIndex: 10,
        borderBottom: `1px solid ${S.border}`, backgroundColor: S.bgCard }}>
        <div style={{ maxWidth: 1100, margin: "0 auto", padding: "12px 24px",
          display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <button onClick={() => navigate("/portal")}
              style={{ display: "flex", alignItems: "center", gap: 5, background: "none",
                border: "none", color: S.textDim, cursor: "pointer", fontSize: 13 }}>
              <ArrowLeft size={14} /> Übersicht
            </button>
            <span style={{ color: S.border }}>|</span>
            <span style={{ fontSize: 15, fontWeight: 600, color: S.textBright }}>
              {form?.icon && <span style={{ marginRight: 6 }}>{form.icon}</span>}
              {form?.name || slug}
            </span>
          </div>
          <button onClick={handleLogout}
            style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12,
              color: S.textDim, background: "none", border: "none", cursor: "pointer" }}>
            <LogOut size={13} /> Abmelden
          </button>
        </div>
      </header>

      {/* ── Main ── */}
      <main style={{ maxWidth: 1100, margin: "0 auto", padding: "36px 24px" }}>

        {/* Load error */}
        {loadErr && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "14px 18px",
            borderRadius: 8, backgroundColor: "rgba(224,112,112,0.1)",
            border: "1px solid rgba(224,112,112,0.3)", color: "#e07070", fontSize: 13 }}>
            <AlertCircle size={14} /> {loadErr}
          </div>
        )}

        {/* Description */}
        {form?.description && (
          <p style={{ fontSize: 14, color: S.textDim, marginBottom: 28, lineHeight: 1.6 }}>
            {form.description}
          </p>
        )}

        {/* ── Form card ── */}
        {fields.length > 0 && (
          <div style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`,
            borderRadius: 14, padding: "28px 32px", marginBottom: 32 }}>

            {rows.map((rowFields, ri) => (
              <div key={ri} style={{ display: "flex", flexWrap: "wrap", margin: "0 -10px 16px" }}>
                {rowFields.map(f => {
                  const isLayout = LAYOUT_TYPES.has(f.type);
                  const width = `${((f.colSpan || 12) / 12) * 100}%`;
                  return (
                    <div key={f.id || f.name} style={{ flex: `0 0 ${width}`, maxWidth: width,
                      padding: "0 10px", boxSizing: "border-box" }}>
                      {!LABEL_SKIP.has(f.type) && f.label && (
                        <label style={{ display: "block", fontSize: 12, fontWeight: 600,
                          color: S.textDim, marginBottom: 6, textTransform: "uppercase",
                          letterSpacing: "0.05em" }}>
                          {f.label}
                          {f.required && <span style={{ color: "#f87171", marginLeft: 3 }}>*</span>}
                        </label>
                      )}
                      <FieldInput
                        field={f}
                        value={params[f.name]}
                        onChange={v => setParam(f.name, v)}
                        onButtonClick={runAction}
                        running={running}
                      />
                    </div>
                  );
                })}
              </div>
            ))}

            {/* Fallback-Buttons wenn kein Button-Feld im Schema */}
            {!hasButtonField && actions.length > 0 && (
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 12 }}>
                {actions.map(a => (
                  <button key={a.id} onClick={() => runAction(a.id)} disabled={running}
                    style={{ display: "inline-flex", alignItems: "center", gap: 8,
                      padding: "10px 24px", borderRadius: 8, fontSize: 14, fontWeight: 600,
                      backgroundColor: "rgba(110,231,183,0.12)",
                      border: "1px solid rgba(110,231,183,0.4)",
                      color: "#6ee7b7", cursor: running ? "wait" : "pointer" }}>
                    {running ? <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} /> : <Play size={14} />}
                    {a.label || "Ausführen"}
                  </button>
                ))}
              </div>
            )}

            {/* Lauft... Indikator */}
            {running && (
              <div style={{ marginTop: 16, display: "flex", alignItems: "center", gap: 8,
                fontSize: 12, color: S.textDim }}>
                <Loader2 size={12} style={{ animation: "spin 1s linear infinite" }} />
                Wird ausgeführt…
              </div>
            )}
          </div>
        )}

        {/* Run error */}
        {runErr && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "12px 16px",
            borderRadius: 8, backgroundColor: "rgba(224,112,112,0.1)",
            border: "1px solid rgba(224,112,112,0.3)", color: "#e07070", fontSize: 13,
            marginBottom: 20 }}>
            <AlertCircle size={14} /> {runErr}
          </div>
        )}

        {/* ── Ergebnisse ── */}
        {results && Object.entries(results).map(([actionId, result]) => {
          const action = actions.find(a => a.id === actionId);
          return (
            <div key={actionId} style={{ backgroundColor: S.bgCard,
              border: `1px solid ${S.border}`, borderRadius: 14,
              overflow: "hidden", marginBottom: 20 }}>
              <div style={{ padding: "14px 20px", borderBottom: `1px solid ${S.border}`,
                display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span style={{ fontSize: 14, fontWeight: 700, color: S.textBright }}>
                  {action?.label || "Ergebnis"}
                </span>
              </div>
              <ResultTable
                result={result}
                formName={form?.name || "export"}
                actionLabel={action?.label || actionId}
                allowDownload={allowDownload}
              />
            </div>
          );
        })}
      </main>

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
