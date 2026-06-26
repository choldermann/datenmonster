/**
 * TransformNode – Canvas-Node für Datentransformationen
 * Typen: number_format, date_format, text, concat
 * Eingabe: ein oder mehrere Quellfelder per Drag
 * Ausgabe: ein Feld das ins Ziel oder weiter gemappt werden kann
 */
import { useRef, useCallback, useEffect} from "react";
import { GripVertical, Minimize2, X, Settings } from "lucide-react";
import { MinimizedNode } from "./mapping/MinimizedNode";

const S = {
  accent: "var(--accent)", bgMain: "var(--bg-main)", bgCard: "var(--bg-card)",
  bgEl: "var(--bg-elevated)", border: "var(--border)", textMain: "var(--text-main)",
  textBright: "var(--text-bright)", textDim: "var(--text-dim)",
};

const NODE_COLOR   = "#818cf8"; // indigo
const NODE_BG      = "rgba(129,140,248,0.08)";
const NODE_BORDER  = "rgba(129,140,248,0.35)";

export const TRANSFORM_TYPES = [
  { value: "number_format", label: "Zahlenformat",  icon: "123", color: "#34d399" },
  { value: "date_format",   label: "Datumsformat",  icon: "📅",  color: "#f9a8d4" },
  { value: "text",          label: "Text",           icon: "Aa",  color: "#93c5fd" },
  { value: "concat",        label: "Verkettung",     icon: "⊕",   color: "#fbbf24" },
];

// Default config per type
export function defaultConfig(type) {
  switch (type) {
    case "number_format": return { decimal_sep: ",", thousands_sep: ".", decimals: 2 };
    case "date_format":   return { input_format: "%Y-%m-%d", output_format: "%d.%m.%Y" };
    case "text":          return { operation: "trim", find: "", replace: "" };
    case "concat":        return { separator: " ", template: "" };
    default: return {};
  }
}

// ─── Config Editor (inline in node) ──────────────────────────────────────────

function NumberFormatConfig({ config, onChange, onMiniPortsReady}) {
  const u = (k, v) => onChange({ ...config, [k]: v });
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
        <label style={{ fontSize: 9, color: S.textDim, width: 70 }}>Dezimal-Zeichen</label>
        <select value={config.decimal_sep ?? ","} onChange={(e) => u("decimal_sep", e.target.value)}
          style={selS}>
          <option value=",">,  (Komma)</option>
          <option value=".">. (Punkt)</option>
        </select>
      </div>
      <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
        <label style={{ fontSize: 9, color: S.textDim, width: 70 }}>Tausend-Zeichen</label>
        <select value={config.thousands_sep ?? "."} onChange={(e) => u("thousands_sep", e.target.value)}
          style={selS}>
          <option value=".">. (Punkt)</option>
          <option value=",">, (Komma)</option>
          <option value=" ">  (Leerzeichen)</option>
          <option value="">  (keines)</option>
        </select>
      </div>
      <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
        <label style={{ fontSize: 9, color: S.textDim, width: 70 }}>Nachkomma</label>
        <input type="number" min={0} max={10} value={config.decimals ?? 2}
          onChange={(e) => u("decimals", parseInt(e.target.value))}
          style={{ ...inpS, width: 50 }} />
      </div>
    </div>
  );
}

