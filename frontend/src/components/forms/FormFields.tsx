import { useEffect, useRef, useState } from "react";
import { Play, Loader2, ChevronDown, CheckCircle2, AlertTriangle, Calendar } from "lucide-react";
import DbDropdownField from "./fields/DbDropdownField";
import CalendarRange, { fmtDE } from "./fields/CalendarRange";

const S = {
  bgEl: "var(--bg-elevated)", border: "var(--border)",
  textMain: "var(--text-main)", textBright: "var(--text-bright)", textDim: "var(--text-dim)",
  accent: "var(--accent)",
};

// Feldtypen ohne Wert (reine Anzeige / Aktion) – kein Label davor, keine Pflichtprüfung.
export const LAYOUT_TYPES = new Set(["heading", "label", "divider", "container"]);
export const LABEL_SKIP   = new Set(["checkbox", "switch", "button", "heading", "label", "divider", "container", "article_exclusion", "daterange"]);

// ── Datumsbereich-Presets ──────────────────────────────────────────────────────
const _p = n => String(n).padStart(2, "0");
const _fmt = d => `${d.getFullYear()}-${_p(d.getMonth() + 1)}-${_p(d.getDate())}`;

/** Berechnet [von, bis] (ISO yyyy-mm-dd) für eine Preset-ID. */
export function computeDatePreset(id) {
  const now = new Date();
  const y = now.getFullYear(), m = now.getMonth();
  const mk = (yy, mm, dd) => _fmt(new Date(yy, mm, dd));
  switch (id) {
    case "this_month": return [mk(y, m, 1), _fmt(now)];
    case "last_month": return [mk(y, m - 1, 1), mk(y, m, 0)];       // Tag 0 = letzter Tag Vormonat
    case "this_year":  return [mk(y, 0, 1), _fmt(now)];
    case "last_year":  return [mk(y - 1, 0, 1), mk(y - 1, 11, 31)];
    case "days_30":    { const s = new Date(now); s.setDate(s.getDate() - 29); return [_fmt(s), _fmt(now)]; }
    case "months_12":  { const s = new Date(now); s.setMonth(s.getMonth() - 12); s.setDate(s.getDate() + 1); return [_fmt(s), _fmt(now)]; }
    default:           return [null, null];
  }
}

const DEFAULT_PRESETS = [
  { id: "this_month", label: "Dieser Monat" },
  { id: "last_month", label: "Letzter Monat" },
  { id: "this_year",  label: "Dieses Jahr" },
  { id: "last_year",  label: "Letztes Jahr" },
  { id: "days_30",    label: "30 Tage" },
  { id: "months_12",  label: "12 Monate" },
];

/**
 * Datumsbereichs-Filter mit Presets. Schreibt zwei Laufzeit-Parameter
 * (config.param_from/param_to, Default "von"/"bis") und löst – sofern auto_run –
 * die verknüpften Actions aus (field.action_ids, sonst alle). SQL bindet sie als
 * :von / :bis.
 */
