/**
 * Branchenvergleich „Ich gegen meine Branche“: eigene Umsatzentwicklung neben dem Umsatzindex
 * des Handelszweigs (Eurostat, Deutschland, über den monstersuite-Datendienst).
 *
 * Verglichen werden Veränderungen zum Vorjahr, keine Niveaus: der Branchenindex (2021 = 100) und
 * der eigene Umsatz in Euro haben keine gemeinsame Skala, die Wachstumsraten schon. Um Zufälle
 * der Rechnungsstellung (eine Großlieferung im März statt April) zu glätten, zählt je Monat die
 * Summe der letzten drei Monate gegen dieselben drei Monate im Vorjahr – für beide Seiten gleich.
 *
 * Nominal: eigener Umsatz gegen NETTUR (Umsatz in jeweiligen Preisen).
 * Real:    eigener Umsatz geteilt durch den Preisindex des Mandanten (preisbereinigung.tsx)
 *          gegen VOL_SLS (Verkaufsvolumen). Ohne gewählten Preisindex nicht möglich.
 *
 * Branche je Mandant: /api/business-config/branche. Ohne Auswahl wird sie aus dem Preisindex
 * abgeleitet (WZ08-46494 → G464), sonst Großhandel gesamt.
 *
 * Konfiguration (widget.config):
 *   spalten: { monat: "Monat", wert: "Umsatz" } – Abfrage liefert einen Wert je Monat (≥ 27 Monate)
 */
import { useEffect, useMemo, useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Legend } from "recharts";
import api, { fehlerText } from "../../../api/client";
import { useAuth } from "../../../context/AuthContext";
import { monatText } from "./monat";
import { monatsFolge } from "./UmfeldWidget";
import { usePreisindex, bereinigen, PreisindexDialog } from "../preisbereinigung";

const FARBE_ICH = "var(--accent)";
const FARBE_BRANCHE = "#a78bfa";
const nf1 = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1, signDisplay: "exceptZero" });
const zahl = (x) => { const n = typeof x === "number" ? x : Number(String(x ?? "").replace(",", ".")); return Number.isFinite(n) ? n : null; };
const prozent = (v) => (v == null ? "–" : `${nf1.format(v * 100)} %`);

// ── Rechnung (rein) ──
/** Je Index i: Summe der Fenster i-f+1 … i geteilt durch dieselbe Summe zwölf Monate früher, minus 1. */
export function vorjahrGleitend(xs, fenster = 3) {
  const summe = (bis) => {
    if (bis - fenster + 1 < 0) return null;
    let s = 0;
    for (let i = bis - fenster + 1; i <= bis; i++) { if (xs[i] == null) return null; s += xs[i]; }
    return s;
  };
  return xs.map((_, i) => {
    const jetzt = summe(i), vorher = summe(i - 12);
    return jetzt != null && vorher != null && vorher > 0 ? jetzt / vorher - 1 : null;
  });
}

/** Vorschlag aus dem Preisindex: WZ08-46494 → G464 (falls im Katalog), WZ08-4773 → G477, sonst Handel gesamt. */
export function brancheAusPreisindex(pi, codes) {
  const r = pi?.region || "";
  const m = /^WZ08-(4[67])(\d)?/.exec(r);
  if (m) {
    const drei = `G${m[1]}${m[2] || ""}`, zwei = `G${m[1]}`;
    if (m[2] && codes.has(drei)) return drei;
    if (codes.has(zwei)) return zwei;
  }
  if (pi?.key === "preise_verbraucher" && codes.has("G4791")) return "G4791";
  return codes.has("G46") ? "G46" : null;
}

