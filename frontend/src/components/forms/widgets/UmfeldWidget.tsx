/**
 * Umsatz & Umfeld: Monatsumsatz neben einer externen Größe (Wetter vom DWD, Atemwegsinfekte
 * aus RKI-GrippeWeb, Übernachtungen und Gastgewerbe-Umsatz), je Deutschland oder Bundesland,
 * mit Zusammenhangs- und Versatzanalyse. Größen mit nurDE gibt es nur für Deutschland insgesamt.
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
 *   groesse: "atemwege" (Vorgabe) | "grippe" | "temperatur" | "niederschlag" | "sonne" | "uebernachtungen" | "umsatz_gastgewerbe"
 *   region:  "Deutschland" (Vorgabe) | Bundesland
 *   warengruppen: { liste: { mapping_id }, umsatz: { mapping_id } } – optional. Die Liste liefert
 *     die Warengruppen (Spalte „Warengruppe“, größte zuerst); bei Auswahl einer Gruppe lädt die
 *     Kachel deren Umsätze über das zweite Mapping (Parameter :warengruppe) nach. Alle Gruppen
 *     auf einmal zu laden sprengte die Zeilengrenze (36 Monate × 17 Regionen × n Gruppen).
 */
import { useEffect, useMemo, useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import api, { fehlerText } from "../../../api/client";
import { monatText } from "./monat";

const GROESSEN = [
  { key: "atemwege", label: "Akute Atemwegserkrankungen (ARE)" },
  { key: "grippe", label: "Grippeähnliche Erkrankungen (ILI)" },
  { key: "temperatur", label: "Temperatur (Monatsmittel)" },
  { key: "niederschlag", label: "Niederschlag (Monatssumme)" },
  { key: "sonne", label: "Sonnenscheindauer (Monatssumme)" },
  { key: "uebernachtungen", label: "Übernachtungen (Hotels, Pensionen …)" },
  { key: "umsatz_gastgewerbe", label: "Umsatz im Gastgewerbe (Index)", nurDE: true },
];
const LAENDER = ["Baden-Württemberg", "Bayern", "Berlin", "Brandenburg", "Bremen", "Hamburg", "Hessen", "Mecklenburg-Vorpommern",
  "Niedersachsen", "Nordrhein-Westfalen", "Rheinland-Pfalz", "Saarland", "Sachsen", "Sachsen-Anhalt", "Schleswig-Holstein", "Thüringen"];
const FARBE_UMSATZ = "var(--accent)";
const FARBE_UMFELD = "#a78bfa";
const nf0 = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const nf2 = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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
// Lückenlose Monatsfolge von a bis b („2024-01“ … „2026-10“) – Monate ohne Umsatz zählen als 0,
// sonst verrutschen Vormonat und Vorjahresmonat (i - 1, i - 12) bei einer kleinen Warengruppe.
export function monatsFolge(a, b) {
  const aus = [];
  if (!a || !b || a > b) return aus;
  let [j, m] = a.split("-").map(Number);
  const [jb, mb] = b.split("-").map(Number);
  while (j < jb || (j === jb && m <= mb)) {
    aus.push(`${j}-${String(m).padStart(2, "0")}`);
    if (++m > 12) { m = 1; j++; }
  }
  return aus;
}
const istId = (x) => typeof x === "number" || /^\d+$/.test(String(x ?? ""));
const staerke = (r) => { const a = Math.abs(r); return a >= 0.6 ? "deutlich" : a >= 0.3 ? "mäßig" : "kaum"; };

export default function UmfeldWidget({ widget, result, params = {} }) {
  const cfg = widget.config || {};
  const sp = { monat: "Monat", region: "Bundesland", wert: "Umsatz", ...(cfg.spalten || {}) };
  const [groesse, setGroesse] = useState(cfg.groesse || "atemwege");
  const [region, setRegion] = useState(cfg.region || "Deutschland");
  const [umfeld, setUmfeld] = useState(null);
  const [fehler, setFehler] = useState(null);
  const [laedt, setLaedt] = useState(false);

  // ── Warengruppe (optional): Liste und Umsätze der gewählten Gruppe per Mapping nachladen ──
  const wgCfg = cfg.warengruppen || {};
  const listeId = istId(wgCfg.liste?.mapping_id) ? Number(wgCfg.liste.mapping_id) : null;
  const umsatzId = istId(wgCfg.umsatz?.mapping_id) ? Number(wgCfg.umsatz.mapping_id) : null;
  const [wgListe, setWgListe] = useState([]);
  const [wg, setWg] = useState("");
  const [wgZeilen, setWgZeilen] = useState(null);
  const [wgLaedt, setWgLaedt] = useState(false);
  const [wgFehler, setWgFehler] = useState(null);
  const paramSchl = JSON.stringify(params || {});
  useEffect(() => {
    if (!listeId || !umsatzId) return;
    let lebt = true;
    api.post("/api/forms/drilldown", { mapping_id: listeId, params: params || {}, max_rows: 500 })
      .then(({ data }) => {
        if (!lebt) return;
        const namen = (data.rows || []).map((r) => String(r.Warengruppe ?? "")).filter(Boolean);
        setWgListe(namen);
        if (wg && !namen.includes(wg)) setWg("");      // Gruppe hat im neuen Zeitraum keinen Umsatz mehr
      })
      .catch(() => lebt && setWgListe([]));
    return () => { lebt = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listeId, umsatzId, paramSchl]);
  useEffect(() => {
    if (!wg || !umsatzId) { setWgZeilen(null); setWgFehler(null); return; }
    let lebt = true;
    setWgLaedt(true); setWgFehler(null);
    api.post("/api/forms/drilldown", { mapping_id: umsatzId, params: { ...(params || {}), warengruppe: wg }, max_rows: 2000 })
      .then(({ data }) => { if (!lebt) return; setWgZeilen(data.rows || []); if (data.error) setWgFehler(data.error); })
      .catch((e) => lebt && setWgFehler(fehlerText(e)))
      .finally(() => lebt && setWgLaedt(false));
    return () => { lebt = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wg, umsatzId, paramSchl]);

  // Umsatz je Monat für die Region; der laufende Monat ist unvollständig und fällt weg.
  // Der Monatsrahmen kommt immer aus dem Gesamtergebnis, damit eine Warengruppe dieselbe Achse hat.
  const umsatz = useMemo(() => {
    const jetzt = new Date().toISOString().slice(0, 7);
    const alleMonate = (result?.rows || []).map((r) => String(r[sp.monat]).slice(0, 7)).filter((k) => k < jetzt).sort();
    const quelle = wg ? (wgZeilen || []) : (result?.rows || []);
    const m = new Map();
    for (const r of quelle) {
      if (region !== "Deutschland" && r[sp.region] !== region) continue;
      const k = String(r[sp.monat]).slice(0, 7);
      m.set(k, (m.get(k) || 0) + (zahl(r[sp.wert]) || 0));
    }
    if (wg && !wgZeilen) return [];
    return monatsFolge(alleMonate[0], alleMonate[alleMonate.length - 1]).map((k) => [k, m.get(k) || 0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result, region, wg, wgZeilen]);
  const von = umsatz[0]?.[0], bis = umsatz[umsatz.length - 1]?.[0];

  const nurDE = !!GROESSEN.find((g) => g.key === groesse)?.nurDE;
  const umfeldRegion = nurDE ? "Deutschland" : region;
  useEffect(() => {
    if (!von || !bis) return;
    let lebt = true;
    setLaedt(true); setFehler(null);
    api.post("/api/umfeld/reihen", { groessen: [groesse], regionen: [umfeldRegion], von, bis })
      .then(({ data }) => lebt && setUmfeld(data.reihen?.[0] || null))
      .catch((e) => lebt && setFehler(fehlerText(e)))
      .finally(() => lebt && setLaedt(false));
    return () => { lebt = false; };
  }, [groesse, umfeldRegion, von, bis]);

  const werteUmfeld = umfeld?.werte?.[umfeldRegion] || {};
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
  const fmtF = (v) => v == null ? "–" : einheit === "2021 = 100" ? `${nf1.format(v)} (2021 = 100)`
    : `${einheit === "°C" ? nf1.format(v) : v >= 1e6 ? `${nf1.format(v / 1e6)} Mio.` : nf0.format(v)} ${einheit}`;
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
        {wgListe.length > 1 && (
          <select value={wg} onChange={(e) => setWg(e.target.value)} style={{ ...auswahl, maxWidth: 240 }} aria-label="Warengruppe">
            <option value="">Alle Warengruppen</option>
            {wgListe.map((g) => <option key={g} value={g}>{g}</option>)}
          </select>
        )}
        <span style={{ fontSize: 12, color: "var(--text-dim)" }}>
          Umsatz{wg ? ` der Warengruppe „${wg}“` : ""} nach Lieferadresse{region !== "Deutschland" ? ` in ${region}` : " (Deutschland)"}
          {anzeige.length ? `, ${monatText(anzeige[0].Monat)} bis ${monatText(anzeige[anzeige.length - 1].Monat)}` : ""}
          {zuKurz ? " (gewählter Zeitraum zu kurz, gezeigt: die letzten 12 abgeschlossenen Monate)" : ""}
        </span>
      </div>

      {wgFehler && <p style={{ margin: 0, fontSize: 12.5, color: "var(--err-soft, var(--err))" }}>Umsatz der Warengruppe nicht verfügbar: {wgFehler}</p>}
      {fehler && <p style={{ margin: 0, fontSize: 12.5, color: "var(--err-soft, var(--err))" }}>Umfelddaten nicht verfügbar: {fehler}</p>}

      <div>
        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-main)", margin: "2px 0 2px 4px" }}>
          <span style={{ color: FARBE_UMSATZ }}>■</span> Umsatz je Monat{wg ? ` – ${wg}` : ""}{wgLaedt ? " – lädt…" : ""}
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
            <YAxis tick={achse} width={60} tickFormatter={(v) => einheit === "°C" ? nf1.format(v) : v >= 1e6 ? `${nf1.format(v / 1e6)} Mio` : nf0.format(v)} />
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
        {wg && (
          <span style={{ fontSize: 12, color: "var(--text-dim)" }}>
            Nur Artikelpositionen der Warengruppe „{wg}“; Versandkosten und Freipositionen zählen hier nicht mit.
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
          {region !== "Deutschland" && (groesse === "atemwege" || groesse === "grippe")
            ? " · Bundesländer erben den Wert ihrer GrippeWeb-Großregion" : ""}
          {region !== "Deutschland" && nurDE ? ` · ${gLabel.replace(/ \(.*\)$/, "")} gibt es nur für Deutschland insgesamt – verglichen wird mit Ihrem Umsatz in ${region}` : ""}
          {umfeld.hinweis ? ` · ${umfeld.hinweis}` : ""}
        </span>
      )}
    </div>
  );
}
