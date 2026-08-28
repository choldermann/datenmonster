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
  const {
    column, aggregation = "first", prefix = "", suffix = "", decimals = 0, color,
    // Vorperioden-/Vorjahresvergleich: zweite Spalte aus derselben SQL-Zeile.
    compare_column, compare_label = "Vorperiode", invert_delta = false,
    // Zusammensetzung: weitere Spalten aus derselben SQL-Zeile als kleine Zeilen
    // unter dem Wert (z.B. Warenumsatz − Wareneinsatz = Rohertrag). Jeder Eintrag:
    // { label, column, prefix?, suffix?, decimals? } – prefix/suffix/decimals fallen
    // auf die Widget-Werte zurück.
    breakdown,
    // Erklärender Satz zur Kennzahl. Als Tooltip an der Beschriftung – manche Zahlen
    // sind ohne ihre Definition nicht deutbar (»davon storniert« etwa erklärt die
    // Differenz zur JTL-Statistik, die Stornos einschließt).
    hint,
  } = cfg;
  const label = widget.label || column || "KPI";

  if (!column) return (
    <div style={{ padding: "32px 20px", textAlign: "center", color: S.textDim, fontSize: 12 }}>
      Keine Spalte konfiguriert
    </div>
  );

  const raw  = aggregate(rows, column, aggregation);
  const text = formatValue(raw, Number(decimals) || 0, prefix, suffix);

  const kpiColor = color || "var(--accent)";

  // Delta gegen die Vergleichsspalte (Vorperiode/Vorjahr) berechnen.
  const cmp = compare_column ? aggregate(rows, compare_column, aggregation) : null;
  let delta = null;
  if (compare_column && raw != null && cmp != null && Number(cmp) !== 0) {
    const pct = ((Number(raw) - Number(cmp)) / Math.abs(Number(cmp))) * 100;
    const up = Number(raw) >= Number(cmp);
    // Bei invert_delta ist ein Rückgang "gut" (z.B. Storno-Quote) → grün trotz Pfeil unten.
    const good = invert_delta ? !up : up;
    delta = {
      up,
      color: good ? "#6ee7b7" : "#e07070",
      pct: Math.abs(pct).toLocaleString("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1 }),
      cmpText: formatValue(cmp, Number(decimals) || 0, prefix, suffix),
    };
  }

  return (
    <div style={{ padding: "24px 24px", textAlign: "center" }}>
      <div style={{ fontSize: 42, fontWeight: 800, color: kpiColor,
        letterSpacing: "-0.02em", lineHeight: 1.1, marginBottom: 8 }}>
        {text}
      </div>
      <div title={hint || undefined}
        style={{ fontSize: 12, fontWeight: 600, color: S.textDim,
          textTransform: "uppercase", letterSpacing: "0.08em",
          cursor: hint ? "help" : undefined,
          borderBottom: hint ? "1px dotted var(--border)" : undefined,
          display: "inline-block" }}>
        {label}
      </div>
      {delta && (
        <div style={{ marginTop: 10, fontSize: 12, color: delta.color,
          display: "flex", alignItems: "center", justifyContent: "center", gap: 4 }}>
          <span style={{ fontWeight: 700 }}>{delta.up ? "↑" : "↓"} {delta.up ? "+" : "−"}{delta.pct} %</span>
          <span style={{ color: S.textDim, fontWeight: 400 }}>
            {compare_label}: {delta.cmpText}
          </span>
        </div>
      )}
      {compare_column && !delta && cmp != null && (
        <div style={{ marginTop: 10, fontSize: 11, color: S.textDim }}>
          {compare_label}: {formatValue(cmp, Number(decimals) || 0, prefix, suffix)}
        </div>
      )}
      {Array.isArray(breakdown) && breakdown.length > 0 && (
        <div style={{ marginTop: 12, paddingTop: 10, borderTop: "1px solid var(--border)",
          display: "flex", flexDirection: "column", gap: 3 }}>
          {breakdown.map((b, i) => {
            const bv = aggregate(rows, b.column, aggregation);
            return (
              <div key={i} style={{ display: "flex", justifyContent: "space-between",
                fontSize: 11, color: S.textDim }}>
                <span>{b.label || b.column}</span>
                <span style={{ fontWeight: 600, color: S.textMain }}>
                  {formatValue(bv,
                    b.decimals != null ? Number(b.decimals) : Number(decimals) || 0,
                    b.prefix != null ? b.prefix : prefix,
                    b.suffix != null ? b.suffix : suffix)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
