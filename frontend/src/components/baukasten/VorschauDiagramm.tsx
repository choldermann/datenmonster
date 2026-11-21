// Vorschau des Baukastens als Diagramm (Balken/Linie) – zeigt sofort, ob das Ergebnis „aussieht wie gedacht“.
// Achse/Werte: aus dem Stein „Ergebnis“, sonst erste Text-/Datumsspalte und die Zahlenspalten.
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const FARBEN = ["var(--accent)", "var(--ok)", "#a78bfa", "var(--err)", "#60a5fa", "#fb923c"];
const nf = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 });

export function achseUndWerte(spalten: string[], zeilen: Record<string, any>[], x?: string, y?: string[]) {
  const zahlig = (c: string) => zeilen.some((r) => typeof r[c] === "number") && zeilen.every((r) => r[c] == null || typeof r[c] === "number");
  const zahlen = spalten.filter(zahlig);
  const achse = x && spalten.includes(x) ? x : spalten.find((c) => !zahlig(c)) || spalten[0];
  const werte = (y || []).filter((c) => spalten.includes(c) && c !== achse);
  return { achse, werte: werte.length ? werte : zahlen.filter((c) => c !== achse).slice(0, 4) };
}

export default function VorschauDiagramm({ art, spalten, zeilen, x, y }: {
  art: "balken" | "linie"; spalten: string[]; zeilen: Record<string, any>[]; x?: string; y?: string[];
}) {
  const { achse, werte } = achseUndWerte(spalten, zeilen, x, y);
  if (!werte.length) return <p className="bk-info">Für ein Diagramm braucht das Ergebnis mindestens eine Zahlenspalte.</p>;
  const daten = zeilen.map((r) => ({ ...r, [achse]: r[achse] == null ? "–" : String(r[achse]).slice(0, 24) }));
  const gemeinsam = (
    <>
      <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
      <XAxis dataKey={achse} tick={{ fill: "var(--text-dim)", fontSize: 10 }} interval="preserveStartEnd" minTickGap={8} />
      <YAxis tick={{ fill: "var(--text-dim)", fontSize: 10 }} width={64} tickFormatter={(v) => nf.format(v)} />
      <Tooltip formatter={(v: any) => (typeof v === "number" ? nf.format(v) : v)}
        contentStyle={{ background: "var(--bg-card)", border: "1px solid var(--border)", fontSize: 12 }} labelStyle={{ color: "var(--text-bright)" }} />
      <Legend wrapperStyle={{ fontSize: 11 }} />
    </>
  );
  return (
    <div style={{ height: 300, border: "1px solid var(--border)", borderRadius: 8, padding: "10px 6px 2px 0" }}>
      <ResponsiveContainer width="100%" height="100%">
        {art === "balken" ? (
          <BarChart data={daten}>{gemeinsam}
            {werte.map((c, i) => <Bar key={c} dataKey={c} fill={FARBEN[i % FARBEN.length]} radius={[3, 3, 0, 0]} isAnimationActive={false} />)}
          </BarChart>
        ) : (
          <LineChart data={daten}>{gemeinsam}
            {werte.map((c, i) => <Line key={c} dataKey={c} stroke={FARBEN[i % FARBEN.length]} strokeWidth={2} dot={false} type="monotone" isAnimationActive={false} />)}
          </LineChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
