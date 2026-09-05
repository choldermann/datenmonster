import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Play, Loader2, Download, AlertCircle, LogOut, Check, FileText } from "lucide-react";
import api, { fehlerText } from "../api/client";
import { getAiProvider } from "../services/aiProvider";
import { useAuth } from "../context/AuthContext";
import { useAIAssistant } from "../contexts/AIAssistantContext";
import { buildDashboardContext } from "../components/forms/dashboardContext";
import WidgetRenderer, { STANDALONE_WIDGET_TYPES } from "../components/forms/WidgetRenderer";
import EmailTableButton from "../components/forms/EmailTableButton";
import FormFields, { validateRequired, fieldsForTab, PipelineResult } from "../components/forms/FormFields";
import ReportOptionsModal, { SECTION_SUMMARY } from "../components/forms/ReportOptionsModal";
import IntrastatExclusionPanel from "../components/forms/IntrastatExclusionPanel";
import { ThemeUmschalter, KiCredits } from "../components/portal/PortalKopfzeile";
import MandantWaehler from "../components/MandantWaehler";
import { formIcon } from "../utils/formIcon";

const S = {
  bgMain: "var(--bg-main)", bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)",
  border: "var(--border)", textMain: "var(--text-main)", textBright: "var(--text-bright)",
  textDim: "var(--text-dim)", accent: "var(--accent)",
};

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
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <EmailTableButton columns={columns} rows={rows} title={`${formName} – ${actionLabel}`} disabled={!rows.length} />
            <button onClick={downloadCsv}
              style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11,
                color: S.accent, background: "none", border: `1px solid ${S.border}`,
                borderRadius: 5, padding: "4px 10px", cursor: "pointer" }}>
              <Download size={11} /> CSV
            </button>
          </div>
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

// ── Export result (Datei-Downloads) ─────────────────────────────────────────────

