import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Pencil, Trash2, Play, CheckCircle2, XCircle, Clock, Loader2 } from "lucide-react";
import api from "../../../api/client";
import { S } from "../constants";

export default function PipelinesPanel({ projectId, canEdit }) {
  const navigate = useNavigate();
  const [pipelines, setPipelines] = useState([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState({});

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/api/pipelines/", { params: projectId ? { project_id: projectId } : {} });
      setPipelines(data || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [projectId]);

  const deletePipeline = async (id, name) => {
    if (!window.confirm(`Pipeline "${name}" löschen?`)) return;
    await api.delete(`/api/pipelines/${id}`);
    load();
  };

  const runPipeline = async (id) => {
    setRunning(r => ({ ...r, [id]: true }));
    try {
      await api.post(`/api/pipelines/${id}/run`);
      load();
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    } finally {
      setRunning(r => ({ ...r, [id]: false }));
    }
  };

  const statusIcon = (status) => {
    if (status === "success") return <CheckCircle2 size={12} style={{ color: "#6ee7b7" }} />;
    if (status === "error") return <XCircle size={12} style={{ color: "#e07070" }} />;
    if (status === "warning") return <CheckCircle2 size={12} style={{ color: "#fce499" }} />;
    return <Clock size={12} style={{ color: S.textDim }} />;
  };

  return (
    <div style={{ padding: 20, maxWidth: 900 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <div>
          <h2 style={{ fontSize: 16, fontWeight: 700, color: S.textBright, margin: 0 }}>Pipelines</h2>
          <p style={{ fontSize: 11, color: S.textDim, marginTop: 4 }}>Visuelle Workflows – FTP → Bedingung → Mapping → Ausgabe</p>
        </div>
        {canEdit && (
          <button onClick={() => navigate("/pipelines/new")}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 14px", borderRadius: 6, backgroundColor: "rgba(252,228,153,0.15)", border: "1px solid rgba(252,228,153,0.4)", color: "var(--accent)", cursor: "pointer", fontSize: 12, fontWeight: 600 }}>
            <Plus size={13} /> Neue Pipeline
          </button>
        )}
      </div>

      {loading && <p style={{ color: S.textDim, fontSize: 12 }}>Lade...</p>}

      {!loading && pipelines.length === 0 && (
        <div style={{ textAlign: "center", padding: 60, border: `1px dashed ${S.border}`, borderRadius: 8 }}>
          <p style={{ fontSize: 36, marginBottom: 12 }}>🔀</p>
          <p style={{ fontSize: 13, color: S.textDim, marginBottom: 6 }}>Noch keine Pipelines</p>
          <p style={{ fontSize: 11, color: S.textDim }}>Erstelle eine Pipeline um Workflows visuell zu gestalten.</p>
        </div>
      )}

      {pipelines.map(p => (
        <div key={p.id} style={{ marginBottom: 8, borderRadius: 8, border: `1px solid ${S.border}`, backgroundColor: S.bgCard, display: "flex", alignItems: "center", padding: "12px 16px", gap: 12 }}>
          <div style={{ width: 8, height: 8, borderRadius: "50%", backgroundColor: p.active ? "#6ee7b7" : S.textDim, flexShrink: 0 }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <p style={{ fontSize: 12, fontWeight: 600, color: S.textBright, margin: 0 }}>{p.name}</p>
            <p style={{ fontSize: 10, color: S.textDim, margin: "3px 0 0" }}>
              {p.nodes?.length || 0} Nodes · {p.connections?.length || 0} Verbindungen
              {p.last_run_at && ` · Letzter Lauf: ${new Date(p.last_run_at).toLocaleString("de-DE")}`}
            </p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            {p.last_run_status && statusIcon(p.last_run_status)}
            <button onClick={() => runPipeline(p.id)} disabled={running[p.id]} title="Ausführen"
              style={{ padding: "4px 8px", borderRadius: 4, border: `1px solid ${S.border}`, background: "none", color: S.textDim, cursor: "pointer" }}
              onMouseEnter={e => e.currentTarget.style.color = "#6ee7b7"}
              onMouseLeave={e => e.currentTarget.style.color = S.textDim}>
              {running[p.id] ? <Loader2 size={11} className="animate-spin" /> : <Play size={11} />}
            </button>
            <button onClick={() => navigate(`/pipelines/${p.id}`)} title="Bearbeiten"
              style={{ padding: "4px 8px", borderRadius: 4, border: `1px solid ${S.border}`, background: "none", color: S.textDim, cursor: "pointer" }}
              onMouseEnter={e => e.currentTarget.style.color = S.accent}
              onMouseLeave={e => e.currentTarget.style.color = S.textDim}>
              <Pencil size={11} />
            </button>
            {canEdit && (
              <button onClick={() => deletePipeline(p.id, p.name)} title="Löschen"
                style={{ padding: "4px 8px", borderRadius: 4, border: `1px solid ${S.border}`, background: "none", color: S.textDim, cursor: "pointer" }}
                onMouseEnter={e => e.currentTarget.style.color = "#e07070"}
                onMouseLeave={e => e.currentTarget.style.color = S.textDim}>
                <Trash2 size={11} />
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