function DateRangeField({ field, params, setParam, onRunAction, running, inp }) {
  const cfg = field.config || {};
  const pf = cfg.param_from || "von";
  const pt = cfg.param_to || "bis";
  const presets = cfg.presets || DEFAULT_PRESETS;
  const autoRun = cfg.auto_run !== false;
  const from = params?.[pf] ?? "";
  const to   = params?.[pt] ?? "";

  // Override mitgeben, weil setParam() erst im nächsten Render greift – der Runner
  // würde sonst die alten Params posten (Stale-Closure).
  const run = override => { if (autoRun && onRunAction) onRunAction(field.action_ids?.length ? field.action_ids : null, override); };
  const applyPreset = id => {
    const [f, t] = computeDatePreset(id);
    if (f && t) { setParam(pf, f); setParam(pt, t); run({ [pf]: f, [pt]: t }); }
  };

  // Kalender-Popover; schließt bei Klick außerhalb.
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  useEffect(() => {
    if (!open) return;
    const onDoc = e => { if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  // Kalenderauswahl: setzt beide Params und löst (sofern auto_run) die Actions aus.
  const onCalChange = (f, t) => { setParam(pf, f); setParam(pt, t); if (f && t) run({ [pf]: f, [pt]: t }); };

  // Default-Preset beim ersten Rendern setzen (und – sofern auto_run – das
  // Dashboard direkt befüllen), wenn noch nichts gewählt ist.
  useEffect(() => {
    if (!from && !to && cfg.default) {
      const [f, t] = computeDatePreset(cfg.default);
      if (f && t) { setParam(pf, f); setParam(pt, t); run({ [pf]: f, [pt]: t }); }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const label = from && to ? `${fmtDE(from)} – ${fmtDE(to)}`
    : from ? `ab ${fmtDE(from)}` : "Zeitraum wählen";

  return (
    <div ref={wrapRef} style={{ position: "relative", display: "flex",
      alignItems: "center", gap: 10, flexWrap: "wrap" }}>
      <button type="button" onClick={() => setOpen(o => !o)} disabled={running}
        style={{ ...inp, width: "auto", display: "inline-flex", alignItems: "center", gap: 8,
          cursor: running ? "wait" : "pointer", color: from ? S.textMain : S.textDim }}>
        <Calendar size={14} style={{ color: S.textDim }} /> {label}
      </button>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {presets.map(p => (
          <button key={p.id} type="button" onClick={() => applyPreset(p.id)} disabled={running}
            style={{ fontSize: 11, fontWeight: 600, padding: "6px 12px", borderRadius: 7,
              background: S.bgEl, border: `1px solid ${S.border}`, color: S.textMain,
              cursor: running ? "wait" : "pointer" }}
            onMouseEnter={e => e.currentTarget.style.borderColor = S.accent}
            onMouseLeave={e => e.currentTarget.style.borderColor = S.border}>
            {p.label}
          </button>
        ))}
      </div>
      {open && (
        <div style={{ position: "absolute", top: "calc(100% + 6px)", left: 0, zIndex: 40,
          background: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 10,
          padding: 14, boxShadow: "0 8px 28px rgba(0,0,0,0.4)" }}>
          <CalendarRange from={from} to={to} onChange={onCalChange} />
        </div>
      )}
    </div>
  );
}

/**
 * Filtert Eingabefelder auf den gerade sichtbaren Ergebnis-Reiter.
 * `config.visible_tabs` (Liste von result_tab-IDs) blendet ein Feld überall sonst
 * aus – z.B. die Artikelauswahl, die nur die Preishistorie steuert. Ohne die
 * Angabe bleibt ein Feld wie bisher auf allen Reitern sichtbar.
 */
export function fieldsForTab(fields, currentTab) {
  return (fields || []).filter(f => {
    const vt = f.config?.visible_tabs;
    if (!Array.isArray(vt) || vt.length === 0) return true;
    return currentTab ? vt.includes(currentTab) : false;
  });
}

/** Button-Feld → Liste der auszulösenden Action-IDs (mehrere via action_ids, sonst einzelne). */
export function buttonActionIds(f) {
  if (f.action_ids && f.action_ids.length) return f.action_ids;
  if (f.action_id) return [f.action_id];
  return null;
}

/** Prüft Pflichtfelder. Gibt die Namen der leer gebliebenen Pflichtfelder zurück. */
export function validateRequired(fields, params) {
  const missing = [];
  for (const f of fields || []) {
    if (!f.required || f.type === "button" || LAYOUT_TYPES.has(f.type) || !f.name) continue;
    const v = params?.[f.name];
    const empty =
      v === undefined || v === null || v === "" ||
      (Array.isArray(v) && v.length === 0) ||
      v === false; // erforderliche Checkbox/Switch muss aktiv sein
    if (empty) missing.push(f.name);
  }
  return missing;
}

/** Ergebnisanzeige für eine Pipeline-Aktion (Status statt Datentabelle). */
export function PipelineResult({ result }) {
  const err = result?.error;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "12px 16px",
      fontSize: 13, color: err ? "#e07070" : "#6ee7b7" }}>
      {err ? <AlertTriangle size={15} /> : <CheckCircle2 size={15} />}
      {err
        ? <span>Pipeline fehlgeschlagen: {err}</span>
        : <span>Pipeline{result.pipeline_name ? ` »${result.pipeline_name}«` : ""} ausgeführt
            {typeof result.nodes_executed === "number" ? ` — ${result.nodes_executed} Schritte` : ""}</span>}
    </div>
  );
}

function groupByRow(fields) {
  const rowMap = {};
  for (const f of fields) {
    const r = f.row ?? 0;
    (rowMap[r] = rowMap[r] || []).push(f);
  }
  return Object.entries(rowMap)
    .sort(([a], [b]) => Number(a) - Number(b))
    .map(([, items]) => items);
}

function FieldInput({ field, value, onChange, onRunAction, running, inp, hasError, compact, params, setParam }) {
  const errStyle = hasError ? { border: "1px solid #f87171" } : {};
  const s = { ...inp, ...errStyle };
  switch (field.type) {
    case "daterange":
      return <DateRangeField field={field} params={params} setParam={setParam}
        onRunAction={onRunAction} running={running} inp={inp} />;
    case "db_dropdown":
      return <DbDropdownField field={field} value={value} onChange={onChange} inp={s}
        onRunAction={onRunAction} running={running} />;
    case "number":
      return <input type="number" value={value ?? ""} onChange={e => onChange(e.target.value)} placeholder={field.placeholder} style={s} />;
    case "date":
      return <input type="date" value={value ?? ""} onChange={e => onChange(e.target.value)} style={s} />;
    case "time":
      return <input type="time" value={value ?? ""} onChange={e => onChange(e.target.value)} style={s} />;
    case "textarea":
      return <textarea value={value ?? ""} onChange={e => onChange(e.target.value)} rows={3}
        placeholder={field.placeholder || field.label} style={{ ...s, resize: "vertical" }} />;
    case "checkbox":
    case "switch":
      return (
        <label style={{ display: "flex", alignItems: "center", gap: 9, cursor: "pointer", padding: compact ? "2px 0" : "9px 0" }}>
          <input type="checkbox" checked={!!value} onChange={e => onChange(e.target.checked)}
            style={{ width: compact ? 15 : 17, height: compact ? 15 : 17, cursor: "pointer" }} />
          <span style={{ fontSize: compact ? 12 : 14, color: S.textMain }}>{field.label}</span>
        </label>
      );
    case "dropdown": {
      // Als Dashboard-Filter nutzbar: bei config.auto_run löst eine Auswahl direkt
      // die verknüpften Actions aus (Override mitgeben gegen Stale-Closure, wie daterange).
      const ddAutoRun = !!field.config?.auto_run;
      const onDdChange = (v) => {
        onChange(v);
        if (ddAutoRun && onRunAction) onRunAction(field.action_ids?.length ? field.action_ids : null, { [field.name]: v });
      };
      return (
        <div style={{ position: "relative" }}>
          <select value={value ?? ""} onChange={e => onDdChange(e.target.value)}
            style={{ ...s, cursor: "pointer", appearance: "none", paddingRight: 30 }}>
            {!ddAutoRun && <option value="">— auswählen —</option>}
            {(field.options || []).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <ChevronDown size={14} style={{ position: "absolute", right: 9, top: "50%",
            transform: "translateY(-50%)", pointerEvents: "none", color: S.textDim }} />
        </div>
      );
    }
    case "multiselect":
      return (
        <select multiple value={Array.isArray(value) ? value : []}
          onChange={e => onChange([...e.target.selectedOptions].map(o => o.value))}
          style={{ ...s, height: compact ? 80 : 96, cursor: "pointer" }}>
          {(field.options || []).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      );
    case "radio":
      return (
        <div style={{ display: "flex", flexDirection: "column", gap: compact ? 5 : 8, padding: "4px 0" }}>
          {(field.options || []).map(o => (
            <label key={o.value} style={{ display: "flex", alignItems: "center", gap: 8,
              cursor: "pointer", fontSize: compact ? 12 : 14 }}>
              <input type="radio" name={field.id} value={o.value} checked={value === o.value}
                onChange={() => onChange(o.value)} style={{ width: 14, height: 14 }} />
              {o.label}
            </label>
          ))}
        </div>
      );
    case "file":
      return <input type="file" onChange={e => onChange(e.target.files?.[0]?.name || "")} style={{ ...s, padding: "6px" }} />;
    case "heading":
      return <h2 style={{ fontSize: compact ? 16 : 22, fontWeight: 700, color: S.textBright, margin: "6px 0 2px" }}>
        {field.content || field.label}</h2>;
    case "label":
      return <p style={{ fontSize: compact ? 12 : 14, color: S.textDim, margin: "2px 0", lineHeight: 1.6 }}>
        {field.content || field.label}</p>;
    case "divider":
      return <hr style={{ border: "none", borderTop: `1px solid ${S.border}`, margin: "6px 0" }} />;
    case "container":
      return field.label
        ? <div style={{ fontSize: compact ? 11 : 13, fontWeight: 700, color: S.textDim,
            borderBottom: `1px solid ${S.border}`, paddingBottom: 4, margin: "8px 0 2px" }}>{field.label}</div>
        : null;
    case "article_exclusion":
      // Wird im FormRunner als eigener Eingabe-Reiter (IntrastatExclusionPanel)
      // gerendert. In der Editor-Vorschau nur ein Hinweis.
      return <div style={{ fontSize: 12, color: S.textDim, padding: "10px 12px", borderRadius: 6,
        border: `1px dashed ${S.border}` }}>
        Ausschlussartikel-Reiter „{field.label || "Ausschlussartikel"}" – im ausgefüllten Formular als eigener Tab sichtbar.
      </div>;
    case "button":
      return (
        <button onClick={() => onRunAction?.(buttonActionIds(field))} disabled={running}
          style={{ display: "inline-flex", alignItems: "center", gap: 7,
            padding: compact ? "8px 20px" : "10px 24px", borderRadius: 7,
            fontSize: compact ? 12 : 14, fontWeight: 600,
            backgroundColor: "rgba(110,231,183,0.12)", border: "1px solid rgba(110,231,183,0.4)",
            color: "#6ee7b7", cursor: running ? "wait" : "pointer",
            ...(field.fullWidth ? { width: "100%", justifyContent: "center" } : {}) }}>
          {running ? <Loader2 size={13} style={{ animation: "spin 1s linear infinite" }} /> : <Play size={13} />}
          {field.label || "Ausführen"}
        </button>
      );
    default:
      return <input type="text" value={value ?? ""} onChange={e => onChange(e.target.value)}
        placeholder={field.placeholder || field.label} style={s} />;
  }
}

/**
 * Gemeinsamer Formular-Feld-Renderer für FormRunner, PortalRunner und FormPreview.
 * Respektiert die im Editor gebaute Zeilen-/Spalten-Anordnung (row/colSpan),
 * rendert alle Feldtypen, zeigt Pflichtfeld-Sternchen und markiert fehlende
 * Pflichtfelder (errors).
 */
export default function FormFields({ fields, params, setParam, onRunAction, running,
                                     compact = false, errors }) {
  const rows = groupByRow(fields || []);
  const errSet = errors instanceof Set ? errors : new Set(errors || []);
  const inp = {
    width: "100%", backgroundColor: S.bgEl, border: `1px solid ${S.border}`,
    borderRadius: compact ? 5 : 6, color: S.textMain, fontSize: compact ? 12 : 14,
    padding: compact ? "7px 10px" : "9px 12px", outline: "none", boxSizing: "border-box",
  };
  const gutter = compact ? 6 : 10;
  return (
    <>
      {rows.map((rowFields, ri) => {
        // Ein Knopf trägt keine Beschriftung und beginnt deshalb ganz oben,
        // während ein Eingabefeld erst unter seinem Label anfängt. Steht beides
        // in derselben Zeile, hängt der Knopf sonst in der Luft – dann wird er
        // auf die Grundlinie der Felder gesetzt.
        const hatBeschriftetes = rowFields.some(
          x => !LABEL_SKIP.has(x.type) && (x.label || x.name));
        return (
        <div key={ri} style={{ display: "flex", flexWrap: "wrap", margin: `0 -${gutter}px ${compact ? 10 : 16}px` }}>
          {rowFields.map(f => {
            const width = `${((f.colSpan || 12) / 12) * 100}%`;
            const aufGrundlinie = hatBeschriftetes && f.type === "button";
            return (
              <div key={f.id || f.name} style={{ flex: `0 0 ${width}`, maxWidth: width,
                padding: `0 ${gutter}px`, boxSizing: "border-box",
                ...(aufGrundlinie
                  ? { display: "flex", flexDirection: "column", justifyContent: "flex-end" }
                  : {}) }}>
                {!LABEL_SKIP.has(f.type) && (f.label || f.name) && (
                  <label style={{ display: "block", fontSize: compact ? 10 : 12, fontWeight: 600,
                    color: S.textDim, marginBottom: compact ? 4 : 6, textTransform: "uppercase",
                    letterSpacing: "0.05em" }}>
                    {f.label || f.name}
                    {f.required && <span style={{ color: "#f87171", marginLeft: 3 }}>*</span>}
                  </label>
                )}
                <FieldInput
                  field={f}
                  value={params?.[f.name]}
                  onChange={v => setParam(f.name, v)}
                  onRunAction={onRunAction}
                  running={running}
                  inp={inp}
                  hasError={f.name && errSet.has(f.name)}
                  compact={compact}
                  params={params}
                  setParam={setParam}
                />
              </div>
            );
          })}
        </div>
        );
      })}
    </>
  );
}
