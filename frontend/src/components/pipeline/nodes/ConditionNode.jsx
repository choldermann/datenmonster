import { S, NODE_COLORS } from "../constants";
import BaseNode from "./BaseNode";

const OPERATORS = [
  { v: "gt",  l: ">" },
  { v: "gte", l: ">=" },
  { v: "lt",  l: "<" },
  { v: "lte", l: "<=" },
  { v: "eq",  l: "=" },
  { v: "neq", l: "≠" },
];

export default function ConditionNode({ node, onRemove, onPositionChange, onUpdate,
  inputPortRef, inputPortDrop, outputPortRefs, runResult }) {

  const config = node.config || {};
  const set = (k, v) => onUpdate({ ...node, config: { ...config, [k]: v } });
  const color = NODE_COLORS.condition;

  const iS = { backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 3, color: S.textBright, fontSize: 10, padding: "2px 5px", outline: "none" };
  const lS = { fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", display: "block", marginBottom: 3 };

  const outputPorts = [
    { id: "yes", label: "✓ Ja",   portRef: outputPortRefs?.[0],
      onDragStart: e => { e.stopPropagation(); e.dataTransfer.setData("from_node", node.id); e.dataTransfer.setData("from_port", "yes"); } },
    { id: "no",  label: "✗ Nein", portRef: outputPortRefs?.[1],
      onDragStart: e => { e.stopPropagation(); e.dataTransfer.setData("from_node", node.id); e.dataTransfer.setData("from_port", "no"); } },
  ];

  return (
    <BaseNode node={node} color={color} icon="❓" label="Bedingung"
      onRemove={onRemove} onPositionChange={onPositionChange} width={240}
      inputPorts={[{ id: "in", label: "Eingang", portRef: inputPortRef, onDrop: inputPortDrop }]}
      outputPorts={outputPorts}
      runResult={runResult}>

      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <label style={lS}>Zeilen aus Vorgänger-Node</label>
        <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
          <select style={{ ...iS, flex: "0 0 52px" }}
            value={config.operator || "gt"}
            onChange={e => set("operator", e.target.value)}>
            {OPERATORS.map(op => <option key={op.v} value={op.v}>{op.l}</option>)}
          </select>
          <input style={{ ...iS, flex: 1 }} type="number"
            value={config.value ?? 0}
            onChange={e => set("value", e.target.value)}
            placeholder="0" />
        </div>

        <div style={{ fontSize: 9, color: S.textDim, padding: "2px 6px", borderRadius: 3,
          backgroundColor: "rgba(255,255,255,0.04)", border: `1px solid ${S.border}` }}>
          Wenn Zeilen{" "}
          <span style={{ color, fontWeight: 700 }}>
            {OPERATORS.find(o => o.v === (config.operator || "gt"))?.l || ">"} {config.value ?? 0}
          </span>
          {" "}→ JA-Pfad
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 12, marginTop: 2 }}>
          <span style={{ fontSize: 8, color: "#6ee7b7", fontWeight: 700 }}>✓ JA →</span>
          <span style={{ fontSize: 8, color: "#e07070", fontWeight: 700 }}>✗ NEIN →</span>
        </div>
      </div>
    </BaseNode>
  );
}
