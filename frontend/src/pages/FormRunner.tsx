import { useState, useEffect, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Play, Loader2, Pencil, AlertCircle } from "lucide-react";
import api from "../api/client";
import WidgetRenderer from "../components/forms/WidgetRenderer";
import FormFields, { validateRequired } from "../components/forms/FormFields";

const S = {
  bgMain: "var(--bg-main)", bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)",
  border: "var(--border)", textMain: "var(--text-main)", textBright: "var(--text-bright)",
  textDim: "var(--text-dim)", accent: "var(--accent)",
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
  const [missing, setMissing] = useState([]);

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

  const runForm = async (actionIds = null) => {
    const miss = validateRequired(form?.schema?.fields || [], params);
    if (miss.length) {
      setMissing(miss);
      setError("Bitte fülle die markierten Pflichtfelder aus.");
      return;
    }
    setMissing([]);
    setRunning(true);
    setError(null);
    try {
      const { data } = await api.post(`/api/forms/${id}/run`, {
        params,
        action_ids: (actionIds && actionIds.length) ? actionIds : null,
      });
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
  const hasButtonField = fields.some(f => f.type === "button");
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
            <FormFields
              fields={fields}
              params={params}
              setParam={setParam}
              onRunAction={runForm}
              running={running}
              compact
              errors={missing}
            />

            {/* Fallback-Button wenn kein Button-Feld im Schema */}
            {!hasButtonField && (
              <div style={{ marginTop: 8, display: "flex", gap: 10, flexWrap: "wrap" }}>
                <button onClick={() => runForm(null)} disabled={running}
                  style={{ display: "flex", alignItems: "center", gap: 7, padding: "8px 18px",
                    borderRadius: 6, backgroundColor: "rgba(110,231,183,0.12)",
                    border: "1px solid rgba(110,231,183,0.35)", color: "#6ee7b7",
                    cursor: running ? "wait" : "pointer", fontSize: 13, fontWeight: 600 }}>
                  {running ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
                  Ausführen
                </button>
              </div>
            )}
          </div>
        ) : (
          // Kein Schema → trotzdem Run-Button für verknüpfte Mappings
          <div style={{ textAlign: "center", padding: "40px 0", marginBottom: 24 }}>
            <p style={{ color: S.textDim, fontSize: 12, marginBottom: 16 }}>
              Dieses Formular hat noch keine Eingabefelder.
            </p>
            <button onClick={() => runForm(null)} disabled={running}
              style={{ display: "inline-flex", alignItems: "center", gap: 7, padding: "8px 20px",
                borderRadius: 6, backgroundColor: "rgba(110,231,183,0.12)",
                border: "1px solid rgba(110,231,183,0.35)", color: "#6ee7b7",
                cursor: running ? "wait" : "pointer", fontSize: 13, fontWeight: 600 }}>
              {running ? <Loader2 size={13} /> : <Play size={13} />}
              Mappings ausführen
            </button>
          </div>
        )}

        {/* Widget-Ergebnisse */}
        {results && widgets.length > 0 && (
          <WidgetRenderer widgets={widgets} results={results} allowDownload={true} />
        )}

        {/* Rohtabellen für Aktionen ohne Widget */}
        {results && (() => {
          const widgetActionIds = new Set(widgets.map(w => w.action_id).filter(Boolean));
          const rawActions = actions.filter(a => !widgetActionIds.has(a.id));
          if (!rawActions.length) return null;
          return (
            <div style={{ display: "flex", flexDirection: "column", gap: 16,
              marginTop: widgets.length > 0 ? 16 : 0 }}>
              {rawActions.map(action => {
                const result = results[action.id];
                if (!result) return null;
                return (
                  <div key={action.id} style={{ backgroundColor: S.bgCard,
                    border: `1px solid ${S.border}`, borderRadius: 10, overflow: "hidden" }}>
                    <div style={{ padding: "10px 16px", borderBottom: `1px solid ${S.border}`,
                      display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                      <span style={{ fontSize: 12, fontWeight: 600, color: S.textBright }}>
                        {action.label || action.id}
                      </span>
                      {result.total !== undefined && (
                        <span style={{ fontSize: 10, color: S.textDim }}>{result.total} Zeilen</span>
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
          );
        })()}
      </div>
    </div>
  );
}
