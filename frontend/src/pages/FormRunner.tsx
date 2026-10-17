import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useAIAssistant } from "../contexts/AIAssistantContext";
import { buildDashboardContext } from "../components/forms/dashboardContext";
import { ArrowLeft, Loader2, Pencil, AlertCircle, FileText, BookOpen } from "lucide-react";
import api, { fehlerText } from "../api/client";
import { getAiProvider } from "../services/aiProvider";
import { ladeExportHerunter, exportDateienAus, nurExporte } from "../components/forms/ExportDateien";
import { validateRequired, fieldsForTab, aktionsAuswahl, feldVorgabe, zeitraumVorgabe } from "../components/forms/FormFields";
import ReportOptionsModal, { SECTION_SUMMARY } from "../components/forms/ReportOptionsModal";
import RunnerErgebnis from "../components/forms/RunnerErgebnis";
import RunnerEingabe, { EingabeReiter } from "../components/forms/RunnerEingabe";
import MandantWaehler from "../components/MandantWaehler";
import CockpitDokuModal from "../components/forms/CockpitDokuModal";
import VorlageGesperrt from "../components/VorlageGesperrt";

const S = {
  bgMain: "var(--bg-main)", bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)",
  border: "var(--border)", textMain: "var(--text-main)", textBright: "var(--text-bright)",
  textDim: "var(--text-dim)", accent: "var(--accent)",
};

