import { useState, useEffect, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Save, Loader2, Globe, GlobeLock, Link, Eye, EyeOff } from "lucide-react";
import api from "../api/client";
import { useProject } from "../context/ProjectContext";
import FieldPalette from "../components/forms/FieldPalette";
import FormCanvas from "../components/forms/FormCanvas";
import FieldProperties from "../components/forms/FieldProperties";
import ActionsEditor from "../components/forms/ActionsEditor";
import WidgetsEditor from "../components/forms/WidgetsEditor";
import FormPreview from "../components/forms/FormPreview";

const S = {
  bgMain: "var(--bg-main)", bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)",
  border: "var(--border)", textMain: "var(--text-main)", textBright: "var(--text-bright)",
  textDim: "var(--text-dim)", accent: "var(--accent)",
};

const TABS = [
  { id: "fields",  label: "Felder" },
  { id: "actions", label: "Aktionen" },
  { id: "widgets", label: "Widgets" },
];

export default function FormEditor() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { activeProject } = useProject();
  const projectId = activeProject?.id ?? null;

  const [form, setForm]           = useState(null);
  const [name, setName]           = useState("Neues Formular");
  const [schema, setSchema]       = useState({ fields: [], layout: [], actions: [], widgets: [] });
  const [slug, setSlug]           = useState("");
  const [published, setPublished] = useState(false);
  const [portalConfig, setPortalConfig] = useState({});
  const [saving, setSaving]       = useState(false);
  const [savedToast, setSavedToast]   = useState(false);
  const [showPublishPanel, setShowPublishPanel] = useState(false);
  const [activeTab, setActiveTab] = useState("fields");
  const [selectedFieldId, setSelectedFieldId]   = useState(null);
  const [showPreview, setShowPreview] = useState(false);

  // Load
  useEffect(() => {
    if (id && id !== "new") {
      api.get(`/api/forms/${id}`).then(({ data }) => {
        setForm(data);
        setName(data.name);
        setSlug(data.slug || "");
        setPublished(data.published || false);
        setPortalConfig(data.portal_config || {});
        setSchema(data.schema || { fields: [], layout: [], actions: [], widgets: [] });
      });
    }
  }, [id]);

  // Derived
  const fields  = schema.fields  || [];
  const actions = schema.actions || [];
  const widgets = schema.widgets || [];
  const selectedField = fields.find(f => f.id === selectedFieldId) || null;

  const setFields = useCallback((next) => {
    setSchema(s => ({ ...s, fields: typeof next === "function" ? next(s.fields || []) : next }));
  }, []);

  const setActions = useCallback((next) => {
    setSchema(s => ({ ...s, actions: typeof next === "function" ? next(s.actions || []) : next }));
  }, []);

  const setWidgets = useCallback((next) => {
    setSchema(s => ({ ...s, widgets: typeof next === "function" ? next(s.widgets || []) : next }));
  }, []);

  const updateSelectedField = (updated) => {
    setFields(prev => prev.map(f => f.id === updated.id ? updated : f));
  };

  // Save
  const save = async () => {
    setSaving(true);
    try {
      const payload = { name, schema, slug: slug || undefined, published, portal_config: portalConfig };
      if (id && id !== "new") {
        const { data } = await api.put(`/api/forms/${id}`, payload);
        setForm(data); setSlug(data.slug || ""); setPublished(data.published || false);
      } else {
        const { data } = await api.post("/api/forms/", { name, project_id: projectId });
        navigate(`/forms/${data.id}`, { replace: true });
        setForm(data); setSlug(data.slug || "");
      }
      setSavedToast(true);
      setTimeout(() => setSavedToast(false), 2000);
    } finally { setSaving(false); }
  };

  const togglePublish = async () => {
    const next = !published;
    setPublished(next);
    if (id && id !== "new") await api.put(`/api/forms/${id}`, { published: next });
  };

  const appUrl = slug ? `/app/${slug}` : null;

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column",
      backgroundColor: S.bgMain, color: S.textMain }}>

      {/* ── Toolbar ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 12px",
        borderBottom: `1px solid ${S.border}`, backgroundColor: S.bgCard,
        flexShrink: 0, minHeight: 44 }}>
        <button onClick={() => navigate("/dashboard")}
          style={{ display: "flex", alignItems: "center", gap: 4, background: "none",
            border: "none", color: S.textDim, cursor: "pointer", fontSize: 11, flexShrink: 0 }}>
          <ArrowLeft size={13} /> Dashboard
        </button>
        <div style={{ width: 1, height: 16, backgroundColor: S.border, flexShrink: 0 }} />
        <input value={name} onChange={e => setName(e.target.value)}
          style={{ flex: 1, background: "none", border: "none", color: S.textBright,
            fontSize: 13, fontWeight: 700, outline: "none", minWidth: 0 }} />

        {/* Tabs */}
        <div style={{ display: "flex", gap: 2, flexShrink: 0 }}>
          {TABS.map(t => (
            <button key={t.id} onClick={() => setActiveTab(t.id)}
              style={{ padding: "4px 10px", borderRadius: 5, border: "none",
                backgroundColor: activeTab === t.id ? "rgba(252,228,153,0.12)" : "transparent",
                color: activeTab === t.id ? S.accent : S.textDim,
                fontSize: 11, fontWeight: activeTab === t.id ? 700 : 400, cursor: "pointer" }}>
              {t.label}
            </button>
          ))}
        </div>

        <div style={{ width: 1, height: 16, backgroundColor: S.border, flexShrink: 0 }} />

        <div style={{ display: "flex", gap: 5, alignItems: "center", flexShrink: 0 }}>
          {/* Preview */}
          {id && id !== "new" && (
            <button onClick={() => setShowPreview(true)} title="Vorschau"
              style={{ display: "flex", alignItems: "center", gap: 4, padding: "4px 9px",
                borderRadius: 5, border: `1px solid ${S.border}`, backgroundColor: "transparent",
                color: S.textDim, cursor: "pointer", fontSize: 11 }}>
              <Eye size={11} /> Vorschau
            </button>
          )}

          {/* Publish Toggle */}
          {id && id !== "new" && (
            <>
              <button onClick={togglePublish}
                style={{ display: "flex", alignItems: "center", gap: 4, padding: "4px 9px",
                  borderRadius: 5, border: `1px solid ${published ? "rgba(110,231,183,0.4)" : S.border}`,
                  backgroundColor: published ? "rgba(110,231,183,0.08)" : "transparent",
                  color: published ? "#6ee7b7" : S.textDim, cursor: "pointer", fontSize: 11, fontWeight: 600 }}>
                {published ? <Globe size={11} /> : <GlobeLock size={11} />}
                {published ? "Veröffentlicht" : "Entwurf"}
              </button>
              <button onClick={() => setShowPublishPanel(p => !p)} title="Portal-Einstellungen"
                style={{ display: "flex", alignItems: "center", padding: "4px 6px",
                  borderRadius: 5, border: `1px solid ${showPublishPanel ? S.accent : S.border}`,
                  backgroundColor: "transparent", color: showPublishPanel ? S.accent : S.textDim,
                  cursor: "pointer" }}>
                <Link size={11} />
              </button>
            </>
          )}

          {/* Save */}
          <button onClick={save} disabled={saving}
            style={{ display: "flex", alignItems: "center", gap: 4, padding: "4px 12px",
              borderRadius: 5, backgroundColor: "rgba(252,228,153,0.1)",
              border: "1px solid rgba(252,228,153,0.35)", color: S.accent,
              cursor: saving ? "wait" : "pointer", fontSize: 11, fontWeight: 700 }}>
            {saving ? <Loader2 size={11} /> : <Save size={11} />}
            {savedToast ? "✓ Gespeichert" : "Speichern"}
          </button>
        </div>
      </div>

      {/* ── Publish Panel ── */}
      {showPublishPanel && (
        <div style={{ flexShrink: 0, borderBottom: `1px solid ${S.border}`,
          backgroundColor: S.bgCard, padding: "10px 14px" }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 16, alignItems: "flex-end" }}>
            <div>
              <label style={{ display: "block", fontSize: 9, fontWeight: 700, color: S.textDim,
                marginBottom: 4, textTransform: "uppercase" }}>URL-Slug</label>
              <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <span style={{ fontSize: 10, color: S.textDim }}>/app/</span>
                <input value={slug} onChange={e => setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))}
                  placeholder="mein-formular"
                  style={{ backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4,
                    color: S.textMain, fontSize: 11, padding: "4px 8px", outline: "none", width: 160 }} />
              </div>
            </div>
            <div>
              <label style={{ display: "block", fontSize: 9, fontWeight: 700, color: S.textDim,
                marginBottom: 4, textTransform: "uppercase" }}>Beschreibung</label>
              <input value={portalConfig.description || ""}
                onChange={e => setPortalConfig(p => ({ ...p, description: e.target.value }))}
                placeholder="Kurzbeschreibung für die Portal-Übersicht"
                style={{ backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4,
                  color: S.textMain, fontSize: 11, padding: "4px 8px", outline: "none", width: 260 }} />
            </div>
            <div>
              <label style={{ display: "block", fontSize: 9, fontWeight: 700, color: S.textDim,
                marginBottom: 4, textTransform: "uppercase" }}>Icon</label>
              <input value={portalConfig.icon || ""}
                onChange={e => setPortalConfig(p => ({ ...p, icon: e.target.value }))}
                placeholder="📊"
                style={{ backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4,
                  color: S.textMain, fontSize: 16, padding: "2px 8px", outline: "none", width: 52, textAlign: "center" }} />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {[
                { k: "allow_download",   l: "Download erlaubt" },
                { k: "allow_manual_run", l: "Manueller Start" },
              ].map(({ k, l }) => (
                <label key={k} style={{ display: "flex", alignItems: "center", gap: 6,
                  cursor: "pointer", fontSize: 11, color: S.textMain }}>
                  <input type="checkbox"
                    checked={k === "allow_manual_run" ? (portalConfig[k] ?? true) : !!portalConfig[k]}
                    onChange={e => setPortalConfig(p => ({ ...p, [k]: e.target.checked }))}
                    style={{ width: 12, height: 12 }} />
                  {l}
                </label>
              ))}
            </div>
            {appUrl && published && (
              <a href={appUrl} target="_blank" rel="noreferrer"
                style={{ fontSize: 10, color: "#6ee7b7", textDecoration: "none",
                  display: "flex", alignItems: "center", gap: 4 }}>
                <Globe size={10} /> {window.location.origin}{appUrl}
              </a>
            )}
          </div>
        </div>
      )}

      {/* ── Main Area ── */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        {/* Left: Palette (nur im fields-Tab) */}
        {activeTab === "fields" && <FieldPalette />}

        {/* Center: Canvas oder Actions */}
        {activeTab === "fields" && (
          <FormCanvas
            fields={fields}
            selectedId={selectedFieldId}
            onSelect={setSelectedFieldId}
            onChange={setFields}
          />
        )}
        {activeTab === "actions" && (
          <ActionsEditor
            actions={actions}
            onChange={setActions}
            projectId={projectId}
          />
        )}
        {activeTab === "widgets" && (
          <WidgetsEditor
            widgets={widgets}
            actions={actions}
            onChange={setWidgets}
          />
        )}

        {/* Right: Properties (nur im fields-Tab, wenn ein Feld ausgewählt) */}
        {activeTab === "fields" && (
          <FieldProperties
            field={selectedField}
            actions={actions}
            onChange={updateSelectedField}
          />
        )}
      </div>

      {/* ── Preview Modal ── */}
      {showPreview && (
        <FormPreview
          schema={schema}
          formId={id}
          onClose={() => setShowPreview(false)}
        />
      )}
    </div>
  );
}
