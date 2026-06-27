import { useState } from "react";
import { X, Sparkles, Loader2, Check, Plus, ChevronDown, ChevronUp } from "lucide-react";
import api from "../api/client";
import { suggestDatasets } from "../services/aiService";
import { S } from "./dashboard/constants";


const ACCENT = "#fce499";

export default function AiDatasetWizard({ connection, projectId, onDone, onClose }) {
  const [description, setDescription] = useState("");
  const [loading, setLoading]         = useState(false);
  const [suggestions, setSuggestions] = useState(null);
  const [selected, setSelected]       = useState({});   // index → true/false
  const [names, setNames]             = useState({});   // index → edited name
  const [sqls, setSqls]               = useState({});   // index → edited sql
  const [expanded, setExpanded]       = useState({});   // index → sql expanded
  const [creating, setCreating]       = useState(false);
  const [results, setResults]         = useState(null);
  const [error, setError]             = useState(null);
  const [tokenCount, setTokenCount]   = useState(0);

  const iS = {
    backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4,
    color: S.textBright, fontSize: 11, padding: "6px 10px", outline: "none", width: "100%",
    boxSizing: "border-box",
  };

  const handleGenerate = async () => {
    if (!description.trim()) return;
    setLoading(true); setError(null); setSuggestions(null); setResults(null); setTokenCount(0);
    try {
      const { suggestions: s } = await suggestDatasets(
        connection.id, description,
        () => setTokenCount(n => n + 1),
      );
      if (!s?.length) { setError("KI hat keine Vorschläge generiert. Beschreibung präzisieren?"); return; }
      setSuggestions(s);
      const sel = {}; const n = {}; const sq = {};
      s.forEach((ds, i) => { sel[i] = true; n[i] = ds.name; sq[i] = ds.sql; });
      setSelected(sel); setNames(n); setSqls(sq); setExpanded({});
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    const toCreate = suggestions
      .map((ds, i) => ({ ...ds, name: names[i] || ds.name, sql: sqls[i] || ds.sql, idx: i }))
      .filter((_, i) => selected[i]);
    if (!toCreate.length) return;

    setCreating(true);
    const res = [];
    for (const ds of toCreate) {
      try {
        await api.post(`/api/connections/${connection.id}/import`, {
          dataset_name: ds.name,
          sql: ds.sql,
          project_id: projectId,
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

  const selectedCount = suggestions ? Object.values(selected).filter(Boolean).length : 0;

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 200, backgroundColor: "rgba(0,0,0,0.65)",
      display: "flex", alignItems: "center", justifyContent: "center",
    }} onClick={onClose}>
      <div style={{
        width: 580, maxHeight: "85vh", display: "flex", flexDirection: "column",
        backgroundColor: S.bgCard, borderRadius: 8,
        border: `1px solid rgba(252,228,153,0.25)`,
        boxShadow: "0 20px 60px rgba(0,0,0,0.6)", overflow: "hidden",
      }} onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "12px 16px", borderBottom: `1px solid ${S.border}`, backgroundColor: "rgba(252,228,153,0.04)" }}>
          <Sparkles size={14} style={{ color: ACCENT }} />
          <div style={{ flex: 1 }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: ACCENT }}>KI-Dataset-Assistent</span>
            <span style={{ fontSize: 11, color: S.textDim, marginLeft: 8 }}>{connection.name}</span>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer" }}>
            <X size={13} />
          </button>
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>

          {/* Beschreibung */}
          <div>
            <label style={{ fontSize: 10, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", display: "block", marginBottom: 4 }}>
              Was benötigst du?
            </label>
            <textarea
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder={'z.B. "Rechnungen mit Kundendaten der letzten 3 Monate, dazu offene Bestellungen"'}
              rows={3}
              style={{ ...iS, resize: "vertical", fontFamily: "inherit", lineHeight: 1.5 }}
              onKeyDown={e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) handleGenerate(); }}
            />
            <span style={{ fontSize: 9, color: S.textDim }}>Ctrl+Enter zum Generieren</span>
          </div>

          {/* Fehler */}
          {error && (
            <div style={{ padding: "8px 10px", borderRadius: 4, backgroundColor: "rgba(224,112,112,0.08)", border: "1px solid rgba(224,112,112,0.25)", fontSize: 11, color: "#e07070" }}>
              ✗ {error}
            </div>
          )}

          {/* Lade-Zustand */}
          {loading && (
            <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "16px", justifyContent: "center", color: S.textDim, fontSize: 11 }}>
              <Loader2 size={14} style={{ color: ACCENT, animation: "spin 1s linear infinite" }} />
              <span style={{ color: ACCENT }}>
                KI analysiert Schema und erstellt Vorschläge…
                {tokenCount > 0 && <span style={{ opacity: 0.6, marginLeft: 6 }}>({tokenCount} Tokens)</span>}
              </span>
            </div>
          )}

          {/* Vorschläge */}
          {suggestions && !results && (
            <div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
                <span style={{ fontSize: 11, color: S.textMain, fontWeight: 600 }}>
                  {suggestions.length} Vorschläge
                </span>
                <div style={{ display: "flex", gap: 8 }}>
                  <button onClick={() => setSelected(Object.fromEntries(suggestions.map((_, i) => [i, true])))}
                    style={{ fontSize: 10, color: ACCENT, background: "none", border: "none", cursor: "pointer" }}>Alle</button>
                  <button onClick={() => setSelected(Object.fromEntries(suggestions.map((_, i) => [i, false])))}
                    style={{ fontSize: 10, color: S.textDim, background: "none", border: "none", cursor: "pointer" }}>Keine</button>
                </div>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {suggestions.map((ds, i) => (
                  <div key={i} style={{
                    borderRadius: 6, border: `1px solid ${selected[i] ? "rgba(252,228,153,0.3)" : S.border}`,
                    backgroundColor: selected[i] ? "rgba(252,228,153,0.04)" : S.bgEl,
                    overflow: "hidden",
                  }}>
                    {/* Kopfzeile */}
                    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px" }}>
                      <div onClick={() => setSelected(s => ({ ...s, [i]: !s[i] }))}
                        style={{ width: 14, height: 14, borderRadius: 3, flexShrink: 0, cursor: "pointer",
                          border: `2px solid ${selected[i] ? ACCENT : S.border}`,
                          backgroundColor: selected[i] ? ACCENT : "transparent",
                          display: "flex", alignItems: "center", justifyContent: "center" }}>
                        {selected[i] && <Check size={9} color="#111" strokeWidth={3} />}
                      </div>
                      <input
                        value={names[i] ?? ds.name}
                        onChange={e => setNames(n => ({ ...n, [i]: e.target.value }))}
                        style={{ ...iS, fontWeight: 700, fontSize: 12, flex: 1, padding: "3px 6px", color: selected[i] ? ACCENT : S.textMain }}
                      />
                      <button onClick={() => setExpanded(e => ({ ...e, [i]: !e[i] }))}
                        style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 2, display: "flex" }}>
                        {expanded[i] ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                      </button>
                    </div>

                    {/* Zweck */}
                    {ds.purpose && (
                      <div style={{ padding: "0 10px 6px 32px", fontSize: 10, color: S.textDim, lineHeight: 1.4 }}>
                        {ds.purpose}
                      </div>
                    )}

                    {/* SQL (ausklappbar) */}
                    {expanded[i] && (
                      <div style={{ padding: "0 10px 10px 10px" }}>
                        <label style={{ fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", display: "block", marginBottom: 3 }}>SQL</label>
                        <textarea
                          value={sqls[i] ?? ds.sql}
                          onChange={e => setSqls(s => ({ ...s, [i]: e.target.value }))}
                          rows={5}
                          style={{ ...iS, fontFamily: "monospace", fontSize: 10, lineHeight: 1.6, resize: "vertical" }}
                        />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Ergebnis */}
          {results && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {results.map((r, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 10px", borderRadius: 5,
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
        <div style={{ padding: "10px 16px", borderTop: `1px solid ${S.border}`, display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button onClick={onClose}
            style={{ padding: "6px 12px", borderRadius: 4, border: `1px solid ${S.border}`, background: "none", color: S.textDim, fontSize: 11, cursor: "pointer" }}>
            {results ? "Schließen" : "Abbrechen"}
          </button>
          {!suggestions && !results && (
            <button onClick={handleGenerate} disabled={loading || !description.trim()}
              style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 14px", borderRadius: 4,
                border: `1px solid rgba(252,228,153,0.3)`, backgroundColor: "rgba(252,228,153,0.08)",
                color: ACCENT, fontSize: 11, fontWeight: 600,
                cursor: loading || !description.trim() ? "not-allowed" : "pointer",
                opacity: loading || !description.trim() ? 0.6 : 1 }}>
              {loading ? <Loader2 size={11} style={{ animation: "spin 1s linear infinite" }} /> : <Sparkles size={11} />}
              {loading ? "Analysiere…" : "Vorschläge generieren"}
            </button>
          )}
          {suggestions && !results && (
            <>
              <button onClick={handleGenerate} disabled={loading}
                style={{ padding: "6px 12px", borderRadius: 4, border: `1px solid ${S.border}`, background: "none", color: S.textDim, fontSize: 11, cursor: "pointer" }}>
                Neu generieren
              </button>
              <button onClick={handleCreate} disabled={creating || selectedCount === 0}
                style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 14px", borderRadius: 4,
                  border: "none", backgroundColor: selectedCount > 0 ? ACCENT : S.bgEl,
                  color: selectedCount > 0 ? "#111" : S.textDim,
                  fontSize: 11, fontWeight: 700,
                  cursor: creating || selectedCount === 0 ? "not-allowed" : "pointer",
                  opacity: creating ? 0.7 : 1 }}>
                {creating ? <Loader2 size={11} style={{ animation: "spin 1s linear infinite" }} /> : <Plus size={11} />}
                {creating ? "Erstelle…" : `${selectedCount} Dataset${selectedCount !== 1 ? "s" : ""} anlegen`}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
