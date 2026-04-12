import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useProject } from "../context/ProjectContext";
import DbConnectionManager from "../components/DbConnectionManager";
import XmlConfigurator from "../components/XmlConfigurator";
import api from "../api/client";
import { Activity, BarChart2, Check, ChevronRight, Database, Download, FolderKanban, FolderOpen, FolderSync, GitBranch, HardDrive, KeyRound, LayoutGrid, Loader2, LogOut, Package, Pencil, Plus, RefreshCw, Server, Settings, Table, Trash2, Users, Wifi, X } from "lucide-react";

import { S } from "../components/dashboard/constants";
import MonitoringPanel from "../components/dashboard/panels/MonitoringPanel";
import Modal from "../components/dashboard/shared/Modal";
import ActiveProjectBanner from "../components/dashboard/shared/ActiveProjectBanner";
import ChangePasswordModal from "../components/dashboard/modals/ChangePasswordModal";
import SystemSettingsModal from "../components/dashboard/modals/SystemSettingsModal";
import { NewProjectTile, ProjectCard, ProjectModal, ShareProjectModal } from "../components/dashboard/panels/ProjectsPanel";
import { EditDatasetModal, DatasetCard, TypeBadge, TypeBadgeEditor, DataExplorer, ManualDatasetModal } from "../components/dashboard/panels/DatasetsPanel";
import DatasetRowEditor from "../components/DatasetRowEditor";
import NewTile from "../components/dashboard/shared/NewTile";
import ExportsPanel from "../components/dashboard/panels/ExportsPanel";
import { FtpPanel, FtpFormModal } from "../components/dashboard/panels/FtpPanel";
import { RestApiPanel } from "../components/dashboard/panels/RestApiPanel";
import AccessImportPanel from "../components/dashboard/panels/AccessImportPanel";
import PipelinesPanel from "../components/dashboard/panels/PipelinesPanel";
import TemplatesPanel from "../components/dashboard/panels/TemplatesPanel";
import ReportsPanel from "../components/dashboard/panels/ReportsPanel";
import { SchedulerPanel } from "../components/dashboard/panels/SchedulerPanel";
import DispatcherPanel from "../components/dashboard/panels/DispatcherPanel";
import NewDatasetWizard from "../components/NewDatasetWizard";


