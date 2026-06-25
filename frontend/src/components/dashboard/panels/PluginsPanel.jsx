import { useState, useEffect, useCallback } from "react";
import { Puzzle, CheckCircle, AlertCircle, Loader2, RefreshCw, Zap, Database, ArrowRightLeft, ChevronDown, ChevronUp } from "lucide-react";
import api from "../../../api/client";
import { S } from "../constants";

const CAP_COLOR = {
  source: { bg: "rgba(110,231,183,0.12)", text: "#6ee7b7", label: "Quelle" },
  target: { bg: "rgba(147,197,253,0.12)", text: "#93c5fd", label: "Ziel" },
  transformer: { bg: "rgba(251,191,36,0.12)", text: "#fbbf24", label: "Transform" },
  compliance: { bg: "rgba(249,168,212,0.12)", text: "#f9a8d4", label: "Compliance" },
  trigger: { bg: "rgba(196,181,253,0.12)", text: "#c4b5fd", label: "Trigger" },
};

function CapBadge({ cap }) {
  const c = CAP_COLOR[cap] || { bg: "rgba(255,255,255,0.06)", text: S.textDim, label: cap };
  return (
    <span style={{ fontSize: 9, padding: "2px 6px", borderRadius: 3, fontWeight: 700,
      textTransform: "uppercase", letterSpacing: "0.04em",
      backgroundColor: c.bg, color: c.text }}>
      {c.label}
    </span>
  );
}

function StatusDot({ status }) {
  const color = status === "active" ? "#6ee7b7" : status === "error" ? "#e07070" : "#6b7280";
  const label = status === "active" ? "Aktiv" : status === "error" ? "Fehler" : "Deaktiviert";
  return (
    <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10, color }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", backgroundColor: color, flexShrink: 0 }} />
      {label}
    </span>
  );
}

function TestModal({ plugin, onClose }) {
  const [config, setConfig] = useState({});
  const [result, setResult] = useState(null);
  const [testing, setTesting] = useState(false);

  const run = async () => {
    setTesting(true);
    setResult(null);
    try {
      const { data } = await api.post(`/api/plugins/${plugin.id}/test`, { config });
      setResult(data);
    } catch (e) {
      setResult({ ok: false, message: e.response?.data?.detail || e.message });
    } finally {
      setTesting(false);
    }
  };

  const iS = {
    backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4,
    color: S.textBright, fontSize: 11, padding: "5px 8px", outline: "none", width: "100%",
  };

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 200,
      backgroundColor: "rgba(0,0,0,0.75)", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div onClick={e => e.stopPropagation()} style={{ backgroundColor: S.bgCard,
        border: `1px solid ${S.border}`, borderRadius: 10, padding: 24, width: 480,
        boxShadow: "0 24px 60px rgba(0,0,0,0.7)" }}>
        <p style={{ fontSize: 14, fontWeight: 700, color: S.textBright, margin: "0 0 4px" }}>
          Verbindungstest · {plugin.name}
        </p>
        <p style={{ fontSize: 11, color: S.textDim, margin: "0 0 16px" }}>
          Konfiguration eingeben und Verbindung testen.
        </p>

        {(plugin.config_schema || []).map(field => (
          <div key={field.key} style={{ marginBottom: 10 }}>
            <label style={{ fontSize: 10, fontWeight: 600, color: S.textDim,
              textTransform: "uppercase", letterSpacing: "0.05em", display: "block", marginBottom: 4 }}>
              {field.label}{field.required && <span style={{ color: "#e07070" }}> *</span>}
            </label>
            {field.type === "select" ? (
              <select value={config[field.key] ?? field.default ?? ""} style={iS}
                onChange={e => setConfig(c => ({ ...c, [field.key]: e.target.value }))}>
                {(field.options || []).map(o => <option key={o} value={o}>{o}</option>)}
              </select>
            ) : (
              <input type={field.type === "number" ? "number" : "text"}
                placeholder={field.placeholder || field.default ?? ""}
                value={config[field.key] ?? ""}
                style={iS}
                onChange={e => setConfig(c => ({ ...c, [field.key]: e.target.value }))} />
            )}
          </div>
        ))}

        {result && (
          <div style={{ marginTop: 12, padding: "10px 12px", borderRadius: 6,
            backgroundColor: result.ok ? "rgba(110,231,183,0.08)" : "rgba(224,112,112,0.08)",
            border: `1px solid ${result.ok ? "rgba(110,231,183,0.3)" : "rgba(224,112,112,0.3)"}` }}>
            <p style={{ fontSize: 12, color: result.ok ? "#6ee7b7" : "#e07070", margin: 0 }}>
              {result.ok ? "✓ " : "✗ "}{result.message}
            </p>
          </div>
        )}

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 16 }}>
          <button onClick={onClose} style={{ padding: "7px 16px", borderRadius: 5,
            border: `1px solid ${S.border}`, background: "none", color: S.textDim, fontSize: 12, cursor: "pointer" }}>
            Schließen
          </button>
          <button onClick={run} disabled={testing} style={{ padding: "7px 18px", borderRadius: 5,
            border: "none", fontSize: 12, fontWeight: 700, cursor: testing ? "wait" : "pointer",
            backgroundColor: "var(--accent)", color: "#111", display: "flex", alignItems: "center", gap: 6,
            opacity: testing ? 0.7 : 1 }}>
            {testing ? <Loader2 size={13} className="animate-spin" /> : <Zap size={13} />}
            {testing ? "Teste..." : "Testen"}
          </button>
        </div>
      </div>
    </div>
  );
}

