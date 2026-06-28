import { useState, useRef, useEffect, useCallback } from "react";
import { Sparkles, X, Send, Loader2, ChevronDown, Trash2, Wand2, Check } from "lucide-react";
import { useAIAssistant, PageContext } from "../../contexts/AIAssistantContext";
import { streamRequest, generateNodes } from "../../services/aiService";

const ACCENT = "#fce499";
const BG = "rgba(14, 14, 28, 0.97)";
const BG_CARD = "#1a1a2e";
const BORDER = "rgba(255,255,255,0.1)";

const MIN_W = 280;
const MAX_W = 800;
const MIN_H = 300;

interface Message {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
}

function MarkdownText({ text }: { text: string }) {
  const parts = text.split(/(```[\s\S]*?```|`[^`]+`)/g);
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("```") && part.endsWith("```")) {
          const code = part.slice(3, -3).replace(/^[a-z]+\n/, "");
          return (
            <pre key={i} style={{
              margin: "6px 0", padding: "8px 10px", borderRadius: 5,
              backgroundColor: "rgba(0,0,0,0.4)", border: `1px solid ${BORDER}`,
              fontSize: 11, overflowX: "auto", whiteSpace: "pre-wrap", lineHeight: 1.5,
              color: "#a8d8a8", fontFamily: "monospace",
            }}>{code.trim()}</pre>
          );
        }
        if (part.startsWith("`") && part.endsWith("`")) {
          return (
            <code key={i} style={{
              backgroundColor: "rgba(0,0,0,0.3)", padding: "1px 4px", borderRadius: 3,
              fontSize: 11, fontFamily: "monospace", color: "#a8d8a8",
            }}>{part.slice(1, -1)}</code>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </>
  );
}

type GenMode = "idle" | "input" | "loading" | "preview";

function nodePreviewLabel(node: any): string {
  switch (node.node_type) {
    case "transform":
      return `Transform (${node.transform_type || "?"}) → ${node.output_field || "?"}`;
    case "constant":
      return `Konstante (${node.const_type || "?"}) → ${node.output_field || "?"}`;
    case "agg": {
      const fs = (node.fields || []).map((f: any) => `${f.func}(${f.input_field}) → ${f.output_field}`).join(", ");
      return `Aggregation: ${fs || "?"}`;
    }
    case "calc":
      return `Fensterfunktion (${node.calc_type || "?"}) → ${node.output_field || "?"}`;
    case "lookup":
      return `Lookup in "${node.lookup_dataset_name || "?"}" → ${(node.output_mappings || []).map((m: any) => m.output_field).join(", ") || "?"}`;
    case "python":
      return `Python → ${(node.output_fields || []).join(", ") || "?"}`;
    case "expr": {
      const fs = (node.output_fields || []).map((f: any) => `${f.name}: ${f.expr}`).join(", ");
      return `Ausdruck: ${fs || "?"}`;
    }
    case "data_quality":
      return `Datenqualität: ${(node.rules || []).map((r: any) => `${r.field}(${r.type})`).join(", ") || "?"}`;
    default:
      return node.node_type || "Unbekannter Node";
  }
}

type AiMode = "schnell" | "auto" | "analyse";

const AI_MODES: { id: AiMode; icon: string; label: string; title: string }[] = [
  { id: "schnell", icon: "⚡", label: "Schnell",  title: "Schnell – think: aus, kurze Antworten, kleines Modell" },
  { id: "auto",    icon: "⚖",  label: "Auto",     title: "Automatisch – Datenmonster wählt Modell und Modus" },
  { id: "analyse", icon: "🧠", label: "Analyse",  title: "Analyse – think: an, lange Antworten, großes Modell" },
];

export default function FloatingAIAssistant() {
  const { isOpen, setIsOpen, pageContext, callGenerateNodes } = useAIAssistant();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [aiAvailable, setAiAvailable] = useState<boolean | null>(null);
  const [aiModel, setAiModel] = useState<string | null>(null);
  const [aiMode, setAiMode] = useState<AiMode>("auto");
  const [genMode, setGenMode] = useState<GenMode>("idle");
  const [genDescription, setGenDescription] = useState("");
  const [genTokens, setGenTokens] = useState("");
  const [genResult, setGenResult] = useState<{ nodes: any[]; explanation: string } | null>(null);
  const [tokenCount, setTokenCount] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<boolean>(false);
  const abortCtrlRef = useRef<AbortController | null>(null);

  // Drag & resize state
  const [pos, setPos] = useState(() => ({
    x: window.innerWidth - 380 - 16,
    y: 54,
  }));
  const [size, setSize] = useState({ w: 380, h: 520 });
  const dragRef = useRef<{ startX: number; startY: number; px: number; py: number } | null>(null);
  const resizeRef = useRef<{ startX: number; startY: number; sw: number; sh: number } | null>(null);
  const [dragging, setDragging] = useState(false);

  const onDragStart = useCallback((e: React.MouseEvent) => {
    // Don't interfere with buttons in the header
    if ((e.target as HTMLElement).closest("button")) return;
    e.preventDefault();
    dragRef.current = { startX: e.clientX, startY: e.clientY, px: pos.x, py: pos.y };
    setDragging(true);

    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return;
      const { px, py, startX, startY } = dragRef.current;
      setPos({
        x: Math.max(0, Math.min(window.innerWidth - size.w, px + ev.clientX - startX)),
        y: Math.max(0, Math.min(window.innerHeight - 60, py + ev.clientY - startY)),
      });
    };
    const onUp = () => {
      dragRef.current = null;
      setDragging(false);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }, [pos, size.w]);

  const onResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    resizeRef.current = { startX: e.clientX, startY: e.clientY, sw: size.w, sh: size.h };

    const onMove = (ev: MouseEvent) => {
      if (!resizeRef.current) return;
      const { startX, startY, sw, sh } = resizeRef.current;
      setSize({
        w: Math.max(MIN_W, Math.min(MAX_W, sw + ev.clientX - startX)),
        h: Math.max(MIN_H, Math.min(window.innerHeight - pos.y - 20, sh + ev.clientY - startY)),
      });
    };
    const onUp = () => {
      resizeRef.current = null;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }, [size, pos.y]);

  useEffect(() => {
    fetch("/api/ai/status", {
      headers: { Authorization: `Bearer ${localStorage.getItem("dm_token") || ""}` },
    })
      .then(r => r.json())
      .then(d => { setAiAvailable(d.enabled && d.ollama_reachable); if (d.model) setAiModel(d.model); })
      .catch(() => setAiAvailable(false));
  }, []);

  useEffect(() => {
    if (isOpen && inputRef.current) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    setMessages([]);
  }, [pageContext?.page]);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");

    const userMsg: Message = { role: "user", content: text };
    const assistantMsg: Message = { role: "assistant", content: "", streaming: true };
    setMessages(prev => [...prev, userMsg, assistantMsg]);
    setStreaming(true);
    setTokenCount(0);
    abortRef.current = false;
    const ctrl = new AbortController();
    abortCtrlRef.current = ctrl;

    const history = messages.map(m => ({ role: m.role, content: m.content }));

    try {
      await streamRequest("/chat", {
        message: text,
        history,
        mode: aiMode,
        page_context: pageContext
          ? {
              page: pageContext.page,
              title: pageContext.title,
              description: pageContext.description,
              currentData: pageContext.currentData ?? {},
            }
          : {},
      }, (_token: string, full: string) => {
        if (abortRef.current) return;
        setTokenCount(prev => prev + 1);
        setMessages(prev => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: "assistant", content: full, streaming: true };
          return updated;
        });
      }, (meta: any) => {
        if (meta?.model) setAiModel(meta.model);
      }, ctrl.signal);
    } catch (e: any) {
      const msg = e?.message || "KI nicht verfügbar";
      if (msg === "__ABORTED__") {
        // Abbruch durch User — partielle Antwort behalten, markieren
        setMessages(prev => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          updated[updated.length - 1] = {
            ...last,
            content: (last.content || "") + (last.content ? "\n\n*[abgebrochen]*" : "*[abgebrochen]*"),
            streaming: false,
          };
          return updated;
        });
      } else {
        const isOllamaError = msg.toLowerCase().includes("ollama");
        const isNetworkError = msg.toLowerCase().includes("nicht erreichbar") || msg.toLowerCase().includes("netzwerk");
        let display = msg;
        if (isNetworkError && !isOllamaError) {
          setAiAvailable(false);
          display = "Backend nicht erreichbar. Bitte Seite neu laden.";
        }
        setMessages(prev => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            role: "assistant",
            content: `⚠ ${display}`,
            streaming: false,
          };
          return updated;
        });
      }
    } finally {
      setStreaming(false);
      setMessages(prev => {
        const updated = [...prev];
        if (updated.length > 0) {
          updated[updated.length - 1] = { ...updated[updated.length - 1], streaming: false };
        }
        return updated;
      });
    }
  }, [input, streaming, messages, pageContext]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const clearConversation = () => {
    abortRef.current = true;
    abortCtrlRef.current?.abort();
    abortCtrlRef.current = null;
    setStreaming(false);
    setTokenCount(0);
    setMessages([]);
  };

  const abortStreaming = () => {
    abortRef.current = true;
    abortCtrlRef.current?.abort();
    abortCtrlRef.current = null;
  };

  const resetGenMode = () => {
    setGenMode("idle");
    setGenDescription("");
    setGenTokens("");
    setGenResult(null);
  };

  const handleGenerate = async () => {
    if (!genDescription.trim()) return;
    setGenMode("loading");
    setGenTokens("");
    setGenResult(null);

    const canvasDatasets = (pageContext?.currentData as any)?.canvasDatasets ?? [];

    try {
      const result = await generateNodes(
        genDescription,
        canvasDatasets,
        (token: string) => setGenTokens(prev => prev + token),
      );
      if (result && Array.isArray(result.nodes) && result.nodes.length > 0) {
        setGenResult(result);
        setGenMode("preview");
      } else {
        throw new Error("Keine Nodes generiert – bitte Beschreibung präzisieren");
      }
    } catch (e: any) {
      setGenMode("input");
      setMessages(prev => [...prev, {
        role: "assistant",
        content: `Fehler beim Generieren: ${e.message}`,
        streaming: false,
      }]);
      resetGenMode();
    }
  };

  const handleApplyNodes = () => {
    if (!genResult) return;
    callGenerateNodes(genResult);
    const n = genResult.nodes.length;
    const explanation = genResult.explanation;
    setMessages([{
      role: "assistant",
      content: `✅ ${n} Node${n !== 1 ? "s" : ""} wurden zum Mapping hinzugefügt.\n\n${explanation || ""}`,
      streaming: false,
    }]);
    resetGenMode();
  };

  const pageLabel = pageContext?.title ?? "Datenmonster";

  return (
    <>
      {/* Trigger button — bleibt immer fixed oben rechts */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        title="KI-Assistent öffnen"
        style={{
          position: "fixed",
          top: 12,
          right: 16,
          zIndex: 9997,
          display: "flex",
          alignItems: "center",
          gap: 6,
          padding: "7px 13px",
          borderRadius: 20,
          border: `1px solid ${isOpen ? ACCENT : "rgba(252,228,153,0.3)"}`,
          backgroundColor: isOpen ? "rgba(252,228,153,0.12)" : "rgba(14,14,28,0.92)",
          color: ACCENT,
          cursor: "pointer",
          fontSize: 12,
          fontWeight: 600,
          backdropFilter: "blur(8px)",
          boxShadow: isOpen ? `0 0 0 1px rgba(252,228,153,0.2), 0 4px 20px rgba(0,0,0,0.5)` : "0 2px 12px rgba(0,0,0,0.4)",
          transition: "all 0.2s ease",
        }}
      >
        <Sparkles size={13} />
        KI Assistent
        <ChevronDown
          size={11}
          style={{
            transform: isOpen ? "rotate(180deg)" : "rotate(0deg)",
            transition: "transform 0.2s ease",
            opacity: 0.6,
          }}
        />
      </button>

      {/* Panel */}
      {isOpen && (
        <div
          style={{
            position: "fixed",
            left: pos.x,
            top: pos.y,
            width: size.w,
            height: size.h,
            zIndex: 9996,
            display: "flex",
            flexDirection: "column",
            backgroundColor: BG,
            border: `1px solid rgba(252,228,153,0.2)`,
            borderRadius: 12,
            boxShadow: "0 8px 40px rgba(0,0,0,0.6), 0 0 0 1px rgba(252,228,153,0.08)",
            backdropFilter: "blur(12px)",
            overflow: "hidden",
            userSelect: dragging ? "none" : "auto",
          }}
        >
          {/* Header — Drag-Zone */}
          <div
            onMouseDown={onDragStart}
            style={{
              padding: "12px 14px",
              borderBottom: `1px solid ${BORDER}`,
              display: "flex",
              alignItems: "center",
              gap: 8,
              flexShrink: 0,
              cursor: "move",
              position: "relative",
            }}
          >
            <Sparkles size={14} color={ACCENT} />
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: ACCENT }}>KI Assistent</div>
              <div style={{ fontSize: 10, color: "rgba(255,255,255,0.35)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {pageLabel}
              </div>
            </div>
            {/* Modell-Chip zentriert */}
            {aiModel && (
              <div style={{
                position: "absolute", left: "50%", top: "50%",
                transform: "translate(-50%, -50%)",
                fontSize: 9, fontFamily: "monospace", fontWeight: 600,
                color: "rgba(252,228,153,0.55)",
                backgroundColor: "rgba(252,228,153,0.06)",
                border: "1px solid rgba(252,228,153,0.12)",
                borderRadius: 10, padding: "2px 8px",
                whiteSpace: "nowrap", pointerEvents: "none",
              }}>
                {aiModel}
              </div>
            )}
            <div style={{ flex: 1 }} />
            {/* Mode-Selector */}
            <div style={{ display: "flex", gap: 2, marginRight: 6 }}>
              {AI_MODES.map(m => (
                <button
                  key={m.id}
                  onClick={() => setAiMode(m.id)}
                  title={m.title}
                  style={{
                    padding: "2px 6px",
                    borderRadius: 5,
                    border: `1px solid ${aiMode === m.id ? ACCENT : "rgba(255,255,255,0.1)"}`,
                    backgroundColor: aiMode === m.id ? "rgba(252,228,153,0.12)" : "transparent",
                    color: aiMode === m.id ? ACCENT : "rgba(255,255,255,0.3)",
                    cursor: "pointer",
                    fontSize: 13,
                    lineHeight: 1,
                    transition: "all 0.15s",
                  }}
                >
                  {m.icon}
                </button>
              ))}
            </div>
            {messages.length > 0 && (
              <button
                onClick={clearConversation}
                title="Unterhaltung löschen"
                style={{ background: "none", border: "none", color: "rgba(255,255,255,0.3)", cursor: "pointer", padding: 4, display: "flex", alignItems: "center" }}
              >
                <Trash2 size={12} />
              </button>
            )}
            <button
              onClick={() => setIsOpen(false)}
              style={{ background: "none", border: "none", color: "rgba(255,255,255,0.3)", cursor: "pointer", padding: 4, display: "flex", alignItems: "center" }}
            >
              <X size={13} />
            </button>
          </div>

          {/* Generate-Node-Panel (overlay) */}
          {genMode !== "idle" && (
            <div style={{
              position: "absolute",
              inset: 0,
              top: 49,
              bottom: 57,
              backgroundColor: BG,
              display: "flex",
              flexDirection: "column",
              padding: "14px",
              gap: 10,
              zIndex: 10,
              borderRadius: "0 0 12px 12px",
              overflowY: "auto",
            }}>
              {/* Panel-Header */}
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
                <Wand2 size={14} color={ACCENT} />
                <span style={{ fontSize: 12, fontWeight: 700, color: ACCENT }}>Nodes generieren</span>
                <button
                  onClick={resetGenMode}
                  style={{ marginLeft: "auto", background: "none", border: "none", color: "rgba(255,255,255,0.35)", cursor: "pointer", padding: 2, display: "flex" }}
                >
                  <X size={12} />
                </button>
              </div>

              {/* Input-Modus */}
              {genMode === "input" && (
                <>
                  <textarea
                    value={genDescription}
                    onChange={e => setGenDescription(e.target.value)}
                    placeholder={"z.B. \"Summiere den Umsatz pro Kunde, formatiere die Zahl und füge das heutige Datum als Export-Datum hinzu\""}
                    rows={6}
                    autoFocus
                    onKeyDown={e => { if (e.key === "Enter" && e.ctrlKey) handleGenerate(); }}
                    style={{
                      flex: 1,
                      resize: "none",
                      backgroundColor: "rgba(255,255,255,0.05)",
                      border: `1px solid ${BORDER}`,
                      borderRadius: 8,
                      color: "rgba(255,255,255,0.85)",
                      fontSize: 12,
                      padding: "10px 12px",
                      outline: "none",
                      fontFamily: "inherit",
                      lineHeight: 1.5,
                    }}
                  />
                  <div style={{ fontSize: 10, color: "rgba(255,255,255,0.25)" }}>
                    Tipp: Nenne Felder und gewünschte Ausgaben. Strg+Enter zum Generieren.
                  </div>
                  <button
                    onClick={handleGenerate}
                    disabled={!genDescription.trim()}
                    style={{
                      padding: "9px 14px",
                      borderRadius: 8,
                      border: "none",
                      backgroundColor: genDescription.trim() ? ACCENT : "rgba(255,255,255,0.08)",
                      color: genDescription.trim() ? "#111" : "rgba(255,255,255,0.2)",
                      cursor: genDescription.trim() ? "pointer" : "default",
                      fontSize: 12, fontWeight: 700,
                      display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
                      flexShrink: 0,
                    }}
                  >
                    <Wand2 size={13} /> Generieren
                  </button>
                </>
              )}

              {/* Lade-Modus */}
              {genMode === "loading" && (
                <div style={{ flex: 1, overflowY: "auto" }}>
                  <div style={{ fontSize: 10, color: "rgba(255,255,255,0.35)", marginBottom: 10, display: "flex", alignItems: "center", gap: 6 }}>
                    <Loader2 size={10} className="animate-spin" />
                    KI denkt nach...
                  </div>
                  <pre style={{
                    fontSize: 10, color: "rgba(255,255,255,0.35)",
                    whiteSpace: "pre-wrap", wordBreak: "break-all",
                    fontFamily: "monospace", margin: 0, lineHeight: 1.4,
                  }}>{genTokens}</pre>
                </div>
              )}

              {/* Vorschau-Modus */}
              {genMode === "preview" && genResult && (
                <>
                  {genResult.explanation && (
                    <div style={{
                      fontSize: 11, color: "rgba(255,255,255,0.65)",
                      backgroundColor: "rgba(255,255,255,0.04)",
                      borderRadius: 8, padding: "8px 10px",
                      border: `1px solid ${BORDER}`,
                      lineHeight: 1.55, flexShrink: 0,
                    }}>
                      {genResult.explanation}
                    </div>
                  )}
                  <div style={{ fontSize: 11, fontWeight: 600, color: "rgba(255,255,255,0.4)", flexShrink: 0 }}>
                    {genResult.nodes.length} Node{genResult.nodes.length !== 1 ? "s" : ""} werden erstellt:
                  </div>
                  <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 5 }}>
                    {genResult.nodes.map((node: any, i: number) => (
                      <div key={i} style={{
                        display: "flex", alignItems: "flex-start", gap: 8,
                        padding: "7px 10px", borderRadius: 8,
                        backgroundColor: "rgba(255,255,255,0.04)",
                        border: `1px solid ${BORDER}`,
                        fontSize: 11, color: "rgba(255,255,255,0.7)",
                      }}>
                        <span style={{ color: ACCENT, fontWeight: 700, minWidth: 16, fontSize: 10, paddingTop: 1 }}>{i + 1}</span>
                        <span style={{ lineHeight: 1.45 }}>{nodePreviewLabel(node)}</span>
                      </div>
                    ))}
                  </div>
                  <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
                    <button
                      onClick={handleApplyNodes}
                      style={{
                        flex: 1, padding: "9px 8px",
                        borderRadius: 8, border: "none",
                        backgroundColor: ACCENT, color: "#111",
                        fontSize: 12, fontWeight: 700, cursor: "pointer",
                        display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
                      }}
                    >
                      <Check size={13} /> Übernehmen
                    </button>
                    <button
                      onClick={() => { setGenMode("input"); setGenResult(null); setGenTokens(""); }}
                      style={{
                        flex: 1, padding: "9px 8px",
                        borderRadius: 8,
                        border: `1px solid ${BORDER}`,
                        backgroundColor: "transparent",
                        color: "rgba(255,255,255,0.4)",
                        fontSize: 12, cursor: "pointer",
                      }}
                    >
                      Verwerfen
                    </button>
                  </div>
                </>
              )}
            </div>
          )}

          {/* Messages */}
          <div style={{
            flex: 1,
            overflowY: "auto",
            padding: "12px 14px",
            display: "flex",
            flexDirection: "column",
            gap: 10,
          }}>
            {messages.length === 0 && (
              <div style={{ textAlign: "center", padding: "20px 0" }}>
                <div style={{ fontSize: 28, marginBottom: 10 }}>✨</div>
                {aiAvailable === false ? (
                  <p style={{ fontSize: 11, color: "rgba(255,255,255,0.3)", margin: 0 }}>
                    KI-Integration ist nicht aktiv.<br />
                    Bitte unter Einstellungen → KI aktivieren.
                  </p>
                ) : (
                  <>
                    <p style={{ fontSize: 12, color: "rgba(255,255,255,0.5)", margin: "0 0 8px" }}>
                      Ich bin dein KI-Assistent für {pageLabel}.
                    </p>
                    <SuggestedQuestions pageContext={pageContext} onSelect={q => { setInput(q); inputRef.current?.focus(); }} />
                    {pageContext?.page === "mapping_editor" && (
                      <button
                        onClick={() => setGenMode("input")}
                        style={{
                          marginTop: 12,
                          width: "100%",
                          padding: "10px 12px",
                          borderRadius: 10,
                          border: `1px dashed rgba(252,228,153,0.3)`,
                          backgroundColor: "rgba(252,228,153,0.05)",
                          color: ACCENT,
                          cursor: "pointer",
                          fontSize: 11,
                          fontWeight: 600,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          gap: 7,
                          transition: "all 0.15s",
                        }}
                        onMouseOver={e => { e.currentTarget.style.backgroundColor = "rgba(252,228,153,0.1)"; e.currentTarget.style.borderColor = "rgba(252,228,153,0.5)"; }}
                        onMouseOut={e => { e.currentTarget.style.backgroundColor = "rgba(252,228,153,0.05)"; e.currentTarget.style.borderColor = "rgba(252,228,153,0.3)"; }}
                      >
                        <Wand2 size={13} />
                        Nodes aus Beschreibung generieren
                      </button>
                    )}
                  </>
                )}
              </div>
            )}

            {messages.map((msg, i) => (
              <div key={i} style={{
                display: "flex",
                justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
              }}>
                <div style={{
                  maxWidth: "85%",
                  padding: "8px 11px",
                  borderRadius: msg.role === "user" ? "12px 12px 3px 12px" : "12px 12px 12px 3px",
                  backgroundColor: msg.role === "user" ? "rgba(252,228,153,0.12)" : BG_CARD,
                  border: `1px solid ${msg.role === "user" ? "rgba(252,228,153,0.2)" : BORDER}`,
                  fontSize: 12,
                  color: msg.role === "user" ? ACCENT : "rgba(255,255,255,0.85)",
                  lineHeight: 1.55,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                }}>
                  {msg.streaming && msg.content === "" ? (
                    <span style={{ color: "rgba(255,255,255,0.3)", fontSize: 11 }}>
                      <Loader2 size={11} style={{ display: "inline", marginRight: 4 }} className="animate-spin" />
                      Denkt nach...
                    </span>
                  ) : (
                    <MarkdownText text={msg.content} />
                  )}
                  {msg.streaming && msg.content !== "" && (
                    <span style={{ display: "inline-block", width: 6, height: 12, backgroundColor: ACCENT, marginLeft: 2, animation: "aiCursor 0.8s ease-in-out infinite", verticalAlign: "middle" }} />
                  )}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          {/* Token-Zähler + Abbrechen (nur während Streaming) */}
          {streaming && (
            <div style={{
              padding: "6px 14px",
              borderTop: `1px solid ${BORDER}`,
              display: "flex",
              alignItems: "center",
              gap: 8,
              flexShrink: 0,
              backgroundColor: "rgba(252,228,153,0.04)",
            }}>
              <Loader2 size={11} className="animate-spin" color={ACCENT} />
              <span style={{ fontSize: 11, color: "rgba(255,255,255,0.45)", flex: 1 }}>
                {tokenCount > 0 ? `${tokenCount} Token generiert` : "Denkt nach…"}
              </span>
              <button
                onClick={abortStreaming}
                title="Generierung abbrechen"
                style={{
                  display: "flex", alignItems: "center", gap: 4,
                  padding: "3px 9px", borderRadius: 6,
                  border: "1px solid rgba(224,112,112,0.4)",
                  backgroundColor: "rgba(224,112,112,0.08)",
                  color: "#e07070", cursor: "pointer", fontSize: 11, fontWeight: 600,
                }}
              >
                <X size={10} /> Abbrechen
              </button>
            </div>
          )}

          {/* Input */}
          <div style={{
            padding: "10px 12px",
            borderTop: streaming ? "none" : `1px solid ${BORDER}`,
            display: "flex",
            gap: 8,
            alignItems: "flex-end",
            flexShrink: 0,
          }}>
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={aiAvailable === false ? "KI nicht verfügbar" : "Frage stellen... (Enter zum Senden)"}
              disabled={streaming || aiAvailable === false}
              rows={1}
              style={{
                flex: 1,
                resize: "none",
                backgroundColor: "rgba(255,255,255,0.05)",
                border: `1px solid ${BORDER}`,
                borderRadius: 8,
                color: "rgba(255,255,255,0.85)",
                fontSize: 12,
                padding: "8px 10px",
                outline: "none",
                fontFamily: "inherit",
                lineHeight: 1.4,
                maxHeight: 100,
                overflowY: "auto",
              }}
              onInput={e => {
                const el = e.currentTarget;
                el.style.height = "auto";
                el.style.height = Math.min(el.scrollHeight, 100) + "px";
              }}
            />
            <button
              onClick={sendMessage}
              disabled={!input.trim() || streaming || aiAvailable === false}
              style={{
                width: 34,
                height: 34,
                borderRadius: 8,
                border: "none",
                backgroundColor: input.trim() && !streaming ? ACCENT : "rgba(255,255,255,0.08)",
                color: input.trim() && !streaming ? "#111" : "rgba(255,255,255,0.2)",
                cursor: input.trim() && !streaming ? "pointer" : "default",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
                transition: "all 0.15s ease",
              }}
            >
              {streaming ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            </button>
          </div>

          {/* Resize handle — rechte untere Ecke */}
          <div
            onMouseDown={onResizeStart}
            title="Größe ändern"
            style={{
              position: "absolute",
              right: 0,
              bottom: 0,
              width: 18,
              height: 18,
              cursor: "nwse-resize",
              display: "flex",
              alignItems: "flex-end",
              justifyContent: "flex-end",
              padding: 3,
              opacity: 0.35,
            }}
          >
            {/* Drei diagonale Linien als Grip-Icon */}
            <svg width="10" height="10" viewBox="0 0 10 10" fill="rgba(255,255,255,0.8)">
              <line x1="2" y1="10" x2="10" y2="2" stroke="rgba(255,255,255,0.8)" strokeWidth="1.2" strokeLinecap="round" />
              <line x1="5" y1="10" x2="10" y2="5" stroke="rgba(255,255,255,0.8)" strokeWidth="1.2" strokeLinecap="round" />
              <line x1="8" y1="10" x2="10" y2="8" stroke="rgba(255,255,255,0.8)" strokeWidth="1.2" strokeLinecap="round" />
            </svg>
          </div>
        </div>
      )}

      <style>{`
        @keyframes aiCursor {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
        .animate-spin { animation: spin 1s linear infinite; }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </>
  );
}

function SuggestedList({ questions, onSelect }: { questions: string[]; onSelect: (q: string) => void }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5, marginTop: 4 }}>
      {questions.map(q => (
        <button key={q} onClick={() => onSelect(q)}
          style={{ background: "none", border: `1px solid rgba(255,255,255,0.1)`, borderRadius: 8, padding: "6px 10px", fontSize: 11, color: "rgba(255,255,255,0.5)", cursor: "pointer", textAlign: "left", transition: "all 0.15s" }}
          onMouseOver={e => { e.currentTarget.style.borderColor = "rgba(252,228,153,0.3)"; e.currentTarget.style.color = "rgba(252,228,153,0.8)"; }}
          onMouseOut={e => { e.currentTarget.style.borderColor = "rgba(255,255,255,0.1)"; e.currentTarget.style.color = "rgba(255,255,255,0.5)"; }}>
          {q}
        </button>
      ))}
    </div>
  );
}

