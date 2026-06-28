import { useState, useRef, useEffect, useCallback } from "react";
import { Sparkles, X, Send, Loader2, ChevronDown, Trash2 } from "lucide-react";
import { useAIAssistant, PageContext } from "../../contexts/AIAssistantContext";
import { streamRequest } from "../../services/aiService";

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

export default function FloatingAIAssistant() {
  const { isOpen, setIsOpen, pageContext } = useAIAssistant();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [aiAvailable, setAiAvailable] = useState<boolean | null>(null);
  const [aiModel, setAiModel] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<boolean>(false);

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
      setPos(prev => ({
        x: Math.max(0, Math.min(window.innerWidth - size.w, dragRef.current!.px + ev.clientX - dragRef.current!.startX)),
        y: Math.max(0, Math.min(window.innerHeight - 60, dragRef.current!.py + ev.clientY - dragRef.current!.startY)),
      }));
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
      const dw = ev.clientX - resizeRef.current.startX;
      const dh = ev.clientY - resizeRef.current.startY;
      setSize({
        w: Math.max(MIN_W, Math.min(MAX_W, resizeRef.current.sw + dw)),
        h: Math.max(MIN_H, Math.min(window.innerHeight - pos.y - 20, resizeRef.current.sh + dh)),
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
    abortRef.current = false;

    const history = messages.map(m => ({ role: m.role, content: m.content }));

    try {
      await streamRequest("/chat", {
        message: text,
        history,
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
        setMessages(prev => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: "assistant", content: full, streaming: true };
          return updated;
        });
      });
    } catch (e: any) {
      setMessages(prev => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: "assistant",
          content: `Fehler: ${e.message || "KI nicht verfügbar"}`,
          streaming: false,
        };
        return updated;
      });
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
    setStreaming(false);
    setMessages([]);
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

          {/* Input */}
          <div style={{
            padding: "10px 12px",
            borderTop: `1px solid ${BORDER}`,
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

function SuggestedQuestions({ pageContext, onSelect }: { pageContext: PageContext | null; onSelect: (q: string) => void }) {
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

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5, marginTop: 4 }}>
      {qs.map(q => (
        <button
          key={q}
          onClick={() => onSelect(q)}
          style={{
            background: "none",
            border: `1px solid rgba(255,255,255,0.1)`,
            borderRadius: 8,
            padding: "6px 10px",
            fontSize: 11,
            color: "rgba(255,255,255,0.5)",
            cursor: "pointer",
            textAlign: "left",
            transition: "all 0.15s",
          }}
          onMouseOver={e => { e.currentTarget.style.borderColor = "rgba(252,228,153,0.3)"; e.currentTarget.style.color = "rgba(252,228,153,0.8)"; }}
          onMouseOut={e => { e.currentTarget.style.borderColor = "rgba(255,255,255,0.1)"; e.currentTarget.style.color = "rgba(255,255,255,0.5)"; }}
        >
          {q}
        </button>
      ))}
    </div>
  );
}
