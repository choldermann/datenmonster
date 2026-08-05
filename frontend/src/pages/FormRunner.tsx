import { useState, useEffect, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Play, Loader2, Pencil, AlertCircle, Check, Download } from "lucide-react";
import api from "../api/client";
import WidgetRenderer, { STANDALONE_WIDGET_TYPES } from "../components/forms/WidgetRenderer";
import FormFields, { validateRequired, PipelineResult } from "../components/forms/FormFields";
import IntrastatExclusionPanel from "../components/forms/IntrastatExclusionPanel";

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

function ExportResult({ result, onDownload }) {
  const files = result.files || [];
  return (
    <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#6ee7b7",
        fontSize: 12, fontWeight: 600 }}>
        <Check size={14} /> Export erzeugt · {result.total ?? 0} Zeilen
      </div>
      {files.length > 0 ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {files.map(f => (
            <button key={f.id} onClick={() => onDownload(f.id, f.file_name)}
              style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px",
                background: S.bgMain, border: `1px solid ${S.border}`, borderRadius: 6,
                color: S.textBright, cursor: "pointer", fontSize: 12, textAlign: "left" }}>
              <Download size={13} /> {f.file_name}
              {f.target_name && <span style={{ color: S.textDim, fontSize: 10 }}>· {f.target_name}</span>}
            </button>
          ))}
        </div>
      ) : (
        <span style={{ color: S.textDim, fontSize: 11 }}>
          Dateien liegen im Bereich „Exporte" zum Download.
        </span>
      )}
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
  const [activeTab, setActiveTab] = useState(null);
  const [inputTab, setInputTab] = useState("main");

  useEffect(() => {
    api.get(`/api/forms/${id}`).then(({ data }) => {
      setForm(data);
      // Standardwerte setzen. Mehrfachauswahl-Felder starten als leere Liste,
      // damit das Backend :name_empty=1 (= kein Filter) bindet.
      const isMulti = f => f.type === "multiselect" || (f.type === "db_dropdown" && f.config?.multiple);
      const defaults = {};
      for (const f of (data.schema?.fields || [])) {
        defaults[f.name] = f.default ?? (isMulti(f) ? [] : "");
      }
      setParams(defaults);
    }).catch(() => setError("Formular nicht gefunden"));
  }, [id]);

  const setParam = useCallback((name, value) => {
    setParams(prev => ({ ...prev, [name]: value }));
  }, []);

  const downloadExport = async (fileId, fileName) => {
    try {
      const resp = await api.get(`/api/exports/${fileId}/download`, { responseType: "blob" });
      const url = URL.createObjectURL(resp.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = fileName || `export_${fileId}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError("Download fehlgeschlagen: " + (e.response?.data?.detail || e.message));
    }
  };

  const runForm = async (actionIds = null, paramsOverride = null) => {
    const effParams = paramsOverride ? { ...params, ...paramsOverride } : params;
    if (paramsOverride) setParams(effParams);
    const miss = validateRequired(form?.schema?.fields || [], effParams);
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
        params: effParams,
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
  const allFields = schema.fields || [];
  // Ausschlussartikel-Feld separat behandeln: es bekommt einen eigenen Eingabe-Reiter.
  const exclusionField = allFields.find(f => f.type === "article_exclusion") || null;
  const fields = exclusionField ? allFields.filter(f => f !== exclusionField) : allFields;
  const hasButtonField = fields.some(f => f.type === "button");
  const actions = schema.actions || [];
  const widgets = schema.widgets || [];
  // Optionale Tab-Ansicht der Ergebnisse (aus schema.result_tabs). Jeder Tab
  // bündelt eine Auswahl an Action-IDs; ohne Konfiguration bleibt alles gestapelt.
  const resultTabs = schema.result_tabs || [];
  const currentTab = activeTab || resultTabs[0]?.id || null;
  const tabActionIds = resultTabs.length
    ? new Set((resultTabs.find(t => t.id === currentTab)?.action_ids) || [])
    : null;

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

      {/* Dashboards (mit Widgets) breiter rendern als reine Eingabeformulare. */}
      <div style={{ maxWidth: widgets.length ? 1200 : 900, margin: "0 auto", padding: "32px 20px" }}>

        {error && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 14px", borderRadius: 6,
            backgroundColor: "rgba(224,112,112,0.1)", border: "1px solid rgba(224,112,112,0.3)",
            color: "#e07070", fontSize: 12, marginBottom: 20 }}>
            <AlertCircle size={14} /> {error}
          </div>
        )}

        {/* Eingabe-Reiter (nur wenn ein Ausschlussartikel-Feld im Schema ist) */}
        {exclusionField && (
          <div style={{ display: "flex", gap: 4, marginBottom: 20, borderBottom: `1px solid ${S.border}` }}>
            {[{ id: "main", label: "Auswertung" },
              { id: "exclusions", label: exclusionField.label || "Ausschlussartikel" }].map(t => {
              const active = inputTab === t.id;
              return (
                <button key={t.id} onClick={() => setInputTab(t.id)}
                  style={{ padding: "8px 16px", background: "none", border: "none",
                    borderBottom: `2px solid ${active ? S.accent : "transparent"}`,
                    color: active ? S.textBright : S.textDim, cursor: "pointer",
                    fontSize: 13, fontWeight: active ? 600 : 400 }}>
                  {t.label}
                </button>
              );
            })}
          </div>
        )}

        {exclusionField && inputTab === "exclusions" && (() => {
          // Verbindung aus dem Template (config.connection_id, beim Install aufgelöst).
          // Nur übernehmen, wenn es eine gültige Zahl ist – sonst Auto-Erkennung im Panel.
          const cId = Number(exclusionField.config?.connection_id);
          return (
            <IntrastatExclusionPanel projectId={form.project_id}
              connectionId={Number.isFinite(cId) && cId > 0 ? cId : null} />
          );
        })()}

        {(!exclusionField || inputTab === "main") && (<>
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

        {/* Ergebnis-Tabs (optional, aus schema.result_tabs) */}
        {results && resultTabs.length > 0 && (
          <div style={{ display: "flex", gap: 4, marginBottom: 16,
            borderBottom: `1px solid ${S.border}`, flexWrap: "wrap" }}>
            {resultTabs.map(tab => {
              const active = tab.id === currentTab;
              return (
                <button key={tab.id} onClick={() => setActiveTab(tab.id)}
                  style={{ padding: "8px 16px", background: "none", border: "none",
                    borderBottom: `2px solid ${active ? "#6ee7b7" : "transparent"}`,
                    color: active ? S.textBright : S.textDim, cursor: "pointer",
                    fontSize: 12, fontWeight: 600, marginBottom: -1 }}>
                  {tab.label}
                </button>
              );
            })}
          </div>
        )}

        {/* Widgets: eigenständige (z.B. Eingangsrechnung) sofort, ergebnis-basierte nach Lauf */}
        {widgets.length > 0 && (results || widgets.some(w => STANDALONE_WIDGET_TYPES.has(w.type))) && (
          <WidgetRenderer
            widgets={tabActionIds ? widgets.filter(w => !w.action_id || tabActionIds.has(w.action_id)) : widgets}
            results={results || {}} allowDownload={true} baseParams={params} />
        )}

        {/* Rohtabellen für Aktionen ohne Widget */}
        {results && (() => {
          const widgetActionIds = new Set(widgets.map(w => w.action_id).filter(Boolean));
          const rawActions = actions.filter(a => !widgetActionIds.has(a.id)
            && (!tabActionIds || tabActionIds.has(a.id)));
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
                      {result.kind !== "pipeline" && result.total !== undefined && (
                        <span style={{ fontSize: 10, color: S.textDim }}>{result.total} Zeilen</span>
                      )}
                    </div>
                    {result.kind === "pipeline" ? (
                      <PipelineResult result={result} />
                    ) : result.error ? (
                      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: 14,
                        color: "#e07070", fontSize: 11 }}>
                        <AlertCircle size={13} /> {result.error}
                      </div>
                    ) : result.kind === "export" ? (
                      <ExportResult result={result} onDownload={downloadExport} />
                    ) : (
                      <ResultTable columns={result.columns} rows={result.rows} />
                    )}
                  </div>
                );
              })}
            </div>
          );
        })()}
        </>)}
      </div>
    </div>
  );
}