function DateFormatConfig({ config, onChange }) {
  const u = (k, v) => onChange({ ...config, [k]: v });
  const PRESETS = [
    { label: "ISO → DE",          input: "%Y-%m-%d",              output: "%d.%m.%Y" },
    { label: "ISO+Zeit → DE",     input: "%Y-%m-%d %H:%M:%S",     output: "%d.%m.%Y %H:%M" },
    { label: "ISO+Zeit+ms → DE",  input: "%Y-%m-%d %H:%M:%S.%f",  output: "%d.%m.%Y" },
    { label: "ISO lang → DE",     input: "%Y-%m-%d",              output: "%d. %B %Y" },
    { label: "ISO → US",          input: "%Y-%m-%d",              output: "%m/%d/%Y" },
    { label: "DE → ISO",          input: "%d.%m.%Y",              output: "%Y-%m-%d" },
  ];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      <div>
        <label style={{ fontSize: 9, color: S.textDim }}>Schnellauswahl</label>
        <select onChange={(e) => { const p = PRESETS[e.target.value]; if (p) u("input_format", p.input) || onChange({ ...config, input_format: p.input, output_format: p.output }); }}
          style={{ ...selS, marginTop: 2, width: "100%" }}>
          <option value="">– Preset wählen –</option>
          {PRESETS.map((p, i) => <option key={i} value={i}>{p.label}</option>)}
        </select>
      </div>
      <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
        <label style={{ fontSize: 9, color: S.textDim, width: 55, flexShrink: 0 }}>Eingabe</label>
        <input value={config.input_format ?? "%Y-%m-%d"} onChange={(e) => u("input_format", e.target.value)}
          style={{ ...inpS, flex: 1, fontFamily: "monospace" }} placeholder="%Y-%m-%d" />
      </div>
      <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
        <label style={{ fontSize: 9, color: S.textDim, width: 55, flexShrink: 0 }}>Ausgabe</label>
        <input value={config.output_format ?? "%d.%m.%Y"} onChange={(e) => u("output_format", e.target.value)}
          style={{ ...inpS, flex: 1, fontFamily: "monospace" }} placeholder="%d.%m.%Y" />
      </div>
      <p style={{ fontSize: 8, color: S.textDim, marginTop: 1 }}>%d Tag · %m Monat · %Y Jahr · %H Stunde · %M Minute</p>
    </div>
  );
}

