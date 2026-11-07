/**
 * Erzeugerpreise: wie sich die Herstellerpreise der Waren entwickeln, die Sie einkaufen
 * (Destatis 61241-0006, Erzeugerpreisindex gewerblicher Produkte nach GP2019, 2021 = 100, über den
 * monstersuite-Datendienst). Steigen sie, folgen die Einkaufspreise meist mit einigen Monaten Verzug.
 *
 * Welche Güterklassen passen, wählt der Nutzer je Mandant (/api/business-config/erzeugerpreise).
 * Ohne Auswahl schlägt die Kachel Klassen aus den Warennummern der Einkäufe vor (Zolltarif-Kapitel →
 * GP-Abteilung, grob) und zeigt sie als Vorschlag – gespeichert wird erst, was jemand übernimmt.
 *
 * Konfiguration (widget.config):
 *   spalten: { warennummer: "Warennummer", wert: "Einkaufswert" } – Zeilen aus „Einkauf je Warennummer“
 */
import { useEffect, useMemo, useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, ReferenceLine } from "recharts";
import api, { fehlerText } from "../../../api/client";
import { useAuth } from "../../../context/AuthContext";
import { monatText } from "./monat";

// Zolltarif (HS-Position bzw. -Kapitel) → GP2019-Klasse. Grob, nur als Vorschlag; die längste Übereinstimmung gewinnt.
export const HS_GP = {
  "4818": "GP19-1722", "4819": "GP19-1721", "4802": "GP19-1712", "4803": "GP19-1712", "4810": "GP19-1712", "4811": "GP19-1712",
  "4820": "GP19-1723", "4821": "GP19-1729", "4823": "GP19-1729", "48": "GP19-17",
  "3923": "GP19-2222", "3924": "GP19-2229", "3926": "GP19-2229", "3920": "GP19-2221", "3921": "GP19-2221", "39": "GP19-22",
  "4015": "GP19-2219", "40": "GP19-221",
  "3401": "GP19-2041", "3402": "GP19-2041", "3405": "GP19-2041", "34": "GP19-204",
  "3307": "GP19-2042", "3304": "GP19-2042", "3305": "GP19-2042", "33": "GP19-2042",
  "3808": "GP19-202", "30": "GP19-21", "61": "GP19-14", "62": "GP19-14", "63": "GP19-13", "56": "GP19-13",
  "44": "GP19-16", "70": "GP19-23", "69": "GP19-23", "73": "GP19-25", "76": "GP19-24", "82": "GP19-25",
  "84": "GP19-28", "85": "GP19-27", "90": "GP19-26", "94": "GP19-31", "96": "GP19-32", "95": "GP19-32",
  "22": "GP19-11", "21": "GP19-10", "19": "GP19-10", "20": "GP19-10", "17": "GP19-10", "15": "GP19-10",
};
const FARBEN = ["var(--accent)", "#a78bfa", "#60a5fa", "#f472b6", "#34d399", "#fbbf24"];
const zahl = (x) => { if (x == null || x === "") return null; const n = typeof x === "number" ? x : Number(String(x).replace(",", ".")); return Number.isFinite(n) ? n : null; };
const nf0 = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const nfP = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1, signDisplay: "exceptZero" });
const monatMinus = (mo, n) => {
  const [j, m] = mo.split("-").map(Number);
  const d = new Date(j, m - 1 - n, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
};
const gpText = (c) => { const d = c.replace("GP19-", ""); return d.replace(/^(\d{2})(\d{2})?(\d{2})?$/, (_, a, b, c2) => [a, b, c2].filter(Boolean).join(".")); };

/** Vorschläge aus Warennummern: {code, wert} je GP-Klasse, die im Katalog steht, nach Einkaufswert. */
export function vorschlaege(rows, sp, katalogCodes) {
  const m = new Map();
  for (const r of rows || []) {
    const kn = String(r[sp.warennummer] ?? "").replace(/\D/g, "");
    if (kn.length < 4) continue;
    let gp = null;
    for (const k of [kn.slice(0, 4), kn.slice(0, 2)]) {
      let c = HS_GP[k];
      while (c && katalogCodes && !katalogCodes.has(c) && c.length > 7) c = c.slice(0, -1);   // gröbere Klasse, falls fein fehlt
      if (c && (!katalogCodes || katalogCodes.has(c))) { gp = c; break; }
    }
    if (!gp) continue;
    m.set(gp, (m.get(gp) || 0) + (zahl(r[sp.wert]) || 0));
  }
  return [...m.entries()].map(([code, wert]) => ({ code, wert })).sort((a, b) => b.wert - a.wert);
}

let katalogCache = null;

export default function ErzeugerpreiseWidget({ widget, result, projectId = null }) {
  const cfg = widget.config || {};
  const sp = { warennummer: "Warennummer", wert: "Einkaufswert", ...(cfg.spalten || {}) };
  const { user } = useAuth();
  const darfAendern = !user?.is_portal_only && projectId != null;

  const [katalog, setKatalog] = useState(null);
  const [katFehler, setKatFehler] = useState(null);
  const [auswahl, setAuswahl] = useState(undefined);
  const [reihe, setReihe] = useState(null);
  const [fehler, setFehler] = useState(null);
  const [waehlen, setWaehlen] = useState(false);
  const [suche, setSuche] = useState("");

  useEffect(() => {
    let lebt = true;
    (katalogCache || (katalogCache = api.get("/api/umfeld/erzeugerpreise/katalog").then((r) => r.data)
      .then((d) => { if (d.hinweis || !(d.gueter || []).length) katalogCache = null; return d; })
      .catch((e) => { katalogCache = null; throw e; })))
      .then((d) => { if (!lebt) return; setKatalog(d.gueter || []); setKatFehler(d.hinweis || null); })
      .catch((e) => lebt && setKatFehler(fehlerText(e)));
    return () => { lebt = false; };
  }, []);
  useEffect(() => {
    let lebt = true;
    const q = projectId != null ? `?project_id=${projectId}` : "";
    api.get(`/api/business-config/erzeugerpreise${q}`)
      .then(({ data }) => lebt && setAuswahl(data.auswahl?.gueter || []))
      .catch(() => lebt && setAuswahl([]));
    return () => { lebt = false; };
  }, [projectId]);

  const labels = useMemo(() => Object.fromEntries((katalog || []).map((z) => [z.code, z.label])), [katalog]);
  const codesKat = useMemo(() => (katalog ? new Set(katalog.map((z) => z.code)) : null), [katalog]);
  const vorschlag = useMemo(() => vorschlaege(result?.rows, sp, codesKat), [result, codesKat]); // eslint-disable-line react-hooks/exhaustive-deps
  const gewaehlt = (auswahl || []).map((z) => z.code);
  const istVorschlag = !gewaehlt.length;
  const zeigen = (istVorschlag ? vorschlag.slice(0, 6).map((v) => v.code) : gewaehlt).slice(0, 12);
  const wertJe = Object.fromEntries(vorschlag.map((v) => [v.code, v.wert]));

  useEffect(() => {
    if (!zeigen.length || !katalog?.length) return;
    let lebt = true;
    const heute = new Date().toISOString().slice(0, 7);
    setFehler(null);
    api.post("/api/umfeld/reihen", { groessen: ["erzeugerpreise"], regionen: zeigen, von: monatMinus(heute, 40), bis: "" })
      .then(({ data }) => lebt && setReihe(data.reihen?.[0] || null))
      .catch((e) => lebt && setFehler(fehlerText(e)));
    return () => { lebt = false; };
  }, [zeigen.join(","), !!katalog?.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const speichern = async (neu) => {
    const gueter = neu.map((c) => ({ code: c, label: labels[c] || c }));
    setAuswahl(gueter);
    if (!darfAendern) return;
    try { await api.put("/api/business-config/erzeugerpreise", { project_id: projectId, gueter }); }
    catch (e) { setFehler(fehlerText(e)); }
  };

  const werte = reihe?.werte || {};
  const stand = reihe?.stand;
  const zeilen = zeigen.map((c) => {
    const w = werte[c] || {};
    const ms = Object.keys(w).sort();
    const letzt = ms[ms.length - 1];
    const jetzt = letzt ? w[letzt] : null;
    const rel = (n) => { const v = letzt ? w[monatMinus(letzt, n)] : null; return jetzt != null && v ? jetzt / v - 1 : null; };
    return { code: c, label: labels[c] || c, letzt, jetzt, vj: rel(12), m3: rel(3), wert: wertJe[c] };
  });
  const chart = useMemo(() => {
    const cs = zeigen.slice(0, 6);
    const ms = [...new Set(cs.flatMap((c) => Object.keys(werte[c] || {})))].sort().slice(-36);
    return ms.map((m) => Object.fromEntries([["Monat", m], ...cs.map((c) => [c, werte[c]?.[m] ?? null])]));
  }, [reihe]); // eslint-disable-line react-hooks/exhaustive-deps

  const th = { textAlign: "left", padding: "6px 8px", fontSize: 11, color: "var(--text-dim)", fontWeight: 600,
    borderBottom: "1px solid var(--border)", whiteSpace: "nowrap" };
  const td = { padding: "5px 8px", fontSize: 12.5, color: "var(--text-main)", borderBottom: "1px solid var(--border)" };
  const rechts = { textAlign: "right", whiteSpace: "nowrap" };
  const achse = { fontSize: 11, fill: "var(--text-dim)" };
  const knopf = { padding: "4px 10px", fontSize: 12, cursor: "pointer", border: "1px solid var(--border)", borderRadius: 6,
    background: "transparent", color: "var(--text-main)" };
  const farbe = (a) => (a == null ? "var(--text-dim)" : a > 0.03 ? "var(--err)" : a < -0.03 ? "var(--ok)" : "var(--text-main)");
  const treffer = (katalog || []).filter((z) => !suche || `${z.label} ${gpText(z.code)}`.toLowerCase().includes(suche.toLowerCase()));

  return (
    <div style={{ padding: "12px 16px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
      {katFehler && <p style={{ margin: 0, fontSize: 12.5, color: "var(--text-dim)" }}>{katFehler}</p>}
      {fehler && <p style={{ margin: 0, fontSize: 12.5, color: "var(--err-soft, var(--err))" }}>Erzeugerpreise nicht verfügbar: {fehler}</p>}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <strong style={{ fontSize: 12, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: ".05em" }}>
          {istVorschlag ? "Vorschlag aus Ihren Warennummern" : "Ihre Güterklassen"}
        </strong>
        {katalog?.length > 0 && (
          <button onClick={() => setWaehlen(!waehlen)} style={knopf}>{waehlen ? "Fertig" : istVorschlag ? "Güterklassen wählen" : "Auswahl ändern"}</button>
        )}
        {istVorschlag && vorschlag.length > 0 && darfAendern && (
          <button onClick={() => speichern(vorschlag.slice(0, 6).map((v) => v.code))} style={knopf}>Vorschlag übernehmen</button>
        )}
        {istVorschlag && !vorschlag.length && katalog?.length > 0 && (
          <span style={{ fontSize: 12, color: "var(--text-dim)" }}>Keine Warennummern im Zeitraum – bitte Güterklassen wählen.</span>
        )}
      </div>
      {waehlen && (
        <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 10, display: "flex", flexDirection: "column", gap: 6 }}>
          <input value={suche} onChange={(e) => setSuche(e.target.value)} placeholder="Ware suchen, z. B. Toilettenpapier, Kunststoff …" aria-label="Güterklasse suchen"
            style={{ padding: "5px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg-elevated)", color: "var(--text-main)", fontSize: 12.5 }} />
          <div style={{ maxHeight: 240, overflow: "auto", display: "flex", flexDirection: "column" }}>
            {treffer.slice(0, 150).map((z) => {
              const an = gewaehlt.includes(z.code);
              const tiefe = z.code.length - 7;
              return (
                <label key={z.code} style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12.5, padding: "2px 0", cursor: "pointer",
                  paddingLeft: suche ? 0 : Math.max(0, tiefe) * 10 }}>
                  <input type="checkbox" checked={an} disabled={!an && gewaehlt.length >= 12}
                    onChange={() => speichern(an ? gewaehlt.filter((c) => c !== z.code) : [...gewaehlt, z.code])} />
                  <span style={{ fontWeight: tiefe <= 0 ? 600 : 400 }}>{z.label}</span>
                  <span style={{ fontSize: 11, color: "var(--text-dim)" }}>GP {gpText(z.code)}</span>
                </label>
              );
            })}
          </div>
          <span style={{ fontSize: 11.5, color: "var(--text-dim)" }}>
            Bis zu 12 Güterklassen. {darfAendern ? "Die Auswahl gilt für diesen Mandanten." : "Ohne Bearbeitungsrecht nur für diese Ansicht."}
          </span>
        </div>
      )}
      {reihe && zeilen.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={th}>Güterklasse</th>
                {istVorschlag && <th style={{ ...th, ...rechts }}>Ihr Einkauf</th>}
                <th style={{ ...th, ...rechts }}>Index {stand ? monatText(stand) : ""}</th>
                <th style={{ ...th, ...rechts }}>zum Vorjahr</th>
                <th style={{ ...th, ...rechts }}>in 3 Monaten</th>
              </tr>
            </thead>
            <tbody>
              {zeilen.map((z, i) => (
                <tr key={z.code}>
                  <td style={td}>
                    {i < 6 && <span style={{ color: FARBEN[i] }}>■ </span>}{z.label}{" "}
                    <span style={{ fontSize: 11, color: "var(--text-dim)" }}>GP {gpText(z.code)}</span>
                  </td>
                  {istVorschlag && <td style={{ ...td, ...rechts }}>{z.wert ? `${nf0.format(z.wert)} €` : "–"}</td>}
                  <td style={{ ...td, ...rechts }}>{z.jetzt == null ? "–" : nf1.format(z.jetzt)}</td>
                  <td style={{ ...td, ...rechts, color: farbe(z.vj), fontWeight: 600 }}>{z.vj == null ? "–" : `${nfP.format(z.vj * 100)} %`}</td>
                  <td style={{ ...td, ...rechts, color: farbe(z.m3) }}>{z.m3 == null ? "–" : `${nfP.format(z.m3 * 100)} %`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {chart.length > 1 && (
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-main)", margin: "2px 0 2px 4px" }}>Erzeugerpreisindex (2021 = 100)</div>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={chart} margin={{ top: 6, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="Monat" tick={achse} tickFormatter={monatText} minTickGap={24} />
              <YAxis tick={achse} domain={["auto", "auto"]} width={40} tickFormatter={(v) => nf0.format(v)} />
              <ReferenceLine y={100} stroke="var(--text-dim)" strokeDasharray="4 4" />
              <Tooltip labelFormatter={monatText} formatter={(v, n) => [v == null ? "–" : nf1.format(v), labels[n] || n]}
                contentStyle={{ background: "var(--bg-card)", border: "1px solid var(--border)", fontSize: 11.5 }} />
              <Legend wrapperStyle={{ fontSize: 11.5 }} formatter={(n) => `GP ${gpText(n)}`} />
              {zeigen.slice(0, 6).map((c, i) => <Line key={c} dataKey={c} stroke={FARBEN[i]} strokeWidth={2} dot={false} connectNulls />)}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      <span style={{ fontSize: 12, color: "var(--text-dim)", lineHeight: 1.5 }}>
        Erzeugerpreise = Verkaufspreise der Hersteller in Deutschland ab Werk, ohne Umsatzsteuer. Sie laufen den Einkaufspreisen des
        Handels meist einige Monate voraus: rot = mehr als 3 % gestiegen – Preiserhöhungen Ihrer Lieferanten sind wahrscheinlich.
        {istVorschlag ? " Der Vorschlag ordnet Ihre Warennummern grob einer Güterklasse zu; mit „Güterklassen wählen“ lässt er sich verfeinern." : ""}
      </span>
      <span style={{ fontSize: 11.5, color: "var(--text-dim)" }}>
        Quelle: {reihe?.quelle || "Statistisches Bundesamt (Destatis)"}, Tabelle 61241-0006{stand ? ` · Daten bis ${monatText(stand)}` : ""}
        {reihe?.hinweis ? ` · ${reihe.hinweis}` : ""} · es werden keine Kundendaten übertragen
      </span>
    </div>
  );
}
