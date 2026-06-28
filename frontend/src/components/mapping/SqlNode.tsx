import { useState, useRef, useEffect, useCallback } from "react";
import { ChevronDown, ChevronRight, Database, GripVertical, Plus, Sparkles, X, Minimize2, RefreshCw, Trash2 } from "lucide-react";
import api from "../../api/client";
import SqlEditorModal from "./SqlEditorModal";
import AiStreamModal from "./AiStreamModal";
import { explainSql, generateSql } from "../../services/aiService";
import { S, SQL_NODE_COLOR } from "./constants";
import { MinimizedNode } from "./MinimizedNode";

function SqlNode({ node, onRemove, onPositionChange, onUpdate, outputRef, dbConnections, onMiniPortsReady, canvasNodes, outputRefs, aiEnabled, mappingId }) {
  const [expanded, setExpanded] = useState(true);
  const [schemaLoading, setSchemaLoading] = useState(false);
  const [schemaError, setSchemaError] = useState(null);
  const [sqlModalOpen, setSqlModalOpen] = useState(false);
  const [sqlModalValue, setSqlModalValue] = useState("");
  const [aiMode, setAiMode] = useState(null); // "explain" | "generate"
  const [pendingSchemaDetect, setPendingSchemaDetect] = useState(false);
  const textareaRef = useRef(null);
  const miniLeftRef = useRef(null);
  const miniRightRef = useRef(null);
  useEffect(() => {
    if (node.minimized) {
      if (outputRef) outputRef.current = miniRightRef.current;
      if (onMiniPortsReady) onMiniPortsReady(node.id, miniLeftRef.current, miniRightRef.current);
    }
  }, [node.minimized, onMiniPortsReady]);

  useEffect(() => {
    if (pendingSchemaDetect && node.sql?.trim()) {
      setPendingSchemaDetect(false);
      loadSchema();
    }
  }, [pendingSchemaDetect, node.sql]);

  const handleMouseDown = (e) => {
    if (e.target.closest("button") || e.target.closest("select") || e.target.closest("textarea") || e.target.closest("input")) return;
    e.preventDefault(); e.stopPropagation();
    const startX = e.clientX - node.x;
    const startY = e.clientY - node.y;
    const onMove = (ev) => onPositionChange(node.id, ev.clientX - startX, ev.clientY - startY);
    const onUp = () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  const set = (k, v) => onUpdate({ ...node, [k]: v });

  const loadSchema = useCallback(async () => {
    if (!node.sql?.trim()) return;
    setSchemaLoading(true);
    setSchemaError(null);
    try {
      const { data } = await api.post("/api/mappings/sql-schema", {
        sql: node.sql,
        connection_id: node.connection_id,
        canvas_nodes: canvasNodes || [],
        external_tables: node.external_tables || [],
      });
      if (data.error) {
        setSchemaError(data.error);
      } else {
        onUpdate({ ...node, output_fields: data.columns });
      }
    } catch (e) {
      setSchemaError(e.message);
    } finally {
      setSchemaLoading(false);
    }
  }, [node, canvasNodes, onUpdate]);

  const detectParams = useCallback(() => {
    const sql = node.sql || "";
    const matches = [...sql.matchAll(/:([a-zA-Z_][a-zA-Z0-9_]*)/g)];
    const unique = [...new Set(matches.map(m => m[1]))];
    const existing = node.param_mappings || [];
    const updated = unique.map(p => {
      const ex = existing.find(e => e.param === p);
      return ex || { param: p, source_field: p };
    });
    onUpdate({ ...node, param_mappings: updated });
  }, [node, onUpdate]);

  const mode = node.mode || "scalar";

  if (node.minimized) {
    return (
      <div style={{ position: "absolute", left: node.x, top: node.y, zIndex: 10, overflow: "visible", width: 44, height: 44 }}
        onMouseDown={handleMouseDown}>
        <MinimizedNode
          type="sql" color={SQL_NODE_COLOR} label="SQL"
          onExpand={() => onUpdate({ ...node, minimized: false })}
          onMouseDown={handleMouseDown}
          portLeftRef={miniLeftRef} portRightRef={miniRightRef}
          onPortLeftDrop={null} onPortRightDragStart={null}
        />
      </div>
    );
  }

  return (
    <>
    <div draggable={false} style={{ position: "absolute", left: node.x, top: node.y, width: 260, zIndex: 10, userSelect: "none", boxShadow: "0 8px 32px rgba(0,0,0,0.5)", borderRadius: 6, overflow: "hidden", border: `1px solid ${SQL_NODE_COLOR}55`, backgroundColor: S.bgCard }}
      onClick={(e) => e.stopPropagation()}>

      {/* Header */}
      <div onMouseDown={handleMouseDown} draggable={false}
        style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 10px", cursor: "grab", backgroundColor: `${SQL_NODE_COLOR}12`, borderBottom: `1px solid ${SQL_NODE_COLOR}33` }}>
        <GripVertical size={12} style={{ color: S.textDim, flexShrink: 0 }} />
        <Database size={11} style={{ color: SQL_NODE_COLOR, flexShrink: 0 }} />
        <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: SQL_NODE_COLOR, flex: 1 }}>SQL Node</span>
        <button onClick={() => setExpanded((v) => !v)}
          style={{ color: S.textDim, lineHeight: 1, background: "none", border: "none", cursor: "pointer", padding: 2 }}>
          {expanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        </button>
        <button onClick={() => onUpdate({ ...node, minimized: true })} title="Minimieren" style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 0, display: "flex" }}><Minimize2 size={10} /></button>
        <button onClick={(e) => { e.stopPropagation(); onRemove(node.id); }}
          style={{ color: S.textDim, flexShrink: 0, lineHeight: 1, background: "none", border: "none", cursor: "pointer" }}
          onMouseEnter={(e) => e.currentTarget.style.color = "#e07070"}
          onMouseLeave={(e) => e.currentTarget.style.color = S.textDim}>
          <X size={12} />
        </button>
      </div>

      {expanded && (
        <div style={{ padding: "8px 10px", display: "flex", flexDirection: "column", gap: 7 }}>
          {/* Verbindung */}
          <div>
            <label style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.08em", color: S.textDim, display: "block", marginBottom: 3 }}>Verbindung</label>
            <select value={node.connection_id || ""}
              onChange={(e) => set("connection_id", parseInt(e.target.value) || null)}
              style={{ width: "100%", backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, color: node.connection_id ? SQL_NODE_COLOR : S.textDim, fontSize: 11, padding: "4px 8px", outline: "none", cursor: "pointer" }}>
              <option value="">– Verbindung wählen –</option>
              {dbConnections.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.db_type})</option>)}
            </select>
          </div>

          {/* Modus */}
          <div>
            <label style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.08em", color: S.textDim, display: "block", marginBottom: 3 }}>Modus</label>
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
              {[
                { v: "scalar",    l: "Scalar",    hint: "1 Wert pro Zeile" },
                { v: "column",    l: "Spalte",    hint: "Alle Zeilen einmalig" },
                { v: "transform", l: "Transform", hint: "SQL auf Canvas-Daten" },
                { v: "lookup",    l: "Lookup",    hint: "Felder per SQL anreichern" },
              ].map((m) => (
                <button key={m.v} onClick={() => set("mode", m.v)} title={m.hint}
                  style={{ flex: 1, padding: "4px 4px", borderRadius: 4, fontSize: 9, fontWeight: 600, cursor: "pointer",
                    backgroundColor: mode === m.v ? `${SQL_NODE_COLOR}22` : S.bgEl,
                    border: `1px solid ${mode === m.v ? SQL_NODE_COLOR : S.border}`,
                    color: mode === m.v ? SQL_NODE_COLOR : S.textDim }}>
                  {m.l}
                </button>
              ))}
            </div>
            <p style={{ fontSize: 9, color: S.textDim, marginTop: 3, lineHeight: 1.3 }}>
              {mode === "scalar" ? "SQL pro Zeile · {Feldname} als Parameter"
               : mode === "column" ? "SQL einmalig · Ergebnis per Index"
               : mode === "transform" ? "SQL auf Canvas-Datasets · Ersetzt gesamten Output"
               : "SQL-Lookup · :param als Platzhalter · mehrere Output-Felder"}
            </p>
          </div>

          {/* Transform: Externe Tabellen */}
          {mode === "transform" && (
            <div>
              <label style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.08em", color: S.textDim, display: "block", marginBottom: 4 }}>
                Externe Tabellen (optional)
              </label>
              {(node.external_tables || []).map((ext, i) => (
                <div key={i} style={{ display: "flex", gap: 4, marginBottom: 4, alignItems: "center" }}>
                  <input value={ext.table || ""} onChange={e => {
                      const t = [...(node.external_tables || [])];
                      t[i] = { ...t[i], table: e.target.value };
                      set("external_tables", t);
                    }} placeholder="schema.Tabelle"
                    style={{ flex: 2, backgroundColor: S.bgMain, border: `1px solid ${S.border}`, borderRadius: 3, color: S.textBright, fontSize: 10, fontFamily: "monospace", padding: "3px 6px", outline: "none" }} />
                  <input value={ext.alias || ""} onChange={e => {
                      const t = [...(node.external_tables || [])];
                      t[i] = { ...t[i], alias: e.target.value };
                      set("external_tables", t);
                    }} placeholder="Alias"
                    style={{ flex: 1, backgroundColor: S.bgMain, border: `1px solid ${S.border}`, borderRadius: 3, color: SQL_NODE_COLOR, fontSize: 10, fontFamily: "monospace", padding: "3px 6px", outline: "none" }} />
                  <button onClick={() => set("external_tables", (node.external_tables || []).filter((_, idx) => idx !== i))}
                    style={{ color: S.textDim, background: "none", border: "none", cursor: "pointer", padding: 2 }}
                    onMouseEnter={e => e.currentTarget.style.color = "#e07070"}
                    onMouseLeave={e => e.currentTarget.style.color = S.textDim}>
                    <Trash2 size={10} />
                  </button>
                </div>
              ))}
              <button onClick={() => set("external_tables", [...(node.external_tables || []), { table: "", alias: "" }])}
                style={{ width: "100%", padding: "3px 0", borderRadius: 3, border: `1px dashed ${S.border}`, background: "none", color: S.textDim, cursor: "pointer", fontSize: 10 }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = SQL_NODE_COLOR; e.currentTarget.style.color = SQL_NODE_COLOR; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = S.border; e.currentTarget.style.color = S.textDim; }}>
                + Tabelle hinzufügen
              </button>
            </div>
          )}

          {/* Lookup: Sub-Modus + Parameter-Mapping */}
          {mode === "lookup" && (
            <>
              <div>
                <label style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.08em", color: S.textDim, display: "block", marginBottom: 3 }}>Ausführung</label>
                <div style={{ display: "flex", gap: 4 }}>
                  {[
                    { v: "row_by_row", l: "Zeile-für-Zeile", hint: "SQL pro Datensatz, :param = Feldwert" },
                    { v: "batch_in",   l: "Batch IN",        hint: "Einmalige IN-Query, alle Werte gesammelt" },
                  ].map(sm => (
                    <button key={sm.v} onClick={() => set("lookup_sub_mode", sm.v)} title={sm.hint}
                      style={{ flex: 1, padding: "4px 4px", borderRadius: 4, fontSize: 9, fontWeight: 600, cursor: "pointer",
                        backgroundColor: (node.lookup_sub_mode || "row_by_row") === sm.v ? `${SQL_NODE_COLOR}22` : S.bgEl,
                        border: `1px solid ${(node.lookup_sub_mode || "row_by_row") === sm.v ? SQL_NODE_COLOR : S.border}`,
                        color: (node.lookup_sub_mode || "row_by_row") === sm.v ? SQL_NODE_COLOR : S.textDim }}>
                      {sm.l}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 3 }}>
                  <label style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.08em", color: S.textDim }}>Parameter</label>
                  <button onClick={detectParams} title="Parameter aus SQL erkennen"
                    style={{ fontSize: 9, padding: "1px 6px", borderRadius: 3, cursor: "pointer", border: `1px solid ${SQL_NODE_COLOR}44`, background: `${SQL_NODE_COLOR}11`, color: SQL_NODE_COLOR }}>
                    ⟳ Erkennen
                  </button>
                </div>
                {(node.param_mappings || []).length === 0 && (
                  <p style={{ fontSize: 9, color: S.textDim, fontStyle: "italic" }}>
                    :param im SQL schreiben → "Erkennen" klicken
                  </p>
                )}
                {(node.param_mappings || []).map((pm, i) => (
                  <div key={pm.param} style={{ display: "flex", alignItems: "center", gap: 4, marginBottom: 3 }}>
                    <span style={{ fontSize: 10, fontFamily: "monospace", color: SQL_NODE_COLOR, minWidth: 60, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>:{pm.param}</span>
                    <span style={{ fontSize: 9, color: S.textDim }}>←</span>
                    <input
                      value={pm.source_field || ""}
                      onChange={e => {
                        const updated = [...(node.param_mappings || [])];
                        updated[i] = { ...updated[i], source_field: e.target.value };
                        set("param_mappings", updated);
                      }}
                      onClick={e => e.stopPropagation()}
                      placeholder="Quellfeld"
                      style={{ flex: 1, backgroundColor: S.bgMain, border: `1px solid ${S.border}`, borderRadius: 3, color: S.textBright, fontSize: 10, fontFamily: "monospace", padding: "3px 6px", outline: "none" }}
                    />
                  </div>
                ))}
              </div>
            </>
          )}

          {/* SQL */}
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 4, marginBottom: 3 }}>
              <label style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.08em", color: S.textDim, flex: 1 }}>SQL</label>
              {aiEnabled && (
                <>
                  <button onClick={() => setAiMode("explain")} title="✨ SQL erklären" disabled={!node.sql?.trim()}
                    style={{ fontSize: 9, padding: "1px 6px", borderRadius: 3, cursor: node.sql?.trim() ? "pointer" : "not-allowed", border: "1px solid rgba(252,228,153,0.3)", background: "rgba(252,228,153,0.07)", color: "#fce499", opacity: node.sql?.trim() ? 1 : 0.4, display: "flex", alignItems: "center", gap: 3 }}>
                    <Sparkles size={9} /> Erklären
                  </button>
                  <button onClick={() => setAiMode("generate")} title="✨ SQL generieren"
                    style={{ fontSize: 9, padding: "1px 6px", borderRadius: 3, cursor: "pointer", border: "1px solid rgba(252,228,153,0.3)", background: "rgba(252,228,153,0.07)", color: "#fce499", display: "flex", alignItems: "center", gap: 3 }}>
                    <Sparkles size={9} /> Generieren
                  </button>
                </>
              )}
              <button onClick={(e) => { e.stopPropagation(); setSqlModalValue(node.sql || ""); setSqlModalOpen(true); }}
                title="SQL-Editor öffnen"
                style={{ fontSize: 9, padding: "1px 6px", borderRadius: 3, cursor: "pointer", border: `1px solid ${SQL_NODE_COLOR}44`, background: `${SQL_NODE_COLOR}11`, color: SQL_NODE_COLOR }}>
                ⛶ Vollbild
              </button>
            </div>
            <textarea
              ref={textareaRef}
              value={node.sql || ""}
              onChange={(e) => set("sql", e.target.value)}
              onClick={(e) => e.stopPropagation()}
              onDoubleClick={(e) => { e.stopPropagation(); setSqlModalValue(node.sql || ""); setSqlModalOpen(true); }}
              placeholder={mode === "scalar"
                ? "SELECT name FROM kunden WHERE id = {Kunden.id}"
                : "SELECT lookup_value FROM ref_table ORDER BY sort_nr"}
              rows={4}
              style={{ width: "100%", backgroundColor: S.bgMain, border: `1px solid ${SQL_NODE_COLOR}44`, borderRadius: 4, color: S.textBright, fontSize: 11, fontFamily: "monospace", padding: "5px 7px", outline: "none", resize: "vertical", boxSizing: "border-box", lineHeight: 1.5 }}
            />
          </div>

          {/* SQL Editor Modal */}
          {sqlModalOpen && (
            <SqlEditorModal
              sql={sqlModalValue}
              connectionId={node.connection_id}
              dbConnections={dbConnections}
              canvasNodes={canvasNodes}
              onSave={(newSql) => { set("sql", newSql); setSqlModalOpen(false); }}
              onClose={() => setSqlModalOpen(false)}
            />
          )}

          {/* Output-Feldname (nur Scalar/Column, wenn noch kein Schema erkannt) */}
          {mode !== "transform" && mode !== "lookup" && (node.output_fields || []).length === 0 && (
            <div>
              <label style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.08em", color: S.textDim, display: "block", marginBottom: 3 }}>Output-Feldname</label>
              <input value={node.output_field || ""}
                onChange={(e) => set("output_field", e.target.value)}
                onClick={(e) => e.stopPropagation()}
                placeholder="sql_ergebnis"
                style={{ width: "100%", backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, color: SQL_NODE_COLOR, fontSize: 11, fontFamily: "monospace", padding: "4px 8px", outline: "none", boxSizing: "border-box" }}
              />
            </div>
          )}

          {/* Schema erkennen Button – alle Modi */}
          {node.sql?.trim() && (
            <div>
              <button onClick={loadSchema} disabled={schemaLoading}
                style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "center", gap: 4, fontSize: 10, padding: "5px 0", borderRadius: 4, cursor: "pointer",
                  border: `1px solid ${SQL_NODE_COLOR}44`, background: `${SQL_NODE_COLOR}11`, color: SQL_NODE_COLOR }}>
                <RefreshCw size={10} className={schemaLoading ? "animate-spin" : ""} />
                {schemaLoading ? "Erkenne Spalten..." : "Spalten aus SELECT erkennen"}
              </button>
              {schemaError && <p style={{ fontSize: 9, color: "#e07070", marginTop: 4 }}>⚠ {schemaError}</p>}
              {(node.output_fields || []).length > 0 && (
                <button onClick={() => onUpdate({ ...node, output_fields: [] })}
                  style={{ marginTop: 3, width: "100%", fontSize: 9, padding: "3px 0", borderRadius: 4, cursor: "pointer",
                    border: `1px solid ${S.border}`, background: "none", color: S.textDim }}>
                  ✕ Zurück zu Einzel-Output
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* Output dots — output_fields (multi) hat immer Vorrang vor output_field (single) */}
      <div style={{ borderTop: `1px solid ${SQL_NODE_COLOR}22`, backgroundColor: `${SQL_NODE_COLOR}06` }}>
        {(node.output_fields || []).length > 0 ? (
          <div style={{ maxHeight: 160, overflowY: "auto", scrollbarWidth: "thin" }}>
            {(node.output_fields || []).map((field, i) => (
              <div key={field} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "5px 10px", borderTop: i > 0 ? `1px solid ${SQL_NODE_COLOR}11` : "none" }}>
                <span style={{ fontSize: 10, fontFamily: "monospace", color: SQL_NODE_COLOR, opacity: 0.9 }}>{field}</span>
                <div
                  ref={(el) => { if (outputRefs) outputRefs.current[`${node.id}_${i}`] = { current: el }; if (i === 0 && outputRef) outputRef.current = el; }}
                  data-sql-output={node.id}
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.setData("source_dataset_id", `__sql__${node.id}`);
                    e.dataTransfer.setData("source_field", field);
                    e.stopPropagation();
                  }}
                  style={{ width: 9, height: 9, borderRadius: "50%", backgroundColor: SQL_NODE_COLOR, cursor: "grab", flexShrink: 0, boxShadow: `0 0 5px ${SQL_NODE_COLOR}88` }}
                  title={`${field} auf Zielfeld ziehen`} />
              </div>
            ))}
          </div>
        ) : (
          <div style={{ padding: "6px 10px", display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 6 }}>
            <span style={{ fontSize: 9, fontFamily: "monospace", color: SQL_NODE_COLOR, opacity: 0.8 }}>
              {node.output_field || "–"}
            </span>
            <div ref={(el) => { if (outputRef) outputRef.current = el; }}
              data-sql-output={node.id}
              draggable
              onDragStart={(e) => {
                e.dataTransfer.setData("source_dataset_id", `__sql__${node.id}`);
                e.dataTransfer.setData("source_field", node.output_field || `sql_${node.id}`);
                e.stopPropagation();
              }}
              style={{ width: 10, height: 10, borderRadius: "50%", backgroundColor: SQL_NODE_COLOR, cursor: "grab", flexShrink: 0, boxShadow: `0 0 6px ${SQL_NODE_COLOR}88` }}
              title="Auf Zielfeld ziehen" />
          </div>
        )}
      </div>
    </div>

    {aiMode === "explain" && (
      <AiStreamModal
        title="✨ SQL erklären"
        readOnly
        autoGenerate
        noApply
        onGenerate={(_desc, onToken) => explainSql(node.sql || "", node.connection_id || null, mappingId, onToken)}
        onClose={() => setAiMode(null)}
      />
    )}
    {aiMode === "generate" && (
      <AiStreamModal
        title="✨ SQL generieren"
        placeholder='z.B. "Alle Kunden die im letzten Monat keine Bestellung hatten"'
        onGenerate={(desc, onToken) => generateSql(desc, node.connection_id || null, mappingId, onToken)}
        onApply={(sql) => {
          onUpdate({ ...node, sql: sql.trim(), output_fields: [] });
          setPendingSchemaDetect(true);
        }}
        onClose={() => setAiMode(null)}
        applyLabel="SQL übernehmen"
        warning={!mappingId ? "Mapping noch nicht gespeichert – die KI kennt keine Canvas-Datasets und wählt Tabellen nur anhand des Prompts. Bitte Mapping zuerst speichern für bessere Ergebnisse." : null}
      />
    )}
    </>
  );
}
// ─── Aggregation Node ──────────────────────────────────────────────────────────

export default SqlNode;
