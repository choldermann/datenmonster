import { useState, useEffect, useRef, useCallback } from "react";
import { Database, Table, ChevronRight, ChevronDown, Search, X, Play, Check } from "lucide-react";
import api from "../../api/client";
import { S, SQL_NODE_COLOR } from "./constants";

const SQLITE_COLOR = "#34d399";

export default function SqlEditorModal({ sql, connectionId, dbConnections, canvasNodes, onSave, onClose }) {
  const [sqlValue, setSqlValue] = useState(sql || "");
  const [activeConn, setActiveConn] = useState(connectionId || null);

  // Tables
  const [tables, setTables] = useState([]);
  const [tablesLoading, setTablesLoading] = useState(false);
  const [tableSearch, setTableSearch] = useState("");
  const [expandedTable, setExpandedTable] = useState(null);
  const [tableFields, setTableFields] = useState({}); // tableName → [fields]
  const [fieldsLoading, setFieldsLoading] = useState(null);

  // SQLite datasets
  const [sqliteDatasets, setSqliteDatasets] = useState([]);
  const [sqliteFields, setSqliteFields] = useState({}); // dsId → [fields]
  const [expandedSqlite, setExpandedSqlite] = useState(null);

  // Source mode: "db" or "sqlite"
  const [sourceMode, setSourceMode] = useState("db");

  // Preview
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewResult, setPreviewResult] = useState(null);

  const textareaRef = useRef(null);

  // Load tables when connection changes
  useEffect(() => {
    if (!activeConn || sourceMode !== "db") return;
    setTablesLoading(true);
    setTables([]);
    api.get(`/api/connections/${activeConn}/tables-only`)
      .then(({ data }) => setTables(data.tables || []))
      .catch(() => {})
      .finally(() => setTablesLoading(false));
  }, [activeConn, sourceMode]);

  // Load SQLite datasets from canvas
  useEffect(() => {
    if (sourceMode !== "sqlite") return;
    const dsIds = (canvasNodes || []).map(n => n.dataset_id).filter(Boolean);
    setSqliteDatasets(dsIds);
  }, [sourceMode, canvasNodes]);

  const loadTableFields = useCallback(async (tableName) => {
    if (tableFields[tableName]) {
      setExpandedTable(t => t === tableName ? null : tableName);
      return;
    }
    setFieldsLoading(tableName);
    try {
      const { data } = await api.get(`/api/connections/${activeConn}/columns`, { params: { table: tableName } });
      setTableFields(prev => ({ ...prev, [tableName]: data.columns || [] }));
      setExpandedTable(tableName);
    } catch {
      setTableFields(prev => ({ ...prev, [tableName]: [] }));
      setExpandedTable(tableName);
    } finally {
      setFieldsLoading(null);
    }
  }, [activeConn, tableFields]);

  const loadSqliteFields = useCallback(async (dsId) => {
    if (sqliteFields[dsId]) {
      setExpandedSqlite(id => id === dsId ? null : dsId);
      return;
    }
    try {
      const { data } = await api.get(`/api/datasets/${dsId}`);
      setSqliteFields(prev => ({ ...prev, [dsId]: data.columns || [] }));
      setExpandedSqlite(dsId);
    } catch {
      setSqliteFields(prev => ({ ...prev, [dsId]: [] }));
      setExpandedSqlite(dsId);
    }
  }, [sqliteFields]);

  const insertAtCursor = (text) => {
    const ta = textareaRef.current;
    if (!ta) { setSqlValue(v => v + text); return; }
    const start = ta.selectionStart;
    const end = ta.selectionEnd;
    const newVal = sqlValue.slice(0, start) + text + sqlValue.slice(end);
    setSqlValue(newVal);
    setTimeout(() => {
      ta.selectionStart = ta.selectionEnd = start + text.length;
      ta.focus();
    }, 0);
  };

  const handleTableClick = (tableName) => {
    if (sourceMode === "db") {
      loadTableFields(tableName);
    }
  };

  const handleTableDoubleClick = (tableName) => {
    insertAtCursor(tableName);
  };

  const handleFieldClick = (field) => {
    insertAtCursor(field);
  };

  const runPreview = async () => {
    if (!sqlValue.trim()) return;
    setPreviewLoading(true);
    setPreviewResult(null);
    try {
      const { data } = await api.post("/api/mappings/sql-schema", {
        sql: sqlValue,
        connection_id: activeConn,
        canvas_nodes: canvasNodes || [],
        external_tables: [],
      });
      setPreviewResult({ columns: data.columns, error: data.error });
    } catch (e) {
      setPreviewResult({ error: e.message });
    } finally {
      setPreviewLoading(false);
    }
  };

  const filteredTables = tables.filter(t =>
    !tableSearch || t.toLowerCase().includes(tableSearch.toLowerCase())
  );

  const iS = {
    backgroundColor: S.bgMain,
    border: `1px solid ${S.border}`,
    color: S.textBright,
    borderRadius: 4,
    padding: "5px 8px",
    fontSize: 11,
    outline: "none",
    width: "100%",
  };

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 200, display: "flex", alignItems: "center", justifyContent: "center", backgroundColor: "rgba(0,0,0,0.85)" }}
      onClick={(e) => e.stopPropagation()}>
      <div style={{ width: "min(1100px, 95vw)", height: "85vh", display: "flex", flexDirection: "column", backgroundColor: S.bgCard, borderRadius: 10, border: `1px solid ${SQL_NODE_COLOR}44`, boxShadow: "0 32px 80px rgba(0,0,0,0.9)", overflow: "hidden" }}>

        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 18px", borderBottom: `1px solid ${SQL_NODE_COLOR}33`, backgroundColor: `${SQL_NODE_COLOR}0d`, flexShrink: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Database size={14} style={{ color: SQL_NODE_COLOR }} />
            <span style={{ fontSize: 13, fontWeight: 700, color: SQL_NODE_COLOR, letterSpacing: "0.06em" }}>SQL EDITOR</span>
            {/* Connection Selector */}
            <select value={activeConn || ""} onChange={e => setActiveConn(parseInt(e.target.value) || null)}
              style={{ ...iS, width: "auto", fontSize: 11, color: SQL_NODE_COLOR }}>
              <option value="">– Verbindung –</option>
              {(dbConnections || []).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
          <button onClick={onClose} style={{ color: S.textDim, background: "none", border: "none", cursor: "pointer", fontSize: 18, lineHeight: 1 }}
            onMouseEnter={e => e.currentTarget.style.color = "#e07070"}
            onMouseLeave={e => e.currentTarget.style.color = S.textDim}>✕</button>
        </div>

        {/* Body */}
        <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>

          {/* Left: Table Browser */}
          <div style={{ width: 220, borderRight: `1px solid ${S.border}`, display: "flex", flexDirection: "column", flexShrink: 0 }}>
            {/* Source mode tabs */}
            <div style={{ display: "flex", borderBottom: `1px solid ${S.border}`, flexShrink: 0 }}>
              {[["db", "DB", SQL_NODE_COLOR], ["sqlite", "SQLite", SQLITE_COLOR]].map(([mode, label, color]) => (
                <button key={mode} onClick={() => setSourceMode(mode)}
                  style={{ flex: 1, padding: "7px 0", fontSize: 10, fontWeight: 700, cursor: "pointer", background: "none", border: "none",
                    borderBottom: `2px solid ${sourceMode === mode ? color : "transparent"}`,
                    color: sourceMode === mode ? color : S.textDim }}>
                  {label}
                </button>
              ))}
            </div>

            {sourceMode === "db" && (
              <>
                <div style={{ padding: "6px 8px", borderBottom: `1px solid ${S.border}`, flexShrink: 0 }}>
                  <div style={{ position: "relative" }}>
                    <Search size={10} style={{ position: "absolute", left: 6, top: "50%", transform: "translateY(-50%)", color: S.textDim }} />
                    <input value={tableSearch} onChange={e => setTableSearch(e.target.value)}
                      placeholder="Tabelle suchen..."
                      style={{ ...iS, paddingLeft: 22, fontSize: 10 }} />
                  </div>
                </div>
                <div style={{ flex: 1, overflowY: "auto", scrollbarWidth: "thin" }}>
                  {tablesLoading && <p style={{ fontSize: 10, color: S.textDim, padding: "8px 10px" }}>Lädt...</p>}
                  {!tablesLoading && !activeConn && <p style={{ fontSize: 10, color: S.textDim, padding: "8px 10px" }}>Verbindung wählen</p>}
                  {filteredTables.map(tbl => (
                    <div key={tbl}>
                      <div onClick={() => handleTableClick(tbl)}
                        onDoubleClick={() => handleTableDoubleClick(tbl)}
                        style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 10px", cursor: "pointer", userSelect: "none",
                          backgroundColor: expandedTable === tbl ? `${SQL_NODE_COLOR}12` : "transparent" }}
                        onMouseEnter={e => e.currentTarget.style.backgroundColor = `${SQL_NODE_COLOR}08`}
                        onMouseLeave={e => e.currentTarget.style.backgroundColor = expandedTable === tbl ? `${SQL_NODE_COLOR}12` : "transparent"}>
                        {fieldsLoading === tbl
                          ? <span style={{ fontSize: 9, color: S.textDim }}>…</span>
                          : expandedTable === tbl
                            ? <ChevronDown size={9} style={{ color: SQL_NODE_COLOR, flexShrink: 0 }} />
                            : <ChevronRight size={9} style={{ color: S.textDim, flexShrink: 0 }} />}
                        <Table size={9} style={{ color: SQL_NODE_COLOR, flexShrink: 0 }} />
                        <span style={{ fontSize: 10, color: S.textMain, fontFamily: "monospace", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{tbl}</span>
                      </div>
                      {expandedTable === tbl && (tableFields[tbl] || []).map(col => (
                        <div key={col.name || col} onClick={() => handleFieldClick(col.name || col)}
                          style={{ display: "flex", alignItems: "center", gap: 5, padding: "3px 10px 3px 26px", cursor: "pointer" }}
                          onMouseEnter={e => e.currentTarget.style.backgroundColor = `${SQL_NODE_COLOR}08`}
                          onMouseLeave={e => e.currentTarget.style.backgroundColor = "transparent"}>
                          <span style={{ fontSize: 8, color: "#6a6a6a", backgroundColor: "#6a6a6a18", borderRadius: 2, padding: "1px 3px", fontFamily: "monospace", flexShrink: 0 }}>
                            {(col.type || col.raw || "").slice(0, 4).toUpperCase()}
                          </span>
                          <span style={{ fontSize: 10, color: S.textDim, fontFamily: "monospace" }}>{col.name || col}</span>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </>
            )}

            {sourceMode === "sqlite" && (
              <div style={{ flex: 1, overflowY: "auto", scrollbarWidth: "thin" }}>
                {sqliteDatasets.length === 0
                  ? <p style={{ fontSize: 10, color: S.textDim, padding: "8px 10px" }}>Keine Datasets im Canvas</p>
                  : sqliteDatasets.map(dsId => {
                      const node = (canvasNodes || []).find(n => n.dataset_id === dsId);
                      const dsName = node?.dataset_name || node?.name || `Dataset ${dsId}`;
                      const safeName = dsName.replace(/[^a-zA-Z0-9_]/g, "_");
                      return (
                        <div key={dsId}>
                          <div onClick={() => loadSqliteFields(dsId)}
                            onDoubleClick={() => insertAtCursor(safeName)}
                            style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 10px", cursor: "pointer", userSelect: "none",
                              backgroundColor: expandedSqlite === dsId ? `${SQLITE_COLOR}12` : "transparent" }}
                            onMouseEnter={e => e.currentTarget.style.backgroundColor = `${SQLITE_COLOR}08`}
                            onMouseLeave={e => e.currentTarget.style.backgroundColor = expandedSqlite === dsId ? `${SQLITE_COLOR}12` : "transparent"}>
                            {expandedSqlite === dsId
                              ? <ChevronDown size={9} style={{ color: SQLITE_COLOR, flexShrink: 0 }} />
                              : <ChevronRight size={9} style={{ color: S.textDim, flexShrink: 0 }} />}
                            <Table size={9} style={{ color: SQLITE_COLOR, flexShrink: 0 }} />
                            <span style={{ fontSize: 10, color: S.textMain, fontFamily: "monospace", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{safeName}</span>
                          </div>
                          {expandedSqlite === dsId && (sqliteFields[dsId] || []).map(col => (
                            <div key={col} onClick={() => handleFieldClick(col)}
                              style={{ padding: "3px 10px 3px 26px", cursor: "pointer", fontSize: 10, color: S.textDim, fontFamily: "monospace" }}
                              onMouseEnter={e => e.currentTarget.style.backgroundColor = `${SQLITE_COLOR}08`}
                              onMouseLeave={e => e.currentTarget.style.backgroundColor = "transparent"}>
                              {col}
                            </div>
                          ))}
                        </div>
                      );
                    })
                }
              </div>
            )}
          </div>

          {/* Right: SQL Editor */}
          <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
            <textarea
              ref={textareaRef}
              autoFocus
              value={sqlValue}
              onChange={e => setSqlValue(e.target.value)}
              onClick={e => e.stopPropagation()}
              spellCheck={false}
              placeholder="SQL hier eingeben...&#10;&#10;Tabellen/Felder links anklicken zum Einfügen&#10;Doppelklick auf Tabelle fügt Namen ein"
              style={{ flex: 1, backgroundColor: S.bgMain, border: "none", borderBottom: `1px solid ${S.border}`, color: S.textBright, fontSize: 13, fontFamily: "monospace", padding: "16px 20px", outline: "none", resize: "none", lineHeight: 1.7 }}
            />

            {/* Preview strip */}
            {previewResult && (
              <div style={{ padding: "6px 16px", backgroundColor: previewResult.error ? "rgba(224,112,112,0.06)" : "rgba(52,211,153,0.06)", borderBottom: `1px solid ${S.border}`, flexShrink: 0 }}>
                {previewResult.error
                  ? <span style={{ fontSize: 10, color: "#e07070" }}>⚠ {previewResult.error}</span>
                  : <span style={{ fontSize: 10, color: SQLITE_COLOR }}>✓ Spalten erkannt: {previewResult.columns.join(", ")}</span>
                }
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 18px", borderTop: `1px solid ${S.border}`, flexShrink: 0, backgroundColor: S.bgEl }}>
          <button onClick={runPreview} disabled={previewLoading || !sqlValue.trim()}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 14px", borderRadius: 5, border: `1px solid ${S.border}`, background: S.bgMain, color: S.textDim, cursor: "pointer", fontSize: 11, opacity: !sqlValue.trim() ? 0.4 : 1 }}
            onMouseEnter={e => { if (sqlValue.trim()) e.currentTarget.style.color = S.textBright; }}
            onMouseLeave={e => e.currentTarget.style.color = S.textDim}>
            <Play size={11} />
            {previewLoading ? "Prüft..." : "Schema prüfen"}
          </button>
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={onClose}
              style={{ padding: "7px 20px", borderRadius: 5, border: `1px solid ${S.border}`, background: "none", color: S.textDim, cursor: "pointer", fontSize: 12 }}
              onMouseEnter={e => e.currentTarget.style.color = S.textBright}
              onMouseLeave={e => e.currentTarget.style.color = S.textDim}>
              Abbrechen
            </button>
            <button onClick={() => onSave(sqlValue)}
              style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 22px", borderRadius: 5, border: `1px solid ${SQL_NODE_COLOR}`, background: `${SQL_NODE_COLOR}22`, color: SQL_NODE_COLOR, cursor: "pointer", fontSize: 12, fontWeight: 700 }}
              onMouseEnter={e => e.currentTarget.style.background = `${SQL_NODE_COLOR}33`}
              onMouseLeave={e => e.currentTarget.style.background = `${SQL_NODE_COLOR}22`}>
              <Check size={13} />
              Speichern
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
