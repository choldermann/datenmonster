/**
 * Währungen der Lieferländer: wie viel des Einkaufs aus Ländern außerhalb des Euroraums kommt und
 * wie sich der Euro gegenüber deren Währungen entwickelt (EZB-Referenzkurse, Monatsdurchschnitt,
 * über den monstersuite-Datendienst).
 *
 * Auch wer in Euro bestellt, hängt am Kurs: der Lieferant hat Kosten in seiner Landeswährung.
 * Wird der Euro stärker (mehr Zloty je Euro), sinken diese Kosten in Euro gerechnet – Spielraum
 * für die nächste Preisverhandlung; wird er schwächer, sind Preiserhöhungen wahrscheinlicher.
 *
 * Konfiguration (widget.config):
 *   spalten: { land: "Land", waehrung: "Bestellwaehrung", wert: "Einkaufswert", lieferanten: "Lieferanten" }
 * Währung je Zeile: die Bestellwährung, wenn sie nicht EUR ist, sonst die Landeswährung des Lieferlands.
 */
import { useEffect, useMemo, useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, ReferenceLine } from "recharts";
import api, { fehlerText } from "../../../api/client";
import { monatText } from "./monat";

// Landeswährungen außerhalb des Euroraums (Stand 2026: Bulgarien seit 01.01.2026 im Euro)
export const LAND_WAEHRUNG = {
  PL: "PLN", HU: "HUF", CZ: "CZK", RO: "RON", SE: "SEK", DK: "DKK", CH: "CHF", LI: "CHF", NO: "NOK", IS: "ISK",
  GB: "GBP", US: "USD", CA: "CAD", MX: "MXN", BR: "BRL", AR: "ARS", CN: "CNY", HK: "HKD", TW: "TWD", JP: "JPY",
  KR: "KRW", IN: "INR", ID: "IDR", MY: "MYR", PH: "PHP", SG: "SGD", TH: "THB", AU: "AUD", NZ: "NZD", ZA: "ZAR",
  TR: "TRY", IL: "ILS", MA: "MAD", DZ: "DZD",
};
const NAME = {
  PLN: "Polnischer Zloty", HUF: "Ungarischer Forint", CZK: "Tschechische Krone", RON: "Rumänischer Leu",
  SEK: "Schwedische Krone", DKK: "Dänische Krone", CHF: "Schweizer Franken", NOK: "Norwegische Krone",
  ISK: "Isländische Krone", GBP: "Britisches Pfund", USD: "US-Dollar", CAD: "Kanadischer Dollar", MXN: "Mexikanischer Peso",
  BRL: "Brasilianischer Real", ARS: "Argentinischer Peso", CNY: "Chinesischer Yuan", HKD: "Hongkong-Dollar",
  TWD: "Taiwan-Dollar", JPY: "Japanischer Yen", KRW: "Südkoreanischer Won", INR: "Indische Rupie", IDR: "Indonesische Rupiah",
  MYR: "Malaysischer Ringgit", PHP: "Philippinischer Peso", SGD: "Singapur-Dollar", THB: "Thailändischer Baht",
  AUD: "Australischer Dollar", NZD: "Neuseeland-Dollar", ZAR: "Südafrikanischer Rand", TRY: "Türkische Lira",
  ILS: "Israelischer Schekel", MAD: "Marokkanischer Dirham", DZD: "Algerischer Dinar",
};
const FARBEN = ["var(--accent)", "#a78bfa", "#60a5fa", "#f472b6", "#34d399", "#fbbf24", "#f87171", "#94a3b8"];
const MAX = 8;
const zahl = (x) => { const n = typeof x === "number" ? x : Number(String(x ?? "").replace(",", ".")); return Number.isFinite(n) ? n : null; };
const nf0 = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1, signDisplay: "exceptZero" });
const kurs = (v) => (v == null ? "–" : new Intl.NumberFormat("de-DE", { maximumSignificantDigits: 5 }).format(v));
const euro = (v) => (v == null ? "–" : `${nf0.format(v)} €`);
const monatMinus = (mo, n) => {
  const [j, m] = mo.split("-").map(Number);
  const d = new Date(j, m - 1 - n, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
};

/** Einkauf je Währung (ohne Euro) und Summen – rein, für Tests. */
export function jeWaehrung(rows, sp) {
  const m = new Map();
  let gesamt = 0, unbekannt = 0;
  for (const r of rows || []) {
    const w = zahl(r[sp.wert]) || 0;
    if (w <= 0) continue;
    gesamt += w;
    const land = String(r[sp.land] || "").toUpperCase().trim();
    const best = String(r[sp.waehrung] || "EUR").toUpperCase().trim();
    const cur = best && best !== "EUR" ? best : LAND_WAEHRUNG[land] || (land.length === 2 && land !== "??" ? "EUR" : null);
    if (!cur) { unbekannt += w; continue; }
    if (cur === "EUR") continue;
    const e = m.get(cur) || { cur, wert: 0, laender: new Set(), inFremd: false, lieferanten: 0 };
    e.wert += w; e.laender.add(land); e.inFremd = e.inFremd || best !== "EUR"; e.lieferanten += zahl(r[sp.lieferanten]) || 0;
    m.set(cur, e);
  }
  const liste = [...m.values()].sort((a, b) => b.wert - a.wert);
  return { liste, gesamt, fremd: liste.reduce((a, e) => a + e.wert, 0), unbekannt };
}

export default function WaehrungenWidget({ widget, result, params = {} }) {
  const cfg = widget.config || {};
  const sp = { land: "Land", waehrung: "Bestellwaehrung", wert: "Einkaufswert", lieferanten: "Lieferanten", ...(cfg.spalten || {}) };
  const { liste, gesamt, fremd, unbekannt } = useMemo(() => jeWaehrung(result?.rows, sp), [result]); // eslint-disable-line react-hooks/exhaustive-deps
  const curs = liste.slice(0, MAX).map((e) => e.cur);
  const [reihe, setReihe] = useState(null);
  const [fehler, setFehler] = useState(null);
  const heute = new Date().toISOString().slice(0, 7);
  const von = monatMinus(heute, 40);

  useEffect(() => {
    if (!curs.length) return;
    let lebt = true;
    setFehler(null);
    api.post("/api/umfeld/reihen", { groessen: ["wechselkurse"], regionen: curs, von, bis: "" })
      .then(({ data }) => lebt && setReihe(data.reihen?.[0] || null))
      .catch((e) => lebt && setFehler(fehlerText(e)));
    return () => { lebt = false; };
  }, [curs.join(","), von]); // eslint-disable-line react-hooks/exhaustive-deps

  const werte = reihe?.werte || {};
  const zeilen = liste.slice(0, MAX).map((e) => {
    const k = werte[e.cur] || {};
    const ms = Object.keys(k).sort();
    const stand = ms[ms.length - 1];
    const jetzt = stand ? k[stand] : null;
    const vj = stand ? k[monatMinus(stand, 12)] : null;
    const aenderung = jetzt != null && vj ? jetzt / vj - 1 : null;     // + = Euro stärker
    return { ...e, stand, jetzt, aenderung, fehlt: !ms.length };
  });

  // Verlauf: Euro in Fremdwährung, erster gemeinsamer Monat der letzten 24 = 100
  const chart = useMemo(() => {
    const alle = [...new Set(curs.flatMap((c) => Object.keys(werte[c] || {})))].sort().slice(-24);
    if (!alle.length) return [];
    const basis = Object.fromEntries(curs.map((c) => [c, (werte[c] || {})[alle[0]]]));
    return alle.map((m) => Object.fromEntries([["Monat", m],
      ...curs.map((c) => [c, basis[c] && werte[c]?.[m] != null ? (werte[c][m] / basis[c]) * 100 : null])]));
  }, [reihe]); // eslint-disable-line react-hooks/exhaustive-deps

  const th = { textAlign: "left", padding: "6px 8px", fontSize: 11, color: "var(--text-dim)", fontWeight: 600,
    borderBottom: "1px solid var(--border)", whiteSpace: "nowrap" };
  const td = { padding: "6px 8px", fontSize: 12.5, color: "var(--text-main)", borderBottom: "1px solid var(--border)", verticalAlign: "top" };
  const rechts = { textAlign: "right", whiteSpace: "nowrap" };
  const achse = { fontSize: 11, fill: "var(--text-dim)" };

  if (!gesamt) return <p style={{ padding: 16, margin: 0, color: "var(--text-dim)", fontSize: 13 }}>Keine Einkäufe im Zeitraum.</p>;
  if (!liste.length) {
    return <p style={{ padding: 16, margin: 0, color: "var(--text-dim)", fontSize: 13 }}>
      Alle Einkäufe im Zeitraum stammen von Lieferanten im Euroraum – kein Wechselkursrisiko.</p>;
  }

  return (
    <div style={{ padding: "12px 16px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ fontSize: 13, color: "var(--text-main)", lineHeight: 1.5 }}>
        <b style={{ color: "var(--text-bright)" }}>{nf0.format((fremd / gesamt) * 100)} %</b> Ihres Einkaufs ({euro(fremd)}) kommt
        von Lieferanten aus Ländern mit eigener Währung.
        {zeilen.some((z) => !z.inFremd) && " Auch in Euro bestellt hängt der Preis am Kurs: der Lieferant hat seine Kosten in Landeswährung."}
      </div>
      {fehler && <p style={{ margin: 0, fontSize: 12.5, color: "var(--err-soft, var(--err))" }}>Wechselkurse nicht verfügbar: {fehler}</p>}
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={th}>Währung</th>
              <th style={{ ...th, ...rechts }}>Ihr Einkauf</th>
              <th style={{ ...th, ...rechts }}>Anteil</th>
              <th style={{ ...th, ...rechts }}>Kurs (1 € =)</th>
              <th style={{ ...th, ...rechts }}>Euro zum Vorjahr</th>
              <th style={th}>Bedeutung für den Einkauf</th>
            </tr>
          </thead>
          <tbody>
            {zeilen.map((z, i) => {
              const a = z.aenderung;
              const farbe = a == null ? "var(--text-dim)" : a > 0.02 ? "var(--ok)" : a < -0.02 ? "var(--err)" : "var(--text-main)";
              const text = a == null ? (z.fehlt ? "kein EZB-Kurs für diese Währung" : "–")
                : a > 0.02 ? "Euro stärker: Ware rechnerisch günstiger – Spielraum für Preisverhandlung"
                : a < -0.02 ? "Euro schwächer: Preiserhöhungen wahrscheinlicher"
                : "Kurs stabil";
              return (
                <tr key={z.cur}>
                  <td style={td}>
                    <div style={{ fontWeight: 600, color: "var(--text-bright)", whiteSpace: "nowrap" }}>
                      <span style={{ color: FARBEN[i % FARBEN.length] }}>■</span> {z.cur} · {NAME[z.cur] || z.cur}
                    </div>
                    <div style={{ fontSize: 11.5, color: "var(--text-dim)" }}>
                      {[...z.laender].join(", ")}{z.lieferanten ? ` · ${nf0.format(z.lieferanten)} Lieferant${z.lieferanten === 1 ? "" : "en"}` : ""}
                      {z.inFremd ? ` · bestellt in ${z.cur}` : " · bestellt in EUR"}
                    </div>
                  </td>
                  <td style={{ ...td, ...rechts }}>{euro(z.wert)}</td>
                  <td style={{ ...td, ...rechts }}>{nf1.format((z.wert / gesamt) * 100).replace("+", "")} %</td>
                  <td style={{ ...td, ...rechts }}>
                    {kurs(z.jetzt)} {z.cur}
                    {z.stand && <div style={{ fontSize: 10.5, color: "var(--text-dim)" }}>Ø {monatText(z.stand)}</div>}
                  </td>
                  <td style={{ ...td, ...rechts, color: farbe, fontWeight: 600 }}>{a == null ? "–" : `${nf1.format(a * 100)} %`}</td>
                  <td style={{ ...td, fontSize: 12, color: "var(--text-dim)" }}>{text}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {chart.length > 1 && (
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-main)", margin: "2px 0 2px 4px" }}>
            Wert des Euro in diesen Währungen ({monatText(chart[0].Monat)} = 100) – steigt die Linie, wird Einkauf dort günstiger
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={chart} margin={{ top: 6, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="Monat" tick={achse} tickFormatter={monatText} minTickGap={24} />
              <YAxis tick={achse} domain={["auto", "auto"]} width={40} tickFormatter={(v) => nf0.format(v)} />
              <ReferenceLine y={100} stroke="var(--text-dim)" strokeDasharray="4 4" />
              <Tooltip labelFormatter={monatText} formatter={(v, n) => [v == null ? "–" : nf1.format(v - 100) + " %", n]}
                contentStyle={{ background: "var(--bg-card)", border: "1px solid var(--border)", fontSize: 11.5 }} />
              <Legend wrapperStyle={{ fontSize: 11.5 }} />
              {curs.map((c, i) => <Line key={c} dataKey={c} name={c} stroke={FARBEN[i % FARBEN.length]} strokeWidth={2} dot={false} connectNulls />)}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      <span style={{ fontSize: 12, color: "var(--text-dim)", lineHeight: 1.5 }}>
        Kurs = Euro-Referenzkurs der EZB, Monatsdurchschnitt. „Euro zum Vorjahr“ vergleicht den letzten Monat mit demselben Monat
        im Vorjahr; grün/rot ab 2 % Veränderung. Lieferland = Land des Lieferanten in JTL.
        {liste.length > MAX ? ` Gezeigt werden die ${MAX} Währungen mit dem größten Einkauf.` : ""}
        {unbekannt > 0 ? ` ${euro(unbekannt)} von Lieferanten ohne Land sind nicht zugeordnet.` : ""}
      </span>
      <span style={{ fontSize: 11.5, color: "var(--text-dim)" }}>{reihe?.quelle || "Quelle: EZB-Statistiken"}{reihe?.hinweis ? ` · ${reihe.hinweis}` : ""}</span>
    </div>
  );
}