function TextConfig({ config, onChange }) {
  const u = (k, v) => onChange({ ...config, [k]: v });
  const OPS = [
    { value: "trim",         label: "Trim (Leerzeichen entfernen)" },
    { value: "upper",        label: "GROSSBUCHSTABEN" },
    { value: "lower",        label: "kleinbuchstaben" },
    { value: "replace",      label: "Ersetzen (Find → Replace)" },
    { value: "prefix",       label: "Präfix hinzufügen" },
    { value: "suffix",       label: "Suffix hinzufügen" },
    { value: "substr",       label: "Teilstring (Start + Länge)" },
    { value: "left",         label: "Erste N Zeichen" },
    { value: "right",        label: "Letzte N Zeichen" },
    { value: "substr_range", label: "Von Position X bis Y" },
    { value: "split",         label: "Aufteilen & Teil N" },
    { value: "length",        label: "Zeichenlänge" },
    { value: "reverse",       label: "Umkehren (Reverse)" },
    { value: "regex_extract", label: "Regex: Muster extrahieren" },
    { value: "regex_replace", label: "Regex: Muster ersetzen" },
  ];
  const op = config.operation ?? "trim";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      <select value={op} onChange={(e) => u("operation", e.target.value)}
        style={{ ...selS, width: "100%" }}>
        {OPS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>

      {op === "replace" && (
        <>
          <input value={config.find ?? ""} onChange={(e) => u("find", e.target.value)}
            style={{ ...inpS, width: "100%" }} placeholder="Suchen..." />
          <input value={config.replace ?? ""} onChange={(e) => u("replace", e.target.value)}
            style={{ ...inpS, width: "100%" }} placeholder="Ersetzen durch..." />
        </>
      )}
      {(op === "prefix" || op === "suffix") && (
        <input value={config.affix ?? ""} onChange={(e) => u("affix", e.target.value)}
          style={{ ...inpS, width: "100%" }} placeholder={op === "prefix" ? "Präfix..." : "Suffix..."} />
      )}
      {op === "substr" && (
        <div style={{ display: "flex", gap: 4 }}>
          <input type="number" value={config.start ?? 0} onChange={(e) => u("start", parseInt(e.target.value))}
            style={{ ...inpS, width: 55 }} placeholder="Start" />
          <input type="number" value={config.length ?? ""} onChange={(e) => u("length", parseInt(e.target.value))}
            style={{ ...inpS, width: 55 }} placeholder="Länge" />
        </div>
      )}
      {(op === "left" || op === "right") && (
        <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
          <label style={{ fontSize: 9, color: S.textDim, flexShrink: 0 }}>Anzahl Zeichen</label>
          <input type="number" min={1} value={config.n ?? 1} onChange={(e) => u("n", parseInt(e.target.value))}
            style={{ ...inpS, width: 55 }} placeholder="N" />
        </div>
      )}
      {op === "substr_range" && (
        <>
          <div style={{ display: "flex", gap: 4 }}>
            <div style={{ flex: 1 }}>
              <label style={{ fontSize: 9, color: S.textDim }}>Von Position</label>
              <input type="number" min={1} value={config.range_start ?? 1} onChange={(e) => u("range_start", parseInt(e.target.value))}
                style={{ ...inpS, width: "100%", marginTop: 2 }} placeholder="1" />
            </div>
            <div style={{ flex: 1 }}>
              <label style={{ fontSize: 9, color: S.textDim }}>Bis Position</label>
              <input type="number" min={1} value={config.range_end ?? 5} onChange={(e) => u("range_end", parseInt(e.target.value))}
                style={{ ...inpS, width: "100%", marginTop: 2 }} placeholder="5" />
            </div>
          </div>
          <p style={{ fontSize: 8, color: S.textDim }}>Position 1 = erstes Zeichen, beide Grenzen inklusive</p>
        </>
      )}
      {op === "split" && (
        <>
          <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
            <label style={{ fontSize: 9, color: S.textDim, width: 70, flexShrink: 0 }}>Trennzeichen</label>
            <input value={config.delimiter ?? ";"} onChange={(e) => u("delimiter", e.target.value)}
              style={{ ...inpS, flex: 1, fontFamily: "monospace" }} placeholder=";" />
          </div>
          <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
            <label style={{ fontSize: 9, color: S.textDim, width: 70, flexShrink: 0 }}>Teil Nr.</label>
            <input type="number" min={1} value={config.part_index ?? 1} onChange={(e) => u("part_index", parseInt(e.target.value))}
              style={{ ...inpS, width: 55 }} placeholder="1" />
          </div>
          <p style={{ fontSize: 8, color: S.textDim }}>Teil 1 = erstes Segment nach dem Aufteilen</p>
        </>
      )}
      {op === "length" && (
        <p style={{ fontSize: 9, color: S.textDim }}>Gibt die Anzahl der Zeichen als Zahl zurück.</p>
      )}
      {op === "reverse" && (
        <p style={{ fontSize: 9, color: S.textDim }}>Kehrt die Reihenfolge aller Zeichen um.</p>
      )}
      {(op === "regex_extract" || op === "regex_replace") && (
        <>
          <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
            <label style={{ fontSize: 9, color: S.textDim, width: 70, flexShrink: 0 }}>Muster (Regex)</label>
            <input value={config.pattern ?? ""} onChange={(e) => u("pattern", e.target.value)}
              style={{ ...inpS, flex: 1, fontFamily: "monospace" }} placeholder="z.B. \d+" />
          </div>
          {op === "regex_replace" && (
            <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
              <label style={{ fontSize: 9, color: S.textDim, width: 70, flexShrink: 0 }}>Ersetzen durch</label>
              <input value={config.repl ?? ""} onChange={(e) => u("repl", e.target.value)}
                style={{ ...inpS, flex: 1, fontFamily: "monospace" }} placeholder="Ersetzung (\\1 für Gruppen)" />
            </div>
          )}
          {op === "regex_extract" && (
            <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
              <label style={{ fontSize: 9, color: S.textDim, width: 70, flexShrink: 0 }}>Gruppe Nr.</label>
              <input type="number" min={0} value={config.group ?? 0} onChange={(e) => u("group", parseInt(e.target.value))}
                style={{ ...inpS, width: 55 }} />
              <span style={{ fontSize: 8, color: S.textDim }}>0 = ganzer Match</span>
            </div>
          )}
          <p style={{ fontSize: 8, color: S.textDim }}>Python-Regex-Syntax · leer lassen = kein Ergebnis</p>
        </>
      )}
    </div>
  );
}

