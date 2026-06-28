import { useRef, useEffect} from "react";
import { GripVertical, Calculator, X, Plus, Minimize2 } from "lucide-react";
import { S } from "./constants";
import { MinimizedNode } from "./MinimizedNode";

export const CALC_COLOR = "#f97316";

const CALC_FUNCTIONS = [
  { v: "formula",      l: "Formel",                  desc: "Eigene Berechnung aus mehreren Feldern", is_formula: true },
  { v: "cumsum",       l: "Kumulierte Summe",         desc: "Laufende Summe", needs_order: true },
  { v: "rolling_avg",  l: "Gleitender Durchschnitt",  desc: "Durchschnitt über N Zeilen", needs_window: true, needs_order: true },
  { v: "rolling_sum",  l: "Gleitendes Summe",         desc: "Summe über N Zeilen", needs_window: true, needs_order: true },
  { v: "rolling_min",  l: "Gleitendes Minimum",       desc: "Min über N Zeilen", needs_window: true, needs_order: true },
  { v: "rolling_max",  l: "Gleitendes Maximum",       desc: "Max über N Zeilen", needs_window: true, needs_order: true },
  { v: "rank",         l: "Rang",                     desc: "Rang innerhalb der Gruppe", needs_order: true },
  { v: "row_number",   l: "Zeilennummer",              desc: "Fortlaufende Nummer" },
  { v: "pct_change",   l: "Prozentuale Änderung",     desc: "Änderung zur Vorzeile", needs_order: true },
  { v: "diff",         l: "Differenz zur Vorzeile",   desc: "Wert minus Vorwert", needs_order: true },
  { v: "lag",          l: "Vorheriger Wert",           desc: "Wert N Zeilen zurück", needs_window: true, needs_order: true },
  { v: "lead",         l: "Nächster Wert",             desc: "Wert N Zeilen voraus", needs_window: true, needs_order: true },
  { v: "pct_of_total", l: "Anteil am Gesamt",          desc: "Wert / Summe aller Werte in %" },
];

const OPERATORS = [
  { v: "+", l: "+" },
  { v: "-", l: "−" },
  { v: "*", l: "×" },
  { v: "/", l: "÷" },
];

const DOT = 10;

function InputDot({ part, index, inputPortRefs, nodeId, onDrop, onUpdate, onMiniPortsReady}) {
  const iS = { backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 3, color: S.textBright, fontSize: 10, padding: "2px 5px", outline: "none", flex: 1, minWidth: 0 };

  const handleDrop = (e) => {
    e.preventDefault(); e.stopPropagation();
    const field = e.dataTransfer.getData("source_field");
    const dsId = e.dataTransfer.getData("source_dataset_id");
    if (field) onUpdate({ ...part, type: "field", value: field, source_dataset_id: dsId });
  };

  const refKey = `${nodeId}_formula_${index}`;
  if (!inputPortRefs.current[refKey]) inputPortRefs.current[refKey] = { current: null };

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}
      onDragOver={e => { e.preventDefault(); e.stopPropagation(); }}
      onDrop={handleDrop}>
      {/* Input Dot */}
      <div
        ref={el => { inputPortRefs.current[refKey].current = el; }}
        style={{
          width: DOT, height: DOT, borderRadius: "50%",
          backgroundColor: part.value ? CALC_COLOR : "transparent",
          border: `2px solid ${CALC_COLOR}`,
          flexShrink: 0, cursor: "crosshair",
          boxShadow: part.value ? `0 0 4px ${CALC_COLOR}66` : "none",
        }}
        title="Feld hierher ziehen"
      />

      {/* Anzeige: Feldname oder Zahl-Eingabe */}
      {part.type === "number" ? (
        <input style={{ ...iS, width: 70, flex: "0 0 70px" }} type="number"
          value={part.value || ""} onChange={e => onUpdate({ ...part, value: e.target.value })}
          placeholder="0" />
      ) : (
        <div style={{ flex: 1, fontSize: 10, color: part.value ? S.textBright : S.textDim, padding: "2px 6px", borderRadius: 3, backgroundColor: S.bgEl, border: `1px solid ${part.value ? CALC_COLOR + "44" : CALC_COLOR + "22"}`, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", cursor: "copy" }}>
          {part.value || "← Feld hierher ziehen"}
        </div>
      )}

      {/* Typ-Toggle */}
      <button onClick={() => onUpdate({ ...part, type: part.type === "number" ? "field" : "number", value: "" })}
        style={{ padding: "1px 5px", borderRadius: 3, fontSize: 8, cursor: "pointer", border: `1px solid ${S.border}`, backgroundColor: "transparent", color: S.textDim, flexShrink: 0 }}>
        {part.type === "number" ? "Feld" : "123"}
      </button>

      {/* Entfernen */}
      <button onClick={() => onUpdate(null)}
        style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0, flexShrink: 0 }}>
        <X size={9} />
      </button>
    </div>
  );
}

