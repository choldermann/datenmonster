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

// Einheit einer KPI-Spalte grob aus dem (deutschen) Spaltennamen ableiten, damit
// die KI Euro/Prozent/Tage nicht verwechselt.
function unitFor(col) {
  const c = String(col).toLowerCase();
  if (/%|anteil|quote|marge/.test(c)) return "%";
  if (/tage|dso|zahldauer/.test(c)) return "Tage";
  if (/umsatz|kapital|offen|ertrag|db2|db ii|auftrag|einsatz|prognose|ytd|vorjahr|ladenh|versand|forderung|wert/.test(c)) return "€";
  return "";
}

function fmtVal(v, unit) {
  const money = unit === "€";
  const n = deNum(v, money);
  if (n == null) return "–";
  if (unit === "%") return `${n} %`;
  if (unit === "Tage") return `${n} Tage`;
  return n; // deNum(money) hängt bereits " €" an
}

function num(v) { const f = parseFloat(v); return isFinite(f) ? f : null; }
function pctNum(cur, vj) { const c = num(cur), v = num(vj); return (c == null || v == null || v === 0) ? null : (100 * (c - v)) / v; }
function signPct(p) { return p == null ? "–" : `${p >= 0 ? "+" : ""}${p.toFixed(1)} %`; }

// Deterministische Bewertung "gut / verbesserungswürdig" je Cockpit-Bereich – direkt
// aus den (strukturierten) KPI-Ergebnissen aller Reiter. Bewusst NICHT vom LLM: so ist
// die Tabelle immer vorhanden, korrekt und stabil; das Modell schreibt nur die Prosa.
function buildAssessment(results) {
  const rowsOf = id => (results?.[id]?.rows) || [];
  const one = id => rowsOf(id)[0] || null;
  const out = [];

  const ov = one("act_overview_kpi");
  if (ov) {
    const p = pctNum(ov.Umsatz, ov.UmsatzVJ);
    out.push({ bereich: "Ertragslage", good: (p == null || p >= 0),
      kommentar: `Umsatz ${signPct(p)} ggü. Vorjahr, DB II-Marge ${deNum(ov.DB2Marge)} %` });
  }
  const kk = one("act_kunden_kpi");
  const decl = rowsOf("act_kunden_rueckgang");
  if (kk || decl.length) {
    const ap = ov ? pctNum(ov.AktiveKunden, ov.AktiveKundenVJ) : null;
    const declSum = decl.reduce((a, r) => a + (num(r.Rueckgang) || 0), 0);
    const good = (ap == null || ap >= 0) && decl.length <= 5;
    out.push({ bereich: "Kunden", good,
      kommentar: `${kk?.Neukunden != null ? deNum(kk.Neukunden) + " Neukunden, " : ""}${decl.length} Kunden rückläufig (−${deNum(declSum, true)})` });
  }
  const zm = one("act_zm_kpi"), op = one("act_op_kpi");
  if (zm || op) {
    const zd = zm ? num(zm.ZahldauerTage) : null, zdv = zm ? num(zm.ZahldauerTageVJ) : null;
    const uq = op ? num(op.UeberfaelligQuote) : null;
    const good = (zd == null || zdv == null || zd <= zdv) && (uq == null || uq < 25);
    const parts = [];
    if (op) { parts.push(`überfällig ${deNum(op.UeberfaelligQuote)} %`); if (op.DSO != null) parts.push(`DSO ${deNum(op.DSO)}`); }
    if (zm) parts.push(`Zahldauer ${deNum(zm.ZahldauerTage)} Tage`);
    out.push({ bereich: "Liquidität", good, kommentar: parts.join(", ") });
  }
  const kap = one("act_kapital_kpi");
  if (kap) {
    const bind = num(kap.Kapitalbindung), lh = num(kap.LadenhueterKapital);
    const share = (bind && lh != null) ? lh / bind : null;
    out.push({ bereich: "Kapital & Lager", good: (share == null || share < 0.15),
      kommentar: `${deNum(kap.Kapitalbindung, true)} gebunden, davon ${deNum(kap.LadenhueterKapital, true)} Ladenhüter` });
  }
  const kl = one("act_klumpen_kpi");
  if (kl) {
    const t5 = num(kl.Top5KundenAnteil);
    out.push({ bereich: "Risiko", good: (t5 == null || t5 < 30),
      kommentar: `Top-5-Kunden ${deNum(kl.Top5KundenAnteil)} %, Top-10 ${deNum(kl.Top10KundenAnteil)} %` });
  }
  const fc = one("act_forecast");
  const churnN = rowsOf("act_churn").length;
  if (fc) {
    const pv = num(fc["Prognose vs VJ %"]);
    out.push({ bereich: "Ausblick", good: (pv == null || pv >= 0),
      kommentar: `Prognose ${signPct(pv)} ggü. Vorjahr${churnN ? `, ${churnN} schlafende Kunden` : ""}` });
  }
  const rt = one("act_retouren_kpi");
  if (rt) {
    const q = num(rt.Quote), qvj = num(rt.QuoteVJ);
    // Eine niedrige Retourenquote ist generell gut (absolut, < 5 %); erst darüber
    // zählt zusätzlich, ob sie ggü. Vorjahr nicht gestiegen ist. So wird eine winzige
    // Quote (z.B. 0,4 %) nicht wegen eines minimalen VJ-Anstiegs als schlecht markiert.
    const RET_QUOTE_OK = 5;
    const good = (q == null) || (q < RET_QUOTE_OK) || (qvj != null && q <= qvj);
    const chg = pctNum(q, qvj);
    out.push({ bereich: "Retouren", good,
      kommentar: `Retourenquote ${deNum(rt.Quote)} % (VJ ${deNum(rt.QuoteVJ)} %${chg != null ? `, ${signPct(chg)}` : ""}), `
        + `Wert ${deNum(rt.Wert, true)}` });
  }
  return out;
}

