/** Kategorien der Templates: eingebaute mit deutschem Namen, alles andere ist
 *  ein frei vergebener Name und wird so angezeigt, wie er gespeichert ist. */
export const KATEGORIE_LABEL: Record<string, string> = {
  general:   "Allgemein",
  jtl:       "JTL WaWi",
  logistics: "Logistik",
  finance:   "Finanzen / Buchhaltung",
  reporting: "Reporting",
};

export const kategorieLabel = (kat?: string | null) =>
  KATEGORIE_LABEL[kat || "general"] || kat || "Allgemein";

/** Eingabe → gespeicherter Wert. Wer den Namen einer eingebauten Kategorie tippt,
 *  landet in derselben Gruppe wie bisher (z. B. „JTL WaWi“ → jtl). */
export function kategorieWert(eingabe: string): string {
  const t = (eingabe || "").trim();
  if (!t) return "general";
  const treffer = Object.entries(KATEGORIE_LABEL)
    .find(([id, label]) => label.toLowerCase() === t.toLowerCase() || id === t.toLowerCase());
  return treffer ? treffer[0] : t;
}
