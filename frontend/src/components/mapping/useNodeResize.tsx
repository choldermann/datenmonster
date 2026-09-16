import { useState, useRef, useEffect, useCallback } from "react";

/**
 * Masse zu einer Zahl machen.
 *
 * Vorlagen-JSON wird von Hand geschrieben, und dort standen Breite/Hoehe als
 * String ("380"). Das hatte zwei Folgen, die beide wie ein Resize-Bug aussahen:
 *   1. React schreibt einen String unveraendert ins style-Attribut — `width: 380`
 *      ohne Einheit ist ungueltiges CSS und wird ignoriert. Die gespeicherte
 *      Breite kam nie an, die Node rendert auf Inhaltsbreite.
 *   2. Beim Ziehen rechnete `startW + ev.clientX` als String-Konkatenation:
 *      "380" + 495 = "380495", erst das anschliessende `- startX` machte daraus
 *      wieder eine Zahl. Die Node sprang auf ~380.000 px.
 */
export function toPx(value, fallback) {
  const n = typeof value === "number" ? value : parseFloat(value);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

/**
 * Resize fuer eine Canvas-Node: haelt die Groesse waehrend des Ziehens lokal und
 * meldet sie erst beim Loslassen nach oben (ein History-Eintrag statt hunderte).
 *
 * `onCommit(width, height)` bekommt immer Zahlen.
 */
export function useNodeResize({ node, defaultWidth, defaultHeight, minWidth = 200, minHeight = 60, onCommit }) {
  const [size, setSize] = useState(() => ({
    w: toPx(node.width, defaultWidth),
    h: toPx(node.height, defaultHeight),
  }));

  // Groesse aktuell halten, ohne den Handler bei jedem Pixel neu zu bauen.
  const sizeRef = useRef(size);
  sizeRef.current = size;
  const dragging = useRef(false);

  // Aenderungen von aussen nachziehen (Vorlage geladen, Mapping gewechselt).
  useEffect(() => {
    if (dragging.current) return;
    setSize({ w: toPx(node.width, defaultWidth), h: toPx(node.height, defaultHeight) });
  }, [node.width, node.height, defaultWidth, defaultHeight]);

  const onResizeStart = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    const start = { x: e.clientX, y: e.clientY, w: sizeRef.current.w, h: sizeRef.current.h };
    dragging.current = true;

    const calc = (ev) => ({
      w: Math.max(minWidth, start.w + ev.clientX - start.x),
      h: Math.max(minHeight, start.h + ev.clientY - start.y),
    });

    const onMove = (ev) => { if (dragging.current) setSize(calc(ev)); };
    const onUp = (ev) => {
      if (dragging.current) {
        const next = calc(ev);
        setSize(next);
        if (onCommit) onCommit(next.w, next.h);
      }
      dragging.current = false;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }, [minWidth, minHeight, onCommit]);

  return { width: size.w, height: size.h, onResizeStart };
}

/**
 * Anfasser unten rechts. Braucht einen Vorfahren mit `position: relative`.
 *
 * 16x16 statt der frueheren 10x10: der Griff sass exakt auf dem letzten
 * Output-Port, und auch wenn er den Hit-Test gewinnt, ist ein 10px-Ziel
 * zwischen lauter Drag-Punkten unangenehm zu treffen. `zIndex` haelt ihn
 * verlaesslich oben, `touchAction: none` verhindert Scroll-Gesten.
 */
export function ResizeHandle({ onMouseDown, title = "Größe ändern" }) {
  return (
    <div
      onMouseDown={onMouseDown}
      title={title}
      style={{
        position: "absolute", right: 0, bottom: 0, width: 16, height: 16,
        cursor: "nwse-resize", opacity: 0.4, zIndex: 3, touchAction: "none",
        padding: 3, boxSizing: "border-box", backgroundClip: "content-box",
        backgroundImage: "linear-gradient(135deg, transparent 30%, #888 30%, #888 40%, transparent 40%, transparent 60%, #888 60%, #888 70%, transparent 70%)",
      }}
      onMouseEnter={(e) => { e.currentTarget.style.opacity = "1"; }}
      onMouseLeave={(e) => { e.currentTarget.style.opacity = "0.4"; }}
    />
  );
}
