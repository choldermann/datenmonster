import {
  ArrowRight, Hash, Calendar, Type, GitBranch,
} from "lucide-react";

export const S = {
  accent: "var(--accent)", bgMain: "var(--bg-main)", bgCard: "var(--bg-card)",
  bgEl: "var(--bg-elevated)", border: "var(--border)", textMain: "var(--text-main)",
  textBright: "var(--text-bright)", textDim: "var(--text-dim)",
};

export const TRANSFORMER_TYPES = [
  { value: "direct",    label: "Direct",    icon: ArrowRight, color: "#6ee7b7" },
  { value: "formula",   label: "Formel",    icon: Hash,       color: "#fce499" },
  { value: "constant",  label: "Konstante", icon: Type,       color: "#93c5fd" },
  { value: "date",      label: "Datum",     icon: Calendar,   color: "#f9a8d4" },
  { value: "condition", label: "Bedingung", icon: GitBranch,  color: "#c4b5fd" },
];

export const JOIN_TYPES = [
  { value: "INNER JOIN",       label: "INNER",      short: "⋈" },
  { value: "LEFT JOIN",        label: "LEFT",       short: "⟕" },
  { value: "RIGHT JOIN",       label: "RIGHT",      short: "⟖" },
  { value: "FULL OUTER JOIN",  label: "FULL",       short: "⟗" },
  { value: "LEFT ANTI JOIN",   label: "LEFT ANTI",  short: "⊳" },
  { value: "RIGHT ANTI JOIN",  label: "RIGHT ANTI", short: "⊲" },
];

export const JOIN_COLOR    = "#f97316";
export const FILTER_COLOR  = "#a78bfa";
export const SORT_COLOR    = "#34d399";
export const SQL_NODE_COLOR = "#38bdf8";
export const AGG_COLOR     = "#f59e0b";

export const DATE_FORMATS = ["YYYY-MM-DD", "DD.MM.YYYY", "YYYYMMDD", "MM/DD/YYYY", "DD/MM/YYYY"];

export const typeColor = {
  csv: "#6ee7b7", xlsx: "#93c5fd", xml: "#fcd34d",
  db_mssql: "#c4b5fd", db_mysql: "#6ee7b7",
};

export const TARGET_TYPE_COLORS = {
  csv: "#6ee7b7", xlsx: "#93c5fd", json: "#fce499", xml: "#fcd34d", db: "#f97316",
  estatistik_intrastat: "#c4b5fd",
};
export const PLUGIN_TARGET_DEFAULT_COLOR = "#a78bfa";

export const TARGET_TYPES = [
  { value: "csv",  label: "CSV" },
  { value: "xlsx", label: "Excel" },
  { value: "json", label: "JSON" },
  { value: "xml",  label: "XML" },
  { value: "db",   label: "Datenbank" },
];

export const CONST_TYPES = [
  { value: "static_text",       label: "Text",            icon: "T",  color: "#93c5fd", preview: (v) => `"${v || ""}"` },
  { value: "static_number",     label: "Zahl",            icon: "#",  color: "#6ee7b7", preview: (v) => v || "0" },
  { value: "current_date",      label: "Aktuelles Datum", icon: "📅", color: "#fcd34d", preview: () => new Date().toLocaleDateString("de-DE") },
  { value: "current_datetime",  label: "Datum + Uhrzeit", icon: "🕐", color: "#fbbf24", preview: () => new Date().toLocaleString("de-DE") },
  { value: "current_year",      label: "Aktuelles Jahr",  icon: "Y",  color: "#fcd34d", preview: () => new Date().getFullYear().toString() },
  { value: "uuid",              label: "UUID (zufällig)", icon: "⬡",  color: "#c4b5fd", preview: () => "xxxxxxxx-xxxx-4xxx-…" },
  { value: "static_bool_true",  label: "true",            icon: "✓",  color: "#6ee7b7", preview: () => "true" },
  { value: "static_bool_false", label: "false",           icon: "✗",  color: "#e07070", preview: () => "false" },
];
export const AGG_FUNCTIONS = [
  { v: "sum",            l: "SUM" },
  { v: "count",          l: "COUNT" },
  { v: "count_distinct", l: "COUNT DISTINCT" },
  { v: "avg",            l: "AVG" },
  { v: "min",            l: "MIN" },
  { v: "max",            l: "MAX" },
  { v: "stddev",         l: "STDDEV" },
  { v: "median",         l: "MEDIAN" },
  { v: "first",          l: "FIRST" },
  { v: "last",           l: "LAST" },
  { v: "group_by",       l: "GROUP BY" },
];
