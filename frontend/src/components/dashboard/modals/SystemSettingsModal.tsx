import { useState, useEffect } from "react";
import { X, Save, Loader2, Check, Eye, EyeOff, TestTube, UserPlus, Trash2, Wifi, Download, Moon, Sun, Monitor, Zap } from "lucide-react";
import { useTheme, type ThemeMode } from "../../../hooks/useTheme";
import api, { fehlerText } from "../../../api/client";
import { useAuth } from "../../../context/AuthContext";
import { testConnection as testAiConnection, listModels, pullModel, deleteModel } from "../../../services/aiService";
import { aiDownloadStore } from "../../../store/aiDownloadStore";
import { getAiProvider, setAiProvider, onAiProviderChange } from "../../../services/aiProvider";
import { S } from "../constants";

const ACCENT = "#fce499";

const TABS = [
  { id: "email", label: "E-Mail", icon: "📧" },
  { id: "ai", label: "KI", icon: "✨" },
  { id: "models", label: "Modelle", icon: "🧠" },
  { id: "users", label: "Benutzer", icon: "👤" },
  { id: "mandanten", label: "Mandanten", icon: "🏢", nurAdmin: true },
  { id: "network", label: "Netzwerk", icon: "🛡️" },
  { id: "appearance", label: "Optik", icon: "🎨" },
  { id: "backup", label: "Sicherung", icon: "💾", nurAdmin: true },
  { id: "language", label: "Sprache", icon: "🌍", disabled: true },
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
      alert(fehlerText(e));
    } finally { setSaving(false); }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const { data } = await api.post("/api/settings/email/test", form);
      setTestResult({ ok: true, msg: data.message || "Test-E-Mail gesendet!" });
    } catch (e) {
      setTestResult({ ok: false, msg: fehlerText(e) });
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

function ProviderSelector({ value, onChange }) {
  const opts = [
    { id: "ollama",       label: "Lokal / Ollama",  desc: "Kostenlos, läuft komplett auf deinem Server" },
    { id: "datenmonster", label: "Datenmonster AI", desc: "Zentrale KI per Credits — kein eigener Key nötig" },
  ];
  return (
    <div>
      <label style={{ fontSize: 10, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", display: "block", marginBottom: 6 }}>KI-Anbieter</label>
      <div style={{ display: "flex", gap: 8 }}>
        {opts.map(o => {
          const sel = value === o.id;
          return (
            <div key={o.id} onClick={() => onChange(o.id)}
              style={{ flex: 1, cursor: "pointer", padding: "10px 12px", borderRadius: 6,
                backgroundColor: sel ? "rgba(252,228,153,0.08)" : S.bgEl,
                border: `1px solid ${sel ? "rgba(252,228,153,0.4)" : S.border}` }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: sel ? ACCENT : S.textMain }}>{o.label}</div>
              <div style={{ fontSize: 10, color: S.textDim, marginTop: 2, lineHeight: 1.4 }}>{o.desc}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const DM_MODELS = [
  { id: "auto",        label: "Automatisch", desc: "Datenmonster wählt je Aufgabe (günstig ↔ leistungsfähig)" },
  { id: "gpt-4o-mini", label: "gpt-4o-mini", desc: "Günstig & schnell — Standard" },
  { id: "gpt-4o",      label: "gpt-4o",      desc: "Leistungsfähig — komplexe SQL/Analyse" },
];

function TopUpPanel({ onDone }) {
  const [packages, setPackages] = useState(null);
  const [selected, setSelected] = useState(null);  // package_code
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);         // { type, text }
  const [done, setDone] = useState(false);
  useEffect(() => {
    api.get("/api/ai/credit-packages").then(({ data }) => setPackages(data.packages || [])).catch(() => setPackages([]));
  }, []);
  if (packages === null)
    return <div style={{ fontSize: 11, color: S.textDim }}>Lade Pakete…</div>;
  if (packages.length === 0)
    return <div style={{ fontSize: 11, color: "#e07070" }}>Pakete momentan nicht verfügbar.</div>;

  const requestInvoice = async () => {
    if (!selected) return;
    setBusy(true); setMsg(null);
    try {
      const { data } = await api.post("/api/ai/purchase/invoice", { package_code: selected });
      setMsg({ type: "ok", text: data.message });
      setDone(true);
      onDone && onDone();
    } catch (err) {
      setMsg({ type: "err", text: fehlerText(err) });
    } finally {
      setBusy(false);
    }
  };

  const lS = { fontSize: 10, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", display: "block", marginBottom: 4 };
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <label style={lS}>Paket wählen</label>
      <div style={{ display: "flex", gap: 8 }}>
        {packages.map(p => {
          const s = selected === p.code;
          return (
            <div key={p.code} onClick={() => { setSelected(p.code); setMsg(null); setDone(false); }}
              style={{ flex: 1, cursor: "pointer", padding: "8px 6px", borderRadius: 5, textAlign: "center",
                backgroundColor: s ? "rgba(252,228,153,0.10)" : S.bgEl,
                border: `1px solid ${s ? "rgba(252,228,153,0.45)" : S.border}` }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: s ? ACCENT : S.textMain }}>{p.name}</div>
              <div style={{ fontSize: 13, fontWeight: 800, color: s ? ACCENT : S.textMain, marginTop: 2 }}>{p.credits} Cr.</div>
              <div style={{ fontSize: 10, color: S.textDim, marginTop: 1 }}>{Number(p.price_eur).toFixed(2)} €</div>
            </div>
          );
        })}
      </div>
      {msg && <div style={{ fontSize: 11, color: msg.type === "ok" ? "#7fd07f" : "#e07070" }}>{msg.text}</div>}
      {!done && (
        <button onClick={requestInvoice} disabled={!selected || busy}
          style={{ padding: "8px 12px", borderRadius: 5, border: "none", fontSize: 12, fontWeight: 700,
            backgroundColor: selected ? ACCENT : S.bgEl, color: selected ? "#111" : S.textDim,
            cursor: selected && !busy ? "pointer" : "default", opacity: busy ? 0.6 : 1 }}>
          {busy ? "Rechnung wird erstellt…" : "Rechnung anfordern"}
        </button>
      )}
      <div style={{ fontSize: 9, color: S.textDim }}>
        Du erhältst eine Rechnung per E-Mail (Zahlung u.a. per PayPal). Nach Zahlungseingang schalten wir dein Guthaben frei.
      </div>
    </div>
  );
}

function DatenmonsterAiPanel({ model, onModel }) {
  const [credits, setCredits] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showTopUp, setShowTopUp] = useState(false);
  const loadCredits = () => {
    setLoading(true);
    api.get("/api/ai/credits")
      .then(({ data }) => setCredits(data))
      .catch(e => setCredits({ error: e.message }))
      .finally(() => setLoading(false));
  };
  useEffect(() => { loadCredits(); }, []);
  const lS = { fontSize: 10, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", display: "block", marginBottom: 4 };
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Guthaben */}
      <div style={{ padding: "12px 14px", borderRadius: 6, backgroundColor: "rgba(252,228,153,0.06)", border: "1px solid rgba(252,228,153,0.2)" }}>
        {loading ? (
          <span style={{ fontSize: 11, color: S.textDim }}>Lade Guthaben…</span>
        ) : credits?.error ? (
          <span style={{ fontSize: 11, color: "#e07070" }}>Guthaben nicht abrufbar: {credits.error}</span>
        ) : (
          <>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
              <span style={{ fontSize: 22, fontWeight: 800, color: ACCENT }}>{credits?.balance ?? "–"}</span>
              <span style={{ fontSize: 11, color: S.textDim }}>Credits</span>
            </div>
            {credits?.month && (
              <div style={{ fontSize: 10, color: S.textDim, marginTop: 4 }}>
                Diesen Monat: {credits.month.credits_used ?? 0} Credits · {credits.month.requests ?? 0} Anfragen
              </div>
            )}
          </>
        )}
        <button onClick={() => setShowTopUp(v => !v)}
          style={{ marginTop: 10, padding: "6px 12px", borderRadius: 5, border: "none", backgroundColor: ACCENT, color: "#111", cursor: "pointer", fontSize: 11, fontWeight: 700 }}>
          {showTopUp ? "Schließen" : "Guthaben aufladen"}
        </button>
        {showTopUp && (
          <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid rgba(252,228,153,0.2)" }}>
            <TopUpPanel onDone={loadCredits} />
          </div>
        )}
      </div>
      {/* Modellwahl */}
      <div>
        <label style={lS}>Modell</label>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {DM_MODELS.map(m => {
            const sel = model === m.id;
            return (
              <div key={m.id} onClick={() => onModel(m.id)}
                style={{ cursor: "pointer", padding: "8px 10px", borderRadius: 5,
                  backgroundColor: sel ? "rgba(252,228,153,0.08)" : S.bgEl,
                  border: `1px solid ${sel ? "rgba(252,228,153,0.35)" : S.border}` }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: sel ? ACCENT : S.textMain }}>{m.label}</div>
                <div style={{ fontSize: 10, color: S.textDim, marginTop: 1 }}>{m.desc}</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function AiSettings() {
  const [form, setForm] = useState({
    ai_enabled:  false,
    ai_provider: "ollama",
    ai_base_url: "http://ollama:11434",
    ai_model:    "qwen2.5-coder:3b",
    ai_prose_model: "",   // Textmodell (Berichte/Erklärungen); "" = automatisch
    ai_dm_model: "auto",
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
  const [aiStatus, setAiStatus] = useState(null); // {code_ready, prose_ready, prose_model, loaded_models}
  const [warming, setWarming]   = useState(false);
  // Wahl dieses Browsers (Portal-Kopfzeile, localStorage). Sie wird jedem KI-Aufruf
  // als `provider` mitgeschickt und schlägt damit die Einstellung hier – deshalb
  // muss sie sichtbar sein und beim Speichern einer abweichenden Wahl weichen.
  const [sitzungsWahl, setSitzungsWahl] = useState(getAiProvider());
  useEffect(() => onAiProviderChange(setSitzungsWahl), []);

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
    refreshStatus();
    // Alle 10s aktualisieren solange die Komponente offen ist (laufende Downloads
    // + Modell-Bereitschaft aus /api/ps).
    const interval = setInterval(() => { refreshModels(); refreshStatus(); }, 10000);
    return () => clearInterval(interval);
  }, []);

  const refreshStatus = () =>
    api.get("/api/ai/status").then(({ data }) => setAiStatus(data)).catch(() => {});

  // Modelle vorab in den Speicher laden (Kaltstart vorziehen), damit v.a. die
  // Bericht-Summary nicht in den Timeout läuft. Aktualisiert danach die Badges.
  const handleWarmup = async () => {
    setWarming(true);
    try { await api.post("/api/ai/warmup", {}); } catch (e) { /* Badge bleibt „nicht bereit" */ }
    finally { setWarming(false); refreshStatus(); }
  };

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const effectiveModel = useCustom ? customModel : form.ai_model;
  const modelInstalled = installedModels.some(m => m.name === effectiveModel || m.name?.startsWith(effectiveModel + ":"));

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
      setInstalledModels(prev => prev.some(m => m.name === effectiveModel) ? prev : [...prev, { name: effectiveModel }]);
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
      // Dieser Browser kann eine eigene Anbieterwahl gespeichert haben (Portal-Kopfzeile).
      // Sie wird jedem KI-Aufruf mitgeschickt und schlägt die Einstellung hier – wer also
      // "Datenmonster AI" einstellt, bekam trotzdem weiter das lokale Modell. Widerspricht
      // die Sitzungswahl der gerade gespeicherten, fällt sie weg: die bewusste Wahl in den
      // Einstellungen ist die jüngere und gewinnt.
      if (sitzungsWahl && sitzungsWahl !== form.ai_provider) setAiProvider(null);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
      // Nach dem Speichern die gewählten Modelle direkt aufwärmen (Auto-Warmup),
      // damit sie beim ersten echten Aufruf bereits im Speicher liegen. Nur Ollama.
      if (form.ai_enabled && form.ai_provider === "ollama") handleWarmup();
    } catch (e) {
      alert(fehlerText(e));
    } finally { setSaving(false); }
  };

  const handleTest = async () => {
    setTesting(true); setTestResult(null);
    try {
      if (form.ai_provider === "datenmonster") {
        const { data } = await api.get("/api/ai/credits");
        // Der Server liefert bereits einen vollständigen, handlungsleitenden Satz
        // (z.B. „Lizenz nicht aktiviert …") – kein „Gateway:"-Präfix davorsetzen.
        if (data?.error) setTestResult({ ok: false, msg: data.error });
        else setTestResult({ ok: true, msg: `Datenmonster AI verbunden ✓ — Guthaben: ${data.balance ?? "?"} Credits` });
        return;
      }
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

  // Bereitschafts-Badge: lädt gerade / im Speicher bereit / noch nicht geladen (Kaltstart).
  const readyBadge = (ready) => {
    const base = { fontSize: 9, display: "inline-flex", alignItems: "center", gap: 3, padding: "1px 6px", borderRadius: 8, fontWeight: 600 };
    if (warming) return <span style={{ ...base, color: ACCENT, backgroundColor: "rgba(252,228,153,0.12)" }}><Loader2 size={9} className="animate-spin" /> lädt…</span>;
    if (ready)   return <span style={{ ...base, color: "#6ee7b7", backgroundColor: "rgba(110,231,183,0.1)" }}><Check size={9} /> bereit</span>;
    return <span style={{ ...base, color: S.textDim, backgroundColor: "rgba(255,255,255,0.05)" }}>○ Kaltstart</span>;
  };

  if (loading) return <p style={{ color: S.textDim, fontSize: 12 }}>Lade...</p>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <p style={{ fontSize: 11, color: S.textDim, margin: 0, lineHeight: 1.6 }}>
        KI-Unterstützung für SQL-, Python- und Expressions-Nodes sowie den Mapping-Canvas.
        Wähle den Anbieter: <b>Ollama</b> (kostenlos, lokal) oder <b>Datenmonster AI</b>
        (zentral per Credits, kein eigener OpenAI-Key nötig).
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
          {/* Anbieterwahl */}
          <ProviderSelector value={form.ai_provider} onChange={v => set("ai_provider", v)} />

          {sitzungsWahl && sitzungsWahl !== form.ai_provider && (
            <div style={{ fontSize: 11, lineHeight: 1.5, color: S.textDim, marginTop: -4,
              padding: "8px 10px", border: `1px solid ${S.border}`, borderRadius: 7 }}>
              Dieser Browser nutzt gerade die abweichende Sitzungswahl{" "}
              <b style={{ color: S.textBright }}>
                {sitzungsWahl === "datenmonster" ? "Datenmonster AI" : "Lokal"}
              </b>{" "}
              (gesetzt in der Portal-Kopfzeile). Sie gilt für alle KI-Antworten dieses
              Browsers und geht der Einstellung hier vor. Beim Speichern wird sie
              zurückgesetzt.{" "}
              <button type="button" onClick={() => setAiProvider(null)}
                style={{ background: "none", border: "none", padding: 0, cursor: "pointer",
                  color: ACCENT, fontSize: 11, textDecoration: "underline" }}>
                Jetzt zurücksetzen
              </button>
            </div>
          )}

          {form.ai_provider === "datenmonster" && (
            <DatenmonsterAiPanel model={form.ai_dm_model} onModel={v => set("ai_dm_model", v)} />
          )}

          {form.ai_provider === "ollama" && (<>
          {/* Ollama URL */}
          <div>
            <label style={lS}>Ollama URL</label>
            <input style={iS} value={form.ai_base_url} onChange={e => set("ai_base_url", e.target.value)}
              placeholder="http://ollama:11434" />
            <span style={{ fontSize: 10, color: S.textDim, marginTop: 3, display: "block" }}>
              Im Docker-Stack: http://ollama:11434 · Extern: http://localhost:11434
            </span>
          </div>

          {/* Modell (Code) */}
          <div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
              <label style={{ ...lS, marginBottom: 0 }}>Modell für Code (SQL, Python, Assistent)</label>
              {readyBadge(aiStatus?.code_ready)}
            </div>
            {!useCustom ? (
              <div style={{ maxHeight: 260, overflowY: "auto", display: "flex", flexDirection: "column", gap: 4, paddingRight: 2 }}>
                {PRESET_MODELS.map(m => {
                  const isSelected = form.ai_model === m.id;
                  const isInstalled = installedModels.some(i => i.name === m.id || i.name?.startsWith(m.id + ":"));
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
                {/* Zusätzlich installierte Modelle, die nicht in PRESET_MODELS sind */}
                {installedModels
                  .filter(m => !PRESET_MODELS.some(p => m.name === p.id || m.name?.startsWith(p.id + ":")))
                  .map(m => {
                    const isSelected = form.ai_model === m.name;
                    return (
                      <div key={m.name}
                        onClick={() => { set("ai_model", m.name); setPullProgress(null); }}
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
                          <span style={{ fontSize: 9, display: "flex", alignItems: "center", gap: 3, color: "#6ee7b7" }}>
                            <Check size={10} /> installiert
                          </span>
                        </div>
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

          {/* Modell (Text/Berichte) */}
          <div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
              <label style={{ ...lS, marginBottom: 0 }}>Modell für Texte (Berichte, Erklärungen)</label>
              {readyBadge(aiStatus?.prose_ready)}
            </div>
            <select style={iS} value={form.ai_prose_model} onChange={e => set("ai_prose_model", e.target.value)}>
              <option value="">Automatisch{aiStatus?.prose_model ? ` (${aiStatus.prose_model})` : ""}</option>
              {installedModels.map(m => (
                <option key={m.name} value={m.name}>{m.name}</option>
              ))}
            </select>
            <span style={{ fontSize: 10, color: S.textDim, marginTop: 3, display: "block", lineHeight: 1.4 }}>
              Für flüssiges Deutsch in Berichten/Zusammenfassungen. Code-Modelle (z.B. Qwen-Coder)
              schreiben oft holpriges Deutsch – hier ein Chat-Modell wie <b>gemma3:4b</b> oder
              <b> qwen3.5:4b</b> wählen. „Automatisch" nimmt ein bewährtes installiertes Textmodell.
            </span>
          </div>

          {/* Warmup: Modelle vorab in den Speicher laden */}
          <div style={{ padding: "10px 12px", borderRadius: 6, backgroundColor: S.bgEl, border: `1px solid ${S.border}` }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 11, color: S.textMain, fontWeight: 600 }}>Modelle vorladen (Kaltstart vermeiden)</div>
                <p style={{ fontSize: 10, color: S.textDim, margin: "3px 0 0", lineHeight: 1.4 }}>
                  Lädt Code- und Textmodell in den Speicher, damit z.B. der Bericht die KI-Analyse
                  nicht wegen Kaltstart-Timeout verwirft. Passiert automatisch beim Speichern.
                </p>
              </div>
              <button onClick={handleWarmup} disabled={warming}
                style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 12px", borderRadius: 5, border: `1px solid ${S.border}`, backgroundColor: "transparent", color: warming ? S.textDim : ACCENT, cursor: warming ? "default" : "pointer", fontSize: 11, fontWeight: 600, flexShrink: 0 }}>
                {warming ? <Loader2 size={12} className="animate-spin" /> : <Zap size={12} />}
                {warming ? "Lädt…" : "Jetzt laden"}
              </button>
            </div>
          </div>

          </>)}

          {/* Timeout */}
          <div>
            <label style={lS}>Timeout (Sekunden)</label>
            <input style={{ ...iS, width: 80 }} type="number" min={10} max={600}
              value={form.ai_timeout} onChange={e => set("ai_timeout", parseInt(e.target.value) || 120)} />
            <span style={{ fontSize: 10, color: S.textDim, marginTop: 3, display: "block" }}>
              {form.ai_provider === "datenmonster" ? "Gilt auch für Gateway-Anfragen" : "Ohne GPU: 60–120s empfohlen"}
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

const ROLE_META = {
  admin:  { label: "Admin",  color: "#fca5a5", bg: "rgba(224,112,112,0.12)", border: "rgba(224,112,112,0.35)", hint: "Vollzugriff inkl. Benutzerverwaltung" },
  editor: { label: "Editor", color: "#93c5fd", bg: "rgba(96,165,250,0.12)",  border: "rgba(96,165,250,0.35)", hint: "Zugriff auf die volle Plattform (Mappings, Pipelines …)" },
  portal: { label: "Portal", color: "#fce499", bg: "rgba(252,228,153,0.10)", border: "rgba(252,228,153,0.35)", hint: "Sieht nur veröffentlichte Formulare, keinen Editor" },
};


// ─── Datensicherung ───────────────────────────────────────────────────────────
// Die Anwendungsdaten liegen im Docker-Volume, nicht im Projektordner. Ohne
// Sicherung ist ein verlorenes Volume der Verlust der gesamten Einrichtung.
function BackupSettings() {
  const [liste, setListe] = useState([]);
  const [frei, setFrei] = useState(null);
  const [behalten, setBehalten] = useState(14);
  const [laden, setLaden] = useState(true);
  const [arbeitet, setArbeitet] = useState(false);
  const [meldung, setMeldung] = useState(null);
  const [pruefung, setPruefung] = useState(null);   // { name, inhalt }
  const [fertig, setFertig] = useState(null);       // Ergebnis des Zurückspielens

  const laden_ = async () => {
    setLaden(true);
    try {
      const { data } = await api.get("/api/backup/");
      setListe(data.sicherungen || []);
      setFrei(data.speicher_frei);
      setBehalten(data.behalten);
    } catch (e) {
      setMeldung({ art: "fehler", text: fehlerText(e) });
    } finally { setLaden(false); }
  };
  useEffect(() => { laden_(); }, []);

  const kb = (b) => b >= 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.round(b / 1024)} KB`;
  const zeit = (iso) => { try { return new Date(iso).toLocaleString("de-DE"); } catch { return iso; } };

  const sichern = async () => {
    setArbeitet(true); setMeldung(null);
    try {
      const { data } = await api.post("/api/backup/");
      setMeldung({ art: "ok", text: `Sicherung angelegt: ${data.name} (${kb(data.groesse)})` });
      await laden_();
    } catch (e) {
      setMeldung({ art: "fehler", text: fehlerText(e) });
    } finally { setArbeitet(false); }
  };

  const herunterladen = async (name) => {
    try {
      const res = await api.get(`/api/backup/${name}/download`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a");
      a.href = url; a.download = name; a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setMeldung({ art: "fehler", text: "Download fehlgeschlagen: " + (fehlerText(e)) });
    }
  };

  const loeschen = async (name) => {
    setArbeitet(true);
    try { await api.delete(`/api/backup/${name}`); await laden_(); }
    catch (e) { setMeldung({ art: "fehler", text: fehlerText(e) }); }
    finally { setArbeitet(false); }
  };

  // Erst prüfen, dann bestätigen lassen – wer zurückspielt, soll vorher sehen,
  // was er bekommt.
  const pruefen = async (name) => {
    setArbeitet(true); setMeldung(null); setFertig(null);
    try {
      const { data } = await api.post(`/api/backup/restore?name=${encodeURIComponent(name)}&bestaetigt=false`);
      setPruefung({ name, inhalt: data.inhalt });
    } catch (e) {
      setMeldung({ art: "fehler", text: fehlerText(e) });
    } finally { setArbeitet(false); }
  };

  const zurueckspielen = async () => {
    if (!pruefung) return;
    setArbeitet(true);
    try {
      const { data } = await api.post(
        `/api/backup/restore?name=${encodeURIComponent(pruefung.name)}&bestaetigt=true`);
      setFertig(data); setPruefung(null); await laden_();
    } catch (e) {
      setMeldung({ art: "fehler", text: fehlerText(e) });
    } finally { setArbeitet(false); }
  };

  // Ein Archiv von aussen wird geprüft und in die Liste aufgenommen. Ob es zur
  // laufenden Anlage passt, entscheidet der Mensch – zurückgespielt wird es
  // danach wie jedes andere, mit derselben Rückfrage.
  const hochladen = async (ev) => {
    const datei = ev.target.files?.[0];
    if (!datei) return;
    setArbeitet(true); setMeldung(null); setFertig(null);
    try {
      const fd = new FormData(); fd.append("datei", datei);
      const { data } = await api.post("/api/backup/upload", fd,
        { headers: { "Content-Type": "multipart/form-data" } });
      const inhalt = Object.entries(data.inhalt || {})
        .filter(([, v]) => v !== null).map(([k, v]) => `${v} ${k}`).join(", ");
      setMeldung({ art: "ok",
        text: `Eingespielt als ${data.name} – enthält ${inhalt}. `
            + `Zum Übernehmen in der Liste auf „Zurückspielen" klicken.` });
      await laden_();
    } catch (e) {
      setMeldung({ art: "fehler", text: fehlerText(e) });
    } finally { setArbeitet(false); ev.target.value = ""; }
  };

  const kasten = (farbe, rand) => ({
    padding: "10px 12px", borderRadius: 6, fontSize: 11, lineHeight: 1.5,
    background: farbe, border: `1px solid ${rand}`, marginBottom: 12,
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div>
        <p style={{ fontSize: 12, fontWeight: 700, color: S.textBright, margin: "0 0 4px" }}>
          Datensicherung
        </p>
        <p style={{ fontSize: 11, color: S.textDim, lineHeight: 1.5, margin: 0 }}>
          Gesichert werden die Datenbank – mit allen Mappings, Formularen, Warnregeln und
          Zeitplänen – sowie die Dateien der Datasets. Die Anwendung muss dafür nicht
          angehalten werden.
        </p>
      </div>

      <div style={kasten("rgba(252,228,153,0.08)", "rgba(252,228,153,0.3)")}>
        <strong>Lade die Sicherung herunter.</strong> Sie liegt sonst auf demselben Server
        wie die Daten – beim Ausfall dieses Servers wäre auch sie verloren. Das Archiv
        enthält die Zugangsdaten aller Verbindungen (verschlüsselt) und gehört an einen
        geschützten Ort.
        <br /><br />
        Der <code>SECRET_KEY</code> aus der <code>.env</code> ist <strong>nicht</strong> im
        Archiv – ohne ihn lassen sich die Zugangsdaten später nicht entschlüsseln. Sichere
        die <code>.env</code> getrennt, oder nutze <code>./backup.sh</code> auf dem Server,
        das beides zusammen ablegt.
      </div>

      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <button onClick={sichern} disabled={arbeitet}
          style={{ padding: "7px 14px", borderRadius: 4, fontSize: 11, fontWeight: 700,
                   cursor: arbeitet ? "default" : "pointer", border: "none",
                   background: ACCENT, color: "#1a1a1a", display: "flex",
                   alignItems: "center", gap: 6, opacity: arbeitet ? 0.6 : 1 }}>
          {arbeitet ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
          Jetzt sichern
        </button>
        <label style={{ padding: "7px 14px", borderRadius: 4, fontSize: 11, fontWeight: 600,
                        cursor: "pointer", border: `1px solid ${S.border}`, color: S.textDim }}>
          Archiv einspielen …
          <input type="file" accept=".tar.gz,.gz" onChange={hochladen} style={{ display: "none" }} />
        </label>
        {frei !== null && (
          <span style={{ fontSize: 10, color: S.textDim, marginLeft: "auto" }}>
            {kb(frei)} frei · die letzten {behalten} Sicherungen bleiben liegen
          </span>
        )}
      </div>

      {meldung && (
        <div style={kasten(
          meldung.art === "fehler" ? "rgba(224,112,112,0.1)" : "rgba(110,231,183,0.08)",
          meldung.art === "fehler" ? "rgba(224,112,112,0.35)" : "rgba(110,231,183,0.3)")}>
          {meldung.text}
        </div>
      )}

      {fertig && (
        <div style={kasten("rgba(252,228,153,0.12)", "rgba(252,228,153,0.45)")}>
          <strong>Zurückgespielt.</strong> {fertig.hinweis}
          <br />
          Der vorherige Stand wurde vorher gesichert als <code>{fertig.sicherheitskopie}</code>.
        </div>
      )}

      {pruefung && (
        <div style={kasten("rgba(224,112,112,0.1)", "rgba(224,112,112,0.4)")}>
          <strong>Wirklich zurückspielen?</strong>
          <br />
          Archiv <code>{pruefung.name}</code> enthält:{" "}
          {Object.entries(pruefung.inhalt || {})
            .filter(([, v]) => v !== null)
            .map(([k, v]) => `${v} ${k}`).join(", ")}.
          <br /><br />
          <strong>Der jetzige Stand wird dabei ersetzt und ist danach weg.</strong> Die
          laufende Anwendung arbeitet zunächst weiter mit den alten Daten – erst nach einem
          Neustart des Backend-Containers gilt der zurückgespielte Stand:
          <br />
          <code style={{ display: "inline-block", marginTop: 4 }}>docker compose restart backend</code>
          <br /><br />
          Zur Sicherheit wird der jetzige Stand vorher automatisch als Archiv abgelegt.
          {pruefung.name.includes("_import") && (
            <>
              <br /><br />
              <strong>Dieses Archiv wurde von aussen eingespielt.</strong> Es kann aus einer
              anderen Anlage stammen – prüfe die Zahlen oben, bevor du fortfährst. Passen sie
              nicht zu dem, was du erwartest, brich lieber ab.
            </>
          )}
          <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
            <button onClick={zurueckspielen} disabled={arbeitet}
              style={{ padding: "6px 12px", borderRadius: 4, fontSize: 11, fontWeight: 700,
                       cursor: "pointer", border: "none", background: "#e07070", color: "#fff" }}>
              Ja, zurückspielen
            </button>
            <button onClick={() => setPruefung(null)}
              style={{ padding: "6px 12px", borderRadius: 4, fontSize: 11, fontWeight: 600,
                       cursor: "pointer", border: `1px solid ${S.border}`,
                       background: "none", color: S.textDim }}>
              Abbrechen
            </button>
          </div>
        </div>
      )}

      <div>
        <p style={{ fontSize: 10, color: S.textDim, textTransform: "uppercase",
                    letterSpacing: "0.06em", marginBottom: 6 }}>
          Sicherungen auf dem Server
        </p>
        {laden ? (
          <p style={{ fontSize: 11, color: S.textDim }}>Lädt …</p>
        ) : liste.length === 0 ? (
          <p style={{ fontSize: 11, color: S.textDim, fontStyle: "italic" }}>
            Noch keine Sicherung vorhanden.
          </p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {liste.map(s => (
              <div key={s.name} style={{ display: "flex", alignItems: "center", gap: 8,
                     padding: "7px 10px", borderRadius: 4, background: S.bgEl,
                     border: `1px solid ${S.border}`, fontSize: 11 }}>
                <span style={{ color: S.textBright, fontFamily: "ui-monospace, monospace" }}>
                  {s.name}
                </span>
                {s.importiert && (
                  <span title="Von aussen eingespielt – stammt möglicherweise aus einer anderen Anlage"
                    style={{ fontSize: 9, fontWeight: 700, padding: "1px 5px", borderRadius: 3,
                             color: "#fcd34d", background: "rgba(252,211,77,0.12)",
                             border: "1px solid rgba(252,211,77,0.35)" }}>
                    eingespielt
                  </span>
                )}
                <span style={{ color: S.textDim }}>{kb(s.groesse)}</span>
                <span style={{ color: S.textDim, marginLeft: "auto" }}>{zeit(s.erstellt)}</span>
                <button onClick={() => herunterladen(s.name)} title="Herunterladen"
                  style={{ background: "none", border: "none", cursor: "pointer",
                           color: ACCENT, padding: 2 }}>
                  <Download size={13} />
                </button>
                <button onClick={() => pruefen(s.name)} disabled={arbeitet} title="Zurückspielen"
                  style={{ background: "none", border: `1px solid ${S.border}`, borderRadius: 3,
                           cursor: "pointer", color: S.textDim, fontSize: 10,
                           padding: "2px 7px", fontWeight: 600 }}>
                  Zurückspielen
                </button>
                <button onClick={() => loeschen(s.name)} disabled={arbeitet} title="Löschen"
                  style={{ background: "none", border: "none", cursor: "pointer",
                           color: S.textDim, padding: 2 }}>
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <p style={{ fontSize: 10, color: S.textDim, lineHeight: 1.6, marginTop: 4 }}>
        Für die regelmäßige Sicherung eignet sich <code>./backup.sh</code> auf dem Server –
        es legt zusätzlich die <code>.env</code> mit ins Archiv und lässt sich in die
        Aufgabenplanung eintragen. Beide arbeiten im selben Verzeichnis, seine Archive
        stehen also auch hier in der Liste. Eine Sicherung, die noch nie zurückgespielt
        wurde, ist keine: prüfe das gelegentlich.
      </p>
    </div>
  );
}

/**
 * Mandanten: welche Verbindung ist ein Betrieb, und wer darf ihn sehen.
 *
 * Ein Mandant ist keine eigene Entität, sondern eine als Mandant markierte
 * DB-Verbindung. Dieselben Cockpits laufen dann wahlweise gegen die eine oder die
 * andere WaWi; Fixkosten, Ausschlusslisten und Nachtläufe hängen am Mandanten.
 *
 * Die Freigabe folgt der Konvention der Formular-Veröffentlichung: keine Auswahl
 * heißt "alle". Erst wer etwas ankreuzt, wird auf genau das beschränkt.
 */
function MandantenSettings() {
  const [verbindungen, setVerbindungen] = useState([]);
  const [benutzer, setBenutzer] = useState([]);
  const [busy, setBusy] = useState(null);
  const [hinweis, setHinweis] = useState(null);
  // Freigaben gelten je Projekt: derselbe Benutzer darf im einen Projekt eine
  // andere WaWi sehen als im anderen. "" = projektuebergreifend (gilt ueberall).
  const [projekte, setProjekte] = useState([]);
  const [projekt, setProjekt] = useState("");

  const laden = (pid = projekt) => Promise.all([
    api.get("/api/mandanten/verwaltung"),
    api.get("/api/mandanten/freigaben", { params: pid ? { project_id: pid } : {} }),
  ]).then(([v, f]) => { setVerbindungen(v.data || []); setBenutzer(f.data || []); })
    .catch(() => {});

  useEffect(() => { laden(); }, []);
  useEffect(() => { api.get("/api/projects/").then(r => setProjekte(r.data || [])).catch(() => {}); }, []);
  useEffect(() => { laden(projekt); }, [projekt]);

  const speichern = async (c, patch) => {
    setBusy(c.connection_id); setHinweis(null);
    try {
      const { data } = await api.put("/api/mandanten/verwaltung", {
        connection_id: c.connection_id,
        is_mandant: patch.is_mandant ?? c.is_mandant,
        mandant_label: patch.mandant_label ?? c.mandant_label,
        ist_standard: patch.ist_standard ?? c.ist_standard,
      });
      const ue = data.uebernommen || {};
      if (ue.kosten || ue.zeitplan) {
        setHinweis(`Bisherige Daten übernommen: ${ue.kosten} Kostenart(en)`
          + (ue.zeitplan ? `, ${ue.zeitplan} Nachtlauf` : ""));
      }
      await laden();
    } catch (e) {
      alert(fehlerText(e, "Speichern fehlgeschlagen"));
    } finally { setBusy(null); }
  };

  const freigabeUmschalten = async (u, cid) => {
    const neu = u.mandanten.includes(cid)
      ? u.mandanten.filter(x => x !== cid) : [...u.mandanten, cid];
    setBusy(`u${u.user_id}`);
    try {
      await api.put("/api/mandanten/freigaben", { user_id: u.user_id, mandanten: neu,
        project_id: projekt || null });
      await laden();
    } catch (e) {
      alert(fehlerText(e, "Speichern fehlgeschlagen"));
    } finally { setBusy(null); }
  };

  const mandanten = verbindungen.filter(v => v.is_mandant);
  const iS = { backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4,
               color: S.textBright, fontSize: 11, padding: "4px 8px", outline: "none" };
  const lS = { fontSize: 10, color: S.textDim, textTransform: "uppercase",
               letterSpacing: "0.06em", display: "block", marginBottom: 6 };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <p style={{ fontSize: 11, color: S.textDim, margin: 0 }}>
        Ein Mandant ist eine WaWi-Datenbank. Markierte Verbindungen erscheinen im
        Portal als Umschalter – dieselben Cockpits, andere Zahlen. Fixkosten,
        Ausschlusslisten und Nachtläufe gehören jeweils genau einem Mandanten.
      </p>

      <div>
        <span style={lS}>Verbindungen</span>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {verbindungen.map(c => (
            <div key={c.connection_id} style={{ padding: "8px 10px", borderRadius: 5,
              backgroundColor: S.bgEl, border: `1px solid ${S.border}`,
              display: "flex", flexDirection: "column", gap: 6 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                <input type="checkbox" checked={c.is_mandant} disabled={busy === c.connection_id}
                  onChange={e => speichern(c, { is_mandant: e.target.checked })} />
                <span style={{ fontSize: 12, color: S.textMain, flex: 1 }}>
                  {c.verbindung}
                  <span style={{ color: S.textDim, fontSize: 10.5 }}> · {c.datenbank}</span>
                </span>
                {busy === c.connection_id && <Loader2 size={11} className="animate-spin" />}
              </label>
              {c.is_mandant && (
                <div style={{ display: "flex", alignItems: "center", gap: 8, paddingLeft: 22 }}>
                  <input style={{ ...iS, flex: 1 }} defaultValue={c.mandant_label}
                    placeholder={`Anzeigename (sonst „${c.verbindung}")`}
                    onBlur={e => e.target.value !== c.mandant_label
                      && speichern(c, { mandant_label: e.target.value })} />
                  <label title="Erstauswahl neuer Benutzer; erbt die bisherigen Kostendaten"
                    style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 10.5,
                      color: S.textDim, cursor: "pointer", whiteSpace: "nowrap" }}>
                    <input type="radio" checked={c.ist_standard}
                      onChange={() => speichern(c, { ist_standard: true })} />
                    Standard
                  </label>
                </div>
              )}
            </div>
          ))}
          {!verbindungen.length && (
            <span style={{ fontSize: 11, color: S.textDim }}>Keine Verbindungen angelegt.</span>
          )}
        </div>
        {hinweis && (
          <p style={{ fontSize: 10.5, color: "#6ee7b7", margin: "6px 0 0" }}>✓ {hinweis}</p>
        )}
      </div>

      {mandanten.length > 0 && (
        <div style={{ borderTop: `1px solid ${S.border}`, paddingTop: 14 }}>
          <span style={lS}>Wer darf welchen Mandanten</span>
          <div style={{ display: "flex", alignItems: "center", gap: 8, margin: "0 0 8px" }}>
            <span style={{ fontSize: 10.5, color: S.textDim, whiteSpace: "nowrap" }}>
              Gilt für
            </span>
            <select value={projekt} onChange={e => setProjekt(e.target.value)}
              style={{ ...iS, maxWidth: 260 }}>
              <option value="">alle Projekte (übergreifend)</option>
              {projekte.map(p => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          <p style={{ fontSize: 10.5, color: S.textDim, margin: "0 0 8px" }}>
            Nichts angekreuzt = alle Mandanten. Administratoren sehen ohnehin alle.
            {projekt
              ? " Angezeigt werden die Freigaben dieses Projekts samt den übergreifenden; gespeichert wird nur für dieses Projekt."
              : " Übergreifende Freigaben gelten in jedem Projekt."}
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {benutzer.map(u => (
              <div key={u.user_id} style={{ padding: "8px 10px", borderRadius: 5,
                backgroundColor: S.bgEl, border: `1px solid ${S.border}` }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                  <span style={{ fontSize: 12, color: S.textMain, flex: 1 }}>{u.username}</span>
                  {u.is_admin && <span style={{ fontSize: 9.5, color: S.textDim }}>alle (Admin)</span>}
                  {!u.is_admin && !u.mandanten.length &&
                    <span style={{ fontSize: 9.5, color: S.textDim }}>alle</span>}
                  {busy === `u${u.user_id}` && <Loader2 size={11} className="animate-spin" />}
                </div>
                {!u.is_admin && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 10, paddingLeft: 2 }}>
                    {mandanten.map(m => (
                      <label key={m.connection_id} style={{ display: "flex", alignItems: "center",
                        gap: 5, fontSize: 11, color: S.textDim, cursor: "pointer" }}>
                        <input type="checkbox" checked={u.mandanten.includes(m.connection_id)}
                          onChange={() => freigabeUmschalten(u, m.connection_id)} />
                        {m.mandant_label || m.verbindung}
                      </label>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}


const roleOf = (u) => (u.is_admin ? "admin" : (u.is_portal_only ? "portal" : "editor"));
const roleToFlags = (role) => ({
  is_admin:       role === "admin",
  is_portal_only: role === "portal",
});

function UserManagement() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState({ username: "", password: "", role: "editor" });
  const [creating, setCreating] = useState(false);
  const [result, setResult] = useState(null);
  const [showPw, setShowPw] = useState(false);
  const [busyId, setBusyId] = useState(null);

  const load = () => api.get("/api/auth/users").then(({ data }) => setUsers(data)).catch(() => {});
  useEffect(() => { load(); }, []);

  const iS = { backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, color: S.textBright, fontSize: 11, padding: "6px 10px", outline: "none", width: "100%" };
  const lS = { fontSize: 10, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", display: "block", marginBottom: 4 };
  const selS = { backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, color: S.textBright, fontSize: 11, padding: "4px 6px", outline: "none", cursor: "pointer" };

  const handleCreate = async () => {
    if (!form.username.trim() || form.password.length < 6) {
      setResult({ ok: false, msg: "Benutzername und Passwort (min. 6 Zeichen) erforderlich" });
      return;
    }
    setCreating(true); setResult(null);
    try {
      const { data } = await api.post("/api/auth/register", {
        username: form.username.trim(), password: form.password, ...roleToFlags(form.role),
      });
      setResult({ ok: true, msg: `Benutzer "${data.username}" (${ROLE_META[form.role].label}) angelegt` });
      setForm({ username: "", password: "", role: "editor" });
      load();
    } catch (e) {
      setResult({ ok: false, msg: fehlerText(e, "Fehler beim Anlegen") });
    } finally { setCreating(false); }
  };

  const handleRoleChange = async (u, role) => {
    setBusyId(u.id);
    try {
      await api.patch(`/api/auth/users/${u.id}`, roleToFlags(role));
      await load();
    } catch (e) {
      alert(fehlerText(e, "Rolle ändern fehlgeschlagen"));
    } finally { setBusyId(null); }
  };

  const handleDelete = async (id, name) => {
    if (!confirm(`Benutzer "${name}" wirklich löschen?`)) return;
    try {
      await api.delete(`/api/auth/users/${id}`);
      load();
    } catch (e) {
      alert(fehlerText(e, "Löschen fehlgeschlagen"));
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <p style={{ fontSize: 11, color: S.textDim, margin: 0 }}>Benutzer anlegen und verwalten. Nur Administratoren haben Zugriff auf diese Ansicht.</p>

      {/* Wer auf welche Datenbank darf, wird NICHT hier entschieden. Das steht
          hier, weil man es genau hier sucht – und sonst nirgends erfährt. */}
      <div style={{ fontSize: 10.5, color: S.textDim, lineHeight: 1.6,
        background: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 6,
        padding: "9px 11px" }}>
        <b style={{ color: S.textMain }}>Auf welche Datenbanken jemand zugreift,
        wird nicht hier festgelegt</b>, sondern in zwei Schritten:
        <div style={{ marginTop: 5 }}>
          1. <b>Projektmitglied machen</b> (im Projekt selbst, Abschnitt „Mitglieder“):
          damit erreicht der Benutzer die Verbindungen, die diesem Projekt
          zugeordnet sind – und nur die.
        </div>
        <div style={{ marginTop: 3 }}>
          2. <b>Mandantenfreigabe</b> (Reiter „Mandanten“): schränkt innerhalb eines
          Projekts weiter ein, zwischen welchen WaWi-Datenbanken er umschalten darf.
          Das greift nur bei Verbindungen, die als Mandant markiert sind.
        </div>
        <div style={{ marginTop: 5, color: S.textDim }}>
          Administratoren sehen unabhängig davon alles.
        </div>
      </div>

      {/* Bestehende Benutzer */}
      {users.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={lS}>Bestehende Benutzer</span>
          {users.map(u => {
            const isSelf = me && u.username === me.username;
            const rm = ROLE_META[roleOf(u)];
            return (
              <div key={u.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", borderRadius: 4, backgroundColor: S.bgEl, border: `1px solid ${S.border}` }}>
                <span style={{ fontSize: 12, color: S.textMain, flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{u.username}</span>
                <span title={rm.hint} style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: rm.color, backgroundColor: rm.bg, border: `1px solid ${rm.border}`, borderRadius: 4, padding: "2px 6px", whiteSpace: "nowrap" }}>{rm.label}</span>
                {isSelf ? (
                  <span style={{ fontSize: 10, color: S.textDim, fontStyle: "italic", whiteSpace: "nowrap" }}>(du)</span>
                ) : (
                  <select value={roleOf(u)} disabled={busyId === u.id} onChange={e => handleRoleChange(u, e.target.value)}
                    title="Rolle ändern" style={selS}>
                    <option value="admin">Admin</option>
                    <option value="editor">Editor</option>
                    <option value="portal">Portal</option>
                  </select>
                )}
                <button onClick={() => handleDelete(u.id, u.username)} disabled={isSelf}
                  style={{ background: "none", border: "none", color: isSelf ? S.border : S.textDim, cursor: isSelf ? "not-allowed" : "pointer", padding: 2, display: "flex", alignItems: "center" }}
                  title={isSelf ? "Eigenen Account kann man nicht löschen" : "Benutzer löschen"}>
                  <Trash2 size={12} />
                </button>
              </div>
            );
          })}
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
        <div>
          <label style={lS}>Rolle</label>
          <select style={{ ...iS, cursor: "pointer" }} value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))}>
            <option value="editor">Editor — volle Plattform</option>
            <option value="portal">Portal — nur veröffentlichte Formulare</option>
            <option value="admin">Admin — Vollzugriff inkl. Benutzerverwaltung</option>
          </select>
          <p style={{ fontSize: 10, color: S.textDim, margin: "4px 0 0" }}>{ROLE_META[form.role].hint}</p>
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

function formatBytes(bytes: number) {
  if (!bytes) return "?";
  if (bytes < 1e9) return `${(bytes / 1e6).toFixed(0)} MB`;
  return `${(bytes / 1e9).toFixed(1)} GB`;
}

function guessModelLanguages(name: string): string[] {
  const n = name.toLowerCase();
  if (/embed|nomic|mxbai|all-minilm/.test(n)) return [];
  if (/vision|llava|moondream|minicpm-v/.test(n)) return [];
  if (/qwen/.test(n)) return ["EN", "ZH", "DE"];
  if (/deepseek/.test(n)) return ["EN", "ZH"];
  if (/mistral-nemo|mistral-small/.test(n)) return ["EN", "FR", "DE", "ES"];
  if (/mistral/.test(n)) return ["EN", "FR", "DE"];
  if (/command-r/.test(n)) return ["EN", "FR", "DE", "ES", "IT"];
  if (/gemma/.test(n)) return ["EN"];
  if (/llama/.test(n)) return ["EN"];
  if (/phi/.test(n)) return ["EN"];
  if (/granite/.test(n)) return ["EN"];
  return ["EN"];
}

function guessModelType(name: string): string[] {
  const n = name.toLowerCase();
  const tags: string[] = [];
  if (/code|coder|starcoder|deepseek-coder|qwen.*coder|codellama/.test(n)) tags.push("Coding");
  if (/embed|nomic|mxbai|all-minilm/.test(n)) tags.push("Embedding");
  if (/vision|llava|moondream|minicpm-v/.test(n)) tags.push("Vision");
  if (!tags.length) tags.push("Chat");
  return tags;
}

function guessModelSize(name: string, size: number): string {
  const n = name.toLowerCase();
  const m = n.match(/(\d+\.?\d*)b/);
  if (m) {
    const b = parseFloat(m[1]);
    if (b <= 3) return "≤3B";
    if (b <= 8) return "7B";
    return "≥13B";
  }
  if (size) {
    if (size < 2.5e9) return "≤3B";
    if (size < 10e9) return "7B";
    return "≥13B";
  }
  return "?";
}

const SIZE_FILTERS = ["Alle", "≤3B", "7B", "≥13B"];
const TYPE_FILTERS = ["Alle", "Chat", "Coding", "Embedding", "Vision"];

interface CatalogEntry {
  name: string;
  description: string;
  sizeLabel: string;
  sizeDisplay: string;
  types: string[];
}

const CATALOG: CatalogEntry[] = [
  // ── Chat · Klein ≤3B ─────────────────────────────────────────────────────
  { name: "gemma3:270m",       description: "Googles winzigstes Gemma-3-Modell – extrem schnell",            sizeLabel: "≤3B",  sizeDisplay: "200 MB", types: ["Chat"] },
  { name: "gemma3:1b",         description: "Googles kleinstes Gemma-3-Modell, ideal für schwache Hardware",  sizeLabel: "≤3B",  sizeDisplay: "815 MB", types: ["Chat"] },
  { name: "gemma3:4b",         description: "Ausgewogenes Google-Modell für Alltagsaufgaben",                 sizeLabel: "≤3B",  sizeDisplay: "2.5 GB", types: ["Chat"] },
  { name: "gemma3n:e2b",       description: "Gemma3 Nano – mobil-optimiert, 2B effektive Parameter",         sizeLabel: "≤3B",  sizeDisplay: "1.5 GB", types: ["Chat"] },
  { name: "gemma3n:e4b",       description: "Gemma3 Nano – mobil-optimiert, 4B effektive Parameter",         sizeLabel: "≤3B",  sizeDisplay: "2.5 GB", types: ["Chat"] },
  { name: "llama3.2:1b",       description: "Metas kleinstes Llama-3.2-Modell",                               sizeLabel: "≤3B",  sizeDisplay: "1.3 GB", types: ["Chat"] },
  { name: "llama3.2:3b",       description: "Schnelles, kompaktes Meta-Modell",                               sizeLabel: "≤3B",  sizeDisplay: "2.0 GB", types: ["Chat"] },
  { name: "phi4-mini:3.8b",    description: "Microsofts kompaktes, hochwertiges Sprachmodell",                sizeLabel: "≤3B",  sizeDisplay: "2.5 GB", types: ["Chat"] },
  { name: "qwen2.5:3b",        description: "Alibabas effizientes Multilingual-Modell",                       sizeLabel: "≤3B",  sizeDisplay: "2.0 GB", types: ["Chat"] },
  { name: "qwen3:0.6b",        description: "Qwen3 – kleinstes Modell, sehr schnell auf CPU",                 sizeLabel: "≤3B",  sizeDisplay: "0.5 GB", types: ["Chat"] },
  { name: "qwen3:1.7b",        description: "Qwen3 – kompakt, gut für einfache Aufgaben",                    sizeLabel: "≤3B",  sizeDisplay: "1.1 GB", types: ["Chat"] },
  { name: "qwen3:4b",          description: "Qwen3 – ausgewogene Größe für CPU-Betrieb",                     sizeLabel: "≤3B",  sizeDisplay: "2.6 GB", types: ["Chat"] },
  { name: "qwen3.5:0.8b",      description: "Qwen3.5 – neuestes Alibaba-Modell, winzig und schnell",          sizeLabel: "≤3B",  sizeDisplay: "0.5 GB", types: ["Chat"] },
  { name: "qwen3.5:2b",        description: "Qwen3.5 – kompakt, verbesserte Reasoning-Fähigkeiten",           sizeLabel: "≤3B",  sizeDisplay: "1.3 GB", types: ["Chat"] },
  { name: "qwen3.5:4b",        description: "Qwen3.5 – gutes Allround-Modell für CPU-Betrieb",                sizeLabel: "≤3B",  sizeDisplay: "2.6 GB", types: ["Chat"] },
  { name: "deepseek-r1:1.5b",  description: "DeepSeek R1 Reasoning-Distillat – kleinste Variante",            sizeLabel: "≤3B",  sizeDisplay: "1.1 GB", types: ["Chat"] },
  // ── Chat · Mittel 7B ─────────────────────────────────────────────────────
  { name: "llama3.1:8b",       description: "Metas leistungsstarkes 8B-Modell mit 128k Kontext",              sizeLabel: "7B",   sizeDisplay: "4.7 GB", types: ["Chat"] },
  { name: "gemma3:12b",        description: "Googles starkes Gemma-3 12B – besser als Gemma2:9b, multimodal", sizeLabel: "7B",   sizeDisplay: "8.1 GB", types: ["Chat", "Vision"] },
  { name: "gemma2:9b",         description: "Googles bewährtes 9B-Modell (Gemma2-Generation)",                sizeLabel: "7B",   sizeDisplay: "5.5 GB", types: ["Chat"] },
  { name: "mistral:7b",        description: "Schnelles, präzises Modell von Mistral AI",                      sizeLabel: "7B",   sizeDisplay: "4.1 GB", types: ["Chat"] },
  { name: "qwen2.5:7b",        description: "Alibabas starkes 7B-Modell, gut für Deutsch",                    sizeLabel: "7B",   sizeDisplay: "4.4 GB", types: ["Chat"] },
  { name: "qwen3:8b",          description: "Qwen3 8B – sehr gutes Reasoning, empfohlen für Deutsch",         sizeLabel: "7B",   sizeDisplay: "5.2 GB", types: ["Chat"] },
  { name: "qwen3.5:9b",        description: "Qwen3.5 9B – stärkstes ~10B-Modell, besser als Qwen3:8b",       sizeLabel: "7B",   sizeDisplay: "5.8 GB", types: ["Chat"] },
  { name: "deepseek-r1:7b",    description: "DeepSeek R1 7B – Reasoning mit Chain-of-Thought (Llama-Basis)",  sizeLabel: "7B",   sizeDisplay: "4.7 GB", types: ["Chat"] },
  { name: "deepseek-r1:8b",    description: "DeepSeek R1 8B – Reasoning-Distillat (Llama-3.1-Basis)",        sizeLabel: "7B",   sizeDisplay: "4.9 GB", types: ["Chat"] },
  { name: "granite3.3:8b",     description: "IBMs Granite 3.3 – stark für Unternehmensaufgaben und Deutsch",  sizeLabel: "7B",   sizeDisplay: "5.0 GB", types: ["Chat"] },
  // ── Chat · Groß ≥13B ─────────────────────────────────────────────────────
  { name: "mistral-nemo:12b",  description: "Mistral Nemo – ausgezeichnete Qualität, sehr multilingual",      sizeLabel: "≥13B", sizeDisplay: "7.1 GB",  types: ["Chat"] },
  { name: "mistral-small:22b", description: "Mistral Small 3.1 – starkes Allround-Modell, multilingual",      sizeLabel: "≥13B", sizeDisplay: "12.2 GB", types: ["Chat"] },
  { name: "mistral-small:24b", description: "Mistral Small 3.2 – verbesserte Version, besonders für Deutsch", sizeLabel: "≥13B", sizeDisplay: "14.3 GB", types: ["Chat"] },
  { name: "phi4:14b",          description: "Microsofts leistungsstärkstes Phi-4-Modell",                     sizeLabel: "≥13B", sizeDisplay: "9.1 GB",  types: ["Chat"] },
  { name: "phi4-reasoning:14b",description: "Phi-4 Reasoning – auf logisches Schlussfolgern spezialisiert",   sizeLabel: "≥13B", sizeDisplay: "9.3 GB",  types: ["Chat"] },
  { name: "qwen2.5:14b",       description: "Alibabas großes Multilingual-Modell",                            sizeLabel: "≥13B", sizeDisplay: "9.0 GB",  types: ["Chat"] },
  { name: "qwen3:14b",         description: "Qwen3 14B – starkes Reasoning, besser als Qwen2.5:14b",          sizeLabel: "≥13B", sizeDisplay: "9.3 GB",  types: ["Chat"] },
  { name: "qwen3:32b",         description: "Qwen3 32B – top Open-Source-Qualität",                           sizeLabel: "≥13B", sizeDisplay: "20 GB",   types: ["Chat"] },
  { name: "qwen3.5:27b",       description: "Qwen3.5 27B – leistungsstarkes großes Modell",                   sizeLabel: "≥13B", sizeDisplay: "17 GB",   types: ["Chat"] },
  { name: "qwen3.5:35b-a3b",   description: "Qwen3.5 35B MoE – effizientes Mixture-of-Experts-Modell",        sizeLabel: "≥13B", sizeDisplay: "22 GB",   types: ["Chat"] },
  { name: "deepseek-r1:14b",   description: "DeepSeek R1 14B – starkes Reasoning-Modell",                     sizeLabel: "≥13B", sizeDisplay: "9.0 GB",  types: ["Chat"] },
  { name: "deepseek-r1:32b",   description: "DeepSeek R1 32B – sehr gutes Reasoning für Server",              sizeLabel: "≥13B", sizeDisplay: "20 GB",   types: ["Chat"] },
  { name: "gemma3:27b",        description: "Googles stärkstes lokales Gemma-3-Modell",                       sizeLabel: "≥13B", sizeDisplay: "17 GB",   types: ["Chat"] },
  { name: "gemma2:27b",        description: "Googles Gemma-2 27B (ältere Generation, weiterhin stark)",       sizeLabel: "≥13B", sizeDisplay: "16 GB",   types: ["Chat"] },
  { name: "llama4:scout",      description: "Metas Llama4 Scout – MoE-Modell, 17B aktiv / 109B gesamt",      sizeLabel: "≥13B", sizeDisplay: "~34 GB",  types: ["Chat"] },
  { name: "llama3.3:70b",      description: "Metas Llama3.3 70B – sehr hohe Qualität, benötigt viel RAM",     sizeLabel: "≥13B", sizeDisplay: "43 GB",   types: ["Chat"] },
  // ── Coding ───────────────────────────────────────────────────────────────
  { name: "qwen2.5-coder:1.5b",    description: "Alibabas kleinstes Coding-Modell",                          sizeLabel: "≤3B",  sizeDisplay: "1.0 GB", types: ["Coding"] },
  { name: "qwen2.5-coder:3b",      description: "Gutes Coding-Modell für schwache Hardware",                 sizeLabel: "≤3B",  sizeDisplay: "2.0 GB", types: ["Coding"] },
  { name: "qwen2.5-coder:7b",      description: "Empfohlen für Code-Generierung und -Analyse",               sizeLabel: "7B",   sizeDisplay: "4.4 GB", types: ["Coding"] },
  { name: "qwen2.5-coder:14b",     description: "Alibabas großes Coding-Modell – sehr stark",                sizeLabel: "≥13B", sizeDisplay: "9.0 GB", types: ["Coding"] },
  { name: "codellama:7b",          description: "Metas auf Code spezialisiertes Llama-Modell",               sizeLabel: "7B",   sizeDisplay: "3.8 GB", types: ["Coding"] },
  { name: "deepseek-coder:6.7b",   description: "DeepSeeks bewährtes Coding-Modell",                         sizeLabel: "7B",   sizeDisplay: "3.8 GB", types: ["Coding"] },
  { name: "deepseek-coder-v2:16b", description: "DeepSeeks MoE-basiertes Coding-Flaggschiff",                sizeLabel: "≥13B", sizeDisplay: "8.9 GB", types: ["Coding"] },
  // ── Embedding ────────────────────────────────────────────────────────────
  { name: "nomic-embed-text",  description: "Schnelles, hochwertiges Text-Embedding-Modell",                  sizeLabel: "≤3B",  sizeDisplay: "274 MB", types: ["Embedding"] },
  { name: "mxbai-embed-large", description: "Starkes Embedding-Modell von mixedbread.ai",                     sizeLabel: "≤3B",  sizeDisplay: "670 MB", types: ["Embedding"] },
  { name: "all-minilm",        description: "Sehr kleines, schnelles Embedding-Modell",                       sizeLabel: "≤3B",  sizeDisplay: "46 MB",  types: ["Embedding"] },
  // ── Vision ───────────────────────────────────────────────────────────────
  { name: "moondream:1.8b",    description: "Kleinstes Vision-Modell für Bildanalyse",                        sizeLabel: "≤3B",  sizeDisplay: "1.1 GB", types: ["Vision"] },
  { name: "llava:7b",          description: "Bewährtes Vision-Language-Modell",                               sizeLabel: "7B",   sizeDisplay: "4.5 GB", types: ["Vision"] },
  { name: "minicpm-v:8b",      description: "Effizientes Vision-Modell mit guter OCR-Leistung",               sizeLabel: "7B",   sizeDisplay: "5.5 GB", types: ["Vision"] },
  { name: "llava:13b",         description: "Stärkeres LLaVA-Modell für komplexe Bildaufgaben",               sizeLabel: "≥13B", sizeDisplay: "8.0 GB", types: ["Vision"] },
];

function ModelLibrary() {
  const [view, setView] = useState<"installed" | "catalog">("installed");
  const [installedModels, setInstalledModels] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sizeFilter, setSizeFilter] = useState("Alle");
  const [typeFilter, setTypeFilter] = useState("Alle");
  const [search, setSearch] = useState("");
  const [deleting, setDeleting] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [pulling, setPulling] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listModels();
      setInstalledModels(data.models ?? []);
    } catch (e: any) {
      setError(e.message || "Fehler beim Laden");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const installedNames = new Set(installedModels.map(m => m.name));

  const handleDelete = async (modelName: string) => {
    setDeleting(modelName);
    setConfirmDelete(null);
    try {
      await deleteModel(modelName);
      setInstalledModels(prev => prev.filter(m => m.name !== modelName));
    } catch (e: any) {
      alert(`Löschen fehlgeschlagen: ${e.message}`);
    } finally {
      setDeleting(null);
    }
  };

  const handlePull = async (modelName: string) => {
    setPulling(modelName);
    aiDownloadStore.set({ pulling: true, model: modelName, status: "Verbinde...", percent: 0, done: false, error: null });
    try {
      await pullModel(modelName, (chunk: any) => {
        const pct = chunk.total ? Math.round((chunk.completed / chunk.total) * 100) : null;
        aiDownloadStore.set({ pulling: true, model: modelName, status: chunk.status, percent: pct });
      });
      aiDownloadStore.set({ pulling: false, status: "Fertig!", percent: 100, done: true, model: modelName, error: null });
      await load();
    } catch (e: any) {
      aiDownloadStore.set({ pulling: false, error: e.message, model: modelName, status: null, percent: null, done: false });
    } finally {
      setPulling(null);
      setTimeout(() => aiDownloadStore.set({ pulling: false, model: null, status: null, percent: null, done: false, error: null }), 4000);
    }
  };

  const chipStyle = (active: boolean) => ({
    padding: "3px 9px", borderRadius: 20, fontSize: 10, fontWeight: 600,
    cursor: "pointer", border: `1px solid ${active ? ACCENT : "rgba(255,255,255,0.12)"}`,
    backgroundColor: active ? "rgba(252,228,153,0.12)" : "transparent",
    color: active ? ACCENT : S.textDim, transition: "all 0.15s",
  });

  const toggleStyle = (active: boolean) => ({
    padding: "4px 14px", borderRadius: 6, fontSize: 11, fontWeight: 600, cursor: "pointer",
    border: `1px solid ${active ? ACCENT : S.border}`,
    backgroundColor: active ? "rgba(252,228,153,0.1)" : "transparent",
    color: active ? ACCENT : S.textDim,
  });

  const searchLower = search.toLowerCase();

  const filteredInstalled = installedModels.filter(m => {
    const size = guessModelSize(m.name, m.size);
    const types = guessModelType(m.name);
    if (sizeFilter !== "Alle" && size !== sizeFilter) return false;
    if (typeFilter !== "Alle" && !types.includes(typeFilter)) return false;
    if (searchLower && !m.name.toLowerCase().includes(searchLower)) return false;
    return true;
  });

  const filteredCatalog = CATALOG.filter(m => {
    if (sizeFilter !== "Alle" && m.sizeLabel !== sizeFilter) return false;
    if (typeFilter !== "Alle" && !m.types.includes(typeFilter)) return false;
    if (searchLower && !m.name.toLowerCase().includes(searchLower)) return false;
    return true;
  });

  return (
    <div>
      {/* View toggle */}
      <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
        <button style={toggleStyle(view === "installed")} onClick={() => setView("installed")}>
          Installiert {!loading && `(${installedModels.length})`}
        </button>
        <button style={toggleStyle(view === "catalog")} onClick={() => setView("catalog")}>
          Katalog ({CATALOG.length})
        </button>
      </div>

      {/* Suchfeld */}
      <div style={{ position: "relative", marginBottom: 10 }}>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Modell suchen… (z.B. gemma, qwen3, coder)"
          style={{
            width: "100%", boxSizing: "border-box",
            padding: "6px 28px 6px 10px", fontSize: 11,
            backgroundColor: S.bgEl, border: `1px solid ${S.border}`,
            borderRadius: 6, color: S.textBright, outline: "none",
          }}
        />
        {search && (
          <button onClick={() => setSearch("")} style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0, display: "flex" }}>
            <X size={12} />
          </button>
        )}
      </div>

      {/* Filter chips */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
        <span style={{ fontSize: 10, color: S.textDim, alignSelf: "center", marginRight: 4 }}>Größe:</span>
        {SIZE_FILTERS.map(f => (
          <button key={f} style={chipStyle(sizeFilter === f)} onClick={() => setSizeFilter(f)}>{f}</button>
        ))}
        <span style={{ fontSize: 10, color: S.textDim, alignSelf: "center", marginLeft: 6, marginRight: 4 }}>Typ:</span>
        {TYPE_FILTERS.map(f => (
          <button key={f} style={chipStyle(typeFilter === f)} onClick={() => setTypeFilter(f)}>{f}</button>
        ))}
      </div>

      {loading && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, color: S.textDim, fontSize: 12 }}>
          <Loader2 size={14} className="animate-spin" /> Modelle werden geladen...
        </div>
      )}
      {error && <p style={{ color: "#e07070", fontSize: 12 }}>{error}</p>}

      {/* Installiert */}
      {view === "installed" && !loading && !error && (
        <>
          {filteredInstalled.length === 0 && (
            <p style={{ fontSize: 12, color: S.textDim }}>
              {installedModels.length === 0 ? "Keine Modelle installiert." : "Kein Modell entspricht dem Filter."}
            </p>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {filteredInstalled.map(m => {
              const size = guessModelSize(m.name, m.size);
              const types = guessModelType(m.name);
              const langs = guessModelLanguages(m.name);
              const isDeleting = deleting === m.name;
              const isConfirming = confirmDelete === m.name;
              const modified = m.modified_at ? new Date(m.modified_at).toLocaleDateString("de-DE") : null;
              return (
                <div key={m.name} style={{ padding: "10px 12px", borderRadius: 8, border: `1px solid ${S.border}`, backgroundColor: "rgba(255,255,255,0.03)", display: "flex", flexDirection: "column", gap: 5 }}>
                  <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 12, fontWeight: 600, color: S.textBright, wordBreak: "break-all" }}>{m.name}</div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 4 }}>
                        <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 10, backgroundColor: "rgba(252,228,153,0.1)", color: ACCENT, border: `1px solid rgba(252,228,153,0.2)` }}>{size}</span>
                        {types.map(t => (
                          <span key={t} style={{ fontSize: 9, padding: "1px 6px", borderRadius: 10, backgroundColor: "rgba(255,255,255,0.06)", color: S.textDim, border: `1px solid rgba(255,255,255,0.1)` }}>{t}</span>
                        ))}
                        {langs.map(l => (
                          <span key={l} style={{ fontSize: 9, padding: "1px 5px", borderRadius: 10, backgroundColor: "rgba(99,179,237,0.1)", color: "#63b3ed", border: "1px solid rgba(99,179,237,0.2)" }}>{l}</span>
                        ))}
                        {m.size && <span style={{ fontSize: 9, color: S.textDim }}>{formatBytes(m.size)}</span>}
                        {modified && <span style={{ fontSize: 9, color: S.textDim }}>· {modified}</span>}
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                      {isConfirming ? (
                        <>
                          <button onClick={() => setConfirmDelete(null)} style={{ fontSize: 10, padding: "3px 8px", borderRadius: 5, border: `1px solid ${S.border}`, background: "none", color: S.textDim, cursor: "pointer" }}>Abbruch</button>
                          <button onClick={() => handleDelete(m.name)} style={{ fontSize: 10, padding: "3px 8px", borderRadius: 5, border: "1px solid #e07070", backgroundColor: "rgba(224,112,112,0.15)", color: "#e07070", cursor: "pointer" }}>
                            {isDeleting ? <Loader2 size={10} /> : "Löschen"}
                          </button>
                        </>
                      ) : (
                        <button onClick={() => setConfirmDelete(m.name)} title="Modell löschen" disabled={isDeleting} style={{ background: "none", border: "none", color: "rgba(255,255,255,0.2)", cursor: "pointer", padding: 4, display: "flex", alignItems: "center" }}>
                          <Trash2 size={12} />
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          {installedModels.length > 0 && (
            <p style={{ fontSize: 10, color: S.textDim, marginTop: 12 }}>
              {filteredInstalled.length} von {installedModels.length} Modell{installedModels.length !== 1 ? "en" : ""} angezeigt
            </p>
          )}
        </>
      )}

      {/* Katalog */}
      {view === "catalog" && (
        <>
          <p style={{ fontSize: 11, color: S.textDim, margin: "0 0 10px" }}>
            Populäre Ollama-Modelle. Klicke "Laden" um ein Modell herunterzuladen.
          </p>
          {filteredCatalog.length === 0 && (
            <p style={{ fontSize: 12, color: S.textDim }}>Kein Modell entspricht dem Filter.</p>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {filteredCatalog.map(m => {
              const isInstalled = installedNames.has(m.name);
              const isPulling = pulling === m.name;
              const langs = guessModelLanguages(m.name);
              return (
                <div key={m.name} style={{ padding: "9px 12px", borderRadius: 8, border: `1px solid ${isInstalled ? "rgba(110,231,183,0.2)" : S.border}`, backgroundColor: isInstalled ? "rgba(110,231,183,0.04)" : "rgba(255,255,255,0.02)", display: "flex", alignItems: "center", gap: 10 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: S.textBright }}>{m.name}</div>
                    <div style={{ fontSize: 10, color: S.textDim, marginTop: 2 }}>{m.description}</div>
                    <div style={{ display: "flex", gap: 4, marginTop: 4, flexWrap: "wrap" }}>
                      <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 10, backgroundColor: "rgba(252,228,153,0.1)", color: ACCENT, border: `1px solid rgba(252,228,153,0.2)` }}>{m.sizeLabel}</span>
                      {m.types.map(t => (
                        <span key={t} style={{ fontSize: 9, padding: "1px 6px", borderRadius: 10, backgroundColor: "rgba(255,255,255,0.06)", color: S.textDim, border: `1px solid rgba(255,255,255,0.1)` }}>{t}</span>
                      ))}
                      {langs.map(l => (
                        <span key={l} style={{ fontSize: 9, padding: "1px 5px", borderRadius: 10, backgroundColor: "rgba(99,179,237,0.1)", color: "#63b3ed", border: "1px solid rgba(99,179,237,0.2)" }}>{l}</span>
                      ))}
                      <span style={{ fontSize: 9, color: S.textDim }}>{m.sizeDisplay}</span>
                    </div>
                  </div>
                  <div style={{ flexShrink: 0 }}>
                    {isInstalled ? (
                      <span style={{ fontSize: 10, color: "#6ee7b7", display: "flex", alignItems: "center", gap: 4 }}>
                        <Check size={11} /> Installiert
                      </span>
                    ) : (
                      <button
                        onClick={() => handlePull(m.name)}
                        disabled={isPulling || pulling !== null}
                        style={{ fontSize: 10, padding: "4px 10px", borderRadius: 6, border: `1px solid ${ACCENT}`, backgroundColor: "rgba(252,228,153,0.08)", color: ACCENT, cursor: isPulling || pulling !== null ? "default" : "pointer", display: "flex", alignItems: "center", gap: 5, opacity: pulling !== null && !isPulling ? 0.5 : 1 }}
                      >
                        {isPulling ? <><Loader2 size={10} className="animate-spin" /> Laden...</> : <><Download size={10} /> Laden</>}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          <p style={{ fontSize: 10, color: S.textDim, marginTop: 12 }}>
            {filteredCatalog.length} von {CATALOG.length} Modellen angezeigt · {installedModels.length} installiert
          </p>
        </>
      )}
    </div>
  );
}

function NetworkSettings() {
  const [form, setForm] = useState({ allowlist: "", blocklist: "", allow_loopback: false });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.get("/api/settings/egress")
      .then(({ data }) => { if (data) setForm(f => ({ ...f, ...data })); })
      .catch(() => {}).finally(() => setLoading(false));
  }, []);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const handleSave = async () => {
    setSaving(true); setSaved(false);
    try {
      await api.post("/api/settings/egress", form);
      setSaved(true); setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      alert(fehlerText(e));
    } finally { setSaving(false); }
  };

  const lS = { fontSize: 10, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", display: "block", marginBottom: 4 };
  const taS = { backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, color: S.textBright, fontSize: 11, padding: "6px 10px", outline: "none", width: "100%", minHeight: 70, fontFamily: "monospace", resize: "vertical" };

  if (loading) return <p style={{ color: S.textDim, fontSize: 12 }}>Lade...</p>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14, maxWidth: 560 }}>
      <p style={{ fontSize: 11, color: S.textDim, margin: 0, lineHeight: 1.6 }}>
        Steuert, welche Ziele serverseitige HTTP-Aufrufe (REST-Connector / API-Studio, Web-Import)
        erreichen dürfen (SSRF-Schutz). <b>Cloud-Metadata-Endpunkte werden immer blockiert.</b>
        Interne/private Netze sind erlaubt (für On-Prem-APIs) und werden protokolliert.
        Ein Eintrag pro Zeile oder kommagetrennt: Hostname (z.B. <code>api.intern.local</code>),
        IP oder CIDR (z.B. <code>10.0.0.0/8</code>).
      </p>

      <div>
        <label style={lS}>Allowlist (immer erlauben, übersteuert Blocks)</label>
        <textarea style={taS} value={form.allowlist}
          onChange={e => set("allowlist", e.target.value)}
          placeholder={"api.intern.local\n10.20.0.0/16"} />
      </div>

      <div>
        <label style={lS}>Blocklist (immer blockieren)</label>
        <textarea style={taS} value={form.blocklist}
          onChange={e => set("blocklist", e.target.value)}
          placeholder={"169.254.0.0/16\nsecret-host.example"} />
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", padding: "10px 12px", borderRadius: 6, backgroundColor: form.allow_loopback ? "rgba(252,228,153,0.07)" : S.bgEl, border: `1px solid ${form.allow_loopback ? "rgba(252,228,153,0.25)" : S.border}` }}
        onClick={() => set("allow_loopback", !form.allow_loopback)}>
        <div style={{ width: 16, height: 16, borderRadius: 3, border: `2px solid ${form.allow_loopback ? ACCENT : S.border}`, backgroundColor: form.allow_loopback ? ACCENT : "transparent", flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
          {form.allow_loopback && <Check size={10} color="#111" strokeWidth={3} />}
        </div>
        <div>
          <span style={{ fontSize: 11, color: form.allow_loopback ? ACCENT : S.textMain, fontWeight: form.allow_loopback ? 700 : 400 }}>
            Loopback (127.0.0.1 / localhost) als Ziel zulassen
          </span>
          <div style={{ fontSize: 10, color: S.textDim, marginTop: 1 }}>
            Standard: aus. Nur aktivieren, wenn eine API auf demselben Host läuft.
          </div>
        </div>
      </div>

      <div>
        <button onClick={handleSave} disabled={saving}
          style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 16px", borderRadius: 5, border: "none", backgroundColor: saved ? "rgba(110,231,183,0.15)" : ACCENT, color: saved ? "#6ee7b7" : "#111", cursor: "pointer", fontSize: 12, fontWeight: 700 }}>
          {saving ? <Loader2 size={12} className="animate-spin" /> : saved ? <Check size={12} /> : <Save size={12} />}
          {saved ? "Gespeichert!" : "Speichern"}
        </button>
      </div>
    </div>
  );
}

function AppearanceSettings() {
  const { mode, setMode } = useTheme();

  const options: { value: ThemeMode; label: string; desc: string; Icon: any }[] = [
    { value: "dark",   label: "Dunkel",  desc: "Dunkles Theme (Standard)",          Icon: Moon    },
    { value: "light",  label: "Hell",    desc: "Helles Theme",                       Icon: Sun     },
    { value: "system", label: "System",  desc: "Folgt den Systemeinstellungen",      Icon: Monitor },
  ];

  return (
    <div style={{ maxWidth: 420 }}>
      <p className="section-title" style={{ marginBottom: 16 }}>Farbschema</p>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {options.map(({ value, label, desc, Icon }) => {
          const active = mode === value;
          return (
            <button key={value} onClick={() => setMode(value)}
              style={{
                display: "flex", alignItems: "center", gap: 14,
                padding: "12px 16px", borderRadius: 8, cursor: "pointer",
                border: `1px solid ${active ? ACCENT : "var(--border)"}`,
                background: active ? "var(--accent-dim)" : "var(--bg-elevated)",
                textAlign: "left", width: "100%",
              }}>
              <Icon size={18} style={{ color: active ? ACCENT : "var(--text-dim)", flexShrink: 0 }} />
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: active ? ACCENT : "var(--text-bright)" }}>
                  {label}
                </div>
                <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 1 }}>{desc}</div>
              </div>
              {active && <Check size={14} style={{ marginLeft: "auto", color: ACCENT }} />}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default function SystemSettingsModal({ onClose }) {
  const [activeTab, setActiveTab] = useState("email");
  const { user: angemeldet } = useAuth();
  // Die Sicherung ist Administratoren vorbehalten: ein Archiv enthält die
  // Zugangsdaten aller Verbindungen. Das Backend weist Fremde ohnehin ab –
  // der Reiter wird hier gar nicht erst angeboten.
  const sichtbareTabs = TABS.filter(
    t => !t.nurAdmin || angemeldet?.is_admin);

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
          {sichtbareTabs.map(tab => (
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
          {activeTab === "email"      && <EmailSettings />}
          {activeTab === "ai"         && <AiSettings />}
          {activeTab === "models"     && <ModelLibrary />}
          {activeTab === "users"      && <UserManagement />}
          {activeTab === "mandanten"  && angemeldet?.is_admin && <MandantenSettings />}
          {activeTab === "network"    && <NetworkSettings />}
          {activeTab === "appearance" && <AppearanceSettings />}
          {activeTab === "backup"     && angemeldet?.is_admin && <BackupSettings />}
        </div>
      </div>
    </div>
  );
}
