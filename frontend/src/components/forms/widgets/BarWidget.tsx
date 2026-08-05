import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer,
} from "recharts";

const S = { textDim: "var(--text-dim)", border: "var(--border)" };

const COLORS = ["#fce49980", "#6ee7b780", "#a78bfa80", "#f87171aa", "#60a5faaa", "#fb923caa"];

// Deutsche Tausenderpunkte für Achse & Tooltip (z.B. 6000000 → 6.000.000).
const NF = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 });
const fmtNum = (v) => (v == null || v === "" || isNaN(Number(v))) ? v : NF.format(Number(v));

export default function BarWidget({ widget, result, onDrilldown }) {
  const { rows = [] } = result;
  const cfg = widget.config || {};
  const { x_column, y_columns = [], stacked = false } = cfg;
  const canDrill = !!onDrilldown && !!x_column;

  if (!x_column || !y_columns.length) return (
    <div style={{ padding: "32px 20px", textAlign: "center", color: S.textDim, fontSize: 12 }}>
      x_column und y_columns konfigurieren
    </div>
  );

  const data = rows.map(r => {
    const entry = { [x_column]: r[x_column] };
    for (const col of y_columns) entry[col] = Number(r[col] ?? 0);
    return entry;
  });

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
          {y_columns.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
          {y_columns.map((col, i) => (
            <Bar key={col} dataKey={col} stackId={stacked ? "a" : undefined}
              fill={COLORS[i % COLORS.length]} radius={[3, 3, 0, 0]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
