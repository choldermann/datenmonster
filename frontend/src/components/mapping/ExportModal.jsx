import { useState, useEffect } from "react";
import { Check, ChevronDown, ChevronRight, Download, Link2, Loader2, Play, Plus, Server, Settings, X } from "lucide-react";
import api from "../../api/client";
import { S, TARGET_TYPES, TARGET_TYPE_COLORS, JOIN_COLOR } from "./constants";

function TargetConfig({ targetType, targetConnectionId, targetTable, targetWriteMode, connections, onChange }) {
  const iS = { backgroundColor: S.bgEl, border: `1px solid ${S.border}`, color: S.textBright, borderRadius: "4px", padding: "6px 10px", width: "100%", outline: "none", fontSize: "12px" };
  const lS = { fontSize: "10px", textTransform: "uppercase", letterSpacing: "0.08em", color: S.textDim, display: "block", marginBottom: "4px" };
  const TARGET_TYPES = [
    { value: "csv", label: "CSV", color: "#6ee7b7" }, { value: "xlsx", label: "Excel", color: "#93c5fd" },
    { value: "json", label: "JSON", color: "#fcd34d" }, { value: "xml", label: "XML", color: "#f9a8d4" },
    { value: "db_mssql", label: "SQL Server", color: "#c4b5fd" }, { value: "db_mysql", label: "MySQL", color: "#6ee7b7" },
  ];
  return (
    <div className="flex flex-col gap-4">
      <div>
        <label style={lS}>Zielformat</label>
        <div className="grid grid-cols-2 gap-1.5">
          {TARGET_TYPES.map((t) => (
            <button key={t.value} onClick={() => onChange({ targetType: t.value })}
              style={{ padding: "7px", borderRadius: 4, fontSize: 11, fontWeight: 600, backgroundColor: targetType === t.value ? t.color + "18" : S.bgEl, border: `1px solid ${targetType === t.value ? t.color : S.border}`, color: targetType === t.value ? t.color : S.textDim, cursor: "pointer" }}>
              {t.label}
            </button>
          ))}
        </div>
      </div>
      {(targetType === "db_mssql" || targetType === "db_mysql") && (<>
        <div><label style={lS}>Verbindung</label><select style={iS} value={targetConnectionId || ""} onChange={(e) => onChange({ targetConnectionId: parseInt(e.target.value) || null })}><option value="">– Verbindung wählen –</option>{connections.filter((c) => c.db_type === (targetType === "db_mssql" ? "mssql" : "mysql")).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
        <div><label style={lS}>Zieltabelle</label><input style={iS} placeholder="tabellen_name" value={targetTable || ""} onChange={(e) => onChange({ targetTable: e.target.value })} /></div>
        <div><label style={lS}>Schreibmodus</label><select style={iS} value={targetWriteMode || "insert"} onChange={(e) => onChange({ targetWriteMode: e.target.value })}><option value="insert">INSERT</option><option value="update">UPDATE</option><option value="upsert">UPSERT</option><option value="truncate_insert">TRUNCATE + INSERT</option></select></div>
      </>)}
    </div>
  );
}

// ─── SVG Overlay (Mapping + Join Lines) ───────────────────────────────────────

function ContextMenu({ x, y, onJoin, onClose }) {
  useEffect(() => {
    const handler = () => onClose();
    window.addEventListener("click", handler);
    return () => window.removeEventListener("click", handler);
  }, [onClose]);

  return (
    <div style={{ position: "fixed", left: x, top: y, zIndex: 100, backgroundColor: S.bgCard, border: `1px solid ${S.border}`, borderRadius: 6, boxShadow: "0 8px 24px rgba(0,0,0,0.5)", minWidth: 160, overflow: "hidden" }}
      onClick={(e) => e.stopPropagation()}>
      <button onClick={onJoin} style={{ display: "flex", alignItems: "center", gap: 8, width: "100%", padding: "9px 14px", fontSize: 12, color: JOIN_COLOR, backgroundColor: "transparent", border: "none", cursor: "pointer", textAlign: "left" }}
        onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = `${JOIN_COLOR}15`)}
        onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}>
        <Link2 size={13} /> Join von hier ziehen
      </button>
    </div>
  );
}

// ─── Export Modal ─────────────────────────────────────────────────────────────

