import { useState, useEffect } from "react";
import { X, Plus, Trash2, RefreshCw } from "lucide-react";
import { S, AGG_FUNCTIONS, WIDGET_TYPES } from "./constants";
import api from "../../api/client";

const ACCENT = "#fce499";

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <p style={{ fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 700, marginBottom: 8 }}>{title}</p>
      {children}
    </div>
  );
}

export default function WidgetConfigPanel({ widget, datasets, onUpdate, onRemove, onClose }) {
  const [columns, setColumns] = useState([]);
  const [loadingCols, setLoadingCols] = useState(false);
  const config = widget.config || {};
  const set = (k, v) => onUpdate({ ...widget, config: { ...config, [k]: v } });
  const setTitle = (v) => onUpdate({ ...widget, title: v });

  const wtype = WIDGET_TYPES.find(w => w.type === widget.type);

  const iS = { backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 3, color: S.textBright, fontSize: 10, padding: "3px 6px", outline: "none", width: "100%" };

  // Spalten laden wenn Datenquelle sich ändert
  useEffect(() => {
    if (!config.dataset_id && !config.sql) { setColumns([]); return; }
    if (config.dataset_id) {
      // Spalten aus bereits geladenem datasets Array
      const ds = (datasets || []).find(d => d.id === config.dataset_id);
      if (ds?.columns?.length) {
        setColumns(ds.columns);
        return;
      }
      // Fallback: column_types
      if (ds?.column_types) {
        setColumns(Object.keys(ds.column_types));
        return;
      }
    }
    if (config.sql) {
      setLoadingCols(true);
      api.post("/api/reports/sql-columns", { sql: config.sql, connection_id: config.connection_id })
        .then(({ data }) => setColumns(data.columns || []))
        .catch(() => setColumns([]))
        .finally(() => setLoadingCols(false));
    }
  }, [config.dataset_id, config.sql, datasets]);

  // Wert-Felder (Mehrfach)
  const valueFields = config.value_fields || [];
  const toggleValueField = (col) => {
    const next = valueFields.includes(col) ? valueFields.filter(f => f !== col) : [...valueFields, col];
    set("value_fields", next);
  };

  return (
    <div style={{ width: 260, flexShrink: 0, backgroundColor: S.bgCard, borderLeft: `1px solid ${S.border}`, display: "flex", flexDirection: "column", overflowY: "auto" }}>
      {/* Header */}
      <div style={{ padding: "10px 14px", borderBottom: `1px solid ${S.border}`, display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 14 }}>{wtype?.icon}</span>
        <span style={{ fontSize: 11, fontWeight: 700, color: S.textBright, flex: 1 }}>{wtype?.label} konfigurieren</span>
        <button onClick={onClose} style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer" }}><X size={12} /></button>
      </div>

      <div style={{ padding: "12px 14px", flex: 1 }}>

        {/* Titel */}
        <Section title="Titel">
          <input style={iS} value={widget.title || ""} onChange={e => setTitle(e.target.value)} placeholder="Widget-Titel" />
        </Section>

        {/* Datenquelle */}
        <Section title="Datenquelle">
          <div style={{ display: "flex", gap: 4, marginBottom: 6 }}>
            {["dataset", "sql"].map(t => (
              <button key={t} onClick={() => set("source_type", t)}
                style={{ flex: 1, padding: "3px 6px", borderRadius: 3, fontSize: 9, fontWeight: 700, cursor: "pointer", border: `1px solid ${(config.source_type || "dataset") === t ? ACCENT : S.border}`, backgroundColor: (config.source_type || "dataset") === t ? ACCENT + "20" : "transparent", color: (config.source_type || "dataset") === t ? ACCENT : S.textDim }}>
                {t === "dataset" ? "Dataset" : "SQL"}
              </button>
            ))}
          </div>

          {(config.source_type || "dataset") === "dataset" ? (
            <select style={iS} value={config.dataset_id || ""} onChange={e => set("dataset_id", parseInt(e.target.value) || null)}>
              <option value="">— Dataset wählen —</option>
              {(datasets || []).map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          ) : (
            <>
              <select style={{ ...iS, marginBottom: 4 }} value={config.connection_id || ""} onChange={e => set("connection_id", parseInt(e.target.value) || null)}>
                <option value="">— DB-Connector wählen —</option>
                {(datasets || []).filter(d => d.connection_id).map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
              <textarea style={{ ...iS, resize: "vertical", minHeight: 80, fontFamily: "monospace", fontSize: 10 }}
                value={config.sql || ""} onChange={e => set("sql", e.target.value)}
                placeholder="SELECT spalte, SUM(wert) FROM tabelle GROUP BY spalte" />
            </>
          )}

          {loadingCols && <p style={{ fontSize: 9, color: S.textDim, marginTop: 4 }}>Lade Spalten...</p>}
        </Section>

        {/* Felder - je nach Widget-Typ */}
        {columns.length > 0 && (
          <>
            {/* X-Achse / Label */}
            {["bar", "line", "pie", "heatmap", "table"].includes(widget.type) && (
              <Section title={widget.type === "pie" ? "Label-Spalte" : widget.type === "heatmap" ? "Datum-Spalte" : widget.type === "table" ? "Spalten auswählen" : "X-Achse"}>
                {widget.type === "table" ? (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                    {columns.map(c => (
                      <button key={c} onClick={() => {
                        const cols = config.columns || [];
                        set("columns", cols.includes(c) ? cols.filter(x => x !== c) : [...cols, c]);
                      }}
                        style={{ padding: "2px 6px", borderRadius: 3, fontSize: 9, cursor: "pointer", border: `1px solid ${(config.columns || []).includes(c) ? ACCENT : S.border}`, backgroundColor: (config.columns || []).includes(c) ? ACCENT + "20" : "transparent", color: (config.columns || []).includes(c) ? ACCENT : S.textDim }}>
                        {c}
                      </button>
                    ))}
                  </div>
                ) : (
                  <select style={iS} value={config[widget.type === "pie" ? "label_field" : widget.type === "heatmap" ? "date_field" : "x_field"] || ""}
                    onChange={e => set(widget.type === "pie" ? "label_field" : widget.type === "heatmap" ? "date_field" : "x_field", e.target.value)}>
                    <option value="">— Spalte wählen —</option>
                    {columns.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                )}
              </Section>
            )}

            {/* Wert-Spalten */}
            {["bar", "line", "kpi"].includes(widget.type) && (
              <Section title={widget.type === "kpi" ? "Wert-Spalte" : "Wert-Spalten"}>
                {widget.type === "kpi" ? (
                  <select style={iS} value={config.value_field || ""} onChange={e => set("value_field", e.target.value)}>
                    <option value="">— Spalte wählen —</option>
                    {columns.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                ) : (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                    {columns.map(c => (
                      <button key={c} onClick={() => toggleValueField(c)}
                        style={{ padding: "2px 6px", borderRadius: 3, fontSize: 9, cursor: "pointer", border: `1px solid ${valueFields.includes(c) ? ACCENT : S.border}`, backgroundColor: valueFields.includes(c) ? ACCENT + "20" : "transparent", color: valueFields.includes(c) ? ACCENT : S.textDim }}>
                        {c}
                      </button>
                    ))}
                  </div>
                )}
              </Section>
            )}

            {widget.type === "pie" && (
              <Section title="Wert-Spalte">
                <select style={iS} value={config.value_field || ""} onChange={e => set("value_field", e.target.value)}>
                  <option value="">— Spalte wählen —</option>
                  {columns.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </Section>
            )}

            {widget.type === "heatmap" && (
              <Section title="Wert-Spalte">
                <select style={iS} value={config.value_field || ""} onChange={e => set("value_field", e.target.value)}>
                  <option value="">— Spalte (leer = Anzahl) —</option>
                  {columns.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </Section>
            )}

            {/* Filter-Spalten */}
            <Section title="Als Filter anbieten">
              <p style={{ fontSize: 9, color: S.textDim, marginBottom: 6 }}>Diese Spalten erscheinen als Filter in der Report-Leiste</p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                {columns.map(c => {
                  const filters = config.filter_fields || [];
                  const active = filters.some(f => f.field === c);
                  return (
                    <button key={c} onClick={() => {
                      const filters = config.filter_fields || [];
                      if (active) {
                        set("filter_fields", filters.filter(f => f.field !== c));
                      } else {
                        set("filter_fields", [...filters, { field: c, label: c, type: "auto" }]);
                      }
                    }}
                      style={{ padding: "2px 6px", borderRadius: 3, fontSize: 9, cursor: "pointer", border: `1px solid ${active ? "#38bdf8" : S.border}`, backgroundColor: active ? "rgba(56,189,248,0.15)" : "transparent", color: active ? "#38bdf8" : S.textDim }}>
                      🔍 {c}
                    </button>
                  );
                })}
              </div>
            </Section>
          </>
        )}

        {/* KPI Optionen */}
        {widget.type === "kpi" && (
          <Section title="Optionen">
            <select style={{ ...iS, marginBottom: 6 }} value={config.agg || "SUM"} onChange={e => set("agg", e.target.value)}>
              {AGG_FUNCTIONS.map(f => <option key={f.v} value={f.v}>{f.l}</option>)}
            </select>
            <select style={{ ...iS, marginBottom: 6 }} value={config.format || "number"} onChange={e => set("format", e.target.value)}>
              <option value="number">Zahl</option>
              <option value="currency">Währung (EUR)</option>
              <option value="percent">Prozent</option>
            </select>
            <input style={iS} value={config.unit || ""} onChange={e => set("unit", e.target.value)} placeholder="Einheit (optional)" />
          </Section>
        )}

        {/* Bar/Line Optionen */}
        {(widget.type === "bar" || widget.type === "line") && (
          <Section title="Optionen">
            {widget.type === "bar" && (
              <div style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", marginBottom: 6 }} onClick={() => set("stacked", !config.stacked)}>
                <div style={{ width: 14, height: 14, borderRadius: 3, border: `2px solid ${config.stacked ? ACCENT : S.border}`, backgroundColor: config.stacked ? ACCENT : "transparent" }} />
                <span style={{ fontSize: 10, color: S.textMain }}>Gestapelt</span>
              </div>
            )}
            <div style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }} onClick={() => set("show_compare", !config.show_compare)}>
              <div style={{ width: 14, height: 14, borderRadius: 3, border: `2px solid ${config.show_compare ? ACCENT : S.border}`, backgroundColor: config.show_compare ? ACCENT : "transparent" }} />
              <span style={{ fontSize: 10, color: S.textMain }}>Vergleichszeitraum anzeigen</span>
            </div>
          </Section>
        )}

        {/* Pie Optionen */}
        {widget.type === "pie" && (
          <Section title="Optionen">
            <div style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }} onClick={() => set("donut", !config.donut)}>
              <div style={{ width: 14, height: 14, borderRadius: 3, border: `2px solid ${config.donut ? ACCENT : S.border}`, backgroundColor: config.donut ? ACCENT : "transparent" }} />
              <span style={{ fontSize: 10, color: S.textMain }}>Donut-Stil</span>
            </div>
          </Section>
        )}

        {/* Tabellen Optionen */}
        {widget.type === "table" && (
          <Section title="Optionen">
            <div style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", marginBottom: 6 }} onClick={() => set("show_totals", !config.show_totals)}>
              <div style={{ width: 14, height: 14, borderRadius: 3, border: `2px solid ${(config.show_totals !== false) ? ACCENT : S.border}`, backgroundColor: (config.show_totals !== false) ? ACCENT : "transparent" }} />
              <span style={{ fontSize: 10, color: S.textMain }}>Summenzeile anzeigen</span>
            </div>
            <div>
              <label style={{ fontSize: 9, color: S.textDim, display: "block", marginBottom: 3 }}>Max. Zeilen</label>
              <input style={iS} type="number" value={config.max_rows || 100} onChange={e => set("max_rows", parseInt(e.target.value) || 100)} />
            </div>
          </Section>
        )}

        {/* Löschen */}
        <button onClick={() => onRemove(widget.id)}
          style={{ width: "100%", padding: "6px", borderRadius: 4, fontSize: 11, cursor: "pointer", backgroundColor: "rgba(224,112,112,0.08)", border: "1px solid rgba(224,112,112,0.25)", color: "#e07070", display: "flex", alignItems: "center", justifyContent: "center", gap: 5, marginTop: 8 }}>
          <Trash2 size={11} /> Widget entfernen
        </button>
      </div>
    </div>
  );
}
