import { ChevronRight, CheckCircle2 } from "lucide-react";

const AMPEL = {
  rot:    "#e05656",
  orange: "#e8913a",
  gelb:   "#e6c84f",
  gruen:  "#5cb85c",
};
const SEV = { rot: 0, orange: 1, gelb: 2, gruen: 3 };

/**
 * Widget "tasklist": Aufgabenliste des Tages. Zeigt je Zeile eine Ampel (rot/
 * orange/gelb/grün), eine Anzahl und eine Empfehlung. Die Farbe + Anzahl kommen
 * aus dem Mapping-Ergebnis (im SQL per CASE berechnet) – hier wird NICHTS geraten.
 * Klick auf eine Zeile öffnet – sofern config.row_detail.map[check_key] gesetzt –
 * die passende Detailliste (Drilldown auf das jeweilige Fach-Mapping).
 *
 * config: { row_detail?: { key_column, map: { <check_key>: {mapping_id, title} } } }
 */
export default function TaskListWidget({ widget, result, onTaskClick }) {
  const cfg = widget.config || {};
  const rd = cfg.row_detail;
  const keyCol = rd?.key_column || "check_key";
  const rows = result.rows || [];

  const sorted = [...rows].sort((a, b) => {
    const sa = SEV[String(a.Ampel || "").toLowerCase()] ?? 9;
    const sb = SEV[String(b.Ampel || "").toLowerCase()] ?? 9;
    if (sa !== sb) return sa - sb;
    return (a.sort ?? 99) - (b.sort ?? 99);
  });

  if (!rows.length) return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "16px",
      color: "var(--text-dim)", fontSize: 13 }}>
      <CheckCircle2 size={15} style={{ color: AMPEL.gruen }} /> Keine offenen Aufgaben – alles im grünen Bereich.
    </div>
  );

  return (
    <div>
      {sorted.map((r, i) => {
        const color = AMPEL[String(r.Ampel || "").toLowerCase()] || AMPEL.gelb;
        const detail = rd?.map ? rd.map[r[keyCol]] : null;
        const canClick = !!(onTaskClick && detail?.mapping_id);
        const hasCount = r.Anzahl !== null && r.Anzahl !== undefined && r.Anzahl !== "";
        return (
          <div key={i}
            onClick={canClick ? () => onTaskClick(r, detail) : undefined}
            style={{ display: "flex", alignItems: "center", gap: 13, padding: "11px 16px",
              borderBottom: i < sorted.length - 1 ? "1px solid var(--border)" : "none",
              cursor: canClick ? "pointer" : "default" }}
            onMouseEnter={canClick ? e => e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.03)" : undefined}
            onMouseLeave={canClick ? e => e.currentTarget.style.backgroundColor = "" : undefined}>
            <span style={{ width: 11, height: 11, borderRadius: "50%", backgroundColor: color,
              flexShrink: 0, boxShadow: `0 0 8px ${color}66` }} />
            {hasCount && (
              <span style={{ fontSize: 16, fontWeight: 800, color: "var(--text-bright)",
                minWidth: 32, textAlign: "right" }}>
                {typeof r.Anzahl === "number" ? r.Anzahl.toLocaleString("de-DE") : r.Anzahl}
              </span>
            )}
            <span style={{ fontSize: 13.5, color: "var(--text-main)", flex: 1 }}>{r.Aufgabe}</span>
            {canClick && <ChevronRight size={15} style={{ color: "var(--text-dim)", flexShrink: 0 }} />}
          </div>
        );
      })}
    </div>
  );
}
