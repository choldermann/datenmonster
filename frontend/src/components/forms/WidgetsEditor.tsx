import { useState } from "react";
import { Plus, Trash2, ChevronDown, ChevronRight, Table2, Hash,
         BarChart2, TrendingUp, PieChart } from "lucide-react";
import DrilldownConfig from "./DrilldownConfig";

const S = {
  bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)", bgMain: "var(--bg-main)",
  border: "var(--border)", textMain: "var(--text-main)", textDim: "var(--text-dim)",
  textBright: "var(--text-bright)", accent: "var(--accent)",
};

const inp = {
  backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4,
  color: S.textMain, fontSize: 11, padding: "5px 8px", outline: "none", width: "100%",
  boxSizing: "border-box",
};

const WIDGET_TYPES = [
  { type: "table", label: "Tabelle",        Icon: Table2,    color: "#60a5fa",
    desc: "Rohdaten als Tabelle mit optionalem CSV-Download" },
  { type: "kpi",   label: "KPI-Kachel",     Icon: Hash,      color: "#fce499",
    desc: "Einzelner Kennwert groß anzeigen (Summe, Durchschnitt, …)" },
  { type: "bar",   label: "Balkendiagramm", Icon: BarChart2, color: "#6ee7b7",
    desc: "Kategorien als Balken vergleichen" },
  { type: "line",  label: "Liniendiagramm", Icon: TrendingUp, color: "#a78bfa",
    desc: "Zeitreihen und Trends als Linie" },
  { type: "pie",   label: "Kreisdiagramm",  Icon: PieChart,  color: "#f87171",
    desc: "Anteile als Kuchen- oder Donut-Diagramm" },
];

function LabelRow({ label, children }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <label style={{ display: "block", fontSize: 9, fontWeight: 700, textTransform: "uppercase",
        letterSpacing: "0.1em", color: S.textDim, marginBottom: 4 }}>{label}</label>
      {children}
    </div>
  );
}

function Inp({ value, onChange, placeholder }) {
  return <input value={value || ""} onChange={e => onChange(e.target.value)}
    placeholder={placeholder} style={inp} />;
}

function TagsInput({ label, value = [], onChange, placeholder }) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const v = draft.trim();
    if (v && !value.includes(v)) onChange([...value, v]);
    setDraft("");
  };
  return (
    <LabelRow label={label}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 4 }}>
        {value.map(v => (
          <span key={v} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10,
            padding: "2px 7px", borderRadius: 10, backgroundColor: "rgba(167,139,250,0.15)",
            border: "1px solid rgba(167,139,250,0.3)", color: "#a78bfa" }}>
            {v}
            <button onClick={() => onChange(value.filter(x => x !== v))}
              style={{ background: "none", border: "none", color: "#a78bfa",
                cursor: "pointer", padding: 0, fontSize: 10, lineHeight: 1 }}>×</button>
          </span>
        ))}
      </div>
      <div style={{ display: "flex", gap: 4 }}>
        <input value={draft} onChange={e => setDraft(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
          placeholder={placeholder || "Spaltenname + Enter"}
          style={{ ...inp, flex: 1 }} />
        <button onClick={add}
          style={{ padding: "4px 8px", borderRadius: 4, border: `1px solid ${S.border}`,
            backgroundColor: S.bgEl, color: S.textDim, cursor: "pointer", fontSize: 11 }}>
          +
        </button>
      </div>
    </LabelRow>
  );
}

