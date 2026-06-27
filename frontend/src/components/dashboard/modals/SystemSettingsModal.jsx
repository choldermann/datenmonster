import { useState, useEffect } from "react";
import { X, Save, Loader2, Check, Eye, EyeOff, TestTube, UserPlus, Trash2, Wifi, Download } from "lucide-react";
import api from "../../../api/client";
import { testConnection as testAiConnection, listModels, pullModel } from "../../../services/aiService";
import { aiDownloadStore } from "../../../store/aiDownloadStore";
import { S } from "../constants";

const ACCENT = "#fce499";

const TABS = [
  { id: "email", label: "E-Mail", icon: "📧" },
  { id: "ai", label: "KI", icon: "✨" },
  { id: "users", label: "Benutzer", icon: "👤" },
  { id: "appearance", label: "Optik", icon: "🎨", disabled: true },
  { id: "language", label: "Sprache", icon: "🌍", disabled: true },
  { id: "license", label: "Lizenz", icon: "🔑", disabled: true },
];

function EmailSettings() {
  const [form, setForm] = useState({
    smtp_host: "", smtp_port: "587", smtp_user: "", smtp_password: "",
    smtp_from: "", smtp_from_name: "Datenmonster", smtp_tls: true,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [showPw, setShowPw] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.get("/api/settings/email").then(({ data }) => {
      if (data) setForm(prev => ({ ...prev, ...data }));
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    try {
      await api.post("/api/settings/email", form);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    } finally { setSaving(false); }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const { data } = await api.post("/api/settings/email/test", form);
      setTestResult({ ok: true, msg: data.message || "Test-E-Mail gesendet!" });
    } catch (e) {
      const detail = e.response?.data?.detail;
      const msg = typeof detail === "string" ? detail
        : Array.isArray(detail) ? detail.map(d => d.msg || JSON.stringify(d)).join(", ")
        : detail ? JSON.stringify(detail)
        : e.message;
      setTestResult({ ok: false, msg });
    } finally { setTesting(false); }
  };

  const iS = { backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, color: S.textBright, fontSize: 11, padding: "6px 10px", outline: "none", width: "100%" };
  const lS = { fontSize: 10, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", display: "block", marginBottom: 4 };

  if (loading) return <p style={{ color: S.textDim, fontSize: 12 }}>Lade...</p>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <p style={{ fontSize: 11, color: S.textDim, margin: 0 }}>
        SMTP-Konfiguration für den E-Mail-Versand aus Pipelines und Benachrichtigungen.
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 120px", gap: 10 }}>
        <div>
          <label style={lS}>SMTP Server</label>
          <input style={iS} value={form.smtp_host} onChange={e => set("smtp_host", e.target.value)} placeholder="smtp.gmail.com" />
        </div>
        <div>
          <label style={lS}>Port</label>
          <input style={iS} value={form.smtp_port} onChange={e => set("smtp_port", e.target.value)} placeholder="587" />
        </div>
      </div>

      <div>
        <label style={lS}>Benutzername / E-Mail</label>
        <input style={iS} value={form.smtp_user} onChange={e => set("smtp_user", e.target.value)} placeholder="user@firma.de" />
      </div>

      <div>
        <label style={lS}>Passwort</label>
        <div style={{ position: "relative" }}>
          <input style={{ ...iS, paddingRight: 36 }} type={showPw ? "text" : "password"}
            value={form.smtp_password} onChange={e => set("smtp_password", e.target.value)} placeholder="••••••••" />
          <button onClick={() => setShowPw(v => !v)}
            style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0 }}>
            {showPw ? <EyeOff size={13} /> : <Eye size={13} />}
          </button>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        <div>
          <label style={lS}>Absender-Adresse</label>
          <input style={iS} value={form.smtp_from} onChange={e => set("smtp_from", e.target.value)} placeholder="noreply@firma.de" />
        </div>
        <div>
          <label style={lS}>Absender-Name</label>
          <input style={iS} value={form.smtp_from_name} onChange={e => set("smtp_from_name", e.target.value)} placeholder="Datenmonster" />
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }} onClick={() => set("smtp_tls", !form.smtp_tls)}>
        <div style={{ width: 16, height: 16, borderRadius: 3, border: `2px solid ${form.smtp_tls ? ACCENT : S.border}`, backgroundColor: form.smtp_tls ? ACCENT : "transparent", display: "flex", alignItems: "center", justifyContent: "center" }}>
          {form.smtp_tls && <Check size={10} color="#111" strokeWidth={3} />}
        </div>
        <span style={{ fontSize: 11, color: S.textMain }}>TLS/STARTTLS verwenden</span>
      </div>

      {testResult && (
        <div style={{ padding: "8px 12px", borderRadius: 5, backgroundColor: testResult.ok ? "rgba(110,231,183,0.08)" : "rgba(224,112,112,0.08)", border: `1px solid ${testResult.ok ? "rgba(110,231,183,0.3)" : "rgba(224,112,112,0.3)"}` }}>
          <p style={{ fontSize: 11, color: testResult.ok ? "#6ee7b7" : "#e07070", margin: 0 }}>
            {testResult.ok ? "✓" : "✗"} {testResult.msg}
          </p>
        </div>
      )}

      <div style={{ display: "flex", gap: 8 }}>
        <button onClick={handleTest} disabled={testing || !form.smtp_host}
          style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 14px", borderRadius: 5, border: `1px solid ${S.border}`, backgroundColor: "transparent", color: S.textDim, cursor: "pointer", fontSize: 12 }}>
          {testing ? <Loader2 size={12} className="animate-spin" /> : <TestTube size={12} />}
          Test-Mail senden
        </button>
        <button onClick={handleSave} disabled={saving}
          style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 16px", borderRadius: 5, border: "none", backgroundColor: saved ? "rgba(110,231,183,0.15)" : ACCENT, color: saved ? "#6ee7b7" : "#111", cursor: "pointer", fontSize: 12, fontWeight: 700 }}>
          {saving ? <Loader2 size={12} className="animate-spin" /> : saved ? <Check size={12} /> : <Save size={12} />}
          {saved ? "Gespeichert!" : "Speichern"}
        </button>
      </div>
    </div>
  );
}


