import { useState } from "react";
import { X, Sparkles, Loader2, Check, Plus, ChevronDown, ChevronUp, ArrowLeft, Table2, Eye } from "lucide-react";
import api from "../api/client";
import { getTableContext, suggestDatasets } from "../services/aiService";
import { S } from "./dashboard/constants";

const ACCENT = "#fce499";

const MATCH_LABELS = {
  keyword:   { label: "Keyword",  color: "rgba(252,228,153,0.7)" },
  fk_parent: { label: "FK ↑",     color: "rgba(167,139,250,0.7)" },
  fk_child:  { label: "FK ↓",     color: "rgba(110,231,183,0.7)" },
  fallback:  { label: "Schema",   color: "rgba(148,163,184,0.5)" },
};

const iS = {
  backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4,
  color: S.textBright, fontSize: 11, padding: "6px 10px", outline: "none", width: "100%",
  boxSizing: "border-box",
};

// ── Step 1: Description ───────────────────────────────────────────────────────
function StepDescription({ description, setDescription, onAnalyze, loading }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <label style={{ fontSize: 10, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em" }}>
        Was benötigst du?
      </label>
      <textarea
        value={description}
        onChange={e => setDescription(e.target.value)}
        placeholder={'z.B. "Rechnungen mit Lieferantendaten der letzten 3 Monate"'}
        rows={3}
        style={{ ...iS, resize: "vertical", fontFamily: "inherit", lineHeight: 1.5 }}
        onKeyDown={e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) onAnalyze(); }}
      />
      <span style={{ fontSize: 9, color: S.textDim }}>Ctrl+Enter</span>
      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <button onClick={onAnalyze} disabled={loading || !description.trim()}
          style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 14px", borderRadius: 4,
            border: `1px solid rgba(252,228,153,0.3)`, backgroundColor: "rgba(252,228,153,0.08)",
            color: ACCENT, fontSize: 11, fontWeight: 600,
            cursor: loading || !description.trim() ? "not-allowed" : "pointer",
            opacity: loading || !description.trim() ? 0.6 : 1 }}>
          {loading ? <Loader2 size={11} className="animate-spin" /> : <Table2 size={11} />}
          {loading ? "Analysiere Schema…" : "Tabellen analysieren"}
        </button>
      </div>
    </div>
  );
}

