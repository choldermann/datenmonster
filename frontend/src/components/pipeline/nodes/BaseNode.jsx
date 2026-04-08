import { useRef } from "react";
import { X, Minimize2 } from "lucide-react";
import { S, NODE_COLORS, PORT_SIZE } from "../constants";

// ─── Minimierte Node-Formen pro Typ ───────────────────────────────────────────
const MINI_SHAPES = {
  trigger:     { shape: "diamond", size: 44 },
  ftp:         { shape: "circle",  size: 44 },
  mapping:     { shape: "hexagon", size: 44 },
  dispatcher:  { shape: "diamond", size: 44 },
  ftp_upload:  { shape: "circle",  size: 44 },
  email:       { shape: "circle",  size: 44 },
  condition:   { shape: "diamond", size: 44 },
};

function MiniShape({ type, color, icon, label, onExpand }) {
  const cfg = MINI_SHAPES[type] || { shape: "circle", size: 44 };
  const s = cfg.size;

  const bgStyle = cfg.shape === "diamond" ? {
    position: "absolute", inset: 0,
    transform: "rotate(45deg)",
    backgroundColor: color + "22",
    border: `2px solid ${color}55`,
    borderRadius: 6,
  } : {
    position: "absolute", inset: 0,
    borderRadius: "50%",
    backgroundColor: color + "22",
    border: `2px solid ${color}55`,
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 5 }}>
      <div style={{ position: "relative", width: s, height: s }}>
        {/* Hintergrundform – kein onClick = nur Drag */}
        <div style={bgStyle} />
        {/* Icon – NUR hier aufklappen */}
        <div
          onClick={(e) => { e.stopPropagation(); if (onExpand) onExpand(); }}
          title="Aufklappen (klicken)"
          style={{
            position: "absolute", inset: 0, zIndex: 5,
            display: "flex", alignItems: "center", justifyContent: "center",
            cursor: "pointer", borderRadius: cfg.shape === "diamond" ? 6 : "50%",
          }}
          onMouseEnter={e => e.currentTarget.style.backgroundColor = color + "35"}
          onMouseLeave={e => e.currentTarget.style.backgroundColor = "transparent"}>
          <span style={{
            fontSize: 16, color,
            transform: cfg.shape === "diamond" ? "rotate(-45deg)" : "none",
            display: "block",
            filter: "drop-shadow(0 1px 2px rgba(0,0,0,0.5))",
            pointerEvents: "none",
          }}>
            {icon}
          </span>
        </div>
      </div>
      <span style={{ fontSize: 8, color, fontWeight: 700,
        textTransform: "uppercase", letterSpacing: "0.06em",
        textShadow: "0 1px 3px rgba(0,0,0,0.8)", whiteSpace: "nowrap" }}>
        {label}
      </span>
    </div>
  );
}

function Port({ side, index = 0, total = 1, color, portRef, draggable,
  onDragStart, onDrop, onDragOver, title, minimized = false }) {
  const spacing = minimized ? 16 : 24;
  const offset = total === 1 ? 0 : (index - (total - 1) / 2) * spacing;
  const sz = minimized ? 8 : PORT_SIZE;

  const style = {
    position: "absolute",
    width: sz, height: sz,
    borderRadius: "50%",
    backgroundColor: color,
    border: `2px solid ${S.bgCard}`,
    cursor: draggable ? "grab" : "crosshair",
    boxShadow: `0 0 4px ${color}88`,
    zIndex: 20,
    ...(side === "left"
      ? { left: -sz / 2 - 2, top: `calc(50% + ${offset}px)`, transform: "translateY(-50%)" }
      : { right: -sz / 2 - 2, top: `calc(50% + ${offset}px)`, transform: "translateY(-50%)" }),
  };

  return (
    <div ref={portRef} style={style} title={title}
      draggable={draggable}
      onDragStart={onDragStart}
      onDrop={onDrop}
      onDragOver={onDragOver}
    />
  );
}

