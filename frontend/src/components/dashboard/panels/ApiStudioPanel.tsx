import { useState, useEffect, useCallback, useMemo } from "react";
import {
  Send, Plus, Trash2, Pencil, Loader2, X, FolderOpen, Save, History,
  Globe, ChevronRight, ChevronDown, Layers, Check, AlertTriangle, Table2,
} from "lucide-react";
import api from "../../../api/client";
import {
  KvEditor, AuthEditor, REST_AUTH_TYPES, METHODS, BODY_TYPES, TEMPLATE_VARS,
} from "./RestApiPanel";

const C = "#22d3ee";                       // Akzentfarbe des API Studios
const BASE = "/api/api-studio";

// Farbe je HTTP-Methode – dieselbe Sprache, die man aus API-Werkzeugen kennt.
const METHOD_COLOR = {
  GET: "#6ee7b7", POST: "#fbbf24", PUT: "#60a5fa", PATCH: "#c084fc",
  DELETE: "#f87171", HEAD: "#94a3b8", OPTIONS: "#94a3b8",
};

const LEER_REQUEST = {
  name: "", url: "", method: "GET",
  headers: {}, query_params: {},
  body_type: "none", body_content: "",
  auth_type: "inherit", auth_config: {},
  data_path: "", flatten: 1,
  collection_id: null, description: "", store_response: 0,
  pagination: { type: "none" }, dataset_mode: "replace", cron_expr: "", active: 1,
};

const iS = { width: "100%", backgroundColor: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 6, color: "#f1f5f9", fontSize: 12, padding: "7px 10px", outline: "none", boxSizing: "border-box" as const };
const lS = { fontSize: 10, fontWeight: 700, textTransform: "uppercase" as const, letterSpacing: "0.07em", color: "#64748b", display: "block", marginBottom: 4 };
const btn = { padding: "7px 14px", borderRadius: 6, fontSize: 12, cursor: "pointer", backgroundColor: "transparent", border: "1px solid rgba(255,255,255,0.12)", color: "#94a3b8" };
const btnPrimary = { ...btn, backgroundColor: C, color: "#083344", border: "none", fontWeight: 700 };

function statusFarbe(code) {
  if (!code) return "#64748b";
  if (code < 300) return "#6ee7b7";
  if (code < 400) return "#60a5fa";
  if (code < 500) return "#fbbf24";
  return "#f87171";
}

