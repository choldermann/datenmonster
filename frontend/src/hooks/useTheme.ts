import { useEffect, useState } from "react";
import { findeTheme } from "../themes";

/** "system" folgt Hell/Dunkel des Betriebssystems, sonst eine Theme-ID aus themes.ts. */
export type ThemeMode = string;

function aufloesen(mode: ThemeMode): { id: string; scheme: "dark" | "light" } {
  if (mode === "system") {
    const dunkel = window.matchMedia("(prefers-color-scheme: dark)").matches;
    return dunkel ? { id: "dark", scheme: "dark" } : { id: "light", scheme: "light" };
  }
  const t = findeTheme(mode) || findeTheme("dark")!;
  return { id: t.id, scheme: t.scheme };
}

function applyTheme(mode: ThemeMode) {
  const { id, scheme } = aufloesen(mode);
  document.documentElement.setAttribute("data-theme", id);
  document.documentElement.setAttribute("data-scheme", scheme);
}

/** Ist das tatsächlich angezeigte Theme dunkel? (für Hell/Dunkel-Umschalter) */
export function istDunkel(mode: ThemeMode): boolean {
  return aufloesen(mode).scheme === "dark";
}

function gespeichert(): ThemeMode {
  const wert = localStorage.getItem("dm_theme");
  return wert && (wert === "system" || findeTheme(wert)) ? wert : "dark";
}

export function useTheme() {
  const [mode, setMode] = useState<ThemeMode>(gespeichert);

  useEffect(() => {
    applyTheme(mode);
    localStorage.setItem("dm_theme", mode);
  }, [mode]);

  // Systemthema-Änderungen live mitverfolgen
  useEffect(() => {
    if (mode !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => applyTheme("system");
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [mode]);

  return { mode, setMode };
}

// Beim ersten Laden sofort anwenden (verhindert Flash)
applyTheme(gespeichert());
