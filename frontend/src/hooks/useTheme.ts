import { useSyncExternalStore } from "react";
import api from "../api/client";
import { findeTheme } from "../themes";

/** "system" folgt Hell/Dunkel des Betriebssystems, sonst eine Theme-ID aus themes.ts. */
export type ThemeMode = string;

/* Das Farbschema gehört zum Benutzerkonto (users.theme). Im Browser liegt nur
 * eine Kopie (dm_theme), damit die Seite vor dem Login bzw. vor der Antwort von
 * /api/auth/me schon im richtigen Theme erscheint und nichts aufblitzt.
 * Ein gemeinsamer Zustand für alle Komponenten: Umschalten im Portal und in den
 * Einstellungen bleibt dadurch synchron. */

const STANDARD = "dark";

function aufloesen(mode: ThemeMode): { id: string; scheme: "dark" | "light" } {
  if (mode === "system") {
    const dunkel = window.matchMedia("(prefers-color-scheme: dark)").matches;
    return dunkel ? { id: "dark", scheme: "dark" } : { id: "light", scheme: "light" };
  }
  const t = findeTheme(mode) || findeTheme(STANDARD)!;
  return { id: t.id, scheme: t.scheme };
}

function gueltig(wert: string | null | undefined): ThemeMode | null {
  return wert && (wert === "system" || findeTheme(wert)) ? wert : null;
}

function anwenden(mode: ThemeMode) {
  const { id, scheme } = aufloesen(mode);
  document.documentElement.setAttribute("data-theme", id);
  document.documentElement.setAttribute("data-scheme", scheme);
}

function lokalLesen(): ThemeMode {
  try { return gueltig(localStorage.getItem("dm_theme")) || STANDARD; } catch { return STANDARD; }
}

let aktuell: ThemeMode = lokalLesen();
const zuhoerer = new Set<() => void>();

function setzen(mode: ThemeMode) {
  aktuell = mode;
  anwenden(mode);
  try { localStorage.setItem("dm_theme", mode); } catch { /* privates Fenster o.ä. */ }
  zuhoerer.forEach(f => f());
}

// Systemthema-Änderungen live mitverfolgen
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if (aktuell === "system") anwenden("system");
});

/** Nach Login bzw. /api/auth/me: Theme aus dem Konto übernehmen.
 *  Kein Eintrag im Konto = Standard (nicht das, was der Vorgänger am selben
 *  Browser eingestellt hatte). */
export function kontoThemeUebernehmen(theme: string | null | undefined) {
  setzen(gueltig(theme) || STANDARD);
}

/** Ist das tatsächlich angezeigte Theme dunkel? (für Hell/Dunkel-Umschalter) */
export function istDunkel(mode: ThemeMode): boolean {
  return aufloesen(mode).scheme === "dark";
}

export function useTheme() {
  const mode = useSyncExternalStore(
    f => { zuhoerer.add(f); return () => { zuhoerer.delete(f); }; },
    () => aktuell,
  );
  const setMode = (neu: ThemeMode) => {
    setzen(neu);
    // Im Konto speichern; schlägt das fehl, gilt die Wahl wenigstens in diesem Browser.
    // Ohne Anmeldung gar nicht erst versuchen – ein 401 leitet sonst zum Login um.
    let angemeldet = false;
    try { angemeldet = !!localStorage.getItem("dm_token"); } catch { /* egal */ }
    if (!angemeldet) return;
    api.put("/api/auth/theme", { theme: neu })
      .catch(e => console.warn("Farbschema nicht im Konto gespeichert:", e));
  };
  return { mode, setMode };
}

// Beim ersten Laden sofort anwenden (verhindert Flash)
anwenden(aktuell);