// ─── Bestätigungs-Modal ───────────────────────────────────────────────────────
function ConfirmModal({ modal, onClose }) {
  if (!modal) return null;
  const { title, message, onConfirm, dangerous } = modal;
  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 200, display: "flex", alignItems: "center",
        justifyContent: "center", backgroundColor: "rgba(0,0,0,0.75)" }} onClick={onClose}>
      <div style={{ backgroundColor: "#1e1e1e", border: `1px solid ${dangerous ? "rgba(224,112,112,0.4)" : "#333"}`,
          borderRadius: 10, padding: 24, width: 420, boxShadow: "0 24px 60px rgba(0,0,0,0.7)" }}
          onClick={e => e.stopPropagation()}>
        <p style={{ fontSize: 14, fontWeight: 700, color: dangerous ? "#e07070" : "#f0f0f0",
            margin: "0 0 10px" }}>{title}</p>
        <p style={{ fontSize: 12, color: "#aaa", margin: "0 0 20px", whiteSpace: "pre-wrap",
            lineHeight: 1.6 }}>{message}</p>
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button onClick={onClose}
            style={{ padding: "7px 16px", borderRadius: 5, border: "1px solid #444",
                background: "none", color: "#aaa", fontSize: 12, cursor: "pointer" }}>
            Abbrechen
          </button>
          <button onClick={() => { onConfirm(); onClose(); }}
            style={{ padding: "7px 18px", borderRadius: 5, border: "none", fontSize: 12,
                fontWeight: 700, cursor: "pointer",
                backgroundColor: dangerous ? "#e07070" : "#fce499",
                color: dangerous ? "#fff" : "#111" }}>
            {dangerous ? "Löschen" : "Bestätigen"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const { user, logout } = useAuth();
  const { activeProject, setActiveProject } = useProject();
  const navigate = useNavigate();
  const location = useLocation();
  // Bestätigungs-Modal State
  const [confirmModal, setConfirmModal] = useState(null);
  const showConfirm = useCallback((title, message, onConfirm, opts = {}) => {
    setConfirmModal({ title, message, onConfirm, ...opts });
  }, []);

    const [tab, setTab] = useState(location.state?.tab || "monitoring");
  const [projects, setProjects] = useState([]);
  const [datasets, setDatasets] = useState([]);
  const [mappings, setMappings] = useState([]);
  const [datasetSearch, setDatasetSearch] = useState("");
  const [mappingSearch, setMappingSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [configuring, setConfiguring] = useState(null);
  const [editingDataset, setEditingDataset] = useState(null);
  const [editingRows, setEditingRows] = useState(null); // für static Datasets
  const [showWizard, setShowWizard] = useState(false);
  const [showManualCreate, setShowManualCreate] = useState(false);
  // Project modals
  const [showNewProject, setShowNewProject] = useState(false);
  const [editingProject, setEditingProject] = useState(null);
  const [sharingProject, setSharingProject] = useState(null);

  const projectId = activeProject?.id ?? null;
  const canEdit = !activeProject || activeProject.role !== "viewer";
  const [showChangePassword, setShowChangePassword] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  const loadProjects = useCallback(async () => {
    try { const { data } = await api.get("/api/projects/"); setProjects(Array.isArray(data) ? data : []); } catch {}
  }, []);

  const loadDatasets = useCallback(async (search = "") => {
    setLoading(true);
    try {
      const p = new URLSearchParams();
      if (projectId != null) p.set("project_id", projectId);
      if (search) p.set("search", search);
      const { data } = await api.get(`/api/datasets/?${p}`);
      setDatasets(Array.isArray(data) ? data : []);
    } finally { setLoading(false); }
  }, [projectId]);

  const loadMappings = useCallback(async (search = "") => {
    try {
      const p = new URLSearchParams();
      if (projectId != null) p.set("project_id", projectId);
      if (search) p.set("search", search);
      const { data } = await api.get(`/api/mappings/?${p}`);
      setMappings(Array.isArray(data) ? data : []);
    } catch {}
  }, [projectId]);

  useEffect(() => { loadProjects(); }, [loadProjects]);
  useEffect(() => { if (tab === "datasets" || tab === "ftp" || tab === "rest") loadDatasets(); }, [tab, loadDatasets]);

  // Auto-Refresh alle 30s wenn auf Datasets-Tab
  useEffect(() => {
    if (tab !== "datasets") return;
    const interval = setInterval(() => loadDatasets(), 30000);
    return () => clearInterval(interval);
  }, [tab, loadDatasets]);
  useEffect(() => { if (tab === "mappings") loadMappings(); }, [tab, loadMappings]);
  // Scheduler und Dispatcher brauchen mappings – sicherstellen dass sie geladen sind
  useEffect(() => {
    if ((tab === "scheduler" || tab === "dispatcher") && mappings.length === 0) {
      loadMappings();
    }
  }, [tab]);

  const deleteDataset = async (id) => {
    showConfirm("Dataset löschen", "Dataset wirklich unwiderruflich löschen?", async () => {
      try {
        await api.delete(`/api/datasets/${id}`);
        loadDatasets();
      } catch (e) {
        if (e.response?.status === 409) {
          const detail = e.response.data?.detail || "Dataset wird in Mappings verwendet.";
          showConfirm("⚠ Dataset wird verwendet", detail + "\n\nTrotzdem löschen?",
            async () => { await api.delete(`/api/datasets/${id}?force=true`); loadDatasets(); },
            { dangerous: true });
        } else { alert("Fehler: " + (e.response?.data?.detail || e.message)); }
      }
    }, { dangerous: true });
  };
  const deleteMapping = async (id) => {
    showConfirm("Mapping löschen", "Mapping wirklich unwiderruflich löschen?", async () => { try { await api.delete(`/api/mappings/${id}`); loadMappings(); } catch (e) { alert(e.response?.data?.detail || e.message); } }, { dangerous: true });
  };
  const deleteProject = async (id) => {
    showConfirm("Projekt löschen", "Projekt und ALLE zugehörigen Daten (Datasets, Mappings, Jobs, Pipelines) unwiderruflich löschen?",
    async () => {
      try {
        await api.delete(`/api/projects/${id}`);
        if (activeProject?.id === id) setActiveProject(null);
        loadProjects();
      } catch (e) { alert(e.response?.data?.detail || e.message); }
    }, { dangerous: true });
  };

  const NAV = [
    { id: "monitoring", label: "Monitoring", icon: Activity, badge: 0 },
    { id: "projects", label: "Projekte", icon: FolderKanban, badge: projects.length },
    { id: "datasets", label: "Datasets", icon: LayoutGrid, badge: datasets.length },
    { id: "connections", label: "DB-Connectors", icon: Database, badge: 0 },
    { id: "mappings",   label: "Mappings",   icon: GitBranch, badge: mappings.length },
    { id: "pipelines",  label: "Pipelines",  icon: GitBranch, badge: 0 },
    { id: "templates",  label: "Templates",  icon: Package,   badge: 0 },
    { id: "reports",    label: "Reports",    icon: BarChart2, badge: 0 },
    { id: "ftp", label: "FTP / SFTP", icon: Server, badge: 0 },
    { id: "rest", label: "REST API", icon: Wifi, badge: 0 },
    { id: "exports", label: "Exporte", icon: HardDrive, badge: 0 },
  ];

  const tColor = { csv: "#6ee7b7", xlsx: "#93c5fd", json: "#fcd34d", xml: "#f9a8d4", db_mssql: "#c4b5fd", db_mysql: "#6ee7b7" };
  const tLabel = { csv: "CSV", xlsx: "Excel", json: "JSON", xml: "XML", db_mssql: "SQL Server", db_mysql: "MySQL" };

  return (
    <div className="h-screen flex overflow-hidden" style={{ backgroundColor: S.bgMain }}>
      {/* ── Sidebar ── */}
      <aside className="w-56 shrink-0 flex flex-col h-screen sticky top-0"
        style={{ backgroundColor: S.bgCard, borderRight: `1px solid ${S.border}` }}>
        <div className="flex items-center gap-3 px-5 py-5" style={{ borderBottom: `1px solid ${S.border}` }}>
          <img src="/datenmonster.svg" alt="Datenmonster" style={{ width: 32, height: 32, borderRadius: 6 }} />
          <div>
            <span className="font-bold font-mono text-sm block" style={{ color: S.accent, letterSpacing: "0.05em" }}>Datenmonster</span>
            <span className="text-xs" style={{ color: S.textDim }}>Holdermann IT</span>
          </div>
        </div>

        <nav className="flex-1 px-3 py-4 flex flex-col gap-1">
          {NAV.map(({ id, label, icon: Icon, badge }) => {
            const active = tab === id;
            return (
              <button key={id} onClick={() => setTab(id)}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all w-full text-left"
                style={active ? { backgroundColor: S.accent, color: "#111" } : { color: S.textDim }}
                onMouseEnter={(e) => { if (!active) e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.04)"; }}
                onMouseLeave={(e) => { if (!active) e.currentTarget.style.backgroundColor = "transparent"; }}>
                <Icon size={15} />
                <span className="flex-1">{label}</span>
                {badge > 0 && (
                  <span className="text-xs font-mono px-1.5 py-0.5 rounded"
                    style={{ backgroundColor: active ? "rgba(0,0,0,0.15)" : "rgba(255,255,255,0.06)", color: active ? "#111" : S.textDim }}>
                    {badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        <div className="px-3 py-4" style={{ borderTop: `1px solid ${S.border}` }}>
          <div style={{ display: "flex", alignItems: "center", padding: "0 12px", marginBottom: 10 }}>
            <p className="text-xs" style={{ color: S.textDim, flex: 1, margin: 0 }}>
              Angemeldet als <span style={{ color: S.textMain }}>{user?.username}</span>
            </p>
            <button onClick={() => setShowSettings(true)} title="Systemeinstellungen"
              style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 4, borderRadius: 4 }}
              onMouseEnter={e => { e.currentTarget.style.color = S.accent; e.currentTarget.style.backgroundColor = "rgba(252,228,153,0.08)"; }}
              onMouseLeave={e => { e.currentTarget.style.color = S.textDim; e.currentTarget.style.backgroundColor = "transparent"; }}>
              <Settings size={14} />
            </button>
          </div>
          <button onClick={() => setShowChangePassword(true)}
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm w-full transition-all mb-1"
            style={{ color: S.textDim }}
            onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "rgba(252,228,153,0.06)"; e.currentTarget.style.color = S.textMain; }}
            onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = S.textDim; }}>
            <KeyRound size={14} /> Passwort ändern
          </button>
          <button onClick={() => { logout(); navigate("/login"); }}
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm w-full transition-all"
            style={{ color: S.textDim }}
            onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "rgba(224,112,112,0.08)"; e.currentTarget.style.color = "#e07070"; }}
            onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.color = S.textDim; }}>
            <LogOut size={14} /> Abmelden
          </button>
        </div>
      </aside>

      {showChangePassword && <ChangePasswordModal onClose={() => setShowChangePassword(false)} />}
      {showSettings && <SystemSettingsModal onClose={() => setShowSettings(false)} />}

      {/* ── Main ── */}
      <main className="flex-1 min-w-0 px-8 py-8 overflow-y-auto h-screen">

        {/* Aktives Projekt Banner */}
        {tab !== "projects" && (
          <ActiveProjectBanner project={activeProject} onSwitch={() => setTab("projects")} />
        )}

        {/* ── Projekte ── */}
        {tab === "projects" && (
          <div>
            <div className="flex items-center justify-between mb-6">
              <div>
                <h1 className="text-sm font-medium uppercase tracking-widest" style={{ color: S.accent }}>Projekte</h1>
                <p className="text-xs mt-0.5" style={{ color: S.textDim }}>
                  {projects.length > 0 ? `${projects.length} Projekte verfügbar` : "Noch keine Projekte"}
                </p>
              </div>
              <button onClick={loadProjects} className="btn-ghost text-xs"><RefreshCw size={12} /> Aktualisieren</button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              <NewProjectTile onClick={() => setShowNewProject(true)} />
              {projects.map((p) => (
                <ProjectCard key={p.id} project={p} isActive={activeProject?.id === p.id}
                  onSelect={(proj) => { setActiveProject(proj); setTab("datasets"); }}
                  onDelete={deleteProject}
                  onShare={setSharingProject}
                  onEdit={setEditingProject} />
              ))}
            </div>
          </div>
        )}

        {/* ── Datasets ── */}
        {tab === "datasets" && (
          <div>
            <div className="flex items-center justify-between mb-6">
              <div>
                <h1 className="text-sm font-medium uppercase tracking-widest" style={{ color: S.accent }}>Datasets</h1>
                <p className="text-xs mt-0.5" style={{ color: S.textDim }}>
                  {datasets.length > 0 ? `${datasets.length} Datasets` : "Noch keine Datasets"}
                  {activeProject && <span style={{ color: S.textDim }}> · Projekt: <span style={{ color: S.textMain }}>{activeProject.name}</span></span>}
                  <span style={{ marginLeft: 8, fontSize: 10, opacity: 0.5 }}>· Auto-Refresh 30s</span>
                </p>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input
                  placeholder="Suchen…"
                  value={datasetSearch}
                  onChange={e => { setDatasetSearch(e.target.value); loadDatasets(e.target.value); }}
                  style={{ padding: "5px 10px", borderRadius: 5, border: `1px solid ${S.border}`,
                    background: S.bgEl, color: S.textMain, fontSize: 11, outline: "none", width: 160 }}
                />
                <button onClick={() => loadDatasets(datasetSearch)} className="btn-ghost text-xs"><RefreshCw size={12} /></button>
              </div>
            </div>
            {loading ? (
              <div className="flex items-center justify-center h-48" style={{ color: S.textDim }}>
                <Loader2 className="animate-spin mr-2" size={18} /> Lade...
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {canEdit && <NewTile label="Neues Dataset" sub="Datei oder SQL-Abfrage" icon={Plus}
                  onClick={() => setShowWizard(true)} />}
                {canEdit && <NewTile label="Manuell anlegen" sub="Leeres Dataset mit Spalten" icon={Table}
                  onClick={() => setShowManualCreate(true)} />}
                {datasets.map((ds) => (
                  <DatasetCard key={ds.id} dataset={ds} canEdit={canEdit}
                    onDelete={deleteDataset} onClick={setSelected}
                    onConfigure={setConfiguring}
                    onEdit={(ds) => setEditingDataset(ds)}
                    onEditRows={(ds) => setEditingRows(ds)}
                    onRequery={loadDatasets} />
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── DB-Connectors ── */}
        {tab === "connections" && (
          <div>
            <div className="mb-6">
              <h1 className="text-sm font-medium uppercase tracking-widest" style={{ color: S.accent }}>DB-Connectors</h1>
              <p className="text-xs mt-0.5" style={{ color: S.textDim }}>
                Verbindungen zu SQL Server und MySQL
                {activeProject && <span> · Projekt: <span style={{ color: S.textMain }}>{activeProject.name}</span></span>}
              </p>
            </div>
            <DbConnectionManager projectId={activeProject?.id ?? null} canEdit={canEdit} onDatasetCreated={loadDatasets} />
          </div>
        )}

        {/* ── Mappings ── */}
        {tab === "mappings" && (
          <div>
            <div className="flex items-center justify-between mb-6">
              <div>
                <h1 className="text-sm font-medium uppercase tracking-widest" style={{ color: S.accent }}>Mappings</h1>
                <p className="text-xs mt-0.5" style={{ color: S.textDim }}>
                  {mappings.length > 0 ? `${mappings.length} Mappings` : "Noch keine Mappings"}
                  {activeProject && <span> · Projekt: <span style={{ color: S.textMain }}>{activeProject.name}</span></span>}
                </p>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input
                  placeholder="Mappings suchen…"
                  value={mappingSearch}
                  onChange={e => {
                    setMappingSearch(e.target.value);
                    loadMappings(e.target.value);
                  }}
                  style={{ padding: "5px 10px", borderRadius: 5, border: `1px solid ${S.border}`,
                    background: S.bgEl, color: S.textMain, fontSize: 11, outline: "none", width: 180 }}
                />
                <button onClick={() => loadMappings(mappingSearch)} className="btn-ghost text-xs"><RefreshCw size={12} /></button>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {canEdit && <NewTile label="Neues Mapping" sub="Felder verbinden und transformieren" icon={GitBranch}
                onClick={() => navigate(`/mappings/new${activeProject ? `?project_id=${activeProject.id}` : ""}`)} />}
              {mappings.map((m) => (
                <div key={m.id} className="card group cursor-pointer transition-all"
                  style={{ borderColor: S.border }}
                  onClick={() => navigate(`/mappings/${m.id}`)}
                  onMouseEnter={(e) => e.currentTarget.style.borderColor = S.accent}
                  onMouseLeave={(e) => e.currentTarget.style.borderColor = S.border}>
                  <div className="flex items-start justify-between min-w-0">
                    <div className="flex items-center gap-3 min-w-0">
                      <GitBranch size={18} style={{ color: S.accent, flexShrink: 0 }} />
                      <p className="font-medium text-sm truncate" style={{ color: S.textBright }}>{m.name}</p>
                    </div>
                    {canEdit && (
                      <button onClick={(e) => { e.stopPropagation(); deleteMapping(m.id); }}
                        className="opacity-0 group-hover:opacity-100 transition-opacity ml-2"
                        style={{ color: S.textDim }}
                        onMouseEnter={(e) => e.currentTarget.style.color = "#e07070"}
                        onMouseLeave={(e) => e.currentTarget.style.color = S.textDim}>
                        <Trash2 size={15} />
                      </button>
                    )}
                  </div>
                  <div className="flex items-center gap-3 mt-4 text-xs" style={{ color: S.textDim }}>
                    <span>{m.field_count || 0} Felder</span>
                    {m.target_type && (
                      <span className="px-1.5 py-0.5 rounded font-mono"
                        style={{ backgroundColor: "rgba(255,255,255,0.04)", color: tColor[m.target_type] || S.textDim }}>
                        → {tLabel[m.target_type] || m.target_type}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1 mt-3 text-xs opacity-0 group-hover:opacity-100 transition-opacity" style={{ color: S.accent }}>
                    <span>Mapping öffnen</span><ChevronRight size={11} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        {tab === "ftp" && (
          <FtpPanel projectId={activeProject?.id ?? null} datasets={datasets} canEdit={canEdit} />
        )}
        {tab === "rest" && (
          <RestApiPanel projectId={activeProject?.id ?? null} datasets={datasets} canEdit={canEdit} />
        )}

        {tab === "pipelines" && (
          <PipelinesPanel projectId={activeProject?.id ?? null} canEdit={canEdit} />
        )}
        {tab === "monitoring" && (
          <MonitoringPanel />
        )}
        {tab === "templates" && (
          <TemplatesPanel projectId={activeProject?.id ?? null} canEdit={canEdit} />
        )}
        {tab === "reports" && (
          <ReportsPanel projectId={activeProject?.id ?? null} canEdit={canEdit} />
        )}
        {tab === "scheduler" && (
          <SchedulerPanel mappings={mappings} projectId={activeProject?.id ?? null} canEdit={canEdit} />
        )}
        {tab === "dispatcher" && (
          <DispatcherPanel projectId={activeProject?.id ?? null} canEdit={canEdit} />
        )}
        {tab === "exports" && (
          <ExportsPanel projectId={activeProject?.id ?? null} />
        )}
        
      </main>

      {/* ── Overlays ── */}
      <ConfirmModal modal={confirmModal} onClose={() => setConfirmModal(null)} />
      {selected && (
        <DataExplorer
          dataset={selected}
          onClose={() => setSelected(null)}
          onColumnTypesChange={(colName, newType) => {
            // Lokaler State-Update damit andere Panels sofort die neuen Typen sehen
            setSelected(prev => prev ? {
              ...prev,
              column_types: {
                ...(prev.column_types || {}),
                [colName]: { ...(prev.column_types?.[colName] || {}), type: newType },
              },
            } : prev);
          }}
        />
      )}
      {showWizard && (
        <NewDatasetWizard
          projectId={activeProject?.id ?? null}
          onDone={() => { setShowWizard(false); loadDatasets(); }}
          onCancel={() => setShowWizard(false)} />
      )}
      {showManualCreate && (
        <ManualDatasetModal
          projectId={activeProject?.id ?? null}
          onDone={() => { setShowManualCreate(false); loadDatasets(); }}
          onCancel={() => setShowManualCreate(false)} />
      )}
      {configuring && (
        <XmlConfigurator dataset={configuring}
          onDone={() => { setConfiguring(null); loadDatasets(); }}
          onCancel={() => setConfiguring(null)} />
      )}
      {editingRows && (
        <DatasetRowEditor
          dataset={editingRows}
          onClose={() => setEditingRows(null)}
          onSaved={() => { setEditingRows(null); loadDatasets(); }}
        />
      )}

      {editingDataset && (
        <EditDatasetModal dataset={editingDataset}
          onDone={() => { setEditingDataset(null); loadDatasets(); }}
          onCancel={() => setEditingDataset(null)} />
      )}
      {showNewProject && (
        <ProjectModal onDone={() => { setShowNewProject(false); loadProjects(); }} onCancel={() => setShowNewProject(false)} />
      )}
      {editingProject && (
        <ProjectModal project={editingProject}
          onDone={() => { setEditingProject(null); loadProjects(); }}
          onCancel={() => setEditingProject(null)} />
      )}
      {sharingProject && <ShareProjectModal project={sharingProject} onClose={() => setSharingProject(null)} />}
    </div>
  );
}
