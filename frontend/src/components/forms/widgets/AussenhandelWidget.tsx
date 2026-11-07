/**
 * Außenhandel je Warennummer: eigener Einkauf neben der Einfuhr Deutschlands derselben Ware
 * (Eurostat Comext, KN8, über den monstersuite-Datendienst).
 *
 * Je Warennummer: Ihr Einkaufswert und Ihr Preis je kg (aus JTL: EK × Menge / Artikelgewicht × Menge)
 * gegen den durchschnittlichen Einfuhrpreis je kg und das Einfuhrvolumen Deutschlands im selben
 * Zeitraum. Ein Klick zeigt den Monatsverlauf des Einfuhrpreises und die wichtigsten Herkunftsländer.
 * An den Dienst gehen nur die Warennummern, keine Mengen, Preise oder Lieferanten.
 *
 * Konfiguration (widget.config):
 *   spalten: { warennummer, artikel, anzahl, wert, kg, jeKg, land } – Spaltennamen der Abfrage
 *   richtung: "einfuhr" (Vorgabe) | "ausfuhr"
 */
import { useEffect, useMemo, useState } from "react";
import { ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";
import api, { fehlerText } from "../../../api/client";
import { monatText } from "./monat";

const MAX_CODES = 15;
const FARBE_MARKT = "#a78bfa";
const zahl = (x) => { const n = typeof x === "number" ? x : Number(String(x ?? "").replace(",", ".")); return Number.isFinite(n) ? n : null; };
const nf0 = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 });
const nf2 = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const nfP = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0, signDisplay: "exceptZero" });
const euro = (v) => (v == null ? "–" : `${nf0.format(v)} €`);
const jeKg = (v) => (v == null ? "–" : `${nf2.format(v)} €/kg`);
const gross = (v) => {
  if (v == null) return "–";
  if (v >= 1e9) return `${nf2.format(v / 1e9)} Mrd €`;
  if (v >= 1e6) return `${nf2.format(v / 1e6)} Mio €`;
  if (v >= 1e3) return `${nf0.format(v / 1e3)} Tsd €`;
  return euro(v);
};
const knText = (c) => (c?.length === 8 ? `${c.slice(0, 4)} ${c.slice(4, 6)} ${c.slice(6)}` : c);

/** Summe € und kg einer Monatsreihe {"YYYY-MM": [€, kg]} im Zeitraum; Monate ohne kg zählen beim Preis nicht mit. */
export function summeZeitraum(monate, von, bis) {
  let eur = 0, eurMitKg = 0, kg = 0, n = 0;
  for (const [m, [e, k]] of Object.entries(monate || {})) {
    if ((von && m < von) || (bis && m > bis)) continue;
    n++; eur += e || 0;
    if (k) { kg += k; eurMitKg += e || 0; }
  }
  return { eur: n ? eur : null, jeKg: kg > 0 ? eurMitKg / kg : null, monate: n };
}

/** Letzte zwölf Monate bis zum Datenstand – für Zeiträume, die die Statistik noch nicht abdeckt. */
export function letzteZwoelf(stand) {
  if (!stand) return ["", ""];
  const [j, m] = stand.split("-").map(Number);
  const d = new Date(j, m - 12, 1);
  return [`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`, stand];
}

