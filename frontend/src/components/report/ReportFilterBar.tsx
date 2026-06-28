import { useState, useEffect } from "react";
import { Filter, X, RefreshCw } from "lucide-react";
import api from "../../api/client";
import { S } from "./constants";

const ACCENT = "#fce499";

// Erkennt den Filter-Typ anhand der Werte
function detectFilterType(values) {
  if (!values?.length) return "text";
  // Datum-Erkennung
  if (values.every(v => /^\d{4}-\d{2}-\d{2}/.test(String(v)))) return "daterange";
  // Zahl-Bereich wenn viele verschiedene numerische Werte
  if (values.every(v => !isNaN(parseFloat(v))) && new Set(values).size > 20) return "numberrange";
  // Dropdown wenn wenige DISTINCT-Werte
  if (new Set(values).size <= 100) return "select";
  // Freitext
  return "text";
}

function DateRangeFilter({ field, label, value, onChange }) {
  const val = value || {};
  return (
    <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
      <span style={{ fontSize: 10, color: S.textDim, whiteSpace: "nowrap" }}>{label}:</span>
      <input type="date" value={val.from || ""} onChange={e => onChange({ ...val, from: e.target.value })}
        style={{ backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 3, color: S.textBright, fontSize: 10, padding: "3px 6px", outline: "none" }} />
      <span style={{ fontSize: 10, color: S.textDim }}>–</span>
      <input type="date" value={val.to || ""} onChange={e => onChange({ ...val, to: e.target.value })}
        style={{ backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 3, color: S.textBright, fontSize: 10, padding: "3px 6px", outline: "none" }} />
    </div>
  );
}

function SelectFilter({ field, label, options, value, onChange, multi }) {
  return (
    <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
      <span style={{ fontSize: 10, color: S.textDim, whiteSpace: "nowrap" }}>{label}:</span>
      <select value={value || ""} onChange={e => onChange(e.target.value)}
        style={{ backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 3, color: S.textBright, fontSize: 10, padding: "3px 6px", outline: "none", maxWidth: 160 }}>
        <option value="">Alle</option>
        {options.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  );
}

function TextFilter({ field, label, value, onChange }) {
  return (
    <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
      <span style={{ fontSize: 10, color: S.textDim, whiteSpace: "nowrap" }}>{label}:</span>
      <input value={value || ""} onChange={e => onChange(e.target.value)} placeholder="Suche..."
        style={{ backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 3, color: S.textBright, fontSize: 10, padding: "3px 6px", outline: "none", width: 120 }} />
    </div>
  );
}

export default function ReportFilterBar({ widgets, filters, onChange, onRefresh }) {
  const [filterDefs, setFilterDefs] = useState([]);
  const [filterOptions, setFilterOptions] = useState({});

  // Sammle alle Filter-Felder aus allen Widgets
  useEffect(() => {
    const allFilters = [];
    const seen = new Set();
    widgets.forEach(w => {
      (w.config?.filter_fields || []).forEach(f => {
        if (!seen.has(f.field)) {
          seen.add(f.field);
          allFilters.push({ ...f, dataset_id: w.config?.dataset_id });
        }
      });
    });
    setFilterDefs(allFilters);

    // Optionen für Select-Filter laden
    allFilters.forEach(async (f) => {
      if (f.dataset_id && !filterOptions[f.field]) {
        try {
          const { data } = await api.get(`/api/reports/filter-options`, {
            params: { dataset_id: f.dataset_id, field: f.field }
          });
          setFilterOptions(prev => ({ ...prev, [f.field]: data.values || [] }));
        } catch (e) {}
      }
    });
  }, [widgets]);

  if (filterDefs.length === 0) return null;

  const hasActiveFilters = Object.values(filters || {}).some(v => v && (typeof v !== "object" || v.from || v.to));

  return (
    <div style={{ padding: "8px 16px", backgroundColor: S.bgCard, borderBottom: `1px solid ${S.border}`, display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 5, flexShrink: 0 }}>
        <Filter size={12} style={{ color: ACCENT }} />
        <span style={{ fontSize: 10, fontWeight: 700, color: ACCENT, textTransform: "uppercase", letterSpacing: "0.06em" }}>Filter</span>
      </div>

      {filterDefs.map(f => {
        const options = filterOptions[f.field] || [];
        const type = f.type === "auto" ? detectFilterType(options) : f.type;
        const val = filters?.[f.field];

        if (type === "daterange") {
          return <DateRangeFilter key={f.field} field={f.field} label={f.label || f.field}
            value={val} onChange={v => onChange({ ...filters, [f.field]: v })} />;
        }
        if (type === "select") {
          return <SelectFilter key={f.field} field={f.field} label={f.label || f.field}
            options={options} value={val} onChange={v => onChange({ ...filters, [f.field]: v })} />;
        }
        return <TextFilter key={f.field} field={f.field} label={f.label || f.field}
          value={val} onChange={v => onChange({ ...filters, [f.field]: v })} />;
      })}

      <div style={{ display: "flex", gap: 6, marginLeft: "auto" }}>
        {hasActiveFilters && (
          <button onClick={() => onChange({})}
            style={{ display: "flex", alignItems: "center", gap: 4, padding: "3px 8px", borderRadius: 3, border: `1px solid ${S.border}`, background: "none", color: S.textDim, cursor: "pointer", fontSize: 10 }}>
            <X size={10} /> Zurücksetzen
          </button>
        )}
        <button onClick={onRefresh}
          style={{ display: "flex", alignItems: "center", gap: 4, padding: "3px 10px", borderRadius: 3, border: `1px solid ${ACCENT}44`, backgroundColor: `${ACCENT}15`, color: ACCENT, cursor: "pointer", fontSize: 10, fontWeight: 600 }}>
          <RefreshCw size={10} /> Anwenden
        </button>
      </div>
    </div>
  );
}
