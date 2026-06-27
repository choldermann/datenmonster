import { useState, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Save, Play, Loader2 } from "lucide-react";
import api from "../api/client";

const S = {
  bgMain: "var(--bg-main)", bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)",
  border: "var(--border)", textMain: "var(--text-main)", textBright: "var(--text-bright)",
  textDim: "var(--text-dim)", accent: "var(--accent)",
};

export default function FormEditor() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [form, setForm] = useState(null);
  const [name, setName] = useState("Neues Formular");
  const [saving, setSaving] = useState(false);
  const [savedToast, setSavedToast] = useState(false);

  useEffect(() => {
    if (id && id !== "new") {
      api.get(`/api/forms/${id}`).then(({ data }) => {
        setForm(data);
        setName(data.name);
      });
    }
  }, [id]);

  const save = async () => {
    setSaving(true);
    try {
      const payload = { name, schema: form?.schema || { fields: [], layout: [], actions: [], widgets: [] } };
      if (id && id !== "new") {
        const { data } = await api.put(`/api/forms/${id}`, payload);
        setForm(data);
      } else {
        const { data } = await api.post("/api/forms/", payload);
        navigate(`/forms/${data.id}`, { replace: true });
        setForm(data);
      }
      setSavedToast(true);
      setTimeout(() => setSavedToast(false), 2500);
    } finally { setSaving(false); }
  };

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column", backgroundColor: S.bgMain, color: S.textMain }}>

      {/* Toolbar */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 16px",
        borderBottom: `1px solid ${S.border}`, backgroundColor: S.bgCard, flexShrink: 0 }}>
        <button onClick={() => navigate("/dashboard")}
          style={{ display: "flex", alignItems: "center", gap: 5, background: "none", border: "none",
            color: S.textDim, cursor: "pointer", fontSize: 12 }}>
          <ArrowLeft size={14} /> Dashboard
        </button>
        <div style={{ width: 1, height: 20, backgroundColor: S.border }} />
        <input value={name} onChange={e => setName(e.target.value)}
          style={{ flex: 1, background: "none", border: "none", color: S.textBright,
            fontSize: 14, fontWeight: 600, outline: "none" }} />
        <div style={{ display: "flex", gap: 8 }}>
          {id && id !== "new" && (
            <button onClick={() => navigate(`/forms/${id}/run`)}
              style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 12px", borderRadius: 6,
                backgroundColor: "rgba(110,231,183,0.12)", border: "1px solid rgba(110,231,183,0.35)",
                color: "#6ee7b7", cursor: "pointer", fontSize: 12, fontWeight: 600 }}>
              <Play size={12} /> Ausführen
            </button>
          )}
          <button onClick={save} disabled={saving}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 12px", borderRadius: 6,
              backgroundColor: "rgba(252,228,153,0.12)", border: "1px solid rgba(252,228,153,0.35)",
              color: S.accent, cursor: saving ? "wait" : "pointer", fontSize: 12, fontWeight: 600 }}>
            {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
            {savedToast ? "Gespeichert ✓" : "Speichern"}
          </button>
        </div>
      </div>

      {/* Placeholder Canvas */}
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
        flexDirection: "column", gap: 16, color: S.textDim }}>
        <div style={{ fontSize: 40, opacity: 0.15 }}>⬜</div>
        <p style={{ fontSize: 14, fontWeight: 600, color: S.textDim }}>Form Builder</p>
        <p style={{ fontSize: 11, color: S.textDim, textAlign: "center", maxWidth: 360, lineHeight: 1.6 }}>
          Drag &amp; Drop Canvas für Formularfelder, Aktionen und Visualisierungen.<br />
          Kommt in Phase 2.
        </p>
        <div style={{ fontSize: 10, color: S.textDim, opacity: 0.6, fontFamily: "monospace",
          backgroundColor: S.bgCard, padding: "8px 14px", borderRadius: 6, border: `1px solid ${S.border}` }}>
          Schema: {JSON.stringify(form?.schema || {}, null, 2).slice(0, 120)}…
        </div>
      </div>
    </div>
  );
}
