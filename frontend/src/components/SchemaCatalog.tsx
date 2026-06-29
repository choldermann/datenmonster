import { useState, useEffect, useCallback } from "react";
import { BookOpen, ChevronDown, ChevronRight, Download, Loader2, Sparkles, Plus, Trash2, Search, Star, StarOff, Upload } from "lucide-react";
import { useRef } from "react";
import api from "../api/client";
import { S } from "./dashboard/constants";

const CATEGORIES = ["Stammdaten", "Bewegungsdaten", "Konfiguration", "Lookup", "System", "Sonstige"];
const CAT_COLOR: Record<string, string> = {
  Stammdaten: "#60a5fa", Bewegungsdaten: "#34d399", Konfiguration: "#fbbf24",
  Lookup: "#a78bfa", System: "#f87171", Sonstige: S.textDim,
};

const inp = (extra?: object) => ({
  backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4,
  color: S.textBright, fontSize: 12, padding: "4px 8px", outline: "none", width: "100%",
  ...extra,
});

interface ColumnMeta { column_name: string; description: string | null; example_values: string | null; }
interface TableMeta {
  id: number; table_full_name: string; business_name: string | null;
  description: string | null; category: string | null; is_important: boolean;
  columns: ColumnMeta[];
}
interface Relation { id: number; from_table: string; from_col: string; to_table: string; to_col: string; description: string | null; }

