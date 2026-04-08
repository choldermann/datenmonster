import { ArrowLeft, Save, Play, Loader2 } from "lucide-react";
import { S } from "./constants";

export default function PipelineHeader({ name, onNameChange, onBack, onSave, onExecute, saving, executing, nodeCount, connCount }) {
  return (
    <div style={{
      height: 52, flexShrink: 0,
      backgroundColor: S.bgCard,
      borderBottom: `1px solid ${S.border}`,
      display: "flex", alignItems: "center",
      padding: "0 16px", gap: 12,
    }}>
      <button onClick={onBack}
        style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 10px", borderRadius: 5, border: `1px solid ${S.border}`, background: "none", color: S.textDim, cursor: "pointer", fontSize: 11 }}
        onMouseEnter={e => e.currentTarget.style.color = S.textBright}
        onMouseLeave={e => e.currentTarget.style.color = S.textDim}>
        <ArrowLeft size={13} /> Dashboard
      </button>

      <input
        value={name}
        onChange={e => onNameChange(e.target.value)}
        placeholder="Pipeline Name"
        style={{ flex: 1, maxWidth: 300, backgroundColor: "transparent", border: "none", borderBottom: `1px solid ${S.border}`, color: S.textBright, fontSize: 14, fontWeight: 600, outline: "none", padding: "4px 0" }}
      />

      <div style={{ flex: 1 }} />

      <span style={{ fontSize: 10, color: S.textDim }}>
        {nodeCount} Nodes · {connCount} Verbindungen
      </span>

      <button onClick={onSave} disabled={saving}
        style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 14px", borderRadius: 5, border: `1px solid ${S.border}`, backgroundColor: S.bgEl, color: S.textBright, cursor: "pointer", fontSize: 12, fontWeight: 600 }}>
        {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
        Speichern
      </button>

      <button onClick={onExecute} disabled={executing}
        style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 16px", borderRadius: 5, border: "none", backgroundColor: "var(--accent)", color: "#111", cursor: "pointer", fontSize: 12, fontWeight: 700 }}>
        {executing ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
        {executing ? "Läuft..." : "Ausführen"}
      </button>
    </div>
  );
}
