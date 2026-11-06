/**
 * Umsatz & Umfeld: Monatsumsatz neben einer externen Größe (Wetter vom DWD, Atemwegsinfekte
 * aus RKI-GrippeWeb), je Deutschland oder Bundesland, mit Zusammenhangs- und Versatzanalyse.
 *
 * Bewusst zwei Diagramme mit gemeinsamer Monatsachse statt einer zweiten y-Achse – zwei
 * Skalen in einem Bild erzeugen Scheinzusammenhänge. Die Umfelddaten kommen über
 * /api/umfeld/reihen vom zentralen Datendienst (monstersuite), Kundendaten gehen nicht hinaus.
 *
 * Alles bezieht sich auf den gewählten Zeitraum (params.von/bis): Diagramme und Zusammenhang. Die
 * Monate davor (die Abfrage liefert bis zu 36) dienen nur als Vergleichsbasis – für den Versatz
 * (Umfeld des Vormonats) und für „ohne Saison“ (gleicher Monat im Vorjahr).
 *
 * Konfiguration (widget.config):
 *   spalten: { monat: "Monat", region: "Bundesland", wert: "Umsatz" }
 *   groesse: "atemwege" (Vorgabe) | "grippe" | "temperatur" | "niederschlag" | "sonne"
 *   region:  "Deutschland" (Vorgabe) | Bundesland
 */
import { useEffect, useMemo, useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import api, { fehlerText } from "../../../api/client";

const GROESSEN = [
  { key: "atemwege", label: "Akute Atemwegserkrankungen (ARE)" },
  { key: "grippe", label: "Grippeähnliche Erkrankungen (ILI)" },
  { key: "temperatur", label: "Temperatur (Monatsmittel)" },
  { key: "niederschlag", label: "Niederschlag (Monatssumme)" },
  { key: "sonne", label: "Sonnenscheindauer (Monatssumme)" },
];
const LAENDER = ["Baden-Württemberg", "Bayern", "Berlin", "Brandenburg", "Bremen", "Hamburg", "Hessen", "Mecklenburg-Vorpommern",
  "Niedersachsen", "Nordrhein-Westfalen", "Rheinland-Pfalz", "Saarland", "Sachsen", "Sachsen-Anhalt", "Schleswig-Holstein", "Thüringen"];
const FARBE_UMSATZ = "var(--accent)";
const FARBE_UMFELD = "#a78bfa";
const nf0 = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const nf2 = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
// „2024-02“ liest sich leicht als 2. Quartal – deshalb überall „Feb 2024“.
const MONATE = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];
export const monatText = (m) => /^\d{4}-\d{2}/.test(String(m)) ? `${MONATE[Number(String(m).slice(5, 7)) - 1]} ${String(m).slice(0, 4)}` : String(m ?? "");
const zahl = (x) => { const n = typeof x === "number" ? x : Number(String(x ?? "").replace(",", ".")); return Number.isFinite(n) ? n : null; };

// ── Statistik (rein) ──
export function korrelation(a, b) {
  const p = a.map((x, i) => [x, b[i]]).filter(([x, y]) => x != null && y != null);
  const n = p.length;
  if (n < 6) return { r: null, n };
  const mx = p.reduce((s, q) => s + q[0], 0) / n, my = p.reduce((s, q) => s + q[1], 0) / n;
  let sxy = 0, sxx = 0, syy = 0;
  for (const [x, y] of p) { sxy += (x - mx) * (y - my); sxx += (x - mx) ** 2; syy += (y - my) ** 2; }
  return { r: sxx && syy ? sxy / Math.sqrt(sxx * syy) : null, n };
}
// Umfeld geht um `lag` Monate voraus: Umsatz[t] gegen Umfeld[t - lag]
const verschoben = (umfeld, lag) => umfeld.map((_, i) => (i - lag >= 0 ? umfeld[i - lag] : null));
// Saisonbereinigt: Veränderung zum Vorjahresmonat (Umsatz relativ, Umfeld absolut)
const zumVorjahr = (xs, relativ) => xs.map((x, i) => {
  const v = i >= 12 ? xs[i - 12] : null;
  if (x == null || v == null) return null;
  return relativ ? (v > 0 ? x / v - 1 : null) : x - v;
});
// `nur` (optional): Indizes, die zählen – die Reihen davor liefern nur Vormonat/Vorjahr.
export function besterVersatz(umsatz, umfeld, maxLag = 3, nur = null) {
  let best = null;
  const maske = (xs) => (nur ? xs.map((x, i) => (nur.has(i) ? x : null)) : xs);
  for (let lag = 0; lag <= maxLag; lag++) {
    const k = korrelation(maske(umsatz), verschoben(umfeld, lag));
    if (k.r != null && (!best || Math.abs(k.r) > Math.abs(best.r) + 0.02)) best = { ...k, lag };   // kleiner Versatz gewinnt bei Gleichstand
  }
  return best;
}
const staerke = (r) => { const a = Math.abs(r); return a >= 0.6 ? "deutlich" : a >= 0.3 ? "mäßig" : "kaum"; };

