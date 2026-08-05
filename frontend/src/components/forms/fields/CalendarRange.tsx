import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

const S = {
  bgEl: "var(--bg-elevated)", bgCard: "var(--bg-card)", border: "var(--border)",
  textMain: "var(--text-main)", textBright: "var(--text-bright)", textDim: "var(--text-dim)",
  accent: "var(--accent)",
};

const pad = n => String(n).padStart(2, "0");
export const toISO = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
export const parseISO = s => {
  if (!s) return null;
  const [y, m, d] = String(s).split("-").map(Number);
  if (!y || !m || !d) return null;
  return new Date(y, m - 1, d);
};
export const fmtDE = s => {
  const d = parseISO(s);
  return d ? `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}` : "";
};

const WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];
const MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
  "August", "September", "Oktober", "November", "Dezember"];

/** Zellen (Date|null) für ein Monatsraster, Woche beginnt Montag. */
function monthMatrix(year, month) {
  const first = new Date(year, month, 1);
  const startDow = (first.getDay() + 6) % 7;           // Montag = 0
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells = [];
  for (let i = 0; i < startDow; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(new Date(year, month, d));
  while (cells.length % 7 !== 0) cells.push(null);
  return cells;
}

const midnight = d => new Date(d.getFullYear(), d.getMonth(), d.getDate());

/**
 * Kalender zur Bereichsauswahl. from/to sind ISO-Strings (yyyy-mm-dd).
 * Erster Klick setzt den Start (from=to=Tag), zweiter Klick den Endtag
 * (bei Bedarf getauscht). onChange(fromISO, toISO) meldet den Bereich.
 */
export default function CalendarRange({ from, to, onChange }) {
  const fromD = parseISO(from), toD = parseISO(to);
  const [view, setView] = useState(() => fromD || new Date());
  const [pendingStart, setPendingStart] = useState(null);

  const y = view.getFullYear(), m = view.getMonth();
  const cells = useMemo(() => monthMatrix(y, m), [y, m]);
  const shiftMonth = delta => setView(new Date(y, m + delta, 1));

  const clickDay = d => {
    if (!pendingStart) {
      setPendingStart(d);
      onChange(toISO(d), toISO(d));
    } else {
      let a = pendingStart, b = d;
      if (b < a) { const t = a; a = b; b = t; }
      onChange(toISO(a), toISO(b));
      setPendingStart(null);
    }
  };

  const lo = fromD ? midnight(fromD) : null;
  const hi = toD ? midnight(toD) : null;
  const isEdge = d => (lo && +midnight(d) === +lo) || (hi && +midnight(d) === +hi);
  const inRange = d => lo && hi && midnight(d) >= lo && midnight(d) <= hi;

  const cellBtn = (edge, ranged) => ({
    width: 30, height: 28, border: "none", borderRadius: ranged && !edge ? 0 : 6,
    fontSize: 12, cursor: "pointer",
    background: edge ? S.accent : ranged ? "rgba(110,231,183,0.14)" : "transparent",
    color: edge ? "#0c1a12" : S.textMain,
    fontWeight: edge ? 700 : 400,
  });

  return (
    <div style={{ userSelect: "none" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <button type="button" onClick={() => shiftMonth(-1)}
          style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 4 }}>
          <ChevronLeft size={16} />
        </button>
        <span style={{ fontSize: 13, fontWeight: 600, color: S.textBright }}>{MONTHS[m]} {y}</span>
        <button type="button" onClick={() => shiftMonth(1)}
          style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 4 }}>
          <ChevronRight size={16} />
        </button>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 30px)", gap: 2 }}>
        {WEEKDAYS.map(w => (
          <div key={w} style={{ textAlign: "center", fontSize: 10, fontWeight: 600,
            color: S.textDim, paddingBottom: 2 }}>{w}</div>
        ))}
        {cells.map((d, i) => d ? (
          <button key={i} type="button" onClick={() => clickDay(d)}
            style={cellBtn(isEdge(d), inRange(d))}>
            {d.getDate()}
          </button>
        ) : <div key={i} />)}
      </div>
    </div>
  );
}
