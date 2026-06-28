import { useRef } from "react";
import { GripVertical, Plus, Trash2, X, Minimize2 } from "lucide-react";
import { S, PARAMS_NODE_COLOR } from "./constants";
import { MinimizedNode } from "./MinimizedNode";

const FIELD_TYPES = [
  { value: "text",   label: "Text" },
  { value: "number", label: "Zahl" },
  { value: "date",   label: "Datum" },
];

const PARAMS_ACTIVE_BORDER = "#fce499";

function ParamsNode({ node, onRemove, onPositionChange, onUpdate, outputRefs, onMiniPortsReady, isActive, onActivate }) {
  const miniLeftRef = useRef(null);
  const miniRightRef = useRef(null);

  const handleMouseDown = (e) => {
    if (e.target.closest("button") || e.target.closest("input") || e.target.closest("select")) return;
    e.preventDefault(); e.stopPropagation();
    const startX = e.clientX - node.x;
    const startY = e.clientY - node.y;
    const onMove = (ev) => onPositionChange(node.id, ev.clientX - startX, ev.clientY - startY);
    const onUp = () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  if (node.minimized) {
    return (
      <div style={{ position: "absolute", left: node.x, top: node.y, zIndex: 10, overflow: "visible", width: 44, height: 44 }}
        onMouseDown={handleMouseDown}>
        <MinimizedNode
          type="params" color={PARAMS_NODE_COLOR} label="PARAMS"
          onExpand={() => onUpdate({ ...node, minimized: false })}
          onMouseDown={handleMouseDown}
          portLeftRef={miniLeftRef} portRightRef={miniRightRef}
          onPortLeftDrop={null} onPortRightDragStart={null}
        />
      </div>
    );
  }

  const fields = node.fields || [];

  const updateField = (i, patch) => {
    const updated = fields.map((f, idx) => idx === i ? { ...f, ...patch } : f);
    onUpdate({ ...node, fields: updated });
  };

  const addField = () => {
    const n = fields.length + 1;
    onUpdate({ ...node, fields: [...fields, { name: `param_${n}`, type: "text", label: `Parameter ${n}`, default: "" }] });
  };

  const removeField = (i) => {
    onUpdate({ ...node, fields: fields.filter((_, idx) => idx !== i) });
  };

  return (
    <div draggable={false}
      style={{ position: "absolute", left: node.x, top: node.y, width: 240, zIndex: 10, userSelect: "none",
        boxShadow: isActive ? `0 0 0 2px ${PARAMS_ACTIVE_BORDER}, 0 8px 32px rgba(0,0,0,0.5)` : "0 8px 32px rgba(0,0,0,0.5)", borderRadius: 6, overflow: "hidden",
        border: isActive ? `1px solid ${PARAMS_ACTIVE_BORDER}` : `1px solid ${PARAMS_NODE_COLOR}55`, backgroundColor: S.bgCard, transition: "box-shadow 0.15s, border-color 0.15s" }}
      onClick={(e) => { e.stopPropagation(); onActivate?.({ type: "params", params: (node.fields || []).map(f => ({ name: f.name, type: f.type, label: f.label })) }); }}>

      {/* Header */}
      <div onMouseDown={handleMouseDown} draggable={false}
        style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 10px", cursor: "grab",
          backgroundColor: `${PARAMS_NODE_COLOR}12`, borderBottom: `1px solid ${PARAMS_NODE_COLOR}33` }}>
        <GripVertical size={12} style={{ color: S.textDim, flexShrink: 0 }} />
        <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: PARAMS_NODE_COLOR, flex: 1 }}>
          Params Node
        </span>
        <button onClick={() => onUpdate({ ...node, minimized: true })} title="Minimieren"
          style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0, display: "flex" }}>
          <Minimize2 size={10} />
        </button>
        <button onClick={(e) => { e.stopPropagation(); onRemove(node.id); }}
          style={{ color: S.textDim, flexShrink: 0, lineHeight: 1, background: "none", border: "none", cursor: "pointer" }}
          onMouseEnter={(e) => e.currentTarget.style.color = "#e07070"}
          onMouseLeave={(e) => e.currentTarget.style.color = S.textDim}>
          <X size={12} />
        </button>
      </div>

      {/* Hint */}
      <div style={{ padding: "5px 10px", borderBottom: `1px solid ${PARAMS_NODE_COLOR}22` }}>
        <p style={{ fontSize: 9, color: S.textDim, margin: 0, lineHeight: 1.4 }}>
          Laufzeit-Parameter aus Formular · Werte kommen per <code style={{ color: PARAMS_NODE_COLOR }}>run_params</code>
        </p>
      </div>

      {/* Fields */}
      <div style={{ maxHeight: 280, overflowY: "auto", scrollbarWidth: "thin" }}>
        {fields.length === 0 && (
          <p style={{ fontSize: 9, color: S.textDim, padding: "8px 10px", fontStyle: "italic", margin: 0 }}>
            Kein Parameter — "+" klicken
          </p>
        )}
        {fields.map((f, i) => (
          <div key={i} style={{ borderBottom: `1px solid ${PARAMS_NODE_COLOR}11`, padding: "6px 10px" }}>
            {/* Name + Type */}
            <div style={{ display: "flex", gap: 4, marginBottom: 3 }}>
              <input value={f.name || ""}
                onChange={(e) => updateField(i, { name: e.target.value })}
                onClick={(e) => e.stopPropagation()}
                placeholder="feldname"
                style={{ flex: 2, backgroundColor: S.bgMain, border: `1px solid ${PARAMS_NODE_COLOR}44`, borderRadius: 3,
                  color: PARAMS_NODE_COLOR, fontSize: 10, fontFamily: "monospace", padding: "3px 6px", outline: "none" }} />
              <select value={f.type || "text"}
                onChange={(e) => updateField(i, { type: e.target.value })}
                style={{ flex: 1, backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 3,
                  color: S.textDim, fontSize: 9, padding: "3px 4px", outline: "none", cursor: "pointer" }}>
                {FIELD_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
              <button onClick={() => removeField(i)}
                style={{ color: S.textDim, background: "none", border: "none", cursor: "pointer", padding: 2, flexShrink: 0 }}
                onMouseEnter={(e) => e.currentTarget.style.color = "#e07070"}
                onMouseLeave={(e) => e.currentTarget.style.color = S.textDim}>
                <Trash2 size={9} />
              </button>
            </div>
            {/* Label + Default */}
            <div style={{ display: "flex", gap: 4 }}>
              <input value={f.label || ""}
                onChange={(e) => updateField(i, { label: e.target.value })}
                onClick={(e) => e.stopPropagation()}
                placeholder="Beschriftung"
                style={{ flex: 2, backgroundColor: S.bgMain, border: `1px solid ${S.border}`, borderRadius: 3,
                  color: S.textMain, fontSize: 9, padding: "2px 5px", outline: "none" }} />
              <input value={f.default || ""}
                onChange={(e) => updateField(i, { default: e.target.value })}
                onClick={(e) => e.stopPropagation()}
                placeholder="Standard"
                style={{ flex: 1, backgroundColor: S.bgMain, border: `1px solid ${S.border}`, borderRadius: 3,
                  color: S.textDim, fontSize: 9, padding: "2px 5px", outline: "none" }} />
            </div>
          </div>
        ))}
      </div>

      {/* Add field */}
      <div style={{ padding: "5px 10px", borderTop: `1px solid ${PARAMS_NODE_COLOR}22` }}>
        <button onClick={addField}
          style={{ width: "100%", padding: "3px 0", borderRadius: 3, border: `1px dashed ${PARAMS_NODE_COLOR}44`,
            background: "none", color: S.textDim, cursor: "pointer", fontSize: 10,
            display: "flex", alignItems: "center", justifyContent: "center", gap: 4 }}
          onMouseEnter={(e) => { e.currentTarget.style.borderColor = PARAMS_NODE_COLOR; e.currentTarget.style.color = PARAMS_NODE_COLOR; }}
          onMouseLeave={(e) => { e.currentTarget.style.borderColor = `${PARAMS_NODE_COLOR}44`; e.currentTarget.style.color = S.textDim; }}>
          <Plus size={10} /> Parameter hinzufügen
        </button>
      </div>

      {/* Output dots */}
      {fields.length > 0 && (
        <div style={{ borderTop: `1px solid ${PARAMS_NODE_COLOR}22`, backgroundColor: `${PARAMS_NODE_COLOR}06` }}>
          <div style={{ maxHeight: 160, overflowY: "auto", scrollbarWidth: "thin" }}>
            {fields.map((f, i) => (
              <div key={f.name || i}
                style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "5px 10px", borderTop: i > 0 ? `1px solid ${PARAMS_NODE_COLOR}11` : "none" }}>
                <span style={{ fontSize: 10, fontFamily: "monospace", color: PARAMS_NODE_COLOR, opacity: 0.9, flex: 1,
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {f.name || `param_${i + 1}`}
                </span>
                <div
                  ref={(el) => { if (outputRefs) outputRefs.current[`${node.id}_${i}`] = { current: el }; }}
                  data-params-output={node.id}
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.setData("source_dataset_id", `__params__${node.id}`);
                    e.dataTransfer.setData("source_field", f.name || `param_${i + 1}`);
                    e.stopPropagation();
                  }}
                  style={{ width: 9, height: 9, borderRadius: "50%", backgroundColor: PARAMS_NODE_COLOR,
                    cursor: "grab", flexShrink: 0, boxShadow: `0 0 5px ${PARAMS_NODE_COLOR}88` }}
                  title={`${f.name} auf Zielfeld ziehen`} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export { PARAMS_NODE_COLOR };
export default ParamsNode;