function PluginCard({ plugin }) {
  const [expanded, setExpanded] = useState(false);
  const [testing, setTesting] = useState(false);

  const hasConfig = (plugin.config_schema || []).length > 0;

  return (
    <div style={{ borderRadius: 8, border: `1px solid ${S.border}`,
      backgroundColor: S.bgCard, overflow: "hidden", marginBottom: 10 }}>
      <div style={{ padding: "14px 16px", display: "flex", alignItems: "flex-start", gap: 12 }}>
        {/* Icon */}
        <div style={{ width: 38, height: 38, borderRadius: 8, flexShrink: 0,
          backgroundColor: "rgba(252,228,153,0.08)", border: "1px solid rgba(252,228,153,0.2)",
          display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Puzzle size={16} style={{ color: "var(--accent)" }} />
        </div>

        {/* Info */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <p style={{ fontSize: 13, fontWeight: 700, color: S.textBright, margin: 0 }}>
              {plugin.name}
            </p>
            <span style={{ fontSize: 9, padding: "2px 6px", borderRadius: 3,
              backgroundColor: "rgba(255,255,255,0.05)", color: S.textDim, fontWeight: 700 }}>
              v{plugin.version}
            </span>
            {(plugin.capabilities || []).map(c => <CapBadge key={c} cap={c} />)}
            <StatusDot status={plugin.status || "active"} />
          </div>
          <p style={{ fontSize: 11, color: S.textDim, margin: "4px 0 0", lineHeight: 1.5 }}>
            {plugin.description}
          </p>
          {plugin.author && (
            <p style={{ fontSize: 10, color: S.textDim, margin: "2px 0 0", opacity: 0.6 }}>
              von {plugin.author} · {plugin.license}
            </p>
          )}
        </div>

        {/* Actions */}
        <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
          {hasConfig && (
            <button onClick={() => setTesting(true)}
              style={{ fontSize: 11, padding: "5px 12px", borderRadius: 5, cursor: "pointer",
                backgroundColor: "rgba(110,231,183,0.1)", border: "1px solid rgba(110,231,183,0.3)",
                color: "#6ee7b7", display: "flex", alignItems: "center", gap: 5 }}>
              <Zap size={11} /> Test
            </button>
          )}
          {(plugin.config_schema || []).length > 0 && (
            <button onClick={() => setExpanded(x => !x)}
              style={{ background: "none", border: "none", cursor: "pointer", color: S.textDim, padding: 4 }}>
              {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
          )}
        </div>
      </div>

      {/* Erweiterte Schema-Ansicht */}
      {expanded && (plugin.config_schema || []).length > 0 && (
        <div style={{ borderTop: `1px solid ${S.border}`, padding: "12px 16px", backgroundColor: S.bgEl }}>
          <p style={{ fontSize: 10, fontWeight: 600, color: S.textDim, textTransform: "uppercase",
            letterSpacing: "0.05em", margin: "0 0 8px" }}>Konfigurationsfelder</p>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
            {plugin.config_schema.map(f => (
              <div key={f.key} style={{ fontSize: 11, color: S.textMain }}>
                <span style={{ color: S.textDim }}>{f.key}</span>
                {f.required && <span style={{ color: "#e07070", marginLeft: 2 }}>*</span>}
                <span style={{ color: S.textDim, opacity: 0.5 }}> · {f.type}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {testing && <TestModal plugin={plugin} onClose={() => setTesting(false)} />}
    </div>
  );
}

function CapabilitySection({ title, icon: Icon, items, emptyText }) {
  if (!items?.length) return null;
  return (
    <div style={{ marginBottom: 24 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <Icon size={14} style={{ color: S.textDim }} />
        <p style={{ fontSize: 11, fontWeight: 600, color: S.textDim, textTransform: "uppercase",
          letterSpacing: "0.06em", margin: 0 }}>{title}</p>
        <span style={{ fontSize: 10, color: S.textDim, opacity: 0.5 }}>({items.length})</span>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {items.map(s => (
          <span key={s.id} style={{ fontSize: 11, padding: "4px 10px", borderRadius: 5,
            backgroundColor: S.bgEl, border: `1px solid ${S.border}`, color: S.textMain }}>
            {s.label}
            <span style={{ fontSize: 9, color: S.textDim, marginLeft: 6 }}>{s.id}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

export default function PluginsPanel() {
  const [plugins, setPlugins] = useState([]);
  const [capabilities, setCapabilities] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [{ data: pl }, { data: caps }] = await Promise.all([
        api.get("/api/plugins/"),
        api.get("/api/plugins/capabilities"),
      ]);
      setPlugins(Array.isArray(pl) ? pl : []);
      setCapabilities(caps);
    } catch (e) {
      console.error("Plugins laden fehlgeschlagen", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase",
            letterSpacing: "0.1em", color: "var(--accent)", margin: "0 0 4px" }}>
            Plugins
          </h1>
          <p style={{ fontSize: 12, color: S.textDim, margin: 0 }}>
            {plugins.length > 0
              ? `${plugins.length} Plugin${plugins.length !== 1 ? "s" : ""} installiert`
              : "Keine Plugins geladen"}
          </p>
        </div>
        <button onClick={load} style={{ display: "flex", alignItems: "center", gap: 6,
          fontSize: 11, padding: "6px 12px", borderRadius: 5, cursor: "pointer",
          background: "none", border: `1px solid ${S.border}`, color: S.textDim }}>
          <RefreshCw size={12} /> Aktualisieren
        </button>
      </div>

      {loading ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center",
          height: 120, color: S.textDim }}>
          <Loader2 size={18} className="animate-spin" style={{ marginRight: 8 }} /> Lade...
        </div>
      ) : plugins.length === 0 ? (
        <div style={{ textAlign: "center", padding: "48px 24px", color: S.textDim }}>
          <Puzzle size={32} style={{ margin: "0 auto 12px", opacity: 0.3 }} />
          <p style={{ fontSize: 13, margin: "0 0 4px" }}>Keine Plugins gefunden</p>
          <p style={{ fontSize: 11, opacity: 0.6, margin: 0 }}>
            Plugins in <code>backend/plugins/</code> ablegen und Backend neu starten.
          </p>
        </div>
      ) : (
        <>
          {/* Capability-Übersicht */}
          {capabilities && (
            <div style={{ marginBottom: 28, padding: "14px 16px", borderRadius: 8,
              backgroundColor: S.bgEl, border: `1px solid ${S.border}` }}>
              <CapabilitySection title="Datenquellen"
                icon={Database} items={capabilities.sources} />
              <CapabilitySection title="Datenziele"
                icon={ArrowRightLeft} items={capabilities.targets} />
            </div>
          )}

          {/* Plugin-Liste */}
          <div>
            {plugins.map(p => <PluginCard key={p.id} plugin={p} />)}
          </div>
        </>
      )}
    </div>
  );
}
