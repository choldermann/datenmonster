import { useState, useRef, useEffect } from "react";
import { X, Loader2, Check, Sparkles, Copy } from "lucide-react";
import { S } from "./constants";
import { getStatus } from "../../services/aiService";

const ACCENT = "#fce499";

function ThinkingDots() {
  const [dots, setDots] = useState(1);
  useEffect(() => {
    const t = setInterval(() => setDots(d => d >= 3 ? 1 : d + 1), 500);
    return () => clearInterval(t);
  }, []);
  return <span style={{ letterSpacing: 2 }}>{"•".repeat(dots)}<span style={{ opacity: 0 }}>{"•".repeat(3 - dots)}</span></span>;
}

/**
 * Universelles KI-Streaming-Modal.
 *
 * Props:
 *   title         - Modalüberschrift
 *   description   - Kurze Beschreibung was die KI tun soll (optional vorbefüllt)
 *   placeholder   - Platzhaltertext im Beschreibungsfeld
 *   onGenerate    - async (description, onToken) => string  — ruft den KI-Endpunkt auf
 *   onApply       - (result: string) => void                — Ergebnis übernehmen
 *   onClose       - () => void
 *   applyLabel    - Text für den Übernehmen-Button (Default: "Übernehmen")
 *   readOnly      - true = kein Beschreibungsfeld
 *   autoGenerate  - true = direkt beim Öffnen generieren (für Erklär-Modus)
 *   noApply       - true = kein Übernehmen-Button (nur Lesen)
 */