const PRESET_MODELS = [
  {
    id: "qwen2.5-coder:1.5b",
    name: "Qwen 2.5 Coder 1.5B",
    ram: "~1 GB",
    cpu: true,
    strengths: ["SQL", "Code", "sehr schnell"],
    note: "Für schwache Hardware — begrenzte Anweisungsfolge",
  },
  {
    id: "qwen2.5-coder:3b",
    name: "Qwen 2.5 Coder 3B",
    ram: "~2 GB",
    cpu: true,
    strengths: ["SQL", "Code"],
    note: "Schneller Kompromiss für CPU-Only Setups",
  },
  {
    id: "qwen2.5-coder:7b",
    name: "Qwen 2.5 Coder 7B",
    ram: "~5 GB",
    cpu: true,
    strengths: ["SQL", "Code", "Kontext"],
    note: "Beste Code-Qualität auf reiner CPU — empfohlen",
    recommended: true,
  },
  {
    id: "qwen2.5-coder:14b",
    name: "Qwen 2.5 Coder 14B",
    ram: "~9 GB",
    cpu: false,
    strengths: ["SQL", "Code", "komplex"],
    note: "Sehr hohe Qualität, setzt GPU voraus",
  },
  {
    id: "qwen2.5-coder:32b",
    name: "Qwen 2.5 Coder 32B",
    ram: "~20 GB",
    cpu: false,
    strengths: ["SQL", "Code", "Architektur"],
    note: "Professionell, nur mit leistungsfähiger GPU",
  },
  {
    id: "llama3.2:3b",
    name: "Llama 3.2 3B",
    ram: "~2 GB",
    cpu: true,
    strengths: ["Deutsch", "Erklärungen", "Chat"],
    note: "Gut für deutsche Erklärungen, schwach bei SQL",
  },
  {
    id: "llama3.1:8b",
    name: "Llama 3.1 8B",
    ram: "~5 GB",
    cpu: true,
    strengths: ["Deutsch", "Allrounder", "Reasoning"],
    note: "Stark für Erklärungen & Allgemeinwissen auf CPU",
  },
  {
    id: "mistral:7b",
    name: "Mistral 7B",
    ram: "~4 GB",
    cpu: true,
    strengths: ["Deutsch", "Code", "Allrounder"],
    note: "Bewährtes Allrounder-Modell, gut auf Deutsch",
  },
  {
    id: "deepseek-coder:6.7b",
    name: "DeepSeek Coder 6.7B",
    ram: "~4 GB",
    cpu: true,
    strengths: ["Code", "SQL", "Präzision"],
    note: "Auf Code spezialisiert, sehr präzise bei SQL",
  },
  {
    id: "phi4-mini",
    name: "Phi-4 Mini",
    ram: "~2.5 GB",
    cpu: true,
    strengths: ["Reasoning", "Allrounder"],
    note: "Microsoft Phi-4 — stark im logischen Denken",
  },
];

