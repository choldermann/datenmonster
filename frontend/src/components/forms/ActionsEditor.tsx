import { useState, useEffect } from "react";
import { Plus, Trash2 } from "lucide-react";
import api from "../../api/client";

const S = {
  bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)", bgMain: "var(--bg-main)",
  border: "var(--border)", textMain: "var(--text-main)", textDim: "var(--text-dim)",
  textBright: "var(--text-bright)", accent: "var(--accent)",
};

const inp = {
  backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4,
  color: S.textMain, fontSize: 11, padding: "5px 8px", outline: "none",
};

export default function ActionsEditor({ actions, onChange, projectId }) {
  const [mappings, setMappings] = useState([]);
  const [pipelines, setPipelines] = useState([]);

  useEffect(() => {
    const p = projectId ? `?project_id=${projectId}` : "";
    api.get(`/api/mappings/${p}`).then(({ data }) => setMappings(Array.isArray(data) ? data : [])).catch(() => {});
    api.get(`/api/pipelines/${p}`).then(({ data }) => setPipelines(Array.isArray(data) ? data : [])).catch(() => {});
  }, [projectId]);

  const addAction = () => {
    const id = `a_${Math.random().toString(36).slice(2, 7)}`;
    onChange([...actions, { id, type: "run_mapping", mapping_id: null, pipeline_id: null, label: "Auswerten" }]);
  };

  const updateAction = (idx, patch) => {
    onChange(actions.map((a, i) => i === idx ? { ...a, ...patch } : a));
  };

  const removeAction = (idx) => {
    onChange(actions.filter((_, i) => i !== idx));
  };

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px", scrollbarWidth: "thin" }}>
      <div style={{ maxWidth: 680 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
          <div>
            <h2 style={{ fontSize: 14, fontWeight: 700, color: S.textBright, margin: 0 }}>Aktionen</h2>
            <p style={{ fontSize: 11, color: S.textDim, marginTop: 4 }}>
              Aktionen werden ausgeführt wenn ein Button gedrückt wird. Eine Aktion startet ein Mapping oder eine Pipeline.
            </p>
          </div>
          <button onClick={addAction}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 12px",
              borderRadius: 6, backgroundColor: "rgba(252,228,153,0.1)",
              border: "1px solid rgba(252,228,153,0.35)", color: S.accent,
              cursor: "pointer", fontSize: 11, fontWeight: 600 }}>
            <Plus size={12} /> Aktion hinzufügen
          </button>
        </div>

        {actions.length === 0 ? (
          <div style={{ textAlign: "center", padding: "48px 0", border: `1px dashed ${S.border}`,
            borderRadius: 10, color: S.textDim }}>
            <p style={{ fontSize: 13, marginBottom: 8 }}>Noch keine Aktionen</p>
            <p style={{ fontSize: 11, opacity: 0.7 }}>
              Aktionen verknüpfen Buttons mit Mappings.
            </p>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {actions.map((action, idx) => (
              <div key={action.id}
                style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`,
                  borderRadius: 8, padding: "14px 16px" }}>
                <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
                  {/* Label */}
                  <div style={{ flex: "0 0 150px" }}>
                    <label style={{ display: "block", fontSize: 9, fontWeight: 700,
                      textTransform: "uppercase", letterSpacing: "0.1em",
                      color: S.textDim, marginBottom: 4 }}>Button-Label</label>
                    <input value={action.label || ""} onChange={e => updateAction(idx, { label: e.target.value })}
                      placeholder="Auswerten" style={{ ...inp, width: "100%", boxSizing: "border-box" }} />
                  </div>
                  {/* Typ */}
                  <div style={{ flex: "0 0 130px" }}>
                    <label style={{ display: "block", fontSize: 9, fontWeight: 700,
                      textTransform: "uppercase", letterSpacing: "0.1em",
                      color: S.textDim, marginBottom: 4 }}>Aktionstyp</label>
                    <select value={action.type || "run_mapping"}
                      onChange={e => updateAction(idx, e.target.value === "run_pipeline"
                        ? { type: "run_pipeline", mapping_id: null }
                        : { type: "run_mapping", pipeline_id: null })}
                      style={{ ...inp, width: "100%", boxSizing: "border-box", cursor: "pointer" }}>
                      <option value="run_mapping">Mapping</option>
                      <option value="run_pipeline">Pipeline</option>
                    </select>
                  </div>
                  {/* Ziel: Mapping oder Pipeline */}
                  {action.type === "run_pipeline" ? (
                    <div style={{ flex: 1 }}>
                      <label style={{ display: "block", fontSize: 9, fontWeight: 700,
                        textTransform: "uppercase", letterSpacing: "0.1em",
                        color: S.textDim, marginBottom: 4 }}>Pipeline starten</label>
                      <select value={action.pipeline_id || ""} onChange={e => updateAction(idx, { pipeline_id: e.target.value ? parseInt(e.target.value) : null })}
                        style={{ ...inp, width: "100%", boxSizing: "border-box", cursor: "pointer" }}>
                        <option value="">— Pipeline auswählen —</option>
                        {pipelines.map(p => (
                          <option key={p.id} value={p.id}>{p.name}</option>
                        ))}
                      </select>
                    </div>
                  ) : (
                    <div style={{ flex: 1 }}>
                      <label style={{ display: "block", fontSize: 9, fontWeight: 700,
                        textTransform: "uppercase", letterSpacing: "0.1em",
                        color: S.textDim, marginBottom: 4 }}>Mapping ausführen</label>
                      <select value={action.mapping_id || ""} onChange={e => updateAction(idx, { mapping_id: e.target.value ? parseInt(e.target.value) : null })}
                        style={{ ...inp, width: "100%", boxSizing: "border-box", cursor: "pointer" }}>
                        <option value="">— Mapping auswählen —</option>
                        {mappings.map(m => (
                          <option key={m.id} value={m.id}>{m.name}</option>
                        ))}
                      </select>
                    </div>
                  )}
                  {/* Delete */}
                  <button onClick={() => removeAction(idx)}
                    style={{ marginTop: 20, color: S.textDim, background: "none", border: "none",
                      cursor: "pointer", padding: 4, flexShrink: 0 }}
                    onMouseEnter={e => e.currentTarget.style.color = "#e07070"}
                    onMouseLeave={e => e.currentTarget.style.color = S.textDim}>
                    <Trash2 size={13} />
                  </button>
                </div>

                <div style={{ marginTop: 8, padding: "6px 8px", backgroundColor: S.bgMain,
                  borderRadius: 4, fontSize: 9, color: S.textDim, fontFamily: "monospace" }}>
                  id: {action.id} · type: {action.type || "run_mapping"}
                  {action.type === "run_pipeline"
                    ? (action.pipeline_id && ` · pipeline_id: ${action.pipeline_id}`)
                    : (action.mapping_id && ` · mapping_id: ${action.mapping_id}`)}
                </div>
              </div>
            ))}
          </div>
        )}

        <div style={{ marginTop: 24, padding: "14px 16px", backgroundColor: S.bgCard,
          border: `1px solid ${S.border}`, borderRadius: 8 }}>
          <p style={{ fontSize: 10, fontWeight: 700, color: S.textDim, margin: "0 0 6px",
            textTransform: "uppercase", letterSpacing: "0.08em" }}>Zukünftige Aktionstypen</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {["E-Mail senden", "REST-Aufruf", "PDF erzeugen", "Plugin ausführen"].map(t => (
              <span key={t} style={{ fontSize: 9, padding: "2px 8px", borderRadius: 10,
                border: `1px dashed ${S.border}`, color: S.textDim, opacity: 0.5 }}>
                {t}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
