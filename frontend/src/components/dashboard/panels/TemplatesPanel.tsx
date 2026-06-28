import { useState, useEffect } from "react";
import { Package, Play, Plus, Upload, Download, Trash2, ChevronDown, ChevronRight, Check, X, Loader2, AlertCircle } from "lucide-react";
import TemplateCreatorModal from "../modals/TemplateCreatorModal";
import api from "../../../api/client";
import { S } from "../constants";

const ACCENT = "var(--accent)";
const ACCENT_HEX = "#fce499";

function TemplateCard({ template, projectId, onInstalled }) {
  const [expanded, setExpanded] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [installed, setInstalled] = useState(false);
  const [error, setError] = useState("");
  const [config, setConfig] = useState({});

  const hasConfig = template.config_required?.length > 0;

  const handleInstall = async () => {
    setInstalling(true);
    setError("");
    try {
      await api.post("/api/templates/install", {
        template_id: template.template_id,
        project_id: projectId,
        config,
      });
      setInstalled(true);
      setTimeout(() => onInstalled(), 1000);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setInstalling(false);
    }
  };

  const iS = {
    backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4,
    color: S.textBright, fontSize: 11, padding: "5px 8px", outline: "none", width: "100%",
  };

  return (
    <div style={{ borderRadius: 8, border: `1px solid ${S.border}`, backgroundColor: S.bgCard, overflow: "hidden", marginBottom: 10 }}>
      {/* Header */}
      <div style={{ padding: "12px 16px", display: "flex", alignItems: "flex-start", gap: 12 }}>
        <div style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: `${ACCENT_HEX}15`, border: `1px solid ${ACCENT_HEX}33`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <Package size={16} style={{ color: ACCENT_HEX }} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <p style={{ fontSize: 13, fontWeight: 700, color: S.textBright, margin: 0 }}>{template.name}</p>
            <span style={{ fontSize: 9, padding: "2px 6px", borderRadius: 3, backgroundColor: `${ACCENT_HEX}15`, color: ACCENT_HEX, fontWeight: 700, textTransform: "uppercase" }}>
              v{template.version}
            </span>
            {template.author && (
              <span style={{ fontSize: 9, color: S.textDim }}>von {template.author}</span>
            )}
          </div>
          <p style={{ fontSize: 11, color: S.textDim, margin: "4px 0 0" }}>{template.description}</p>
        </div>
        <button
          onClick={() => setExpanded(v => !v)}
          style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 4, flexShrink: 0 }}>
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
      </div>

      {/* Details */}
      {expanded && (
        <div style={{ padding: "0 16px 16px", borderTop: `1px solid ${S.border}`, paddingTop: 12 }}>

          {/* Hinweise */}
          {template.hinweise?.length > 0 && (
            <div style={{ marginBottom: 14 }}>
              <p style={{ fontSize: 10, fontWeight: 700, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>Voraussetzungen</p>
              {template.hinweise.map((h, i) => (
                <div key={i} style={{ display: "flex", gap: 6, alignItems: "flex-start", marginBottom: 4 }}>
                  <AlertCircle size={11} style={{ color: ACCENT_HEX, flexShrink: 0, marginTop: 1 }} />
                  <p style={{ fontSize: 11, color: S.textDim, margin: 0 }}>{h}</p>
                </div>
              ))}
            </div>
          )}

          {/* Konfiguration */}
          {hasConfig && (
            <div style={{ marginBottom: 14 }}>
              <p style={{ fontSize: 10, fontWeight: 700, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>Konfiguration</p>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {template.config_required.map(cfg => (
                  <div key={cfg.key}>
                    <label style={{ fontSize: 10, color: S.textDim, display: "block", marginBottom: 3 }}>{cfg.label}</label>
                    {cfg.type === "db_connector" ? (
                      <p style={{ fontSize: 10, color: S.textDim, fontStyle: "italic" }}>
                        → Wird aus dem Mapping-Editor DB-Connector übernommen
                      </p>
                    ) : (
                      <input style={iS}
                        value={config[cfg.key] || cfg.default || ""}
                        onChange={e => setConfig(prev => ({ ...prev, [cfg.key]: e.target.value }))}
                        placeholder={cfg.default || cfg.label}
                      />
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Was wird angelegt */}
          <div style={{ marginBottom: 14, padding: "8px 10px", borderRadius: 5, backgroundColor: `${ACCENT_HEX}08`, border: `1px solid ${ACCENT_HEX}22` }}>
            <p style={{ fontSize: 10, fontWeight: 700, color: ACCENT_HEX, marginBottom: 4 }}>Was wird installiert:</p>
            <p style={{ fontSize: 10, color: S.textDim, margin: 0 }}>
              ✓ SQL-Datasets für Versendungen und Eingänge<br />
              ✓ Zwei Mappings → INSTAT XML<br />
              ✓ Pipeline mit monatlichem Trigger + E-Mail Benachrichtigung
            </p>
          </div>

          {/* Error */}
          {error && (
            <div style={{ marginBottom: 10, padding: "8px 10px", borderRadius: 5, backgroundColor: "rgba(224,112,112,0.1)", border: "1px solid rgba(224,112,112,0.3)" }}>
              <p style={{ fontSize: 11, color: "#e07070", margin: 0 }}>✗ {error}</p>
            </div>
          )}

          {/* Install Button */}
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button
            onClick={async () => {
              if (!window.confirm(`Template "${template.name}" und alle angelegten Datasets, Mappings und Pipelines löschen?`)) return;
              try {
                await api.delete(`/api/templates/${template.template_id}`);
                onInstalled(); // reload
              } catch(e) { alert(e.response?.data?.detail || e.message); }
            }}
            style={{ padding: "8px 12px", borderRadius: 6, backgroundColor: "rgba(224,112,112,0.08)", border: "1px solid rgba(224,112,112,0.25)", color: "#e07070", cursor: "pointer", fontSize: 12, display: "flex", alignItems: "center", gap: 5 }}
            onMouseEnter={e => e.currentTarget.style.backgroundColor = "rgba(224,112,112,0.15)"}
            onMouseLeave={e => e.currentTarget.style.backgroundColor = "rgba(224,112,112,0.08)"}>
            <Trash2 size={12} /> Löschen
          </button>
          <button
            onClick={async () => {
              const { data } = await api.get(`/api/templates/${template.template_id}/detail`);
              const blob = new Blob([JSON.stringify(data.content, null, 2)], { type: "application/json" });
              const url = URL.createObjectURL(blob);
              const a = document.createElement("a");
              a.href = url;
              a.download = `${template.template_id}.json`;
              a.click();
              URL.revokeObjectURL(url);
            }}
            style={{ padding: "8px 12px", borderRadius: 6, backgroundColor: "rgba(255,255,255,0.05)", border: `1px solid ${S.border}`, color: S.textDim, cursor: "pointer", fontSize: 12, display: "flex", alignItems: "center", gap: 5 }}>
            <Download size={12} /> Herunterladen
          </button>
          <button onClick={handleInstall} disabled={installing || installed}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 16px", borderRadius: 6, backgroundColor: installed ? "rgba(110,231,183,0.15)" : ACCENT_HEX, border: "none", color: installed ? "#6ee7b7" : "#111", cursor: installing || installed ? "default" : "pointer", fontSize: 12, fontWeight: 700 }}>
            {installing ? <Loader2 size={13} className="animate-spin" /> : installed ? <Check size={13} /> : <Play size={13} />}
            {installing ? "Wird installiert..." : installed ? "Installiert!" : "Template installieren"}
          </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function TemplatesPanel({ projectId, canEdit }) {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [creating, setCreating] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/api/templates/");
      setTemplates(data || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      await api.post("/api/templates/upload", form);
      load();
    } catch (err) {
      alert(err.response?.data?.detail || err.message);
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const categories = [...new Set(templates.map(t => t.category || "general"))];

  return (
    <div style={{ padding: 20, maxWidth: 900 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <div>
          <h2 style={{ fontSize: 16, fontWeight: 700, color: S.textBright, margin: 0 }}>Templates</h2>
          <p style={{ fontSize: 11, color: S.textDim, marginTop: 4 }}>Vorkonfigurierte ETL-Setups für typische Anwendungsfälle – ein Klick und alles ist eingerichtet.</p>
        </div>
        {canEdit && (
          <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => setCreating(true)}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 14px", borderRadius: 6, backgroundColor: "rgba(252,228,153,0.15)", border: "1px solid rgba(252,228,153,0.4)", color: ACCENT_HEX, cursor: "pointer", fontSize: 12, fontWeight: 600 }}>
            <Plus size={13} /> Template erstellen
          </button>
          <label style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 14px", borderRadius: 6, backgroundColor: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", color: S.textDim, cursor: "pointer", fontSize: 12, fontWeight: 600 }}>
            <Upload size={13} />
            {uploading ? "Lädt..." : "Template hochladen"}
            <input type="file" accept=".json" style={{ display: "none" }} onChange={handleUpload} />
          </label>
          </div>
        )}
      </div>

      {loading && <p style={{ color: S.textDim, fontSize: 12 }}>Lade Templates...</p>}

      {creating && (
        <TemplateCreatorModal
          projectId={projectId}
          onClose={() => setCreating(false)}
          onSaved={() => { setCreating(false); load(); }}
        />
      )}

      {!loading && templates.length === 0 && (
        <div style={{ textAlign: "center", padding: 60, border: `1px dashed ${S.border}`, borderRadius: 8 }}>
          <Package size={40} style={{ color: S.textDim, marginBottom: 12 }} />
          <p style={{ fontSize: 13, color: S.textDim, marginBottom: 6 }}>Noch keine Templates vorhanden</p>
          <p style={{ fontSize: 11, color: S.textDim }}>Lade ein Template-JSON hoch um loszulegen.</p>
        </div>
      )}

      {categories.map(cat => {
        const catTemplates = templates.filter(t => (t.category || "general") === cat);
        return (
          <div key={cat}>
            <p style={{ fontSize: 10, fontWeight: 700, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 10, marginTop: 16 }}>
              {cat === "jtl" ? "JTL WaWi" : cat === "general" ? "Allgemein" : cat}
            </p>
            {catTemplates.map(t => (
              <TemplateCard key={t.template_id} template={t} projectId={projectId} onInstalled={load} />
            ))}
          </div>
        );
      })}
    </div>
  );
}
