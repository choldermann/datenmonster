import { useRef } from "react";
import { ShieldCheck, GripVertical, Plus, X } from "lucide-react";
import { S } from "./constants";

export const DQ_NODE_COLOR = "#06b6d4";

const RULE_TYPES = [
  { value: "required",  label: "Pflichtfeld" },
  { value: "number",    label: "Zahl" },
  { value: "email",     label: "E-Mail" },
  { value: "date",      label: "Datum" },
  { value: "url",       label: "URL" },
  { value: "phone",     label: "Telefon" },
  { value: "plz_de",    label: "PLZ (DE)" },
  { value: "iban",      label: "IBAN" },
  { value: "ean",       label: "EAN" },
  { value: "vat_id",    label: "USt-IdNr." },
  { value: "regex",     label: "Regex" },
];

export default function DataQualityNode({ node, onUpdate, onRemove, onPositionChange, debugHighlight, debugStats }) {
  const dragging = useRef(false);
  const offset = useRef({ x: 0, y: 0 });
  const C = DQ_NODE_COLOR;

  const handleMouseDown = (e) => {
    if (e.target.closest("select,input,button,textarea")) return;
    e.preventDefault(); e.stopPropagation();
    dragging.current = true;
    offset.current = { x: e.clientX - node.x, y: e.clientY - node.y };
    const onMove = (ev) => {
      if (!dragging.current) return;
      onPositionChange(node.id, ev.clientX - offset.current.x, ev.clientY - offset.current.y);
    };
    const onUp = () => {
      dragging.current = false;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  const rules = node.rules || [];

  const addRule = () => onUpdate({
    ...node,
    rules: [...rules, { field: "", type: "required", message: "" }],
  });

  const removeRule = (i) => onUpdate({
    ...node,
    rules: rules.filter((_, idx) => idx !== i),
  });

  const updateRule = (i, key, val) => onUpdate({
    ...node,
    rules: rules.map((r, idx) => idx === i ? { ...r, [key]: val } : r),
  });

  return (
    <div
      draggable={false}
      onClick={(e) => e.stopPropagation()}
      style={{
        position: "absolute", left: node.x, top: node.y,
        width: 340, zIndex: debugHighlight ? 20 : 10, userSelect: "none",
        boxShadow: debugHighlight ? `0 0 0 2px ${C}, 0 0 20px ${C}55, 0 8px 32px rgba(0,0,0,0.5)` : "0 8px 32px rgba(0,0,0,0.5)",
        borderRadius: 6, border: debugHighlight ? `1.5px solid ${C}cc` : `1px solid ${C}55`,
        backgroundColor: S.bgCard, overflow: "visible", transition: "box-shadow 0.2s, border-color 0.2s",
      }}
    >
      {/* Header */}
      <div
        onMouseDown={handleMouseDown}
        style={{
          display: "flex", alignItems: "center", gap: 6, padding: "7px 10px",
          cursor: "grab", backgroundColor: C + "12",
          borderBottom: "1px solid " + C + "33", borderRadius: "6px 6px 0 0",
        }}
      >
        <GripVertical size={12} style={{ color: S.textDim, flexShrink: 0 }} />
        <ShieldCheck size={11} style={{ color: C, flexShrink: 0 }} />
        <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: C, flex: 1 }}>
          {node.label || "Datenqualität"}
        </span>
        <span style={{ fontSize: 9, color: S.textDim, fontFamily: "monospace" }}>#{node.id.slice(0, 6)}</span>
        <button
          onClick={() => onRemove(node.id)}
          style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0 }}
        >
          <X size={11} />
        </button>
      </div>

      <div style={{ padding: "8px 10px", display: "flex", flexDirection: "column", gap: 5, borderRadius: "0 0 6px 6px", overflow: "hidden" }}>

        <input
          value={node.label || ""}
          onChange={(e) => onUpdate({ ...node, label: e.target.value })}
          onClick={(e) => e.stopPropagation()}
          placeholder="Bezeichnung (optional)"
          style={{
            width: "100%", boxSizing: "border-box", padding: "4px 8px", fontSize: 11,
            backgroundColor: S.bgEl, border: "1px solid " + S.border,
            borderRadius: 3, color: S.textBright, outline: "none",
          }}
        />

        {rules.length === 0 && (
          <p style={{ fontSize: 10, color: S.textDim, fontStyle: "italic", margin: 0 }}>
            Noch keine Regeln — bitte hinzufügen
          </p>
        )}

        {rules.map((rule, i) => (
          <div key={i} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <input
                value={rule.field || ""}
                onChange={(e) => updateRule(i, "field", e.target.value)}
                onClick={(e) => e.stopPropagation()}
                placeholder="Feldname"
                style={{
                  width: 90, flexShrink: 0, padding: "3px 6px", fontSize: 11,
                  backgroundColor: S.bgEl, border: "1px solid " + S.border,
                  borderRadius: 3, color: S.textBright, outline: "none",
                }}
              />
              <select
                value={rule.type || "required"}
                onChange={(e) => updateRule(i, "type", e.target.value)}
                onClick={(e) => e.stopPropagation()}
                style={{
                  flex: 1, padding: "3px 4px", fontSize: 10,
                  backgroundColor: S.bgEl, border: "1px solid " + S.border,
                  borderRadius: 3, color: S.textBright, outline: "none",
                }}
              >
                {RULE_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
              <button
                onClick={() => removeRule(i)}
                style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0, flexShrink: 0 }}
              >
                <X size={10} />
              </button>
            </div>
            {rule.type === "regex" && (
              <input
                value={rule.pattern || ""}
                onChange={(e) => updateRule(i, "pattern", e.target.value)}
                onClick={(e) => e.stopPropagation()}
                placeholder="Regex-Muster (z.B. ^\d{5}$)"
                style={{
                  width: "100%", boxSizing: "border-box", padding: "3px 6px", fontSize: 10,
                  backgroundColor: S.bgEl, border: "1px solid " + S.border,
                  borderRadius: 3, color: "#fbbf24", outline: "none", fontFamily: "monospace",
                }}
              />
            )}
            <input
              value={rule.message || ""}
              onChange={(e) => updateRule(i, "message", e.target.value)}
              onClick={(e) => e.stopPropagation()}
              placeholder="Fehlermeldung (optional)"
              style={{
                width: "100%", boxSizing: "border-box", padding: "3px 6px", fontSize: 10,
                backgroundColor: S.bgEl, border: "1px solid " + S.border,
                borderRadius: 3, color: S.textDim, outline: "none",
              }}
            />
          </div>
        ))}

        <button
          onClick={addRule}
          style={{
            background: "none", border: `1px dashed ${C}55`, borderRadius: 4,
            color: C, cursor: "pointer", padding: "4px 8px", fontSize: 10,
            display: "flex", alignItems: "center", gap: 4, alignSelf: "flex-start",
          }}
        >
          <Plus size={10} /> Regel hinzufügen
        </button>

        <div style={{ fontSize: 9, color: S.textDim, padding: "4px 8px", borderRadius: 4, backgroundColor: C + "08", border: "1px solid " + C + "22", lineHeight: 1.4 }}>
          💡 Fügt <code style={{ color: C, background: "none" }}>__dq_valid__</code> und{" "}
          <code style={{ color: C, background: "none" }}>__dq_errors__</code> zu jeder Zeile hinzu.
        </div>

        {debugStats && (
          <div style={{ fontSize: 9, color: S.textDim, display: "flex", gap: 8, paddingTop: 2, borderTop: `1px solid ${C}22` }}>
            <span>↓ {(debugStats.rows_out ?? "–").toLocaleString()} Zeilen</span>
            {debugStats.errors > 0 && <span style={{ color: "#f87171" }}>⚠ {debugStats.errors} ungültig</span>}
          </div>
        )}
      </div>
    </div>
  );
}
