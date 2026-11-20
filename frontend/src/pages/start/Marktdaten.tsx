/**
 * Büro › Marktdaten: Katalog aller Markt- und Umfelddaten des monstersuite-Datendienstes
 * (Destatis, Eurostat, DWD, RKI, EZB, EU-Kommission) – entdecken, Kurve ansehen, als CSV mitnehmen.
 * Im Mapping nutzbar über „Neues Dataset › Umfelddaten“ (components/dataset/StepUmfeld.tsx).
 * Backend: GET /api/umfeld/datenkatalog, POST /api/umfeld/reihen.
 */
import { useEffect, useMemo, useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { Download, Search, X, Loader2 } from "lucide-react";
import api, { fehlerText } from "../../api/client";
import { S, karte, knopf, Seitenkopf } from "./StartLayout";
import { useAuth } from "../../context/AuthContext";
import { GRUPPEN, kurzQuelle, type Groesse } from "../../components/dataset/StepUmfeld";
import { monatText } from "../../components/forms/widgets/monat";

const FARBEN = ["var(--accent)", "#a78bfa", "#fcd34d"];
const ZEITRAUM = [[24, "2 J."], [60, "5 J."], [120, "10 J."], [0, "alles"]] as const;
const nf = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 });
const achse = { fontSize: 11, fill: "var(--text-dim)" };
const tt = { background: "var(--bg-card)", border: "1px solid var(--border)", fontSize: 11.5 };

function vonMonat(monate: number, takt: string) {
  if (!monate) return "";
  const d = new Date(); d.setMonth(d.getMonth() - monate);
  const m = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  return takt === "jahr" ? m.slice(0, 4) : m;
}

function aktualisierung(h: number) {
  return h <= 12 ? "mehrmals täglich geprüft" : h <= 24 ? "täglich geprüft" : "wöchentlich geprüft";
}

