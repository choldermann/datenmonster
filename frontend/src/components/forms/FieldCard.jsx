import { Trash2, GripVertical } from "lucide-react";
import { getFieldDef } from "./fieldTypes";

const S = {
  bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)", bgMain: "var(--bg-main)",
  border: "var(--border)", textMain: "var(--text-main)", textDim: "var(--text-dim)",
  textBright: "var(--text-bright)",
};

const inputBase = {
  width: "100%", backgroundColor: S.bgMain, border: `1px solid var(--border)`,
  borderRadius: 4, color: S.textMain, fontSize: 11, padding: "5px 8px",
  boxSizing: "border-box", pointerEvents: "none",
};

function FieldPreviewContent({ field }) {
  switch (field.type) {
    case "text":
    case "number":
    case "time":
      return (
        <input readOnly placeholder={field.placeholder || field.label}
          style={{ ...inputBase, color: "var(--text-dim)" }} />
      );
    case "date":
      return <input type="date" readOnly style={{ ...inputBase, color: "var(--text-dim)" }} />;
    case "textarea":
      return (
        <textarea readOnly rows={2} placeholder={field.placeholder || field.label}
          style={{ ...inputBase, resize: "none", color: "var(--text-dim)" }} />
      );
    case "checkbox":
    case "switch":
      return (
        <label style={{ display: "flex", alignItems: "center", gap: 6, pointerEvents: "none" }}>
          <input type="checkbox" readOnly style={{ width: 13, height: 13 }} />
          <span style={{ fontSize: 11, color: S.textDim }}>{field.label}</span>
        </label>
      );
    case "dropdown":
    case "multiselect":
      return (
        <select disabled style={{ ...inputBase, color: "var(--text-dim)" }}>
          <option>— auswählen —</option>
          {(field.options || []).map(o => <option key={o.value}>{o.label}</option>)}
        </select>
      );
    case "radio":
      return (
        <div style={{ display: "flex", flexDirection: "column", gap: 3, pointerEvents: "none" }}>
          {(field.options || []).slice(0, 3).map(o => (
            <label key={o.value} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 10, color: S.textDim }}>
              <input type="radio" readOnly style={{ width: 11, height: 11 }} /> {o.label}
            </label>
          ))}
        </div>
      );
    case "file":
      return (
        <button disabled style={{ ...inputBase, textAlign: "left", cursor: "default",
          color: "var(--text-dim)", display: "block" }}>
          Datei auswählen…
        </button>
      );
    case "button":
      return (
        <button disabled
          style={{ padding: "6px 16px", borderRadius: 5, backgroundColor: "rgba(110,231,183,0.12)",
            border: "1px solid rgba(110,231,183,0.35)", color: "#6ee7b7",
            fontSize: 11, fontWeight: 600, cursor: "default" }}>
          {field.label || "Button"}
        </button>
      );
    case "heading":
      return <p style={{ fontSize: 15, fontWeight: 700, color: S.textBright, margin: 0 }}>{field.content || "Überschrift"}</p>;
    case "label":
      return <p style={{ fontSize: 11, color: S.textDim, margin: 0, lineHeight: 1.5 }}>{field.content || "Text"}</p>;
    case "divider":
      return <hr style={{ border: "none", borderTop: `1px solid ${S.border}`, margin: 0 }} />;
    case "container":
      return (
        <div style={{ border: `1px dashed ${S.border}`, borderRadius: 4, padding: "8px 10px",
          fontSize: 10, color: S.textDim, textAlign: "center" }}>Container</div>
      );
    default:
      return <p style={{ fontSize: 10, color: S.textDim, margin: 0 }}>{field.type}</p>;
  }
}

const LABEL_TYPES = new Set(["checkbox", "switch", "button", "heading", "label", "divider", "container"]);

export default function FieldCard({ field, selected, onClick, onDelete, dragHandleProps }) {
  const def = getFieldDef(field.type);

  return (
    <div onClick={e => { e.stopPropagation(); onClick(); }}
      style={{ flex: `0 0 ${(field.colSpan / 12) * 100}%`,
        maxWidth: `${(field.colSpan / 12) * 100}%`,
        boxSizing: "border-box", padding: "0 4px" }}>
      <div style={{
        backgroundColor: selected ? `${def.color}0a` : S.bgEl,
        border: `1px solid ${selected ? def.color : S.border}`,
        borderRadius: 6, padding: "8px 10px", position: "relative",
        cursor: "pointer", transition: "border-color 0.12s, background-color 0.12s",
      }}>
        {/* Drag handle */}
        <div {...dragHandleProps}
          style={{ position: "absolute", top: 4, left: 4, color: S.textDim,
            cursor: "grab", opacity: 0.4, display: "flex" }}
          onClick={e => e.stopPropagation()}>
          <GripVertical size={11} />
        </div>

        {/* Delete */}
        <button onClick={e => { e.stopPropagation(); onDelete(); }}
          style={{ position: "absolute", top: 4, right: 4, background: "none", border: "none",
            color: S.textDim, cursor: "pointer", padding: 2, lineHeight: 1, display: "flex",
            opacity: selected ? 1 : 0.4 }}
          onMouseEnter={e => e.currentTarget.style.color = "#e07070"}
          onMouseLeave={e => e.currentTarget.style.color = S.textDim}>
          <Trash2 size={10} />
        </button>

        {/* Type badge */}
        <span style={{ fontSize: 8, fontWeight: 700, textTransform: "uppercase",
          letterSpacing: "0.1em", color: def.color, marginBottom: 4, display: "block",
          paddingLeft: 14 }}>
          {def.label}
        </span>

        {/* Label (nur für Felder die ein separates Label haben) */}
        {!LABEL_TYPES.has(field.type) && (
          <label style={{ display: "block", fontSize: 10, fontWeight: 600,
            color: S.textDim, marginBottom: 4 }}>
            {field.label || field.name}
            {field.required && <span style={{ color: "#f87171", marginLeft: 2 }}>*</span>}
          </label>
        )}

        {/* Field Preview */}
        <FieldPreviewContent field={field} />

        {/* Width indicator */}
        <div style={{ position: "absolute", bottom: 3, right: 6, fontSize: 8,
          color: S.textDim, opacity: 0.5 }}>
          {field.colSpan}/12
        </div>
      </div>
    </div>
  );
}
