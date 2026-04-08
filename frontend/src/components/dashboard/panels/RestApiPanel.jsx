import { useState, useEffect } from "react";
import { Wifi, WifiOff, X, Plus, Trash2, Pencil, Play, CheckCircle2, XCircle, Loader2, Check } from "lucide-react";
import api from "../../../api/client";
import { S } from "../constants";

const REST_COLOR = "#818cf8";

const REST_AUTH_TYPES = [
  { v: "none",      l: "Keine Auth" },
  { v: "basic",     l: "Basic Auth" },
  { v: "bearer",    l: "Bearer Token" },
  { v: "apikey",    l: "API Key" },
  { v: "oauth2_cc", l: "OAuth2 Client Credentials" },
];
const REST_PAG_TYPES = [
  { v: "none",        l: "Keine Paginierung" },
  { v: "page",        l: "Seiten (page/limit)" },
  { v: "offset",      l: "Offset/Limit" },
  { v: "cursor",      l: "Cursor-basiert" },
  { v: "link_header", l: "Link-Header (RFC 5988)" },
];
const METHODS = ["GET","POST","PUT","PATCH"];
const BODY_TYPES = [
  { v: "none", l: "Kein Body" },
  { v: "json", l: "JSON" },
  { v: "form", l: "Form-Data" },
  { v: "raw",  l: "Raw" },
];
const TEMPLATE_VARS = ["{{heute}}","{{gestern}}","{{morgen}}","{{timestamp}}","{{iso_heute}}","{{monat}}","{{jahr}}","{{epoch_ms}}"];
const EMPTY_SOURCE = {
  name: "", url: "", method: "GET",
  headers: {}, query_params: {},
  body_type: "none", body_content: "",
  auth_type: "none", auth_config: {},
  data_path: "", flatten: 1,
  pagination: { type: "none" },
  dataset_mode: "replace", cron_expr: "", active: 1,
};

