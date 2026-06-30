import { useEffect, useState } from "react";

export type ThemeMode = "dark" | "light" | "system";

function applyTheme(mode: ThemeMode) {
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const useDark = mode === "dark" || (mode === "system" && prefersDark);
  document.documentElement.setAttribute("data-theme", useDark ? "dark" : "light");
}

export function useTheme() {
  const [mode, setMode] = useState<ThemeMode>(
    () => (localStorage.getItem("dm_theme") as ThemeMode) || "dark"
  );

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
const saved = (localStorage.getItem("dm_theme") as ThemeMode) || "dark";
applyTheme(saved);
