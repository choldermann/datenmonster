/**
 * Ergebnisbereich eines Formularlaufs – gemeinsam für FormRunner (Editor,
 * Büro) und PortalRunner.
 *
 * Bis hierher waren beide Runner Kopien, die bei jeder Änderung auseinanderliefen
 * (Paritätsregel). Erster Schritt der Zusammenführung (Büro, Phase 5):
 * alles nach den Eingabefeldern – Export-Ergebnisse, Reiterleiste, Widgets und
 * Rohtabellen für Aktionen ohne Widget – lebt jetzt nur noch hier.
 */
import { useRef, useState } from "react";
import { fehlerText } from "../../api/client";
import { tabelleAlsExcel } from "./excelExport";
import { csvZelle } from "../../utils/csvSicher";
import { AlertCircle, Download } from "lucide-react";
import WidgetRenderer, { STANDALONE_WIDGET_TYPES } from "./WidgetRenderer";
import EmailTableButton from "./EmailTableButton";
import { ExportErgebnisse } from "./ExportDateien";
import { widgetsForTab, PipelineResult } from "./FormFields";

const S = {
  bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)", border: "var(--border)",
  textMain: "var(--text-main)", textBright: "var(--text-bright)", textDim: "var(--text-dim)",
  accent: "var(--accent)",
};

