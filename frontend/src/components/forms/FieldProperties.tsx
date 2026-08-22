import { Trash2, Plus, X } from "lucide-react";
import { getFieldDef } from "./fieldTypes";

const S = {
  bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)", bgMain: "var(--bg-main)",
  border: "var(--border)", textMain: "var(--text-main)", textDim: "var(--text-dim)",
  textBright: "var(--text-bright)",
};

const inp = {
  width: "100%", backgroundColor: "var(--bg-elevated)", border: "1px solid var(--border)",
  borderRadius: 4, color: "var(--text-main)", fontSize: 11, padding: "5px 8px",
  outline: "none", boxSizing: "border-box",
};

function Label({ children }) {
  return (
    <label style={{ display: "block", fontSize: 9, fontWeight: 700, textTransform: "uppercase",
      letterSpacing: "0.1em", color: S.textDim, marginBottom: 4 }}>
      {children}
    </label>
  );
}

function Row({ children, gap = 8 }) {
  return <div style={{ display: "flex", gap, marginBottom: 12 }}>{children}</div>;
}

function Section({ title, children }) {
  return (
    <div style={{ borderBottom: `1px solid ${S.border}`, padding: "12px 14px" }}>
      {title && <p style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase",
        letterSpacing: "0.1em", color: S.textDim, margin: "0 0 10px" }}>{title}</p>}
      {children}
    </div>
  );
}

const COL_SPANS = [2, 3, 4, 6, 8, 9, 12];

const HAS_OPTIONS = new Set(["dropdown", "multiselect", "radio"]);
const HAS_NAME    = new Set(["text", "textarea", "number", "date", "time", "checkbox", "switch", "dropdown", "multiselect", "radio", "file", "db_dropdown"]);
const HAS_DEFAULT = new Set(["text", "number", "date", "time"]);
const HAS_PLACEHOLDER = new Set(["text", "textarea", "number"]);
const HAS_CONTENT = new Set(["heading", "label"]);
const IS_LAYOUT   = new Set(["heading", "label", "divider", "container"]);
// Felder, die Actions per action_ids auslösen (Button + Dashboard-Filter).
const HAS_ACTIONS = new Set(["button", "daterange", "db_dropdown"]);

const DATE_PRESETS = [
  { id: "", label: "— keins (leer starten) —" },
  { id: "this_month", label: "Dieser Monat" },
  { id: "last_month", label: "Letzter Monat" },
  { id: "this_year",  label: "Dieses Jahr" },
  { id: "last_year",  label: "Letztes Jahr" },
  { id: "days_30",    label: "30 Tage" },
  { id: "months_12",  label: "12 Monate" },
];

