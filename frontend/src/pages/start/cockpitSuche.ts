/**
 * Zu einer Warnung das Cockpit finden, in dem man ihr nachgeht.
 *
 * Die Warnregeln tragen nur einen Anzeigenamen („GF-Cockpit“, „Lager-Cockpit“),
 * keine Formular-ID. Gesucht wird deshalb über den Namen im selben Projekt;
 * findet sich nichts Eindeutiges, bekommt die Warnung keinen „Ansehen“-Knopf.
 */
const KUERZEL: Record<string, string> = { gf: "geschäftsführer" };

function stamm(name: string): string {
  const erstes = (name || "").toLowerCase().split(/[\s-]/)[0] || "";
  return KUERZEL[erstes] || erstes;
}

export function passendesCockpit(warnung: any, cockpits: any[]) {
  const s = stamm(warnung?.cockpit || "");
  if (!s) return null;
  const treffer = cockpits.filter((c) => c.art === "cockpit"
    && (c.name || "").toLowerCase().startsWith(s.slice(0, 6)));
  return treffer.find((c) => c.project_id === warnung.project_id) || (treffer.length === 1 ? treffer[0] : null);
}
