/**
 * Preisbereinigung: eigener Umsatz geteilt durch die Preisentwicklung der Branche (Destatis).
 *
 * Welche Branche zum Betrieb gehört, steht je Mandant unter /api/business-config/preisindex.
 * Die Indexreihe kommt über /api/umfeld/reihen vom monstersuite-Datendienst (2021 = 100).
 * Bereinigt wird auf die Preise des letzten Indexmonats: Umsatz(m) × I(ref) / I(m). Damit bleibt
 * der jüngste Wert fast unverändert, und ältere Monate zeigen, was dieselbe Menge heute kosten würde.
 */
import { useEffect, useMemo, useState } from "react";
import { X, Search } from "lucide-react";
import api, { fehlerText } from "../../api/client";
import { monatText } from "./widgets/monat";

const EVENT = "dm-preisindex-geaendert";
const auswahlCache = new Map<string, Promise<any>>();
const reihenCache = new Map<string, Promise<any>>();
const k = (projectId) => String(projectId ?? "ohne");

function auswahlLaden(projectId, neu = false) {
  if (neu || !auswahlCache.has(k(projectId))) {
    const q = projectId != null ? `?project_id=${projectId}` : "";
    auswahlCache.set(k(projectId), api.get(`/api/business-config/preisindex${q}`).then((r) => r.data)
      .catch(() => ({ auswahl: null, fehler: true })));
  }
  return auswahlCache.get(k(projectId));
}

function reiheLaden(key, region) {
  const s = `${key}|${region}`;
  if (!reihenCache.has(s)) {
    reihenCache.set(s, api.post("/api/umfeld/reihen", { groessen: [key], regionen: [region], von: "2015-01", bis: "" })
      .then(({ data }) => { const r = data.reihen?.[0] || null; if (!r || r.hinweis) reihenCache.delete(s); return r; })
      .catch((e) => { reihenCache.delete(s); return { fehler: fehlerText(e) }; }));
  }
  return reihenCache.get(s);
}

/** Auswahl und Indexreihe des aktiven Mandanten. */
export function usePreisindex(projectId, aktiv = true) {
  const [auswahl, setAuswahl] = useState(undefined);      // undefined = lädt, null = keine
  const [mandantName, setMandantName] = useState(null);
  const [reihe, setReihe] = useState(null);
  useEffect(() => {
    if (!aktiv) return;
    let lebt = true;
    const holen = (neu = false) => auswahlLaden(projectId, neu).then((d) => {
      if (!lebt) return;
      setAuswahl(d.auswahl || null); setMandantName(d.mandant_name || null);
    });
    holen();
    const bei = (e) => { if (e.detail === k(projectId)) holen(); };
    window.addEventListener(EVENT, bei);
    return () => { lebt = false; window.removeEventListener(EVENT, bei); };
  }, [projectId, aktiv]);
  useEffect(() => {
    if (!auswahl) { setReihe(null); return; }
    let lebt = true;
    reiheLaden(auswahl.key, auswahl.region).then((r) => lebt && setReihe(r));
    return () => { lebt = false; };
  }, [auswahl?.key, auswahl?.region]); // eslint-disable-line react-hooks/exhaustive-deps
  const werte = reihe?.werte?.[auswahl?.region] || null;
  return { auswahl, mandantName, werte, quelle: reihe?.quelle, stand: reihe?.stand, fehler: reihe?.fehler || null };
}

export async function preisindexSpeichern(projectId, wahl) {
  if (wahl) await api.put("/api/business-config/preisindex", { project_id: projectId ?? null, ...wahl });
  else await api.delete(`/api/business-config/preisindex${projectId != null ? `?project_id=${projectId}` : ""}`);
  auswahlCache.delete(k(projectId));
  window.dispatchEvent(new CustomEvent(EVENT, { detail: k(projectId) }));
}

/**
 * Bereinigte Werte je Monat. `monate` = Achsenwerte („2026-03“), `betraege` = gleich lange Liste.
 * Monate nach dem letzten Indexmonat gelten als zu dessen Preisen (Faktor 1); Monate ohne
 * Index (vor 2015) bleiben leer. Gibt { werte, ref } zurück, ref = Bezugsmonat oder null.
 */
export function bereinigen(monate, betraege, index) {
  if (!index) return { werte: monate.map(() => null), ref: null };
  const verfuegbar = Object.keys(index).sort();
  const letzterAchse = [...monate].sort().pop();
  const ref = verfuegbar.filter((m) => m <= letzterAchse).pop() || null;
  if (!ref) return { werte: monate.map(() => null), ref: null };
  const iRef = index[ref];
  const werte = monate.map((m, i) => {
    const b = betraege[i];
    if (b == null) return null;
    const im = m > ref ? iRef : index[m];
    return im ? Math.round((b * iRef) / im * 100) / 100 : null;
  });
  return { werte, ref };
}

