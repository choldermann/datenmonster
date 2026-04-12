import { NODE_COLORS } from "./constants";

export default function PipelineSvgOverlay({ connections, nodes, nodeRefs, canvasRef, tick, onConnectionClick }) {
  if (!canvasRef?.current) return null;

  const canvasRect = canvasRef.current.getBoundingClientRect();
  const scrollLeft = canvasRef.current.scrollLeft;
  const scrollTop  = canvasRef.current.scrollTop;

  const toSvg = (rect) => ({
    left:   rect.left   - canvasRect.left  + scrollLeft,
    right:  rect.right  - canvasRect.left  + scrollLeft,
    top:    rect.top    - canvasRect.top   + scrollTop,
    height: rect.height,
  });

  const usedColors = new Set();

  const paths = connections.map((conn, i) => {
    const fromRef = nodeRefs.current[`${conn.from_node}_${conn.from_port}_out`];
    const toRef   = nodeRefs.current[`${conn.to_node}_${conn.to_port}_in`];
    if (!fromRef?.current || !toRef?.current) return null;

    const from = toSvg(fromRef.current.getBoundingClientRect());
    const to   = toSvg(toRef.current.getBoundingClientRect());

    const x1 = from.right;
    const y1 = from.top + from.height / 2;
    const x2 = to.left;
    const y2 = to.top + to.height / 2;
    const cx = Math.max(60, Math.abs(x2 - x1) * 0.5);

    // Farbe der Ausgangsnode, No-Match immer rot
    const fromNode = (nodes || []).find(n => n.id === conn.from_node);
    let color = NODE_COLORS[fromNode?.type] || "#6ee7b7";
    if (conn.from_port === "no_match") color = "#e07070";

    const markerId = `arr-${color.replace("#", "")}`;
    usedColors.add(color);

    const pathD = `M${x1} ${y1} C${x1+cx} ${y1} ${x2-cx} ${y2} ${x2} ${y2}`;
    return (
      <g key={i} style={{ pointerEvents: onConnectionClick ? "all" : "none", cursor: onConnectionClick ? "pointer" : "default" }}>
        {onConnectionClick && (
          <path d={pathD} fill="none" stroke="transparent" strokeWidth="12"
            onClick={(e) => { e.stopPropagation(); onConnectionClick(conn, i); }} />
        )}
        <path
          d={pathD}
          fill="none" stroke={color} strokeWidth="2" strokeOpacity="0.75"
          markerEnd={`url(#${markerId})`}
          onClick={onConnectionClick ? (e) => { e.stopPropagation(); onConnectionClick(conn, i); } : undefined}
          onMouseEnter={onConnectionClick ? (e) => { e.currentTarget.style.strokeWidth = "4"; e.currentTarget.style.strokeOpacity = "1"; } : undefined}
          onMouseLeave={onConnectionClick ? (e) => { e.currentTarget.style.strokeWidth = "2"; e.currentTarget.style.strokeOpacity = "0.75"; } : undefined}
        />
      </g>
    );
  }).filter(Boolean);

  if (paths.length === 0) return null;

  return (
    <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none", zIndex: 5, overflow: "visible" }}>
      <defs>
        {[...usedColors].map(color => (
          <marker key={color} id={`arr-${color.replace("#", "")}`}
            markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
            <path d="M0,0 L0,6 L8,3 z" fill={color} fillOpacity="0.85" />
          </marker>
        ))}
      </defs>
      {paths}
    </svg>
  );
}
