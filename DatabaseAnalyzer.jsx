import { useState, useEffect, useRef, useCallback } from "react";
import { Loader2, X, ZoomIn, ZoomOut, Maximize2, Search, ChevronRight, AlertTriangle, Download } from "lucide-react";
import api from "../api/client";
import { S } from "./dashboard/constants";

const TYPE_COLORS = { integer: "#93c5fd", decimal: "#6ee7b7", date: "#fcd34d", boolean: "#c4b5fd", string: "#6a6a6a" };
const TYPE_LABELS = { integer: "INT", decimal: "DEC", date: "DAT", boolean: "BOL", string: "STR" };
const FK_COLOR = "#6ee7b7";
const IMPLICIT_COLOR = "#fcd34d";
const NODE_W = 220;
const NODE_HEADER = 36;
const ROW_H = 22;
const NODE_PADDING = 8;

function computeLayout(tables) {
  const cols = Math.max(1, Math.ceil(Math.sqrt(tables.length * 0.7)));
  const positions = {};
  tables.forEach((t, i) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    positions[t.key] = {
      x: col * (NODE_W + 80) + 40,
      y: row * 300 + 40,
      w: NODE_W,
      h: NODE_HEADER + NODE_PADDING + t.columns.length * ROW_H + NODE_PADDING,
    };
  });
  return positions;
}

