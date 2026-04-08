import { useState, useEffect, useRef, useCallback } from "react";
import { HardDrive, Download, Trash2, RefreshCw, Inbox, X, Check, Loader2 } from "lucide-react";
import api from "../../../api/client";
import { S } from "../constants";

function ExportsPanel({ projectId }) {
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState(new Set()); // Set of ids
  const [isDragOver, setIsDragOver] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = projectId != null ? `?project_id=${projectId}` : "";
      const { data } = await api.get(`/api/exports/${params}`);
      setFiles(Array.isArray(data) ? data : []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  const fmtSize = (b) => {
    if (!b) return "0 B";
    if (b < 1024) return `${b} B`;
    if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
    return `${(b / 1048576).toFixed(1)} MB`;
  };

  const fmtDate = (iso) => {
    if (!iso) return "";
    const d = new Date(iso);
    return d.toLocaleString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  };

  const EXT_COLORS = { csv: "#6ee7b7", xlsx: "#93c5fd", json: "#fce499", xml: "#fcd34d", db: "#f97316" };

  const toggleSelect = (id) => setSelected((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  const selectAll = () => setSelected(new Set(files.map((f) => f.id)));
  const clearSel = () => setSelected(new Set());

  const downloadFile = async (f) => {
    try {
      const resp = await api.get(`/api/exports/${f.id}/download`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([resp.data]));
      const a = document.createElement("a"); a.href = url; a.download = f.file_name; a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(`Fehler: ${e.response?.data?.detail || e.message}`);
    }
  };

  const downloadSelected = async () => {
    for (const id of selected) {
      const f = files.find((x) => x.id === id);
      if (f) await downloadFile(f);
    }
  };

  const deleteSelected = async () => {
    if (!window.confirm(`${selected.size} Datei(en) wirklich löschen?`)) return;
    setDeleting(true);
    try {
      await api.delete("/api/exports/", { data: [...selected] });
      setSelected(new Set());
      await load();
    } catch (e) {
      alert(`Fehler: ${e.response?.data?.detail || e.message}`);
    } finally { setDeleting(false); }
  };

  const deleteSingle = async (f) => {
    if (!window.confirm(`"${f.file_name}" löschen?`)) return;
    try {
      await api.delete(`/api/exports/${f.id}`);
      setSelected((prev) => { const next = new Set(prev); next.delete(f.id); return next; });
      await load();
    } catch (e) { alert(`Fehler: ${e.response?.data?.detail || e.message}`); }
  };

  // Drag-to-select: track last hovered row for range selection
  const dragStartIdRef = useRef(null);
  const isDraggingSelectRef = useRef(false);

  const handleRowMouseDown = (e, id) => {
    if (e.button !== 0) return;
    dragStartIdRef.current = id;
    isDraggingSelectRef.current = true;
  };

  const handleRowMouseEnter = (id) => {
    if (!isDraggingSelectRef.current) return;
    // Select range from dragStart to current
    const startIdx = files.findIndex((f) => f.id === dragStartIdRef.current);
    const endIdx = files.findIndex((f) => f.id === id);
    if (startIdx < 0 || endIdx < 0) return;
    const [from, to] = startIdx <= endIdx ? [startIdx, endIdx] : [endIdx, startIdx];
    const rangeIds = files.slice(from, to + 1).map((f) => f.id);
    setSelected((prev) => { const next = new Set(prev); rangeIds.forEach((rid) => next.add(rid)); return next; });
  };

  useEffect(() => {
    const up = () => { isDraggingSelectRef.current = false; };
    window.addEventListener("mouseup", up);
    return () => window.removeEventListener("mouseup", up);
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", userSelect: "none" }}>
      {/* Header bar */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "14px 20px", borderBottom: `1px solid ${S.border}`, flexShrink: 0 }}>
        <HardDrive size={16} style={{ color: S.accent }} />
        <span style={{ fontSize: 13, fontWeight: 700, color: S.textBright }}>Exporte</span>
        <span style={{ fontSize: 11, color: S.textDim }}>({files.length})</span>
        <div style={{ flex: 1 }} />
        {selected.size > 0 && (
          <>
            <span style={{ fontSize: 11, color: S.accent }}>{selected.size} ausgewählt</span>
            <button onClick={downloadSelected}
              style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 12px", borderRadius: 4, border: `1px solid #22c55e55`, backgroundColor: "#22c55e18", color: "#22c55e", fontSize: 11, fontWeight: 600, cursor: "pointer" }}>
              <Download size={12} /> Herunterladen
            </button>
            <button onClick={deleteSelected} disabled={deleting}
              style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 12px", borderRadius: 4, border: `1px solid #ef444455`, backgroundColor: "#ef444418", color: "#f87171", fontSize: 11, fontWeight: 600, cursor: "pointer" }}>
              <Trash2 size={12} /> Löschen
            </button>
            <button onClick={clearSel} style={{ fontSize: 11, color: S.textDim, background: "none", border: "none", cursor: "pointer" }}>Abwählen</button>
          </>
        )}
        {selected.size === 0 && files.length > 0 && (
          <button onClick={selectAll} style={{ fontSize: 11, color: S.textDim, background: "none", border: "none", cursor: "pointer" }}>Alle wählen</button>
        )}
        <button onClick={load} title="Aktualisieren" style={{ color: S.textDim, background: "none", border: "none", cursor: "pointer", padding: 4, borderRadius: 4 }}
          onMouseEnter={(e) => e.currentTarget.style.color = S.accent}
          onMouseLeave={(e) => e.currentTarget.style.color = S.textDim}>
          <RefreshCw size={13} />
        </button>
      </div>

      {/* Hint bar */}
      <div style={{ padding: "6px 20px", borderBottom: `1px solid ${S.border}`, backgroundColor: "rgba(252,228,153,0.04)", flexShrink: 0 }}>
        <p style={{ fontSize: 10, color: S.textDim }}>
          Klicken zum Auswählen · Gedrückt halten &amp; ziehen für Mehrfachauswahl · Doppelklick zum Herunterladen
        </p>
      </div>

      {/* File list */}
      <div style={{ flex: 1, overflowY: "auto", scrollbarWidth: "thin" }}>
        {loading && (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 120, color: S.textDim }}>
            <Loader2 size={20} className="animate-spin" />
          </div>
        )}
        {!loading && files.length === 0 && (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: 200, gap: 12, color: S.textDim }}>
            <Inbox size={36} style={{ opacity: 0.3 }} />
            <p style={{ fontSize: 13 }}>Noch keine Exporte vorhanden</p>
            <p style={{ fontSize: 11 }}>Führe ein Mapping aus, um Dateien hier zu sehen.</p>
          </div>
        )}
        {!loading && files.length > 0 && (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${S.border}`, backgroundColor: S.bgCard }}>
                {["", "Dateiname", "Mapping", "Ziel", "Größe", "Ausgelöst", "Datum", ""].map((h, i) => (
                  <th key={i} style={{ padding: "7px 12px", textAlign: "left", fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em", color: S.textDim, whiteSpace: "nowrap" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {files.map((f) => {
                const isSel = selected.has(f.id);
                return (
                  <tr key={f.id}
                    onMouseDown={(e) => handleRowMouseDown(e, f.id)}
                    onMouseEnter={() => handleRowMouseEnter(f.id)}
                    onClick={() => toggleSelect(f.id)}
                    onDoubleClick={() => downloadFile(f)}
                    style={{ borderBottom: `1px solid ${S.border}`, cursor: "pointer", backgroundColor: isSel ? "rgba(252,228,153,0.08)" : "transparent", transition: "background-color 0.05s" }}
                    onMouseLeave={(e) => { if (!isSel) e.currentTarget.style.backgroundColor = "transparent"; }}
                    onMouseOver={(e) => { if (!isSel) e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.025)"; }}>
                    {/* Checkbox */}
                    <td style={{ padding: "8px 10px 8px 16px", width: 28 }}>
                      <div style={{ width: 14, height: 14, borderRadius: 3, border: `2px solid ${isSel ? S.accent : S.border}`, backgroundColor: isSel ? S.accent : "transparent", display: "flex", alignItems: "center", justifyContent: "center" }}>
                        {isSel && <Check size={9} color="#111" strokeWidth={3} />}
                      </div>
                    </td>
                    {/* Filename */}
                    <td style={{ padding: "8px 12px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: 9, fontWeight: 700, padding: "2px 5px", borderRadius: 3, backgroundColor: (EXT_COLORS[f.file_ext] || S.textDim) + "22", color: EXT_COLORS[f.file_ext] || S.textDim, textTransform: "uppercase", letterSpacing: "0.05em", flexShrink: 0 }}>{f.file_ext}</span>
                        <span style={{ color: S.textBright, fontFamily: "monospace", fontSize: 11, maxWidth: 240, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={f.file_name}>{f.file_name}</span>
                      </div>
                    </td>
                    {/* Mapping */}
                    <td style={{ padding: "8px 12px", color: S.textDim, maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.mapping_name || "–"}</td>
                    {/* Target */}
                    <td style={{ padding: "8px 12px", color: S.textDim }}>{f.target_name || "–"}</td>
                    {/* Size */}
                    <td style={{ padding: "8px 12px", color: S.textDim, whiteSpace: "nowrap" }}>{fmtSize(f.file_size)}</td>
                    {/* Triggered by */}
                    <td style={{ padding: "8px 12px" }}>
                      <span style={{ fontSize: 9, fontWeight: 600, padding: "2px 6px", borderRadius: 3, textTransform: "uppercase", letterSpacing: "0.05em", backgroundColor: f.triggered_by === "scheduler" ? "rgba(167,139,250,0.15)" : "rgba(252,228,153,0.1)", color: f.triggered_by === "scheduler" ? "#a78bfa" : S.accent }}>
                        {f.triggered_by === "scheduler" ? "Scheduler" : "Manuell"}
                      </span>
                    </td>
                    {/* Date */}
                    <td style={{ padding: "8px 12px", color: S.textDim, whiteSpace: "nowrap", fontSize: 11 }}>{fmtDate(f.created_at)}</td>
                    {/* Actions */}
                    <td style={{ padding: "8px 14px 8px 4px" }}>
                      <div style={{ display: "flex", gap: 4, opacity: 0 }} className="row-actions"
                        onMouseEnter={(e) => e.currentTarget.style.opacity = 1}
                        onMouseLeave={(e) => e.currentTarget.style.opacity = 0}>
                        <button onClick={(e) => { e.stopPropagation(); downloadFile(f); }} title="Herunterladen"
                          style={{ padding: "3px 6px", borderRadius: 4, border: `1px solid ${S.border}`, background: "none", color: S.textDim, cursor: "pointer" }}
                          onMouseEnter={(e) => { e.currentTarget.style.color = "#22c55e"; e.currentTarget.style.borderColor = "#22c55e55"; }}
                          onMouseLeave={(e) => { e.currentTarget.style.color = S.textDim; e.currentTarget.style.borderColor = S.border; }}>
                          <Download size={11} />
                        </button>
                        <button onClick={(e) => { e.stopPropagation(); deleteSingle(f); }} title="Löschen"
                          style={{ padding: "3px 6px", borderRadius: 4, border: `1px solid ${S.border}`, background: "none", color: S.textDim, cursor: "pointer" }}
                          onMouseEnter={(e) => { e.currentTarget.style.color = "#f87171"; e.currentTarget.style.borderColor = "#ef444455"; }}
                          onMouseLeave={(e) => { e.currentTarget.style.color = S.textDim; e.currentTarget.style.borderColor = S.border; }}>
                          <Trash2 size={11} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
const CRON_PRESETS = [
  { label: "Täglich", value: "0 6 * * *" },
  { label: "Stündlich", value: "0 * * * *" },
  { label: "Alle 15 Min", value: "*/15 * * * *" },
  { label: "Wöchentlich Mo", value: "0 6 * * 1" },
];


export default ExportsPanel;
