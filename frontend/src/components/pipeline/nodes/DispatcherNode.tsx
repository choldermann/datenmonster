import { S, NODE_COLORS } from "../constants";
import BaseNode from "./BaseNode";
import { Plus, X } from "lucide-react";

// Bedingungen die nur bei FTP-/Datei-Eingang Sinn machen
const FTP_CONDITIONS = [
  { v: "filename",       l: "Dateiname enthält" },
  { v: "file_extension", l: "Dateiendung" },
  { v: "column_exists",  l: "Spalte existiert" },
  { v: "column_value",   l: "Spalte = Wert" },
  { v: "xml_tag_exists", l: "XML-Tag existiert" },
  { v: "xml_schema",     l: "XML-Schema (Dataset)" },
  { v: "rows_gt",        l: "Zeilen > N" },
  { v: "rows_lt",        l: "Zeilen < N" },
  { v: "rows_eq",        l: "Zeilen = N" },
];

// Bedingungen die nach einem Mapping Sinn machen
const MAPPING_CONDITIONS = [
  { v: "rows_gt", l: "Zeilen > N" },
  { v: "rows_lt", l: "Zeilen < N" },
  { v: "rows_eq", l: "Zeilen = N" },
];

function getSourceType(nodeId, allNodes, connections) {
  // Suche den Node der in diesen Node hineinführt
  const incomingConn = (connections || []).find(c => c.to_node === nodeId);
  if (!incomingConn) return null;
  const sourceNode = (allNodes || []).find(n => n.id === incomingConn.from_node);
  return sourceNode?.type || null;
}

