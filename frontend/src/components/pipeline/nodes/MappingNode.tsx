import { S, NODE_COLORS } from "../constants";
import BaseNode from "./BaseNode";

export default function MappingNode({ node, onRemove, onPositionChange, onUpdate, inputPortRef, inputPortDrop, outputPortRef, mappings, runResult, isActive, onActivate }) {
  const config = node.config || {};
  const set = (k, v) => onUpdate({ ...node, config: { ...config, [k]: v } });

  const iS = { backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 3, color: S.textBright, fontSize: 10, padding: "3px 6px", outline: "none", width: "100%", minWidth: 0 };
  const lS = { fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", display: "block", marginBottom: 3 };
  const color = NODE_COLORS.mapping;

  const selectedMapping = (mappings || []).find(m => m.id === config.mapping_id);

  return (
    <BaseNode node={node} color={color} icon="⚙️" label="Mapping"
      runResult={runResult} isActive={isActive} onActivate={onActivate}
      onRemove={onRemove} onPositionChange={onPositionChange}
      inputPorts={[{ id: "in", label: "Eingang", portRef: inputPortRef, onDrop: inputPortDrop }]}
      outputPorts={[{
        id: "out", label: "Ergebnis",
        portRef: outputPortRef,
        onDragStart: e => {
          e.stopPropagation();
          e.dataTransfer.setData("from_node", node.id);
          e.dataTransfer.setData("from_port", "out");
        }
      }]}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <div>
          <label style={lS}>Mapping</label>
          <select style={iS} value={config.mapping_id || ""} onChange={e => set("mapping_id", parseInt(e.target.value) || null)}>
            <option value="">— Mapping wählen —</option>
            {(mappings || []).map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
        </div>

        {selectedMapping && (
          <div style={{ fontSize: 9, color: S.textDim, padding: "4px 6px", borderRadius: 3, backgroundColor: `${color}10`, border: `1px solid ${color}22` }}>
            ID: {selectedMapping.id} · {selectedMapping.canvas_nodes?.length || 0} Datasets
          </div>
        )}

        <div>
          <label style={lS}>Bei Fehler</label>
          <select style={iS} value={config.on_error || "stop"} onChange={e => set("on_error", e.target.value)}>
            <option value="stop">Pipeline stoppen</option>
            <option value="continue">Weiter (ignorieren)</option>
            <option value="notify">Weiter + Fehler loggen</option>
          </select>
        </div>
      </div>
    </BaseNode>
  );
}