/** Auswahl der Branche (Liste vom Datendienst, mit Suche). */
export function PreisindexDialog({ projectId, aktuell, mandantName, onClose }) {
  const [liste, setListe] = useState(null);
  const [fehler, setFehler] = useState("");
  const [suche, setSuche] = useState("");
  const [laeuft, setLaeuft] = useState(false);
  useEffect(() => {
    api.get("/api/umfeld/preise/katalog")
      .then(({ data }) => { setListe(data.indizes || []); if (data.hinweis) setFehler(data.hinweis); })
      .catch((e) => setFehler(fehlerText(e)));
  }, []);
  const gefiltert = useMemo(() => {
    const t = suche.trim().toLowerCase();
    return (liste || []).filter((x) => !t || x.label.toLowerCase().includes(t) || x.region.toLowerCase().includes(t));
  }, [liste, suche]);
  const waehlen = async (x) => {
    setLaeuft(true); setFehler("");
    try { await preisindexSpeichern(projectId, x && { key: x.key, region: x.region, label: x.label }); onClose(); }
    catch (e) { setFehler(fehlerText(e)); setLaeuft(false); }
  };
  const knopf = { padding: "7px 14px", borderRadius: 6, fontSize: 13, cursor: "pointer", border: "1px solid var(--border)",
    background: "transparent", color: "var(--text-main)" };
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 1000, background: "rgba(0,0,0,.45)",
      display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <div onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Branche für die Preisbereinigung"
        style={{ width: "min(560px, 100%)", maxHeight: "80vh", background: "var(--bg-card)", border: "1px solid var(--border)",
          borderRadius: 10, padding: 18, display: "flex", flexDirection: "column", gap: 10, color: "var(--text-main)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <strong style={{ fontSize: 15, color: "var(--text-bright)" }}>Branche für die Preisbereinigung</strong>
          <button onClick={onClose} aria-label="Schließen" style={{ ...knopf, padding: 4, border: "none" }}><X size={16} /></button>
        </div>
        <p style={{ margin: 0, fontSize: 12.5, color: "var(--text-dim)", lineHeight: 1.45 }}>
          Mit dem Preisindex Ihrer Branche rechnet das Cockpit die Preissteigerung aus dem Umsatz heraus – dann sieht man,
          ob mehr verkauft oder nur teurer verkauft wurde. Gilt für {mandantName || "diesen Betrieb"}.
          Händler an Endkunden wählen die Verbraucherpreise.
        </p>
        <div style={{ position: "relative" }}>
          <Search size={13} style={{ position: "absolute", left: 9, top: 9, color: "var(--text-dim)" }} />
          <input autoFocus value={suche} onChange={(e) => setSuche(e.target.value)} placeholder="z. B. Reinigungsmittel, Papier, medizinisch"
            style={{ width: "100%", padding: "7px 9px 7px 28px", borderRadius: 6, border: "1px solid var(--border)",
              background: "var(--bg-input, var(--bg-elevated))", color: "var(--text-main)", fontSize: 13, boxSizing: "border-box" }} />
        </div>
        <div style={{ overflowY: "auto", border: "1px solid var(--border)", borderRadius: 6, minHeight: 120 }}>
          {liste == null && !fehler && <div style={{ padding: 12, fontSize: 12.5, color: "var(--text-dim)" }}>Lädt…</div>}
          {gefiltert.map((x) => {
            const aktiv = aktuell && aktuell.key === x.key && aktuell.region === x.region;
            return (
              <button key={`${x.key}|${x.region}`} disabled={laeuft} onClick={() => waehlen(x)}
                style={{ display: "flex", justifyContent: "space-between", gap: 10, width: "100%", textAlign: "left",
                  padding: "7px 10px", fontSize: 12.5, cursor: "pointer", border: "none", borderBottom: "1px solid var(--border)",
                  background: aktiv ? "color-mix(in srgb, var(--accent) 14%, transparent)" : "transparent", color: "var(--text-main)" }}>
                <span>{x.label}</span>
                <span style={{ color: "var(--text-dim)", whiteSpace: "nowrap" }}>{x.region.replace("WZ08-", "WZ ")}</span>
              </button>
            );
          })}
          {liste && !gefiltert.length && <div style={{ padding: 12, fontSize: 12.5, color: "var(--text-dim)" }}>Keine Branche gefunden.</div>}
        </div>
        {fehler && <span style={{ fontSize: 12.5, color: "var(--err-soft, var(--err))" }}>{fehler}</span>}
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
          {aktuell ? <button onClick={() => waehlen(null)} disabled={laeuft} style={knopf}>Preisbereinigung ausschalten</button> : <span />}
          <button onClick={onClose} style={knopf}>Abbrechen</button>
        </div>
      </div>
    </div>
  );
}

export const bezugText = (ref) => (ref ? `Preisstand ${monatText(ref)}` : "");
