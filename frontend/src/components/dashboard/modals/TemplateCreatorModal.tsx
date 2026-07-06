import { useState, useEffect } from "react";
import { X, Check, ChevronDown, ChevronRight, Save, Loader2, Database, GitBranch, Workflow } from "lucide-react";
import api from "../../../api/client";
import { S } from "../constants";

const ACCENT = "#fce499";

function TreeItem({ icon, label, sublabel, checked, onChange, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  const hasChildren = children && children.length > 0;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "5px 8px", borderRadius: 4, cursor: "pointer", backgroundColor: checked ? `${ACCENT}10` : "transparent" }}
        onClick={() => onChange(!checked)}>
        {hasChildren && (
          <span onClick={e => { e.stopPropagation(); setOpen(v => !v); }} style={{ color: S.textDim, flexShrink: 0 }}>
            {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </span>
        )}
        {!hasChildren && <span style={{ width: 12, flexShrink: 0 }} />}

        {/* Checkbox */}
        <div style={{ width: 14, height: 14, borderRadius: 3, border: `2px solid ${checked ? ACCENT : S.border}`, backgroundColor: checked ? ACCENT : "transparent", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}
          onClick={e => { e.stopPropagation(); onChange(!checked); }}>
          {checked && <Check size={9} color="#111" strokeWidth={3} />}
        </div>

        <span style={{ fontSize: 11, flexShrink: 0 }}>{icon}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{ fontSize: 11, color: S.textBright, margin: 0, fontWeight: 500 }}>{label}</p>
          {sublabel && <p style={{ fontSize: 9, color: S.textDim, margin: 0 }}>{sublabel}</p>}
        </div>
      </div>
      {open && hasChildren && (
        <div style={{ paddingLeft: 20, borderLeft: `1px solid ${S.border}`, marginLeft: 14 }}>
          {children}
        </div>
      )}
    </div>
  );
}