function Detail({ g, onClose }: { g: Groesse; onClose: () => void }) {
  const start = g.regionen.find((r) => r.code === "Deutschland" || r.code === "Insgesamt" || r.code === "BS-ESI-I")
    || g.regionen[0];
  const [regionen, setRegionen] = useState<string[]>(start ? [start.code] : []);
  const [monate, setMonate] = useState<number>(60);
  const [suche, setSuche] = useState("");
  const [daten, setDaten] = useState<any>(null);
  const [fehler, setFehler] = useState("");
  const name = (c: string) => g.regionen.find((r) => r.code === c)?.label || c;

  useEffect(() => {
    if (!regionen.length) { setDaten(null); return; }
    setDaten(null); setFehler("");
    api.post("/api/umfeld/reihen", { groessen: [g.key], regionen, von: vonMonat(monate, g.takt), bis: "" })
      .then(({ data }) => setDaten((data.reihen || [])[0] || {}))
      .catch((e) => setFehler(fehlerText(e)));
  }, [g.key, regionen.join("|"), monate]);

  const zeilen = useMemo(() => {
    const w = daten?.werte || {};
    const perioden = [...new Set(Object.values(w).flatMap((x: any) => Object.keys(x || {})))].sort();
    return perioden.map((p) => ({ Periode: p, ...Object.fromEntries(regionen.map((r) => [r, w[r]?.[p] ?? null])) }));
  }, [daten, regionen]);

  const treffer = useMemo(() => {
    const s = suche.trim().toLowerCase();
    if (!s) return [];
    return g.regionen.filter((r) => !regionen.includes(r.code)
      && (r.code + " " + r.label).toLowerCase().includes(s)).slice(0, 12);
  }, [suche, g.regionen, regionen]);

  const csv = () => {
    const kopf = ["Periode", ...regionen.map(name)].join(";");
    const rumpf = zeilen.map((z) => [z.Periode, ...regionen.map((r) => z[r] == null ? "" : String(z[r]).replace(".", ","))].join(";"));
    const text = [kopf, ...rumpf, "", `Einheit: ${g.einheit}`, `Quelle: ${g.quelle}`].join("\r\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob(["﻿" + text], { type: "text/csv;charset=utf-8" }));
    a.download = `${g.key}.csv`; a.click(); URL.revokeObjectURL(a.href);
  };

  const viele = g.regionen.length > 20;
  return (
    <div style={{ ...karte, padding: 18, display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h2 style={{ margin: 0, fontSize: 18, color: S.textBright }}>{g.label}</h2>
          <p style={{ margin: "4px 0 0", fontSize: 12.5, color: S.textDim, lineHeight: 1.5 }}>
            {g.einheit} · {g.takt === "jahr" ? "Jahreswerte" : "Monatswerte"}
            {g.von ? ` · ${monatText(g.von)} bis ${monatText(g.bis)}` : ""} · {aktualisierung(g.aktualisierung_h)}
          </p>
        </div>
        <button onClick={onClose} aria-label="Schließen" style={{ ...knopf.neben, padding: 6, minHeight: 0 }}><X size={16} /></button>
      </div>

      {g.regionen.length > 1 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
            {regionen.map((r, i) => (
              <span key={r} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, padding: "3px 6px 3px 10px",
                borderRadius: 999, border: `1px solid ${FARBEN[i]}`, color: S.textBright }}>
                {name(r)}
                <button onClick={() => setRegionen(regionen.filter((x) => x !== r))} aria-label="entfernen"
                  style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0, display: "flex" }}>
                  <X size={12} /></button>
              </span>
            ))}
            {regionen.length < 3 && !viele && (
              <select value="" onChange={(e) => e.target.value && setRegionen([...regionen, e.target.value])}
                style={{ fontSize: 12, padding: "4px 8px", borderRadius: 8, border: `1px solid ${S.border}`,
                  backgroundColor: S.bgEl, color: S.textMain }}>
                <option value="">+ vergleichen mit …</option>
                {g.regionen.filter((r) => !regionen.includes(r.code)).map((r) => <option key={r.code} value={r.code}>{r.label}</option>)}
              </select>
            )}
          </div>
          {regionen.length < 3 && viele && (
            <div style={{ position: "relative", maxWidth: 420 }}>
              <Search size={13} style={{ position: "absolute", left: 9, top: 10, color: S.textDim }} />
              <input value={suche} onChange={(e) => setSuche(e.target.value)} placeholder={`${g.regionen.length} Einträge durchsuchen …`}
                style={{ width: "100%", padding: "7px 10px 7px 28px", fontSize: 12.5, borderRadius: 8,
                  border: `1px solid ${S.border}`, backgroundColor: S.bgEl, color: S.textBright, outline: "none" }} />
              {treffer.length > 0 && (
                <div style={{ position: "absolute", zIndex: 5, top: "100%", left: 0, right: 0, marginTop: 2, ...karte,
                  maxHeight: 260, overflowY: "auto" }}>
                  {treffer.map((r) => (
                    <button key={r.code} onClick={() => { setRegionen([...regionen, r.code]); setSuche(""); }}
                      style={{ display: "block", width: "100%", textAlign: "left", padding: "6px 10px", fontSize: 12.5,
                        background: "none", border: "none", color: S.textMain, cursor: "pointer" }}>
                      {r.label} <span style={{ color: S.textDim }}>{r.code !== r.label ? r.code : ""}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
        {ZEITRAUM.map(([m, t]) => (
          <button key={m} onClick={() => setMonate(m)} style={{ ...knopf.neben, minHeight: 0, padding: "4px 10px", fontSize: 12,
            borderColor: monate === m ? S.accent : S.border, color: monate === m ? S.textBright : S.textMain }}>{t}</button>
        ))}
        <button onClick={csv} disabled={!zeilen.length} style={{ ...knopf.neben, minHeight: 0, padding: "4px 10px", fontSize: 12, marginLeft: "auto" }}>
          <Download size={13} /> CSV
        </button>
      </div>

      {fehler && <p style={{ margin: 0, color: "var(--err)", fontSize: 13 }}>{fehler}</p>}
      {!daten && !fehler && regionen.length > 0 && (
        <div style={{ height: 240, display: "flex", alignItems: "center", justifyContent: "center", color: S.textDim, gap: 8 }}>
          <Loader2 size={16} className="animate-spin" /> Lädt …
        </div>
      )}
      {daten?.hinweis && <p style={{ margin: 0, fontSize: 12.5, color: S.textDim }}>{daten.hinweis}</p>}
      {daten && zeilen.length > 0 && (
        <>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={zeilen} margin={{ top: 6, right: 16, bottom: 0, left: 4 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="Periode" tick={achse} tickFormatter={monatText} minTickGap={24} />
              <YAxis tick={achse} width={64} domain={["auto", "auto"]} tickFormatter={(v) => nf.format(v)} />
              <Tooltip labelFormatter={monatText} formatter={(v: any) => (v == null ? "–" : `${nf.format(v)} ${g.einheit}`)} contentStyle={tt} />
              {regionen.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
              {regionen.map((r, i) => (
                <Line key={r} dataKey={r} name={name(r)} stroke={FARBEN[i]} strokeWidth={2} dot={false}
                  connectNulls isAnimationActive={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
          <div style={{ overflowX: "auto", border: `1px solid ${S.border}`, borderRadius: 10, maxHeight: 260 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead><tr>
                <th style={{ textAlign: "left", padding: "8px 12px", color: S.textDim, fontWeight: 500, position: "sticky", top: 0, background: S.bgCard }}>Periode</th>
                {regionen.map((r) => <th key={r} style={{ textAlign: "right", padding: "8px 12px", color: S.textDim, fontWeight: 500,
                  position: "sticky", top: 0, background: S.bgCard }}>{name(r)}</th>)}
              </tr></thead>
              <tbody>
                {[...zeilen].reverse().map((z) => (
                  <tr key={z.Periode}>
                    <td style={{ padding: "6px 12px", borderTop: `1px solid ${S.border}`, color: S.textMain }}>{monatText(z.Periode)}</td>
                    {regionen.map((r) => <td key={r} style={{ padding: "6px 12px", borderTop: `1px solid ${S.border}`, textAlign: "right",
                      color: S.textBright, fontVariantNumeric: "tabular-nums" }}>{z[r] == null ? "–" : nf.format(z[r])}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <p style={{ margin: 0, fontSize: 11.5, color: S.textDim, lineHeight: 1.5 }}>
        Quelle: {g.quelle}. Die Quellenangabe gehört bei jeder Weitergabe der Zahlen dazu.
      </p>
    </div>
  );
}

export default function Marktdaten() {
  const { user } = useAuth();
  const [katalog, setKatalog] = useState<Groesse[] | null>(null);
  const [fehler, setFehler] = useState("");
  const [suche, setSuche] = useState("");
  const [offen, setOffen] = useState<string | null>(null);

  useEffect(() => {
    api.get("/api/umfeld/datenkatalog").then(({ data }) => setKatalog(data.groessen || []))
      .catch((e) => setFehler(fehlerText(e, "Datenkatalog nicht erreichbar")));
  }, []);

  const gruppen = useMemo(() => {
    if (!katalog) return [];
    const s = suche.trim().toLowerCase();
    const passt = (g: Groesse) => !s || [g.label, g.quelle, g.einheit, ...g.regionen.slice(0, 2000).map((r) => r.label)]
      .some((t) => (t || "").toLowerCase().includes(s));
    const nachKey = Object.fromEntries(katalog.map((g) => [g.key, g]));
    const bekannt = new Set(GRUPPEN.flatMap(([, k]) => k));
    const aus = GRUPPEN.map(([t, k]) => [t, k.map((x) => nachKey[x]).filter(Boolean)] as [string, Groesse[]]);
    aus.push(["Weitere", katalog.filter((g) => !bekannt.has(g.key))]);
    return aus.map(([t, l]) => [t, l.filter(passt)] as [string, Groesse[]]).filter(([, l]) => l.length);
  }, [katalog, suche]);

  const gewaehlt = katalog?.find((g) => g.key === offen) || null;
  const quellen = katalog ? new Set(katalog.map((g) => kurzQuelle(g.quelle).split(" ")[0])).size : 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20, maxWidth: 1100 }}>
      <Seitenkopf titel="Marktdaten"
        text={katalog ? `${katalog.length} Reihen aus amtlichen Quellen – Wetter, Preise, Branchenumsätze, Konjunktur, Bevölkerung. `
          + "Täglich aktuell, ohne eigenes Konto. Ihre eigenen Zahlen verlassen dabei nie Ihr System."
          : "Markt- und Umfelddaten aus amtlichen Quellen."} />
      {fehler && <p style={{ margin: 0, color: "var(--err)" }}>{fehler}</p>}
      {!katalog && !fehler && <span style={{ color: S.textDim }}>Lädt …</span>}
      {katalog && (
        <>
          <div style={{ position: "relative", maxWidth: 460 }}>
            <Search size={15} style={{ position: "absolute", left: 11, top: 11, color: S.textDim }} />
            <input value={suche} onChange={(e) => setSuche(e.target.value)}
              placeholder="Suchen, z. B. Papier, Diesel, Bayern, Großhandel …"
              style={{ width: "100%", padding: "9px 12px 9px 34px", fontSize: 14, borderRadius: 10,
                border: `1px solid ${S.border}`, backgroundColor: S.bgEl, color: S.textBright, outline: "none" }} />
          </div>

          {gewaehlt && <Detail key={gewaehlt.key} g={gewaehlt} onClose={() => setOffen(null)} />}

          {gruppen.map(([titel, liste]) => (
            <section key={titel} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <h2 style={{ margin: 0, fontSize: 13, textTransform: "uppercase", letterSpacing: "0.08em", color: S.textDim }}>{titel}</h2>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(250px, 1fr))", gap: 10 }}>
                {liste.map((g) => (
                  <button key={g.key} onClick={() => { setOffen(g.key); window.scrollTo({ top: 0, behavior: "smooth" }); }}
                    style={{ ...karte, textAlign: "left", padding: "12px 14px", cursor: "pointer", display: "flex",
                      flexDirection: "column", gap: 4, borderColor: offen === g.key ? S.accent : S.border }}>
                    <span style={{ fontSize: 14, fontWeight: 600, color: S.textBright }}>{g.label}</span>
                    <span style={{ fontSize: 12, color: S.textDim }}>{kurzQuelle(g.quelle)} · {g.einheit}</span>
                    <span style={{ fontSize: 12, color: S.textDim }}>
                      {g.von ? `${monatText(g.von)} – ${monatText(g.bis)}` : (g.hinweis || "noch keine Daten")}
                      {g.regionen.length > 1 ? ` · ${nf.format(g.regionen.length)} ${g.regionen_art === "land" ? "Regionen" : "Einträge"}` : ""}
                    </span>
                  </button>
                ))}
              </div>
            </section>
          ))}
          {gruppen.length === 0 && <p style={{ margin: 0, color: S.textDim }}>Nichts gefunden.</p>}

          {!user?.is_portal_only && (
            <p style={{ margin: 0, fontSize: 12.5, color: S.textDim, lineHeight: 1.5 }}>
              Mit eigenen Zahlen verknüpfen: in der Werkstatt „Neues Dataset › Umfelddaten“ – danach steht die Reihe im
              Mapping-Editor wie jede andere Quelle bereit ({quellen} Quellen, Lizenzen geprüft).
            </p>
          )}
        </>
      )}
    </div>
  );
}
