import { useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer, ReferenceLine, ReferenceArea,
} from "recharts";
import { Flag, Plus } from "lucide-react";
import { useAuth } from "../../../context/AuthContext";
import { useEreignisse, aufAchse, ereignisZeitraum, EreignisDialog } from "../ereignisse";
import { monatsAchse } from "./monat";

const S = { textDim: "var(--text-dim)" };

const COLORS = ["var(--accent)", "var(--ok)", "#a78bfa", "var(--err)", "#60a5fa", "#fb923c"];

/**
 * Liniendiagramm. Liegt auf der x-Achse eine Zeitachse (Monat „2026-03“ oder Datum), erscheinen
 * die eigenen Ereignisse automatisch: Tag = gestrichelte Linie, Zeitraum = leichte Fläche, im
 * Hinweisfenster mit Bezeichnung. config.ereignisse = false schaltet das für ein Diagramm ab.
 */
export default function LineWidget({ widget, result, onDrilldown, projectId = null }) {
  const { rows = [] } = result;
  const cfg = widget.config || {};
  const { x_column, y_columns = [], curved = false } = cfg;
  const canDrill = !!onDrilldown && !!x_column;
  const { user } = useAuth();
  const mitEreignissen = cfg.ereignisse !== false;
  const ev = useEreignisse(projectId, mitEreignissen);
  const [dialog, setDialog] = useState(null);

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

  // Ereignisse auf die Achse legen (null = keine Zeitachse → keine Markierungen, kein Knopf)
  const marken = mitEreignissen ? aufAchse(data.map(d => d[x_column]), ev.ereignisse) : null;
  const jeX = new Map();
  for (const m of marken || []) {
    const xs = data.map(d => String(d[x_column]));
    const i1 = xs.indexOf(String(m.x1)), i2 = m.x2 != null ? xs.indexOf(String(m.x2)) : i1;
    for (let i = i1; i <= i2; i++) jeX.set(xs[i], [...(jeX.get(xs[i]) || []), m.e]);
  }
  // Monatsachse als „Feb 2024“ statt „2024-02“ (Werte bleiben roh – Drilldown und Ereignisse brauchen sie)
  const alsMonat = monatsAchse(data.map(d => d[x_column]));
  const darfErfassen = !!marken && !user?.is_portal_only && projectId != null;
  const tage = (marken || []).filter(m => m.x2 == null);
  const beschriften = tage.length <= 4;

  const HinweisMitEreignissen = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    const es = jeX.get(String(label)) || [];
    return (
      <div style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 6,
        fontSize: 11, padding: "7px 10px", maxWidth: 260 }}>
        <div style={{ color: "var(--text-bright)", fontWeight: 600, marginBottom: 3 }}>{alsMonat ? alsMonat(label) : label}</div>
        {payload.map(p => (
          <div key={p.dataKey} style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
            <span style={{ color: "var(--text-dim)" }}>
              <span style={{ display: "inline-block", width: 8, height: 2, background: p.color, marginRight: 5, verticalAlign: "middle" }} />
              {p.name}
            </span>
            <span style={{ color: "var(--text-main)" }}>{Number(p.value).toLocaleString("de-DE")}</span>
          </div>
        ))}
        {es.length > 0 && (
          <div style={{ marginTop: 5, paddingTop: 5, borderTop: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 3 }}>
            {es.map(e => (
              <div key={e.id} style={{ color: "var(--text-main)" }}>
                <Flag size={10} style={{ color: "var(--text-dim)", marginRight: 4, verticalAlign: "-1px" }} />
                {e.titel} <span style={{ color: "var(--text-dim)" }}>· {e.kategorie} · {ereignisZeitraum(e)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div style={{ padding: "8px 8px 16px" }}>
      {(darfErfassen || (marken && marken.length > 0)) && (
        <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 10, padding: "0 12px 4px", fontSize: 11.5, color: S.textDim }}>
          {marken && marken.length > 0 && (
            <span title={marken.map(m => `${m.e.titel} (${ereignisZeitraum(m.e)})`).join("\n")}>
              <Flag size={11} style={{ verticalAlign: "-1px", marginRight: 3 }} />
              {marken.length} {marken.length === 1 ? "Ereignis" : "Ereignisse"}
            </span>
          )}
          {darfErfassen && (
            <button onClick={() => setDialog({ datum: new Date().toISOString().slice(0, 10) })}
              title="Aktion, Messe, Preisänderung … eintragen – erscheint als Markierung in allen Verläufen"
              style={{ display: "inline-flex", alignItems: "center", gap: 3, fontSize: 11.5, padding: "2px 8px", borderRadius: 5,
                border: "1px solid var(--border)", background: "transparent", color: "var(--text-main)", cursor: "pointer" }}>
              <Plus size={11} /> Ereignis
            </button>
          )}
        </div>
      )}
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data} margin={{ top: beschriften && tage.length ? 16 : 4, right: 20, bottom: 4, left: 0 }}
          style={canDrill ? { cursor: "pointer" } : undefined}
          onClick={canDrill ? (e) => { if (e && e.activeLabel != null) onDrilldown(x_column, e.activeLabel); } : undefined}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
          <XAxis dataKey={x_column} tick={{ fontSize: 11, fill: S.textDim }}
            tickFormatter={alsMonat || undefined} minTickGap={alsMonat ? 12 : 5} />
          <YAxis tick={{ fontSize: 11, fill: S.textDim }} width={52} />
          {(marken || []).filter(m => m.x2 != null).map(m => (
            <ReferenceArea key={`a-${m.e.id}`} x1={m.x1} x2={m.x2} fill="var(--accent)" fillOpacity={0.08} ifOverflow="extendDomain" />
          ))}
          {tage.map(m => (
            <ReferenceLine key={`l-${m.e.id}`} x={m.x1} stroke="var(--text-dim)" strokeDasharray="4 4" strokeOpacity={0.8}
              label={beschriften ? { value: m.e.titel.length > 18 ? m.e.titel.slice(0, 17) + "…" : m.e.titel,
                position: "insideTopLeft", fontSize: 10, fill: "var(--text-dim)", offset: 4 } : undefined} />
          ))}
          <Tooltip content={<HinweisMitEreignissen />} />
          {y_columns.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
          {y_columns.map((col, i) => (
            <Line key={col} dataKey={col} stroke={COLORS[i % COLORS.length]}
              strokeWidth={2} type={curved ? "monotone" : "linear"}
              dot={{ r: 3, fill: COLORS[i % COLORS.length] }} activeDot={{ r: 5 }} />
          ))}
        </LineChart>
      </ResponsiveContainer>
      {dialog && (
        <EreignisDialog projectId={projectId} vorgabe={dialog} kategorien={ev.kategorien}
          mandantName={ev.mandant_name} onClose={() => setDialog(null)} />
      )}
    </div>
  );
}
