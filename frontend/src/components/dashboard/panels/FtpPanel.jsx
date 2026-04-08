import { useCallback, useEffect, useState } from "react";
import { Check, CheckCircle2, Filter, FolderSync, Loader2, Pencil, Play, Plus, RefreshCw, Server, Trash2, Wifi, WifiOff, X, XCircle } from "lucide-react";
import api from "../../../api/client";
import { S } from "../constants";

const CRON_PRESETS = [
  { label: "Täglich",      value: "0 6 * * *" },
  { label: "Stündlich",    value: "0 * * * *" },
  { label: "Alle 15 Min",  value: "*/15 * * * *" },
  { label: "Wöchentlich Mo", value: "0 6 * * 1" },
];

function FtpFormModal({ source, projectId, datasets, onDone, onClose }) {
  const isNew = !source;
  const [form, setForm] = useState({
    name: source?.name || "",
    protocol: source?.protocol || "ftp",
    host: source?.host || "",
    port: source?.port || "",
    username: source?.username || "",
    password: source?.password || "",
    remote_dir: source?.remote_dir || "/",
    filename_filter: source?.filename_filter || "*",
    file_type: source?.file_type || "csv",
    csv_delimiter: source?.csv_delimiter || ";",
    skip_rows: source?.skip_rows || 0,
    after_import: source?.after_import || "nothing",
    move_dir: source?.move_dir || "",
    dataset_id: (source?.dataset_id && datasets?.find(d => d.id === source.dataset_id)) ? source.dataset_id : "",
    dataset_mode: source?.dataset_mode || "replace",
    dataset_name_tpl: source?.dataset_name_tpl || "",
    cron_expr: source?.cron_expr || "",
    active: source?.active !== false,
    start_date: source?.start_date || "",
    end_date: source?.end_date || "",
  });
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const iS = { backgroundColor: "#1a1a1a", border: "1px solid #333", color: "#fff", borderRadius: 4, padding: "6px 10px", width: "100%", outline: "none", fontSize: 12 };
  const lS = { fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", color: S.textDim, display: "block", marginBottom: 3 };
  const row = { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 };

  const handleSave = async () => {
    if (!form.name || !form.host || !form.username) { alert("Name, Host und Benutzer sind Pflichtfelder"); return; }
    setSaving(true);
    try {
      const dsId = form.dataset_id && datasets?.find(d => d.id === parseInt(form.dataset_id)) ? parseInt(form.dataset_id) : null;
      const payload = { ...form, port: form.port ? parseInt(form.port) : null, dataset_id: dsId, project_id: projectId, skip_rows: parseInt(form.skip_rows) || 0 };
      if (isNew) await api.post("/api/ftp-sources/", payload);
      else await api.put(`/api/ftp-sources/${source.id}`, payload);
      onDone();
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    } finally { setSaving(false); }
  };

  const handleTest = async () => {
    if (!source) { alert("Erst speichern, dann testen"); return; }
    setTesting(true); setTestResult(null);
    try {
      const { data } = await api.post(`/api/ftp-sources/${source.id}/test`);
      setTestResult({ ok: true, files: data.files, count: data.count });
    } catch (e) {
      setTestResult({ ok: false, msg: e.response?.data?.detail || e.message });
    } finally { setTesting(false); }
  };

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 60, backgroundColor: "rgba(0,0,0,0.75)", display: "flex", alignItems: "center", justifyContent: "center" }} onClick={onClose}>
      <div style={{ width: 560, maxHeight: "90vh", overflowY: "hidden", backgroundColor: S.bgCard, borderRadius: 10, border: `1px solid ${S.border}`, display: "flex", flexDirection: "column" }} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 18px", borderBottom: `1px solid ${S.border}` }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: S.textBright }}>{isNew ? "Neue FTP/SFTP-Quelle" : "FTP/SFTP-Quelle bearbeiten"}</span>
          <button onClick={onClose} style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer" }}><X size={15} /></button>
        </div>

        <div style={{ padding: "16px 18px", display: "flex", flexDirection: "column", gap: 14, overflowY: "auto", maxHeight: "calc(90vh - 60px)" }}>
          {/* Name */}
          <div><label style={lS}>Name</label><input style={iS} value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="z.B. Kunden-FTP" /></div>

          {/* Protokoll */}
          <div>
            <label style={lS}>Protokoll</label>
            <div style={{ display: "flex", gap: 8 }}>
              {["ftp", "sftp"].map((p) => (
                <button key={p} onClick={() => set("protocol", p)} style={{ padding: "5px 14px", borderRadius: 4, fontSize: 11, fontWeight: 600, cursor: "pointer", border: `1px solid ${form.protocol === p ? S.accent : S.border}`, backgroundColor: form.protocol === p ? "rgba(252,228,153,0.1)" : "#1a1a1a", color: form.protocol === p ? S.accent : S.textDim }}>
                  {p.toUpperCase()}
                </button>
              ))}
            </div>
          </div>

          {/* Host + Port */}
          <div style={row}>
            <div><label style={lS}>Host</label><input style={iS} value={form.host} onChange={(e) => set("host", e.target.value)} placeholder="ftp.example.com" /></div>
            <div><label style={lS}>Port (leer = Standard)</label><input style={iS} value={form.port} onChange={(e) => set("port", e.target.value)} placeholder={form.protocol === "sftp" ? "22" : "21"} /></div>
          </div>

          {/* Benutzer + Passwort */}
          <div style={row}>
            <div><label style={lS}>Benutzername</label><input style={iS} value={form.username} onChange={(e) => set("username", e.target.value)} /></div>
            <div><label style={lS}>Passwort</label><input style={{ ...iS }} type="password" value={form.password} onChange={(e) => set("password", e.target.value)} placeholder={!isNew && !form.password ? "••••••••  (unverändert)" : ""} /></div>
          </div>

          {/* Verzeichnis + Filter */}
          <div style={row}>
            <div><label style={lS}>Verzeichnis</label><input style={iS} value={form.remote_dir} onChange={(e) => set("remote_dir", e.target.value)} placeholder="/export/" /></div>
            <div><label style={lS}>Dateifilter (Glob)</label><input style={iS} value={form.filename_filter} onChange={(e) => set("filename_filter", e.target.value)} placeholder="*.csv" /></div>
          </div>

          {/* Dateiformat */}
          <div style={row}>
            <div>
              <label style={lS}>Dateiformat</label>
              <select style={iS} value={form.file_type} onChange={(e) => set("file_type", e.target.value)}>
                <option value="csv">CSV</option>
                <option value="xlsx">Excel (XLSX)</option>
                <option value="ods">ODS (LibreOffice)</option>
                <option value="xml">XML</option>
              </select>
            </div>
            {form.file_type === "csv" && (
              <div>
                <label style={lS}>CSV-Trennzeichen</label>
                <select style={iS} value={form.csv_delimiter} onChange={(e) => set("csv_delimiter", e.target.value)}>
                  {[";", ",", "|", "\t"].map((d) => <option key={d} value={d}>{d === "\t" ? "Tab" : d}</option>)}
                </select>
              </div>
            )}

            {/* Zeilen überspringen */}
            {["xlsx","xls","ods","csv"].includes(form.file_type) && (
              <div>
                <label style={lS}>Zeilen überspringen</label>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <input
                    type="number" min={0} max={1000}
                    value={form.skip_rows || 0}
                    onChange={e => set("skip_rows", Math.max(0, parseInt(e.target.value) || 0))}
                    style={{ ...iS, width: 80, textAlign: "center" }}
                  />
                  <span style={{ fontSize: 11, color: "var(--text-dim)" }}>
                    {(form.skip_rows || 0) === 0 ? "Keine Zeilen überspringen" : `Erste ${form.skip_rows} Zeile${form.skip_rows === 1 ? "" : "n"} überspringen`}
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* Nach Import */}
          <div>
            <label style={lS}>Nach dem Import</label>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {[{ v: "nothing", l: "Nichts tun" }, { v: "move", l: "Verschieben" }, { v: "delete", l: "Löschen" }].map((o) => (
                <button key={o.v} onClick={() => set("after_import", o.v)} style={{ padding: "5px 12px", borderRadius: 4, fontSize: 11, fontWeight: 600, cursor: "pointer", border: `1px solid ${form.after_import === o.v ? S.accent : S.border}`, backgroundColor: form.after_import === o.v ? "rgba(252,228,153,0.1)" : "#1a1a1a", color: form.after_import === o.v ? S.accent : S.textDim }}>
                  {o.l}
                </button>
              ))}
            </div>
            {form.after_import === "move" && (
              <input style={{ ...iS, marginTop: 8 }} value={form.move_dir} onChange={(e) => set("move_dir", e.target.value)} placeholder="Zielverzeichnis z.B. /processed/" />
            )}
          </div>

          {/* Dataset-Ziel */}
          <div style={{ padding: "12px 14px", borderRadius: 6, border: `1px solid ${S.border}`, backgroundColor: "#161616" }}>
            <p style={{ fontSize: 11, fontWeight: 700, color: S.textBright, marginBottom: 10 }}>Ziel-Dataset</p>
            <div style={row}>
              <div>
                <label style={lS}>Bestehendes Dataset (optional)</label>
                <select style={iS} value={form.dataset_id} onChange={(e) => set("dataset_id", e.target.value)}>
                  <option value="">— Neues Dataset anlegen —</option>
                  {datasets.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>
              </div>
              <div>
                <label style={lS}>Schreibmodus</label>
                <select style={iS} value={form.dataset_mode} onChange={(e) => set("dataset_mode", e.target.value)}>
                  <option value="replace">Ersetzen (replace)</option>
                  <option value="append">Anhängen (append)</option>
                </select>
              </div>
            </div>
            {!form.dataset_id && (
              <div style={{ marginTop: 10 }}>
                <label style={lS}>Name für neues Dataset</label>
                <input style={iS} value={form.dataset_name_tpl} onChange={(e) => set("dataset_name_tpl", e.target.value)} placeholder={form.name || "FTP-Import"} />
              </div>
            )}
          </div>

          {/* Zeitplan */}
          <div style={{ padding: "12px 14px", borderRadius: 6, border: `1px solid ${S.border}`, backgroundColor: "#161616" }}>
            <p style={{ fontSize: 11, fontWeight: 700, color: S.textBright, marginBottom: 10 }}>Zeitplan (optional)</p>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
              {CRON_PRESETS.map((p) => (
                <button key={p.value} onClick={() => set("cron_expr", p.value)} style={{ padding: "4px 10px", borderRadius: 3, fontSize: 10, cursor: "pointer", border: `1px solid ${form.cron_expr === p.value ? S.accent : S.border}`, backgroundColor: form.cron_expr === p.value ? "rgba(252,228,153,0.1)" : "#1a1a1a", color: form.cron_expr === p.value ? S.accent : S.textDim }}>
                  {p.label}
                </button>
              ))}
            </div>
            <input style={iS} value={form.cron_expr} onChange={(e) => set("cron_expr", e.target.value)} placeholder="Cron-Ausdruck z.B. 0 6 * * *" />
            <div style={{ ...row, marginTop: 10 }}>
              <div><label style={lS}>Startdatum</label><input type="date" style={iS} value={form.start_date} onChange={(e) => set("start_date", e.target.value)} /></div>
              <div><label style={lS}>Enddatum</label><input type="date" style={iS} value={form.end_date} onChange={(e) => set("end_date", e.target.value)} /></div>
            </div>
            <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10, cursor: "pointer", fontSize: 12, color: S.textMain }}>
              <input type="checkbox" checked={form.active} onChange={(e) => set("active", e.target.checked)} />
              Aktiv
            </label>
          </div>

          {/* Verbindungstest */}
          {!isNew && (
            <div>
              <button onClick={handleTest} disabled={testing} style={{ padding: "6px 14px", borderRadius: 4, fontSize: 11, fontWeight: 600, cursor: "pointer", border: `1px solid ${S.border}`, backgroundColor: "#1a1a1a", color: S.textMain, display: "flex", alignItems: "center", gap: 6 }}>
                {testing ? <Loader2 size={12} className="animate-spin" /> : <Wifi size={12} />} Verbindung testen
              </button>
              {testResult && (
                <div style={{ marginTop: 8, padding: "8px 12px", borderRadius: 4, fontSize: 11, backgroundColor: testResult.ok ? "rgba(110,231,183,0.08)" : "rgba(248,113,113,0.08)", border: `1px solid ${testResult.ok ? "#6ee7b7" : "#f87171"}`, color: testResult.ok ? "#6ee7b7" : "#f87171" }}>
                  {testResult.ok ? (
                    <div>
                      <p style={{ fontWeight: 600, marginBottom: 4 }}>✓ Verbunden · {testResult.count} Datei(en) gefunden</p>
                      {testResult.files.slice(0, 8).map((f) => <p key={f} style={{ opacity: 0.8 }}>• {f}</p>)}
                      {testResult.count > 8 && <p style={{ opacity: 0.6 }}>… und {testResult.count - 8} weitere</p>}
                    </div>
                  ) : <p>✗ {testResult.msg}</p>}
                </div>
              )}
            </div>
          )}
        </div>

        <div style={{ padding: "12px 18px", borderTop: `1px solid ${S.border}`, display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button onClick={onClose} className="btn-ghost text-xs">Abbrechen</button>
          <button onClick={handleSave} disabled={saving} className="btn-primary text-xs">
            {saving ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />} {isNew ? "Erstellen" : "Speichern"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── REST API Panel ───────────────────────────────────────────────────────────
const REST_COLOR = "#818cf8"; // indigo-400

const REST_AUTH_TYPES = [
  { v: "none",       l: "Keine Auth" },
  { v: "basic",      l: "Basic Auth" },
  { v: "bearer",     l: "Bearer Token" },
  { v: "apikey",     l: "API Key" },
  { v: "oauth2_cc",  l: "OAuth2 Client Credentials" },
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
const TEMPLATE_VARS = ["{{heute}}", "{{gestern}}", "{{morgen}}", "{{timestamp}}", "{{iso_heute}}", "{{monat}}", "{{jahr}}", "{{epoch_ms}}"];

const EMPTY_SOURCE = {
  name: "", url: "", method: "GET",
  headers: {}, query_params: {},
  body_type: "none", body_content: "",
  auth_type: "none", auth_config: {},
  data_path: "", flatten: 1,
  pagination: { type: "none" },
  dataset_mode: "replace", cron_expr: "", active: 1,
};


function FtpPanel({ projectId, datasets, canEdit }) {
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState(null);    // null | "new" | source object
  const [triggering, setTriggering] = useState({}); // { [id]: true }

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = projectId != null ? `?project_id=${projectId}` : "";
      const { data } = await api.get(`/api/ftp-sources/${p}`);
      setSources(Array.isArray(data) ? data : []);
    } catch {} finally { setLoading(false); }
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  const handleDelete = async (id) => {
    if (!confirm("FTP-Quelle wirklich löschen?")) return;
    await api.delete(`/api/ftp-sources/${id}`);
    load();
  };

  const handleTrigger = async (id) => {
    setTriggering((t) => ({ ...t, [id]: true }));
    try {
      await api.post(`/api/ftp-sources/${id}/trigger`);
      setTimeout(() => { load(); setTriggering((t) => ({ ...t, [id]: false })); }, 2500);
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
      setTriggering((t) => ({ ...t, [id]: false }));
    }
  };

  const statusColor = { success: "#6ee7b7", error: "#f87171" };

  return (
    <div style={{ padding: "28px 32px", maxWidth: 900 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <div>
          <h2 style={{ fontSize: 16, fontWeight: 700, color: S.textBright }}>FTP / SFTP Quellen</h2>
          <p style={{ fontSize: 12, color: S.textDim, marginTop: 2 }}>Dateien von FTP/SFTP-Servern automatisch importieren und in Datasets speichern</p>
        </div>
        {canEdit && (
          <button onClick={() => setEditing("new")} className="btn-primary text-xs"><Plus size={13} /> Neue Quelle</button>
        )}
      </div>

      {loading && <div style={{ color: S.textDim, fontSize: 12 }}><Loader2 size={14} className="animate-spin inline mr-2" />Lädt…</div>}

      {!loading && sources.length === 0 && (
        <div style={{ textAlign: "center", padding: "60px 0", color: S.textDim }}>
          <Server size={36} style={{ margin: "0 auto 12px", opacity: 0.3 }} />
          <p style={{ fontSize: 13 }}>Noch keine FTP/SFTP-Quelle konfiguriert</p>
          {canEdit && <button onClick={() => setEditing("new")} className="btn-primary text-xs mt-4"><Plus size={12} /> Erste Quelle anlegen</button>}
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {sources.map((s) => (
          <div key={s.id} style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`, borderRadius: 8, padding: "14px 18px" }}>
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                  <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 3, backgroundColor: s.protocol === "sftp" ? "rgba(147,197,253,0.15)" : "rgba(110,231,183,0.12)", color: s.protocol === "sftp" ? "#93c5fd" : "#6ee7b7", textTransform: "uppercase" }}>{s.protocol}</span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: S.textBright }}>{s.name}</span>
                  {!s.active && <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 3, backgroundColor: "rgba(255,255,255,0.05)", color: S.textDim }}>Inaktiv</span>}
                </div>
                <div style={{ fontSize: 11, color: S.textDim, display: "flex", gap: 14, flexWrap: "wrap" }}>
                  <span>🖥 {s.host}{s.port ? `:${s.port}` : ""}</span>
                  <span>📁 {s.remote_dir}</span>
                  <span>🔍 {s.filename_filter}</span>
                  <span>📄 {s.file_type?.toUpperCase()}</span>
                  {s.cron_expr && <span>⏰ {s.cron_expr}</span>}
                  <span style={{ color: s.dataset_mode === "append" ? "#fcd34d" : S.textDim }}>
                    {s.dataset_mode === "append" ? "↓ Anhängen" : "↺ Ersetzen"}
                  </span>
                  {s.after_import !== "nothing" && (
                    <span style={{ color: s.after_import === "delete" ? "#f87171" : "#c4b5fd" }}>
                      {s.after_import === "delete" ? "🗑 Löschen" : `📦 → ${s.move_dir || "?"}`}
                    </span>
                  )}
                </div>

                {/* Letzter Run */}
                {s.last_run_at && (
                  <div style={{ marginTop: 6, display: "flex", alignItems: "center", gap: 6, fontSize: 10, color: statusColor[s.last_run_status] || S.textDim }}>
                    {s.last_run_status === "success" ? <CheckCircle2 size={11} /> : <XCircle size={11} />}
                    <span>{new Date(s.last_run_at).toLocaleString("de-DE")} · {s.last_run_msg}</span>
                  </div>
                )}
              </div>

              <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                {canEdit && (
                  <>
                    <button onClick={() => handleTrigger(s.id)} disabled={!!triggering[s.id]} title="Jetzt synchronisieren"
                      style={{ padding: "5px 10px", borderRadius: 4, fontSize: 11, cursor: "pointer", border: `1px solid ${S.border}`, backgroundColor: "#1a1a1a", color: triggering[s.id] ? S.textDim : "#6ee7b7", display: "flex", alignItems: "center", gap: 4 }}>
                      {triggering[s.id] ? <Loader2 size={11} className="animate-spin" /> : <FolderSync size={11} />} Sync
                    </button>
                    <button onClick={() => setEditing(s)} title="Bearbeiten"
                      style={{ padding: "5px 8px", borderRadius: 4, cursor: "pointer", border: `1px solid ${S.border}`, backgroundColor: "#1a1a1a", color: S.textDim }}>
                      <Pencil size={11} />
                    </button>
                    <button onClick={() => handleDelete(s.id)} title="Löschen"
                      style={{ padding: "5px 8px", borderRadius: 4, cursor: "pointer", border: `1px solid ${S.border}`, backgroundColor: "#1a1a1a", color: "#f87171" }}>
                      <Trash2 size={11} />
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {editing && (
        <FtpFormModal
          source={editing === "new" ? null : editing}
          projectId={projectId}
          datasets={datasets}
          onDone={() => { setEditing(null); load(); }}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

export { FtpPanel, FtpFormModal };
