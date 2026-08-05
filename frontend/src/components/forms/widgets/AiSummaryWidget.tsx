import { useState, useEffect } from "react";
import { Sparkles, Loader2, AlertCircle } from "lucide-react";
import { streamRequest } from "../../../services/aiService";

const S = {
  textMain: "var(--text-main)", textDim: "var(--text-dim)", accent: "var(--accent)",
};

/**
 * Widget "ai_summary": erzeugt aus dem Ergebnis der verknüpften Action (z.B. der
 * KPI-Zeile) eine kurze KI-Management-Zusammenfassung über /api/ai/summarize-data.
 * Verbraucht KEINE eigene DB-Abfrage – es nutzt das bereits geladene Action-Ergebnis.
 * Der Endpunkt streamt (SSE), damit der Text fortlaufend erscheint und langsame
 * Modell-Kaltstarts nicht zu "Network Error" führen.
 *
 * config: { width, instruction? }
 */
export default function AiSummaryWidget({ widget, result }) {
  const cfg = widget.config || {};
  const rows = result?.rows || [];
  const columns = result?.columns || [];
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  // Nur (neu) generieren, wenn sich die zugrunde liegenden Daten ändern.
  const dataKey = JSON.stringify(rows) + "|" + (cfg.instruction || "");

  useEffect(() => {
    if (!rows.length) { setText(""); setErr(null); return; }
    const ac = new AbortController();
    setLoading(true); setErr(null); setText("");
    streamRequest(
      "/summarize-data",
      { label: widget.label || "", columns, rows, instruction: cfg.instruction || "" },
      (_tok, full) => setText(full),
      null,
      ac.signal,
    )
      .catch(e => { if (e.message !== "__ABORTED__") setErr(e.message); })
      .finally(() => { if (!ac.signal.aborted) setLoading(false); });
    return () => ac.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataKey]);

  return (
    <div style={{ padding: "14px 16px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8,
        fontSize: 10, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase",
        color: S.accent }}>
        <Sparkles size={12} /> KI-Analyse
        {loading && <Loader2 size={11} style={{ animation: "spin 1s linear infinite", color: S.textDim }} />}
      </div>
      {!rows.length ? (
        <p style={{ fontSize: 12, color: S.textDim, margin: 0 }}>Warten auf Kennzahlen …</p>
      ) : err ? (
        <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#e07070", fontSize: 12 }}>
          <AlertCircle size={13} /> {err}
        </div>
      ) : text ? (
        <p style={{ fontSize: 13.5, lineHeight: 1.65, color: S.textMain, margin: 0, whiteSpace: "pre-wrap" }}>
          {text}
        </p>
      ) : (
        <p style={{ fontSize: 12, color: S.textDim, margin: 0 }}>
          KI erstellt die Analyse … (kann beim ersten Mal einige Sekunden dauern)
        </p>
      )}
    </div>
  );
}