export default function DatabaseAnalyzer({ connection, onClose, projectId = null, onDatasetsImported }) {
  const [phase, setPhase] = useState("config"); // config | loading | done | error
  const [progress, setProgress] = useState(0);
  const [progressMsg, setProgressMsg] = useState("Verbinde mit Datenbank...");
  const [schema, setSchema] = useState(null);
  const [error, setError] = useState(null);
  const [positions, setPositions] = useState({});
  const [dragging, setDragging] = useState(null);
  const [selected, setSelected] = useState(null);
  const [zoom, setZoom] = useState(0.75);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [panDragging, setPanDragging] = useState(null);
  const [search, setSearch] = useState("");
  const [showImplicit, setShowImplicit] = useState(true);
  const [tableLimit, setTableLimit] = useState(25);
  const [schemaFilter, setSchemaFilter] = useState("");
  const [availableSchemas, setAvailableSchemas] = useState([]);
  const [tableFilter, setTableFilter] = useState("");
  const [includeRelated, setIncludeRelated] = useState(true);
  const [startTable, setStartTable] = useState("");
  const [traversalDepth, setTraversalDepth] = useState(2);
  const [markedTables, setMarkedTables] = useState(new Set()); // markierte Tabellen für Import
  const [hiddenTables, setHiddenTables] = useState(new Set()); // ausgeblendete Nodes
  const [confirmRemove, setConfirmRemove] = useState(null); // { tableKey, tableName }
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null); // { done, failed }
  const svgRef = useRef(null);

  const toggleMark = (tableKey) => {
    setMarkedTables(prev => {
      const next = new Set(prev);
      if (next.has(tableKey)) next.delete(tableKey);
      else next.add(tableKey);
      return next;
    });
  };

  const importMarkedTables = async () => {
    if (!markedTables.size || !projectId) return;
    setImporting(true);
    setImportResult(null);
    let done = 0, failed = [];
    for (const tableKey of markedTables) {
      const table = schema.tables.find(t => t.key === tableKey);
      if (!table) continue;
      // SQL generieren
      const sql = table.schema && table.schema !== "dbo"
        ? `SELECT * FROM [${table.schema}].[${table.name}]`
        : `SELECT * FROM [${table.name}]`;
      const datasetName = table.name;
      try {
        await api.post(`/api/connections/${connection.id}/import`, {
          sql,
          dataset_name: datasetName,
          project_id: projectId,
        });
        done++;
      } catch (e) {
        failed.push(table.name);
      }
    }
    setImporting(false);
    setImportResult({ done, failed });
    setMarkedTables(new Set());
  };

  const startAnalysis = useCallback(async () => {
    setPhase("loading");
    setProgress(5);
    setProgressMsg("Verbinde mit Datenbank...");
    setError(null);
    const steps = [
      [800,  15, "Lade Tabellenliste..."],
      [2000, 35, "Lese Spalten und Typen..."],
      [4000, 55, "Ermittle Primary Keys..."],
      [6000, 70, "Analysiere Foreign Keys..."],
      [9000, 85, "Erkenne implizite Beziehungen..."],
    ];
    const timers = steps.map(([ms, pct, msg]) =>
      setTimeout(() => { setProgress(pct); setProgressMsg(msg); }, ms)
    );
    try {
      const params = new URLSearchParams({ table_limit: tableLimit, implicit_limit: 300, timeout: 60 });
      if (schemaFilter) params.append("schema_filter", schemaFilter);
      if (startTable.trim()) {
        params.append("start_table", startTable.trim());
        params.append("depth", traversalDepth);
      } else if (tableFilter.trim()) {
        params.append("table_filter", tableFilter.trim());
        params.append("include_related", includeRelated ? "true" : "false");
      }
      const { data } = await api.get(`/api/connections/${connection.id}/analyze?${params}`);
      timers.forEach(clearTimeout);
      setProgress(100);
      setProgressMsg("Fertig!");
      setSchema(data);
      setPositions(computeLayout(data.tables));
      if (data.available_schemas?.length > 0) setAvailableSchemas(data.available_schemas);
      setTimeout(() => setPhase("done"), 400);
    } catch (e) {
      timers.forEach(clearTimeout);
      setError(e.response?.data?.detail || e.message);
      setPhase("error");
    }
  }, [connection.id, tableLimit, schemaFilter, startTable, traversalDepth]);

  const startNodeDrag = (e, tableKey) => {
    e.stopPropagation();
    const pos = positions[tableKey];
    setDragging({ tableKey, startX: e.clientX, startY: e.clientY, origX: pos.x, origY: pos.y });
  };

  useEffect(() => {
    if (!dragging) return;
    const onMove = (e) => {
      const dx = (e.clientX - dragging.startX) / zoom;
      const dy = (e.clientY - dragging.startY) / zoom;
      setPositions(prev => ({ ...prev, [dragging.tableKey]: { ...prev[dragging.tableKey], x: dragging.origX + dx, y: dragging.origY + dy } }));
    };
    const onUp = () => setDragging(null);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
  }, [dragging, zoom]);

  const startPan = (e) => {
    if (e.target !== svgRef.current) return;
    setPanDragging({ startX: e.clientX - pan.x, startY: e.clientY - pan.y });
  };

  useEffect(() => {
    if (!panDragging) return;
    const onMove = (e) => setPan({ x: e.clientX - panDragging.startX, y: e.clientY - panDragging.startY });
    const onUp = () => setPanDragging(null);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
  }, [panDragging]);

  const onWheel = (e) => {
    e.preventDefault();
    setZoom(z => Math.min(2, Math.max(0.2, z - e.deltaY * 0.001)));
  };

  const fitScreen = () => {
    if (!schema?.tables.length) return;
    const xs = schema.tables.map(t => positions[t.key]?.x || 0);
    const ys = schema.tables.map(t => positions[t.key]?.y || 0);
    setPan({ x: -(Math.min(...xs)) * zoom + 40, y: -(Math.min(...ys)) * zoom + 40 });
  };

  const exportPng = () => {
    if (!schema?.tables.length) return;

    const visibleTables = schema.tables.filter(t => !hiddenTables.has(t.key));
    if (!visibleTables.length) return;

    const padding = 40;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    visibleTables.forEach(t => {
      const pos = positions[t.key];
      if (!pos) return;
      const h = NODE_HEADER + NODE_PADDING + t.columns.length * ROW_H + NODE_PADDING;
      minX = Math.min(minX, pos.x);
      minY = Math.min(minY, pos.y);
      maxX = Math.max(maxX, pos.x + pos.w);
      maxY = Math.max(maxY, pos.y + h);
    });

    const contentW = maxX - minX + padding * 2;
    const contentH = maxY - minY + padding * 2;
    const scale = 2;

    const svg = svgRef.current;
    if (!svg) return;

    const clone = svg.cloneNode(true);
    clone.setAttribute("viewBox", `${minX - padding} ${minY - padding} ${contentW} ${contentH}`);
    clone.setAttribute("width", contentW);
    clone.setAttribute("height", contentH);

    // Echte CSS-Variablen-Werte vom Browser auslesen
    const rootStyles = getComputedStyle(document.documentElement);
    const getVar = (v) => {
      const raw = v.trim();
      if (raw.startsWith("var(")) {
        const varName = raw.slice(4, -1).trim();
        return rootStyles.getPropertyValue(varName).trim() || "#888";
      }
      return raw;
    };

    // Alle CSS-Variablen die im SVG vorkommen könnten
    const cssVarMap = {};
    ["--bg-card","--bg-main","--bg-elevated","--border","--text-main","--text-bright","--text-dim","--accent"].forEach(v => {
      const val = rootStyles.getPropertyValue(v).trim();
      if (val) {
        cssVarMap[`var(${v})`] = val;
        cssVarMap[v] = val;
      }
    });

    // Alle Attribute in allen Elementen ersetzen
    const replaceVars = (el) => {
      ["fill", "stroke", "color", "background", "background-color"].forEach(attr => {
        const val = el.getAttribute(attr);
        if (val && cssVarMap[val]) el.setAttribute(attr, cssVarMap[val]);
      });
      const style = el.getAttribute("style");
      if (style) {
        let newStyle = style;
        Object.entries(cssVarMap).forEach(([k, v]) => {
          newStyle = newStyle.replaceAll(k, v);
        });
        el.setAttribute("style", newStyle);
      }
      Array.from(el.children || []).forEach(replaceVars);
    };
    replaceVars(clone);

    // Inline-Style für Text-Farben
    const styleEl = document.createElement("style");
    styleEl.textContent = `
      text { font-family: 'Courier New', monospace; }
    `;
    clone.insertBefore(styleEl, clone.firstChild);

    const serializer = new XMLSerializer();
    let svgStr = serializer.serializeToString(clone);

    // Nochmal CSS-Variablen im serialisierten String ersetzen (Fallback)
    Object.entries(cssVarMap).forEach(([k, v]) => {
      svgStr = svgStr.replaceAll(k, v);
    });

    const svgBlob = new Blob([svgStr], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(svgBlob);

    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width  = contentW * scale;
      canvas.height = contentH * scale;
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#0d0d0d";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.scale(scale, scale);
      ctx.drawImage(img, 0, 0);
      URL.revokeObjectURL(url);
      const link = document.createElement("a");
      link.download = `schema_${connection.name.replace(/[^a-z0-9]/gi, "_")}.png`;
      link.href = canvas.toDataURL("image/png");
      link.click();
    };
    img.onerror = () => URL.revokeObjectURL(url);
    img.src = url;
  };

  const computeEdges = () => {
    if (!schema) return [];
    return schema.relationships
      .filter(r => showImplicit || r.type === "foreign_key")
      .filter(r => !hiddenTables.has(r.from_table) && !hiddenTables.has(r.to_table))
      .map(rel => {
        const from = positions[rel.from_table];
        const to = positions[rel.to_table];
        if (!from || !to) return null;
        const fromTable = schema.tables.find(t => t.key === rel.from_table);
        const toTable = schema.tables.find(t => t.key === rel.to_table);
        if (!fromTable || !toTable) return null;
        const fromColIdx = fromTable.columns.findIndex(c => c.name === rel.from_col);
        const toColIdx = toTable.columns.findIndex(c => c.name === rel.to_col);
        const fromY = from.y + NODE_HEADER + NODE_PADDING + (fromColIdx >= 0 ? fromColIdx * ROW_H + ROW_H / 2 : ROW_H / 2);
        const toY = to.y + NODE_HEADER + NODE_PADDING + (toColIdx >= 0 ? toColIdx * ROW_H + ROW_H / 2 : ROW_H / 2);
        const cx = (from.x + from.w + to.x) / 2;
        return { ...rel, path: `M ${from.x + from.w} ${fromY} C ${cx} ${fromY} ${cx} ${toY} ${to.x} ${toY}`, color: rel.type === "foreign_key" ? FK_COLOR : IMPLICIT_COLOR };
      }).filter(Boolean);
  };

  const filteredTables = schema?.tables.filter(t => !hiddenTables.has(t.key) && (!search || t.key.toLowerCase().includes(search.toLowerCase()))) || [];
  const edges = phase === "done" ? computeEdges() : [];

  // ── Config ────────────────────────────────────────────────────────────────
  if (phase === "config") return (
    <div style={{ position: "fixed", inset: 0, zIndex: 200, backgroundColor: "rgba(0,0,0,0.85)", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`, borderRadius: 12, padding: "28px 32px", width: 440, boxShadow: "0 24px 60px rgba(0,0,0,0.7)" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
          <p style={{ fontSize: 15, fontWeight: 700, color: S.textBright, margin: 0 }}>Schema analysieren</p>
          <button onClick={onClose} style={{ color: S.textDim, background: "none", border: "none", cursor: "pointer" }}><X size={16} /></button>
        </div>
        <p style={{ fontSize: 12, color: S.textDim, marginBottom: 20 }}>
          <strong style={{ color: S.textMain }}>{connection.name}</strong> · {connection.db_type?.toUpperCase()} · {connection.host}
        </p>
        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 11, fontWeight: 600, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.05em", display: "block", marginBottom: 6 }}>Max. Tabellen</label>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {[5, 10, 25, 50, 100].map(n => (
              <button key={n} onClick={() => setTableLimit(n)} style={{ fontSize: 12, padding: "5px 14px", borderRadius: 4, cursor: "pointer", border: `1px solid ${tableLimit === n ? S.accent : S.border}`, backgroundColor: tableLimit === n ? "rgba(252,228,153,0.1)" : "transparent", color: tableLimit === n ? S.accent : S.textDim }}>{n}</button>
            ))}
          </div>
          <p style={{ fontSize: 10, color: S.textDim, marginTop: 6 }}>Harter Stopp – gilt auch bei Starttabelle. Mehr Tabellen = längere Ladezeit.</p>
        </div>
        <div style={{ marginBottom: 20 }}>
          <label style={{ fontSize: 11, fontWeight: 600, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.05em", display: "block", marginBottom: 6 }}>Schema-Filter (optional)</label>
          {availableSchemas.length > 0 ? (
            <select value={schemaFilter} onChange={e => setSchemaFilter(e.target.value)}
              style={{ backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, color: S.textMain, fontSize: 12, padding: "7px 10px", width: "100%", boxSizing: "border-box" }}>
              <option value="">Alle Schemas</option>
              {availableSchemas.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          ) : (
            <input value={schemaFilter} onChange={e => setSchemaFilter(e.target.value)}
              placeholder="z.B. dbo, Amazon, eBay..."
              style={{ backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, color: S.textMain, fontSize: 12, padding: "7px 10px", width: "100%", boxSizing: "border-box", outline: "none" }} />
          )}
          <p style={{ fontSize: 10, color: S.textDim, marginTop: 6 }}>Nur Tabellen aus diesem Schema laden. Leer = alle Schemas.</p>
        </div>
        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 11, fontWeight: 600, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.05em", display: "block", marginBottom: 6 }}>Tabellenfilter (optional)</label>
          <input value={tableFilter} onChange={e => setTableFilter(e.target.value)}
            placeholder="z.B. Rechnung, Artikel, Kunde..."
            disabled={!!startTable.trim()}
            style={{ backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, color: startTable.trim() ? S.textDim : S.textMain, fontSize: 12, padding: "7px 10px", width: "100%", boxSizing: "border-box", outline: "none", opacity: startTable.trim() ? 0.4 : 1 }} />
          <p style={{ fontSize: 10, color: S.textDim, marginTop: 6 }}>Nur Tabellen laden deren Name diesen Text enthält. Wird ignoriert wenn Starttabelle gesetzt.</p>
          {tableFilter.trim() && !startTable.trim() && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
              <input type="checkbox" id="include-related" checked={includeRelated} onChange={e => setIncludeRelated(e.target.checked)}
                style={{ accentColor: S.accent, cursor: "pointer", width: 14, height: 14 }} />
              <label htmlFor="include-related" style={{ fontSize: 12, color: S.textMain, cursor: "pointer" }}>
                Verknüpfte Tabellen einbeziehen
              </label>
            </div>
          )}
        </div>

        <div style={{ marginBottom: 20, padding: "12px 14px", borderRadius: 6, border: `1px solid ${startTable.trim() ? "rgba(252,228,153,0.3)" : S.border}`, backgroundColor: startTable.trim() ? "rgba(252,228,153,0.04)" : "transparent" }}>
          <label style={{ fontSize: 11, fontWeight: 600, color: startTable.trim() ? S.accent : S.textDim, textTransform: "uppercase", letterSpacing: "0.05em", display: "block", marginBottom: 6 }}>
            Starttabelle (optional)
          </label>
          <input value={startTable} onChange={e => setStartTable(e.target.value)}
            placeholder="z.B. tRechnung oder dbo.tRechnung"
            style={{ backgroundColor: S.bgEl, border: `1px solid ${startTable.trim() ? "rgba(252,228,153,0.4)" : S.border}`, borderRadius: 4, color: S.textMain, fontSize: 12, padding: "7px 10px", width: "100%", boxSizing: "border-box", outline: "none" }} />
          <p style={{ fontSize: 10, color: S.textDim, marginTop: 6 }}>
            Traversiert den FK-Graphen ab dieser Tabelle in alle Richtungen. Tabellenfilter wird dann ignoriert.
          </p>
          {startTable.trim() && (
            <div style={{ marginTop: 10 }}>
              <label style={{ fontSize: 11, fontWeight: 600, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.05em", display: "block", marginBottom: 6 }}>Traversierungstiefe</label>
              <div style={{ display: "flex", gap: 6 }}>
                {[1, 2, 3].map(d => (
                  <button key={d} onClick={() => setTraversalDepth(d)} style={{
                    fontSize: 12, padding: "5px 16px", borderRadius: 4, cursor: "pointer",
                    border: `1px solid ${traversalDepth === d ? S.accent : S.border}`,
                    backgroundColor: traversalDepth === d ? "rgba(252,228,153,0.1)" : "transparent",
                    color: traversalDepth === d ? S.accent : S.textDim,
                  }}>
                    {d === 1 ? "1 – Direkt" : d === 2 ? "2 – Erweitert" : "3 – Tief"}
                  </button>
                ))}
              </div>
              <p style={{ fontSize: 10, color: S.textDim, marginTop: 6 }}>
                Tiefe 1 = nur direkte Nachbarn · Tiefe 2 = auch deren Nachbarn · Tiefe 3 = drei Ebenen
              </p>
            </div>
          )}
        </div>

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button onClick={onClose} style={{ fontSize: 12, padding: "8px 16px", borderRadius: 6, cursor: "pointer", background: "transparent", border: `1px solid ${S.border}`, color: S.textDim }}>Abbrechen</button>
          <button onClick={startAnalysis} style={{ fontSize: 12, fontWeight: 600, padding: "8px 20px", borderRadius: 6, cursor: "pointer", background: "rgba(252,228,153,0.15)", border: "1px solid rgba(252,228,153,0.4)", color: S.accent }}>Analysieren</button>
        </div>
      </div>
    </div>
  );

  // ── Loading ───────────────────────────────────────────────────────────────
  if (phase === "loading") return (
    <div style={{ position: "fixed", inset: 0, zIndex: 200, backgroundColor: "rgba(0,0,0,0.85)", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`, borderRadius: 12, padding: "32px 40px", width: 420, textAlign: "center", boxShadow: "0 24px 60px rgba(0,0,0,0.7)" }}>
        <Loader2 size={32} style={{ color: S.accent, margin: "0 auto 16px" }} className="animate-spin" />
        <p style={{ fontSize: 14, fontWeight: 600, color: S.textBright, marginBottom: 8 }}>Analysiere Schema...</p>
        <p style={{ fontSize: 12, color: S.textDim, marginBottom: 20 }}>{progressMsg}</p>
        <div style={{ height: 6, backgroundColor: S.bgEl, borderRadius: 3, overflow: "hidden" }}>
          <div style={{ height: "100%", borderRadius: 3, backgroundColor: S.accent, width: `${progress}%`, transition: "width 0.5s ease" }} />
        </div>
        <p style={{ fontSize: 11, color: S.textDim, marginTop: 8 }}>{progress}%</p>
        <button onClick={() => setPhase("config")} style={{ marginTop: 16, fontSize: 11, color: S.textDim, background: "none", border: "none", cursor: "pointer", textDecoration: "underline" }}>Abbrechen</button>
      </div>
    </div>
  );

  // ── Error ─────────────────────────────────────────────────────────────────
  if (phase === "error") return (
    <div style={{ position: "fixed", inset: 0, zIndex: 200, backgroundColor: "rgba(0,0,0,0.85)", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ backgroundColor: S.bgCard, border: "1px solid rgba(248,113,113,0.3)", borderRadius: 12, padding: "28px 32px", width: 440, boxShadow: "0 24px 60px rgba(0,0,0,0.7)" }}>
        <p style={{ fontSize: 14, fontWeight: 700, color: "#f87171", marginBottom: 12 }}>Analyse fehlgeschlagen</p>
        <p style={{ fontSize: 12, color: S.textDim, marginBottom: 20 }}>{error}</p>
        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 11, fontWeight: 600, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.05em", display: "block", marginBottom: 6 }}>Tabellenfilter (optional)</label>
          <input value={tableFilter} onChange={e => setTableFilter(e.target.value)}
            placeholder="z.B. Rechnung, Artikel, Kunde..."
            disabled={!!startTable.trim()}
            style={{ backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, color: startTable.trim() ? S.textDim : S.textMain, fontSize: 12, padding: "7px 10px", width: "100%", boxSizing: "border-box", outline: "none", opacity: startTable.trim() ? 0.4 : 1 }} />
          <p style={{ fontSize: 10, color: S.textDim, marginTop: 6 }}>Nur Tabellen laden deren Name diesen Text enthält. Wird ignoriert wenn Starttabelle gesetzt.</p>
          {tableFilter.trim() && !startTable.trim() && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
              <input type="checkbox" id="include-related" checked={includeRelated} onChange={e => setIncludeRelated(e.target.checked)}
                style={{ accentColor: S.accent, cursor: "pointer", width: 14, height: 14 }} />
              <label htmlFor="include-related" style={{ fontSize: 12, color: S.textMain, cursor: "pointer" }}>
                Verknüpfte Tabellen einbeziehen
              </label>
            </div>
          )}
        </div>
        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 11, fontWeight: 600, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.05em", display: "block", marginBottom: 6 }}>Starttabelle (optional)</label>
          <input value={startTable} onChange={e => setStartTable(e.target.value)}
            placeholder="z.B. tRechnung oder dbo.tRechnung"
            style={{ backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, color: S.textMain, fontSize: 12, padding: "7px 10px", width: "100%", boxSizing: "border-box", outline: "none" }} />
        </div>

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button onClick={onClose} style={{ fontSize: 12, padding: "7px 14px", borderRadius: 6, background: "transparent", border: `1px solid ${S.border}`, color: S.textDim, cursor: "pointer" }}>Schliessen</button>
          <button onClick={() => setPhase("config")} style={{ fontSize: 12, padding: "7px 14px", borderRadius: 6, background: "rgba(252,228,153,0.1)", border: "1px solid rgba(252,228,153,0.3)", color: S.accent, cursor: "pointer" }}>Einstellungen anpassen</button>
        </div>
      </div>
    </div>
  );

  // ── ER-Diagramm ───────────────────────────────────────────────────────────
  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 200, display: "flex", flexDirection: "column", backgroundColor: "#0a0a0a" }}>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 16px", borderBottom: `1px solid ${S.border}`, backgroundColor: S.bgCard, flexShrink: 0 }}>
        <span style={{ fontSize: 14, fontWeight: 700, color: S.textBright }}>Database Analyzer</span>
        <span style={{ fontSize: 11, color: S.textDim, fontFamily: "monospace" }}>{connection.name} · {connection.db_type?.toUpperCase()}</span>
        {schema && <span style={{ fontSize: 11, color: S.textDim }}>{schema.table_count} Tabellen · {schema.explicit_count} FK · {schema.implicit_count} implizit</span>}
        {schema && startTable.trim() && (
          <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 4, backgroundColor: "rgba(252,228,153,0.12)", border: "1px solid rgba(252,228,153,0.3)", color: S.accent }}>
            ⚓ {startTable.trim()} · Tiefe {traversalDepth}
          </span>
        )}
        <div style={{ flex: 1 }} />
        {availableSchemas.length > 1 && (
          <select value={schemaFilter} onChange={e => { setSchemaFilter(e.target.value); setPhase("config"); }}
            style={{ backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, color: S.textMain, fontSize: 11, padding: "4px 8px" }}>
            <option value="">Alle Schemas</option>
            {availableSchemas.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        )}
        <div style={{ position: "relative" }}>
          <Search size={12} style={{ position: "absolute", left: 8, top: "50%", transform: "translateY(-50%)", color: S.textDim }} />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Tabelle suchen..."
            style={{ backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, color: S.textMain, fontSize: 11, padding: "5px 8px 5px 26px", width: 160, outline: "none" }} />
        </div>
        <button onClick={() => setShowImplicit(v => !v)} style={{ fontSize: 10, padding: "4px 10px", borderRadius: 4, cursor: "pointer", border: `1px solid ${showImplicit ? IMPLICIT_COLOR + "66" : S.border}`, backgroundColor: showImplicit ? IMPLICIT_COLOR + "15" : "transparent", color: showImplicit ? IMPLICIT_COLOR : S.textDim }}>
          Implizit
        </button>
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <button onClick={() => setZoom(z => Math.max(0.2, z - 0.1))} style={{ color: S.textDim, background: "none", border: "none", cursor: "pointer" }}><ZoomOut size={14} /></button>
          <span style={{ fontSize: 10, color: S.textDim, minWidth: 36, textAlign: "center" }}>{Math.round(zoom * 100)}%</span>
          <button onClick={() => setZoom(z => Math.min(2, z + 0.1))} style={{ color: S.textDim, background: "none", border: "none", cursor: "pointer" }}><ZoomIn size={14} /></button>
          <button onClick={fitScreen} style={{ color: S.textDim, background: "none", border: "none", cursor: "pointer" }} title="Fit to screen"><Maximize2 size={14} /></button>
          <button onClick={exportPng} style={{ color: S.textDim, background: "none", border: "none", cursor: "pointer" }} title="Als PNG exportieren"><Download size={14} /></button>
        </div>
        {hiddenTables.size > 0 && (
          <button onClick={() => setHiddenTables(new Set())} style={{
            fontSize: 10, padding: "4px 10px", borderRadius: 4, cursor: "pointer",
            border: "1px solid rgba(251,191,36,0.4)", backgroundColor: "rgba(251,191,36,0.08)", color: "#fbbf24",
          }}>↺ {hiddenTables.size} einblenden</button>
        )}
        <button onClick={() => setPhase("config")} style={{ fontSize: 10, padding: "4px 10px", borderRadius: 4, cursor: "pointer", border: `1px solid ${S.border}`, backgroundColor: "transparent", color: S.textDim }}>
          Einstellungen
        </button>
        {markedTables.size > 0 && (
          <button onClick={importMarkedTables} disabled={importing || !projectId} style={{
            fontSize: 11, fontWeight: 600, padding: "5px 14px", borderRadius: 4, cursor: importing ? "wait" : "pointer",
            border: "1px solid rgba(110,231,183,0.4)", backgroundColor: "rgba(110,231,183,0.12)", color: "#6ee7b7",
            display: "flex", alignItems: "center", gap: 6,
          }}>
            {importing ? <Loader2 size={11} className="animate-spin" /> : null}
            {importing ? "Importiere..." : `${markedTables.size} Dataset${markedTables.size > 1 ? "s" : ""} importieren`}
          </button>
        )}
        <button onClick={onClose} style={{ color: S.textDim, background: "none", border: "none", cursor: "pointer" }}><X size={16} /></button>
      </div>

      {/* Legende + Truncated-Warnung */}
      <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "6px 16px", backgroundColor: S.bgCard, borderBottom: `1px solid ${S.border}`, flexShrink: 0, flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 10, color: FK_COLOR }}>
          <div style={{ width: 20, height: 2, backgroundColor: FK_COLOR }} /> Foreign Key
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 10, color: IMPLICIT_COLOR }}>
          <div style={{ width: 20, height: 0, borderTop: `2px dashed ${IMPLICIT_COLOR}` }} /> Implizit
        </div>
        <span style={{ fontSize: 10, color: S.textDim }}>Klick = Details · Ziehen = Verschieben · Mausrad = Zoom · Hintergrund ziehen = Pan</span>
        {schema?.truncated && (
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginLeft: "auto", fontSize: 11, color: "#fbbf24", padding: "3px 10px", borderRadius: 4, backgroundColor: "rgba(251,191,36,0.1)", border: "1px solid rgba(251,191,36,0.25)" }}>
            <AlertTriangle size={12} />
            {schema.truncated_msg}
            <button onClick={() => setPhase("config")} style={{ marginLeft: 4, fontSize: 10, color: "#fbbf24", background: "none", border: "none", cursor: "pointer", textDecoration: "underline" }}>Anpassen</button>
          </div>
        )}
      </div>

      {/* Canvas */}
      <div style={{ flex: 1, overflow: "hidden", position: "relative", cursor: panDragging ? "grabbing" : "grab" }}>
        <svg ref={svgRef} style={{ width: "100%", height: "100%", userSelect: "none" }} onMouseDown={startPan} onWheel={onWheel}>
          <g transform={`translate(${pan.x},${pan.y}) scale(${zoom})`}>
            {edges.map((edge, i) => (
              <path key={i} d={edge.path} fill="none" stroke={edge.color}
                strokeWidth={edge.type === "foreign_key" ? 1.5 : 1}
                strokeDasharray={edge.type === "implicit" ? "4 3" : undefined}
                strokeOpacity={0.5} />
            ))}
            {filteredTables.map((table) => {
              const pos = positions[table.key];
              if (!pos) return null;
              const isSelected = selected?.key === table.key;
              const nodeH = NODE_HEADER + NODE_PADDING + table.columns.length * ROW_H + NODE_PADDING;
              return (
                <g key={table.key} transform={`translate(${pos.x},${pos.y})`}
                  onMouseDown={(e) => startNodeDrag(e, table.key)}
                  onClick={() => setSelected(isSelected ? null : table)}
                  style={{ cursor: dragging?.tableKey === table.key ? "grabbing" : "pointer" }}>
                  <rect x={3} y={3} width={pos.w} height={nodeH} rx={6} fill="rgba(0,0,0,0.4)" />
                  <rect x={0} y={0} width={pos.w} height={nodeH} rx={6} fill={S.bgCard} stroke={isSelected ? S.accent : S.border} strokeWidth={isSelected ? 2 : 1} />
                  <rect x={0} y={0} width={pos.w} height={NODE_HEADER} rx={6} fill={isSelected ? "rgba(252,228,153,0.12)" : "rgba(255,255,255,0.04)"} />
                  <rect x={0} y={NODE_HEADER - 6} width={pos.w} height={6} fill={isSelected ? "rgba(252,228,153,0.12)" : "rgba(255,255,255,0.04)"} />
                  {table.schema && table.schema !== "dbo" && <text x={10} y={14} fontSize={8} fill={S.textDim} fontFamily="monospace">{table.schema}</text>}
                  <text x={10} y={table.schema && table.schema !== "dbo" ? 27 : 22} fontSize={12} fontWeight={700} fill={isSelected ? S.accent : S.textBright} fontFamily="monospace" style={{ pointerEvents: "none" }}>
                    {table.name.length > 22 ? table.name.slice(0, 22) + "..." : table.name}
                  </text>
                  {table.row_count != null && <text x={pos.w - 10} y={22} fontSize={9} fill={S.textDim} textAnchor="end" fontFamily="monospace">{table.row_count.toLocaleString()}</text>}
                  {markedTables.has(table.key) && (
                    <rect x={pos.w - 44} y={2} width={20} height={20} rx={4} fill="rgba(110,231,183,0.25)" stroke="#6ee7b7" strokeWidth={1} />
                  )}
                  {markedTables.has(table.key) && (
                    <text x={pos.w - 34} y={16} fontSize={12} fontWeight={700} fill="#6ee7b7" textAnchor="middle">✓</text>
                  )}
                  {/* X-Button zum Entfernen */}
                  <g onClick={(e) => { e.stopPropagation(); setConfirmRemove({ tableKey: table.key, tableName: table.name }); }}
                    style={{ cursor: "pointer" }}
                    onMouseEnter={e => e.currentTarget.querySelector("rect").setAttribute("fill", "rgba(224,112,112,0.3)")}
                    onMouseLeave={e => e.currentTarget.querySelector("rect").setAttribute("fill", "rgba(224,112,112,0.1)")}>
                    <rect x={pos.w - 22} y={2} width={20} height={20} rx={4} fill="rgba(224,112,112,0.1)" stroke="rgba(224,112,112,0.3)" strokeWidth={1} />
                    <text x={pos.w - 12} y={16} fontSize={11} fontWeight={700} fill="#e07070" textAnchor="middle">✕</text>
                  </g>
                  <line x1={0} y1={NODE_HEADER} x2={pos.w} y2={NODE_HEADER} stroke={S.border} strokeWidth={1} />
                  {table.columns.map((col, ci) => {
                    const cy = NODE_HEADER + NODE_PADDING + ci * ROW_H;
                    const tc = TYPE_COLORS[col.type] || "#6a6a6a";
                    const tl = TYPE_LABELS[col.type] || col.type?.slice(0, 3).toUpperCase();
                    return (
                      <g key={col.name}>
                        <rect x={1} y={cy} width={pos.w - 2} height={ROW_H} fill="transparent"
                          onMouseEnter={e => e.currentTarget.setAttribute("fill", "rgba(255,255,255,0.03)")}
                          onMouseLeave={e => e.currentTarget.setAttribute("fill", "transparent")} />
                        {col.is_primary && <text x={8} y={cy + 14} fontSize={10} fill="#fbbf24">PK</text>}
                        <rect x={col.is_primary ? 28 : 8} y={cy + 4} width={28} height={14} rx={2} fill={tc + "20"} />
                        <text x={col.is_primary ? 42 : 22} y={cy + 14} fontSize={8} fontWeight={700} fill={tc} textAnchor="middle" fontFamily="monospace">{tl}</text>
                        <text x={col.is_primary ? 62 : 42} y={cy + 14} fontSize={10} fill={col.is_primary ? S.textBright : S.textMain} fontFamily="monospace" style={{ pointerEvents: "none" }}>
                          {col.name.length > 22 ? col.name.slice(0, 22) + "..." : col.name}
                        </text>
                      </g>
                    );
                  })}
                </g>
              );
            })}
          </g>
        </svg>
      </div>

      {/* Import Ergebnis Modal */}
      {importResult && (
        <div style={{ position: "absolute", inset: 0, zIndex: 50, backgroundColor: "rgba(0,0,0,0.7)",
          display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`, borderRadius: 10,
            padding: "24px 28px", width: 380, boxShadow: "0 24px 60px rgba(0,0,0,0.7)" }}>
            <p style={{ fontSize: 14, fontWeight: 700, color: S.textBright, marginBottom: 12 }}>
              Import abgeschlossen
            </p>
            <p style={{ fontSize: 12, color: "#6ee7b7", marginBottom: importResult.failed.length ? 8 : 16 }}>
              ✓ {importResult.done} Dataset{importResult.done !== 1 ? "s" : ""} erfolgreich importiert
            </p>
            {importResult.failed.length > 0 && (
              <p style={{ fontSize: 12, color: "#f87171", marginBottom: 16 }}>
                ✗ Fehlgeschlagen: {importResult.failed.join(", ")}
              </p>
            )}
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button onClick={() => setImportResult(null)} style={{
                fontSize: 12, padding: "7px 14px", borderRadius: 6, cursor: "pointer",
                background: "transparent", border: `1px solid ${S.border}`, color: S.textDim,
              }}>Weiter analysieren</button>
              {importResult.done > 0 && (
                <button onClick={() => { setImportResult(null); onDatasetsImported?.(); }} style={{
                  fontSize: 12, fontWeight: 600, padding: "7px 14px", borderRadius: 6, cursor: "pointer",
                  background: "rgba(110,231,183,0.12)", border: "1px solid rgba(110,231,183,0.4)", color: "#6ee7b7",
                }}>Zum Dashboard</button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Bestätigungs-Modal Node entfernen */}
      {confirmRemove && (
        <div onClick={() => setConfirmRemove(null)} style={{
          position: "fixed", inset: 0, zIndex: 9999,
          backgroundColor: "rgba(0,0,0,0.6)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <div onClick={e => e.stopPropagation()} style={{
            background: S.bgCard, border: `1px solid ${S.border}`,
            borderRadius: 10, padding: "20px 24px", width: 360,
            boxShadow: "0 24px 60px rgba(0,0,0,0.7)",
          }}>
            <p style={{ fontSize: 14, fontWeight: 700, color: S.textBright, margin: "0 0 10px" }}>
              Tabelle ausblenden
            </p>
            <p style={{ fontSize: 12, color: S.textMain, margin: "0 0 6px" }}>
              <span style={{ fontFamily: "monospace", color: S.accent }}>{confirmRemove.tableName}</span>
            </p>
            <p style={{ fontSize: 11, color: S.textDim, margin: "0 0 20px" }}>
              Die Tabelle wird aus dem Diagramm entfernt. Die Analyse wird nicht neu geladen.
            </p>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button onClick={() => setConfirmRemove(null)} style={{
                fontSize: 12, padding: "7px 14px", borderRadius: 6, cursor: "pointer",
                background: "transparent", border: `1px solid ${S.border}`, color: S.textDim,
              }}>Abbrechen</button>
              <button onClick={() => {
                setHiddenTables(prev => new Set([...prev, confirmRemove.tableKey]));
                if (selected?.key === confirmRemove.tableKey) setSelected(null);
                setConfirmRemove(null);
              }} style={{
                fontSize: 12, fontWeight: 600, padding: "7px 14px", borderRadius: 6, cursor: "pointer",
                background: "rgba(224,112,112,0.15)", border: "1px solid rgba(224,112,112,0.4)", color: "#e07070",
              }}>Ausblenden</button>
            </div>
          </div>
        </div>
      )}

      {/* Detail Panel */}
      {selected && (
        <div style={{ position: "absolute", right: 0, top: 96, bottom: 0, width: 300, backgroundColor: S.bgCard, borderLeft: `1px solid ${S.border}`, display: "flex", flexDirection: "column", zIndex: 10 }}>
          <div style={{ padding: "12px 14px", borderBottom: `1px solid ${S.border}`, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div>
              <p style={{ fontSize: 13, fontWeight: 700, color: S.textBright, margin: 0, fontFamily: "monospace" }}>{selected.name}</p>
              <p style={{ fontSize: 10, color: S.textDim, margin: "2px 0 0" }}>
                {selected.schema} · {selected.columns.length} Spalten{selected.row_count != null && ` · ${selected.row_count.toLocaleString()} Zeilen`}
              </p>
            </div>
            <button onClick={() => setSelected(null)} style={{ color: S.textDim, background: "none", border: "none", cursor: "pointer" }}><X size={14} /></button>
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: "8px 0" }}>
            {/* Import-Checkbox */}
            {projectId && (
              <div style={{ padding: "8px 14px 12px", borderBottom: `1px solid ${S.border}` }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <input type="checkbox" id="mark-import"
                    checked={markedTables.has(selected.key)}
                    onChange={() => toggleMark(selected.key)}
                    style={{ accentColor: "#6ee7b7", cursor: "pointer", width: 15, height: 15 }} />
                  <label htmlFor="mark-import" style={{ fontSize: 12, color: "#6ee7b7", cursor: "pointer", fontWeight: 600 }}>
                    Als Dataset importieren
                  </label>
                </div>
                {markedTables.has(selected.key) && (
                  <p style={{ fontSize: 10, color: S.textDim, margin: "4px 0 0 23px" }}>
                    SELECT * FROM {selected.schema !== "dbo" ? `[${selected.schema}].` : ""}[{selected.name}]
                  </p>
                )}
              </div>
            )}
            <p style={{ fontSize: 9, fontWeight: 700, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.08em", padding: "4px 14px 8px" }}>Spalten</p>
            {selected.columns.map(col => {
              const tc = TYPE_COLORS[col.type] || "#6a6a6a";
              const tl = TYPE_LABELS[col.type] || col.type?.slice(0, 3).toUpperCase();
              return (
                <div key={col.name} style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 14px" }}>
                  {col.is_primary && <span style={{ fontSize: 9, fontWeight: 700, color: "#fbbf24", flexShrink: 0 }}>PK</span>}
                  <span style={{ fontSize: 8, fontWeight: 700, color: tc, backgroundColor: tc + "20", borderRadius: 2, padding: "1px 4px", flexShrink: 0 }}>{tl}</span>
                  <span style={{ fontSize: 11, fontFamily: "monospace", color: col.is_primary ? S.textBright : S.textMain, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{col.name}</span>
                  <span style={{ fontSize: 9, color: S.textDim, flexShrink: 0 }}>{col.raw}</span>
                </div>
              );
            })}
            {selected.foreign_keys.length > 0 && (
              <>
                <p style={{ fontSize: 9, fontWeight: 700, color: FK_COLOR, textTransform: "uppercase", letterSpacing: "0.08em", padding: "12px 14px 8px" }}>Foreign Keys</p>
                {selected.foreign_keys.map((fk, i) => (
                  <div key={i} style={{ padding: "4px 14px", fontSize: 11, color: S.textMain, fontFamily: "monospace" }}>
                    <span style={{ color: FK_COLOR }}>{fk.from_col}</span>
                    <span style={{ color: S.textDim }}> → </span>
                    <span style={{ color: S.textBright }}>{fk.to_table}.{fk.to_col}</span>
                  </div>
                ))}
              </>
            )}
            {(() => {
              const implRels = schema?.relationships.filter(r => r.type === "implicit" && (r.from_table === selected.key || r.to_table === selected.key)) || [];
              if (!implRels.length) return null;
              return (
                <>
                  <p style={{ fontSize: 9, fontWeight: 700, color: IMPLICIT_COLOR, textTransform: "uppercase", letterSpacing: "0.08em", padding: "12px 14px 8px" }}>Implizite Beziehungen</p>
                  {implRels.map((r, i) => {
                    const other = r.from_table === selected.key ? r.to_table : r.from_table;
                    return (
                      <div key={i} style={{ padding: "4px 14px", fontSize: 11, color: S.textMain, fontFamily: "monospace", cursor: "pointer" }}
                        onClick={() => { const t = schema.tables.find(t => t.key === other); if (t) setSelected(t); }}>
                        <span style={{ color: IMPLICIT_COLOR }}>{r.from_col}</span>
                        <span style={{ color: S.textDim }}> ... </span>
                        <span style={{ color: S.textBright }}>{other}</span>
                        <ChevronRight size={10} style={{ display: "inline", marginLeft: 4, color: S.textDim }} />
                      </div>
                    );
                  })}
                </>
              );
            })()}
          </div>
        </div>
      )}
    </div>
  );
}
