/**
 * Schalter „Markt“ für jede Kurve mit Monatsachse: legt eine Reihe aus den Marktdaten (monstersuite-Datendienst:
 * Destatis, Eurostat, DWD, EZB …) gestrichelt mit eigener rechter Achse neben die eigenen Zahlen.
 *
 * ERP-neutral: gebraucht wird nur die Monatsachse der Kurve – deshalb wirkt das in JTL-, büro+- und Lexware-Cockpits
 * gleich. Vorschläge kommen aus dem Branchenprofil des Projekts (Vergleichsbranche, Preisindex – gesetzt von Hand
 * oder über ein Marktlage-Paket), dazu die Suche im ganzen Katalog.
 *
 * Die Wahl ist eine Ansichts-Einstellung je Betrachter und Kurve (localStorage), keine Projekteinstellung.
 * config.markt = false schaltet den Schalter für eine Kurve ab.
 */
import { useEffect, useMemo, useState } from "react";
import { Globe, Search, X } from "lucide-react";
import api, { fehlerText } from "../../api/client";

export type MarktWahl = { groesse: string; region: string; label: string; einheit: string; quelle?: string };

const reihenCache = new Map<string, Promise<any>>();
let katalogCache: Promise<any[]> | null = null;

function katalogLaden(): Promise<any[]> {
  if (!katalogCache) {
    katalogCache = api.get("/api/umfeld/datenkatalog").then(({ data }) => data.groessen || [])
      .catch((e) => { katalogCache = null; throw e; });
  }
  return katalogCache;
}

function reiheLaden(g: string, r: string) {
  const s = `${g}|${r}`;
  if (!reihenCache.has(s)) {
    reihenCache.set(s, api.post("/api/umfeld/reihen", { groessen: [g], regionen: [r], von: "2015-01", bis: "" })
      .then(({ data }) => {
        const x = data.reihen?.[0] || null;
        if (!x || (x.hinweis && !Object.keys(x.werte?.[r] || {}).length)) reihenCache.delete(s);
        return x;
      })
      .catch((e) => { reihenCache.delete(s); return { fehler: fehlerText(e) }; }));
  }
  return reihenCache.get(s);
}

const speicherKey = (projectId, widgetId) => `dm-markt-${projectId ?? "ohne"}-${widgetId}`;
function lesen(k: string): MarktWahl | null {
  try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : null; } catch { return null; }
}
function schreiben(k: string, w: MarktWahl | null) {
  try { if (w) localStorage.setItem(k, JSON.stringify(w)); else localStorage.removeItem(k); } catch { /* egal */ }
}

/** Vorschläge aus dem Branchenprofil des Projekts plus ein paar allgemeine Reihen. */
async function vorschlaege(projectId): Promise<MarktWahl[]> {
  const q = projectId != null ? `?project_id=${projectId}` : "";
  const [br, pi] = await Promise.all([
    api.get(`/api/business-config/branche${q}`).then((r) => r.data.auswahl).catch(() => null),
    api.get(`/api/business-config/preisindex${q}`).then((r) => r.data.auswahl).catch(() => null),
  ]);
  const aus: MarktWahl[] = [];
  if (br?.code) {
    const name = (br.label || br.code).replace(/\s*\(.*\)$/, "");
    aus.push({ groesse: "umsatz_handel_real_ka", region: br.code, label: `Branchenumsatz real: ${name}`, einheit: "2021 = 100" });
    aus.push({ groesse: "umsatz_handel_ka", region: br.code, label: `Branchenumsatz nominal: ${name}`, einheit: "2021 = 100" });
  }
  if (pi?.key) aus.push({ groesse: pi.key, region: pi.region, label: `Preisindex: ${(pi.label || pi.region).replace(/^Großhandel: /, "")}`, einheit: "2021 = 100" });
  aus.push({ groesse: "preise_verbraucher", region: "Deutschland", label: "Verbraucherpreise", einheit: "2021 = 100" });
  aus.push({ groesse: "stimmung", region: "BS-ESI-I", label: "Wirtschaftsklima (ESI)", einheit: "Ø = 100" });
  aus.push({ groesse: "temperatur", region: "Deutschland", label: "Temperatur Deutschland", einheit: "°C" });
  return aus.filter((x, i) => aus.findIndex((y) => y.groesse === x.groesse && y.region === x.region) === i);
}

