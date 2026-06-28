import { useState, useRef, useEffect} from "react";
import { GripVertical, Search, X, Plus, Minimize2 } from "lucide-react";
import { S } from "./constants";
import { MinimizedNode } from "./MinimizedNode";

export const LOOKUP_COLOR = "#34d399"; // emerald

const LOOKUP_ACTIVE_BORDER = "#fce499";

function LookupNode({ node, onRemove, onPositionChange, onUpdate, outputRefs, inputRef, allDatasets, allSourceFields, onMiniPortsReady, isActive, onActivate }) {
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

  const set = (k, v) => onUpdate({ ...node, [k]: v });

  // Lookup-Dataset Spalten
  const lookupDs = allDatasets?.find(d => d.id === node.lookup_dataset_id);
  const lookupCols = lookupDs?.columns || [];

  // Output-Mappings: welche Spalten aus dem Lookup-Dataset ausgegeben werden
  const outputMappings = node.output_mappings || []; // [{lookup_col, output_field}]

  const addOutput = () => onUpdate({ ...node, output_mappings: [...outputMappings, { lookup_col: "", output_field: "" }] });
  const removeOutput = (i) => onUpdate({ ...node, output_mappings: outputMappings.filter((_, idx) => idx !== i) });
  const updateOutput = (i, key, val) => {
    const updated = outputMappings.map((m, idx) => {
      if (idx !== i) return m;
      const next = { ...m, [key]: val };
      if (key === "lookup_col" && !m.output_field) next.output_field = val;
      return next;
    });
    onUpdate({ ...node, output_mappings: updated });
  };

  // Drop auf Input-Dot
  const handleInputDrop = (e) => {
    e.preventDefault(); e.stopPropagation();
    const field = e.dataTransfer.getData("source_field");
    const dsId = e.dataTransfer.getData("source_dataset_id");
    if (field) onUpdate({ ...node, input_field: field, input_source_dataset_id: dsId });
  };

  const iS = { backgroundColor: S.bgEl, border: "1px solid " + S.border, borderRadius: 3, color: S.textBright, fontSize: 10, padding: "3px 6px", outline: "none", flex: 1, minWidth: 0, maxWidth: "100%" };
  const DOT = 10;

  if (node.minimized) {
    return (
      <div style={{ position: "absolute", left: node.x, top: node.y, zIndex: 10, overflow: "visible", width: 54, height: 54 }}
        onMouseDown={handleMouseDown}>
        <MinimizedNode
          type="lookup" color={LOOKUP_COLOR} label="Lookup"
          onExpand={() => onUpdate({ ...node, minimized: false })}
          onMouseDown={handleMouseDown}
          portLeftRef={miniLeftRef} portRightRef={miniRightRef}
          onPortLeftDrop={null} onPortRightDragStart={null}
        />
      </div>
    );
  }

  return (
    <div draggable={false} onClick={e => { e.stopPropagation(); onActivate?.({ type: "lookup", inputField: node.input_field, lookupDatasetId: node.lookup_dataset_id, lookupKeyCol: node.lookup_key_col, outputMappings: (node.output_mappings || []).map(m => m.output_field) }); }}
      style={{ position: "absolute", left: node.x, top: node.y, width: 300, zIndex: 10, userSelect: "none", boxShadow: isActive ? `0 0 0 2px ${LOOKUP_ACTIVE_BORDER}, 0 8px 32px rgba(0,0,0,0.5)` : "0 8px 32px rgba(0,0,0,0.5)", borderRadius: 6, border: isActive ? `1px solid ${LOOKUP_ACTIVE_BORDER}` : "1px solid " + LOOKUP_COLOR + "55", backgroundColor: S.bgCard, overflow: "hidden", transition: "box-shadow 0.15s, border-color 0.15s" }}>

      {/* Header */}
      <div onMouseDown={handleMouseDown}
        style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 10px", cursor: "grab", backgroundColor: LOOKUP_COLOR + "12", borderBottom: "1px solid " + LOOKUP_COLOR + "33", borderRadius: "6px 6px 0 0" }}>
        <GripVertical size={12} style={{ color: S.textDim, flexShrink: 0 }} />
        <Search size={11} style={{ color: LOOKUP_COLOR, flexShrink: 0 }} />
        <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: LOOKUP_COLOR, flex: 1 }}>Lookup Node</span>
        <button onClick={() => onUpdate({ ...node, minimized: true })} title="Minimieren" style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0, display: "flex" }}><Minimize2 size={10} /></button>
        <button onClick={() => onRemove(node.id)} style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0 }}><X size={11} /></button>
      </div>

      <div style={{ padding: "8px 10px", display: "flex", flexDirection: "column", gap: 8 }}>

        {/* Eingabefeld */}
        <div>
          <p style={{ fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>Eingabefeld (Suchwert)</p>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <div
              ref={el => { if (inputRef) inputRef.current = el; }}
              onDragOver={e => { e.preventDefault(); e.stopPropagation(); }}
              onDrop={handleInputDrop}
              style={{ width: 14, height: 14, borderRadius: "50%", backgroundColor: node.input_field ? LOOKUP_COLOR : "transparent", border: "2px solid " + LOOKUP_COLOR, flexShrink: 0, cursor: "crosshair" }}
              title="Quellfeld hierher ziehen"
            />
            <select style={iS} value={node.input_field || ""} onChange={e => set("input_field", e.target.value)}>
              <option value="">— Feld wählen —</option>
              {allSourceFields.map(f => <option key={f} value={f}>{f}</option>)}
            </select>
          </div>
        </div>

        {/* Lookup Dataset */}
        <div>
          <p style={{ fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>Lookup-Dataset</p>
          <select style={{ ...iS, maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis" }} value={node.lookup_dataset_id || ""} onChange={e => onUpdate({ ...node, lookup_dataset_id: parseInt(e.target.value) || null, lookup_key_col: "", output_mappings: [] })}>
            <option value="">— Dataset wählen —</option>
            {(allDatasets || []).map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </div>

        {/* Schlüsselspalte im Lookup-Dataset */}
        {lookupDs && (
          <div>
            <p style={{ fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
              Suche in Spalte <span style={{ color: LOOKUP_COLOR, fontWeight: 400 }}>· wo {node.input_field || "?"} =</span>
            </p>
            <select style={iS} value={node.lookup_key_col || ""} onChange={e => set("lookup_key_col", e.target.value)}>
              <option value="">— Schlüsselspalte wählen —</option>
              {lookupCols.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
        )}

        {/* Nicht gefunden */}
        {lookupDs && (
          <div>
            <p style={{ fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>Wenn nicht gefunden</p>
            <div style={{ display: "flex", gap: 4 }}>
              {[["null", "Leer"], ["skip", "Zeile überspringen"], ["error", "Fehler"]].map(([v, l]) => (
                <button key={v} onClick={() => set("on_missing", v)}
                  style={{ flex: 1, padding: "3px 6px", borderRadius: 3, fontSize: 9, fontWeight: 600, cursor: "pointer", border: "1px solid " + ((node.on_missing || "null") === v ? LOOKUP_COLOR : S.border), backgroundColor: (node.on_missing || "null") === v ? LOOKUP_COLOR + "20" : "transparent", color: (node.on_missing || "null") === v ? LOOKUP_COLOR : S.textDim }}>
                  {l}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Ausgabefelder */}
        {lookupDs && (
          <div>
            <p style={{ fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>Ausgabefelder aus Lookup</p>
            {outputMappings.length === 0 && <p style={{ fontSize: 10, color: S.textDim, fontStyle: "italic" }}>Noch keine Felder</p>}
            {outputMappings.map((m, i) => (
              <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr 1fr " + DOT + "px 18px", gap: 4, alignItems: "center", marginBottom: 4 }}>
                <select style={iS} value={m.lookup_col} onChange={e => updateOutput(i, "lookup_col", e.target.value)}>
                  <option value="">— Spalte —</option>
                  {lookupCols.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
                <input style={iS} value={m.output_field} onChange={e => updateOutput(i, "output_field", e.target.value)} placeholder="Ausgabename" />
                <div
                  ref={el => {
                    if (outputRefs?.current) {
                      if (!outputRefs.current[node.id + "_" + i]) outputRefs.current[node.id + "_" + i] = { current: null };
                      outputRefs.current[node.id + "_" + i].current = el;
                    }
                  }}
                  draggable={!!m.output_field}
                  onDragStart={e => {
                    if (!m.output_field) { e.preventDefault(); return; }
                    e.stopPropagation();
                    e.dataTransfer.setData("source_dataset_id", "__lookup__" + node.id);
                    e.dataTransfer.setData("source_field", m.output_field);
                  }}
                  style={{ width: DOT, height: DOT, borderRadius: "50%", backgroundColor: m.output_field ? LOOKUP_COLOR : S.border, cursor: m.output_field ? "grab" : "default", border: "2px solid " + LOOKUP_COLOR, flexShrink: 0 }}
                  title={m.output_field ? m.output_field + " auf Zielfeld ziehen" : "Ausgabename eingeben"}
                />
                <button onClick={() => removeOutput(i)} style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0 }}><X size={10} /></button>
              </div>
            ))}
            <button onClick={addOutput}
              style={{ width: "100%", padding: "3px", borderRadius: 3, fontSize: 10, fontWeight: 600, cursor: "pointer", backgroundColor: LOOKUP_COLOR + "12", border: "1px dashed " + LOOKUP_COLOR + "55", color: LOOKUP_COLOR, display: "flex", alignItems: "center", justifyContent: "center", gap: 4, marginTop: 2 }}>
              <Plus size={10} /> Feld hinzufügen
            </button>
          </div>
        )}

        <div style={{ fontSize: 9, color: S.textDim, padding: "4px 8px", borderRadius: 4, backgroundColor: LOOKUP_COLOR + "08", border: "1px solid " + LOOKUP_COLOR + "22" }}>
          💡 Lookup-Dataset wird einmalig geladen und gecacht – kein Performance-Problem bei großen Quellen
        </div>
      </div>
    </div>
  );
}

export default LookupNode;
