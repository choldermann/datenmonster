/**
 * Stimmung: Konjunkturumfragen der EU-Kommission für Deutschland (Eurostat ei_bssi_m_r2, saisonbereinigt,
 * über den monstersuite-Datendienst) – Wirtschaftsklima (ESI, langjähriger Durchschnitt = 100) und
 * Vertrauensindikatoren (Salden) – neben dem eigenen Umsatzwachstum.
 *
 * Die Umfragen erscheinen am Monatsende für den laufenden Monat, also früher als jede Umsatzstatistik.
 * Die Kachel prüft, ob das eigene Wachstum (3 Monate gegen Vorjahr, wie im Branchenvergleich) dem
 * gewählten Indikator mit Verzug folgt (0–6 Monate) – ein Hinweis, kein Prognosemodell.
 *
 * Konfiguration (widget.config):
 *   spalten: { monat: "Monat", wert: "Umsatz" } – Abfrage liefert einen Wert je Monat (≥ 27 Monate)
 */
import { useEffect, useMemo, useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts";
import api, { fehlerText } from "../../../api/client";
import { monatText } from "./monat";
import { monatsFolge, besterVersatz } from "./UmfeldWidget";
import { vorjahrGleitend } from "./BranchenvergleichWidget";

const INDIKATOREN = [
  { key: "BS-ESI-I", kurz: "Wirtschaftsklima", art: "index" },
  { key: "BS-RCI-BAL", kurz: "Einzelhandel", art: "saldo" },
  { key: "BS-CSMCI-BAL", kurz: "Verbraucher", art: "saldo" },
  { key: "BS-ICI-BAL", kurz: "Industrie", art: "saldo" },
  { key: "BS-SCI-BAL", kurz: "Dienstleistungen", art: "saldo" },
  { key: "BS-CCI-BAL", kurz: "Bau", art: "saldo" },
];
const zahl = (x) => { if (x == null || x === "") return null; const n = typeof x === "number" ? x : Number(String(x).replace(",", ".")); return Number.isFinite(n) ? n : null; };
const nf1 = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const nfS = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1, signDisplay: "exceptZero" });
const nf2 = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const monatMinus = (mo, n) => {
  const [j, m] = mo.split("-").map(Number);
  const d = new Date(j, m - 1 - n, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
};
const staerke = (r) => { const a = Math.abs(r); return a >= 0.6 ? "deutlich" : a >= 0.3 ? "mäßig" : "kaum"; };

export default function StimmungWidget({ widget, result }) {
  const cfg = widget.config || {};
  const sp = { monat: "Monat", wert: "Umsatz", ...(cfg.spalten || {}) };
  const [reihe, setReihe] = useState(null);
  const [fehler, setFehler] = useState(null);
  const [ind, setInd] = useState("BS-ESI-I");
  const heute = new Date().toISOString().slice(0, 7);

  useEffect(() => {
    let lebt = true;
    api.post("/api/umfeld/reihen", { groessen: ["stimmung"], regionen: INDIKATOREN.map((i) => i.key), von: monatMinus(heute, 60), bis: "" })
      .then(({ data }) => lebt && setReihe(data.reihen?.[0] || null))
      .catch((e) => lebt && setFehler(fehlerText(e)));
    return () => { lebt = false; };
  }, [heute]);
  const werte = reihe?.werte || {};

  // Eigener Umsatz: lückenlose Monatsfolge ohne laufenden Monat, Wachstum 3 Monate gegen Vorjahr
  const eigen = useMemo(() => {
    const m = new Map();
    for (const r of result?.rows || []) {
      const mo = String(r[sp.monat] ?? "").slice(0, 7);
      if (!/^\d{4}-\d{2}$/.test(mo) || mo >= heute) continue;
      m.set(mo, (m.get(mo) || 0) + (zahl(r[sp.wert]) || 0));
    }
    const ks = [...m.keys()].sort();
    if (!ks.length) return { monate: [], yoy: [] };
    const monate = monatsFolge(ks[0], ks[ks.length - 1]);
    return { monate, yoy: vorjahrGleitend(monate.map((mo) => m.get(mo) || 0)) };
  }, [result]); // eslint-disable-line react-hooks/exhaustive-deps

  const w = werte[ind] || {};
  const stimmungAuf = eigen.monate.map((m) => w[m] ?? null);
  const versatz = useMemo(() => besterVersatz(eigen.yoy, stimmungAuf, 6), [JSON.stringify(eigen.yoy), JSON.stringify(stimmungAuf)]); // eslint-disable-line react-hooks/exhaustive-deps

  const alle = [...new Set([...Object.keys(w), ...eigen.monate])].filter((m) => m < heute).sort().slice(-36);
  const yoyJe = Object.fromEntries(eigen.monate.map((m, i) => [m, eigen.yoy[i] == null ? null : eigen.yoy[i] * 100]));
  const chart = alle.map((m) => ({ Monat: m, Stimmung: w[m] ?? null, Wachstum: yoyJe[m] ?? null }));

  const karte = (i) => {
    const r = werte[i.key] || {};
    const ms = Object.keys(r).sort();
    const st = ms[ms.length - 1];
    const v = st ? r[st] : null, v3 = st ? r[monatMinus(st, 3)] : null;
    const d = v != null && v3 != null ? v - v3 : null;
    const gewaehlt = ind === i.key;
    return (
      <button key={i.key} onClick={() => setInd(i.key)} aria-pressed={gewaehlt}
        style={{ flex: "1 1 140px", textAlign: "left", cursor: "pointer", borderRadius: 8, padding: "8px 10px",
          border: `1px solid ${gewaehlt ? "var(--accent)" : "var(--border)"}`,
          background: gewaehlt ? "color-mix(in srgb, var(--accent) 10%, transparent)" : "transparent", color: "var(--text-main)" }}>
        <div style={{ fontSize: 11.5, color: "var(--text-dim)" }}>{i.kurz}</div>
        <div style={{ fontSize: 18, fontWeight: 650, color: "var(--text-bright)", fontFamily: "var(--font-mono)" }}>
          {v == null ? "–" : i.art === "index" ? nf1.format(v) : nfS.format(v)}
        </div>
        <div style={{ fontSize: 11.5, color: d == null ? "var(--text-dim)" : d > 0.5 ? "var(--ok)" : d < -0.5 ? "var(--err)" : "var(--text-dim)" }}>
          {d == null ? "–" : `${d > 0 ? "▲" : d < 0 ? "▼" : "■"} ${nfS.format(d)} in 3 Monaten`}
        </div>
      </button>
    );
  };

  const gew = INDIKATOREN.find((i) => i.key === ind);
  const achse = { fontSize: 11, fill: "var(--text-dim)" };
  const tt = { background: "var(--bg-card)", border: "1px solid var(--border)", fontSize: 11.5 };
  const stand = Object.keys(w).sort().pop();
  const trend = stand && w[monatMinus(stand, 3)] != null ? w[stand] - w[monatMinus(stand, 3)] : null;

  return (
    <div style={{ padding: "12px 16px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
      {fehler && <p style={{ margin: 0, fontSize: 12.5, color: "var(--err-soft, var(--err))" }}>Stimmungsdaten nicht verfügbar: {fehler}</p>}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }} role="group" aria-label="Indikator">{INDIKATOREN.map(karte)}</div>

      {chart.length > 1 && (
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-main)", margin: "2px 0 2px 4px" }}>
            {gew?.kurz}{gew?.art === "index" ? " (langjähriger Durchschnitt = 100)" : " (Saldo: positive minus negative Antworten, %-Punkte)"}
          </div>
          <ResponsiveContainer width="100%" height={170}>
            <LineChart data={chart} syncId={`stimmung-${widget.id}`} margin={{ top: 6, right: 16, bottom: 0, left: 4 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="Monat" tick={achse} hide />
              <YAxis tick={achse} width={56} domain={["auto", "auto"]} tickFormatter={(v) => nf1.format(v)} />
              <ReferenceLine y={gew?.art === "index" ? 100 : 0} stroke="var(--text-dim)" strokeDasharray="4 4" />
              <Tooltip labelFormatter={monatText} formatter={(v) => (v == null ? "–" : nf1.format(v))} contentStyle={tt} />
              <Line dataKey="Stimmung" name={gew?.kurz} stroke="#a78bfa" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
          <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-main)", margin: "6px 0 2px 4px" }}>
            Ihr Umsatzwachstum (3 Monate gegen dieselben 3 Monate im Vorjahr, %)
          </div>
          <ResponsiveContainer width="100%" height={150}>
            <LineChart data={chart} syncId={`stimmung-${widget.id}`} margin={{ top: 6, right: 16, bottom: 4, left: 4 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="Monat" tick={achse} tickFormatter={monatText} minTickGap={18} />
              <YAxis tick={achse} width={56} tickFormatter={(v) => `${nf1.format(v)} %`} />
              <ReferenceLine y={0} stroke="var(--text-dim)" strokeDasharray="4 4" />
              <Tooltip labelFormatter={monatText} formatter={(v) => (v == null ? "–" : `${nfS.format(v)} %`)} contentStyle={tt} />
              <Line dataKey="Wachstum" name="Ihr Wachstum" stroke="var(--accent)" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: "10px 12px", fontSize: 13, lineHeight: 1.5, color: "var(--text-main)",
        display: "flex", flexDirection: "column", gap: 4 }}>
        <strong style={{ fontSize: 12, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: ".05em" }}>Zusammenhang</strong>
        {versatz?.r != null ? (
          <span>
            Ihr Umsatzwachstum hing <b style={{ color: "var(--text-bright)" }}>{staerke(versatz.r)}</b> mit „{gew?.kurz}“ zusammen
            (r = {nf2.format(versatz.r)}, {versatz.n} Monate), am stärksten {versatz.lag === 0 ? "im selben Monat" : `mit ${versatz.lag} Monat${versatz.lag > 1 ? "en" : ""} Verzug`}.
            {Math.abs(versatz.r) >= 0.3 && versatz.lag > 0 && versatz.r > 0 && trend != null && Math.abs(trend) > 0.5 && (
              <> Die Stimmung ist in den letzten drei Monaten {trend > 0 ? "gestiegen" : "gesunken"} – das spräche eher für
                {trend > 0 ? " stärkeres" : " schwächeres"} Wachstum in den nächsten {versatz.lag} Monat{versatz.lag > 1 ? "en" : ""}.</>
            )}
          </span>
        ) : (
          <span style={{ color: "var(--text-dim)" }}>Für den Zusammenhang fehlen Monate: es braucht rund zwei Jahre eigenen Umsatz.</span>
        )}
        <span style={{ fontSize: 12, color: "var(--text-dim)" }}>
          Die Umfragen erscheinen zum Monatsende für den laufenden Monat – Wochen vor jeder Umsatzstatistik. Ein Zusammenhang ist
          noch keine Ursache, und er gilt für das Gesamtgeschäft, nicht für einzelne Kunden.
        </span>
      </div>
      <span style={{ fontSize: 11.5, color: "var(--text-dim)" }}>
        Quelle: {reihe?.quelle || "Eurostat / EU-Kommission, Konjunkturumfragen"}{stand ? ` · Stand ${monatText(stand)}` : ""}
        {reihe?.hinweis ? ` · ${reihe.hinweis}` : ""} · es werden keine Kundendaten übertragen
      </span>
    </div>
  );
}