// ── Table preview modal ───────────────────────────────────────────────────────
function TablePreviewModal({ table, onClose }) {
  const cols = table.columns || [];
  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 300, backgroundColor: "rgba(0,0,0,0.55)",
      display: "flex", alignItems: "center", justifyContent: "center" }}
      onClick={onClose}>
      <div style={{ width: 520, maxHeight: "70vh", display: "flex", flexDirection: "column",
        backgroundColor: S.bgCard, borderRadius: 8, border: `1px solid ${S.border}`,
        boxShadow: "0 16px 48px rgba(0,0,0,0.6)", overflow: "hidden" }}
        onClick={e => e.stopPropagation()}>

        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 14px",
          borderBottom: `1px solid ${S.border}`, backgroundColor: "rgba(255,255,255,0.02)" }}>
          <Table2 size={13} style={{ color: S.textDim }} />
          <span style={{ flex: 1, fontSize: 12, fontWeight: 700, color: S.textBright, fontFamily: "monospace" }}>
            {table.full_name}
          </span>
          <span style={{ fontSize: 10, color: S.textDim }}>{cols.length} Spalten</span>
          <button onClick={onClose} style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", marginLeft: 4 }}>
            <X size={12} />
          </button>
        </div>

        <div style={{ overflowY: "auto", flex: 1 }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
            <thead>
              <tr style={{ backgroundColor: "rgba(255,255,255,0.03)", position: "sticky", top: 0 }}>
                <th style={{ textAlign: "left", padding: "5px 14px", color: S.textDim, fontWeight: 600, fontSize: 9,
                  textTransform: "uppercase", letterSpacing: "0.06em", borderBottom: `1px solid ${S.border}` }}>Spalte</th>
                <th style={{ textAlign: "left", padding: "5px 10px", color: S.textDim, fontWeight: 600, fontSize: 9,
                  textTransform: "uppercase", letterSpacing: "0.06em", borderBottom: `1px solid ${S.border}` }}>Typ</th>
                <th style={{ textAlign: "left", padding: "5px 14px 5px 0", color: S.textDim, fontWeight: 600, fontSize: 9,
                  textTransform: "uppercase", letterSpacing: "0.06em", borderBottom: `1px solid ${S.border}` }}>Info</th>
              </tr>
            </thead>
            <tbody>
              {cols.map((col, i) => (
                <tr key={i} style={{ borderBottom: `1px solid rgba(255,255,255,0.04)`,
                  backgroundColor: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.01)" }}>
                  <td style={{ padding: "4px 14px", color: col.pk ? ACCENT : S.textMain, fontFamily: "monospace", fontWeight: col.pk ? 700 : 400 }}>
                    {col.name}
                  </td>
                  <td style={{ padding: "4px 10px", color: S.textDim, fontFamily: "monospace", fontSize: 10 }}>
                    {col.type}
                  </td>
                  <td style={{ padding: "4px 14px 4px 0" }}>
                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                      {col.pk && (
                        <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 8,
                          color: ACCENT, border: `1px solid rgba(252,228,153,0.35)` }}>PK</span>
                      )}
                      {col.fk && (
                        <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 8,
                          color: "rgba(167,139,250,0.8)", border: "1px solid rgba(167,139,250,0.3)",
                          fontFamily: "monospace", maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                          title={`FK → ${col.fk}`}>
                          → {col.fk}
                        </span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ── Step 2: Table selection ───────────────────────────────────────────────────
function StepTableSelect({ tables, allTables, selected, setSelected, keywords, onGenerate, onBack }) {
  const [tableSearch, setTableSearch] = useState("");
  const [preview, setPreview] = useState(null);

  const toggleTable = (fullName) => {
    setSelected(s => s.includes(fullName) ? s.filter(n => n !== fullName) : [...s, fullName]);
  };

  const searchResults = tableSearch.length >= 2
    ? allTables.filter(t =>
        t.full_name.toLowerCase().includes(tableSearch.toLowerCase()) &&
        !tables.find(st => st.full_name === t.full_name)
      ).slice(0, 8)
    : [];

  return (
    <>
    {preview && <TablePreviewModal table={preview} onClose={() => setPreview(null)} />}
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: 11, color: S.textMain, fontWeight: 600 }}>
          {tables.length} Tabellen im Kontext
        </span>
        <div style={{ display: "flex", gap: 6 }}>
          {keywords.map(kw => (
            <span key={kw} style={{ fontSize: 9, padding: "1px 6px", borderRadius: 10,
              backgroundColor: "rgba(252,228,153,0.1)", color: "rgba(252,228,153,0.6)",
              border: "1px solid rgba(252,228,153,0.2)" }}>
              {kw}
            </span>
          ))}
        </div>
      </div>

      {/* Suggested tables */}
      <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 220, overflowY: "auto" }}>
        {tables.map(t => {
          const isSelected = selected.includes(t.full_name);
          const ml = MATCH_LABELS[t.match_type] || MATCH_LABELS.fallback;
          return (
            <div key={t.full_name} onClick={() => toggleTable(t.full_name)}
              style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 8px",
                borderRadius: 5, cursor: "pointer",
                backgroundColor: isSelected ? "rgba(252,228,153,0.05)" : S.bgEl,
                border: `1px solid ${isSelected ? "rgba(252,228,153,0.25)" : S.border}` }}>
              <div style={{ width: 13, height: 13, borderRadius: 3, flexShrink: 0,
                border: `2px solid ${isSelected ? ACCENT : S.border}`,
                backgroundColor: isSelected ? ACCENT : "transparent",
                display: "flex", alignItems: "center", justifyContent: "center" }}>
                {isSelected && <Check size={8} color="#111" strokeWidth={3} />}
              </div>
              <span style={{ fontSize: 11, color: isSelected ? S.textBright : S.textMain, flex: 1, fontFamily: "monospace" }}>
                {t.full_name}
              </span>
              <span style={{ fontSize: 9, color: S.textDim }}>{t.col_count}S</span>
              <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 8,
                color: ml.color, border: `1px solid ${ml.color}`, opacity: 0.8 }}>
                {ml.label}
              </span>
              {t.columns && (
                <button onClick={e => { e.stopPropagation(); setPreview(t); }}
                  style={{ background: "none", border: "none", cursor: "pointer", color: S.textDim,
                    display: "flex", padding: "1px 2px", borderRadius: 3 }}
                  title="Spalten anzeigen">
                  <Eye size={11} />
                </button>
              )}
            </div>
          );
        })}
      </div>

      {/* Add more tables */}
      <div>
        <input value={tableSearch} onChange={e => setTableSearch(e.target.value)}
          placeholder="Weitere Tabelle suchen…"
          style={{ ...iS, fontSize: 10, padding: "4px 8px" }} />
        {searchResults.length > 0 && (
          <div style={{ marginTop: 4, display: "flex", flexDirection: "column", gap: 2 }}>
            {searchResults.map(t => (
              <div key={t.full_name} onClick={() => { toggleTable(t.full_name); setTableSearch(""); }}
                style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 8px",
                  borderRadius: 4, cursor: "pointer", backgroundColor: S.bgEl,
                  border: `1px solid ${S.border}` }}>
                <Plus size={10} style={{ color: S.textDim }} />
                <span style={{ fontSize: 10, color: S.textMain, fontFamily: "monospace" }}>{t.full_name}</span>
                <span style={{ fontSize: 9, color: S.textDim, marginLeft: "auto" }}>{t.col_count} Sp.</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={{ fontSize: 9, color: S.textDim }}>
        {selected.length} von {tables.length} Tabellen ausgewählt
      </div>

    </div>
    </>
  );
}

// ── Step 3: Suggestions ───────────────────────────────────────────────────────
function StepSuggestions({ suggestions, selected, setSelected, names, setNames, sqls, setSqls, expanded, setExpanded }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
        <span style={{ fontSize: 11, color: S.textMain, fontWeight: 600 }}>{suggestions.length} Vorschläge</span>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => setSelected(Object.fromEntries(suggestions.map((_, i) => [i, true])))}
            style={{ fontSize: 10, color: ACCENT, background: "none", border: "none", cursor: "pointer" }}>Alle</button>
          <button onClick={() => setSelected(Object.fromEntries(suggestions.map((_, i) => [i, false])))}
            style={{ fontSize: 10, color: S.textDim, background: "none", border: "none", cursor: "pointer" }}>Keine</button>
        </div>
      </div>
      {suggestions.map((ds, i) => (
        <div key={i} style={{ borderRadius: 6, border: `1px solid ${selected[i] ? "rgba(252,228,153,0.3)" : S.border}`,
          backgroundColor: selected[i] ? "rgba(252,228,153,0.04)" : S.bgEl, overflow: "hidden" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 10px" }}>
            <div onClick={() => setSelected(s => ({ ...s, [i]: !s[i] }))}
              style={{ width: 13, height: 13, borderRadius: 3, flexShrink: 0, cursor: "pointer",
                border: `2px solid ${selected[i] ? ACCENT : S.border}`,
                backgroundColor: selected[i] ? ACCENT : "transparent",
                display: "flex", alignItems: "center", justifyContent: "center" }}>
              {selected[i] && <Check size={8} color="#111" strokeWidth={3} />}
            </div>
            <input value={names[i] ?? ds.name} onChange={e => setNames(n => ({ ...n, [i]: e.target.value }))}
              style={{ ...iS, fontWeight: 700, fontSize: 12, flex: 1, padding: "3px 6px",
                color: selected[i] ? ACCENT : S.textMain }} />
            <button onClick={() => setExpanded(e => ({ ...e, [i]: !e[i] }))}
              style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", display: "flex" }}>
              {expanded[i] ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
            </button>
          </div>
          {ds.purpose && (
            <div style={{ padding: "0 10px 5px 31px", fontSize: 10, color: S.textDim }}>{ds.purpose}</div>
          )}
          {expanded[i] && (
            <div style={{ padding: "0 10px 10px" }}>
              <label style={{ fontSize: 9, color: S.textDim, textTransform: "uppercase", display: "block", marginBottom: 3 }}>SQL</label>
              <textarea value={sqls[i] ?? ds.sql} onChange={e => setSqls(s => ({ ...s, [i]: e.target.value }))}
                rows={5} style={{ ...iS, fontFamily: "monospace", fontSize: 10, lineHeight: 1.6, resize: "vertical" }} />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function AiDatasetWizard({ connection, projectId, onDone, onClose }) {
  const [step, setStep]               = useState(0);  // 0=desc, 1=tables, 2=suggestions
  const [description, setDescription] = useState("");

  // Step 1 state
  const [analyzing, setAnalyzing]     = useState(false);
  const [tableInfo, setTableInfo]     = useState([]);   // filtered tables from backend
  const [allTables, setAllTables]     = useState([]);   // full schema for search
  const [selectedTables, setSelectedTables] = useState([]);  // full_names
  const [keywords, setKeywords]       = useState([]);

  // Step 2 state
  const [generating, setGenerating]   = useState(false);
  const [tokenCount, setTokenCount]   = useState(0);
  const [suggestions, setSuggestions] = useState(null);
  const [selSug, setSelSug]           = useState({});
  const [names, setNames]             = useState({});
  const [sqls, setSqls]               = useState({});
  const [expanded, setExpanded]       = useState({});

  // Step 3 state
  const [creating, setCreating]       = useState(false);
  const [results, setResults]         = useState(null);
  const [error, setError]             = useState(null);

  const handleAnalyze = async () => {
    if (!description.trim()) return;
    setAnalyzing(true); setError(null);
    try {
      const data = await getTableContext(connection.id, description);
      if (data.error) { setError(data.error); return; }
      setTableInfo(data.tables || []);
      setKeywords(data.keywords || []);
      setSelectedTables([]);

      // Load all tables for the search box
      const cached = connection.schema_cache_table_count
        ? null  // don't re-fetch if we just need names
        : null;
      // We'll search within tableInfo for now; full list via separate call if needed
      setAllTables(data.all_tables || data.tables || []);
      setStep(1);
    } catch (e) {
      setError(e.message);
    } finally {
      setAnalyzing(false);
    }
  };

  const handleGenerate = async () => {
    setGenerating(true); setError(null); setSuggestions(null); setTokenCount(0);
    setStep(2); // advance immediately so user sees generation progress on step 3
    try {
      const { suggestions: s } = await suggestDatasets(
        connection.id, description, selectedTables,
        () => setTokenCount(n => n + 1),
      );
      if (!s?.length) { setError("KI hat keine Vorschläge generiert. Beschreibung oder Tabellenauswahl anpassen?"); return; }
      setSuggestions(s);
      const sel = {}; const n = {}; const sq = {};
      s.forEach((ds, i) => { sel[i] = true; n[i] = ds.name; sq[i] = ds.sql; });
      setSelSug(sel); setNames(n); setSqls(sq); setExpanded({});
    } catch (e) {
      setError(e.message);
      setStep(1); // back to table selection on error
    } finally {
      setGenerating(false);
    }
  };

  const handleCreate = async () => {
    const toCreate = suggestions
      .map((ds, i) => ({ name: names[i] || ds.name, sql: sqls[i] || ds.sql }))
      .filter((_, i) => selSug[i]);
    if (!toCreate.length) return;
    setCreating(true);
    const res = [];
    for (const ds of toCreate) {
      try {
        await api.post(`/api/connections/${connection.id}/import`, {
          dataset_name: ds.name, sql: ds.sql, project_id: projectId,
        });
        res.push({ name: ds.name, ok: true });
      } catch (e) {
        res.push({ name: ds.name, ok: false, error: e.response?.data?.detail || e.message });
      }
    }
    setResults(res);
    setCreating(false);
    if (res.every(r => r.ok)) setTimeout(() => { onDone?.(); onClose(); }, 1500);
  };

  const selectedCount = suggestions ? Object.values(selSug).filter(Boolean).length : 0;

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 200, backgroundColor: "rgba(0,0,0,0.65)",
      display: "flex", alignItems: "center", justifyContent: "center" }} onClick={onClose}>
      <div style={{ width: 600, maxHeight: "88vh", display: "flex", flexDirection: "column",
        backgroundColor: S.bgCard, borderRadius: 8,
        border: "1px solid rgba(252,228,153,0.25)",
        boxShadow: "0 20px 60px rgba(0,0,0,0.6)", overflow: "hidden" }}
        onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "12px 16px",
          borderBottom: `1px solid ${S.border}`, backgroundColor: "rgba(252,228,153,0.04)" }}>
          <Sparkles size={14} style={{ color: ACCENT }} />
          <div style={{ flex: 1 }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: ACCENT }}>KI-Dataset-Assistent</span>
            <span style={{ fontSize: 11, color: S.textDim, marginLeft: 8 }}>{connection.name}</span>
          </div>
          {/* Step indicator */}
          <div style={{ display: "flex", gap: 4, marginRight: 8 }}>
            {["Beschreibung", "Tabellen", "Vorschläge"].map((label, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 3 }}>
                <div style={{ width: 18, height: 18, borderRadius: "50%", fontSize: 9, fontWeight: 700,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  backgroundColor: step === i ? ACCENT : step > i ? "rgba(252,228,153,0.2)" : S.bgEl,
                  color: step === i ? "#111" : step > i ? ACCENT : S.textDim,
                  border: `1px solid ${step >= i ? "rgba(252,228,153,0.4)" : S.border}` }}>
                  {step > i ? "✓" : i + 1}
                </div>
                {i < 2 && <div style={{ width: 12, height: 1, backgroundColor: step > i ? "rgba(252,228,153,0.3)" : S.border }} />}
              </div>
            ))}
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer" }}>
            <X size={13} />
          </button>
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflowY: "auto", padding: 16 }}>
          {error && (
            <div style={{ padding: "8px 10px", borderRadius: 4, marginBottom: 12,
              backgroundColor: "rgba(224,112,112,0.08)", border: "1px solid rgba(224,112,112,0.25)",
              fontSize: 11, color: "#e07070" }}>✗ {error}</div>
          )}

          {step === 0 && (
            <StepDescription description={description} setDescription={setDescription}
              onAnalyze={handleAnalyze} loading={analyzing} />
          )}
          {step === 1 && (
            <StepTableSelect tables={tableInfo} allTables={allTables}
              selected={selectedTables} setSelected={setSelectedTables}
              keywords={keywords} onGenerate={handleGenerate}
              onBack={() => setStep(0)} />
          )}
          {step === 2 && generating && (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center",
              justifyContent: "center", gap: 16, padding: "40px 0" }}>
              <Loader2 size={28} className="animate-spin" style={{ color: ACCENT, opacity: 0.7 }} />
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: 12, color: S.textMain, fontWeight: 600 }}>KI analysiert und generiert SQL…</div>
                {tokenCount > 0 && (
                  <div style={{ fontSize: 10, color: S.textDim, marginTop: 4 }}>{tokenCount} Tokens empfangen</div>
                )}
              </div>
              <div style={{ fontSize: 10, color: S.textDim, opacity: 0.6 }}>
                {selectedTables.length} Tabellen im Kontext · {description.slice(0, 60)}{description.length > 60 ? "…" : ""}
              </div>
            </div>
          )}
          {step === 2 && !generating && suggestions && !results && (
            <StepSuggestions suggestions={suggestions}
              selected={selSug} setSelected={setSelSug}
              names={names} setNames={setNames}
              sqls={sqls} setSqls={setSqls}
              expanded={expanded} setExpanded={setExpanded} />
          )}
          {results && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {results.map((r, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 10px",
                  borderRadius: 5,
                  backgroundColor: r.ok ? "rgba(110,231,183,0.06)" : "rgba(224,112,112,0.06)",
                  border: `1px solid ${r.ok ? "rgba(110,231,183,0.2)" : "rgba(224,112,112,0.2)"}` }}>
                  <span style={{ color: r.ok ? "#6ee7b7" : "#e07070" }}>{r.ok ? "✓" : "✗"}</span>
                  <span style={{ fontSize: 11, color: S.textBright, flex: 1, fontFamily: "monospace" }}>{r.name}</span>
                  {!r.ok && <span style={{ fontSize: 10, color: "#e07070" }}>{r.error}</span>}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ padding: "10px 16px", borderTop: `1px solid ${S.border}`,
          display: "flex", gap: 8, justifyContent: "flex-end" }}>
          {results ? (
            <button onClick={onClose} style={{ padding: "6px 12px", borderRadius: 4,
              border: `1px solid ${S.border}`, background: "none", color: S.textDim, fontSize: 11, cursor: "pointer" }}>
              Schließen
            </button>
          ) : (
            <>
              <button onClick={onClose} style={{ padding: "6px 12px", borderRadius: 4,
                border: `1px solid ${S.border}`, background: "none", color: S.textDim, fontSize: 11, cursor: "pointer" }}>
                Abbrechen
              </button>
              {step > 0 && !generating && (
                <button onClick={() => { setStep(s => s - 1); setSuggestions(null); setError(null); }}
                  style={{ display: "flex", alignItems: "center", gap: 4, padding: "6px 12px", borderRadius: 4,
                    border: `1px solid ${S.border}`, background: "none", color: S.textDim, fontSize: 11, cursor: "pointer" }}>
                  <ArrowLeft size={10} /> Zurück
                </button>
              )}
              {step === 1 && (
                <button onClick={handleGenerate}
                  disabled={selectedTables.length === 0}
                  style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 14px", borderRadius: 4,
                    border: "1px solid rgba(252,228,153,0.3)", backgroundColor: "rgba(252,228,153,0.08)",
                    color: ACCENT, fontSize: 11, fontWeight: 600,
                    cursor: selectedTables.length === 0 ? "not-allowed" : "pointer",
                    opacity: selectedTables.length === 0 ? 0.6 : 1 }}>
                  <Sparkles size={11} />
                  SQL generieren ({selectedTables.length} Tabellen)
                </button>
              )}
              {step === 2 && !generating && !results && (
                <>
                  <button onClick={() => { setSuggestions(null); setStep(1); setError(null); }}
                    style={{ padding: "6px 12px", borderRadius: 4, border: `1px solid ${S.border}`,
                      background: "none", color: S.textDim, fontSize: 11, cursor: "pointer" }}>
                    Neu generieren
                  </button>
                  <button onClick={handleCreate} disabled={creating || selectedCount === 0}
                    style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 14px", borderRadius: 4,
                      border: "none", backgroundColor: selectedCount > 0 ? ACCENT : S.bgEl,
                      color: selectedCount > 0 ? "#111" : S.textDim,
                      fontSize: 11, fontWeight: 700,
                      cursor: creating || selectedCount === 0 ? "not-allowed" : "pointer",
                      opacity: creating ? 0.7 : 1 }}>
                    {creating ? <Loader2 size={11} className="animate-spin" /> : <Plus size={11} />}
                    {creating ? "Erstelle…" : `${selectedCount} Dataset${selectedCount !== 1 ? "s" : ""} anlegen`}
                  </button>
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
