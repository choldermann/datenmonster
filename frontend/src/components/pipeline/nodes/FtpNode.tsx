import { useRef } from "react";
import { S, NODE_COLORS } from "../constants";
import BaseNode from "./BaseNode";

export default function FtpNode({ node, onRemove, onPositionChange, onUpdate, inputPortRef, inputPortDrop, outputPortRef, ftpSources, runResult, isActive, onActivate }) {
  const config = node.config || {};
  const set = (k, v) => onUpdate({ ...node, config: { ...config, [k]: v } });

  const iS = { backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 3, color: S.textBright, fontSize: 10, padding: "3px 6px", outline: "none", width: "100%", minWidth: 0 };
  const lS = { fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", display: "block", marginBottom: 3 };

  const selectedSource = (ftpSources || []).find(s => s.id === config.ftp_source_id);

  return (
    <BaseNode node={node} color={NODE_COLORS.ftp} icon="📥" label="FTP Input"
      runResult={runResult} isActive={isActive} onActivate={onActivate}
      onRemove={onRemove} onPositionChange={onPositionChange}
      inputPorts={[{ id: "in", label: "Trigger", portRef: inputPortRef, onDrop: inputPortDrop }]}
      outputPorts={[{ id: "out", label: "Dateien",
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
          <label style={lS}>FTP-Quelle</label>
          <select style={iS} value={config.ftp_source_id || ""} onChange={e => set("ftp_source_id", parseInt(e.target.value) || null)}>
            <option value="">— Quelle wählen —</option>
            {(ftpSources || []).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>

        {selectedSource && (
          <div style={{ fontSize: 9, color: S.textDim, padding: "4px 6px", borderRadius: 3, backgroundColor: `${NODE_COLORS.ftp}10`, border: `1px solid ${NODE_COLORS.ftp}22` }}>
            {selectedSource.host} · {selectedSource.remote_dir || "/"} · {selectedSource.filename_filter || "*"}
          </div>
        )}

        <div>
          <label style={lS}>Nach Import</label>
          <select style={iS} value={config.after_import || "nothing"} onChange={e => set("after_import", e.target.value)}>
            <option value="nothing">Nichts tun</option>
            <option value="move">Verschieben</option>
            <option value="delete">Löschen</option>
          </select>
        </div>

        {config.after_import === "move" && (
          <div>
            <label style={lS}>Zielverzeichnis</label>
            <input style={iS} value={config.move_dir || ""} onChange={e => set("move_dir", e.target.value)} placeholder="/processed/" />
          </div>
        )}
      </div>
    </BaseNode>
  );
}
