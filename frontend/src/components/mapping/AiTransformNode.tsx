import { useRef, useState } from "react";
import { Sparkles, GripVertical, Plus, X, Play, Loader2, ChevronDown, ChevronUp, Database } from "lucide-react";
import { S } from "./constants";
import api from "../../api/client";

export const AI_NODE_COLOR = "#a78bfa";
const DOT = 10;
const ACTIVE_BORDER = "#fce499";

const FIELD_TYPES = ["string", "integer", "float", "boolean"];

const TYPE_COLORS: Record<string, string> = {
  string: "#94a3b8", integer: "#60a5fa", float: "#34d399",
  boolean: "#f472b6", date: "#f59e0b", datetime: "#f59e0b",
};

interface OutputField { name: string; type: string; }
interface AvailableField { name: string; type: string; dataset: string; }
interface AiNode {
  id: string; x: number; y: number;
  prompt_template: string;
  output_fields: OutputField[];
  model: string | null;
  batch_size: number;
}

export default function AiTransformNode({
  node, onUpdate, onRemove, onPositionChange, outputRefs,
  availableFields = [],
  debugHighlight, isActive, onActivate,
}: {
  node: AiNode; onUpdate: (n: AiNode) => void; onRemove: () => void;
  onPositionChange: (id: string, x: number, y: number) => void;
  outputRefs: any;
  availableFields?: AvailableField[];
  debugHighlight?: boolean; isActive?: boolean; onActivate?: () => void;
}) {
  const dragging   = useRef(false);
  const offset     = useRef({ x: 0, y: 0 });
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const C = AI_NODE_COLOR;

  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewResult, setPreviewResult]   = useState<any>(null);
  const [previewError, setPreviewError]     = useState<string | null>(null);
  const [expanded, setExpanded]             = useState(true);
  const [fieldsOpen, setFieldsOpen]         = useState(true);
  const [fieldSearch, setFieldSearch]       = useState("");

  const handleMouseDown = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest("select,input,button,textarea")) return;
    e.preventDefault(); e.stopPropagation();
    onActivate?.();
    dragging.current = true;
    offset.current = { x: e.clientX - node.x, y: e.clientY - node.y };
    const onMove = (ev: MouseEvent) => {
      if (!dragging.current) return;
      onPositionChange(node.id, ev.clientX - offset.current.x, ev.clientY - offset.current.y);
    };
    const onUp = () => {
      dragging.current = false;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  const insertPlaceholder = (fieldName: string) => {
    const ta = textareaRef.current;
    if (!ta) {
      onUpdate({ ...node, prompt_template: (node.prompt_template || "") + `{{${fieldName}}}` });
      return;
    }
    const start = ta.selectionStart ?? (node.prompt_template || "").length;
    const end   = ta.selectionEnd   ?? start;
    const val   = node.prompt_template || "";
    const next  = val.slice(0, start) + `{{${fieldName}}}` + val.slice(end);
    onUpdate({ ...node, prompt_template: next });
    // restore cursor after React re-render
    requestAnimationFrame(() => {
      ta.focus();
      const newPos = start + fieldName.length + 4;
      ta.setSelectionRange(newPos, newPos);
    });
  };

  const outputFields: OutputField[] = node.output_fields || [];

  const addField = () => onUpdate({
    ...node,
    output_fields: [...outputFields, { name: `feld_${outputFields.length + 1}`, type: "string" }],
  });
  const removeField = (i: number) => onUpdate({
    ...node, output_fields: outputFields.filter((_, idx) => idx !== i),
  });
  const updateField = (i: number, key: "name" | "type", val: string) => onUpdate({
    ...node, output_fields: outputFields.map((f, idx) => idx === i ? { ...f, [key]: val } : f),
  });

  const handlePreview = async () => {
    if (!node.prompt_template || outputFields.length === 0) return;
    setPreviewLoading(true); setPreviewError(null); setPreviewResult(null);
    try {
      const { data } = await api.post("/api/ai/transform-preview", {
        prompt_template: node.prompt_template,
        output_fields:   outputFields,
        model:           node.model || null,
      });
      setPreviewResult(data.result);
    } catch (e: any) {
      setPreviewError(e.response?.data?.detail || e.message);
    } finally {
      setPreviewLoading(false);
    }
  };

  const activeBorder = isActive && !debugHighlight;
  const borderColor  = debugHighlight ? `${C}cc` : activeBorder ? ACTIVE_BORDER : `${C}55`;
  const boxShadow    = debugHighlight
    ? `0 0 0 2px ${C}, 0 0 20px ${C}55, 0 8px 32px rgba(0,0,0,0.5)`
    : activeBorder
    ? `0 0 0 2px ${ACTIVE_BORDER}, 0 8px 32px rgba(0,0,0,0.5)`
    : "0 8px 32px rgba(0,0,0,0.5)";

  const labelStyle = { fontSize: 9, color: S.textDim, textTransform: "uppercase" as const, letterSpacing: "0.07em", marginBottom: 2 };
  const inp = (extra?: object) => ({
    backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 3,
    color: S.textBright, fontSize: 11, padding: "3px 6px", outline: "none", width: "100%", ...extra,
  });

  const filteredFields = availableFields.filter(f =>
    f.name.toLowerCase().includes(fieldSearch.toLowerCase())
  );

  // Group by dataset
  const byDataset: Record<string, AvailableField[]> = {};
  for (const f of filteredFields) {
    if (!byDataset[f.dataset]) byDataset[f.dataset] = [];
    byDataset[f.dataset].push(f);
  }

  return (
    <div
      draggable={false}
      onMouseDown={handleMouseDown}
      style={{
        position: "absolute", left: node.x, top: node.y,
        width: 300, userSelect: "none", cursor: "grab",
        backgroundColor: S.bgCard, border: `1.5px solid ${borderColor}`,
        borderRadius: 10, boxShadow, zIndex: isActive ? 10 : 1,
      }}
    >
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 10px",
        borderBottom: `1px solid ${C}33`, borderRadius: "8px 8px 0 0",
        background: `linear-gradient(135deg, ${C}22, ${C}11)` }}>
        <GripVertical size={12} color={C} style={{ flexShrink: 0 }} />
        <Sparkles size={13} color={C} style={{ flexShrink: 0 }} />
        <span style={{ fontSize: 11, fontWeight: 700, color: C, flex: 1 }}>KI-Transform</span>
        <button onClick={() => setExpanded(e => !e)}
          style={{ background: "none", border: "none", cursor: "pointer", color: S.textDim, padding: 2 }}>
          {expanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
        </button>
        <button onClick={onRemove}
          style={{ background: "none", border: "none", cursor: "pointer", color: S.textDim, padding: 2 }}>
          <X size={11} />
        </button>
      </div>

      {expanded && (
        <div style={{ padding: "10px 10px 8px" }}>

          {/* ── Verfügbare Felder Panel ── */}
          <div style={{ marginBottom: 10, border: `1px solid ${C}33`, borderRadius: 6, overflow: "hidden" }}>
              <button
                onClick={() => setFieldsOpen(o => !o)}
                style={{ display: "flex", alignItems: "center", gap: 5, width: "100%", padding: "5px 8px",
                  background: `${C}11`, border: "none", cursor: "pointer", color: S.textDim }}>
                <Database size={10} color={C} />
                <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em", color: C, flex: 1, textAlign: "left" }}>
                  Verfügbare Felder
                </span>
                <span style={{ fontSize: 9, color: S.textDim }}>Doppelklick → in Prompt einfügen</span>
                {fieldsOpen ? <ChevronUp size={9} color={S.textDim} /> : <ChevronDown size={9} color={S.textDim} />}
              </button>

              {fieldsOpen && (
                <div>
                  {/* Suche */}
                  <div style={{ padding: "4px 6px", borderBottom: `1px solid ${S.border}` }}>
                    <input
                      value={fieldSearch}
                      onChange={e => setFieldSearch(e.target.value)}
                      placeholder="Feld suchen..."
                      style={{ ...inp(), fontSize: 10, padding: "2px 5px" }}
                    />
                  </div>
                  {/* Feldliste */}
                  <div style={{ maxHeight: 140, overflowY: "auto", padding: "4px 0" }}>
                    {Object.entries(byDataset).map(([ds, fields]) => (
                      <div key={ds}>
                        <div style={{ fontSize: 8, color: S.textDim, padding: "2px 8px 1px",
                          textTransform: "uppercase", letterSpacing: "0.08em", opacity: 0.6 }}>
                          {ds}
                        </div>
                        {fields.map(f => (
                          <div
                            key={f.name}
                            onDoubleClick={() => insertPlaceholder(f.name)}
                            title={`Doppelklick: {{${f.name}}} in Prompt einfügen`}
                            style={{ display: "flex", alignItems: "center", gap: 6,
                              padding: "3px 8px", cursor: "pointer",
                              transition: "background 0.1s" }}
                            onMouseEnter={e => (e.currentTarget.style.backgroundColor = `${C}15`)}
                            onMouseLeave={e => (e.currentTarget.style.backgroundColor = "transparent")}
                          >
                            <span style={{ fontSize: 8, padding: "1px 4px", borderRadius: 3,
                              backgroundColor: `${TYPE_COLORS[f.type] || "#94a3b8"}22`,
                              color: TYPE_COLORS[f.type] || "#94a3b8", fontWeight: 600,
                              minWidth: 28, textAlign: "center", textTransform: "uppercase" }}>
                              {f.type === "integer" ? "INT" : f.type === "boolean" ? "BOOL" : f.type === "datetime" ? "DT" : f.type.slice(0, 3).toUpperCase()}
                            </span>
                            <span style={{ fontSize: 10, color: S.textBright, fontFamily: "monospace", flex: 1 }}>
                              {f.name}
                            </span>
                            <span style={{ fontSize: 9, color: S.textDim, opacity: 0.5 }}>
                              {`{{${f.name}}}`}
                            </span>
                          </div>
                        ))}
                      </div>
                    ))}
                    {availableFields.length === 0 && (
                      <div style={{ fontSize: 10, color: S.textDim, padding: "6px 8px", fontStyle: "italic" }}>
                        Erst Datasets auf den Canvas ziehen
                      </div>
                    )}
                    {availableFields.length > 0 && filteredFields.length === 0 && (
                      <div style={{ fontSize: 10, color: S.textDim, padding: "6px 8px", fontStyle: "italic" }}>
                        Keine Felder gefunden
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

          {/* Prompt Template */}
          <div style={{ marginBottom: 8 }}>
            <div style={labelStyle}>Prompt-Template</div>
            <textarea
              ref={textareaRef}
              value={node.prompt_template || ""}
              onChange={e => onUpdate({ ...node, prompt_template: e.target.value })}
              placeholder={"Kategorisiere dieses Produkt:\nName: {{cArtNr}}\nBeschreibung: {{cName}}\nGib category (A/B/C) zurück."}
              rows={4}
              style={{ ...inp(), resize: "vertical", fontFamily: "monospace", lineHeight: 1.5 }}
            />
          </div>

          {/* Output-Felder */}
          <div style={{ marginBottom: 8 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
              <div style={labelStyle}>Ausgabefelder</div>
              <button onClick={addField}
                style={{ display: "flex", alignItems: "center", gap: 3, background: "none", border: "none",
                  cursor: "pointer", color: C, fontSize: 10 }}>
                <Plus size={9} /> Feld
              </button>
            </div>
            {outputFields.map((f, i) => (
              <div key={i} style={{ display: "flex", gap: 4, alignItems: "center", marginBottom: 4 }}>
                {/* Output dot */}
                <div ref={el => {
                    if (outputRefs?.current) {
                      const key = node.id + "_" + i;
                      if (!outputRefs.current[key]) outputRefs.current[key] = { current: null };
                      outputRefs.current[key].current = el;
                    }
                  }}
                  draggable={!!f.name}
                  onDragStart={e => {
                    if (!f.name) { e.preventDefault(); return; }
                    e.stopPropagation();
                    e.dataTransfer.setData("source_dataset_id", "__ai__" + node.id);
                    e.dataTransfer.setData("source_field", f.name);
                  }}
                  style={{ width: DOT, height: DOT, borderRadius: "50%",
                    backgroundColor: f.name ? C : "#4b5563", flexShrink: 0,
                    border: "2px solid rgba(255,255,255,0.3)",
                    boxShadow: f.name ? `0 0 6px ${C}88` : "none",
                    cursor: f.name ? "grab" : "default" }}
                  title={f.name ? f.name + " auf Zielfeld ziehen" : "Feldname eingeben"} />
                <input value={f.name} onChange={e => updateField(i, "name", e.target.value)}
                  style={{ ...inp(), flex: 1 }} placeholder="feldname" />
                <select value={f.type} onChange={e => updateField(i, "type", e.target.value)}
                  style={{ ...inp(), width: 70, cursor: "pointer" }}>
                  {FIELD_TYPES.map(t => <option key={t}>{t}</option>)}
                </select>
                <button onClick={() => removeField(i)}
                  style={{ background: "none", border: "none", cursor: "pointer", color: "#f87171", padding: 1 }}>
                  <X size={10} />
                </button>
              </div>
            ))}
            {outputFields.length === 0 && (
              <div style={{ fontSize: 10, color: S.textDim, fontStyle: "italic" }}>
                Noch keine Ausgabefelder definiert
              </div>
            )}
          </div>

          {/* Model + Batch */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 60px", gap: 6, marginBottom: 8 }}>
            <div>
              <div style={labelStyle}>Modell (leer = Standard)</div>
              <input value={node.model || ""}
                onChange={e => onUpdate({ ...node, model: e.target.value || null })}
                style={inp()} placeholder="z.B. qwen2.5:7b" />
            </div>
            <div>
              <div style={labelStyle}>Batch</div>
              <input type="number" min={1} max={50} value={node.batch_size || 10}
                onChange={e => onUpdate({ ...node, batch_size: parseInt(e.target.value) || 10 })}
                style={inp()} />
            </div>
          </div>

          {/* Preview Button */}
          <button onClick={handlePreview} disabled={previewLoading || !node.prompt_template || outputFields.length === 0}
            style={{ display: "flex", alignItems: "center", gap: 5, width: "100%", justifyContent: "center",
              padding: "5px 0", borderRadius: 5, border: `1px solid ${C}55`,
              backgroundColor: `${C}15`, color: C, fontSize: 11, cursor: "pointer",
              opacity: (!node.prompt_template || outputFields.length === 0) ? 0.4 : 1 }}>
            {previewLoading ? <Loader2 size={11} className="animate-spin" /> : <Play size={11} />}
            Vorschau (1 Beispiel-Row)
          </button>

          {previewError && (
            <div style={{ marginTop: 6, fontSize: 10, color: "#f87171", backgroundColor: "rgba(248,113,113,0.1)",
              borderRadius: 4, padding: "4px 8px" }}>
              {previewError}
            </div>
          )}
          {previewResult && (
            <div style={{ marginTop: 6, backgroundColor: S.bgEl, borderRadius: 4, padding: "6px 8px" }}>
              <div style={{ fontSize: 9, color: C, marginBottom: 3, textTransform: "uppercase" }}>Vorschau-Ergebnis</div>
              {Object.entries(previewResult).map(([k, v]) => (
                <div key={k} style={{ fontSize: 11, color: S.textBright }}>
                  <span style={{ color: S.textDim }}>{k}: </span>{String(v)}
                </div>
              ))}
            </div>
          )}

          <div style={{ marginTop: 6, fontSize: 9, color: "#fbbf24", opacity: 0.7 }}>
            ⚠ KI-Transforms erhöhen die Ausführungszeit (1 LLM-Aufruf pro {node.batch_size || 10} Zeilen)
          </div>
        </div>
      )}
    </div>
  );
}