function CalcNode({ node, onRemove, onPositionChange, onUpdate, outputRef, inputPortRefs, allSourceFields, onMiniPortsReady, debugHighlight, debugStats, isActive, onActivate }) {
  const dragging = useRef(false);
  const miniLeftRef = useRef(null);
  const miniRightRef = useRef(null);
  useEffect(() => {
    if (node.minimized) {
      // Output-Ref auf rechten Port-Dot zeigen lassen
      if (outputRef) outputRef.current = miniRightRef.current;
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
  const fn = CALC_FUNCTIONS.find(f => f.v === node.calc_type) || CALC_FUNCTIONS[0];
  const isFormula = (node.calc_type || "formula") === "formula";

  // Formel-Teile
  const formulaParts = node.formula_parts || [
    { type: "field", value: "" },
    { op: "*" },
    { type: "field", value: "" },
  ];

  const updatePart = (i, val) => {
    if (val === null) {
      // Entfernen: Teil + angrenzenden Operator
      const next = [...formulaParts];
      if (i > 0 && next[i-1]?.op !== undefined) next.splice(i-1, 2);
      else if (i < next.length-1 && next[i+1]?.op !== undefined) next.splice(i, 2);
      else next.splice(i, 1);
      set("formula_parts", next.length ? next : [{ type: "field", value: "" }]);
    } else {
      const next = [...formulaParts];
      next[i] = val;
      set("formula_parts", next);
    }
  };

  const addPart = () => {
    set("formula_parts", [...formulaParts, { op: "+" }, { type: "field", value: "" }]);
  };

  // Vorschau
  const formulaPreview = formulaParts.map(p => p.op ? ` ${p.op} ` : (p.value || "?")).join("");

  const ACTIVE_BORDER = "#fce499";
  const activeBorder = isActive && !debugHighlight;

  const iS = { backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 3, color: S.textBright, fontSize: 10, padding: "3px 6px", outline: "none", flex: 1, minWidth: 0 };
  const lS = { fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", display: "block", marginBottom: 3 };

  if (node.minimized) {
    return (
      <div style={{ position: "absolute", left: node.x, top: node.y, zIndex: 10, overflow: "visible", width: 44, height: 44 }}
        onMouseDown={handleMouseDown}>
        <MinimizedNode
          type="calc" color={CALC_COLOR} label="Berechnung"
          onExpand={() => onUpdate({ ...node, minimized: false })}
          onMouseDown={null}
          portLeftRef={miniLeftRef} portRightRef={miniRightRef}
          onPortLeftDrop={null} onPortRightDragStart={null}
        />
      </div>
    );
  }

  return (
    <div draggable={false} onClick={e => { e.stopPropagation(); onActivate?.({ type: "calc", calcType: node.calc_type || "formula", outputField: node.output_field, inputField: node.input_field }); }}
      style={{ position: "absolute", left: node.x, top: node.y, width: 270, zIndex: debugHighlight ? 20 : 10, userSelect: "none", boxShadow: debugHighlight ? `0 0 0 2px ${CALC_COLOR}, 0 0 20px ${CALC_COLOR}55, 0 8px 32px rgba(0,0,0,0.5)` : activeBorder ? `0 0 0 2px ${ACTIVE_BORDER}, 0 8px 32px rgba(0,0,0,0.5)` : "0 8px 32px rgba(0,0,0,0.5)", borderRadius: 6, border: debugHighlight ? `1.5px solid ${CALC_COLOR}cc` : activeBorder ? `1px solid ${ACTIVE_BORDER}` : `1px solid ${CALC_COLOR}55`, backgroundColor: S.bgCard, overflow: "hidden", transition: "box-shadow 0.2s, border-color 0.2s" }}>

      {/* Header */}
      <div onMouseDown={handleMouseDown}
        style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 10px", cursor: "grab", backgroundColor: CALC_COLOR + "12", borderBottom: `1px solid ${CALC_COLOR}33` }}>
        <GripVertical size={12} style={{ color: S.textDim, flexShrink: 0 }} />
        <Calculator size={11} style={{ color: CALC_COLOR, flexShrink: 0 }} />
        <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: CALC_COLOR, flex: 1 }}>Berechnung</span>
        <button onClick={() => onUpdate({ ...node, minimized: true })} title="Minimieren" style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0, display: "flex" }}><Minimize2 size={10} /></button>
        <button onClick={() => onRemove(node.id)} style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0 }}><X size={11} /></button>
      </div>

      <div style={{ padding: "8px 10px", display: "flex", flexDirection: "column", gap: 8 }}>

        {/* Funktion */}
        <div>
          <label style={lS}>Funktion</label>
          <select style={iS} value={node.calc_type || "formula"} onChange={e => set("calc_type", e.target.value)}>
            {CALC_FUNCTIONS.map(f => <option key={f.v} value={f.v}>{f.l}</option>)}
          </select>
          <p style={{ fontSize: 9, color: S.textDim, marginTop: 3 }}>{fn.desc}</p>
        </div>

        {/* ── FORMEL-MODUS ── */}
        {isFormula && (
          <div>
            <label style={lS}>Felder verbinden · Operatoren wählen</label>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              {formulaParts.map((part, i) => {
                if (part.op !== undefined) {
                  return (
                    <div key={i} style={{ display: "flex", justifyContent: "center", gap: 4, padding: "2px 0" }}>
                      {OPERATORS.map(op => (
                        <button key={op.v} onClick={() => updatePart(i, { op: op.v })}
                          style={{ padding: "3px 10px", borderRadius: 4, fontSize: 13, fontWeight: 700, cursor: "pointer", border: `1px solid ${part.op === op.v ? CALC_COLOR : S.border}`, backgroundColor: part.op === op.v ? CALC_COLOR + "25" : "transparent", color: part.op === op.v ? CALC_COLOR : S.textDim }}>
                          {op.l}
                        </button>
                      ))}
                    </div>
                  );
                }
                return (
                  <InputDot key={i} part={part} index={i}
                    inputPortRefs={inputPortRefs || { current: {} }}
                    nodeId={node.id}
                    onDrop={() => {}}
                    onUpdate={v => updatePart(i, v)} />
                );
              })}
            </div>

            <button onClick={addPart}
              style={{ width: "100%", padding: "3px", borderRadius: 3, fontSize: 9, fontWeight: 600, cursor: "pointer", backgroundColor: CALC_COLOR + "10", border: `1px dashed ${CALC_COLOR}44`, color: CALC_COLOR, display: "flex", alignItems: "center", justifyContent: "center", gap: 3, marginTop: 6 }}>
              <Plus size={9} /> Feld hinzufügen
            </button>

            <div style={{ marginTop: 6, padding: "4px 8px", borderRadius: 3, backgroundColor: CALC_COLOR + "08", border: `1px solid ${CALC_COLOR}22`, fontFamily: "monospace", fontSize: 10, color: CALC_COLOR }}>
              = {formulaPreview}
            </div>
          </div>
        )}

        {/* ── STANDARD-MODUS ── */}
        {!isFormula && (
          <>
            {node.calc_type !== "row_number" && (
              <div>
                <label style={lS}>Eingabefeld</label>
                <select style={iS} value={node.input_field || ""} onChange={e => set("input_field", e.target.value)}>
                  <option value="">— Feld wählen —</option>
                  {allSourceFields.map(f => <option key={f} value={f}>{f}</option>)}
                </select>
              </div>
            )}
            {fn.needs_order && (
              <div>
                <label style={lS}>Sortieren nach <span style={{ fontWeight: 400 }}>· optional</span></label>
                <div style={{ display: "flex", gap: 4 }}>
                  <select style={iS} value={node.order_field || ""} onChange={e => set("order_field", e.target.value)}>
                    <option value="">— Keine Sortierung —</option>
                    {allSourceFields.map(f => <option key={f} value={f}>{f}</option>)}
                  </select>
                  <button onClick={() => set("order_dir", node.order_dir === "desc" ? "asc" : "desc")}
                    style={{ padding: "3px 8px", borderRadius: 3, fontSize: 10, fontWeight: 700, cursor: "pointer", border: `1px solid ${S.border}`, backgroundColor: "transparent", color: S.textDim, flexShrink: 0 }}>
                    {node.order_dir === "desc" ? "↓" : "↑"}
                  </button>
                </div>
              </div>
            )}
            <div>
              <label style={lS}>Gruppieren nach <span style={{ fontWeight: 400 }}>· optional</span></label>
              <select style={iS} value={node.group_field || ""} onChange={e => set("group_field", e.target.value)}>
                <option value="">— Keine Gruppierung —</option>
                {allSourceFields.map(f => <option key={f} value={f}>{f}</option>)}
              </select>
            </div>
            {fn.needs_window && (
              <div>
                <label style={lS}>Fenstergröße (Zeilen)</label>
                <input style={iS} type="number" min={1} max={999} value={node.window_size || 3}
                  onChange={e => set("window_size", parseInt(e.target.value) || 3)} />
              </div>
            )}
          </>
        )}

        {/* Ausgabefeld */}
        <div style={{ borderTop: `1px solid ${S.border}`, paddingTop: 8 }}>
          <label style={lS}>Ausgabefeld</label>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <input style={iS} value={node.output_field || ""} onChange={e => set("output_field", e.target.value)}
              placeholder={isFormula ? "z.B. Gesamtbetrag" : "z.B. kum_umsatz"} />
            <div
              ref={el => { if (outputRef && el) outputRef.current = el; }}
              draggable={!!node.output_field}
              onDragStart={e => {
                if (!node.output_field) { e.preventDefault(); return; }
                e.stopPropagation();
                e.dataTransfer.setData("source_dataset_id", "__calc__" + node.id);
                e.dataTransfer.setData("source_field", node.output_field);
              }}
              style={{ width: DOT, height: DOT, borderRadius: "50%", backgroundColor: node.output_field ? CALC_COLOR : S.border, cursor: node.output_field ? "grab" : "default", border: `2px solid ${CALC_COLOR}`, flexShrink: 0 }}
              title={node.output_field ? node.output_field + " auf Zielfeld ziehen" : "Ausgabename eingeben"}
            />
          </div>
        </div>
        {debugStats && (
          <div style={{ fontSize: 9, color: "#94a3b8", display: "flex", gap: 8, padding: "3px 8px 5px", borderTop: `1px solid ${CALC_COLOR}22` }}>
            <span>↓ {(debugStats.rows_out ?? "–").toLocaleString()} Zeilen</span>
            {debugStats.errors > 0 && <span style={{ color: "#f87171" }}>⚠ {debugStats.errors} Fehler</span>}
          </div>
        )}
      </div>
    </div>
  );
}

export default CalcNode;
