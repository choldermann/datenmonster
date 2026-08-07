import { useState, useEffect, useMemo } from "react";
import { Sparkles, Loader2, AlertCircle } from "lucide-react";
import { streamRequest } from "../../../services/aiService";

const S = {
  textMain: "var(--text-main)", textDim: "var(--text-dim)", accent: "var(--accent)",
};

// de-DE Zahlformatierung (Tausenderpunkt, Komma). money → auf ganze Euro gerundet.
function deNum(v, money = false) {
  const f = typeof v === "number" ? v : parseFloat(v);
  if (!isFinite(f)) return null;
  const s = new Intl.NumberFormat("de-DE", {
    maximumFractionDigits: money ? 0 : 1,
  }).format(f);
  return money ? `${s} €` : s;
}

function pctChange(cur, vj) {
  const c = parseFloat(cur), v = parseFloat(vj);
  if (!isFinite(c) || !isFinite(v) || v === 0) return null;
  const p = (100 * (c - v)) / v;
  return `${p >= 0 ? "+" : ""}${p.toFixed(1)} %`;
}

// Baut aus einem Action-Ergebnis (rows) einen kompakten, vorformatierten Kurztext.
// Die KI rechnet nichts nach – sie webt diese Texte nur in die Lagebeurteilung ein.
function buildSectionText(kind, rows) {
  if (!Array.isArray(rows) || rows.length === 0) return "";

  if (kind === "platform") {
    // Nur Plattformen mit Umsatz im Zeitraum; Entwicklung ggü. Vorjahr.
    const withRev = rows.filter(r => parseFloat(r.Umsatz) > 0).slice(0, 6);
    if (!withRev.length) return "";
    return withRev.map(r => {
      const chg = pctChange(r.Umsatz, r.UmsatzVJ);
      const marge = r["DB-Marge %"];
      let line = `${r.Plattform}: ${deNum(r.Umsatz, true)}`;
      if (r.UmsatzVJ != null) line += ` (VJ ${deNum(r.UmsatzVJ, true)}${chg ? `, ${chg}` : ""})`;
      if (marge != null && isFinite(parseFloat(marge))) line += `, DB-Marge ${deNum(marge)} %`;
      return line;
    }).join("\n");
  }

  if (kind === "decline") {
    // Kunden mit rückläufigem Umsatz (Rueckgang = UmsatzVJ − Umsatz, absteigend).
    const sum = rows.reduce((a, r) => a + (parseFloat(r.Rueckgang) || 0), 0);
    const ex = rows.slice(0, 2)
      .map(r => `${r.Kunde} (−${deNum(r.Rueckgang, true)})`).join(", ");
    return `${rows.length} Kunden mit rückläufigem Umsatz, zusammen −${deNum(sum, true)} gegenüber dem Vorjahr.`
      + (ex ? ` Beispiele: ${ex}.` : "");
  }

  if (kind === "ladenhueter") {
    const sum = rows.reduce((a, r) => a + (parseFloat(r.Kapitalbindung) || 0), 0);
    const ex = rows.slice(0, 2).map(r => {
      const tage = parseFloat(r.TageOhneVerkauf);
      const t = isFinite(tage) && tage < 9999 ? `, ${deNum(tage)} Tage ohne Verkauf` : ", kein Verkauf erfasst";
      return `${r.Artikel} (${deNum(r.Kapitalbindung, true)}${t})`;
    }).join(", ");
    return `${rows.length} Ladenhüter binden zusammen ${deNum(sum, true)} Kapital.`
      + (ex ? ` Beispiele: ${ex}.` : "");
  }

  return "";
}

/**
 * Widget "ai_summary": erzeugt aus dem Ergebnis der verknüpften Action (z.B. der
 * KPI-Zeile) eine kurze KI-Management-Zusammenfassung über /api/ai/summarize-data.
 * Verbraucht KEINE eigene DB-Abfrage – es nutzt das bereits geladene Action-Ergebnis.
 *
 * Optional können über config.extra_sections weitere, bereits geladene Action-
 * Ergebnisse desselben Formulars einbezogen werden (z.B. Umsatz je Plattform,
 * Kundenrückgang, Ladenhüter). Sie werden hier vorformatiert und als »sections«
 * mitgeschickt, damit die KI eine reichere Lagebeurteilung schreibt.
 *
 * config: { width, instruction?, extra_sections?: [{action_id, label, kind}] }
 */
export default function AiSummaryWidget({ widget, result, results, onAiText }) {
  const cfg = widget.config || {};
  const rows = result?.rows || [];
  const columns = result?.columns || [];
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  // Fertigen KI-Text nach oben melden (FormRunner gibt ihn dem PDF-Report mit, damit
  // der Report den langsamen KI-Aufruf überspringt).
  useEffect(() => {
    onAiText?.(widget.action_id, text || "");
  }, [text, widget.action_id]);

  // Zusatz-Sektionen aus den übrigen Action-Ergebnissen aufbauen (leere fallen raus).
  const sections = useMemo(() => {
    const defs = Array.isArray(cfg.extra_sections) ? cfg.extra_sections : [];
    return defs
      .map(s => ({ label: s.label || "", text: buildSectionText(s.kind, (results?.[s.action_id]?.rows) || []) }))
      .filter(s => s.text);
  }, [cfg.extra_sections, results]);

  // Nur (neu) generieren, wenn sich die zugrunde liegenden Daten ändern.
  const dataKey = JSON.stringify(rows) + "|" + JSON.stringify(sections) + "|" + (cfg.instruction || "");

  useEffect(() => {
    if (!rows.length) { setText(""); setErr(null); return; }
    const ac = new AbortController();
    setLoading(true); setErr(null); setText("");

    // Beim Filterwechsel (z.B. Zeitraum) wird die noch streamende Anfrage per abort()
    // abgebrochen und sofort eine neue gestartet. Die gerade schließende SSE-Verbindung
    // kann die neue Anfrage mit "Failed to fetch" abschmieren lassen – das ist KEIN
    // echter Serverausfall. Darum bei transientem Netzwerkfehler einmal kurz verzögert
    // neu versuchen (der Retry feuert nur, wenn noch kein Token gestreamt wurde).
    async function run() {
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          await streamRequest(
            "/summarize-data",
            { label: widget.label || "", columns, rows, sections, instruction: cfg.instruction || "" },
            (_tok, full) => { if (!ac.signal.aborted) setText(full); },
            null,
            ac.signal,
          );
          return;
        } catch (e) {
          if (ac.signal.aborted || e.message === "__ABORTED__") return;
          const transient = /nicht erreichbar|Netzwerkfehler/.test(e.message);
          if (attempt === 0 && transient) {
            await new Promise(r => setTimeout(r, 500));
            if (ac.signal.aborted) return;
            continue;
          }
          setErr(e.message);
          return;
        }
      }
    }
    run().finally(() => { if (!ac.signal.aborted) setLoading(false); });
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
