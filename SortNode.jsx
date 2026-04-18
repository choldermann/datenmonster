import { useRef, useState } from "react";
import { X, GripVertical, ArrowUpDown, Plus, Trash2, ChevronUp, ChevronDown } from "lucide-react";
import { S } from "./constants";

export const SORT_COLOR = "#a78bfa";

export default function SortNode({ node, allSourceFields, onUpdate, onRemove, onPositionChange }) {
  const dragRef = useRef(null);
  const [dragging, setDragging] = useState(false);

  const fields = node.sort_fields || [{ field: "", dir: "asc" }];

  const updateFields = (newFields) => {
    onUpdate({ ...node, sort_fields: newFields });
  };

  const addField = () => {
    updateFields([...fields, { field: "", dir: "asc" }]);
  };

  const removeField = (i) => {
    updateFields(fields.filter((_, idx) => idx !== i));
  };

  const setField = (i, key, val) => {
    updateFields(fields.map((f, idx) => idx === i ? { ...f, [key]: val } : f));
  };

  // Drag
  const onMouseDown = (e) => {
    if (e.target.closest("select,input,button")) return;
    e.preventDefault();
    const startX = e.clientX - node.x;
    const startY = e.clientY - node.y;
    setDragging(true);
    const onMove = (ev) => onPositionChange(node.id, ev.clientX - startX, ev.clientY - startY);
    const onUp = () => { setDragging(false); window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  const iS = { backgroundColor: S.bgMain, border: `1px solid ${S.border}`, color: S.textBright, borderRadius: 4, padding: "4px 8px", fontSize: 11, outline: "none" };

  return (
    <div ref={dragRef} onMouseDown={onMouseDown}
      style={{
        position: "absolute", left: node.x, top: node.y, width: 280, zIndex: 10,
        backgroundColor: S.bgCard, border: `1.5px solid ${SORT_COLOR}55`,
        borderRadius: 8, boxShadow: dragging ? "0 8px 32px rgba(0,0,0,0.5)" : "0 4px 16px rgba(0,0,0,0.3)",
        cursor: dragging ? "grabbing" : "grab", userSelect: "none",
      }}>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 10px", borderBottom: `1px solid ${S.border}` }}>
        <GripVertical size={12} style={{ color: S.textDim, flexShrink: 0 }} />
        <ArrowUpDown size={13} style={{ color: SORT_COLOR, flexShrink: 0 }} />
        <span style={{ fontSize: 12, fontWeight: 700, color: SORT_COLOR, flex: 1 }}>Sortierung</span>
        <button onClick={() => onRemove(node.id)} style={{ color: S.textDim, background: "none", border: "none", cursor: "pointer", padding: 2 }}
          onMouseEnter={e => e.currentTarget.style.color = "#e07070"}
          onMouseLeave={e => e.currentTarget.style.color = S.textDim}>
          <X size={13} />
        </button>
      </div>

      {/* Sort fields */}
      <div style={{ padding: "10px 10px 8px" }}>
        {fields.map((f, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
            <span style={{ fontSize: 10, color: S.textDim, width: 14, textAlign: "center", flexShrink: 0 }}>{i + 1}</span>
            <select value={f.field} onChange={e => setField(i, "field", e.target.value)}
              style={{ ...iS, flex: 1, minWidth: 0 }}>
              <option value="">– Feld –</option>
              {allSourceFields.map(sf => <option key={sf} value={sf}>{sf}</option>)}
            </select>
            <button onClick={() => setField(i, "dir", f.dir === "asc" ? "desc" : "asc")}
              title={f.dir === "asc" ? "Aufsteigend" : "Absteigend"}
              style={{ background: "none", border: `1px solid ${S.border}`, borderRadius: 4, cursor: "pointer", padding: "3px 6px", color: SORT_COLOR, display: "flex", alignItems: "center", gap: 2, fontSize: 10, fontWeight: 700, flexShrink: 0 }}>
              {f.dir === "asc" ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              {f.dir === "asc" ? "ASC" : "DESC"}
            </button>
            {fields.length > 1 && (
              <button onClick={() => removeField(i)} style={{ color: S.textDim, background: "none", border: "none", cursor: "pointer", padding: 2, flexShrink: 0 }}
                onMouseEnter={e => e.currentTarget.style.color = "#e07070"}
                onMouseLeave={e => e.currentTarget.style.color = S.textDim}>
                <Trash2 size={11} />
              </button>
            )}
          </div>
        ))}

        <button onClick={addField} style={{
          width: "100%", display: "flex", alignItems: "center", justifyContent: "center", gap: 4,
          padding: "5px 0", borderRadius: 4, border: `1px dashed ${S.border}`,
          background: "none", color: S.textDim, cursor: "pointer", fontSize: 11,
          marginTop: 2,
        }}
          onMouseEnter={e => { e.currentTarget.style.borderColor = SORT_COLOR; e.currentTarget.style.color = SORT_COLOR; }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = S.border; e.currentTarget.style.color = S.textDim; }}>
          <Plus size={11} /> Sortierfeld hinzufügen
        </button>
      </div>

      {/* Output port */}
      <div style={{ padding: "6px 10px", borderTop: `1px solid ${S.border}`, display: "flex", justifyContent: "flex-end" }}>
        <span style={{ fontSize: 9, color: SORT_COLOR, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>
          SORT · {fields.filter(f => f.field).length} Feld{fields.filter(f => f.field).length !== 1 ? "er" : ""}
        </span>
      </div>
    </div>
  );
}
