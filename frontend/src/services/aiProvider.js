/**
 * Gewählter KI-Anbieter für die laufende Sitzung.
 *
 * Die globale Einstellung (Systemeinstellungen → KI) bleibt davon unberührt –
 * die Wahl gilt nur für die eigenen Anfragen dieses Browsers und wird jedem
 * KI-Stream als `provider` mitgeschickt (Backend: _require_ai). Genau wie im
 * Schema-Katalog, nur eben dauerhaft statt pro Lauf.
 */
const KEY = "dm_ai_provider";
const ERLAUBT = ["ollama", "datenmonster"];
const horcher = new Set();

export function getAiProvider() {
  try {
    const v = localStorage.getItem(KEY);
    return ERLAUBT.includes(v) ? v : null;   // null = globale Einstellung nutzen
  } catch {
    return null;                              // Privater Modus o.ä.
  }
}

export function setAiProvider(v) {
  try {
    if (ERLAUBT.includes(v)) localStorage.setItem(KEY, v);
    else localStorage.removeItem(KEY);
  } catch { /* Speicher nicht verfügbar – Wahl gilt dann nur für diesen Aufruf */ }
  horcher.forEach(fn => fn(getAiProvider()));
}

/** Meldet sich an Änderungen an (z.B. Kopfzeile ↔ andere Ansicht). */
export function onAiProviderChange(fn) {
  horcher.add(fn);
  return () => horcher.delete(fn);
}
