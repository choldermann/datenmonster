import { Play, Loader2, ChevronDown } from "lucide-react";

const S = {
  bgEl: "var(--bg-elevated)", border: "var(--border)",
  textMain: "var(--text-main)", textBright: "var(--text-bright)", textDim: "var(--text-dim)",
};

// Feldtypen ohne Wert (reine Anzeige / Aktion) – kein Label davor, keine Pflichtprüfung.
export const LAYOUT_TYPES = new Set(["heading", "label", "divider", "container"]);
export const LABEL_SKIP   = new Set(["checkbox", "switch", "button", "heading", "label", "divider", "container"]);

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

function FieldInput({ field, value, onChange, onRunAction, running, inp, hasError, compact }) {
  const errStyle = hasError ? { border: "1px solid #f87171" } : {};
  const s = { ...inp, ...errStyle };
  switch (field.type) {
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
    case "dropdown":
      return (
        <div style={{ position: "relative" }}>
          <select value={value ?? ""} onChange={e => onChange(e.target.value)}
            style={{ ...s, cursor: "pointer", appearance: "none", paddingRight: 30 }}>
            <option value="">— auswählen —</option>
            {(field.options || []).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <ChevronDown size={14} style={{ position: "absolute", right: 9, top: "50%",
            transform: "translateY(-50%)", pointerEvents: "none", color: S.textDim }} />
        </div>
      );
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
    case "button":
      return (
        <button onClick={() => onRunAction?.(buttonActionIds(field))} disabled={running}
          style={{ display: "inline-flex", alignItems: "center", gap: 7,
            padding: compact ? "8px 20px" : "10px 24px", borderRadius: 7,
            fontSize: compact ? 12 : 14, fontWeight: 600,
            backgroundColor: "rgba(110,231,183,0.12)", border: "1px solid rgba(110,231,183,0.4)",
            color: "#6ee7b7", cursor: running ? "wait" : "pointer" }}>
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
      {rows.map((rowFields, ri) => (
        <div key={ri} style={{ display: "flex", flexWrap: "wrap", margin: `0 -${gutter}px ${compact ? 10 : 16}px` }}>
          {rowFields.map(f => {
            const width = `${((f.colSpan || 12) / 12) * 100}%`;
            return (
              <div key={f.id || f.name} style={{ flex: `0 0 ${width}`, maxWidth: width,
                padding: `0 ${gutter}px`, boxSizing: "border-box" }}>
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
                />
              </div>
            );
          })}
        </div>
      ))}
    </>
  );
}
