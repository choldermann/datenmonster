import { useState, useRef, useEffect } from "react";
import { GripVertical } from "lucide-react";
import { GRID_COLS, ROW_HEIGHT, WIDGET_TYPES, S } from "./constants";
import { KpiWidget, BarChartWidget, LineChartWidget, PieChartWidget, TableWidget, HeatmapWidget } from "./widgets/ChartWidgets";

const ACCENT = "#fce499";
const COL_WIDTH_PCT = 100 / GRID_COLS;

function WidgetFrame({ widget, data, compareData, preview, onSelect, selected, onUpdate }) {
  const wtype = WIDGET_TYPES.find(w => w.type === widget.type);
  const dragState = useRef(null);
  const resizeState = useRef(null);
  const containerRef = useRef(null);

  // ── Drag (verschieben) ──────────────────────────────────────────────────────
  const startDrag = (e) => {
    if (preview) return;
    e.preventDefault();
    e.stopPropagation();
    const canvas = containerRef.current?.closest("[data-canvas]");
    if (!canvas) return;
    const canvasRect = canvas.getBoundingClientRect();
    dragState.current = {
      startMouseX: e.clientX, startMouseY: e.clientY,
      startX: widget.x, startY: widget.y,
      canvasRect, colW: canvasRect.width / GRID_COLS,
    };
    const onMove = (ev) => {
      if (!dragState.current) return;
      const { startMouseX, startMouseY, startX, startY, colW } = dragState.current;
      const dx = Math.round((ev.clientX - startMouseX) / colW);
      const dy = Math.round((ev.clientY - startMouseY) / ROW_HEIGHT);
      const newX = Math.max(0, Math.min(GRID_COLS - widget.w, startX + dx));
      const newY = Math.max(0, startY + dy);
      if (newX !== widget.x || newY !== widget.y) {
        onUpdate(widget.id, { x: newX, y: newY });
      }
    };
    const onUp = () => {
      dragState.current = null;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  // ── Resize ──────────────────────────────────────────────────────────────────
  const startResize = (e) => {
    if (preview) return;
    e.preventDefault();
    e.stopPropagation();
    const canvas = containerRef.current?.closest("[data-canvas]");
    if (!canvas) return;
    const canvasRect = canvas.getBoundingClientRect();
    resizeState.current = {
      startMouseX: e.clientX, startMouseY: e.clientY,
      startW: widget.w, startH: widget.h,
      colW: canvasRect.width / GRID_COLS,
    };
    const onMove = (ev) => {
      if (!resizeState.current) return;
      const { startMouseX, startMouseY, startW, startH, colW } = resizeState.current;
      const dw = Math.round((ev.clientX - startMouseX) / colW);
      const dh = Math.round((ev.clientY - startMouseY) / ROW_HEIGHT);
      const newW = Math.max(2, Math.min(GRID_COLS - widget.x, startW + dw));
      const newH = Math.max(2, startH + dh);
      if (newW !== widget.w || newH !== widget.h) {
        onUpdate(widget.id, { w: newW, h: newH });
      }
    };
    const onUp = () => {
      resizeState.current = null;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  const renderContent = () => {
    const props = { config: widget.config || {}, data: data || [], compareData };
    switch (widget.type) {
      case "kpi":     return <KpiWidget {...props} />;
      case "bar":     return <BarChartWidget {...props} />;
      case "line":    return <LineChartWidget {...props} />;
      case "pie":     return <PieChartWidget {...props} />;
      case "table":   return <TableWidget {...props} />;
      case "heatmap": return <HeatmapWidget {...props} />;
      default:        return null;
    }
  };

  return (
    <div
      ref={containerRef}
      onClick={e => { e.stopPropagation(); onSelect(widget.id); }}
      style={{
        position: "absolute",
        left: `${widget.x * COL_WIDTH_PCT}%`,
        top: widget.y * ROW_HEIGHT,
        width: `${widget.w * COL_WIDTH_PCT}%`,
        height: widget.h * ROW_HEIGHT,
        backgroundColor: S.bgCard,
        border: `1px solid ${selected ? ACCENT : S.border}`,
        borderRadius: 8,
        overflow: "hidden",
        boxShadow: selected ? `0 0 0 2px ${ACCENT}44` : "none",
        display: "flex", flexDirection: "column",
        userSelect: "none",
      }}
    >
      {/* Header */}
      <div
        onMouseDown={startDrag}
        style={{
          display: "flex", alignItems: "center", gap: 6,
          padding: "5px 10px", flexShrink: 0,
          borderBottom: `1px solid ${S.border}`,
          backgroundColor: selected ? `${ACCENT}08` : "transparent",
          cursor: preview ? "default" : "grab",
        }}
      >
        {!preview && <GripVertical size={11} style={{ color: S.textDim, flexShrink: 0 }} />}
        <span style={{ fontSize: 11 }}>{wtype?.icon}</span>
        <span style={{ fontSize: 11, fontWeight: 600, color: S.textBright, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {widget.title || wtype?.label}
        </span>
      </div>

      {/* Content */}
      <div style={{ flex: 1, padding: widget.type === "table" ? 0 : "8px", minHeight: 0, overflow: "hidden" }}>
        {renderContent()}
      </div>

      {/* Resize Handle */}
      {!preview && (
        <div
          onMouseDown={startResize}
          style={{
            position: "absolute", bottom: 0, right: 0,
            width: 18, height: 18, cursor: "se-resize",
            display: "flex", alignItems: "center", justifyContent: "center",
            color: selected ? ACCENT : S.textDim, fontSize: 12, lineHeight: 1,
            backgroundColor: selected ? `${ACCENT}15` : "transparent",
            borderRadius: "8px 0 8px 0",
          }}
        >
          ⌟
        </div>
      )}
    </div>
  );
}

export default function ReportCanvas({ widgets, widgetData, preview, selectedId, onSelect, onPositionChange, onDrop }) {
  const canvasRef = useRef(null);
  const maxRow = widgets.reduce((m, w) => Math.max(m, w.y + w.h), 8);
  const canvasHeight = Math.max(600, (maxRow + 4) * ROW_HEIGHT);

  const handleUpdate = (id, changes) => {
    onPositionChange(id, changes);
  };

  return (
    <div
      ref={canvasRef}
      data-canvas
      onClick={() => onSelect(null)}
      onDragOver={e => e.preventDefault()}
      onDrop={e => {
        e.preventDefault();
        const type = e.dataTransfer.getData("new_widget_type");
        if (!type || !canvasRef.current) return;
        const rect = canvasRef.current.getBoundingClientRect();
        const x = Math.floor(((e.clientX - rect.left) / rect.width) * GRID_COLS);
        const y = Math.floor((e.clientY - rect.top + canvasRef.current.scrollTop) / ROW_HEIGHT);
        onDrop(type, Math.max(0, x), Math.max(0, y));
      }}
      style={{
        flex: 1, position: "relative", overflow: "auto",
        backgroundImage: !preview
          ? "radial-gradient(circle, rgba(255,255,255,0.04) 1px, transparent 1px)"
          : "none",
        backgroundSize: "24px 24px",
      }}
    >
      <div style={{ position: "relative", width: "100%", height: canvasHeight }}>
        {widgets.map(w => (
          <WidgetFrame
            key={w.id}
            widget={w}
            data={widgetData?.[w.id]?.data}
            compareData={widgetData?.[w.id]?.compareData}
            preview={preview}
            selected={selectedId === w.id}
            onSelect={onSelect}
            onUpdate={handleUpdate}
          />
        ))}

        {widgets.length === 0 && (
          <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 12, pointerEvents: "none" }}>
            <p style={{ fontSize: 32 }}>📊</p>
            <p style={{ fontSize: 13, color: S.textDim, fontWeight: 600 }}>Report Canvas</p>
            <p style={{ fontSize: 11, color: S.textDim }}>Widgets aus der linken Leiste hinzufügen oder ziehen</p>
          </div>
        )}
      </div>
    </div>
  );
}