function AiSettings() {
  const [form, setForm] = useState({
    ai_enabled:  false,
    ai_provider: "ollama",
    ai_base_url: "http://ollama:11434",
    ai_model:    "qwen2.5-coder:3b",
    ai_timeout:  120,
  });
  const [customModel, setCustomModel] = useState("");
  const [useCustom, setUseCustom] = useState(false);
  const [loading, setLoading]   = useState(true);
  const [saving,  setSaving]    = useState(false);
  const [saved,   setSaved]     = useState(false);
  const [testing, setTesting]   = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [installedModels, setInstalledModels] = useState([]);
  const [pulling, setPulling]   = useState(false);
  const [pullProgress, setPullProgress] = useState(null); // {status, percent, completed, total}

  useEffect(() => {
    api.get("/api/settings/ai").then(({ data }) => {
      if (data) {
        setForm(f => ({ ...f, ...data }));
        const isPreset = PRESET_MODELS.some(m => m.id === data.ai_model);
        if (!isPreset && data.ai_model) {
          setUseCustom(true);
          setCustomModel(data.ai_model);
        }
      }
    }).catch(() => {}).finally(() => setLoading(false));

    const refreshModels = () =>
      listModels().then(({ models }) => setInstalledModels(models || [])).catch(() => {});
    refreshModels();
    // Alle 10s aktualisieren solange die Komponente offen ist (laufende Downloads)
    const interval = setInterval(refreshModels, 10000);
    return () => clearInterval(interval);
  }, []);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const effectiveModel = useCustom ? customModel : form.ai_model;
  const modelInstalled = installedModels.some(m => m === effectiveModel || m.startsWith(effectiveModel + ":"));

  const handlePull = async () => {
    setPulling(true);
    setPullProgress({ status: "Verbinde...", percent: 0 });
    aiDownloadStore.set({ pulling: true, model: effectiveModel, status: "Verbinde...", percent: 0, done: false, error: null });
    try {
      await pullModel(effectiveModel, (chunk) => {
        if (chunk.status === "error") {
          const p = { status: `Fehler: ${chunk.error}`, percent: 0, error: true };
          setPullProgress(p);
          aiDownloadStore.set({ ...p, pulling: false });
          return;
        }
        const percent = chunk.total > 0 ? Math.round((chunk.completed / chunk.total) * 100) : null;
        const p = { status: chunk.status || "...", percent, completed: chunk.completed, total: chunk.total };
        setPullProgress(p);
        aiDownloadStore.set({ ...p, pulling: true, model: effectiveModel });
      });
      setPullProgress({ status: "Fertig!", percent: 100, done: true });
      aiDownloadStore.set({ pulling: false, status: "Fertig!", percent: 100, done: true });
      setInstalledModels(prev => prev.includes(effectiveModel) ? prev : [...prev, effectiveModel]);
      setTimeout(() => {
        setPullProgress(null);
        aiDownloadStore.set({ pulling: false, model: null, status: null, percent: null, done: false });
      }, 4000);
    } catch (e) {
      const p = { status: `Fehler: ${e.message}`, percent: 0, error: true };
      setPullProgress(p);
      aiDownloadStore.set({ ...p, pulling: false });
    } finally {
      setPulling(false);
    }
  };

  const handleSave = async () => {
    setSaving(true); setSaved(false);
    try {
      await api.post("/api/settings/ai", { ...form, ai_model: effectiveModel });
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    } finally { setSaving(false); }
  };

  const handleTest = async () => {
    setTesting(true); setTestResult(null);
    try {
      const status = await testAiConnection(form.ai_base_url, effectiveModel);
      if (status.ollama_reachable) {
        setTestResult({
          ok: true,
          msg: status.model_loaded
            ? `Verbunden ✓ — Modell "${effectiveModel}" geladen`
            : `Ollama erreichbar, aber Modell "${effectiveModel}" noch nicht geladen. Führe "ollama pull ${effectiveModel}" im Container aus.`,
        });
      } else {
        setTestResult({ ok: false, msg: `Ollama nicht erreichbar: ${status.error || "Keine Antwort"}` });
      }
    } catch (e) {
      setTestResult({ ok: false, msg: e.message });
    } finally { setTesting(false); }
  };

  const iS = { backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, color: S.textBright, fontSize: 11, padding: "6px 10px", outline: "none", width: "100%" };
  const lS = { fontSize: 10, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", display: "block", marginBottom: 4 };

  if (loading) return <p style={{ color: S.textDim, fontSize: 12 }}>Lade...</p>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <p style={{ fontSize: 11, color: S.textDim, margin: 0, lineHeight: 1.6 }}>
        Lokale KI-Unterstützung über Ollama — kostenlos, läuft komplett auf deinem Server.
        KI-Buttons erscheinen in SQL-, Python- und Expressions-Nodes sowie im Mapping-Canvas.
      </p>

      {/* KI aktivieren */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", padding: "10px 12px", borderRadius: 6, backgroundColor: form.ai_enabled ? "rgba(252,228,153,0.07)" : S.bgEl, border: `1px solid ${form.ai_enabled ? "rgba(252,228,153,0.25)" : S.border}` }}
        onClick={() => set("ai_enabled", !form.ai_enabled)}>
        <div style={{ width: 16, height: 16, borderRadius: 3, border: `2px solid ${form.ai_enabled ? ACCENT : S.border}`, backgroundColor: form.ai_enabled ? ACCENT : "transparent", flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
          {form.ai_enabled && <Check size={10} color="#111" strokeWidth={3} />}
        </div>
        <span style={{ fontSize: 11, color: form.ai_enabled ? ACCENT : S.textMain, fontWeight: form.ai_enabled ? 700 : 400 }}>
          KI-Integration aktivieren
        </span>
      </div>

      {form.ai_enabled && (
        <>
          {/* Ollama URL */}
          <div>
            <label style={lS}>Ollama URL</label>
            <input style={iS} value={form.ai_base_url} onChange={e => set("ai_base_url", e.target.value)}
              placeholder="http://ollama:11434" />
            <span style={{ fontSize: 10, color: S.textDim, marginTop: 3, display: "block" }}>
              Im Docker-Stack: http://ollama:11434 · Extern: http://localhost:11434
            </span>
          </div>

          {/* Modell */}
          <div>
            <label style={lS}>Modell</label>
            {!useCustom ? (
              <div style={{ maxHeight: 260, overflowY: "auto", display: "flex", flexDirection: "column", gap: 4, paddingRight: 2 }}>
                {PRESET_MODELS.map(m => {
                  const isSelected = form.ai_model === m.id;
                  const isInstalled = installedModels.some(i => i === m.id || i.startsWith(m.id + ":"));
                  return (
                    <div key={m.id}
                      onClick={() => { set("ai_model", m.id); setPullProgress(null); }}
                      style={{
                        padding: "7px 10px", borderRadius: 5, cursor: "pointer",
                        border: `1px solid ${isSelected ? ACCENT : S.border}`,
                        backgroundColor: isSelected ? "rgba(252,228,153,0.06)" : S.bgEl,
                        transition: "border-color 0.15s",
                      }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span style={{ fontSize: 11, fontWeight: 600, color: isSelected ? ACCENT : S.textBright, flex: 1 }}>
                          {m.name}
                        </span>
                        {m.recommended && (
                          <span style={{ fontSize: 8, padding: "1px 5px", borderRadius: 8, backgroundColor: "rgba(252,228,153,0.15)", color: ACCENT, border: `1px solid rgba(252,228,153,0.3)`, fontWeight: 700 }}>
                            ★ Empfohlen
                          </span>
                        )}
                        {isInstalled && (
                          <span style={{ fontSize: 9, display: "flex", alignItems: "center", gap: 3, color: "#6ee7b7" }}>
                            <Check size={10} /> installiert
                          </span>
                        )}
                      </div>
                      <div style={{ display: "flex", gap: 4, marginTop: 5, flexWrap: "wrap", alignItems: "center" }}>
                        <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 4, backgroundColor: "rgba(255,255,255,0.06)", color: S.textDim, border: `1px solid ${S.border}` }}>
                          {m.ram}
                        </span>
                        <span style={{
                          fontSize: 9, padding: "1px 5px", borderRadius: 4, fontWeight: 700,
                          backgroundColor: m.cpu ? "rgba(110,231,183,0.1)" : "rgba(139,92,246,0.1)",
                          color: m.cpu ? "#6ee7b7" : "#a78bfa",
                          border: `1px solid ${m.cpu ? "rgba(110,231,183,0.25)" : "rgba(139,92,246,0.25)"}`,
                        }}>
                          {m.cpu ? "CPU" : "GPU"}
                        </span>
                        {m.strengths.map(s => (
                          <span key={s} style={{ fontSize: 9, padding: "1px 5px", borderRadius: 4, backgroundColor: "rgba(255,255,255,0.04)", color: S.textDim, border: `1px solid ${S.border}` }}>
                            {s}
                          </span>
                        ))}
                      </div>
                      <p style={{ fontSize: 10, color: S.textDim, margin: "4px 0 0", lineHeight: 1.4 }}>{m.note}</p>
                    </div>
                  );
                })}
              </div>
            ) : (
              <input style={iS} value={customModel}
                onChange={e => { setCustomModel(e.target.value); setPullProgress(null); }}
                placeholder="z.B. deepseek-coder-v2:lite" />
            )}
            <button onClick={() => { setUseCustom(v => !v); setCustomModel(""); setPullProgress(null); }}
              style={{ marginTop: 6, background: "none", border: "none", color: S.textDim, fontSize: 10, cursor: "pointer", padding: 0, textDecoration: "underline" }}>
              {useCustom ? "← Aus der Liste wählen" : "Anderes Modell eingeben →"}
            </button>

            {/* Download-Bereich */}
            {!modelInstalled && effectiveModel && !pulling && !pullProgress && (
              <button onClick={handlePull}
                style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 6, padding: "6px 12px", borderRadius: 4, border: "1px solid rgba(251,191,36,0.4)", backgroundColor: "rgba(251,191,36,0.08)", color: "#fbbf24", fontSize: 11, fontWeight: 600, cursor: "pointer", width: "100%" }}>
                <Download size={12} /> Modell jetzt herunterladen
              </button>
            )}

            {/* Fortschrittsanzeige */}
            {(pulling || pullProgress) && (
              <div style={{ marginTop: 8, padding: "8px 10px", borderRadius: 4, backgroundColor: "rgba(0,0,0,0.25)", border: `1px solid ${pullProgress?.error ? "rgba(224,112,112,0.3)" : pullProgress?.done ? "rgba(110,231,183,0.3)" : "rgba(252,228,153,0.2)"}` }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: pullProgress?.percent != null ? 6 : 0 }}>
                  <span style={{ fontSize: 10, color: pullProgress?.error ? "#e07070" : pullProgress?.done ? "#6ee7b7" : ACCENT }}>
                    {pullProgress?.error ? "✗ " : pullProgress?.done ? "✓ " : "⬇ "}
                    {pullProgress?.status || "Verbinde..."}
                  </span>
                  {pullProgress?.percent != null && (
                    <span style={{ fontSize: 10, color: S.textDim }}>{pullProgress.percent}%</span>
                  )}
                </div>
                {pullProgress?.percent != null && !pullProgress.done && !pullProgress.error && (
                  <div style={{ height: 3, backgroundColor: "rgba(255,255,255,0.08)", borderRadius: 2, overflow: "hidden" }}>
                    <div style={{
                      height: "100%", borderRadius: 2, backgroundColor: ACCENT,
                      width: `${pullProgress.percent}%`,
                      transition: "width 0.3s ease",
                    }} />
                  </div>
                )}
                {pulling && pullProgress?.percent == null && (
                  <div style={{ height: 3, backgroundColor: "rgba(255,255,255,0.08)", borderRadius: 2, overflow: "hidden" }}>
                    <div style={{ height: "100%", width: "40%", backgroundColor: ACCENT, animation: "aiSweep 1.4s ease-in-out infinite" }} />
                  </div>
                )}
                {pulling && !pullProgress?.done && !pullProgress?.error && (
                  <p style={{ fontSize: 9, color: S.textDim, margin: "6px 0 0", lineHeight: 1.4 }}>
                    Ollama lädt im Hintergrund weiter, auch wenn du dieses Fenster schließt. Einstellungen neu öffnen um Status zu sehen.
                  </p>
                )}
              </div>
            )}
          </div>

          {/* Timeout */}
          <div>
            <label style={lS}>Timeout (Sekunden)</label>
            <input style={{ ...iS, width: 80 }} type="number" min={10} max={600}
              value={form.ai_timeout} onChange={e => set("ai_timeout", parseInt(e.target.value) || 120)} />
            <span style={{ fontSize: 10, color: S.textDim, marginTop: 3, display: "block" }}>
              Ohne GPU: 60–120s empfohlen
            </span>
          </div>

          {/* Verbindungstest */}
          {testResult && (
            <div style={{ padding: "8px 12px", borderRadius: 5, backgroundColor: testResult.ok ? "rgba(110,231,183,0.08)" : "rgba(224,112,112,0.08)", border: `1px solid ${testResult.ok ? "rgba(110,231,183,0.3)" : "rgba(224,112,112,0.3)"}` }}>
              <p style={{ fontSize: 11, color: testResult.ok ? "#6ee7b7" : "#e07070", margin: 0, lineHeight: 1.5 }}>{testResult.msg}</p>
            </div>
          )}
        </>
      )}

      <div style={{ display: "flex", gap: 8 }}>
        {form.ai_enabled && (
          <button onClick={handleTest} disabled={testing}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 14px", borderRadius: 5, border: `1px solid ${S.border}`, backgroundColor: "transparent", color: S.textDim, cursor: "pointer", fontSize: 12 }}>
            {testing ? <Loader2 size={12} className="animate-spin" /> : <Wifi size={12} />}
            Verbindung testen
          </button>
        )}
        <button onClick={handleSave} disabled={saving}
          style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 16px", borderRadius: 5, border: "none", backgroundColor: saved ? "rgba(110,231,183,0.15)" : ACCENT, color: saved ? "#6ee7b7" : "#111", cursor: "pointer", fontSize: 12, fontWeight: 700 }}>
          {saving ? <Loader2 size={12} className="animate-spin" /> : saved ? <Check size={12} /> : <Save size={12} />}
          {saved ? "Gespeichert!" : "Speichern"}
        </button>
      </div>
    </div>
  );
}

