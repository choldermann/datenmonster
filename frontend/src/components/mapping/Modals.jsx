import { useState, useEffect } from "react";
import { Check, ChevronDown, Loader2, Plus, Settings, Trash2, Type, X } from "lucide-react";
import api from "../../api/client";
import { S, TARGET_TYPES, TARGET_TYPE_COLORS } from "./constants";

function FieldPickerModal({ connId, table, existingFields, onConfirm, onClose }) {
  const [cols, setCols] = useState([]);
  const [colDetails, setColDetails] = useState([]); // { name, type, raw, is_primary }
  const [selected, setSelected] = useState(() => new Set(existingFields || []));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    setLoading(true);
    api.get(`/api/connections/${connId}/columns?table=${encodeURIComponent(table)}`)
      .then(({ data }) => {
        setCols(data.columns || []);
        setColDetails(data.column_details || []);
        // Wenn noch keine Felder gewählt: alle vorauswählen
        if (!existingFields || existingFields.length === 0) {
          setSelected(new Set(data.columns || []));
        }
      })
      .catch((e) => setError(e.response?.data?.detail || e.message))
      .finally(() => setLoading(false));
  }, [connId, table]);

  const filtered = cols.filter((c) => c.toLowerCase().includes(search.toLowerCase()));
  const allFilteredSelected = filtered.length > 0 && filtered.every((c) => selected.has(c));

  const toggle = (col) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(col) ? next.delete(col) : next.add(col);
      return next;
    });
  };

  const toggleAll = () => {
    if (allFilteredSelected) {
      setSelected((prev) => { const next = new Set(prev); filtered.forEach((c) => next.delete(c)); return next; });
    } else {
      setSelected((prev) => { const next = new Set(prev); filtered.forEach((c) => next.add(c)); return next; });
    }
  };

  const handleConfirm = () => {
    // Preserve original column order
    const ordered = cols.filter((c) => selected.has(c));
    onConfirm(ordered, colDetails);
  };

  const iS = { backgroundColor: S.bgMain, border: `1px solid ${S.border}`, color: S.textBright, borderRadius: 4, padding: "6px 10px", width: "100%", outline: "none", fontSize: 12 };

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 70, display: "flex", alignItems: "center", justifyContent: "center", backgroundColor: "rgba(0,0,0,0.8)" }} onClick={onClose}>
      <div style={{ width: 460, maxHeight: "80vh", display: "flex", flexDirection: "column", backgroundColor: S.bgCard, borderRadius: 8, border: `1px solid ${S.border}`, boxShadow: "0 24px 60px rgba(0,0,0,0.8)" }} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 18px", borderBottom: `1px solid ${S.border}`, flexShrink: 0 }}>
          <div>
            <span style={{ fontSize: 13, fontWeight: 700, color: S.textBright }}>Zielfelder wählen</span>
            <p style={{ fontSize: 11, color: S.textDim, marginTop: 2, fontFamily: "monospace" }}>{table}</p>
          </div>
          <button onClick={onClose} style={{ color: S.textDim, background: "none", border: "none", cursor: "pointer", fontSize: 16 }}>✕</button>
        </div>

        {/* Search + Select All */}
        <div style={{ padding: "10px 18px", borderBottom: `1px solid ${S.border}`, flexShrink: 0, display: "flex", gap: 8, alignItems: "center" }}>
          <input
            style={{ ...iS, flex: 1 }}
            placeholder="Spalten suchen…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            autoFocus
          />
          <button
            onClick={toggleAll}
            style={{ padding: "6px 12px", borderRadius: 4, fontSize: 11, fontWeight: 600, cursor: "pointer", border: `1px solid ${S.border}`, backgroundColor: S.bgEl, color: S.textDim, whiteSpace: "nowrap", flexShrink: 0 }}>
            {allFilteredSelected ? "Alle ab" : "Alle an"}
          </button>
        </div>

        {/* Column list */}
        <div style={{ flex: 1, overflowY: "auto", scrollbarWidth: "thin", padding: "8px 10px" }}>
          {loading && (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, padding: 32, color: S.textDim }}>
              <Loader2 size={16} className="animate-spin" /> Lade Spalten…
            </div>
          )}
          {error && (
            <div style={{ padding: 16, color: "#e07070", fontSize: 12 }}>⚠ {error}</div>
          )}
          {!loading && !error && filtered.length === 0 && (
            <div style={{ padding: 16, color: S.textDim, fontSize: 12, textAlign: "center" }}>Keine Spalten gefunden</div>
          )}
          {!loading && !error && filtered.map((col) => {
            const isChecked = selected.has(col);
            const detail = colDetails.find(d => d.name === col);
            const TYPE_COLORS = { integer:"#93c5fd", decimal:"#6ee7b7", date:"#fcd34d", boolean:"#c4b5fd", string:"#6a6a6a" };
            return (
              <div key={col}
                onClick={() => toggle(col)}
                style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 10px", borderRadius: 5, cursor: "pointer", marginBottom: 2, userSelect: "none",
                  backgroundColor: isChecked ? "rgba(252,228,153,0.06)" : "transparent",
                  border: `1px solid ${isChecked ? "rgba(252,228,153,0.2)" : "transparent"}` }}
                onMouseEnter={(e) => { if (!isChecked) e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.03)"; }}
                onMouseLeave={(e) => { if (!isChecked) e.currentTarget.style.backgroundColor = "transparent"; }}>
                <div style={{ width: 16, height: 16, borderRadius: 3, border: `2px solid ${isChecked ? S.accent : S.textDim}`, backgroundColor: isChecked ? S.accent : "transparent", flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", transition: "all 0.1s" }}>
                  {isChecked && <Check size={10} color="#111" strokeWidth={3} />}
                </div>
                <span style={{ fontSize: 12, fontFamily: "monospace", color: isChecked ? S.textBright : S.textMain, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "flex", alignItems: "center", gap: 5 }}>
                  {detail?.is_primary && <span title="Primärschlüssel" style={{ fontSize: 10 }}>🔑</span>}
                  {col}
                </span>
                {detail && (
                  <span style={{ fontSize: 8, fontWeight: 700, color: TYPE_COLORS[detail.type] || "#6a6a6a",
                    backgroundColor: (TYPE_COLORS[detail.type] || "#6a6a6a") + "20",
                    borderRadius: 2, padding: "1px 4px", flexShrink: 0, fontFamily: "monospace" }}>
                    {detail.type?.slice(0,3).toUpperCase()}
                  </span>
                )}
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div style={{ padding: "12px 18px", borderTop: `1px solid ${S.border}`, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontSize: 11, color: S.textDim }}>
            {selected.size} von {cols.length} Feldern gewählt
          </span>
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={onClose} className="btn-ghost text-xs">Abbrechen</button>
            <button
              onClick={handleConfirm}
              disabled={selected.size === 0}
              className="btn-primary text-xs"
              style={{ opacity: selected.size === 0 ? 0.5 : 1 }}>
              <Check size={12} /> Übernehmen
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── TargetConfigModal ────────────────────────────────────────────────────────
function TargetConfigModal({ target, dbConnections, onSave, onClose }) {
  const isNew = !target;
  const [name, setName] = useState(target?.name || "");
  const [targetType, setTargetType] = useState(target?.target_type || "csv");
  const [connId, setConnId] = useState(target?.target_connection_id ? String(target.target_connection_id) : "");
  const [table, setTable] = useState(target?.target_table || "");
  const [writeMode, setWriteMode] = useState(target?.target_write_mode || "insert");
  const [opts, setOpts] = useState(target?.target_options || {});
  const [saveAsDataset, setSaveAsDataset] = useState(target?.save_as_dataset || false);
  const [datasetWriteMode, setDatasetWriteMode] = useState(target?.target_options?.dataset_write_mode || "replace");
  const [activeTab, setActiveTab] = useState("general");
  const [requiredFields, setRequiredFields] = useState(target?.target_options?.required_fields || []);
  const [deduplicateFields, setDeduplicateFields] = useState(target?.target_options?.deduplicate_fields || []);
  const [deduplicateEnabled, setDeduplicateEnabled] = useState(target?.target_options?.deduplicate_enabled || false);
  const [sortFields, setSortFields] = useState(target?.target_options?.sort_fields || []);
  const [rowLimit, setRowLimit] = useState(target?.target_options?.row_limit || "");

  // Felder aus target.fields extrahieren für Validierung
  const availableFields = (target?.fields || []).map(f => f.target_field).filter(Boolean);

  // Tabellen-Dropdown State
  const [availableTables, setAvailableTables] = useState([]);
  const [tablesLoading, setTablesLoading] = useState(false);
  const [tablesError, setTablesError] = useState(null);

  // FieldPicker State
  const [showFieldPicker, setShowFieldPicker] = useState(false);
  const [pendingSave, setPendingSave] = useState(null); // hält das fertige Objekt bis Felder gewählt sind

  const iS = { backgroundColor: S.bgMain, border: `1px solid ${S.border}`, color: S.textBright, borderRadius: 4, padding: "6px 10px", width: "100%", outline: "none", fontSize: 12 };
  const lS = { fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", color: S.textDim, display: "block", marginBottom: 4 };

  // Tabellen laden, wenn Verbindung gewählt und Typ = db
  useEffect(() => {
    if (targetType !== "db" || !connId) {
      setAvailableTables([]);
      return;
    }
    setTablesLoading(true);
    setTablesError(null);
    api.get(`/api/connections/${connId}/tables-only`)
      .then(({ data }) => setAvailableTables(data.tables || []))
      .catch((e) => setTablesError(e.response?.data?.detail || "Tabellen konnten nicht geladen werden"))
      .finally(() => setTablesLoading(false));
  }, [connId, targetType]);

  // Wenn Verbindung wechselt: Tabelle zurücksetzen
  const handleConnChange = (newConnId) => {
    setConnId(newConnId);
    setTable("");
  };

  const buildTargetObj = () => ({
    id: target?.id || `t_${Date.now()}`,
    name: name.trim() || targetType.toUpperCase(),
    target_type: targetType,
    target_connection_id: targetType === "db" ? (parseInt(connId) || null) : null,
    target_table: targetType === "db" ? table : "",
    target_write_mode: writeMode,
    target_options: {
      ...opts,
      dataset_write_mode: datasetWriteMode,
      required_fields: requiredFields,
      deduplicate_enabled: deduplicateEnabled,
      deduplicate_fields: deduplicateFields,
      sort_fields: sortFields.filter(sf => sf.field),
      row_limit: rowLimit ? parseInt(rowLimit) : null,
    },
    save_as_dataset: saveAsDataset,
    fields: target?.fields || [],
  });

  const handleSubmit = () => {
    // Bei DB-Typ: erst FieldPicker öffnen
    if (targetType === "db" && connId && table) {
      setPendingSave(buildTargetObj());
      setShowFieldPicker(true);
      return;
    }
    onSave(buildTargetObj());
  };

  const handleFieldPickerConfirm = (selectedCols, colDetails) => {
    if (!pendingSave) return;
    // column_types aus DB-Schema bauen
    const targetColumnTypes = {};
    (colDetails || []).forEach(d => {
      targetColumnTypes[d.name] = {
        type: d.type,
        raw: d.raw,
        is_primary: d.is_primary,
        autoincrement: false,
      };
    });
    const updatedObj = {
      ...pendingSave,
      target_options: { ...pendingSave.target_options, selected_columns: selectedCols },
      target_column_types: targetColumnTypes,
      // Zielfelder im Mapping anlegen (als leere connections, werden dann manuell verbunden)
      fields: selectedCols.map((col) => ({
        target_field: col,
        source_field: null,
        source_dataset_id: null,
        transformer: { type: "direct" },
      })),
    };
    setShowFieldPicker(false);
    setPendingSave(null);
    onSave(updatedObj);
  };

  return (
    <>
      <div style={{ position: "fixed", inset: 0, zIndex: 60, display: "flex", alignItems: "center", justifyContent: "center", backgroundColor: "rgba(0,0,0,0.7)" }} onClick={onClose}>
        <div style={{ width: 440, backgroundColor: S.bgCard, borderRadius: 8, border: `1px solid ${S.border}`, boxShadow: "0 24px 60px rgba(0,0,0,0.7)" }} onClick={(e) => e.stopPropagation()}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 18px", borderBottom: `1px solid ${S.border}` }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: S.textBright }}>{isNew ? "Neues Ziel" : "Ziel bearbeiten"}</span>
            <button onClick={onClose} style={{ color: S.textDim, background: "none", border: "none", cursor: "pointer", fontSize: 16 }}>✕</button>
          </div>
          <div style={{ padding: "16px 18px", display: "flex", flexDirection: "column", gap: 14 }}>
            {/* Name */}
            <div>
              <label style={lS}>Name</label>
              <input style={iS} value={name} onChange={(e) => setName(e.target.value)} placeholder="z.B. Kunden-Export" />
            </div>
            {/* Type */}
            <div>
              <label style={lS}>Typ</label>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {TARGET_TYPES.map((t) => (
                  <button key={t.value} onClick={() => { setTargetType(t.value); setTable(""); }}
                    style={{ padding: "6px 12px", borderRadius: 4, fontSize: 11, fontWeight: 600, cursor: "pointer", border: `1px solid ${targetType === t.value ? (TARGET_TYPE_COLORS[t.value] || S.accent) : S.border}`, backgroundColor: targetType === t.value ? (TARGET_TYPE_COLORS[t.value] || S.accent) + "22" : S.bgMain, color: targetType === t.value ? (TARGET_TYPE_COLORS[t.value] || S.accent) : S.textDim }}>
                    {t.label}
                  </button>
                ))}
              </div>
            </div>
            {/* CSV options */}
            {targetType === "csv" && (
              <div>
                <label style={lS}>Trennzeichen</label>
                <select style={iS} value={opts.delimiter || ";"} onChange={(e) => setOpts({ ...opts, delimiter: e.target.value })}>
                  {[";", ",", "|", "\t"].map((d) => <option key={d} value={d}>{d === "\t" ? "Tab" : d}</option>)}
                </select>
              </div>
            )}
            {/* DB options */}
            {targetType === "db" && (
              <>
                <div>
                  <label style={lS}>Verbindung</label>
                  <select style={iS} value={connId} onChange={(e) => handleConnChange(e.target.value)}>
                    <option value="">– wählen –</option>
                    {dbConnections.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.db_type})</option>)}
                  </select>
                </div>
                <div>
                  <label style={lS}>Zieltabelle</label>
                  {tablesLoading ? (
                    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", backgroundColor: S.bgMain, borderRadius: 4, border: `1px solid ${S.border}`, color: S.textDim, fontSize: 12 }}>
                      <Loader2 size={13} className="animate-spin" /> Lade Tabellen…
                    </div>
                  ) : tablesError ? (
                    <div style={{ fontSize: 11, color: "#e07070", padding: "6px 0" }}>⚠ {tablesError}</div>
                  ) : availableTables.length > 0 ? (
                    <select style={iS} value={table} onChange={(e) => setTable(e.target.value)}>
                      <option value="">– Tabelle wählen –</option>
                      {availableTables.map((t) => <option key={t} value={t}>{t}</option>)}
                    </select>
                  ) : (
                    /* Fallback: freies Textfeld wenn noch keine Verbindung gewählt oder keine Tabellen */
                    <input style={iS} value={table} onChange={(e) => setTable(e.target.value)} placeholder={connId ? "Keine Tabellen gefunden" : "Erst Verbindung wählen"} />
                  )}
                </div>
                <div>
                  <label style={lS}>Schreibmodus</label>
                  <select style={iS} value={writeMode} onChange={(e) => setWriteMode(e.target.value)}>
                    {[{ v: "insert", l: "Insert (anhängen)" }, { v: "truncate_insert", l: "Truncate + Insert" }, { v: "update", l: "Update" }, { v: "upsert", l: "Upsert" }].map((m) => (
                      <option key={m.v} value={m.v}>{m.l}</option>
                    ))}
                  </select>
                </div>
                {connId && table && (
                  <p style={{ fontSize: 10, color: S.textDim, fontStyle: "italic" }}>
                    💡 Nach dem Speichern kannst du die Zielfelder aus der Tabelle auswählen.
                  </p>
                )}
              </>
            )}
            {/* Als Dataset speichern */}
            <div
              onClick={() => setSaveAsDataset((v) => !v)}
              style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "10px 12px", borderRadius: 6, border: `1px solid ${saveAsDataset ? S.accent : S.border}`, backgroundColor: saveAsDataset ? "rgba(252,228,153,0.06)" : S.bgMain, cursor: "pointer", userSelect: "none" }}>
              <div style={{ width: 16, height: 16, borderRadius: 3, border: `2px solid ${saveAsDataset ? S.accent : S.textDim}`, backgroundColor: saveAsDataset ? S.accent : "transparent", flexShrink: 0, marginTop: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
                {saveAsDataset && <Check size={10} color="#111" strokeWidth={3} />}
              </div>
              <div>
                <p style={{ fontSize: 12, fontWeight: 600, color: saveAsDataset ? S.accent : S.textMain, marginBottom: 2 }}>Als Dataset speichern</p>
                <p style={{ fontSize: 11, color: S.textDim, lineHeight: 1.4 }}>Output wird als wiederverwendbares Dataset gespeichert und steht in anderen Mappings als Quelle zur Verfügung.</p>
              </div>
            </div>

            {/* Dataset Schreibmodus – nur wenn save_as_dataset aktiv */}
            {saveAsDataset && (
              <div style={{ padding: "10px 12px", borderRadius: 6, border: `1px solid ${S.accent}33`, backgroundColor: "rgba(252,228,153,0.04)" }}>
                <label style={lS}>Schreibmodus</label>
                <div style={{ display: "flex", gap: 6 }}>
                  {[
                    { v: "replace", l: "Überschreiben", desc: "Dataset wird bei jedem Ausführen komplett ersetzt" },
                    { v: "append",  l: "Anfügen",       desc: "Neue Zeilen werden zum bestehenden Dataset hinzugefügt" },
                    { v: "upsert",  l: "Upsert",        desc: "Zeilen mit gleichem Primärschlüssel werden aktualisiert, neue werden eingefügt" },
                  ].map(({ v, l, desc }) => (
                    <div key={v} onClick={(e) => { e.stopPropagation(); setDatasetWriteMode(v); }}
                      style={{ flex: 1, padding: "8px 10px", borderRadius: 5, cursor: "pointer", border: `1px solid ${datasetWriteMode === v ? S.accent : S.border}`, backgroundColor: datasetWriteMode === v ? "rgba(252,228,153,0.1)" : "transparent" }}>
                      <p style={{ fontSize: 11, fontWeight: 600, color: datasetWriteMode === v ? S.accent : S.textMain, marginBottom: 2 }}>{l}</p>
                      <p style={{ fontSize: 10, color: S.textDim, lineHeight: 1.4 }}>{desc}</p>
                    </div>
                  ))}
                </div>
                {datasetWriteMode === "upsert" && (
                  <p style={{ fontSize: 10, color: "#fbbf24", marginTop: 8, lineHeight: 1.4 }}>
                    🔑 Upsert benötigt mindestens ein als Primärschlüssel markiertes Feld im Ziel-Dataset. Primärschlüssel können im Dataset-Editor gesetzt werden.
                  </p>
                )}
              </div>
            )}
          </div>

          {/* Tab-Navigation */}
          <div style={{ display: "flex", gap: 0, borderTop: `1px solid ${S.border}`, backgroundColor: S.bgEl }}>
            {[["general", "Allgemein"], ["sort", "Sortierung"], ["validation", "Validierung"]].map(([tab, label]) => (
              <button key={tab} onClick={() => setActiveTab(tab)}
                style={{ padding: "8px 16px", fontSize: 11, fontWeight: 600, cursor: "pointer", background: "none", border: "none", borderBottom: `2px solid ${activeTab === tab ? S.accent : "transparent"}`, color: activeTab === tab ? S.accent : S.textDim }}>
                {label}
              </button>
            ))}
          </div>

          {/* Sortierungs-Tab */}
          {activeTab === "sort" && (
            <div style={{ padding: "14px 18px", display: "flex", flexDirection: "column", gap: 14 }}>
              <p style={{ fontSize: 11, color: S.textDim, margin: 0 }}>
                Sortierung wird auf den fertigen Output angewendet – vor dem Schreiben ins Ziel.
              </p>

              {/* Sort fields */}
              <div>
                <label style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", color: S.textDim, display: "block", marginBottom: 8 }}>Sortierfelder</label>
                {sortFields.map((sf, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
                    <span style={{ fontSize: 10, color: S.textDim, width: 16, textAlign: "center" }}>{i + 1}</span>
                    <select value={sf.field} onChange={e => setSortFields(prev => prev.map((f, idx) => idx === i ? { ...f, field: e.target.value } : f))}
                      style={{ backgroundColor: S.bgMain, border: `1px solid ${S.border}`, color: S.textBright, borderRadius: 4, padding: "5px 8px", fontSize: 11, outline: "none", flex: 1 }}>
                      <option value="">– Feld wählen –</option>
                      {availableFields.map(f => <option key={f} value={f}>{f}</option>)}
                    </select>
                    <button onClick={() => setSortFields(prev => prev.map((f, idx) => idx === i ? { ...f, dir: f.dir === "asc" ? "desc" : "asc" } : f))}
                      style={{ background: "none", border: `1px solid ${S.border}`, borderRadius: 4, cursor: "pointer", padding: "4px 8px", color: "#a78bfa", fontSize: 10, fontWeight: 700, flexShrink: 0 }}>
                      {sf.dir === "asc" ? "▲ ASC" : "▼ DESC"}
                    </button>
                    <button onClick={() => setSortFields(prev => prev.filter((_, idx) => idx !== i))}
                      style={{ color: S.textDim, background: "none", border: "none", cursor: "pointer", padding: 2, flexShrink: 0 }}
                      onMouseEnter={e => e.currentTarget.style.color = "#e07070"}
                      onMouseLeave={e => e.currentTarget.style.color = S.textDim}>✕</button>
                  </div>
                ))}
                <button onClick={() => setSortFields(prev => [...prev, { field: "", dir: "asc" }])}
                  style={{ width: "100%", padding: "6px 0", borderRadius: 4, border: `1px dashed ${S.border}`, background: "none", color: S.textDim, cursor: "pointer", fontSize: 11, marginTop: 4 }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = "#a78bfa"; e.currentTarget.style.color = "#a78bfa"; }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = S.border; e.currentTarget.style.color = S.textDim; }}>
                  + Sortierfeld hinzufügen
                </button>
              </div>

              {/* Row limit */}
              <div>
                <label style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", color: S.textDim, display: "block", marginBottom: 4 }}>Limit (optional)</label>
                <input type="number" value={rowLimit} onChange={e => setRowLimit(e.target.value)}
                  placeholder="z.B. 1000 – leer = alle Zeilen"
                  style={{ backgroundColor: S.bgMain, border: `1px solid ${S.border}`, color: S.textBright, borderRadius: 4, padding: "6px 10px", width: "100%", outline: "none", fontSize: 12 }} />
                <p style={{ fontSize: 10, color: S.textDim, marginTop: 4 }}>Maximale Anzahl Zeilen im Output. Leer lassen für alle Zeilen.</p>
              </div>
            </div>
          )}

          {/* Validierungs-Tab */}
          {activeTab === "validation" && (
            <div style={{ padding: "14px 18px", display: "flex", flexDirection: "column", gap: 16 }}>

              {/* Pflichtfelder */}
              <div>
                <p style={{ fontSize: 11, fontWeight: 600, color: S.textBright, marginBottom: 4 }}>Pflichtfelder</p>
                <p style={{ fontSize: 10, color: S.textDim, marginBottom: 10 }}>Export schlägt fehl wenn diese Felder leer sind.</p>
                {availableFields.length === 0 && (
                  <p style={{ fontSize: 10, color: S.textDim, fontStyle: "italic" }}>Erst Zielfelder im Mapping definieren.</p>
                )}
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {availableFields.map(f => {
                    const active = requiredFields.includes(f);
                    return (
                      <button key={f} onClick={() => setRequiredFields(prev => active ? prev.filter(x => x !== f) : [...prev, f])}
                        style={{ padding: "3px 10px", borderRadius: 4, fontSize: 10, fontWeight: 600, cursor: "pointer", border: `1px solid ${active ? "#e07070" : S.border}`, backgroundColor: active ? "rgba(224,112,112,0.12)" : "transparent", color: active ? "#e07070" : S.textDim }}>
                        {active ? "✕ " : ""}{f}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Duplikat-Entfernung */}
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}
                  onClick={() => setDeduplicateEnabled(v => !v)}>
                  <div style={{ width: 16, height: 16, borderRadius: 3, border: `2px solid ${deduplicateEnabled ? S.accent : S.textDim}`, backgroundColor: deduplicateEnabled ? S.accent : "transparent", flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer" }}>
                    {deduplicateEnabled && <Check size={10} color="#111" strokeWidth={3} />}
                  </div>
                  <p style={{ fontSize: 11, fontWeight: 600, color: deduplicateEnabled ? S.accent : S.textMain, cursor: "pointer" }}>Duplikate entfernen</p>
                </div>
                {deduplicateEnabled && (
                  <>
                    <p style={{ fontSize: 10, color: S.textDim, marginBottom: 8 }}>Schlüsselfelder – Zeilen mit gleicher Kombination werden dedupliziert (erste Zeile bleibt).</p>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                      {availableFields.map(f => {
                        const active = deduplicateFields.includes(f);
                        return (
                          <button key={f} onClick={() => setDeduplicateFields(prev => active ? prev.filter(x => x !== f) : [...prev, f])}
                            style={{ padding: "3px 10px", borderRadius: 4, fontSize: 10, fontWeight: 600, cursor: "pointer", border: `1px solid ${active ? S.accent : S.border}`, backgroundColor: active ? "rgba(252,228,153,0.12)" : "transparent", color: active ? S.accent : S.textDim }}>
                            {active ? "✓ " : ""}{f}
                          </button>
                        );
                      })}
                    </div>
                    {deduplicateFields.length === 0 && availableFields.length > 0 && (
                      <p style={{ fontSize: 10, color: S.textDim, fontStyle: "italic", marginTop: 6 }}>Keine Felder gewählt = alle Spalten als Schlüssel.</p>
                    )}
                  </>
                )}
              </div>
            </div>
          )}

          <div style={{ padding: "12px 18px", borderTop: `1px solid ${S.border}`, display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <button onClick={onClose} className="btn-ghost text-xs">Abbrechen</button>
            <button onClick={handleSubmit} className="btn-primary text-xs">
              <Check size={12} /> {isNew ? "Ziel erstellen" : (targetType === "db" && connId && table ? "Speichern & Felder wählen" : "Speichern")}
            </button>
          </div>
        </div>
      </div>

      {/* FieldPicker tritt über das TargetConfigModal */}
      {showFieldPicker && pendingSave && (
        <FieldPickerModal
          connId={connId}
          table={table}
          existingFields={target?.fields?.map((f) => f.target_field).filter(Boolean) || []}
          onConfirm={handleFieldPickerConfirm}
          onClose={() => { setShowFieldPicker(false); setPendingSave(null); }}
        />
      )}
    </>
  );
}

// ─── Main MappingEditor ────────────────────────────────────────────────────────

export { FieldPickerModal, TargetConfigModal };