export default function FieldProperties({ field, onChange, actions, resultTabs }) {
  if (!field) return (
    <div style={{ width: 240, flexShrink: 0, borderLeft: `1px solid ${S.border}`,
      backgroundColor: S.bgCard, display: "flex", alignItems: "center",
      justifyContent: "center" }}>
      <p style={{ fontSize: 11, color: S.textDim, textAlign: "center", padding: "0 20px", lineHeight: 1.6 }}>
        Feld anklicken<br />um Eigenschaften zu bearbeiten
      </p>
    </div>
  );

  const def = getFieldDef(field.type);
  const set = (patch) => onChange({ ...field, ...patch });
  const setCfg = (patch) => set({ config: { ...(field.config || {}), ...patch } });
  const cfg = field.config || {};

  return (
    <div style={{ width: 240, flexShrink: 0, borderLeft: `1px solid ${S.border}`,
      backgroundColor: S.bgCard, display: "flex", flexDirection: "column",
      overflowY: "auto", scrollbarWidth: "thin" }}>

      {/* Header */}
      <div style={{ padding: "10px 14px", borderBottom: `1px solid ${S.border}`,
        display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase",
          letterSpacing: "0.1em", color: def.color }}>
          {def.label}
        </span>
      </div>

      {/* Content / Label */}
      {HAS_CONTENT.has(field.type) && (
        <Section title="Inhalt">
          <Label>Text</Label>
          <textarea value={field.content || ""} onChange={e => set({ content: e.target.value })}
            rows={2} style={{ ...inp, resize: "vertical" }} />
        </Section>
      )}

      {/* Label & Name */}
      {!IS_LAYOUT.has(field.type) && (
        <Section title="Beschriftung">
          {field.type !== "button" && (
            <Row>
              <div style={{ flex: 1 }}>
                <Label>Label</Label>
                <input value={field.label || ""} onChange={e => set({ label: e.target.value })} style={inp} />
              </div>
            </Row>
          )}
          {field.type === "button" && (
            <Row>
              <div style={{ flex: 1 }}>
                <Label>Button-Text</Label>
                <input value={field.label || ""} onChange={e => set({ label: e.target.value })} style={inp} />
              </div>
            </Row>
          )}
          {HAS_NAME.has(field.type) && field.type !== "button" && (
            <Row>
              <div style={{ flex: 1 }}>
                <Label>Parameter-Name</Label>
                <input value={field.name || ""}
                  onChange={e => set({ name: e.target.value.replace(/\s+/g, "_") })}
                  placeholder="param_name" style={{ ...inp, fontFamily: "monospace", color: def.color }} />
              </div>
            </Row>
          )}
        </Section>
      )}

      {/* Placeholder & Default */}
      {(HAS_PLACEHOLDER.has(field.type) || HAS_DEFAULT.has(field.type)) && (
        <Section>
          {HAS_PLACEHOLDER.has(field.type) && (
            <Row>
              <div style={{ flex: 1 }}>
                <Label>Platzhalter</Label>
                <input value={field.placeholder || ""} onChange={e => set({ placeholder: e.target.value })} style={inp} />
              </div>
            </Row>
          )}
          {HAS_DEFAULT.has(field.type) && (
            <Row>
              <div style={{ flex: 1 }}>
                <Label>Standardwert</Label>
                <input value={field.default || ""} onChange={e => set({ default: e.target.value })} style={inp} />
              </div>
            </Row>
          )}
        </Section>
      )}

      {/* Required */}
      {HAS_NAME.has(field.type) && field.type !== "button" && (
        <Section>
          <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
            <input type="checkbox" checked={!!field.required}
              onChange={e => set({ required: e.target.checked })} style={{ width: 13, height: 13 }} />
            <span style={{ fontSize: 11, color: S.textMain }}>Pflichtfeld</span>
          </label>
        </Section>
      )}

      {/* Options for select types */}
      {HAS_OPTIONS.has(field.type) && (
        <Section title="Optionen">
          {(field.options || []).map((opt, i) => (
            <div key={i} style={{ display: "flex", gap: 4, marginBottom: 4, alignItems: "center" }}>
              <input value={opt.label} onChange={e => {
                const opts = [...(field.options || [])];
                opts[i] = { ...opts[i], label: e.target.value, value: e.target.value.toLowerCase().replace(/\s+/g, "_") };
                set({ options: opts });
              }} placeholder={`Option ${i + 1}`} style={{ ...inp, flex: 1 }} />
              <button onClick={() => set({ options: field.options.filter((_, j) => j !== i) })}
                style={{ color: S.textDim, background: "none", border: "none", cursor: "pointer", flexShrink: 0 }}
                onMouseEnter={e => e.currentTarget.style.color = "#e07070"}
                onMouseLeave={e => e.currentTarget.style.color = S.textDim}>
                <X size={10} />
              </button>
            </div>
          ))}
          <button onClick={() => set({ options: [...(field.options || []), { value: `opt_${(field.options || []).length + 1}`, label: `Option ${(field.options || []).length + 1}` }] })}
            style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10, color: S.textDim,
              background: "none", border: `1px dashed ${S.border}`, borderRadius: 4,
              padding: "3px 8px", cursor: "pointer", width: "100%", justifyContent: "center" }}
            onMouseEnter={e => e.currentTarget.style.color = S.textMain}
            onMouseLeave={e => e.currentTarget.style.color = S.textDim}>
            <Plus size={10} /> Option hinzufügen
          </button>
        </Section>
      )}

      {/* Dashboard-Filter: Zeitraum (daterange) */}
      {field.type === "daterange" && (
        <Section title="Zeitraum-Filter">
          <Row>
            <div style={{ flex: 1 }}>
              <Label>Standard-Preset (beim Öffnen)</Label>
              <select value={cfg.default || ""} onChange={e => setCfg({ default: e.target.value })}
                style={{ ...inp, cursor: "pointer" }}>
                {DATE_PRESETS.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
              </select>
            </div>
          </Row>
          <Row>
            <div style={{ flex: 1 }}>
              <Label>Param »von«</Label>
              <input value={cfg.param_from || ""} onChange={e => setCfg({ param_from: e.target.value.replace(/\s+/g, "_") })}
                placeholder="von" style={{ ...inp, fontFamily: "monospace", color: def.color }} />
            </div>
            <div style={{ flex: 1 }}>
              <Label>Param »bis«</Label>
              <input value={cfg.param_to || ""} onChange={e => setCfg({ param_to: e.target.value.replace(/\s+/g, "_") })}
                placeholder="bis" style={{ ...inp, fontFamily: "monospace", color: def.color }} />
            </div>
          </Row>
          <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
            <input type="checkbox" checked={cfg.auto_run !== false}
              onChange={e => setCfg({ auto_run: e.target.checked })} style={{ width: 13, height: 13 }} />
            <span style={{ fontSize: 11, color: S.textMain }}>Bei Änderung automatisch ausführen</span>
          </label>
          <p style={{ fontSize: 9, color: S.textDim, marginTop: 6, lineHeight: 1.4 }}>
            Das SQL bindet die Werte als <code>:{cfg.param_from || "von"}</code> / <code>:{cfg.param_to || "bis"}</code>.
          </p>
        </Section>
      )}

      {/* Dashboard-Filter: DB-Auswahl (db_dropdown) */}
      {field.type === "db_dropdown" && (
        <Section title="DB-Auswahl">
          <Row>
            <div style={{ flex: 1 }}>
              <Label>Verbindungs-ID</Label>
              <input value={cfg.connection_id ?? ""} onChange={e => setCfg({ connection_id: e.target.value })}
                placeholder="{{connection_jtl}} oder Zahl"
                style={{ ...inp, fontFamily: "monospace" }} />
            </div>
          </Row>
          <Row>
            <div style={{ flex: 1 }}>
              <Label>Lookup-Art</Label>
              <select value={cfg.kind || "warengruppe"} onChange={e => setCfg({ kind: e.target.value })}
                style={{ ...inp, cursor: "pointer" }}>
                <option value="warengruppe">Warengruppe</option>
                <option value="kategorie">Kategorie</option>
                <option value="plattform">Plattform</option>
              </select>
            </div>
          </Row>
          <Row>
            <div style={{ flex: 1 }}>
              <Label>Platzhalter</Label>
              <input value={cfg.placeholder || ""} onChange={e => setCfg({ placeholder: e.target.value })}
                placeholder="— alle —" style={inp} />
            </div>
          </Row>
          <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", marginBottom: 8 }}>
            <input type="checkbox" checked={!!cfg.multiple}
              onChange={e => setCfg({ multiple: e.target.checked })} style={{ width: 13, height: 13 }} />
            <span style={{ fontSize: 11, color: S.textMain }}>Mehrfachauswahl (Multiselect)</span>
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
            <input type="checkbox" checked={cfg.auto_run !== false}
              onChange={e => setCfg({ auto_run: e.target.checked })} style={{ width: 13, height: 13 }} />
            <span style={{ fontSize: 11, color: S.textMain }}>Bei Änderung automatisch ausführen</span>
          </label>
          <p style={{ fontSize: 9, color: S.textDim, marginTop: 6, lineHeight: 1.4 }}>
            {cfg.multiple
              ? <>Liste → SQL-Muster <code>(:{field.name || "param"}_empty = 1 OR spalte IN (:{field.name || "param"}))</code>.</>
              : <>SQL bindet <code>:{field.name || "param"}</code>; „alle" via <code>NULLIF(:{field.name || "param"}, '')</code>.</>}
          </p>
        </Section>
      )}

      {/* Button/Filter → Actions verknüpfen (mehrere möglich) */}
      {HAS_ACTIONS.has(field.type) && (() => {
        const selIds = (field.action_ids && field.action_ids.length)
          ? field.action_ids
          : (field.action_id ? [field.action_id] : []);
        return (
          <Section title="Aktionen">
            <Label>Verknüpfte Aktionen</Label>
            {(actions || []).length === 0 ? (
              <p style={{ fontSize: 10, color: S.textDim }}>
                Noch keine Aktionen — im Tab "Aktionen" anlegen.
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                {(actions || []).map(a => {
                  const checked = selIds.includes(a.id);
                  return (
                    <label key={a.id} style={{ display: "flex", alignItems: "center", gap: 6,
                      fontSize: 11, color: S.textMain, cursor: "pointer" }}>
                      <input type="checkbox" checked={checked}
                        onChange={e => {
                          const next = e.target.checked
                            ? [...selIds, a.id]
                            : selIds.filter(x => x !== a.id);
                          set({ action_ids: next, action_id: "" });
                        }}
                        style={{ width: 13, height: 13 }} />
                      {a.label || a.id}
                    </label>
                  );
                })}
              </div>
            )}
            <p style={{ fontSize: 9, color: S.textDim, marginTop: 6, lineHeight: 1.4 }}>
              Mehrere Aktionen möglich — ein Klick führt alle aus. Ohne Auswahl laufen alle Aktionen.
            </p>
          </Section>
        );
      })()}

      {/* Sichtbarkeit: Feld nur auf bestimmten Ergebnis-Reitern zeigen */}
      {!IS_LAYOUT.has(field.type) && (resultTabs || []).length > 0 && (() => {
        const sel = Array.isArray(cfg.visible_tabs) ? cfg.visible_tabs : [];
        return (
          <Section title="Sichtbarkeit">
            <Label>Nur in diesen Reitern</Label>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              {(resultTabs || []).map(t => {
                const checked = sel.includes(t.id);
                return (
                  <label key={t.id} style={{ display: "flex", alignItems: "center", gap: 6,
                    fontSize: 11, color: S.textMain, cursor: "pointer" }}>
                    <input type="checkbox" checked={checked}
                      onChange={e => setCfg({ visible_tabs: e.target.checked
                        ? [...sel, t.id] : sel.filter(x => x !== t.id) })}
                      style={{ width: 13, height: 13 }} />
                    {t.label || t.id}
                  </label>
                );
              })}
            </div>
            <p style={{ fontSize: 9, color: S.textDim, marginTop: 6, lineHeight: 1.4 }}>
              Ohne Auswahl steht das Feld über allen Reitern. Nützlich für Filter, die
              nur eine Auswertung steuern (z.B. Artikelwahl für die Preishistorie).
            </p>
          </Section>
        );
      })()}

      {/* Layout: Breite */}
      <Section title="Layout">
        <Label>Breite (von 12 Spalten)</Label>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
          {COL_SPANS.map(cs => (
            <button key={cs} onClick={() => set({ colSpan: cs })}
              style={{ padding: "3px 7px", borderRadius: 4, fontSize: 10, cursor: "pointer",
                backgroundColor: field.colSpan === cs ? `${def.color}20` : "transparent",
                border: `1px solid ${field.colSpan === cs ? def.color : S.border}`,
                color: field.colSpan === cs ? def.color : S.textDim, fontWeight: field.colSpan === cs ? 700 : 400 }}>
              {cs === 12 ? "12 (voll)" : cs === 6 ? "6 (½)" : cs === 4 ? "4 (⅓)" : cs === 3 ? "3 (¼)" : cs}
            </button>
          ))}
        </div>
      </Section>
    </div>
  );
}
