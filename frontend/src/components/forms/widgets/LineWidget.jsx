import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer, Dot,
} from "recharts";

const S = { textDim: "var(--text-dim)" };

const COLORS = ["#fce499", "#6ee7b7", "#a78bfa", "#f87171", "#60a5fa", "#fb923c"];

export default function LineWidget({ widget, result }) {
  const { rows = [] } = result;
  const cfg = widget.config || {};
  const { x_column, y_columns = [], curved = false } = cfg;

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
        <LineChart data={data} margin={{ top: 4, right: 20, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
          <XAxis dataKey={x_column} tick={{ fontSize: 11, fill: S.textDim }} />
          <YAxis tick={{ fontSize: 11, fill: S.textDim }} width={52} />
          <Tooltip
            contentStyle={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border)",
              borderRadius: 6, fontSize: 11 }}
            labelStyle={{ color: "var(--text-bright)", fontWeight: 600 }}
          />
          {y_columns.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
          {y_columns.map((col, i) => (
            <Line key={col} dataKey={col} stroke={COLORS[i % COLORS.length]}
              strokeWidth={2} type={curved ? "monotone" : "linear"}
              dot={{ r: 3, fill: COLORS[i % COLORS.length] }} activeDot={{ r: 5 }} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
