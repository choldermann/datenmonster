import type React from "react";

/** Mini-Fenster im jeweiligen Theme: die Kachel trägt selbst data-theme,
 *  die Farben kommen also direkt aus themes.css. */
export default function ThemeVorschau({ id }: { id: string }) {
  const zeile = (breite: string, farbe: string) => (
    <div style={{ height: 4, width: breite, borderRadius: 2, backgroundColor: farbe }} />
  );
  return (
    <div data-theme={id} style={{ backgroundColor: "var(--bg-main)", padding: 8, height: 74,
      display: "flex", gap: 6, borderBottom: "1px solid var(--border)" }}>
      <div style={{ width: 16, display: "flex", flexDirection: "column", gap: 4 }}>
        <div style={{ height: 8, backgroundColor: "var(--accent)", borderRadius: "var(--radius-sm)" }} />
        {zeile("100%", "var(--text-dim)")}
        {zeile("100%", "var(--text-dim)")}
      </div>
      <div style={{ flex: 1, backgroundColor: "var(--bg-card)", border: "1px solid var(--border)",
        borderRadius: "var(--radius)", boxShadow: "var(--shadow-card)", padding: 6,
        display: "flex", flexDirection: "column", gap: 4 }}>
        <div style={{ fontFamily: "var(--font-display)", fontSize: 10, lineHeight: 1,
          color: "var(--accent)", textShadow: "var(--glow)", fontSizeAdjust: "0.55" } as React.CSSProperties}>
          READY.
        </div>
        {zeile("80%", "var(--text-bright)")}
        {zeile("55%", "var(--text-main)")}
        <div style={{ display: "flex", gap: 4, marginTop: "auto" }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", backgroundColor: "var(--ok)" }} />
          <span style={{ width: 8, height: 8, borderRadius: "50%", backgroundColor: "var(--warn)" }} />
          <span style={{ width: 8, height: 8, borderRadius: "50%", backgroundColor: "var(--err)" }} />
          <span style={{ marginLeft: "auto", width: 22, height: 8, backgroundColor: "var(--accent)",
            borderRadius: "var(--radius-sm)" }} />
        </div>
      </div>
    </div>
  );
}
