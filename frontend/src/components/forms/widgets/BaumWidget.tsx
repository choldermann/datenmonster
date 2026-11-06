/**
 * Baum-Widget: ein Ergebnis als aufklappbarer Baum (Ein Cockpit mit Rubriken, Phase 2).
 *
 * Jede Ebene ergibt in Summe ihren Oberpunkt. Linienstärke = Anteil am Oberpunkt,
 * Farbe = besser/schlechter als im Vorjahr, gestrichelt = Zusatzinfo (zählt nicht mit).
 * Blätter öffnen rechts eine Seitenleiste mit der passenden Tabelle und Sprüngen in
 * Reiter dieses oder eines anderen Cockpits.
 *
 * Konfiguration (widget.config), Werte kommen aus results[widget.action_id] im Langformat:
 *   spalten:  { knoten: "Knoten", wert: "Wert", vj: "WertVJ" }
 *   verlauf:  { action_id, spalten: { knoten, monat, wert } }        – optional, für Sparklines
 *   wurzel:   { id, titel, untertitel, kinder: [...],
 *               zeilen: [{ label, wert | formel, quote?: true, hl?: true }] }
 *   knoten:   { <id>: { titel, untertitel, wert?: <Knoten-Schlüssel, Vorgabe = id>, formel?: "a - b",
 *                       gut?: "runter", kinder?: [...], ansichten?: { Label: [...] }, ansicht?,
 *                       zusatz?: [...], info?: true, einheit?: "eur" | "anzahl", beschreibung?,
 *                       tabelle?: { action_id, filter?: { spalte, wert } },
 *                       spruenge?: [{ label?, reiter, rubrik?, felder?, zeitraum? }],
 *                       hinweis?: { wert: <Schlüssel>, text: "{n} … ohne Kosten" } } }
 *   offen:    ["ergebnis", …]   – beim ersten Öffnen aufgeklappt
 *   Ansicht waagerecht (Wurzel links) oder senkrecht (Wurzel oben): Knopf in der Leiste, je Benutzer
 *   gemerkt. Verschobene Kacheln merkt sich jede Richtung für sich.
 *   hoehe:    640               – Höhe der Fläche in px
 *
 * Sprung mit Filter (nur in eine andere Rubrik): felder: { <Feldname im Ziel>: { praefix, ausser? } }
 * nimmt den Schlüssel aus der Knoten-ID („lief_123“ → lieferant = 123). Passt die ID nicht oder steht
 * der Rest in `ausser` (Vorgabe ["rest"] = „Übrige“), springt er ohne diesen Filter. Der Zeitraum
 * (von/bis) geht mit, außer bei zeitraum: false. sprung_mitnehmen: ["plattform"] (am Widget) gibt die
 * eigenen Filter des Cockpits an jedes Ziel weiter, das ein gleichnamiges Feld hat; leere Filter nicht.
 * Ein Filter aus dem Knoten (felder) geht vor.
 * Plan: ~/.claude/plans/ein-cockpit-rubriken.md, Phase 2.
 */
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import TableWidget from "./TableWidget";
import api from "../../../api/client";
import { useRubriken, findeRubrik, rubrikPfad } from "../../../pages/start/rubriken";

const nf0 = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const fmt = (v, einheit = "eur") => v == null ? "–" : nf0.format(Math.round(v)) + (einheit === "anzahl" ? "" : " €");
const pct = (v) => nf1.format(v * 100) + " %";
const zahl = (x) => { const n = typeof x === "number" ? x : Number(String(x ?? "").replace(",", ".")); return Number.isFinite(n) ? n : null; };

const GX = 74, GY = 16, W = 236, RW = 318;
const VX = 18, VY = 64;                                  // Abstände in der senkrechten Ansicht
// Richtung je Benutzer (Server, /api/start/einstellungen); lokal nur als Zwischenstand gegen Flackern.
const RICHTUNG_KEY = "dm-baum-richtung";
const reduziert = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

function richtung(v, p, gut) {
  if (v == null || p == null || p === 0) return "neutral";
  const d = (v - p) / Math.abs(p);
  if (Math.abs(d) < 0.02) return "neutral";
  return (d > 0) === (gut !== "runter") ? "ok" : "err";
}
const FARBE = { ok: "var(--ok)", err: "var(--err)", neutral: "var(--text-dim)" };

function Delta({ v, p, gut }) {
  if (v == null || p == null || p === 0) return null;
  const d = (v - p) / Math.abs(p);
  return <span style={{ color: FARBE[richtung(v, p, gut)] }}>{d >= 0 ? "▲" : "▼"} {nf1.format(Math.abs(d) * 100)} %</span>;
}

function Spark({ werte, st }) {
  if (!werte || werte.length < 2) return null;
  const w = 206, h = 28, mn = Math.min(...werte), mx = Math.max(...werte), r = (mx - mn) || 1;
  const pts = werte.map((v, i) => [i * w / (werte.length - 1), h - 2 - (v - mn) / r * (h - 6)]);
  const d = "M" + pts.map((p) => p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" L");
  const last = pts[pts.length - 1];
  const c = FARBE[st];
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden="true"
      style={{ display: "block", margin: "6px 0 2px", width: "100%", height: 30, overflow: "visible" }}>
      <path d={`${d} L${w} ${h} L0 ${h} Z`} style={{ fill: c, opacity: 0.14 }} />
      <path d={d} style={{ fill: "none", stroke: c, strokeWidth: 1.5 }} />
      <circle cx={last[0]} cy={last[1]} r={2.6} style={{ fill: c }} />
    </svg>
  );
}

