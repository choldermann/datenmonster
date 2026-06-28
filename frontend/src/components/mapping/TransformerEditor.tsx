import { useRef, useState } from "react";
import { X, ArrowRight, Hash, Calendar, Type, GitBranch, ChevronDown } from "lucide-react";
import { S, TRANSFORMER_TYPES, JOIN_TYPES, JOIN_COLOR, DATE_FORMATS } from "./constants";

function TransformerEditor({ connection, allSourceFields, onClose, onChange }) {
  const t = connection.transformer || { type: "direct" };
  const set = (k, v) => onChange({ ...t, [k]: v });
  const [fieldSearch, setFieldSearch] = useState("");
  const formulaInputRef = useRef(null);

  const iS = { backgroundColor: S.bgMain, border: `1px solid ${S.border}`, color: S.textBright, borderRadius: "4px", padding: "5px 8px", width: "100%", outline: "none", fontSize: "12px" };
  const lS = { fontSize: "10px", textTransform: "uppercase", letterSpacing: "0.08em", color: S.textDim, display: "block", marginBottom: "3px" };

  const insertField = (f) => {
    const el = formulaInputRef.current;
    if (!el) { set("formula", (t.formula || "") + `{${f}}`); return; }
    const start = el.selectionStart;
    const end = el.selectionEnd;
    const cur = t.formula || "";
    const next = cur.slice(0, start) + `{${f}}` + cur.slice(end);
    set("formula", next);
    // Restore cursor after React re-render
    setTimeout(() => { el.focus(); el.setSelectionRange(start + f.length + 2, start + f.length + 2); }, 0);
  };

  const filteredFields = allSourceFields.filter((f) => f.toLowerCase().includes(fieldSearch.toLowerCase()));

  return (
    <div style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`, borderRadius: 8, padding: 16, width: 480, boxShadow: "0 16px 48px rgba(0,0,0,0.6)" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <p style={{ fontSize: 11, color: S.accent, fontWeight: 600, fontFamily: "monospace", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", marginRight: 8 }}>
          {connection.source_field || "–"} → {connection.target_field}
        </p>
        <button onClick={onClose} style={{ color: S.textDim, flexShrink: 0 }}><X size={14} /></button>
      </div>

      {/* Type selector */}
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 14 }}>
        {TRANSFORMER_TYPES.map((tt) => (
          <button key={tt.value} onClick={() => set("type", tt.value)}
            style={{ display: "flex", alignItems: "center", gap: 4, padding: "4px 8px", borderRadius: 4, fontSize: 11, cursor: "pointer",
              backgroundColor: t.type === tt.value ? tt.color + "22" : S.bgEl,
              border: `1px solid ${t.type === tt.value ? tt.color : S.border}`,
              color: t.type === tt.value ? tt.color : S.textDim }}>
            <tt.icon size={10} /> {tt.label}
          </button>
        ))}
      </div>

      {/* Direct */}
      {t.type === "direct" && (
        <div>
          <label style={lS}>Quellfeld</label>
          <select style={iS} value={t.source_field || connection.source_field || ""} onChange={(e) => set("source_field", e.target.value)}>
            <option value="">– Feld wählen –</option>
            {allSourceFields.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
        </div>
      )}

      {/* Formula – 2-column layout: input left, field list right */}
      {t.type === "formula" && (
        <div style={{ display: "flex", gap: 10 }}>
          {/* Left: formula input */}
          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 6 }}>
            <label style={lS}>Formel</label>
            <textarea
              ref={formulaInputRef}
              style={{ ...iS, resize: "vertical", minHeight: 80, fontFamily: "monospace", lineHeight: 1.5 }}
              placeholder="{Preis} * {Menge}"
              value={t.formula || ""}
              onChange={(e) => set("formula", e.target.value)}
            />
            <p style={{ fontSize: 9, color: S.textDim }}>Felder mit {"{Feldname}"} einfügen · Klick auf Feld fügt an Cursorposition ein</p>
          </div>
          {/* Right: scrollable field list */}
          <div style={{ width: 200, display: "flex", flexDirection: "column", gap: 4 }}>
            <label style={lS}>Felder</label>
            <input
              style={{ ...iS, padding: "4px 6px", fontSize: 11 }}
              placeholder="Suchen..."
              value={fieldSearch}
              onChange={(e) => setFieldSearch(e.target.value)}
              onClick={(e) => e.stopPropagation()}
            />
            <div style={{ height: 180, overflowY: "auto", scrollbarWidth: "thin" }}>
              {filteredFields.length === 0 && <p style={{ fontSize: 10, color: S.textDim, padding: "4px 0" }}>Keine Felder</p>}
              {filteredFields.map((f) => (
                <button key={f}
                  onMouseDown={(e) => { e.preventDefault(); insertField(f); }}
                  style={{ display: "block", width: "100%", textAlign: "left", padding: "5px 6px", borderRadius: 3, fontSize: 12, fontFamily: "monospace", cursor: "pointer", color: S.accent, backgroundColor: "transparent", border: "none", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
                  onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = S.bgEl)}
                  onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
                  title={f}>
                  + {f}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Constant */}
      {t.type === "constant" && (
        <div>
          <label style={lS}>Konstanter Wert</label>
          <input style={iS} placeholder="Fixer Wert" value={t.constant_value || ""} onChange={(e) => set("constant_value", e.target.value)} />
        </div>
      )}

      {/* Date */}
      {t.type === "date" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div>
            <label style={lS}>Quellfeld</label>
            <select style={iS} value={t.source_field || ""} onChange={(e) => set("source_field", e.target.value)}>
              <option value="">– Feld wählen –</option>
              {allSourceFields.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <div>
              <label style={lS}>Eingang</label>
              <select style={iS} value={t.date_input_format || "YYYY-MM-DD"} onChange={(e) => set("date_input_format", e.target.value)}>
                {DATE_FORMATS.map((f) => <option key={f} value={f}>{f}</option>)}
              </select>
            </div>
            <div>
              <label style={lS}>Ausgabe</label>
              <select style={iS} value={t.date_output_format || "DD.MM.YYYY"} onChange={(e) => set("date_output_format", e.target.value)}>
                {DATE_FORMATS.map((f) => <option key={f} value={f}>{f}</option>)}
              </select>
            </div>
          </div>
        </div>
      )}

      {/* Condition */}
      {t.type === "condition" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div><label style={lS}>Bedingung (z.B. {"{Feld}"} &gt; 100)</label><input style={iS} value={t.condition || ""} onChange={(e) => set("condition", e.target.value)} /></div>
          <div><label style={lS}>Wenn wahr</label><input style={iS} value={t.condition_true || ""} onChange={(e) => set("condition_true", e.target.value)} /></div>
          <div><label style={lS}>Wenn falsch</label><input style={iS} value={t.condition_false || ""} onChange={(e) => set("condition_false", e.target.value)} /></div>
        </div>
      )}
    </div>
  );
}

// ─── Join Editor Popup ─────────────────────────────────────────────────────────
function JoinEditor({ join, onClose, onChange, onDelete }) {
  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 60, display: "flex", alignItems: "center", justifyContent: "center", backgroundColor: "rgba(0,0,0,0.6)" }} onClick={onClose}>
      <div style={{ backgroundColor: S.bgCard, border: `1px solid ${JOIN_COLOR}55`, borderRadius: 8, padding: 20, width: 320, boxShadow: "0 16px 48px rgba(0,0,0,0.6)" }} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
          <div>
            <p style={{ fontSize: 11, color: JOIN_COLOR, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}>Join</p>
            <p style={{ fontSize: 10, color: S.textDim, marginTop: 2, fontFamily: "monospace" }}>
              {join.left_field} = {join.right_field}
            </p>
          </div>
          <button onClick={onClose} style={{ color: S.textDim }}><X size={14} /></button>
        </div>
        {/* Join type selector */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6, marginBottom: 16 }}>
          {JOIN_TYPES.map((jt) => {
            const isAnti = jt.value.includes("ANTI");
            const activeColor = isAnti ? "#e07070" : JOIN_COLOR;
            return (
            <button key={jt.value} onClick={() => onChange({ ...join, join_type: jt.value })}
              style={{
                padding: "8px 10px", borderRadius: 4, fontSize: 11, fontWeight: 600, cursor: "pointer",
                backgroundColor: join.join_type === jt.value ? activeColor + "22" : S.bgEl,
                border: `1px solid ${join.join_type === jt.value ? activeColor : S.border}`,
                color: join.join_type === jt.value ? activeColor : S.textDim,
                display: "flex", flexDirection: "column", alignItems: "center", gap: 2,
              }}>
              <span style={{ fontSize: 16 }}>{jt.short}</span>
              <span>{jt.label}</span>
            </button>
            );
          })}
        </div>
        <button onClick={onDelete}
          style={{ width: "100%", padding: "7px", borderRadius: 4, fontSize: 11, cursor: "pointer", backgroundColor: "rgba(224,112,112,0.1)", border: "1px solid rgba(224,112,112,0.3)", color: "#e07070" }}>
          Join löschen
        </button>
      </div>
    </div>
  );
}

// ─── Target Config ─────────────────────────────────────────────────────────────

export { TransformerEditor, JoinEditor };
