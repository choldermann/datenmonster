export const S = {
  accent: "var(--accent)",
  bgMain: "var(--bg-main)",
  bgCard: "var(--bg-card)",
  bgEl: "var(--bg-elevated)",
  border: "var(--border)",
  textMain: "var(--text-main)",
  textBright: "var(--text-bright)",
  textDim: "var(--text-dim)",
};

export const WIDGET_TYPES = [
  { type: "kpi",      label: "KPI",           icon: "📊", desc: "Einzelne Kennzahl",     defaultW: 3, defaultH: 2 },
  { type: "bar",      label: "Balken",         icon: "📈", desc: "Balkendiagramm",        defaultW: 6, defaultH: 4 },
  { type: "line",     label: "Linie",          icon: "📉", desc: "Liniendiagramm",        defaultW: 6, defaultH: 4 },
  { type: "pie",      label: "Torte/Donut",    icon: "🥧", desc: "Tortendiagramm",        defaultW: 4, defaultH: 4 },
  { type: "table",    label: "Tabelle",        icon: "📋", desc: "Tabelle mit Summen",    defaultW: 12, defaultH: 5 },
  { type: "heatmap",  label: "Heatmap",        icon: "🗓️", desc: "Kalender-Heatmap",     defaultW: 12, defaultH: 4 },
];

export const AGG_FUNCTIONS = [
  { v: "SUM",   l: "Summe" },
  { v: "COUNT", l: "Anzahl" },
  { v: "AVG",   l: "Durchschnitt" },
  { v: "MIN",   l: "Minimum" },
  { v: "MAX",   l: "Maximum" },
];

export const CHART_COLORS = [
  "#fce499", "#38bdf8", "#6ee7b7", "#f97316",
  "#a78bfa", "#f472b6", "#34d399", "#fb923c",
];

export const GRID_COLS = 12;
export const ROW_HEIGHT = 60; // px pro Grid-Zeile