function ExportModal({ canvasNodes, connections, joins, transformNodes, constantNodes, connections_list, onClose }) {
  const [targetType, setTargetType] = useState("csv");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [connections_db, setConnectionsDb] = useState([]);
  const [targetConnectionId, setTargetConnectionId] = useState("");
  const [showXmlEditor, setShowXmlEditor] = useState(false);
  const [targetTable, setTargetTable] = useState("");
  const [writeMode, setWriteMode] = useState("insert");
  const [keyColumns, setKeyColumns] = useState("");
  const [csvDelimiter, setCsvDelimiter] = useState(";");
  const [xmlTemplate, setXmlTemplate] = useState({ root: "Daten", row: "Datensatz", fields: [] });

  const targetFields = connections.map((c) => c.target_field).filter(Boolean);

  useEffect(() => {
    api.get("/api/connections").then((r) => setConnectionsDb(r.data || [])).catch(() => {});
    // Init xml template fields from connections
    if (xmlTemplate.fields.length === 0 && targetFields.length > 0) {
      setXmlTemplate((prev) => ({ ...prev, fields: targetFields.map((f) => ({ field: f, xmlPath: f, isAttribute: false })) }));
    }
  }, []);

  const execute = async () => {
    setRunning(true); setResult(null);
    try {
      const opts = {};
      if (targetType === "csv") opts.delimiter = csvDelimiter;
      if (targetType === "xml") opts.xml_template = xmlTemplate;
      if (targetType === "db") {
        opts.key_columns = keyColumns.split(",").map((s) => s.trim()).filter(Boolean);
      }

      const payload = {
        canvas_nodes: canvasNodes, fields: connections, joins, transform_nodes: transformNodes, constant_nodes: constantNodes,
        target_type: targetType,
        target_connection_id: targetConnectionId ? parseInt(targetConnectionId) : null,
        target_table: targetTable,
        target_write_mode: writeMode,
        target_options: opts,
      };

      if (targetType === "db") {
        const res = await api.post("/api/mappings/execute", payload);
        setResult({ type: "db", ...res.data });
      } else {
        // File download
        const res = await api.post("/api/mappings/execute", payload, { responseType: "blob" });
        const ext = targetType;
        const url = URL.createObjectURL(res.data);
        const a = document.createElement("a");
        a.href = url; a.download = `export.${ext}`; a.click();
        URL.revokeObjectURL(url);
        setResult({ type: "download", ok: true });
      }
    } catch (e) {
      setResult({ type: "error", message: e.response?.data?.detail || e.message });
    } finally {
      setRunning(false);
    }
  };

  const TARGET_TYPES = [
    { value: "csv", label: "CSV", icon: "📄" },
    { value: "xlsx", label: "XLSX", icon: "📊" },
    { value: "json", label: "JSON", icon: "{ }" },
    { value: "xml", label: "XML", icon: "🌿" },
    { value: "db", label: "Datenbank", icon: "🗄️" },
  ];

  const WRITE_MODES = [
    { value: "insert", label: "INSERT – nur neue Zeilen" },
    { value: "truncate_insert", label: "TRUNCATE + INSERT – alles neu" },
    { value: "update", label: "UPDATE – bestehende aktualisieren" },
    { value: "upsert", label: "UPSERT – neu oder aktualisieren" },
  ];

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 70, display: "flex", alignItems: "center", justifyContent: "center", backgroundColor: "rgba(0,0,0,0.7)" }} onClick={onClose}>
      <div style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`, borderRadius: 8, padding: 24, width: 560, maxHeight: "90vh", overflowY: "auto", scrollbarWidth: "thin", boxShadow: "0 24px 64px rgba(0,0,0,0.7)" }} onClick={(e) => e.stopPropagation()}>

        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
          <div>
            <p style={{ fontSize: 13, fontWeight: 700, color: S.textBright }}>Mapping ausführen</p>
            <p style={{ fontSize: 11, color: S.textDim, marginTop: 2 }}>{targetFields.length} Zielfelder · {canvasNodes.length} Datasets</p>
          </div>
          <button onClick={onClose} style={{ color: S.textDim }}><X size={14} /></button>
        </div>

        {/* Target type selector */}
        <div style={{ marginBottom: 20 }}>
          <p style={{ fontSize: 10, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>Export-Ziel</p>
          <div style={{ display: "flex", gap: 6 }}>
            {TARGET_TYPES.map((t) => (
              <button key={t.value} onClick={() => setTargetType(t.value)}
                style={{ flex: 1, padding: "10px 6px", borderRadius: 6, cursor: "pointer", fontSize: 11, fontWeight: 600, textAlign: "center", border: `1px solid ${targetType === t.value ? S.accent : S.border}`, backgroundColor: targetType === t.value ? "rgba(252,228,153,0.1)" : S.bgEl, color: targetType === t.value ? S.accent : S.textDim, transition: "all 0.1s" }}>
                <div style={{ fontSize: 16, marginBottom: 3 }}>{t.icon}</div>
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {/* CSV options */}
        {targetType === "csv" && (
          <div style={{ marginBottom: 16 }}>
            <p style={{ fontSize: 10, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>Trennzeichen</p>
            <div style={{ display: "flex", gap: 6 }}>
              {[";", ",", "\t", "|"].map((d) => (
                <button key={d} onClick={() => setCsvDelimiter(d)}
                  style={{ padding: "5px 12px", borderRadius: 4, cursor: "pointer", fontSize: 12, fontFamily: "monospace", border: `1px solid ${csvDelimiter === d ? S.accent : S.border}`, backgroundColor: csvDelimiter === d ? "rgba(252,228,153,0.1)" : S.bgEl, color: csvDelimiter === d ? S.accent : S.textDim }}>
                  {d === "\t" ? "TAB" : d}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* XML Template */}
        {targetType === "xml" && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
              <p style={{ fontSize: 10, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.08em" }}>XML-Struktur</p>
              <button onClick={() => setShowXmlEditor(true)}
                style={{ fontSize: 11, padding: "5px 14px", borderRadius: 4, cursor: "pointer", backgroundColor: "rgba(125,211,252,0.1)", border: "1px solid rgba(125,211,252,0.3)", color: "#7dd3fc" }}>
                🌿 Template-Editor öffnen
              </button>
            </div>
            {xmlTemplate?.tree ? (
              <div style={{ padding: "8px 12px", backgroundColor: S.bgMain, borderRadius: 4, border: `1px solid ${S.border}`, fontSize: 11, fontFamily: "monospace", color: S.textDim }}>
                <span style={{ color: "#7dd3fc" }}>&lt;{xmlTemplate.tree.tag}&gt;</span>
                {" · "}
                <span style={{ color: S.textMain }}>{countNodes(xmlTemplate.tree)} Elemente</span>
                {" · "}
                <span style={{ color: "#fbbf24" }}>{countAttrs(xmlTemplate.tree)} Attribute</span>
                {" · "}
                <span style={{ color: "#6ee7b7" }}>{countBindings(xmlTemplate.tree)} Feldbindungen</span>
              </div>
            ) : (
              <div style={{ padding: "10px 12px", backgroundColor: S.bgMain, borderRadius: 4, border: `1px dashed ${S.border}`, fontSize: 11, color: S.textDim, textAlign: "center" }}>
                Noch kein Template definiert – Editor öffnen
              </div>
            )}
          </div>
        )}

        {/* DB options */}
        {targetType === "db" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 16 }}>
            <div>
              <p style={{ fontSize: 10, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>Verbindung</p>
              <select value={targetConnectionId} onChange={(e) => setTargetConnectionId(e.target.value)}
                style={{ width: "100%", padding: "7px 10px", backgroundColor: S.bgMain, border: `1px solid ${S.border}`, borderRadius: 4, color: S.textBright, fontSize: 12, outline: "none" }}>
                <option value="">-- Verbindung wählen --</option>
                {connections_db.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.db_type})</option>)}
              </select>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <div>
                <p style={{ fontSize: 10, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>Zieltabelle</p>
                <input value={targetTable} onChange={(e) => setTargetTable(e.target.value)} placeholder="dbo.MeineTabelle"
                  style={{ width: "100%", padding: "7px 10px", backgroundColor: S.bgMain, border: `1px solid ${S.border}`, borderRadius: 4, color: S.textBright, fontSize: 12, outline: "none", fontFamily: "monospace", boxSizing: "border-box" }} />
              </div>
              <div>
                <p style={{ fontSize: 10, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>Schreibmodus</p>
                <select value={writeMode} onChange={(e) => setWriteMode(e.target.value)}
                  style={{ width: "100%", padding: "7px 10px", backgroundColor: S.bgMain, border: `1px solid ${S.border}`, borderRadius: 4, color: S.textBright, fontSize: 12, outline: "none" }}>
                  {WRITE_MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                </select>
              </div>
            </div>
            {(writeMode === "update" || writeMode === "upsert") && (
              <div>
                <p style={{ fontSize: 10, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>Schlüsselspalten (kommagetrennt)</p>
                <input value={keyColumns} onChange={(e) => setKeyColumns(e.target.value)} placeholder="ID, Artikelnummer"
                  style={{ width: "100%", padding: "7px 10px", backgroundColor: S.bgMain, border: `1px solid ${S.border}`, borderRadius: 4, color: S.textBright, fontSize: 12, outline: "none", fontFamily: "monospace", boxSizing: "border-box" }} />
              </div>
            )}
          </div>
        )}

        {/* Result feedback */}
        {result && (
          <div style={{ marginBottom: 16, padding: "10px 12px", borderRadius: 6, backgroundColor: result.type === "error" ? "rgba(224,112,112,0.1)" : "rgba(110,231,183,0.1)", border: `1px solid ${result.type === "error" ? "#e07070" : "#6ee7b7"}44` }}>
            {result.type === "error" && <p style={{ fontSize: 12, color: "#e07070" }}>⚠ {result.message}</p>}
            {result.type === "download" && <p style={{ fontSize: 12, color: "#6ee7b7" }}>✓ Download gestartet</p>}
            {result.type === "db" && (
              <>
                <p style={{ fontSize: 12, color: "#6ee7b7" }}>✓ {result.rows_affected} Zeilen geschrieben → {result.table} ({result.mode})</p>
                {result.errors?.map((e, i) => <p key={i} style={{ fontSize: 11, color: "#e07070", marginTop: 4 }}>⚠ {e}</p>)}
              </>
            )}
          </div>
        )}

        {/* Execute button */}
        <button onClick={execute} disabled={running || (targetType === "db" && (!targetConnectionId || !targetTable))}
          style={{ width: "100%", padding: "11px", borderRadius: 6, cursor: running ? "wait" : "pointer", backgroundColor: S.accent, border: "none", color: "#111", fontSize: 13, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", gap: 8, opacity: running ? 0.7 : 1 }}>
          {running ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
          {running ? "Wird ausgeführt…" : "Ausführen"}
        </button>
      </div>

      {/* XML Template Editor modal (above export modal) */}
      {showXmlEditor && (
        <XmlTemplateEditor
          fields={targetFields}
          template={xmlTemplate}
          onChange={(t) => setXmlTemplate(t)}
          onClose={() => setShowXmlEditor(false)}
        />
      )}
    </div>
  );
}

// Helper functions for ExportModal XML stats
function countNodes(node) {
  return 1 + (node?.children || []).reduce((s, c) => s + countNodes(c), 0);
}
function countAttrs(node) {
  return (node?.attributes?.length || 0) + (node?.children || []).reduce((s, c) => s + countAttrs(c), 0);
}
function countBindings(node) {
  const own = (node?.fieldBinding ? 1 : 0) + (node?.attributes || []).filter((a) => a.fieldBinding).length;
  return own + (node?.children || []).reduce((s, c) => s + countBindings(c), 0);
}

// ─── Preview Panel ────────────────────────────────────────────────────────────

function TargetAddField({ onAdd }) {
  const [show, setShow] = useState(false);
  const [val, setVal] = useState("");
  if (!show) return (
    <div style={{ padding: "8px 12px", borderTop: `1px solid ${S.border}`, flexShrink: 0 }}>
      <button onClick={() => setShow(true)} className="btn-ghost text-xs w-full justify-center" style={{ display: "flex", alignItems: "center", gap: 4, justifyContent: "center", width: "100%" }}>
        <Plus size={10} /> Zielfeld hinzufügen
      </button>
    </div>
  );
  return (
    <div style={{ padding: "8px 12px", borderTop: `1px solid ${S.border}`, flexShrink: 0 }}>
      <div style={{ display: "flex", gap: 6 }}>
        <input autoFocus className="input" style={{ fontSize: 11, fontFamily: "monospace", padding: "5px 8px", flex: 1 }}
          placeholder="Feldname..." value={val}
          onChange={(e) => setVal(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && val.trim()) { onAdd(val.trim()); setVal(""); setShow(false); } if (e.key === "Escape") setShow(false); }}
          onClick={(e) => e.stopPropagation()} />
        <button onClick={() => { if (val.trim()) { onAdd(val.trim()); setVal(""); } setShow(false); }}
          style={{ padding: "5px 10px", borderRadius: 4, backgroundColor: S.accent, color: "#111", fontWeight: 700, fontSize: 13, border: "none", cursor: "pointer" }}>+</button>
      </div>
    </div>
  );
}

// ─── SQL Node ──────────────────────────────────────────────────────────────────


export { ExportModal, ContextMenu, TargetConfig, TargetAddField };
