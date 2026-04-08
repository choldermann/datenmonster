import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Pencil, Trash2, BarChart2 } from "lucide-react";
import api from "../../../api/client";
import { S } from "../constants";

export default function ReportsPanel({ projectId, canEdit }) {
  const navigate = useNavigate();
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/api/reports/", { params: projectId ? { project_id: projectId } : {} });
      setReports(data || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [projectId]);

  const deleteReport = async (id, name) => {
    if (!window.confirm(`Report "${name}" löschen?`)) return;
    await api.delete(`/api/reports/${id}`);
    load();
  };

  return (
    <div style={{ padding: 20, maxWidth: 900 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <div>
          <h2 style={{ fontSize: 16, fontWeight: 700, color: S.textBright, margin: 0 }}>Reports</h2>
          <p style={{ fontSize: 11, color: S.textDim, marginTop: 4 }}>Interaktive Dashboards mit Diagrammen, Tabellen und KPIs.</p>
        </div>
        {canEdit && (
          <button onClick={() => navigate("/reports/new")}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 14px", borderRadius: 6, backgroundColor: "rgba(252,228,153,0.15)", border: "1px solid rgba(252,228,153,0.4)", color: "var(--accent)", cursor: "pointer", fontSize: 12, fontWeight: 600 }}>
            <Plus size={13} /> Neuer Report
          </button>
        )}
      </div>

      {loading && <p style={{ color: S.textDim, fontSize: 12 }}>Lade...</p>}

      {!loading && reports.length === 0 && (
        <div style={{ textAlign: "center", padding: 60, border: `1px dashed ${S.border}`, borderRadius: 8 }}>
          <BarChart2 size={40} style={{ color: S.textDim, marginBottom: 12 }} />
          <p style={{ fontSize: 13, color: S.textDim, marginBottom: 6 }}>Noch keine Reports</p>
          <p style={{ fontSize: 11, color: S.textDim }}>Erstelle deinen ersten Report mit Charts, Tabellen und KPI-Kacheln.</p>
        </div>
      )}

      {reports.map(r => (
        <div key={r.id} style={{ marginBottom: 8, borderRadius: 8, border: `1px solid ${S.border}`, backgroundColor: S.bgCard, display: "flex", alignItems: "center", padding: "12px 16px", gap: 12, cursor: "pointer" }}
          onClick={() => navigate(`/reports/${r.id}`)}>
          <BarChart2 size={18} style={{ color: "var(--accent)", flexShrink: 0 }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <p style={{ fontSize: 12, fontWeight: 600, color: S.textBright, margin: 0 }}>{r.name}</p>
            <p style={{ fontSize: 10, color: S.textDim, margin: "3px 0 0" }}>
              {r.widgets?.length || 0} Widget{r.widgets?.length !== 1 ? "s" : ""}
              {r.updated_at && ` · Geändert: ${new Date(r.updated_at).toLocaleDateString("de-DE")}`}
            </p>
          </div>
          <div style={{ display: "flex", gap: 4 }} onClick={e => e.stopPropagation()}>
            <button onClick={() => navigate(`/reports/${r.id}`)}
              style={{ padding: "4px 8px", borderRadius: 4, border: `1px solid ${S.border}`, background: "none", color: S.textDim, cursor: "pointer" }}
              onMouseEnter={e => e.currentTarget.style.color = "var(--accent)"}
              onMouseLeave={e => e.currentTarget.style.color = S.textDim}>
              <Pencil size={11} />
            </button>
            {canEdit && (
              <button onClick={() => deleteReport(r.id, r.name)}
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
