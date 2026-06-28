import { useState, useEffect, useRef } from "react";
import { CheckCircle2, Database, Loader2, Server, Upload, X } from "lucide-react";
import api from "../../../api/client";
import { S } from "../constants";

const ACCESS_COLOR = "#fce499"; // passt zum Design-Akzent

function AccessImportPanel({ projectId, canEdit, onDatasetCreated }) {
  const [mdbAvailable, setMdbAvailable] = useState(null);
  const [mode, setMode] = useState("upload");
  const [step, setStep] = useState(1);
  const [serverPath, setServerPath] = useState("");
  const [uploadFile, setUploadFile] = useState(null);
  const [tmpPath, setTmpPath] = useState(null);
  const [tables, setTables] = useState([]);
  const [selectedTable, setSelectedTable] = useState("");
  const [preview, setPreview] = useState(null);
  const [datasetName, setDatasetName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const fileInputRef = useRef(null);

  useEffect(() => {
    api.get("/api/datasets/access/check-mdbtools")
      .then(({ data }) => setMdbAvailable(data.available))
      .catch(() => setMdbAvailable(false));
  }, []);

  const reset = () => {
    setStep(1); setTables([]); setSelectedTable(""); setPreview(null);
    setDatasetName(""); setError(""); setSuccess(""); setUploadFile(null);
    setTmpPath(null); setServerPath("");
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
        ({ data } = await api.post("/api/datasets/access/tables-from-upload", form));
        setTmpPath(data.tmp_token);
      }
      setTables(data.tables || []);
      if (data.tables?.length === 1) setSelectedTable(data.tables[0]);
      setDatasetName(uploadFile?.name?.replace(/\.(mdb|accdb)$/i, "") || "Access Import");
      setStep(2);
    } catch (e) {
      setError(e.response?.data?.detail || "Fehler beim Lesen der Tabellenliste");
    } finally { setLoading(false); }
  };

  const loadPreview = async (table) => {
    setSelectedTable(table); setPreview(null);
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

  const doImport = async () => {
    setLoading(true); setError(""); setSuccess("");
    try {
      const form = new FormData();
      form.append("name", datasetName || selectedTable);
      form.append("table", selectedTable);
      if (projectId) form.append("project_id", projectId);
      if (mode === "path") {
        form.append("server_path", serverPath);
      } else if (tmpPath) {
        form.append("tmp_token", tmpPath);
      } else if (uploadFile) {
        form.append("file", uploadFile);
      }
      await api.post("/api/datasets/access/import", form);
      setSuccess(`Tabelle "${selectedTable}" erfolgreich importiert`);
      setStep(3);
      if (onDatasetCreated) onDatasetCreated();
    } catch (e) {
      setError(e.response?.data?.detail || "Import fehlgeschlagen");
    } finally { setLoading(false); }
  };

  const iS = { width: "100%", backgroundColor: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 6, color: "#f1f5f9", fontSize: 13, padding: "8px 12px", outline: "none", boxSizing: "border-box" };
  const lS = { fontSize: 11, color: "#94a3b8", display: "block", marginBottom: 5, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" };

  return (
    <div style={{ maxWidth: 680, margin: "0 auto", padding: "24px 0" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
        <div style={{ width: 38, height: 38, borderRadius: 8, backgroundColor: `${ACCESS_COLOR}18`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <Database size={18} style={{ color: ACCESS_COLOR }} />
        </div>
        <div>
          <h2 style={{ fontSize: 15, fontWeight: 700, color: "#f1f5f9", margin: 0 }}>Access Import</h2>
          <p style={{ fontSize: 12, color: "#64748b", margin: 0 }}>Microsoft Access .mdb / .accdb als Dataset importieren</p>
        </div>
        {mdbAvailable === false && <span style={{ marginLeft: "auto", fontSize: 11, color: "#f87171", backgroundColor: "rgba(248,113,113,0.1)", padding: "4px 10px", borderRadius: 4, border: "1px solid rgba(248,113,113,0.3)" }}>mdbtools nicht installiert</span>}
        {mdbAvailable === true && <span style={{ marginLeft: "auto", fontSize: 11, color: "#6ee7b7", backgroundColor: "rgba(110,231,183,0.08)", padding: "4px 10px", borderRadius: 4, border: "1px solid rgba(110,231,183,0.2)" }}>mdbtools verfügbar</span>}
      </div>

      {mdbAvailable === false && (
        <div style={{ backgroundColor: "rgba(248,113,113,0.06)", border: "1px solid rgba(248,113,113,0.2)", borderRadius: 8, padding: "14px 18px", marginBottom: 20 }}>
          <p style={{ fontSize: 13, color: "#fca5a5", fontWeight: 600, marginBottom: 4 }}>mdbtools nicht gefunden</p>
          <p style={{ fontSize: 12, color: "#94a3b8", lineHeight: 1.6, margin: 0 }}>Füge <code style={{ backgroundColor: "rgba(0,0,0,0.3)", padding: "2px 6px", borderRadius: 3 }}>mdbtools \</code> ins Dockerfile ein und baue neu.</p>
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 24 }}>
        {[{n:1,l:"Datei"},{n:2,l:"Tabelle"},{n:3,l:"Fertig"}].map((s, i, arr) => (
          <div key={s.n} style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <div style={{ width: 24, height: 24, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, backgroundColor: step >= s.n ? ACCESS_COLOR : "rgba(255,255,255,0.08)", color: step >= s.n ? "#000" : "#64748b" }}>{s.n}</div>
              <span style={{ fontSize: 12, color: step >= s.n ? "#f1f5f9" : "#64748b", fontWeight: step === s.n ? 600 : 400 }}>{s.l}</span>
            </div>
            {i < arr.length - 1 && <div style={{ width: 24, height: 1, backgroundColor: step > s.n ? ACCESS_COLOR : "rgba(255,255,255,0.1)" }} />}
          </div>
        ))}
      </div>

      {step === 1 && (
        <div style={{ backgroundColor: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 10, padding: 20 }}>
          <div style={{ display: "flex", gap: 6, marginBottom: 20 }}>
            {[{v:"upload",l:"Datei hochladen"},{v:"path",l:"Serverpfad"}].map(m => (
              <button key={m.v} onClick={() => { setMode(m.v); setError(""); }}
                style={{ flex: 1, padding: "8px 14px", borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: "pointer", backgroundColor: mode === m.v ? `${ACCESS_COLOR}20` : "transparent", border: `1px solid ${mode === m.v ? ACCESS_COLOR : "rgba(255,255,255,0.1)"}`, color: mode === m.v ? ACCESS_COLOR : "#64748b" }}>
                {m.l}
              </button>
            ))}
          </div>
          {mode === "upload" ? (
            <div>
              <label style={lS}>Access-Datei (.mdb / .accdb)</label>
              <div onClick={() => fileInputRef.current?.click()}
                style={{ border: `2px dashed ${uploadFile ? ACCESS_COLOR : "rgba(255,255,255,0.12)"}`, borderRadius: 8, padding: "28px 20px", textAlign: "center", cursor: "pointer", backgroundColor: uploadFile ? `${ACCESS_COLOR}08` : "transparent" }}>
                <input ref={fileInputRef} type="file" accept=".mdb,.accdb" style={{ display: "none" }}
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) { setUploadFile(f); setError(""); } }} />
                {uploadFile ? (
                  <div>
                    <p style={{ fontSize: 13, fontWeight: 600, color: ACCESS_COLOR, marginBottom: 4 }}>{uploadFile.name}</p>
                    <p style={{ fontSize: 11, color: "#64748b" }}>{(uploadFile.size / 1024 / 1024).toFixed(1)} MB</p>
                    {uploadFile.size > 200 * 1024 * 1024 && <p style={{ fontSize: 11, color: "#fbbf24", marginTop: 6 }}>Grosse Datei - Import kann einige Minuten dauern</p>}
                  </div>
                ) : (
                  <div>
                    <Upload size={24} style={{ color: "#475569", marginBottom: 8 }} />
                    <p style={{ fontSize: 13, color: "#64748b", marginBottom: 4 }}>Klicken oder Datei hierher ziehen</p>
                    <p style={{ fontSize: 11, color: "#374151" }}>.mdb / .accdb</p>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div>
              <label style={lS}>Dateipfad auf dem Server</label>
              <input style={iS} value={serverPath} onChange={(e) => setServerPath(e.target.value)} placeholder="/data/datenbank.accdb" />
              <p style={{ fontSize: 11, color: "#475569", marginTop: 6 }}>Absoluter Pfad zur Datei auf dem Server. Fuer grosse Dateien (500MB+) empfohlen.</p>
            </div>
          )}
          {error && <p style={{ fontSize: 12, color: "#f87171", marginTop: 12, padding: "8px 12px", backgroundColor: "rgba(248,113,113,0.08)", borderRadius: 6 }}>{error}</p>}
          <button onClick={loadTables}
            disabled={loading || mdbAvailable === false || (mode === "upload" && !uploadFile) || (mode === "path" && !serverPath.trim())}
            style={{ marginTop: 16, width: "100%", padding: "10px", borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: "pointer", backgroundColor: ACCESS_COLOR, color: "#000", border: "none", opacity: (loading || mdbAvailable === false) ? 0.5 : 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
            {loading ? <><Loader2 size={14} className="animate-spin" /> Lese Tabellen...</> : "Tabellen laden"}
          </button>
        </div>
      )}

      {step === 2 && (
        <div style={{ backgroundColor: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 10, padding: 20 }}>
          <p style={{ fontSize: 12, color: "#64748b", marginBottom: 16 }}>{tables.length} Tabelle{tables.length !== 1 ? "n" : ""} gefunden</p>
          <div style={{ maxHeight: 260, overflowY: "auto", scrollbarWidth: "thin", marginBottom: 16 }}>
            {tables.map((t) => (
              <div key={t} onClick={() => loadPreview(t)}
                style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 12px", borderRadius: 6, cursor: "pointer", marginBottom: 3, border: `1px solid ${selectedTable === t ? ACCESS_COLOR : "transparent"}`, backgroundColor: selectedTable === t ? `${ACCESS_COLOR}10` : "transparent" }}>
                <div style={{ width: 8, height: 8, borderRadius: "50%", backgroundColor: selectedTable === t ? ACCESS_COLOR : "#374151", flexShrink: 0 }} />
                <span style={{ fontSize: 13, fontFamily: "monospace", color: selectedTable === t ? ACCESS_COLOR : "#94a3b8", fontWeight: selectedTable === t ? 600 : 400 }}>{t}</span>
              </div>
            ))}
          </div>
          {preview && (
            <div style={{ marginBottom: 16, backgroundColor: "rgba(0,0,0,0.2)", borderRadius: 6, padding: 12, overflow: "auto", scrollbarWidth: "thin" }}>
              <p style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", color: ACCESS_COLOR, marginBottom: 8 }}>Vorschau - {preview.total_columns} Spalten</p>
              <table style={{ fontSize: 11, borderCollapse: "collapse", minWidth: "max-content" }}>
                <thead><tr>{preview.columns?.map(c => <th key={c} style={{ textAlign: "left", padding: "4px 10px", fontFamily: "monospace", color: "#64748b", borderBottom: "1px solid rgba(255,255,255,0.06)", whiteSpace: "nowrap" }}>{c}</th>)}</tr></thead>
                <tbody>{preview.rows?.map((row, i) => <tr key={i}>{preview.columns?.map(c => <td key={c} style={{ padding: "3px 10px", color: "#94a3b8", fontFamily: "monospace", whiteSpace: "nowrap" }}>{String(row[c] ?? "")}</td>)}</tr>)}</tbody>
              </table>
            </div>
          )}
          <div style={{ marginBottom: 16 }}>
            <label style={lS}>Dataset-Name</label>
            <input style={iS} value={datasetName} onChange={(e) => setDatasetName(e.target.value)} placeholder="Mein Access-Dataset" />
          </div>
          {error && <p style={{ fontSize: 12, color: "#f87171", marginBottom: 12, padding: "8px 12px", backgroundColor: "rgba(248,113,113,0.08)", borderRadius: 6 }}>{error}</p>}
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={reset} style={{ flex: 1, padding: "9px", borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: "pointer", backgroundColor: "transparent", border: "1px solid rgba(255,255,255,0.1)", color: "#64748b" }}>Zurueck</button>
            <button onClick={doImport} disabled={!selectedTable || loading}
              style={{ flex: 2, padding: "9px", borderRadius: 6, fontSize: 13, fontWeight: 700, cursor: "pointer", backgroundColor: selectedTable ? ACCESS_COLOR : "#374151", color: selectedTable ? "#000" : "#64748b", border: "none", opacity: loading ? 0.6 : 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
              {loading ? <><Loader2 size={14} className="animate-spin" /> Importiere...</> : (selectedTable ? `"${selectedTable}" importieren` : "Tabelle waehlen")}
            </button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div style={{ backgroundColor: "rgba(110,231,183,0.05)", border: "1px solid rgba(110,231,183,0.2)", borderRadius: 10, padding: 28, textAlign: "center" }}>
          <CheckCircle2 size={40} style={{ color: "#6ee7b7", marginBottom: 12 }} />
          <p style={{ fontSize: 15, fontWeight: 700, color: "#f1f5f9", marginBottom: 6 }}>{success}</p>
          <p style={{ fontSize: 12, color: "#64748b", marginBottom: 20 }}>Das Dataset ist jetzt im Datasets-Tab verfuegbar.</p>
          <button onClick={reset} style={{ padding: "9px 24px", borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: "pointer", backgroundColor: "transparent", border: `1px solid ${ACCESS_COLOR}`, color: ACCESS_COLOR }}>Weitere Tabelle importieren</button>
        </div>
      )}
    </div>
  );
}


export default AccessImportPanel;
