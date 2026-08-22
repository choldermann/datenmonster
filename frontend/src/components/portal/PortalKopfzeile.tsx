import { useEffect, useState } from "react";
import { Sun, Moon, Sparkles, Cpu } from "lucide-react";
import api from "../../api/client";
import { useTheme } from "../../hooks/useTheme";
import { getAiProvider, setAiProvider, onAiProviderChange } from "../../services/aiProvider";

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

/** KI-Anbieter + verbleibendes Guthaben.
 *
 *  Zeigt das Guthaben, sobald die Lizenz überhaupt eines hat – auch wenn global
 *  Ollama eingestellt ist (sonst sieht man im Portal nie, was noch da ist). Steht
 *  Guthaben zur Verfügung, kann der Benutzer je Sitzung zwischen dem lokalen Modell
 *  und Datenmonster AI wählen; die globale Einstellung bleibt unberührt.
 *  Fehler bleiben still: im Portal soll kein Gateway-Problem den Kopf belegen. */
export function KiCredits() {
  const [daten, setDaten] = useState(null);
  const [provider, setProvider] = useState(getAiProvider());

  useEffect(() => {
    let aktiv = true;
    api.get("/api/ai/credits")
      .then(({ data }) => { if (aktiv) setDaten(data); })
      .catch(() => {});
    return () => { aktiv = false; };
  }, []);

  // Wahl kann auch anderswo geändert werden – Anzeige mitziehen.
  useEffect(() => onAiProviderChange(setProvider), []);

  if (!daten || daten.error || daten.balance === undefined || daten.balance === null) return null;

  const guthaben = Number(daten.balance);
  const knapp = guthaben <= 0;
  const farbe = knapp ? "#e07070" : ACCENT;
  // Was gilt gerade? Ohne eigene Wahl entscheidet die globale Einstellung (daten.enabled).
  const aktiv = provider || (daten.enabled ? "datenmonster" : "ollama");
  const verbrauch = daten.month
    ? `Diesen Monat verbraucht: ${daten.month.credits_used ?? 0} Credits `
      + `in ${daten.month.requests ?? 0} Anfragen`
    : "KI-Guthaben dieser Lizenz";

  const knopf = (wert, text, titel) => (
    <button key={wert} onClick={() => { setAiProvider(wert); setProvider(wert); }} title={titel}
      style={{ border: "none", padding: "4px 9px", fontSize: 11, cursor: "pointer",
        backgroundColor: aktiv === wert ? `${ACCENT}22` : "transparent",
        color: aktiv === wert ? S.textBright : S.textDim,
        fontWeight: aktiv === wert ? 600 : 400 }}>
      {text}
    </button>
  );

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
      {guthaben > 0 && (
        <span style={{ display: "inline-flex", alignItems: "center",
          border: `1px solid ${S.border}`, borderRadius: 7, overflow: "hidden" }}>
          {knopf("ollama", <><Cpu size={11} style={{ verticalAlign: "-1px", marginRight: 4 }} />Lokal</>,
                 "Lokales Modell – kostenlos, aber langsamer")}
          {knopf("datenmonster", "Datenmonster AI", "Schnelleres Modell über Datenmonster AI – verbraucht Credits")}
        </span>
      )}
      <span title={verbrauch}
        style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "4px 10px",
          borderRadius: 20, backgroundColor: `${farbe}14`, border: `1px solid ${farbe}44`,
          whiteSpace: "nowrap", opacity: aktiv === "datenmonster" ? 1 : 0.65 }}>
        <Sparkles size={12} style={{ color: farbe }} />
        <span style={{ fontSize: 12, fontWeight: 700, color: farbe }}>
          {guthaben.toLocaleString("de-DE")}
        </span>
        <span style={{ fontSize: 11, color: S.textDim }}>
          {knapp ? "Credits – aufgebraucht" : "Credits"}
        </span>
      </span>
    </span>
  );
}
