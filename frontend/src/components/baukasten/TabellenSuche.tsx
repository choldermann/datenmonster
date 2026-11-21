// Tabellensuche im Stein „Aus Tabelle“ / „Dazuholen“.
// Eigene Klappliste statt <datalist>: die native Liste öffnet sich in ziehbaren Elementen (draggable) nicht
// zuverlässig (Chrome/Firefox). Sucht nach Teilen des Namens, auch ohne Schema („rechnung“ → Rechnung.tRechnung).
import { useEffect, useMemo, useRef, useState } from "react";

const MAX = 60;

export default function TabellenSuche({ tabellen, wert, onWahl }: {
  tabellen: { name: string; spalten: unknown[] }[] | null;
  wert: string;
  onWahl: (name: string) => void;
}) {
  const [text, setText] = useState(wert);
  const [offen, setOffen] = useState(false);
  const [aktiv, setAktiv] = useState(0);
  const box = useRef<HTMLSpanElement>(null);
  const liste = useRef<HTMLUListElement>(null);

  useEffect(() => { setText(wert); }, [wert]);
  useEffect(() => {
    if (!offen) return;
    const zu = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) { setOffen(false); setText(wert); } };
    document.addEventListener("mousedown", zu);
    return () => document.removeEventListener("mousedown", zu);
  }, [offen, wert]);

  const treffer = useMemo(() => {
    const alle = tabellen || [];
    const q = text.trim().toLowerCase();
    if (!q || q === wert.toLowerCase()) return alle.slice(0, MAX);
    const teile = q.split(/\s+/);
    const passt = alle.filter((t) => { const n = t.name.toLowerCase(); return teile.every((p) => n.includes(p)); });
    // Namen, deren Tabellenteil mit dem Suchtext beginnt, zuerst
    const rang = (n: string) => { const kurz = n.toLowerCase().split(".").pop() || ""; return kurz.startsWith(teile[0]) || kurz.startsWith("t" + teile[0]) ? 0 : 1; };
    return passt.sort((a, b) => rang(a.name) - rang(b.name) || a.name.length - b.name.length).slice(0, MAX);
  }, [tabellen, text, wert]);

  useEffect(() => { setAktiv(0); }, [text]);
  useEffect(() => { (liste.current?.children[aktiv] as HTMLElement | undefined)?.scrollIntoView({ block: "nearest" }); }, [aktiv]);

  const waehlen = (n: string) => { setText(n); setOffen(false); if (n !== wert) onWahl(n); };

  return (
    <span className="bk-suche" ref={box} onClick={(e) => e.stopPropagation()} onMouseDown={(e) => e.stopPropagation()}>
      <input className="bk-chip breit" value={text} aria-label="Tabelle" role="combobox" aria-expanded={offen} autoComplete="off"
        placeholder={tabellen ? `Tabelle suchen (${tabellen.length.toLocaleString("de-DE")}) …` : "Tabellen laden …"}
        onFocus={(e) => { setOffen(true); e.currentTarget.select(); }}
        onChange={(e) => { setText(e.target.value); setOffen(true); }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setOffen(true); setAktiv((a) => Math.min(a + 1, treffer.length - 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setAktiv((a) => Math.max(a - 1, 0)); }
          else if (e.key === "Enter") { e.preventDefault(); if (treffer[aktiv]) waehlen(treffer[aktiv].name); }
          else if (e.key === "Escape") { setOffen(false); setText(wert); }
        }} />
      {offen && (
        <ul className="bk-suche-liste" ref={liste} role="listbox">
          {tabellen === null ? <li className="leer">Tabellen werden geladen …</li>
            : !treffer.length ? <li className="leer">Keine Tabelle mit „{text}“</li>
            : treffer.map((t, i) => (
              <li key={t.name} role="option" aria-selected={i === aktiv} className={i === aktiv ? "aktiv" : ""}
                onMouseEnter={() => setAktiv(i)} onMouseDown={(e) => { e.preventDefault(); waehlen(t.name); }}>
                {t.name}<span>{t.spalten.length} Sp.</span>
              </li>))}
          {tabellen && treffer.length === MAX && <li className="leer">… weitertippen, um einzugrenzen</li>}
        </ul>)}
    </span>
  );
}
