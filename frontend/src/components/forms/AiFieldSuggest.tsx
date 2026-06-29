import { useState, useRef } from "react";
import { Sparkles, ChevronDown, ChevronUp, Loader2 } from "lucide-react";
import api from "../../api/client";
import { newField, getFieldDef } from "./fieldTypes";

const S = {
  bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)", border: "var(--border)",
  textDim: "var(--text-dim)", textMain: "var(--text-main)", textBright: "var(--text-bright)",
  accent: "var(--accent)",
};

const AI_COLOR = "#a78bfa";

interface SuggestedField {
  type: string;
  label: string;
  name: string;
  required: boolean;
  placeholder: string;
  options: { value: string; label: string }[];
}

interface Props {
  existingFields: { name?: string; type: string }[];
  onAddFields: (fields: ReturnType<typeof newField>[]) => void;
  maxRow: number;
}

export default function AiFieldSuggest({ existingFields, onAddFields, maxRow }: Props) {
  const [open, setOpen]               = useState(false);
  const [description, setDescription] = useState("");
  const [loading, setLoading]         = useState(false);
  const [streamText, setStreamText]   = useState("");
  const [suggested, setSuggested]     = useState<SuggestedField[] | null>(null);
  const [selected, setSelected]       = useState<Set<number>>(new Set());
  const [error, setError]             = useState<string | null>(null);
  const abortRef = useRef<(() => void) | null>(null);

  const run = async () => {
    if (!description.trim()) return;
    setLoading(true);
    setStreamText("");
    setSuggested(null);
    setSelected(new Set());
    setError(null);

    const existingNames = existingFields
      .map(f => f.name)
      .filter((n): n is string => !!n && n.length > 0);

    let done = false;
    abortRef.current = () => { done = true; };

    try {
      const resp = await fetch(
        `${(api.defaults.baseURL || "").replace(/\/$/, "")}/api/ai/suggest-fields`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${localStorage.getItem("dm_token") || ""}`,
          },
          body: JSON.stringify({ description, existing_field_names: existingNames }),
        }
      );

      const reader = resp.body?.getReader();
      if (!reader) throw new Error("Kein Stream");
      const dec = new TextDecoder();
      let buf = "";

      while (true) {
        if (done) { reader.cancel(); break; }
        const { value, done: streamDone } = await reader.read();
        if (streamDone) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6).trim();
          if (payload === "[DONE]") break;
          try {
            const msg = JSON.parse(payload);
            if (msg.token)  setStreamText(t => t + msg.token);
            if (msg.error)  setError(msg.error);
            if (msg.result) setSuggested(msg.result);
          } catch { /* ignore */ }
        }
      }
    } catch (e: any) {
      setError(String(e?.message ?? e));
    } finally {
      setLoading(false);
    }
  };

  const toggleAll = (val: boolean) => {
    if (!suggested) return;
    setSelected(val ? new Set(suggested.map((_, i) => i)) : new Set());
  };

  const insert = () => {
    if (!suggested) return;
    const toAdd = [...selected]
      .sort((a, b) => a - b)
      .map(i => {
        const s = suggested[i];
        const base = newField(s.type, maxRow + 1);
        base.label = s.label;
        if (s.name) base.name = s.name;
        if (s.placeholder) base.placeholder = s.placeholder;
        if (s.required) base.required = true;
        if (s.options?.length) base.options = s.options;
        if (s.type === "heading" || s.type === "label") base.content = s.label;
        return base;
      });
    if (!toAdd.length) return;
    onAddFields(toAdd);
    setSuggested(null);
    setSelected(new Set());
    setStreamText("");
    setDescription("");
  };

  return (
    <div style={{ borderTop: `1px solid ${S.border}` }}>
      {/* Header */}
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "8px 12px", background: "none", border: "none", cursor: "pointer",
          color: AI_COLOR,
        }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <Sparkles size={12} />
          <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.12em" }}>
            KI-Vorschlag
          </span>
        </div>
        {open ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
      </button>

      {open && (
        <div style={{ padding: "0 10px 10px" }}>
          <textarea
            value={description}
            onChange={e => setDescription(e.target.value)}
            placeholder="z.B. Auftragserfassung mit Kundennummer, Artikel und Lieferdatum"
            rows={3}
            style={{
              width: "100%", boxSizing: "border-box", resize: "vertical",
              backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 5,
              color: S.textMain, fontSize: 10, padding: "6px 8px", outline: "none",
              fontFamily: "inherit", lineHeight: 1.4,
            }}
            onKeyDown={e => { if (e.key === "Enter" && e.ctrlKey) run(); }}
          />

          <button
            onClick={run}
            disabled={loading || !description.trim()}
            style={{
              marginTop: 6, width: "100%", padding: "5px 0",
              backgroundColor: loading ? "transparent" : `${AI_COLOR}18`,
              border: `1px solid ${loading ? S.border : `${AI_COLOR}55`}`,
              borderRadius: 5, color: loading ? S.textDim : AI_COLOR,
              fontSize: 10, fontWeight: 700, cursor: loading ? "wait" : "pointer",
              display: "flex", alignItems: "center", justifyContent: "center", gap: 5,
            }}>
            {loading ? <Loader2 size={10} style={{ animation: "spin 1s linear infinite" }} /> : <Sparkles size={10} />}
            {loading ? "KI denkt…" : "Felder vorschlagen"}
          </button>

          {/* Streaming-Text während KI antwortet */}
          {loading && streamText && (
            <div style={{
              marginTop: 6, fontSize: 9, color: S.textDim, backgroundColor: S.bgEl,
              border: `1px solid ${S.border}`, borderRadius: 4, padding: "4px 6px",
              maxHeight: 60, overflowY: "auto", whiteSpace: "pre-wrap", lineHeight: 1.4,
            }}>
              {streamText}
            </div>
          )}

          {error && (
            <div style={{ marginTop: 6, fontSize: 9, color: "#f87171", padding: "4px 6px",
              backgroundColor: "rgba(248,113,113,0.08)", borderRadius: 4, border: "1px solid rgba(248,113,113,0.25)" }}>
              {error}
            </div>
          )}

          {/* Vorschlagsliste */}
          {suggested && suggested.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                <span style={{ fontSize: 9, fontWeight: 700, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.1em" }}>
                  {suggested.length} Vorschläge
                </span>
                <div style={{ display: "flex", gap: 4 }}>
                  <button onClick={() => toggleAll(true)}
                    style={{ fontSize: 8, color: AI_COLOR, background: "none", border: "none", cursor: "pointer", padding: "1px 3px" }}>
                    Alle
                  </button>
                  <button onClick={() => toggleAll(false)}
                    style={{ fontSize: 8, color: S.textDim, background: "none", border: "none", cursor: "pointer", padding: "1px 3px" }}>
                    Keine
                  </button>
                </div>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 2, maxHeight: 200, overflowY: "auto" }}>
                {suggested.map((f, i) => {
                  const def = getFieldDef(f.type);
                  const isChecked = selected.has(i);
                  return (
                    <label key={i}
                      style={{
                        display: "flex", alignItems: "center", gap: 6, cursor: "pointer",
                        padding: "4px 6px", borderRadius: 4,
                        backgroundColor: isChecked ? `${AI_COLOR}10` : "transparent",
                        border: `1px solid ${isChecked ? `${AI_COLOR}33` : "transparent"}`,
                        transition: "all 0.1s",
                      }}>
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => setSelected(prev => {
                          const next = new Set(prev);
                          next.has(i) ? next.delete(i) : next.add(i);
                          return next;
                        })}
                        style={{ width: 10, height: 10, flexShrink: 0, accentColor: AI_COLOR }}
                      />
                      <div style={{ width: 16, height: 16, borderRadius: 3, flexShrink: 0,
                        backgroundColor: `${def.color}18`, border: `1px solid ${def.color}33`,
                        display: "flex", alignItems: "center", justifyContent: "center" }}>
                        <def.Icon size={9} style={{ color: def.color }} />
                      </div>
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div style={{ fontSize: 10, color: S.textBright, fontWeight: 500,
                          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {f.label}
                        </div>
                        {f.required && (
                          <div style={{ fontSize: 8, color: "#f87171" }}>Pflichtfeld</div>
                        )}
                      </div>
                    </label>
                  );
                })}
              </div>

              <button
                onClick={insert}
                disabled={selected.size === 0}
                style={{
                  marginTop: 6, width: "100%", padding: "5px 0",
                  backgroundColor: selected.size > 0 ? `${AI_COLOR}18` : "transparent",
                  border: `1px solid ${selected.size > 0 ? `${AI_COLOR}55` : S.border}`,
                  borderRadius: 5, color: selected.size > 0 ? AI_COLOR : S.textDim,
                  fontSize: 10, fontWeight: 700, cursor: selected.size > 0 ? "pointer" : "default",
                }}>
                {selected.size > 0 ? `${selected.size} Felder einfügen` : "Felder auswählen"}
              </button>
            </div>
          )}

          {suggested && suggested.length === 0 && (
            <div style={{ marginTop: 6, fontSize: 9, color: S.textDim, textAlign: "center" }}>
              Keine Vorschläge erhalten.
            </div>
          )}
        </div>
      )}

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