export default function BaumWidget({ widget, result, results = {}, formId = null, onTab = null, params = {} }) {
  const cfg = widget.config || {};
  const sp = { knoten: "Knoten", wert: "Wert", vj: "WertVJ", ...(cfg.spalten || {}) };
  const wurzel = cfg.wurzel || { id: "wurzel", titel: widget.label || "Ergebnis", kinder: [], zeilen: [] };
  const sp2 = { eltern: "Eltern", ansicht: "Ansicht", titel: "Titel", untertitel: "Untertitel", ...(cfg.spalten || {}) };
  // Feste Knoten aus der Konfiguration; Zeilen mit „Eltern“ legen ihren Knoten selbst an
  // (Kanäle, Warengruppen, Lieferanten … sind bei jedem Kunden andere). Sie erben gut/Sprünge
  // vom Oberpunkt bzw. dessen kind_vorlage und hängen in dessen Ansicht „Ansicht“ (sonst kinder).
  const defs = useMemo(() => {
    const out = {};
    for (const [k, d] of Object.entries(cfg.knoten || {})) {
      const dd: any = { ...(d as any) };
      if (dd.ansichten) dd.ansichten = Object.fromEntries(Object.entries(dd.ansichten).map(([a, l]) => [a, [...(l as any)]]));
      if (dd.kinder) dd.kinder = [...dd.kinder];
      out[k] = dd;
    }
    out[wurzel.id] = { ...wurzel, kinder: [...(wurzel.kinder || [])], istWurzel: true };
    const schonDrin = new Set();
    for (const r of result?.rows || []) {
      const k = r[sp.knoten], pa = r[sp2.eltern];
      if (k == null) continue;
      // Untertitel aus den Daten (z. B. „233 Kunden …“) gilt auch für feste Knoten.
      if (out[k] && r[sp2.untertitel]) out[k].untertitel = r[sp2.untertitel];
      if (pa == null || pa === "" || !out[pa] || schonDrin.has(k) || k === pa) continue;
      schonDrin.add(k);
      const eltern = out[pa], ans = r[sp2.ansicht];
      // Vorlage für Kinder: je Ansicht (Kanal ≠ Warengruppe) oder für alle.
      const vorlage = (ans && eltern.kind_vorlage_je_ansicht?.[ans]) || eltern.kind_vorlage || {};
      // Fest konfigurierte Knoten (z. B. Bestandskunden mit Zusatzknoten) behalten ihre Angaben.
      out[k] = { gut: eltern.gut, ...vorlage, titel: r[sp2.titel] || String(k),
        untertitel: r[sp2.untertitel] || vorlage.untertitel || ans || "", dynamisch: !out[k], ...(out[k] || {}) };
      if (!out[k].titel) out[k].titel = r[sp2.titel] || String(k);
      if (ans) {
        eltern.ansichten = eltern.ansichten || {};
        const l = (eltern.ansichten[ans] = eltern.ansichten[ans] || []);
        if (!l.includes(k)) l.push(k);
      } else {
        const l = (eltern.kinder = eltern.kinder || []);
        if (!l.includes(k)) l.push(k);
      }
    }
    // Ansichten ohne einen einzigen Knoten weglassen (z. B. Kanal bei nur einer Plattform: bleibt, ist aber 1)
    for (const d of Object.values(out) as any[]) {
      if (d.ansichten) for (const a of Object.keys(d.ansichten)) if (!d.ansichten[a].length) delete d.ansichten[a];
      if (d.ansichten && !Object.keys(d.ansichten).length) delete d.ansichten;
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [widget, result]);
  const navigate = useNavigate();
  const ktx = useRubriken();                       // nur im Büro vorhanden
  const speicherKey = `dm-baum-${formId ?? "x"}-${widget.id}`;

  // ── Zustand (Aufgeklappt, Ansicht je Knoten, verschobene Kacheln) ──
  const [zustand, setZustand] = useState(() => {
    let s = null;
    try { s = JSON.parse(localStorage.getItem(speicherKey) || "null"); } catch { s = null; }
    return {
      offen: new Set(s?.offen || cfg.offen || [wurzel.id]),
      ansicht: s?.ansicht || {},
      versatz: s?.versatz || {},
      versatzV: s?.versatzV || {},
    };
  });
  const [ausrichtung, setAusrichtung] = useState(() => {
    try { return localStorage.getItem(RICHTUNG_KEY) === "senkrecht" ? "senkrecht" : "waagerecht"; } catch { return "waagerecht"; }
  });
  useEffect(() => {
    let lebt = true;
    api.get("/api/start/einstellungen").then(({ data }) => {
      if (lebt && (data?.baum_richtung === "senkrecht" || data?.baum_richtung === "waagerecht")) {
        setAusrichtung(data.baum_richtung);
        try { localStorage.setItem(RICHTUNG_KEY, data.baum_richtung); } catch { /* egal */ }
      }
    }).catch(() => { /* ohne Server bleibt die lokale Wahl */ });
    return () => { lebt = false; };
  }, []);
  const senkrecht = ausrichtung === "senkrecht";
  const vKey = senkrecht ? "versatzV" : "versatz";
  const [panel, setPanel] = useState(null);
  useEffect(() => {
    try {
      localStorage.setItem(speicherKey, JSON.stringify({
        offen: [...zustand.offen], ansicht: zustand.ansicht, versatz: zustand.versatz, versatzV: zustand.versatzV }));
    } catch { /* egal */ }
  }, [zustand, speicherKey]);

  const ansichtVon = (id) => {
    const d = defs[id];
    if (!d?.ansichten) return null;
    const namen = Object.keys(d.ansichten);
    const a = zustand.ansicht[id];
    return a && d.ansichten[a] ? a : (d.ansicht && d.ansichten[d.ansicht] ? d.ansicht : namen[0]);
  };
  const summenKinder = (id) => {
    const d = defs[id]; if (!d) return [];
    if (d.ansichten) return (d.ansichten[ansichtVon(id)] || []).filter((k) => defs[k]);
    return (d.kinder || []).filter((k) => defs[k]);
  };
  const kinder = (id) => summenKinder(id).concat((defs[id]?.zusatz || []).filter((k) => defs[k]))
    .filter((k) => !(defs[k]?.leer_ausblenden && !werte[k]?.v && !werte[k]?.p))
    // Unterpunkte aus den Daten (Kanal, Lieferant …) mit 0 € im Zeitraum nicht als Kachel zeigen.
    // Die Σ-Prüfung rechnet weiter mit allen (summenKinder), dort zählen sie ja 0.
    .filter((k) => !(defs[k]?.dynamisch && Math.abs(werte[k]?.v || 0) < 0.5));
  const alleKinder = (id) => {
    const d = defs[id]; if (!d) return [];
    let k = [...(d.kinder || []), ...(d.zusatz || [])];
    for (const v of Object.values(d.ansichten || {})) k = k.concat(v as any);
    return k.filter((x) => defs[x]);
  };
  const eltern = useMemo(() => {
    const m = {};
    for (const id of Object.keys(defs)) for (const k of alleKinder(id)) if (!(k in m)) m[k] = id;
    return m;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defs]);

  // ── Werte ──
  const daten = useMemo(() => {
    const m = new Map();
    for (const r of result?.rows || []) {
      const k = r[sp.knoten];
      if (k == null) continue;
      m.set(String(k), { v: zahl(r[sp.wert]), p: zahl(r[sp.vj]) });
    }
    return m;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result]);
  const verlauf = useMemo(() => {
    const vc = cfg.verlauf;
    const res = vc?.action_id ? results[vc.action_id] : null;
    if (!res?.rows) return null;
    const s = { knoten: "Knoten", monat: "Monat", wert: "Wert", ...(vc.spalten || {}) };
    const m = new Map();
    for (const r of res.rows) {
      const k = String(r[s.knoten]);
      if (!m.has(k)) m.set(k, []);
      m.get(k).push([String(r[s.monat]), zahl(r[s.wert]) ?? 0]);
    }
    for (const [k, l] of m) m.set(k, l.sort((a, b) => a[0].localeCompare(b[0])).map((x) => x[1]));
    return m;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [results, widget]);

  const werte = useMemo(() => {
    const cache = {};
    const formel = (f, welche, tiefe) => {
      let summe = 0, vz = 1;
      for (const t of String(f).match(/[+-]|[^\s+-]+/g) || []) {
        if (t === "+") { vz = 1; continue; }
        if (t === "-") { vz = -1; continue; }
        const n = /^\d+([.,]\d+)?$/.test(t) ? zahl(t) : wert(t, tiefe + 1)?.[welche];
        if (n == null) return null;
        summe += vz * n; vz = 1;
      }
      return summe;
    };
    const wert = (id, tiefe = 0) => {
      if (id in cache) return cache[id];
      if (tiefe > 20) return null;
      const d = defs[id];
      let r;
      if (d?.formel) r = { v: formel(d.formel, "v", tiefe), p: formel(d.formel, "p", tiefe) };
      else r = daten.get(String(d?.wert ?? id)) || { v: null, p: null };
      cache[id] = r;
      return r;
    };
    const out = {};
    for (const id of Object.keys(defs)) out[id] = wert(id);
    // Zeilen der Wurzel (Umsatz, DB I …) als eigene Werte
    (wurzel.zeilen || []).forEach((z, i) => {
      out[`__z${i}`] = z.formel ? { v: formel(z.formel, "v", 0), p: formel(z.formel, "p", 0) }
        : (out[z.wert] || daten.get(String(z.wert)) || { v: null, p: null });
    });
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [daten, defs]);

  const bezug = werte["__z0"]?.v ?? null;           // erste Wurzelzeile = Bezug (Umsatz)
  const anteil = (id) => {
    const d = defs[id], pa = eltern[id], v = werte[id]?.v;
    if (d?.info || v == null || !pa) return null;
    if (defs[pa]?.istWurzel) return bezug ? { s: Math.abs(v / bezug), von: "vom " + ((wurzel.zeilen || [])[0]?.label || "Bezug") } : null;
    const pv = werte[pa]?.v;
    return pv ? { s: Math.abs(v / pv), von: "von " + defs[pa].titel } : null;
  };
  const status = (id) => {
    const d = defs[id];
    if (d?.istWurzel) {
      const i = (wurzel.zeilen || []).findIndex((z) => z.hl);
      const z = werte[`__z${i >= 0 ? i : (wurzel.zeilen || []).length - 1}`];
      return z ? richtung(z.v, z.p) : "neutral";
    }
    return richtung(werte[id]?.v, werte[id]?.p, d?.gut);
  };

  // ── Sichtbare Knoten ──
  const sichtbar = useMemo(() => {
    const out = [];
    const lauf = (id, tiefe) => { out.push(id); if (zustand.offen.has(id) && tiefe < 12) for (const k of kinder(id)) lauf(k, tiefe + 1); };
    lauf(wurzel.id, 0);
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zustand, defs]);

  // ── Anordnung, Zeichnen, Verschieben ──
  const vpRef = useRef(null), weltRef = useRef(null), svgRef = useRef(null);
  const elsRef = useRef({});
  const posRef = useRef({}), zielRef = useRef({});
  const ansichtRef = useRef({ x: 30, y: 24, s: 1 });
  const eingepasst = useRef(false);

  const gesamtVersatz = (id, versatz) => {
    let x = 0, y = 0;
    for (let a = id, n = 0; a && n < 30; a = eltern[a], n++) { const o = versatz[a]; if (o) { x += o.x; y += o.y; } }
    return { x, y };
  };
  const berechneZiele = useCallback((versatz) => {
    const p = {}; let cursor = 0;
    if (senkrecht) {
      // Wurzel oben, jede Ebene eine Zeile; Zeilenhöhe = höchste Kachel der Ebene.
      const hoeheJe = [];
      const messen = (id, tiefe) => {
        hoeheJe[tiefe] = Math.max(hoeheJe[tiefe] || 0, elsRef.current[id]?.offsetHeight || 120);
        if (zustand.offen.has(id) && tiefe < 12) for (const k of kinder(id)) messen(k, tiefe + 1);
      };
      messen(wurzel.id, 0);
      const yJe = [0];
      for (let t = 0; t < hoeheJe.length; t++) yJe[t + 1] = yJe[t] + hoeheJe[t] + VY;
      const setzeV = (id, tiefe) => {
        const w = elsRef.current[id]?.offsetWidth || (tiefe === 0 ? RW : W);
        const ks = zustand.offen.has(id) && tiefe < 12 ? kinder(id) : [];
        if (!ks.length) { p[id] = { x: cursor, y: yJe[tiefe] }; cursor += w + VX; return cursor - VX - w / 2; }
        const cs = ks.map((k) => setzeV(k, tiefe + 1)), c = (cs[0] + cs[cs.length - 1]) / 2;
        p[id] = { x: c - w / 2, y: yJe[tiefe] }; if (p[id].x + w + VX > cursor) cursor = p[id].x + w + VX; return c;
      };
      setzeV(wurzel.id, 0);
    } else {
    const setze = (id, tiefe) => {
      const el = elsRef.current[id]; const h = el?.offsetHeight || 120;
      const x = tiefe === 0 ? 0 : RW + GX + (tiefe - 1) * (W + GX);
      const ks = zustand.offen.has(id) ? kinder(id) : [];
      if (!ks.length) { p[id] = { x, y: cursor }; cursor += h + GY; return cursor - GY - h / 2; }
      const cs = ks.map((k) => setze(k, tiefe + 1)), c = (cs[0] + cs[cs.length - 1]) / 2;
      p[id] = { x, y: c - h / 2 }; if (p[id].y + h + GY > cursor) cursor = p[id].y + h + GY; return c;
    };
    setze(wurzel.id, 0);
    }
    const t = {};
    for (const id of sichtbar) { const o = gesamtVersatz(id, versatz); t[id] = { x: (p[id]?.x || 0) + o.x, y: (p[id]?.y || 0) + o.y }; }
    return t;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sichtbar, zustand.offen, eltern, senkrecht]);

  const ansichtSetzen = () => {
    const v = ansichtRef.current;
    if (weltRef.current) weltRef.current.style.transform = `translate(${v.x}px,${v.y}px) scale(${v.s})`;
    if (vpRef.current) { vpRef.current.style.backgroundPosition = `${v.x}px ${v.y}px`; vpRef.current.style.backgroundSize = `${22 * v.s}px ${22 * v.s}px`; }
  };
  const malen = () => {
    const pos = posRef.current;
    for (const id of sichtbar) { const el = elsRef.current[id], p = pos[id]; if (el && p) el.style.transform = `translate(${p.x}px,${p.y}px)`; }
    let pfade = "";
    for (const id of sichtbar) {
      const pa = eltern[id]; if (!pa || !sichtbar.includes(pa)) continue;
      const a = pos[pa], b = pos[id], ea = elsRef.current[pa], eb = elsRef.current[id];
      if (!a || !b || !ea || !eb) continue;
      const d = defs[id], an = anteil(id);
      const breite = d.info ? 2 : Math.max(1.6, Math.min(16, (an ? an.s : 0.3) * 16));
      const st = status(id);
      const stil = d.info ? `stroke:var(--text-dim);opacity:.7;stroke-dasharray:5 6`
        : `stroke:${FARBE[st]};opacity:${st === "neutral" ? 0.45 : 0.55}`;
      let pfad;
      if (senkrecht) {
        const x1 = a.x + ea.offsetWidth / 2, y1 = a.y + ea.offsetHeight, x2 = b.x + eb.offsetWidth / 2, y2 = b.y;
        const dy = Math.max(30, (y2 - y1) / 2);
        pfad = `M${x1} ${y1} C${x1} ${y1 + dy}, ${x2} ${y2 - dy}, ${x2} ${y2}`;
      } else {
        const x1 = a.x + ea.offsetWidth, y1 = a.y + ea.offsetHeight / 2, x2 = b.x, y2 = b.y + eb.offsetHeight / 2;
        const dx = Math.max(40, (x2 - x1) / 2);
        pfad = `M${x1} ${y1} C${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
      }
      pfade += `<path style="fill:none;stroke-linecap:round;${stil}" stroke-width="${breite.toFixed(1)}" d="${pfad}"/>`;
    }
    if (svgRef.current) svgRef.current.innerHTML = pfade;
  };
  const einpassen = () => {
    const vp = vpRef.current; if (!vp || !vp.clientWidth) return;
    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
    for (const id of sichtbar) {
      const p = zielRef.current[id], el = elsRef.current[id]; if (!p || !el) continue;
      x0 = Math.min(x0, p.x); y0 = Math.min(y0, p.y); x1 = Math.max(x1, p.x + el.offsetWidth); y1 = Math.max(y1, p.y + el.offsetHeight);
    }
    if (x0 > x1) return;
    const W0 = vp.clientWidth, H0 = vp.clientHeight, pad = 32;
    const s = Math.max(0.3, Math.min(1.05, (W0 - 2 * pad) / (x1 - x0), (H0 - 2 * pad) / (y1 - y0)));
    ansichtRef.current = { s, x: (W0 - (x1 - x0) * s) / 2 - x0 * s, y: Math.max(pad, (H0 - (y1 - y0) * s) / 2) - y0 * s };
    ansichtSetzen();
  };

  // Nach jedem Rendern: Ziele aus den gemessenen Höhen, dann dorthin gleiten.
  useLayoutEffect(() => {
    const ziel = berechneZiele(zustand[vKey]);
    zielRef.current = ziel;
    const pos = posRef.current;
    for (const id of sichtbar) if (!pos[id]) { const pa = eltern[id]; pos[id] = pa && pos[pa] ? { ...pos[pa] } : { ...ziel[id] }; }
    if (!eingepasst.current && (result?.rows || []).length) { eingepasst.current = true; posRef.current = { ...ziel }; malen(); einpassen(); return; }
    if (reduziert()) { posRef.current = { ...pos, ...ziel }; malen(); return; }
    const von = JSON.parse(JSON.stringify(pos)), t0 = performance.now(), dauer = 240;
    let laeuft = true;
    const schritt = (jetzt) => {
      if (!laeuft) return;
      const k = Math.min(1, (jetzt - t0) / dauer), e = 1 - Math.pow(1 - k, 3);
      for (const id of sichtbar) { const f = von[id] || ziel[id], z = ziel[id]; posRef.current[id] = { x: f.x + (z.x - f.x) * e, y: f.y + (z.y - f.y) * e }; }
      malen();
      if (k < 1) requestAnimationFrame(schritt);
    };
    requestAnimationFrame(schritt);
    return () => { laeuft = false; };
  });

  // Die Fläche gibt es erst, wenn Werte da sind – deshalb an hatDaten hängen.
  const hatDaten = (result?.rows || []).length > 0;
  useEffect(() => { ansichtSetzen(); }, [hatDaten]);
  useEffect(() => {
    const vp = vpRef.current; if (!vp) return;
    const rad = (e) => {
      e.preventDefault();
      const r = vp.getBoundingClientRect(), cx = e.clientX - r.left, cy = e.clientY - r.top;
      zoomen(Math.exp(-e.deltaY * 0.0015), cx, cy);
    };
    vp.addEventListener("wheel", rad, { passive: false });
    return () => vp.removeEventListener("wheel", rad);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hatDaten]);
  const zoomen = (f, cx, cy) => {
    const v = ansichtRef.current, s = Math.min(1.6, Math.max(0.3, v.s * f));
    ansichtRef.current = { s, x: cx - (cx - v.x) * s / v.s, y: cy - (cy - v.y) * s / v.s };
    ansichtSetzen();
  };

  const verschiebenStart = (e) => {
    if (e.target.closest(".dmb-node,.dmb-legende,.dmb-panel,button")) return;
    const vp = vpRef.current, sx = e.clientX, sy = e.clientY, v0 = { ...ansichtRef.current };
    vp.setPointerCapture?.(e.pointerId); vp.style.cursor = "grabbing";
    const mv = (ev) => { ansichtRef.current = { ...v0, x: v0.x + ev.clientX - sx, y: v0.y + ev.clientY - sy }; ansichtSetzen(); };
    const up = () => { vp.style.cursor = "grab"; vp.removeEventListener("pointermove", mv); vp.removeEventListener("pointerup", up); };
    vp.addEventListener("pointermove", mv); vp.addEventListener("pointerup", up);
  };
  const ziehenStart = (e, id) => {
    if (e.target.closest("button")) return;
    e.stopPropagation();
    const el = elsRef.current[id], sx = e.clientX, sy = e.clientY;
    const o0 = { ...(zustand[vKey][id] || { x: 0, y: 0 }) };
    let bewegt = false, versatz = zustand[vKey];
    el.setPointerCapture?.(e.pointerId);
    const mv = (ev) => {
      const s = ansichtRef.current.s, dx = (ev.clientX - sx) / s, dy = (ev.clientY - sy) / s;
      if (!bewegt && Math.hypot(dx, dy) < 4) return;
      bewegt = true; el.style.zIndex = "3"; el.style.cursor = "grabbing";
      versatz = { ...zustand[vKey], [id]: { x: o0.x + dx, y: o0.y + dy } };
      const z = berechneZiele(versatz); zielRef.current = z; posRef.current = { ...posRef.current, ...z }; malen();
    };
    const up = () => {
      el.style.zIndex = ""; el.style.cursor = "";
      el.removeEventListener("pointermove", mv); el.removeEventListener("pointerup", up);
      if (bewegt) setZustand((z) => ({ ...z, [vKey]: versatz }));
    };
    el.addEventListener("pointermove", mv); el.addEventListener("pointerup", up);
  };

  // ── Bedienung ──
  const zuklappen = (offen, id) => { offen.delete(id); for (const k of alleKinder(id)) zuklappen(offen, k); };
  const umschalten = (id) => setZustand((z) => {
    const offen = new Set(z.offen);
    if (offen.has(id)) zuklappen(offen, id); else offen.add(id);
    return { ...z, offen };
  });
  const ansichtWaehlen = (id, name) => setZustand((z) => {
    const offen = new Set(z.offen);
    for (const k of alleKinder(id)) zuklappen(offen, k);
    offen.add(id);
    return { ...z, offen, ansicht: { ...z.ansicht, [id]: name } };
  });
  const spaeterEinpassen = () => setTimeout(einpassen, 280);
  const richtungWaehlen = (r) => {
    if (r === ausrichtung) return;
    setAusrichtung(r);
    try { localStorage.setItem(RICHTUNG_KEY, r); } catch { /* egal */ }
    api.put("/api/start/einstellungen", { baum_richtung: r }).catch(() => { /* bleibt lokal gemerkt */ });
    spaeterEinpassen();
  };

  // Feldwerte für das Ziel aus der Knoten-ID; {} = nur Zeitraum, gefiltert = welche Felder greifen.
  const sprungWerte = (s, knotenId) => {
    const werte = {}, gefiltert = [];
    for (const feld of cfg.sprung_mitnehmen || []) {
      const v = params?.[feld];
      if (Array.isArray(v) ? v.length : v != null && v !== "") werte[feld] = v;
    }
    for (const [feld, regel] of Object.entries(s.felder || {}) as [string, any][]) {
      const praefix = regel?.praefix ?? "";
      const id = String(knotenId ?? "");
      if (!id.startsWith(praefix)) continue;
      const wert = id.slice(praefix.length);
      if (!wert || (regel?.ausser || ["rest"]).includes(wert)) continue;
      werte[feld] = wert;
      gefiltert.push(feld);
    }
    if (s.zeitraum !== false) for (const p of ["von", "bis"]) if (params?.[p]) werte[p] = params[p];
    return { werte, gefiltert };
  };
  const sprungZiel = (s, knotenId) => {
    if (!s.rubrik) return onTab ? () => onTab(s.reiter) : null;
    const r = ktx?.gruppen ? findeRubrik(ktx.gruppen, s.rubrik) : null;
    return r ? () => navigate(rubrikPfad(r, null, s.reiter, sprungWerte(s, knotenId).werte)) : null;
  };

  // ── Darstellung ──
  const knopf = { border: "1px solid var(--border)", background: "transparent", borderRadius: 5, padding: "3px 8px",
    fontSize: 11.5, whiteSpace: "nowrap" as const, cursor: "pointer", color: "var(--text-main)" };
  const werkzeug = { border: "1px solid var(--border)", background: "transparent", borderRadius: 6, padding: "6px 11px",
    fontSize: 12.5, cursor: "pointer", color: "var(--text-main)", minHeight: 32 };

  const kachel = (id) => {
    const d = defs[id], w = werte[id] || { v: null, p: null }, st = status(id), an = anteil(id);
    const ks = kinder(id), offen = zustand.offen.has(id), sk = summenKinder(id);
    let summe = null;
    if (sk.length && w.v != null && !d.istWurzel) {
      const vs = sk.map((k) => werte[k]?.v);
      if (vs.every((x) => x != null)) {
        const s = vs.reduce((a, b) => a + b, 0), diff = s - w.v;
        summe = Math.abs(diff) <= Math.max(1, Math.abs(w.v) * 0.0005) ? { ok: true } : { ok: false, diff };
      }
    }
    // Hinweis: {wert, text, wenn: "null"} – Vorgabe: zeigen, wenn der Wert größer 0 ist.
    const hinweisN = d.hinweis ? (d.hinweis.wert ? daten.get(String(d.hinweis.wert))?.v : w.v) : null;
    const hinweisAn = d.hinweis && (d.hinweis.wenn === "null" ? !hinweisN : hinweisN > 0);
    const hatDetails = !!(d.tabelle || (d.spruenge || []).length || d.beschreibung);
    const expKnopf = ks.length > 0 && (
      <button onClick={() => umschalten(id)} aria-expanded={offen}
        style={{ ...knopf, ...(offen ? { borderColor: "var(--accent)", color: "var(--accent)" } : {}) }}>
        {offen ? `${senkrecht ? "▴" : "◂"} einklappen` : `${senkrecht ? "▾" : "▸"} ${ks.length} Unterpunkte`}
      </button>
    );
    const detailKnopf = hatDetails && (
      <button onClick={() => setPanel(id)} style={knopf}>{d.tabelle && !ks.length ? "Tabelle öffnen" : "Details"}</button>
    );
    const rand = d.istWurzel ? "1.5px solid var(--accent)" : `1px ${d.info ? "dashed" : "solid"} var(--border)`;
    return (
      <div key={id} ref={(el) => { if (el) elsRef.current[id] = el; else delete elsRef.current[id]; }}
        className="dmb-node" onPointerDown={(e) => ziehenStart(e, id)}
        style={{ position: "absolute", left: 0, top: 0, width: d.istWurzel ? RW : W, background: "var(--bg-card)", border: rand,
          borderRadius: 8, boxShadow: "0 1px 2px rgba(0,0,0,.08), 0 4px 14px rgba(0,0,0,.08)",
          padding: d.istWurzel ? "14px 16px 12px 19px" : "10px 12px 9px 15px", cursor: "grab", userSelect: "none", touchAction: "none",
          color: "var(--text-main)" }}>
        <div style={{ position: "absolute", left: 0, top: 8, bottom: 8, width: 4, borderRadius: "0 3px 3px 0", background: FARBE[st] }} />
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
          <span style={{ fontWeight: 650, fontSize: d.istWurzel ? 16 : 14.5, color: "var(--text-bright)" }}>{d.titel}</span>
          <span style={{ color: "var(--text-dim)", fontSize: 11.5, textAlign: "right" }}>{d.untertitel || ""}</span>
        </div>
        {d.ansichten && (
          <div role="group" aria-label="Aufteilen nach" style={{ display: "flex", flexWrap: "wrap", gap: 4, margin: "7px 0 2px" }}>
            {Object.keys(d.ansichten).map((a) => {
              const an2 = a === ansichtVon(id);
              return (
                <button key={a} onClick={() => ansichtWaehlen(id, a)} aria-pressed={an2}
                  style={{ fontSize: 11, border: `1px solid ${an2 ? "var(--accent)" : "var(--border)"}`, background: "transparent",
                    borderRadius: 999, padding: "2px 8px", cursor: "pointer", color: an2 ? "var(--accent)" : "var(--text-dim)",
                    fontWeight: an2 ? 600 : 400 }}>{a}</button>
              );
            })}
          </div>
        )}
        {d.istWurzel ? (
          <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 9, fontVariantNumeric: "tabular-nums" }}>
            <tbody>
              {(wurzel.zeilen || []).map((z, i) => {
                const zw = werte[`__z${i}`] || {};
                const td = { padding: "4px 0", borderTop: "1px solid var(--border)", fontSize: 12.5, fontWeight: z.hl ? 600 : 400 };
                const num = { ...td, fontFamily: "var(--font-mono)", textAlign: "right" as const, paddingLeft: 8, whiteSpace: "nowrap" as const };
                return (
                  <tr key={i}>
                    <td style={{ ...td, color: z.hl ? "var(--text-bright)" : "var(--text-dim)" }}>{z.label}</td>
                    <td style={num}>{fmt(zw.v)}</td>
                    <td style={num}>{z.quote && zw.v != null && bezug ? pct(zw.v / bezug) : ""}</td>
                    <td style={num}><Delta v={zw.v} p={zw.p} gut={z.gut} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (<>
          <div style={{ fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums", fontSize: 19, fontWeight: 600, marginTop: 6,
            letterSpacing: "-.02em", color: w.v == null ? "var(--text-dim)" : "var(--text-bright)" }}>
            {w.v == null ? <span style={{ fontSize: 13, fontWeight: 500, fontStyle: "italic", fontFamily: "var(--font-body)" }}>keine Daten</span> : fmt(w.v, d.einheit)}
          </div>
          {w.p != null && (
            <div style={{ display: "flex", gap: 10, alignItems: "baseline", fontSize: 12, marginTop: 1, fontFamily: "var(--font-mono)" }}>
              <Delta v={w.v} p={w.p} gut={d.gut} /><span style={{ color: "var(--text-dim)" }}>VJ {fmt(w.p, d.einheit)}</span>
            </div>
          )}
          <Spark werte={verlauf?.get(String(d.wert ?? id))} st={st} />
          {hinweisAn && (
            <div style={{ fontSize: 11.5, color: "var(--warn)", marginTop: 4, lineHeight: 1.35 }}>
              {String(d.hinweis.text || "{n} ohne Wert").replace("{n}", nf0.format(hinweisN || 0))}
            </div>
          )}
        </>)}
        {(an || d.info || summe) && (
          <div style={{ marginTop: 4, fontSize: 11.5, color: "var(--text-dim)" }}>
            {an ? `${nf0.format(an.s * 100)} % ${an.von}` : d.info ? "Zusatzinfo" : ""}
            {summe?.ok && <span title="Die Unterpunkte ergeben zusammen genau diesen Wert" style={{ color: "var(--ok)", fontFamily: "var(--font-mono)" }}>{an || d.info ? " · " : ""}Σ ✓</span>}
            {summe && !summe.ok && <span title={`Die Unterpunkte weichen um ${fmt(summe.diff)} von diesem Wert ab`} style={{ color: "var(--warn)", fontFamily: "var(--font-mono)" }}>{an || d.info ? " · " : ""}Σ ≠</span>}
          </div>
        )}
        {(detailKnopf || expKnopf) && (
          <div style={{ display: "flex", justifyContent: "flex-end", flexWrap: "wrap", gap: 4, marginTop: 6 }}>{detailKnopf}{expKnopf}</div>
        )}
      </div>
    );
  };

  const pd = panel ? defs[panel] : null;
  const panelTabelle = useMemo(() => {
    const t = pd?.tabelle; if (!t?.action_id) return null;
    const res = results[t.action_id]; if (!res) return null;
    let rows = res.rows || [];
    // {titel} im Filterwert = Titel des Knotens (Kanal, Warengruppe, Kostenblock …)
    const fw = t.filter ? String(t.filter.wert ?? "{titel}").replace("{titel}", pd.titel) : null;
    if (t.filter?.spalte) rows = rows.filter((r) => String(r[t.filter.spalte]) === fw);
    return { ...res, rows, total: rows.length };
  }, [pd, results]);

  const hoehe = Number(cfg.hoehe) || 640;
  const legende = [
    [<path key="a" d="M0 7 H44" strokeWidth="2" style={{ stroke: "var(--text-dim)" }} />, "dünn = kleiner Anteil am Oberpunkt"],
    [<path key="b" d="M0 7 H44" strokeWidth="10" style={{ stroke: "var(--text-dim)", opacity: 0.5 }} />, "dick = großer Anteil"],
    [<path key="c" d="M0 7 H44" strokeWidth="4" style={{ stroke: "var(--ok)", opacity: 0.6 }} />, "grün = besser als Vorjahr"],
    [<path key="d" d="M0 7 H44" strokeWidth="4" style={{ stroke: "var(--err)", opacity: 0.65 }} />, "rot = schlechter als Vorjahr"],
    [<path key="e" d="M0 7 H44" strokeWidth="2" strokeDasharray="5 6" style={{ stroke: "var(--text-dim)" }} />, "gestrichelt = Zusatzinfo, zählt nicht zur Summe"],
  ];

  if (!(result?.rows || []).length && !result?.error) {
    return <p style={{ padding: 16, margin: 0, color: "var(--text-dim)", fontSize: 13 }}>Noch keine Werte. Sobald die Auswertung gelaufen ist, erscheint hier der Baum.</p>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "6px 8px", padding: "10px 14px",
        borderBottom: "1px solid var(--border)", background: "var(--bg-elevated)" }}>
        <button style={werkzeug} onClick={() => { setZustand((z) => ({ ...z, offen: new Set([wurzel.id]) })); spaeterEinpassen(); }}>Alles einklappen</button>
        <button style={werkzeug} onClick={() => { setZustand((z) => ({ ...z, [vKey]: {} })); spaeterEinpassen(); }}>Neu ordnen</button>
        <div role="group" aria-label="Richtung" style={{ display: "inline-flex" }}>
          {[["waagerecht", "↔ Waagerecht"], ["senkrecht", "↕ Senkrecht"]].map(([r, text], i) => {
            const an = ausrichtung === r;
            return (
              <button key={r} aria-pressed={an} onClick={() => richtungWaehlen(r)}
                style={{ ...werkzeug, borderRadius: i === 0 ? "6px 0 0 6px" : "0 6px 6px 0", marginLeft: i ? -1 : 0,
                  ...(an ? { borderColor: "var(--accent)", color: "var(--accent)", position: "relative" as const, zIndex: 1,
                    background: "color-mix(in srgb, var(--accent) 10%, transparent)" } : {}) }}>{text}</button>
            );
          })}
        </div>
        <button style={werkzeug} onClick={einpassen}>Einpassen</button>
        <button style={{ ...werkzeug, width: 32, padding: "6px 0" }} aria-label="Verkleinern"
          onClick={() => zoomen(1 / 1.2, vpRef.current.clientWidth / 2, vpRef.current.clientHeight / 2)}>−</button>
        <button style={{ ...werkzeug, width: 32, padding: "6px 0" }} aria-label="Vergrößern"
          onClick={() => zoomen(1.2, vpRef.current.clientWidth / 2, vpRef.current.clientHeight / 2)}>+</button>
        <span style={{ color: "var(--text-dim)", fontSize: 12, flex: "1 1 220px" }}>
          Kacheln ziehen, Hintergrund verschieben, Mausrad zoomt.
        </span>
      </div>
      <div ref={vpRef} onPointerDown={verschiebenStart}
        style={{ position: "relative", height: hoehe, overflow: "hidden", cursor: "grab", touchAction: "none",
          backgroundImage: "radial-gradient(color-mix(in srgb, var(--text-dim) 30%, transparent) 1.2px, transparent 1.3px)",
          backgroundSize: "22px 22px" }}>
        <div ref={weltRef} style={{ position: "absolute", left: 0, top: 0, transformOrigin: "0 0" }}>
          <svg ref={svgRef} width="1" height="1" style={{ position: "absolute", left: 0, top: 0, overflow: "visible", pointerEvents: "none" }} />
          {sichtbar.map(kachel)}
        </div>

        <div className="dmb-legende" aria-label="Legende"
          style={{ position: "absolute", left: 14, bottom: 14, background: "var(--bg-card)", border: "1px solid var(--border)",
            borderRadius: 8, padding: "10px 12px", fontSize: 12, color: "var(--text-dim)", display: "grid",
            gridTemplateColumns: "44px 1fr", gap: "6px 10px", alignItems: "center", maxWidth: 300, zIndex: 4 }}>
          <span style={{ gridColumn: "1 / -1", color: "var(--text-bright)", fontWeight: 600 }}>So liest man die Linien</span>
          {legende.map(([svg, text], i) => (
            <span key={i} style={{ display: "contents" }}>
              <svg style={{ width: 44, height: 14, overflow: "visible" }}>{svg}</svg><span>{text}</span>
            </span>
          ))}
        </div>

        <aside className="dmb-panel" aria-hidden={!pd}
          style={{ position: "absolute", top: 0, right: 0, bottom: 0, width: "min(520px, 100%)", background: "var(--bg-card)",
            borderLeft: "1px solid var(--border)", boxShadow: "-8px 0 24px rgba(0,0,0,.14)", zIndex: 6, display: "flex", flexDirection: "column",
            transform: pd ? "none" : "translateX(105%)", transition: reduziert() ? "none" : "transform .22s ease" }}>
          {pd && (<>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, padding: "14px 16px 10px",
              borderBottom: "1px solid var(--border)" }}>
              <div>
                <h3 style={{ margin: 0, fontSize: 16, color: "var(--text-bright)" }}>{pd.titel}</h3>
                {werte[panel]?.v != null && (
                  <span style={{ fontSize: 12.5, color: "var(--text-dim)", fontFamily: "var(--font-mono)" }}>
                    {fmt(werte[panel].v, pd.einheit)}{werte[panel].p != null && ` · VJ ${fmt(werte[panel].p, pd.einheit)}`}
                  </span>
                )}
              </div>
              <button onClick={() => setPanel(null)} aria-label="Schließen" style={{ ...werkzeug, width: 32, padding: "6px 0" }}>×</button>
            </div>
            <div style={{ padding: "12px 16px 20px", overflow: "auto", display: "flex", flexDirection: "column", gap: 12 }}>
              {pd.beschreibung && <p style={{ margin: 0, lineHeight: 1.5, fontSize: 13.5 }}>{pd.beschreibung}</p>}
              {(pd.spruenge || []).map((s, i) => {
                const los = sprungZiel(s, panel); if (!los) return null;
                const r = s.rubrik && ktx?.gruppen ? findeRubrik(ktx.gruppen, s.rubrik) : null;
                const gefiltert = s.rubrik && sprungWerte(s, panel).gefiltert.length > 0;
                return (
                  <button key={i} onClick={los} style={{ ...werkzeug, textAlign: "left" }}
                    title={gefiltert ? `Öffnet gleich gefiltert auf „${pd.titel}“` : undefined}>
                    → {s.label || (r ? `${r.name} · Reiter „${s.reiter}“` : `Reiter „${s.reiter}“`)}
                    {gefiltert && <span style={{ display: "block", fontSize: 11.5, color: "var(--text-dim)" }}>
                      nur „{pd.titel}“</span>}
                  </button>
                );
              })}
              {panelTabelle
                ? <div style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
                    <TableWidget widget={{ id: `baum-${panel}`, type: "table", label: pd.titel, config: pd.tabelle?.config || {} }}
                      result={panelTabelle} allowDownload={true} onDrilldown={undefined} onAiAction={undefined} />
                  </div>
                : pd.tabelle && <p style={{ margin: 0, fontSize: 12.5, color: "var(--text-dim)" }}>Die Tabelle ist noch nicht geladen.</p>}
            </div>
          </>)}
        </aside>
      </div>
    </div>
  );
}
