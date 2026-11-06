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
 * Kartenumrisse: Natural Earth (gemeinfrei) – Welt aus world-atlas (1:50 Mio.), Bundesländer
 * aus admin-1 1:10 Mio., vereinfacht (src/assets/geo). Beides wird erst geladen, wenn eine Karte
 * erscheint, und liegt in der App: keine Kartendienste, keine Daten nach außen.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { geoPath, geoNaturalEarth1, geoConicConformal, geoMercator } from "d3-geo";
import { feature } from "topojson-client";

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
    return m;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result, widget]);

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
      text: i === 0 ? (n === 1 ? "mit Wert" : `bis ${kurz(grenzen[0], einheit)}`) : i === n - 1 ? `ab ${kurz(grenzen[i - 1], einheit)}` : `${kurz(grenzen[i - 1], einheit)} – ${kurz(grenzen[i], einheit)}`,
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
        <div ref={flaecheRef} style={{ position: "relative", height: hoeheKarte, overflow: "hidden", borderRadius: 8,
          background: "color-mix(in srgb, var(--bg-elevated) 45%, transparent)" }}
          onMouseLeave={() => { setHover(null); setTipp(null); }}>
          {fehler && <p style={{ padding: 16, color: "var(--err-soft)", fontSize: 12 }}>Karte konnte nicht geladen werden: {fehler}</p>}
          {!geo && !fehler && <p style={{ padding: 16, color: "var(--text-dim)", fontSize: 12 }}>Karte lädt…</p>}
          {geo && (
            <svg width={breite} height={hoeheKarte} role="img"
              aria-label={`${widget.label || "Karte"}: ${rangliste.slice(0, 5).map((d) => `${d.name} ${fmt(d.v, einheit)}`).join(", ")}`}>
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
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 14, fontWeight: 600, color: "var(--text-bright)" }}>{fmt(hd.v, einheit)}</div>
                {summe > 0 && hd.v > 0 && <div style={{ color: "var(--text-dim)" }}>{nf1.format((hd.v / summe) * 100)} % vom Gesamt</div>}
                {hd.p != null && (
                  <div style={{ color: "var(--text-dim)" }}>
                    Vorjahr {fmt(hd.p, einheit)}
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
        </div>
      </div>

      {/* Rangliste = Textansicht der Karte; Überfahren hebt das Gebiet hervor */}
      <div style={{ flex: "1 1 220px", minWidth: 200, display: "flex", flexDirection: "column", gap: 2, maxHeight: hoeheKarte + 60, overflow: "auto" }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: ".06em", padding: "2px 0 6px" }}>
          Rangfolge
        </div>
        {rangliste.map((d) => {
          const anteil = summe > 0 && d.v > 0 ? d.v / summe : 0;
          const aktiv = hover === d.key;
          return (
            <div key={d.key || d.name} onMouseEnter={() => { setHover(d.key); setTipp(null); }} onMouseLeave={() => setHover(null)}
              style={{ padding: "5px 8px", borderRadius: 6, fontSize: 12.5, cursor: "default",
                background: aktiv ? "color-mix(in srgb, var(--accent) 10%, transparent)" : "transparent" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <span style={{ color: "var(--text-main)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{d.name}</span>
                <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-bright)", whiteSpace: "nowrap" }}>{kurz(d.v, einheit)}</span>
              </div>
              <div style={{ height: 3, marginTop: 4, borderRadius: 2, background: "var(--bg-elevated)" }}>
                <div style={{ height: 3, width: `${Math.max(anteil > 0 ? 1.5 : 0, anteil * 100)}%`, borderRadius: 2, background: "var(--accent)" }} />
              </div>
            </div>
          );
        })}
        {nichtAufKarte.length > 0 && (
          <p style={{ margin: "8px 0 0", fontSize: 11.5, color: "var(--text-dim)", lineHeight: 1.45 }}>
            Nicht auf der Karte: {nichtAufKarte.map((d) => `${d.name} (${kurz(d.v, einheit)})`).join(", ")}
          </p>
        )}
      </div>
    </div>
  );
}