function SuggestedQuestions({ pageContext, onSelect }: { pageContext: PageContext | null; onSelect: (q: string) => void }) {
  const activeNode = (pageContext?.currentData as any)?.activeNode;

  // Python-Node aktiv → spezifische Vorschläge
  if (activeNode?.type === "python") {
    const hasScript = !!activeNode.script?.trim();
    const qs = [
      hasScript ? "Erkläre mir diesen Python-Code" : null,
      hasScript ? "Wie kann ich diesen Code verbessern?" : null,
      "Schreibe Python-Code der Brutto in Netto umrechnet (19% MwSt)",
      "Wie greife ich auf Felder aus row zu und schreibe neue Felder?",
      "Wie fange ich Fehler ab ohne die ganze Zeile zu stoppen?",
    ].filter(Boolean) as string[];
    return <SuggestedList questions={qs} onSelect={onSelect} />;
  }

  // Expression-Node aktiv → spezifische Vorschläge
  if (activeNode?.type === "expression") {
    const hasFields = (activeNode.fields || []).some((f: any) => f.expr?.trim());
    const qs = [
      hasFields ? "Erkläre mir die aktuellen Ausdrücke" : null,
      "Wie verbinde ich Vor- und Nachname mit Leerzeichen?",
      "Wie berechne ich Brutto aus Netto mit 19% MwSt?",
      "Welche Funktionen sind verfügbar? (concat, if_, round, ...)",
      "Wie formatiere ich ein Datum in DD.MM.YYYY?",
    ].filter(Boolean) as string[];
    return <SuggestedList questions={qs} onSelect={onSelect} />;
  }

  // SQL-Node aktiv → spezifische Vorschläge
  if (activeNode?.type === "sql") {
    const mode = activeNode.mode || "scalar";
    const hasSql = !!activeNode.sql?.trim();
    const qs = [
      hasSql ? "Erkläre mir das aktuelle SQL" : null,
      mode === "scalar" ? "Generiere SQL für einen Scalar-Lookup mit {Feldname}" : null,
      mode === "transform" ? "Generiere ein Transform-SQL das zwei Canvas-Datasets joined" : null,
      mode === "lookup" ? "Generiere ein Lookup-SQL mit :param als Parameter" : null,
      mode === "column" ? "Generiere SQL für eine einmalige Spaltenabfrage" : null,
      "Welche Modi gibt es im SQL-Node?",
    ].filter(Boolean) as string[];
    return <SuggestedList questions={qs} onSelect={onSelect} />;
  }

  // Dataset-Node aktiv → Datenanalyse-Vorschläge
  if (activeNode?.type === "dataset") {
    const qs = [
      activeNode.name ? `Analysiere das Dataset "${activeNode.name}" für mich` : "Analysiere dieses Dataset für mich",
      activeNode.columns?.length ? `Welche Felder hat das Dataset? (${(activeNode.columns as string[]).slice(0, 3).join(", ")}...)` : "Welche Felder hat dieses Dataset?",
      "Welche Transformationen empfiehlst du für dieses Dataset?",
      "Wie kann ich dieses Dataset mit einem anderen joinen?",
      "Gibt es potenzielle Datenkualitätsprobleme?",
    ];
    return <SuggestedList questions={qs} onSelect={onSelect} />;
  }

  // Aggregation-Node aktiv
  if (activeNode?.type === "aggregation") {
    const qs = [
      "Erkläre mir die verfügbaren Aggregationsfunktionen",
      "Wie berechne ich den Umsatz pro Kunde (GROUP BY)?",
      "Was ist der Unterschied zwischen SUM, AVG und COUNT?",
      "Wie kombiniere ich mehrere Aggregationen?",
    ];
    return <SuggestedList questions={qs} onSelect={onSelect} />;
  }

  // Calc-Node aktiv
  if (activeNode?.type === "calc") {
    const calcType = activeNode.calcType || "formula";
    const qs = [
      calcType === "formula" ? "Wie schreibe ich eine Formel mit mehreren Feldern?" : `Erkläre mir die Funktion "${calcType}"`,
      "Wie berechne ich eine kumulierte Summe?",
      "Wie erstelle ich eine Zeilennummer (row_number)?",
      "Wie berechne ich den gleitenden Durchschnitt über 7 Zeilen?",
    ];
    return <SuggestedList questions={qs} onSelect={onSelect} />;
  }

  // Transform-Node aktiv
  if (activeNode?.type === "transform") {
    const tType = activeNode.transformType || "number_format";
    const qs = [
      `Erkläre mir den Typ "${tType}"`,
      "Wie formatiere ich eine Zahl mit Komma als Dezimalzeichen?",
      "Wie konvertiere ich ein Datum von ISO in deutsches Format?",
      "Wie verkette ich mehrere Felder zu einem Text?",
    ];
    return <SuggestedList questions={qs} onSelect={onSelect} />;
  }

  // REST-Node aktiv
  if (activeNode?.type === "rest") {
    const qs = [
      activeNode.url ? `Erkläre mir diesen API-Aufruf: ${(activeNode.url as string).slice(0, 60)}` : "Erkläre mir den REST-Node",
      "Wie übergebe ich Feldwerte als URL-Parameter?",
      "Was ist der Unterschied zwischen Einzel- und Batch-Modus?",
      "Wie verarbeite ich eine JSON-Antwort mit verschachtelten Objekten?",
    ];
    return <SuggestedList questions={qs} onSelect={onSelect} />;
  }

  // Lookup-Node aktiv
  if (activeNode?.type === "lookup") {
    const qs = [
      "Erkläre mir wie der Lookup-Node funktioniert",
      "Was passiert wenn kein Treffer gefunden wird?",
      "Wie wähle ich die richtige Schlüsselspalte?",
      "Wie verwende ich mehrere Lookup-Ausgabefelder?",
    ];
    return <SuggestedList questions={qs} onSelect={onSelect} />;
  }

  // Switch-Node aktiv
  if (activeNode?.type === "switch") {
    const qs = [
      "Erkläre mir wie der Switch-Node Verzweigungen auswählt",
      "Wie setze ich einen Fallback (Immer) ein?",
      "Wie prüfe ich ob ein Dataset Zeilen hat?",
      "Wie kombiniere ich mehrere Verzweigungen sinnvoll?",
    ];
    return <SuggestedList questions={qs} onSelect={onSelect} />;
  }

  // Params-Node aktiv
  if (activeNode?.type === "params") {
    const qs = [
      "Erkläre mir den Params-Node und run_params",
      "Wie übergebe ich Parameter aus einem Formular?",
      "Wie verwende ich einen Parameter in einem SQL-Node?",
      "Welche Feldtypen sind für Parameter verfügbar?",
    ];
    return <SuggestedList questions={qs} onSelect={onSelect} />;
  }

  // Constant-Node aktiv
  if (activeNode?.type === "constant") {
    const qs = [
      "Erkläre mir die verfügbaren Konstantentypen",
      "Wie füge ich das heutige Datum als Konstante ein?",
      "Wie verwende ich eine Konstante als Eingabe für eine Berechnung?",
    ];
    return <SuggestedList questions={qs} onSelect={onSelect} />;
  }

  // DataQuality-Node aktiv
  if (activeNode?.type === "data_quality") {
    const qs = [
      "Erkläre mir die verfügbaren Validierungsregeln",
      "Wie validiere ich eine E-Mail-Adresse?",
      "Wie schreibe ich einen eigenen Regex für PLZ?",
      "Wie filtere ich später nach __dq_valid__?",
    ];
    return <SuggestedList questions={qs} onSelect={onSelect} />;
  }

  const questions: Record<string, string[]> = {
    dashboard: [
      "Was kann ich hier alles machen?",
      "Wie erstelle ich ein neues Mapping?",
      "Wie funktioniert ein Scheduler?",
    ],
    mapping_editor: [
      "Wie füge ich einen Join hinzu?",
      "Was ist der Unterschied zwischen SQL-Node und Transform-Node?",
      "Wie erstelle ich eine Berechnung?",
    ],
    pipeline_editor: [
      "Wie kombiniere ich mehrere Mappings?",
      "Wie funktionieren Bedingungen in Pipelines?",
    ],
    report_editor: [
      "Wie erstelle ich ein Balkendiagramm?",
      "Wie filter ich die angezeigten Daten?",
    ],
    form_editor: [
      "Wie übergebe ich Parameter an ein Mapping?",
      "Wie füge ich ein Dropdown-Feld hinzu?",
    ],
  };

  const page = pageContext?.page ?? "dashboard";
  const qs = questions[page] ?? questions.dashboard;
  return <SuggestedList questions={qs} onSelect={onSelect} />;
}