function groesse(bytes) {
  if (bytes == null) return "–";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** Sehr schlichtes JSON-Einfärben – reicht, um Struktur schnell zu erfassen. */
function JsonAnsicht({ text }) {
  const teile = useMemo(() => {
    const out = [];
    const re = /("(?:\\.|[^"\\])*"\s*:)|("(?:\\.|[^"\\])*")|(\b-?\d+\.?\d*(?:[eE][+-]?\d+)?\b)|(\btrue\b|\bfalse\b|\bnull\b)/g;
    let last = 0, m;
    while ((m = re.exec(text)) !== null) {
      if (m.index > last) out.push({ t: text.slice(last, m.index), f: "#64748b" });
      const farbe = m[1] ? "#7dd3fc" : m[2] ? "#a5b4fc" : m[3] ? "#fbbf24" : "#f472b6";
      out.push({ t: m[0], f: farbe });
      last = m.index + m[0].length;
    }
    if (last < text.length) out.push({ t: text.slice(last), f: "#64748b" });
    return out;
  }, [text]);

  return (
    <pre style={{ margin: 0, fontFamily: "monospace", fontSize: 11, lineHeight: 1.6, whiteSpace: "pre", color: "#94a3b8" }}>
      {teile.map((p, i) => <span key={i} style={{ color: p.f }}>{p.t}</span>)}
    </pre>
  );
}

// ── Antwort-Ansicht ───────────────────────────────────────────────────────────

function AntwortAnsicht({ antwort, aufDatenpfad }) {
  const [reiter, setReiter] = useState("pretty");

  if (!antwort) return (
    <div style={{ padding: "48px 24px", textAlign: "center", color: "#475569" }}>
      <Send size={28} style={{ marginBottom: 10, opacity: 0.35 }} />
      <p style={{ fontSize: 13, margin: 0 }}>Noch keine Antwort – Request abschicken.</p>
    </div>
  );

  if (!antwort.success) return (
    <div style={{ padding: 16 }}>
      <div style={{ display: "flex", gap: 10, padding: 14, borderRadius: 8, backgroundColor: "rgba(248,113,113,0.07)", border: "1px solid rgba(248,113,113,0.25)" }}>
        <AlertTriangle size={16} style={{ color: "#f87171", flexShrink: 0, marginTop: 1 }} />
        <div>
          <p style={{ fontSize: 12, color: "#f87171", fontWeight: 700, margin: 0 }}>Request nicht zustande gekommen</p>
          <p style={{ fontSize: 11, color: "#fca5a5", fontFamily: "monospace", margin: "6px 0 0", wordBreak: "break-word" }}>{antwort.error}</p>
        </div>
      </div>
    </div>
  );

  const pretty = antwort.json != null ? JSON.stringify(antwort.json, null, 2) : null;
  const REITER = [
    { id: "pretty", l: "Lesbar", aus: !pretty },
    { id: "raw", l: "Roh" },
    { id: "headers", l: `Header (${Object.keys(antwort.response_headers || {}).length})` },
    { id: "tabelle", l: `Tabelle${antwort.rows ? ` (${antwort.rows})` : ""}`, aus: !antwort.rows },
  ].filter(r => !r.aus);
  const aktiv = REITER.some(r => r.id === reiter) ? reiter : REITER[0]?.id;

  return (
    <div>
      {/* Statuszeile */}
      <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "10px 16px", borderBottom: "1px solid rgba(255,255,255,0.06)", flexWrap: "wrap" }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: statusFarbe(antwort.status_code), fontFamily: "monospace" }}>
          {antwort.status_code} {antwort.reason}
        </span>
        <span style={{ fontSize: 11, color: "#64748b" }}>{antwort.duration_ms} ms</span>
        <span style={{ fontSize: 11, color: "#64748b" }}>{groesse(antwort.size_bytes)}</span>
        {antwort.content_type && (
          <span style={{ fontSize: 10, color: "#64748b", fontFamily: "monospace", backgroundColor: "rgba(255,255,255,0.04)", padding: "2px 6px", borderRadius: 3 }}>
            {antwort.content_type.split(";")[0]}
          </span>
        )}
        {antwort.truncated && (
          <span style={{ fontSize: 10, color: "#fbbf24" }}>Antwort gekürzt angezeigt</span>
        )}
      </div>

      {/* Hinweis, wo die Daten stecken */}
      {antwort.table_hint && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "12px 16px 0", padding: "8px 12px", borderRadius: 6, backgroundColor: `${C}0e`, border: `1px solid ${C}33` }}>
          <Table2 size={13} style={{ color: C, flexShrink: 0 }} />
          <span style={{ fontSize: 11, color: "#94a3b8" }}>
            Die Liste steckt vermutlich unter <code style={{ fontFamily: "monospace", color: C }}>{antwort.table_hint}</code>
          </span>
          <button onClick={() => aufDatenpfad(antwort.table_hint)}
            style={{ ...btn, marginLeft: "auto", padding: "3px 10px", fontSize: 11, borderColor: `${C}55`, color: C }}>
            Als Datenpfad übernehmen
          </button>
        </div>
      )}

      {/* Reiter */}
      <div style={{ display: "flex", gap: 2, padding: "10px 16px 0" }}>
        {REITER.map(r => (
          <button key={r.id} onClick={() => setReiter(r.id)}
            style={{ padding: "5px 12px", fontSize: 11, fontWeight: 600, cursor: "pointer", border: "none", borderRadius: 5,
              backgroundColor: aktiv === r.id ? `${C}18` : "transparent", color: aktiv === r.id ? C : "#64748b" }}>
            {r.l}
          </button>
        ))}
      </div>

      <div style={{ padding: 16, maxHeight: 420, overflow: "auto" }}>
        {aktiv === "pretty" && <JsonAnsicht text={pretty} />}
        {aktiv === "raw" && (
          <pre style={{ margin: 0, fontFamily: "monospace", fontSize: 11, lineHeight: 1.6, whiteSpace: "pre-wrap", wordBreak: "break-word", color: "#94a3b8" }}>
            {antwort.body_text || "(leerer Antwortkörper)"}
          </pre>
        )}
        {aktiv === "headers" && (
          <table style={{ fontSize: 11, borderCollapse: "collapse", width: "100%" }}>
            <tbody>
              {Object.entries(antwort.response_headers || {}).map(([k, v]) => (
                <tr key={k}>
                  <td style={{ padding: "3px 12px 3px 0", color: "#7dd3fc", fontFamily: "monospace", verticalAlign: "top", whiteSpace: "nowrap" }}>{k}</td>
                  <td style={{ padding: "3px 0", color: "#94a3b8", fontFamily: "monospace", wordBreak: "break-all" }}>{String(v)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {aktiv === "tabelle" && (
          <div style={{ overflowX: "auto" }}>
            <table style={{ fontSize: 10, borderCollapse: "collapse", minWidth: "max-content" }}>
              <thead>
                <tr>{antwort.columns.map(c => (
                  <th key={c} style={{ textAlign: "left", padding: "4px 10px", color: "#64748b", borderBottom: "1px solid rgba(255,255,255,0.08)", whiteSpace: "nowrap", fontFamily: "monospace" }}>{c}</th>
                ))}</tr>
              </thead>
              <tbody>
                {antwort.preview.map((row, i) => (
                  <tr key={i}>{antwort.columns.map(c => (
                    <td key={c} style={{ padding: "3px 10px", color: "#94a3b8", fontFamily: "monospace", whiteSpace: "nowrap", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis" }}>
                      {row[c] === null || row[c] === undefined ? "–" : String(row[c])}
                    </td>
                  ))}</tr>
                ))}
              </tbody>
            </table>
            {antwort.rows > antwort.preview.length && (
              <p style={{ fontSize: 10, color: "#475569", marginTop: 8 }}>
                Vorschau der ersten {antwort.preview.length} von {antwort.rows} Zeilen.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Sammlungs-Dialog ──────────────────────────────────────────────────────────

function SammlungsDialog({ initial, projectId, onSaved, onClose }) {
  const [f, setF] = useState({
    name: "", description: "", base_url: "", default_headers: {},
    auth_type: "none", auth_config: {}, ...(initial || {}),
  });
  const [saving, setSaving] = useState(false);
  const [fehler, setFehler] = useState("");
  const set = (k, v) => setF(p => ({ ...p, [k]: v }));

  const speichern = async () => {
    setSaving(true); setFehler("");
    try {
      const payload = { ...f, project_id: projectId ?? null };
      if (initial?.id) await api.put(`${BASE}/collections/${initial.id}`, payload);
      else await api.post(`${BASE}/collections`, payload);
      onSaved();
    } catch (e) { setFehler(e.response?.data?.detail || "Fehler beim Speichern"); }
    finally { setSaving(false); }
  };

  return (
    <Dialog titel={initial?.id ? "Sammlung bearbeiten" : "Neue Sammlung"} onClose={onClose}>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div><label style={lS}>Name</label>
          <input style={iS} value={f.name} onChange={e => set("name", e.target.value)} placeholder="z.B. Shopware Shop" autoFocus /></div>
        <div><label style={lS}>Basis-URL</label>
          <input style={iS} value={f.base_url || ""} onChange={e => set("base_url", e.target.value)} placeholder="https://api.example.com/v1" />
          <p style={{ fontSize: 10, color: "#475569", marginTop: 4 }}>Requests dürfen dann nur noch den Pfad angeben, z.B. <code style={{ fontFamily: "monospace" }}>/orders</code>. Eine vollständige URL im Request gewinnt.</p>
        </div>
        <div><label style={lS}>Beschreibung</label>
          <input style={iS} value={f.description || ""} onChange={e => set("description", e.target.value)} /></div>
        <KvEditor label="Standard-Header" value={f.default_headers} onChange={v => set("default_headers", v)} />
        <div>
          <label style={lS}>Standard-Auth</label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 4 }}>
            {REST_AUTH_TYPES.map(a => (
              <button key={a.v} onClick={() => { set("auth_type", a.v); set("auth_config", {}); }}
                style={{ padding: "5px 12px", borderRadius: 5, fontSize: 11, cursor: "pointer",
                  border: `1px solid ${f.auth_type === a.v ? C : "rgba(255,255,255,0.1)"}`,
                  backgroundColor: f.auth_type === a.v ? `${C}18` : "transparent",
                  color: f.auth_type === a.v ? C : "#64748b" }}>{a.l}</button>
            ))}
          </div>
          <AuthEditor authType={f.auth_type} authConfig={f.auth_config || {}} onChange={v => set("auth_config", v)} />
        </div>
        {fehler && <p style={{ fontSize: 12, color: "#f87171" }}>{fehler}</p>}
      </div>
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 18 }}>
        <button style={btn} onClick={onClose}>Abbrechen</button>
        <button style={{ ...btnPrimary, opacity: !f.name || saving ? 0.5 : 1 }} disabled={!f.name || saving} onClick={speichern}>
          {saving ? "Speichern…" : "Speichern"}
        </button>
      </div>
    </Dialog>
  );
}

// ── Umgebungs-Dialog ──────────────────────────────────────────────────────────

function UmgebungsDialog({ umgebungen, projectId, onChanged, onClose }) {
  const [auswahl, setAuswahl] = useState(umgebungen[0] || null);
  const [f, setF] = useState(umgebungen[0] || { name: "", variables: [] });
  const [saving, setSaving] = useState(false);
  const [fehler, setFehler] = useState("");

  const waehlen = (u) => { setAuswahl(u); setF(u ? { ...u } : { name: "", variables: [] }); setFehler(""); };
  const setVar = (i, k, v) => setF(p => ({ ...p, variables: p.variables.map((x, j) => j === i ? { ...x, [k]: v } : x) }));

  const speichern = async () => {
    setSaving(true); setFehler("");
    try {
      const payload = { ...f, project_id: projectId ?? null, variables: f.variables || [] };
      if (f.id) await api.put(`${BASE}/environments/${f.id}`, payload);
      else await api.post(`${BASE}/environments`, payload);
      await onChanged();
      onClose();
    } catch (e) { setFehler(e.response?.data?.detail || "Fehler beim Speichern"); }
    finally { setSaving(false); }
  };

  const loeschen = async () => {
    if (!f.id || !window.confirm(`Umgebung „${f.name}" löschen?`)) return;
    await api.delete(`${BASE}/environments/${f.id}`);
    await onChanged();
    onClose();
  };

  return (
    <Dialog titel="Umgebungen" onClose={onClose} breit>
      <div style={{ display: "grid", gridTemplateColumns: "180px 1fr", gap: 16 }}>
        {/* Liste */}
        <div style={{ borderRight: "1px solid rgba(255,255,255,0.07)", paddingRight: 12 }}>
          {umgebungen.map(u => (
            <button key={u.id} onClick={() => waehlen(u)}
              style={{ display: "block", width: "100%", textAlign: "left", padding: "6px 8px", borderRadius: 5, fontSize: 12, cursor: "pointer", border: "none", marginBottom: 2,
                backgroundColor: f.id === u.id ? `${C}18` : "transparent", color: f.id === u.id ? C : "#94a3b8" }}>
              {u.name}
            </button>
          ))}
          <button onClick={() => waehlen(null)}
            style={{ display: "flex", alignItems: "center", gap: 5, width: "100%", padding: "6px 8px", borderRadius: 5, fontSize: 12, cursor: "pointer", border: "none", backgroundColor: "transparent", color: "#64748b", marginTop: 4 }}>
            <Plus size={12} /> Neue Umgebung
          </button>
        </div>

        {/* Bearbeiten */}
        <div>
          <label style={lS}>Name</label>
          <input style={{ ...iS, marginBottom: 14 }} value={f.name || ""} onChange={e => setF(p => ({ ...p, name: e.target.value }))} placeholder="z.B. Produktion" />

          <label style={lS}>Variablen</label>
          <p style={{ fontSize: 10, color: "#475569", margin: "0 0 8px" }}>
            Im Request als <code style={{ fontFamily: "monospace" }}>{"{{name}}"}</code> einsetzbar. Geheime Werte werden verschlüsselt gespeichert und nie zurückgegeben.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 5, marginBottom: 8 }}>
            {(f.variables || []).map((v, i) => (
              <div key={i} style={{ display: "flex", gap: 5, alignItems: "center" }}>
                <input style={{ ...iS, fontSize: 11, padding: "4px 8px", flex: "0 0 140px" }} placeholder="name"
                  value={v.key || ""} onChange={e => setVar(i, "key", e.target.value)} />
                <input style={{ ...iS, fontSize: 11, padding: "4px 8px", flex: 1 }} placeholder="Wert"
                  type={v.secret ? "password" : "text"}
                  value={v.value || ""} onChange={e => setVar(i, "value", e.target.value)} />
                <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10, color: "#64748b", cursor: "pointer", whiteSpace: "nowrap" }}>
                  <input type="checkbox" checked={!!v.secret} onChange={e => setVar(i, "secret", e.target.checked)} /> geheim
                </label>
                <button onClick={() => setF(p => ({ ...p, variables: p.variables.filter((_, j) => j !== i) }))}
                  style={{ color: "#f87171", fontSize: 14, padding: "2px 4px", background: "none", border: "none", cursor: "pointer" }}>×</button>
              </div>
            ))}
          </div>
          <button onClick={() => setF(p => ({ ...p, variables: [...(p.variables || []), { key: "", value: "", secret: false }] }))}
            style={{ ...btn, padding: "4px 10px", fontSize: 11, color: C, borderColor: `${C}44` }}>
            <Plus size={11} style={{ display: "inline", marginRight: 4 }} /> Variable
          </button>

          {fehler && <p style={{ fontSize: 12, color: "#f87171", marginTop: 10 }}>{fehler}</p>}
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 18 }}>
        {f.id && <button style={{ ...btn, color: "#f87171", borderColor: "rgba(248,113,113,0.25)", marginRight: "auto" }} onClick={loeschen}>Löschen</button>}
        <button style={btn} onClick={onClose}>Schließen</button>
        <button style={{ ...btnPrimary, opacity: !f.name || saving ? 0.5 : 1 }} disabled={!f.name || saving} onClick={speichern}>
          {saving ? "Speichern…" : "Speichern"}
        </button>
      </div>
    </Dialog>
  );
}

// ── Verlauf ───────────────────────────────────────────────────────────────────

function VerlaufsListe({ eintraege, onLaden, onLeeren, canEdit }) {
  if (!eintraege.length) return (
    <p style={{ fontSize: 12, color: "#475569", padding: "24px 16px", textAlign: "center" }}>Noch keine Requests geschickt.</p>
  );
  return (
    <div>
      {canEdit && (
        <div style={{ display: "flex", justifyContent: "flex-end", padding: "8px 12px" }}>
          <button style={{ ...btn, padding: "3px 10px", fontSize: 11, color: "#f87171", borderColor: "rgba(248,113,113,0.22)" }} onClick={onLeeren}>
            Verlauf leeren
          </button>
        </div>
      )}
      <div style={{ display: "flex", flexDirection: "column" }}>
        {eintraege.map(h => (
          <button key={h.id} onClick={() => onLaden(h)}
            style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", background: "none", border: "none", borderBottom: "1px solid rgba(255,255,255,0.04)", cursor: "pointer", textAlign: "left", width: "100%" }}>
            <span style={{ fontSize: 9, fontWeight: 700, fontFamily: "monospace", color: METHOD_COLOR[h.method] || "#94a3b8", flex: "0 0 52px" }}>{h.method}</span>
            <span style={{ fontSize: 11, fontWeight: 700, fontFamily: "monospace", color: statusFarbe(h.status_code), flex: "0 0 34px" }}>{h.status_code ?? "—"}</span>
            <span style={{ fontSize: 11, color: "#94a3b8", fontFamily: "monospace", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{h.url}</span>
            <span style={{ fontSize: 10, color: "#475569", flexShrink: 0 }}>{h.duration_ms} ms</span>
            <span style={{ fontSize: 10, color: "#475569", flexShrink: 0 }}>{new Date(h.created_at).toLocaleTimeString("de-DE")}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Dialog-Hülle ──────────────────────────────────────────────────────────────

function Dialog({ titel, children, onClose, breit }) {
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60, padding: 20 }}>
      <div onClick={e => e.stopPropagation()}
        style={{ backgroundColor: "#0f172a", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, width: breit ? 760 : 520, maxWidth: "100%", maxHeight: "88vh", overflowY: "auto", padding: 20 }}>
        <div style={{ display: "flex", alignItems: "center", marginBottom: 16 }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: "#f1f5f9", margin: 0 }}>{titel}</h3>
          <button onClick={onClose} style={{ marginLeft: "auto", color: "#64748b", background: "none", border: "none", cursor: "pointer" }}><X size={16} /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

// ── Hauptpanel ────────────────────────────────────────────────────────────────

function ApiStudioPanel({ projectId, canEdit }) {
  const [sammlungen, setSammlungen] = useState([]);
  const [requests, setRequests] = useState([]);
  const [umgebungen, setUmgebungen] = useState([]);
  const [verlauf, setVerlauf] = useState([]);

  const [envId, setEnvId] = useState(null);
  const [offen, setOffen] = useState({});           // aufgeklappte Sammlungen
  const [aktiveId, setAktiveId] = useState(null);   // id des geladenen Requests
  const [f, setF] = useState(LEER_REQUEST);
  const [reiter, setReiter] = useState("params");

  const [antwort, setAntwort] = useState(null);
  const [sende, setSende] = useState(false);
  const [speichere, setSpeichere] = useState(false);
  const [fehler, setFehler] = useState("");
  const [dialog, setDialog] = useState(null);       // "sammlung" | "umgebung" | "verlauf"
  const [sammlungEdit, setSammlungEdit] = useState(null);

  const p = projectId ? { project_id: projectId } : {};

  const laden = useCallback(async () => {
    try {
      const [c, r, u] = await Promise.all([
        api.get(`${BASE}/collections`, { params: p }),
        api.get("/api/rest-sources/", { params: p }),
        api.get(`${BASE}/environments`, { params: p }),
      ]);
      setSammlungen(c.data);
      setRequests(r.data);
      setUmgebungen(u.data);
      setEnvId(prev => (u.data.some(e => e.id === prev) ? prev
        : (u.data.find(e => e.is_default)?.id ?? null)));
    } catch { /* Panel bleibt leer */ }
  }, [projectId]);

  const verlaufLaden = useCallback(async () => {
    try {
      const { data } = await api.get(`${BASE}/history`, { params: { ...p, limit: 100 } });
      setVerlauf(data);
    } catch { /* ignorieren */ }
  }, [projectId]);

  useEffect(() => { laden(); verlaufLaden(); }, [laden, verlaufLaden]);

  const set = (k, v) => setF(prev => ({ ...prev, [k]: v }));

  const requestLaden = (r) => {
    setAktiveId(r.id);
    setF({ ...LEER_REQUEST, ...r, auth_config: r.auth_config || {}, body_content: r.body_content || "" });
    setAntwort(null); setFehler("");
  };

  const neuerRequest = (collectionId = null) => {
    setAktiveId(null);
    setF({ ...LEER_REQUEST, collection_id: collectionId });
    setAntwort(null); setFehler("");
  };

  const senden = async () => {
    setSende(true); setFehler(""); setAntwort(null);
    try {
      const { data } = await api.post(`${BASE}/send`, {
        rest_source_id: aktiveId, collection_id: f.collection_id,
        environment_id: envId, project_id: projectId ?? null,
        name: f.name || null, url: f.url, method: f.method,
        headers: f.headers, query_params: f.query_params,
        body_type: f.body_type, body_content: f.body_content,
        auth_type: f.auth_type, auth_config: f.auth_config,
        data_path: f.data_path || null, flatten: f.flatten,
      });
      setAntwort(data);
      verlaufLaden();
    } catch (e) {
      setFehler(e.response?.data?.detail || "Request fehlgeschlagen");
    } finally { setSende(false); }
  };

  const speichern = async () => {
    setSpeichere(true); setFehler("");
    try {
      const payload = { ...f, project_id: projectId ?? null,
        data_path: f.data_path || null,
        pagination: f.pagination || { type: "none" } };
      const { data } = aktiveId
        ? await api.put(`/api/rest-sources/${aktiveId}`, payload)
        : await api.post("/api/rest-sources/", payload);
      setAktiveId(data.id);
      await laden();
    } catch (e) { setFehler(e.response?.data?.detail || "Speichern fehlgeschlagen"); }
    finally { setSpeichere(false); }
  };

  const requestLoeschen = async (r) => {
    if (!window.confirm(`Request „${r.name}" löschen?`)) return;
    await api.delete(`/api/rest-sources/${r.id}`);
    if (aktiveId === r.id) neuerRequest();
    laden();
  };

  const sammlungLoeschen = async (c) => {
    if (!window.confirm(`Sammlung „${c.name}" löschen? Die Requests bleiben erhalten.`)) return;
    await api.delete(`${BASE}/collections/${c.id}`);
    laden();
  };

  const verlaufEintragLaden = async (h) => {
    const s = h.request_snapshot || (await api.get(`${BASE}/history/${h.id}`)).data.request_snapshot || {};
    setAktiveId(h.rest_source_id ?? null);
    setF(prev => ({ ...prev, url: s.url || h.url, method: s.method || h.method,
      query_params: s.query_params || {}, body_type: s.body_type || "none",
      body_content: s.body_content || "" }));
    setDialog(null);
  };

  const ohneSammlung = requests.filter(r => !r.collection_id);
  const envVars = umgebungen.find(u => u.id === envId)?.variables || [];
  const alleVars = [...envVars.map(v => `{{${v.key}}}`), ...TEMPLATE_VARS];

  const REITER = [
    { id: "params", l: `Params${Object.keys(f.query_params || {}).length ? ` (${Object.keys(f.query_params).length})` : ""}` },
    { id: "headers", l: `Headers${Object.keys(f.headers || {}).length ? ` (${Object.keys(f.headers).length})` : ""}` },
    { id: "body", l: "Body" },
    { id: "auth", l: "Auth" },
    { id: "daten", l: "Datenpfad" },
  ];

  return (
    <div style={{ maxWidth: 1400, margin: "0 auto", padding: "20px 0" }}>
      {/* Kopfzeile */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
        <div style={{ width: 38, height: 38, borderRadius: 8, backgroundColor: `${C}18`, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Globe size={18} style={{ color: C }} />
        </div>
        <div>
          <h2 style={{ fontSize: 15, fontWeight: 700, color: "#f1f5f9", margin: 0 }}>API Studio</h2>
          <p style={{ fontSize: 12, color: "#64748b", margin: 0 }}>REST-APIs testen, verstehen und als Connector speichern</p>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
          <select style={{ ...iS, width: "auto", fontSize: 11, padding: "6px 8px" }}
            value={envId ?? ""} onChange={e => setEnvId(e.target.value ? parseInt(e.target.value) : null)}>
            <option value="">Ohne Umgebung</option>
            {umgebungen.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
          {canEdit && <button style={{ ...btn, padding: "6px 10px", fontSize: 11 }} onClick={() => setDialog("umgebung")}>
            <Layers size={12} style={{ display: "inline", marginRight: 5 }} />Umgebungen
          </button>}
          <button style={{ ...btn, padding: "6px 10px", fontSize: 11 }} onClick={() => { verlaufLaden(); setDialog("verlauf"); }}>
            <History size={12} style={{ display: "inline", marginRight: 5 }} />Verlauf
          </button>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "250px 1fr", gap: 16, alignItems: "start" }}>
        {/* ── Seitenleiste ── */}
        <div style={{ backgroundColor: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 10, padding: 10, position: "sticky", top: 20 }}>
          {canEdit && (
            <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
              <button style={{ ...btn, flex: 1, padding: "5px 8px", fontSize: 11, color: C, borderColor: `${C}44` }}
                onClick={() => { setSammlungEdit(null); setDialog("sammlung"); }}>
                <Plus size={11} style={{ display: "inline", marginRight: 4 }} />Sammlung
              </button>
              <button style={{ ...btn, flex: 1, padding: "5px 8px", fontSize: 11 }} onClick={() => neuerRequest()}>
                <Plus size={11} style={{ display: "inline", marginRight: 4 }} />Request
              </button>
            </div>
          )}

          {sammlungen.length === 0 && requests.length === 0 && (
            <p style={{ fontSize: 11, color: "#475569", padding: "16px 6px", textAlign: "center", lineHeight: 1.6 }}>
              Noch nichts angelegt. Einfach rechts eine URL eintippen und senden – speichern kannst du später.
            </p>
          )}

          {sammlungen.map(c => {
            const kinder = requests.filter(r => r.collection_id === c.id);
            const auf = offen[c.id] !== false;
            return (
              <div key={c.id} style={{ marginBottom: 4 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 4, padding: "4px 2px" }}>
                  <button onClick={() => setOffen(o => ({ ...o, [c.id]: !auf }))}
                    style={{ display: "flex", alignItems: "center", gap: 5, flex: 1, minWidth: 0, background: "none", border: "none", cursor: "pointer", padding: 0, textAlign: "left" }}>
                    {auf ? <ChevronDown size={12} style={{ color: "#64748b", flexShrink: 0 }} /> : <ChevronRight size={12} style={{ color: "#64748b", flexShrink: 0 }} />}
                    <FolderOpen size={12} style={{ color: C, flexShrink: 0 }} />
                    <span style={{ fontSize: 12, fontWeight: 600, color: "#e2e8f0", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.name}</span>
                  </button>
                  {canEdit && (
                    <>
                      <button title="Request in dieser Sammlung" onClick={() => neuerRequest(c.id)}
                        style={{ color: "#64748b", background: "none", border: "none", cursor: "pointer", padding: 2 }}><Plus size={11} /></button>
                      <button title="Sammlung bearbeiten" onClick={() => { setSammlungEdit(c); setDialog("sammlung"); }}
                        style={{ color: "#64748b", background: "none", border: "none", cursor: "pointer", padding: 2 }}><Pencil size={10} /></button>
                      <button title="Sammlung löschen" onClick={() => sammlungLoeschen(c)}
                        style={{ color: "#64748b", background: "none", border: "none", cursor: "pointer", padding: 2 }}><Trash2 size={10} /></button>
                    </>
                  )}
                </div>
                {auf && (
                  <div style={{ marginLeft: 14, borderLeft: "1px solid rgba(255,255,255,0.06)", paddingLeft: 6 }}>
                    {kinder.length === 0 && <p style={{ fontSize: 10, color: "#475569", padding: "3px 4px", margin: 0 }}>leer</p>}
                    {kinder.map(r => <RequestZeile key={r.id} r={r} aktiv={aktiveId === r.id} onClick={() => requestLaden(r)} onDelete={canEdit ? () => requestLoeschen(r) : null} />)}
                  </div>
                )}
              </div>
            );
          })}

          {ohneSammlung.length > 0 && (
            <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid rgba(255,255,255,0.06)" }}>
              <p style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em", color: "#475569", margin: "0 0 4px 2px" }}>Ohne Sammlung</p>
              {ohneSammlung.map(r => <RequestZeile key={r.id} r={r} aktiv={aktiveId === r.id} onClick={() => requestLaden(r)} onDelete={canEdit ? () => requestLoeschen(r) : null} />)}
            </div>
          )}
        </div>

        {/* ── Arbeitsbereich ── */}
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {/* URL-Leiste */}
          <div style={{ backgroundColor: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 10, padding: 14 }}>
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10 }}>
              <input style={{ ...iS, flex: 1, fontWeight: 600 }} placeholder="Name des Requests (zum Speichern)"
                value={f.name} onChange={e => set("name", e.target.value)} />
              <select style={{ ...iS, width: "auto", fontSize: 11 }} value={f.collection_id ?? ""}
                onChange={e => set("collection_id", e.target.value ? parseInt(e.target.value) : null)}>
                <option value="">Ohne Sammlung</option>
                {sammlungen.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>

            <div style={{ display: "flex", gap: 8 }}>
              <select style={{ ...iS, width: 110, fontWeight: 700, color: METHOD_COLOR[f.method] || "#f1f5f9" }}
                value={f.method} onChange={e => set("method", e.target.value)}>
                {METHODS.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
              <input style={{ ...iS, flex: 1, fontFamily: "monospace" }} placeholder="https://api.example.com/v1/orders  oder  /orders"
                value={f.url} onChange={e => set("url", e.target.value)}
                onKeyDown={e => { if (e.key === "Enter" && f.url && !sende) senden(); }} />
              <button style={{ ...btnPrimary, display: "flex", alignItems: "center", gap: 6, opacity: !f.url || sende ? 0.5 : 1 }}
                disabled={!f.url || sende} onClick={senden}>
                {sende ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />} Senden
              </button>
              {canEdit && (
                <button style={{ ...btn, display: "flex", alignItems: "center", gap: 6, opacity: !f.name || !f.url || speichere ? 0.5 : 1 }}
                  disabled={!f.name || !f.url || speichere} onClick={speichern} title={!f.name ? "Name vergeben, dann speichern" : "Als Connector speichern"}>
                  {speichere ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} {aktiveId ? "Sichern" : "Speichern"}
                </button>
              )}
            </div>

            {/* Verfügbare Variablen */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 10 }}>
              {alleVars.map(v => (
                <code key={v} title="In die URL einfügen"
                  onClick={() => set("url", (f.url || "") + v)}
                  style={{ fontSize: 10, backgroundColor: `${C}12`, color: C, padding: "2px 6px", borderRadius: 3, cursor: "pointer", fontFamily: "monospace" }}>{v}</code>
              ))}
            </div>

            {/* Reiter */}
            <div style={{ display: "flex", gap: 2, marginTop: 14, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
              {REITER.map(t => (
                <button key={t.id} onClick={() => setReiter(t.id)}
                  style={{ padding: "7px 12px", fontSize: 11, fontWeight: 600, cursor: "pointer", background: "none", border: "none",
                    borderBottom: `2px solid ${reiter === t.id ? C : "transparent"}`, color: reiter === t.id ? C : "#64748b" }}>
                  {t.l}
                </button>
              ))}
            </div>

            <div style={{ paddingTop: 14 }}>
              {reiter === "params" && <KvEditor label="Query-Parameter" value={f.query_params} onChange={v => set("query_params", v)} />}
              {reiter === "headers" && <KvEditor label="Headers" value={f.headers} onChange={v => set("headers", v)} />}
              {reiter === "body" && (
                <div>
                  <div style={{ display: "flex", gap: 6, marginBottom: 8, flexWrap: "wrap" }}>
                    {BODY_TYPES.map(b => (
                      <button key={b.v} onClick={() => set("body_type", b.v)}
                        style={{ padding: "4px 10px", borderRadius: 4, fontSize: 11, cursor: "pointer",
                          border: `1px solid ${f.body_type === b.v ? C : "rgba(255,255,255,0.1)"}`,
                          backgroundColor: f.body_type === b.v ? `${C}18` : "transparent",
                          color: f.body_type === b.v ? C : "#64748b" }}>{b.l}</button>
                    ))}
                  </div>
                  {f.body_type !== "none" && (
                    <textarea style={{ ...iS, fontFamily: "monospace", minHeight: 140, resize: "vertical", lineHeight: 1.5 }}
                      placeholder={f.body_type === "json" ? '{\n  "key": "value"\n}'
                        : f.body_type === "xml" ? "<anfrage>\n  <feld>Wert</feld>\n</anfrage>"
                        : ["form", "multipart"].includes(f.body_type) ? "key=value\nkey2=value2"
                        : "Roher Text…"}
                      value={f.body_content || ""} onChange={e => set("body_content", e.target.value)} />
                  )}
                </div>
              )}
              {reiter === "auth" && (
                <div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
                    {[{ v: "inherit", l: "Von Sammlung erben" }, ...REST_AUTH_TYPES].map(a => (
                      <button key={a.v} onClick={() => { set("auth_type", a.v); set("auth_config", {}); }}
                        style={{ padding: "5px 12px", borderRadius: 5, fontSize: 11, cursor: "pointer",
                          border: `1px solid ${f.auth_type === a.v ? C : "rgba(255,255,255,0.1)"}`,
                          backgroundColor: f.auth_type === a.v ? `${C}18` : "transparent",
                          color: f.auth_type === a.v ? C : "#64748b" }}>{a.l}</button>
                    ))}
                  </div>
                  {f.auth_type === "inherit" && (
                    <p style={{ fontSize: 11, color: "#64748b", margin: 0 }}>
                      {f.collection_id
                        ? <>Nutzt die Auth der Sammlung <strong style={{ color: "#94a3b8" }}>{sammlungen.find(c => c.id === f.collection_id)?.name}</strong>.</>
                        : "Ohne Sammlung bedeutet das: keine Authentifizierung."}
                    </p>
                  )}
                  <AuthEditor authType={f.auth_type} authConfig={f.auth_config || {}} onChange={v => set("auth_config", v)} />
                </div>
              )}
              {reiter === "daten" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  <div>
                    <label style={lS}>Datenpfad in der Antwort</label>
                    <input style={{ ...iS, fontFamily: "monospace" }} value={f.data_path || ""} onChange={e => set("data_path", e.target.value)}
                      placeholder='z.B. "data", "results.items"' />
                    <p style={{ fontSize: 10, color: "#475569", marginTop: 4 }}>Wo die Liste in der Antwort steckt. Leer lassen, wenn die Antwort direkt ein Array ist.</p>
                  </div>
                  <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                    <input type="checkbox" checked={!!f.flatten} onChange={e => set("flatten", e.target.checked ? 1 : 0)} />
                    <span style={{ fontSize: 12, color: "#94a3b8" }}>Verschachtelte Objekte flach machen</span>
                  </label>
                  <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                    <input type="checkbox" checked={!!f.store_response} onChange={e => set("store_response", e.target.checked ? 1 : 0)} />
                    <span style={{ fontSize: 12, color: "#94a3b8" }}>Antwortkörper im Verlauf speichern</span>
                  </label>
                  <p style={{ fontSize: 10, color: "#475569", margin: 0 }}>
                    Standardmäßig merkt sich der Verlauf nur Status, Dauer und Größe – Antworten können personenbezogene Daten enthalten.
                  </p>
                </div>
              )}
            </div>

            {fehler && (
              <p style={{ fontSize: 12, color: "#f87171", marginTop: 12, padding: "8px 12px", backgroundColor: "rgba(248,113,113,0.08)", borderRadius: 6 }}>{fehler}</p>
            )}
          </div>

          {/* Antwort */}
          <div style={{ backgroundColor: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 10, overflow: "hidden" }}>
            <AntwortAnsicht antwort={antwort} aufDatenpfad={(pfad) => { set("data_path", pfad); setReiter("daten"); }} />
          </div>
        </div>
      </div>

      {/* Dialoge */}
      {dialog === "sammlung" && (
        <SammlungsDialog initial={sammlungEdit} projectId={projectId}
          onSaved={() => { setDialog(null); laden(); }} onClose={() => setDialog(null)} />
      )}
      {dialog === "umgebung" && (
        <UmgebungsDialog umgebungen={umgebungen} projectId={projectId}
          onChanged={laden} onClose={() => setDialog(null)} />
      )}
      {dialog === "verlauf" && (
        <Dialog titel="Verlauf" onClose={() => setDialog(null)} breit>
          <VerlaufsListe eintraege={verlauf} canEdit={canEdit} onLaden={verlaufEintragLaden}
            onLeeren={async () => {
              if (!window.confirm("Gesamten Verlauf dieses Projekts löschen?")) return;
              await api.delete(`${BASE}/history`, { params: p });
              verlaufLaden();
            }} />
        </Dialog>
      )}
    </div>
  );
}

function RequestZeile({ r, aktiv, onClick, onDelete }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4, borderRadius: 5, backgroundColor: aktiv ? `${C}14` : "transparent" }}>
      <button onClick={onClick}
        style={{ display: "flex", alignItems: "center", gap: 6, flex: 1, minWidth: 0, padding: "4px 6px", background: "none", border: "none", cursor: "pointer", textAlign: "left" }}>
        <span style={{ fontSize: 8, fontWeight: 700, fontFamily: "monospace", flex: "0 0 34px", color: METHOD_COLOR[r.method] || "#94a3b8" }}>{r.method}</span>
        <span style={{ fontSize: 11, color: aktiv ? C : "#94a3b8", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.name}</span>
      </button>
      {onDelete && (
        <button onClick={onDelete} title="Request löschen"
          style={{ color: "#475569", background: "none", border: "none", cursor: "pointer", padding: 2, flexShrink: 0 }}><Trash2 size={10} /></button>
      )}
    </div>
  );
}

export default ApiStudioPanel;
export { ApiStudioPanel };
