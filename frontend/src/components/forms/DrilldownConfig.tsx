import { useEffect, useState } from "react";
import api from "../../api/client";

/**
 * Wiederverwendbares Konfig-Panel für den Drilldown-Block eines Chart-Widgets.
 * Schreibt `{ type:"mapping", mapping_id, param }` bzw. null via onChange.
 * Wird sowohl im Report-Editor (WidgetConfigPanel) als auch im Formular-Editor
 * (WidgetsEditor) eingebunden. Selbst-gestylt über CSS-Variablen, damit es zu
 * beiden Themes passt.
 */
export default function DrilldownConfig({ value, dimensionField, projectId, onChange, needsKeyColumn = false }) {
  const [mappings, setMappings] = useState([]);

  useEffect(() => {
    api.get("/api/mappings/", { params: projectId ? { project_id: projectId } : {} })
      .then(r => setMappings(Array.isArray(r.data) ? r.data : []))
      .catch(() => setMappings([]));
  }, [projectId]);

  const enabled = !!value;
  const dd = value || {};
  const levels = dd.levels || [];
  const accent = "var(--accent)";
  const iS = { backgroundColor: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 3,
    color: "var(--text-bright)", fontSize: 10, padding: "3px 6px", outline: "none", width: "100%" };
  const lbl = { fontSize: 9, color: "var(--text-dim)", display: "block", marginBottom: 3 };

  const toggle = () => onChange(enabled ? null : { type: "mapping", mapping_id: "", param: "" });
  const setDd = (patch) => onChange({ ...dd, type: "mapping", ...patch });
  const setLevels = (lv) => onChange({ ...dd, type: "mapping", levels: lv });
  const setLevel = (i, patch) => setLevels(levels.map((l, j) => j === i ? { ...l, ...patch } : l));
  const addLevel = () => setLevels([...levels, { mapping_id: "", param: "", key_column: "", title: "" }]);
  const removeLevel = (i) => setLevels(levels.filter((_, j) => j !== i));

  const MappingSelect = ({ val, onPick }) => (
    <select style={{ ...iS, marginBottom: 6, cursor: "pointer" }} value={val || ""}
      onChange={e => onPick(parseInt(e.target.value) || "")}>
      <option value="">— Mapping wählen —</option>
      {mappings.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
    </select>
  );

  return (
    <div>
      <div onClick={toggle} style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", marginBottom: enabled ? 8 : 0 }}>
        <div style={{ width: 14, height: 14, borderRadius: 3, flexShrink: 0,
          border: `2px solid ${enabled ? accent : "var(--border)"}`,
          backgroundColor: enabled ? accent : "transparent" }} />
        <span style={{ fontSize: 10, color: "var(--text-main)" }}>Drilldown per Klick (Detail-Mapping)</span>
      </div>

      {enabled && (
        <>
          <label style={lbl}>Detail-Mapping (Ebene 1)</label>
          <MappingSelect val={dd.mapping_id} onPick={v => setDd({ mapping_id: v })} />

          {needsKeyColumn && (
            <>
              <label style={lbl}>Schlüsselspalte (Klick-Wert der Zeile)</label>
              <input style={{ ...iS, marginBottom: 6 }} value={dd.key_column || ""}
                onChange={e => setDd({ key_column: e.target.value })} placeholder="z.B. kRechnung" />
            </>
          )}

          <label style={lbl}>Parametername{dimensionField ? ` (Standard: ${dimensionField})` : ""}</label>
          <input style={iS} value={dd.param || ""} onChange={e => setDd({ param: e.target.value })}
            placeholder={dimensionField || "z.B. artikel"} />

          <p style={{ fontSize: 9, color: "var(--text-dim)", marginTop: 4, lineHeight: 1.4 }}>
            Der geklickte Wert wird als <code style={{ color: accent }}>:{dd.param || dimensionField || "param"}</code> an
            das Mapping übergeben. Aktuelle Dashboard-Filter (z.&nbsp;B. <code>:von</code>/<code>:bis</code>) werden mitgeschickt.
          </p>

          {/* Tiefere Ebenen: Klick auf eine Zeile im Detail-Modal öffnet die nächste Ebene */}
          <div style={{ marginTop: 10, borderTop: "1px solid var(--border)", paddingTop: 8 }}>
            <span style={{ fontSize: 9, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
              Weitere Ebenen ({levels.length})
            </span>
            {levels.map((l, i) => (
              <div key={i} style={{ marginTop: 8, padding: 8, border: "1px solid var(--border)", borderRadius: 4 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: 9, color: accent, fontWeight: 700 }}>Ebene {i + 2}</span>
                  <button onClick={() => removeLevel(i)} style={{ background: "none", border: "none", color: "#e07070", cursor: "pointer", fontSize: 10 }}>entfernen</button>
                </div>
                <label style={lbl}>Detail-Mapping</label>
                <MappingSelect val={l.mapping_id} onPick={v => setLevel(i, { mapping_id: v })} />
                <label style={lbl}>Schlüsselspalte (Klick-Wert der Vorgänger-Zeile)</label>
                <input style={{ ...iS, marginBottom: 6 }} value={l.key_column || ""}
                  onChange={e => setLevel(i, { key_column: e.target.value })} placeholder="z.B. kArtikel" />
                <label style={lbl}>Parametername</label>
                <input style={{ ...iS, marginBottom: 6 }} value={l.param || ""}
                  onChange={e => setLevel(i, { param: e.target.value })} placeholder={l.key_column || "z.B. kArtikel"} />
                <label style={lbl}>Titel (optional)</label>
                <input style={iS} value={l.title || ""} onChange={e => setLevel(i, { title: e.target.value })}
                  placeholder={`Ebene ${i + 2}`} />
              </div>
            ))}
            <button onClick={addLevel} style={{ marginTop: 8, fontSize: 10, color: accent, background: "none",
              border: `1px dashed ${accent}66`, borderRadius: 4, padding: "4px 8px", cursor: "pointer", width: "100%" }}>
              + Ebene hinzufügen
            </button>
          </div>

          {!dd.mapping_id && (
            <p style={{ fontSize: 9, color: "#d9a441", marginTop: 4 }}>
              Ohne gewähltes Mapping fällt das Dashboard auf den einfachen Zeilen-Filter zurück.
            </p>
          )}
        </>
      )}
    </div>
  );
}