export default function TemplateCreatorModal({ projectId, onClose, onSaved }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("general");
  const [version, setVersion] = useState("1.0");

  const [datasets, setDatasets] = useState([]);
  const [mappings, setMappings] = useState([]);
  const [pipelines, setPipelines] = useState([]);
  const [forms, setForms] = useState([]);
  const [reports, setReports] = useState([]);

  const [selectedDatasets, setSelectedDatasets] = useState(new Set());
  const [selectedMappings, setSelectedMappings] = useState(new Set());
  const [selectedPipelines, setSelectedPipelines] = useState(new Set());
  const [selectedForms, setSelectedForms] = useState(new Set());
  const [selectedReports, setSelectedReports] = useState(new Set());

  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const p = projectId ? `?project_id=${projectId}` : "";
    const params = projectId ? { params: { project_id: projectId } } : {};
    Promise.all([
      api.get(`/api/datasets/${p}`),
      api.get(`/api/mappings/${p}`),
      api.get(`/api/pipelines/${p}`),
      api.get(`/api/forms/`, params),
      api.get(`/api/reports/`, params),
    ]).then(([ds, ms, ps, fs, rs]) => {
      setDatasets(ds.data || []);
      setMappings(ms.data || []);
      setPipelines(ps.data || []);
      setForms(fs.data || []);
      setReports(rs.data || []);
    }).finally(() => setLoading(false));
  }, [projectId]);

  const toggle = (set, setFn, id) => {
    setFn(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleAll = (items, setFn, idKey = "id") => {
    setFn(prev => {
      const allSelected = items.every(i => prev.has(i[idKey]));
      if (allSelected) return new Set();
      return new Set(items.map(i => i[idKey]));
    });
  };

  const handleSave = async () => {
    if (!name.trim()) return;
    setSaving(true);
    try {
      const payload = {
        name,
        description,
        category,
        version,
        project_id: projectId,
        dataset_ids: [...selectedDatasets],
        mapping_ids: [...selectedMappings],
        pipeline_ids: [...selectedPipelines],
        form_ids: [...selectedForms],
        report_ids: [...selectedReports],
      };
      await api.post("/api/templates/create", payload);
      onSaved();
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  const totalSelected = selectedDatasets.size + selectedMappings.size + selectedPipelines.size + selectedForms.size + selectedReports.size;

  const iS = { backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, color: S.textBright, fontSize: 11, padding: "5px 8px", outline: "none", width: "100%" };
  const lS = { fontSize: 10, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", display: "block", marginBottom: 4 };

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 60, backgroundColor: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center" }} onClick={onClose}>
      <div style={{ width: 580, maxHeight: "88vh", display: "flex", flexDirection: "column", backgroundColor: S.bgCard, borderRadius: 10, border: `1px solid ${ACCENT}44`, boxShadow: "0 24px 64px rgba(0,0,0,0.6)" }} onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div style={{ padding: "14px 18px", borderBottom: `1px solid ${S.border}`, display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 16 }}>📦</span>
          <span style={{ fontSize: 14, fontWeight: 700, color: S.textBright, flex: 1 }}>Neues Template erstellen</span>
          <button onClick={onClose} style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer" }}><X size={14} /></button>
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: "16px 18px", display: "flex", flexDirection: "column", gap: 14 }}>

          {/* Metadaten */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <div style={{ gridColumn: "1 / -1" }}>
              <label style={lS}>Name *</label>
              <input style={iS} value={name} onChange={e => setName(e.target.value)} placeholder="z.B. JTL Intrastat Meldung" autoFocus />
            </div>
            <div style={{ gridColumn: "1 / -1" }}>
              <label style={lS}>Beschreibung</label>
              <textarea style={{ ...iS, resize: "vertical", minHeight: 60, fontFamily: "inherit" }}
                value={description} onChange={e => setDescription(e.target.value)}
                placeholder="Was macht dieses Template? Für wen ist es gedacht?" />
            </div>
            <div>
              <label style={lS}>Kategorie</label>
              <select style={iS} value={category} onChange={e => setCategory(e.target.value)}>
                <option value="general">Allgemein</option>
                <option value="jtl">JTL WaWi</option>
                <option value="logistics">Logistik</option>
                <option value="finance">Finanzen / Buchhaltung</option>
                <option value="reporting">Reporting</option>
              </select>
            </div>
            <div>
              <label style={lS}>Version</label>
              <input style={iS} value={version} onChange={e => setVersion(e.target.value)} placeholder="1.0" />
            </div>
          </div>

          {/* Baumstruktur */}
          <div>
            <label style={lS}>Inhalte auswählen</label>
            <div style={{ border: `1px solid ${S.border}`, borderRadius: 6, backgroundColor: S.bgEl, padding: "8px 6px", maxHeight: 340, overflowY: "auto" }}>
              {loading && <p style={{ fontSize: 11, color: S.textDim, padding: "8px 10px" }}>Lade Projektinhalte...</p>}

              {/* Datasets */}
              {datasets.length > 0 && (
                <div style={{ marginBottom: 4 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 8px" }}>
                    <span style={{ fontSize: 13 }}>🗄️</span>
                    <span style={{ fontSize: 11, fontWeight: 700, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", flex: 1 }}>Datasets</span>
                    <button onClick={() => toggleAll(datasets, setSelectedDatasets)}
                      style={{ fontSize: 9, color: ACCENT, background: "none", border: "none", cursor: "pointer", padding: 0 }}>
                      {datasets.every(d => selectedDatasets.has(d.id)) ? "Alle ab" : "Alle an"}
                    </button>
                  </div>
                  {datasets.map(ds => (
                    <TreeItem key={ds.id} icon="📋" label={ds.name}
                      sublabel={`${ds.row_count?.toLocaleString() || 0} Zeilen · ${ds.file_type}`}
                      checked={selectedDatasets.has(ds.id)}
                      onChange={() => toggle(selectedDatasets, setSelectedDatasets, ds.id)} />
                  ))}
                </div>
              )}

              {/* Mappings */}
              {mappings.length > 0 && (
                <div style={{ marginBottom: 4 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 8px" }}>
                    <span style={{ fontSize: 13 }}>⚙️</span>
                    <span style={{ fontSize: 11, fontWeight: 700, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", flex: 1 }}>Mappings</span>
                    <button onClick={() => toggleAll(mappings, setSelectedMappings)}
                      style={{ fontSize: 9, color: ACCENT, background: "none", border: "none", cursor: "pointer", padding: 0 }}>
                      {mappings.every(m => selectedMappings.has(m.id)) ? "Alle ab" : "Alle an"}
                    </button>
                  </div>
                  {mappings.map(m => (
                    <TreeItem key={m.id} icon="🔄" label={m.name}
                      sublabel={`${m.canvas_nodes?.length || 0} Datasets · ${(m.targets || []).length} Ziele`}
                      checked={selectedMappings.has(m.id)}
                      onChange={() => toggle(selectedMappings, setSelectedMappings, m.id)} />
                  ))}
                </div>
              )}

              {/* Pipelines */}
              {pipelines.length > 0 && (
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 8px" }}>
                    <span style={{ fontSize: 13 }}>🔀</span>
                    <span style={{ fontSize: 11, fontWeight: 700, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", flex: 1 }}>Pipelines</span>
                    <button onClick={() => toggleAll(pipelines, setSelectedPipelines)}
                      style={{ fontSize: 9, color: ACCENT, background: "none", border: "none", cursor: "pointer", padding: 0 }}>
                      {pipelines.every(p => selectedPipelines.has(p.id)) ? "Alle ab" : "Alle an"}
                    </button>
                  </div>
                  {pipelines.map(p => (
                    <TreeItem key={p.id} icon="▶️" label={p.name}
                      sublabel={`${p.nodes?.length || 0} Nodes · ${p.connections?.length || 0} Verbindungen`}
                      checked={selectedPipelines.has(p.id)}
                      onChange={() => toggle(selectedPipelines, setSelectedPipelines, p.id)} />
                  ))}
                </div>
              )}

              {/* Formulare */}
              {forms.length > 0 && (
                <div style={{ marginBottom: 4 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 8px" }}>
                    <span style={{ fontSize: 13 }}>📝</span>
                    <span style={{ fontSize: 11, fontWeight: 700, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", flex: 1 }}>Formulare</span>
                    <button onClick={() => toggleAll(forms, setSelectedForms)}
                      style={{ fontSize: 9, color: ACCENT, background: "none", border: "none", cursor: "pointer", padding: 0 }}>
                      {forms.every(f => selectedForms.has(f.id)) ? "Alle ab" : "Alle an"}
                    </button>
                  </div>
                  {forms.map(f => (
                    <TreeItem key={f.id} icon="🧾" label={f.name}
                      sublabel={`${f.schema?.fields?.length || 0} Felder · ${f.schema?.actions?.length || 0} Aktionen`}
                      checked={selectedForms.has(f.id)}
                      onChange={() => toggle(selectedForms, setSelectedForms, f.id)} />
                  ))}
                </div>
              )}

              {/* Reports */}
              {reports.length > 0 && (
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 8px" }}>
                    <span style={{ fontSize: 13 }}>📊</span>
                    <span style={{ fontSize: 11, fontWeight: 700, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", flex: 1 }}>Reports</span>
                    <button onClick={() => toggleAll(reports, setSelectedReports)}
                      style={{ fontSize: 9, color: ACCENT, background: "none", border: "none", cursor: "pointer", padding: 0 }}>
                      {reports.every(r => selectedReports.has(r.id)) ? "Alle ab" : "Alle an"}
                    </button>
                  </div>
                  {reports.map(r => (
                    <TreeItem key={r.id} icon="📈" label={r.name}
                      sublabel={`${r.widgets?.length || 0} Widgets`}
                      checked={selectedReports.has(r.id)}
                      onChange={() => toggle(selectedReports, setSelectedReports, r.id)} />
                  ))}
                </div>
              )}

              {!loading && datasets.length === 0 && mappings.length === 0 && pipelines.length === 0 && forms.length === 0 && reports.length === 0 && (
                <p style={{ fontSize: 11, color: S.textDim, padding: "12px 10px", fontStyle: "italic" }}>
                  Keine Inhalte im Projekt gefunden.
                </p>
              )}
            </div>
          </div>

          {totalSelected > 0 && (
            <div style={{ fontSize: 10, color: ACCENT, padding: "5px 10px", borderRadius: 4, backgroundColor: `${ACCENT}10`, border: `1px solid ${ACCENT}22` }}>
              ✓ {totalSelected} Element{totalSelected !== 1 ? "e" : ""} ausgewählt
              {selectedDatasets.size > 0 && ` · ${selectedDatasets.size} Dataset${selectedDatasets.size !== 1 ? "s" : ""}`}
              {selectedMappings.size > 0 && ` · ${selectedMappings.size} Mapping${selectedMappings.size !== 1 ? "s" : ""}`}
              {selectedPipelines.size > 0 && ` · ${selectedPipelines.size} Pipeline${selectedPipelines.size !== 1 ? "s" : ""}`}
              {selectedForms.size > 0 && ` · ${selectedForms.size} Formular${selectedForms.size !== 1 ? "e" : ""}`}
              {selectedReports.size > 0 && ` · ${selectedReports.size} Report${selectedReports.size !== 1 ? "s" : ""}`}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ padding: "12px 18px", borderTop: `1px solid ${S.border}`, display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button onClick={onClose} style={{ padding: "6px 14px", borderRadius: 5, border: `1px solid ${S.border}`, background: "none", color: S.textDim, cursor: "pointer", fontSize: 12 }}>Abbrechen</button>
          <button onClick={handleSave} disabled={saving || !name.trim() || totalSelected === 0}
            style={{ padding: "6px 16px", borderRadius: 5, backgroundColor: ACCENT, border: "none", color: "#111", cursor: saving || !name.trim() || totalSelected === 0 ? "default" : "pointer", fontSize: 12, fontWeight: 700, opacity: !name.trim() || totalSelected === 0 ? 0.5 : 1, display: "flex", alignItems: "center", gap: 6 }}>
            {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
            {saving ? "Wird gespeichert..." : "Template speichern"}
          </button>
        </div>
      </div>
    </div>
  );
}