function UserManagement() {
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState({ username: "", password: "" });
  const [creating, setCreating] = useState(false);
  const [result, setResult] = useState(null);
  const [showPw, setShowPw] = useState(false);

  const load = () => api.get("/api/auth/users").then(({ data }) => setUsers(data)).catch(() => {});
  useEffect(() => { load(); }, []);

  const iS = { backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, color: S.textBright, fontSize: 11, padding: "6px 10px", outline: "none", width: "100%" };
  const lS = { fontSize: 10, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", display: "block", marginBottom: 4 };

  const handleCreate = async () => {
    if (!form.username.trim() || form.password.length < 6) {
      setResult({ ok: false, msg: "Benutzername und Passwort (min. 6 Zeichen) erforderlich" });
      return;
    }
    setCreating(true); setResult(null);
    try {
      const { data } = await api.post("/api/auth/register", { username: form.username.trim(), password: form.password });
      setResult({ ok: true, msg: `Benutzer "${data.username}" angelegt` });
      setForm({ username: "", password: "" });
      load();
    } catch (e) {
      setResult({ ok: false, msg: e.response?.data?.detail || "Fehler beim Anlegen" });
    } finally { setCreating(false); }
  };

  const handleDelete = async (id, name) => {
    if (!confirm(`Benutzer "${name}" wirklich löschen?`)) return;
    try {
      await api.delete(`/api/auth/users/${id}`);
      load();
    } catch (e) {
      alert(e.response?.data?.detail || "Löschen fehlgeschlagen");
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <p style={{ fontSize: 11, color: S.textDim, margin: 0 }}>Benutzer anlegen und verwalten. Nur Administratoren haben Zugriff auf diese Ansicht.</p>

      {/* Bestehende Benutzer */}
      {users.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={lS}>Bestehende Benutzer</span>
          {users.map(u => (
            <div key={u.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "6px 10px", borderRadius: 4, backgroundColor: S.bgEl, border: `1px solid ${S.border}` }}>
              <span style={{ fontSize: 12, color: S.textMain }}>{u.username}</span>
              <button onClick={() => handleDelete(u.id, u.username)}
                style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 2, display: "flex", alignItems: "center" }}
                title="Benutzer löschen">
                <Trash2 size={12} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Neuen Benutzer anlegen */}
      <div style={{ borderTop: `1px solid ${S.border}`, paddingTop: 14, display: "flex", flexDirection: "column", gap: 10 }}>
        <span style={lS}>Neuen Benutzer anlegen</span>
        <div>
          <label style={lS}>Benutzername</label>
          <input style={iS} value={form.username} onChange={e => setForm(f => ({ ...f, username: e.target.value }))} placeholder="neuer.benutzer" />
        </div>
        <div>
          <label style={lS}>Passwort</label>
          <div style={{ position: "relative" }}>
            <input style={{ ...iS, paddingRight: 36 }} type={showPw ? "text" : "password"}
              value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))} placeholder="••••••••" />
            <button onClick={() => setShowPw(v => !v)}
              style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0 }}>
              {showPw ? <EyeOff size={13} /> : <Eye size={13} />}
            </button>
          </div>
        </div>
        {result && (
          <div style={{ padding: "7px 10px", borderRadius: 4, backgroundColor: result.ok ? "rgba(110,231,183,0.08)" : "rgba(224,112,112,0.08)", border: `1px solid ${result.ok ? "rgba(110,231,183,0.3)" : "rgba(224,112,112,0.3)"}` }}>
            <p style={{ fontSize: 11, color: result.ok ? "#6ee7b7" : "#e07070", margin: 0 }}>{result.ok ? "✓" : "✗"} {result.msg}</p>
          </div>
        )}
        <button onClick={handleCreate} disabled={creating}
          style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 16px", borderRadius: 5, border: "none", backgroundColor: ACCENT, color: "#111", cursor: "pointer", fontSize: 12, fontWeight: 700, alignSelf: "flex-start" }}>
          {creating ? <Loader2 size={12} className="animate-spin" /> : <UserPlus size={12} />}
          Benutzer anlegen
        </button>
      </div>
    </div>
  );
}