export default function DispatcherNode({ node, onRemove, onPositionChange, onUpdate,
  inputPortRef, inputPortDrop, outputPortRefs, xmlDatasets, allNodes, connections, runResult, isActive, onActivate }) {

  const config = node.config || {};
  const conds  = config.conditions || [];
  const set    = (k, v) => onUpdate({ ...node, config: { ...config, [k]: v } });
  const setConds = (c) => set("conditions", c);

  const addCond   = () => setConds([...conds, { type: sourceType === "mapping" ? "rows_gt" : "filename", threshold: 0, pattern: "" }]);
  const removeCond = (i) => setConds(conds.filter((_, idx) => idx !== i));
  const updateCond = (i, k, v) => setConds(conds.map((c, idx) => idx === i ? { ...c, [k]: v } : c));

  const iS = { backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 3, color: S.textBright, fontSize: 10, padding: "2px 5px", outline: "none", flex: 1, minWidth: 0 };
  const lS = { fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", display: "block", marginBottom: 3 };
  const color = NODE_COLORS.dispatcher;

  // Eingangsquelle ermitteln
  const sourceType = getSourceType(node.id, allNodes, connections);
  const isMappingSource = sourceType === "mapping";
  const conditionTypes  = isMappingSource ? MAPPING_CONDITIONS : FTP_CONDITIONS;

  const outputPorts = [
    { id: "match",    label: "✓ Bedingung erfüllt",  portRef: outputPortRefs?.[0],
      onDragStart: e => { e.stopPropagation(); e.dataTransfer.setData("from_node", node.id); e.dataTransfer.setData("from_port", "match"); } },
    { id: "no_match", label: "✗ Nicht erfüllt",       portRef: outputPortRefs?.[1],
      onDragStart: e => { e.stopPropagation(); e.dataTransfer.setData("from_node", node.id); e.dataTransfer.setData("from_port", "no_match"); } },
  ];

  return (
    <BaseNode node={node} color={color} icon="🔀" label="Verzweigung"
      onRemove={onRemove} onPositionChange={onPositionChange} width={270}
      inputPorts={[{ id: "in", label: "Eingang", portRef: inputPortRef, onDrop: inputPortDrop }]}
      outputPorts={outputPorts}
      runResult={runResult} isActive={isActive} onActivate={onActivate}>

      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>

        {/* Eingangsquellen-Hinweis */}
        {sourceType && (
          <div style={{ fontSize: 9, color: S.textDim, padding: "2px 6px", borderRadius: 3,
            backgroundColor: "rgba(255,255,255,0.04)", border: `1px solid ${S.border}` }}>
            Eingang: <span style={{ color: NODE_COLORS[sourceType] || S.textMain, fontWeight: 600 }}>
              {sourceType === "mapping" ? "Mapping" : sourceType === "ftp" ? "FTP" :
               sourceType === "trigger" ? "Trigger" : sourceType}
            </span>
            {isMappingSource && <span style={{ color: S.textDim }}> · prüft Ergebnis-Zeilen</span>}
          </div>
        )}

        {/* AND/OR nur bei mehreren Bedingungen und FTP-Quelle */}
        {!isMappingSource && conds.length > 1 && (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <label style={{ ...lS, marginBottom: 0 }}>Verknüpfung</label>
            <div style={{ display: "flex", gap: 4 }}>
              {["AND", "OR"].map(m => (
                <button key={m} onClick={() => set("condition_mode", m)}
                  style={{ padding: "1px 8px", borderRadius: 3, fontSize: 9, fontWeight: 700, cursor: "pointer",
                    border: `1px solid ${(config.condition_mode || "AND") === m ? color : S.border}`,
                    backgroundColor: (config.condition_mode || "AND") === m ? color + "20" : "transparent",
                    color: (config.condition_mode || "AND") === m ? color : S.textDim }}>
                  {m}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Bedingungen */}
        {conds.map((c, i) => (
          <div key={i} style={{ display: "flex", gap: 4, alignItems: "center" }}>
            <select style={{ ...iS, flex: "0 0 120px" }} value={c.type}
              onChange={e => updateCond(i, "type", e.target.value)}>
              {conditionTypes.map(t => <option key={t.v} value={t.v}>{t.l}</option>)}
            </select>

            {/* Zeilenanzahl */}
            {(c.type === "rows_gt" || c.type === "rows_lt" || c.type === "rows_eq") && (
              <input style={{ ...iS, flex: "0 0 60px" }} type="number"
                value={c.threshold ?? 0}
                onChange={e => updateCond(i, "threshold", parseInt(e.target.value) || 0)}
                placeholder="0" />
            )}

            {/* FTP-spezifisch */}
            {c.type === "filename" && (
              <input style={iS} value={c.pattern || ""}
                onChange={e => updateCond(i, "pattern", e.target.value)}
                placeholder="*_orders.csv" />
            )}
            {c.type === "file_extension" && (
              <input style={iS} value={c.extension || ""}
                onChange={e => updateCond(i, "extension", e.target.value)}
                placeholder=".xml" />
            )}
            {(c.type === "column_exists" || c.type === "xml_tag_exists") && (
              <input style={iS} value={c.column || ""}
                onChange={e => updateCond(i, "column", e.target.value)}
                placeholder="Spaltenname" />
            )}
            {c.type === "column_value" && (<>
              <input style={{ ...iS, flex: "0 0 55px" }} value={c.column || ""}
                onChange={e => updateCond(i, "column", e.target.value)} placeholder="Spalte" />
              <input style={iS} value={c.value || ""}
                onChange={e => updateCond(i, "value", e.target.value)} placeholder="Wert" />
            </>)}
            {c.type === "xml_schema" && (
              <select style={iS} value={c.dataset_id || ""}
                onChange={e => updateCond(i, "dataset_id", parseInt(e.target.value) || null)}>
                <option value="">— Dataset —</option>
                {(xmlDatasets || []).map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
            )}

            <button onClick={() => removeCond(i)}
              style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0, flexShrink: 0 }}>
              <X size={9} />
            </button>
          </div>
        ))}

        <button onClick={addCond}
          style={{ padding: "3px", borderRadius: 3, fontSize: 9, fontWeight: 600, cursor: "pointer",
            backgroundColor: color + "10", border: `1px dashed ${color}44`, color,
            display: "flex", alignItems: "center", justifyContent: "center", gap: 3 }}>
          <Plus size={9} /> Bedingung hinzufügen
        </button>

        {/* Port-Labels */}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 12, marginTop: 2 }}>
          <span style={{ fontSize: 8, color: "#6ee7b7", fontWeight: 700 }}>✓ JA →</span>
          <span style={{ fontSize: 8, color: "#e07070", fontWeight: 700 }}>✗ NEIN →</span>
        </div>
      </div>
    </BaseNode>
  );
}