function KvEditor({ label, value, onChange }) {
  const entries = Object.entries(value || {});
  const [newK, setNewK] = useState(""); const [newV, setNewV] = useState("");
  const iS2 = { backgroundColor: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 4, color: "#f1f5f9", fontSize: 11, padding: "4px 8px", outline: "none", flex: 1 };
  return (
    <div>
      <label style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em", color: "#64748b", display: "block", marginBottom: 6 }}>{label}</label>
      <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 6 }}>
        {entries.map(([k, v]) => (
          <div key={k} style={{ display: "flex", gap: 4, alignItems: "center" }}>
            <input style={iS2} value={k} onChange={(e) => { const n = {...value}; const val = n[k]; delete n[k]; n[e.target.value] = val; onChange(n); }} />
            <span style={{ color: "#475569", fontSize: 11 }}>:</span>
            <input style={iS2} value={v} onChange={(e) => onChange({ ...value, [k]: e.target.value })} />
            <button onClick={() => { const n = {...value}; delete n[k]; onChange(n); }} style={{ color: "#f87171", fontSize: 14, lineHeight: 1, padding: "2px 4px" }}>×</button>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 4 }}>
        <input style={iS2} placeholder="Key" value={newK} onChange={e => setNewK(e.target.value)} />
        <span style={{ color: "#475569", fontSize: 11 }}>:</span>
        <input style={iS2} placeholder="Value" value={newV} onChange={e => setNewV(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter" && newK) { onChange({ ...value, [newK]: newV }); setNewK(""); setNewV(""); }}} />
        <button onClick={() => { if (newK) { onChange({ ...value, [newK]: newV }); setNewK(""); setNewV(""); }}}
          style={{ color: REST_COLOR, fontSize: 13, padding: "2px 8px", border: `1px solid ${REST_COLOR}44`, borderRadius: 4, backgroundColor: `${REST_COLOR}10`, cursor: "pointer" }}>+</button>
      </div>
    </div>
  );
}

function PaginationEditor({ value, onChange }) {
  const pag = value || { type: "none" };
  const set = (k, v) => onChange({ ...pag, [k]: v });
  const iS2 = { backgroundColor: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 4, color: "#f1f5f9", fontSize: 11, padding: "4px 8px", outline: "none", width: "100%" };
  const lS2 = { fontSize: 10, color: "#64748b", display: "block", marginBottom: 3 };
  return (
    <div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
        {REST_PAG_TYPES.map(p => (
          <button key={p.v} onClick={() => onChange({ type: p.v })}
            style={{ padding: "4px 10px", borderRadius: 4, fontSize: 11, cursor: "pointer", border: `1px solid ${pag.type === p.v ? REST_COLOR : "rgba(255,255,255,0.1)"}`, backgroundColor: pag.type === p.v ? `${REST_COLOR}18` : "transparent", color: pag.type === p.v ? REST_COLOR : "#64748b" }}>
            {p.l}
          </button>
        ))}
      </div>
      {pag.type === "page" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 8 }}>
          <div><label style={lS2}>Seiten-Param</label><input style={iS2} value={pag.page_param || "page"} onChange={e => set("page_param", e.target.value)} /></div>
          <div><label style={lS2}>Limit-Param</label><input style={iS2} value={pag.limit_param || "per_page"} onChange={e => set("limit_param", e.target.value)} /></div>
          <div><label style={lS2}>Pro Seite</label><input style={iS2} type="number" value={pag.limit || 100} onChange={e => set("limit", parseInt(e.target.value))} /></div>
          <div><label style={lS2}>Startseite</label><input style={iS2} type="number" value={pag.start_page ?? 1} onChange={e => set("start_page", parseInt(e.target.value))} /></div>
        </div>
      )}
      {pag.type === "offset" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
          <div><label style={lS2}>Offset-Param</label><input style={iS2} value={pag.offset_param || "skip"} onChange={e => set("offset_param", e.target.value)} /></div>
          <div><label style={lS2}>Limit-Param</label><input style={iS2} value={pag.limit_param || "take"} onChange={e => set("limit_param", e.target.value)} /></div>
          <div><label style={lS2}>Pro Request</label><input style={iS2} type="number" value={pag.limit || 100} onChange={e => set("limit", parseInt(e.target.value))} /></div>
        </div>
      )}
      {pag.type === "cursor" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <div><label style={lS2}>Cursor-Param</label><input style={iS2} value={pag.cursor_param || "cursor"} onChange={e => set("cursor_param", e.target.value)} /></div>
          <div><label style={lS2}>Cursor-Pfad in Response</label><input style={iS2} placeholder="meta.next_cursor" value={pag.cursor_path || ""} onChange={e => set("cursor_path", e.target.value)} /></div>
          <div><label style={lS2}>Limit-Param (optional)</label><input style={iS2} value={pag.limit_param || ""} onChange={e => set("limit_param", e.target.value)} /></div>
          <div><label style={lS2}>Limit</label><input style={iS2} type="number" value={pag.limit || 100} onChange={e => set("limit", parseInt(e.target.value))} /></div>
        </div>
      )}
      {pag.type === "link_header" && (
        <p style={{ fontSize: 11, color: "#64748b" }}>Liest automatisch <code style={{ fontFamily: "monospace" }}>Link: &lt;url&gt;; rel="next"</code> aus dem Response-Header.</p>
      )}
    </div>
  );
}

function AuthEditor({ authType, authConfig, onChange }) {
  const set = (k, v) => onChange({ ...authConfig, [k]: v });
  const iS2 = { width: "100%", backgroundColor: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 4, color: "#f1f5f9", fontSize: 11, padding: "5px 8px", outline: "none", boxSizing: "border-box" };
  const lS2 = { fontSize: 10, color: "#64748b", display: "block", marginBottom: 3 };
  if (authType === "basic") return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 8 }}>
      <div><label style={lS2}>Benutzername</label><input style={iS2} value={authConfig.username || ""} onChange={e => set("username", e.target.value)} /></div>
      <div><label style={lS2}>Passwort</label><input style={iS2} type="password" value={authConfig.password || ""} onChange={e => set("password", e.target.value)} /></div>
    </div>
  );
  if (authType === "bearer") return (
    <div style={{ marginTop: 8 }}>
      <label style={lS2}>Token</label>
      <input style={iS2} value={authConfig.token || ""} onChange={e => set("token", e.target.value)} placeholder="eyJ..." />
    </div>
  );
  if (authType === "apikey") return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginTop: 8 }}>
      <div><label style={lS2}>Header/Param-Name</label><input style={iS2} value={authConfig.key || "X-Api-Key"} onChange={e => set("key", e.target.value)} /></div>
      <div><label style={lS2}>Wert</label><input style={iS2} value={authConfig.value || ""} onChange={e => set("value", e.target.value)} /></div>
      <div><label style={lS2}>Ort</label>
        <select style={iS2} value={authConfig.location || "header"} onChange={e => set("location", e.target.value)}>
          <option value="header">Header</option><option value="query">Query-Param</option>
        </select>
      </div>
    </div>
  );
  if (authType === "oauth2_cc") return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 8 }}>
      <div style={{ gridColumn: "1/-1" }}><label style={lS2}>Token-URL</label><input style={iS2} value={authConfig.token_url || ""} onChange={e => set("token_url", e.target.value)} placeholder="https://auth.example.com/oauth/token" /></div>
      <div><label style={lS2}>Client ID</label><input style={iS2} value={authConfig.client_id || ""} onChange={e => set("client_id", e.target.value)} /></div>
      <div><label style={lS2}>Client Secret</label><input style={iS2} type="password" value={authConfig.client_secret || ""} onChange={e => set("client_secret", e.target.value)} /></div>
      <div style={{ gridColumn: "1/-1" }}><label style={lS2}>Scope (optional)</label><input style={iS2} value={authConfig.scope || ""} onChange={e => set("scope", e.target.value)} /></div>
    </div>
  );
  return null;
}

