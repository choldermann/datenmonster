import { useState, useRef, useEffect} from "react";
import { GripVertical, Layers, X, Plus, Minimize2 } from "lucide-react";
import { S, AGG_COLOR, AGG_FUNCTIONS } from "./constants";
import { MinimizedNode } from "./MinimizedNode";

function AggNode({ node, onRemove, onPositionChange, onUpdate, outputRefs, inputRefs, allSourceFields, nodeRef, onMiniPortsReady}) {
  const internalRef = useRef(null);
  const miniLeftRef = useRef(null);
  const miniRightRef = useRef(null);
  useEffect(() => {
    if (node.minimized) {
      // Output-Ref auf rechten Port-Dot zeigen lassen
      if (outputRefs?.current?.[node.id]) outputRefs.current[node.id].current = miniRightRef.current;
      if (onMiniPortsReady) onMiniPortsReady(node.id, miniLeftRef.current, miniRightRef.current);
    }
  }, [node.minimized, onMiniPortsReady]);
  const ref = nodeRef || internalRef;
  const dragging = useRef(false);
  const offset = useRef({ x: 0, y: 0 });

  const handleMouseDown = (e) => {
    if (e.target.closest("select,input,button,textarea")) return;
    if (e.target.getAttribute("draggable") === "true") return;
    e.preventDefault(); e.stopPropagation();
    dragging.current = true;
    offset.current = { x: e.clientX - node.x, y: e.clientY - node.y };
    const onMove = (ev) => { if (!dragging.current) return; onPositionChange(node.id, ev.clientX - offset.current.x, ev.clientY - offset.current.y); };
    const onUp = () => { dragging.current = false; window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  const fields = node.fields || [];
  const addField = () => onUpdate({ ...node, fields: [...fields, { input_field: "", func: "sum", output_field: "" }] });
  const removeField = (i) => onUpdate({ ...node, fields: fields.filter((_, idx) => idx !== i) });
  const updateField = (i, key, val) => {
    const updated = fields.map((f, idx) => {
      if (idx !== i) return f;
      const next = { ...f, [key]: val };
      if ((key === "input_field" || key === "func") && !f.output_field) {
        const fn = key === "func" ? val : f.func;
        const inf = key === "input_field" ? val : f.input_field;
        next.output_field = inf ? `${fn}_${inf}` : "";
      }
      return next;
    });
    onUpdate({ ...node, fields: updated });
  };

  // Wenn ein Feld per Drop auf den Input-Dot gesetzt wird
  const handleInputDrop = (i, e) => {
    e.preventDefault();
    const srcField = e.dataTransfer.getData("source_field");
    if (srcField) updateField(i, "input_field", srcField);
  };

  const iS = { backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 3, color: S.textBright, fontSize: 10, padding: "2px 4px", outline: "none", flex: 1, minWidth: 0 };
  const DOT = 10;

  if (node.minimized) {
    return (
      <div style={{ position: "absolute", left: node.x, top: node.y, zIndex: 10, overflow: "visible", width: 46, height: 46 }}
        onMouseDown={handleMouseDown}>
        <MinimizedNode
          type="agg" color={AGG_COLOR} label="Aggregation"
          onExpand={() => onUpdate({ ...node, minimized: false })}
          onMouseDown={handleMouseDown}
          portLeftRef={miniLeftRef} portRightRef={miniRightRef}
          onPortLeftDrop={null} onPortRightDragStart={null}
        />
      </div>
    );
  }

  return (
    <div ref={ref} draggable={false}
      onClick={(e) => e.stopPropagation()}
      style={{ position: "absolute", left: node.x, top: node.y, width: 340, zIndex: 10, userSelect: "none", boxShadow: "0 8px 32px rgba(0,0,0,0.5)", borderRadius: 6, overflow: "visible", border: `1px solid ${AGG_COLOR}55`, backgroundColor: S.bgCard }}>

      {/* Header */}
      <div onMouseDown={handleMouseDown} draggable={false}
        style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 10px", cursor: "grab", backgroundColor: `${AGG_COLOR}12`, borderBottom: `1px solid ${AGG_COLOR}33`, borderRadius: "6px 6px 0 0" }}>
        <GripVertical size={12} style={{ color: S.textDim, flexShrink: 0 }} />
        <Layers size={11} style={{ color: AGG_COLOR, flexShrink: 0 }} />
        <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: AGG_COLOR, flex: 1 }}>Aggregation</span>
        <button onClick={() => onUpdate({ ...node, minimized: true })} title="Minimieren" style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0, display: "flex" }}><Minimize2 size={10} /></button>
        <button onClick={() => onRemove(node.id)} style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0, display: "flex" }}><X size={11} /></button>
      </div>

      {/* Body – overflow hidden für sauberes Aussehen, Dots ragen per margin heraus */}
      <div style={{ backgroundColor: S.bgCard, borderRadius: "0 0 6px 6px", border: `1px solid ${AGG_COLOR}33`, borderTop: "none" }}>

      {/* Column headers */}
      {fields.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: `${DOT}px 1fr 72px 1fr 18px ${DOT}px`, gap: 4, padding: "4px 6px 2px", alignItems: "center" }}>
          <div />
          <span style={{ fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em" }}>Eingabe</span>
          <span style={{ fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em" }}>Funktion</span>
          <span style={{ fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em" }}>Ausgabe</span>
          <div /><div />
        </div>
      )}

      {/* Fields */}
      <div style={{ display: "flex", flexDirection: "column", gap: 4, padding: fields.length > 0 ? "2px 6px 8px" : "8px 10px", maxHeight: 300, overflowY: "auto", scrollbarWidth: "thin" }}>
        {fields.length === 0 && (
          <p style={{ fontSize: 10, color: S.textDim, textAlign: "center", padding: "8px 0" }}>Noch keine Felder</p>
        )}
        {fields.map((f, i) => (
          <div key={i} style={{ display: "grid", gridTemplateColumns: `${DOT}px 1fr 72px 1fr 18px ${DOT}px`, gap: 4, alignItems: "center" }}>

            {/* Input Dot – links, accept drop */}
            <div
              ref={el => { if (inputRefs?.current) inputRefs.current[`${node.id}_${i}`] = { current: el }; }}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => handleInputDrop(i, e)}
              style={{ width: DOT, height: DOT, borderRadius: "50%", backgroundColor: f.input_field ? AGG_COLOR : S.border, cursor: "crosshair", flexShrink: 0, boxShadow: f.input_field ? `0 0 5px ${AGG_COLOR}88` : "none", border: `1px solid ${AGG_COLOR}`, transition: "background 0.15s" }}
              title="Quellfeld hierher ziehen"
            />

            {/* Input field select */}
            <select style={iS} value={f.input_field} onChange={(e) => updateField(i, "input_field", e.target.value)}>
              <option value="">— Feld —</option>
              {allSourceFields.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>

            {/* Function */}
            <select style={{ ...iS, color: AGG_COLOR, fontWeight: 700, flex: "none", width: "100%" }} value={f.func} onChange={(e) => updateField(i, "func", e.target.value)}>
              {AGG_FUNCTIONS.map((fn) => <option key={fn.v} value={fn.v}>{fn.l}</option>)}
            </select>

            {/* Output field name */}
            <input style={iS} value={f.output_field} onChange={(e) => updateField(i, "output_field", e.target.value)} placeholder="Ausgabefeld" />

            {/* Remove */}
            <button onClick={() => removeField(i)} style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0, display: "flex", alignItems: "center", justifyContent: "center" }}><X size={10} /></button>

            {/* Output Dot – rechts, draggable */}
            <div
              ref={el => { if (outputRefs?.current) outputRefs.current[`${node.id}_${i}`] = { current: el }; }}
              draggable={!!f.output_field}
              onDragStart={(e) => {
                if (!f.output_field) { e.preventDefault(); return; }
                e.stopPropagation();
                e.dataTransfer.setData("source_dataset_id", `__agg__${node.id}`);
                e.dataTransfer.setData("source_field", f.output_field);
              }}
              style={{ width: DOT, height: DOT, borderRadius: "50%", backgroundColor: f.output_field ? AGG_COLOR : S.border, cursor: f.output_field ? "grab" : "default", flexShrink: 0, boxShadow: f.output_field ? `0 0 5px ${AGG_COLOR}88` : "none", border: `1px solid ${AGG_COLOR}`, transition: "background 0.15s" }}
              title={f.output_field ? `${f.output_field} auf Zielfeld ziehen` : "Ausgabefeld eingeben"}
            />
          </div>
        ))}
      </div>

      {/* Add button */}
      <div style={{ padding: "0 6px 8px" }}>
        <button onClick={addField}
          style={{ width: "100%", padding: "4px", borderRadius: 3, fontSize: 10, fontWeight: 600, cursor: "pointer", backgroundColor: `${AGG_COLOR}12`, border: `1px dashed ${AGG_COLOR}55`, color: AGG_COLOR, display: "flex", alignItems: "center", justifyContent: "center", gap: 4 }}>
          <Plus size={10} /> Feld hinzufügen
        </button>
      </div>
      </div>{/* /Body */}
    </div>
  );
}


export default AggNode;
