const S = {
  textBright: "var(--text-bright)", textDim: "var(--text-dim)", textMain: "var(--text-main)",
};

function aggregate(rows, column, method) {
  const vals = rows.map(r => r[column]).filter(v => v !== null && v !== undefined && v !== "");
  if (!vals.length) return null;
  switch (method) {
    case "sum":   return vals.reduce((s, v) => s + Number(v), 0);
    case "avg":   return vals.reduce((s, v) => s + Number(v), 0) / vals.length;
    case "count": return vals.length;
    case "max":   return Math.max(...vals.map(Number));
    case "min":   return Math.min(...vals.map(Number));
    default:      return vals[0]; // "first"
  }
}

function formatValue(val, decimals = 0, prefix = "", suffix = "") {
  if (val === null || val === undefined) return "—";
  const n = Number(val);
  if (isNaN(n)) return String(val);
  const formatted = n.toLocaleString("de-DE", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  return `${prefix}${formatted}${suffix}`;
}

export default function KpiWidget({ widget, result }) {
  const { rows = [] } = result;
  const cfg = widget.config || {};
  const { column, aggregation = "first", prefix = "", suffix = "", decimals = 0, color } = cfg;
  const label = widget.label || column || "KPI";

  if (!column) return (
    <div style={{ padding: "32px 20px", textAlign: "center", color: S.textDim, fontSize: 12 }}>
      Keine Spalte konfiguriert
    </div>
  );

  const raw  = aggregate(rows, column, aggregation);
  const text = formatValue(raw, Number(decimals) || 0, prefix, suffix);

  const kpiColor = color || "var(--accent)";

  return (
    <div style={{ padding: "28px 24px", textAlign: "center" }}>
      <div style={{ fontSize: 42, fontWeight: 800, color: kpiColor,
        letterSpacing: "-0.02em", lineHeight: 1.1, marginBottom: 8 }}>
        {text}
      </div>
      <div style={{ fontSize: 12, fontWeight: 600, color: S.textDim,
        textTransform: "uppercase", letterSpacing: "0.08em" }}>
        {label}
      </div>
    </div>
  );
}
