import { useState, useEffect, useRef } from "react";
import {
  Upload, Database, X, ChevronRight, ChevronLeft,
  Loader2, CheckCircle, FileText, Code2, AlertCircle,
} from "lucide-react";
import api from "../api/client";

const S = {
  accent: "var(--accent)", bgMain: "var(--bg-main)", bgCard: "var(--bg-card)",
  bgEl: "var(--bg-elevated)", border: "var(--border)", textMain: "var(--text-main)",
  textBright: "var(--text-bright)", textDim: "var(--text-dim)",
};

const inputStyle = {
  backgroundColor: S.bgEl, border: `1px solid ${S.border}`, color: S.textBright,
  borderRadius: "0.5rem", padding: "0.4rem 0.75rem", width: "100%",
  outline: "none", fontSize: "0.875rem",
};
const labelStyle = {
  fontSize: "0.65rem", textTransform: "uppercase", letterSpacing: "0.08em",
  color: S.textDim, display: "block", marginBottom: "0.3rem",
};

// ─── Step: Choose ─────────────────────────────────────────────────────────────
function StepChoose({ onChoose }) {
  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs mb-2" style={{ color: S.textDim }}>
        Wähle, wie das Dataset erstellt werden soll:
      </p>
      {[
        {
          key: "file", icon: Upload, color: "#93c5fd", bg: "rgba(147,197,253,0.1)",
          title: "Datei hochladen", sub: "CSV, XLSX oder XML-Datei importieren",
        },
        {
          key: "sql", icon: Database, color: "#c4b5fd", bg: "rgba(196,181,253,0.1)",
          title: "SQL-Abfrage", sub: "Dataset aus einer Datenbankverbindung abfragen",
        },
      ].map(({ key, icon: Icon, color, bg, title, sub }) => (
        <button
          key={key}
          onClick={() => onChoose(key)}
          className="flex items-center gap-5 p-5 rounded-xl text-left transition-all duration-150 w-full"
          style={{ backgroundColor: S.bgEl, border: `1px solid ${S.border}` }}
          onMouseEnter={(e) => (e.currentTarget.style.borderColor = S.accent)}
          onMouseLeave={(e) => (e.currentTarget.style.borderColor = S.border)}
        >
          <div className="rounded-lg p-3 shrink-0" style={{ backgroundColor: bg }}>
            <Icon size={22} style={{ color }} />
          </div>
          <div>
            <p className="text-sm font-medium" style={{ color: S.textBright }}>{title}</p>
            <p className="text-xs mt-1" style={{ color: S.textDim }}>{sub}</p>
          </div>
          <ChevronRight size={16} className="ml-auto shrink-0" style={{ color: S.textDim }} />
        </button>
      ))}
    </div>
  );
}

