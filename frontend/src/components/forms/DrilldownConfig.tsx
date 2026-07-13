import { useEffect, useState } from "react";
import api from "../../api/client";

/**
 * Wiederverwendbares Konfig-Panel für den Drilldown-Block eines Chart-Widgets.
 * Schreibt `{ type:"mapping", mapping_id, param }` bzw. null via onChange.
 * Wird sowohl im Report-Editor (WidgetConfigPanel) als auch im Formular-Editor
 * (WidgetsEditor) eingebunden. Selbst-gestylt über CSS-Variablen, damit es zu
 * beiden Themes passt.
 */
export default function DrilldownConfig({ value, dimensionField, projectId, onChange }) {
  const [mappings, setMappings] = useState([]);

  useEffect(() => {
    api.get("/api/mappings/", { params: projectId ? { project_id: projectId } : {} })
      .then(r => setMappings(Array.isArray(r.data) ? r.data : []))
      .catch(() => setMappings([]));
  }, [projectId]);

  const enabled = !!value;
  const dd = value || {};
  const accent = "var(--accent)";
  const iS = { backgroundColor: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 3,
    color: "var(--text-bright)", fontSize: 10, padding: "3px 6px", outline: "none", width: "100%" };
  const lbl = { fontSize: 9, color: "var(--text-dim)", display: "block", marginBottom: 3 };

  const toggle = () => onChange(enabled ? null : { type: "mapping", mapping_id: "", param: "" });
  const setDd = (patch) => onChange({ ...dd, type: "mapping", ...patch });

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
          <label style={lbl}>Detail-Mapping</label>
          <select style={{ ...iS, marginBottom: 6, cursor: "pointer" }} value={dd.mapping_id || ""}
            onChange={e => setDd({ mapping_id: parseInt(e.target.value) || "" })}>
            <option value="">— Mapping wählen —</option>
            {mappings.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>

          <label style={lbl}>Parametername{dimensionField ? ` (Standard: ${dimensionField})` : ""}</label>
          <input style={iS} value={dd.param || ""} onChange={e => setDd({ param: e.target.value })}
            placeholder={dimensionField || "z.B. artikel"} />

          <p style={{ fontSize: 9, color: "var(--text-dim)", marginTop: 4, lineHeight: 1.4 }}>
            Der geklickte Wert wird als <code style={{ color: accent }}>:{dd.param || dimensionField || "param"}</code> an
            das Mapping übergeben (SQL-Node z.&nbsp;B. <code>WHERE cArtNr = :{dd.param || dimensionField || "param"}</code>).
          </p>
          {enabled && !dd.mapping_id && (
            <p style={{ fontSize: 9, color: "#d9a441", marginTop: 4 }}>
              Ohne gewähltes Mapping fällt das Dashboard auf den einfachen Zeilen-Filter zurück.
            </p>
          )}
        </>
      )}
    </div>
  );
}