function WidgetConfig({ widget, actions, onUpdate }) {
  const cfg = widget.config || {};
  const set = (patch) => onUpdate({ ...widget, config: { ...cfg, ...patch } });
  const setTop = (patch) => onUpdate({ ...widget, ...patch });

  const COL_WIDTHS = [
    { v: 4,  l: "4 (⅓)" }, { v: 6, l: "6 (½)" }, { v: 8, l: "8 (⅔)" }, { v: 12, l: "12 (voll)" },
  ];

  return (
    <div style={{ padding: "12px 14px", borderTop: `1px solid ${S.border}`,
      backgroundColor: S.bgMain }}>

      {/* Titel */}
      <LabelRow label="Titel">
        <Inp value={widget.label} onChange={v => setTop({ label: v })} placeholder="Widget-Titel" />
      </LabelRow>

      {/* Verknüpfte Aktion */}
      <LabelRow label="Datenquelle (Aktion)">
        <select value={widget.action_id || ""}
          onChange={e => setTop({ action_id: e.target.value })}
          style={{ ...inp, cursor: "pointer" }}>
          <option value="">— Aktion auswählen —</option>
          {actions.map(a => <option key={a.id} value={a.id}>{a.label || a.id}</option>)}
        </select>
      </LabelRow>

      {/* Breite */}
      <LabelRow label="Breite">
        <div style={{ display: "flex", gap: 4 }}>
          {COL_WIDTHS.map(({ v, l }) => (
            <button key={v} onClick={() => set({ width: v })}
              style={{ flex: 1, padding: "4px 4px", borderRadius: 4, fontSize: 10, cursor: "pointer",
                backgroundColor: (cfg.width || 12) === v ? "rgba(167,139,250,0.15)" : "transparent",
                border: `1px solid ${(cfg.width || 12) === v ? "#a78bfa" : S.border}`,
                color: (cfg.width || 12) === v ? "#a78bfa" : S.textDim }}>
              {l}
            </button>
          ))}
        </div>
      </LabelRow>

      {/* Typ-spezifische Config */}
      {widget.type === "kpi" && (
        <>
          <LabelRow label="Spalte">
            <Inp value={cfg.column} onChange={v => set({ column: v })} placeholder="z.B. total" />
          </LabelRow>
          <LabelRow label="Aggregation">
            <select value={cfg.aggregation || "first"}
              onChange={e => set({ aggregation: e.target.value })} style={{ ...inp, cursor: "pointer" }}>
              {[["first","Erster Wert"],["sum","Summe"],["avg","Durchschnitt"],
                ["count","Anzahl"],["max","Maximum"],["min","Minimum"]].map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
          </LabelRow>
          <div style={{ display: "flex", gap: 8 }}>
            <div style={{ flex: 1 }}>
              <LabelRow label="Präfix">
                <Inp value={cfg.prefix} onChange={v => set({ prefix: v })} placeholder="€" />
              </LabelRow>
            </div>
            <div style={{ flex: 1 }}>
              <LabelRow label="Suffix">
                <Inp value={cfg.suffix} onChange={v => set({ suffix: v })} placeholder="%" />
              </LabelRow>
            </div>
            <div style={{ flex: 1 }}>
              <LabelRow label="Nachkomma">
                <Inp value={cfg.decimals} onChange={v => set({ decimals: v })} placeholder="0" />
              </LabelRow>
            </div>
          </div>
        </>
      )}

      {(widget.type === "bar" || widget.type === "line") && (
        <>
          <LabelRow label="X-Achse (Kategorie / Zeit)">
            <Inp value={cfg.x_column} onChange={v => set({ x_column: v })} placeholder="z.B. monat" />
          </LabelRow>
          <TagsInput label="Y-Achse (Wert-Spalten)"
            value={cfg.y_columns || []} onChange={v => set({ y_columns: v })}
            placeholder="Spaltenname + Enter" />
          {widget.type === "bar" && (
            <LabelRow label="Gestapelt">
              <label style={{ display: "flex", alignItems: "center", gap: 7, cursor: "pointer",
                fontSize: 11, color: S.textMain }}>
                <input type="checkbox" checked={!!cfg.stacked}
                  onChange={e => set({ stacked: e.target.checked })}
                  style={{ width: 12, height: 12 }} />
                Balken stapeln
              </label>
            </LabelRow>
          )}
          {widget.type === "line" && (
            <LabelRow label="Geglättet">
              <label style={{ display: "flex", alignItems: "center", gap: 7, cursor: "pointer",
                fontSize: 11, color: S.textMain }}>
                <input type="checkbox" checked={!!cfg.curved}
                  onChange={e => set({ curved: e.target.checked })}
                  style={{ width: 12, height: 12 }} />
                Kurven statt Geraden
              </label>
            </LabelRow>
          )}
        </>
      )}

      {widget.type === "pie" && (
        <>
          <LabelRow label="Label-Spalte (Kategorie)">
            <Inp value={cfg.label_column} onChange={v => set({ label_column: v })} placeholder="z.B. kategorie" />
          </LabelRow>
          <LabelRow label="Wert-Spalte">
            <Inp value={cfg.value_column} onChange={v => set({ value_column: v })} placeholder="z.B. betrag" />
          </LabelRow>
          <LabelRow label="Donut">
            <label style={{ display: "flex", alignItems: "center", gap: 7, cursor: "pointer",
              fontSize: 11, color: S.textMain }}>
              <input type="checkbox" checked={!!cfg.donut}
                onChange={e => set({ donut: e.target.checked })}
                style={{ width: 12, height: 12 }} />
              Als Donut-Diagramm anzeigen
            </label>
          </LabelRow>
        </>
      )}

      {["bar", "line", "pie"].includes(widget.type) && (
        <LabelRow label="Drilldown">
          <DrilldownConfig
            value={cfg.drilldown}
            dimensionField={widget.type === "pie" ? cfg.label_column : cfg.x_column}
            onChange={(dd) => set({ drilldown: dd })}
          />
        </LabelRow>
      )}
    </div>
  );
}

export default function WidgetsEditor({ widgets = [], actions = [], onChange }) {
  const [expanded, setExpanded] = useState(null);
  const [showPalette, setShowPalette] = useState(false);

  const addWidget = (type) => {
    const id = `w_${Math.random().toString(36).slice(2, 7)}`;
    const def = WIDGET_TYPES.find(t => t.type === type);
    const w = { id, type, label: def?.label || type, action_id: actions[0]?.id || "", config: { width: 12 } };
    onChange([...widgets, w]);
    setExpanded(id);
    setShowPalette(false);
  };

  const updateWidget = (updated) => {
    onChange(widgets.map(w => w.id === updated.id ? updated : w));
  };

  const removeWidget = (id) => {
    onChange(widgets.filter(w => w.id !== id));
    if (expanded === id) setExpanded(null);
  };

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px", scrollbarWidth: "thin" }}>
      <div style={{ maxWidth: 720 }}>

        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
          marginBottom: 20 }}>
          <div>
            <h2 style={{ fontSize: 14, fontWeight: 700, color: S.textBright, margin: 0 }}>Widgets</h2>
            <p style={{ fontSize: 11, color: S.textDim, marginTop: 4 }}>
              Visualisierungen der Aktions-Ergebnisse. Tabelle, KPI, Balken-, Linien- oder Kreisdiagramm.
            </p>
          </div>
          <div style={{ position: "relative" }}>
            <button onClick={() => setShowPalette(p => !p)}
              style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 12px",
                borderRadius: 6, backgroundColor: "rgba(252,228,153,0.1)",
                border: "1px solid rgba(252,228,153,0.35)", color: S.accent,
                cursor: "pointer", fontSize: 11, fontWeight: 600 }}>
              <Plus size={12} /> Widget hinzufügen
            </button>
            {showPalette && (
              <div style={{ position: "absolute", right: 0, top: "calc(100% + 6px)", zIndex: 20,
                backgroundColor: S.bgCard, border: `1px solid ${S.border}`,
                borderRadius: 8, padding: 8, width: 260,
                boxShadow: "0 8px 32px rgba(0,0,0,0.4)" }}>
                {WIDGET_TYPES.map(({ type, label, Icon, color, desc }) => (
                  <button key={type} onClick={() => addWidget(type)}
                    style={{ display: "flex", alignItems: "flex-start", gap: 10, width: "100%",
                      padding: "8px 10px", borderRadius: 6, border: "none",
                      backgroundColor: "transparent", cursor: "pointer", textAlign: "left" }}
                    onMouseEnter={e => e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.04)"}
                    onMouseLeave={e => e.currentTarget.style.backgroundColor = "transparent"}>
                    <Icon size={15} style={{ color, flexShrink: 0, marginTop: 1 }} />
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 600, color: S.textBright }}>{label}</div>
                      <div style={{ fontSize: 10, color: S.textDim, lineHeight: 1.4 }}>{desc}</div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Empty state */}
        {widgets.length === 0 && (
          <div style={{ textAlign: "center", padding: "48px 0",
            border: `1px dashed ${S.border}`, borderRadius: 10, color: S.textDim }}>
            <div style={{ fontSize: 24, marginBottom: 8, opacity: 0.3 }}>📊</div>
            <p style={{ fontSize: 13, marginBottom: 6 }}>Noch keine Widgets</p>
            <p style={{ fontSize: 11, opacity: 0.7 }}>
              Widgets visualisieren die Ergebnisse deiner Aktionen.
            </p>
          </div>
        )}

        {/* Widget list */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {widgets.map((widget, idx) => {
            const def = WIDGET_TYPES.find(t => t.type === widget.type);
            const Icon = def?.Icon || Table2;
            const isOpen = expanded === widget.id;
            const action = actions.find(a => a.id === widget.action_id);

            return (
              <div key={widget.id}
                style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`,
                  borderRadius: 8, overflow: "hidden" }}>
                {/* Header row */}
                <div style={{ display: "flex", alignItems: "center", gap: 10,
                  padding: "10px 14px", cursor: "pointer" }}
                  onClick={() => setExpanded(isOpen ? null : widget.id)}>
                  <Icon size={13} style={{ color: def?.color || S.textDim, flexShrink: 0 }} />
                  <span style={{ flex: 1, fontSize: 12, fontWeight: 600, color: S.textBright }}>
                    {widget.label || def?.label}
                  </span>
                  {action && (
                    <span style={{ fontSize: 10, color: S.textDim, backgroundColor: S.bgEl,
                      padding: "2px 7px", borderRadius: 10 }}>
                      → {action.label || action.id}
                    </span>
                  )}
                  <button onClick={e => { e.stopPropagation(); removeWidget(widget.id); }}
                    style={{ color: S.textDim, background: "none", border: "none",
                      cursor: "pointer", padding: 3, flexShrink: 0 }}
                    onMouseEnter={e => e.currentTarget.style.color = "#e07070"}
                    onMouseLeave={e => e.currentTarget.style.color = S.textDim}>
                    <Trash2 size={12} />
                  </button>
                  {isOpen ? <ChevronDown size={12} style={{ color: S.textDim, flexShrink: 0 }} />
                           : <ChevronRight size={12} style={{ color: S.textDim, flexShrink: 0 }} />}
                </div>
                {isOpen && (
                  <WidgetConfig widget={widget} actions={actions} onUpdate={updateWidget} />
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
