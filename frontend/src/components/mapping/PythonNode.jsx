import { useRef, useState } from "react";
import { Code, GripVertical, Plus, Sparkles, X } from "lucide-react";
import { S } from "./constants";
import AiStreamModal from "./AiStreamModal";
import { generatePython } from "../../services/aiService";

export const PYTHON_NODE_COLOR = "#22c55e";

const DOT = 10;

export default function PythonNode({ node, onUpdate, onRemove, onPositionChange, outputRefs, debugHighlight, aiEnabled, mappingId }) {
  const dragging = useRef(false);
  const offset = useRef({ x: 0, y: 0 });
  const [aiOpen, setAiOpen] = useState(false);
  const C = PYTHON_NODE_COLOR;

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
    output_fields: [...outputFields, `feld_${outputFields.length + 1}`],
  });

  const removeField = (i) => onUpdate({
    ...node,
    output_fields: outputFields.filter((_, idx) => idx !== i),
  });

  const updateField = (i, val) => onUpdate({
    ...node,
    output_fields: outputFields.map((f, idx) => (idx === i ? val : f)),
  });

  return (
    <>
    <div
      draggable={false}
      onClick={(e) => e.stopPropagation()}
      style={{
        position: "absolute", left: node.x, top: node.y,
        width: 300, zIndex: debugHighlight ? 20 : 10, userSelect: "none",
        boxShadow: debugHighlight ? `0 0 0 2px ${C}, 0 0 20px ${C}55, 0 8px 32px rgba(0,0,0,0.5)` : "0 8px 32px rgba(0,0,0,0.5)",
        borderRadius: 6, border: debugHighlight ? `1.5px solid ${C}cc` : "1px solid " + C + "55",
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
        <Code size={11} style={{ color: C, flexShrink: 0 }} />
        <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: C, flex: 1 }}>
          Python Script
        </span>
        <span style={{ fontSize: 9, color: S.textDim, fontFamily: "monospace" }}>#{node.id.slice(0, 6)}</span>
        {aiEnabled && (
          <button onClick={() => setAiOpen(true)} title="✨ Python-Code mit KI generieren"
            style={{ background: "none", border: "none", color: "#fce499", cursor: "pointer", padding: "0 2px", display: "flex", alignItems: "center" }}>
            <Sparkles size={11} />
          </button>
        )}
        <button
          onClick={() => onRemove(node.id)}
          style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0 }}
        >
          <X size={11} />
        </button>
      </div>

      <div style={{ padding: "8px 10px", display: "flex", flexDirection: "column", gap: 8, borderRadius: "0 0 6px 6px", overflow: "hidden" }}>

        {/* Code Editor */}
        <div>
          <p style={{ fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
            Python-Skript · <code style={{ color: C, background: "none" }}>row</code> = aktueller Datensatz
          </p>
          <textarea
            value={node.script || ""}
            onChange={(e) => onUpdate({ ...node, script: e.target.value })}
            onKeyDown={(e) => {
              if (e.key === "Tab") {
                e.preventDefault();
                const ta = e.target;
                const start = ta.selectionStart;
                const end = ta.selectionEnd;
                const newVal = ta.value.substring(0, start) + "    " + ta.value.substring(end);
                onUpdate({ ...node, script: newVal });
                requestAnimationFrame(() => { ta.selectionStart = ta.selectionEnd = start + 4; });
              }
            }}
            onClick={(e) => e.stopPropagation()}
            spellCheck={false}
            placeholder={"# row enthält alle Eingabefelder als dict\n# Beispiel:\nrow['netto'] = float(row.get('brutto', 0)) / 1.19\nreturn row"}
            style={{
              width: "100%", boxSizing: "border-box",
              minHeight: 100, resize: "vertical",
              fontFamily: "monospace", fontSize: 11, lineHeight: 1.5,
              color: "#e2e8f0", backgroundColor: "rgba(0,0,0,0.4)",
              border: "1px solid " + C + "33", borderRadius: 4,
              padding: "6px 8px", outline: "none",
            }}
          />
        </div>

        {/* Output Fields */}
        <div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
            <p style={{ fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Ausgabefelder
            </p>
            <button
              onClick={addField}
              title="Ausgabefeld hinzufügen"
              style={{ background: "none", border: "none", color: C, cursor: "pointer", padding: 0, display: "flex" }}
            >
              <Plus size={10} />
            </button>
          </div>

          {outputFields.length === 0 && (
            <p style={{ fontSize: 10, color: S.textDim, fontStyle: "italic" }}>Noch keine Felder – bitte hinzufügen</p>
          )}

          {outputFields.map((f, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 4, marginBottom: 4 }}>
              <input
                value={f}
                onChange={(e) => updateField(i, e.target.value)}
                onClick={(e) => e.stopPropagation()}
                placeholder="feldname"
                style={{
                  flex: 1, padding: "3px 6px", fontSize: 11,
                  backgroundColor: S.bgEl, border: "1px solid " + S.border,
                  borderRadius: 3, color: S.textBright, outline: "none",
                }}
              />
              <button
                onClick={() => removeField(i)}
                style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0, flexShrink: 0 }}
              >
                <X size={10} />
              </button>
              {/* Output dot – außerhalb der Node-Box für Verbindungen */}
              <div
                ref={(el) => {
                  if (outputRefs?.current) {
                    const key = node.id + "_" + i;
                    if (!outputRefs.current[key]) outputRefs.current[key] = { current: null };
                    outputRefs.current[key].current = el;
                  }
                }}
                draggable={!!f}
                onDragStart={(e) => {
                  if (!f) { e.preventDefault(); return; }
                  e.stopPropagation();
                  e.dataTransfer.setData("source_dataset_id", "__python__" + node.id);
                  e.dataTransfer.setData("source_field", f);
                }}
                style={{
                  width: DOT, height: DOT, borderRadius: "50%", flexShrink: 0,
                  backgroundColor: f ? C : S.border,
                  border: "2px solid " + C,
                  cursor: f ? "grab" : "default",
                  marginRight: -16,
                }}
                title={f ? f + " auf Zielfeld ziehen" : "Feldname eingeben"}
              />
            </div>
          ))}
        </div>

        <div style={{ fontSize: 9, color: S.textDim, padding: "4px 8px", borderRadius: 4, backgroundColor: C + "08", border: "1px solid " + C + "22", lineHeight: 1.4 }}>
          💡 Felder aus <code style={{ color: C, background: "none" }}>row</code> lesen &amp; schreiben, dann <code style={{ color: C, background: "none" }}>return row</code> — Fehler stoppen nur diese Zeile.
        </div>
      </div>
    </div>

    {aiOpen && (
      <AiStreamModal
        title="✨ Python-Code generieren"
        placeholder='z.B. "Netto aus Brutto berechnen, MwSt 19%"'
        onGenerate={(desc, onToken) => generatePython(desc, mappingId, node.id, node.script || "", onToken)}
        onApply={(code) => onUpdate({ ...node, script: code })}
        onClose={() => setAiOpen(false)}
        applyLabel="Code übernehmen"
      />
    )}
    </>
  );
}