function ConcatConfig({ config, onChange, inputs }) {
  const u = (k, v) => onChange({ ...config, [k]: v });
  // Build preview from input field names
  const preview = inputs.length
    ? inputs.map((inp) => inp.source_field || "?").join(config.separator ?? " ")
    : "Feld1 + Feld2";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
        <label style={{ fontSize: 9, color: S.textDim, width: 60, flexShrink: 0 }}>Trennzeichen</label>
        <input value={config.separator ?? " "} onChange={(e) => u("separator", e.target.value)}
          style={{ ...inpS, width: 60, fontFamily: "monospace" }} placeholder="Leerzeichen" />
      </div>
      <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
        <label style={{ fontSize: 9, color: S.textDim, width: 60, flexShrink: 0 }}>Template</label>
        <input value={config.template ?? ""} onChange={(e) => u("template", e.target.value)}
          style={{ ...inpS, flex: 1, fontFamily: "monospace" }} placeholder="{0} {1} (leer = einfach)" />
      </div>
      <p style={{ fontSize: 9, color: S.textDim, fontFamily: "monospace" }}>→ {preview}</p>
    </div>
  );
}

// Shared input styles
const inpS = { padding: "3px 6px", backgroundColor: "var(--bg-main)", border: "1px solid var(--border)", borderRadius: 3, color: "var(--text-bright)", fontSize: 10, outline: "none" };
const selS = { padding: "3px 4px", backgroundColor: "var(--bg-main)", border: "1px solid var(--border)", borderRadius: 3, color: "var(--text-main)", fontSize: 10, outline: "none" };

// ─── TransformNode ────────────────────────────────────────────────────────────