// Generische KPI-Zeile (eine Ergebniszeile) vorformatieren: "Name: Wert (VJ …, ±%)".
// Vorjahreswerte werden über die Spalte Name+"VJ" gepaart und übersprungen.
function buildKpiText(rows) {
  if (!Array.isArray(rows) || rows.length === 0) return "";
  const row = rows[0];
  const keys = Object.keys(row);
  const vjKeys = new Set(keys.filter(k => /vj$/i.test(k)));
  const lines = [];
  for (const k of keys) {
    if (vjKeys.has(k)) continue;
    if (/^kkunde$|^kartikel$/i.test(k)) continue;
    const unit = unitFor(k);
    let line = `${k}: ${fmtVal(row[k], unit)}`;
    const vj = row[k + "VJ"];
    const chg = vj != null ? pctChange(row[k], vj) : null;
    if (vj != null && chg) line += ` (VJ ${fmtVal(vj, unit)}, ${chg})`;
    lines.push(line);
  }
  return lines.join("\n");
}

// Baut aus einem Action-Ergebnis (rows) einen kompakten, vorformatierten Kurztext.
// Die KI rechnet nichts nach – sie webt diese Texte nur in die Lagebeurteilung ein.
function buildSectionText(kind, rows) {
  if (!Array.isArray(rows) || rows.length === 0) return "";

  if (kind === "kpi") return buildKpiText(rows);

  if (kind === "churn") {
    const sum = rows.reduce((a, r) => a + (parseFloat(r["Umsatz 24M"]) || 0), 0);
    const ex = rows.slice(0, 2).map(r => {
      const tage = parseFloat(r["Tage inaktiv"]);
      const t = isFinite(tage) ? `, ${deNum(tage)} Tage inaktiv` : "";
      return `${r.Kunde} (${deNum(r["Umsatz 24M"], true)}${t})`;
    }).join(", ");
    return `${rows.length} früher regelmäßige Kunden sind inaktiv geworden, zusammen ${deNum(sum, true)} Umsatz (24 Monate).`
      + (ex ? ` Beispiele: ${ex}.` : "");
  }

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

// Fettschrift **…** inline auflösen.
function renderInline(s, keyBase) {
  return String(s).split(/(\*\*[^*]+\*\*)/g).map((p, i) => {
    const m = /^\*\*([^*]+)\*\*$/.exec(p);
    return m
      ? <strong key={`${keyBase}-${i}`} style={{ color: S.textMain }}>{m[1]}</strong>
      : <span key={`${keyBase}-${i}`}>{p}</span>;
  });
}

const SEP_RE = /^:?-{2,}:?$/;

// Sehr schlanker Markdown-Renderer (nur was der Report-Prompt erzeugt):
// ## Überschriften, Absätze mit **fett**, und eine Pipe-Tabelle. Wird laufend
// beim Streamen neu geparst – halbe Tabellenzeilen erscheinen erst, wenn vollständig.
function MiniMarkdown({ text }) {
  const lines = String(text).split("\n");
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (/^\s*$/.test(line)) { i++; continue; }
    if (/^##\s+/.test(line)) { blocks.push({ type: "h", text: line.replace(/^#+\s+/, "") }); i++; continue; }
    if (/^\s*\|/.test(line)) {
      const rows = [];
      while (i < lines.length && /^\s*\|/.test(lines[i])) {
        const cells = lines[i].trim().replace(/^\|/, "").replace(/\|\s*$/, "").split("|").map(c => c.trim());
        if (!cells.every(c => c === "" || SEP_RE.test(c))) rows.push(cells);
        i++;
      }
      if (rows.length) blocks.push({ type: "table", rows });
      continue;
    }
    const para = [];
    while (i < lines.length && !/^\s*$/.test(lines[i]) && !/^##\s+/.test(lines[i]) && !/^\s*\|/.test(lines[i])) {
      para.push(lines[i]); i++;
    }
    blocks.push({ type: "p", text: para.join(" ") });
  }

  return (
    <div style={{ fontSize: 13.5, lineHeight: 1.6, color: S.textMain }}>
      {blocks.map((b, bi) => {
        if (b.type === "h") return (
          <div key={bi} style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.05em",
            textTransform: "uppercase", color: S.accent, margin: bi ? "14px 0 6px" : "0 0 6px" }}>
            {b.text}
          </div>
        );
        if (b.type === "p") return (
          <p key={bi} style={{ margin: "0 0 6px" }}>{renderInline(b.text, `p${bi}`)}</p>
        );
        // table
        const [head, ...body] = b.rows;
        return (
          <table key={bi} style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, margin: "4px 0 6px" }}>
            <thead>
              <tr>{head.map((c, ci) => (
                <th key={ci} style={{ textAlign: "left", padding: "5px 8px", borderBottom: "2px solid var(--border)",
                  color: S.textDim, fontWeight: 600, whiteSpace: "nowrap" }}>{renderInline(c, `h${bi}-${ci}`)}</th>
              ))}</tr>
            </thead>
            <tbody>
              {body.map((r, ri) => (
                <tr key={ri}>{r.map((c, ci) => (
                  <td key={ci} style={{ padding: "5px 8px", borderBottom: "1px solid var(--border)",
                    verticalAlign: "top", whiteSpace: ci === 1 ? "nowrap" : "normal" }}>{renderInline(c, `c${bi}-${ri}-${ci}`)}</td>
                ))}</tr>
              ))}
            </tbody>
          </table>
        );
      })}
    </div>
  );
}

