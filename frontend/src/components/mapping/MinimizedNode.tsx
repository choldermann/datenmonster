/**
 * MinimizedNode – gemeinsame minimierte Darstellung für alle Mapping-Nodes.
 * Drag: gesamte Node verschiebbar via onMouseDown
 * Expand: NUR durch Klick auf das Icon in der Mitte
 */
import { S } from "./constants";

const SHAPES = {
  dataset:  { shape: "rect",    w: 52, h: 36, r: 6  },
  agg:      { shape: "hexagon", w: 46, h: 46, r: 0  },
  sql:      { shape: "diamond", w: 44, h: 44, r: 5  },
  constant: { shape: "circle",  w: 44, h: 44, r: 0  },
  rest:     { shape: "rect",    w: 48, h: 38, r: 12 },
  lookup:   { shape: "oval",    w: 54, h: 34, r: 17 },
  calc:     { shape: "rect",    w: 44, h: 44, r: 8  },
  switch:   { shape: "diamond", w: 44, h: 44, r: 5  },
};

const ICONS = {
  agg: "∑", sql: "⚡", constant: "C", rest: "🌐",
  lookup: "🔍", calc: "⚙", switch: "⑂", dataset: "📄",
};

export function MinimizedNode({ type, color, label, onExpand, portLeftRef, portRightRef,
  onPortLeftDrop, onPortRightDragStart, onMouseDown }) {

  const cfg = SHAPES[type] || SHAPES.dataset;
  const icon = ICONS[type] || "□";
  const { w, h } = cfg;

  // Form-Style
  const shapeStyle = cfg.shape === "diamond" ? {
    position: "absolute", inset: 0,
    transform: "rotate(45deg)",
    backgroundColor: color + "18",
    border: `2px solid ${color}55`,
    borderRadius: cfg.r,
  } : cfg.shape === "hexagon" ? {
    position: "absolute", inset: 0,
    clipPath: "polygon(25% 0%, 75% 0%, 100% 50%, 75% 100%, 25% 100%, 0% 50%)",
    backgroundColor: color + "18",
  } : {
    position: "absolute", inset: 0,
    borderRadius: cfg.shape === "circle" || cfg.shape === "oval" ? "50%" : cfg.r,
    backgroundColor: color + "18",
    border: `2px solid ${color}55`,
  };

  return (
    <div onMouseDown={onMouseDown}
      style={{ display: "inline-flex", flexDirection: "column",
        alignItems: "center", gap: 4,
        userSelect: "none", cursor: "grab", overflow: "visible" }}>

      {/* Form Container – Ports drin damit left/right/-6 und top:50% korrekt relativ zur Form sind */}
      <div style={{ position: "relative", width: w, height: h }}>

        {/* Port Links */}
        <div ref={portLeftRef}
          onDrop={onPortLeftDrop}
          onDragOver={e => e.preventDefault()}
          style={{ position: "absolute", left: -6, top: "50%",
            transform: "translateY(-50%)",
            width: 8, height: 8, borderRadius: "50%",
            backgroundColor: color, border: "2px solid #1e1e1e",
            cursor: "crosshair", zIndex: 20,
            boxShadow: `0 0 4px ${color}88` }} />

        {/* Port Rechts */}
        <div ref={portRightRef}
          draggable
          onDragStart={onPortRightDragStart}
          style={{ position: "absolute", right: -6, top: "50%",
            transform: "translateY(-50%)",
            width: 8, height: 8, borderRadius: "50%",
            backgroundColor: color, border: "2px solid #1e1e1e",
            cursor: "grab", zIndex: 20,
            boxShadow: `0 0 4px ${color}88` }} />
        {/* Hintergrundform – kein Click-Handler = nur Drag */}
        <div style={shapeStyle} />

        {/* Icon – NUR hier aufklappen */}
        <div
          onClick={(e) => { e.stopPropagation(); if (onExpand) onExpand(e); }}
          title="Aufklappen (klicken)"
          style={{
            position: "absolute", inset: 0, zIndex: 5,
            display: "flex", alignItems: "center", justifyContent: "center",
            transform: cfg.shape === "diamond" ? "none" : "none",
            cursor: "pointer", borderRadius: cfg.r,
          }}
          onMouseEnter={e => e.currentTarget.style.backgroundColor = color + "30"}
          onMouseLeave={e => e.currentTarget.style.backgroundColor = "transparent"}>
          <span style={{
            fontSize: cfg.shape === "hexagon" ? 14 : 13,
            color, fontWeight: 700, pointerEvents: "none",
            textShadow: "0 1px 3px rgba(0,0,0,0.7)",
            transform: cfg.shape === "diamond" ? "rotate(-45deg)" : "none",
            display: "block",
          }}>
            {icon}
          </span>
        </div>
      </div>

      {/* Label */}
      <span style={{ fontSize: 8, color, fontWeight: 700,
        textTransform: "uppercase", letterSpacing: "0.05em",
        maxWidth: w + 16, overflow: "hidden", textOverflow: "ellipsis",
        whiteSpace: "nowrap", textAlign: "center",
        textShadow: "0 1px 3px rgba(0,0,0,0.8)" }}>
        {label}
      </span>
    </div>
  );
}