function ExportResult({ result, onDownload, allowDownload }) {
  const files = result.files || [];
  if (result.error) return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "14px 18px",
      color: "#e07070", fontSize: 13 }}>
      <AlertCircle size={14} /> {result.error}
    </div>
  );
  return (
    <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#6ee7b7",
        fontSize: 13, fontWeight: 600 }}>
        <Check size={14} /> Export erzeugt · {result.total ?? 0} Zeilen
      </div>
      {files.length === 0 ? (
        <span style={{ color: S.textDim, fontSize: 12 }}>Keine Dateien erzeugt.</span>
      ) : allowDownload ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {files.map(f => (
            <button key={f.id} onClick={() => onDownload(f.id, f.file_name)}
              style={{ display: "flex", alignItems: "center", gap: 8, padding: "9px 14px",
                background: S.bgMain, border: `1px solid ${S.border}`, borderRadius: 8,
                color: S.textBright, cursor: "pointer", fontSize: 13, textAlign: "left" }}>
              <Download size={13} /> {f.file_name}
              {f.target_name && <span style={{ color: S.textDim, fontSize: 11 }}>· {f.target_name}</span>}
            </button>
          ))}
        </div>
      ) : (
        <span style={{ color: S.textDim, fontSize: 12 }}>Download ist für dieses Formular deaktiviert.</span>
      )}
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
  const [missing, setMissing] = useState([]);
  const [activeTab, setActiveTab] = useState(null);
  const [inputTab, setInputTab]   = useState("main");
  const [reporting, setReporting] = useState(false);
  const [reportModal, setReportModal] = useState(false); // Abschnittsauswahl vor dem PDF
  // Vom ai_summary-Widget erzeugte Analyse einsammeln: sie wandert in den Report,
  // damit dieser den langsamen KI-Aufruf überspringt (sonst droht ein Timeout).
  const [aiSummaries, setAiSummaries] = useState({});
  const [aiLoading, setAiLoading]     = useState({});
  const { setFormAiAllowed, setPageContext } = useAIAssistant();

  // KI-Assistent im Portal nur zeigen, wenn das Formular es erlaubt.
  useEffect(() => {
    setFormAiAllowed(!!form?.show_ai_assistant);
    return () => setFormAiAllowed(false);
  }, [form, setFormAiAllowed]);

  // Bei aktivem Assistenten die angezeigten Ergebnisse (aktiver Reiter) + Filter einspeisen.
  useEffect(() => {
    if (!form?.show_ai_assistant) return;
    setPageContext(buildDashboardContext(form.widgets, form.actions, form.result_tabs,
      form.name, results, params, activeTab));
    return () => setPageContext(null);
  }, [form, results, params, activeTab, setPageContext]);

  useEffect(() => {
    api.get(`/api/portal/forms/${slug}`)
      .then(({ data }) => {
        setForm(data);
        const isMulti = f => f.type === "multiselect" || (f.type === "db_dropdown" && f.config?.multiple);
        const defaults = {};
        for (const f of (data.fields || [])) {
          if (f.name) defaults[f.name] = f.default ?? (isMulti(f) ? [] : "");
        }
        setParams(defaults);
      })
      .catch(() => setLoadErr("Formular nicht gefunden oder kein Zugriff."));
  }, [slug]);

  // Formulare ganz ohne Eingabefelder (z.B. Health-Check) haben keinen Auslöser:
  // kein Datumsfilter, keine Auswahl. Sie würden dauerhaft leer dastehen – deshalb
  // einmal automatisch laufen, sobald das Formular geladen ist.
  const autostart = useRef(null);
  useEffect(() => {
    if (!form || autostart.current === form.slug) return;
    if ((form.fields || []).length > 0 || !(form.actions || []).length) return;
    autostart.current = form.slug;
    runAction(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form]);

  const setParam = useCallback((name, value) => {
    setParams(prev => ({ ...prev, [name]: value }));
  }, []);

  const runAction = async (actionIds, paramsOverride) => {
    const effParams = paramsOverride ? { ...params, ...paramsOverride } : params;
    if (paramsOverride) setParams(effParams);
    // Nur sichtbare Felder prüfen – ein auf einem anderen Reiter ausgeblendetes
    // Pflichtfeld darf den Lauf nicht blockieren.
    const tabNow = activeTab || (form?.result_tabs || [])[0]?.id || null;
    const miss = validateRequired(fieldsForTab(form?.fields || [], tabNow), effParams);
    if (miss.length) {
      setMissing(miss);
      setRunErr("Bitte fülle die markierten Pflichtfelder aus.");
      return;
    }
    setMissing([]);
    setRunning(true); setRunErr(null);
    try {
      const body = { params: effParams, action_ids: (actionIds && actionIds.length) ? actionIds : null };
      const { data } = await api.post(`/api/portal/forms/${slug}/run`, body);
      setResults(data.results || {});
    } catch (e) {
      setRunErr(fehlerText(e));
    } finally { setRunning(false); }
  };

  const aiBusy = Object.values(aiLoading).some(Boolean);

  const downloadReport = async (sections) => {
    setReporting(true);
    try {
      const wantSummary = !sections || sections.includes(SECTION_SUMMARY);
      const aiSummary = wantSummary
        ? (Object.values(aiSummaries).find(t => t && t.trim()) || null) : null;
      const resp = await api.post(`/api/portal/forms/${slug}/report`,
        { params, ai_summary: aiSummary, sections: sections || null, ai_provider: getAiProvider() },
        { responseType: "blob", timeout: 180000 });
      const url = URL.createObjectURL(resp.data);
      const a = document.createElement("a");
      a.href = url;
      // Umlaute transliterieren (ä→ae …), sonst würden sie zu "_".
      const nameSafe = (form?.name || "report")
        .replace(/ä/g, "ae").replace(/ö/g, "oe").replace(/ü/g, "ue")
        .replace(/Ä/g, "Ae").replace(/Ö/g, "Oe").replace(/Ü/g, "Ue").replace(/ß/g, "ss")
        .replace(/[^a-z0-9]+/gi, "_").replace(/^_+|_+$/g, "");
      a.download = `${nameSafe}_${new Date().toISOString().slice(0, 10)}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      // Fehlermeldung steckt bei Blob-Responses im Blob-Text
      let msg = e.message;
      try { msg = fehlerText(JSON.parse(await e.response?.data?.text()), msg); } catch { /* ignore */ }
      setRunErr("PDF-Report fehlgeschlagen: " + msg);
    } finally {
      setReporting(false);
      setReportModal(false);
    }
  };

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
      setRunErr("Download fehlgeschlagen: " + (fehlerText(e)));
    }
  };

  const handleLogout = () => { logout(); navigate("/login"); };

  // Loading
  if (!form && !loadErr) return (
    <div style={{ height: "100vh", display: "flex", alignItems: "center",
      justifyContent: "center", backgroundColor: S.bgMain, color: S.textDim, fontSize: 14 }}>
      Lädt…
    </div>
  );

  const allFields = form?.fields  || [];
  // Ausschlussartikel-Feld separat behandeln: eigener Eingabe-Reiter wie im Editor-Runner.
  const exclusionField = allFields.find(f => f.type === "article_exclusion") || null;
  const fields  = exclusionField ? allFields.filter(f => f !== exclusionField) : allFields;
  const actions = form?.actions || [];
  const widgets = form?.widgets || [];
  const allowDownload  = form?.allow_download || false;
  // Optionale Ergebnis-Register (aus schema.result_tabs). Jeder Tab bündelt Action-IDs.
  const resultTabs = form?.result_tabs || [];
  const currentTab = activeTab || resultTabs[0]?.id || null;
  const tabActionIds = resultTabs.length
    ? new Set((resultTabs.find(t => t.id === currentTab)?.action_ids) || [])
    : null;
  // Felder, die nur zu einem Reiter gehören (config.visible_tabs), außerhalb ausblenden.
  const visibleFields  = fieldsForTab(fields, currentTab);
  const hasButtonField = visibleFields.some(f => f.type === "button");
  // Actions ohne Widget → als Rohtabelle zeigen (ggf. nach aktivem Register gefiltert)
  const widgetActionIds = new Set(widgets.map(w => w.action_id).filter(Boolean));
  const rawResultActions = actions.filter(a => !widgetActionIds.has(a.id)
    && (!tabActionIds || tabActionIds.has(a.id)));

  return (
    <div style={{ minHeight: "100vh", backgroundColor: S.bgMain, color: S.textMain }}>

      {/* ── Header ── */}
      <header style={{ position: "sticky", top: 0, zIndex: 10,
        borderBottom: `1px solid ${S.border}`, backgroundColor: S.bgCard }}>
        <div style={{ maxWidth: widgets.length ? 1760 : 1100, margin: "0 auto", padding: "12px 24px",
          display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <button onClick={() => navigate("/portal")}
              style={{ display: "flex", alignItems: "center", gap: 5, background: "none",
                border: "none", color: S.textDim, cursor: "pointer", fontSize: 13 }}>
              <ArrowLeft size={14} /> Übersicht
            </button>
            <span style={{ color: S.border }}>|</span>
            <span style={{ fontSize: 15, fontWeight: 600, color: S.textBright }}>
              {form?.icon && <span style={{ marginRight: 6 }}>{formIcon(form.icon)}</span>}
              {form?.name || slug}
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
            {widgets.length > 0 && allowDownload && (
              <button onClick={() => setReportModal(true)} disabled={reporting || aiBusy}
                title={aiBusy ? "KI-Analyse wird noch erstellt – bitte kurz warten" : "PDF-Report erzeugen"}
                style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 12px", borderRadius: 6,
                  border: `1px solid ${S.accent}55`, backgroundColor: `${S.accent}15`, color: S.accent,
                  opacity: (reporting || aiBusy) ? 0.5 : 1,
                  cursor: reporting ? "wait" : aiBusy ? "not-allowed" : "pointer",
                  fontSize: 12, fontWeight: 600 }}>
                {(reporting || aiBusy)
                  ? <Loader2 size={12} style={{ animation: "spin 1s linear infinite" }} />
                  : <FileText size={12} />}
                {reporting ? "Erstelle PDF…" : aiBusy ? "KI-Analyse läuft…" : "PDF-Report"}
              </button>
            )}
            {/* Der Mandant steht neben dem Formularnamen im Kopf: eine Umsatzzahl
                ohne sichtbaren Betrieb dahinter ist im Zweifel wertlos. */}
            <MandantWaehler projectId={form?.project_id ?? null}
              onWechsel={() => { setResults({}); runAction(null); }} />
            <KiCredits />
            <ThemeUmschalter />
            <button onClick={handleLogout}
              style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12,
                color: S.textDim, background: "none", border: "none", cursor: "pointer" }}>
              <LogOut size={13} /> Abmelden
            </button>
          </div>
        </div>
      </header>

      {/* ── Main ── (Dashboards mit Widgets breiter) */}
      <main style={{ maxWidth: widgets.length ? 1760 : 1100, margin: "0 auto", padding: "36px 24px" }}>

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

        {/* Eingabe-Reiter (nur wenn ein Ausschlussartikel-Feld im Schema ist) */}
        {exclusionField && (
          <div style={{ display: "flex", gap: 4, marginBottom: 24, borderBottom: `1px solid ${S.border}` }}>
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

        {/* Ausschlussartikel-Verwaltung */}
        {exclusionField && inputTab === "exclusions" && (() => {
          const cId = Number(exclusionField.config?.connection_id);
          return (
            <IntrastatExclusionPanel projectId={form.project_id}
              connectionId={Number.isFinite(cId) && cId > 0 ? cId : null} />
          );
        })()}

        {(!exclusionField || inputTab === "main") && (<>
        {/* ── Form card ── */}
        {/* Dashboard ohne Eingabefelder: es gäbe sonst nichts zum Starten – der Lauf
            beginnt automatisch (siehe unten), der Knopf bleibt zum Aktualisieren. */}
        {visibleFields.length === 0 && actions.length > 0 && (
          <div style={{ textAlign: "center", marginBottom: 28 }}>
            <button onClick={() => runAction(null)} disabled={running}
              style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "10px 24px",
                borderRadius: 8, fontSize: 14, fontWeight: 600,
                backgroundColor: "rgba(110,231,183,0.12)",
                border: "1px solid rgba(110,231,183,0.4)",
                color: "#6ee7b7", cursor: running ? "wait" : "pointer" }}>
              {running ? <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} /> : <Play size={14} />}
              {running ? "Wird ausgeführt …" : results ? "Aktualisieren" : "Ausführen"}
            </button>
          </div>
        )}

        {visibleFields.length > 0 && (
          <div style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`,
            borderRadius: 14, padding: "28px 32px", marginBottom: 32 }}>

            <FormFields
              fields={visibleFields}
              params={params}
              setParam={setParam}
              onRunAction={runAction}
              running={running}
              errors={missing}
            />

            {/* Fallback-Button wenn kein Button-Feld im Schema. Wie im Editor-FormRunner
                genau EIN Sammel-Lauf über alle Actions – bei Dashboards mit vielen
                Actions wäre ein Button je Action eine Buttonwand statt eines Formulars. */}
            {!hasButtonField && actions.length > 0 && (
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 12 }}>
                <button onClick={() => runAction(null)} disabled={running}
                  style={{ display: "inline-flex", alignItems: "center", gap: 8,
                    padding: "10px 24px", borderRadius: 8, fontSize: 14, fontWeight: 600,
                    backgroundColor: "rgba(110,231,183,0.12)",
                    border: "1px solid rgba(110,231,183,0.4)",
                    color: "#6ee7b7", cursor: running ? "wait" : "pointer" }}>
                  {running ? <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} /> : <Play size={14} />}
                  {actions.length === 1 ? (actions[0].label || "Ausführen") : "Ausführen"}
                </button>
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

        {/* Ergebnis-Register (optional, aus schema.result_tabs) */}
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

        {/* ── Widget-Ergebnisse ──
            Standalone-Widgets (z.B. Eingangsrechnungs-Freigabe) rendern ohne Action-Result;
            reguläre Widgets erst nach dem Ausführen. Parität zum Editor-FormRunner. */}
        {widgets.length > 0 && (results || widgets.some(w => STANDALONE_WIDGET_TYPES.has(w.type))) && (
          <WidgetRenderer
            widgets={tabActionIds ? widgets.filter(w => !w.action_id || tabActionIds.has(w.action_id)) : widgets}
            results={results || {}}
            allowDownload={allowDownload}
            baseParams={params}
            projectId={form.project_id}
            onAiText={(aid, text, loading) => {
              setAiSummaries(prev => prev[aid] === text ? prev : { ...prev, [aid]: text });
              setAiLoading(prev => prev[aid] === loading ? prev : { ...prev, [aid]: loading });
            }}
          />
        )}

        {/* ── Rohtabellen für Aktionen ohne Widget ── */}
        {results && rawResultActions.map(action => {
          const result = results[action.id];
          if (!result) return null;
          return (
            <div key={action.id} style={{ backgroundColor: S.bgCard,
              border: `1px solid ${S.border}`, borderRadius: 14,
              overflow: "hidden", marginBottom: 20, marginTop: widgets.length > 0 ? 20 : 0 }}>
              <div style={{ padding: "14px 20px", borderBottom: `1px solid ${S.border}`,
                display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span style={{ fontSize: 14, fontWeight: 700, color: S.textBright }}>
                  {action.label || "Ergebnis"}
                </span>
              </div>
              {result.kind === "pipeline" ? (
                <PipelineResult result={result} />
              ) : result.kind === "export" ? (
                <ExportResult result={result} onDownload={downloadExport} allowDownload={allowDownload} />
              ) : (
                <ResultTable
                  result={result}
                  formName={form?.name || "export"}
                  actionLabel={action.label || action.id}
                  allowDownload={allowDownload}
                />
              )}
            </div>
          );
        })}
        </>)}
      </main>

      {reportModal && (
        // Das Portal liefert das Schema flach aus (_portal_form_out) – der Dialog
        // braucht nur Widgets und Reiter.
        <ReportOptionsModal formId={form?.id} busy={reporting}
          schema={{ widgets, result_tabs: resultTabs }}
          onClose={() => { if (!reporting) setReportModal(false); }}
          onConfirm={downloadReport} />
      )}

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
