import { useState, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Save, Play, Loader2, Globe, GlobeLock, Link } from "lucide-react";
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
  const [slug, setSlug] = useState("");
  const [published, setPublished] = useState(false);
  const [portalConfig, setPortalConfig] = useState({});
  const [saving, setSaving] = useState(false);
  const [savedToast, setSavedToast] = useState(false);
  const [showPublishPanel, setShowPublishPanel] = useState(false);

  useEffect(() => {
    if (id && id !== "new") {
      api.get(`/api/forms/${id}`).then(({ data }) => {
        setForm(data);
        setName(data.name);
        setSlug(data.slug || "");
        setPublished(data.published || false);
        setPortalConfig(data.portal_config || {});
      });
    }
  }, [id]);

  const save = async () => {
    setSaving(true);
    try {
      const payload = {
        name,
        schema: form?.schema || { fields: [], layout: [], actions: [], widgets: [] },
        slug: slug || undefined,
        published,
        portal_config: portalConfig,
      };
      if (id && id !== "new") {
        const { data } = await api.put(`/api/forms/${id}`, payload);
        setForm(data); setSlug(data.slug || ""); setPublished(data.published || false);
      } else {
        const { data } = await api.post("/api/forms/", { name });
        navigate(`/forms/${data.id}`, { replace: true });
        setForm(data); setSlug(data.slug || "");
      }
      setSavedToast(true);
      setTimeout(() => setSavedToast(false), 2500);
    } finally { setSaving(false); }
  };

  const togglePublish = async () => {
    const next = !published;
    setPublished(next);
    if (id && id !== "new") {
      await api.put(`/api/forms/${id}`, { published: next });
    }
  };

  const appUrl = slug ? `/app/${slug}` : null;

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column",
      backgroundColor: S.bgMain, color: S.textMain }}>

      {/* Toolbar */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 14px",
        borderBottom: `1px solid ${S.border}`, backgroundColor: S.bgCard, flexShrink: 0 }}>
        <button onClick={() => navigate("/dashboard")}
          style={{ display: "flex", alignItems: "center", gap: 5, background: "none",
            border: "none", color: S.textDim, cursor: "pointer", fontSize: 12 }}>
          <ArrowLeft size={14} /> Dashboard
        </button>
        <div style={{ width: 1, height: 18, backgroundColor: S.border }} />
        <input value={name} onChange={e => setName(e.target.value)}
          style={{ flex: 1, background: "none", border: "none", color: S.textBright,
            fontSize: 14, fontWeight: 600, outline: "none" }} />
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>

          {/* Publish Toggle */}
          {id && id !== "new" && (
            <>
              <button onClick={togglePublish} title={published ? "Veröffentlicht — klicken zum Zurückziehen" : "Veröffentlichen"}
                style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 10px",
                  borderRadius: 6, border: `1px solid ${published ? "rgba(110,231,183,0.4)" : S.border}`,
                  backgroundColor: published ? "rgba(110,231,183,0.1)" : "transparent",
                  color: published ? "#6ee7b7" : S.textDim, cursor: "pointer", fontSize: 11, fontWeight: 600 }}>
                {published ? <Globe size={12} /> : <GlobeLock size={12} />}
                {published ? "Veröffentlicht" : "Entwurf"}
              </button>
              <button onClick={() => setShowPublishPanel(p => !p)} title="Portal-Einstellungen"
                style={{ display: "flex", alignItems: "center", gap: 4, padding: "5px 8px",
                  borderRadius: 6, border: `1px solid ${S.border}`, backgroundColor: "transparent",
                  color: S.textDim, cursor: "pointer", fontSize: 11 }}>
                <Link size={12} />
              </button>
            </>
          )}

          {id && id !== "new" && (
            <button onClick={() => navigate(`/forms/${id}/run`)}
              style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 10px",
                borderRadius: 6, backgroundColor: "rgba(110,231,183,0.08)",
                border: "1px solid rgba(110,231,183,0.3)", color: "#6ee7b7",
                cursor: "pointer", fontSize: 11, fontWeight: 600 }}>
              <Play size={11} /> Test
            </button>
          )}
          <button onClick={save} disabled={saving}
            style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 12px",
              borderRadius: 6, backgroundColor: "rgba(252,228,153,0.1)",
              border: "1px solid rgba(252,228,153,0.35)", color: S.accent,
              cursor: saving ? "wait" : "pointer", fontSize: 11, fontWeight: 600 }}>
            {saving ? <Loader2 size={11} /> : <Save size={11} />}
            {savedToast ? "✓" : "Speichern"}
          </button>
        </div>
      </div>

      {/* Publish-Panel */}
      {showPublishPanel && (
        <div style={{ flexShrink: 0, borderBottom: `1px solid ${S.border}`,
          backgroundColor: S.bgCard, padding: "12px 16px" }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 20, alignItems: "flex-end" }}>
            <div>
              <label style={{ display: "block", fontSize: 10, fontWeight: 600, color: S.textDim,
                marginBottom: 4, textTransform: "uppercase" }}>URL-Slug</label>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ fontSize: 11, color: S.textDim }}>/app/</span>
                <input value={slug} onChange={e => setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))}
                  placeholder="mein-formular"
                  style={{ backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 5,
                    color: S.textMain, fontSize: 12, padding: "4px 8px", outline: "none", width: 180 }} />
              </div>
            </div>
            <div>
              <label style={{ display: "block", fontSize: 10, fontWeight: 600, color: S.textDim,
                marginBottom: 4, textTransform: "uppercase" }}>Beschreibung (Portal)</label>
              <input value={portalConfig.description || ""} onChange={e => setPortalConfig(p => ({ ...p, description: e.target.value }))}
                placeholder="Kurze Beschreibung für die Portal-Übersicht"
                style={{ backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 5,
                  color: S.textMain, fontSize: 12, padding: "4px 8px", outline: "none", width: 280 }} />
            </div>
            <div>
              <label style={{ display: "block", fontSize: 10, fontWeight: 600, color: S.textDim,
                marginBottom: 4, textTransform: "uppercase" }}>Icon (Emoji)</label>
              <input value={portalConfig.icon || ""} onChange={e => setPortalConfig(p => ({ ...p, icon: e.target.value }))}
                placeholder="📊"
                style={{ backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 5,
                  color: S.textMain, fontSize: 14, padding: "4px 8px", outline: "none", width: 60,
                  textAlign: "center" }} />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {[
                { key: "allow_download",   label: "Download erlaubt" },
                { key: "allow_manual_run", label: "Manueller Start erlaubt" },
                { key: "is_homepage",      label: "Als Startseite" },
              ].map(({ key, label }) => (
                <label key={key} style={{ display: "flex", alignItems: "center", gap: 7,
                  cursor: "pointer", fontSize: 11, color: S.textMain }}>
                  <input type="checkbox"
                    checked={!!(key === "allow_manual_run" ? (portalConfig[key] ?? true) : portalConfig[key])}
                    onChange={e => setPortalConfig(p => ({ ...p, [key]: e.target.checked }))}
                    style={{ width: 13, height: 13 }} />
                  {label}
                </label>
              ))}
            </div>
            {appUrl && published && (
              <a href={appUrl} target="_blank" rel="noreferrer"
                style={{ fontSize: 11, color: "#6ee7b7", textDecoration: "none",
                  display: "flex", alignItems: "center", gap: 4 }}>
                <Globe size={11} /> {window.location.origin}{appUrl}
              </a>
            )}
          </div>
        </div>
      )}

      {/* Canvas-Platzhalter */}
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
        flexDirection: "column", gap: 14, color: S.textDim }}>
        <div style={{ fontSize: 40, opacity: 0.12 }}>⬜</div>
        <p style={{ fontSize: 13, fontWeight: 600, color: S.textDim }}>Form Builder Canvas</p>
        <p style={{ fontSize: 11, color: S.textDim, textAlign: "center", maxWidth: 360, lineHeight: 1.6 }}>
          Drag &amp; Drop für Formularfelder, Aktionen und Visualisierungen.<br />
          Kommt in Phase 2.
        </p>
        {form && (
          <div style={{ fontSize: 10, color: S.textDim, opacity: 0.6, fontFamily: "monospace",
            backgroundColor: S.bgCard, padding: "8px 14px", borderRadius: 6,
            border: `1px solid ${S.border}`, maxWidth: 500, overflowX: "auto" }}>
            slug: {form.slug} · v{form.version} · {form.published ? "✅ veröffentlicht" : "🔒 Entwurf"}
          </div>
        )}
      </div>
    </div>
  );
}
