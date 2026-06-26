import { useEffect, useRef, useState, useCallback } from "react";

const W = 180;
const H = 120;

const NODE_COLORS = {
  dataset:   "rgba(100,116,139,0.65)",
  transform: "rgba(129,140,248,0.6)",
  constant:  "rgba(167,139,250,0.6)",
  sql:       "rgba(56,189,248,0.6)",
  agg:       "rgba(245,158,11,0.6)",
  rest:      "rgba(20,184,166,0.6)",
  lookup:    "rgba(52,211,153,0.6)",
  calc:      "rgba(251,113,133,0.6)",
  sw:        "rgba(251,191,36,0.6)",
  python:    "rgba(34,197,94,0.6)",
};

function buildNodes({ canvasNodes, transformNodes, constantNodes, sqlNodes, aggNodes, restNodes, lookupNodes, calcNodes, switchNodes, pythonNodes }) {
  return [
    ...canvasNodes.map(n => ({ x: n.x, y: n.y, w: n.width || 230, h: n.height || 260, c: NODE_COLORS.dataset })),
    ...transformNodes.map(n => ({ x: n.x, y: n.y, w: 200, h: 130, c: NODE_COLORS.transform })),
    ...constantNodes.map(n => ({ x: n.x, y: n.y, w: 180, h: 80,  c: NODE_COLORS.constant })),
    ...sqlNodes.map(n =>       ({ x: n.x, y: n.y, w: 220, h: 160, c: NODE_COLORS.sql })),
    ...aggNodes.map(n =>       ({ x: n.x, y: n.y, w: 240, h: 180, c: NODE_COLORS.agg })),
    ...restNodes.map(n =>      ({ x: n.x, y: n.y, w: 240, h: 180, c: NODE_COLORS.rest })),
    ...lookupNodes.map(n =>    ({ x: n.x, y: n.y, w: 240, h: 160, c: NODE_COLORS.lookup })),
    ...calcNodes.map(n =>      ({ x: n.x, y: n.y, w: 220, h: 150, c: NODE_COLORS.calc })),
    ...switchNodes.map(n =>    ({ x: n.x, y: n.y, w: 240, h: 160, c: NODE_COLORS.sw })),
    ...(pythonNodes || []).map(n => ({ x: n.x, y: n.y, w: 300, h: 200, c: NODE_COLORS.python })),
  ];
}

export default function CanvasMinimap({
  canvasRef,
  canvasNodes = [], transformNodes = [], constantNodes = [],
  sqlNodes = [], aggNodes = [], restNodes = [], lookupNodes = [],
  calcNodes = [], switchNodes = [], pythonNodes = [],
  tick,
}) {
  const cvs = useRef(null);
  const tf  = useRef(null); // transform params for click handler
  const [visible, setVisible] = useState(false);

  const draw = useCallback(() => {
    const el     = canvasRef.current;
    const canvas = cvs.current;
    if (!el || !canvas) return;

    const nodes = buildNodes({ canvasNodes, transformNodes, constantNodes, sqlNodes, aggNodes, restNodes, lookupNodes, calcNodes, switchNodes, pythonNodes });

    if (nodes.length === 0) { setVisible(false); return; }

    // Bounding box of all nodes
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const n of nodes) {
      if (n.x < x0) x0 = n.x;
      if (n.y < y0) y0 = n.y;
      if (n.x + n.w > x1) x1 = n.x + n.w;
      if (n.y + n.h > y1) y1 = n.y + n.h;
    }
    const PAD = 32;
    x0 -= PAD; y0 -= PAD; x1 += PAD; y1 += PAD;
    const totalW = x1 - x0;
    const totalH = y1 - y0;

    // Only show when content is larger than viewport
    const needsMap = totalW > el.clientWidth + 20 || totalH > el.clientHeight + 20;
    setVisible(needsMap);
    if (!needsMap) return;

    const scale  = Math.min(W / totalW, H / totalH);
    const offX   = (W - totalW * scale) / 2;
    const offY   = (H - totalH * scale) / 2;
    tf.current   = { scale, offX, offY, x0, y0 };

    const mx = (x) => (x - x0) * scale + offX;
    const my = (y) => (y - y0) * scale + offY;

    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, W, H);

    // Background
    ctx.fillStyle = "rgba(8, 12, 24, 0.93)";
    ctx.fillRect(0, 0, W, H);

    // Subtle dot grid
    ctx.fillStyle = "rgba(255,255,255,0.05)";
    for (let gx = 6; gx < W; gx += 14) {
      for (let gy = 4; gy < H; gy += 10) {
        ctx.fillRect(gx, gy, 1, 1);
      }
    }

    // Nodes
    for (const n of nodes) {
      ctx.fillStyle = n.c;
      const nw = Math.max(n.w * scale, 3);
      const nh = Math.max(n.h * scale, 3);
      ctx.fillRect(mx(n.x), my(n.y), nw, nh);
    }

    // Viewport rect
    const vx = mx(el.scrollLeft);
    const vy = my(el.scrollTop);
    const vw = el.clientWidth  * scale;
    const vh = el.clientHeight * scale;

    ctx.fillStyle   = "rgba(252,228,153,0.07)";
    ctx.fillRect(vx, vy, vw, vh);
    ctx.strokeStyle = "rgba(252,228,153,0.65)";
    ctx.lineWidth   = 1;
    ctx.strokeRect(vx, vy, vw, vh);

  }, [canvasRef, canvasNodes, transformNodes, constantNodes, sqlNodes, aggNodes, restNodes, lookupNodes, calcNodes, switchNodes, pythonNodes]);

  // Redraw when nodes change or canvas scrolls
  useEffect(() => { draw(); }, [draw, tick]);

  useEffect(() => {
    const el = canvasRef.current;
    if (!el) return;
    el.addEventListener("scroll", draw, { passive: true });
    const ro = new ResizeObserver(draw);
    ro.observe(el);
    return () => { el.removeEventListener("scroll", draw); ro.disconnect(); };
  }, [canvasRef, draw]);

  // Click → scroll canvas to center on that point
  const handleClick = useCallback((e) => {
    const params = tf.current;
    const el     = canvasRef.current;
    const canvas = cvs.current;
    if (!params || !el || !canvas) return;

    const rect   = canvas.getBoundingClientRect();
    const cx     = e.clientX - rect.left;
    const cy     = e.clientY - rect.top;
    const canX   = (cx - params.offX) / params.scale + params.x0;
    const canY   = (cy - params.offY) / params.scale + params.y0;

    el.scrollTo({
      left: canX - el.clientWidth  / 2,
      top:  canY - el.clientHeight / 2,
      behavior: "smooth",
    });
  }, [canvasRef]);

  return (
    <div
      title="Minimap – klicken zum Navigieren"
      style={{
        position: "absolute",
        bottom: 16,
        right: 16,
        zIndex: 25,
        borderRadius: 7,
        overflow: "hidden",
        border: "1px solid rgba(255,255,255,0.09)",
        boxShadow: "0 4px 20px rgba(0,0,0,0.6)",
        cursor: "crosshair",
        opacity: visible ? 0.88 : 0,
        pointerEvents: visible ? "auto" : "none",
        transition: "opacity 0.3s",
      }}
      onMouseEnter={e => { if (visible) e.currentTarget.style.opacity = "1"; }}
      onMouseLeave={e => { if (visible) e.currentTarget.style.opacity = "0.88"; }}
    >
      <canvas ref={cvs} width={W} height={H} onClick={handleClick} />
    </div>
  );
}
