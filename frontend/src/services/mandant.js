import api from "../api/client";

/**
 * Der aktive Mandant – also die JTL-Datenbank, die die Cockpits gerade auswerten.
 *
 * Anders als die KI-Anbieterwahl liegt hier NICHTS im Browser: der Server kennt
 * die Wahl je Benutzer und löst sie bei jedem Lauf selbst auf. Diese Datei hält
 * nur eine Kopie für die Anzeige und benachrichtigt die Oberfläche, wenn
 * umgeschaltet wurde. So kann es keinen zweiten, unsichtbaren Zustand geben, der
 * die serverseitige Wahl still übersteuert.
 */

const listeners = new Set();
const cache = new Map();          // project_id → { aktiv, mandanten }

const schluessel = (projectId) => (projectId == null ? "null" : String(projectId));

/** Mandanten eines Projekts laden (aus dem Zwischenspeicher, sofern vorhanden). */
export async function ladeMandanten(projectId, { frisch = false } = {}) {
  const k = schluessel(projectId);
  if (!frisch && cache.has(k)) return cache.get(k);
  try {
    const q = projectId != null ? `?project_id=${projectId}` : "";
    const { data } = await api.get(`/api/mandanten${q}`);
    const stand = { aktiv: data.aktiv ?? null, mandanten: data.mandanten || [] };
    cache.set(k, stand);
    return stand;
  } catch {
    // Kein Zugriff oder alter Server: dann gibt es eben keine Mandantenwahl.
    const leer = { aktiv: null, mandanten: [] };
    cache.set(k, leer);
    return leer;
  }
}

/** Mandant wechseln. Der Rückgabewert ist der jetzt aktive Mandant. */
export async function setzeMandant(projectId, connectionId) {
  const { data } = await api.put("/api/mandanten/aktiv", {
    project_id: projectId ?? null, connection_id: connectionId,
  });
  const k = schluessel(projectId);
  const stand = cache.get(k) || { mandanten: [] };
  cache.set(k, { ...stand, aktiv: data.aktiv });
  listeners.forEach(fn => { try { fn(projectId, data.aktiv); } catch { /* egal */ } });
  return data.aktiv;
}

/** Auf Mandantenwechsel horchen. Gibt die Abmeldefunktion zurück. */
export function onMandantChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function mandantAusCache(projectId) {
  return cache.get(schluessel(projectId)) || null;
}
