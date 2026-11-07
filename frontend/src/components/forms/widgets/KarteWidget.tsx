/**
 * Karten-Widget: Werte je Land oder Bundesland als eingefärbte Karte (Choroplethe).
 *
 * Eine Farbe, hell → dunkel = wenig → viel (fünf Stufen nach Quantilen), aus der Akzentfarbe
 * gemischt – passt so zu allen Farbschemata, auch dunklen. Länder ohne Wert bleiben neutral.
 * Neben der Karte die Rangliste als Textansicht; Überfahren zeigt Wert, Anteil und Vorjahr.
 *
 * Konfiguration (widget.config), Werte aus results[widget.action_id]:
 *   karte:   "welt" (Länder, Schlüssel = ISO-3166-Nummer) | "deutschland" (Bundesländer, Schlüssel = Name)
 *   spalten: { schluessel: "IsoNum" | "Bundesland", name: "Land", wert: "Umsatz", vj?: "UmsatzVJ" }
 *   einheit: "eur" (Vorgabe) | "anzahl"
 *   zusatz:  [{ spalte, label, einheit? }]   – weitere Zeilen im Hinweisfenster
 *   ausschnitt: "europa" (Vorgabe) | "welt"  – nur bei karte = "welt", umschaltbar
 *   hoehe:   460
 *
 * Deutschlandkarte mit Euro-Werten: Umschalter „Bezug“ – Gesamt, je 1.000 Einwohner oder je 1 Mio. €
 * verfügbares Einkommen der Haushalte („Kaufkraft“), dazu ein Index (Ø Deutschland = 100). Einwohner und
 * Einkommen je Bundesland kommen von Destatis über den monstersuite-Datendienst (/api/umfeld/strukturdaten),
 * erst wenn jemand umschaltet; es gehen keine Kundendaten hinaus. Die Wahl merkt sich der Browser je Widget.
 *
 * Kartenumrisse: Natural Earth (gemeinfrei) – Welt aus world-atlas (1:50 Mio.), Bundesländer
 * aus admin-1 1:10 Mio., vereinfacht (src/assets/geo). Beides wird erst geladen, wenn eine Karte
 * erscheint, und liegt in der App: keine Kartendienste, keine Daten nach außen.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { geoPath, geoNaturalEarth1, geoConicConformal, geoMercator } from "d3-geo";
import { feature } from "topojson-client";
import api, { fehlerText } from "../../../api/client";

const nf0 = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const zahl = (x) => { const n = typeof x === "number" ? x : Number(String(x ?? "").replace(",", ".")); return Number.isFinite(n) ? n : null; };
const fmt = (v, einheit = "eur") => v == null ? "–" : nf0.format(Math.round(v)) + (einheit === "anzahl" ? "" : " €");
const kurz = (v, einheit = "eur") => {
  if (v == null) return "–";
  const e = einheit === "anzahl" ? "" : " €";
  const a = Math.abs(v);
  if (a >= 1e6) return nf1.format(v / 1e6) + " Mio." + e;
  if (a >= 1e4) return nf0.format(v / 1e3) + " T" + (e ? "€" : "");
  return nf0.format(v) + e;
};

// Fünf Stufen einer Farbe; die erste noch deutlich vom „kein Wert“-Grau unterscheidbar.
const STUFEN = [18, 34, 52, 72, 92];
const stufeFarbe = (i) => `color-mix(in srgb, var(--accent) ${STUFEN[i]}%, var(--bg-card))`;
const OHNE = "var(--bg-elevated)";

const nf2 = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const BEZUG = {
  gesamt:    { text: "Gesamt" },
  einwohner: { text: "je Einwohner", einheit: "€ je 1.000 Einwohner", kurz: "€/1.000 EW" },
  kaufkraft: { text: "je Kaufkraft", einheit: "€ je 1 Mio. € Haushaltseinkommen", kurz: "€/Mio. € Eink." },
};
let strukturCache: Promise<any> | null = null;
const ladeStruktur = () => (strukturCache || (strukturCache = api.get("/api/umfeld/strukturdaten").then((r) => {
  if (r.data?.hinweis) strukturCache = null;           // „wird geladen“ nicht festhalten
  return r.data;
}).catch((e) => { strukturCache = null; throw e; })));
const bezugLesen = (id) => { try { const v = localStorage.getItem(`dm-karte-bezug-${id}`); return v && BEZUG[v] ? v : "gesamt"; } catch { return "gesamt"; } };
const bezugSchreiben = (id, v) => { try { localStorage.setItem(`dm-karte-bezug-${id}`, v); } catch { /* ohne Speicher */ } };

