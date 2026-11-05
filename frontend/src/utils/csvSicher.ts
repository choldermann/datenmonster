/**
 * Formel-Injektion in CSV-Downloads verhindern (Gegenstück zu
 * backend/app/core/csv_sicher.py – Regeln dort erklärt).
 * Zahlen bleiben Zahlen; "-5" oder "- Sonderposten" bleiben unverändert.
 */
export function csvZelle(v: unknown): string {
  const s = v == null ? "" : String(v);
  if (typeof v !== "string" || !s) return s;
  const erstes = s[0];
  if ("=@\t\r".includes(erstes) || ("+-".includes(erstes) && /[(!|=]/.test(s))) return "'" + s;
  return s;
}
