import { useState, useEffect, useCallback, useRef } from "react";
import { BookOpen, CheckCircle, Database, Loader2, Pencil, Plus, RefreshCw, Sparkles, Trash2, Upload, X, XCircle, ChevronDown, ChevronUp, Search } from "lucide-react";
import api from "../api/client";
import { S } from "./dashboard/constants";
import DatabaseAnalyzer from "./DatabaseAnalyzer";
import AiDatasetWizard from "./AiDatasetWizard";
import SchemaCatalog from "./SchemaCatalog";

const DEFAULT_PORTS = { mssql: 1433, mysql: 3306, postgresql: 5432 };
const ACCESS_COLOR = "#fce499";

// ─── Connection Form ──────────────────────────────────────────────────────────
function ConnectionForm({ initial, projectId, onSaved, onCancel }) {
  const [form, setForm] = useState(initial || { name: "", db_type: "mssql", host: "", port: 1433, database: "", username: "", password: "" });
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const set = (k, v) => setForm((f) => { const u = { ...f, [k]: v }; if (k === "db_type") u.port = DEFAULT_PORTS[v]; return u; });
  const inputStyle = { backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, color: S.textBright, fontSize: 12, padding: "6px 10px", outline: "none", width: "100%" };
  const labelStyle = { fontSize: 10, color: S.textDim, display: "block", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.06em" };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (initial?.id) await api.put(`/api/connections/${initial.id}`, { ...form, project_id: projectId });
      else await api.post("/api/connections/", { ...form, project_id: projectId });
      onSaved();
    } finally { setSaving(false); }
  };

  const handleTest = async () => {
    setTesting(true); setTestResult(null);
    try {
      const { data } = await api.post("/api/connections/test", { ...form, id: initial?.id || null });
      setTestResult(data);
    } catch (e) {
      setTestResult({ success: false, message: e.response?.data?.detail || e.message });
    } finally { setTesting(false); }
  };

  return (
    <div style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`, borderRadius: 8, padding: 20, marginBottom: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: S.textBright }}>{initial ? "Verbindung bearbeiten" : "Neue Verbindung"}</span>
        <button onClick={onCancel} style={{ color: S.textDim, background: "none", border: "none", cursor: "pointer" }}><X size={14} /></button>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
        <div style={{ gridColumn: "1/-1" }}>
          <label style={labelStyle}>Name</label>
          <input style={inputStyle} value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Meine Verbindung" />
        </div>
        <div>
          <label style={labelStyle}>Datenbank-Typ</label>
          <select style={inputStyle} value={form.db_type} onChange={(e) => set("db_type", e.target.value)}>
            <option value="mssql">SQL Server (MSSQL)</option>
            <option value="mysql">MySQL / MariaDB</option>
            <option value="postgresql">PostgreSQL</option>
          </select>
        </div>
        <div>
          <label style={labelStyle}>Port</label>
          <input style={inputStyle} type="number" value={form.port} onChange={(e) => set("port", parseInt(e.target.value))} />
        </div>
        <div>
          <label style={labelStyle}>Host / Server</label>
          <input style={inputStyle} value={form.host} onChange={(e) => set("host", e.target.value)} placeholder="localhost" />
        </div>
        <div>
          <label style={labelStyle}>Datenbank</label>
          <input style={inputStyle} value={form.database} onChange={(e) => set("database", e.target.value)} placeholder="datenbankname" />
        </div>
        <div>
          <label style={labelStyle}>Benutzername</label>
          <input style={inputStyle} value={form.username} onChange={(e) => set("username", e.target.value)} />
        </div>
        <div>
          <label style={labelStyle}>Passwort</label>
          <input style={inputStyle} type="password" value={form.password} onChange={(e) => set("password", e.target.value)} placeholder={initial ? "leer lassen = unverändert" : ""} />
        </div>
      </div>
      {testResult && (
        <div style={{ padding: "8px 12px", borderRadius: 5, marginBottom: 12, fontSize: 11,
          backgroundColor: testResult.success ? "rgba(110,231,183,0.08)" : "rgba(224,112,112,0.08)",
          color: testResult.success ? "#6ee7b7" : "#e07070",
          border: `1px solid ${testResult.success ? "rgba(110,231,183,0.25)" : "rgba(224,112,112,0.25)"}` }}>
          {testResult.success ? "✓ Verbindung erfolgreich" : `✗ ${testResult.message}`}
        </div>
      )}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button onClick={handleTest} disabled={testing || !form.host || !form.database} className="btn-ghost text-xs">
          {testing ? <Loader2 size={12} className="animate-spin" /> : null} Testen
        </button>
        <button onClick={handleSave} disabled={saving || !form.name || !form.host || !form.database} className="btn-primary text-xs">
          {saving ? <Loader2 size={12} className="animate-spin" /> : null} Speichern
        </button>
      </div>
    </div>
  );
}

// ─── Import Connection Modal ──────────────────────────────────────────────────
function ImportConnectionModal({ projectId, onDone, onCancel }) {
  const [connections, setConnections] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/api/connections/").then(({ data }) => { setConnections(data); setLoading(false); });
  }, []);

  const importConn = async (conn) => {
    await api.post("/api/connections/", {
      name: conn.name, db_type: conn.db_type, host: conn.host,
      port: conn.port, database: conn.database, username: conn.username,
      password: "", project_id: projectId,
    });
    onDone();
  };

  const typeLabel = { mssql: "SQL Server", mysql: "MySQL", postgresql: "PostgreSQL" };
  const typeColor = { mssql: "#93c5fd", mysql: "#6ee7b7", postgresql: "#f9a8d4" };

  return (
    <div style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`, borderRadius: 8, padding: 20, marginBottom: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 12 }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: S.textBright }}>Verbindung importieren</span>
        <button onClick={onCancel} style={{ color: S.textDim, background: "none", border: "none", cursor: "pointer" }}><X size={14} /></button>
      </div>
      {loading ? <Loader2 size={16} className="animate-spin" /> : connections.filter(c => c.project_id !== projectId).map((conn) => (
        <div key={conn.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px",
          borderRadius: 5, marginBottom: 4, border: `1px solid ${S.border}`, cursor: "pointer" }}
          onClick={() => importConn(conn)}
          onMouseEnter={e => e.currentTarget.style.borderColor = S.accent}
          onMouseLeave={e => e.currentTarget.style.borderColor = S.border}>
          <Database size={13} style={{ color: typeColor[conn.db_type], flexShrink: 0 }} />
          <span style={{ fontSize: 12, color: S.textBright, flex: 1 }}>{conn.name}</span>
          <span style={{ fontSize: 10, color: typeColor[conn.db_type], backgroundColor: "rgba(255,255,255,0.05)", padding: "1px 6px", borderRadius: 3 }}>{typeLabel[conn.db_type]}</span>
        </div>
      ))}
    </div>
  );
}

