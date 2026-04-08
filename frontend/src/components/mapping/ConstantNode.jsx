import { useState, useRef, useEffect} from "react";
import { GripVertical, Plus, Type, X, Minimize2 } from "lucide-react";
import { S, CONST_TYPES } from "./constants";
import { MinimizedNode } from "./MinimizedNode";

function ConstantNode({ node, onRemove, onPositionChange, onUpdate, outputRef, onMiniPortsReady}) {
  const miniLeftRef = useRef(null);
  const miniRightRef = useRef(null);
  useEffect(() => {
    if (node.minimized) {
      // Output-Ref auf rechten Port-Dot zeigen lassen
      if (outputRef) outputRef.current = miniRightRef.current;
      if (onMiniPortsReady) onMiniPortsReady(node.id, miniLeftRef.current, miniRightRef.current);
    }
  }, [node.minimized, onMiniPortsReady]);
  const ct = CONST_TYPES.find((t) => t.value === node.const_type) || CONST_TYPES[0];
  const needsValue = node.const_type === "static_text" || node.const_type === "static_number";

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
          type="constant" color="rgba(167,139,250,1)" label="Konstante"
          onExpand={() => onUpdate({ ...node, minimized: false })}
          onMouseDown={handleMouseDown}
          portLeftRef={miniLeftRef} portRightRef={miniRightRef}
          onPortLeftDrop={null} onPortRightDragStart={null}
        />
      </div>
    );
  }

  return (
    <div draggable={false} style={{ position: "absolute", left: node.x, top: node.y, width: 200, zIndex: 10, userSelect: "none", boxShadow: "0 8px 32px rgba(0,0,0,0.5)", borderRadius: 6, overflow: "hidden", border: `1px solid rgba(167,139,250,0.4)`, backgroundColor: S.bgCard }}
      onClick={(e) => e.stopPropagation()}>
      {/* Header */}
      <div onMouseDown={handleMouseDown} draggable={false} style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 10px", cursor: "grab", backgroundColor: "rgba(167,139,250,0.08)", borderBottom: `1px solid rgba(167,139,250,0.2)` }}>
        <GripVertical size={12} style={{ color: S.textDim, flexShrink: 0 }} />
        <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "#a78bfa" }}>Konstante</span>
        <button onClick={(e) => { e.stopPropagation(); onUpdate({ ...node, minimized: true }); }} title="Minimieren"
          style={{ marginLeft: "auto", color: S.textDim, flexShrink: 0, lineHeight: 1 }}
          onMouseEnter={(e) => e.currentTarget.style.color = "#a78bfa"}
          onMouseLeave={(e) => e.currentTarget.style.color = S.textDim}>
          <Minimize2 size={10} />
        </button>
        <button onClick={(e) => { e.stopPropagation(); onRemove(node.id); }}
          style={{ color: S.textDim, flexShrink: 0, lineHeight: 1 }}
          onMouseEnter={(e) => e.currentTarget.style.color = "#e07070"}
          onMouseLeave={(e) => e.currentTarget.style.color = S.textDim}>
          <X size={12} />
        </button>
      </div>

      {/* Type selector */}
      <div style={{ padding: "8px 10px", borderBottom: `1px solid ${S.border}` }}>
        <select value={node.const_type}
          onChange={(e) => onUpdate({ ...node, const_type: e.target.value, const_value: "" })}
          style={{ width: "100%", backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, color: ct.color, fontSize: 11, padding: "4px 8px", fontFamily: "monospace", cursor: "pointer", outline: "none" }}>
          {CONST_TYPES.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
      </div>

      {/* Value input (only for static types) */}
      {needsValue && (
        <div style={{ padding: "6px 10px", borderBottom: `1px solid ${S.border}` }}>
          <input
            value={node.const_value || ""}
            onChange={(e) => onUpdate({ ...node, const_value: e.target.value })}
            placeholder={node.const_type === "static_text" ? "Wert eingeben…" : "0"}
            type={node.const_type === "static_number" ? "number" : "text"}
            style={{ width: "100%", backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, color: S.textBright, fontSize: 11, padding: "5px 8px", fontFamily: "monospace", outline: "none", boxSizing: "border-box" }}
          />
        </div>
      )}

      {/* Output field name */}
      <div style={{ padding: "6px 10px", borderBottom: `1px solid ${S.border}` }}>
        <input
          value={node.output_field || ""}
          onChange={(e) => onUpdate({ ...node, output_field: e.target.value })}
          placeholder="Feldname im Ziel…"
          style={{ width: "100%", backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, color: S.accent, fontSize: 11, padding: "5px 8px", fontFamily: "monospace", outline: "none", boxSizing: "border-box" }}
        />
      </div>

      {/* Output dot + preview */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "7px 10px 8px" }}>
        <span style={{ fontSize: 10, fontFamily: "monospace", color: ct.color, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {ct.preview(node.const_value)}
        </span>
        <span
          ref={(el) => { if (outputRef) outputRef.current = el; }}
          draggable
          onDragStart={(e) => {
            e.stopPropagation();
            e.dataTransfer.setData("source_dataset_id", `__const__${node.id}`);
            e.dataTransfer.setData("source_field", node.output_field || "value");
          }}
          title="Ausgabe ins Ziel ziehen"
          style={{
            display: "inline-block", width: 12, height: 12, borderRadius: "50%",
            backgroundColor: "#a78bfa", border: "2px solid #c4b5fd",
            boxShadow: "0 0 6px rgba(167,139,250,0.6)",
            flexShrink: 0, marginLeft: 8, cursor: "grab",
          }} />
      </div>
    </div>
  );
}

// ─── Context Menu ──────────────────────────────────────────────────────────────

export default ConstantNode;
