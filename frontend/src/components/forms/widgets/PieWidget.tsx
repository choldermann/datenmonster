import {
  PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
} from "recharts";

const S = { textDim: "var(--text-dim)" };

const COLORS = ["#fce499", "#6ee7b7", "#a78bfa", "#f87171", "#60a5fa", "#fb923c",
                "#34d399", "#f472b6", "#38bdf8", "#facc15"];

export default function PieWidget({ widget, result, onDrilldown }) {
  const { rows = [] } = result;
  const cfg = widget.config || {};
  const { label_column, value_column, donut = false } = cfg;
  const canDrill = !!onDrilldown && !!label_column;

  if (!label_column || !value_column) return (
    <div style={{ padding: "32px 20px", textAlign: "center", color: S.textDim, fontSize: 12 }}>
      label_column und value_column konfigurieren
    </div>
  );

  const data = rows.map(r => ({
    name:  String(r[label_column] ?? ""),
    value: Number(r[value_column] ?? 0),
  })).filter(d => d.value !== 0);

  const innerRadius = donut ? "55%" : "0%";

  return (
    <div style={{ padding: "16px 8px" }}>
      <ResponsiveContainer width="100%" height={280}>
        <PieChart>
          <Pie data={data} cx="50%" cy="50%" outerRadius="70%"
            innerRadius={innerRadius} dataKey="value" nameKey="name"
            label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
            labelLine={false}
            style={canDrill ? { cursor: "pointer" } : undefined}
            onClick={canDrill ? (d) => { if (d && d.name != null) onDrilldown(label_column, d.name); } : undefined}>
            {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
          </Pie>
          <Tooltip
            contentStyle={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border)",
              borderRadius: 6, fontSize: 11 }}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
