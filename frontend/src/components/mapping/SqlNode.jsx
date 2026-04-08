import { useState, useRef, useEffect} from "react";
import { ChevronDown, ChevronRight, Database, GripVertical, Plus, X, Minimize2 } from "lucide-react";
import { S, SQL_NODE_COLOR } from "./constants";
import { MinimizedNode } from "./MinimizedNode";

function SqlNode({ node, onRemove, onPositionChange, onUpdate, outputRef, dbConnections, onMiniPortsReady}) {
  const [expanded, setExpanded] = useState(true);
  const textareaRef = useRef(null);
  const miniLeftRef = useRef(null);
  const miniRightRef = useRef(null);
  useEffect(() => {
    if (node.minimized) {
      // Output-Ref auf rechten Port-Dot zeigen lassen
      if (outputRef) outputRef.current = miniRightRef.current;
      if (onMiniPortsReady) onMiniPortsReady(node.id, miniLeftRef.current, miniRightRef.current);
    }
  }, [node.minimized, onMiniPortsReady]);

  const handleMouseDown = (e) => {
    if (e.target.closest("button") || e.target.closest("select") || e.target.closest("textarea") || e.target.closest("input")) return;
    e.preventDefault(); e.stopPropagation();
    const startX = e.clientX - node.x;
    const startY = e.clientY - node.y;
    const onMove = (ev) => onPositionChange(node.id, ev.clientX - startX, ev.clientY - startY);
    const onUp = () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  const set = (k, v) => onUpdate({ ...node, [k]: v });
  const mode = node.mode || "scalar";

  if (node.minimized) {
    return (
      <div style={{ position: "absolute", left: node.x, top: node.y, zIndex: 10, overflow: "visible", width: 44, height: 44 }}
        onMouseDown={handleMouseDown}>
        <MinimizedNode
          type="sql" color={SQL_NODE_COLOR} label="SQL"
          onExpand={() => onUpdate({ ...node, minimized: false })}
          onMouseDown={handleMouseDown}
          portLeftRef={miniLeftRef} portRightRef={miniRightRef}
          onPortLeftDrop={null} onPortRightDragStart={null}
        />
      </div>
    );
  }

  return (
    <div draggable={false} style={{ position: "absolute", left: node.x, top: node.y, width: 260, zIndex: 10, userSelect: "none", boxShadow: "0 8px 32px rgba(0,0,0,0.5)", borderRadius: 6, overflow: "hidden", border: `1px solid ${SQL_NODE_COLOR}55`, backgroundColor: S.bgCard }}
      onClick={(e) => e.stopPropagation()}>

      {/* Header */}
      <div onMouseDown={handleMouseDown} draggable={false}
        style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 10px", cursor: "grab", backgroundColor: `${SQL_NODE_COLOR}12`, borderBottom: `1px solid ${SQL_NODE_COLOR}33` }}>
        <GripVertical size={12} style={{ color: S.textDim, flexShrink: 0 }} />
        <Database size={11} style={{ color: SQL_NODE_COLOR, flexShrink: 0 }} />
        <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: SQL_NODE_COLOR, flex: 1 }}>SQL Node</span>
        <button onClick={() => setExpanded((v) => !v)}
          style={{ color: S.textDim, lineHeight: 1, background: "none", border: "none", cursor: "pointer", padding: 2 }}>
          {expanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        </button>
        <button onClick={() => onUpdate({ ...node, minimized: true })} title="Minimieren" style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0, display: "flex" }}><Minimize2 size={10} /></button>
        <button onClick={(e) => { e.stopPropagation(); onRemove(node.id); }}
          style={{ color: S.textDim, flexShrink: 0, lineHeight: 1, background: "none", border: "none", cursor: "pointer" }}
          onMouseEnter={(e) => e.currentTarget.style.color = "#e07070"}
          onMouseLeave={(e) => e.currentTarget.style.color = S.textDim}>
          <X size={12} />
        </button>
      </div>

      {expanded && (
        <div style={{ padding: "8px 10px", display: "flex", flexDirection: "column", gap: 7 }}>
          {/* Verbindung */}
          <div>
            <label style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.08em", color: S.textDim, display: "block", marginBottom: 3 }}>Verbindung</label>
            <select value={node.connection_id || ""}
              onChange={(e) => set("connection_id", parseInt(e.target.value) || null)}
              style={{ width: "100%", backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, color: node.connection_id ? SQL_NODE_COLOR : S.textDim, fontSize: 11, padding: "4px 8px", outline: "none", cursor: "pointer" }}>
              <option value="">– Verbindung wählen –</option>
              {dbConnections.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.db_type})</option>)}
            </select>
          </div>

          {/* Modus */}
          <div>
            <label style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.08em", color: S.textDim, display: "block", marginBottom: 3 }}>Modus</label>
            <div style={{ display: "flex", gap: 4 }}>
              {[{ v: "scalar", l: "Scalar", hint: "1 Wert pro Zeile" }, { v: "column", l: "Spalte", hint: "Alle Zeilen einmalig" }].map((m) => (
                <button key={m.v} onClick={() => set("mode", m.v)} title={m.hint}
                  style={{ flex: 1, padding: "4px 6px", borderRadius: 4, fontSize: 10, fontWeight: 600, cursor: "pointer",
                    backgroundColor: mode === m.v ? `${SQL_NODE_COLOR}22` : S.bgEl,
                    border: `1px solid ${mode === m.v ? SQL_NODE_COLOR : S.border}`,
                    color: mode === m.v ? SQL_NODE_COLOR : S.textDim }}>
                  {m.l}
                </button>
              ))}
            </div>
            <p style={{ fontSize: 9, color: S.textDim, marginTop: 3, lineHeight: 1.3 }}>
              {mode === "scalar" ? "SQL wird pro Zeile ausgeführt · {Feldname} als Parameter" : "SQL einmalig ausgeführt · Ergebnis per Zeilenindex gemappt"}
            </p>
          </div>

          {/* SQL */}
          <div>
            <label style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.08em", color: S.textDim, display: "block", marginBottom: 3 }}>SQL</label>
            <textarea
              ref={textareaRef}
              value={node.sql || ""}
              onChange={(e) => set("sql", e.target.value)}
              onClick={(e) => e.stopPropagation()}
              placeholder={mode === "scalar"
                ? "SELECT name FROM kunden WHERE id = {Kunden.id}"
                : "SELECT lookup_value FROM ref_table ORDER BY sort_nr"}
              rows={4}
              style={{ width: "100%", backgroundColor: S.bgMain, border: `1px solid ${SQL_NODE_COLOR}44`, borderRadius: 4, color: S.textBright, fontSize: 11, fontFamily: "monospace", padding: "5px 7px", outline: "none", resize: "vertical", boxSizing: "border-box", lineHeight: 1.5 }}
            />
          </div>

          {/* Output-Feldname */}
          <div>
            <label style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.08em", color: S.textDim, display: "block", marginBottom: 3 }}>Output-Feldname</label>
            <input value={node.output_field || ""}
              onChange={(e) => set("output_field", e.target.value)}
              onClick={(e) => e.stopPropagation()}
              placeholder="sql_ergebnis"
              style={{ width: "100%", backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, color: SQL_NODE_COLOR, fontSize: 11, fontFamily: "monospace", padding: "4px 8px", outline: "none", boxSizing: "border-box" }}
            />
          </div>
        </div>
      )}

      {/* Output dot */}
      <div style={{ padding: "6px 10px", borderTop: `1px solid ${SQL_NODE_COLOR}22`, display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 6, backgroundColor: `${SQL_NODE_COLOR}06` }}>
        <span style={{ fontSize: 9, fontFamily: "monospace", color: SQL_NODE_COLOR, opacity: 0.8 }}>
          {node.output_field || "–"}
        </span>
        <div ref={(el) => { if (outputRef) outputRef.current = el; }}
          data-sql-output={node.id}
          draggable
          onDragStart={(e) => {
            e.dataTransfer.setData("source_dataset_id", `__sql__${node.id}`);
            e.dataTransfer.setData("source_field", node.output_field || `sql_${node.id}`);
            e.stopPropagation();
          }}
          style={{ width: 10, height: 10, borderRadius: "50%", backgroundColor: SQL_NODE_COLOR, cursor: "grab", flexShrink: 0, boxShadow: `0 0 6px ${SQL_NODE_COLOR}88` }}
          title="Auf Zielfeld ziehen" />
      </div>
    </div>
  );
}
// ─── Aggregation Node ──────────────────────────────────────────────────────────

export default SqlNode;
