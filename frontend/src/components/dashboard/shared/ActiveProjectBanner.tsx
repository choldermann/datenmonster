import { AlertCircle, FolderKanban, FolderSync } from "lucide-react";
import { S } from "../constants";

function ActiveProjectBanner({ project, onSwitch }) {
  if (!project) return (
    <div className="flex items-center justify-center gap-3 py-2 px-4 mb-6 rounded-xl"
      style={{ backgroundColor: "rgba(255,255,255,0.02)", border: `1px dashed ${S.border}` }}>
      <AlertCircle size={13} style={{ color: S.textDim }} />
      <span className="text-xs" style={{ color: S.textDim }}>Kein aktives Projekt –</span>
      <button onClick={onSwitch} className="text-xs underline" style={{ color: S.accent }}>Projekt wählen</button>
    </div>
  );
  return (
    <div className="flex items-center justify-center gap-3 py-2 px-6 mb-6 rounded-xl"
      style={{ backgroundColor: "rgba(252,228,153,0.04)", border: `1px solid rgba(252,228,153,0.15)` }}>
      <FolderKanban size={14} style={{ color: S.accent }} />
      <span className="text-xs font-medium" style={{ color: S.accent }}>{project.name}</span>
      {project.description && (
        <span className="text-xs" style={{ color: S.textDim }}>· {project.description}</span>
      )}
      {project.role === "viewer" && (
        <span className="text-xs px-2 py-0.5 rounded font-mono"
          style={{ backgroundColor: "rgba(147,197,253,0.08)", color: "#93c5fd", border: "1px solid rgba(147,197,253,0.2)" }}>
          Nur Lesen
        </span>
      )}
      <button onClick={onSwitch}
        className="ml-3 text-xs px-2 py-0.5 rounded"
        style={{ backgroundColor: "rgba(255,255,255,0.04)", color: S.textDim, border: `1px solid ${S.border}` }}
        onMouseEnter={(e) => e.currentTarget.style.color = S.textBright}
        onMouseLeave={(e) => e.currentTarget.style.color = S.textDim}>
        wechseln
      </button>
    </div>
  );
}

// ─── Dataset Card ─────────────────────────────────────────────────────────────

export default ActiveProjectBanner;