// ─── Access Import Section ────────────────────────────────────────────────────
function AccessImportSection({ projectId, canEdit, onDatasetCreated }) {
  const [open, setOpen] = useState(false);
  const [mdbAvailable, setMdbAvailable] = useState(null);
  const [mode, setMode] = useState("upload");
  const [step, setStep] = useState(1);
  const [serverPath, setServerPath] = useState("");
  const [uploadFile, setUploadFile] = useState(null);
  const [tmpPath, setTmpPath] = useState(null);
  const [tables, setTables] = useState([]);
  const [selectedTables, setSelectedTables] = useState([]); // Mehrfachauswahl
  const [preview, setPreview] = useState(null);
  const [previewTable, setPreviewTable] = useState(null);
  const [namePrefix, setNamePrefix] = useState("");
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importResults, setImportResults] = useState([]);
  const [error, setError] = useState("");
  const fileInputRef = useRef(null);

  useEffect(() => {
    api.get("/api/datasets/access/check-mdbtools")
      .then(({ data }) => setMdbAvailable(data.available))
      .catch(() => setMdbAvailable(false));
  }, []);

  const reset = () => {
    setStep(1); setTables([]); setSelectedTables([]); setPreview(null);
    setPreviewTable(null); setNamePrefix(""); setError(""); setImportResults([]);
    setUploadFile(null); setTmpPath(null); setServerPath("");
  };

  const loadTables = async () => {
    setLoading(true); setError("");
    try {
      let data;
      if (mode === "path") {
        ({ data } = await api.post("/api/datasets/access/tables-from-path", { path: serverPath }));
        setTmpPath(null);
      } else {
        const form = new FormData();
        form.append("file", uploadFile);
        // Kein Timeout im Browser – große Dateien können Minuten dauern
        ({ data } = await api.post("/api/datasets/access/tables-from-upload", form, {
          timeout: 0,  // kein axios-Timeout
        }));
        setTmpPath(data.tmp_token);
      }
      setTables(data.tables || []);
      setSelectedTables(data.tables || []);
      setNamePrefix(uploadFile?.name?.replace(/\.(mdb|accdb)$/i, "") || "");
      setStep(2);
    } catch (e) {
      const status = e.response?.status;
      const detail = e.response?.data?.detail || e.message || "Unbekannter Fehler";
      if (status === 413) {
        setError(`Datei zu groß für Upload. Bitte nutze den Serverpfad-Modus: Lege die Datei direkt auf dem Server ab und trage den Pfad ein.`);
      } else {
        setError(detail);
      }
    } finally { setLoading(false); }
  };

  const loadPreview = async (table) => {
    if (previewTable === table) { setPreview(null); setPreviewTable(null); return; }
    setPreviewTable(table); setPreview(null);
    const isUpload = mode !== "path";
    if (isUpload && !tmpPath) return;
    if (!isUpload && !serverPath) return;
    try {
      const payload = isUpload
        ? { tmp_token: tmpPath, table }
        : { path: serverPath, table };
      const { data } = await api.post("/api/datasets/access/preview", payload);
      setPreview(data);
    } catch { /* Preview optional */ }
  };

  const toggleTable = (t) => {
    setSelectedTables(prev =>
      prev.includes(t) ? prev.filter(x => x !== t) : [...prev, t]
    );
  };

  const doImport = async () => {
    if (!selectedTables.length) return;
    setImporting(true); setError("");
    const results = [];
    for (const table of selectedTables) {
      const dsName = namePrefix ? `${namePrefix} – ${table}` : table;
      try {
        const form = new FormData();
        form.append("name", dsName);
        form.append("table", table);
        if (projectId) form.append("project_id", projectId);
        if (mode === "path") form.append("server_path", serverPath);
        else if (tmpPath) form.append("tmp_token", tmpPath);
        else if (uploadFile) form.append("file", uploadFile);
        await api.post("/api/datasets/access/import", form);
        results.push({ table, name: dsName, ok: true });
      } catch (e) {
        results.push({ table, name: dsName, ok: false, error: e.response?.data?.detail || "Fehler" });
      }
    }
    setImportResults(results);
    setStep(3);
    setImporting(false);
    if (results.some(r => r.ok) && onDatasetCreated) onDatasetCreated();
  };

  const iS = { backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, color: S.textBright, fontSize: 11, padding: "5px 9px", outline: "none", width: "100%" };

  return (
    <div style={{ borderTop: `1px solid ${S.border}`, marginTop: 24, paddingTop: 16 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", marginBottom: open ? 16 : 0 }}
        onClick={() => setOpen(v => !v)}>
        <div style={{ width: 28, height: 28, borderRadius: 6, backgroundColor: `${ACCESS_COLOR}15`,
          display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <Database size={14} style={{ color: ACCESS_COLOR }} />
        </div>
        <div style={{ flex: 1 }}>
          <p style={{ fontSize: 12, fontWeight: 700, color: S.textBright, margin: 0 }}>Access Import</p>
          <p style={{ fontSize: 10, color: S.textDim, margin: 0 }}>Microsoft Access .mdb / .accdb als Dataset(s) importieren</p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {mdbAvailable === false && <span style={{ fontSize: 9, color: "#e07070", border: "1px solid rgba(224,112,112,0.3)", padding: "2px 7px", borderRadius: 3 }}>mdbtools fehlt</span>}
          {mdbAvailable === true && <span style={{ fontSize: 9, color: "#6ee7b7", border: "1px solid rgba(110,231,183,0.3)", padding: "2px 7px", borderRadius: 3 }}>bereit</span>}
          {open ? <ChevronUp size={14} style={{ color: S.textDim }} /> : <ChevronDown size={14} style={{ color: S.textDim }} />}
        </div>
      </div>

      {open && (
        <div style={{ backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 8, padding: 16 }}>

          {/* Schritt-Indikator */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
            {[{n:1,l:"Datei"},{n:2,l:"Tabellen"},{n:3,l:"Fertig"}].map((s, i, arr) => (
              <div key={s.n} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <div style={{ width: 20, height: 20, borderRadius: "50%", display: "flex", alignItems: "center",
                  justifyContent: "center", fontSize: 10, fontWeight: 700,
                  backgroundColor: step >= s.n ? ACCESS_COLOR : "rgba(255,255,255,0.08)",
                  color: step >= s.n ? "#000" : S.textDim }}>{s.n}</div>
                <span style={{ fontSize: 10, color: step >= s.n ? S.textBright : S.textDim, fontWeight: step === s.n ? 600 : 400 }}>{s.l}</span>
                {i < arr.length - 1 && <div style={{ width: 20, height: 1, backgroundColor: step > s.n ? ACCESS_COLOR : S.border }} />}
              </div>
            ))}
          </div>

          {/* Schritt 1: Datei */}
          {step === 1 && (
            <>
              <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
                {[{v:"upload",l:"Upload"},{v:"path",l:"Serverpfad"}].map(m => (
                  <button key={m.v} onClick={() => { setMode(m.v); setError(""); }}
                    style={{ flex: 1, padding: "6px 10px", borderRadius: 5, fontSize: 11, fontWeight: 600, cursor: "pointer",
                      backgroundColor: mode === m.v ? `${ACCESS_COLOR}20` : "transparent",
                      border: `1px solid ${mode === m.v ? ACCESS_COLOR : S.border}`,
                      color: mode === m.v ? ACCESS_COLOR : S.textDim }}>
                    {m.l}
                  </button>
                ))}
              </div>

              {mode === "upload" ? (
                <div onClick={() => fileInputRef.current?.click()}
                  style={{ border: `2px dashed ${uploadFile ? ACCESS_COLOR : S.border}`, borderRadius: 6,
                    padding: "20px", textAlign: "center", cursor: "pointer",
                    backgroundColor: uploadFile ? `${ACCESS_COLOR}06` : "transparent", marginBottom: 12 }}>
                  <input ref={fileInputRef} type="file" accept=".mdb,.accdb" style={{ display: "none" }}
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) { setUploadFile(f); setError(""); } }} />
                  {uploadFile ? (
                    <div>
                      <p style={{ fontSize: 12, fontWeight: 600, color: ACCESS_COLOR, margin: "0 0 4px" }}>{uploadFile.name}</p>
                      <p style={{ fontSize: 10, color: S.textDim, margin: 0 }}>{(uploadFile.size / 1024 / 1024).toFixed(1)} MB</p>
                    </div>
                  ) : (
                    <p style={{ fontSize: 12, color: S.textDim, margin: 0 }}>Klicken oder .mdb / .accdb hierher ziehen</p>
                  )}
                </div>
              ) : (
                <div style={{ marginBottom: 12 }}>
                  <label style={{ fontSize: 10, color: S.textDim, display: "block", marginBottom: 4 }}>Dateipfad auf dem Server</label>
                  <input style={iS} value={serverPath} onChange={(e) => setServerPath(e.target.value)} placeholder="/data/datenbank.accdb" />
                </div>
              )}
              {error && <p style={{ fontSize: 11, color: "#e07070", margin: "0 0 10px" }}>⚠ {error}</p>}
              <button onClick={loadTables}
                disabled={loading || mdbAvailable === false || (mode === "upload" && !uploadFile) || (mode === "path" && !serverPath.trim())}
                style={{ width: "100%", padding: "8px", borderRadius: 5, fontSize: 12, fontWeight: 700, cursor: "pointer",
                  backgroundColor: ACCESS_COLOR, color: "#000", border: "none", opacity: loading ? 0.6 : 1,
                  display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
                {loading
                  ? <><Loader2 size={13} className="animate-spin" /> {mode === "upload" && uploadFile?.size > 100*1024*1024 ? "Lade & verarbeite große Datei…" : "Lese Tabellen…"}</>
                  : "Tabellen laden"}
              </button>
            </>
          )}

          {/* Schritt 2: Tabellen auswählen */}
          {step === 2 && (
            <>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                <span style={{ fontSize: 11, color: S.textDim }}>{tables.length} Tabellen · {selectedTables.length} ausgewählt</span>
                <div style={{ display: "flex", gap: 6 }}>
                  <button onClick={() => setSelectedTables([...tables])} style={{ fontSize: 10, color: S.accent, background: "none", border: "none", cursor: "pointer" }}>Alle</button>
                  <button onClick={() => setSelectedTables([])} style={{ fontSize: 10, color: S.textDim, background: "none", border: "none", cursor: "pointer" }}>Keine</button>
                </div>
              </div>

              <div style={{ maxHeight: 220, overflowY: "auto", scrollbarWidth: "thin", marginBottom: 12, border: `1px solid ${S.border}`, borderRadius: 5 }}>
                {tables.map((t) => (
                  <div key={t} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div onClick={() => toggleTable(t)}
                      style={{ display: "flex", alignItems: "center", gap: 8, flex: 1,
                        padding: "7px 10px", cursor: "pointer",
                        backgroundColor: selectedTables.includes(t) ? `${ACCESS_COLOR}08` : "transparent",
                        borderBottom: `1px solid ${S.border}` }}>
                      <div style={{ width: 14, height: 14, borderRadius: 3, border: `2px solid ${selectedTables.includes(t) ? ACCESS_COLOR : S.border}`,
                        backgroundColor: selectedTables.includes(t) ? ACCESS_COLOR : "transparent",
                        display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                        {selectedTables.includes(t) && <span style={{ fontSize: 9, color: "#000", fontWeight: 900, lineHeight: 1 }}>✓</span>}
                      </div>
                      <span style={{ fontSize: 11, fontFamily: "monospace", color: selectedTables.includes(t) ? ACCESS_COLOR : S.textMain }}>{t}</span>
                    </div>
                    <button onClick={() => loadPreview(t)}
                      style={{ padding: "0 10px", fontSize: 10, color: previewTable === t ? S.accent : S.textDim,
                        background: "none", border: "none", cursor: "pointer", whiteSpace: "nowrap" }}>
                      {previewTable === t ? "▲ schließen" : "▼ Vorschau"}
                    </button>
                  </div>
                ))}
              </div>

              {/* Vorschau */}
              {preview && previewTable && (
                <div style={{ marginBottom: 12, backgroundColor: "rgba(0,0,0,0.2)", borderRadius: 5, padding: 10, overflow: "auto", maxHeight: 140, scrollbarWidth: "thin" }}>
                  <p style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", color: ACCESS_COLOR, margin: "0 0 6px" }}>{previewTable} · {preview.total_columns} Spalten</p>
                  <table style={{ fontSize: 10, borderCollapse: "collapse", minWidth: "max-content" }}>
                    <thead><tr>{preview.columns?.map(c => <th key={c} style={{ textAlign: "left", padding: "2px 8px", color: S.textDim, borderBottom: `1px solid ${S.border}`, whiteSpace: "nowrap" }}>{c}</th>)}</tr></thead>
                    <tbody>{preview.rows?.map((row, i) => <tr key={i}>{preview.columns?.map(c => <td key={c} style={{ padding: "2px 8px", color: S.textMain, whiteSpace: "nowrap" }}>{String(row[c] ?? "")}</td>)}</tr>)}</tbody>
                  </table>
                </div>
              )}

              {/* Dataset-Namenspräfix */}
              <div style={{ marginBottom: 12 }}>
                <label style={{ fontSize: 10, color: S.textDim, display: "block", marginBottom: 4 }}>
                  Dataset-Präfix <span style={{ color: S.textDim, fontStyle: "italic" }}>(optional – wird vor Tabellennamen gesetzt)</span>
                </label>
                <input style={iS} value={namePrefix} onChange={e => setNamePrefix(e.target.value)} placeholder="z.B. MeineDB → MeineDB – Tabelle1" />
              </div>

              {error && <p style={{ fontSize: 11, color: "#e07070", margin: "0 0 10px" }}>⚠ {error}</p>}
              <div style={{ display: "flex", gap: 8 }}>
                <button onClick={reset} style={{ flex: 1, padding: "7px", borderRadius: 5, fontSize: 11, fontWeight: 600, cursor: "pointer", backgroundColor: "transparent", border: `1px solid ${S.border}`, color: S.textDim }}>Zurück</button>
                <button onClick={doImport} disabled={!selectedTables.length || importing}
                  style={{ flex: 2, padding: "7px", borderRadius: 5, fontSize: 12, fontWeight: 700, cursor: "pointer",
                    backgroundColor: selectedTables.length ? ACCESS_COLOR : S.bgEl,
                    color: selectedTables.length ? "#000" : S.textDim, border: "none",
                    opacity: importing ? 0.7 : 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
                  {importing
                    ? <><Loader2 size={13} className="animate-spin" /> Importiere…</>
                    : `${selectedTables.length} Tabelle${selectedTables.length !== 1 ? "n" : ""} importieren`}
                </button>
              </div>
            </>
          )}

          {/* Schritt 3: Ergebnis */}
          {step === 3 && (
            <>
              <div style={{ marginBottom: 14 }}>
                {importResults.map(r => (
                  <div key={r.table} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 10px",
                    borderRadius: 4, marginBottom: 4,
                    backgroundColor: r.ok ? "rgba(110,231,183,0.06)" : "rgba(224,112,112,0.06)",
                    border: `1px solid ${r.ok ? "rgba(110,231,183,0.2)" : "rgba(224,112,112,0.2)"}` }}>
                    <span style={{ fontSize: 12, color: r.ok ? "#6ee7b7" : "#e07070" }}>{r.ok ? "✓" : "✗"}</span>
                    <span style={{ fontSize: 11, color: S.textBright, flex: 1, fontFamily: "monospace" }}>{r.name}</span>
                    {!r.ok && <span style={{ fontSize: 10, color: "#e07070" }}>{r.error}</span>}
                  </div>
                ))}
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button onClick={reset}
                  style={{ flex: 1, padding: "7px", borderRadius: 5, fontSize: 11, fontWeight: 600, cursor: "pointer",
                    border: `1px solid ${ACCESS_COLOR}`, backgroundColor: "transparent", color: ACCESS_COLOR }}>
                  Weiteren Import
                </button>
                <button onClick={() => setOpen(false)}
                  style={{ flex: 1, padding: "7px", borderRadius: 5, fontSize: 11, fontWeight: 600, cursor: "pointer",
                    border: `1px solid ${S.border}`, backgroundColor: "transparent", color: S.textDim }}>
                  Schließen
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ─── New Connection Tiles ─────────────────────────────────────────────────────
function NewConnTile({ label, sub, icon: Icon, onClick }) {
  const [hovered, setHovered] = useState(false);
  return (
    <div onClick={onClick} onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
      className="card transition-all duration-150 cursor-pointer flex flex-col items-center justify-center gap-3 min-h-[116px]"
      style={{
        borderColor: hovered ? "rgba(110,231,170,0.6)" : "rgba(110,231,170,0.25)",
        backgroundColor: hovered ? "rgba(110,231,170,0.07)" : "rgba(110,231,170,0.03)",
        borderStyle: "dashed",
      }}>
      <div className="rounded-full p-2" style={{ backgroundColor: hovered ? "rgba(110,231,170,0.15)" : "rgba(110,231,170,0.07)" }}>
        <Icon size={20} style={{ color: hovered ? "#6ee7aa" : "#4ade80" }} />
      </div>
      <div className="text-center">
        <p className="text-sm font-medium" style={{ color: hovered ? "#6ee7aa" : "#4ade80" }}>{label}</p>
        <p className="text-xs mt-0.5" style={{ color: "rgba(110,231,170,0.5)" }}>{sub}</p>
      </div>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────
export default function DbConnectionManager({ projectId = null, canEdit = true, onDatasetCreated }) {
  const [connections, setConnections] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingConn, setEditingConn] = useState(null);
  const [showImport, setShowImport] = useState(false);
  const [testResults, setTestResults] = useState({});

  const [analyzingConn, setAnalyzingConn]   = useState(null);
  const [aiWizardConn, setAiWizardConn]     = useState(null);
  const [catalogConn, setCatalogConn]       = useState(null);
  const [rebuildingCache, setRebuildingCache] = useState({});  // conn_id → bool

  const rebuildCache = async (conn) => {
    const prevCachedAt = conn.schema_cached_at;   // remember old value
    setRebuildingCache(r => ({ ...r, [conn.id]: true }));
    try {
      await api.post(`/api/connections/${conn.id}/rebuild-schema-cache`);
    } catch { /* background task still runs */ }

    // Poll every 2s until schema_cached_at has changed (max 120s)
    const deadline = Date.now() + 120_000;
    const poll = async () => {
      if (Date.now() > deadline) { setRebuildingCache(r => ({ ...r, [conn.id]: false })); return; }
      const params = projectId != null ? `?project_id=${projectId}` : "";
      const { data } = await api.get(`/api/connections/${params}`);
      const fresh = data.find(c => c.id === conn.id);
      const changed = fresh?.schema_cached_at && fresh.schema_cached_at !== prevCachedAt;
      setConnections(data);
      if (changed) {
        setRebuildingCache(r => ({ ...r, [conn.id]: false }));
      } else {
        setTimeout(poll, 2000);
      }
    };
    setTimeout(poll, 2000);
  };

  const cacheAge = (isoStr) => {
    if (!isoStr) return null;
    const mins = Math.round((Date.now() - new Date(isoStr)) / 60000);
    if (mins < 1)   return "gerade eben";
    if (mins < 60)  return `vor ${mins} Min`;
    const hrs = Math.round(mins / 60);
    if (hrs < 24)   return `vor ${hrs} Std`;
    return `vor ${Math.round(hrs / 24)} Tagen`;
  };

  const load = useCallback(async () => {
    const params = projectId != null ? `?project_id=${projectId}` : "";
    const { data } = await api.get(`/api/connections/${params}`);
    setConnections(data);
    setLoading(false);
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  const deleteConn = async (id) => {
    if (!confirm("Verbindung wirklich löschen?")) return;
    await api.delete(`/api/connections/${id}`); load();
  };

  const testConn = async (conn) => {
    setTestResults((p) => ({ ...p, [conn.id]: "loading" }));
    const { data } = await api.get(`/api/connections/${conn.id}/test`);
    setTestResults((p) => ({ ...p, [conn.id]: data.success ? "ok" : "error" }));
  };

  const typeLabel = { mssql: "SQL Server", mysql: "MySQL", postgresql: "PostgreSQL" };
  const typeColor = { mssql: "#93c5fd", mysql: "#6ee7b7", postgresql: "#f9a8d4" };

  return (
    <div>
      {(showForm && !editingConn) && (
        <ConnectionForm projectId={projectId} onSaved={() => { setShowForm(false); load(); }} onCancel={() => setShowForm(false)} />
      )}
      {editingConn && (
        <ConnectionForm initial={editingConn} projectId={projectId}
          onSaved={() => { setEditingConn(null); load(); }}
          onCancel={() => setEditingConn(null)} />
      )}
      {showImport && (
        <ImportConnectionModal projectId={projectId}
          onDone={() => { setShowImport(false); load(); }}
          onCancel={() => setShowImport(false)} />
      )}

      {analyzingConn && (
        <DatabaseAnalyzer connection={analyzingConn} projectId={projectId}
          onClose={() => setAnalyzingConn(null)}
          onDatasetsImported={() => { setAnalyzingConn(null); onDatasetCreated?.(); }} />
      )}

      {aiWizardConn && (
        <AiDatasetWizard connection={aiWizardConn} projectId={projectId}
          onDone={() => { onDatasetCreated?.(); }}
          onClose={() => setAiWizardConn(null)} />
      )}

      {catalogConn && (
        <div style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.6)", zIndex: 1000, display: "flex", alignItems: "flex-start", justifyContent: "center", paddingTop: 60 }}>
          <div style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`, borderRadius: 10, width: "min(860px, 95vw)", maxHeight: "80vh", display: "flex", flexDirection: "column", overflow: "hidden" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px", borderBottom: `1px solid ${S.border}` }}>
              <span style={{ fontWeight: 700, color: S.textBright, fontSize: 13 }}>
                Schema-Katalog — {catalogConn.name}
              </span>
              <button onClick={() => setCatalogConn(null)} style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer" }}>
                <X size={14} />
              </button>
            </div>
            <div style={{ overflowY: "auto", padding: 16, flex: 1 }}>
              <SchemaCatalog connectionId={catalogConn.id} />
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center h-24" style={{ color: S.textDim }}>
          <Loader2 className="animate-spin mr-2" size={16} />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {canEdit && <NewConnTile label="Neue Verbindung" sub="SQL Server, MySQL, PostgreSQL" icon={Plus}
            onClick={() => { setShowForm(true); setEditingConn(null); }} />}
          {canEdit && <NewConnTile label="Verbindung importieren" sub="Aus anderem Projekt übernehmen" icon={Upload}
            onClick={() => setShowImport(true)} />}
          {connections.map((conn) => (
            <div key={conn.id} className="card group transition-all" style={{ borderColor: S.border }}>
              <div className="flex items-start justify-between">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate" style={{ color: S.textBright }}>{conn.name}</p>
                  <p className="text-xs font-mono mt-0.5 truncate" style={{ color: S.textDim }}>
                    {conn.host}:{conn.port}/{conn.database}
                  </p>
                </div>
                <div className="flex items-center gap-1 ml-2 shrink-0">
                  <button onClick={() => setAnalyzingConn(conn)} className="text-xs px-2 py-0.5 rounded"
                    style={{ backgroundColor: S.bgEl, color: "#a78bfa", border: `1px solid rgba(167,139,250,0.3)` }}
                    title="Schema analysieren">
                    <Search size={10} />
                  </button>
                  {conn.schema_cached_at && (
                    <button onClick={() => setCatalogConn(conn)} className="text-xs px-2 py-0.5 rounded"
                      style={{ backgroundColor: S.bgEl, color: "#34d399", border: `1px solid rgba(52,211,153,0.3)` }}
                      title="Schema-Katalog">
                      <BookOpen size={10} />
                    </button>
                  )}
                  <button onClick={() => setAiWizardConn(conn)} className="text-xs px-2 py-0.5 rounded"
                    style={{ backgroundColor: S.bgEl, color: "#fce499", border: `1px solid rgba(252,228,153,0.3)` }}
                    title="KI-Dataset-Assistent">
                    <Sparkles size={10} />
                  </button>
                  <button onClick={() => testConn(conn)} className="text-xs px-2 py-0.5 rounded"
                    style={{ backgroundColor: S.bgEl, color: S.textDim, border: `1px solid ${S.border}` }} title="Verbindung testen">
                    {testResults[conn.id] === "loading" ? <Loader2 size={10} className="animate-spin" />
                      : testResults[conn.id] === "ok" ? <CheckCircle size={10} style={{ color: "#6ee7b7" }} />
                      : testResults[conn.id] === "error" ? <XCircle size={10} style={{ color: "#e07070" }} />
                      : "Test"}
                  </button>
                  {canEdit && (<>
                    <button onClick={() => setEditingConn(conn)}
                      className="p-1 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                      style={{ color: S.textDim }}
                      onMouseEnter={(e) => e.currentTarget.style.color = S.accent}
                      onMouseLeave={(e) => e.currentTarget.style.color = S.textDim}>
                      <Pencil size={13} />
                    </button>
                    <button onClick={() => deleteConn(conn.id)}
                      className="p-1 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                      style={{ color: S.textDim }}
                      onMouseEnter={(e) => e.currentTarget.style.color = "#e07070"}
                      onMouseLeave={(e) => e.currentTarget.style.color = S.textDim}>
                      <Trash2 size={13} />
                    </button>
                  </>)}
                </div>
              </div>
              <div className="flex items-center gap-2 mt-3">
                <span className="text-xs px-2 py-0.5 rounded font-mono"
                  style={{ backgroundColor: "rgba(255,255,255,0.05)", color: typeColor[conn.db_type] }}>
                  {typeLabel[conn.db_type]}
                </span>
                <span className="text-xs" style={{ color: S.textDim }}>{conn.username}</span>
                <div className="flex items-center gap-1 ml-auto">
                  {rebuildingCache[conn.id] ? (
                    <span style={{ fontSize: 9, color: "rgba(252,228,153,0.7)" }}>
                      Schema wird geladen…
                    </span>
                  ) : conn.schema_cached_at ? (
                    <span style={{ fontSize: 9, color: "rgba(252,228,153,0.5)" }} title={`${conn.schema_table_count} Tabellen gecacht`}>
                      ✦ {conn.schema_table_count}T · {cacheAge(conn.schema_cached_at)}
                    </span>
                  ) : (
                    <span style={{ fontSize: 9, color: S.textDim }}>kein Schema-Cache</span>
                  )}
                  <button onClick={() => rebuildCache(conn)} disabled={rebuildingCache[conn.id]}
                    title="Schema-Cache neu aufbauen"
                    style={{ background: "none", border: "none", color: rebuildingCache[conn.id] ? "rgba(252,228,153,0.6)" : S.textDim, cursor: rebuildingCache[conn.id] ? "wait" : "pointer", padding: "1px 2px", display: "flex" }}>
                    <RefreshCw size={9} className={rebuildingCache[conn.id] ? "animate-spin" : ""} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Access Import – als aufklappbarer Abschnitt unter den Verbindungen */}
      <AccessImportSection
        projectId={projectId}
        canEdit={canEdit}
        onDatasetCreated={onDatasetCreated}
      />
    </div>
  );
}