export default function UmfeldWidget({ widget, result, params = {} }) {
  const cfg = widget.config || {};
  const sp = { monat: "Monat", region: "Bundesland", wert: "Umsatz", ...(cfg.spalten || {}) };
  const [groesse, setGroesse] = useState(cfg.groesse || "atemwege");
  const [region, setRegion] = useState(cfg.region || "Deutschland");
  const [umfeld, setUmfeld] = useState(null);
  const [fehler, setFehler] = useState(null);
  const [laedt, setLaedt] = useState(false);

  // Umsatz je Monat für die Region; der laufende Monat ist unvollständig und fällt weg.
  const umsatz = useMemo(() => {
    const m = new Map();
    for (const r of result?.rows || []) {
      if (region !== "Deutschland" && r[sp.region] !== region) continue;
      const k = String(r[sp.monat]).slice(0, 7);
      m.set(k, (m.get(k) || 0) + (zahl(r[sp.wert]) || 0));
    }
    const jetzt = new Date().toISOString().slice(0, 7);
    return [...m.entries()].filter(([k]) => k < jetzt).sort((a, b) => a[0].localeCompare(b[0]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result, region]);
  const von = umsatz[0]?.[0], bis = umsatz[umsatz.length - 1]?.[0];

  useEffect(() => {
    if (!von || !bis) return;
    let lebt = true;
    setLaedt(true); setFehler(null);
    api.post("/api/umfeld/reihen", { groessen: [groesse], regionen: [region], von, bis })
      .then(({ data }) => lebt && setUmfeld(data.reihen?.[0] || null))
      .catch((e) => lebt && setFehler(fehlerText(e)))
      .finally(() => lebt && setLaedt(false));
    return () => { lebt = false; };
  }, [groesse, region, von, bis]);

  const werteUmfeld = umfeld?.werte?.[region] || {};
  const daten = umsatz.map(([m, v]) => ({ Monat: m, Umsatz: Math.round(v), Umfeld: werteUmfeld[m] ?? null }));
  // Angezeigt wird der gewählte Zeitraum; ist er kürzer als 3 Monate, die letzten 12 als Verlauf.
  const selVon = String(params?.von || "").slice(0, 7), selBis = String(params?.bis || "").slice(0, 7);
  let anzeige = daten.filter((d) => (!selVon || d.Monat >= selVon) && (!selBis || d.Monat <= selBis));
  const zuKurz = anzeige.length < 3;
  if (zuKurz) anzeige = daten.slice(-12);
  const reiheU = daten.map((d) => d.Umsatz), reiheF = daten.map((d) => d.Umfeld);
  // Nur Monate des angezeigten Zeitraums zählen; die Monate davor liefern Vormonat und Vorjahr.
  const imZeitraum = new Set(daten.map((d, i) => (anzeige.includes(d) ? i : -1)).filter((i) => i >= 0));
  const schl = JSON.stringify([reiheU, reiheF, [...imZeitraum]]);
  const roh = useMemo(() => besterVersatz(reiheU, reiheF, 3, imZeitraum), [schl]); // eslint-disable-line react-hooks/exhaustive-deps
  const bereinigt = useMemo(() => besterVersatz(zumVorjahr(reiheU, true), zumVorjahr(reiheF, false), 2, imZeitraum),
    [schl]); // eslint-disable-line react-hooks/exhaustive-deps

  const gLabel = GROESSEN.find((g) => g.key === groesse)?.label || groesse;
  const kurzG = gLabel.replace(/ \(.*\)$/, "");
  const einheit = umfeld?.einheit || "";
  const fmtU = (v) => v == null ? "–" : `${nf0.format(v)} €`;
  const fmtF = (v) => v == null ? "–" : `${einheit === "°C" ? nf1.format(v) : nf0.format(v)} ${einheit}`;
  const satz = (k, bereinigtText) => {
    if (!k || k.r == null) return null;
    const richtung = k.r >= 0 ? "mehr" : "weniger";
    const versatz = k.lag === 0 ? "im selben Monat" : `wenn ${kurzG} ${k.lag} Monat${k.lag > 1 ? "e" : ""} vorausgeht`;
    return (
      <span>
        {bereinigtText}: <b style={{ color: "var(--text-bright)" }}>{staerke(k.r)}</b> (r = {nf2.format(k.r)}, {k.n} Monate),
        am stärksten {versatz}{Math.abs(k.r) >= 0.3 ? ` – höhere Werte gehen mit ${richtung} Umsatz einher` : ""}.
      </span>
    );
  };

  const auswahl = { padding: "5px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg-elevated)",
    color: "var(--text-main)", fontSize: 12.5 };
  const achse = { fontSize: 11, fill: "var(--text-dim)" };
  const hinweis = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    const d = payload[0].payload;
    return (
      <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 6, padding: "7px 10px", fontSize: 11.5 }}>
        <div style={{ fontWeight: 600, color: "var(--text-bright)", marginBottom: 3 }}>{monatText(label)}</div>
        <div><span style={{ color: FARBE_UMSATZ }}>■</span> Umsatz {fmtU(d.Umsatz)}</div>
        <div><span style={{ color: FARBE_UMFELD }}>■</span> {kurzG} {fmtF(d.Umfeld)}</div>
      </div>
    );
  };

  if (!(result?.rows || []).length) return <p style={{ padding: 16, margin: 0, color: "var(--text-dim)", fontSize: 13 }}>Keine Umsätze für den Vergleich.</p>;

  return (
    <div style={{ padding: "12px 16px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
        <select value={groesse} onChange={(e) => setGroesse(e.target.value)} style={auswahl} aria-label="Umfeldgröße">
          {GROESSEN.map((g) => <option key={g.key} value={g.key}>{g.label}</option>)}
        </select>
        <select value={region} onChange={(e) => setRegion(e.target.value)} style={auswahl} aria-label="Region">
          <option value="Deutschland">Deutschland</option>
          {LAENDER.map((l) => <option key={l} value={l}>{l}</option>)}
        </select>
        <span style={{ fontSize: 12, color: "var(--text-dim)" }}>
          Umsatz nach Lieferadresse{region !== "Deutschland" ? ` in ${region}` : " (Deutschland)"}
          {anzeige.length ? `, ${monatText(anzeige[0].Monat)} bis ${monatText(anzeige[anzeige.length - 1].Monat)}` : ""}
          {zuKurz ? " (gewählter Zeitraum zu kurz, gezeigt: die letzten 12 abgeschlossenen Monate)" : ""}
        </span>
      </div>

      {fehler && <p style={{ margin: 0, fontSize: 12.5, color: "var(--err-soft, var(--err))" }}>Umfelddaten nicht verfügbar: {fehler}</p>}

      <div>
        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-main)", margin: "2px 0 2px 4px" }}>
          <span style={{ color: FARBE_UMSATZ }}>■</span> Umsatz je Monat
        </div>
        <ResponsiveContainer width="100%" height={190}>
          <LineChart data={anzeige} syncId={`umfeld-${widget.id}`} margin={{ top: 6, right: 16, bottom: 0, left: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(127,127,127,0.12)" />
            <XAxis dataKey="Monat" tick={achse} hide />
            <YAxis tick={achse} width={60} tickFormatter={(v) => v >= 1e6 ? `${nf1.format(v / 1e6)} Mio` : v >= 1e3 ? `${nf0.format(v / 1e3)} T` : nf0.format(v)} />
            <Tooltip content={hinweis} />
            <Line dataKey="Umsatz" stroke={FARBE_UMSATZ} strokeWidth={2} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-main)", margin: "6px 0 2px 4px" }}>
          <span style={{ color: FARBE_UMFELD }}>■</span> {gLabel}{einheit ? ` (${einheit})` : ""}{laedt ? " – lädt…" : ""}
        </div>
        <ResponsiveContainer width="100%" height={170}>
          <LineChart data={anzeige} syncId={`umfeld-${widget.id}`} margin={{ top: 6, right: 16, bottom: 4, left: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(127,127,127,0.12)" />
            <XAxis dataKey="Monat" tick={achse} minTickGap={18} tickFormatter={monatText} />
            <YAxis tick={achse} width={60} tickFormatter={(v) => einheit === "°C" ? nf1.format(v) : nf0.format(v)} />
            <Tooltip content={hinweis} />
            <Line dataKey="Umfeld" stroke={FARBE_UMFELD} strokeWidth={2} dot={false} activeDot={{ r: 4 }} connectNulls isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: "10px 12px", fontSize: 13, lineHeight: 1.5,
        display: "flex", flexDirection: "column", gap: 4, color: "var(--text-main)" }}>
        <strong style={{ fontSize: 12, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: ".05em" }}>
          Zusammenhang{anzeige.length ? ` · ${monatText(anzeige[0].Monat)} bis ${monatText(anzeige[anzeige.length - 1].Monat)}` : ""}
        </strong>
        {roh?.r != null ? satz(roh, "Im Verlauf") : <span style={{ color: "var(--text-dim)" }}>Im Verlauf: der Zeitraum hat zu wenige Monate (mindestens 6).</span>}
        {bereinigt?.r != null
          ? satz(bereinigt, "Ohne Saison (jeder Monat gegen denselben Monat im Vorjahr)")
          : <span style={{ color: "var(--text-dim)" }}>Ohne Saison: für mindestens 6 Monate des Zeitraums fehlt der Vorjahresmonat.</span>}
        {roh?.n != null && roh.n < 12 && (
          <span style={{ fontSize: 12, color: "var(--warn, var(--text-dim))" }}>
            Nur {roh.n} Monate – die Aussage ist unsicher. Mit „Letzte 12 Monate“ oder einem längeren Zeitraum wird sie belastbarer.
          </span>
        )}
        <span style={{ fontSize: 12, color: "var(--text-dim)" }}>
          Der erste Wert enthält die Jahreszeit: Steigt beides im Winter, hängt es „im Verlauf“ zusammen, auch wenn nur die Saison
          dahintersteckt. Der zweite rechnet sie heraus – er sagt, ob ein stärkerer Winter als im Vorjahr auch mehr Umsatz als im
          Vorjahr brachte. Ein Zusammenhang ist noch keine Ursache.
        </span>
      </div>

      {umfeld && (
        <span style={{ fontSize: 11.5, color: "var(--text-dim)" }}>
          Quelle: {umfeld.quelle}{umfeld.stand ? ` · Stand ${/^\d{4}-W\d{2}$/.test(umfeld.stand) ? `KW ${umfeld.stand.slice(6)}/${umfeld.stand.slice(0, 4)}` : monatText(umfeld.stand)}` : ""}
          {region !== "Deutschland" && groesse !== "temperatur" && groesse !== "niederschlag" && groesse !== "sonne"
            ? " · Bundesländer erben den Wert ihrer GrippeWeb-Großregion" : ""}
          {umfeld.hinweis ? ` · ${umfeld.hinweis}` : ""}
        </span>
      )}
    </div>
  );
}
