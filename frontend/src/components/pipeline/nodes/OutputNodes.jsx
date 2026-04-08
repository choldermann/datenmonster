import { S, NODE_COLORS } from "../constants";
import BaseNode from "./BaseNode";

// ─── FTP Upload Node ──────────────────────────────────────────────────────────
export function FtpUploadNode({ node, onRemove, onPositionChange, onUpdate, inputPortRef, inputPortDrop, ftpSources, runResult }) {
  const config = node.config || {};
  const set = (k, v) => onUpdate({ ...node, config: { ...config, [k]: v } });

  const iS = { backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 3, color: S.textBright, fontSize: 10, padding: "3px 6px", outline: "none", width: "100%", minWidth: 0 };
  const lS = { fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", display: "block", marginBottom: 3 };
  const color = NODE_COLORS.ftp_upload;

  return (
    <BaseNode node={node} color={color} icon="📤" label="FTP Upload"
      onRemove={onRemove} onPositionChange={onPositionChange}
      inputPorts={[{ id: "in", label: "Datei", portRef: inputPortRef, onDrop: inputPortDrop }]}
     runResult={runResult}>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <div>
          <label style={lS}>FTP-Ziel</label>
          <select style={iS} value={config.ftp_source_id || ""} onChange={e => set("ftp_source_id", parseInt(e.target.value) || null)}>
            <option value="">— Ziel wählen —</option>
            {(ftpSources || []).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
        <div>
          <label style={lS}>Zielverzeichnis</label>
          <input style={iS} value={config.remote_dir || ""} onChange={e => set("remote_dir", e.target.value)} placeholder="/outbound/" />
        </div>
        <div>
          <label style={lS}>Dateiname</label>
          <input style={iS} value={config.filename || ""} onChange={e => set("filename", e.target.value)} placeholder="export_{datum}.csv" />
        </div>
      </div>
    </BaseNode>
  );
}

// ─── E-Mail Node ──────────────────────────────────────────────────────────────
export function EmailNode({ node, onRemove, onPositionChange, onUpdate, inputPortRef, inputPortDrop, runResult }) {
  const config = node.config || {};
  const set = (k, v) => onUpdate({ ...node, config: { ...config, [k]: v } });

  const iS = { backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 3, color: S.textBright, fontSize: 10, padding: "3px 6px", outline: "none", width: "100%", minWidth: 0 };
  const lS = { fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", display: "block", marginBottom: 3 };
  const color = NODE_COLORS.email;

  return (
    <BaseNode node={node} color={color} icon="📧" label="E-Mail"
      onRemove={onRemove} onPositionChange={onPositionChange}
      inputPorts={[{ id: "in", label: "Auslöser", portRef: inputPortRef, onDrop: inputPortDrop }]}
     runResult={runResult}>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <div>
          <label style={lS}>Empfänger *</label>
          <input style={iS} value={config.to || ""} onChange={e => set("to", e.target.value)} placeholder="info@firma.de" />
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <div style={{ flex: 1 }}>
            <label style={lS}>CC</label>
            <input style={iS} value={config.cc || ""} onChange={e => set("cc", e.target.value)} placeholder="cc@firma.de" />
          </div>
          <div style={{ flex: 1 }}>
            <label style={lS}>BCC</label>
            <input style={iS} value={config.bcc || ""} onChange={e => set("bcc", e.target.value)} placeholder="bcc@firma.de" />
          </div>
        </div>
        <div>
          <label style={lS}>Betreff</label>
          <input style={iS} value={config.subject || ""} onChange={e => set("subject", e.target.value)} placeholder="Pipeline abgeschlossen" />
        </div>
        <div>
          <label style={lS}>Nachricht</label>
          <textarea style={{ ...iS, resize: "vertical", minHeight: 48, fontFamily: "inherit" }}
            value={config.body || ""} onChange={e => set("body", e.target.value)}
            placeholder="Die Pipeline wurde erfolgreich ausgeführt." />
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {["success", "error", "always"].map(t => (
            <button key={t} onClick={() => set("send_on", t)}
              style={{ flex: 1, padding: "2px 4px", borderRadius: 3, fontSize: 9, fontWeight: 600, cursor: "pointer", border: `1px solid ${(config.send_on || "always") === t ? color : S.border}`, backgroundColor: (config.send_on || "always") === t ? color + "20" : "transparent", color: (config.send_on || "always") === t ? color : S.textDim }}>
              {t === "success" ? "✓ Erfolg" : t === "error" ? "✗ Fehler" : "Immer"}
            </button>
          ))}
        </div>
      </div>
    </BaseNode>
  );
}
