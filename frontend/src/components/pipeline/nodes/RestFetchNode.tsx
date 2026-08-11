import { S, NODE_COLORS } from "../constants";
import BaseNode from "./BaseNode";

export default function RestFetchNode({
  node, onRemove, onPositionChange, onUpdate,
  inputPortRef, inputPortDrop, outputPortRef,
  restSources, runResult, isActive, onActivate,
}) {
  const config = node.config || {};
  const set = (k, v) => onUpdate({ ...node, config: { ...config, [k]: v } });

  const iS = {
    backgroundColor: S.bgEl, border: `1px solid ${S.border}`,
    borderRadius: 3, color: S.textBright, fontSize: 10,
    padding: "3px 6px", outline: "none", width: "100%", minWidth: 0,
  };
  const lS = {
    fontSize: 9, color: S.textDim, textTransform: "uppercase",
    letterSpacing: "0.06em", display: "block", marginBottom: 3,
  };

  const color = NODE_COLORS.rest_fetch;
  const selectedSrc = (restSources || []).find(s => s.id === config.rest_source_id);

  return (
    <BaseNode
      node={node} color={color} icon="🌐" label="REST Fetch"
      runResult={runResult} isActive={isActive} onActivate={onActivate}
      onRemove={onRemove} onPositionChange={onPositionChange}
      inputPorts={[{ id: "in", label: "Trigger", portRef: inputPortRef, onDrop: inputPortDrop }]}
      outputPorts={[{
        id: "out", label: "Daten",
        portRef: outputPortRef,
        onDragStart: e => {
          e.stopPropagation();
          e.dataTransfer.setData("from_node", node.id);
          e.dataTransfer.setData("from_port", "out");
        },
      }]}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <div>
          <label style={lS}>REST-Quelle</label>
          <select
            style={iS}
            value={config.rest_source_id || ""}
            onChange={e => set("rest_source_id", parseInt(e.target.value) || null)}
          >
            <option value="">— Quelle wählen —</option>
            {(restSources || []).map(s => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </div>

        {selectedSrc && (
          <div style={{
            fontSize: 9, color: S.textDim, padding: "4px 6px",
            borderRadius: 3, backgroundColor: `${color}10`,
            border: `1px solid ${color}22`,
          }}>
            {selectedSrc.method || "GET"} · {selectedSrc.url?.slice(0, 40)}{selectedSrc.url?.length > 40 ? "…" : ""}
            {selectedSrc.data_path ? ` · Pfad: ${selectedSrc.data_path}` : ""}
          </div>
        )}

        {/*
          Für jede Zeile: kommt der Node hinter einem anderen, der Daten
          liefert, wird der Request einmal pro Zeile ausgeführt und {{spalte}}
          jeweils mit deren Werten gefüllt. Ohne das gilt nur die erste Zeile –
          womit "Liste holen, dann Details je Element" nicht ginge.
        */}
        <div>
          <label style={{ display: "flex", alignItems: "flex-start", gap: 5, cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={!!config.for_each}
              onChange={e => onUpdate({
                ...node,
                config: e.target.checked
                  ? { ...config, for_each: true, for_each_max: config.for_each_max || 100 }
                  : { ...config, for_each: false },
              })}
              style={{ marginTop: 1 }}
            />
            <span style={{ fontSize: 9, color: S.textBright, lineHeight: 1.4 }}>
              Für jede Zeile des Vorgängers
              <span style={{ color: S.textDim, display: "block" }}>
                {"{{spalte}}"} wird je Zeile eingesetzt
              </span>
            </span>
          </label>
        </div>

        {config.for_each && (
          <div>
            <label style={lS}>Höchstens Zeilen</label>
            <input
              style={iS} type="number" min={1}
              value={config.for_each_max ?? 100}
              onChange={e => set("for_each_max", parseInt(e.target.value) || 1)}
            />
            <span style={{ fontSize: 8, color: S.textDim, display: "block", marginTop: 2 }}>
              So viele Aufrufe entstehen höchstens.
            </span>
          </div>
        )}

        <div>
          <label style={lS}>Fehler-Handling</label>
          <select style={iS} value={config.on_error || "stop"} onChange={e => set("on_error", e.target.value)}>
            <option value="stop">Abbrechen</option>
            <option value="continue">Weiter</option>
          </select>
        </div>
      </div>
    </BaseNode>
  );
}
