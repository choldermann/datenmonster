import { useEffect, useRef, useState } from "react";
import { Filter, Plus, X } from "lucide-react";
import { S, FILTER_COLOR, SORT_COLOR } from "./constants";

function SortEditor({ node, onSave, onClose }) {
  const [sorts, setSorts] = useState(() => (node.sorts || []).length > 0 ? node.sorts : [{ field: "", dir: "asc" }]);
  const fields = node.dataset_columns || [];

  const addSort = () => setSorts(s => [...s, { field: "", dir: "asc" }]);
  const removeSort = (i) => setSorts(s => s.filter((_, idx) => idx !== i));
  const update = (i, key, val) => setSorts(s => s.map((item, idx) => idx === i ? { ...item, [key]: val } : item));

  const handleSave = () => {
    const valid = sorts.filter(s => s.field);
    onSave(valid);
    onClose();
  };

  const iS = { backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, color: S.textBright, fontSize: 12, padding: "6px 8px", outline: "none", flex: 1 };

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 60, display: "flex", alignItems: "center", justifyContent: "center", backgroundColor: "rgba(0,0,0,0.6)" }} onClick={onClose}>
      <div style={{ backgroundColor: S.bgCard, border: `1px solid ${SORT_COLOR}55`, borderRadius: 8, padding: 20, width: 420, boxShadow: "0 16px 48px rgba(0,0,0,0.6)" }} onClick={e => e.stopPropagation()}>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <div>
            <p style={{ fontSize: 11, color: SORT_COLOR, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}>Sortierung</p>
            <p style={{ fontSize: 11, color: S.textDim, marginTop: 2 }}>{node.dataset_name}</p>
          </div>
          <button onClick={onClose} style={{ color: S.textDim }}><X size={14} /></button>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
          {sorts.map((s, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 11, color: S.textDim, width: 18, textAlign: "right", flexShrink: 0 }}>{i + 1}.</span>
              <select style={iS} value={s.field} onChange={e => update(i, "field", e.target.value)}>
                <option value="">— Spalte wählen —</option>
                {fields.map(f => <option key={f} value={f}>{f}</option>)}
              </select>
              <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
                {[["asc", "↑ A→Z"], ["desc", "↓ Z→A"]].map(([val, label]) => (
                  <button key={val} onClick={() => update(i, "dir", val)}
                    style={{ padding: "5px 10px", borderRadius: 4, fontSize: 11, fontWeight: 600, cursor: "pointer", border: `1px solid ${s.dir === val ? SORT_COLOR : S.border}`, backgroundColor: s.dir === val ? `${SORT_COLOR}20` : "transparent", color: s.dir === val ? SORT_COLOR : S.textDim }}>
                    {label}
                  </button>
                ))}
              </div>
              <button onClick={() => removeSort(i)} style={{ color: S.textDim, flexShrink: 0 }}><X size={12} /></button>
            </div>
          ))}
        </div>

        <button onClick={addSort}
          style={{ width: "100%", padding: "6px", borderRadius: 4, fontSize: 11, fontWeight: 600, cursor: "pointer", backgroundColor: `${SORT_COLOR}12`, border: `1px dashed ${SORT_COLOR}55`, color: SORT_COLOR, marginBottom: 14, display: "flex", alignItems: "center", justifyContent: "center", gap: 4 }}>
          <Plus size={11} /> Spalte hinzufügen
        </button>

        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={handleSave}
            style={{ flex: 1, padding: "8px", borderRadius: 4, cursor: "pointer", backgroundColor: SORT_COLOR, border: "none", color: "#111", fontSize: 12, fontWeight: 700 }}>
            Sortierung speichern
          </button>
          {(node.sorts || []).length > 0 && (
            <button onClick={() => { onSave([]); onClose(); }}
              style={{ padding: "8px 14px", borderRadius: 4, cursor: "pointer", backgroundColor: "rgba(224,112,112,0.1)", border: "1px solid rgba(224,112,112,0.3)", color: "#e07070", fontSize: 12 }}>
              Entfernen
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function FilterEditor({ datasetId, field, currentFilter, onSave, onClose }) {
  const [expr, setExpr] = useState(currentFilter || "");
  const inputRef = useRef(null);

  useEffect(() => { setTimeout(() => inputRef.current?.focus(), 50); }, []);

  const EXAMPLES = ["> 100", "< 0", "= 1", '= "aktiv"', '!= ""', "LIKE %GmbH%", ">= 2024-01-01"];

  const handleSave = () => { onSave(datasetId, field, expr.trim()); onClose(); };

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 60, display: "flex", alignItems: "center", justifyContent: "center", backgroundColor: "rgba(0,0,0,0.6)" }} onClick={onClose}>
      <div style={{ backgroundColor: S.bgCard, border: `1px solid ${FILTER_COLOR}55`, borderRadius: 8, padding: 20, width: 380, boxShadow: "0 16px 48px rgba(0,0,0,0.6)" }} onClick={(e) => e.stopPropagation()}>

        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
          <div>
            <p style={{ fontSize: 11, color: FILTER_COLOR, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}>Filter</p>
            <p style={{ fontSize: 11, color: S.textBright, fontFamily: "monospace", marginTop: 2 }}>{field}</p>
          </div>
          <button onClick={onClose} style={{ color: S.textDim }}><X size={14} /></button>
        </div>

        {/* Input */}
        <div style={{ marginBottom: 12 }}>
          <p style={{ fontSize: 10, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>Bedingung</p>
          <div style={{ display: "flex", alignItems: "center", gap: 6, backgroundColor: S.bgMain, border: `1px solid ${FILTER_COLOR}66`, borderRadius: 4, padding: "6px 10px" }}>
            <span style={{ fontSize: 11, fontFamily: "monospace", color: S.textDim, flexShrink: 0 }}>{field}</span>
            <input
              ref={inputRef}
              value={expr}
              onChange={(e) => setExpr(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleSave(); if (e.key === "Escape") onClose(); }}
              placeholder="> 100"
              style={{ flex: 1, background: "transparent", border: "none", outline: "none", fontSize: 12, fontFamily: "monospace", color: S.textBright }}
            />
            {expr && (
              <button onClick={() => setExpr("")} style={{ color: S.textDim, lineHeight: 1 }}><X size={11} /></button>
            )}
          </div>
          <p style={{ fontSize: 10, color: S.textDim, marginTop: 4 }}>Operatoren: = != &lt; &gt; &lt;= &gt;= LIKE · Text in Anführungszeichen</p>
        </div>

        {/* Quick examples */}
        <div style={{ marginBottom: 16 }}>
          <p style={{ fontSize: 10, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>Beispiele</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {EXAMPLES.map((ex) => (
              <button key={ex} onClick={() => setExpr(ex)}
                style={{ fontSize: 10, fontFamily: "monospace", padding: "3px 7px", borderRadius: 3, cursor: "pointer", backgroundColor: expr === ex ? FILTER_COLOR + "22" : S.bgEl, border: `1px solid ${expr === ex ? FILTER_COLOR : S.border}`, color: expr === ex ? FILTER_COLOR : S.textDim }}>
                {ex}
              </button>
            ))}
          </div>
        </div>

        {/* Actions */}
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={handleSave}
            style={{ flex: 1, padding: "8px", borderRadius: 4, cursor: "pointer", backgroundColor: FILTER_COLOR, border: "none", color: "#111", fontSize: 12, fontWeight: 700 }}>
            Filter setzen
          </button>
          {currentFilter && (
            <button onClick={() => { onSave(datasetId, field, ""); onClose(); }}
              style={{ padding: "8px 14px", borderRadius: 4, cursor: "pointer", backgroundColor: "rgba(224,112,112,0.1)", border: "1px solid rgba(224,112,112,0.3)", color: "#e07070", fontSize: 12 }}>
              Entfernen
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Draggable Dataset Node ────────────────────────────────────────────────────


const CAST_COLOR = "#38bdf8"; // sky

const CAST_TYPES = [
  { v: "string",   l: "Text",    c: "#6a6a6a" },
  { v: "integer",  l: "Ganzzahl", c: "#93c5fd" },
  { v: "decimal",  l: "Dezimal", c: "#6ee7b7" },
  { v: "date",     l: "Datum",   c: "#fcd34d" },
  { v: "datetime", l: "Datum+Zeit", c: "#fbbf24" },
  { v: "boolean",  l: "Boolean", c: "#c4b5fd" },
];

const DATE_INPUT_FORMATS = [
  "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y",
  "%Y%m%d", "%d.%m.%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S",
];

const DECIMAL_SEPS = [
  { v: ".", l: "Punkt (1234.56)" },
  { v: ",", l: "Komma (1234,56)" },
];

// TypeConvertEditor wird für zwei Zwecke genutzt:
// 1. cast_rules im DatasetNode (Quelle): datasetId + field → onSave(dsId, field, rule)
// 2. target_type in Connection (Ziel):   mode="target"  → onSave(rule)
function TypeConvertEditor({ datasetId, field, currentCast, onSave, onClose, mode = "source", title = null }) {
  const [castType, setCastType] = useState(currentCast?.type || "");
  const [dateFormat, setDateFormat] = useState(currentCast?.date_format || "%d.%m.%Y");
  const [decSep, setDecSep] = useState(currentCast?.decimal_sep || ",");
  const [onError, setOnError] = useState(currentCast?.on_error || "null");

  const handleSave = () => {
    if (!castType) {
      if (mode === "target") { onSave(null); }
      else { onSave(datasetId, field, null); }
      onClose();
      return;
    }
    const rule = { type: castType, date_format: dateFormat, decimal_sep: decSep, on_error: onError };
    if (mode === "target") { onSave(rule); }
    else { onSave(datasetId, field, rule); }
    onClose();
  };

  const iS = { backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, color: S.textBright, fontSize: 11, padding: "5px 8px", outline: "none", width: "100%" };

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 60, display: "flex", alignItems: "center", justifyContent: "center", backgroundColor: "rgba(0,0,0,0.6)" }} onClick={onClose}>
      <div style={{ backgroundColor: S.bgCard, border: `1px solid ${CAST_COLOR}55`, borderRadius: 8, padding: 20, width: 360, boxShadow: "0 16px 48px rgba(0,0,0,0.6)" }} onClick={e => e.stopPropagation()}>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <div>
            <p style={{ fontSize: 11, color: CAST_COLOR, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}>{title || (mode === "target" ? "Zieltyp festlegen" : "Typ-Konvertierung")}</p>
            <p style={{ fontSize: 11, color: S.textBright, fontFamily: "monospace", marginTop: 2 }}>{field}</p>
          </div>
          <button onClick={onClose} style={{ color: S.textDim, background: "none", border: "none", cursor: "pointer" }}><X size={14} /></button>
        </div>

        <div style={{ marginBottom: 12 }}>
          <p style={{ fontSize: 10, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>Zieltyp</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            <button onClick={() => setCastType("")}
              style={{ padding: "4px 10px", borderRadius: 4, fontSize: 10, cursor: "pointer", border: `1px solid ${!castType ? CAST_COLOR : S.border}`, backgroundColor: !castType ? `${CAST_COLOR}20` : "transparent", color: !castType ? CAST_COLOR : S.textDim }}>
              Keine
            </button>
            {CAST_TYPES.map(t => (
              <button key={t.v} onClick={() => setCastType(t.v)}
                style={{ padding: "4px 10px", borderRadius: 4, fontSize: 10, cursor: "pointer", border: `1px solid ${castType === t.v ? t.c : S.border}`, backgroundColor: castType === t.v ? t.c + "20" : "transparent", color: castType === t.v ? t.c : S.textDim }}>
                {t.l}
              </button>
            ))}
          </div>
        </div>

        {(castType === "date" || castType === "datetime") && (
          <div style={{ marginBottom: 12 }}>
            <p style={{ fontSize: 10, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>Eingangsformat</p>
            <select style={iS} value={dateFormat} onChange={e => setDateFormat(e.target.value)}>
              {DATE_INPUT_FORMATS.map(f => <option key={f} value={f}>{f}</option>)}
            </select>
            <p style={{ fontSize: 10, color: S.textDim, marginTop: 4 }}>Beispiel: 31.12.2024 → %d.%m.%Y</p>
          </div>
        )}

        {castType === "decimal" && (
          <div style={{ marginBottom: 12 }}>
            <p style={{ fontSize: 10, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>Dezimaltrennzeichen</p>
            <div style={{ display: "flex", gap: 6 }}>
              {DECIMAL_SEPS.map(s => (
                <button key={s.v} onClick={() => setDecSep(s.v)}
                  style={{ flex: 1, padding: "5px", borderRadius: 4, fontSize: 10, cursor: "pointer", border: `1px solid ${decSep === s.v ? CAST_COLOR : S.border}`, backgroundColor: decSep === s.v ? `${CAST_COLOR}20` : "transparent", color: decSep === s.v ? CAST_COLOR : S.textDim }}>
                  {s.l}
                </button>
              ))}
            </div>
          </div>
        )}

        <div style={{ marginBottom: 16 }}>
          <p style={{ fontSize: 10, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>Bei Fehler</p>
          <div style={{ display: "flex", gap: 6 }}>
            {[["null", "Leer lassen"], ["skip", "Zeile überspringen"], ["error", "Fehler werfen"]].map(([v, l]) => (
              <button key={v} onClick={() => setOnError(v)}
                style={{ flex: 1, padding: "5px", borderRadius: 4, fontSize: 10, cursor: "pointer", border: `1px solid ${onError === v ? CAST_COLOR : S.border}`, backgroundColor: onError === v ? `${CAST_COLOR}20` : "transparent", color: onError === v ? CAST_COLOR : S.textDim }}>
                {l}
              </button>
            ))}
          </div>
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={handleSave}
            style={{ flex: 1, padding: "8px", borderRadius: 4, cursor: "pointer", backgroundColor: CAST_COLOR, border: "none", color: "#111", fontSize: 12, fontWeight: 700 }}>
            {castType ? (mode === "target" ? "Zieltyp setzen" : "Konvertierung setzen") : (mode === "target" ? "Kein Zieltyp" : "Keine Konvertierung")}
          </button>
          {currentCast && (
            <button onClick={() => { onSave(datasetId, field, null); onClose(); }}
              style={{ padding: "8px 14px", borderRadius: 4, cursor: "pointer", backgroundColor: "rgba(224,112,112,0.1)", border: "1px solid rgba(224,112,112,0.3)", color: "#e07070", fontSize: 12 }}>
              Entfernen
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export { SortEditor, FilterEditor, TypeConvertEditor, CAST_COLOR };