export function MarktDialog({ projectId, aktuell, onWahl, onClose }) {
  const [vor, setVor] = useState<MarktWahl[] | null>(null);
  const [katalog, setKatalog] = useState<any[] | null>(null);
  const [suche, setSuche] = useState("");
  const [fehler, setFehler] = useState("");
  useEffect(() => {
    vorschlaege(projectId).then(setVor);
    katalogLaden().then(setKatalog).catch((e) => setFehler(fehlerText(e)));
  }, [projectId]);
  const treffer = useMemo(() => {
    const t = suche.trim().toLowerCase();
    if (!t || !katalog) return [];
    const aus: MarktWahl[] = [];
    for (const g of katalog) {
      if (g.takt !== "monat") continue;
      const passtGroesse = g.label.toLowerCase().includes(t);
      for (const r of g.regionen || []) {
        if (passtGroesse || r.label.toLowerCase().includes(t) || r.code.toLowerCase().includes(t)) {
          aus.push({ groesse: g.key, region: r.code, einheit: g.einheit, quelle: g.quelle,
            label: g.regionen.length > 1 ? `${g.label}: ${r.label}` : g.label });
          if (aus.length >= 40) return aus;
        }
      }
    }
    return aus;
  }, [suche, katalog]);
  const zeile = (x: MarktWahl) => {
    const an = aktuell && aktuell.groesse === x.groesse && aktuell.region === x.region;
    return (
      <button key={`${x.groesse}|${x.region}`} onClick={() => onWahl(x)}
        style={{ display: "flex", justifyContent: "space-between", gap: 10, width: "100%", textAlign: "left", padding: "7px 10px",
          border: "none", borderTop: "1px solid var(--border)", cursor: "pointer", fontSize: 12.5,
          background: an ? "color-mix(in srgb, var(--accent) 12%, transparent)" : "transparent", color: "var(--text-main)" }}>
        <span>{x.label}</span><span style={{ color: "var(--text-dim)", whiteSpace: "nowrap" }}>{x.einheit}</span>
      </button>
    );
  };
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 1000, background: "rgba(0,0,0,.45)",
      display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <div onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Marktreihe einblenden"
        style={{ width: "min(560px, 100%)", maxHeight: "80vh", background: "var(--bg-card)", border: "1px solid var(--border)",
          borderRadius: 10, padding: 18, display: "flex", flexDirection: "column", gap: 10, color: "var(--text-main)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <strong style={{ fontSize: 15, color: "var(--text-bright)" }}>Markt einblenden</strong>
          <button onClick={onClose} aria-label="Schließen" style={{ padding: 4, border: "none", background: "transparent",
            color: "var(--text-main)", cursor: "pointer" }}><X size={16} /></button>
        </div>
        <p style={{ margin: 0, fontSize: 12.5, color: "var(--text-dim)", lineHeight: 1.45 }}>
          Die Reihe erscheint gestrichelt mit eigener Achse rechts neben Ihren Zahlen – so sieht man, ob man mit dem Markt
          läuft. Die Auswahl gilt nur für diese Kurve und nur für Sie.
        </p>
        <div style={{ position: "relative" }}>
          <Search size={13} style={{ position: "absolute", left: 9, top: 9, color: "var(--text-dim)" }} />
          <input autoFocus value={suche} onChange={(e) => setSuche(e.target.value)}
            placeholder="Katalog durchsuchen, z. B. Internethandel, Diesel, Papier, Bayern"
            style={{ width: "100%", padding: "7px 9px 7px 28px", borderRadius: 6, border: "1px solid var(--border)",
              background: "var(--bg-elevated)", color: "var(--text-main)", fontSize: 13, boxSizing: "border-box" }} />
        </div>
        <div style={{ overflowY: "auto", border: "1px solid var(--border)", borderRadius: 6, minHeight: 120 }}>
          {!suche.trim() && (
            <>
              <div style={{ padding: "6px 10px", fontSize: 11, color: "var(--text-dim)" }}>Vorschläge für dieses Projekt</div>
              {vor == null ? <div style={{ padding: 10, fontSize: 12.5, color: "var(--text-dim)" }}>Lädt …</div> : vor.map(zeile)}
            </>
          )}
          {suche.trim() && treffer.map(zeile)}
          {suche.trim() && katalog && !treffer.length && <div style={{ padding: 10, fontSize: 12.5, color: "var(--text-dim)" }}>Nichts gefunden.</div>}
        </div>
        {fehler && <p style={{ margin: 0, fontSize: 12.5, color: "var(--err)" }}>{fehler}</p>}
        {aktuell && (
          <button onClick={() => onWahl(null)} style={{ alignSelf: "flex-start", fontSize: 12.5, padding: "6px 12px", borderRadius: 6,
            border: "1px solid var(--border)", background: "transparent", color: "var(--text-main)", cursor: "pointer" }}>
            Ausblenden
          </button>
        )}
      </div>
    </div>
  );
}

/** Hook für LineWidget: Schalter, Dialog und die Werte der gewählten Reihe je Monat. */
export function useMarktvergleich({ widget, projectId, moeglich }) {
  const k = speicherKey(projectId, widget.id);
  const [wahl, setWahl] = useState<MarktWahl | null>(() => (moeglich ? lesen(k) : null));
  const [reihe, setReihe] = useState<any>(null);
  const [dialog, setDialog] = useState(false);
  useEffect(() => {
    if (!wahl || !moeglich) { setReihe(null); return; }
    let lebt = true;
    reiheLaden(wahl.groesse, wahl.region).then((r) => lebt && setReihe(r));
    return () => { lebt = false; };
  }, [wahl?.groesse, wahl?.region, moeglich]); // eslint-disable-line react-hooks/exhaustive-deps

  const werte: Record<string, number> | null = reihe && !reihe.fehler ? (reihe.werte?.[wahl?.region || ""] || null) : null;
  const name = wahl ? `Markt: ${wahl.label}` : null;
  const knopf = moeglich ? (
    <button onClick={() => setDialog(true)} aria-pressed={!!wahl}
      title={wahl ? `${wahl.label} (${wahl.einheit})${reihe?.quelle ? `\nQuelle: ${reihe.quelle}` : ""}\nKlicken zum Ändern`
        : "Eine Marktreihe (Branchenumsatz, Preise, Stimmung, Wetter …) neben die eigenen Zahlen legen"}
      style={{ display: "inline-flex", alignItems: "center", gap: 3, fontSize: 11.5, padding: "2px 8px", borderRadius: 5,
        border: "1px solid var(--border)", cursor: "pointer", maxWidth: 260, overflow: "hidden", whiteSpace: "nowrap",
        textOverflow: "ellipsis",
        background: wahl ? "color-mix(in srgb, var(--accent) 18%, transparent)" : "transparent",
        color: wahl ? "var(--text-bright)" : "var(--text-main)" }}>
      <Globe size={11} /> {wahl ? wahl.label : "Markt"}
      {reihe?.fehler && <span style={{ color: "var(--err)" }}> · nicht verfügbar</span>}
      {reihe?.hinweis && !werte && <span style={{ color: "var(--text-dim)" }}> · lädt</span>}
    </button>
  ) : null;
  const dialogEl = dialog ? (
    <MarktDialog projectId={projectId} aktuell={wahl} onClose={() => setDialog(false)}
      onWahl={(w) => { setWahl(w); schreiben(k, w); setDialog(false); }} />
  ) : null;

  /** Schreibt die Marktwerte in die Datenzeilen (Monat aus „JJJJ-MM“ oder Datum); liefert true, wenn etwas dazukam. */
  const anwenden = (data: any[], xCol: string) => {
    if (!werte || !name) return false;
    let treffer = 0;
    for (const d of data) {
      const v = werte[String(d[xCol] ?? "").slice(0, 7)];
      d[name] = v == null ? null : v;
      if (v != null) treffer++;
    }
    return treffer > 0;
  };
  return { moeglich, wahl, name, einheit: wahl?.einheit || "", knopf, dialog: dialogEl, anwenden };
}