/** Werte je Bundesland auf Einwohner bzw. Einkommen beziehen; Index = Wert / Bundesschnitt × 100.
 *  Der Schnitt zählt alle 16 Länder, auch solche ohne Umsatz. */
export function aufBezug(eintraege, laender, bezug) {
  const nenner = (k) => {
    const l = laender?.[k]; if (!l) return null;
    return bezug === "einwohner" ? (l.einwohner ? l.einwohner / 1000 : null) : (l.einkommen_mio ? l.einkommen_mio : null);
  };
  let sv = 0, sn = 0;
  for (const k of Object.keys(laender || {})) { const n = nenner(k); if (n) sn += n; }
  for (const d of eintraege) if (d.v > 0 && nenner(d.key)) sv += d.v;
  const schnitt = sn > 0 ? sv / sn : null;
  return eintraege.map((d) => {
    const n = nenner(d.key);
    if (!n) return { ...d, v: null, p: null, roh: d.v, index: null };
    const v = d.v == null ? null : d.v / n;
    return { ...d, v, p: d.p == null ? null : d.p / n, roh: d.v, index: v != null && schnitt ? (v / schnitt) * 100 : null };
  });
}

// Geometrien einmal je Sitzung laden (eigene Chunks, nur wenn eine Karte gezeigt wird).
const cache: Record<string, Promise<any>> = {};
function ladeGeometrie(karte) {
  if (!cache[karte]) {
    cache[karte] = karte === "deutschland"
      ? import("../../../assets/geo/de_bundeslaender.json").then((m) => (m.default || m).features)
      : import("world-atlas/countries-50m.json").then((m) => {
          const topo = m.default || m;
          // Antarktis (010) frisst auf der Weltkarte nur Platz.
          return feature(topo, topo.objects.countries).features.filter((f) => String(f.id) !== "010");
        });
  }
  return cache[karte];
}

// Europa-Ausschnitt: von Portugal/Island bis zur Ostgrenze der EU, Nordkap bis Kreta.
const EUROPA = { type: "Feature", geometry: { type: "Polygon", coordinates: [[[-11, 34], [-11, 70.5], [34, 70.5], [34, 34], [-11, 34]]] } };

