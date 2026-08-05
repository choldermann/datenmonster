// Baut einen kompakten Kontext aus den aktuell angezeigten Dashboard-Ergebnissen
// für den KI-Assistenten (pageContext.currentData → landet im Chat-Prompt).
// Bewusst klein gehalten (Backend kürzt den Kontext bei ~4000 Zeichen): nur der
// aktive Ergebnis-Reiter, wenige Beispielzeilen pro Widget.

const MAX_ROWS = 6;

export function buildDashboardContext(widgets = [], actions = [], resultTabs = [],
  formName = "Dashboard", results = null, params = {}, activeTab = null) {
  if (!results) return null;

  const curTabId = activeTab || resultTabs[0]?.id || null;
  const curTab = resultTabs.find(t => t.id === curTabId) || null;
  const tabActionIds = resultTabs.length
    ? new Set((curTab?.action_ids) || [])
    : null;

  // Sprechendes Label je Action (bevorzugt Widget-Label).
  const labelByAction = {};
  for (const a of actions) labelByAction[a.id] = a.label || a.id;
  for (const w of widgets) {
    if (w.action_id && w.label) labelByAction[w.action_id] = w.label;
  }

  const ergebnisse = {};
  for (const [aid, res] of Object.entries(results)) {
    if (tabActionIds && !tabActionIds.has(aid)) continue;
    if (!res || !Array.isArray(res.rows) || !res.rows.length) continue;
    const label = labelByAction[aid] || aid;
    ergebnisse[label] = {
      spalten: res.columns || Object.keys(res.rows[0] || {}),
      zeilen: res.rows.slice(0, MAX_ROWS),
      gesamt: res.total,
    };
  }

  // Nur nicht-leere Filter mitgeben.
  const filter = {};
  for (const [k, v] of Object.entries(params || {})) {
    if (v === "" || v == null || (Array.isArray(v) && v.length === 0)) continue;
    filter[k] = v;
  }

  return {
    page: "form_dashboard",
    title: formName || "Dashboard",
    currentData: {
      dashboard: formName,
      aktiverReiter: curTab?.label || null,
      filter,
      ergebnisse,
    },
  };
}