export default function BaseNode({
  node, color, icon, label,
  onRemove, onPositionChange, onUpdate,
  inputPorts = [],
  outputPorts = [],
  children,
  width = 240,
  runResult,
}) {
  const dragging = useRef(false);
  const offset = useRef({ x: 0, y: 0 });
  const nodeColor = color || NODE_COLORS[node.type] || S.accent;
  const minimized = node.minimized || false;

  const toggleMinimize = (e) => {
    e.stopPropagation();
    if (onUpdate) onUpdate({ ...node, minimized: !minimized });
  };

  const handleMouseDown = (e) => {
    if (e.target.closest("select,input,button,textarea,label")) return;
    e.preventDefault(); e.stopPropagation();
    dragging.current = true;
    offset.current = { x: e.clientX - node.x, y: e.clientY - node.y };
    const onMove = (ev) => {
      if (!dragging.current) return;
      onPositionChange(node.id, ev.clientX - offset.current.x, ev.clientY - offset.current.y);
    };
    const onUp = () => {
      dragging.current = false;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  // ── Minimierter Zustand ────────────────────────────────────────────────────
  if (minimized) {
    const cfg = MINI_SHAPES[node.type] || { shape: "circle", size: 44 };
    const s = cfg.size;
    return (
      <div
        onMouseDown={handleMouseDown}
        onClick={e => e.stopPropagation()}
        style={{
          position: "absolute", left: node.x, top: node.y,
          width: s + 20, // etwas Platz für Ports
          height: s + 30, // Platz für Label
          zIndex: 10, userSelect: "none",
          display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "flex-start",
          paddingTop: 4, cursor: "grab",
          overflow: "visible",
        }}
      >
        {/* Input Ports */}
        {inputPorts.map((p, i) => (
          <Port key={p.id} side="left" index={i} total={inputPorts.length}
            color={nodeColor} portRef={p.portRef}
            onDrop={p.onDrop} onDragOver={e => e.preventDefault()}
            title={p.label || "Eingang"} minimized />
        ))}
        {/* Output Ports */}
        {outputPorts.map((p, i) => (
          <Port key={p.id} side="right" index={i} total={outputPorts.length}
            color={nodeColor} portRef={p.portRef}
            draggable onDragStart={p.onDragStart}
            title={p.label || "Ausgang"} minimized />
        ))}
        {/* Mini-Shape */}
        <MiniShape
          type={node.type}
          color={nodeColor}
          icon={runResult
            ? (runResult.status === "ok" ? "✓" : runResult.status === "error" ? "✗" : "⚠")
            : icon}
          label={label}
          onExpand={toggleMinimize}
        />
      </div>
    );
  }

  // ── Normaler (aufgeklappter) Zustand ──────────────────────────────────────
  return (
    <div
      draggable={false}
      onClick={e => e.stopPropagation()}
      style={{
        position: "absolute", left: node.x, top: node.y, width,
        zIndex: 10, userSelect: "none",
        boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
        borderRadius: 8, overflow: "visible",
        border: `1px solid ${nodeColor}55`,
        backgroundColor: S.bgCard,
      }}
    >
      {/* Input Ports */}
      {inputPorts.map((p, i) => (
        <Port key={p.id} side="left" index={i} total={inputPorts.length}
          color={nodeColor} portRef={p.portRef}
          onDrop={p.onDrop} onDragOver={e => e.preventDefault()}
          title={p.label || "Eingang"} />
      ))}
      {/* Output Ports */}
      {outputPorts.map((p, i) => (
        <Port key={p.id} side="right" index={i} total={outputPorts.length}
          color={nodeColor} portRef={p.portRef}
          draggable onDragStart={p.onDragStart}
          title={p.label || "Ausgang"} />
      ))}

      {/* Header */}
      <div onMouseDown={handleMouseDown} style={{
        display: "flex", alignItems: "center", gap: 6,
        padding: "7px 10px", cursor: "grab",
        backgroundColor: runResult
          ? (runResult.status === "ok" ? "rgba(110,231,183,0.12)"
            : runResult.status === "error" ? "rgba(224,112,112,0.12)"
            : "rgba(251,191,36,0.12)")
          : nodeColor + "18",
        borderBottom: `1px solid ${nodeColor}33`,
        borderRadius: "8px 8px 0 0",
        transition: "background-color 0.3s",
      }}>
        <span style={{ fontSize: 13, flexShrink: 0 }}>
          {runResult
            ? (runResult.status === "ok" ? "✓" : runResult.status === "error" ? "✗" : "⚠")
            : icon}
        </span>
        <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: runResult
            ? (runResult.status === "ok" ? "#6ee7b7" : runResult.status === "error" ? "#e07070" : "#fbbf24")
            : nodeColor,
          flex: 1 }}>
          {label}
        </span>
        {runResult && (
          <span style={{ fontSize: 9,
            color: runResult.status === "ok" ? "#6ee7b7" : runResult.status === "error" ? "#e07070" : "#fbbf24",
            backgroundColor: "rgba(0,0,0,0.2)", padding: "1px 5px", borderRadius: 3,
            maxWidth: 90, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
            title={runResult.message || ""}>
            {runResult.rows != null ? `${runResult.rows} Zeilen` : runResult.message || runResult.status}
          </span>
        )}
        {/* Minimier-Button */}
        <button onClick={toggleMinimize} title="Minimieren"
          style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0, lineHeight: 1 }}
          onMouseEnter={e => e.currentTarget.style.color = nodeColor}
          onMouseLeave={e => e.currentTarget.style.color = S.textDim}>
          <Minimize2 size={10} />
        </button>
        <button onClick={() => onRemove(node.id)}
          style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0, lineHeight: 1 }}
          onMouseEnter={e => e.currentTarget.style.color = "#e07070"}
          onMouseLeave={e => e.currentTarget.style.color = S.textDim}>
          <X size={11} />
        </button>
      </div>

      {/* Body */}
      <div style={{ padding: "8px 10px" }}>
        {children}
        {runResult?.status === "error" && runResult.message && (
          <div style={{ marginTop: 6, padding: "4px 7px", borderRadius: 4,
            backgroundColor: "rgba(224,112,112,0.08)", border: "1px solid rgba(224,112,112,0.25)",
            fontSize: 9, color: "#e07070", lineHeight: 1.4 }}>
            {runResult.message}
          </div>
        )}
      </div>
    </div>
  );
}

export { Port };