const monatMinus = (mo, n) => {
  const [j, m] = String(mo).split("-").map(Number);
  const d = new Date(j, m - 1 - n, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
};
let katalogCache = null;

export default function BranchenvergleichWidget({ widget, result, params = {}, projectId = null }) {
  const cfg = widget.config || {};
  const sp = { monat: "Monat", wert: "Umsatz", ...(cfg.spalten || {}) };
  const { user } = useAuth();
  const darfAendern = !user?.is_portal_only && projectId != null;

  const [katalog, setKatalog] = useState(null);
  const [katFehler, setKatFehler] = useState(null);
  const [gespeichert, setGespeichert] = useState(undefined);       // undefined = lädt, null = keine
  const [mandantName, setMandantName] = useState(null);
  const [lokal, setLokal] = useState(null);                        // Auswahl ohne Schreibrecht
  const [art, setArt] = useState("nominal");
  const [reihe, setReihe] = useState(null);
  const [fehler, setFehler] = useState(null);
  const [laedt, setLaedt] = useState(false);
  const [piDialog, setPiDialog] = useState(false);
  const pi = usePreisindex(projectId, true);

  useEffect(() => {
    let lebt = true;
    (katalogCache || (katalogCache = api.get("/api/umfeld/branchen/katalog").then((r) => r.data)
      .then((d) => { if (d.hinweis || !(d.branchen || []).length) katalogCache = null; return d; })
      .catch((e) => { katalogCache = null; throw e; })))
      .then((d) => { if (!lebt) return; setKatalog(d.branchen || []); setKatFehler(d.hinweis || null); })
      .catch((e) => lebt && setKatFehler(fehlerText(e)));
    return () => { lebt = false; };
  }, []);
  useEffect(() => {
    let lebt = true;
    const q = projectId != null ? `?project_id=${projectId}` : "";
    api.get(`/api/business-config/branche${q}`)
      .then(({ data }) => { if (!lebt) return; setGespeichert(data.auswahl || null); setMandantName(data.mandant_name || null); })
      .catch(() => lebt && setGespeichert(null));
    return () => { lebt = false; };
  }, [projectId, pi.auswahl?.region]);   // Mandantwechsel ändert auch den Preisindex → neu lesen

  const codes = useMemo(() => new Set((katalog || []).map((b) => b.code)), [katalog]);
  const vorschlag = katalog ? brancheAusPreisindex(pi.auswahl, codes) : null;
  const code = lokal || gespeichert?.code || vorschlag;
  const istVorschlag = !lokal && !gespeichert?.code && !!code;
  const label = (katalog || []).find((b) => b.code === code)?.label || gespeichert?.label || code || "";

  const waehlen = async (neu) => {
    if (!neu) return;
    if (!darfAendern) { setLokal(neu); return; }
    const lab = (katalog || []).find((b) => b.code === neu)?.label || "";
    try {
      const { data } = await api.put("/api/business-config/branche", { project_id: projectId, code: neu, label: lab });
      setGespeichert(data.auswahl); setLokal(null);
    } catch (e) { setFehler(fehlerText(e)); setLokal(neu); }
  };

  // Eigener Umsatz: lückenlose Monatsfolge, laufender Monat fällt weg (unvollständig)
  const eigen = useMemo(() => {
    const jetzt = new Date().toISOString().slice(0, 7);
    const m = new Map();
    for (const r of result?.rows || []) {
      const mo = String(r[sp.monat] ?? "").slice(0, 7);
      if (!/^\d{4}-\d{2}$/.test(mo) || mo >= jetzt) continue;
      m.set(mo, (m.get(mo) || 0) + (zahl(r[sp.wert]) || 0));
    }
    const ks = [...m.keys()].sort();
    return monatsFolge(ks[0], ks[ks.length - 1]).map((mo) => [mo, m.get(mo) || 0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result]);
  const von = eigen[0]?.[0], bis = eigen[eigen.length - 1]?.[0];

  const groesse = art === "real" ? "umsatz_handel_real" : "umsatz_handel";
  useEffect(() => {
    if (!code || !von || !bis) return;
    let lebt = true;
    setLaedt(true); setFehler(null);
    api.post("/api/umfeld/reihen", { groessen: [groesse], regionen: [code], von, bis })
      .then(({ data }) => lebt && setReihe(data.reihen?.[0] || null))
      .catch((e) => lebt && setFehler(fehlerText(e)))
      .finally(() => lebt && setLaedt(false));
    return () => { lebt = false; };
  }, [code, groesse, von, bis]);

  const monate = eigen.map(([m]) => m);
  const ichRoh = eigen.map(([, v]) => v);
  const realOk = art !== "real" || !!pi.werte;
  const ich = art === "real" ? (pi.werte ? bereinigen(monate, ichRoh, pi.werte).werte : monate.map(() => null)) : ichRoh;
  const brancheWerte = reihe?.werte?.[code] || {};
  const branche = monate.map((m) => brancheWerte[m] ?? null);
  const yIch = useMemo(() => vorjahrGleitend(ich), [JSON.stringify(ich)]); // eslint-disable-line react-hooks/exhaustive-deps
  const yBr = useMemo(() => vorjahrGleitend(branche), [JSON.stringify(branche)]); // eslint-disable-line react-hooks/exhaustive-deps
  const daten = monate.map((m, i) => ({ Monat: m, Ich: yIch[i] == null ? null : yIch[i] * 100, Branche: yBr[i] == null ? null : yBr[i] * 100 }));

  // Angezeigt wird der gewählte Zeitraum; ist er kürzer als 6 Monate, die letzten 24 als Verlauf.
  const selVon = String(params?.von || "").slice(0, 7), selBis = String(params?.bis || "").slice(0, 7);
  let anzeige = daten.filter((d) => (!selVon || d.Monat >= selVon) && (!selBis || d.Monat <= selBis) && (d.Ich != null || d.Branche != null));
  const zuKurz = anzeige.length < 6;
  if (zuKurz) anzeige = daten.filter((d) => d.Ich != null || d.Branche != null).slice(-24);

  // Fazit: letzte 12 Monate mit Branchenwert gegen die 12 davor
  const fazit = useMemo(() => {
    let ende = -1;
    for (let i = monate.length - 1; i >= 0; i--) if (branche[i] != null && ich[i] != null) { ende = i; break; }
    if (ende < 23) return null;
    const s = (xs, a, b) => { let t = 0; for (let i = a; i <= b; i++) { if (xs[i] == null) return null; t += xs[i]; } return t; };
    const i1 = s(ich, ende - 11, ende), i0 = s(ich, ende - 23, ende - 12);
    const b1 = s(branche, ende - 11, ende), b0 = s(branche, ende - 23, ende - 12);
    if (!i1 || !i0 || !b1 || !b0) return null;
    const imZeitraum = anzeige.map((d) => d.Monat);
    const vergleichbar = daten.filter((d) => imZeitraum.includes(d.Monat) && d.Ich != null && d.Branche != null);
    return { ende: monate[ende], ich: i1 / i0 - 1, branche: b1 / b0 - 1,
      besser: vergleichbar.filter((d) => d.Ich > d.Branche).length, von: vergleichbar.length };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(ich), JSON.stringify(branche), anzeige.length]);

  const auswahl = { padding: "5px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg-elevated)",
    color: "var(--text-main)", fontSize: 12.5 };
  const knopf = (aktiv) => ({ padding: "4px 10px", fontSize: 12, cursor: "pointer", border: "1px solid var(--border)",
    background: aktiv ? "color-mix(in srgb, var(--accent) 18%, transparent)" : "transparent",
    color: aktiv ? "var(--text-bright)" : "var(--text-main)" });
  const achse = { fontSize: 11, fill: "var(--text-dim)" };
  const gruppen = [
    { name: "Großhandel", f: (c) => c.startsWith("G46") },
    { name: "Einzelhandel", f: (c) => c.startsWith("G47") },
    { name: "Kfz-Handel", f: (c) => c.startsWith("G45") },
    { name: "Handel gesamt", f: (c) => c === "G" },
  ];
  const kurzLabel = label.length > 70 ? label.slice(0, 68) + "…" : label;
  const hinweis = ({ active, payload, label: mo }) => {
    if (!active || !payload?.length) return null;
    const d = payload[0].payload;
    return (
      <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 6, padding: "7px 10px", fontSize: 11.5 }}>
        <div style={{ fontWeight: 600, color: "var(--text-bright)", marginBottom: 3 }}>
          {monatText(monatMinus(mo, 2))} – {monatText(mo)} gegen Vorjahr
        </div>
        <div><span style={{ color: FARBE_ICH }}>■</span> Ihr Umsatz {prozent(d.Ich == null ? null : d.Ich / 100)}</div>
        <div><span style={{ color: FARBE_BRANCHE }}>■</span> Branche {prozent(d.Branche == null ? null : d.Branche / 100)}</div>
      </div>
    );
  };

  if (!(result?.rows || []).length) return <p style={{ padding: 16, margin: 0, color: "var(--text-dim)", fontSize: 13 }}>Keine Umsätze für den Vergleich.</p>;

  return (
    <div style={{ padding: "12px 16px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
        <select value={code || ""} onChange={(e) => waehlen(e.target.value)} style={{ ...auswahl, maxWidth: 420 }} aria-label="Branche"
          disabled={!katalog?.length}>
          {!code && <option value="">Branche wählen…</option>}
          {gruppen.map((g) => {
            const xs = (katalog || []).filter((b) => g.f(b.code));
            return xs.length ? (
              <optgroup key={g.name} label={g.name}>
                {xs.map((b) => <option key={b.code} value={b.code}>{b.label}</option>)}
              </optgroup>
            ) : null;
          })}
        </select>
        <div style={{ display: "inline-flex", borderRadius: 6, overflow: "hidden" }} role="group" aria-label="Nominal oder real">
          <button onClick={() => setArt("nominal")} style={{ ...knopf(art === "nominal"), borderRadius: "6px 0 0 6px" }}
            title="Umsatz in Euro, wie er in den Rechnungen steht">nominal</button>
          <button onClick={() => setArt("real")} style={{ ...knopf(art === "real"), borderRadius: "0 6px 6px 0", borderLeft: "none" }}
            title="Preissteigerung herausgerechnet: verkaufte Menge statt Euro">real</button>
        </div>
        <span style={{ fontSize: 12, color: "var(--text-dim)" }}>
          {istVorschlag ? "Vorschlag" + (pi.auswahl ? " aus dem Preisindex" : "") + (darfAendern ? " – zum Festlegen auswählen" : "") : ""}
          {gespeichert?.code && mandantName ? `gilt für ${mandantName}` : ""}
        </span>
      </div>

      {katFehler && <p style={{ margin: 0, fontSize: 12.5, color: "var(--text-dim)" }}>{katFehler}</p>}
      {fehler && <p style={{ margin: 0, fontSize: 12.5, color: "var(--err-soft, var(--err))" }}>Branchendaten nicht verfügbar: {fehler}</p>}
      {!realOk && (
        <div style={{ fontSize: 12.5, color: "var(--text-main)", border: "1px dashed var(--border)", borderRadius: 8, padding: "8px 12px" }}>
          Für den realen Vergleich muss die Preissteigerung aus Ihrem Umsatz herausgerechnet werden – dafür braucht das Cockpit
          den Preisindex Ihrer Branche.{" "}
          {darfAendern && <button onClick={() => setPiDialog(true)} style={{ ...knopf(false), borderRadius: 6 }}>Preisindex wählen</button>}
        </div>
      )}

      <div>
        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-main)", margin: "2px 0 2px 4px" }}>
          Veränderung zum Vorjahr in %, je Monat die letzten 3 Monate gegen dieselben 3 im Vorjahr{laedt ? " – lädt…" : ""}
        </div>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={anzeige} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(127,127,127,0.12)" />
            <XAxis dataKey="Monat" tick={achse} minTickGap={18} tickFormatter={monatText} />
            <YAxis tick={achse} width={52} tickFormatter={(v) => `${nf1.format(v)} %`} />
            <ReferenceLine y={0} stroke="var(--text-dim)" strokeOpacity={0.6} />
            <Tooltip content={hinweis} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Line dataKey="Ich" name={`Ihr Umsatz${art === "real" ? " (real)" : ""}`} stroke={FARBE_ICH} strokeWidth={2} dot={false}
              activeDot={{ r: 4 }} isAnimationActive={false} connectNulls />
            <Line dataKey="Branche" name={`Branche${art === "real" ? " (real)" : ""}: ${kurzLabel}`} stroke={FARBE_BRANCHE} strokeWidth={2}
              dot={false} activeDot={{ r: 4 }} isAnimationActive={false} connectNulls />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: "10px 12px", fontSize: 13, lineHeight: 1.5,
        display: "flex", flexDirection: "column", gap: 4, color: "var(--text-main)" }}>
        <strong style={{ fontSize: 12, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: ".05em" }}>
          Ich gegen meine Branche{fazit ? ` · 12 Monate bis ${monatText(fazit.ende)}` : ""}
        </strong>
        {fazit ? (
          <>
            <span>
              Ihr Umsatz{art === "real" ? " (real)" : ""}: <b style={{ color: "var(--text-bright)" }}>{prozent(fazit.ich)}</b> zum Vorjahr,
              Branche: <b style={{ color: "var(--text-bright)" }}>{prozent(fazit.branche)}</b> –{" "}
              <b style={{ color: fazit.ich >= fazit.branche ? "var(--ok)" : "var(--err)" }}>
                {nf1.format((fazit.ich - fazit.branche) * 100).replace(/^\+/, "")} Prozentpunkte {fazit.ich >= fazit.branche ? "besser" : "schlechter"}
              </b> als die Branche.
            </span>
            {fazit.von > 0 && (
              <span>Im gezeigten Zeitraum lagen Sie in {fazit.besser} von {fazit.von} Monaten über der Branchenentwicklung.</span>
            )}
          </>
        ) : (
          <span style={{ color: "var(--text-dim)" }}>
            {code ? "Für das Fazit fehlen noch Werte: es braucht 24 Monate eigenen Umsatz, für die auch Branchenwerte vorliegen." : "Bitte eine Branche wählen."}
          </span>
        )}
        <span style={{ fontSize: 12, color: "var(--text-dim)" }}>
          Verglichen werden Wachstumsraten, nicht Größen: die Branche ist ein Index aller deutschen Unternehmen dieses Handelszweigs.
          Ihr Umsatz = Rechnungen netto ohne Stornos (gefiltert nach Plattform, falls gewählt).
          {art === "real" ? " Real: Ihr Umsatz geteilt durch den gewählten Preisindex, die Branche als Verkaufsvolumen." : ""}
          {" "}Die Branchenwerte erscheinen etwa zwei Monate nach Monatsende.
        </span>
      </div>

      {(reihe || katalog) && (
        <span style={{ fontSize: 11.5, color: "var(--text-dim)" }}>
          Quelle: {reihe?.quelle || "Eurostat"}, Index 2021 = 100, nicht saisonbereinigt
          {reihe?.werte?.[code] && Object.keys(reihe.werte[code]).length
            ? ` · Branche bis ${monatText(Object.keys(reihe.werte[code]).sort().pop())}` : ""}
          {reihe?.hinweis ? ` · ${reihe.hinweis}` : ""}
        </span>
      )}
      {piDialog && (
        <PreisindexDialog projectId={projectId} aktuell={pi.auswahl} mandantName={pi.mandantName} onClose={() => setPiDialog(false)} />
      )}
    </div>
  );
}
