/**
 * Monatsbeschriftung für Zeitachsen: „2024-02“ liest sich leicht als 2. Quartal, deshalb
 * überall „Feb 2024“. Gilt für reine Monate („2026-03“) und Monatserste („2026-03-01“),
 * nicht für Tagesdaten – die bleiben, wie sie sind.
 */
const MONATE = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];

const text = (m) => `${MONATE[Number(m.slice(5, 7)) - 1]} ${m.slice(0, 4)}`;

/** Ein Wert als Monat geschrieben, sonst unverändert (Tooltips, Überschriften). */
export const monatText = (m) => /^\d{4}-\d{2}/.test(String(m)) ? text(String(m)) : String(m ?? "");

/**
 * Formatierer für eine Achse, wenn ALLE Werte Monate sind – sonst null (Kategorien, Tage,
 * gemischte Achsen bleiben unberührt). Monatserste zählen nur, wenn es mehrere sind.
 */
export function monatsAchse(werte) {
  const xs = (werte || []).map((v) => String(v ?? ""));
  if (!xs.length) return null;
  if (xs.every((x) => /^\d{4}-\d{2}$/.test(x))) return (v) => /^\d{4}-\d{2}$/.test(String(v)) ? text(String(v)) : String(v ?? "");
  if (xs.length > 1 && xs.every((x) => /^\d{4}-\d{2}-01(T00:00(:00)?(\.0+)?Z?)?$/.test(x)))
    return (v) => /^\d{4}-\d{2}-01/.test(String(v)) ? text(String(v)) : String(v ?? "");
  return null;
}
