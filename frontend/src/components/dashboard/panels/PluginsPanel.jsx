import { useState, useEffect, useCallback } from "react";
import { Puzzle, CheckCircle, AlertCircle, Loader2, RefreshCw, Zap, Database, ArrowRightLeft,
  ChevronDown, ChevronUp, Container, Play, Square, Trash2, Plus, X } from "lucide-react";
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
  const color = status === "active" || status === "running" ? "#6ee7b7"
    : status === "error" ? "#e07070" : "#6b7280";
  const label = status === "active" ? "Aktiv"
    : status === "running" ? "Läuft"
    : status === "error" ? "Fehler"
    : status === "exited" ? "Gestoppt"
    : status === "starting" ? "Startet..."
    : "Gestoppt";
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
                placeholder={field.placeholder || (field.default ?? "")}
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
        <div style={{ width: 38, height: 38, borderRadius: 8, flexShrink: 0,
          backgroundColor: "rgba(252,228,153,0.08)", border: "1px solid rgba(252,228,153,0.2)",
          display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Puzzle size={16} style={{ color: "var(--accent)" }} />
        </div>

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

function CapabilitySection({ title, icon: Icon, items }) {
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

// ── Tier-2 Plugin Manager ─────────────────────────────────────────────────────

const CONTAINER_STATUS_COLOR = {
  running: "#6ee7b7",
  exited: "#6b7280",
  stopped: "#6b7280",
  starting: "#fbbf24",
  error: "#e07070",
  unknown: "#6b7280",
};

function Tier2Card({ plugin, onStart, onStop, onDelete, busy }) {
  const statusColor = CONTAINER_STATUS_COLOR[plugin.status] || "#6b7280";
  const isRunning = plugin.status === "running";
  const isStarting = plugin.status === "starting";
  const [testing, setTesting] = useState(false);

  return (
    <div style={{ borderRadius: 8, border: `1px solid ${S.border}`,
      backgroundColor: S.bgCard, padding: "14px 16px", marginBottom: 10,
      display: "flex", alignItems: "flex-start", gap: 12 }}>
      <div style={{ width: 38, height: 38, borderRadius: 8, flexShrink: 0,
        backgroundColor: "rgba(196,181,253,0.08)", border: "1px solid rgba(196,181,253,0.2)",
        display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Container size={16} style={{ color: "#c4b5fd" }} />
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <p style={{ fontSize: 13, fontWeight: 700, color: S.textBright, margin: 0 }}>
            {plugin.name}
          </p>
          <span style={{ fontSize: 9, padding: "2px 6px", borderRadius: 3,
            backgroundColor: "rgba(196,181,253,0.12)", color: "#c4b5fd", fontWeight: 700,
            textTransform: "uppercase", letterSpacing: "0.04em" }}>
            Tier 2
          </span>
          {(plugin.capabilities || []).map(c => <CapBadge key={c} cap={c} />)}
          <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10, color: statusColor }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", backgroundColor: statusColor }} />
            {isStarting ? "Startet..." : plugin.status}
          </span>
        </div>
        <p style={{ fontSize: 10, color: S.textDim, margin: "4px 0 0", fontFamily: "monospace",
          opacity: 0.7 }}>
          {plugin.docker_image}
        </p>
        {plugin.description && (
          <p style={{ fontSize: 11, color: S.textDim, margin: "4px 0 0" }}>{plugin.description}</p>
        )}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
        {isRunning && (
          <button onClick={() => setTesting(true)} disabled={busy}
            style={{ fontSize: 11, padding: "5px 12px", borderRadius: 5, cursor: busy ? "not-allowed" : "pointer",
              backgroundColor: "rgba(110,231,183,0.1)", border: "1px solid rgba(110,231,183,0.3)",
              color: "#6ee7b7", display: "flex", alignItems: "center", gap: 5, opacity: busy ? 0.5 : 1 }}>
            <Zap size={11} /> Test
          </button>
        )}
        {isRunning ? (
          <button onClick={onStop} disabled={busy}
            style={{ fontSize: 11, padding: "5px 12px", borderRadius: 5, cursor: busy ? "wait" : "pointer",
              backgroundColor: "rgba(224,112,112,0.1)", border: "1px solid rgba(224,112,112,0.3)",
              color: "#e07070", display: "flex", alignItems: "center", gap: 5, opacity: busy ? 0.6 : 1 }}>
            {busy ? <Loader2 size={11} className="animate-spin" /> : <Square size={11} />}
            Stop
          </button>
        ) : (
          <button onClick={onStart} disabled={busy || isStarting}
            style={{ fontSize: 11, padding: "5px 12px", borderRadius: 5,
              cursor: (busy || isStarting) ? "wait" : "pointer",
              backgroundColor: "rgba(110,231,183,0.1)", border: "1px solid rgba(110,231,183,0.3)",
              color: "#6ee7b7", display: "flex", alignItems: "center", gap: 5,
              opacity: (busy || isStarting) ? 0.6 : 1 }}>
            {busy || isStarting ? <Loader2 size={11} className="animate-spin" /> : <Play size={11} />}
            Start
          </button>
        )}
        <button onClick={onDelete} disabled={busy}
          style={{ padding: "5px 8px", borderRadius: 5, cursor: busy ? "not-allowed" : "pointer",
            background: "none", border: `1px solid ${S.border}`, color: S.textDim,
            display: "flex", alignItems: "center", opacity: busy ? 0.4 : 1 }}>
          <Trash2 size={13} />
        </button>
      </div>
      {testing && <TestModal plugin={plugin} onClose={() => setTesting(false)} />}
    </div>
  );
}

function RegisterTier2Modal({ onClose, onSaved }) {
  const [form, setForm] = useState({
    id: "", name: "", docker_image: "", description: "", author: "",
    license: "professional",
    capabilities: ["source"],
    source_type_id: "", source_type_label: "",
    target_type_id: "", target_type_label: "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const toggleCap = (cap) => {
    setForm(f => ({
      ...f,
      capabilities: f.capabilities.includes(cap)
        ? f.capabilities.filter(c => c !== cap)
        : [...f.capabilities, cap],
    }));
  };

  const save = async () => {
    if (!form.id || !form.name || !form.docker_image) {
      setError("ID, Name und Docker-Image sind Pflichtfelder.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await api.post("/api/plugins/tier2", form);
      onSaved();
      onClose();
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  const iS = {
    backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4,
    color: S.textBright, fontSize: 11, padding: "5px 8px", outline: "none", width: "100%",
    boxSizing: "border-box",
  };

  const Label = ({ children }) => (
    <label style={{ fontSize: 10, fontWeight: 600, color: S.textDim, textTransform: "uppercase",
      letterSpacing: "0.05em", display: "block", marginBottom: 4 }}>{children}</label>
  );

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 200,
      backgroundColor: "rgba(0,0,0,0.75)", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div onClick={e => e.stopPropagation()} style={{ backgroundColor: S.bgCard,
        border: `1px solid ${S.border}`, borderRadius: 10, padding: 24, width: 520,
        boxShadow: "0 24px 60px rgba(0,0,0,0.7)", maxHeight: "90vh", overflowY: "auto" }}>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <div>
            <p style={{ fontSize: 14, fontWeight: 700, color: S.textBright, margin: 0 }}>
              Tier-2 Plugin registrieren
            </p>
            <p style={{ fontSize: 11, color: S.textDim, margin: "4px 0 0" }}>
              Docker-Container-basiertes Plugin hinzufügen.
            </p>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none",
            cursor: "pointer", color: S.textDim, padding: 4 }}>
            <X size={16} />
          </button>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div>
            <Label>Plugin-ID *</Label>
            <input value={form.id} style={iS} placeholder="mein-plugin"
              onChange={e => set("id", e.target.value)} />
          </div>
          <div>
            <Label>Name *</Label>
            <input value={form.name} style={iS} placeholder="Mein Plugin"
              onChange={e => set("name", e.target.value)} />
          </div>
        </div>

        <div style={{ marginTop: 12 }}>
          <Label>Docker-Image *</Label>
          <input value={form.docker_image} style={iS} placeholder="holdermann/mein-plugin:latest"
            onChange={e => set("docker_image", e.target.value)} />
        </div>

        <div style={{ marginTop: 12 }}>
          <Label>Beschreibung</Label>
          <input value={form.description} style={iS}
            onChange={e => set("description", e.target.value)} />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 12 }}>
          <div>
            <Label>Autor</Label>
            <input value={form.author} style={iS} onChange={e => set("author", e.target.value)} />
          </div>
          <div>
            <Label>Lizenz</Label>
            <select value={form.license} style={iS} onChange={e => set("license", e.target.value)}>
              {["free", "professional", "business", "enterprise"].map(l => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
          </div>
        </div>

        <div style={{ marginTop: 16 }}>
          <Label>Capabilities</Label>
          <div style={{ display: "flex", gap: 8 }}>
            {["source", "target", "transformer", "trigger"].map(cap => (
              <button key={cap} onClick={() => toggleCap(cap)}
                style={{ fontSize: 11, padding: "4px 12px", borderRadius: 4, cursor: "pointer",
                  border: `1px solid ${form.capabilities.includes(cap) ? "#6ee7b7" : S.border}`,
                  backgroundColor: form.capabilities.includes(cap) ? "rgba(110,231,183,0.12)" : "transparent",
                  color: form.capabilities.includes(cap) ? "#6ee7b7" : S.textDim }}>
                {cap}
              </button>
            ))}
          </div>
        </div>

        {form.capabilities.includes("source") && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 12 }}>
            <div>
              <Label>Quell-Typ-ID</Label>
              <input value={form.source_type_id} style={iS} placeholder="mein_quelltyp"
                onChange={e => set("source_type_id", e.target.value)} />
            </div>
            <div>
              <Label>Quell-Typ-Label</Label>
              <input value={form.source_type_label} style={iS} placeholder="Mein Quelltyp"
                onChange={e => set("source_type_label", e.target.value)} />
            </div>
          </div>
        )}

        {form.capabilities.includes("target") && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 12 }}>
            <div>
              <Label>Ziel-Typ-ID</Label>
              <input value={form.target_type_id} style={iS} placeholder="mein_zieltyp"
                onChange={e => set("target_type_id", e.target.value)} />
            </div>
            <div>
              <Label>Ziel-Typ-Label</Label>
              <input value={form.target_type_label} style={iS} placeholder="Mein Zieltyp"
                onChange={e => set("target_type_label", e.target.value)} />
            </div>
          </div>
        )}

        {error && (
          <div style={{ marginTop: 14, padding: "8px 12px", borderRadius: 6,
            backgroundColor: "rgba(224,112,112,0.08)", border: "1px solid rgba(224,112,112,0.3)" }}>
            <p style={{ fontSize: 11, color: "#e07070", margin: 0 }}>{error}</p>
          </div>
        )}

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 20 }}>
          <button onClick={onClose} style={{ padding: "7px 16px", borderRadius: 5,
            border: `1px solid ${S.border}`, background: "none", color: S.textDim, fontSize: 12, cursor: "pointer" }}>
            Abbrechen
          </button>
          <button onClick={save} disabled={saving}
            style={{ padding: "7px 18px", borderRadius: 5, border: "none", fontSize: 12,
              fontWeight: 700, cursor: saving ? "wait" : "pointer",
              backgroundColor: "var(--accent)", color: "#111",
              display: "flex", alignItems: "center", gap: 6, opacity: saving ? 0.7 : 1 }}>
            {saving ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
            {saving ? "Registriere..." : "Registrieren"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Tier2Section({ onRefresh }) {
  const [plugins, setPlugins] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState({});
  const [showRegister, setShowRegister] = useState(false);
  const [pmOnline, setPmOnline] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/api/plugins/tier2");
      setPlugins(Array.isArray(data) ? data : []);
      setPmOnline(true);
    } catch (e) {
      if (e.response?.status === 503) {
        setPmOnline(false);
      } else {
        setPmOnline(false);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const setBusyFor = (id, val) => setBusy(b => ({ ...b, [id]: val }));

  const handleStart = async (id) => {
    setBusyFor(id, true);
    try {
      await api.post(`/api/plugins/tier2/${id}/start`);
      await load();
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    } finally {
      setBusyFor(id, false);
    }
  };

  const handleStop = async (id) => {
    setBusyFor(id, true);
    try {
      await api.post(`/api/plugins/tier2/${id}/stop`);
      await load();
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    } finally {
      setBusyFor(id, false);
    }
  };

  const handleDelete = async (id, name) => {
    if (!confirm(`Plugin "${name}" wirklich entfernen?\nDer Container wird gestoppt und gelöscht.`)) return;
    setBusyFor(id, true);
    try {
      await api.delete(`/api/plugins/tier2/${id}`);
      await load();
      onRefresh();
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    } finally {
      setBusyFor(id, false);
    }
  };

  return (
    <div style={{ marginTop: 32 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Container size={14} style={{ color: "#c4b5fd" }} />
          <p style={{ fontSize: 11, fontWeight: 600, color: S.textDim, textTransform: "uppercase",
            letterSpacing: "0.06em", margin: 0 }}>Tier-2 Plugins (Container)</p>
          {pmOnline !== null && (
            <span style={{ fontSize: 9, padding: "2px 6px", borderRadius: 3, fontWeight: 700,
              textTransform: "uppercase",
              backgroundColor: pmOnline ? "rgba(110,231,183,0.12)" : "rgba(224,112,112,0.12)",
              color: pmOnline ? "#6ee7b7" : "#e07070" }}>
              {pmOnline ? "PM Online" : "PM Offline"}
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <button onClick={load} style={{ display: "flex", alignItems: "center", gap: 5,
            fontSize: 11, padding: "5px 10px", borderRadius: 5, cursor: "pointer",
            background: "none", border: `1px solid ${S.border}`, color: S.textDim }}>
            <RefreshCw size={11} />
          </button>
          <button onClick={() => setShowRegister(true)} disabled={!pmOnline}
            style={{ display: "flex", alignItems: "center", gap: 5,
              fontSize: 11, padding: "5px 12px", borderRadius: 5, cursor: pmOnline ? "pointer" : "not-allowed",
              backgroundColor: pmOnline ? "rgba(196,181,253,0.12)" : "transparent",
              border: `1px solid ${pmOnline ? "rgba(196,181,253,0.4)" : S.border}`,
              color: pmOnline ? "#c4b5fd" : S.textDim, opacity: pmOnline ? 1 : 0.5 }}>
            <Plus size={11} /> Plugin registrieren
          </button>
        </div>
      </div>

      {loading ? (
        <div style={{ display: "flex", alignItems: "center", gap: 8, color: S.textDim,
          padding: "16px 0", fontSize: 12 }}>
          <Loader2 size={14} className="animate-spin" /> Lade...
        </div>
      ) : !pmOnline ? (
        <div style={{ padding: "16px", borderRadius: 8, backgroundColor: S.bgEl,
          border: `1px solid ${S.border}`, fontSize: 12, color: S.textDim }}>
          Plugin Manager nicht erreichbar. Prüfe ob der <code>plugin-manager</code> Container läuft.
        </div>
      ) : plugins.length === 0 ? (
        <div style={{ padding: "16px", borderRadius: 8, backgroundColor: S.bgEl,
          border: `1px solid ${S.border}`, textAlign: "center", color: S.textDim }}>
          <Container size={24} style={{ margin: "0 auto 8px", opacity: 0.3 }} />
          <p style={{ fontSize: 12, margin: "0 0 4px" }}>Keine Tier-2 Plugins registriert</p>
          <p style={{ fontSize: 11, opacity: 0.6, margin: 0 }}>
            Container-basierte Plugins (Java, SAP, KI) über "Plugin registrieren" hinzufügen.
          </p>
        </div>
      ) : (
        plugins.map(p => (
          <Tier2Card key={p.id} plugin={p} busy={busy[p.id]}
            onStart={() => handleStart(p.id)}
            onStop={() => handleStop(p.id)}
            onDelete={() => handleDelete(p.id, p.name)} />
        ))
      )}

      {showRegister && (
        <RegisterTier2Modal
          onClose={() => setShowRegister(false)}
          onSaved={() => { load(); onRefresh(); }}
        />
      )}
    </div>
  );
}

// ── Hauptpanel ────────────────────────────────────────────────────────────────

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
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase",
            letterSpacing: "0.1em", color: "var(--accent)", margin: "0 0 4px" }}>
            Plugins
          </h1>
          <p style={{ fontSize: 12, color: S.textDim, margin: 0 }}>
            {plugins.length > 0
              ? `${plugins.length} Plugin${plugins.length !== 1 ? "s" : ""} installiert`
              : "Keine Tier-1 Plugins geladen"}
          </p>
        </div>
        <button onClick={load} style={{ display: "flex", alignItems: "center", gap: 6,
          fontSize: 11, padding: "6px 12px", borderRadius: 5, cursor: "pointer",
          background: "none", border: `1px solid ${S.border}`, color: S.textDim }}>
          <RefreshCw size={12} /> Aktualisieren
        </button>
      </div>

      {/* Tier-1 Plugins */}
      {loading ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center",
          height: 120, color: S.textDim }}>
          <Loader2 size={18} className="animate-spin" style={{ marginRight: 8 }} /> Lade...
        </div>
      ) : (
        <>
          {plugins.length > 0 && (
            <>
              {capabilities && (
                <div style={{ marginBottom: 28, padding: "14px 16px", borderRadius: 8,
                  backgroundColor: S.bgEl, border: `1px solid ${S.border}` }}>
                  <CapabilitySection title="Datenquellen" icon={Database} items={capabilities.sources} />
                  <CapabilitySection title="Datenziele" icon={ArrowRightLeft} items={capabilities.targets} />
                </div>
              )}
              <div>
                {plugins.filter(p => !p.tier || p.tier === 1).map(p => (
                  <PluginCard key={p.id} plugin={p} />
                ))}
              </div>
            </>
          )}

          {plugins.length === 0 && (
            <div style={{ textAlign: "center", padding: "32px 24px", color: S.textDim,
              backgroundColor: S.bgEl, borderRadius: 8, border: `1px solid ${S.border}` }}>
              <Puzzle size={28} style={{ margin: "0 auto 10px", opacity: 0.3 }} />
              <p style={{ fontSize: 13, margin: "0 0 4px" }}>Keine Tier-1 Plugins gefunden</p>
              <p style={{ fontSize: 11, opacity: 0.6, margin: 0 }}>
                Plugins in <code>backend/plugins/</code> ablegen und Backend neu starten.
              </p>
            </div>
          )}
        </>
      )}

      {/* Tier-2 Plugin Manager */}
      <Tier2Section onRefresh={load} />
    </div>
  );
}
