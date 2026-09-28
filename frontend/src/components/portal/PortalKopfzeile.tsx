import { useEffect, useRef, useState } from "react";
import type React from "react";
import { Sparkles, Cpu, Palette, Check } from "lucide-react";
import api from "../../api/client";
import { useTheme } from "../../hooks/useTheme";
import { THEMES, GRUPPEN, findeTheme } from "../../themes";
import { getAiProvider, setAiProvider, onAiProviderChange } from "../../services/aiProvider";

const S = {
  border: "var(--border)", textDim: "var(--text-dim)", textBright: "var(--text-bright)",
  accent: "var(--accent)", bgEl: "var(--bg-elevated)",
};
const ACCENT = "var(--accent)";

/** Farbschema wählen – dieselbe Auswahl wie in den Systemeinstellungen, damit
 *  auch reine Portal-Benutzer ihr Theme bekommen. Gespeichert wird im Konto. */
export function ThemeUmschalter() {
  const { mode, setMode } = useTheme();
  const [offen, setOffen] = useState(false);
  const rahmen = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!offen) return;
    const zu = (e: MouseEvent) => { if (!rahmen.current?.contains(e.target as Node)) setOffen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOffen(false); };
    document.addEventListener("mousedown", zu);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", zu); document.removeEventListener("keydown", esc); };
  }, [offen]);

  const name = mode === "system" ? "System" : (findeTheme(mode)?.label || "Dunkel");
  const eintrag = (wert: string, label: string, farbfeld: React.ReactNode) => {
    const aktiv = mode === wert;
    return (
      <button key={wert} onClick={() => { setMode(wert); setOffen(false); }}
        style={{ display: "flex", alignItems: "center", gap: 9, width: "100%", padding: "6px 8px",
          borderRadius: 6, border: "none", cursor: "pointer", textAlign: "left", fontSize: 12,
          backgroundColor: aktiv ? "var(--accent-dim)" : "transparent",
          color: aktiv ? ACCENT : S.textBright }}>
        {farbfeld}
        <span style={{ flex: 1 }}>{label}</span>
        {aktiv && <Check size={13} />}
      </button>
    );
  };

  return (
    <div ref={rahmen} style={{ position: "relative" }}>
      <button onClick={() => setOffen(o => !o)} title="Farbschema wählen" aria-label="Farbschema wählen"
        aria-expanded={offen}
        style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 9px",
          borderRadius: 7, border: `1px solid ${S.border}`, backgroundColor: "transparent",
          color: S.textDim, cursor: "pointer", fontSize: 11.5 }}>
        <Palette size={13} />
        {name}
      </button>
      {offen && (
        <div style={{ position: "absolute", right: 0, top: "calc(100% + 6px)", zIndex: 1000, width: 230,
          maxHeight: "70vh", overflowY: "auto", padding: 6, borderRadius: 8,
          backgroundColor: "var(--bg-card)", border: `1px solid ${S.border}`,
          boxShadow: "0 12px 32px rgba(0,0,0,0.35)" }}>
          {GRUPPEN.map(g => (
            <div key={g.id} style={{ marginBottom: 4 }}>
              <div className="label" style={{ padding: "6px 8px 2px", marginBottom: 0 }}>{g.label}</div>
              {THEMES.filter(t => t.gruppe === g.id).map(t => eintrag(t.id, t.label, <Farbfeld id={t.id} />))}
              {g.id === "klassisch" && eintrag("system", "System",
                <span style={{ display: "flex" }}><Farbfeld id="light" halb /><Farbfeld id="dark" halb /></span>)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Kleines Farbmuster eines Themes (Hintergrund, Karte, Akzent). */
function Farbfeld({ id, halb = false }: { id: string; halb?: boolean }) {
  return (
    <span data-theme={id} style={{ display: "flex", alignItems: "center", gap: 2, padding: 3,
      width: halb ? 17 : 34, height: 20, overflow: "hidden", flexShrink: 0,
      backgroundColor: "var(--bg-main)", border: "1px solid var(--border)", borderRadius: 4 }}>
      <span style={{ width: 12, height: 12, flexShrink: 0, backgroundColor: "var(--bg-card)", border: "1px solid var(--border)" }} />
      <span style={{ width: 12, height: 12, flexShrink: 0, backgroundColor: "var(--accent)" }} />
    </span>
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
  const farbe = knapp ? "var(--err-soft)" : ACCENT;
  // Was gilt gerade? Ohne eigene Wahl entscheidet die globale Einstellung (daten.enabled).
  const aktiv = provider || (daten.enabled ? "datenmonster" : "ollama");
  const verbrauch = daten.month
    ? `Diesen Monat verbraucht: ${daten.month.credits_used ?? 0} Credits `
      + `in ${daten.month.requests ?? 0} Anfragen`
    : "KI-Guthaben dieser Lizenz";

  const knopf = (wert, text, titel) => (
    <button key={wert} onClick={() => { setAiProvider(wert); setProvider(wert); }} title={titel}
      style={{ border: "none", padding: "4px 9px", fontSize: 11, cursor: "pointer",
        backgroundColor: aktiv === wert ? `color-mix(in srgb, ${ACCENT} 13.3%, transparent)` : "transparent",
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
          borderRadius: 20, backgroundColor: `color-mix(in srgb, ${farbe} 7.8%, transparent)`, border: `1px solid color-mix(in srgb, ${farbe} 26.7%, transparent)`,
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