// ─── Step: File Upload ────────────────────────────────────────────────────────
function StepFileUpload({ onDone, projectId }) {
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState(null);
  const [name, setName] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [delimiter, setDelimiter] = useState("auto");
  const [skipRows, setSkipRows] = useState(0);
  const [detectedDelimiter, setDetectedDelimiter] = useState(null);
  const inputRef = useRef();

  const extColor = { csv: "#6ee7b7", xlsx: "#93c5fd", xls: "#93c5fd", xml: "#fcd34d", ods: "#86efac" };

  const detectDelimiter = (f) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target.result;
      const firstLine = text.split("\n")[0] || "";
      const counts = {
        ";": (firstLine.match(/;/g) || []).length,
        ",": (firstLine.match(/,/g) || []).length,
        "\t": (firstLine.match(/\t/g) || []).length,
        "|": (firstLine.match(/\|/g) || []).length,
      };
      const detected = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
      if (detected && detected[1] > 0) {
        setDetectedDelimiter(detected[0]);
      }
    };
    reader.readAsText(f.slice(0, 2048));
  };

  const handleFile = (f) => {
    if (!f) return;
    setFile(f);
    setError("");
    setName(f.name.replace(/\.[^.]+$/, "").replace(/[_-]/g, " "));
    const ext = f.name.split(".").pop()?.toLowerCase();
    if (ext === "csv") detectDelimiter(f);
  };

  const handleUpload = async () => {
    if (!file || !name.trim()) return;
    setUploading(true);
    setError("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("name", name.trim());
      if (projectId != null) fd.append("project_id", projectId);
      const ext = file.name.split(".").pop()?.toLowerCase();
      if (ext === "csv") {
        const sep = delimiter === "auto" ? (detectedDelimiter || ",") : delimiter;
        fd.append("csv_delimiter", sep);
      }
      if (skipRows > 0) fd.append("skip_rows", skipRows);
      await api.post("/api/datasets/upload", fd);
      setSuccess(true);
      setTimeout(onDone, 800);
    } catch (err) {
      setError(err.response?.data?.detail || "Upload fehlgeschlagen");
    } finally {
      setUploading(false);
    }
  };

  if (success) return (
    <div className="flex flex-col items-center justify-center py-12 gap-3">
      <CheckCircle size={40} style={{ color: "#6ee7b7" }} />
      <p className="text-sm font-medium" style={{ color: S.textBright }}>Dataset erstellt!</p>
    </div>
  );

  const ext = file?.name?.split(".").pop()?.toLowerCase();
  const isCsv = ext === "csv";
  const effectiveDelimiter = delimiter === "auto" ? (detectedDelimiter || "?") : delimiter;
  const delimiterLabels = { ",": "Komma (,)", ";": "Semikolon (;)", "\t": "Tab (\\t)", "|": "Pipe (|)", "auto": "Auto-Erkennung" };

  return (
    <div className="flex flex-col gap-5">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); handleFile(e.dataTransfer.files[0]); }}
        onClick={() => inputRef.current?.click()}
        className="rounded-xl flex flex-col items-center justify-center gap-3 py-10 cursor-pointer transition-all"
        style={{
          border: `2px dashed ${dragging ? S.accent : file ? "rgba(110,231,183,0.4)" : S.border}`,
          backgroundColor: dragging ? "rgba(252,228,153,0.04)" : file ? "rgba(110,231,183,0.03)" : "transparent",
        }}
      >
        <input ref={inputRef} type="file" accept=".csv,.xlsx,.xls,.xml,.ods" className="hidden"
          onChange={(e) => handleFile(e.target.files[0])} />
        {file ? (
          <>
            <FileText size={28} style={{ color: extColor[ext] || S.textDim }} />
            <div className="text-center">
              <p className="text-sm font-medium" style={{ color: S.textBright }}>{file.name}</p>
              <p className="text-xs mt-1" style={{ color: S.textDim }}>
                {(file.size / 1024).toFixed(1)} KB · Andere Datei wählen
              </p>
            </div>
          </>
        ) : (
          <>
            <Upload size={28} style={{ color: S.textDim }} />
            <div className="text-center">
              <p className="text-sm" style={{ color: S.textMain }}>Datei hier ablegen oder klicken</p>
              <p className="text-xs mt-1" style={{ color: S.textDim }}>CSV, XLSX, XML</p>
            </div>
          </>
        )}
      </div>

      {file && (
        <div>
          <label style={labelStyle}>Dataset-Name</label>
          <input style={inputStyle} value={name} onChange={(e) => setName(e.target.value)}
            placeholder="z.B. Kundenliste 2024" autoFocus />
        </div>
      )}

      {isCsv && file && (
        <div>
          <label style={labelStyle}>CSV-Trennzeichen</label>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {["auto", ",", ";", "\t", "|"].map(d => (
              <button key={d} onClick={() => setDelimiter(d)}
                style={{ padding: "5px 12px", borderRadius: 5, fontSize: 11, fontWeight: 600, cursor: "pointer", border: `1px solid ${delimiter === d ? S.accent : S.border}`, backgroundColor: delimiter === d ? "rgba(252,228,153,0.1)" : "transparent", color: delimiter === d ? S.accent : S.textDim }}>
                {delimiterLabels[d]}
              </button>
            ))}
          </div>
          {delimiter === "auto" && detectedDelimiter && (
            <p style={{ fontSize: 11, color: "#6ee7b7", marginTop: 6 }}>
              ✓ Erkannt: <strong>{delimiterLabels[detectedDelimiter] || detectedDelimiter}</strong>
            </p>
          )}
          {delimiter === "auto" && !detectedDelimiter && (
            <p style={{ fontSize: 11, color: S.textDim, marginTop: 6 }}>Analysiere Datei…</p>
          )}
        </div>
      )}

      {file && ["xlsx","xls","ods","csv"].includes(file.name.split(".").pop()?.toLowerCase()) && (
        <div>
          <label style={{...labelStyle}}>Zeilen überspringen</label>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 6 }}>
            <input
              type="number"
              min={0}
              max={1000}
              value={skipRows}
              onChange={e => setSkipRows(Math.max(0, parseInt(e.target.value) || 0))}
              style={{
                width: 80, padding: "5px 10px", borderRadius: 5, fontSize: 12,
                background: "var(--bg-elevated)", border: `1px solid ${S.border}`,
                color: "var(--text-main)", textAlign: "center",
              }}
            />
            <span style={{ fontSize: 11, color: S.textDim }}>
              {skipRows === 0 ? "Keine Zeilen überspringen" : `Erste ${skipRows} Zeile${skipRows === 1 ? "" : "n"} überspringen`}
            </span>
          </div>
          {skipRows > 0 && (
            <p style={{ fontSize: 11, color: "#6ee7b7", marginTop: 6 }}>
              ✓ Import beginnt ab Zeile {skipRows + 1}
            </p>
          )}
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 text-xs px-3 py-2 rounded"
          style={{ backgroundColor: "rgba(220,50,50,0.08)", border: "1px solid rgba(220,50,50,0.2)", color: "#e07070" }}>
          <AlertCircle size={13} /> {error}
        </div>
      )}

      {file && (
        <button onClick={handleUpload} disabled={uploading || !name.trim()}
          className="btn-primary w-full justify-center">
          {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
          {uploading ? "Wird hochgeladen..." : "Dataset erstellen"}
        </button>
      )}
    </div>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
const panelStyle = (border, bg) => ({
  display: "flex", flexDirection: "column",
  border: `1px solid ${border}`, borderRadius: 8, overflow: "hidden",
});
const panelHeaderStyle = (bg, border) => ({
  padding: "6px 10px", borderBottom: `1px solid ${border}`,
  backgroundColor: bg, flexShrink: 0, fontSize: 10,
  textTransform: "uppercase", letterSpacing: "0.08em",
});
const scrollBody = { flex: 1, overflowY: "auto", overflowX: "auto", scrollbarWidth: "thin" };
const rowBtn = (active, accent, border) => ({
  display: "flex", alignItems: "center", gap: 6, width: "100%", textAlign: "left",
  padding: "5px 10px", fontSize: 11, fontFamily: "monospace",
  color: active ? accent : "var(--text-main)",
  backgroundColor: active ? "rgba(252,228,153,0.06)" : "transparent",
  border: "none", cursor: "pointer", whiteSpace: "nowrap",
  borderBottom: `1px solid ${border}`,
});

function Checkbox({ active, accent, border }) {
  return (
    <span style={{
      width: 12, height: 12, borderRadius: 3, flexShrink: 0,
      border: `1px solid ${active ? accent : border}`,
      backgroundColor: active ? "rgba(252,228,153,0.2)" : "transparent",
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      {active && <span style={{ width: 6, height: 6, borderRadius: 1, backgroundColor: accent, display: "block" }} />}
    </span>
  );
}

// Mini-Panel: Tabellen + Felder nebeneinander für JOIN-Editor etc.
function TableFieldPicker({ connId, tables, label, selectedTable, selectedFields, onTableClick, onFieldClick, loadingTables }) {
  const [cols, setCols] = useState([]);
  const [loadingCols, setLoadingCols] = useState(false);

  useEffect(() => {
    if (!selectedTable || !connId) return;
    setLoadingCols(true);
    api.get(`/api/connections/${connId}/columns`, { params: { table: selectedTable } })
      .then(({ data }) => setCols(data?.columns || []))
      .catch(() => setCols([]))
      .finally(() => setLoadingCols(false));
  }, [selectedTable, connId]);

  return (
    <div style={{ display: "flex", gap: 8, height: "100%" }}>
      <div style={{ ...panelStyle(S.border, S.bgEl), width: 180 }}>
        <div style={{ ...panelHeaderStyle(S.bgEl, S.border), color: S.textDim }}>{label} – Tabelle</div>
        <div style={scrollBody}>
          {loadingTables ? <div style={{ display: "flex", justifyContent: "center", padding: 12 }}><Loader2 size={12} className="animate-spin" style={{ color: S.textDim }} /></div>
            : tables.map((t) => (
              <button key={t} onClick={() => onTableClick(t)} style={rowBtn(selectedTable === t, S.accent, S.border)}
                onMouseEnter={(e) => { if (selectedTable !== t) e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.04)"; }}
                onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = selectedTable === t ? "rgba(252,228,153,0.06)" : "transparent"; }}>
                {t}
              </button>
            ))}
        </div>
      </div>
      <div style={{ ...panelStyle(S.border, S.bgEl), width: 170 }}>
        <div style={{ ...panelHeaderStyle(S.bgEl, S.border), color: S.textDim }}>Felder {selectedFields.length > 0 && <span style={{ color: S.accent }}>({selectedFields.length})</span>}</div>
        <div style={scrollBody}>
          {!selectedTable ? <div style={{ padding: "12px 10px", fontSize: 11, color: S.textDim, textAlign: "center" }}>← Tabelle wählen</div>
            : loadingCols ? <div style={{ display: "flex", justifyContent: "center", padding: 12 }}><Loader2 size={12} className="animate-spin" style={{ color: S.textDim }} /></div>
            : cols.map((col) => {
              const active = selectedFields.includes(col);
              return (
                <button key={col} onClick={() => onFieldClick(col)} style={rowBtn(active, S.accent, S.border)}
                  onMouseEnter={(e) => { if (!active) e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.04)"; }}
                  onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = active ? "rgba(252,228,153,0.06)" : "transparent"; }}>
                  <Checkbox active={active} accent={S.accent} border={S.border} />
                  {col}
                </button>
              );
            })}
        </div>
      </div>
    </div>
  );
}

// ─── Step: SQL Query ──────────────────────────────────────────────────────────
function StepSqlQuery({ onDone, name, setName, editDataset, projectId }) {
  const [connections, setConnections]     = useState([]);
  const [loadingConns, setLoadingConns]   = useState(true);
  const [selectedConn, setSelectedConn]   = useState(null);
  const [tables, setTables]               = useState([]);
  const [loadingTables, setLoadingTables] = useState(false);
  const [tableSearch, setTableSearch]     = useState("");
  const [selectedTable, setSelectedTable] = useState(null);
  const [tableAlias, setTableAlias]       = useState("");   // FROM tbl AS alias
  const [columns, setColumns]             = useState([]);
  const [loadingColumns, setLoadingColumns] = useState(false);
  const [selectedColumns, setSelectedColumns] = useState([]);
  const [selectedJoinColumns, setSelectedJoinColumns] = useState({}); // {joinIndex: [col,...]}
  const [fieldTab, setFieldTab] = useState("main"); // "main" | joinIndex (number)
  const [sql, setSql]       = useState("SELECT * FROM ");
  const [preview, setPreview]             = useState(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [importing, setImporting]         = useState(false);
  const [error, setError]                 = useState("");
  const [success, setSuccess]             = useState(false);

  // ── Query-Builder state ──────────────────────────────────────────────────────
  const [activeClause, setActiveClause]   = useState(null);
  const [joins, setJoins]                 = useState([]);   // [{type,table,alias,onLeft,onRight}]
  const [whereConditions, setWhereConditions] = useState([]);
  const [orderBy, setOrderBy]             = useState([]);   // [{field,dir}]
  const [groupBy, setGroupBy]             = useState([]);   // [field]

  // ── Pending JOIN editor state (one row being built) ──────────────────────────
  // When JOIN tab active, clicking a table selects it as join target.
  // Clicking a field from the MAIN table sets onLeft; from join table sets onRight.
  const [pendingJoin, setPendingJoin] = useState({ type: "INNER JOIN", table: null, alias: "", onLeft: "", onRight: "" });
  const [joinTargetCols, setJoinTargetCols] = useState([]);  // cols of pending join table

  // ── WHERE / ORDER / GROUP pending ───────────────────────────────────────────
  const [whereField, setWhereField] = useState("");
  const [whereOp, setWhereOp]       = useState("=");
  const [whereVal, setWhereVal]     = useState("");

  // ── Load connections (+ restore config on edit) ──────────────────────────────
  useEffect(() => {
    const params = projectId != null ? `?project_id=${projectId}` : "";
    api.get(`/api/connections/${params}`).then(async ({ data }) => {
      setConnections(data);
      if (editDataset?.query_config && editDataset?.source_connection_id) {
        const cfg = editDataset.query_config;
        const conn = data.find((c) => c.id === editDataset.source_connection_id);
        if (conn) {
          setSelectedConn(conn);
          const tablesRes = await api.get(`/api/connections/${conn.id}/tables`);
          setTables(tablesRes.data?.tables || []);
          if (cfg.selectedTable) {
            setSelectedTable(cfg.selectedTable);
            setTableAlias(cfg.tableAlias || "");
            setSelectedColumns(cfg.selectedColumns || []);
            const colsRes = await api.get(`/api/connections/${conn.id}/columns`, { params: { table: cfg.selectedTable } });
            setColumns(colsRes.data?.columns || []);
          }
          if (cfg.joins?.length) {
            const restored = await Promise.all(cfg.joins.map(async (j) => {
              try { const r = await api.get(`/api/connections/${conn.id}/columns`, { params: { table: j.table } }); return { ...j, _allCols: r.data?.columns || [] }; }
              catch { return j; }
            }));
            setJoins(restored);
          }
          setWhereConditions(cfg.whereConditions || []);
          setOrderBy(cfg.orderBy || []);
          setGroupBy(cfg.groupBy || []);
          setSelectedJoinColumns(cfg.selectedJoinColumns || {});
          setSql(editDataset.source_sql || "");
        }
      } else if (data.length === 1) {
        selectConn(data[0]);
      }
      setLoadingConns(false);
    });
  }, []);

  const selectConn = async (conn) => {
    setSelectedConn(conn); setTables([]); setTableSearch("");
    setSelectedTable(null); setTableAlias(""); setColumns([]); setSelectedColumns([]);
    setJoins([]); setWhereConditions([]); setOrderBy([]); setGroupBy([]);
    setPendingJoin({ type: "INNER JOIN", table: null, alias: "", onLeft: "", onRight: "" });
    setSql("SELECT * FROM "); setPreview(null); setError("");
    setLoadingTables(true);
    try { const { data } = await api.get(`/api/connections/${conn.id}/tables`); setTables(data?.tables || data || []); }
    catch { setTables([]); } finally { setLoadingTables(false); }
  };

  // ── SQL builder ──────────────────────────────────────────────────────────────
  const rebuildSql = (tbl, tblAlias, selCols, selJoinCols, jns, wheres, obs, gbs) => {
    const mainRef = tblAlias?.trim() || tbl;
    const mainPart = selCols.length === 0 ? `${mainRef}.*` : selCols.map((c) => `${mainRef}.${c}`).join(", ");
    const joinParts = jns.map((j, i) => {
      const ref = j.alias?.trim() || j.table;
      const jCols = selJoinCols[i] || [];
      return jCols.length === 0 ? `${ref}.*` : jCols.map((c) => `${ref}.${c}`).join(", ");
    });
    const allParts = [mainPart, ...joinParts];
    const selectPart = selCols.length === 0 && jns.length === 0 ? `*` : allParts.join(", ");

    const aliasStr = tblAlias?.trim() ? ` AS ${tblAlias.trim()}` : "";
    let q = `SELECT ${selectPart}\nFROM ${tbl}${aliasStr}`;
    for (const j of jns) {
      const ja = j.alias?.trim() ? ` AS ${j.alias.trim()}` : "";
      const jRef = j.alias?.trim() || j.table;
      q += `\n${j.type} ${j.table}${ja} ON ${mainRef}.${j.onLeft} = ${jRef}.${j.onRight}`;
    }
    if (wheres.length > 0) q += `\nWHERE ${wheres.map((w) => `${w.field} ${w.op}${["IS NULL","IS NOT NULL"].includes(w.op) ? "" : ` '${w.value}'`}`).join("\n  AND ")}`;
    if (gbs.length > 0) q += `\nGROUP BY ${gbs.join(", ")}`;
    if (obs.length > 0) q += `\nORDER BY ${obs.map((o) => `${o.field} ${o.dir}`).join(", ")}`;
    setSql(q); setPreview(null);
  };

  // ── Table click ──────────────────────────────────────────────────────────────
  const handleTableClick = async (tbl) => {
    if (activeClause === "join") {
      if (pendingJoin.table === tbl) return;
      setPendingJoin((p) => ({ ...p, table: tbl, onRight: "", alias: "" }));
      setJoinTargetCols([]);
      try { const { data } = await api.get(`/api/connections/${selectedConn.id}/columns`, { params: { table: tbl } }); setJoinTargetCols(data?.columns || []); }
      catch { setJoinTargetCols([]); }
      return;
    }
    setSelectedTable(tbl); setTableAlias(""); setSelectedColumns([]); setSelectedJoinColumns({});
    setJoins([]); setWhereConditions([]); setOrderBy([]); setGroupBy([]);
    setPendingJoin({ type: "INNER JOIN", table: null, alias: "", onLeft: "", onRight: "" });
    setFieldTab("main"); setPreview(null); setError(""); setName(tbl);
    setLoadingColumns(true); setColumns([]);
    try { const { data } = await api.get(`/api/connections/${selectedConn.id}/columns`, { params: { table: tbl } }); setColumns(data?.columns || []); }
    catch { setColumns([]); } finally { setLoadingColumns(false); }
    rebuildSql(tbl, "", [], {}, [], [], [], []);
  };

  // ── Field click (main table) ──────────────────────────────────────────────────
  const handleMainFieldClick = (col) => {
    if (activeClause === "where") { setWhereField(`${mainRef}.${col}`); return; }
    if (activeClause === "orderby") {
      const fqf = `${mainRef}.${col}`;
      if (!orderBy.find((o) => o.field === fqf)) {
        const next = [...orderBy, { field: fqf, dir: "ASC" }];
        setOrderBy(next); rebuildSql(selectedTable, tableAlias, selectedColumns, selectedJoinColumns, joins, whereConditions, next, groupBy);
      }
      return;
    }
    if (activeClause === "groupby") {
      const fqf = `${mainRef}.${col}`;
      if (!groupBy.includes(fqf)) {
        const next = [...groupBy, fqf];
        setGroupBy(next); rebuildSql(selectedTable, tableAlias, selectedColumns, selectedJoinColumns, joins, whereConditions, orderBy, next);
      }
      return;
    }
    const next = selectedColumns.includes(col) ? selectedColumns.filter((c) => c !== col) : [...selectedColumns, col];
    setSelectedColumns(next);
    rebuildSql(selectedTable, tableAlias, next, selectedJoinColumns, joins, whereConditions, orderBy, groupBy);
  };

  // ── Field click (join table by index) ────────────────────────────────────────
  const handleJoinFieldClick = (joinIdx, col) => {
    const jRef = joins[joinIdx]?.alias?.trim() || joins[joinIdx]?.table;
    if (activeClause === "where") { setWhereField(`${jRef}.${col}`); return; }
    if (activeClause === "orderby") {
      const fqf = `${jRef}.${col}`;
      if (!orderBy.find((o) => o.field === fqf)) {
        const next = [...orderBy, { field: fqf, dir: "ASC" }];
        setOrderBy(next); rebuildSql(selectedTable, tableAlias, selectedColumns, selectedJoinColumns, joins, whereConditions, next, groupBy);
      }
      return;
    }
    if (activeClause === "groupby") {
      const fqf = `${jRef}.${col}`;
      if (!groupBy.includes(fqf)) {
        const next = [...groupBy, fqf];
        setGroupBy(next); rebuildSql(selectedTable, tableAlias, selectedColumns, selectedJoinColumns, joins, whereConditions, orderBy, next);
      }
      return;
    }
    const prev = selectedJoinColumns[joinIdx] || [];
    const next = { ...selectedJoinColumns, [joinIdx]: prev.includes(col) ? prev.filter((c) => c !== col) : [...prev, col] };
    setSelectedJoinColumns(next);
    rebuildSql(selectedTable, tableAlias, selectedColumns, next, joins, whereConditions, orderBy, groupBy);
  };

  // ── JOIN confirm ─────────────────────────────────────────────────────────────
  const confirmJoin = () => {
    const { type, table, alias, onLeft, onRight } = pendingJoin;
    if (!table || !onLeft || !onRight) return;
    const j = { type, table, alias: alias.trim() || null, onLeft, onRight, _allCols: joinTargetCols };
    const next = [...joins, j];
    setJoins(next);
    setFieldTab(next.length - 1); // switch to new join's field tab
    setPendingJoin({ type: "INNER JOIN", table: null, alias: "", onLeft: "", onRight: "" });
    setJoinTargetCols([]);
    rebuildSql(selectedTable, tableAlias, selectedColumns, selectedJoinColumns, next, whereConditions, orderBy, groupBy);
  };

  const removeJoin = (i) => {
    const next = joins.filter((_, idx) => idx !== i);
    const nextJC = {};
    Object.entries(selectedJoinColumns).forEach(([k, v]) => { if (Number(k) !== i) nextJC[Number(k) > i ? Number(k) - 1 : Number(k)] = v; });
    setJoins(next); setSelectedJoinColumns(nextJC);
    if (fieldTab === i || (typeof fieldTab === "number" && fieldTab >= next.length)) setFieldTab("main");
    rebuildSql(selectedTable, tableAlias, selectedColumns, nextJC, next, whereConditions, orderBy, groupBy);
  };

  // ── WHERE ────────────────────────────────────────────────────────────────────
  const addWhere = () => {
    if (!whereField) return;
    const next = [...whereConditions, { field: whereField, op: whereOp, value: whereVal }];
    setWhereConditions(next); setWhereField(""); setWhereVal("");
    rebuildSql(selectedTable, tableAlias, selectedColumns, selectedJoinColumns, joins, next, orderBy, groupBy);
  };
  const removeWhere = (i) => { const next = whereConditions.filter((_, idx) => idx !== i); setWhereConditions(next); rebuildSql(selectedTable, tableAlias, selectedColumns, selectedJoinColumns, joins, next, orderBy, groupBy); };

  // ── ORDER BY ─────────────────────────────────────────────────────────────────
  const removeOrderBy = (i) => { const next = orderBy.filter((_, idx) => idx !== i); setOrderBy(next); rebuildSql(selectedTable, tableAlias, selectedColumns, selectedJoinColumns, joins, whereConditions, next, groupBy); };
  const toggleObDir = (i) => {
    const next = orderBy.map((o, idx) => idx === i ? { ...o, dir: o.dir === "ASC" ? "DESC" : "ASC" } : o);
    setOrderBy(next); rebuildSql(selectedTable, tableAlias, selectedColumns, selectedJoinColumns, joins, whereConditions, next, groupBy);
  };

  // ── GROUP BY ─────────────────────────────────────────────────────────────────
  const removeGroupBy = (i) => { const next = groupBy.filter((_, idx) => idx !== i); setGroupBy(next); rebuildSql(selectedTable, tableAlias, selectedColumns, selectedJoinColumns, joins, whereConditions, orderBy, next); };

  // ── Preview / Import ─────────────────────────────────────────────────────────
  const handlePreview = async () => {
    if (!selectedConn || !sql.trim()) return;
    setLoadingPreview(true); setError(""); setPreview(null);
    try { const { data } = await api.post(`/api/connections/${selectedConn.id}/preview`, { sql: sql.trim() }); setPreview(data); }
    catch (err) { setError(err.response?.data?.detail || "Abfrage fehlgeschlagen"); }
    finally { setLoadingPreview(false); }
  };

  const buildQueryConfig = () => ({
    selectedTable, tableAlias, selectedColumns, selectedJoinColumns, joins, whereConditions, orderBy, groupBy, connId: selectedConn?.id,
  });

  const handleImport = async () => {
    if (!selectedConn || !sql.trim() || !name.trim()) return;
    setImporting(true); setError("");
    try {
      const payload = { sql: sql.trim(), dataset_name: name.trim(), query_config: buildQueryConfig(), project_id: projectId ?? null };
      if (editDataset)
        await api.post(`/api/connections/${selectedConn.id}/reimport/${editDataset.id}`, payload);
      else
        await api.post(`/api/connections/${selectedConn.id}/import`, payload);
      setSuccess(true); setTimeout(onDone, 800);
    } catch (err) { setError(err.response?.data?.detail || "Import fehlgeschlagen"); }
    finally { setImporting(false); }
  };

  const mainRef = tableAlias?.trim() || selectedTable;
  const allFields = [
    ...(selectedTable ? columns.map((c) => `${mainRef}.${c}`) : []),
    ...joins.flatMap((j, i) => {
      const ref = j.alias?.trim() || j.table;
      return (j._allCols || []).map((c) => `${ref}.${c}`);
    }),
  ];

  const filteredTables = tables.filter((t) => t.toLowerCase().includes(tableSearch.toLowerCase()));

  const tagStyle = {
    display: "inline-flex", alignItems: "center", gap: 4,
    padding: "2px 8px", borderRadius: 4, fontSize: 10, fontFamily: "monospace",
    backgroundColor: "rgba(255,255,255,0.05)", border: `1px solid ${S.border}`, color: S.textMain,
  };

  const clauseBtn = (key, label, count) => (
    <button onClick={() => setActiveClause(activeClause === key ? null : key)}
      style={{
        padding: "4px 12px", borderRadius: 6, fontSize: 11, cursor: "pointer",
        backgroundColor: activeClause === key ? "rgba(252,228,153,0.12)" : S.bgEl,
        border: `1px solid ${activeClause === key ? S.accent : S.border}`,
        color: activeClause === key ? S.accent : S.textMain,
      }}>
      {label}{count > 0 && <span style={{ marginLeft: 5, color: S.accent }}>({count})</span>}
    </button>
  );

  if (success) return (
    <div className="flex flex-col items-center justify-center py-12 gap-3">
      <CheckCircle size={40} style={{ color: "#6ee7b7" }} />
      <p className="text-sm font-medium" style={{ color: S.textBright }}>Dataset erstellt!</p>
    </div>
  );
  if (loadingConns) return <div className="flex items-center justify-center py-12" style={{ color: S.textDim }}><Loader2 size={18} className="animate-spin mr-2" /> Lade Verbindungen…</div>;
  if (!loadingConns && connections.length === 0) return (
    <div className="text-center py-12">
      <Database size={32} className="mx-auto mb-3" style={{ color: S.textDim }} />
      <p className="text-sm" style={{ color: S.textMain }}>Keine Datenbankverbindungen</p>
      <p className="text-xs mt-1" style={{ color: S.textDim }}>Zuerst eine Verbindung unter „Datenbanken" anlegen</p>
    </div>
  );

  const typeColor = { mssql: "#93c5fd", mysql: "#6ee7b7" };
  const typeLabel = { mssql: "SQL Server", mysql: "MySQL" };

  return (
    <div className="flex flex-col gap-3" style={{ height: "calc(92vh - 110px)", minHeight: 500 }}>

      {/* ── Verbindung ── */}
      <div className="flex gap-2 flex-wrap shrink-0">
        {connections.map((conn) => (
          <button key={conn.id} onClick={() => selectConn(conn)}
            className="flex items-center gap-2 px-3 py-2 rounded-lg transition-all"
            style={{ backgroundColor: selectedConn?.id === conn.id ? "rgba(252,228,153,0.06)" : S.bgEl, border: `1px solid ${selectedConn?.id === conn.id ? S.accent : S.border}` }}>
            <Database size={13} style={{ color: typeColor[conn.db_type] || S.textDim }} />
            <span className="text-xs font-medium" style={{ color: S.textBright }}>{conn.name}</span>
            <span className="text-xs px-1.5 py-0.5 rounded font-mono" style={{ backgroundColor: "rgba(255,255,255,0.04)", color: typeColor[conn.db_type] }}>{typeLabel[conn.db_type]}</span>
          </button>
        ))}
      </div>

      {selectedConn && (
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 10, minHeight: 0 }}>

          {/* ── 3-Spalten oben: Tabellen | Felder | SQL ── */}
          <div style={{ display: "flex", gap: 10, flex: 1, minHeight: 0 }}>

            {/* Tabellenliste */}
            <div style={{ ...panelStyle(S.border, S.bgEl), width: 240, flexShrink: 0 }}>
              <div style={{ ...panelHeaderStyle(S.bgEl, S.border), padding: "5px 8px" }}>
                <input value={tableSearch} onChange={(e) => setTableSearch(e.target.value)} placeholder="Tabelle suchen…"
                  style={{ width: "100%", background: "transparent", border: "none", outline: "none", fontSize: 11, color: S.textMain }} />
              </div>
              <div style={scrollBody}>
                {loadingTables
                  ? <div style={{ display: "flex", justifyContent: "center", padding: 14 }}><Loader2 size={13} className="animate-spin" style={{ color: S.textDim }} /></div>
                  : filteredTables.map((t) => {
                    const isMain = selectedTable === t;
                    const isJoinTarget = pendingJoin.table === t;
                    const isExistingJoin = joins.some((j) => j.table === t);
                    return (
                      <button key={t} onClick={() => handleTableClick(t)} title={t}
                        style={{
                          ...rowBtn(isMain || isJoinTarget, S.accent, S.border),
                          color: isMain ? S.accent : isJoinTarget ? "#93c5fd" : isExistingJoin ? "#6ee7b7" : S.textMain,
                        }}
                        onMouseEnter={(e) => { if (!isMain && !isJoinTarget) e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.04)"; }}
                        onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = (isMain || isJoinTarget) ? "rgba(252,228,153,0.06)" : "transparent"; }}>
                        {t}
                      </button>
                    );
                  })}
              </div>
            </div>

            {/* Felder – mit Tabs: Haupttabelle + JOINs */}
            <div style={{ ...panelStyle(S.border, S.bgEl), width: 220, flexShrink: 0 }}>
              {/* Tab-Header */}
              <div style={{ display: "flex", borderBottom: `1px solid ${S.border}`, backgroundColor: S.bgEl, flexShrink: 0, overflowX: "auto" }}>
                <button onClick={() => setFieldTab("main")}
                  style={{ padding: "5px 10px", fontSize: 10, whiteSpace: "nowrap", border: "none", cursor: "pointer", borderBottom: fieldTab === "main" ? `2px solid ${S.accent}` : "2px solid transparent", color: fieldTab === "main" ? S.accent : S.textDim, backgroundColor: "transparent" }}>
                  {selectedTable ? (tableAlias?.trim() || selectedTable.split(".").pop()) : "Felder"}
                  {selectedColumns.length > 0 && <span style={{ marginLeft: 3, color: S.accent }}>({selectedColumns.length})</span>}
                </button>
                {joins.map((j, i) => {
                  const ref = j.alias?.trim() || j.table.split(".").pop();
                  const cnt = (selectedJoinColumns[i] || []).length;
                  return (
                    <button key={i} onClick={() => setFieldTab(i)}
                      style={{ padding: "5px 10px", fontSize: 10, whiteSpace: "nowrap", border: "none", cursor: "pointer", borderBottom: fieldTab === i ? `2px solid #93c5fd` : "2px solid transparent", color: fieldTab === i ? "#93c5fd" : S.textDim, backgroundColor: "transparent" }}>
                      {ref}{cnt > 0 && <span style={{ marginLeft: 3, color: "#93c5fd" }}>({cnt})</span>}
                    </button>
                  );
                })}
              </div>
              {/* Felder-Liste */}
              <div style={scrollBody}>
                {fieldTab === "main" ? (
                  !selectedTable
                    ? <div style={{ padding: "12px 10px", fontSize: 11, color: S.textDim, textAlign: "center" }}>← Tabelle wählen</div>
                    : loadingColumns
                    ? <div style={{ display: "flex", justifyContent: "center", padding: 12 }}><Loader2 size={12} className="animate-spin" style={{ color: S.textDim }} /></div>
                    : columns.map((col) => {
                      let active = selectedColumns.includes(col);
                      if (activeClause === "where") active = whereField === `${mainRef}.${col}`;
                      else if (activeClause === "orderby") active = orderBy.some((o) => o.field === `${mainRef}.${col}`);
                      else if (activeClause === "groupby") active = groupBy.includes(`${mainRef}.${col}`);
                      return (
                        <button key={col} onClick={() => handleMainFieldClick(col)} title={col}
                          style={rowBtn(active, S.accent, S.border)}
                          onMouseEnter={(e) => { if (!active) e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.04)"; }}
                          onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = active ? "rgba(252,228,153,0.06)" : "transparent"; }}>
                          <Checkbox active={active} accent={S.accent} border={S.border} />{col}
                        </button>
                      );
                    })
                ) : (() => {
                  const ji = fieldTab;
                  const j = joins[ji];
                  if (!j) return null;
                  const jCols = j._allCols || [];
                  const jRef = j.alias?.trim() || j.table;
                  const jSelected = selectedJoinColumns[ji] || [];
                  return jCols.length === 0
                    ? <div style={{ padding: "12px 10px", fontSize: 11, color: S.textDim, textAlign: "center" }}>Keine Felder</div>
                    : jCols.map((col) => {
                      let active = jSelected.includes(col);
                      if (activeClause === "where") active = whereField === `${jRef}.${col}`;
                      else if (activeClause === "orderby") active = orderBy.some((o) => o.field === `${jRef}.${col}`);
                      else if (activeClause === "groupby") active = groupBy.includes(`${jRef}.${col}`);
                      return (
                        <button key={col} onClick={() => handleJoinFieldClick(ji, col)} title={col}
                          style={{ ...rowBtn(active, "#93c5fd", S.border), color: active ? "#93c5fd" : S.textMain }}
                          onMouseEnter={(e) => { if (!active) e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.04)"; }}
                          onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = active ? "rgba(147,197,253,0.08)" : "transparent"; }}>
                          <Checkbox active={active} accent="#93c5fd" border={S.border} />{col}
                        </button>
                      );
                    });
                })()}
              </div>
            </div>

            {/* SQL Editor */}
            <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
              <div className="relative" style={{ flex: 1 }}>
                <Code2 size={12} className="absolute top-3 left-3" style={{ color: S.textDim, zIndex: 1 }} />
                <textarea value={sql} onChange={(e) => { setSql(e.target.value); setPreview(null); setError(""); }}
                  className="font-mono text-xs resize-none input"
                  style={{ paddingLeft: "2rem", lineHeight: "1.8", width: "100%", height: "100%", boxSizing: "border-box" }}
                  spellCheck={false} placeholder="SELECT * FROM tabelle …" />
              </div>
            </div>
          </div>

          {/* ── Query Builder ── */}
          <div style={{ border: `1px solid ${S.border}`, borderRadius: 8, overflow: "hidden", flexShrink: 0 }}>
            <div style={{ display: "flex", gap: 8, padding: "8px 12px", borderBottom: `1px solid ${S.border}`, backgroundColor: S.bgEl, alignItems: "center", flexWrap: "wrap" }}>
              <span style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", color: S.textDim, marginRight: 4 }}>Query Builder</span>
              {clauseBtn("join", "JOIN", joins.length)}
              {clauseBtn("where", "WHERE", whereConditions.length)}
              {clauseBtn("orderby", "ORDER BY", orderBy.length)}
              {clauseBtn("groupby", "GROUP BY", groupBy.length)}
              {selectedTable && (
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginLeft: "auto" }}>
                  <span style={{ fontSize: 10, color: S.textDim }}>FROM {selectedTable}</span>
                  <input value={tableAlias}
                    onChange={(e) => { setTableAlias(e.target.value); rebuildSql(selectedTable, e.target.value, selectedColumns, selectedJoinColumns, joins, whereConditions, orderBy, groupBy); }}
                    placeholder="AS alias"
                    style={{ width: 90, background: "transparent", border: `1px solid ${S.border}`, borderRadius: 4, outline: "none", fontSize: 10, color: "#6ee7aa", padding: "2px 7px" }} />
                </div>
              )}
            </div>

            {activeClause && (
              <div style={{ padding: 12 }}>

                {/* ── JOIN ── */}
                {activeClause === "join" && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {/* Bestehende JOINs */}
                    {joins.length > 0 && (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                        {joins.map((j, i) => (
                          <span key={i} style={tagStyle}>
                            <span style={{ color: "#93c5fd" }}>{j.type}</span>&nbsp;
                            {j.table}{j.alias ? ` AS ${j.alias}` : ""} ON&nbsp;
                            {mainRef}.{j.onLeft} = {j.alias || j.table}.{j.onRight}
                            <button onClick={() => removeJoin(i)} style={{ border: "none", background: "none", cursor: "pointer", color: S.textDim, padding: 0, marginLeft: 2 }}>×</button>
                          </span>
                        ))}
                      </div>
                    )}

                    {/* Pending JOIN – horizontale Zeile */}
                    <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
                      {/* Typ */}
                      <div>
                        <label style={labelStyle}>JOIN-Typ</label>
                        <select value={pendingJoin.type} onChange={(e) => setPendingJoin((p) => ({ ...p, type: e.target.value }))}
                          style={{ ...inputStyle, padding: "4px 8px", fontSize: 11, width: 140 }}>
                          {["INNER JOIN", "LEFT JOIN", "RIGHT JOIN", "FULL OUTER JOIN"].map((t) => <option key={t}>{t}</option>)}
                        </select>
                      </div>
                      {/* Join-Tabelle (read-only, aus Tabellenauswahl) */}
                      <div>
                        <label style={labelStyle}>Tabelle</label>
                        <div style={{ ...inputStyle, padding: "4px 10px", fontSize: 11, width: 160, color: pendingJoin.table ? "#93c5fd" : S.textDim, display: "flex", alignItems: "center" }}>
                          {pendingJoin.table || "← Tabelle anklicken"}
                        </div>
                      </div>
                      {/* Alias */}
                      <div>
                        <label style={labelStyle}>Alias</label>
                        <input value={pendingJoin.alias} onChange={(e) => setPendingJoin((p) => ({ ...p, alias: e.target.value }))}
                          placeholder="z.B. ap" style={{ ...inputStyle, padding: "4px 8px", fontSize: 11, width: 80 }} />
                      </div>
                      {/* ON links – Dropdown */}
                      <div>
                        <label style={labelStyle}>ON – {mainRef || "Haupttabelle"}</label>
                        <select value={pendingJoin.onLeft} onChange={(e) => setPendingJoin((p) => ({ ...p, onLeft: e.target.value }))}
                          style={{ ...inputStyle, padding: "4px 8px", fontSize: 11, width: 180 }}>
                          <option value="">Feld wählen…</option>
                          {columns.map((c) => <option key={c} value={c}>{mainRef}.{c}</option>)}
                        </select>
                      </div>
                      {/* ON rechts – Dropdown */}
                      <div>
                        <label style={labelStyle}>ON – {pendingJoin.alias || pendingJoin.table || "JOIN-Tabelle"}</label>
                        <select value={pendingJoin.onRight} onChange={(e) => setPendingJoin((p) => ({ ...p, onRight: e.target.value }))}
                          style={{ ...inputStyle, padding: "4px 8px", fontSize: 11, width: 180 }}
                          disabled={!pendingJoin.table}>
                          <option value="">Feld wählen…</option>
                          {joinTargetCols.map((c) => <option key={c} value={c}>{pendingJoin.alias || pendingJoin.table}.{c}</option>)}
                        </select>
                      </div>
                      {/* Confirm */}
                      <button onClick={confirmJoin}
                        disabled={!pendingJoin.table || !pendingJoin.onLeft || !pendingJoin.onRight}
                        className="btn-primary text-xs" style={{ marginBottom: 1 }}>
                        + JOIN hinzufügen
                      </button>
                    </div>
                    <p style={{ fontSize: 10, color: S.textDim }}>
                      Workflow: 1) JOIN-Tabelle in der Tabellenliste anklicken → 2) JOIN-Typ + Alias wählen → 3) ON-Felder in den Dropdowns wählen → 4) bestätigen
                    </p>
                  </div>
                )}

                {/* ── WHERE ── */}
                {activeClause === "where" && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {whereConditions.length > 0 && (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                        {whereConditions.map((w, i) => (
                          <span key={i} style={tagStyle}>
                            {w.field} <span style={{ color: "#fcd34d" }}>{w.op}</span>
                            {!["IS NULL","IS NOT NULL"].includes(w.op) && ` '${w.value}'`}
                            <button onClick={() => removeWhere(i)} style={{ border: "none", background: "none", cursor: "pointer", color: S.textDim, padding: 0, marginLeft: 2 }}>×</button>
                          </span>
                        ))}
                      </div>
                    )}
                    <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
                      <div style={{ flex: 2, minWidth: 140 }}>
                        <label style={labelStyle}>Feld <span style={{ color: S.textDim }}>(oder Feldliste anklicken)</span></label>
                        <select value={whereField} onChange={(e) => setWhereField(e.target.value)}
                          style={{ ...inputStyle, padding: "4px 8px", fontSize: 11 }}>
                          <option value="">Feld wählen…</option>
                          {allFields.map((f) => <option key={f}>{f}</option>)}
                        </select>
                      </div>
                      <div style={{ width: 120 }}>
                        <label style={labelStyle}>Operator</label>
                        <select value={whereOp} onChange={(e) => setWhereOp(e.target.value)}
                          style={{ ...inputStyle, padding: "4px 8px", fontSize: 11 }}>
                          {["=","!=",">","<",">=","<=","LIKE","NOT LIKE","IN","IS NULL","IS NOT NULL"].map((o) => <option key={o}>{o}</option>)}
                        </select>
                      </div>
                      {!["IS NULL","IS NOT NULL"].includes(whereOp) && (
                        <div style={{ flex: 2, minWidth: 120 }}>
                          <label style={labelStyle}>Wert</label>
                          <input value={whereVal} onChange={(e) => setWhereVal(e.target.value)} placeholder="Wert…"
                            style={{ ...inputStyle, padding: "4px 8px", fontSize: 11 }} />
                        </div>
                      )}
                      <button onClick={addWhere} disabled={!whereField} className="btn-primary text-xs">+ Bedingung</button>
                    </div>
                  </div>
                )}

                {/* ── ORDER BY ── */}
                {activeClause === "orderby" && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    <p style={{ fontSize: 10, color: S.textDim }}>Felder in der Feldliste anklicken um sie hinzuzufügen. Richtung umschalten durch Klick auf ASC/DESC.</p>
                    {orderBy.length > 0 && (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                        {orderBy.map((o, i) => (
                          <span key={i} style={tagStyle}>
                            {o.field}&nbsp;
                            <button onClick={() => toggleObDir(i)}
                              style={{ border: `1px solid ${S.border}`, borderRadius: 3, background: "rgba(255,255,255,0.05)", cursor: "pointer", color: "#6ee7b7", padding: "0 4px", fontSize: 9 }}>
                              {o.dir}
                            </button>
                            <button onClick={() => removeOrderBy(i)} style={{ border: "none", background: "none", cursor: "pointer", color: S.textDim, padding: 0, marginLeft: 2 }}>×</button>
                          </span>
                        ))}
                      </div>
                    )}
                    {orderBy.length === 0 && <div style={{ color: S.textDim, fontSize: 11 }}>Noch keine Sortierfelder. Felder links anklicken.</div>}
                  </div>
                )}

                {/* ── GROUP BY ── */}
                {activeClause === "groupby" && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    <p style={{ fontSize: 10, color: S.textDim }}>Felder in der Feldliste anklicken um sie hinzuzufügen.</p>
                    {groupBy.length > 0 && (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                        {groupBy.map((g, i) => (
                          <span key={i} style={tagStyle}>
                            {g}
                            <button onClick={() => removeGroupBy(i)} style={{ border: "none", background: "none", cursor: "pointer", color: S.textDim, padding: 0, marginLeft: 2 }}>×</button>
                          </span>
                        ))}
                      </div>
                    )}
                    {groupBy.length === 0 && <div style={{ color: S.textDim, fontSize: 11 }}>Noch keine Gruppierfelder. Felder links anklicken.</div>}
                  </div>
                )}

              </div>
            )}
          </div>

          {/* ── Fehler ── */}
          {error && (
            <div className="flex items-center gap-2 text-xs px-3 py-2 rounded shrink-0"
              style={{ backgroundColor: "rgba(220,50,50,0.08)", border: "1px solid rgba(220,50,50,0.2)", color: "#e07070" }}>
              <AlertCircle size={13} /> {error}
            </div>
          )}

          {/* ── Vorschau-Modal ── */}
          {preview && (
            <div className="fixed inset-0 z-60 flex items-center justify-center p-4"
              style={{ backgroundColor: "rgba(0,0,0,0.6)", backdropFilter: "blur(3px)" }}
              onClick={() => setPreview(null)}>
              <div className="rounded-2xl flex flex-col" style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`, width: "96vw", maxWidth: 1600, height: "88vh", overflow: "hidden" }}
                onClick={(e) => e.stopPropagation()}>
                <div className="flex items-center justify-between px-5 py-3 shrink-0" style={{ borderBottom: `1px solid ${S.border}`, backgroundColor: S.bgEl }}>
                  <span className="text-xs font-semibold" style={{ color: S.textBright }}>
                    Vorschau – <span style={{ color: S.textMain, fontWeight: 400 }}>{preview.total_rows} Zeilen · {preview.columns?.length} Spalten</span>
                  </span>
                  <button onClick={() => setPreview(null)} style={{ color: S.textDim, background: "none", border: "none", cursor: "pointer" }}><X size={15} /></button>
                </div>
                <div className="overflow-auto flex-1" style={{ scrollbarWidth: "thin" }}>
                  <table className="text-xs border-collapse w-full">
                    <thead className="sticky top-0">
                      <tr style={{ backgroundColor: S.bgEl }}>
                        {preview.columns?.map((col) => (
                          <th key={col} className="text-left px-3 py-2 font-mono font-medium whitespace-nowrap"
                            style={{ color: S.accent, borderRight: `1px solid ${S.border}`, borderBottom: `1px solid ${S.border}` }}>{col}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {preview.rows?.map((row, i) => (
                        <tr key={i} style={{ borderTop: `1px solid ${S.border}` }}>
                          {preview.columns?.map((col) => (
                            <td key={col} className="px-3 py-1.5 font-mono whitespace-nowrap"
                              style={{ color: S.textMain, borderRight: `1px solid ${S.border}`, maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis" }}>
                              {row[col] ?? <span style={{ color: S.textDim }}>null</span>}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* ── Actions ── */}
          <div className="flex items-center gap-3 shrink-0">
            <button onClick={handlePreview} disabled={loadingPreview || !sql.trim()} className="btn-ghost text-xs">
              {loadingPreview && <Loader2 size={12} className="animate-spin" />} Vorschau
            </button>
            <button onClick={handleImport} disabled={importing || !name.trim() || !sql.trim()} className="btn-primary text-xs ml-auto">
              {importing ? <Loader2 size={12} className="animate-spin" /> : <ChevronRight size={12} />}
              {editDataset ? "Dataset aktualisieren" : "Als Dataset speichern"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Main Wizard ──────────────────────────────────────────────────────────────
export default function NewDatasetWizard({ onDone, onCancel, editDataset, projectId = null }) {
  const [step, setStep] = useState(editDataset ? "sql" : "choose");
  const [dsName, setDsName] = useState(editDataset?.name || "");

  const titles = { choose: "Neues Dataset", file: "Datei hochladen" };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: "rgba(0,0,0,0.75)", backdropFilter: "blur(4px)" }}>
      <div className={`w-full rounded-2xl flex flex-col ${step === "sql" ? "max-w-screen-xl" : "max-w-lg"}`}
        style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`, maxHeight: "92vh", overflow: "hidden" }}>

        {/* ── Header ── */}
        <div className="flex items-center justify-between px-6 py-4 shrink-0"
          style={{ borderBottom: `1px solid ${S.border}` }}>
          <div className="flex items-center gap-3 flex-1 min-w-0">
            {step !== "choose" && !editDataset && (
              <button onClick={() => { setStep("choose"); setDsName(""); }} className="p-1 rounded transition-colors"
                style={{ color: S.textDim, flexShrink: 0 }}
                onMouseEnter={(e) => (e.currentTarget.style.color = S.textMain)}
                onMouseLeave={(e) => (e.currentTarget.style.color = S.textDim)}>
                <ChevronLeft size={16} />
              </button>
            )}
            <h2 className="text-sm font-semibold shrink-0" style={{ color: S.textBright }}>
              {editDataset ? "SQL-Dataset bearbeiten" : step === "sql" ? "SQL-Abfrage" : titles[step]}
            </h2>
            {step === "sql" && (
              <input
                value={dsName}
                onChange={(e) => setDsName(e.target.value)}
                placeholder="Dataset-Name…"
                style={{
                  marginLeft: 12, flex: 1, minWidth: 0,
                  backgroundColor: "transparent",
                  border: `1px solid ${dsName.trim() ? "rgba(110,231,170,0.5)" : "rgba(220,80,80,0.4)"}`,
                  borderRadius: 6, padding: "3px 10px", fontSize: 12,
                  color: dsName.trim() ? "#6ee7aa" : "#e07070",
                  outline: "none",
                }}
              />
            )}
          </div>
          <button onClick={onCancel} className="p-1.5 rounded transition-colors shrink-0 ml-3" style={{ color: S.textDim }}
            onMouseEnter={(e) => (e.currentTarget.style.color = S.textMain)}
            onMouseLeave={(e) => (e.currentTarget.style.color = S.textDim)}>
            <X size={16} />
          </button>
        </div>

        {/* ── Content ── */}
        <div className="flex-1 overflow-y-auto px-6 py-5" style={{ scrollbarWidth: "thin" }}>
          {step === "choose" && <StepChoose onChoose={(p) => setStep(p)} />}
          {step === "file" && <StepFileUpload onDone={onDone} projectId={projectId} />}
          {step === "sql" && <StepSqlQuery onDone={onDone} name={dsName} setName={setDsName} editDataset={editDataset} projectId={projectId} />}
        </div>
      </div>
    </div>
  );
}
