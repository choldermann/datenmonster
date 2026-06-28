import { useState, useRef, useEffect} from "react";
import { GripVertical, Globe, X, Plus, Minimize2 } from "lucide-react";
import { S } from "./constants";
import { MinimizedNode } from "./MinimizedNode";

export const REST_NODE_COLOR = "#a78bfa"; // violet

const REST_ACTIVE_BORDER = "#fce499";

function RestNode({ node, onRemove, onPositionChange, onUpdate, outputRefs, inputRefs, allSourceFields, onMiniPortsReady, isActive, onActivate }) {
  const dragging = useRef(false);
  const miniLeftRef = useRef(null);
  const miniRightRef = useRef(null);
  useEffect(() => {
    if (node.minimized) {
      // Output-Ref auf rechten Port-Dot zeigen lassen
      if (outputRefs?.current?.[node.id]) outputRefs.current[node.id].current = miniRightRef.current;
      if (onMiniPortsReady) onMiniPortsReady(node.id, miniLeftRef.current, miniRightRef.current);
    }
  }, [node.minimized, onMiniPortsReady]);
  const offset = useRef({ x: 0, y: 0 });

  const handleMouseDown = (e) => {
    if (e.target.closest("select,input,button,textarea")) return;
    if (e.target.getAttribute("draggable") === "true") return;
    e.preventDefault(); e.stopPropagation();
    dragging.current = true;
    offset.current = { x: e.clientX - node.x, y: e.clientY - node.y };
    const onMove = (ev) => { if (!dragging.current) return; onPositionChange(node.id, ev.clientX - offset.current.x, ev.clientY - offset.current.y); };
    const onUp = () => { dragging.current = false; window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  const inputFields = node.input_fields || (node.input_field ? [{ field: node.input_field, placeholder: "{" + node.input_field + "}" }] : []);
  const mappings = node.response_mappings || [];
  const auth = node.auth || { type: "none" };

  const set = (k, v) => onUpdate({ ...node, [k]: v });
  const setAuth = (k, v) => onUpdate({ ...node, auth: { ...auth, [k]: v } });

  const addInput = () => onUpdate({ ...node, input_fields: [...inputFields, { field: "", placeholder: "" }] });
  const removeInput = (i) => onUpdate({ ...node, input_fields: inputFields.filter((_, idx) => idx !== i) });
  const updateInput = (i, key, val) => {
    const updated = inputFields.map((f, idx) => {
      if (idx !== i) return f;
      const next = { ...f, [key]: val };
      if (key === "field" && !f.placeholder) next.placeholder = "{" + val + "}";
      return next;
    });
    onUpdate({ ...node, input_fields: updated });
  };

  const addMapping = () => onUpdate({ ...node, response_mappings: [...mappings, { json_path: "", output_field: "" }] });
  const removeMapping = (i) => onUpdate({ ...node, response_mappings: mappings.filter((_, idx) => idx !== i) });
  const updateMapping = (i, key, val) => {
    const updated = mappings.map((m, idx) => {
      if (idx !== i) return m;
      const next = { ...m, [key]: val };
      if (key === "json_path" && !m.output_field) {
        next.output_field = val.split(".").pop().replace(/[^a-zA-Z0-9_]/g, "_") || "";
      }
      return next;
    });
    onUpdate({ ...node, response_mappings: updated });
  };

  const handleInputDrop = (e, idx) => {
    e.preventDefault();
    e.stopPropagation();
    const field = e.dataTransfer.getData("source_field");
    const dsId = e.dataTransfer.getData("source_dataset_id");
    if (!field) return;
    // Feldname ohne Prefix für Anzeige
    const displayField = field;
    const newFields = [...inputFields];
    newFields[idx] = { field: displayField, placeholder: "{" + displayField + "}", source_dataset_id: dsId };
    onUpdate({ ...node, input_fields: newFields });
  };

  const iS = { backgroundColor: S.bgEl, border: "1px solid " + S.border, borderRadius: 3, color: S.textBright, fontSize: 10, padding: "3px 6px", outline: "none", flex: 1 };
  const DOT = 10;

  if (node.minimized) {
    return (
      <div style={{ position: "absolute", left: node.x, top: node.y, zIndex: 10, overflow: "visible", width: 48, height: 48 }}
        onMouseDown={handleMouseDown}>
        <MinimizedNode
          type="rest" color={REST_NODE_COLOR} label="REST API"
          onExpand={() => onUpdate({ ...node, minimized: false })}
          onMouseDown={handleMouseDown}
          portLeftRef={miniLeftRef} portRightRef={miniRightRef}
          onPortLeftDrop={null} onPortRightDragStart={null}
        />
      </div>
    );
  }

  return (
    <div draggable={false} onClick={(e) => { e.stopPropagation(); onActivate?.({ type: "rest", url: node.url, method: node.method || "GET", mode: node.mode || "single", outputFields: (node.response_mappings || []).map(m => m.output_field) }); }}
      style={{ position: "absolute", left: node.x, top: node.y, width: 330, zIndex: 10, userSelect: "none", boxShadow: isActive ? `0 0 0 2px ${REST_ACTIVE_BORDER}, 0 8px 32px rgba(0,0,0,0.5)` : "0 8px 32px rgba(0,0,0,0.5)", borderRadius: 6, border: isActive ? `1px solid ${REST_ACTIVE_BORDER}` : "1px solid " + REST_NODE_COLOR + "55", backgroundColor: S.bgCard, transition: "box-shadow 0.15s, border-color 0.15s" }}>

      <div onMouseDown={handleMouseDown}
        style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 10px", cursor: "grab", backgroundColor: REST_NODE_COLOR + "12", borderBottom: "1px solid " + REST_NODE_COLOR + "33", borderRadius: "6px 6px 0 0" }}>
        <GripVertical size={12} style={{ color: S.textDim, flexShrink: 0 }} />
        <Globe size={11} style={{ color: REST_NODE_COLOR, flexShrink: 0 }} />
        <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: REST_NODE_COLOR, flex: 1 }}>REST API Node</span>
        <button onClick={() => onUpdate({ ...node, minimized: true })} title="Minimieren" style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0, display: "flex" }}><Minimize2 size={10} /></button>
        <button onClick={() => onRemove(node.id)} style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0 }}><X size={11} /></button>
      </div>

      <div style={{ padding: "8px 10px", display: "flex", flexDirection: "column", gap: 8 }}>

        {/* Eingabefelder */}
        <div>
          <p style={{ fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>Eingabefelder</p>
          {inputFields.map((inp, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 4, marginBottom: 4 }}>
              <div
                style={{ width: 24, height: 24, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, cursor: "crosshair" }}
                onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
                onDragLeave={(e) => { e.stopPropagation(); }}
                onDrop={(e) => { e.stopPropagation(); handleInputDrop(e, i); }}
                title="Quellfeld hierher ziehen"
              >
                <div
                  ref={el => { if (inputRefs && inputRefs.current) inputRefs.current[node.id + "_" + i] = { current: el }; }}
                  style={{ width: 12, height: 12, borderRadius: "50%", backgroundColor: inp.field ? REST_NODE_COLOR : "transparent", border: "2px solid " + REST_NODE_COLOR, pointerEvents: "none" }}
                />
              </div>
              <select style={iS} value={inp.field || ""} onChange={(e) => updateInput(i, "field", e.target.value)}>
                <option value="">— Feld wählen —</option>
                {allSourceFields.map(f => <option key={f} value={f}>{f}</option>)}
              </select>
              <input style={{ ...iS, width: 80, flex: "0 0 80px" }} value={inp.placeholder || ""} onChange={(e) => updateInput(i, "placeholder", e.target.value)}
                placeholder="{feldname}" title="Platzhalter in URL" />
              <button onClick={() => removeInput(i)} style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0, flexShrink: 0 }}><X size={10} /></button>
            </div>
          ))}
          <button onClick={addInput}
            style={{ width: "100%", padding: "3px", borderRadius: 3, fontSize: 10, fontWeight: 600, cursor: "pointer", backgroundColor: REST_NODE_COLOR + "10", border: "1px dashed " + REST_NODE_COLOR + "44", color: REST_NODE_COLOR, display: "flex", alignItems: "center", justifyContent: "center", gap: 4 }}>
            <Plus size={9} /> Eingabefeld hinzufügen
          </button>
        </div>

        {/* URL */}
        <div>
          <p style={{ fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
            URL
            {inputFields.filter(f => f.field).length > 0 && (
              <span style={{ color: REST_NODE_COLOR, fontWeight: 400 }}> · {inputFields.filter(f => f.field).map(f => f.placeholder || ("{" + f.field + "}")).join(", ")}</span>
            )}
          </p>
          <input style={iS} value={node.url || ""} onChange={(e) => set("url", e.target.value)}
            placeholder="https://api.example.com/artikel/{ArtNr}" />
        </div>

        {/* Methode */}
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <p style={{ fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", flexShrink: 0 }}>Methode</p>
          {["GET", "POST"].map(m => (
            <button key={m} onClick={() => set("method", m)}
              style={{ padding: "2px 8px", borderRadius: 3, fontSize: 10, fontWeight: 700, cursor: "pointer", border: "1px solid " + ((node.method || "GET") === m ? REST_NODE_COLOR : S.border), backgroundColor: (node.method || "GET") === m ? REST_NODE_COLOR + "20" : "transparent", color: (node.method || "GET") === m ? REST_NODE_COLOR : S.textDim }}>
              {m}
            </button>
          ))}
        </div>

        {/* Modus */}
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <p style={{ fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", flexShrink: 0 }}>Modus</p>
          {[["single", "Einzeln"], ["batch", "Batch"]].map(([val, label]) => (
            <button key={val} onClick={() => set("mode", val)}
              style={{ padding: "2px 8px", borderRadius: 3, fontSize: 10, fontWeight: 700, cursor: "pointer",
                border: "1px solid " + ((node.mode || "single") === val ? REST_NODE_COLOR : S.border),
                backgroundColor: (node.mode || "single") === val ? REST_NODE_COLOR + "20" : "transparent",
                color: (node.mode || "single") === val ? REST_NODE_COLOR : S.textDim }}>
              {label}
            </button>
          ))}
          {(node.mode || "single") === "batch" && (
            <span style={{ fontSize: 9, color: S.textDim }}>Trennzeichen:</span>
          )}
          {(node.mode || "single") === "batch" && (
            <input style={{ backgroundColor: S.bgEl, border: "1px solid " + S.border, borderRadius: 3,
              color: S.textBright, fontSize: 10, padding: "2px 4px", outline: "none", width: 30 }}
              value={node.join_separator || ","} onChange={(e) => set("join_separator", e.target.value)} />
          )}
        </div>

        {(node.mode || "single") === "batch" && (
          <div style={{ fontSize: 9, color: S.textDim, padding: "4px 8px", borderRadius: 4,
            backgroundColor: REST_NODE_COLOR + "08", border: "1px solid " + REST_NODE_COLOR + "22" }}>
            🔄 Alle Werte aus dem Eingabefeld werden gesammelt und in einem einzigen API-Call abgefragt.
            Platzhalter in der URL: <code style={{ color: REST_NODE_COLOR }}>{"{{ids}}"}</code> oder <code style={{ color: REST_NODE_COLOR }}>{"{{" + (node.input_fields?.[0]?.field || "field") + "s}}"}</code>
          </div>
        )}

        {/* Auth */}
        <div>
          <p style={{ fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>Auth</p>
          <select style={iS} value={auth.type || "none"} onChange={(e) => setAuth("type", e.target.value)}>
            <option value="none">Keine</option>
            <option value="bearer">Bearer Token</option>
            <option value="apikey">API Key (Header)</option>
            <option value="basic">Basic Auth</option>
          </select>
          {auth.type === "bearer" && <input style={{ ...iS, marginTop: 4 }} type="password" value={auth.token || ""} onChange={(e) => setAuth("token", e.target.value)} placeholder="Bearer Token" />}
          {auth.type === "apikey" && (
            <div style={{ display: "flex", gap: 4, marginTop: 4 }}>
              <input style={iS} value={auth.key_name || ""} onChange={(e) => setAuth("key_name", e.target.value)} placeholder="Header-Name" />
              <input style={iS} type="password" value={auth.key_value || ""} onChange={(e) => setAuth("key_value", e.target.value)} placeholder="Wert" />
            </div>
          )}
          {auth.type === "basic" && (
            <div style={{ display: "flex", gap: 4, marginTop: 4 }}>
              <input style={iS} value={auth.username || ""} onChange={(e) => setAuth("username", e.target.value)} placeholder="Benutzername" />
              <input style={iS} type="password" value={auth.password || ""} onChange={(e) => setAuth("password", e.target.value)} placeholder="Passwort" />
            </div>
          )}
        </div>

        {/* Daten-Pfad */}
        <div>
          <p style={{ fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>Daten-Pfad <span style={{ fontWeight: 400 }}>· leer = Root</span></p>
          <input style={iS} value={node.data_path || ""} onChange={(e) => set("data_path", e.target.value)} placeholder="z.B. data.result" />
        </div>

        {/* Ausgabefelder */}
        <div>
          <p style={{ fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>Ausgabefelder</p>
          {mappings.length === 0 && <p style={{ fontSize: 10, color: S.textDim, fontStyle: "italic" }}>Noch keine Felder</p>}
          {mappings.map((m, i) => (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr 1fr " + DOT + "px 18px", gap: 4, alignItems: "center", marginBottom: 4 }}>
              <input style={iS} value={m.json_path} onChange={(e) => updateMapping(i, "json_path", e.target.value)} placeholder="JSON-Pfad" />
              <input style={iS} value={m.output_field} onChange={(e) => updateMapping(i, "output_field", e.target.value)} placeholder="Ausgabename" />
              <div
                ref={el => {
                  if (outputRefs && outputRefs.current) {
                    if (!outputRefs.current[node.id + "_" + i]) {
                      outputRefs.current[node.id + "_" + i] = { current: null };
                    }
                    outputRefs.current[node.id + "_" + i].current = el;
                  }
                }}
                draggable={!!m.output_field}
                onDragStart={(e) => {
                  if (!m.output_field) { e.preventDefault(); return; }
                  e.stopPropagation();
                  e.dataTransfer.setData("source_dataset_id", "__rest__" + node.id);
                  e.dataTransfer.setData("source_field", m.output_field);
                }}
                style={{ width: DOT, height: DOT, borderRadius: "50%", backgroundColor: m.output_field ? REST_NODE_COLOR : S.border, cursor: m.output_field ? "grab" : "default", border: "2px solid " + REST_NODE_COLOR, flexShrink: 0 }}
                title={m.output_field ? (m.output_field + " auf Zielfeld ziehen") : "Ausgabename eingeben"}
              />
              <button onClick={() => removeMapping(i)} style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0 }}><X size={10} /></button>
            </div>
          ))}
          <button onClick={addMapping}
            style={{ width: "100%", padding: "3px", borderRadius: 3, fontSize: 10, fontWeight: 600, cursor: "pointer", backgroundColor: REST_NODE_COLOR + "12", border: "1px dashed " + REST_NODE_COLOR + "55", color: REST_NODE_COLOR, display: "flex", alignItems: "center", justifyContent: "center", gap: 4, marginTop: 2 }}>
            <Plus size={10} /> Feld hinzufügen
          </button>
        </div>

        <div style={{ fontSize: 9, color: S.textDim, padding: "4px 8px", borderRadius: 4, backgroundColor: REST_NODE_COLOR + "08", border: "1px solid " + REST_NODE_COLOR + "22" }}>
          💡 Gleiche Eingabewerte werden gecacht – jede Kombination nur 1× abgefragt
        </div>
      </div>
    </div>
  );
}

export default RestNode;