/** Rohtabelle einer Aktion ohne Widget – mit CSV und Mail, sofern erlaubt. */
export function ErgebnisTabelle({ result, formName, actionLabel, allowDownload }) {
  const { columns = [], rows = [], total, error, download_disabled } = result;
  const canDownload = allowDownload && !download_disabled;
  const [xlsxLaeuft, setXlsxLaeuft] = useState(false);
  const downloadXlsx = async () => {
    setXlsxLaeuft(true);
    try {
      await tabelleAlsExcel({ titel: actionLabel, columns, rows, datei: `${formName}-${actionLabel}` });
    } catch (e) {
      alert(`Excel-Export fehlgeschlagen: ${fehlerText(e)}`);
    } finally { setXlsxLaeuft(false); }
  };

  const downloadCsv = () => {
    const header = columns.join(";");
    const body = rows.map(r =>
      columns.map(c => `"${csvZelle(r[c]).replace(/"/g, '""')}"`).join(";")
    ).join("\n");
    const blob = new Blob(["﻿" + header + "\n" + body], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${formName}-${actionLabel}.csv`;
    a.click();
  };

  if (error) return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "14px 18px",
      color: "var(--err-soft)", fontSize: 13 }}>
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
            <button onClick={downloadXlsx} disabled={xlsxLaeuft || !rows.length}
              style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11,
                color: S.accent, background: "none", border: `1px solid ${S.border}`,
                borderRadius: 5, padding: "4px 10px", cursor: xlsxLaeuft ? "wait" : "pointer" }}>
              <Download size={11} /> {xlsxLaeuft ? "Excel …" : "Excel"}
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

/**
 * Hauptreiter aus schema.reiter_gruppen ([{id, label, reiter: [tab-id, …]}]). Reiter, die in
 * keiner Gruppe stehen (z. B. eigene Reiter beim Kunden), bilden je einen eigenen Hauptreiter
 * an ihrer Stelle. Gruppen ohne vorhandenen Reiter entfallen. Ohne Angabe: jeder Reiter allein.
 */
export function reiterGruppieren(resultTabs, reiterGruppen) {
  const nachId = new Map(resultTabs.map(t => [t.id, t]));
  const vergeben = new Set();
  const gruppen = [];
  for (const g of reiterGruppen || []) {
    const tabs = (g.reiter || []).map(id => nachId.get(id)).filter(t => t && !vergeben.has(t.id));
    if (!tabs.length) continue;
    tabs.forEach(t => vergeben.add(t.id));
    gruppen.push({ id: g.id, label: g.label, tabs });
  }
  // Übrige Reiter nach der Gruppe ihres Vorgängers einsortieren, sonst ans Ende.
  let zuletzt = -1;
  for (const t of resultTabs) {
    if (vergeben.has(t.id)) { zuletzt = gruppen.findIndex(g => g.tabs.some(x => x.id === t.id)); continue; }
    gruppen.splice(zuletzt + 1, 0, { id: `einzel_${t.id}`, label: t.label, tabs: [t] });
    zuletzt += 1;
  }
  return gruppen;
}

/**
 * Alles nach den Eingabefeldern. `form` braucht id, name und project_id.
 * `onAiText(actionId, text, loading)` sammelt die KI-Analysen für den PDF-Report.
 */
export default function RunnerErgebnis({
  form, actions, widgets, results, resultTabs, currentTab, onTab, tabActionIds,
  params, allowDownload, onDownload, onAiText, reiterScroll = false, reiterGruppen = null,
}) {
  const gruppen = reiterGruppieren(resultTabs, reiterGruppen);
  const aktiveGruppe = gruppen.find(g => g.tabs.some(t => t.id === currentTab)) || gruppen[0];
  // Zuletzt gewählte Unterseite je Hauptreiter (Rückkehr landet dort, wo man war).
  const zuletzt = useRef({});
  if (aktiveGruppe && currentTab) zuletzt.current[aktiveGruppe.id] = currentTab;
  const gruppeWaehlen = (g) => {
    const z = zuletzt.current[g.id];
    onTab(g.tabs.some(t => t.id === z) ? z : g.tabs[0].id);
  };
  const mitStandalone = widgets.some(w => STANDALONE_WIDGET_TYPES.has(w.type));
  // Aktionen ohne Widget → als Rohtabelle zeigen (ggf. nach aktivem Reiter gefiltert).
  // Export-Aktionen stehen über den Reitern (ExportErgebnisse) – sie gehören meist zu keinem.
  const widgetActionIds = new Set(widgets.map(w => w.action_id).filter(Boolean));
  const rohAktionen = results ? actions.filter(a => !widgetActionIds.has(a.id)
    && a.type !== "export_mapping"
    && !(a.type === "run_pipeline" && (results?.[a.id]?.files || []).length)
    && (!tabActionIds || tabActionIds.has(a.id))) : [];

  return (
    <>
      {results && (
        <ExportErgebnisse actions={actions} results={results}
          allowDownload={allowDownload} onDownload={onDownload} />
      )}

      {/* Ergebnis-Reiter (optional, aus schema.result_tabs) – bei eigenständigen Widgets
          schon vor dem ersten Lauf, sonst käme man nie auf einen Reiter, dessen
          Filter den ersten Lauf erst auslöst */}
      {(results || mitStandalone) && resultTabs.length > 0 && (
        <div role="tablist" style={{ display: "flex", gap: 4, marginBottom: 16,
          borderBottom: `1px solid ${S.border}`, flexWrap: reiterScroll ? "nowrap" : "wrap",
          overflowX: reiterScroll ? "auto" : undefined, scrollbarWidth: "thin" }}>
          {gruppen.map(g => {
            const active = g.id === aktiveGruppe?.id;
            return (
              <button key={g.id} onClick={() => gruppeWaehlen(g)} role="tab" aria-selected={active}
                style={{ padding: "8px 16px", background: "none", border: "none",
                  borderBottom: `${reiterScroll ? 2.5 : 2}px solid ${active ? (reiterScroll ? "var(--accent)" : "var(--ok)") : "transparent"}`,
                  color: active ? S.textBright : S.textDim, cursor: "pointer",
                  fontSize: reiterScroll ? 13.5 : 12, fontWeight: 600, marginBottom: -1,
                  whiteSpace: "nowrap", flex: "none" }}>
                {g.label}
              </button>
            );
          })}
        </div>
      )}

      {/* Unterseiten des gewählten Hauptreiters */}
      {(results || mitStandalone) && aktiveGruppe && aktiveGruppe.tabs.length > 1 && (
        <div role="tablist" aria-label={aktiveGruppe.label}
          style={{ display: "flex", flexWrap: "wrap", gap: 6, margin: "-6px 0 16px" }}>
          {aktiveGruppe.tabs.map(tab => {
            const active = tab.id === currentTab;
            return (
              <button key={tab.id} onClick={() => onTab(tab.id)} role="tab" aria-selected={active}
                style={{ padding: "4px 12px", borderRadius: 999, cursor: "pointer", fontSize: 12.5,
                  fontWeight: active ? 650 : 500, whiteSpace: "nowrap",
                  border: `1px solid ${active ? "var(--accent)" : S.border}`,
                  background: active ? "color-mix(in srgb, var(--accent) 12%, transparent)" : "transparent",
                  color: active ? "var(--accent)" : S.textMain }}>
                {tab.label}
              </button>
            );
          })}
        </div>
      )}

      {/* Widgets: eigenständige (z. B. Eingangsrechnungs-Freigabe) sofort, ergebnis-basierte nach dem Lauf */}
      {widgets.length > 0 && (results || mitStandalone) && (
        <WidgetRenderer
          widgets={widgetsForTab(widgets, currentTab, tabActionIds)}
          results={results || {}} allowDownload={allowDownload} baseParams={params}
          projectId={form.project_id} formId={form.id}
          onAiText={onAiText} onTab={onTab} />
      )}

      {/* Rohtabellen für Aktionen ohne Widget */}
      {rohAktionen.map(action => {
        const result = results[action.id];
        if (!result) return null;
        return (
          <div key={action.id} style={{ backgroundColor: S.bgCard,
            border: `1px solid ${S.border}`, borderRadius: 12,
            overflow: "hidden", marginBottom: 16, marginTop: widgets.length > 0 ? 16 : 0 }}>
            <div style={{ padding: "12px 18px", borderBottom: `1px solid ${S.border}` }}>
              <span style={{ fontSize: 14, fontWeight: 700, color: S.textBright }}>
                {action.label || action.id}
              </span>
            </div>
            {result.kind === "pipeline" ? (
              <PipelineResult result={result} />
            ) : (
              <ErgebnisTabelle result={result} formName={form?.name || "export"}
                actionLabel={action.label || action.id} allowDownload={allowDownload} />
            )}
          </div>
        );
      })}
    </>
  );
}
