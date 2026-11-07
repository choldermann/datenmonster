/**
 * Insolvenzklima: Unternehmensinsolvenzen in Deutschland (Destatis 52411, beantragte Verfahren je
 * Monat, über den monstersuite-Datendienst) neben der eigenen Zahlungsmoral.
 *
 * Oben die Lage insgesamt (letzte 12 Monate gegen die 12 davor), darunter die Kundenbranchen des
 * Mandanten – JTL kennt keine Branche am Kunden, deshalb wählt der Nutzer sie (je Mandant gespeichert
 * unter /api/business-config/kundenbranchen). Ohne Auswahl die Abschnitte A–S zur Orientierung.
 * Das Diagramm legt die eigene Ø Zahlungsdauer je Rechnungsmonat über die Insolvenzen insgesamt.
 * Die jüngsten zwei Monate fehlen bei der Zahlungsdauer: dort sind erst die schnellen Zahler erfasst.
 *
 * Konfiguration (widget.config):
 *   spalten: { monat: "Monat", dauer: "ZahldauerTage", verspaetet: "AnteilVerspaetet" }
 */
import { useEffect, useMemo, useState } from "react";
import { ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";
import api, { fehlerText } from "../../../api/client";
import { useAuth } from "../../../context/AuthContext";
import { monatText } from "./monat";

const zahl = (x) => { const n = typeof x === "number" ? x : Number(String(x ?? "").replace(",", ".")); return Number.isFinite(n) ? n : null; };
const nf0 = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const nfP = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0, signDisplay: "exceptZero" });
const ABSCHNITT = /^WZ08-[A-U]$/;
const monatMinus = (mo, n) => {
  const [j, m] = mo.split("-").map(Number);
  const d = new Date(j, m - 1 - n, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
};

/** Summe der letzten 12 Monate bis `stand` und der 12 davor; null, wenn ein Monat fehlt. */
export function zwoelfMonate(werte, stand) {
  if (!werte || !stand) return { jetzt: null, vorher: null, aenderung: null };
  const summe = (bis) => {
    let s = 0;
    for (let i = 0; i < 12; i++) { const v = werte[monatMinus(bis, i)]; if (v == null) return null; s += v; }
    return s;
  };
  const jetzt = summe(stand), vorher = summe(monatMinus(stand, 12));
  return { jetzt, vorher, aenderung: jetzt != null && vorher ? jetzt / vorher - 1 : null };
}

let katalogCache = null;

export default function InsolvenzenWidget({ widget, result, projectId = null }) {
  const cfg = widget.config || {};
  const sp = { monat: "Monat", dauer: "ZahldauerTage", verspaetet: "AnteilVerspaetet", ...(cfg.spalten || {}) };
  const { user } = useAuth();
  const darfAendern = !user?.is_portal_only && projectId != null;

  const [katalog, setKatalog] = useState(null);
  const [katFehler, setKatFehler] = useState(null);
  const [auswahl, setAuswahl] = useState(undefined);        // undefined = lädt
  const [mandantName, setMandantName] = useState(null);
  const [reihe, setReihe] = useState(null);
  const [fehler, setFehler] = useState(null);
  const [waehlen, setWaehlen] = useState(false);
  const [suche, setSuche] = useState("");

  useEffect(() => {
    let lebt = true;
    (katalogCache || (katalogCache = api.get("/api/umfeld/insolvenzen/katalog").then((r) => r.data)
      .then((d) => { if (d.hinweis || !(d.zweige || []).length) katalogCache = null; return d; })
      .catch((e) => { katalogCache = null; throw e; })))
      .then((d) => { if (!lebt) return; setKatalog(d.zweige || []); setKatFehler(d.hinweis || null); })
      .catch((e) => lebt && setKatFehler(fehlerText(e)));
    return () => { lebt = false; };
  }, []);
  useEffect(() => {
    let lebt = true;
    const q = projectId != null ? `?project_id=${projectId}` : "";
    api.get(`/api/business-config/kundenbranchen${q}`)
      .then(({ data }) => { if (!lebt) return; setAuswahl(data.auswahl?.zweige || []); setMandantName(data.mandant_name || null); })
      .catch(() => lebt && setAuswahl([]));
    return () => { lebt = false; };
  }, [projectId]);

  const labels = useMemo(() => Object.fromEntries((katalog || []).map((z) => [z.code, z.label])), [katalog]);
  const gewaehlt = (auswahl || []).map((z) => z.code);
  const zeigen = gewaehlt.length ? gewaehlt : (katalog || []).map((z) => z.code).filter((c) => ABSCHNITT.test(c));
  const codes = ["Insgesamt", ...zeigen].slice(0, 20);

  useEffect(() => {
    if (!katalog?.length || auswahl === undefined) return;
    let lebt = true;
    const heute = new Date().toISOString().slice(0, 7);
    setFehler(null);
    api.post("/api/umfeld/reihen", { groessen: ["insolvenzen"], regionen: codes, von: monatMinus(heute, 40), bis: "" })
      .then(({ data }) => lebt && setReihe(data.reihen?.[0] || null))
      .catch((e) => lebt && setFehler(fehlerText(e)));
    return () => { lebt = false; };
  }, [codes.join(","), !!katalog?.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const speichern = async (neu) => {
    const zweige = neu.map((c) => ({ code: c, label: labels[c] || c }));
    setAuswahl(zweige);
    if (!darfAendern) return;
    try { await api.put("/api/business-config/kundenbranchen", { project_id: projectId, zweige }); }
    catch (e) { setFehler(fehlerText(e)); }
  };

  const werte = reihe?.werte || {};
  const stand = reihe?.stand;
  const ges = zwoelfMonate(werte.Insgesamt, stand);
  const zeilen = zeigen.map((c) => ({ code: c, label: labels[c] || c, ...zwoelfMonate(werte[c], stand), letzter: werte[c]?.[stand] ?? null }))
    .sort((a, b) => (gewaehlt.length ? 0 : (b.jetzt || 0) - (a.jetzt || 0)));

  // Diagramm: Insolvenzen insgesamt je Monat + eigene Zahlungsdauer (ohne die jüngsten zwei Monate)
  const grenze = monatMinus(new Date().toISOString().slice(0, 7), 2);
  const eigen = useMemo(() => {
    const m = new Map();
    for (const r of result?.rows || []) {
      const mo = String(r[sp.monat] ?? "").slice(0, 7);
      if (/^\d{4}-\d{2}$/.test(mo) && mo < grenze) m.set(mo, { dauer: zahl(r[sp.dauer]), spaet: zahl(r[sp.verspaetet]) });
    }
    return m;
  }, [result]); // eslint-disable-line react-hooks/exhaustive-deps
  const monate = [...new Set([...Object.keys(werte.Insgesamt || {}), ...eigen.keys()])].sort().slice(-36);
  const chart = monate.map((m) => ({ Monat: m, Insolvenzen: werte.Insgesamt?.[m] ?? null, Zahldauer: eigen.get(m)?.dauer ?? null,
    Verspaetet: eigen.get(m)?.spaet ?? null }));

  const th = { textAlign: "left", padding: "6px 8px", fontSize: 11, color: "var(--text-dim)", fontWeight: 600,
    borderBottom: "1px solid var(--border)", whiteSpace: "nowrap" };
  const td = { padding: "5px 8px", fontSize: 12.5, color: "var(--text-main)", borderBottom: "1px solid var(--border)" };
  const rechts = { textAlign: "right", whiteSpace: "nowrap" };
  const achse = { fontSize: 11, fill: "var(--text-dim)" };
  const knopf = { padding: "4px 10px", fontSize: 12, cursor: "pointer", border: "1px solid var(--border)", borderRadius: 6,
    background: "transparent", color: "var(--text-main)" };
  const farbe = (a) => (a == null ? "var(--text-dim)" : a > 0.05 ? "var(--err)" : a < -0.05 ? "var(--ok)" : "var(--text-main)");
  const treffer = (katalog || []).filter((z) => z.code !== "Insgesamt" && (!suche || `${z.label} ${z.code}`.toLowerCase().includes(suche.toLowerCase())));

  return (
    <div style={{ padding: "12px 16px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
      {katFehler && <p style={{ margin: 0, fontSize: 12.5, color: "var(--text-dim)" }}>{katFehler}</p>}
      {fehler && <p style={{ margin: 0, fontSize: 12.5, color: "var(--err-soft, var(--err))" }}>Insolvenzdaten nicht verfügbar: {fehler}</p>}
      {ges.jetzt != null && (
        <div style={{ fontSize: 13, color: "var(--text-main)", lineHeight: 1.5 }}>
          Unternehmensinsolvenzen in Deutschland, {monatText(monatMinus(stand, 11))} – {monatText(stand)}:{" "}
          <b style={{ color: "var(--text-bright)" }}>{nf0.format(ges.jetzt)}</b>
          {ges.aenderung != null && <> – <b style={{ color: farbe(ges.aenderung) }}>{nfP.format(ges.aenderung * 100)} %</b> gegenüber den zwölf Monaten davor.</>}
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <strong style={{ fontSize: 12, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: ".05em" }}>
          {gewaehlt.length ? `Ihre Kundenbranchen${mandantName ? ` (${mandantName})` : ""}` : "Nach Wirtschaftsabschnitten"}
        </strong>
        {katalog?.length > 0 && (
          <button onClick={() => setWaehlen(!waehlen)} style={knopf}>
            {waehlen ? "Fertig" : gewaehlt.length ? "Branchen ändern" : "Kundenbranchen wählen"}
          </button>
        )}
        {!gewaehlt.length && !waehlen && (
          <span style={{ fontSize: 12, color: "var(--text-dim)" }}>Wählen Sie die Branchen Ihrer wichtigsten Kunden – z. B. Gebäudereinigung, Gastronomie, Pflegeheime.</span>
        )}
      </div>
      {waehlen && (
        <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 10, display: "flex", flexDirection: "column", gap: 6 }}>
          <input value={suche} onChange={(e) => setSuche(e.target.value)} placeholder="Branche suchen …" aria-label="Branche suchen"
            style={{ padding: "5px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg-elevated)", color: "var(--text-main)", fontSize: 12.5 }} />
          <div style={{ maxHeight: 220, overflow: "auto", display: "flex", flexDirection: "column" }}>
            {treffer.slice(0, 120).map((z) => {
              const an = gewaehlt.includes(z.code);
              return (
                <label key={z.code} style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12.5, padding: "2px 0", cursor: "pointer",
                  paddingLeft: ABSCHNITT.test(z.code) ? 0 : Math.min(3, z.code.length - 7) * 10 }}>
                  <input type="checkbox" checked={an} disabled={!an && gewaehlt.length >= 12}
                    onChange={() => speichern(an ? gewaehlt.filter((c) => c !== z.code) : [...gewaehlt, z.code])} />
                  <span style={{ fontWeight: ABSCHNITT.test(z.code) ? 600 : 400 }}>{z.label}</span>
                  <span style={{ fontSize: 11, color: "var(--text-dim)" }}>{z.code.replace("WZ08-", "WZ ")}</span>
                </label>
              );
            })}
          </div>
          <span style={{ fontSize: 11.5, color: "var(--text-dim)" }}>
            Bis zu 12 Branchen. {darfAendern ? "Die Auswahl gilt für diesen Mandanten." : "Ohne Bearbeitungsrecht nur für diese Ansicht."}
          </span>
        </div>
      )}
      {reihe && zeilen.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={th}>Wirtschaftszweig</th>
                <th style={{ ...th, ...rechts }}>{stand ? monatText(stand) : "Letzter Monat"}</th>
                <th style={{ ...th, ...rechts }}>Letzte 12 Monate</th>
                <th style={{ ...th, ...rechts }}>Zu den 12 davor</th>
              </tr>
            </thead>
            <tbody>
              {zeilen.map((z) => (
                <tr key={z.code}>
                  <td style={td}>{z.label} <span style={{ fontSize: 11, color: "var(--text-dim)" }}>{z.code.replace("WZ08-", "WZ ")}</span></td>
                  <td style={{ ...td, ...rechts }}>{z.letzter == null ? "–" : nf0.format(z.letzter)}</td>
                  <td style={{ ...td, ...rechts }}>{z.jetzt == null ? "–" : nf0.format(z.jetzt)}</td>
                  <td style={{ ...td, ...rechts, color: farbe(z.aenderung), fontWeight: 600 }}>{z.aenderung == null ? "–" : `${nfP.format(z.aenderung * 100)} %`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {chart.length > 1 && (
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-main)", margin: "6px 0 2px 4px" }}>
            Insolvenzen in Deutschland je Monat und Ihre Ø Zahlungsdauer
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <ComposedChart data={chart} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="Monat" tick={achse} tickFormatter={monatText} minTickGap={24} />
              <YAxis yAxisId="i" tick={achse} width={48} tickFormatter={(v) => nf0.format(v)} />
              <YAxis yAxisId="t" orientation="right" tick={achse} width={36} tickFormatter={(v) => `${nf0.format(v)} T`} />
              <Tooltip labelFormatter={monatText}
                formatter={(v, n) => (v == null ? "–" : n === "Insolvenzen" ? nf0.format(v) : n === "Ø Zahlungsdauer" ? `${nf1.format(v)} Tage` : `${nf1.format(v)} %`)}
                contentStyle={{ background: "var(--bg-card)", border: "1px solid var(--border)", fontSize: 11.5 }} />
              <Legend wrapperStyle={{ fontSize: 11.5 }} />
              <Bar yAxisId="i" dataKey="Insolvenzen" fill="color-mix(in srgb, #a78bfa 45%, transparent)" />
              <Line yAxisId="t" dataKey="Zahldauer" name="Ø Zahlungsdauer" stroke="var(--accent)" strokeWidth={2} dot={false} connectNulls />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
      <span style={{ fontSize: 12, color: "var(--text-dim)", lineHeight: 1.5 }}>
        Beantragte Insolvenzverfahren von Unternehmen (eröffnet oder mangels Masse abgewiesen), nach dem Wirtschaftszweig des Schuldners.
        Rot: mehr als 5 % über dem Vorjahreszeitraum. Ihre Zahlungsdauer = Tage von Rechnung bis Zahlungseingang, nur bezahlte Rechnungen;
        die jüngsten zwei Monate fehlen, weil dort erst die schnellen Zahler erfasst sind. Die Statistik erscheint mit etwa drei Monaten Verzug.
      </span>
      <span style={{ fontSize: 11.5, color: "var(--text-dim)" }}>
        Quelle: {reihe?.quelle || "Statistisches Bundesamt (Destatis)"}, Tabellen 52411-0018/-0019{stand ? ` · Daten bis ${monatText(stand)}` : ""}
        {reihe?.hinweis ? ` · ${reihe.hinweis}` : ""} · es werden keine Kundendaten übertragen
      </span>
    </div>
  );
}