export default function KarteWidget({ widget, result }) {
  const cfg = widget.config || {};
  const karte = cfg.karte === "deutschland" ? "deutschland" : "welt";
  const sp = { schluessel: karte === "deutschland" ? "Bundesland" : "IsoNum", name: karte === "deutschland" ? "Bundesland" : "Land",
    wert: "Umsatz", vj: null, ...(cfg.spalten || {}) };
  const einheit = cfg.einheit || "eur";
  const hoehe = Number(cfg.hoehe) || 460;
  const [ausschnitt, setAusschnitt] = useState(cfg.ausschnitt === "welt" ? "welt" : "europa");
  const [geo, setGeo] = useState(null);
  const [fehler, setFehler] = useState(null);
  const [hover, setHover] = useState(null);       // Schlüssel des überfahrenen Gebiets
  const [tipp, setTipp] = useState(null);         // {x, y} relativ zur Kartenfläche
  const flaecheRef = useRef(null);
  const [breite, setBreite] = useState(640);
  const mitBezug = karte === "deutschland" && einheit !== "anzahl";
  const [bezug, setBezugRoh] = useState(() => (mitBezug ? bezugLesen(widget.id) : "gesamt"));
  const setBezug = (b) => { setBezugRoh(b); bezugSchreiben(widget.id, b); };
  const [struktur, setStruktur] = useState(null);
  const [strukturFehler, setStrukturFehler] = useState(null);
  useEffect(() => {
    if (bezug === "gesamt" || struktur) return;
    let lebt = true;
    ladeStruktur().then((d) => { if (!lebt) return; if (d?.hinweis && !Object.values(d.laender || {}).some((l: any) => l.einwohner)) setStrukturFehler(d.hinweis); else setStruktur(d); })
      .catch((e) => lebt && setStrukturFehler(fehlerText(e)));
    return () => { lebt = false; };
  }, [bezug, struktur]);
  const bezogen = bezug !== "gesamt" && !!struktur;

  useEffect(() => {
    let lebt = true;
    ladeGeometrie(karte).then((g) => lebt && setGeo(g)).catch((e) => lebt && setFehler(String(e?.message || e)));
    return () => { lebt = false; };
  }, [karte]);

  useEffect(() => {
    const el = flaecheRef.current; if (!el) return;
    const ro = new ResizeObserver(([e]) => setBreite(Math.max(280, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Schlüssel vereinheitlichen: ISO-Nummern dreistellig wie im Atlas („40“ → „040“).
  const norm = (k) => {
    if (k == null) return "";
    const s = String(k).trim();
    return karte === "welt" && /^\d+$/.test(s) ? s.padStart(3, "0") : s;
  };

  const daten = useMemo(() => {
    const m = new Map();
    for (const r of result?.rows || []) {
      const k = norm(r[sp.schluessel]);
      const v = zahl(r[sp.wert]);
      if (!k && v == null) continue;
      m.set(k || `__${r[sp.name]}`, { key: k, name: r[sp.name] ?? k, v, p: sp.vj ? zahl(r[sp.vj]) : null, row: r });
    }
    if (!bezogen) return m;
    return new Map(aufBezug([...m.values()], struktur.laender, bezug).map((d) => [d.key || `__${d.name}`, d]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result, widget, bezogen, bezug, struktur]);
  // Bezogene Werte sind klein (Euro je 1.000 Einwohner) – eigene Formate
  const fmtW = (v) => (!bezogen ? fmt(v, einheit) : v == null ? "–" : `${v < 100 ? nf2.format(v) : nf0.format(v)} €`);
  const kurzW = (v) => (!bezogen ? kurz(v, einheit) : v == null ? "–" : v < 100 ? nf2.format(v) : nf0.format(v));

  const summe = useMemo(() => [...daten.values()].reduce((a, d) => a + (d.v > 0 ? d.v : 0), 0), [daten]);
  const geoKeys = useMemo(() => new Set((geo || []).map((f) => norm(karte === "welt" ? f.id : f.properties?.id))),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [geo]);

  // Stufen nach Quantilen der positiven Werte, die auf der Karte liegen.
  const grenzen = useMemo(() => {
    const vs = [...daten.values()].filter((d) => d.v > 0 && geoKeys.has(d.key)).map((d) => d.v).sort((a, b) => a - b);
    if (!vs.length) return [];
    const n = Math.min(STUFEN.length, vs.length);
    const g = [];
    for (let i = 1; i < n; i++) g.push(vs[Math.floor((i * vs.length) / n)]);
    return [...new Set(g)];
  }, [daten, geoKeys]);
  const stufe = (v) => { let i = 0; while (i < grenzen.length && v >= grenzen[i]) i++; return i + (STUFEN.length - 1 - grenzen.length); };
  const farbe = (k) => { const d = daten.get(k); return d && d.v > 0 ? stufeFarbe(stufe(d.v)) : OHNE; };

  const hoeheKarte = hoehe;
  const pfade = useMemo(() => {
    if (!geo) return [];
    const ext: [[number, number], [number, number]] = [[8, 8], [breite - 8, hoeheKarte - 8]];
    let proj;
    if (karte === "deutschland") proj = geoMercator().fitExtent(ext, { type: "FeatureCollection", features: geo });
    else if (ausschnitt === "europa") proj = geoConicConformal().parallels([35, 65]).rotate([-12, 0]).fitExtent(ext, EUROPA);
    else proj = geoNaturalEarth1().fitExtent(ext, { type: "Sphere" });
    const pfad = geoPath(proj);
    return geo.map((f) => ({ key: norm(karte === "welt" ? f.id : f.properties?.id), name: f.properties?.name, d: pfad(f) }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geo, breite, hoeheKarte, karte, ausschnitt]);

  const rangliste = useMemo(() => [...daten.values()].filter((d) => d.v != null).sort((a, b) => (b.v || 0) - (a.v || 0)), [daten]);
  const nichtAufKarte = geo ? rangliste.filter((d) => !geoKeys.has(d.key) && d.v) : [];

  const bewegen = (e, key) => {
    const r = flaecheRef.current?.getBoundingClientRect(); if (!r) return;
    setHover(key); setTipp({ x: e.clientX - r.left, y: e.clientY - r.top });
  };

  if (result?.error) return <p style={{ padding: 16, color: "var(--err-soft)", fontSize: 12 }}>{result.error}</p>;
  if (!(result?.rows || []).length) return <p style={{ padding: 16, margin: 0, color: "var(--text-dim)", fontSize: 13 }}>Für den Zeitraum gibt es keine Werte.</p>;

  const hd = hover ? daten.get(hover) : null;
  const hName = hd?.name || pfade.find((p) => p.key === hover)?.name || hover;
  const legende = (() => {
    const n = grenzen.length + 1, ab = STUFEN.length - n;
    return Array.from({ length: n }, (_, i) => ({
      farbe: stufeFarbe(ab + i),
      text: i === 0 ? (n === 1 ? "mit Wert" : `bis ${kurzW(grenzen[0])}`) : i === n - 1 ? `ab ${kurzW(grenzen[i - 1])}` : `${kurzW(grenzen[i - 1])} – ${kurzW(grenzen[i])}`,
    }));
  })();

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 16, padding: "12px 16px 16px" }}>
      <div style={{ flex: "3 1 420px", minWidth: 0, display: "flex", flexDirection: "column", gap: 8 }}>
        {karte === "welt" && (
          <div role="group" aria-label="Ausschnitt" style={{ display: "flex", gap: 6 }}>
            {[["europa", "Europa"], ["welt", "Welt"]].map(([a, t]) => (
              <button key={a} onClick={() => setAusschnitt(a)} aria-pressed={ausschnitt === a}
                style={{ padding: "3px 11px", borderRadius: 999, fontSize: 12, cursor: "pointer",
                  border: `1px solid ${ausschnitt === a ? "var(--accent)" : "var(--border)"}`,
                  background: ausschnitt === a ? "color-mix(in srgb, var(--accent) 12%, transparent)" : "transparent",
                  color: ausschnitt === a ? "var(--accent)" : "var(--text-main)", fontWeight: ausschnitt === a ? 600 : 500 }}>{t}</button>
            ))}
          </div>
        )}
        {mitBezug && (
          <div role="group" aria-label="Bezug" style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
            {Object.entries(BEZUG).map(([b, { text }]) => (
              <button key={b} onClick={() => setBezug(b)} aria-pressed={bezug === b}
                title={b === "gesamt" ? "Absolute Werte" : `Wert ${BEZUG[b].einheit} – zeigt, wo Sie gemessen an der Größe des Landes stark oder schwach sind`}
                style={{ padding: "3px 11px", borderRadius: 999, fontSize: 12, cursor: "pointer",
                  border: `1px solid ${bezug === b ? "var(--accent)" : "var(--border)"}`,
                  background: bezug === b ? "color-mix(in srgb, var(--accent) 12%, transparent)" : "transparent",
                  color: bezug === b ? "var(--accent)" : "var(--text-main)", fontWeight: bezug === b ? 600 : 500 }}>{text}</button>
            ))}
            {bezug !== "gesamt" && !struktur && !strukturFehler && <span style={{ fontSize: 11.5, color: "var(--text-dim)" }}>Einwohnerdaten laden…</span>}
            {strukturFehler && bezug !== "gesamt" && <span style={{ fontSize: 11.5, color: "var(--err-soft, var(--err))" }}>Bezugsdaten nicht verfügbar: {strukturFehler}</span>}
          </div>
        )}
        <div ref={flaecheRef} style={{ position: "relative", height: hoeheKarte, overflow: "hidden", borderRadius: 8,
          background: "color-mix(in srgb, var(--bg-elevated) 45%, transparent)" }}
          onMouseLeave={() => { setHover(null); setTipp(null); }}>
          {fehler && <p style={{ padding: 16, color: "var(--err-soft)", fontSize: 12 }}>Karte konnte nicht geladen werden: {fehler}</p>}
          {!geo && !fehler && <p style={{ padding: 16, color: "var(--text-dim)", fontSize: 12 }}>Karte lädt…</p>}
          {geo && (
            <svg width={breite} height={hoeheKarte} role="img"
              aria-label={`${widget.label || "Karte"}: ${rangliste.slice(0, 5).map((d) => `${d.name} ${fmtW(d.v)}`).join(", ")}`}>
              {pfade.map((p) => p.d && (
                <path key={p.key || p.name} d={p.d} fill={farbe(p.key)}
                  stroke={hover === p.key ? "var(--text-bright)" : "var(--bg-card)"} strokeWidth={hover === p.key ? 1.6 : 0.7}
                  strokeLinejoin="round" style={{ cursor: daten.has(p.key) ? "pointer" : "default", transition: "fill .15s" }}
                  onMouseMove={(e) => bewegen(e, p.key)} />
              ))}
              {/* überfahrenes Gebiet nach vorn, damit der Rand nicht verdeckt wird */}
              {hover && pfade.filter((p) => p.key === hover && p.d).map((p) => (
                <path key="hl" d={p.d} fill="none" stroke="var(--text-bright)" strokeWidth={1.6} pointerEvents="none" />
              ))}
            </svg>
          )}
          {hover && tipp && (
            <div role="tooltip" style={{ position: "absolute", left: Math.min(tipp.x + 14, breite - 220), top: Math.max(8, tipp.y - 12),
              width: 206, pointerEvents: "none", background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 8,
              boxShadow: "0 6px 20px rgba(0,0,0,.18)", padding: "9px 11px", fontSize: 12, color: "var(--text-main)", zIndex: 2 }}>
              <div style={{ fontWeight: 650, color: "var(--text-bright)", marginBottom: 4 }}>{hName}</div>
              {hd && hd.v != null ? (<>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 14, fontWeight: 600, color: "var(--text-bright)" }}>{fmtW(hd.v)}</div>
                {bezogen && <div style={{ color: "var(--text-dim)", fontSize: 11 }}>{BEZUG[bezug].einheit}</div>}
                {bezogen && hd.index != null && (
                  <div style={{ color: "var(--text-dim)" }}>Index <b style={{ color: hd.index >= 100 ? "var(--ok)" : "var(--text-main)" }}>{nf0.format(hd.index)}</b> (Ø Deutschland = 100)</div>
                )}
                {bezogen && hd.roh != null && <div style={{ color: "var(--text-dim)" }}>gesamt {fmt(hd.roh, einheit)}</div>}
                {!bezogen && summe > 0 && hd.v > 0 && <div style={{ color: "var(--text-dim)" }}>{nf1.format((hd.v / summe) * 100)} % vom Gesamt</div>}
                {hd.p != null && (
                  <div style={{ color: "var(--text-dim)" }}>
                    Vorjahr {fmtW(hd.p)}
                    {hd.p !== 0 && (
                      <span style={{ marginLeft: 6, color: hd.v >= hd.p ? "var(--ok)" : "var(--err)" }}>
                        {hd.v >= hd.p ? "▲" : "▼"} {nf1.format(Math.abs((hd.v - hd.p) / hd.p) * 100)} %
                      </span>
                    )}
                  </div>
                )}
                {(cfg.zusatz || []).map((z) => (
                  <div key={z.spalte} style={{ display: "flex", justifyContent: "space-between", color: "var(--text-dim)" }}>
                    <span>{z.label || z.spalte}</span>
                    <span style={{ color: "var(--text-main)" }}>{z.einheit === "eur" ? fmt(zahl(hd.row[z.spalte]), "eur")
                      : z.einheit === "prozent" ? `${nf1.format(zahl(hd.row[z.spalte]) ?? 0)} %` : nf0.format(zahl(hd.row[z.spalte]) ?? 0)}</span>
                  </div>
                ))}
              </>) : <div style={{ color: "var(--text-dim)" }}>keine Werte im Zeitraum</div>}
            </div>
          )}
        </div>
        <div aria-label="Legende" style={{ display: "flex", flexWrap: "wrap", gap: "6px 14px", alignItems: "center", fontSize: 11.5, color: "var(--text-dim)" }}>
          {legende.map((l, i) => (
            <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <span style={{ width: 16, height: 10, borderRadius: 2, background: l.farbe }} />{l.text}
            </span>
          ))}
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 16, height: 10, borderRadius: 2, background: OHNE, border: "1px solid var(--border)" }} />kein Wert
          </span>
          {bezogen && (
            <span style={{ flexBasis: "100%", fontSize: 11 }}>
              {BEZUG[bezug].einheit}. Quelle: Destatis, {bezug === "einwohner"
                ? `Bevölkerungsstand 31.12.${struktur.stand?.einwohner || ""}`
                : `verfügbares Einkommen der privaten Haushalte ${struktur.stand?.einkommen_mio || ""} (VGR der Länder)`} – Datenlizenz Deutschland 2.0
            </span>
          )}
        </div>
      </div>

      {/* Rangliste = Textansicht der Karte; Überfahren hebt das Gebiet hervor */}
      <div style={{ flex: "1 1 220px", minWidth: 200, display: "flex", flexDirection: "column", gap: 2, maxHeight: hoeheKarte + 60, overflow: "auto" }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: ".06em", padding: "2px 0 6px" }}>
          Rangfolge{bezogen ? ` · ${BEZUG[bezug].kurz}` : ""}
        </div>
        {rangliste.map((d) => {
          const maxV = rangliste[0]?.v || 0;
          const anteil = bezogen ? (maxV > 0 && d.v > 0 ? d.v / maxV : 0) : summe > 0 && d.v > 0 ? d.v / summe : 0;
          const aktiv = hover === d.key;
          return (
            <div key={d.key || d.name} onMouseEnter={() => { setHover(d.key); setTipp(null); }} onMouseLeave={() => setHover(null)}
              style={{ padding: "5px 8px", borderRadius: 6, fontSize: 12.5, cursor: "default",
                background: aktiv ? "color-mix(in srgb, var(--accent) 10%, transparent)" : "transparent" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <span style={{ color: "var(--text-main)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{d.name}</span>
                <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-bright)", whiteSpace: "nowrap" }}>{kurzW(d.v)}</span>
              </div>
              <div style={{ height: 3, marginTop: 4, borderRadius: 2, background: "var(--bg-elevated)" }}>
                <div style={{ height: 3, width: `${Math.max(anteil > 0 ? 1.5 : 0, anteil * 100)}%`, borderRadius: 2, background: "var(--accent)" }} />
              </div>
            </div>
          );
        })}
        {nichtAufKarte.length > 0 && (
          <p style={{ margin: "8px 0 0", fontSize: 11.5, color: "var(--text-dim)", lineHeight: 1.45 }}>
            Nicht auf der Karte: {nichtAufKarte.map((d) => `${d.name} (${kurzW(d.v)})`).join(", ")}
          </p>
        )}
      </div>
    </div>
  );
}
