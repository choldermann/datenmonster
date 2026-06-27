import { useRef, useState } from "react";
import { FunctionSquare, GripVertical, Plus, Sparkles, X } from "lucide-react";
import { S } from "./constants";
import AiStreamModal from "./AiStreamModal";
import { generateExpression } from "../../services/aiService";

export const EXPR_NODE_COLOR = "#e879f9";

const DOT = 10;
const HINT = "Formel-Syntax: {feldname}, concat({a}, \" \", {b}), if_(Bedingung, dann, sonst), round({preis} * 1.19, 2)";

export default function ExprNode({ node, onUpdate, onRemove, onPositionChange, outputRefs, debugHighlight, debugStats, aiEnabled, mappingId }) {
  const dragging = useRef(false);
  const offset = useRef({ x: 0, y: 0 });
  const [aiFieldIdx, setAiFieldIdx] = useState(null);
  const C = EXPR_NODE_COLOR;

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

  const outputFields = node.output_fields || [];

  const addField = () => onUpdate({
    ...node,
    output_fields: [...outputFields, { name: `feld_${outputFields.length + 1}`, expr: "" }],
  });

  const removeField = (i) => onUpdate({
    ...node,
    output_fields: outputFields.filter((_, idx) => idx !== i),
  });

  const updateField = (i, key, val) => onUpdate({
    ...node,
    output_fields: outputFields.map((f, idx) => idx === i ? { ...f, [key]: val } : f),
  });

  return (
    <div
      draggable={false}
      onClick={(e) => e.stopPropagation()}
      style={{
        position: "absolute", left: node.x, top: node.y,
        width: 320, zIndex: debugHighlight ? 20 : 10, userSelect: "none",
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
        <FunctionSquare size={11} style={{ color: C, flexShrink: 0 }} />
        <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: C, flex: 1 }}>
          {node.label || "Expression"}
        </span>
        <span style={{ fontSize: 9, color: S.textDim, fontFamily: "monospace" }}>#{node.id.slice(0, 6)}</span>
        <button
          onClick={() => onRemove(node.id)}
          style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0 }}
        >
          <X size={11} />
        </button>
      </div>

      <div style={{ padding: "8px 10px", display: "flex", flexDirection: "column", gap: 6, borderRadius: "0 0 6px 6px", overflow: "hidden" }}>

        {outputFields.length === 0 && (
          <p style={{ fontSize: 10, color: S.textDim, fontStyle: "italic", margin: 0 }}>
            Noch keine Felder — bitte hinzufügen
          </p>
        )}

        {outputFields.map((f, i) => (
          <div key={i} style={{ display: "flex", flexDirection: "column", gap: 3 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <input
                value={f.name || ""}
                onChange={(e) => updateField(i, "name", e.target.value)}
                onClick={(e) => e.stopPropagation()}
                placeholder="feldname"
                title="Ausgabefeldname"
                style={{
                  width: 90, padding: "3px 6px", fontSize: 11, flexShrink: 0,
                  backgroundColor: S.bgEl, border: "1px solid " + S.border,
                  borderRadius: 3, color: C, outline: "none", fontFamily: "monospace",
                }}
              />
              <span style={{ color: S.textDim, fontSize: 11, flexShrink: 0 }}>=</span>
              <input
                value={f.expr || ""}
                onChange={(e) => updateField(i, "expr", e.target.value)}
                onClick={(e) => e.stopPropagation()}
                placeholder='concat({a}, " ", {b})'
                title={HINT}
                style={{
                  flex: 1, padding: "3px 6px", fontSize: 11,
                  backgroundColor: S.bgEl, border: "1px solid " + S.border,
                  borderRadius: 3, color: S.textBright, outline: "none", fontFamily: "monospace",
                }}
              />
              {aiEnabled && (
                <button onClick={() => setAiFieldIdx(i)} title="✨ Ausdruck mit KI generieren"
                  style={{ background: "none", border: "none", color: "#fce499", cursor: "pointer", padding: 0, flexShrink: 0 }}>
                  <Sparkles size={10} />
                </button>
              )}
              <button
                onClick={() => removeField(i)}
                style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0, flexShrink: 0 }}
              >
                <X size={10} />
              </button>
              {/* Output dot */}
              <div
                ref={(el) => {
                  if (outputRefs?.current) {
                    const key = node.id + "_" + i;
                    if (!outputRefs.current[key]) outputRefs.current[key] = { current: null };
                    outputRefs.current[key].current = el;
                  }
                }}
                draggable={!!(f.name)}
                onDragStart={(e) => {
                  if (!f.name) { e.preventDefault(); return; }
                  e.stopPropagation();
                  e.dataTransfer.setData("source_dataset_id", "__expr__" + node.id);
                  e.dataTransfer.setData("source_field", f.name);
                }}
                style={{
                  width: DOT, height: DOT, borderRadius: "50%", flexShrink: 0,
                  backgroundColor: f.name ? C : S.border,
                  border: "2px solid " + C,
                  cursor: f.name ? "grab" : "default",
                  marginRight: -16,
                }}
                title={f.name ? f.name + " auf Zielfeld ziehen" : "Feldname eingeben"}
              />
            </div>
          </div>
        ))}

        <button
          onClick={addField}
          style={{
            background: "none", border: `1px dashed ${C}55`, borderRadius: 4,
            color: C, cursor: "pointer", padding: "4px 8px", fontSize: 10,
            display: "flex", alignItems: "center", gap: 4, alignSelf: "flex-start",
          }}
        >
          <Plus size={10} /> Formelfeld hinzufügen
        </button>

        <div style={{ fontSize: 9, color: S.textDim, padding: "4px 8px", borderRadius: 4, backgroundColor: C + "08", border: "1px solid " + C + "22", lineHeight: 1.4 }}>
          💡 <code style={{ color: C, background: "none" }}>{"{feld}"}</code> = Feldwert ·{" "}
          <code style={{ color: C, background: "none" }}>concat()</code>{" "}
          <code style={{ color: C, background: "none" }}>upper()</code>{" "}
          <code style={{ color: C, background: "none" }}>if_()</code>{" "}
          <code style={{ color: C, background: "none" }}>round()</code>{" "}
          <code style={{ color: C, background: "none" }}>today()</code>
        </div>

        {debugStats && (
          <div style={{ fontSize: 9, color: S.textDim, display: "flex", gap: 8, paddingTop: 2, borderTop: `1px solid ${C}22` }}>
            <span>↓ {(debugStats.rows_out ?? "–").toLocaleString()} Zeilen</span>
            {debugStats.errors > 0 && <span style={{ color: "#f87171" }}>⚠ {debugStats.errors} Fehler</span>}
          </div>
        )}
      </div>
    </div>

    {aiFieldIdx !== null && (
      <AiStreamModal
        title={`✨ Ausdruck generieren — ${outputFields[aiFieldIdx]?.name || "Feld"}`}
        placeholder='z.B. "Vorname und Nachname mit Leerzeichen verbinden"'
        onGenerate={(desc, onToken) =>
          generateExpression(
            desc,
            mappingId,
            node.id,
            outputFields[aiFieldIdx]?.name || "",
            onToken,
          )
        }
        onApply={(expr) => updateField(aiFieldIdx, "expr", expr.trim())}
        onClose={() => setAiFieldIdx(null)}
        applyLabel="Ausdruck übernehmen"
      />
    )}
  );
}
