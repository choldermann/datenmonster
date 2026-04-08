import { useState, useEffect } from "react";
import { RefreshCw, Trash2, ChevronDown, ChevronRight, X, Filter } from "lucide-react";
import api from "../../../api/client";
import { S } from "../constants";

const LOG_COLOR = { info: "#6ee7b7", warning: "#fce499", error: "#e07070" };
const LOG_BG = { info: "rgba(110,231,183,0.06)", warning: "rgba(252,228,153,0.06)", error: "rgba(224,112,112,0.06)" };
const LOG_BORDER = { info: "rgba(110,231,183,0.2)", warning: "rgba(252,228,153,0.2)", error: "rgba(224,112,112,0.2)" };

const MODULES = ["mapping", "scheduler", "ftp", "dispatcher", "rest", "import"];

function formatDuration(ms) {
  if (!ms) return null;
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatDate(str) {
  if (!str) return "";
  const d = new Date(str);
  return d.toLocaleString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function DiffBadge({ before, after }) {
  if (before == null || after == null) return null;
  const diff = after - before;
  return (
    <span style={{ fontSize: 9, fontWeight: 700, padding: "1px 5px", borderRadius: 3, backgroundColor: diff > 0 ? "rgba(110,231,183,0.15)" : diff < 0 ? "rgba(224,112,112,0.15)" : "rgba(255,255,255,0.05)", color: diff > 0 ? "#6ee7b7" : diff < 0 ? "#e07070" : S.textDim }}>
      {diff > 0 ? "+" : ""}{diff} Zeilen
    </span>
  );
}

function LogRow({ log }) {
  const [expanded, setExpanded] = useState(false);
  const color = LOG_COLOR[log.level] || S.textDim;
  const hasDetails = log.details && Object.keys(log.details).length > 0;
  const hasDiff = log.rows_before != null && log.rows_after != null;

  return (
    <div style={{ borderBottom: `1px solid ${S.border}`, backgroundColor: expanded ? LOG_BG[log.level] : "transparent" }}>
      <div
        style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 12px", cursor: hasDetails || hasDiff ? "pointer" : "default" }}
        onClick={() => (hasDetails || hasDiff) && setExpanded(v => !v)}>

        {/* Level Badge */}
        <span style={{ fontSize: 8, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", padding: "2px 6px", borderRadius: 3, backgroundColor: LOG_BG[log.level], color, border: `1px solid ${LOG_BORDER[log.level]}`, flexShrink: 0, width: 52, textAlign: "center" }}>
          {log.level}
        </span>

        {/* Modul */}
        <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: S.textDim, flexShrink: 0, width: 70 }}>
          {log.module}
        </span>

        {/* Message */}
        <span style={{ fontSize: 11, color: S.textMain, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {log.entity_name && <span style={{ color: S.textDim }}>{log.entity_name} · </span>}
          {log.message}
        </span>

        {/* Badges */}
        <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
          {log.rows_processed != null && (
            <span style={{ fontSize: 9, color: S.textDim }}>{log.rows_processed.toLocaleString()} Zeilen</span>
          )}
          {hasDiff && <DiffBadge before={log.rows_before} after={log.rows_after} />}
          {log.duration_ms != null && (
            <span style={{ fontSize: 9, color: S.textDim }}>{formatDuration(log.duration_ms)}</span>
          )}
          <span style={{ fontSize: 9, color: S.textDim, flexShrink: 0 }}>{formatDate(log.created_at)}</span>
          {(hasDetails || hasDiff) && (
            expanded ? <ChevronDown size={12} style={{ color: S.textDim }} /> : <ChevronRight size={12} style={{ color: S.textDim }} />
          )}
        </div>
      </div>

      {/* Details */}
      {expanded && (
        <div style={{ padding: "0 12px 10px 12px" }}>
          {hasDiff && (
            <div style={{ display: "flex", gap: 12, marginBottom: 8 }}>
              <span style={{ fontSize: 10, color: S.textDim }}>Vorher: <strong style={{ color: S.textBright }}>{log.rows_before?.toLocaleString()}</strong></span>
              <span style={{ fontSize: 10, color: S.textDim }}>Nachher: <strong style={{ color: S.textBright }}>{log.rows_after?.toLocaleString()}</strong></span>
              <DiffBadge before={log.rows_before} after={log.rows_after} />
            </div>
          )}
          {hasDetails && (
            <pre style={{ fontSize: 10, color: S.textDim, backgroundColor: S.bgEl, borderRadius: 4, padding: "8px 10px", overflow: "auto", maxHeight: 200, margin: 0, fontFamily: "monospace" }}>
              {JSON.stringify(log.details, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

export default function LogPanel({ projectId }) {
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ level: "", module: "", search: "" });
  const [offset, setOffset] = useState(0);
  const LIMIT = 50;

  const fetchLogs = async (resetOffset = true) => {
    setLoading(true);
    try {
      const params = { limit: LIMIT, offset: resetOffset ? 0 : offset };
      if (filters.level) params.level = filters.level;
      if (filters.module) params.module = filters.module;
      if (projectId) params.project_id = projectId;
      const { data } = await api.get("/api/logs/", { params });
      if (resetOffset) {
        setLogs(data.logs || []);
        setOffset(LIMIT);
      } else {
        setLogs(prev => [...prev, ...(data.logs || [])]);
        setOffset(prev => prev + LIMIT);
      }
      setTotal(data.total || 0);
    } catch (e) {
      console.error("Log fetch error:", e);
    } finally {
      setLoading(false);
    }
  };

  const load = fetchLogs;

  useEffect(() => { fetchLogs(true); }, [filters.level, filters.module, projectId]);

  const clearLogs = async () => {
    if (!window.confirm("Logs älter als 30 Tage löschen?")) return;
    await api.delete("/api/logs/");
    load(true);
  };

  const filteredLogs = filters.search
    ? logs.filter(l => l.message?.toLowerCase().includes(filters.search.toLowerCase()) || l.entity_name?.toLowerCase().includes(filters.search.toLowerCase()))
    : logs;

  const iS = { backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, color: S.textBright, fontSize: 11, padding: "5px 8px", outline: "none" };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>

      {/* Header */}
      <div style={{ padding: "14px 20px", borderBottom: `1px solid ${S.border}`, display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
        <div style={{ flex: 1 }}>
          <h2 style={{ fontSize: 14, fontWeight: 700, color: S.textBright, margin: 0 }}>System-Log</h2>
          <p style={{ fontSize: 10, color: S.textDim, marginTop: 2 }}>{total.toLocaleString()} Einträge gesamt</p>
        </div>
        <button onClick={() => load(true)} style={{ padding: "5px 10px", borderRadius: 4, border: `1px solid ${S.border}`, background: "none", color: S.textDim, cursor: "pointer", display: "flex", alignItems: "center", gap: 4, fontSize: 11 }}>
          <RefreshCw size={11} /> Aktualisieren
        </button>
        <button onClick={clearLogs} style={{ padding: "5px 10px", borderRadius: 4, border: `1px solid rgba(224,112,112,0.3)`, background: "none", color: "#e07070", cursor: "pointer", display: "flex", alignItems: "center", gap: 4, fontSize: 11 }}>
          <Trash2 size={11} /> Alte löschen
        </button>
      </div>

      {/* Filter Bar */}
      <div style={{ padding: "10px 20px", borderBottom: `1px solid ${S.border}`, display: "flex", gap: 8, flexShrink: 0, flexWrap: "wrap" }}>
        {/* Level Filter */}
        <div style={{ display: "flex", gap: 4 }}>
          {["", "info", "warning", "error"].map(lvl => (
            <button key={lvl} onClick={() => { setFilters(f => ({ ...f, level: lvl })); setOffset(0); }}
              style={{ padding: "3px 10px", borderRadius: 4, fontSize: 10, fontWeight: 600, cursor: "pointer", border: `1px solid ${filters.level === lvl ? (LOG_COLOR[lvl] || S.accent) : S.border}`, backgroundColor: filters.level === lvl ? (LOG_BG[lvl] || "rgba(252,228,153,0.1)") : "transparent", color: filters.level === lvl ? (LOG_COLOR[lvl] || S.accent) : S.textDim }}>
              {lvl || "Alle Level"}
            </button>
          ))}
        </div>

        {/* Modul Filter */}
        <select style={iS} value={filters.module} onChange={e => { setFilters(f => ({ ...f, module: e.target.value })); setOffset(0); }}>
          <option value="">Alle Module</option>
          {MODULES.map(m => <option key={m} value={m}>{m}</option>)}
        </select>

        {/* Suche */}
        <div style={{ display: "flex", alignItems: "center", gap: 6, flex: 1, minWidth: 200, backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, padding: "0 8px" }}>
          <Filter size={11} style={{ color: S.textDim }} />
          <input value={filters.search} onChange={e => setFilters(f => ({ ...f, search: e.target.value }))}
            placeholder="Suche in Nachrichten..."
            style={{ background: "none", border: "none", outline: "none", fontSize: 11, color: S.textBright, flex: 1, padding: "5px 0" }} />
          {filters.search && <button onClick={() => setFilters(f => ({ ...f, search: "" }))} style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0 }}><X size={10} /></button>}
        </div>
      </div>

      {/* Log Liste */}
      <div style={{ flex: 1, overflowY: "auto", scrollbarWidth: "thin" }}>
        {loading && logs.length === 0 && (
          <div style={{ padding: 40, textAlign: "center", color: S.textDim, fontSize: 12 }}>Lade Logs...</div>
        )}
        {!loading && filteredLogs.length === 0 && (
          <div style={{ padding: 40, textAlign: "center", color: S.textDim, fontSize: 12 }}>Keine Log-Einträge gefunden</div>
        )}
        {filteredLogs.map(log => <LogRow key={log.id} log={log} />)}

        {/* Mehr laden */}
        {logs.length < total && !filters.search && (
          <div style={{ padding: 12, textAlign: "center" }}>
            <button onClick={() => { setOffset(logs.length); load(false); }}
              style={{ padding: "6px 16px", borderRadius: 4, border: `1px solid ${S.border}`, background: "none", color: S.textDim, cursor: "pointer", fontSize: 11 }}>
              {loading ? "Lade..." : `Mehr laden (${total - logs.length} weitere)`}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
