import { useEffect, useState } from "react";
import { Sun, Moon, Sparkles } from "lucide-react";
import api from "../../api/client";
import { useTheme } from "../../hooks/useTheme";

const S = {
  border: "var(--border)", textDim: "var(--text-dim)", textBright: "var(--text-bright)",
  accent: "var(--accent)", bgEl: "var(--bg-elevated)",
};
const ACCENT = "#fce499";

/** Hell/Dunkel umschalten. Nutzt denselben Speicher wie der Editor (dm_theme),
 *  d.h. die Wahl gilt geräteweit und bleibt nach dem Abmelden erhalten. */
export function ThemeUmschalter() {
  const { mode, setMode } = useTheme();
  // Aus dem Zustand ableiten, nicht aus dem DOM: das Attribut wird erst im Effekt
  // gesetzt, die Beschriftung hinkte sonst einen Klick hinterher.
  const dunkel = mode === "dark"
    || (mode === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  return (
    <button
      onClick={() => setMode(dunkel ? "light" : "dark")}
      title={dunkel ? "Zur hellen Ansicht wechseln" : "Zur dunklen Ansicht wechseln"}
      aria-label={dunkel ? "Helle Ansicht" : "Dunkle Ansicht"}
      style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 9px",
        borderRadius: 7, border: `1px solid ${S.border}`, backgroundColor: "transparent",
        color: S.textDim, cursor: "pointer", fontSize: 11.5 }}>
      {dunkel ? <Sun size={13} /> : <Moon size={13} />}
      {dunkel ? "Hell" : "Dunkel"}
    </button>
  );
}

/** Verbleibendes KI-Guthaben. Zeigt sich nur, wenn die Instanz überhaupt über
 *  Datenmonster AI läuft — bei eigener Ollama-Installation gibt es keine Credits.
 *  Fehler bleiben still: im Portal soll kein Gateway-Problem den Kopf belegen. */
export function KiCredits() {
  const [daten, setDaten] = useState(null);

  useEffect(() => {
    let aktiv = true;
    api.get("/api/ai/credits")
      .then(({ data }) => { if (aktiv) setDaten(data); })
      .catch(() => {});
    return () => { aktiv = false; };
  }, []);

  if (!daten?.enabled || daten.error || daten.balance === undefined
      || daten.balance === null) return null;

  const knapp = Number(daten.balance) <= 0;
  const farbe = knapp ? "#e07070" : ACCENT;
  const verbrauch = daten.month
    ? `Diesen Monat verbraucht: ${daten.month.credits_used ?? 0} Credits `
      + `in ${daten.month.requests ?? 0} Anfragen`
    : "KI-Guthaben dieser Lizenz";

  return (
    <span title={verbrauch}
      style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "4px 10px",
        borderRadius: 20, backgroundColor: `${farbe}14`, border: `1px solid ${farbe}44`,
        whiteSpace: "nowrap" }}>
      <Sparkles size={12} style={{ color: farbe }} />
      <span style={{ fontSize: 12, fontWeight: 700, color: farbe }}>
        {Number(daten.balance).toLocaleString("de-DE")}
      </span>
      <span style={{ fontSize: 11, color: S.textDim }}>
        {knapp ? "Credits – aufgebraucht" : "Credits"}
      </span>
    </span>
  );
}
