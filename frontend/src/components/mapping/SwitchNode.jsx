import { useState, useRef, useEffect} from "react";
import { GripVertical, GitBranch, X, Plus, Minimize2 } from "lucide-react";
import { S } from "./constants";
import { MinimizedNode } from "./MinimizedNode";

export const SWITCH_COLOR = "#e879f9";

const SWITCH_CONDITIONS = [
  { v: "has_rows",     l: "Hat Zeilen (> 0)" },
  { v: "no_rows",      l: "Keine Zeilen (= 0)" },
  { v: "row_count_gt", l: "Zeilenzahl > N" },
  { v: "row_count_lt", l: "Zeilenzahl < N" },
  { v: "always",       l: "Immer (Fallback)" },
];

function SwitchNode({ node, onRemove, onPositionChange, onUpdate, outputRefs, allDatasets, onMiniPortsReady}) {
  const dragging = useRef(false);
  const miniLeftRef = useRef(null);
  const miniRightRef = useRef(null);
  useEffect(() => {
    if (node.minimized) {
      // Output-Ref auf rechten Port-Dot zeigen lassen
      if (outputRefs?.current?.[node.id]) outputRefs.current[node.id].current = miniRightRef.current;
      if (onMiniPortsReady) onMiniPortsReady(node.id, miniLeftRef.current, miniRightRef.current);
    }
  }, [node.minimized, onMiniPortsReady]);
  const offset = useRef({ x: 0, y: 0 });

  const handleMouseDown = (e) => {
    if (e.target.closest("select,input,button,textarea")) return;
    e.preventDefault(); e.stopPropagation();
    dragging.current = true;
    offset.current = { x: e.clientX - node.x, y: e.clientY - node.y };
    const onMove = (ev) => { if (!dragging.current) return; onPositionChange(node.id, ev.clientX - offset.current.x, ev.clientY - offset.current.y); };
    const onUp = () => { dragging.current = false; window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  const branches = node.branches || [
    { id: "b1", condition: "has_rows", dataset_id: null, source_dataset_id: null, threshold: 0, label: "Wenn Daten vorhanden" },
    { id: "b2", condition: "always",   dataset_id: null, source_dataset_id: null, threshold: 0, label: "Sonst (Fallback)" },
  ];

  const updateBranch = (i, key, val) => onUpdate({ ...node, branches: branches.map((b, idx) => idx === i ? { ...b, [key]: val } : b) });
  const addBranch = () => {
    const id = "b" + Math.random().toString(36).slice(2, 6);
    onUpdate({ ...node, branches: [...branches, { id, condition: "has_rows", dataset_id: null, source_dataset_id: null, threshold: 0, label: "Zweig " + (branches.length + 1) }] });
  };
  const removeBranch = (i) => { if (branches.length > 1) onUpdate({ ...node, branches: branches.filter((_, idx) => idx !== i) }); };
  const set = (k, v) => onUpdate({ ...node, [k]: v });

  const iS = { backgroundColor: S.bgEl, border: "1px solid " + S.border, borderRadius: 3, color: S.textBright, fontSize: 10, padding: "2px 5px", outline: "none", width: "100%", minWidth: 0 };
  const DOT = 10;

  if (node.minimized) {
    return (
      <div style={{ position: "absolute", left: node.x, top: node.y, zIndex: 10, overflow: "visible", width: 44, height: 44 }}
        onMouseDown={handleMouseDown}>
        <MinimizedNode
          type="switch" color={SWITCH_COLOR} label="Switch"
          onExpand={() => onUpdate({ ...node, minimized: false })}
          onMouseDown={handleMouseDown}
          portLeftRef={miniLeftRef} portRightRef={miniRightRef}
          onPortLeftDrop={null} onPortRightDragStart={null}
        />
      </div>
    );
  }

  return (
    <div draggable={false} onClick={e => e.stopPropagation()}
      style={{ position: "absolute", left: node.x, top: node.y, width: 270, zIndex: 10, userSelect: "none", boxShadow: "0 8px 32px rgba(0,0,0,0.5)", borderRadius: 6, border: "1px solid " + SWITCH_COLOR + "55", backgroundColor: S.bgCard, overflow: "hidden" }}>

      {/* Header */}
      <div onMouseDown={handleMouseDown}
        style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 8px", cursor: "grab", backgroundColor: SWITCH_COLOR + "12", borderBottom: "1px solid " + SWITCH_COLOR + "33" }}>
        <GripVertical size={11} style={{ color: S.textDim, flexShrink: 0 }} />
        <GitBranch size={10} style={{ color: SWITCH_COLOR, flexShrink: 0 }} />
        <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: SWITCH_COLOR, flex: 1 }}>Switch Node</span>
        <button onClick={() => onUpdate({ ...node, minimized: true })} title="Minimieren" style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0 }}><Minimize2 size={10} /></button>
        <button onClick={() => onRemove(node.id)} style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0 }}><X size={10} /></button>
      </div>

      <div style={{ padding: "6px 8px", display: "flex", flexDirection: "column", gap: 6 }}>

        {/* Ausgabefeld */}
        <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
          <input style={{ ...iS, flex: 1 }} value={node.output_field || ""} onChange={e => set("output_field", e.target.value)} placeholder="Ausgabefeld" />
          <div
            ref={el => { if (outputRefs?.current) { if (!outputRefs.current[node.id]) outputRefs.current[node.id] = { current: null }; outputRefs.current[node.id].current = el; } }}
            draggable={!!node.output_field}
            onDragStart={e => {
              if (!node.output_field) { e.preventDefault(); return; }
              e.stopPropagation();
              e.dataTransfer.setData("source_dataset_id", "__switch__" + node.id);
              e.dataTransfer.setData("source_field", node.output_field);
            }}
            style={{ width: DOT, height: DOT, borderRadius: "50%", backgroundColor: node.output_field ? SWITCH_COLOR : S.border, cursor: node.output_field ? "grab" : "default", border: "2px solid " + SWITCH_COLOR, flexShrink: 0 }}
          />
        </div>

        <p style={{ fontSize: 8, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", margin: 0 }}>Verzweigungen · erste zutreffende gewinnt</p>

        {/* Zweige */}
        {branches.map((b, i) => (
          <div key={b.id} style={{ padding: "5px 6px", borderRadius: 4, border: "1px solid " + SWITCH_COLOR + "33", backgroundColor: SWITCH_COLOR + "05", display: "flex", flexDirection: "column", gap: 4 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <span style={{ fontSize: 9, color: SWITCH_COLOR, fontWeight: 700, flexShrink: 0 }}>#{i+1}</span>
              <input style={{ ...iS, fontSize: 9, flex: 1 }} value={b.label} onChange={e => updateBranch(i, "label", e.target.value)} placeholder="Label" />
              {branches.length > 1 && <button onClick={() => removeBranch(i)} style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0, flexShrink: 0 }}><X size={9} /></button>}
            </div>

            <div style={{ display: "flex", gap: 3 }}>
              <select style={{ ...iS, flex: 1 }} value={b.condition} onChange={e => updateBranch(i, "condition", e.target.value)}>
                {SWITCH_CONDITIONS.map(c => <option key={c.v} value={c.v}>{c.l}</option>)}
              </select>
              {(b.condition === "row_count_gt" || b.condition === "row_count_lt") && (
                <input style={{ ...iS, width: 40, flex: "0 0 40px" }} type="number" value={b.threshold || 0} onChange={e => updateBranch(i, "threshold", parseInt(e.target.value) || 0)} />
              )}
            </div>

            {b.condition !== "always" && (
              <select style={iS} value={b.dataset_id || ""} onChange={e => updateBranch(i, "dataset_id", parseInt(e.target.value) || null)}>
                <option value="">— Prüf-Dataset —</option>
                {(allDatasets || []).map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
            )}

            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <span style={{ fontSize: 9, color: S.textDim, flexShrink: 0 }}>→</span>
              <select style={{ ...iS, flex: 1 }} value={b.source_dataset_id || ""} onChange={e => updateBranch(i, "source_dataset_id", parseInt(e.target.value) || null)}>
                <option value="">— Ausgabe-Dataset —</option>
                {(allDatasets || []).map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
            </div>
          </div>
        ))}

        <button onClick={addBranch}
          style={{ padding: "3px", borderRadius: 3, fontSize: 9, fontWeight: 600, cursor: "pointer", backgroundColor: SWITCH_COLOR + "10", border: "1px dashed " + SWITCH_COLOR + "44", color: SWITCH_COLOR, display: "flex", alignItems: "center", justifyContent: "center", gap: 3 }}>
          <Plus size={9} /> Zweig hinzufügen
        </button>

        <p style={{ fontSize: 8, color: S.textDim, padding: "3px 6px", borderRadius: 3, backgroundColor: SWITCH_COLOR + "08", border: "1px solid " + SWITCH_COLOR + "22", margin: 0 }}>
          💡 Erste zutreffende Bedingung gewinnt. Ausgabe-Dataset wird als Quelle verwendet.
        </p>
      </div>
    </div>
  );
}

export default SwitchNode;
