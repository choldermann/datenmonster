import { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { Loader2, X, ChevronRight, ChevronLeft, Sparkles } from "lucide-react";
import api from "../../api/client";
import { S } from "../dashboard/constants";

export default function SmartMappingModal({ projectId, connections, onClose, onApply }) {
  const [step, setStep] = useState(1); // 1=Eingabe, 2=Vorschau
  const [loading, setLoading] = useState(false);
  const [presets, setPresets] = useState([]);
  const [selectedPreset, setSelectedPreset] = useState(null);
  const [query, setQuery] = useState("");
  const [selectedConn, setSelectedConn] = useState(connections?.[0]?.id || null);
  const [suggestion, setSuggestion] = useState(null);
  const [selectedTables, setSelectedTables] = useState(new Set());
  const [hasAiKey, setHasAiKey] = useState(false);

  useEffect(() => {
    api.get("/api/smart-mapping/presets").then(({ data }) => setPresets(data)).catch(() => {});
    api.get("/api/settings/ai").then(({ data }) => setHasAiKey(!!data?.claude_api_key && data.claude_api_key !== "••••••••")).catch(() => {});
  }, []);

  const handleSuggest = async () => {
    setLoading(true);
    try {
      const { data } = await api.post("/api/smart-mapping/suggest", {
        query: query || selectedPreset || "",
        preset: selectedPreset,
        connection_id: selectedConn ? parseInt(selectedConn) : null,
        project_id: projectId,
        use_ai: hasAiKey && !!query && !selectedPreset,
      });
      setSuggestion(data);
      setSelectedTables(new Set(data.tables.map(t => t.key)));
      setStep(2);
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    } finally { setLoading(false); }
  };

  const handleApply = () => {
    if (!suggestion) return;
    const tables = suggestion.tables.filter(t => selectedTables.has(t.key));
    const joins = suggestion.joins.filter(j =>
      selectedTables.has(j.from_table) && selectedTables.has(j.to_table)
    );
    onApply({ tables, joins });
    onClose();
  };

  const toggleTable = (key) => {
    setSelectedTables(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const canProceed = selectedPreset || query.trim().length > 2;

  return createPortal(
    <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 9999, backgroundColor: "rgba(0,0,0,0.75)", display: "flex", alignItems: "center", justifyContent: "center", padding: "1rem" }}>
      <div onClick={e => e.stopPropagation()} style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`, borderRadius: 12, width: "100%", maxWidth: 560, boxShadow: "0 24px 60px rgba(0,0,0,0.7)", display: "flex", flexDirection: "column", maxHeight: "85vh" }}>

        {/* Header */}
        <div style={{ padding: "16px 20px", borderBottom: `1px solid ${S.border}`, display: "flex", alignItems: "center", gap: 10 }}>
          <Sparkles size={16} style={{ color: S.accent }} />
          <p style={{ fontSize: 15, fontWeight: 700, color: S.textBright, margin: 0, flex: 1 }}>Smart Mapping</p>
          <span style={{ fontSize: 11, color: S.textDim }}>Schritt {step} / 2</span>
          <button onClick={onClose} style={{ color: S.textDim, background: "none", border: "none", cursor: "pointer" }}><X size={16} /></button>
        </div>

        {/* Schritt 1 – Eingabe */}
        {step === 1 && (
          <div style={{ padding: "20px", display: "flex", flexDirection: "column", gap: 16, overflowY: "auto" }}>

            {/* Presets */}
            <div>
              <p style={{ fontSize: 11, fontWeight: 600, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.05em", margin: "0 0 10px" }}>JTL Presets</p>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {presets.map(p => (
                  <button key={p.key} onClick={() => { setSelectedPreset(selectedPreset === p.key ? null : p.key); setQuery(""); }}
                    style={{ fontSize: 12, padding: "6px 14px", borderRadius: 20, cursor: "pointer",
                      border: `1px solid ${selectedPreset === p.key ? S.accent : S.border}`,
                      backgroundColor: selectedPreset === p.key ? "rgba(252,228,153,0.12)" : "transparent",
                      color: selectedPreset === p.key ? S.accent : S.textDim,
                    }}>
                    {p.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Freitext */}
            <div>
              <p style={{ fontSize: 11, fontWeight: 600, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.05em", margin: "0 0 8px" }}>
                {hasAiKey ? "✨ KI-Freitext" : "Freitext (Keyword-Matching)"}
              </p>
              <textarea value={query} onChange={e => { setQuery(e.target.value); setSelectedPreset(null); }}
                placeholder={hasAiKey ? "z.B. Alle offenen Rechnungen mit Kundendaten der letzten 30 Tage" : "z.B. Rechnungen Kunden Zahlungen"}
                rows={3}
                style={{ width: "100%", boxSizing: "border-box", backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 6, color: S.textMain, fontSize: 13, padding: "10px 12px", outline: "none", resize: "vertical", fontFamily: "inherit" }} />
              {!hasAiKey && (
                <p style={{ fontSize: 10, color: S.textDim, marginTop: 4 }}>
                  Kein Claude API-Key → Keyword-Matching. <span style={{ color: S.accent, cursor: "pointer" }} onClick={() => {}}>API-Key konfigurieren →</span>
                </p>
              )}
            </div>

            {/* Verbindung */}
            {connections?.length > 0 && (
              <div>
                <p style={{ fontSize: 11, fontWeight: 600, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.05em", margin: "0 0 8px" }}>Datenbankverbindung</p>
                <select value={selectedConn || ""} onChange={e => setSelectedConn(e.target.value)}
                  style={{ backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, color: S.textMain, fontSize: 12, padding: "7px 10px", width: "100%" }}>
                  <option value="">Keine (nur vorhandene Datasets)</option>
                  {connections.map(c => <option key={c.id} value={c.id}>{c.name} ({c.db_type})</option>)}
                </select>
              </div>
            )}

            {/* Footer */}
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", paddingTop: 4 }}>
              <button onClick={onClose} style={{ fontSize: 12, padding: "8px 16px", borderRadius: 6, cursor: "pointer", background: "transparent", border: `1px solid ${S.border}`, color: S.textDim }}>Abbrechen</button>
              <button onClick={handleSuggest} disabled={!canProceed || loading}
                style={{ fontSize: 12, fontWeight: 600, padding: "8px 20px", borderRadius: 6, cursor: canProceed ? "pointer" : "not-allowed",
                  background: canProceed ? "rgba(252,228,153,0.15)" : "transparent",
                  border: `1px solid ${canProceed ? "rgba(252,228,153,0.4)" : S.border}`,
                  color: canProceed ? S.accent : S.textDim,
                  display: "flex", alignItems: "center", gap: 6, opacity: loading ? 0.7 : 1 }}>
                {loading ? <Loader2 size={13} className="animate-spin" /> : <ChevronRight size={13} />}
                {loading ? "Analysiere..." : "Weiter"}
              </button>
            </div>
          </div>
        )}

        {/* Schritt 2 – Vorschau */}
        {step === 2 && suggestion && (
          <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
            <div style={{ padding: "12px 20px", borderBottom: `1px solid ${S.border}`, fontSize: 12, color: S.textDim }}>
              {suggestion.message}
              {suggestion.used_ai && <span style={{ marginLeft: 8, color: S.accent, fontWeight: 600 }}>✨ KI</span>}
            </div>

            <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px", display: "flex", flexDirection: "column", gap: 8 }}>
              <p style={{ fontSize: 11, fontWeight: 600, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.05em", margin: "0 0 4px" }}>
                Erkannte Tabellen ({suggestion.tables.length})
              </p>

              {suggestion.tables.length === 0 && (
                <p style={{ fontSize: 12, color: S.textDim }}>Keine passenden Tabellen gefunden. Versuche andere Keywords.</p>
              )}

              {suggestion.tables.map(t => (
                <div key={t.key} onClick={() => toggleTable(t.key)}
                  style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", borderRadius: 8, cursor: "pointer",
                    border: `1px solid ${selectedTables.has(t.key) ? "rgba(110,231,183,0.3)" : S.border}`,
                    backgroundColor: selectedTables.has(t.key) ? "rgba(110,231,183,0.05)" : "transparent",
                  }}>
                  <div style={{ width: 16, height: 16, borderRadius: 3, border: `2px solid ${selectedTables.has(t.key) ? "#6ee7b7" : S.border}`, backgroundColor: selectedTables.has(t.key) ? "#6ee7b7" : "transparent", flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
                    {selectedTables.has(t.key) && <span style={{ color: "#111", fontSize: 10, fontWeight: 700 }}>✓</span>}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{ fontSize: 13, fontWeight: 600, color: S.textBright, margin: 0, fontFamily: "monospace" }}>{t.name}</p>
                    <p style={{ fontSize: 10, color: S.textDim, margin: "2px 0 0" }}>{t.schema} · {t.columns.length} Spalten</p>
                  </div>
                  {t.already_exists ? (
                    <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 3, backgroundColor: "rgba(110,231,183,0.1)", color: "#6ee7b7", border: "1px solid rgba(110,231,183,0.2)", whiteSpace: "nowrap" }}>✓ vorhanden</span>
                  ) : (
                    <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 3, backgroundColor: "rgba(147,197,253,0.1)", color: "#93c5fd", border: "1px solid rgba(147,197,253,0.2)", whiteSpace: "nowrap" }}>→ wird importiert</span>
                  )}
                </div>
              ))}

              {suggestion.joins.length > 0 && (
                <>
                  <p style={{ fontSize: 11, fontWeight: 600, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.05em", margin: "12px 0 4px" }}>
                    Erkannte JOINs ({suggestion.joins.filter(j => selectedTables.has(j.from_table) && selectedTables.has(j.to_table)).length})
                  </p>
                  {suggestion.joins.filter(j => selectedTables.has(j.from_table) && selectedTables.has(j.to_table)).map((j, i) => (
                    <div key={i} style={{ fontSize: 11, color: S.textMain, fontFamily: "monospace", padding: "6px 14px", borderRadius: 6, backgroundColor: "rgba(255,255,255,0.02)", border: `1px solid ${S.border}` }}>
                      <span style={{ color: "#6ee7b7" }}>{j.from_table}</span>
                      <span style={{ color: S.textDim }}>.{j.from_col} → </span>
                      <span style={{ color: "#6ee7b7" }}>{j.to_table}</span>
                      <span style={{ color: S.textDim }}>.{j.to_col}</span>
                    </div>
                  ))}
                </>
              )}
            </div>

            <div style={{ padding: "14px 20px", borderTop: `1px solid ${S.border}`, display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button onClick={() => setStep(1)} style={{ fontSize: 12, padding: "8px 14px", borderRadius: 6, cursor: "pointer", background: "transparent", border: `1px solid ${S.border}`, color: S.textDim, display: "flex", alignItems: "center", gap: 6 }}>
                <ChevronLeft size={13} /> Zurück
              </button>
              <button onClick={handleApply} disabled={selectedTables.size === 0}
                style={{ fontSize: 12, fontWeight: 600, padding: "8px 20px", borderRadius: 6, cursor: selectedTables.size > 0 ? "pointer" : "not-allowed",
                  background: "rgba(110,231,183,0.15)", border: "1px solid rgba(110,231,183,0.4)", color: "#6ee7b7",
                  opacity: selectedTables.size === 0 ? 0.5 : 1 }}>
                {selectedTables.size} Tabelle{selectedTables.size !== 1 ? "n" : ""} ins Mapping übernehmen
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  , document.body);
}
