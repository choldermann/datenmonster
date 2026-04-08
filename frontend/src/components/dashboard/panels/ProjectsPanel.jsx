import { useCallback, useEffect, useState } from "react";
import { FolderPlus, Users, X, Check, Plus, Pencil, Trash2, Share2, FolderKanban, ChevronDown, AlertCircle, Loader2 } from "lucide-react";
import api from "../../../api/client";
import { S } from "../constants";
import Modal from "../shared/Modal";
import NewTile from "../shared/NewTile";

function NewProjectTile({ onClick }) {
  const [hovered, setHovered] = useState(false);
  return (
    <div onClick={onClick} onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
      className="card transition-all duration-150 cursor-pointer flex flex-col items-center justify-center gap-3 min-h-[120px]"
      style={{
        borderColor: hovered ? "rgba(110,231,170,0.6)" : "rgba(110,231,170,0.25)",
        backgroundColor: hovered ? "rgba(110,231,170,0.07)" : "rgba(110,231,170,0.03)",
        borderStyle: "dashed",
      }}>
      <div className="rounded-full p-2" style={{ backgroundColor: hovered ? "rgba(110,231,170,0.15)" : "rgba(110,231,170,0.07)" }}>
        <FolderPlus size={20} style={{ color: hovered ? "#6ee7aa" : "#4ade80" }} />
      </div>
      <div className="text-center">
        <p className="text-sm font-medium" style={{ color: hovered ? "#6ee7aa" : "#4ade80" }}>Neues Projekt</p>
        <p className="text-xs mt-0.5" style={{ color: "rgba(110,231,170,0.5)" }}>Datasets, Mappings, Verbindungen</p>
      </div>
    </div>
  );
}

