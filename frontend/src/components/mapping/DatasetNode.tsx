import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ArrowUpDown, Eye, FileText, GripVertical, Loader2, Minimize2, X } from "lucide-react";
import api from "../../api/client";
import { CONST_TYPES, FILTER_COLOR, JOIN_COLOR, S, SORT_COLOR, typeColor } from "./constants";
import { SortEditor, FilterEditor, TypeConvertEditor, CAST_COLOR } from "./FilterSortEditor";
import { MinimizedNode } from "./MinimizedNode";

const DATASET_ACTIVE_BORDER = "#fce499";

function DatasetNode({ node, connections, joins, onFieldClick, onFieldRightClick, onJoinDrop, onFieldDoubleClick, onFilterClick, onCastChange, onRegisterNodeRef, onFieldListScroll, pendingSource, pendingJoin, onRemove, onPositionChange, onResize, fieldRefs, onSortChange, onSchemaRefresh, debugHighlight, debugSampleRows, debugSelectedRowIdx, debugStats, isActive, onActivate }) {
  const dragState = useRef(null);
  const resizeState = useRef(null);
  const FIELD_H = 28;
  const [nodeWidth, setNodeWidth] = useState(node.width || 230);
  const [nodeHeight, setNodeHeight] = useState(node.height || 300);
  const filters = node.filters || {};
  const [showPreview, setShowPreview] = useState(false);
  const [previewData, setPreviewData] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewMode, setPreviewMode] = useState("full"); // "full" | "filtered"
  const [schemaLoading, setSchemaLoading] = useState(false);

  const isDbDataset = node.dataset_file_type?.startsWith("db_");

  const detectSchema = async (e) => {
    e.stopPropagation();
    setSchemaLoading(true);
    try {
      const { data } = await api.post(`/api/datasets/${node.dataset_id}/detect-schema`);
      if (data?.column_types && onSchemaRefresh) onSchemaRefresh(node.dataset_id, data.column_types);
    } catch { /* silent */ } finally {
      setSchemaLoading(false);
    }
  };

  const hasFilters = Object.values(filters).some(Boolean);

  const loadPreview = async (mode) => {
    setPreviewLoading(true);
    setPreviewData(null);
    try {
      if (mode === "filtered" && hasFilters) {
        const { data } = await api.post(`/api/datasets/${node.dataset_id}/filtered-preview`, { filters, limit: 200 });
        setPreviewData(data);
      } else {
        const { data } = await api.get(`/api/datasets/${node.dataset_id}/data?page=0&page_size=200`);
        setPreviewData(data);
      }
    } catch { setPreviewData(null); }
    finally { setPreviewLoading(false); }
  };

  const openPreview = (e) => {
    e.stopPropagation();
    const mode = hasFilters ? "filtered" : "full";
    setPreviewMode(mode);
    setShowPreview(true);
    loadPreview(mode);
  };

  const switchPreviewMode = (mode) => {
    setPreviewMode(mode);
    loadPreview(mode);
  };

  const handleMouseDown = useCallback((e) => {
    if (e.target.closest("[data-field]") || e.target.closest("button")) return;
    e.preventDefault(); e.stopPropagation();
    dragState.current = { startX: e.clientX - node.x, startY: e.clientY - node.y };
    const onMove = (ev) => { if (!dragState.current) return; onPositionChange(node.dataset_id, ev.clientX - dragState.current.startX, ev.clientY - dragState.current.startY); };
    const onUp = () => { dragState.current = null; window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }, [node.x, node.y, node.dataset_id, onPositionChange]);

  const handleResizeMouseDown = useCallback((e) => {
    e.preventDefault(); e.stopPropagation();
    resizeState.current = { startX: e.clientX, startY: e.clientY, startW: nodeWidth, startH: nodeHeight };
    const onMove = (ev) => {
      if (!resizeState.current) return;
      const newW = Math.max(180, resizeState.current.startW + ev.clientX - resizeState.current.startX);
      const newH = Math.max(100, resizeState.current.startH + ev.clientY - resizeState.current.startY);
      setNodeWidth(newW);
      setNodeHeight(newH);
    };
    const onUp = (ev) => {
      if (resizeState.current) {
        const newW = Math.max(180, resizeState.current.startW + ev.clientX - resizeState.current.startX);
        const newH = Math.max(100, resizeState.current.startH + ev.clientY - resizeState.current.startY);
        if (onResize) onResize(node.dataset_id, newW, newH);
      }
      resizeState.current = null;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }, [nodeWidth, nodeHeight, node.dataset_id, onResize]);

  const clickTimers = useRef({});
  const fieldListRef = useRef(null);
  const nodeBodyRef = useRef(null);

  const fields = node.dataset_columns || [];
  const activeFilterCount = Object.values(filters).filter(Boolean).length;
  const activeSortCount = (node.sorts || []).filter(s => s.field).length;
  const castRules = node.cast_rules || {};
  const activeCastCount = Object.keys(castRules).length;
  const [showSortEditor, setShowSortEditor] = useState(false);
  const [castEditor, setCastEditor] = useState(null); // { field, currentCast }
  const [debugTooltip, setDebugTooltip] = useState(null); // { field, x, y }

  // Register the field-list scroll container so SvgOverlay can clamp lines
  useEffect(() => {
    if (onRegisterNodeRef) onRegisterNodeRef(node.dataset_id, fieldListRef, nodeBodyRef);
  }, [node.dataset_id, onRegisterNodeRef]);

  // ── Minimierte Ansicht ─────────────────────────────────────────────────────
  if (node.minimized) {
    const color = typeColor[node.dataset_file_type] || S.accent;
    const fields = node.dataset_columns || [];

    return (
      <div ref={nodeBodyRef} style={{ position: "absolute", left: node.x, top: node.y, zIndex: 10,
          overflow: "visible", userSelect: "none", cursor: "grab" }}
        onMouseDown={handleMouseDown}>
        <div style={{ position: "relative", width: 60, height: 40 }}>
          {/* Input-Port links (kein ref nötig) */}
          <div style={{ position: "absolute", left: -6, top: "50%",
              transform: "translateY(-50%)", width: 8, height: 8,
              borderRadius: "50%", backgroundColor: color,
              border: "2px solid #1e1e1e", zIndex: 20,
              boxShadow: `0 0 4px ${color}88`, pointerEvents: "none" }} />

          {/* Hintergrund-Box – nur für Drag, kein Click-Handler */}
          <div style={{ width: "100%", height: "100%", borderRadius: 6,
            backgroundColor: color + "18", border: `2px solid ${color}55` }} />

          {/* Icon in der Mitte – NUR hier kann man aufklappen */}
          <div
            onClick={(e) => { e.stopPropagation(); onPositionChange(node.dataset_id, node.x, node.y, true); }}
            title="Aufklappen (klicken)"
            style={{ position: "absolute", inset: 0,
              display: "flex", alignItems: "center", justifyContent: "center",
              cursor: "pointer", borderRadius: 6, zIndex: 5 }}
            onMouseEnter={e => {
              e.currentTarget.style.backgroundColor = color + "40";
              e.currentTarget.querySelector("svg").style.filter = "drop-shadow(0 0 4px " + color + ")";
            }}
            onMouseLeave={e => {
              e.currentTarget.style.backgroundColor = "transparent";
              e.currentTarget.querySelector("svg").style.filter = "none";
            }}>
            <FileText size={14} style={{ color, flexShrink: 0, transition: "filter 0.15s" }} />
          </div>

          {/* Output-Port rechts – fieldRefs zeigen hierauf damit SvgOverlay korrekte x-Position hat */}
          <div
            ref={(el) => {
              if (el) fields.forEach(field =>
                fieldRefs.current[`${node.dataset_id}__${field}`] = el
              );
            }}
            style={{ position: "absolute", right: -6, top: "50%",
                transform: "translateY(-50%)", width: 8, height: 8,
                borderRadius: "50%", backgroundColor: color,
                border: "2px solid #1e1e1e", zIndex: 20,
                boxShadow: `0 0 4px ${color}88`, pointerEvents: "none" }} />
        </div>

        {/* Label */}
        <div style={{ fontSize: 8, color, fontWeight: 700, textAlign: "center", marginTop: 3,
          maxWidth: 60, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          textShadow: "0 1px 3px rgba(0,0,0,0.8)" }}>
          {node.dataset_name}
        </div>
      </div>
    );
  }

  return (
    <>
    <div ref={nodeBodyRef} onClick={(e) => { e.stopPropagation(); onActivate?.({ type: "dataset", name: node.dataset_name, datasetId: node.dataset_id, fileType: node.dataset_file_type, columns: (node.dataset_columns || []).slice(0, 30).map(c => c.name || c) }); }} style={{ position: "absolute", left: node.x, top: node.y, width: nodeWidth, zIndex: debugHighlight ? 20 : 10, userSelect: "none", boxShadow: debugHighlight ? "0 0 0 2px #38bdf8, 0 0 24px #38bdf855, 0 8px 32px rgba(0,0,0,0.5)" : isActive ? `0 0 0 2px ${DATASET_ACTIVE_BORDER}, 0 8px 32px rgba(0,0,0,0.5)` : "0 8px 32px rgba(0,0,0,0.5)", borderRadius: 6, overflow: "hidden", border: debugHighlight ? "1.5px solid #38bdf8aa" : isActive ? `1px solid ${DATASET_ACTIVE_BORDER}` : `1px solid ${S.border}`, backgroundColor: S.bgCard, transition: "box-shadow 0.2s, border-color 0.2s" }}>
      {/* Header */}
      <div onMouseDown={handleMouseDown} style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", cursor: "grab", backgroundColor: S.bgEl, borderBottom: `1px solid ${S.border}` }}>
        <GripVertical size={12} style={{ color: S.textDim, flexShrink: 0 }} />
        <FileText size={12} style={{ color: typeColor[node.dataset_file_type] || S.accent, flexShrink: 0 }} />
        <span style={{ fontSize: 12, fontWeight: 600, color: S.textBright, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{node.dataset_name}</span>
        {activeSortCount > 0 && (
          <span style={{ fontSize: 9, color: SORT_COLOR, fontWeight: 700, backgroundColor: `${SORT_COLOR}18`, padding: "1px 5px", borderRadius: 3, flexShrink: 0 }}>
            ↕ {activeSortCount}
          </span>
        )}
        <button onClick={(e) => { e.stopPropagation(); setShowSortEditor(true); }} title="Sortierung"
          style={{ color: activeSortCount > 0 ? SORT_COLOR : S.textDim, flexShrink: 0, lineHeight: 1 }}
          onMouseEnter={(e) => (e.currentTarget.style.color = SORT_COLOR)}
          onMouseLeave={(e) => (e.currentTarget.style.color = activeSortCount > 0 ? SORT_COLOR : S.textDim)}>
          <ArrowUpDown size={12} />
        </button>
        {isDbDataset && (
          <button onClick={detectSchema} title="PK/FK aus DB-Schema erkennen" style={{ color: schemaLoading ? S.accent : S.textDim, flexShrink: 0, lineHeight: 1 }}
            onMouseEnter={(e) => (e.currentTarget.style.color = S.accent)}
            onMouseLeave={(e) => (e.currentTarget.style.color = schemaLoading ? S.accent : S.textDim)}>
            {schemaLoading ? <Loader2 size={12} className="animate-spin" /> : <span style={{ fontSize: 11, lineHeight: 1 }}>🔑</span>}
          </button>
        )}
        <button onClick={openPreview} title="Vorschau" style={{ color: S.textDim, flexShrink: 0, lineHeight: 1 }}
          onMouseEnter={(e) => (e.currentTarget.style.color = S.accent)}
          onMouseLeave={(e) => (e.currentTarget.style.color = S.textDim)}>
          <Eye size={12} />
        </button>
        <button onClick={(e) => { e.stopPropagation(); onPositionChange(node.dataset_id, node.x, node.y, true); }} title="Minimieren"
          style={{ color: S.textDim, flexShrink: 0, lineHeight: 1 }}
          onMouseEnter={(e) => (e.currentTarget.style.color = S.accent)}
          onMouseLeave={(e) => (e.currentTarget.style.color = S.textDim)}>
          <Minimize2 size={11} />
        </button>
        <button onClick={(e) => { e.stopPropagation(); onRemove(node.dataset_id); }} style={{ color: S.textDim, flexShrink: 0, lineHeight: 1 }}
          onMouseEnter={(e) => (e.currentTarget.style.color = "#e07070")}
          onMouseLeave={(e) => (e.currentTarget.style.color = S.textDim)}>
          <X size={12} />
        </button>
      </div>

      {/* Fields */}
      <div ref={fieldListRef} onScroll={onFieldListScroll} style={{ maxHeight: nodeHeight, overflowY: "auto", scrollbarWidth: "thin" }}>
        {fields.map((field) => {
          const conn = connections.find((c) => c.source_dataset_id === node.dataset_id && c.source_field === field);
          const hasJoin = joins.some((j) => (j.left_dataset_id === node.dataset_id && j.left_field === field) || (j.right_dataset_id === node.dataset_id && j.right_field === field));
          const isPending = pendingSource?.dataset_id === node.dataset_id && pendingSource?.field === field;
          const isJoinPending = pendingJoin?.dataset_id === node.dataset_id && pendingJoin?.field === field;
          const hasFilter = !!filters[field];
          const refKey = `${node.dataset_id}__${field}`;

          return (
            <div
              key={field}
              data-field="1"
              draggable
              ref={(el) => { if (el) fieldRefs.current[refKey] = el; }}
              onDragStart={(e) => {
                e.stopPropagation();
                e.dataTransfer.setData("source_dataset_id", node.dataset_id);
                e.dataTransfer.setData("source_field", field);
                e.dataTransfer.effectAllowed = "copy";
              }}
              onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); e.currentTarget.style.backgroundColor = `${JOIN_COLOR}22`; e.currentTarget.style.outline = `1px solid ${JOIN_COLOR}`; }}
              onDragLeave={(e) => { e.currentTarget.style.backgroundColor = isJoinPending ? `${JOIN_COLOR}22` : isPending ? "rgba(252,228,153,0.12)" : conn ? "rgba(110,231,183,0.04)" : "transparent"; e.currentTarget.style.outline = "none"; }}
              onDrop={(e) => {
                e.preventDefault(); e.stopPropagation();
                e.currentTarget.style.outline = "none"; e.currentTarget.style.backgroundColor = "transparent";
                const srcDsId = parseInt(e.dataTransfer.getData("source_dataset_id"));
                const srcField = e.dataTransfer.getData("source_field");
                if (!srcField || isNaN(srcDsId) || srcDsId === node.dataset_id) return;
                onJoinDrop(srcDsId, srcField, node.dataset_id, field);
              }}
              onClick={(e) => {
                e.stopPropagation();
                // Ignore if this is part of a double-click sequence
                if (e.detail === 2) return;
                onFieldClick(node.dataset_id, field);
              }}
              onDoubleClick={(e) => {
                e.stopPropagation();
                onFieldDoubleClick(node.dataset_id, field);
              }}
              onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); onFieldRightClick(node.dataset_id, field, e); }}
              style={{
                height: FIELD_H, display: "flex", alignItems: "center", justifyContent: "space-between",
                padding: "0 10px", cursor: "grab", borderBottom: `1px solid ${S.border}`,
                backgroundColor: isJoinPending ? `${JOIN_COLOR}22` : isPending ? "rgba(252,228,153,0.12)" : hasFilter ? "rgba(167,139,250,0.06)" : conn ? "rgba(110,231,183,0.04)" : "transparent",
                position: "relative",
              }}
              onMouseEnter={(e) => {
                if (!isPending && !isJoinPending) e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.04)";
                if (debugSampleRows?.length) {
                  const rect = e.currentTarget.getBoundingClientRect();
                  setDebugTooltip({ field, x: rect.right + 8, y: rect.top + rect.height / 2 });
                }
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = isJoinPending ? `${JOIN_COLOR}22` : isPending ? "rgba(252,228,153,0.12)" : hasFilter ? "rgba(167,139,250,0.06)" : conn ? "rgba(110,231,183,0.04)" : "transparent";
                setDebugTooltip(null);
              }}
            >
              <span style={{ fontSize: 11, fontFamily: "monospace", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: isJoinPending ? JOIN_COLOR : isPending ? S.accent : hasFilter ? "#a78bfa" : conn ? "#6ee7b7" : S.textMain, display: "flex", alignItems: "center", gap: 0 }}>
                {(() => {
                  const ti = node.dataset_column_types?.[field];
                  if (ti?.is_primary) return (
                    <span title="Primärschlüssel" style={{ width: 14, flexShrink: 0, display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 9 }}>🔑</span>
                  );
                  if (ti?.is_fk) return (
                    <span title="Fremdschlüssel" style={{ width: 14, flexShrink: 0, display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
                      <span style={{ fontSize: 7, fontWeight: 800, color: "#fb923c", backgroundColor: "#fb923c18", borderRadius: 2, padding: "1px 2px", lineHeight: 1 }}>FK</span>
                    </span>
                  );
                  return <span style={{ width: 14, flexShrink: 0 }} />;
                })()}
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{field}</span>
              </span>
              <div style={{ display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
                <span
                onClick={(e) => { e.stopPropagation(); if (onFilterClick) onFilterClick(node.dataset_id, field, filters[field] || ""); }}
                title={hasFilter ? ("Filter: " + filters[field]) : "Filter setzen"}
                style={{ fontSize: 9, color: hasFilter ? "#a78bfa" : S.textDim, cursor: "pointer", padding: "1px 3px", borderRadius: 2, lineHeight: 1 }}
              >⊤</span>
              <span
                onClick={(e) => { e.stopPropagation(); setCastEditor({ field, currentCast: castRules[field] || null }); }}
                title={castRules[field] ? ("Konvertierung: " + castRules[field].type) : "Typ-Konvertierung"}
                style={{ fontSize: 9, color: castRules[field] ? CAST_COLOR : S.textDim, cursor: "pointer", padding: "1px 3px", borderRadius: 2, lineHeight: 1, fontWeight: 700 }}
              >⇄</span>
                {/* Verbindungspunkt – orange bei Join, grau sonst */}
                <div style={{ width: 6, height: 6, borderRadius: "50%", flexShrink: 0,
                  backgroundColor: hasJoin ? JOIN_COLOR : "#3a3a3a",
                  opacity: hasJoin ? 0.8 : 1 }} />
                {(() => {
                  const ti = node.dataset_column_types?.[field];
                  if (!ti) return null;
                  const TMETA = { integer: { l: "INT", c: "#93c5fd" }, decimal: { l: "DEC", c: "#6ee7b7" }, string: { l: "STR", c: "#6a6a6a" }, date: { l: "DATE", c: "#fcd34d" }, bool: { l: "BOOL", c: "#c4b5fd" } };
                  const m = TMETA[ti.type] || { l: ti.type?.slice(0,3).toUpperCase(), c: "#6a6a6a" };
                  return <span title={ti.raw || ti.type} style={{ fontSize: 8, fontWeight: 700, color: m.c, backgroundColor: m.c + "18", borderRadius: 2, padding: "1px 3px", cursor: "help" }}>{m.l}</span>;
                })()}
                <div style={{
                  width: 8, height: 8, borderRadius: "50%",
                  backgroundColor: isPending ? S.accent : conn ? "#fbbf24" : "transparent",
                  border: `2px solid ${isPending ? S.accent : conn ? "#fbbf24" : S.textDim}`,
                  boxShadow: isPending ? `0 0 6px ${S.accent}` : conn ? "0 0 5px #fbbf2466" : "none",
                }} />
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div style={{ padding: "5px 10px", borderTop: `1px solid ${S.border}`, display: "flex", justifyContent: "space-between", alignItems: "center", position: "relative" }}>
        <span style={{ fontSize: 10, fontFamily: "monospace", color: S.textDim }}>{fields.length} Felder</span>
        <div style={{ display: "flex", gap: 6 }}>
          {activeFilterCount > 0 && (
            <span style={{ fontSize: 9, color: "#a78bfa", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700, display: "flex", alignItems: "center", gap: 3 }}>
              <span style={{ backgroundColor: "rgba(167,139,250,0.15)", padding: "1px 4px", borderRadius: 3 }}>⊤ {activeFilterCount}</span>
              FILTER
            </span>
          )}
          {joins.some((j) => j.left_dataset_id === node.dataset_id || j.right_dataset_id === node.dataset_id) && (
            <span style={{ fontSize: 9, color: JOIN_COLOR, textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700 }}>JOIN</span>
          )}
        </div>
        {/* Resize handle */}
        <div
          onMouseDown={handleResizeMouseDown}
          title="Größe ändern"
          style={{ position: "absolute", right: 3, bottom: 3, width: 10, height: 10, cursor: "nwse-resize", opacity: 0.4,
            backgroundImage: "linear-gradient(135deg, transparent 30%, #888 30%, #888 40%, transparent 40%, transparent 60%, #888 60%, #888 70%, transparent 70%)",
          }}
          onMouseEnter={(e) => e.currentTarget.style.opacity = "1"}
          onMouseLeave={(e) => e.currentTarget.style.opacity = "0.4"}
        />
      </div>
    </div>

    {/* Preview Modal */}
    {showPreview && (
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
        style={{ backgroundColor: "rgba(0,0,0,0.8)", backdropFilter: "blur(4px)" }}
        onClick={() => setShowPreview(false)}>
        <div style={{ width: "92vw", maxWidth: 1400, height: "82vh", backgroundColor: S.bgCard, border: `1px solid ${S.border}`, borderRadius: 12, display: "flex", flexDirection: "column", overflow: "hidden" }}
          onClick={(e) => e.stopPropagation()}>
          {/* Modal Header */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 18px", borderBottom: `1px solid ${S.border}`, backgroundColor: S.bgEl, flexShrink: 0 }}>
            <Eye size={14} style={{ color: S.accent }} />
            <span style={{ fontSize: 13, fontWeight: 600, color: S.textBright }}>{node.dataset_name}</span>
            <span style={{ fontSize: 11, fontFamily: "monospace", color: S.textDim }}>
              {debugStats ? (
                <span style={{ color: "#38bdf8" }}>↓ {(debugStats.rows_out ?? 0).toLocaleString()} geladen · </span>
              ) : null}
              {node.dataset_row_count?.toLocaleString() || 0} Zeilen · {(node.dataset_columns || []).length} Spalten
            </span>
            {hasFilters && (
              <div style={{ display: "flex", gap: 2, marginLeft: 12, backgroundColor: "rgba(255,255,255,0.05)", borderRadius: 6, padding: 2 }}>
                {[["full", "Vollständig"], ["filtered", `Gefiltert (${Object.values(filters).filter(Boolean).length})`]].map(([mode, label]) => (
                  <button key={mode} onClick={() => switchPreviewMode(mode)}
                    style={{ fontSize: 11, fontWeight: 600, padding: "4px 12px", borderRadius: 4, cursor: "pointer", border: "none", transition: "all 0.15s",
                      backgroundColor: previewMode === mode ? S.accent + "22" : "transparent",
                      color: previewMode === mode ? S.accent : S.textDim,
                      outline: previewMode === mode ? `1px solid ${S.accent}55` : "none" }}>
                    {label}
                  </button>
                ))}
              </div>
            )}
            <button onClick={() => setShowPreview(false)}
              style={{ marginLeft: "auto", color: S.textDim, lineHeight: 1 }}
              onMouseEnter={(e) => e.currentTarget.style.color = S.textBright}
              onMouseLeave={(e) => e.currentTarget.style.color = S.textDim}>
              <X size={15} />
            </button>
          </div>
          {/* Table */}
          <div style={{ flex: 1, minHeight: 0, overflow: "scroll", scrollbarWidth: "thin" }}>
            {previewLoading ? (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: S.textDim }}>
                <Loader2 size={18} className="animate-spin" style={{ marginRight: 8 }} /> Lade Daten…
              </div>
            ) : !previewData ? (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: S.textDim }}>
                Keine Daten verfügbar
              </div>
            ) : (
              <table style={{ fontSize: 12, borderCollapse: "collapse", minWidth: "max-content", width: "100%" }}>
                <thead style={{ position: "sticky", top: 0, zIndex: 1 }}>
                  <tr style={{ backgroundColor: S.bgEl }}>
                    {previewData.columns.map((col) => (
                      <th key={col} style={{ textAlign: "left", padding: "8px 14px", fontFamily: "monospace", fontWeight: 600, color: S.accent, borderRight: `1px solid ${S.border}`, borderBottom: `1px solid ${S.border}`, whiteSpace: "nowrap" }}>
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {previewData.preview.map((row, i) => (
                    <tr key={i} style={{ borderTop: `1px solid ${S.border}` }}
                      onMouseEnter={(e) => e.currentTarget.style.backgroundColor = S.bgEl}
                      onMouseLeave={(e) => e.currentTarget.style.backgroundColor = "transparent"}>
                      {previewData.columns.map((col) => (
                        <td key={col} style={{ padding: "6px 14px", fontFamily: "monospace", color: row[col] == null ? S.textDim : S.textMain, borderRight: `1px solid ${S.border}`, whiteSpace: "nowrap", maxWidth: 240, overflow: "hidden", textOverflow: "ellipsis" }}>
                          {row[col] ?? <span style={{ opacity: 0.4 }}>null</span>}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          {/* Footer */}
          {previewData && (
            <div style={{ padding: "8px 18px", borderTop: `1px solid ${S.border}`, backgroundColor: S.bgEl, flexShrink: 0 }}>
              {previewMode === "filtered" && hasFilters ? (
                <span style={{ fontSize: 11, color: S.textDim }}>
                  <span style={{ color: FILTER_COLOR, fontWeight: 600 }}>{previewData.total ?? previewData.preview?.length}</span> Treffer nach Filter · max. 200 Zeilen angezeigt · Gesamt: <span style={{ color: S.textBright }}>{node.dataset_row_count?.toLocaleString() || 0}</span>
                </span>
              ) : (
                <span style={{ fontSize: 11, color: S.textDim }}>Zeigt bis zu 200 Zeilen · Gesamtdatensätze: <span style={{ color: S.textBright }}>{node.dataset_row_count?.toLocaleString() || 0}</span></span>
              )}
            </div>
          )}
        </div>
      </div>
    )}
    {showSortEditor && (
      <SortEditor
        node={node}
        onSave={(sorts) => { if (onSortChange) onSortChange(node.dataset_id, sorts); }}
        onClose={() => setShowSortEditor(false)}
      />
    )}
    {castEditor && (
      <TypeConvertEditor
        datasetId={node.dataset_id}
        field={castEditor.field}
        currentCast={castEditor.currentCast}
        onSave={(dsId, field, cast) => {
          const newRules = { ...castRules };
          if (cast) newRules[field] = cast;
          else delete newRules[field];
          if (onCastChange) onCastChange(dsId, newRules);
        }}
        onClose={() => setCastEditor(null)}
      />
    )}

    {/* Debug Field Tooltip – via Portal damit overflow:hidden den Node nicht clippt */}
    {debugTooltip && debugSampleRows?.length > 0 && createPortal((() => {
      const rowIdx = debugSelectedRowIdx !== null && debugSelectedRowIdx !== undefined ? debugSelectedRowIdx : null;
      const rows = rowIdx !== null ? [debugSampleRows[rowIdx]].filter(Boolean) : debugSampleRows.slice(0, 5);
      const values = rows.map(r => r?.[debugTooltip.field] !== undefined ? r[debugTooltip.field] : undefined).filter(v => v !== undefined);
      if (!values.length) return null;
      return (
        <div style={{
          position: "fixed", left: debugTooltip.x, top: debugTooltip.y, transform: "translateY(-50%)",
          zIndex: 9999, backgroundColor: "#0f172a", border: "1px solid rgba(56,189,248,0.5)",
          borderRadius: 6, padding: "7px 11px", minWidth: 130, maxWidth: 240,
          boxShadow: "0 8px 28px rgba(0,0,0,0.8)", pointerEvents: "none",
        }}>
          <p style={{ fontSize: 9, fontWeight: 700, color: "#38bdf8", marginBottom: 5, textTransform: "uppercase", letterSpacing: "0.07em" }}>{debugTooltip.field}</p>
          {values.map((v, i) => (
            <p key={i} style={{ fontSize: 10, color: v === null ? "#475569" : "#e2e8f0", fontFamily: "monospace", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontStyle: v === null ? "italic" : "normal", lineHeight: 1.6 }}>
              {v === null ? "null" : String(v)}
            </p>
          ))}
        </div>
      );
    })(), document.body)}
    </>
  );
}

// ─── Dataset Preview Table ─────────────────────────────────────────────────────
function DatasetPreviewTable({ dataset }) {
  const [data, setData] = useState(null);
  useEffect(() => { api.get(`/api/datasets/${dataset.id}/data?page=0&page_size=50`).then((r) => setData(r.data)); }, [dataset.id]);
  if (!data) return <div style={{ display: "flex", alignItems: "center", justifyContent: "center", flex: 1, color: S.textDim }}><Loader2 size={18} className="animate-spin" style={{ marginRight: 8 }} />Lade...</div>;
  return (
    <div style={{ flex: 1, minHeight: 0, overflow: "scroll", scrollbarWidth: "thin" }}>
      <table style={{ fontSize: 11, borderCollapse: "collapse", minWidth: "max-content" }}>
        <thead style={{ position: "sticky", top: 0, zIndex: 10 }}>
          <tr style={{ backgroundColor: S.bgEl }}>
            {data.columns.map((col) => <th key={col} style={{ textAlign: "left", padding: "10px 14px", fontFamily: "monospace", whiteSpace: "nowrap", color: S.accent, borderRight: `1px solid ${S.border}`, borderBottom: `1px solid ${S.border}` }}>{col}</th>)}
          </tr>
        </thead>
        <tbody>
          {data.preview.map((row, i) => (
            <tr key={i} style={{ borderTop: `1px solid ${S.border}` }}>
              {data.columns.map((col) => <td key={col} style={{ padding: "7px 14px", fontFamily: "monospace", whiteSpace: "nowrap", maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", color: S.textMain, borderRight: `1px solid ${S.border}` }}>{row[col] ?? <span style={{ color: S.textDim }}>null</span>}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export { DatasetNode, DatasetPreviewTable };
