import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Pencil, Trash2, Play, FileText } from "lucide-react";
import api from "../../../api/client";
import { S } from "../constants";

export default function FormsPanel({ projectId, canEdit }) {
  const navigate = useNavigate();
  const [forms, setForms] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/api/forms/", { params: projectId ? { project_id: projectId } : {} });
      setForms(data || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [projectId]);

  const createForm = async () => {
    try {
      const { data } = await api.post("/api/forms/", {
        name: "Neues Formular",
        project_id: projectId || null,
      });
      navigate(`/forms/${data.id}`);
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    }
  };

  const deleteForm = async (id, name) => {
    if (!window.confirm(`Formular "${name}" löschen?`)) return;
    await api.delete(`/api/forms/${id}`);
    load();
  };

  if (loading) return (
    <div style={{ padding: 40, textAlign: "center", color: S.textDim, fontSize: 12 }}>Lädt…</div>
  );

  return (
    <div style={{ padding: 20, maxWidth: 900 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <div>
          <h2 style={{ fontSize: 16, fontWeight: 700, color: S.textBright, margin: 0 }}>Formulare</h2>
          <p style={{ fontSize: 11, color: S.textDim, marginTop: 4 }}>
            Eingabemasken → Mapping-Ausführung → Visualisierung
          </p>
        </div>
        {canEdit && (
          <button onClick={createForm}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 14px", borderRadius: 6,
              backgroundColor: "rgba(252,228,153,0.15)", border: "1px solid rgba(252,228,153,0.4)",
              color: "var(--accent)", cursor: "pointer", fontSize: 12, fontWeight: 600 }}>
            <Plus size={13} /> Neues Formular
          </button>
        )}
      </div>

      {forms.length === 0 ? (
        <div style={{ textAlign: "center", padding: "60px 0" }}>
          <FileText size={40} style={{ color: S.textDim, opacity: 0.3, marginBottom: 12 }} />
          <p style={{ color: S.textDim, fontSize: 12, marginBottom: 16 }}>Noch keine Formulare erstellt.</p>
          {canEdit && (
            <button onClick={createForm}
              style={{ padding: "8px 18px", borderRadius: 6, backgroundColor: "rgba(252,228,153,0.15)",
                border: "1px solid rgba(252,228,153,0.4)", color: "var(--accent)",
                cursor: "pointer", fontSize: 12, fontWeight: 600 }}>
              Erstes Formular erstellen
            </button>
          )}
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 12 }}>
          {forms.map((f) => {
            const schema = f.schema || {};
            const fieldCount = (schema.fields || []).length;
            const actionCount = (schema.actions || []).length;
            const widgetCount = (schema.widgets || []).length;
            return (
              <div key={f.id}
                style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`, borderRadius: 8,
                  padding: "14px 16px", display: "flex", flexDirection: "column", gap: 8,
                  transition: "border-color 0.15s" }}
                onMouseEnter={e => e.currentTarget.style.borderColor = "rgba(252,228,153,0.3)"}
                onMouseLeave={e => e.currentTarget.style.borderColor = S.border}>

                <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{ fontSize: 13, fontWeight: 600, color: S.textBright, margin: 0,
                      overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {f.name}
                    </p>
                    <p style={{ fontSize: 10, color: S.textDim, margin: "3px 0 0" }}>
                      v{f.version} · {new Date(f.updated_at).toLocaleDateString("de-DE")}
                    </p>
                  </div>
                  <div style={{ display: "flex", gap: 4, flexShrink: 0, marginLeft: 8 }}>
                    <button onClick={() => navigate(`/forms/${f.id}/run`)} title="Formular ausführen"
                      style={{ width: 28, height: 28, display: "flex", alignItems: "center", justifyContent: "center",
                        borderRadius: 5, border: "1px solid rgba(110,231,183,0.3)",
                        backgroundColor: "rgba(110,231,183,0.08)", color: "#6ee7b7", cursor: "pointer" }}
                      onMouseEnter={e => e.currentTarget.style.backgroundColor = "rgba(110,231,183,0.18)"}
                      onMouseLeave={e => e.currentTarget.style.backgroundColor = "rgba(110,231,183,0.08)"}>
                      <Play size={11} />
                    </button>
                    {canEdit && (
                      <>
                        <button onClick={() => navigate(`/forms/${f.id}`)} title="Bearbeiten"
                          style={{ width: 28, height: 28, display: "flex", alignItems: "center", justifyContent: "center",
                            borderRadius: 5, border: `1px solid ${S.border}`,
                            backgroundColor: "transparent", color: S.textDim, cursor: "pointer" }}
                          onMouseEnter={e => e.currentTarget.style.color = S.textBright}
                          onMouseLeave={e => e.currentTarget.style.color = S.textDim}>
                          <Pencil size={11} />
                        </button>
                        <button onClick={() => deleteForm(f.id, f.name)} title="Löschen"
                          style={{ width: 28, height: 28, display: "flex", alignItems: "center", justifyContent: "center",
                            borderRadius: 5, border: "1px solid transparent",
                            backgroundColor: "transparent", color: S.textDim, cursor: "pointer" }}
                          onMouseEnter={e => { e.currentTarget.style.color = "#e07070"; e.currentTarget.style.borderColor = "rgba(224,112,112,0.3)"; }}
                          onMouseLeave={e => { e.currentTarget.style.color = S.textDim; e.currentTarget.style.borderColor = "transparent"; }}>
                          <Trash2 size={11} />
                        </button>
                      </>
                    )}
                  </div>
                </div>

                <div style={{ display: "flex", gap: 8 }}>
                  {[
                    { label: `${fieldCount} Felder`, color: "#fb923c" },
                    { label: `${actionCount} Aktionen`, color: "#38bdf8" },
                    { label: `${widgetCount} Widgets`, color: "#a78bfa" },
                  ].map(({ label, color }) => (
                    <span key={label} style={{ fontSize: 9, padding: "2px 7px", borderRadius: 10,
                      backgroundColor: `${color}18`, border: `1px solid ${color}33`, color }}>
                      {label}
                    </span>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
