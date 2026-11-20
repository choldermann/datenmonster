import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer,
} from "recharts";
import { monatsAchse } from "./monat";
import { useArbeitstageSchalter } from "../arbeitstage";
import { useMarktvergleich } from "../marktvergleich";

const S = { textDim: "var(--text-dim)", border: "var(--border)" };

// Kräftige, gut unterscheidbare Farben je Serie/Plattform.
const COLORS = ["var(--accent)", "var(--ok)", "#a78bfa", "var(--err)", "#60a5fa", "#fb923c",
  "#34d399", "#f472b6", "#facc15", "#22d3ee", "#c084fc", "#4ade80"];

// Deutsche Tausenderpunkte für Achse & Tooltip (z.B. 6000000 → 6.000.000).
const NF = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 });
const fmtNum = (v) => (v == null || v === "" || isNaN(Number(v))) ? v : NF.format(Number(v));
const NF2 = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 });

/**
 * Balkendiagramm. config.arbeitstage = { spalten: { Wert: 0 } } oder { spalten: "*" } (alle Serien,
 * z. B. im Serien-Pivot) bietet bei einer Monatsachse den Schalter „Arbeitstage“ (siehe arbeitstage.tsx).
 */
export default function BarWidget({ widget, result, onDrilldown, projectId = null }) {
  const { rows = [] } = result;
  const cfg = widget.config || {};
  const { x_column, y_columns = [], series_column, value_column } = cfg;
  const canDrill = !!onDrilldown && !!x_column;
  const monatsachse = !!monatsAchse(rows.map(r => r[x_column]));
  const at = useArbeitstageSchalter({ widget, projectId, spalten: cfg.arbeitstage?.spalten || null, monatsachse });
  // Schalter „Markt“ wie im Liniendiagramm: Marktreihe als gestrichelte Linie mit rechter Achse
  const markt = useMarktvergleich({ widget, projectId, moeglich: monatsachse && cfg.markt !== false });

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

  at.anwenden(data, x_column, seriesKeys);
  const mitMarkt = markt.anwenden(data, x_column);
  const stacked = pivot ? (cfg.stacked !== false) : !!cfg.stacked;

  if (!x_column || !seriesKeys.length) return (
    <div style={{ padding: "32px 20px", textAlign: "center", color: S.textDim, fontSize: 12 }}>
      {pivot ? "series_column/value_column konfigurieren" : "x_column und y_columns konfigurieren"}
    </div>
  );

  // Monatsachse als „Feb 2024“ statt „2024-02“ (Werte bleiben roh für den Drilldown)
  const alsMonat = monatsAchse(data.map(d => d[x_column]));

  return (
    <div style={{ padding: at.moeglich || markt.moeglich ? "8px 8px 16px" : "16px 8px" }}>
      {(at.moeglich || markt.moeglich) && (
        <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 10, padding: "0 12px 4px" }}>
          {markt.knopf}{at.knopf}
        </div>
      )}
      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart data={data} margin={{ top: 4, right: 20, bottom: 4, left: 0 }}
          style={canDrill ? { cursor: "pointer" } : undefined}
          onClick={canDrill ? (e) => { if (e && e.activeLabel != null) onDrilldown(x_column, e.activeLabel); } : undefined}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
          <XAxis dataKey={x_column} tick={{ fontSize: 11, fill: S.textDim }}
            tickFormatter={alsMonat || undefined} minTickGap={alsMonat ? 12 : 5} />
          <YAxis tick={{ fontSize: 11, fill: S.textDim }} width={72} tickFormatter={fmtNum} />
          {mitMarkt && (
            <YAxis yAxisId="markt" orientation="right" width={48} domain={["auto", "auto"]}
              tick={{ fontSize: 10.5, fill: S.textDim }} tickFormatter={(v) => NF2.format(v)}
              label={{ value: markt.einheit, angle: 90, position: "insideRight", fontSize: 10, fill: S.textDim, dx: 6 }} />
          )}
          <Tooltip
            contentStyle={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border)",
              borderRadius: 6, fontSize: 11 }}
            labelStyle={{ color: "var(--text-bright)", fontWeight: 600 }}
            formatter={(v, name) => [String(name).startsWith("Markt: ") ? (v == null ? "–" : NF2.format(Number(v))) : fmtNum(v), name]}
            labelFormatter={(l) => at.moeglich
              ? <>{alsMonat ? alsMonat(l) : l}{at.hinweis(l)}</>
              : (alsMonat ? alsMonat(l) : l)}
          />
          {(seriesKeys.length > 1 || mitMarkt) && <Legend wrapperStyle={{ fontSize: 11 }} />}
          {seriesKeys.map((col, i) => (
            <Bar key={col} dataKey={col} name={at.name(col)} stackId={stacked ? "a" : undefined}
              fill={COLORS[i % COLORS.length]} radius={stacked ? 0 : [3, 3, 0, 0]} />
          ))}
          {mitMarkt && (
            <Line yAxisId="markt" dataKey={markt.name} name={`${markt.name} (${markt.einheit}, rechte Achse)`}
              stroke="var(--text-dim)" strokeWidth={2} strokeDasharray="6 4" type="monotone"
              dot={false} activeDot={{ r: 4 }} connectNulls />
          )}
        </ComposedChart>
      </ResponsiveContainer>
      {at.dialog}
      {markt.dialog}
    </div>
  );
}
