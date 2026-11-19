import { useEffect, useMemo, useRef, useState } from "react";
import { Filter } from "lucide-react";

// Excel-ähnlicher Spaltenfilter: Werteliste mit Häkchen + Suche.
// filter = { [spalte]: string[] erlaubte Werte } – fehlt die Spalte, ist sie ungefiltert.

const S = {
  bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)", border: "var(--border)",
  textMain: "var(--text-main)", textDim: "var(--text-dim)", accent: "var(--accent)",
};

export const filterSchluessel = (v) => (v === null || v === undefined ? "" : String(v));

export function filtereZeilen(rows, filter) {
  const aktiv = Object.entries(filter || {});
  if (!aktiv.length) return rows;
  const sets = aktiv.map(([c, werte]) => [c, new Set(werte as string[])] as const);
  return rows.filter(r => sets.every(([c, set]) => set.has(filterSchluessel(r[c]))));
}

const MAX_WERTE = 500;

export default function SpaltenFilter({ spalte, rows, filter, setFilter, anzeige }) {
  const [offen, setOffen] = useState(null); // {x, y}
  const [suche, setSuche] = useState("");
  const [auswahl, setAuswahl] = useState(null); // Set während das Fenster offen ist
  const knopf = useRef(null);
  const fenster = useRef(null);
  const aktiv = !!filter?.[spalte];

  // Werte aus den Zeilen, die die ANDEREN Filter durchlassen (wie Excel)
  const werte = useMemo(() => {
    if (!offen) return [];
    const andere = { ...(filter || {}) }; delete andere[spalte];
    const zaehler = new Map();
    for (const r of filtereZeilen(rows, andere)) {
      const k = filterSchluessel(r[spalte]);
      const e = zaehler.get(k);
      if (e) e.n++; else zaehler.set(k, { k, roh: r[spalte], n: 1 });
    }
    return [...zaehler.values()].sort((a, b) =>
      typeof a.roh === "number" && typeof b.roh === "number" ? a.roh - b.roh
        : a.k.localeCompare(b.k, "de", { numeric: true }));
  }, [offen, rows, filter, spalte]);

  const sichtbar = useMemo(() => {
    const q = suche.trim().toLowerCase();
    return (q ? werte.filter(w => (anzeige(w.roh) || "(leer)").toLowerCase().includes(q)) : werte);
  }, [werte, suche, anzeige]);

  useEffect(() => {
    if (!offen) return;
    const weg = (e) => {
      if (fenster.current?.contains(e.target) || knopf.current?.contains(e.target)) return;
      setOffen(null);
    };
    const esc = (e) => { if (e.key === "Escape") { e.stopPropagation(); setOffen(null); } };
    document.addEventListener("mousedown", weg);
    window.addEventListener("keydown", esc, true);
    return () => { document.removeEventListener("mousedown", weg); window.removeEventListener("keydown", esc, true); };
  }, [offen]);

  const oeffnen = (e) => {
    e.stopPropagation();
    if (offen) { setOffen(null); return; }
    const r = knopf.current.getBoundingClientRect();
    const breite = 260;
    setOffen({ x: Math.max(8, Math.min(r.left, window.innerWidth - breite - 8)), y: r.bottom + 4 });
    setSuche("");
    setAuswahl(filter?.[spalte] ? new Set(filter[spalte]) : null); // null = alle
  };

  const istAn = (k) => (auswahl ? auswahl.has(k) : true);
  const umschalten = (k) => {
    const s = auswahl ? new Set(auswahl) : new Set(werte.map(w => w.k));
    if (s.has(k)) s.delete(k); else s.add(k);
    setAuswahl(s);
  };
  const alleSichtbaren = (an) => {
    const s = auswahl ? new Set(auswahl) : new Set(werte.map(w => w.k));
    for (const w of sichtbar) { if (an) s.add(w.k); else s.delete(w.k); }
    setAuswahl(s);
  };
  const anwenden = () => {
    const neu = { ...(filter || {}) };
    // Suche aktiv + OK = wie Excel: nur die gefundenen Werte (sofern angehakt)
    let s = auswahl;
    if (suche.trim()) s = new Set(sichtbar.filter(w => istAn(w.k)).map(w => w.k));
    if (!s || werte.every(w => s.has(w.k))) delete neu[spalte];
    else neu[spalte] = [...s];
    setFilter(neu);
    setOffen(null);
  };
  // Immer bedienbar: hebt den Filter dieser Spalte auf und setzt alle Häkchen zurück –
  // auch wenn erst im Fenster abgewählt, aber noch nicht mit OK bestätigt wurde.
  const loeschen = (e) => {
    e?.stopPropagation();
    setSuche(""); setAuswahl(null);
    if (aktiv) {
      const neu = { ...(filter || {}) }; delete neu[spalte];
      setFilter(neu);
    }
    setOffen(null);
  };

  const btn = { padding: "4px 10px", borderRadius: 4, fontSize: 11, fontWeight: 600, cursor: "pointer",
    border: `1px solid ${S.border}`, backgroundColor: S.bgEl, color: S.textMain };

  return (
    <>
      <span ref={knopf} onClick={oeffnen} title={aktiv ? "Filter aktiv – klicken zum Ändern" : "Filtern"}
        style={{ display: "inline-flex", alignItems: "center", marginLeft: 5, padding: 2, borderRadius: 3, cursor: "pointer",
          verticalAlign: "middle", color: aktiv ? S.accent : S.textDim, opacity: aktiv ? 1 : 0.45,
          backgroundColor: aktiv ? "color-mix(in srgb, var(--accent) 15%, transparent)" : "transparent" }}>
        <Filter size={10} fill={aktiv ? "currentColor" : "none"} />
      </span>
      {offen && (
        <div ref={fenster} onClick={e => e.stopPropagation()}
          style={{ position: "fixed", left: offen.x, top: offen.y, width: 260, zIndex: 2000,
            backgroundColor: S.bgCard, border: `1px solid ${S.border}`, borderRadius: 8,
            boxShadow: "0 10px 30px rgba(0,0,0,0.45)", padding: 8, textTransform: "none",
            letterSpacing: "normal", fontWeight: 400, fontSize: 11, color: S.textMain, textAlign: "left", cursor: "default" }}>
          <input autoFocus value={suche} onChange={e => setSuche(e.target.value)} placeholder="Suchen …"
            onKeyDown={e => { if (e.key === "Enter") anwenden(); }}
            style={{ width: "100%", boxSizing: "border-box", padding: "5px 8px", fontSize: 11, borderRadius: 4,
              border: `1px solid ${S.border}`, backgroundColor: S.bgEl, color: S.textMain, outline: "none" }} />
          <div style={{ display: "flex", gap: 10, margin: "6px 2px", fontSize: 10.5 }}>
            <a onClick={() => alleSichtbaren(true)} style={{ color: S.accent, cursor: "pointer" }}>Alle auswählen</a>
            <a onClick={() => alleSichtbaren(false)} style={{ color: S.accent, cursor: "pointer" }}>Keine</a>
          </div>
          <div style={{ maxHeight: 260, overflow: "auto", border: `1px solid ${S.border}`, borderRadius: 4, scrollbarWidth: "thin" }}>
            {sichtbar.slice(0, MAX_WERTE).map(w => (
              <label key={w.k} style={{ display: "flex", alignItems: "center", gap: 6, padding: "3px 8px", cursor: "pointer", whiteSpace: "nowrap" }}>
                <input type="checkbox" checked={istAn(w.k)} onChange={() => umschalten(w.k)} />
                <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", color: w.k === "" ? S.textDim : S.textMain }}>
                  {w.k === "" ? "(leer)" : anzeige(w.roh)}
                </span>
                <span style={{ color: S.textDim, fontSize: 10 }}>{w.n}</span>
              </label>
            ))}
            {sichtbar.length > MAX_WERTE && (
              <div style={{ padding: "4px 8px", color: S.textDim }}>… {sichtbar.length - MAX_WERTE} weitere – Suche eingrenzen</div>
            )}
            {!sichtbar.length && <div style={{ padding: "6px 8px", color: S.textDim }}>Kein Treffer</div>}
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 6, marginTop: 8 }}>
            <button type="button" onClick={loeschen} style={btn}>Filter löschen</button>
            <div style={{ display: "flex", gap: 6 }}>
              <button type="button" onClick={() => setOffen(null)} style={btn}>Abbrechen</button>
              <button type="button" onClick={anwenden} style={{ ...btn, borderColor: S.accent, color: S.accent }}>OK</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