export default function SchemaCatalog({ connectionId }: { connectionId: number }) {
  const [tables, setTables]       = useState<TableMeta[]>([]);
  const [relations, setRelations] = useState<Relation[]>([]);
  const [loading, setLoading]     = useState(true);
  const [search, setSearch]       = useState("");
  const [expanded, setExpanded]   = useState<Set<string>>(new Set());
  const [suggesting, setSuggesting] = useState(false);
  const [suggestProgress, setSuggestProgress] = useState<{done: number; total: number} | null>(null);
  const [activeTab, setActiveTab] = useState<"tables" | "relations">("tables");
  const [newRel, setNewRel]       = useState({ from_table: "", from_col: "", to_table: "", to_col: "", description: "" });
  const [addingRel, setAddingRel] = useState(false);
  const [dirty, setDirty]         = useState<Record<string, TableMeta>>({});
  const [importing, setImporting] = useState(false);
  const importRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/api/schema-catalog/${connectionId}`);
      // Erste Verwendung: Katalog-Einträge aus Schema-Cache anlegen
      if ((data.tables || []).length === 0) {
        await api.post(`/api/schema-catalog/${connectionId}/sync`);
        const { data: fresh } = await api.get(`/api/schema-catalog/${connectionId}`);
        setTables(fresh.tables || []);
        setRelations(fresh.relations || []);
      } else {
        setTables(data.tables || []);
        setRelations(data.relations || []);
      }
    } finally { setLoading(false); }
  }, [connectionId]);

  useEffect(() => { load(); }, [load]);

  const save = async (tbl: TableMeta) => {
    await api.put(`/api/schema-catalog/${connectionId}/table`, {
      table_full_name: tbl.table_full_name,
      business_name: tbl.business_name || null,
      description: tbl.description || null,
      category: tbl.category || null,
      is_important: tbl.is_important,
    });
    setDirty(d => { const n = {...d}; delete n[tbl.table_full_name]; return n; });
  };

  const saveCol = async (tableName: string, col: ColumnMeta) => {
    await api.put(`/api/schema-catalog/${connectionId}/column`, {
      table_full_name: tableName, column_name: col.column_name,
      description: col.description || null, example_values: col.example_values || null,
    });
  };

  const updateDirty = (tbl: TableMeta, changes: Partial<TableMeta>) => {
    const updated = { ...tbl, ...changes };
    setTables(ts => ts.map(t => t.table_full_name === tbl.table_full_name ? updated : t));
    setDirty(d => ({ ...d, [tbl.table_full_name]: updated }));
  };

  const handleAiSuggest = async (tableNames: string[] = []) => {
    setSuggesting(true);
    setSuggestProgress({ done: 0, total: tableNames.length || tables.filter(t => !t.description).length });
    try {
      const token = localStorage.getItem("dm_token") || "";
      const resp  = await fetch(`/api/schema-catalog/${connectionId}/ai-suggest`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ table_full_names: tableNames }),
      });
      const reader  = resp.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop()!;
        for (const line of lines) {
          if (!line.startsWith("data:")) continue;
          const msg = JSON.parse(line.slice(5).trim());
          if (msg.progress !== undefined) setSuggestProgress({ done: msg.progress, total: msg.total });
          if (msg.done) { await load(); setSuggestProgress(null); }
        }
      }
    } finally { setSuggesting(false); }
  };

  const addRelation = async () => {
    if (!newRel.from_table || !newRel.from_col || !newRel.to_table || !newRel.to_col) return;
    setAddingRel(true);
    try {
      await api.post(`/api/schema-catalog/${connectionId}/relations`, newRel);
      setNewRel({ from_table: "", from_col: "", to_table: "", to_col: "", description: "" });
      await load();
    } finally { setAddingRel(false); }
  };

  const handleExport = async () => {
    const token = localStorage.getItem("dm_token") || "";
    const resp  = await fetch(`/api/schema-catalog/${connectionId}/export`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const blob = await resp.blob();
    const cd   = resp.headers.get("content-disposition") || "";
    const name = cd.match(/filename="([^"]+)"/)?.[1] || `schema_catalog_${connectionId}.json`;
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href = url; a.download = name; a.click();
    URL.revokeObjectURL(url);
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const text    = await file.text();
      const payload = JSON.parse(text);
      await api.post(`/api/schema-catalog/${connectionId}/import`, payload);
      await load();
    } catch (err: any) {
      alert("Import fehlgeschlagen: " + (err.response?.data?.detail || err.message));
    } finally {
      setImporting(false);
      if (importRef.current) importRef.current.value = "";
    }
  };

  const deleteRelation = async (id: number) => {
    await api.delete(`/api/schema-catalog/${connectionId}/relations/${id}`);
    setRelations(rs => rs.filter(r => r.id !== id));
  };

  const filtered = tables.filter(t =>
    !search || t.table_full_name.toLowerCase().includes(search.toLowerCase()) ||
    (t.description || "").toLowerCase().includes(search.toLowerCase()) ||
    (t.business_name || "").toLowerCase().includes(search.toLowerCase())
  );

  const toggleExpand = (name: string) =>
    setExpanded(s => { const n = new Set(s); n.has(name) ? n.delete(name) : n.add(name); return n; });

  const described = tables.filter(t => t.description).length;
  const undescribed = tables.filter(t => !t.description).length;

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: 20, color: S.textDim, fontSize: 12 }}>
      <Loader2 size={14} className="animate-spin" /> Lade Katalog…
    </div>
  );

  return (
    <div style={{ fontSize: 12, color: S.textMain }}>
      {/* Hidden file input for import */}
      <input ref={importRef} type="file" accept=".json" style={{ display: "none" }} onChange={handleImport} />

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <BookOpen size={14} color={S.accent} />
          <span style={{ fontWeight: 700, color: S.textBright }}>Schema-Katalog</span>
          <span style={{ color: S.textDim }}>
            {described}/{tables.length} beschrieben
          </span>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <button onClick={handleExport}
            style={{ display: "flex", alignItems: "center", gap: 5, backgroundColor: S.bgEl,
              color: S.textDim, border: `1px solid ${S.border}`, borderRadius: 6, padding: "5px 10px",
              cursor: "pointer", fontSize: 11 }}>
            <Download size={11} /> Export
          </button>
          <button onClick={() => importRef.current?.click()} disabled={importing}
            style={{ display: "flex", alignItems: "center", gap: 5, backgroundColor: S.bgEl,
              color: S.textDim, border: `1px solid ${S.border}`, borderRadius: 6, padding: "5px 10px",
              cursor: importing ? "not-allowed" : "pointer", fontSize: 11 }}>
            {importing ? <Loader2 size={11} className="animate-spin" /> : <Upload size={11} />}
            Import
          </button>
          <button
            onClick={() => handleAiSuggest()}
            disabled={suggesting || undescribed === 0}
            style={{ display: "flex", alignItems: "center", gap: 5, backgroundColor: suggesting ? S.bgEl : "#7c3aed",
              color: "#fff", border: "none", borderRadius: 6, padding: "5px 10px", cursor: suggesting ? "not-allowed" : "pointer",
              fontSize: 11, opacity: undescribed === 0 ? 0.5 : 1 }}
          >
            {suggesting ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} />}
            {suggesting
              ? suggestProgress ? `${suggestProgress.done}/${suggestProgress.total}` : "…"
              : `KI: ${undescribed} beschreiben`}
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 2, marginBottom: 12, borderBottom: `1px solid ${S.border}` }}>
        {(["tables", "relations"] as const).map(tab => (
          <button key={tab} onClick={() => setActiveTab(tab)} style={{
            background: "none", border: "none", cursor: "pointer", padding: "6px 12px",
            fontSize: 11, fontWeight: activeTab === tab ? 700 : 400,
            color: activeTab === tab ? S.textBright : S.textDim,
            borderBottom: activeTab === tab ? `2px solid ${S.accent}` : "2px solid transparent",
            marginBottom: -1,
          }}>
            {tab === "tables" ? `Tabellen (${tables.length})` : `Beziehungen (${relations.length})`}
          </button>
        ))}
      </div>

      {activeTab === "tables" && (
        <>
          {/* Search */}
          <div style={{ position: "relative", marginBottom: 10 }}>
            <Search size={11} style={{ position: "absolute", left: 8, top: "50%", transform: "translateY(-50%)", color: S.textDim }} />
            <input value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Tabelle suchen…"
              style={{ ...inp(), paddingLeft: 26 }} />
          </div>

          {/* Table List */}
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {filtered.map(tbl => {
              const isOpen = expanded.has(tbl.table_full_name);
              const isDirty = !!dirty[tbl.table_full_name];
              const current = dirty[tbl.table_full_name] || tbl;
              return (
                <div key={tbl.table_full_name} style={{ backgroundColor: S.bgEl, borderRadius: 6, border: `1px solid ${isDirty ? S.accent : S.border}` }}>
                  {/* Row header */}
                  <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 10px", cursor: "pointer" }}
                    onClick={() => toggleExpand(tbl.table_full_name)}>
                    {isOpen ? <ChevronDown size={11} color={S.textDim} /> : <ChevronRight size={11} color={S.textDim} />}
                    <button onClick={e => { e.stopPropagation(); updateDirty(current, { is_important: !current.is_important }); save({ ...current, is_important: !current.is_important }); }}
                      style={{ background: "none", border: "none", cursor: "pointer", padding: 0, display: "flex" }}>
                      {current.is_important
                        ? <Star size={11} fill="#fbbf24" color="#fbbf24" />
                        : <StarOff size={11} color={S.textDim} />}
                    </button>
                    <span style={{ fontWeight: 600, color: S.textBright, fontFamily: "monospace" }}>{tbl.table_full_name}</span>
                    {current.business_name && (
                      <span style={{ color: S.accent, fontSize: 11 }}>"{current.business_name}"</span>
                    )}
                    {current.category && (
                      <span style={{ color: CAT_COLOR[current.category] || S.textDim, fontSize: 10,
                        backgroundColor: S.bgCard, borderRadius: 3, padding: "1px 5px" }}>
                        {current.category}
                      </span>
                    )}
                    {!current.description && (
                      <span style={{ color: "#f87171", fontSize: 10, marginLeft: "auto" }}>keine Beschreibung</span>
                    )}
                    {current.description && (
                      <span style={{ color: S.textDim, fontSize: 11, marginLeft: "auto", overflow: "hidden",
                        textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 260 }}>
                        {current.description}
                      </span>
                    )}
                  </div>

                  {/* Expanded edit form */}
                  {isOpen && (
                    <div style={{ padding: "0 10px 10px", borderTop: `1px solid ${S.border}`, marginTop: 4, paddingTop: 10 }}>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
                        <div>
                          <div style={{ fontSize: 10, color: S.textDim, marginBottom: 3 }}>ANZEIGENAME</div>
                          <input style={inp()} value={current.business_name || ""}
                            onChange={e => updateDirty(current, { business_name: e.target.value })}
                            onBlur={() => save(current)} placeholder="z.B. Artikel" />
                        </div>
                        <div>
                          <div style={{ fontSize: 10, color: S.textDim, marginBottom: 3 }}>KATEGORIE</div>
                          <select style={{ ...inp(), cursor: "pointer" }} value={current.category || ""}
                            onChange={e => { const updated = { ...current, category: e.target.value || null }; updateDirty(current, { category: e.target.value || null }); save(updated); }}>
                            <option value="">— wählen —</option>
                            {CATEGORIES.map(c => <option key={c}>{c}</option>)}
                          </select>
                        </div>
                      </div>
                      <div style={{ marginBottom: 8 }}>
                        <div style={{ fontSize: 10, color: S.textDim, marginBottom: 3 }}>BESCHREIBUNG</div>
                        <input style={inp()} value={current.description || ""}
                          onChange={e => updateDirty(current, { description: e.target.value })}
                          onBlur={() => save(current)}
                          placeholder="Was enthält diese Tabelle? (1 Satz)" />
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <button onClick={() => handleAiSuggest([tbl.table_full_name])}
                          disabled={suggesting}
                          style={{ display: "flex", alignItems: "center", gap: 4, background: "none",
                            border: `1px solid ${S.border}`, borderRadius: 4, padding: "3px 8px",
                            color: S.textDim, fontSize: 10, cursor: "pointer" }}>
                          <Sparkles size={10} /> KI-Vorschlag
                        </button>
                        {isDirty && (
                          <button onClick={() => save(current)}
                            style={{ backgroundColor: S.accent, color: "#fff", border: "none",
                              borderRadius: 4, padding: "3px 10px", fontSize: 10, cursor: "pointer" }}>
                            Speichern
                          </button>
                        )}
                      </div>

                      {/* Columns */}
                      {current.columns.length > 0 && (
                        <div style={{ marginTop: 10, borderTop: `1px solid ${S.border}`, paddingTop: 8 }}>
                          <div style={{ fontSize: 10, color: S.textDim, marginBottom: 6 }}>SPALTEN</div>
                          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                            {current.columns.map(col => (
                              <div key={col.column_name} style={{ display: "grid", gridTemplateColumns: "120px 1fr 100px", gap: 6, alignItems: "center" }}>
                                <span style={{ fontFamily: "monospace", fontSize: 11, color: S.textBright }}>{col.column_name}</span>
                                <input style={inp({ padding: "2px 6px" })}
                                  defaultValue={col.description || ""}
                                  onBlur={e => saveCol(tbl.table_full_name, { ...col, description: e.target.value })}
                                  placeholder="Beschreibung…" />
                                <input style={inp({ padding: "2px 6px" })}
                                  defaultValue={col.example_values || ""}
                                  onBlur={e => saveCol(tbl.table_full_name, { ...col, example_values: e.target.value })}
                                  placeholder="Beispiel…" />
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}

      {activeTab === "relations" && (
        <div>
          {/* Neue Relation */}
          <div style={{ backgroundColor: S.bgEl, borderRadius: 6, padding: 12, marginBottom: 12, border: `1px solid ${S.border}` }}>
            <div style={{ fontSize: 10, color: S.textDim, marginBottom: 8 }}>NEUE FK-BEZIEHUNG</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 80px 1fr 80px", gap: 6, marginBottom: 6 }}>
              <input style={inp()} value={newRel.from_table}
                onChange={e => setNewRel(r => ({ ...r, from_table: e.target.value }))}
                placeholder="Von Tabelle (z.B. Rechnung.tRechnungPos)" />
              <input style={inp()} value={newRel.from_col}
                onChange={e => setNewRel(r => ({ ...r, from_col: e.target.value }))}
                placeholder="Spalte" />
              <input style={inp()} value={newRel.to_table}
                onChange={e => setNewRel(r => ({ ...r, to_table: e.target.value }))}
                placeholder="Zu Tabelle (z.B. dbo.tArtikel)" />
              <input style={inp()} value={newRel.to_col}
                onChange={e => setNewRel(r => ({ ...r, to_col: e.target.value }))}
                placeholder="Spalte" />
            </div>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <input style={{ ...inp(), flex: 1 }} value={newRel.description}
                onChange={e => setNewRel(r => ({ ...r, description: e.target.value }))}
                placeholder="Beschreibung (optional)" />
              <button onClick={addRelation} disabled={addingRel || !newRel.from_table || !newRel.to_table}
                style={{ display: "flex", alignItems: "center", gap: 4, backgroundColor: S.accent,
                  color: "#fff", border: "none", borderRadius: 4, padding: "5px 10px",
                  cursor: "pointer", fontSize: 11, whiteSpace: "nowrap" }}>
                <Plus size={11} /> Hinzufügen
              </button>
            </div>
          </div>

          {/* Relation List */}
          {relations.length === 0 ? (
            <div style={{ color: S.textDim, fontSize: 11, padding: "12px 0" }}>
              Noch keine manuellen Beziehungen definiert.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {relations.map(r => (
                <div key={r.id} style={{ display: "flex", alignItems: "center", gap: 8,
                  backgroundColor: S.bgEl, borderRadius: 6, padding: "6px 10px",
                  border: `1px solid ${S.border}` }}>
                  <span style={{ fontFamily: "monospace", fontSize: 11, color: S.textBright }}>
                    {r.from_table}.<span style={{ color: "#fbbf24" }}>{r.from_col}</span>
                    {" → "}
                    {r.to_table}.<span style={{ color: "#fbbf24" }}>{r.to_col}</span>
                  </span>
                  {r.description && <span style={{ color: S.textDim, fontSize: 11 }}>({r.description})</span>}
                  <button onClick={() => deleteRelation(r.id)}
                    style={{ marginLeft: "auto", background: "none", border: "none",
                      color: "#f87171", cursor: "pointer", padding: 2 }}>
                    <Trash2 size={11} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