// Bewertungstabelle (deterministisch, siehe buildAssessment).
function AssessmentTable({ rows }) {
  if (!rows?.length) return null;
  return (
    <div style={{ marginTop: 14 }}>
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.05em",
        textTransform: "uppercase", color: S.accent, margin: "0 0 6px" }}>
        Bewertung
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr>
            {["Bereich", "Status", "Kommentar"].map((h, i) => (
              <th key={i} style={{ textAlign: "left", padding: "5px 8px",
                borderBottom: "2px solid var(--border)", color: S.textDim, fontWeight: 600, whiteSpace: "nowrap" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td style={{ padding: "5px 8px", borderBottom: "1px solid var(--border)",
                fontWeight: 600, color: S.textMain, whiteSpace: "nowrap" }}>{r.bereich}</td>
              <td style={{ padding: "5px 8px", borderBottom: "1px solid var(--border)", whiteSpace: "nowrap",
                color: r.good ? "#3f9d5a" : "#c98a1c", fontWeight: 600 }}>
                {r.good ? "👍 gut" : "⚠️ verbesserungswürdig"}
              </td>
              <td style={{ padding: "5px 8px", borderBottom: "1px solid var(--border)", color: S.textMain }}>{r.kommentar}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
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

  // Fertigen KI-Text + Lade-Status nach oben melden: FormRunner gibt den Text dem
  // PDF-Report mit (Report überspringt so den langsamen KI-Aufruf) und sperrt den
  // Report-Button, solange die Analyse noch streamt.
  useEffect(() => {
    onAiText?.(widget.action_id, text || "", loading);
  }, [text, loading, widget.action_id]);

  // Zusatz-Sektionen aus den übrigen Action-Ergebnissen aufbauen (leere fallen raus).
  const sections = useMemo(() => {
    const defs = Array.isArray(cfg.extra_sections) ? cfg.extra_sections : [];
    return defs
      .map(s => ({ label: s.label || "", text: buildSectionText(s.kind, (results?.[s.action_id]?.rows) || []) }))
      .filter(s => s.text);
  }, [cfg.extra_sections, results]);

  // Bewertungstabelle (nur im Report-Layout) – rein aus den Daten, unabhängig vom LLM.
  const assessment = useMemo(
    () => (cfg.report_layout ? buildAssessment(results) : []),
    [cfg.report_layout, results],
  );

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
            { label: widget.label || "", columns, rows, sections,
              instruction: cfg.instruction || "",
              layout: cfg.report_layout ? "report" : "prose" },
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
        cfg.report_layout ? (
          <>
            <MiniMarkdown text={text} />
            <AssessmentTable rows={assessment} />
          </>
        ) : (
          <p style={{ fontSize: 13.5, lineHeight: 1.65, color: S.textMain, margin: 0, whiteSpace: "pre-wrap" }}>
            {text}
          </p>
        )
      ) : (
        cfg.report_layout && assessment.length ? (
          <AssessmentTable rows={assessment} />
        ) : (
          <p style={{ fontSize: 12, color: S.textDim, margin: 0 }}>
            KI erstellt die Analyse … (kann beim ersten Mal einige Sekunden dauern)
          </p>
        )
      )}
    </div>
  );
}
