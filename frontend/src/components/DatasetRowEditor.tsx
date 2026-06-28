import { useState, useEffect, useCallback } from "react";
import { Plus, Trash2, Save, X, Edit3, Check } from "lucide-react";
import api from "../api/client";

const S = {
  bg:       "var(--bg-card)",
  bgEl:     "var(--bg-elevated)",
  bgMain:   "var(--bg-main)",
  border:   "var(--border)",
  text:     "var(--text-main)",
  textDim:  "var(--text-dim)",
  textBright:"var(--text-bright)",
  accent:   "var(--accent)",
};

const ACCENT = "#34d399"; // teal – passt zu static Datasets

export default function DatasetRowEditor({ dataset, onClose, onSaved }) {
  const [rows, setRows]       = useState([]);
  const [columns, setColumns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving]   = useState(false);
  const [dirty, setDirty]     = useState(false);
  const [editCell, setEditCell] = useState(null); // {row, col}

  // Spalten aus Dataset-Definition oder geladenen Daten
  const effectiveCols = columns.length > 0
    ? columns
    : (dataset.columns || []);

  // ── Laden ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    setLoading(true);
    api.get(`/api/datasets/${dataset.id}/rows`)
      .then(({ data }) => {
        const loadedRows = data.rows || [];
        const loadedCols = data.columns?.length > 0
          ? data.columns
          : (dataset.columns || []);
        setRows(loadedRows.map(r => ({ ...r, __key: Math.random() })));
        setColumns(loadedCols);
      })
      .catch(() => {
        // Leeres Dataset mit definierten Spalten
        setRows([]);
        setColumns(dataset.columns || []);
      })
      .finally(() => setLoading(false));
  }, [dataset.id]);

  // ── Zeile hinzufügen ───────────────────────────────────────────────────────
  const addRow = () => {
    const empty = {};
    effectiveCols.forEach(c => empty[c] = "");
    empty.__key = Math.random();
    setRows(prev => [...prev, empty]);
    setDirty(true);
  };

  // ── Zeile löschen ──────────────────────────────────────────────────────────
  const deleteRow = (idx) => {
    setRows(prev => prev.filter((_, i) => i !== idx));
    setDirty(true);
  };

  // ── Zelle bearbeiten ───────────────────────────────────────────────────────
  const updateCell = useCallback((rowIdx, col, value) => {
    setRows(prev => prev.map((r, i) =>
      i === rowIdx ? { ...r, [col]: value } : r
    ));
    setDirty(true);
  }, []);

  // ── Spalte hinzufügen ──────────────────────────────────────────────────────
  const addColumn = () => {
    const name = prompt("Spaltenname:");
    if (!name?.trim()) return;
    setColumns(prev => [...prev, name.trim()]);
    setRows(prev => prev.map(r => ({ ...r, [name.trim()]: "" })));
    setDirty(true);
  };

  // ── Speichern ──────────────────────────────────────────────────────────────
  const save = async () => {
    setSaving(true);
    try {
      const clean = rows.map(r => {
        const out = {};
        effectiveCols.forEach(c => { out[c] = r[c] ?? ""; });
        return out;
      });
      await api.put(`/api/datasets/${dataset.id}/rows`, { rows: clean });
      setDirty(false);
      onSaved?.();
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  // ── Styles ─────────────────────────────────────────────────────────────────
  const thS = {
    padding: "6px 8px",
    fontSize: 10,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.06em",
    color: S.textDim,
    borderBottom: `1px solid ${S.border}`,
    borderRight: `1px solid ${S.border}`,
    whiteSpace: "nowrap",
    backgroundColor: S.bgMain,
    position: "sticky",
    top: 0,
    zIndex: 1,
  };

  const tdS = (isEditing) => ({
    padding: 0,
    borderBottom: `1px solid ${S.border}`,
    borderRight: `1px solid ${S.border}`,
    backgroundColor: isEditing ? `${ACCENT}10` : "transparent",
    minWidth: 120,
  });

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 1000,
      backgroundColor: "rgba(0,0,0,0.7)",
      display: "flex", alignItems: "center", justifyContent: "center",
    }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div style={{
        backgroundColor: S.bg,
        border: `1px solid ${S.border}`,
        borderRadius: 8,
        width: "min(90vw, 900px)",
        maxHeight: "85vh",
        display: "flex",
        flexDirection: "column",
        boxShadow: "0 24px 80px rgba(0,0,0,0.6)",
      }}>

        {/* Header */}
        <div style={{
          display: "flex", alignItems: "center", gap: 10,
          padding: "12px 16px",
          borderBottom: `1px solid ${S.border}`,
          flexShrink: 0,
        }}>
          <Edit3 size={14} style={{ color: ACCENT }} />
          <div style={{ flex: 1 }}>
            <p style={{ margin: 0, fontSize: 13, fontWeight: 600, color: S.textBright }}>
              {dataset.name}
            </p>
            <p style={{ margin: 0, fontSize: 10, color: S.textDim }}>
              {rows.length} Zeile{rows.length !== 1 ? "n" : ""} · {effectiveCols.length} Spalte{effectiveCols.length !== 1 ? "n" : ""}
              {dirty && <span style={{ color: ACCENT, marginLeft: 8 }}>● Ungespeicherte Änderungen</span>}
            </p>
          </div>

          <button onClick={addColumn} title="Spalte hinzufügen"
            style={{ padding: "5px 10px", borderRadius: 4, fontSize: 10, fontWeight: 600,
              border: `1px solid ${S.border}`, backgroundColor: "transparent",
              color: S.textDim, cursor: "pointer" }}>
            + Spalte
          </button>

          <button onClick={addRow}
            style={{ display: "flex", alignItems: "center", gap: 5,
              padding: "5px 12px", borderRadius: 4, fontSize: 11, fontWeight: 600,
              border: `1px solid ${ACCENT}55`, backgroundColor: `${ACCENT}15`,
              color: ACCENT, cursor: "pointer" }}>
            <Plus size={11} /> Zeile
          </button>

          <button onClick={save} disabled={!dirty || saving}
            style={{ display: "flex", alignItems: "center", gap: 5,
              padding: "5px 14px", borderRadius: 4, fontSize: 11, fontWeight: 700,
              border: "none",
              backgroundColor: dirty ? ACCENT : S.bgEl,
              color: dirty ? "#000" : S.textDim,
              cursor: dirty ? "pointer" : "default",
              opacity: saving ? 0.7 : 1 }}>
            <Save size={11} /> {saving ? "Speichern…" : "Speichern"}
          </button>

          <button onClick={onClose}
            style={{ background: "none", border: "none", color: S.textDim,
              cursor: "pointer", padding: 4, display: "flex" }}>
            <X size={16} />
          </button>
        </div>

        {/* Tabelle */}
        <div style={{ flex: 1, overflow: "auto" }}>
          {loading ? (
            <div style={{ padding: 40, textAlign: "center", color: S.textDim, fontSize: 12 }}>
              Lade Daten…
            </div>
          ) : effectiveCols.length === 0 ? (
            <div style={{ padding: 40, textAlign: "center", color: S.textDim, fontSize: 12 }}>
              Keine Spalten definiert. Spalte hinzufügen um zu beginnen.
            </div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
              <thead>
                <tr>
                  <th style={{ ...thS, width: 36, textAlign: "center" }}>#</th>
                  {effectiveCols.map(col => (
                    <th key={col} style={thS}>{col}</th>
                  ))}
                  <th style={{ ...thS, width: 36 }} />
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={effectiveCols.length + 2}
                      style={{ padding: "24px", textAlign: "center",
                        color: S.textDim, fontSize: 11, fontStyle: "italic" }}>
                      Noch keine Zeilen. "+ Zeile" klicken um zu beginnen.
                    </td>
                  </tr>
                ) : rows.map((row, ri) => (
                  <tr key={row.__key || ri}
                    style={{ backgroundColor: ri % 2 === 0 ? "transparent" : `${S.bgEl}50` }}>
                    <td style={{ ...tdS(false), textAlign: "center",
                      color: S.textDim, fontSize: 10, width: 36 }}>
                      {ri + 1}
                    </td>
                    {effectiveCols.map(col => {
                      const isEditing = editCell?.row === ri && editCell?.col === col;
                      return (
                        <td key={col} style={tdS(isEditing)}
                          onClick={() => setEditCell({ row: ri, col })}>
                          {isEditing ? (
                            <input
                              autoFocus
                              value={row[col] ?? ""}
                              onChange={e => updateCell(ri, col, e.target.value)}
                              onBlur={() => setEditCell(null)}
                              onKeyDown={e => {
                                if (e.key === "Enter" || e.key === "Tab") {
                                  e.preventDefault();
                                  setEditCell(null);
                                  // Tab → nächste Spalte
                                  if (e.key === "Tab") {
                                    const nextCol = effectiveCols[effectiveCols.indexOf(col) + 1];
                                    if (nextCol) setEditCell({ row: ri, col: nextCol });
                                    else if (ri + 1 < rows.length)
                                      setEditCell({ row: ri + 1, col: effectiveCols[0] });
                                  }
                                }
                                if (e.key === "Escape") setEditCell(null);
                              }}
                              style={{
                                width: "100%", padding: "5px 8px",
                                background: "transparent", border: "none",
                                outline: `2px solid ${ACCENT}`,
                                color: S.textBright, fontSize: 11,
                                boxSizing: "border-box",
                              }}
                            />
                          ) : (
                            <div style={{
                              padding: "5px 8px", minHeight: 26,
                              color: row[col] ? S.textBright : S.textDim,
                              fontStyle: row[col] ? "normal" : "italic",
                              cursor: "text",
                              whiteSpace: "nowrap", overflow: "hidden",
                              textOverflow: "ellipsis", maxWidth: 200,
                            }}>
                              {row[col] !== undefined && row[col] !== ""
                                ? String(row[col])
                                : "—"}
                            </div>
                          )}
                        </td>
                      );
                    })}
                    <td style={{ ...tdS(false), width: 36, textAlign: "center" }}>
                      <button onClick={() => deleteRow(ri)}
                        title="Zeile löschen"
                        style={{ background: "none", border: "none",
                          color: S.textDim, cursor: "pointer", padding: 4,
                          display: "flex", alignItems: "center" }}
                        onMouseEnter={e => e.currentTarget.style.color = "#f87171"}
                        onMouseLeave={e => e.currentTarget.style.color = S.textDim}>
                        <Trash2 size={11} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding: "8px 16px",
          borderTop: `1px solid ${S.border}`,
          display: "flex", alignItems: "center", gap: 8,
          fontSize: 10, color: S.textDim, flexShrink: 0,
        }}>
          <span>Klick auf Zelle zum Bearbeiten · Tab = nächste Spalte · Enter = bestätigen</span>
          <span style={{ flex: 1 }} />
          {dirty && (
            <button onClick={() => { setDirty(false); onClose(); }}
              style={{ background: "none", border: "none",
                color: S.textDim, cursor: "pointer", fontSize: 10 }}>
              Ohne Speichern schließen
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