// ─── Project Card ─────────────────────────────────────────────────────────────
function ProjectCard({ project, isActive, onSelect, onDelete, onShare, onEdit }) {
  const [hovered, setHovered] = useState(false);
  const roleColor = { owner: "#fce499", editor: "#93c5fd", viewer: "#6ee7b7" };
  const roleLabel = { owner: "Eigentümer", editor: "Bearbeiter", viewer: "Betrachter" };
  return (
    <div onClick={() => onSelect(project)}
      onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
      className="card group cursor-pointer transition-all duration-150"
      style={{
        borderColor: isActive ? S.accent : hovered ? "rgba(252,228,153,0.3)" : S.border,
        backgroundColor: isActive ? "rgba(252,228,153,0.04)" : "transparent",
      }}>
      <div className="flex items-start justify-between min-w-0">
        <div className="flex items-center gap-3 min-w-0">
          <FolderKanban size={18} style={{ color: isActive ? S.accent : S.textDim, flexShrink: 0 }} />
          <div className="min-w-0">
            <p className="font-medium text-sm truncate" style={{ color: S.textBright }}>{project.name}</p>
            {project.description && (
              <p className="text-xs mt-0.5 truncate" style={{ color: S.textDim }}>{project.description}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0 ml-2">
          {project.role === "owner" && (
            <>
              <button onClick={(e) => { e.stopPropagation(); onShare(project); }}
                className="p-1 rounded" title="Freigeben"
                style={{ color: S.textDim }}
                onMouseEnter={(e) => e.currentTarget.style.color = "#93c5fd"}
                onMouseLeave={(e) => e.currentTarget.style.color = S.textDim}>
                <Share2 size={13} />
              </button>
              <button onClick={(e) => { e.stopPropagation(); onEdit(project); }}
                className="p-1 rounded"
                style={{ color: S.textDim }}
                onMouseEnter={(e) => e.currentTarget.style.color = S.accent}
                onMouseLeave={(e) => e.currentTarget.style.color = S.textDim}>
                <Pencil size={13} />
              </button>
              <button onClick={(e) => { e.stopPropagation(); onDelete(project.id); }}
                className="p-1 rounded"
                style={{ color: S.textDim }}
                onMouseEnter={(e) => e.currentTarget.style.color = "#e07070"}
                onMouseLeave={(e) => e.currentTarget.style.color = S.textDim}>
                <Trash2 size={13} />
              </button>
            </>
          )}
        </div>
      </div>
      <div className="flex items-center gap-3 mt-4">
        <span className="text-xs px-2 py-0.5 rounded font-mono"
          style={{ backgroundColor: "rgba(255,255,255,0.04)", color: roleColor[project.role] || S.textDim }}>
          {roleLabel[project.role] || project.role}
        </span>
        {isActive && (
          <span className="text-xs px-2 py-0.5 rounded font-mono flex items-center gap-1"
            style={{ backgroundColor: "rgba(252,228,153,0.08)", color: S.accent, border: `1px solid rgba(252,228,153,0.2)` }}>
            <Check size={10} /> Aktiv
          </span>
        )}
      </div>
    </div>
  );
}

// ─── Create/Edit Project Modal ────────────────────────────────────────────────
function ProjectModal({ project, onDone, onCancel }) {
  const [name, setName] = useState(project?.name || "");
  const [description, setDescription] = useState(project?.description || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleSave = async () => {
    if (!name.trim()) { setError("Name ist Pflichtfeld"); return; }
    setSaving(true); setError("");
    try {
      if (project) await api.patch(`/api/projects/${project.id}`, { name: name.trim(), description: description.trim() });
      else await api.post("/api/projects/", { name: name.trim(), description: description.trim() });
      onDone();
    } catch (err) {
      setError(err.response?.data?.detail || "Fehler beim Speichern");
    } finally { setSaving(false); }
  };

  return (
    <Modal title={project ? "Projekt bearbeiten" : "Neues Projekt"} onClose={onCancel}>
      <div className="flex flex-col gap-4">
        <div>
          <label className="block text-xs uppercase tracking-widest mb-1.5" style={{ color: S.textDim }}>Projektname</label>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSave()} autoFocus placeholder="Mein Projekt" />
        </div>
        <div>
          <label className="block text-xs uppercase tracking-widest mb-1.5" style={{ color: S.textDim }}>Beschreibung (optional)</label>
          <input className="input" value={description} onChange={(e) => setDescription(e.target.value)}
            placeholder="Kurze Beschreibung..." />
        </div>
        {error && <p className="text-xs" style={{ color: "#e07070" }}>{error}</p>}
        <div className="flex gap-3 pt-1">
          <button onClick={onCancel} className="btn-ghost text-xs">Abbrechen</button>
          <button onClick={handleSave} disabled={saving || !name.trim()} className="btn-primary text-xs ml-auto">
            {saving && <Loader2 size={12} className="animate-spin" />}
            {project ? "Speichern" : "Erstellen"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ─── Share Project Modal ──────────────────────────────────────────────────────
function ShareProjectModal({ project, onClose }) {
  const [users, setUsers] = useState([]);
  const [members, setMembers] = useState([]);
  const [selectedUser, setSelectedUser] = useState("");
  const [role, setRole] = useState("editor");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [{ data: u }, { data: m }] = await Promise.all([
      api.get("/api/auth/users"),
      api.get(`/api/projects/${project.id}/members`),
    ]);
    setUsers(u); setMembers(m);
  }, [project.id]);

  useEffect(() => { load(); }, [load]);

  const addMember = async () => {
    if (!selectedUser) return;
    setSaving(true); setError("");
    try {
      await api.post(`/api/projects/${project.id}/members`, { user_id: Number(selectedUser), role });
      setSelectedUser(""); load();
    } catch (err) { setError(err.response?.data?.detail || "Fehler"); }
    finally { setSaving(false); }
  };

  const removeMember = async (userId) => {
    await api.delete(`/api/projects/${project.id}/members/${userId}`);
    load();
  };

  const availableUsers = users.filter((u) => !members.find((m) => m.user_id === u.id));
  const roleColor = { owner: S.accent, editor: "#93c5fd", viewer: "#6ee7b7" };
  const roleLabel = { owner: "Eigentümer", editor: "Bearbeiter", viewer: "Betrachter" };

  return (
    <Modal title={`„${project.name}" freigeben`} onClose={onClose} width="max-w-lg">
      <div className="flex flex-col gap-5">
        {/* Mitglieder hinzufügen */}
        <div>
          <label className="block text-xs uppercase tracking-widest mb-2" style={{ color: S.textDim }}>Benutzer hinzufügen</label>
          <div className="flex gap-2">
            <select className="input flex-1 text-xs"
              value={selectedUser} onChange={(e) => setSelectedUser(e.target.value)}
              style={{ color: selectedUser ? S.textBright : S.textDim }}>
              <option value="">Benutzer wählen…</option>
              {availableUsers.map((u) => <option key={u.id} value={u.id}>{u.username}</option>)}
            </select>
            <select className="input text-xs" value={role} onChange={(e) => setRole(e.target.value)} style={{ width: 110 }}>
              <option value="editor">Bearbeiter</option>
              <option value="viewer">Betrachter</option>
            </select>
            <button onClick={addMember} disabled={!selectedUser || saving} className="btn-primary text-xs px-3">
              {saving ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
            </button>
          </div>
          {availableUsers.length === 0 && (
            <p className="text-xs mt-2" style={{ color: S.textDim }}>Keine weiteren Benutzer verfügbar.</p>
          )}
          {error && <p className="text-xs mt-2" style={{ color: "#e07070" }}>{error}</p>}
        </div>

        {/* Mitgliederliste */}
        <div>
          <label className="block text-xs uppercase tracking-widest mb-2" style={{ color: S.textDim }}>
            Mitglieder ({members.length})
          </label>
          {members.length === 0
            ? <p className="text-xs" style={{ color: S.textDim }}>Noch keine Mitglieder freigegeben.</p>
            : (
              <div className="flex flex-col gap-2">
                {members.map((m) => (
                  <div key={m.user_id} className="flex items-center justify-between px-3 py-2 rounded-lg"
                    style={{ backgroundColor: S.bgEl, border: `1px solid ${S.border}` }}>
                    <div className="flex items-center gap-2">
                      <Users size={13} style={{ color: S.textDim }} />
                      <span className="text-xs font-medium" style={{ color: S.textBright }}>{m.username}</span>
                      <span className="text-xs px-1.5 py-0.5 rounded font-mono"
                        style={{ backgroundColor: "rgba(255,255,255,0.04)", color: roleColor[m.role] }}>
                        {roleLabel[m.role]}
                      </span>
                    </div>
                    <button onClick={() => removeMember(m.user_id)} style={{ color: S.textDim }}
                      onMouseEnter={(e) => e.currentTarget.style.color = "#e07070"}
                      onMouseLeave={(e) => e.currentTarget.style.color = S.textDim}>
                      <X size={13} />
                    </button>
                  </div>
                ))}
              </div>
            )}
        </div>
      </div>
    </Modal>
  );
}

// ─── Edit Dataset Modal ───────────────────────────────────────────────────────

export { NewProjectTile, ProjectCard, ProjectModal, ShareProjectModal };