export default function TransformNode({ node, onPositionChange, onUpdate, onRemove, outputRef, inputRefs , onMiniPortsReady }) {
  const dragState = useRef(null);
  const miniLeftRef = useRef(null);
  const miniRightRef = useRef(null);
  useEffect(() => {
    if (node.minimized) {
      // Output-Ref auf rechten Port-Dot zeigen lassen
      if (outputRef) outputRef.current = miniRightRef.current;
      if (onMiniPortsReady) onMiniPortsReady(node.id, miniLeftRef.current, miniRightRef.current);
    }
  }, [node.minimized, onMiniPortsReady]);
  const tt = TRANSFORM_TYPES.find((t) => t.value === node.type) || TRANSFORM_TYPES[0];

  const handleMouseDown = useCallback((e) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    dragState.current = { startX: e.clientX - node.x, startY: e.clientY - node.y };
    const onMove = (ev) => {
      if (!dragState.current) return;
      onPositionChange(node.id, ev.clientX - dragState.current.startX, ev.clientY - dragState.current.startY);
    };
    const onUp = () => { dragState.current = null; window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }, [node.x, node.y, node.id, onPositionChange]);

  const updateConfig = (cfg) => onUpdate({ ...node, config: cfg });
  const updateOutputField = (val) => onUpdate({ ...node, output_field: val });

  const removeInput = (portId) => onUpdate({ ...node, inputs: node.inputs.filter((inp) => inp.port_id !== portId) });

  if (node.minimized) {
    return (
      <div style={{ position: "absolute", left: node.x, top: node.y, zIndex: 12,
          overflow: "visible", width: 44, height: 44 }}
        onMouseDown={handleMouseDown}>
        <MinimizedNode
          type="calc" color={NODE_COLOR} label={tt.label}
          onExpand={() => onUpdate({ ...node, minimized: false })}
          onMouseDown={null}
          portLeftRef={miniLeftRef} portRightRef={miniRightRef}
          onPortLeftDrop={null} onPortRightDragStart={null}
        />

        </div>
    );
  }

  return (
    <div style={{
      position: "absolute", left: node.x, top: node.y, width: 240, zIndex: 12,
      backgroundColor: S.bgCard, border: `1px solid ${NODE_BORDER}`,
      borderRadius: 7, overflow: "hidden", boxShadow: `0 6px 24px rgba(0,0,0,0.5), 0 0 0 1px ${NODE_BORDER}`,
      userSelect: "none",
    }}>
      {/* Header */}
      <div onMouseDown={handleMouseDown}
        style={{ display: "flex", alignItems: "center", gap: 7, padding: "7px 10px", cursor: "grab", backgroundColor: NODE_BG, borderBottom: `1px solid ${NODE_BORDER}` }}>
        <GripVertical size={11} style={{ color: NODE_COLOR, flexShrink: 0 }} />
        <span style={{ fontSize: 13, flexShrink: 0 }}>{tt.icon}</span>
        <span style={{ fontSize: 11, fontWeight: 700, color: NODE_COLOR, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{tt.label}</span>
        {/* Type selector */}
        <select value={node.type} onChange={(e) => onUpdate({ ...node, type: e.target.value, config: defaultConfig(e.target.value), inputs: [] })}
          onClick={(e) => e.stopPropagation()}
          style={{ ...selS, fontSize: 9, padding: "2px 3px", color: NODE_COLOR, border: `1px solid ${NODE_BORDER}` }}>
          {TRANSFORM_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
        </select>
        <button onClick={(e) => { e.stopPropagation(); onUpdate({ ...node, minimized: true }); }}
          title="Minimieren"
          style={{ color: S.textDim, background: "none", border: "none", cursor: "pointer", flexShrink: 0 }}
          onMouseEnter={(e) => (e.currentTarget.style.color = NODE_COLOR)}
          onMouseLeave={(e) => (e.currentTarget.style.color = S.textDim)}>
          <Minimize2 size={10} />
        </button>
        <button onClick={(e) => { e.stopPropagation(); onRemove(node.id); }}
          style={{ color: S.textDim, background: "none", border: "none", cursor: "pointer", flexShrink: 0 }}
          onMouseEnter={(e) => (e.currentTarget.style.color = "#f87171")}
          onMouseLeave={(e) => (e.currentTarget.style.color = S.textDim)}>
          <X size={11} />
        </button>
      </div>

      <div style={{ padding: "8px 10px", display: "flex", flexDirection: "column", gap: 8 }}>
        {/* Inputs */}
        <div>
          <p style={{ fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>
            Eingabe{node.type === "concat" ? "n" : ""}
          </p>
          {node.inputs.length === 0 && (
            <div
              onDragOver={(e) => { e.preventDefault(); e.currentTarget.style.borderColor = NODE_COLOR; }}
              onDragLeave={(e) => { e.currentTarget.style.borderColor = "transparent"; }}
              onDrop={(e) => {
                e.preventDefault(); e.stopPropagation();
                e.currentTarget.style.borderColor = "transparent";
                const rawDsId = e.dataTransfer.getData("source_dataset_id");
                const dsId = rawDsId.startsWith("__") ? rawDsId : parseInt(rawDsId);
                const field = e.dataTransfer.getData("source_field");
                if (!field) return;
                const portId = Math.random().toString(36).slice(2, 8);
                onUpdate({ ...node, inputs: [...node.inputs, { port_id: portId, source_dataset_id: dsId, source_field: field }] });
              }}
              style={{ padding: "6px 8px", borderRadius: 4, border: "1px dashed transparent", borderColor: `${NODE_COLOR}40`, textAlign: "center", fontSize: 9, color: S.textDim, cursor: "default" }}>
              ← Feld hierher ziehen
            </div>
          )}
          {node.inputs.map((inp) => (
            <div key={inp.port_id}
              ref={(el) => { if (el && inputRefs) inputRefs.current[`${node.id}__${inp.port_id}`] = el; }}
              style={{ display: "flex", alignItems: "center", gap: 5, padding: "4px 6px", borderRadius: 3, backgroundColor: S.bgMain, marginBottom: 3 }}>
              {/* Left dot – input port */}
              <span style={{ width: 7, height: 7, borderRadius: "50%", backgroundColor: NODE_COLOR, flexShrink: 0, marginLeft: -3 }} />
              <span style={{ fontSize: 10, color: S.textMain, fontFamily: "monospace", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{inp.source_field}</span>
              <button onClick={() => removeInput(inp.port_id)}
                style={{ color: S.textDim, background: "none", border: "none", cursor: "pointer", fontSize: 10, padding: 0, lineHeight: 1 }}>✕</button>
            </div>
          ))}
          {/* Extra drop zone for concat (multiple inputs) */}
          {node.type === "concat" && node.inputs.length > 0 && (
            <div
              onDragOver={(e) => { e.preventDefault(); e.currentTarget.style.borderColor = NODE_COLOR; }}
              onDragLeave={(e) => { e.currentTarget.style.borderColor = `${NODE_COLOR}40`; }}
              onDrop={(e) => {
                e.preventDefault(); e.stopPropagation();
                e.currentTarget.style.borderColor = `${NODE_COLOR}40`;
                const rawDsId = e.dataTransfer.getData("source_dataset_id");
                const dsId = rawDsId.startsWith("__") ? rawDsId : parseInt(rawDsId);
                const field = e.dataTransfer.getData("source_field");
                if (!field) return;
                const portId = Math.random().toString(36).slice(2, 8);
                onUpdate({ ...node, inputs: [...node.inputs, { port_id: portId, source_dataset_id: dsId, source_field: field }] });
              }}
              style={{ padding: "3px 8px", borderRadius: 3, border: `1px dashed ${NODE_COLOR}40`, textAlign: "center", fontSize: 9, color: S.textDim, cursor: "default", marginTop: 2 }}>
              + weiteres Feld
            </div>
          )}
        </div>

        {/* Config */}
        <div style={{ borderTop: `1px solid ${S.border}`, paddingTop: 7 }}>
          <p style={{ fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 5 }}>Konfiguration</p>
          {node.type === "number_format" && <NumberFormatConfig config={node.config} onChange={updateConfig} />}
          {node.type === "date_format"   && <DateFormatConfig   config={node.config} onChange={updateConfig} />}
          {node.type === "text"          && <TextConfig          config={node.config} onChange={updateConfig} />}
          {node.type === "concat"        && <ConcatConfig        config={node.config} onChange={updateConfig} inputs={node.inputs} />}
        </div>

        {/* Output */}
        <div style={{ borderTop: `1px solid ${S.border}`, paddingTop: 7 }}>
          <p style={{ fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>Ausgabefeld</p>
          <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <input value={node.output_field || ""} onChange={(e) => updateOutputField(e.target.value)}
              onClick={(e) => e.stopPropagation()}
              style={{ ...inpS, flex: 1, fontFamily: "monospace", color: tt.color }}
              placeholder="ausgabe_feld" />
            {/* Right dot – output port (ref for SVG lines) */}
            <span
              ref={(el) => { if (el && outputRef) outputRef.current = el; }}
              draggable
              onDragStart={(e) => {
                e.stopPropagation();
                e.dataTransfer.setData("source_dataset_id", `__transform__${node.id}`);
                e.dataTransfer.setData("source_field", node.output_field || "");
              }}
              style={{ width: 10, height: 10, borderRadius: "50%", backgroundColor: tt.color, flexShrink: 0, cursor: "grab", border: `2px solid ${S.bgCard}`, boxShadow: `0 0 4px ${tt.color}` }}
              title="Ausgabe ins Ziel ziehen" />
          </div>
        </div>
      </div>
    </div>
  );
}