function RestSourceForm({ initial, projectId, datasets, onSaved, onCancel }) {
  const [form, setForm] = useState({ ...EMPTY_SOURCE, ...initial });
  const [activeTab, setActiveTab] = useState("request");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const set = (k, v) => { setForm(f => ({ ...f, [k]: v })); setTestResult(null); };

  const handleTest = async () => {
    setTesting(true); setTestResult(null); setError("");
    try {
      const { data } = await api.post("/api/rest-sources/test", {
        url: form.url, method: form.method, headers: form.headers,
        query_params: form.query_params, body_type: form.body_type,
        body_content: form.body_content, auth_type: form.auth_type,
        auth_config: form.auth_config, data_path: form.data_path,
        flatten: form.flatten, pagination: form.pagination,
      });
      setTestResult(data);
    } catch (e) { setTestResult({ success: false, error: e.response?.data?.detail || "Fehler" }); }
    finally { setTesting(false); }
  };

  const handleSave = async () => {
    setSaving(true); setError("");
    try {
      const payload = { ...form, project_id: projectId ?? null, pagination: form.pagination || { type: "none" } };
      if (initial?.id) await api.put(`/api/rest-sources/${initial.id}`, payload);
      else await api.post("/api/rest-sources/", payload);
      onSaved();
    } catch (e) { setError(e.response?.data?.detail || "Fehler beim Speichern"); }
    finally { setSaving(false); }
  };

  const iS = { width: "100%", backgroundColor: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 6, color: "#f1f5f9", fontSize: 12, padding: "7px 10px", outline: "none", boxSizing: "border-box" };
  const lS = { fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em", color: "#64748b", display: "block", marginBottom: 4 };
  const TABS = [
    { id: "request", l: "Request" },
    { id: "auth",    l: "Auth" },
    { id: "response",l: "Response" },
    { id: "paging",  l: "Paginierung" },
    { id: "schedule",l: "Scheduler" },
  ];

  return (
    <div style={{ backgroundColor: "rgba(255,255,255,0.02)", border: `1px solid ${REST_COLOR}33`, borderRadius: 10, overflow: "hidden", marginBottom: 16 }}>
      {/* Form Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 16px", backgroundColor: `${REST_COLOR}0c`, borderBottom: `1px solid ${REST_COLOR}22` }}>
        <div style={{ width: 28, height: 28, borderRadius: 6, backgroundColor: `${REST_COLOR}20`, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Wifi size={14} style={{ color: REST_COLOR }} />
        </div>
        <input style={{ ...iS, flex: 1, fontSize: 13, fontWeight: 600, backgroundColor: "transparent", border: "none", padding: "0" }}
          placeholder="Name des Connectors…" value={form.name} onChange={e => set("name", e.target.value)} />
        <button onClick={onCancel} style={{ color: "#64748b", padding: 4 }}><X size={14} /></button>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", borderBottom: `1px solid rgba(255,255,255,0.06)`, padding: "0 12px" }}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setActiveTab(t.id)}
            style={{ padding: "8px 12px", fontSize: 11, fontWeight: 600, cursor: "pointer", backgroundColor: "transparent", border: "none", borderBottom: `2px solid ${activeTab === t.id ? REST_COLOR : "transparent"}`, color: activeTab === t.id ? REST_COLOR : "#64748b", transition: "all 0.1s" }}>
            {t.l}
          </button>
        ))}
      </div>

      <div style={{ padding: 16 }}>
        {/* ── Request Tab ── */}
        {activeTab === "request" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {/* URL + Method */}
            <div style={{ display: "flex", gap: 8 }}>
              <div style={{ width: 100, flexShrink: 0 }}>
                <label style={lS}>Methode</label>
                <select style={iS} value={form.method} onChange={e => set("method", e.target.value)}>
                  {METHODS.map(m => <option key={m}>{m}</option>)}
                </select>
              </div>
              <div style={{ flex: 1 }}>
                <label style={lS}>URL</label>
                <input style={iS} value={form.url} onChange={e => set("url", e.target.value)} placeholder="https://api.example.com/v1/orders" />
              </div>
            </div>
            {/* Template-Vars Hinweis */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {TEMPLATE_VARS.map(v => (
                <code key={v} style={{ fontSize: 10, backgroundColor: `${REST_COLOR}15`, color: REST_COLOR, padding: "2px 6px", borderRadius: 3, cursor: "pointer", fontFamily: "monospace" }}
                  onClick={() => set("url", form.url + v)}>{v}</code>
              ))}
            </div>
            <KvEditor label="Query-Parameter" value={form.query_params} onChange={v => set("query_params", v)} />
            <KvEditor label="Headers" value={form.headers} onChange={v => set("headers", v)} />
            {/* Body */}
            <div>
              <label style={lS}>Body-Typ</label>
              <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
                {BODY_TYPES.map(b => (
                  <button key={b.v} onClick={() => set("body_type", b.v)}
                    style={{ padding: "4px 10px", borderRadius: 4, fontSize: 11, cursor: "pointer", border: `1px solid ${form.body_type === b.v ? REST_COLOR : "rgba(255,255,255,0.1)"}`, backgroundColor: form.body_type === b.v ? `${REST_COLOR}18` : "transparent", color: form.body_type === b.v ? REST_COLOR : "#64748b" }}>
                    {b.l}
                  </button>
                ))}
              </div>
              {form.body_type !== "none" && (
                <textarea style={{ ...iS, fontFamily: "monospace", minHeight: 100, resize: "vertical", lineHeight: 1.5 }}
                  placeholder={form.body_type === "json" ? '{\n  "key": "value"\n}' : form.body_type === "form" ? "key=value\nkey2=value2" : "Raw body…"}
                  value={form.body_content || ""} onChange={e => set("body_content", e.target.value)} />
              )}
            </div>
          </div>
        )}

        {/* ── Auth Tab ── */}
        {activeTab === "auth" && (
          <div>
            <label style={lS}>Auth-Typ</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
              {REST_AUTH_TYPES.map(a => (
                <button key={a.v} onClick={() => { set("auth_type", a.v); set("auth_config", {}); }}
                  style={{ padding: "5px 12px", borderRadius: 5, fontSize: 11, cursor: "pointer", border: `1px solid ${form.auth_type === a.v ? REST_COLOR : "rgba(255,255,255,0.1)"}`, backgroundColor: form.auth_type === a.v ? `${REST_COLOR}18` : "transparent", color: form.auth_type === a.v ? REST_COLOR : "#64748b" }}>
                  {a.l}
                </button>
              ))}
            </div>
            <AuthEditor authType={form.auth_type} authConfig={form.auth_config || {}} onChange={v => set("auth_config", v)} />
          </div>
        )}

        {/* ── Response Tab ── */}
        {activeTab === "response" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div>
              <label style={lS}>Datenpfad in Response (JSON-Dot-Notation)</label>
              <input style={iS} value={form.data_path || ""} onChange={e => set("data_path", e.target.value)} placeholder='z.B. "data", "results.items", "response.data.list"' />
              <p style={{ fontSize: 10, color: "#475569", marginTop: 4 }}>Leer lassen wenn die Antwort direkt ein Array ist.</p>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                <div onClick={() => set("flatten", form.flatten ? 0 : 1)}
                  style={{ width: 36, height: 20, borderRadius: 10, backgroundColor: form.flatten ? REST_COLOR : "#374151", position: "relative", transition: "background 0.2s", cursor: "pointer" }}>
                  <div style={{ position: "absolute", top: 2, left: form.flatten ? 18 : 2, width: 16, height: 16, borderRadius: "50%", backgroundColor: "#fff", transition: "left 0.2s" }} />
                </div>
                <span style={{ fontSize: 12, color: "#94a3b8" }}>Verschachtelte Objekte flach machen</span>
              </label>
            </div>
          </div>
        )}

        {/* ── Paginierung Tab ── */}
        {activeTab === "paging" && (
          <PaginationEditor value={form.pagination} onChange={v => set("pagination", v)} />
        )}

        {/* ── Scheduler Tab ── */}
        {activeTab === "schedule" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <label style={lS}>Ziel-Dataset</label>
                <select style={iS} value={form.dataset_id || ""} onChange={e => set("dataset_id", e.target.value ? parseInt(e.target.value) : null)}>
                  <option value="">Neues Dataset erstellen</option>
                  {datasets?.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>
              </div>
              <div>
                <label style={lS}>Modus</label>
                <select style={iS} value={form.dataset_mode} onChange={e => set("dataset_mode", e.target.value)}>
                  <option value="replace">Ersetzen (replace)</option>
                  <option value="append">Anhängen (append)</option>
                </select>
              </div>
            </div>
            <div>
              <label style={lS}>Cron-Ausdruck (leer = manuell)</label>
              <input style={iS} value={form.cron_expr || ""} onChange={e => set("cron_expr", e.target.value)} placeholder='z.B. "0 6 * * *" = täglich 6 Uhr' />
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                <div onClick={() => set("active", form.active ? 0 : 1)}
                  style={{ width: 36, height: 20, borderRadius: 10, backgroundColor: form.active ? "#6ee7b7" : "#374151", position: "relative", transition: "background 0.2s", cursor: "pointer" }}>
                  <div style={{ position: "absolute", top: 2, left: form.active ? 18 : 2, width: 16, height: 16, borderRadius: "50%", backgroundColor: "#fff", transition: "left 0.2s" }} />
                </div>
                <span style={{ fontSize: 12, color: "#94a3b8" }}>Aktiv</span>
              </label>
            </div>
          </div>
        )}

        {/* Test-Ergebnis */}
        {testResult && (
          <div style={{ marginTop: 12, padding: 12, borderRadius: 8, backgroundColor: testResult.success ? "rgba(110,231,183,0.06)" : "rgba(248,113,113,0.06)", border: `1px solid ${testResult.success ? "rgba(110,231,183,0.2)" : "rgba(248,113,113,0.2)"}` }}>
            {testResult.success ? (
              <div>
                <p style={{ fontSize: 12, color: "#6ee7b7", fontWeight: 600, marginBottom: 8 }}>✓ Verbindung erfolgreich · {testResult.rows} Einträge (1. Seite) · {testResult.columns?.length} Spalten</p>
                {testResult.preview?.length > 0 && (
                  <div style={{ overflowX: "auto", maxHeight: 200, overflowY: "auto", scrollbarWidth: "thin" }}>
                    <table style={{ fontSize: 10, borderCollapse: "collapse", minWidth: "max-content" }}>
                      <thead>
                        <tr>{testResult.columns?.map(c => <th key={c} style={{ textAlign: "left", padding: "3px 8px", color: "#64748b", borderBottom: "1px solid rgba(255,255,255,0.06)", whiteSpace: "nowrap", fontFamily: "monospace" }}>{c}</th>)}</tr>
                      </thead>
                      <tbody>
                        {testResult.preview?.map((row, i) => (
                          <tr key={i}>{testResult.columns?.map(c => <td key={c} style={{ padding: "2px 8px", color: "#94a3b8", fontFamily: "monospace", whiteSpace: "nowrap", maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis" }}>{String(row[c] ?? "")}</td>)}</tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            ) : (
              <p style={{ fontSize: 12, color: "#f87171", fontFamily: "monospace" }}>{testResult.error}</p>
            )}
          </div>
        )}

        {error && <p style={{ fontSize: 12, color: "#f87171", marginTop: 8, padding: "8px 12px", backgroundColor: "rgba(248,113,113,0.08)", borderRadius: 6 }}>{error}</p>}
      </div>

      {/* Aktionsleiste */}
      <div style={{ display: "flex", gap: 8, padding: "12px 16px", borderTop: `1px solid rgba(255,255,255,0.06)`, backgroundColor: "rgba(0,0,0,0.15)" }}>
        <button onClick={handleTest} disabled={!form.url || testing}
          style={{ padding: "7px 16px", borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: "pointer", backgroundColor: "transparent", border: `1px solid ${REST_COLOR}`, color: REST_COLOR, opacity: testing ? 0.6 : 1, display: "flex", alignItems: "center", gap: 6 }}>
          {testing ? <><Loader2 size={12} className="animate-spin" /> Teste…</> : <><Wifi size={12} /> Verbindung testen</>}
        </button>
        <div style={{ flex: 1 }} />
        <button onClick={onCancel} style={{ padding: "7px 14px", borderRadius: 6, fontSize: 12, cursor: "pointer", backgroundColor: "transparent", border: "1px solid rgba(255,255,255,0.1)", color: "#64748b" }}>Abbrechen</button>
        <button onClick={handleSave} disabled={!form.name || !form.url || saving}
          style={{ padding: "7px 20px", borderRadius: 6, fontSize: 12, fontWeight: 700, cursor: "pointer", backgroundColor: REST_COLOR, color: "#fff", border: "none", opacity: saving ? 0.6 : 1, display: "flex", alignItems: "center", gap: 6 }}>
          {saving ? <><Loader2 size={12} className="animate-spin" /> Speichern…</> : "Speichern"}
        </button>
      </div>
    </div>
  );
}

function RestApiPanel({ projectId, datasets, canEdit }) {
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editSource, setEditSource] = useState(null);
  const [importing, setImporting] = useState({});
  const [importName, setImportName] = useState({});

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/api/rest-sources/", { params: projectId ? { project_id: projectId } : {} });
      setSources(data);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [projectId]);

  const handleDelete = async (id) => {
    if (!window.confirm("Connector löschen?")) return;
    await api.delete(`/api/rest-sources/${id}`);
    load();
  };

  const handleTrigger = async (s) => {
    setImporting(p => ({ ...p, [s.id]: true }));
    try {
      await api.post(`/api/rest-sources/${s.id}/trigger`);
      setTimeout(load, 1500);
    } catch { /* ignore */ }
    finally { setTimeout(() => setImporting(p => ({ ...p, [s.id]: false })), 1500); }
  };

  const handleImport = async (s) => {
    setImporting(p => ({ ...p, [s.id]: "importing" }));
    try {
      await api.post(`/api/rest-sources/${s.id}/import`, {
        dataset_name: importName[s.id] || s.name,
        dataset_mode: s.dataset_mode,
        dataset_id: s.dataset_id,
      });
      load();
    } catch { /* ignore */ }
    finally { setImporting(p => ({ ...p, [s.id]: false })); }
  };

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "20px 0" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
        <div style={{ width: 38, height: 38, borderRadius: 8, backgroundColor: `${REST_COLOR}18`, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Wifi size={18} style={{ color: REST_COLOR }} />
        </div>
        <div>
          <h2 style={{ fontSize: 15, fontWeight: 700, color: "#f1f5f9", margin: 0 }}>REST API Connectors</h2>
          <p style={{ fontSize: 12, color: "#64748b", margin: 0 }}>HTTP/REST-APIs als Dataset-Quelle · Auth · Paginierung · Scheduler</p>
        </div>
        {canEdit && !showForm && (
          <button onClick={() => { setEditSource(null); setShowForm(true); }}
            style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6, padding: "7px 14px", borderRadius: 7, fontSize: 12, fontWeight: 600, cursor: "pointer", backgroundColor: `${REST_COLOR}18`, border: `1px solid ${REST_COLOR}44`, color: REST_COLOR }}>
            <Plus size={13} /> Neuer Connector
          </button>
        )}
      </div>

      {/* Formular */}
      {showForm && (
        <RestSourceForm
          initial={editSource}
          projectId={projectId}
          datasets={datasets}
          onSaved={() => { setShowForm(false); setEditSource(null); load(); }}
          onCancel={() => { setShowForm(false); setEditSource(null); }}
        />
      )}

      {/* Liste */}
      {loading ? (
        <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#64748b", fontSize: 13 }}>
          <Loader2 size={16} className="animate-spin" /> Lade…
        </div>
      ) : sources.length === 0 && !showForm ? (
        <div style={{ textAlign: "center", padding: "48px 24px", color: "#475569" }}>
          <Wifi size={32} style={{ marginBottom: 12, opacity: 0.4 }} />
          <p style={{ fontSize: 14 }}>Noch keine REST-Connectors.</p>
          {canEdit && <button onClick={() => setShowForm(true)} style={{ marginTop: 12, padding: "8px 20px", borderRadius: 7, fontSize: 12, fontWeight: 600, cursor: "pointer", backgroundColor: `${REST_COLOR}18`, border: `1px solid ${REST_COLOR}44`, color: REST_COLOR }}>Ersten Connector anlegen</button>}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {sources.map(s => {
            const isImporting = importing[s.id];
            const pag = s.pagination?.type || "none";
            return (
              <div key={s.id} style={{ backgroundColor: "rgba(255,255,255,0.02)", border: `1px solid ${s.last_run_status === "error" ? "rgba(248,113,113,0.3)" : "rgba(255,255,255,0.07)"}`, borderRadius: 10, overflow: "hidden" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 16px" }}>
                  {/* Status-Dot */}
                  <div style={{ width: 8, height: 8, borderRadius: "50%", flexShrink: 0, backgroundColor: s.last_run_status === "ok" ? "#6ee7b7" : s.last_run_status === "error" ? "#f87171" : "#374151" }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      <span style={{ fontSize: 13, fontWeight: 600, color: "#f1f5f9" }}>{s.name}</span>
                      <span style={{ fontSize: 10, fontWeight: 700, padding: "1px 6px", borderRadius: 3, backgroundColor: `${REST_COLOR}20`, color: REST_COLOR }}>{s.method}</span>
                      {pag !== "none" && <span style={{ fontSize: 10, color: "#64748b", backgroundColor: "rgba(255,255,255,0.05)", padding: "1px 6px", borderRadius: 3 }}>⟳ {pag}</span>}
                      {s.auth_type !== "none" && <span style={{ fontSize: 10, color: "#fbbf24", backgroundColor: "rgba(251,191,36,0.1)", padding: "1px 6px", borderRadius: 3 }}>🔑 {s.auth_type}</span>}
                      {s.cron_expr && <span style={{ fontSize: 10, color: "#6ee7b7", backgroundColor: "rgba(110,231,183,0.08)", padding: "1px 6px", borderRadius: 3 }}>⏱ {s.cron_expr}</span>}
                    </div>
                    <p style={{ fontSize: 11, color: "#475569", margin: "2px 0 0", fontFamily: "monospace", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.url}</p>
                    {s.last_run_at && (
                      <p style={{ fontSize: 10, color: s.last_run_status === "error" ? "#f87171" : "#64748b", margin: "2px 0 0" }}>
                        Letzter Lauf: {new Date(s.last_run_at).toLocaleString("de-DE")} · {s.last_rows ?? 0} Zeilen
                        {s.last_run_msg && s.last_run_status === "error" && ` · ${s.last_run_msg.slice(0, 80)}`}
                      </p>
                    )}
                  </div>
                  <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                    {canEdit && (
                      <>
                        <button onClick={() => { setEditSource(s); setShowForm(true); }}
                          style={{ padding: "5px 10px", borderRadius: 5, fontSize: 11, cursor: "pointer", backgroundColor: "transparent", border: "1px solid rgba(255,255,255,0.1)", color: "#94a3b8" }}>
                          <Pencil size={11} />
                        </button>
                        <button onClick={() => handleTrigger(s)} disabled={!!isImporting}
                          style={{ padding: "5px 12px", borderRadius: 5, fontSize: 11, fontWeight: 600, cursor: "pointer", backgroundColor: `${REST_COLOR}15`, border: `1px solid ${REST_COLOR}44`, color: REST_COLOR, display: "flex", alignItems: "center", gap: 5 }}>
                          {isImporting ? <Loader2 size={11} className="animate-spin" /> : <Play size={11} />} Import
                        </button>
                        <button onClick={() => handleDelete(s.id)}
                          style={{ padding: "5px 10px", borderRadius: 5, fontSize: 11, cursor: "pointer", backgroundColor: "transparent", border: "1px solid rgba(248,113,113,0.2)", color: "#f87171" }}>
                          <Trash2 size={11} />
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─── Access Import Panel ──────────────────────────────────────────────────────
const ACCESS_COLOR = "#f59e0b";


export { RestApiPanel, RestSourceForm };
