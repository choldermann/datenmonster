import { useState } from "react";
import { X, FileText, Loader2 } from "lucide-react";

const S = {
  bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)", border: "var(--border)",
  textMain: "var(--text-main)", textBright: "var(--text-bright)", textDim: "var(--text-dim)",
  accent: "var(--accent)",
};

export const SECTION_SUMMARY = "__summary__";
export const SECTION_ASSESSMENT = "__assessment__";

const storageKey = (formId) => `dm_report_sections_${formId}`;

/** Wählbare Abschnitte aus dem Formular-Schema ableiten: KI-Analyse, Bewertungs-
 *  tabelle und die Ergebnis-Reiter (Deckblatt ist immer dabei). */
export function reportSections(schema = {}) {
  const widgets = schema.widgets || [];
  const aiWidget = widgets.find(w => w.type === "ai_summary");
  const out = [];
  if (aiWidget) {
    out.push({ id: SECTION_SUMMARY, label: "Management-Summary (KI-Analyse)",
      hint: "Fließtext-Analyse der Kennzahlen" });
    if (aiWidget.config?.report_layout) {
      out.push({ id: SECTION_ASSESSMENT, label: "Bewertungstabelle",
        hint: "Ampel je Bereich (gut / verbesserungswürdig)" });
    }
  }
  for (const tab of (schema.result_tabs || [])) {
    const ids = new Set(tab.action_ids || []);
    const n = widgets.filter(w => w.action_id && ids.has(w.action_id)).length;
    out.push({ id: tab.id, label: tab.label || tab.id,
      hint: n ? `${n} Auswertung${n === 1 ? "" : "en"}` : "" });
  }
  return out;
}

/** Zuletzt gewählte Abschnitte laden – unbekannte/entfallene IDs werden verworfen,
 *  neu hinzugekommene Abschnitte sind vorausgewählt (Report bleibt vollständig). */
export function loadSelection(formId, sections) {
  const all = sections.map(s => s.id);
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey(formId)) || "null");
    if (Array.isArray(saved)) {
      const known = new Set(saved.filter(id => all.includes(id)));
      return known.size ? all.filter(id => known.has(id)) : all;
    }
  } catch { /* kaputter Eintrag → Standard */ }
  return all;
}

/**
 * Auswahl-Dialog vor dem PDF-Report: welche Abschnitte sollen hinein?
 * Abgewählte Reiter werden serverseitig gar nicht erst abgefragt – der Report
 * wird dadurch auch schneller.
 */
export default function ReportOptionsModal({ formId, schema, busy, onClose, onConfirm }) {
  const sections = reportSections(schema);
  const [selected, setSelected] = useState(() => new Set(loadSelection(formId, sections)));

  const toggle = (id) => setSelected(prev => {
    const next = new Set(prev);
    next.has(id) ? next.delete(id) : next.add(id);
    return next;
  });

  const confirm = () => {
    // Formular ohne wählbare Abschnitte → null = kompletter Report (wie bisher).
    if (!sections.length) return onConfirm(null);
    const picked = sections.map(s => s.id).filter(id => selected.has(id));
    try { localStorage.setItem(storageKey(formId), JSON.stringify(picked)); } catch { /* egal */ }
    onConfirm(picked);
  };

  const allOn = selected.size === sections.length;
  const nothingPicked = sections.length > 0 && selected.size === 0;

  return (
    <div onClick={busy ? undefined : onClose}
      style={{ position: "fixed", inset: 0, zIndex: 1000, backgroundColor: "rgba(0,0,0,0.55)",
        display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
      <div onClick={e => e.stopPropagation()}
        style={{ width: "min(520px, 94vw)", maxHeight: "88vh", backgroundColor: S.bgCard,
          border: `1px solid ${S.border}`, borderRadius: 12, display: "flex", flexDirection: "column",
          overflow: "hidden", boxShadow: "0 20px 60px rgba(0,0,0,0.5)" }}>

        {/* Header */}
        <div style={{ padding: "14px 18px", borderBottom: `1px solid ${S.border}`,
          display: "flex", alignItems: "center", gap: 10 }}>
          <FileText size={15} style={{ color: S.accent, flexShrink: 0 }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <p style={{ fontSize: 14, fontWeight: 700, color: S.textBright, margin: 0 }}>
              PDF-Report zusammenstellen
            </p>
            <p style={{ fontSize: 11, color: S.textDim, margin: "2px 0 0" }}>
              Deckblatt (Firma, Zeitraum, Filter) ist immer dabei.
            </p>
          </div>
          <button onClick={onClose} disabled={busy}
            style={{ background: "none", border: "none", color: S.textDim,
              cursor: busy ? "default" : "pointer", padding: 2, flexShrink: 0 }}>
            <X size={16} />
          </button>
        </div>

        {/* Abschnitte */}
        <div style={{ overflow: "auto", padding: "12px 18px", display: "flex",
          flexDirection: "column", gap: 4 }}>
          {sections.length === 0 ? (
            <p style={{ fontSize: 12, color: S.textDim, margin: "8px 0" }}>
              Dieses Formular hat keine auswählbaren Abschnitte – der Report enthält alle Auswertungen.
            </p>
          ) : sections.map(sec => {
            const on = selected.has(sec.id);
            return (
              <label key={sec.id}
                style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "8px 10px",
                  borderRadius: 8, cursor: "pointer", backgroundColor: on ? S.bgEl : "transparent",
                  border: `1px solid ${on ? S.border : "transparent"}` }}>
                <input type="checkbox" checked={on} onChange={() => toggle(sec.id)}
                  style={{ marginTop: 2, accentColor: S.accent, cursor: "pointer" }} />
                <span style={{ minWidth: 0 }}>
                  <span style={{ display: "block", fontSize: 12.5, fontWeight: 600,
                    color: on ? S.textBright : S.textMain }}>{sec.label}</span>
                  {sec.hint && (
                    <span style={{ display: "block", fontSize: 10.5, color: S.textDim, marginTop: 1 }}>
                      {sec.hint}
                    </span>
                  )}
                </span>
              </label>
            );
          })}
        </div>

        {/* Footer */}
        <div style={{ padding: "12px 18px", borderTop: `1px solid ${S.border}`,
          display: "flex", alignItems: "center", gap: 10 }}>
          {sections.length > 0 && (
            <button onClick={() => setSelected(allOn ? new Set() : new Set(sections.map(s => s.id)))}
              style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer",
                fontSize: 11.5 }}>
              {allOn ? "Nichts auswählen" : "Alles auswählen"}
            </button>
          )}
          <span style={{ flex: 1 }} />
          <button onClick={onClose} disabled={busy}
            style={{ padding: "6px 14px", borderRadius: 6, border: `1px solid ${S.border}`,
              background: "none", color: S.textDim, cursor: busy ? "default" : "pointer", fontSize: 12 }}>
            Abbrechen
          </button>
          <button onClick={confirm} disabled={busy || nothingPicked}
            title={nothingPicked ? "Mindestens einen Abschnitt auswählen" : ""}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 16px", borderRadius: 6,
              border: `1px solid ${S.accent}55`, backgroundColor: `${S.accent}15`, color: S.accent,
              opacity: (busy || nothingPicked) ? 0.5 : 1, fontSize: 12, fontWeight: 600,
              cursor: busy ? "wait" : nothingPicked ? "not-allowed" : "pointer" }}>
            {busy ? <Loader2 size={12} style={{ animation: "spin 1s linear infinite" }} /> : <FileText size={12} />}
            {busy ? "Erstelle PDF…" : "PDF erzeugen"}
          </button>
        </div>
      </div>
    </div>
  );
}