export default function SystemSettingsModal({ onClose }) {
  const [activeTab, setActiveTab] = useState("email");

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 60, backgroundColor: "rgba(0,0,0,0.7)", display: "flex", alignItems: "flex-end", justifyContent: "flex-start" }} onClick={onClose}>
      <div style={{ width: 480, maxHeight: "70vh", display: "flex", flexDirection: "column", backgroundColor: S.bgCard, borderRadius: "10px 10px 0 0", border: `1px solid ${S.border}`, borderBottom: "none", boxShadow: "0 -8px 40px rgba(0,0,0,0.5)", marginLeft: 20 }} onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div style={{ padding: "14px 18px", borderBottom: `1px solid ${S.border}`, display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 16 }}>⚙️</span>
          <span style={{ fontSize: 14, fontWeight: 700, color: S.textBright, flex: 1 }}>Systemeinstellungen</span>
          <button onClick={onClose} style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer" }}><X size={14} /></button>
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", borderBottom: `1px solid ${S.border}`, padding: "0 18px" }}>
          {TABS.map(tab => (
            <button key={tab.id}
              onClick={() => !tab.disabled && setActiveTab(tab.id)}
              style={{ padding: "8px 14px", fontSize: 11, fontWeight: 600, background: "none", border: "none", cursor: tab.disabled ? "default" : "pointer", color: activeTab === tab.id ? ACCENT : S.textDim, borderBottom: `2px solid ${activeTab === tab.id ? ACCENT : "transparent"}`, opacity: tab.disabled ? 0.4 : 1, display: "flex", alignItems: "center", gap: 5 }}>
              {tab.icon} {tab.label}
              {tab.disabled && <span style={{ fontSize: 8, color: S.textDim }}>bald</span>}
            </button>
          ))}
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflowY: "auto", padding: "16px 18px" }}>
          {activeTab === "email" && <EmailSettings />}
          {activeTab === "ai" && <AiSettings />}
          {activeTab === "users" && <UserManagement />}
        </div>
      </div>
    </div>
  );
}