export default function AiStreamModal({
  title,
  description: initialDescription = "",
  placeholder = "Beschreibe was generiert werden soll...",
  onGenerate,
  onApply,
  onClose,
  applyLabel = "Übernehmen",
  readOnly = false,
  autoGenerate = false,
  noApply = false,
  warning = null,
}) {
  const [description, setDescription] = useState(initialDescription);
  const [result, setResult]           = useState("");
  const [streaming, setStreaming]     = useState(false);
  const [done, setDone]               = useState(false);
  const [error, setError]             = useState(null);
  const [copied, setCopied]           = useState(false);
  const [activeModel, setActiveModel] = useState(null);
  const resultRef = useRef(null);

  useEffect(() => {
    getStatus().then(s => setActiveModel(s.model)).catch(() => {});
    if (autoGenerate) handleGenerate();
  }, []);

  const handleGenerate = async () => {
    if (!onGenerate) return;
    setStreaming(true);
    setDone(false);
    setError(null);
    setResult("");
    try {
      await onGenerate(description, (token, full) => {
        setResult(full);
        if (resultRef.current) {
          resultRef.current.scrollTop = resultRef.current.scrollHeight;
        }
      });
      setDone(true);
    } catch (e) {
      setError(e.message);
    } finally {
      setStreaming(false);
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(result).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  const iS = {
    backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4,
    color: S.textBright, fontSize: 11, padding: "6px 10px", outline: "none",
    width: "100%", boxSizing: "border-box",
  };

  return (
    <div
      style={{ position: "fixed", inset: 0, zIndex: 200, backgroundColor: "rgba(0,0,0,0.65)", display: "flex", alignItems: "center", justifyContent: "center" }}
      onClick={onClose}
    >
      <div
        style={{ width: 520, maxHeight: "80vh", display: "flex", flexDirection: "column", backgroundColor: S.bgCard, borderRadius: 8, border: `1px solid rgba(252,228,153,0.25)`, boxShadow: "0 20px 60px rgba(0,0,0,0.6)", overflow: "hidden" }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "12px 16px", borderBottom: `1px solid ${S.border}`, backgroundColor: "rgba(252,228,153,0.04)" }}>
          <Sparkles size={14} style={{ color: ACCENT }} />
          <span style={{ fontSize: 13, fontWeight: 700, color: ACCENT }}>{title}</span>
          {activeModel && (
            <span style={{ fontSize: 9, color: S.textDim, marginLeft: 6,
              padding: "1px 6px", borderRadius: 8, border: `1px solid ${S.border}`,
              fontFamily: "monospace" }}>
              {activeModel}
            </span>
          )}
          <span style={{ flex: 1 }} />
          <button onClick={onClose} style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 2 }}>
            <X size={13} />
          </button>
        </div>

        {/* Fortschrittsbalken */}
        {streaming && (
          <div style={{ height: 2, backgroundColor: "rgba(252,228,153,0.12)", position: "relative", overflow: "hidden" }}>
            <div style={{
              position: "absolute", top: 0, left: 0, height: "100%",
              width: result ? "100%" : "60%",
              backgroundColor: ACCENT,
              transition: result ? "width 0.3s ease" : "none",
              animation: result ? "none" : "aiSweep 1.4s ease-in-out infinite",
            }} />
          </div>
        )}
        <style>{`
          @keyframes aiSweep {
            0%   { left: -60%; width: 60%; }
            100% { left: 100%; width: 60%; }
          }
        `}</style>

        <div style={{ flex: 1, overflowY: "auto", padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
          {warning && (
            <div style={{
              padding: "7px 10px", borderRadius: 4, fontSize: 11, lineHeight: 1.5,
              backgroundColor: "rgba(251,191,36,0.08)", border: "1px solid rgba(251,191,36,0.3)",
              color: "#fbbf24", display: "flex", gap: 7, alignItems: "flex-start",
            }}>
              <span style={{ marginTop: 1 }}>⚠</span>
              <span>{warning}</span>
            </div>
          )}
          {/* Beschreibungsfeld */}
          {!readOnly && (
            <div>
              <label style={{ fontSize: 10, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", display: "block", marginBottom: 4 }}>
                Beschreibung
              </label>
              <textarea
                value={description}
                onChange={e => setDescription(e.target.value)}
                placeholder={placeholder}
                rows={2}
                style={{ ...iS, resize: "vertical", fontFamily: "inherit", lineHeight: 1.5 }}
                onKeyDown={e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) handleGenerate(); }}
              />
              <span style={{ fontSize: 9, color: S.textDim }}>Ctrl+Enter zum Generieren</span>
            </div>
          )}

          {/* Ergebnis-Bereich */}
          {(result || streaming || error) && (
            <div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                <label style={{ fontSize: 10, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                  {streaming ? "Generiere..." : "Ergebnis"}
                </label>
                {result && !streaming && (
                  <button onClick={handleCopy}
                    style={{ background: "none", border: "none", color: copied ? "#6ee7b7" : S.textDim, cursor: "pointer", fontSize: 10, display: "flex", alignItems: "center", gap: 4 }}>
                    {copied ? <Check size={10} /> : <Copy size={10} />}
                    {copied ? "Kopiert" : "Kopieren"}
                  </button>
                )}
              </div>
              {error ? (
                <div style={{ padding: "8px 10px", borderRadius: 4, backgroundColor: "rgba(224,112,112,0.08)", border: "1px solid rgba(224,112,112,0.25)", fontSize: 11, color: "#e07070" }}>
                  ✗ {error}
                </div>
              ) : streaming && !result ? (
                <div style={{
                  backgroundColor: "rgba(0,0,0,0.25)", border: `1px solid ${S.border}`, borderRadius: 4,
                  padding: "16px 10px", display: "flex", alignItems: "center", justifyContent: "center",
                  gap: 10, color: S.textDim, fontSize: 11,
                }}>
                  <Loader2 size={13} style={{ color: ACCENT, animation: "spin 1s linear infinite" }} />
                  <span style={{ color: ACCENT }}>Modell denkt nach <ThinkingDots /></span>
                </div>
              ) : (
                <div
                  ref={resultRef}
                  style={{
                    backgroundColor: "rgba(0,0,0,0.35)", border: `1px solid ${S.border}`, borderRadius: 4,
                    padding: "8px 10px", fontFamily: "monospace", fontSize: 11, color: "#e2e8f0",
                    whiteSpace: "pre-wrap", wordBreak: "break-word", lineHeight: 1.6,
                    maxHeight: 300, overflowY: "auto",
                    borderLeft: streaming ? `2px solid ${ACCENT}` : `1px solid ${S.border}`,
                  }}
                >
                  {result}
                  {streaming && <span style={{ color: ACCENT }}>▌</span>}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ padding: "10px 16px", borderTop: `1px solid ${S.border}`, display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button onClick={onClose}
            style={{ padding: "6px 12px", borderRadius: 4, border: `1px solid ${S.border}`, background: "none", color: S.textDim, fontSize: 11, cursor: "pointer" }}>
            Schließen
          </button>
          {!readOnly && (
            <button onClick={handleGenerate} disabled={streaming || (!readOnly && !description.trim())}
              style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 14px", borderRadius: 4, border: `1px solid rgba(252,228,153,0.3)`, backgroundColor: "rgba(252,228,153,0.08)", color: ACCENT, fontSize: 11, fontWeight: 600, cursor: streaming ? "not-allowed" : "pointer", opacity: streaming ? 0.6 : 1 }}>
              {streaming ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} />}
              {streaming ? "Generiere..." : "Generieren"}
            </button>
          )}
          {!noApply && onApply && done && result && (
            <button onClick={() => { onApply(result); onClose(); }}
              style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 14px", borderRadius: 4, border: "none", backgroundColor: ACCENT, color: "#111", fontSize: 11, fontWeight: 700, cursor: "pointer" }}>
              <Check size={11} /> {applyLabel}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
