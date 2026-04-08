import { useMemo } from "react";
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from "recharts";
import { CHART_COLORS, S } from "../constants";

const tooltipStyle = { backgroundColor: S.bgCard, border: `1px solid #333`, borderRadius: 4, fontSize: 11 };

// ─── KPI Widget ───────────────────────────────────────────────────────────────
export function KpiWidget({ config, data }) {
  const value = useMemo(() => {
    if (!data?.length || !config.value_field) return null;
    const agg = config.agg || "SUM";
    const vals = data.map(r => parseFloat(r[config.value_field]) || 0);
    if (agg === "SUM") return vals.reduce((a, b) => a + b, 0);
    if (agg === "COUNT") return vals.length;
    if (agg === "AVG") return vals.reduce((a, b) => a + b, 0) / vals.length;
    if (agg === "MIN") return Math.min(...vals);
    if (agg === "MAX") return Math.max(...vals);
    return vals[0];
  }, [data, config]);

  const prevValue = useMemo(() => {
    if (!config.compare_data?.length || !config.value_field) return null;
    const vals = config.compare_data.map(r => parseFloat(r[config.value_field]) || 0);
    return vals.reduce((a, b) => a + b, 0);
  }, [config]);

  const delta = prevValue && value ? ((value - prevValue) / Math.abs(prevValue) * 100) : null;

  const formatted = value === null ? "–" : config.format === "currency"
    ? new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" }).format(value)
    : config.format === "percent"
    ? value.toFixed(1) + "%"
    : value.toLocaleString("de-DE", { maximumFractionDigits: 2 });

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", gap: 4 }}>
      {config.label && <p style={{ fontSize: 11, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", margin: 0 }}>{config.label}</p>}
      <p style={{ fontSize: 32, fontWeight: 800, color: "var(--accent)", margin: 0, lineHeight: 1 }}>{formatted}</p>
      {config.unit && <p style={{ fontSize: 11, color: S.textDim, margin: 0 }}>{config.unit}</p>}
      {delta !== null && (
        <div style={{ display: "flex", alignItems: "center", gap: 4, padding: "2px 8px", borderRadius: 12, backgroundColor: delta >= 0 ? "rgba(110,231,183,0.1)" : "rgba(224,112,112,0.1)" }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: delta >= 0 ? "#6ee7b7" : "#e07070" }}>
            {delta >= 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(1)}% ggü. Vorperiode
          </span>
        </div>
      )}
    </div>
  );
}

// ─── Bar Chart Widget ─────────────────────────────────────────────────────────
export function BarChartWidget({ config, data, compareData }) {
  if (!data?.length) return <EmptyState />;
  const { x_field, value_fields = [], stacked } = config;

  const chartData = useMemo(() => {
    if (!x_field) return data.slice(0, 50);
    // Aggregation
    const grouped = {};
    data.forEach(row => {
      const key = row[x_field];
      if (!grouped[key]) grouped[key] = { [x_field]: key };
      (value_fields.length ? value_fields : [Object.keys(row).find(k => k !== x_field)]).forEach(f => {
        grouped[key][f] = (grouped[key][f] || 0) + (parseFloat(row[f]) || 0);
      });
    });
    return Object.values(grouped).slice(0, 50);
  }, [data, x_field, value_fields]);

  const fields = value_fields.length ? value_fields : [Object.keys(data[0] || {}).find(k => k !== x_field)].filter(Boolean);

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={chartData} margin={{ top: 5, right: 10, bottom: 20, left: 10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
        <XAxis dataKey={x_field} tick={{ fontSize: 10, fill: S.textDim }} angle={-30} textAnchor="end" height={40} />
        <YAxis tick={{ fontSize: 10, fill: S.textDim }} />
        <Tooltip contentStyle={tooltipStyle} />
        {fields.length > 1 && <Legend wrapperStyle={{ fontSize: 10 }} />}
        {fields.map((f, i) => (
          <Bar key={f} dataKey={f} fill={CHART_COLORS[i % CHART_COLORS.length]} stackId={stacked ? "s" : undefined} radius={[2,2,0,0]} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

// ─── Line Chart Widget ────────────────────────────────────────────────────────
export function LineChartWidget({ config, data, compareData }) {
  if (!data?.length) return <EmptyState />;
  const { x_field, value_fields = [] } = config;

  const chartData = useMemo(() => {
    if (!x_field) return data.slice(0, 100);
    const grouped = {};
    data.forEach(row => {
      const key = row[x_field];
      if (!grouped[key]) grouped[key] = { [x_field]: key };
      (value_fields.length ? value_fields : [Object.keys(row).find(k => k !== x_field)]).forEach(f => {
        grouped[key][f] = (grouped[key][f] || 0) + (parseFloat(row[f]) || 0);
      });
    });
    // Vergleichszeitraum einmischen
    if (compareData?.length) {
      compareData.forEach(row => {
        const key = row[x_field];
        if (grouped[key]) {
          value_fields.forEach(f => { grouped[key][f + "_vgl"] = (grouped[key][f + "_vgl"] || 0) + (parseFloat(row[f]) || 0); });
        }
      });
    }
    return Object.values(grouped).slice(0, 100);
  }, [data, compareData, x_field, value_fields]);

  const fields = value_fields.length ? value_fields : [Object.keys(data[0] || {}).find(k => k !== x_field)].filter(Boolean);
  const hasCompare = compareData?.length > 0 && value_fields.length > 0;

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={chartData} margin={{ top: 5, right: 10, bottom: 20, left: 10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
        <XAxis dataKey={x_field} tick={{ fontSize: 10, fill: S.textDim }} angle={-30} textAnchor="end" height={40} />
        <YAxis tick={{ fontSize: 10, fill: S.textDim }} />
        <Tooltip contentStyle={tooltipStyle} />
        {(fields.length > 1 || hasCompare) && <Legend wrapperStyle={{ fontSize: 10 }} />}
        {fields.map((f, i) => (
          <Line key={f} type="monotone" dataKey={f} stroke={CHART_COLORS[i % CHART_COLORS.length]} strokeWidth={2} dot={false} />
        ))}
        {hasCompare && fields.map((f, i) => (
          <Line key={f+"_vgl"} type="monotone" dataKey={f+"_vgl"} stroke={CHART_COLORS[i % CHART_COLORS.length]} strokeWidth={1.5} strokeDasharray="4 2" dot={false} name={f + " (Vgl.)"} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

// ─── Pie Chart Widget ─────────────────────────────────────────────────────────
export function PieChartWidget({ config, data }) {
  if (!data?.length) return <EmptyState />;
  const { label_field, value_field, donut } = config;

  const chartData = useMemo(() => {
    if (!label_field || !value_field) return [];
    const grouped = {};
    data.forEach(row => {
      const key = String(row[label_field] || "Sonstige");
      grouped[key] = (grouped[key] || 0) + (parseFloat(row[value_field]) || 0);
    });
    return Object.entries(grouped).map(([name, value]) => ({ name, value })).sort((a,b) => b.value - a.value).slice(0, 10);
  }, [data, label_field, value_field]);

  return (
    <ResponsiveContainer width="100%" height="100%">
      <PieChart>
        <Pie data={chartData} dataKey="value" nameKey="name"
          innerRadius={donut ? "45%" : 0} outerRadius="70%"
          paddingAngle={2} label={({ name, percent }) => `${name} ${(percent*100).toFixed(0)}%`}
          labelLine={false}>
          {chartData.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
        </Pie>
        <Tooltip contentStyle={tooltipStyle} formatter={v => v.toLocaleString("de-DE")} />
      </PieChart>
    </ResponsiveContainer>
  );
}

// ─── Table Widget ─────────────────────────────────────────────────────────────
export function TableWidget({ config, data }) {
  if (!data?.length) return <EmptyState />;
  const cols = config.columns?.length ? config.columns : Object.keys(data[0] || {}).slice(0, 8);
  const numericCols = cols.filter(c => data.some(r => !isNaN(parseFloat(r[c]))));

  const totals = numericCols.reduce((acc, c) => {
    acc[c] = data.reduce((s, r) => s + (parseFloat(r[c]) || 0), 0);
    return acc;
  }, {});

  return (
    <div style={{ height: "100%", overflowY: "auto", scrollbarWidth: "thin" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
        <thead>
          <tr style={{ backgroundColor: S.bgEl }}>
            {cols.map(c => (
              <th key={c} style={{ padding: "6px 10px", textAlign: "left", color: S.textDim, fontWeight: 700, fontSize: 10, textTransform: "uppercase", letterSpacing: "0.05em", borderBottom: `1px solid ${S.border}`, whiteSpace: "nowrap" }}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.slice(0, config.max_rows || 100).map((row, i) => (
            <tr key={i} style={{ borderBottom: `1px solid ${S.border}`, backgroundColor: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.02)" }}>
              {cols.map(c => (
                <td key={c} style={{ padding: "5px 10px", color: numericCols.includes(c) ? S.textBright : S.textMain, textAlign: numericCols.includes(c) ? "right" : "left", whiteSpace: "nowrap" }}>
                  {numericCols.includes(c) ? (parseFloat(row[c]) || 0).toLocaleString("de-DE", { maximumFractionDigits: 2 }) : (row[c] ?? "–")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        {config.show_totals !== false && numericCols.length > 0 && (
          <tfoot>
            <tr style={{ backgroundColor: "rgba(252,228,153,0.06)", borderTop: `1px solid rgba(252,228,153,0.2)` }}>
              {cols.map(c => (
                <td key={c} style={{ padding: "6px 10px", color: "var(--accent)", fontWeight: 700, textAlign: numericCols.includes(c) ? "right" : "left", fontSize: 11 }}>
                  {numericCols.includes(c) ? totals[c].toLocaleString("de-DE", { maximumFractionDigits: 2 }) : "Summe"}
                </td>
              ))}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  );
}

// ─── Heatmap Widget ───────────────────────────────────────────────────────────
export function HeatmapWidget({ config, data }) {
  if (!data?.length) return <EmptyState />;
  const { date_field, value_field } = config;

  const byDate = useMemo(() => {
    const map = {};
    data.forEach(row => {
      const d = row[date_field]?.toString().slice(0, 10);
      if (d) map[d] = (map[d] || 0) + (parseFloat(row[value_field]) || 1);
    });
    return map;
  }, [data, date_field, value_field]);

  const maxVal = Math.max(...Object.values(byDate), 1);
  const dates = Object.keys(byDate).sort();
  if (!dates.length) return <EmptyState />;

  const startDate = new Date(dates[0]);
  const endDate = new Date(dates[dates.length - 1]);
  const weeks = [];
  let current = new Date(startDate);
  current.setDate(current.getDate() - current.getDay()); // Start bei Sonntag

  while (current <= endDate) {
    const week = [];
    for (let d = 0; d < 7; d++) {
      const dateStr = current.toISOString().slice(0, 10);
      week.push({ date: dateStr, value: byDate[dateStr] || 0 });
      current.setDate(current.getDate() + 1);
    }
    weeks.push(week);
  }

  const getColor = (v) => {
    if (v === 0) return "rgba(255,255,255,0.04)";
    const intensity = Math.min(v / maxVal, 1);
    return `rgba(252,228,153,${0.1 + intensity * 0.8})`;
  };

  return (
    <div style={{ height: "100%", overflowX: "auto", display: "flex", alignItems: "center", padding: "8px 4px" }}>
      <div style={{ display: "flex", gap: 2 }}>
        {weeks.map((week, wi) => (
          <div key={wi} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {week.map((day, di) => (
              <div key={di} title={`${day.date}: ${day.value.toLocaleString("de-DE")}`}
                style={{ width: 12, height: 12, borderRadius: 2, backgroundColor: getColor(day.value), cursor: "default" }} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 8 }}>
      <p style={{ fontSize: 24 }}>📊</p>
      <p style={{ fontSize: 11, color: S.textDim }}>Datenquelle konfigurieren</p>
    </div>
  );
}
