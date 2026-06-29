import { useEffect, useRef, useState } from "react";
import { Loader2, ChevronDown } from "lucide-react";
import api from "../../api/client";
import { S } from "./constants";

function PreviewPanel({ canvasNodes, connections, joins, transformNodes, constantNodes, sqlNodes, aggNodes, restNodes, lookupNodes, calcNodes, switchNodes, pythonNodes, aiNodes, exprNodes, qualityNodes, targets }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const loadPreview = async () => {
    if (!open) {
      setOpen(true);
      await fetchPreview();
    } else {
      setOpen(false);
    }
  };

  const fetchPreview = async () => {
    setLoading(true);
    try {
      const { data } = await api.post("/api/mappings/preview", {
        canvas_nodes:    canvasNodes,
        joins,
        transform_nodes: transformNodes,
        constant_nodes:  constantNodes,
        sql_nodes:       sqlNodes,
        agg_nodes:       aggNodes,
        rest_nodes:      restNodes,
        lookup_nodes:    lookupNodes,
        calc_nodes:      calcNodes,
        switch_nodes:    switchNodes,
        python_nodes:    pythonNodes,
        ai_nodes:        aiNodes,
        expr_nodes:      exprNodes,
        quality_nodes:   qualityNodes,
        // Targets bevorzugen (inkl. target_type pro Connection)
        // Fallback: legacy fields-Liste
        targets:         targets?.length ? targets : undefined,
        fields:          !targets?.length ? connections : undefined,
        preview_rows: 50,
      });
      setResult(data);
    } catch (e) {
      setResult({ columns: [], rows: [], total: 0, errors: [e.message] });
    } finally {
      setLoading(false);
    }
  };

  // Re-fetch when constant nodes arrive after async load (panel already open)
  const prevConstLen = useRef(0);
  useEffect(() => {
    const len = constantNodes?.length || 0;
    if (open && len > 0 && len !== prevConstLen.current) {
      prevConstLen.current = len;
      fetchPreview();
    }
  }, [constantNodes, open]);

  const refresh = async (e) => {
    e.stopPropagation();
    await fetchPreview();
  };

  return (
    <div style={{ flexShrink: 0, borderTop: `1px solid ${S.border}`, backgroundColor: S.bgCard }}>
      {/* Toggle header */}
      <div
        onClick={loadPreview}
        style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 16px", cursor: "pointer", userSelect: "none" }}
        onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.03)")}
        onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
      >
        <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: S.accent }}>
          {open ? "▼" : "▶"} Vorschau
        </span>
        {result && !loading && (
          <span style={{ fontSize: 10, color: S.textDim }}>
            {result.total} Zeilen · {result.columns.length} Spalten
            {result.errors?.length > 0 && <span style={{ color: "#e07070", marginLeft: 8 }}>⚠ {result.errors.length} Fehler</span>}
          </span>
        )}
        {open && (
          <button
            onClick={refresh}
            style={{ marginLeft: "auto", fontSize: 10, color: S.textDim, backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, padding: "2px 8px", cursor: "pointer" }}
            onMouseEnter={(e) => (e.currentTarget.style.color = S.accent)}
            onMouseLeave={(e) => (e.currentTarget.style.color = S.textDim)}
          >
            ↻ Aktualisieren
          </button>
        )}
      </div>

      {/* Content */}
      {open && (
        <div style={{ height: 240, display: "flex", flexDirection: "column", borderTop: `1px solid ${S.border}` }}>
          {loading && (
            <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 8, color: S.textDim }}>
              <Loader2 size={16} className="animate-spin" /> Berechne Vorschau…
            </div>
          )}

          {!loading && result?.errors?.length > 0 && result.rows.length === 0 && (
            <div style={{ padding: 16 }}>
              {result.errors.map((e, i) => (
                <p key={i} style={{ fontSize: 11, color: "#e07070", marginBottom: 4 }}>⚠ {e}</p>
              ))}
            </div>
          )}

          {!loading && result && result.rows.length > 0 && (
            <div style={{ flex: 1, overflow: "auto", scrollbarWidth: "thin" }}>
              {result.errors?.length > 0 && (
                <div style={{ padding: "6px 12px", backgroundColor: "rgba(224,112,112,0.06)", borderBottom: `1px solid ${S.border}` }}>
                  {result.errors.map((e, i) => <span key={i} style={{ fontSize: 10, color: "#e07070", marginRight: 12 }}>⚠ {e}</span>)}
                </div>
              )}
              <table style={{ fontSize: 11, borderCollapse: "collapse", minWidth: "max-content", width: "100%" }}>
                <thead style={{ position: "sticky", top: 0, zIndex: 5 }}>
                  <tr style={{ backgroundColor: S.bgEl }}>
                    {result.columns.map((col) => {
                      const ti = result.column_types?.[col];
                      const TMETA = { integer: { l: "INT", c: "#93c5fd" }, decimal: { l: "DEC", c: "#6ee7b7" }, string: { l: "STR", c: "#6a6a6a" }, date: { l: "DATE", c: "#fcd34d" }, datetime: { l: "DT", c: "#fbbf24" }, bool: { l: "BOOL", c: "#c4b5fd" } };
                      const m = ti ? (TMETA[ti.type] || { l: ti.type?.slice(0,3).toUpperCase(), c: "#6a6a6a" }) : null;
                      return (
                        <th key={col} style={{ textAlign: "left", padding: "5px 12px", fontFamily: "monospace", whiteSpace: "nowrap", borderRight: `1px solid ${S.border}`, borderBottom: `1px solid ${S.border}`, fontWeight: 600 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                            <span style={{ color: S.accent }}>{col}</span>
                            {m && <span style={{ fontSize: 8, fontWeight: 700, color: m.c, backgroundColor: m.c + "18", borderRadius: 2, padding: "1px 3px", flexShrink: 0 }}>{m.l}</span>}
                          </div>
                        </th>
                      );
                    })}
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((row, i) => (
                    <tr key={i} style={{ borderTop: `1px solid ${S.border}`, backgroundColor: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.01)" }}>
                      {result.columns.map((col) => (
                        <td key={col} style={{ padding: "5px 12px", fontFamily: "monospace", whiteSpace: "nowrap", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", borderRight: `1px solid ${S.border}`, textAlign: (() => { const t = result.column_types?.[col]?.type; return t === "integer" || t === "decimal" ? "right" : "left"; })() }}>
                          {(() => {
                            const val = row[col];
                            const ctype = result.column_types?.[col]?.type;
                            if (val === null || val === undefined) return <span style={{ color: S.textDim, fontStyle: "italic" }}>null</span>;
                            if (ctype === "boolean") return <span style={{ color: val ? "#6ee7b7" : "#e07070" }}>{val ? "✓ true" : "✗ false"}</span>;
                            if (ctype === "integer") return <span style={{ color: "#93c5fd" }}>{val}</span>;
                            if (ctype === "decimal") return <span style={{ color: "#6ee7b7" }}>{val}</span>;
                            if (ctype === "date" || ctype === "datetime") return <span style={{ color: "#fcd34d" }}>{String(val)}</span>;
                            return <span style={{ color: S.textMain }}>{String(val)}</span>;
                          })()}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {!loading && result && result.rows.length === 0 && result.errors?.length === 0 && (
            <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: S.textDim, fontSize: 12 }}>
              Keine Daten
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── TargetAddField ───────────────────────────────────────────────────────────

export default PreviewPanel;
