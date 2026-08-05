import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer,
} from "recharts";

const S = { textDim: "var(--text-dim)", border: "var(--border)" };

// Kräftige, gut unterscheidbare Farben je Serie/Plattform.
const COLORS = ["#fce499", "#6ee7b7", "#a78bfa", "#f87171", "#60a5fa", "#fb923c",
  "#34d399", "#f472b6", "#facc15", "#22d3ee", "#c084fc", "#4ade80"];

// Deutsche Tausenderpunkte für Achse & Tooltip (z.B. 6000000 → 6.000.000).
const NF = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 });
const fmtNum = (v) => (v == null || v === "" || isNaN(Number(v))) ? v : NF.format(Number(v));

export default function BarWidget({ widget, result, onDrilldown }) {
  const { rows = [] } = result;
  const cfg = widget.config || {};
  const { x_column, y_columns = [], series_column, value_column } = cfg;
  const canDrill = !!onDrilldown && !!x_column;

  // Zwei Modi:
  //  a) klassisch: feste Wert-Spalten (y_columns)
  //  b) Serien-Pivot: eine Kategorie-Spalte (series_column, z.B. Plattform) wird zu
  //     gestapelten, farblich getrennten Serien; Werte aus value_column.
  const pivot = !!(series_column && value_column);

  let data = [];
  let seriesKeys = [];
  if (pivot) {
    const xVals = [];
    const seen = new Set();
    const byX = {};
    const skSet = new Set();
    for (const r of rows) {
      const xv = r[x_column];
      const sv = r[series_column];
      if (xv == null) continue;
      if (!seen.has(xv)) { seen.add(xv); xVals.push(xv); byX[xv] = { [x_column]: xv }; }
      const key = (sv == null || sv === "") ? "Unbekannt" : String(sv);
      skSet.add(key);
      byX[xv][key] = (byX[xv][key] || 0) + Number(r[value_column] ?? 0);
    }
    seriesKeys = [...skSet];
    data = xVals.map(xv => byX[xv]);
  } else {
    seriesKeys = y_columns;
    data = rows.map(r => {
      const entry = { [x_column]: r[x_column] };
      for (const col of y_columns) entry[col] = Number(r[col] ?? 0);
      return entry;
    });
  }

  const stacked = pivot ? (cfg.stacked !== false) : !!cfg.stacked;

  if (!x_column || !seriesKeys.length) return (
    <div style={{ padding: "32px 20px", textAlign: "center", color: S.textDim, fontSize: 12 }}>
      {pivot ? "series_column/value_column konfigurieren" : "x_column und y_columns konfigurieren"}
    </div>
  );

  return (
    <div style={{ padding: "16px 8px" }}>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data} margin={{ top: 4, right: 20, bottom: 4, left: 0 }}
          style={canDrill ? { cursor: "pointer" } : undefined}
          onClick={canDrill ? (e) => { if (e && e.activeLabel != null) onDrilldown(x_column, e.activeLabel); } : undefined}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
          <XAxis dataKey={x_column} tick={{ fontSize: 11, fill: S.textDim }} />
          <YAxis tick={{ fontSize: 11, fill: S.textDim }} width={72} tickFormatter={fmtNum} />
          <Tooltip
            contentStyle={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border)",
              borderRadius: 6, fontSize: 11 }}
            labelStyle={{ color: "var(--text-bright)", fontWeight: 600 }}
            formatter={(v, name) => [fmtNum(v), name]}
          />
          {seriesKeys.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
          {seriesKeys.map((col, i) => (
            <Bar key={col} dataKey={col} name={col} stackId={stacked ? "a" : undefined}
              fill={COLORS[i % COLORS.length]} radius={stacked ? 0 : [3, 3, 0, 0]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
