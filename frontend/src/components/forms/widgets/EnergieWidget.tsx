/**
 * Energie & Kraftstoff: Diesel-, Super- und Heizölpreise in Deutschland (EU Weekly Oil Bulletin,
 * Monatsmittel und letzte Woche) und der Erzeugerpreis für Strom (Destatis GP 35.11.1), dazu der
 * rechnerische Preiseffekt auf passende Kostenblöcke des Mandanten (Fixkosten pflegen).
 *
 * Kostenblöcke werden über den Namen erkannt (Fuhrpark/Kraftstoff → Diesel, Strom/Energie → Strom,
 * Heizung/Heizöl → Heizöl). Der Effekt ist eine Obergrenze: er unterstellt, dass der Block ganz aus
 * diesem Energieträger besteht.
 *
 * Konfiguration (widget.config):
 *   spalten: { block: "Kostenblock", monat: "Euro pro Monat" } – Zeilen aus „Kostenblöcke“
 */
import { useEffect, useMemo, useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";
import api, { fehlerText } from "../../../api/client";
import { monatText } from "./monat";

const STROM = "GP19-35111";
const zahl = (x) => { if (x == null || x === "") return null; const n = typeof x === "number" ? x : Number(String(x).replace(",", ".")); return Number.isFinite(n) ? n : null; };
const nf0 = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const nf2 = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const nf3 = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 3, maximumFractionDigits: 3 });
const nfP = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1, signDisplay: "exceptZero" });
const monatMinus = (mo, n) => {
  const [j, m] = mo.split("-").map(Number);
  const d = new Date(j, m - 1 - n, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
};
// Kostenblock → Energieträger (über den Namen)
export const TRAEGER = [
  { key: "Diesel", muster: /fuhrpark|kraftstoff|diesel|benzin|tank|fahrzeug|kfz|lkw|transporter|sprit/i },
  { key: "Strom", muster: /strom|energie|elektri/i },
  { key: "Heizöl", muster: /heiz|heizöl|wärme/i },
];
export function traegerVon(name) { return TRAEGER.find((t) => t.muster.test(String(name || "")))?.key || null; }

/** Veränderung zum Vorjahr: letzter vollständiger Monat gegen denselben Monat ein Jahr davor. */
export function zumVorjahr(werte, heute = new Date().toISOString().slice(0, 7)) {
  const ms = Object.keys(werte || {}).filter((m) => m < heute).sort();
  const letzt = ms[ms.length - 1];
  const v = letzt ? werte[letzt] : null, vj = letzt ? werte[monatMinus(letzt, 12)] : null;
  return { monat: letzt, wert: v, vj, aenderung: v != null && vj ? v / vj - 1 : null };
}

export default function EnergieWidget({ widget, result }) {
  const cfg = widget.config || {};
  const sp = { block: "Kostenblock", monat: "Euro pro Monat", ...(cfg.spalten || {}) };
  const [kraft, setKraft] = useState(null);
  const [strom, setStrom] = useState(null);
  const [fehler, setFehler] = useState(null);
  const heute = new Date().toISOString().slice(0, 7);

  useEffect(() => {
    let lebt = true;
    const von = monatMinus(heute, 40);
    Promise.all([
      api.post("/api/umfeld/reihen", { groessen: ["kraftstoff"], regionen: ["Diesel", "Super 95", "Heizöl"], von, bis: "" }),
      api.post("/api/umfeld/reihen", { groessen: ["erzeugerpreise"], regionen: [STROM], von, bis: "" }),
    ]).then(([a, b]) => { if (!lebt) return; setKraft(a.data.reihen?.[0] || null); setStrom(b.data.reihen?.[0] || null); })
      .catch((e) => lebt && setFehler(fehlerText(e)));
    return () => { lebt = false; };
  }, [heute]);

  const w = kraft?.werte || {};
  const s = strom?.werte?.[STROM] || {};
  const kennz = {
    Diesel: zumVorjahr(w.Diesel, heute), "Super 95": zumVorjahr(w["Super 95"], heute),
    Heizöl: zumVorjahr(w["Heizöl"], heute), Strom: zumVorjahr(s, heute),
  };
  const bloecke = useMemo(() => (result?.rows || []).map((r) => ({ name: r[sp.block], monat: zahl(r[sp.monat]), traeger: traegerVon(r[sp.block]) }))
    .filter((b) => b.traeger && b.monat), [result]); // eslint-disable-line react-hooks/exhaustive-deps

  const chart = useMemo(() => {
    const ms = [...new Set([...Object.keys(w.Diesel || {}), ...Object.keys(s)])].filter((m) => m < heute).sort().slice(-36);
    return ms.map((m) => ({ Monat: m, Diesel: w.Diesel?.[m] ?? null, "Super 95": w["Super 95"]?.[m] ?? null, "Heizöl": w["Heizöl"]?.[m] ?? null, Strom: s[m] ?? null }));
  }, [kraft, strom]); // eslint-disable-line react-hooks/exhaustive-deps

  const kachel = { flex: "1 1 180px", border: "1px solid var(--border)", borderRadius: 8, padding: "10px 12px", display: "flex", flexDirection: "column", gap: 2 };
  const farbe = (a) => (a == null ? "var(--text-dim)" : a > 0.03 ? "var(--err)" : a < -0.03 ? "var(--ok)" : "var(--text-main)");
  const achse = { fontSize: 11, fill: "var(--text-dim)" };
  const tt = { background: "var(--bg-card)", border: "1px solid var(--border)", fontSize: 11.5 };

  const kachelInhalt = (titel, k, einheit, extra = null) => (
    <div style={kachel}>
      <span style={{ fontSize: 11.5, color: "var(--text-dim)" }}>{titel}</span>
      <span style={{ fontSize: 20, fontWeight: 650, color: "var(--text-bright)", fontFamily: "var(--font-mono)" }}>
        {k.wert == null ? "–" : einheit === "index" ? nf1.format(k.wert) : `${nf3.format(k.wert)} €`}
        <span style={{ fontSize: 11.5, fontWeight: 400, color: "var(--text-dim)" }}>{einheit === "index" ? " (2021 = 100)" : "/l"}</span>
      </span>
      <span style={{ fontSize: 12, color: farbe(k.aenderung), fontWeight: 600 }}>
        {k.aenderung == null ? "–" : `${nfP.format(k.aenderung * 100)} % zum Vorjahr`}
        <span style={{ fontWeight: 400, color: "var(--text-dim)" }}>{k.monat ? ` · Ø ${monatText(k.monat)}` : ""}</span>
      </span>
      {extra}
    </div>
  );

  return (
    <div style={{ padding: "12px 16px 16px", display: "flex", flexDirection: "column", gap: 12 }}>
      {fehler && <p style={{ margin: 0, fontSize: 12.5, color: "var(--err-soft, var(--err))" }}>Energiepreise nicht verfügbar: {fehler}</p>}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
        {kachelInhalt("Diesel (mit Steuern)", kennz.Diesel, "l",
          <span style={{ fontSize: 11.5, color: "var(--text-dim)" }}>
            netto ohne USt. {kennz.Diesel.wert == null ? "–" : `${nf3.format(kennz.Diesel.wert / 1.19)} €`}
          </span>)}
        {kachelInhalt("Super 95 (mit Steuern)", kennz["Super 95"], "l")}
        {kachelInhalt("Heizöl (mit Steuern)", kennz["Heizöl"], "l")}
        {kachelInhalt("Strom – Erzeugerpreis", kennz.Strom, "index")}
      </div>

      <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: "10px 12px", fontSize: 13, lineHeight: 1.5, color: "var(--text-main)" }}>
        <strong style={{ fontSize: 12, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: ".05em" }}>Wirkung auf Ihre Kostenblöcke</strong>
        {bloecke.length ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 3, marginTop: 4 }}>
            {bloecke.map((b) => {
              const a = kennz[b.traeger]?.aenderung;
              const effekt = a == null ? null : (b.monat * a) / (1 + a);    // Anteil der heutigen Kosten, der auf die Preisänderung entfällt
              return (
                <span key={b.name}>
                  „{b.name}“ ({nf0.format(b.monat)} € im Monat) – {b.traeger}{" "}
                  {a == null ? "ohne Vorjahreswert" : <>
                    <b style={{ color: farbe(a) }}>{nfP.format(a * 100)} %</b> zum Vorjahr: davon gehen bis zu{" "}
                    <b style={{ color: "var(--text-bright)" }}>{nf0.format(Math.abs(effekt))} € im Monat</b> auf {a >= 0 ? "höhere" : "niedrigere"} Preise zurück
                  </>}
                </span>
              );
            })}
            <span style={{ fontSize: 12, color: "var(--text-dim)" }}>
              „Bis zu“: gerechnet, als bestünde der Block ganz aus diesem Energieträger. Steckt darin auch Leasing oder Versicherung, ist der Effekt kleiner.
            </span>
          </div>
        ) : (
          <div style={{ fontSize: 12.5, color: "var(--text-dim)", marginTop: 4 }}>
            Kein passender Kostenblock gefunden. Legen Sie unter „Fixkosten pflegen“ Blöcke wie „Fuhrpark“, „Kraftstoff“ oder „Strom“ an,
            dann rechnet die Kachel den Preiseffekt.
          </div>
        )}
      </div>

      {chart.length > 1 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
          <div style={{ flex: "2 1 420px", minWidth: 0 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-main)", margin: "2px 0 2px 4px" }}>Kraftstoff und Heizöl, € je Liter (Monatsmittel, mit Steuern)</div>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={chart} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="Monat" tick={achse} tickFormatter={monatText} minTickGap={24} />
                <YAxis tick={achse} width={40} domain={["auto", "auto"]} tickFormatter={(v) => nf2.format(v)} />
                <Tooltip labelFormatter={monatText} formatter={(v) => (v == null ? "–" : `${nf3.format(v)} €/l`)} contentStyle={tt} />
                <Legend wrapperStyle={{ fontSize: 11.5 }} />
                <Line dataKey="Diesel" stroke="var(--accent)" strokeWidth={2} dot={false} connectNulls />
                <Line dataKey="Super 95" stroke="#60a5fa" strokeWidth={2} dot={false} connectNulls />
                <Line dataKey="Heizöl" stroke="#f472b6" strokeWidth={2} dot={false} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div style={{ flex: "1 1 260px", minWidth: 0 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-main)", margin: "2px 0 2px 4px" }}>Strom, Erzeugerpreisindex (2021 = 100)</div>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={chart} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="Monat" tick={achse} tickFormatter={monatText} minTickGap={24} />
                <YAxis tick={achse} width={40} domain={["auto", "auto"]} tickFormatter={(v) => nf0.format(v)} />
                <Tooltip labelFormatter={monatText} formatter={(v) => (v == null ? "–" : nf1.format(v))} contentStyle={tt} />
                <Line dataKey="Strom" stroke="#fbbf24" strokeWidth={2} dot={false} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
      <span style={{ fontSize: 12, color: "var(--text-dim)", lineHeight: 1.5 }}>
        Kraftstoffpreise: Durchschnitt der Tankstellenpreise in Deutschland je Woche, hier als Monatsmittel; „zum Vorjahr“ vergleicht den
        letzten abgeschlossenen Monat. Strom: Erzeugerpreis für elektrischen Strom (Großhandel und Sondervertragskunden) – zeigt die
        Richtung, nicht Ihren Tarif. Netto = mit Steuern geteilt durch 1,19.
      </span>
      <span style={{ fontSize: 11.5, color: "var(--text-dim)" }}>
        Quellen: {kraft?.quelle || "EU-Kommission, Weekly Oil Bulletin – CC BY 4.0"}; {strom?.quelle || "Statistisches Bundesamt (Destatis)"},
        Tabelle 61241-0006 · es werden keine Kundendaten übertragen
      </span>
    </div>
  );
}
