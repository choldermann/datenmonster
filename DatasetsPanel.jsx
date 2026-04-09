import { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { Database, FileText, Trash2, RefreshCw, Settings, ChevronRight, Plus, Pencil, X, Check, Upload, ChevronDown, Loader2, Server, Table } from "lucide-react";
import api from "../../../api/client";
import { S } from "../constants";
import Modal from "../shared/Modal";
import NewDatasetWizard from "../../../components/NewDatasetWizard";
import XmlConfigurator from "../../../components/XmlConfigurator";

// ─── Spaltentypen ─────────────────────────────────────────────────────────────
const COL_TYPES = [
  { value: "string",  label: "Text" },
  { value: "integer", label: "Ganzzahl" },
  { value: "decimal", label: "Dezimalzahl" },
  { value: "date",    label: "Datum" },
  { value: "boolean", label: "Boolean" },
];

function EditDatasetModal({ dataset, onDone, onCancel }) {
  const [name, setName] = useState(dataset.name);
  const [saving, setSaving] = useState(false);
  const [tab, setTab] = useState("name"); // "name" | "columns" | "schedule"
  const isDbDataset = dataset.file_type?.startsWith("db_") && !!dataset.source_connection_id;
  const [cronExpr, setCronExpr] = useState(dataset.cron_expr || "");
  const [autoRefresh, setAutoRefresh] = useState(dataset.auto_refresh === 1);
  const [savingSchedule, setSavingSchedule] = useState(false);

  const CRON_PRESETS = [
    { label: "Alle 5 Min",     value: "*/5 * * * *" },
    { label: "Alle 15 Min",    value: "*/15 * * * *" },
    { label: "Stündlich",      value: "0 * * * *" },
    { label: "Täglich 06:00",  value: "0 6 * * *" },
    { label: "Täglich 22:00",  value: "0 22 * * *" },
    { label: "Wöchentlich Mo", value: "0 6 * * 1" },
  ];

  const handleSaveSchedule = async () => {
    setSavingSchedule(true);
    try {
      await api.patch(`/api/datasets/${dataset.id}`, {
        cron_expr: cronExpr.trim(),
        auto_refresh: autoRefresh ? 1 : 0,
      });
      onDone();
    } catch (e) {
      alert(e.response?.data?.detail || "Fehler beim Speichern");
    } finally {
      setSavingSchedule(false);
    }
  };
  // column_types als editierbarer State: { colName: { type, raw, is_primary, autoincrement } }
  const [confirmSaveColumns, setConfirmSaveColumns] = useState(false); // Warnungs-Modal
  const [colTypes, setColTypes] = useState(() => {
    const ct = dataset.column_types || {};
    // Für alle Spalten sicherstellen dass is_primary/autoincrement vorhanden
    const result = {};
    for (const col of (dataset.columns || [])) {
      result[col] = {
        type: ct[col]?.type || "string",
        raw: ct[col]?.raw || "manual",
        is_primary: ct[col]?.is_primary || false,
        autoincrement: ct[col]?.autoincrement || false,
      };
    }
    return result;
  });
  const [savingCols, setSavingCols] = useState(false);

  const iS = {
    background: "var(--bg-elevated)", border: "1px solid var(--border)",
    borderRadius: 6, padding: "6px 10px", fontSize: 13,
    color: "var(--text-main)", width: "100%",
  };

  const togglePrimary = (col) => setColTypes(prev => {
    const cur = prev[col];
    const updated = { ...cur, is_primary: !cur.is_primary };
    if (!updated.is_primary) updated.autoincrement = false;
    return { ...prev, [col]: updated };
  });

  const toggleAutoincrement = (col) => setColTypes(prev => ({
    ...prev,
    [col]: { ...prev[col], autoincrement: !prev[col].autoincrement },
  }));

  const handleSaveName = async () => {
    setSaving(true);
    try { await api.patch(`/api/datasets/${dataset.id}`, { name }); onDone(); }
    finally { setSaving(false); }
  };

  const handleSaveColumns = () => {
    // Prüfen ob Typen geändert wurden → Warnung anzeigen
    const origTypes = dataset.column_types || {};
    const changed = Object.keys(colTypes).filter(col =>
      origTypes[col]?.type && colTypes[col]?.type !== origTypes[col]?.type
    );
    if (changed.length > 0) {
      setConfirmSaveColumns(true);
      return;
    }
    doSaveColumns(false);
  };

  const doSaveColumns = async (convertData) => {
    setConfirmSaveColumns(false);
    setSavingCols(true);
    try {
      if (convertData) {
        // Für jede geänderte Spalte Daten konvertieren
        const origTypes = dataset.column_types || {};
        const changed = Object.keys(colTypes).filter(col =>
          origTypes[col]?.type && colTypes[col]?.type !== origTypes[col]?.type
        );
        for (const col of changed) {
          await api.post(`/api/datasets/${dataset.id}/convert_column`, {
            col_name: col, new_type: colTypes[col].type
          });
        }
        // Restliche Änderungen (is_primary etc.) speichern
        await api.put(`/api/datasets/${dataset.id}/column_types`, colTypes);
      } else {
        await api.put(`/api/datasets/${dataset.id}/column_types`, colTypes);
      }
      onDone();
    } catch (e) {
      alert(e.response?.data?.detail || "Fehler beim Speichern");
    } finally {
      setSavingCols(false);
    }
  };

  const cols = dataset.columns || [];

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 300, background: "rgba(0,0,0,0.75)",
        display: "flex", alignItems: "center", justifyContent: "center", padding: "1rem" }}
      onClick={onCancel}>
      <div onClick={e => e.stopPropagation()} style={{
        background: "var(--bg-card)", border: "1px solid var(--border)",
        borderRadius: 12, width: "100%", maxWidth: 580,
        maxHeight: "85vh", display: "flex", flexDirection: "column", overflow: "hidden",
      }}>
        {/* Header */}
        <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--border)",
            display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <p style={{ fontSize: 15, fontWeight: 600, margin: 0, color: "var(--text-bright)" }}>
            Dataset bearbeiten
          </p>
          <button onClick={onCancel} style={{ background: "none", border: "none",
              cursor: "pointer", color: "var(--text-dim)", fontSize: 18, lineHeight: 1 }}>✕</button>
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", borderBottom: "1px solid var(--border)", padding: "0 18px" }}>
          {[
            { key: "name", label: "Name" },
            { key: "columns", label: "Spalten & Schlüssel" },
            ...(isDbDataset ? [{ key: "schedule", label: "⏰ Zeitplan" }] : []),
          ].map(t => (
            <button key={t.key} onClick={() => setTab(t.key)} style={{
              background: "none", border: "none", cursor: "pointer",
              padding: "10px 14px", fontSize: 12, fontWeight: 600,
              color: tab === t.key ? "var(--accent)" : "var(--text-dim)",
              borderBottom: tab === t.key ? "2px solid var(--accent)" : "2px solid transparent",
              marginBottom: -1,
            }}>{t.label}</button>
          ))}
        </div>

        {/* Body */}
        <div style={{ padding: "16px 18px", overflow: "auto", flex: 1 }}>
          {tab === "name" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <label style={{ fontSize: 11, fontWeight: 600, color: "var(--text-dim)",
                  textTransform: "uppercase", letterSpacing: "0.05em", display: "block", marginBottom: 4 }}>
                Dataset-Name
              </label>
              <input style={iS} value={name} onChange={e => setName(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleSaveName()} autoFocus />
            </div>
          )}

          {tab === "schedule" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <input type="checkbox" id="auto-refresh" checked={autoRefresh}
                  onChange={e => setAutoRefresh(e.target.checked)}
                  style={{ accentColor: "#6ee7b7", cursor: "pointer", width: 16, height: 16 }} />
                <label htmlFor="auto-refresh" style={{ fontSize: 13, color: "var(--text-main)", cursor: "pointer" }}>
                  Automatisch aktualisieren
                </label>
              </div>
              {autoRefresh && (
                <>
                  <div>
                    <label style={{ fontSize: 11, fontWeight: 600, color: "var(--text-dim)",
                        textTransform: "uppercase", letterSpacing: "0.05em", display: "block", marginBottom: 6 }}>
                      Zeitplan (Cron-Ausdruck)
                    </label>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
                      {CRON_PRESETS.map(p => (
                        <button key={p.value} onClick={() => setCronExpr(p.value)} style={{
                          fontSize: 11, padding: "4px 10px", borderRadius: 4, cursor: "pointer",
                          border: `1px solid ${cronExpr === p.value ? "var(--accent)" : "var(--border)"}`,
                          backgroundColor: cronExpr === p.value ? "rgba(252,228,153,0.1)" : "transparent",
                          color: cronExpr === p.value ? "var(--accent)" : "var(--text-dim)",
                        }}>{p.label}</button>
                      ))}
                    </div>
                    <input value={cronExpr} onChange={e => setCronExpr(e.target.value)}
                      placeholder="z.B. 0 6 * * * (täglich um 06:00)"
                      style={{ backgroundColor: "var(--bg-elevated)", border: "1px solid var(--border)",
                        borderRadius: 6, padding: "6px 10px", fontSize: 13,
                        color: "var(--text-main)", width: "100%", boxSizing: "border-box" }} />
                    <p style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 6 }}>
                      Format: Minute Stunde Tag Monat Wochentag
                    </p>
                  </div>
                  {dataset.last_refresh_at && (
                    <div style={{ padding: "8px 12px", borderRadius: 6,
                      backgroundColor: dataset.last_refresh_status === "error"
                        ? "rgba(248,113,113,0.08)" : "rgba(110,231,183,0.06)",
                      border: `1px solid ${dataset.last_refresh_status === "error"
                        ? "rgba(248,113,113,0.2)" : "rgba(110,231,183,0.2)"}` }}>
                      <p style={{ fontSize: 11, margin: 0,
                        color: dataset.last_refresh_status === "error" ? "#f87171" : "#6ee7b7" }}>
                        {dataset.last_refresh_status === "error" ? "✗" : "✓"}{" "}
                        Letzte Aktualisierung: {new Date(dataset.last_refresh_at).toLocaleString("de-DE")}
                        {dataset.last_refresh_msg && ` – ${dataset.last_refresh_msg}`}
                      </p>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {tab === "columns" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <p style={{ fontSize: 11, color: "var(--text-dim)", margin: "0 0 8px" }}>
                🔑 = Primärschlüssel &nbsp;·&nbsp; AI = Autoincrement (nur Ganzzahl)
              </p>
              {cols.length === 0 && (
                <p style={{ fontSize: 12, color: "var(--text-dim)" }}>Keine Spalten vorhanden.</p>
              )}
              {cols.map(col => {
                const info = colTypes[col] || { type: "string", is_primary: false, autoincrement: false };
                const canAutoincrement = info.is_primary && info.type === "integer";
                return (
                  <div key={col} style={{ display: "flex", flexDirection: "column", gap: 4,
                      padding: "8px 10px", borderRadius: 8,
                      background: info.is_primary ? "rgba(251,191,36,0.05)" : "rgba(255,255,255,0.02)",
                      border: `1px solid ${info.is_primary ? "rgba(251,191,36,0.2)" : "var(--border)"}` }}>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 130px 34px", gap: 8, alignItems: "center" }}>
                      <span style={{ fontSize: 12, fontFamily: "monospace", color: "var(--text-bright)",
                          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {info.is_primary && <span style={{ marginRight: 5 }}>🔑</span>}
                        {col}
                      </span>
                      <select value={info.type}
                        onChange={e => setColTypes(prev => ({
                          ...prev,
                          [col]: { ...prev[col], type: e.target.value,
                            // Autoincrement zurücksetzen wenn kein integer mehr
                            autoincrement: e.target.value === "integer" ? prev[col].autoincrement : false }
                        }))}
                        style={{ ...iS, padding: "4px 8px", fontSize: 12 }}>
                        {COL_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                      </select>
                      <button
                        onClick={() => togglePrimary(col)}
                        title={info.is_primary ? "Primärschlüssel entfernen" : "Als Primärschlüssel markieren"}
                        style={{
                          background: info.is_primary ? "rgba(251,191,36,0.2)" : "none",
                          border: `1px solid ${info.is_primary ? "rgba(251,191,36,0.5)" : "var(--border)"}`,
                          borderRadius: 6, cursor: "pointer", fontSize: 14,
                          display: "flex", alignItems: "center", justifyContent: "center",
                          height: 32, width: 34, flexShrink: 0,
                        }}>🔑</button>
                    </div>
                    {canAutoincrement && (
                      <div style={{ display: "flex", alignItems: "center", gap: 6, paddingLeft: 4 }}>
                        <input type="checkbox" id={`ai-edit-${col}`}
                          checked={info.autoincrement}
                          onChange={() => toggleAutoincrement(col)}
                          style={{ accentColor: "#6ee7b7", cursor: "pointer" }} />
                        <label htmlFor={`ai-edit-${col}`}
                          style={{ fontSize: 11, color: "var(--text-dim)", cursor: "pointer" }}>
                          Autoincrement – ID wird automatisch vergeben
                        </label>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ padding: "12px 18px", borderTop: "1px solid var(--border)",
            display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button onClick={onCancel} style={{
            fontSize: 13, padding: "7px 16px", borderRadius: 6, cursor: "pointer",
            background: "transparent", border: "1px solid var(--border)", color: "var(--text-dim)",
          }}>Abbrechen</button>
          {tab === "name" ? (
            <button onClick={handleSaveName} disabled={saving || !name.trim()} style={{
              fontSize: 13, fontWeight: 600, padding: "7px 16px", borderRadius: 6,
              cursor: saving ? "wait" : "pointer",
              background: "rgba(110,231,183,0.15)", border: "1px solid rgba(110,231,183,0.4)",
              color: "#6ee7b7", opacity: saving || !name.trim() ? 0.5 : 1,
            }}>{saving ? "Speichert…" : "Speichern"}</button>
          ) : tab === "schedule" ? (
            <button onClick={handleSaveSchedule} disabled={savingSchedule} style={{
              fontSize: 13, fontWeight: 600, padding: "7px 16px", borderRadius: 6,
              cursor: savingSchedule ? "wait" : "pointer",
              background: "rgba(110,231,183,0.15)", border: "1px solid rgba(110,231,183,0.4)",
              color: "#6ee7b7", opacity: savingSchedule ? 0.5 : 1,
            }}>{savingSchedule ? "Speichert…" : "Zeitplan speichern"}</button>
          ) : (
            <button onClick={handleSaveColumns} disabled={savingCols} style={{
              fontSize: 13, fontWeight: 600, padding: "7px 16px", borderRadius: 6,
              cursor: savingCols ? "wait" : "pointer",
              background: "rgba(110,231,183,0.15)", border: "1px solid rgba(110,231,183,0.4)",
              color: "#6ee7b7", opacity: savingCols ? 0.5 : 1,
            }}>{savingCols ? "Speichert…" : "Spalten speichern"}</button>
          )}
        </div>
      </div>
      {/* Bestätigungs-Modal für Typ-Konvertierung */}
      {confirmSaveColumns && createPortal(
        <div onClick={() => setConfirmSaveColumns(false)} style={{
          position: "fixed", inset: 0, zIndex: 9999,
          backgroundColor: "rgba(0,0,0,0.75)",
          display: "flex", alignItems: "center", justifyContent: "center",
          padding: "1rem",
        }}>
          <div onClick={e => e.stopPropagation()} style={{
            background: "var(--bg-card)", border: "1px solid var(--border)",
            borderRadius: 10, padding: "20px 24px",
            width: "100%", maxWidth: 520,
            boxShadow: "0 24px 60px rgba(0,0,0,0.7)",
          }}>
            <p style={{ fontSize: 14, fontWeight: 700, color: "var(--text-bright)", margin: "0 0 10px" }}>
              Spaltentypen speichern
            </p>
            <p style={{ fontSize: 12, color: "var(--text-main)", margin: "0 0 12px", lineHeight: 1.6 }}>
              Du hast einen oder mehrere Datentypen geändert.
            </p>
            <div style={{ fontSize: 12, color: "#f87171", marginBottom: 20, lineHeight: 1.6,
              padding: "10px 12px", borderRadius: 6, backgroundColor: "rgba(248,113,113,0.08)",
              border: "1px solid rgba(248,113,113,0.2)",
              wordBreak: "break-word", overflowWrap: "break-word" }}>
              <p style={{ margin: "0 0 4px", fontWeight: 600 }}>⚠ Achtung</p>
              <p style={{ margin: 0 }}>Wenn du die Daten konvertierst, werden Inhalte unwiederbringlich geändert. Nicht konvertierbare Werte werden auf leer gesetzt.</p>
            </div>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button onClick={() => setConfirmSaveColumns(false)} style={{
                fontSize: 12, padding: "7px 14px", borderRadius: 6, cursor: "pointer",
                background: "transparent", border: "1px solid var(--border)", color: "var(--text-dim)",
              }}>Abbrechen</button>
              <button onClick={() => doSaveColumns(false)} style={{
                fontSize: 12, padding: "7px 14px", borderRadius: 6, cursor: "pointer",
                background: "rgba(147,197,253,0.1)", border: "1px solid rgba(147,197,253,0.3)",
                color: "#93c5fd",
              }}>Nur Label ändern</button>
              <button onClick={() => doSaveColumns(true)} style={{
                fontSize: 12, fontWeight: 600, padding: "7px 14px", borderRadius: 6, cursor: "pointer",
                background: "rgba(252,228,153,0.15)", border: "1px solid rgba(252,228,153,0.4)",
                color: "var(--accent)",
              }}>Daten konvertieren</button>
            </div>
          </div>
        </div>
      , document.body)}
    </div>
  );
}

// ─── Scheduler Panel ─────────────────────────────────────────────────────────
// ─── Cron Builder Helpers ─────────────────────────────────────────────────────
const WEEKDAYS = [
  { label: "Mo", value: 1 }, { label: "Di", value: 2 }, { label: "Mi", value: 3 },
  { label: "Do", value: 4 }, { label: "Fr", value: 5 }, { label: "Sa", value: 6 },
  { label: "So", value: 0 },
];


function DatasetCard({ dataset, onDelete, onClick, onConfigure, onEdit, onRequery, canEdit = true }) {
  const typeColor = { csv: "#6ee7b7", xlsx: "#93c5fd", xml: "#fcd34d", db_mssql: "#c4b5fd", db_mysql: "#6ee7b7" };
  const typeLabel = { csv: "CSV", xlsx: "XLSX", xml: "XML", db_mssql: "SQL Server", db_mysql: "MySQL" };
  const isPending = dataset.xml_configured === 0;
  const isDb = dataset.file_type?.startsWith("db_") && dataset.source_sql;
  const [requerying, setRequerying] = useState(false);

  const handleRequery = async (e) => {
    e.stopPropagation();
    setRequerying(true);
    try {
      await api.post(`/api/datasets/${dataset.id}/requery`);
      onRequery?.();
    } catch (err) {
      alert(err.response?.data?.detail || err.message);
    } finally { setRequerying(false); }
  };

  return (
    <div onClick={() => !isPending && onClick(dataset)}
      className="card group transition-all duration-150"
      style={{ borderColor: S.border, cursor: isPending ? "default" : "pointer", opacity: isPending ? 0.85 : 1 }}
      onMouseEnter={(e) => { if (!isPending) e.currentTarget.style.borderColor = S.accent; }}
      onMouseLeave={(e) => (e.currentTarget.style.borderColor = S.border)}>
      <div className="flex items-start justify-between min-w-0">
        <div className="flex items-center gap-3 min-w-0">
          <FileText size={18} style={{ color: typeColor[dataset.file_type] || S.textMain, flexShrink: 0 }} />
          <div className="min-w-0">
            <p className="font-medium text-sm truncate" style={{ color: S.textBright }}>{dataset.name}</p>
            <p className="text-xs font-mono mt-0.5 truncate" style={{ color: S.textDim }}>{dataset.original_filename}</p>
          </div>
        </div>
        {canEdit && (
          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0 ml-2">
            {isDb && (
              <button onClick={handleRequery} disabled={requerying} title="SQL neu ausführen"
                className="p-1 rounded" style={{ color: "#c4b5fd" }}
                onMouseEnter={(e) => e.currentTarget.style.color = "#a78bfa"}
                onMouseLeave={(e) => e.currentTarget.style.color = "#c4b5fd"}>
                {requerying ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
              </button>
            )}
            <button onClick={(e) => { e.stopPropagation(); onEdit(dataset); }}
              className="p-1 rounded" style={{ color: S.textDim }}
              onMouseEnter={(e) => e.currentTarget.style.color = S.accent}
              onMouseLeave={(e) => e.currentTarget.style.color = S.textDim}>
              <Pencil size={13} />
            </button>
            <button onClick={(e) => { e.stopPropagation(); onDelete(dataset.id); }}
              className="p-1 rounded" style={{ color: S.textDim }}
              onMouseEnter={(e) => e.currentTarget.style.color = "#e07070"}
              onMouseLeave={(e) => e.currentTarget.style.color = S.textDim}>
              <Trash2 size={13} />
            </button>
          </div>
        )}
      </div>
      {isPending ? (
        <div className="mt-4">
          <div className="flex items-center gap-2 text-xs mb-3" style={{ color: "#fbbf24" }}>
            <span>⚠</span> XML-Konfiguration erforderlich
          </div>
          {canEdit && (
            <button onClick={(e) => { e.stopPropagation(); onConfigure(dataset); }}
              className="btn-primary text-xs w-full justify-center">
              <Settings size={12} /> Zielknoten wählen
            </button>
          )}
        </div>
      ) : (
        <>
          <div className="flex items-center gap-3 mt-4 text-xs flex-wrap" style={{ color: S.textDim }}>
            <span>{(dataset.row_count || 0).toLocaleString()} Zeilen</span>
            <span>{dataset.columns?.length || 0} Spalten</span>
            <span className="px-1.5 py-0.5 rounded font-mono"
              style={{ backgroundColor: "rgba(255,255,255,0.04)", color: typeColor[dataset.file_type] || S.textDim }}>
              {typeLabel[dataset.file_type] || dataset.file_type}
            </span>
            {dataset.updated_at && (
              <span style={{ color: S.textDim, fontSize: 10 }} title={new Date(dataset.updated_at).toLocaleString("de-DE")}>
                ↺ {new Date(dataset.updated_at).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })}
              </span>
            )}
            {dataset.auto_refresh === 1 && dataset.cron_expr && (
              <span title={`Auto-Refresh: ${dataset.cron_expr}${dataset.last_refresh_at ? " · Zuletzt: " + new Date(dataset.last_refresh_at).toLocaleString("de-DE") : ""}`}
                style={{
                  display: "inline-flex", alignItems: "center", gap: 3,
                  fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 3,
                  backgroundColor: dataset.last_refresh_status === "error"
                    ? "rgba(248,113,113,0.15)" : "rgba(110,231,183,0.12)",
                  color: dataset.last_refresh_status === "error" ? "#f87171" : "#6ee7b7",
                  border: `1px solid ${dataset.last_refresh_status === "error"
                    ? "rgba(248,113,113,0.3)" : "rgba(110,231,183,0.3)"}`,
                }}>
                ⏰ AUTO
              </span>
            )}
          </div>
          <div className="flex items-center gap-1 mt-3 text-xs opacity-0 group-hover:opacity-100 transition-opacity"
            style={{ color: S.accent }}>
            <span>Explorer öffnen</span><ChevronRight size={11} />
          </div>
        </>
      )}
    </div>
  );
}

// ─── New Tile (generic) ───────────────────────────────────────────────────────
function NewTile({ label, sub, icon: Icon, onClick }) {
  const [hovered, setHovered] = useState(false);
  return (
    <div onClick={onClick} onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
      className="card transition-all duration-150 cursor-pointer flex flex-col items-center justify-center gap-3 min-h-[116px]"
      style={{
        borderColor: hovered ? "rgba(110,231,170,0.6)" : "rgba(110,231,170,0.25)",
        backgroundColor: hovered ? "rgba(110,231,170,0.07)" : "rgba(110,231,170,0.03)",
        borderStyle: "dashed",
      }}>
      <div className="rounded-full p-2" style={{ backgroundColor: hovered ? "rgba(110,231,170,0.15)" : "rgba(110,231,170,0.07)" }}>
        <Icon size={20} style={{ color: hovered ? "#6ee7aa" : "#4ade80" }} />
      </div>
      <div className="text-center">
        <p className="text-sm font-medium" style={{ color: hovered ? "#6ee7aa" : "#4ade80" }}>{label}</p>
        <p className="text-xs mt-0.5" style={{ color: "rgba(110,231,170,0.5)" }}>{sub}</p>
      </div>
    </div>
  );
}

// ─── Data Explorer ────────────────────────────────────────────────────────────
const PAGE_SIZE = 100;
// ─── Feldtyp-Hilfsfunktionen ─────────────────────────────────────────────────
const TYPE_META = {
  integer: { label: "INT",  color: "#93c5fd" },
  decimal: { label: "DEC",  color: "#6ee7b7" },
  string:  { label: "STR",  color: "#8a8a8a" },
  date:    { label: "DATE", color: "#fcd34d" },
  bool:    { label: "BOOL", color: "#c4b5fd" },
};
function TypeBadge({ colName, columnTypes, style = {} }) {
  const info = columnTypes?.[colName];
  if (!info) return null;
  const meta = TYPE_META[info.type] || { label: info.type?.toUpperCase()?.slice(0,4), color: "#8a8a8a" };
  return (
    <span title={info.raw || info.type}
      style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.05em", color: meta.color,
        backgroundColor: meta.color + "18", borderRadius: 3, padding: "1px 4px", marginLeft: 4,
        cursor: info.raw ? "help" : "default", ...style }}>
      {meta.label}
    </span>
  );
}

// Editierbarer Typ-Badge – öffnet Dropdown bei Klick
function TypeBadgeEditor({ colName, columnTypes, datasetId, onTypeChange, style = {} }) {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);   // kurzes ✓ Feedback
  const [error, setError] = useState(false);   // kurzes ✗ Feedback
  const ref = useRef(null);

  const info = columnTypes?.[colName];
  const meta = info
    ? (TYPE_META[info.type] || { label: info.type?.toUpperCase()?.slice(0,4), color: "#8a8a8a" })
    : { label: "?", color: "#8a8a8a" };

  // Klick außerhalb schließt Dropdown
  useEffect(() => {
    if (!open) return;
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const [confirmConvert, setConfirmConvert] = useState(null); // { newType } wenn Warnung angezeigt wird

  const handleSelect = async (newType) => {
    setOpen(false);
    if (newType === info?.type) return;
    // Warnung anzeigen bevor Daten konvertiert werden
    setConfirmConvert({ newType });
  };

  const doConvert = async (newType, convertData) => {
    setConfirmConvert(null);
    setSaving(true); setError(false); setSaved(false);
    try {
      if (convertData) {
        // Daten tatsächlich konvertieren
        const { data } = await api.post(
          `/api/datasets/${datasetId}/convert_column`,
          { col_name: colName, new_type: newType }
        );
        if (onTypeChange) onTypeChange(colName, newType, data.column_types, true);
      } else {
        // Nur Label ändern, keine Daten konvertieren
        const { data } = await api.patch(
          `/api/datasets/${datasetId}/column_types`,
          { [colName]: newType }
        );
        if (onTypeChange) onTypeChange(colName, newType, data.column_types);
      }
      setSaved(true);
      setTimeout(() => setSaved(false), 1800);
    } catch (e) {
      console.error("Typ-Änderung fehlgeschlagen:", e);
      setError(true);
      setTimeout(() => setError(false), 2000);
    } finally {
      setSaving(false);
    }
  };

  const badgeColor = error ? "#e07070" : saved ? "#6ee7b7" : meta.color;
  const badgeLabel = saving ? "…" : saved ? "✓" : error ? "✗" : meta.label;

  return (
    <span ref={ref} style={{ position: "relative", display: "inline-block", marginLeft: 4 }}>
      <span
        onClick={(e) => { e.stopPropagation(); if (!saving) setOpen(v => !v); }}
        title={`Typ: ${info?.type || "unbekannt"} – klicken zum Ändern`}
        style={{
          fontSize: 9, fontWeight: 700, letterSpacing: "0.05em",
          color: badgeColor,
          backgroundColor: badgeColor + "18",
          borderRadius: 3, padding: "1px 4px",
          cursor: saving ? "wait" : "pointer",
          border: `1px solid ${open ? badgeColor + "88" : saved || error ? badgeColor + "66" : "transparent"}`,
          transition: "all 0.15s",
          ...style,
        }}
        onMouseEnter={e => { if (!saving && !saved && !error) e.currentTarget.style.borderColor = meta.color + "66"; }}
        onMouseLeave={e => { if (!open && !saved && !error) e.currentTarget.style.borderColor = "transparent"; }}
      >
        {badgeLabel}{!saving && !saved && !error ? " ▾" : ""}
      </span>

      {open && (
        <div onClick={e => e.stopPropagation()} style={{
          position: "absolute", top: "calc(100% + 4px)", left: 0, zIndex: 999,
          backgroundColor: "#1e1e1e", border: "1px solid #333",
          borderRadius: 6, boxShadow: "0 8px 24px rgba(0,0,0,0.6)",
          minWidth: 130, overflow: "hidden",
        }}>
          <div style={{ padding: "5px 8px 4px", fontSize: 8, color: "#666",
            textTransform: "uppercase", letterSpacing: "0.08em", borderBottom: "1px solid #2a2a2a" }}>
            {colName}
          </div>
          {Object.entries(TYPE_META).map(([typeKey, m]) => (
            <div key={typeKey} onClick={() => handleSelect(typeKey)}
              style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "6px 10px", cursor: "pointer", fontSize: 11,
                backgroundColor: info?.type === typeKey ? m.color + "18" : "transparent",
                color: info?.type === typeKey ? m.color : "#ccc",
              }}
              onMouseEnter={e => e.currentTarget.style.backgroundColor = m.color + "22"}
              onMouseLeave={e => e.currentTarget.style.backgroundColor = info?.type === typeKey ? m.color + "18" : "transparent"}
            >
              <span style={{ fontSize: 9, fontWeight: 700, color: m.color,
                backgroundColor: m.color + "20", borderRadius: 3, padding: "1px 5px",
                minWidth: 36, textAlign: "center" }}>{m.label}</span>
              <span>{{ string:"Text", integer:"Ganzzahl", decimal:"Dezimal",
                         date:"Datum", datetime:"Datum+Zeit", bool:"Boolean" }[typeKey] || typeKey}</span>
              {info?.type === typeKey && <span style={{ marginLeft: "auto", color: m.color }}>✓</span>}
            </div>
          ))}
        </div>
      )}
      {/* Bestätigungs-Modal für Typ-Konvertierung */}
      {confirmConvert && createPortal(
        <div onClick={() => setConfirmConvert(null)} style={{
          position: "fixed", inset: 0, zIndex: 9999,
          backgroundColor: "rgba(0,0,0,0.75)",
          display: "flex", alignItems: "center", justifyContent: "center",
          padding: "1rem",
        }}>
          <div onClick={e => e.stopPropagation()} style={{
            background: "var(--bg-card)", border: "1px solid var(--border)",
            borderRadius: 10, padding: "20px 24px",
            width: "100%", maxWidth: 520,
            boxShadow: "0 24px 60px rgba(0,0,0,0.7)",
          }}>
            <p style={{ fontSize: 14, fontWeight: 700, color: "var(--text-bright)", margin: "0 0 10px" }}>
              Datentyp ändern
            </p>
            <p style={{ fontSize: 12, color: "var(--text-main)", margin: "0 0 12px", lineHeight: 1.6 }}>
              Spalte <strong style={{ color: "var(--accent)" }}>{colName}</strong> von{" "}
              <strong>{info?.type}</strong> → <strong>{confirmConvert.newType}</strong>
            </p>
            <div style={{ fontSize: 12, color: "#f87171", marginBottom: 20, lineHeight: 1.6,
              padding: "10px 12px", borderRadius: 6, backgroundColor: "rgba(248,113,113,0.08)",
              border: "1px solid rgba(248,113,113,0.2)",
              wordBreak: "break-word", overflowWrap: "break-word" }}>
              <p style={{ margin: "0 0 4px", fontWeight: 600 }}>⚠ Achtung</p>
              <p style={{ margin: 0 }}>Wenn du die Daten konvertierst, werden Inhalte unwiederbringlich geändert. Nicht konvertierbare Werte werden auf leer gesetzt.</p>
            </div>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button onClick={() => setConfirmConvert(null)} style={{
                fontSize: 12, padding: "7px 14px", borderRadius: 6, cursor: "pointer",
                background: "transparent", border: "1px solid var(--border)", color: "var(--text-dim)",
              }}>Abbrechen</button>
              <button onClick={() => doConvert(confirmConvert.newType, false)} style={{
                fontSize: 12, padding: "7px 14px", borderRadius: 6, cursor: "pointer",
                background: "rgba(147,197,253,0.1)", border: "1px solid rgba(147,197,253,0.3)",
                color: "#93c5fd",
              }}>Nur Label ändern</button>
              <button onClick={() => doConvert(confirmConvert.newType, true)} style={{
                fontSize: 12, fontWeight: 600, padding: "7px 14px", borderRadius: 6, cursor: "pointer",
                background: "rgba(252,228,153,0.15)", border: "1px solid rgba(252,228,153,0.4)",
                color: "var(--accent)",
              }}>Daten konvertieren</button>
            </div>
          </div>
        </div>
      , document.body)}
    </span>
  );
}

function DataExplorer({ dataset, onClose, onColumnTypesChange }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [colWidths, setColWidths] = useState({});      // col → px-Breite
  const [expandedCell, setExpandedCell] = useState(null); // {row, col, value}
  const resizing = useRef(null); // { col, startX, startW }

  const startResize = (e, col) => {
    e.preventDefault();
    const startW = colWidths[col] || 200;
    resizing.current = { col, startX: e.clientX, startW };
    const onMove = (ev) => {
      if (!resizing.current) return;
      const delta = ev.clientX - resizing.current.startX;
      const newW  = Math.max(60, resizing.current.startW + delta);
      setColWidths(prev => ({ ...prev, [resizing.current.col]: newW }));
    };
    const onUp = () => {
      resizing.current = null;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };
  // column_types immer direkt vom Backend laden – verhindert Stale-State
  const [columnTypes, setColumnTypes] = useState(dataset.column_types || {});

  const loadPage = (p) => {
    setLoading(true);
    api.get(`/api/datasets/${dataset.id}/data?page=${p}&page_size=${PAGE_SIZE}`)
      .then((r) => { setData(r.data); setLoading(false); });
  };

  // Beim Öffnen: Daten laden + column_types IMMER frisch vom Backend holen
  useEffect(() => {
    loadPage(0);
    // Expliziter GET /{id} Aufruf - gibt garantiert aktuelle column_types zurück
    api.get(`/api/datasets/${dataset.id}`)
      .then((r) => {
        if (r.data?.column_types) {
          setColumnTypes(r.data.column_types);
        }
      })
      .catch(() => {
        // Fallback: Prop-Wert nutzen
        setColumnTypes(dataset.column_types || {});
      });
  }, [dataset.id]);

  const handleTypeChange = (colName, newType, savedTypes, reloadData = false) => {
    // savedTypes kommt direkt aus der Backend-Antwort → immer korrekt
    if (savedTypes) {
      setColumnTypes(savedTypes);
    } else {
      setColumnTypes(prev => ({
        ...prev,
        [colName]: { ...(prev[colName] || {}), type: newType },
      }));
    }
    if (onColumnTypesChange) onColumnTypesChange(colName, newType);
    // Nach Daten-Konvertierung Tabelle neu laden
    if (reloadData) {
      setPage(0);
      loadPage(0);
    }
  };
  const filtered = data?.preview?.filter((row) => !search || Object.values(row).some((v) => String(v ?? "").toLowerCase().includes(search.toLowerCase())));
  const totalPages = Math.ceil(dataset.row_count / PAGE_SIZE);
  const goTo = (p) => { setPage(p); loadPage(p); };
  return (
    <div className="fixed inset-0 z-50 flex flex-col" style={{ background: "rgba(10,10,10,0.97)", backdropFilter: "blur(4px)" }}>
      <div className="flex items-center justify-between px-6 py-4 shrink-0"
        style={{ borderBottom: `1px solid ${S.border}`, backgroundColor: S.bgCard }}>
        <div className="flex items-center gap-3">
          <Table size={16} style={{ color: S.accent }} />
          <span className="font-medium text-sm" style={{ color: S.textBright }}>{dataset.name}</span>
          <span className="text-xs font-mono" style={{ color: S.textDim }}>{dataset.row_count} Zeilen · {dataset.columns?.length} Spalten</span>
        </div>
        <div className="flex items-center gap-3">
          <input className="input text-sm py-1.5 w-56" placeholder="Suchen..." value={search} onChange={(e) => setSearch(e.target.value)} />
          <button onClick={onClose} className="btn-ghost text-sm">Schließen</button>
        </div>
      </div>
      <div className="flex-1 min-h-0 p-5 flex flex-col">
        {loading ? (
          <div className="flex items-center justify-center h-48" style={{ color: S.textDim }}>
            <Loader2 className="animate-spin mr-2" size={18} /> Lade Daten...
          </div>
        ) : (
          <div className="flex-1 min-h-0 rounded-xl overflow-hidden flex flex-col" style={{ border: `1px solid ${S.border}` }}>
            <div className="flex-1 min-h-0 overflow-scroll" style={{ scrollbarWidth: "thin" }}>
              <table className="text-xs border-collapse" style={{ minWidth: "max-content" }}>
                <thead className="sticky top-0 z-10">
                  <tr style={{ backgroundColor: S.bgEl }}>
                    {data.columns.map((col) => (
                      <th key={col}
                        className="text-left px-4 py-3 font-medium font-mono whitespace-nowrap"
                        style={{
                          color: S.accent,
                          borderRight: `1px solid ${S.border}`,
                          borderBottom: `1px solid ${S.border}`,
                          width: colWidths[col] || "auto",
                          minWidth: colWidths[col] || 80,
                          maxWidth: colWidths[col] || undefined,
                          position: "relative",
                          userSelect: "none",
                        }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                          {columnTypes?.[col]?.is_primary && (
                            <span title="Primärschlüssel" style={{ fontSize: 11, lineHeight: 1, cursor: "default" }}>🔑</span>
                          )}
                          <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis" }}>{col}</span>
                          <TypeBadgeEditor
                            colName={col}
                            columnTypes={columnTypes}
                            datasetId={dataset.id}
                            onTypeChange={handleTypeChange}
                          />
                        </div>
                        {/* Resize-Handle */}
                        <div
                          onMouseDown={(e) => startResize(e, col)}
                          style={{
                            position: "absolute", right: 0, top: 0, bottom: 0,
                            width: 6, cursor: "col-resize",
                            backgroundColor: "transparent",
                            zIndex: 2,
                          }}
                          onMouseEnter={e => e.currentTarget.style.backgroundColor = S.accent + "66"}
                          onMouseLeave={e => e.currentTarget.style.backgroundColor = "transparent"}
                        />
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered?.map((row, i) => (
                    <tr key={i} style={{ borderTop: `1px solid ${S.border}` }}
                      onMouseEnter={(e) => e.currentTarget.style.backgroundColor = S.bgEl}
                      onMouseLeave={(e) => e.currentTarget.style.backgroundColor = "transparent"}>
                      {data.columns.map((col) => (
                        <td key={col}
                          className="px-4 py-2.5 font-mono"
                          style={{
                            color: S.textMain,
                            borderRight: `1px solid ${S.border}`,
                            width: colWidths[col] || "auto",
                            maxWidth: colWidths[col] || 220,
                            overflow: "hidden",
                            whiteSpace: "nowrap",
                            textOverflow: "ellipsis",
                            cursor: row[col] !== null && row[col] !== undefined ? "pointer" : "default",
                          }}
                          title={row[col] !== null && row[col] !== undefined ? String(row[col]) : ""}
                          onClick={() => row[col] !== null && row[col] !== undefined &&
                            setExpandedCell({ row: i, col, value: String(row[col]) })
                          }>
                          {row[col] !== null && row[col] !== undefined
                            ? String(row[col])
                            : <span style={{ color: S.textDim }}>null</span>}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {filtered?.length === 0 && <div className="text-center py-12" style={{ color: S.textDim }}>Keine Ergebnisse</div>}
            </div>
          </div>
        )}
      </div>
      {/* Zell-Inhalt expandiert anzeigen */}
      {expandedCell && (
        <div
          style={{
            position: "fixed", inset: 0, zIndex: 60,
            backgroundColor: "rgba(0,0,0,0.6)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}
          onClick={() => setExpandedCell(null)}
        >
          <div
            style={{
              backgroundColor: S.bgCard,
              border: `1px solid ${S.border}`,
              borderRadius: 8, padding: "16px 20px",
              maxWidth: "min(80vw, 700px)", maxHeight: "60vh",
              overflow: "auto",
              boxShadow: "0 24px 60px rgba(0,0,0,0.7)",
            }}
            onClick={e => e.stopPropagation()}
          >
            <p style={{ fontSize: 10, color: S.textDim, marginBottom: 8,
              textTransform: "uppercase", letterSpacing: "0.06em" }}>
              {expandedCell.col}
            </p>
            {/* Textarea statt pre – Text ist direkt selektierbar und kopierbar */}
            <textarea
              readOnly
              value={expandedCell.value}
              onClick={e => e.target.select()}
              style={{
                fontSize: 12, color: S.textBright,
                whiteSpace: "pre-wrap", wordBreak: "break-all",
                fontFamily: "monospace", width: "100%", minHeight: 60,
                background: "transparent", border: `1px solid ${S.border}`,
                borderRadius: 4, padding: "6px 8px", resize: "vertical",
                outline: "none", cursor: "text", boxSizing: "border-box",
              }}
            />
            <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 10 }}>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  const btn = e.currentTarget;
                  // Textarea finden und selektieren
                  const ta = btn.closest("div").previousSibling;
                  if (ta && ta.select) ta.select();
                  if (navigator.clipboard) {
                    navigator.clipboard.writeText(expandedCell.value)
                      .then(() => {
                        btn.textContent = "✓ Kopiert!";
                        btn.style.color = "#6ee7b7";
                        btn.style.borderColor = "#6ee7b7";
                        setTimeout(() => {
                          btn.textContent = "Kopieren";
                          btn.style.color = S.textDim;
                          btn.style.borderColor = S.border;
                        }, 1500);
                      })
                      .catch(() => {
                        if (ta && ta.select) { ta.select(); }
                        btn.textContent = "Text markiert – Strg+C drücken";
                        setTimeout(() => { btn.textContent = "Kopieren"; }, 2500);
                      });
                  } else {
                    if (ta && ta.select) { ta.select(); }
                    btn.textContent = "Text markiert – Strg+C drücken";
                    setTimeout(() => { btn.textContent = "Kopieren"; }, 2500);
                  }
                }}
                style={{ fontSize: 10, padding: "4px 10px",
                  borderRadius: 4, border: `1px solid ${S.border}`,
                  backgroundColor: "transparent", color: S.textDim, cursor: "pointer",
                  transition: "color 0.2s, border-color 0.2s" }}>
                Kopieren
              </button>
              <span style={{ fontSize: 10, color: S.textDim }}>
                oder Klick ins Feld → Strg+A → Strg+C
              </span>
            </div>
          </div>
        </div>
      )}

      {!loading && data && (
        <div className="px-6 py-3 flex items-center justify-between shrink-0"
          style={{ borderTop: `1px solid ${S.border}`, backgroundColor: S.bgCard }}>
          <span className="text-xs" style={{ color: S.textDim }}>
            Zeilen <span style={{ color: S.textBright }}>{page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, dataset.row_count)}</span> von <span style={{ color: S.textBright }}>{dataset.row_count}</span>
          </span>
          {totalPages > 1 && (
            <div className="flex items-center gap-2">
              <button onClick={() => goTo(page - 1)} disabled={page === 0}
                className="px-3 py-1 rounded text-xs font-medium disabled:opacity-30"
                style={{ backgroundColor: S.bgEl, color: S.textMain, border: `1px solid ${S.border}` }}>← Zurück</button>
              <span className="text-xs font-mono" style={{ color: S.textDim }}>{page + 1} / {totalPages}</span>
              <button onClick={() => goTo(page + 1)} disabled={page >= totalPages - 1}
                className="px-3 py-1 rounded text-xs font-medium disabled:opacity-30"
                style={{ backgroundColor: S.bgEl, color: S.textMain, border: `1px solid ${S.border}` }}>Weiter →</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}


// ─── ManualDatasetModal ────────────────────────────────────────────────────────

export function ManualDatasetModal({ projectId, onDone, onCancel }) {
  const [name, setName] = useState("");
  const [columns, setColumns] = useState([{ name: "", type: "string", is_primary: false, autoincrement: false }]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const addColumn = () => setColumns(c => [...c, { name: "", type: "string", is_primary: false, autoincrement: false }]);
  const removeColumn = (i) => setColumns(c => c.filter((_, idx) => idx !== i));
  const updateColumn = (i, field, value) => setColumns(c =>
    c.map((col, idx) => {
      if (idx !== i) return col;
      const updated = { ...col, [field]: value };
      // Autoincrement nur bei is_primary=true sinnvoll
      if (field === "is_primary" && !value) updated.autoincrement = false;
      // Autoincrement nur bei integer
      if (field === "type" && value !== "integer") updated.autoincrement = false;
      return updated;
    })
  );

  const handleCreate = async () => {
    if (!name.trim()) { setError("Name ist pflicht"); return; }
    const validCols = columns.filter(c => c.name.trim());
    setSaving(true); setError("");
    try {
      await api.post("/api/datasets/create", {
        name: name.trim(),
        columns: validCols,
        project_id: projectId,
      });
      onDone();
    } catch (e) {
      setError(e.response?.data?.detail || "Fehler beim Anlegen");
    } finally {
      setSaving(false);
    }
  };

  const iS = {
    background: "var(--bg-elevated)", border: "1px solid var(--border)",
    borderRadius: 6, padding: "6px 10px", fontSize: 13,
    color: "var(--text-main)", width: "100%",
  };

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 300, background: "rgba(0,0,0,0.75)",
        display: "flex", alignItems: "center", justifyContent: "center", padding: "1rem" }}
      onClick={onCancel}>
      <div onClick={e => e.stopPropagation()} style={{
        background: "var(--bg-card)", border: "1px solid var(--border)",
        borderRadius: 12, width: "100%", maxWidth: 560,
        maxHeight: "85vh", display: "flex", flexDirection: "column", overflow: "hidden",
      }}>
        {/* Header */}
        <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--border)",
            display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <p style={{ fontSize: 15, fontWeight: 600, margin: 0, color: "var(--text-bright)" }}>
            Leeres Dataset anlegen
          </p>
          <button onClick={onCancel} style={{ background: "none", border: "none",
              cursor: "pointer", color: "var(--text-dim)", fontSize: 18, lineHeight: 1 }}>✕</button>
        </div>

        {/* Body */}
        <div style={{ padding: "16px 18px", overflow: "auto", display: "flex", flexDirection: "column", gap: 16 }}>

          {/* Name */}
          <div>
            <label style={{ fontSize: 11, fontWeight: 600, color: "var(--text-dim)",
                textTransform: "uppercase", letterSpacing: "0.05em", display: "block", marginBottom: 6 }}>
              Dataset-Name
            </label>
            <input value={name} onChange={e => setName(e.target.value)}
              placeholder="z.B. Meine Tabelle" autoFocus style={iS} />
          </div>

          {/* Spalten */}
          <div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
              <label style={{ fontSize: 11, fontWeight: 600, color: "var(--text-dim)",
                  textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Spalten
              </label>
              <button onClick={addColumn} style={{
                fontSize: 11, fontWeight: 600, padding: "3px 10px", borderRadius: 6,
                cursor: "pointer", background: "rgba(110,231,183,0.1)",
                border: "1px solid rgba(110,231,183,0.3)", color: "#6ee7b7",
              }}>+ Spalte hinzufügen</button>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {columns.map((col, i) => (
                <div key={i} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 140px 32px 32px", gap: 8, alignItems: "center" }}>
                    <input
                      value={col.name}
                      onChange={e => updateColumn(i, "name", e.target.value)}
                      placeholder={`Spalte ${i + 1}`}
                      style={iS}
                    />
                    <select value={col.type} onChange={e => updateColumn(i, "type", e.target.value)} style={iS}>
                      {COL_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                    </select>
                    {/* 🔑 Primary Key Toggle */}
                    <button
                      onClick={() => updateColumn(i, "is_primary", !col.is_primary)}
                      title={col.is_primary ? "Primärschlüssel entfernen" : "Als Primärschlüssel markieren"}
                      style={{
                        background: col.is_primary ? "rgba(251,191,36,0.15)" : "none",
                        border: `1px solid ${col.is_primary ? "rgba(251,191,36,0.4)" : "var(--border)"}`,
                        borderRadius: 6, cursor: "pointer", fontSize: 14,
                        display: "flex", alignItems: "center", justifyContent: "center",
                        height: 32, width: 32, flexShrink: 0,
                      }}>🔑</button>
                    {/* ✕ Remove */}
                    <button onClick={() => removeColumn(i)} disabled={columns.length === 1}
                      style={{ background: "none", border: "none", cursor: columns.length === 1 ? "default" : "pointer",
                          color: "var(--text-dim)", fontSize: 16, opacity: columns.length === 1 ? 0.3 : 1,
                          display: "flex", alignItems: "center", justifyContent: "center" }}>✕</button>
                  </div>
                  {/* Autoincrement – nur bei is_primary + integer */}
                  {col.is_primary && col.type === "integer" && (
                    <div style={{ display: "flex", alignItems: "center", gap: 6, paddingLeft: 8 }}>
                      <input
                        type="checkbox"
                        id={`ai-${i}`}
                        checked={col.autoincrement}
                        onChange={e => updateColumn(i, "autoincrement", e.target.checked)}
                        style={{ accentColor: "#6ee7b7", cursor: "pointer" }}
                      />
                      <label htmlFor={`ai-${i}`} style={{ fontSize: 11, color: "var(--text-dim)", cursor: "pointer" }}>
                        Autoincrement (ID automatisch vergeben)
                      </label>
                    </div>
                  )}
                </div>
              ))}
            </div>
            <p style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 6 }}>
              Spalten ohne Namen werden ignoriert. Daten können später im Zeileneditor eingegeben werden.
            </p>
          </div>

          {error && (
            <p style={{ fontSize: 12, color: "#e07070", margin: 0 }}>{error}</p>
          )}
        </div>

        {/* Footer */}
        <div style={{ padding: "12px 18px", borderTop: "1px solid var(--border)",
            display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button onClick={onCancel} style={{
            fontSize: 13, padding: "7px 16px", borderRadius: 6, cursor: "pointer",
            background: "transparent", border: "1px solid var(--border)", color: "var(--text-dim)",
          }}>Abbrechen</button>
          <button onClick={handleCreate} disabled={saving || !name.trim()} style={{
            fontSize: 13, fontWeight: 600, padding: "7px 16px", borderRadius: 6,
            cursor: saving ? "wait" : "pointer",
            background: "rgba(110,231,183,0.15)", border: "1px solid rgba(110,231,183,0.4)",
            color: "#6ee7b7", opacity: saving || !name.trim() ? 0.5 : 1,
          }}>
            {saving ? "Wird angelegt…" : "Dataset anlegen"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── ExportsPanel ─────────────────────────────────────────────────────────────

export { EditDatasetModal, DatasetCard, TypeBadge, TypeBadgeEditor, DataExplorer };