export default function AussenhandelWidget({ widget, result, params = {} }) {
  const cfg = widget.config || {};
  const sp = { warennummer: "Warennummer", artikel: "Hauptartikel", anzahl: "Artikel", wert: "Einkaufswert",
    kg: "GewichtKg", jeKg: "EKjeKg", land: "Lieferland", ...(cfg.spalten || {}) };
  const richtung = cfg.richtung === "ausfuhr" ? "ausfuhr" : "einfuhr";
  const wort = richtung === "ausfuhr" ? "Ausfuhr" : "Einfuhr";

  const eigen = useMemo(() => (result?.rows || []).map((r) => ({
    kn: String(r[sp.warennummer] ?? "").replace(/\D/g, ""),
    artikel: r[sp.artikel] || "", anzahl: zahl(r[sp.anzahl]), wert: zahl(r[sp.wert]),
    kg: zahl(r[sp.kg]), jeKg: zahl(r[sp.jeKg]), land: String(r[sp.land] || "").toUpperCase(),
  })).filter((x) => x.kn.length === 8), [result]); // eslint-disable-line react-hooks/exhaustive-deps

  const codes = eigen.slice(0, MAX_CODES).map((x) => x.kn);
  const selVon = String(params?.von || "").slice(0, 7), selBis = String(params?.bis || "").slice(0, 7);
  const [markt, setMarkt] = useState(null);
  const [fehler, setFehler] = useState(null);
  const [laedt, setLaedt] = useState(false);
  const [offen, setOffen] = useState(null);

  useEffect(() => {
    if (!codes.length) return;
    let lebt = true;
    setLaedt(true); setFehler(null);
    api.post("/api/umfeld/aussenhandel", { warennummern: codes, von: selVon, bis: selBis })
      .then(({ data }) => lebt && setMarkt(data))
      .catch((e) => lebt && setFehler(fehlerText(e)))
      .finally(() => lebt && setLaedt(false));
    return () => { lebt = false; };
  }, [codes.join(","), selVon, selBis]); // eslint-disable-line react-hooks/exhaustive-deps

  const jeCode = useMemo(() => Object.fromEntries((markt?.warennummern || []).map((w) => [w.code, w])), [markt]);

  // Je Zeile: Marktwerte im gewählten Zeitraum; liegt er ganz nach dem Datenstand, die letzten zwölf Monate
  const zeilen = eigen.slice(0, MAX_CODES).map((x) => {
    const w = jeCode[x.kn];
    const r = w?.[richtung];
    if (!r) return { ...x, w, m: null };
    let von = selVon, bis = selBis, ersatz = false;
    let m = summeZeitraum(r.monate, von, bis);
    if (!m.monate || !(von || bis)) {      // kein Zeitraum oder ganz nach dem Datenstand
      [von, bis] = letzteZwoelf(w.stand); m = summeZeitraum(r.monate, von, bis); ersatz = true;
    }
    if (!ersatz) {
      const drin = Object.keys(r.monate).filter((mo) => (!von || mo >= von) && (!bis || mo <= bis)).sort();
      von = drin[0]; bis = drin[drin.length - 1];
    }
    const abw = x.jeKg != null && m.jeKg ? x.jeKg / m.jeKg - 1 : null;
    return { ...x, w, m, von, bis, ersatz, abw };
  });
  const periodeMonate = selVon && selBis
    ? (Number(selBis.slice(0, 4)) - Number(selVon.slice(0, 4))) * 12 + Number(selBis.slice(5)) - Number(selVon.slice(5)) + 1 : 0;
  const standMin = Object.values(jeCode).map((w) => w.stand).filter(Boolean).sort()[0];
  const ohneKn = (result?.rows || []).length - eigen.length;

  const th = { textAlign: "left", padding: "6px 8px", fontSize: 11, color: "var(--text-dim)", fontWeight: 600,
    borderBottom: "1px solid var(--border)", whiteSpace: "nowrap" };
  const td = { padding: "6px 8px", fontSize: 12.5, color: "var(--text-main)", borderBottom: "1px solid var(--border)", verticalAlign: "top" };
  const rechts = { textAlign: "right", whiteSpace: "nowrap" };

  if (!(result?.rows || []).length) {
    return <p style={{ padding: 16, margin: 0, color: "var(--text-dim)", fontSize: 13 }}>
      Keine Einkäufe mit Warennummer im Zeitraum. Die Warennummer (Zolltarifnummer) wird in JTL am Artikel gepflegt.</p>;
  }

  return (
    <div style={{ padding: "12px 16px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
      {fehler && <p style={{ margin: 0, fontSize: 12.5, color: "var(--err-soft, var(--err))" }}>Außenhandelsdaten nicht verfügbar: {fehler}</p>}
      {laedt && !markt && <p style={{ margin: 0, fontSize: 12.5, color: "var(--text-dim)" }}>Außenhandelsdaten werden geladen …</p>}
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={th}>Warennummer</th>
              <th style={{ ...th, ...rechts }}>Ihr Einkauf</th>
              <th style={{ ...th, ...rechts }}>Ihr Preis</th>
              <th style={{ ...th, ...rechts }}>{wort}preis DE</th>
              <th style={{ ...th, ...rechts }}>Abweichung</th>
              <th style={{ ...th, ...rechts }}>{wort} DE (Markt)</th>
            </tr>
          </thead>
          <tbody>
            {zeilen.map((z) => {
              const auf = offen === z.kn;
              const farbe = z.abw == null ? "var(--text-dim)" : z.abw > 0.05 ? "var(--err)" : z.abw < -0.05 ? "var(--ok)" : "var(--text-main)";
              return [
                <tr key={z.kn} onClick={() => setOffen(auf ? null : z.kn)} style={{ cursor: "pointer",
                  background: auf ? "color-mix(in srgb, var(--accent) 8%, transparent)" : undefined }}>
                  <td style={td}>
                    <div style={{ fontWeight: 600, color: "var(--text-bright)", whiteSpace: "nowrap" }}>
                      <span style={{ color: "var(--text-dim)", marginRight: 4 }}>{auf ? "▾" : "▸"}</span>{knText(z.kn)}
                    </div>
                    <div style={{ fontSize: 11.5, color: "var(--text-dim)", maxWidth: 420 }} title={z.w?.label || ""}>
                      {z.artikel}{z.anzahl > 1 ? ` + ${z.anzahl - 1} weitere` : ""}
                    </div>
                  </td>
                  <td style={{ ...td, ...rechts }}>{euro(z.wert)}</td>
                  <td style={{ ...td, ...rechts }}>{jeKg(z.jeKg)}</td>
                  <td style={{ ...td, ...rechts }}>
                    {z.w?.hinweis && !z.m ? <span style={{ fontSize: 11.5, color: "var(--text-dim)" }}>{z.w.hinweis}</span> : jeKg(z.m?.jeKg)}
                  </td>
                  <td style={{ ...td, ...rechts, color: farbe, fontWeight: 600 }}>{z.abw == null ? "–" : `${nfP.format(z.abw * 100)} %`}</td>
                  <td style={{ ...td, ...rechts }}>
                    {gross(z.m?.eur)}
                    {z.m?.monate && (z.ersatz || z.m.monate < periodeMonate)
                      ? <div style={{ fontSize: 10.5, color: "var(--text-dim)" }}>{monatText(z.von)} – {monatText(z.bis)}</div> : null}
                  </td>
                </tr>,
                auf && <tr key={z.kn + "-d"}><td colSpan={6} style={{ ...td, background: "var(--bg-elevated)" }}>
                  <Detail z={z} richtung={richtung} wort={wort} />
                </td></tr>,
              ];
            })}
          </tbody>
        </table>
      </div>
      <span style={{ fontSize: 12, color: "var(--text-dim)", lineHeight: 1.5 }}>
        Ihr Preis = Einkaufswert der Bestellungen je kg Artikelgewicht aus JTL (Artikel ohne Gewicht zählen beim Preis nicht mit).
        {wort}preis = durchschnittlicher Wert je kg aller {wort === "Einfuhr" ? "Einfuhren nach" : "Ausfuhren aus"} Deutschland
        unter dieser Warennummer im selben Zeitraum – ein Richtwert: dort steckt die ganze Bandbreite der Qualitäten,
        und das JTL-Gewicht enthält oft die Verpackung. Rot: Sie zahlen mehr als 5 % über dem Schnitt, grün: mehr als 5 % darunter.
        {eigen.length > MAX_CODES ? ` Gezeigt werden die ${MAX_CODES} Warennummern mit dem größten Einkaufswert.` : ""}
        {ohneKn > 0 ? ` ${ohneKn} Zeile(n) ohne gültige achtstellige Warennummer fehlen.` : ""}
      </span>
      <span style={{ fontSize: 11.5, color: "var(--text-dim)" }}>
        Quelle: {markt?.quelle || "Eurostat Comext"}{standMin ? ` · Daten bis ${monatText(standMin)}` : ""} · etwa zwei Monate Verzug
        · übermittelt werden nur die Warennummern
      </span>
    </div>
  );
}

function Detail({ z, richtung, wort }) {
  const r = z.w?.[richtung];
  if (!r) return <span style={{ fontSize: 12.5, color: "var(--text-dim)" }}>{z.w?.hinweis || "Keine Außenhandelsdaten für diese Warennummer."}</span>;
  const monate = Object.keys(r.monate).sort().slice(-36);
  const daten = monate.map((m) => {
    const [e, k] = r.monate[m];
    return { Monat: m, Wert: e ?? null, JeKg: k ? e / k : null };
  });
  const achse = { fontSize: 11, fill: "var(--text-dim)" };
  const laender = r.laender || [];
  const max = Math.max(1, ...laender.map((l) => l.euro));
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 16 }}>
      <div style={{ flex: "2 1 420px", minWidth: 0 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-main)", marginBottom: 2 }}>
          {wort} Deutschland je Monat
        </div>
        {z.w?.label && <div style={{ fontSize: 11, color: "var(--text-dim)", marginBottom: 6 }}>{z.w.label}</div>}
        <ResponsiveContainer width="100%" height={220}>
          <ComposedChart data={daten} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="Monat" tick={achse} tickFormatter={monatText} minTickGap={24} />
            <YAxis yAxisId="w" tick={achse} tickFormatter={(v) => gross(v).replace(" €", "")} width={64} />
            <YAxis yAxisId="p" orientation="right" tick={achse} tickFormatter={(v) => nf2.format(v)} width={44} />
            <Tooltip formatter={(v, n) => (n === "€/kg" ? jeKg(v) : gross(v))} labelFormatter={monatText}
              contentStyle={{ background: "var(--bg-card)", border: "1px solid var(--border)", fontSize: 11.5 }} />
            <Legend wrapperStyle={{ fontSize: 11.5 }} />
            <Bar yAxisId="w" dataKey="Wert" name={`${wort}wert`} fill="color-mix(in srgb, var(--accent) 45%, transparent)" />
            <Line yAxisId="p" dataKey="JeKg" name="€/kg" stroke={FARBE_MARKT} strokeWidth={2} dot={false} connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div style={{ flex: "1 1 260px", minWidth: 0 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-main)", marginBottom: 6 }}>
          {richtung === "ausfuhr" ? "Ziel" : "Herkunfts"}länder{" "}
          {r.zeitraum?.[0] ? `${monatText(r.zeitraum[0])} – ${monatText(r.zeitraum[1])}` : "gesamt"}
        </div>
        {laender.length === 0 && <span style={{ fontSize: 12, color: "var(--text-dim)" }}>Keine Länderwerte.</span>}
        {laender.slice(0, 10).map((l) => (
          <div key={l.iso} style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto auto", gap: 8, alignItems: "center",
            fontSize: 12, padding: "2px 0", fontWeight: l.iso === z.land ? 700 : 400 }}
            title={l.iso === z.land ? "Ihr Hauptlieferland für diese Warennummer" : ""}>
            <div style={{ minWidth: 0 }}>
              <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {l.name}{l.iso === z.land ? " ★" : ""}
              </div>
              <div style={{ height: 4, borderRadius: 2, background: "var(--accent)", opacity: 0.6, width: `${(l.euro / max) * 100}%` }} />
            </div>
            <span style={{ color: "var(--text-dim)", whiteSpace: "nowrap" }}>{gross(l.euro)}</span>
            <span style={{ whiteSpace: "nowrap", minWidth: 74, textAlign: "right" }}>{l.kg ? jeKg(l.euro / l.kg) : "–"}</span>
          </div>
        ))}
        {r.laender_gesamt > 10 && <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 4 }}>{r.laender_gesamt - 10} weitere Länder</div>}
      </div>
    </div>
  );
}