export default function FormRunner({ formId = null, eingebettet = null }: { formId?: any; eingebettet?: null | "seite" | "inhalt" } = {}) {
  const routeParams = useParams();
  const id = formId ?? routeParams.id;
  const zurueck = eingebettet ? "/start/cockpits" : "/dashboard";
  const zurueckText = eingebettet ? "Cockpits" : "Dashboard";
  const navigate = useNavigate();
  const [form, setForm] = useState(null);
  const [params, setParams] = useState({});
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState(null);
  const [dokuOffen, setDokuOffen] = useState(false);
  const [kompat, setKompat] = useState(null);   // JTL-Version des Mandanten vs. Cockpit
  const [aiSummaries, setAiSummaries] = useState({}); // {action_id: KI-Analysetext} für den PDF-Report
  const [aiLoading, setAiLoading] = useState({});     // {action_id: bool} – KI-Analyse streamt noch
  const [error, setError] = useState(null);
  const [missing, setMissing] = useState([]);
  const [activeTab, setActiveTab] = useState(null);
  const [inputTab, setInputTab] = useState("main");
  const { setFormAiAllowed, setPageContext } = useAIAssistant();

  // Schwebenden KI-Assistenten in diesem Formular nur zeigen, wenn ausdrücklich
  // erlaubt (schema.show_ai_assistant); beim Verlassen zurücksetzen.
  useEffect(() => {
    setFormAiAllowed(!!form?.schema?.show_ai_assistant);
    return () => setFormAiAllowed(false);
  }, [form, setFormAiAllowed]);

  // Bei aktivem Assistenten die aktuell angezeigten Ergebnisse (aktiver Reiter) +
  // gesetzte Filter als Kontext einspeisen, damit die KI Fragen dazu beantworten kann.
  useEffect(() => {
    const sch = form?.schema;
    if (!sch?.show_ai_assistant) return;
    setPageContext(buildDashboardContext(sch.widgets, sch.actions, sch.result_tabs,
      form?.name, results, params, activeTab));
    return () => setPageContext(null);
  }, [form, results, params, activeTab, setPageContext]);

  useEffect(() => {
    api.get(`/api/forms/${id}`).then(({ data }) => {
      setForm(data);
      // Standardwerte setzen. Mehrfachauswahl-Felder starten als leere Liste,
      // damit das Backend :name_empty=1 (= kein Filter) bindet.
      const isMulti = f => f.type === "multiselect" || (f.type === "db_dropdown" && f.config?.multiple);
      const defaults = {};
      for (const f of (data.schema?.fields || [])) {
        defaults[f.name] = feldVorgabe(f, isMulti(f));
      }
      if (eingebettet === "inhalt") {
        for (const f of (data.schema?.fields || [])) Object.assign(defaults, zeitraumVorgabe(f));
      }
      setParams(defaults);
    }).catch(() => setError("Formular nicht gefunden"));
  }, [id]);

  const setParam = useCallback((name, value) => {
    setParams(prev => ({ ...prev, [name]: value }));
  }, []);

  const downloadExport = async (fileId, fileName) => {
    try {
      await ladeExportHerunter(fileId, fileName);
    } catch (e) {
      setError("Download fehlgeschlagen: " + (fehlerText(e)));
    }
  };

  // Wie im Portal: ein Formular ohne Eingabefelder hat keinen Auslöser und bliebe
  // sonst leer, bis jemand den Knopf findet.
  const autostart = useRef(null);
  useEffect(() => {
    if (!form || autostart.current === form.id) return;
    const sch = form.schema || {};
    // In der Übersicht (eingebettet="inhalt") gibt es keine Eingabe: dort immer mit den Vorgaben starten.
    if (((sch.fields || []).length > 0 && eingebettet !== "inhalt") || !(sch.actions || []).length) return;
    autostart.current = form.id;
    runForm(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form]);

  // Passt das Cockpit zur JTL-Version des Mandanten? Geprüft wird serverseitig
  // gegen die vorhandenen Objekte – nach einem JTL-Update fällt der Hinweis von
  // selbst weg, hier ist nichts zu pflegen.
  const ladeKompat = useCallback(() => {
    if (!id) return;
    api.get(`/api/forms/${id}/kompatibilitaet`)
      .then(({ data }) => setKompat(data?.fehlend?.length || data?.felder?.length ? data : null))
      .catch(() => setKompat(null));   // nicht prüfbar: dann eben kein Hinweis
  }, [id]);

  useEffect(() => { ladeKompat(); }, [ladeKompat]);

  const [reporting, setReporting] = useState(false);
  const [reportModal, setReportModal] = useState(false); // Abschnittsauswahl vor dem PDF
  const downloadReport = async (sections) => {
    setReporting(true);
    try {
      // Bereits im Formular erzeugte KI-Analyse mitgeben → Report überspringt den
      // langsamen KI-Aufruf (verhindert den Timeout/„Network Error"). Ist die
      // KI-Analyse abgewählt, gar nicht erst mitschicken.
      const wantSummary = !sections || sections.includes(SECTION_SUMMARY);
      const aiSummary = wantSummary
        ? (Object.values(aiSummaries).find(t => t && t.trim()) || null) : null;
      // Report-Erzeugung kann (KI/JTL) einige Sekunden dauern → großzügiges Timeout.
      const resp = await api.post(`/api/forms/${id}/report`,
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
      setError("PDF-Report fehlgeschlagen: " + msg);
    } finally {
      setReporting(false);
      setReportModal(false);
    }
  };

  // Report-Button sperren, solange eine KI-Analyse noch streamt – so kann man nicht
  // „zu früh" klicken und einen Report ohne (bzw. mit halber) KI-Analyse auslösen.
  const aiBusy = Object.values(aiLoading).some(Boolean);

  const runForm = async (actionIds = null, paramsOverride = null) => {
    const effParams = paramsOverride ? { ...params, ...paramsOverride } : params;
    if (paramsOverride) setParams(effParams);
    // Nur sichtbare Felder prüfen – ein auf einem anderen Reiter ausgeblendetes
    // Pflichtfeld darf den Lauf nicht blockieren.
    const tabNow = activeTab || (form?.schema?.result_tabs || [])[0]?.id || null;
    const miss = validateRequired(fieldsForTab(form?.schema?.fields || [], tabNow), effParams);
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
        ...aktionsAuswahl(actionIds),
      });
      const neu = data.results || {};
      // Ein Export-Knopf soll die angezeigten Auswertungen nicht wegwischen.
      setResults(prev => nurExporte(neu) ? { ...(prev || {}), ...neu } : neu);
      for (const f of exportDateienAus(neu)) await downloadExport(f.id, f.file_name);
    } catch (e) {
      setError(fehlerText(e));
    } finally {
      setRunning(false);
    }
  };

  if (!form && !error) return (
    <div style={{ height: eingebettet ? 160 : "100vh", display: "flex", alignItems: "center", justifyContent: "center",
      backgroundColor: S.bgMain, color: S.textDim, fontSize: 12 }}>
      Lädt…
    </div>
  );

  // Vorlage ohne laufende Berechtigung: statt der Auswertung der Kauf-Hinweis. Die
  // Auswertung waere ohnehin gesperrt (das Backend laesst den Lauf nicht durch) —
  // hier steht, warum, und wie es weitergeht.
  if (form?.gesperrt) return (
    <div style={{ minHeight: eingebettet ? undefined : "100vh", backgroundColor: S.bgMain, color: S.textMain }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 16px",
        borderBottom: `1px solid ${S.border}`, backgroundColor: S.bgCard }}>
        <button onClick={() => navigate(zurueck)}
          style={{ display: "flex", alignItems: "center", gap: 5, background: "none", border: "none",
            color: S.textDim, cursor: "pointer", fontSize: 12 }}>
          <ArrowLeft size={14} /> {zurueckText}
        </button>
        <div style={{ width: 1, height: 20, backgroundColor: S.border }} />
        <span style={{ fontSize: 14, fontWeight: 600, color: S.textBright }}>{form?.name}</span>
      </div>
      <VorlageGesperrt sperre={form.gesperrt}
        onErneutGeprueft={() => api.get(`/api/forms/${id}`).then(({ data }) => setForm(data))} />
    </div>
  );

  const schema = form?.schema || {};
  const allFields = schema.fields || [];
  // Ausschlussartikel-Feld separat behandeln: es bekommt einen eigenen Eingabe-Reiter.
  const exclusionField = allFields.find(f => f.type === "article_exclusion") || null;
  const fields = exclusionField ? allFields.filter(f => f !== exclusionField) : allFields;
  const actions = schema.actions || [];
  const widgets = schema.widgets || [];
  // Optionale Tab-Ansicht der Ergebnisse (aus schema.result_tabs). Jeder Tab
  // bündelt eine Auswahl an Action-IDs; ohne Konfiguration bleibt alles gestapelt.
  const resultTabs = schema.result_tabs || [];
  const currentTab = activeTab || resultTabs[0]?.id || null;
  const tabActionIds = resultTabs.length
    ? new Set((resultTabs.find(t => t.id === currentTab)?.action_ids) || [])
    : null;
  // Felder, die nur zu einem Reiter gehören (config.visible_tabs), außerhalb ausblenden.
  const visibleFields = fieldsForTab(fields, currentTab);
  const hasButtonField = visibleFields.some(f => f.type === "button");

  return (
    <div style={{ minHeight: eingebettet ? undefined : "100vh", backgroundColor: eingebettet === "inhalt" ? "transparent" : S.bgMain, color: S.textMain }}>

      {/* Toolbar */}
      {eingebettet !== "inhalt" && (
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, padding: "10px 16px",
        borderBottom: `1px solid ${S.border}`, backgroundColor: S.bgCard }}>
        <button onClick={() => navigate(zurueck)}
          style={{ display: "flex", alignItems: "center", gap: 5, background: "none", border: "none",
            color: S.textDim, cursor: "pointer", fontSize: 12 }}>
          <ArrowLeft size={14} /> {zurueckText}
        </button>
        <div style={{ width: 1, height: 20, backgroundColor: S.border }} />
        <span style={{ flex: 1, fontSize: 14, fontWeight: 600, color: S.textBright }}>{form?.name}</span>
        <MandantWaehler projectId={form?.project_id ?? null}
          onWechsel={() => { setResults({}); ladeKompat(); runForm(null); }} kompakt />
        {widgets.length > 0 && (
          <button onClick={() => setDokuOffen(true)} title="Was zeigt dieses Cockpit? Datenquellen und Aufbau"
            style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 12px", borderRadius: 6,
              border: `1px solid ${S.border}`, backgroundColor: "transparent", color: S.textDim,
              cursor: "pointer", fontSize: 12, fontWeight: 600 }}
            onMouseEnter={(e) => { e.currentTarget.style.color = S.textBright; e.currentTarget.style.borderColor = S.accent + "55"; }}
            onMouseLeave={(e) => { e.currentTarget.style.color = S.textDim; e.currentTarget.style.borderColor = S.border; }}>
            <BookOpen size={12} /> Erklärung
          </button>
        )}
        {widgets.length > 0 && (
          <button onClick={() => setReportModal(true)} disabled={reporting || aiBusy}
            title={aiBusy ? "KI-Analyse wird noch erstellt – bitte kurz warten" : "PDF-Report erzeugen"}
            style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 12px", borderRadius: 6,
              border: `1px solid color-mix(in srgb, ${S.accent} 33.3%, transparent)`, backgroundColor: `color-mix(in srgb, ${S.accent} 8.2%, transparent)`, color: S.accent,
              opacity: (reporting || aiBusy) ? 0.5 : 1,
              cursor: reporting ? "wait" : aiBusy ? "not-allowed" : "pointer", fontSize: 12, fontWeight: 600 }}>
            {(reporting || aiBusy) ? <Loader2 size={12} style={{ animation: "spin 1s linear infinite" }} /> : <FileText size={12} />}
            {reporting ? "Erstelle PDF…" : aiBusy ? "KI-Analyse läuft…" : "PDF-Report"}
          </button>
        )}
        {!eingebettet && (
        <button onClick={() => navigate(`/forms/${id}`)}
          style={{ display: "flex", alignItems: "center", gap: 5, background: "none", border: "none",
            color: S.textDim, cursor: "pointer", fontSize: 12 }}>
          <Pencil size={12} /> Bearbeiten
        </button>
        )}
      </div>
      )}

      {/* Dashboards (mit Widgets) breiter rendern als reine Eingabeformulare. */}
      <div style={{ maxWidth: widgets.length ? 1760 : 900, margin: "0 auto",
        padding: eingebettet === "inhalt" ? 0 : eingebettet ? "24px 0" : "32px 20px" }}>

        {kompat && (
          <div style={{ display: "flex", gap: 10, padding: "12px 14px", borderRadius: 6,
            backgroundColor: "color-mix(in srgb, var(--accent) 8%, transparent)", border: "1px solid color-mix(in srgb, var(--accent) 35%, transparent)",
            color: S.textMain, fontSize: 12, marginBottom: 20, lineHeight: 1.6 }}>
            <AlertCircle size={15} style={{ color: S.accent, flexShrink: 0, marginTop: 1 }} />
            <div>
              <strong style={{ color: S.textBright }}>
                Dieses Cockpit passt nicht zur JTL-Version dieses Mandanten
                {kompat.version ? ` (JTL ${kompat.version})` : ""}.
              </strong>
              <div style={{ marginTop: 4 }}>
                {kompat.fehlend?.length > 0 && (<>
                  Nicht verfügbar: {kompat.fehlend.map((x) => <code key={x} style={{ fontFamily: "monospace" }}>{x}</code>)
                    .reduce((a, b) => [a, ", ", b])}.{" "}
                </>)}
                {/* Fehlende Felder kommen aus dem Trockenlauf: die Tabelle gibt es,
                    die Spalte nicht (JTL 2.0 hat z. B. fWertNettoGesamtFixiert entfernt). */}
                {kompat.felder?.length > 0 && (<>
                  Fehlende Felder: {kompat.felder.map((x) => <code key={x} style={{ fontFamily: "monospace" }}>{x}</code>)
                    .reduce((a, b) => [a, ", ", b])}.{" "}
                </>)}
                Betroffen sind {kompat.aktionen_betroffen} von{" "}
                {kompat.aktionen_gesamt} Auswertungen
                {kompat.reiter?.length ? `, darunter die Reiter ${kompat.reiter.map(r => r.label).join(", ")}` : ""}.
              </div>
              <div style={{ marginTop: 4, color: S.textDim }}>
                Die betroffenen Kacheln sagen es noch einmal kurz. Nach einem Update der
                JTL-Wawi verschwindet der Hinweis von selbst – geprüft wird bei jedem
                Aufruf, was die Datenbank tatsächlich hergibt.
              </div>
            </div>
          </div>
        )}

        {error && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 14px", borderRadius: 6,
            backgroundColor: "color-mix(in srgb, var(--err-soft) 10%, transparent)", border: "1px solid color-mix(in srgb, var(--err-soft) 30%, transparent)",
            color: "var(--err-soft)", fontSize: 12, marginBottom: 20 }}>
            <AlertCircle size={14} /> {error}
          </div>
        )}

        <EingabeReiter exclusionField={exclusionField} inputTab={inputTab} setInputTab={setInputTab}
          projectId={form.project_id} />

        {(!exclusionField || inputTab === "main") && (<>
        {eingebettet !== "inhalt" && (
          // Werkstatt: kompakt, ohne Felder ein Hinweis für Bauende; Händler-Ansicht
          // ohne Felder wie das Portal mit „Aktualisieren“.
          <RunnerEingabe fields={visibleFields} params={params} setParam={setParam} onRun={runForm}
            running={running} missing={missing} actions={actions} results={results}
            hasButtonField={hasButtonField} kompakt ohneFelderHinweis={!eingebettet} />
        )}

        <RunnerErgebnis form={form} actions={actions} widgets={widgets} results={results}
          resultTabs={resultTabs} currentTab={currentTab} onTab={setActiveTab} tabActionIds={tabActionIds}
          params={params} allowDownload={true} onDownload={downloadExport}
          onAiText={(aid, text, loading) => {
            setAiSummaries(prev => prev[aid] === text ? prev : { ...prev, [aid]: text });
            setAiLoading(prev => prev[aid] === loading ? prev : { ...prev, [aid]: loading });
          }} />
        </>)}
      </div>

      {dokuOffen && <CockpitDokuModal formId={id} onClose={() => setDokuOffen(false)} />}

      {/* Abschnittsauswahl für den PDF-Report */}
      {reportModal && (
        <ReportOptionsModal formId={id} schema={schema} busy={reporting}
          onClose={() => { if (!reporting) setReportModal(false); }}
          onConfirm={downloadReport} />
      )}
    </div>
  );
}
