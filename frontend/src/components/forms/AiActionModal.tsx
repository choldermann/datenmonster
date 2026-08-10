import { useState, useEffect } from "react";
import { X, Sparkles, Loader2, AlertCircle, TrendingDown } from "lucide-react";
import api from "../../api/client";
import { streamRequest } from "../../services/aiService";

const S = {
  bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)", border: "var(--border)",
  textMain: "var(--text-main)", textBright: "var(--text-bright)", textDim: "var(--text-dim)",
  accent: "var(--accent)",
};
const ACCENT = "#fce499";

function fmtNum(v, digits = 0) {
  const n = typeof v === "number" ? v : parseFloat(v);
  if (!isFinite(n)) return "–";
  return n.toLocaleString("de-DE", { maximumFractionDigits: digits });
}

// Fakten-Kacheln je Aktionstyp: [Label, Wert-aus-Zeile-oder-meta].
function factChips(kind, row, meta) {
  if (kind === "customer_winback") {
    const chips = [
      ["Letzte Bestellung", row.LetzteBestellung ?? "–"],
      ["Tage inaktiv", fmtNum(row.TageInaktiv)],
      ["Bestellungen", fmtNum(row.BestellungenGesamt)],
      ["Umsatz gesamt", fmtNum(row.UmsatzGesamt) + " €"],
    ];
    if (meta?.top_percent != null) chips.push(["Kundenrang", `Top ${meta.top_percent} %`]);
    return chips;
  }
  if (kind === "region_potential") {
    const chips = [
      ["Auftragseingang", fmtNum(row.Umsatz) + " €"],
      ["Vorjahr", fmtNum(row.UmsatzVJ) + " €"],
      ["Umsatzanteil", fmtNum(row.UmsatzAnteil, 1) + " %"],
      ["Bevölkerungsanteil", fmtNum(row.BevoelkerungsAnteil, 1) + " %"],
      ["Aktive Kunden", fmtNum(row.Kunden)],
      ["Kunden rückläufig", fmtNum(row.KundenRueckgang)],
    ];
    if (meta?.bewertung) chips.push(["Bewertung", meta.bewertung]);
    return chips;
  }
  // article_liquidation
  const chips = [
    ["Lagerbestand", fmtNum(row.Bestand) + " Stk"],
    ["Lagerreichweite", meta?.reichweite == null ? "kein Absatz" : fmtNum(meta.reichweite) + " Tage"],
    ["Tage o. Verkauf", fmtNum(row.TageOhneVerkauf)],
    ["Gebundenes Kapital", fmtNum(row.Kapitalbindung) + " €"],
  ];
  if (row.MargeProzent != null) chips.push(["Marge", fmtNum(row.MargeProzent, 1) + " %"]);
  return chips;
}

/**
 * Modal für die KI-Handlungsempfehlung zu einer einzelnen Widget-Zeile.
 * 1) holt die Fakten per Analyse-Mapping (/api/forms/drilldown),
 * 2) streamt die Empfehlung + die serverseitig berechnete Kennzahl (meta)
 *    von /api/ai/recommend-action.
 */
export default function AiActionModal({ kind, label, title, factsMapping, keyParam,
  keyValue, baseParams = {}, onClose }) {
  const [row, setRow] = useState(null);
  const [meta, setMeta] = useState(null);
  const [text, setText] = useState("");
  const [phase, setPhase] = useState("facts");   // facts | ai | done | error
  const [error, setError] = useState(null);

  useEffect(() => {
    const ac = new AbortController();
    (async () => {
      // 1) Fakten laden
      let factRow;
      try {
        const params = { ...baseParams, [keyParam]: keyValue };
        const { data } = await api.post("/api/forms/drilldown", { mapping_id: factsMapping, params });
        factRow = (data.rows || [])[0];
        if (!factRow) { setError("Keine Detaildaten für diese Auswahl gefunden."); setPhase("error"); return; }
        setRow(factRow); setPhase("ai");
      } catch (e) {
        setError(e.response?.data?.detail || e.message); setPhase("error"); return;
      }
      // 2) KI-Empfehlung streamen
      try {
        await streamRequest(
          "/recommend-action",
          { kind, label: label || "", columns: Object.keys(factRow), rows: [factRow] },
          (_tok, full) => { if (!ac.signal.aborted) setText(full); },
          (m) => { if (!ac.signal.aborted) setMeta(m); },
          ac.signal,
        );
        if (!ac.signal.aborted) setPhase("done");
      } catch (e) {
        if (ac.signal.aborted || e.message === "__ABORTED__") return;
        setError(e.message); setPhase("error");
      }
    })();
    return () => ac.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [factsMapping, keyValue, kind]);

  // Hervorgehobene Kennzahl (rechts oben): Wahrscheinlichkeit bzw. Kapitalfreisetzung.
  const primary = kind === "customer_winback"
    ? (meta?.probability != null ? { val: `${meta.probability} %`, cap: "Rückgewinnung" } : null)
    : kind === "region_potential"
    ? (meta?.marktdurchdringung != null
        ? { val: `${fmtNum(meta.marktdurchdringung, 2)}`, cap: "Marktdurchdringung" } : null)
    : (meta?.capital_release != null ? { val: `${fmtNum(meta.capital_release)} €`, cap: "Kapitalfreisetzung" } : null);
  const discount = kind === "article_liquidation" && meta?.discount != null ? meta.discount : null;

  const chips = row ? factChips(kind, row, meta) : [];

  return (
    <div onClick={onClose}
      style={{ position: "fixed", inset: 0, zIndex: 1000, backgroundColor: "rgba(0,0,0,0.55)",
        display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
      <div onClick={e => e.stopPropagation()}
        style={{ width: "min(560px, 94vw)", maxHeight: "88vh", backgroundColor: S.bgCard,
          border: `1px solid ${S.border}`, borderRadius: 12, display: "flex", flexDirection: "column",
          overflow: "hidden", boxShadow: "0 20px 60px rgba(0,0,0,0.5)" }}>

        {/* Header */}
        <div style={{ padding: "14px 18px", borderBottom: `1px solid ${S.border}`,
          display: "flex", alignItems: "flex-start", gap: 12 }}>
          <span style={{ width: 10, height: 10, borderRadius: "50%", backgroundColor: "#e05656",
            marginTop: 5, flexShrink: 0 }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase",
              color: S.textDim, margin: 0 }}>{title || "KI-Handlungsempfehlung"}</p>
            <p style={{ fontSize: 15, fontWeight: 700, color: S.textBright, margin: "3px 0 0",
              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</p>
          </div>
          {primary && (
            <div style={{ textAlign: "right", flexShrink: 0 }}>
              <div style={{ fontSize: 22, fontWeight: 800, color: ACCENT, lineHeight: 1 }}>{primary.val}</div>
              <div style={{ fontSize: 9.5, color: S.textDim, textTransform: "uppercase",
                letterSpacing: "0.05em", marginTop: 3 }}>{primary.cap}</div>
            </div>
          )}
          <button onClick={onClose} style={{ background: "none", border: "none", color: S.textDim,
            cursor: "pointer", padding: 2, flexShrink: 0 }}><X size={16} /></button>
        </div>

        <div style={{ overflow: "auto", padding: 18, display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Fakten-Kacheln */}
          {phase === "facts" ? (
            <div style={{ display: "flex", alignItems: "center", gap: 10, color: S.textDim, fontSize: 12 }}>
              <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} /> Fakten werden ermittelt…
            </div>
          ) : chips.length > 0 && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 8 }}>
              {chips.map(([cap, val]) => (
                <div key={cap} style={{ backgroundColor: S.bgEl, border: `1px solid ${S.border}`,
                  borderRadius: 8, padding: "8px 11px" }}>
                  <div style={{ fontSize: 9.5, color: S.textDim, textTransform: "uppercase",
                    letterSpacing: "0.04em" }}>{cap}</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: S.textMain, marginTop: 2 }}>{val}</div>
                </div>
              ))}
            </div>
          )}

          {discount != null && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5,
              color: S.textMain, backgroundColor: `${ACCENT}12`, border: `1px solid ${ACCENT}33`,
              borderRadius: 8, padding: "9px 12px" }}>
              <TrendingDown size={15} style={{ color: ACCENT, flexShrink: 0 }} />
              Empfohlener Rabatt: <strong style={{ color: ACCENT }}>{discount} %</strong>
            </div>
          )}

          {kind === "region_potential" && meta?.potenzial != null && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5,
              color: S.textMain, backgroundColor: `${ACCENT}12`, border: `1px solid ${ACCENT}33`,
              borderRadius: 8, padding: "9px 12px" }}>
              <TrendingDown size={15} style={{ color: ACCENT, flexShrink: 0, transform: "rotate(180deg)" }} />
              Rechnerisches Zusatzpotenzial bei durchschnittlicher Erschließung:&nbsp;
              <strong style={{ color: ACCENT }}>{fmtNum(meta.potenzial)} €</strong>
            </div>
          )}

          {/* KI-Empfehlung */}
          {phase !== "facts" && (
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8,
                fontSize: 10, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase",
                color: S.accent }}>
                <Sparkles size={12} /> KI-Empfehlung
                {phase === "ai" && <Loader2 size={11} style={{ animation: "spin 1s linear infinite", color: S.textDim }} />}
              </div>
              {phase === "error" ? (
                <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#e07070", fontSize: 12.5 }}>
                  <AlertCircle size={14} /> {error}
                </div>
              ) : text ? (
                <p style={{ fontSize: 13.5, lineHeight: 1.65, color: S.textMain, margin: 0, whiteSpace: "pre-wrap" }}>{text}</p>
              ) : (
                <p style={{ fontSize: 12, color: S.textDim, margin: 0 }}>
                  KI formuliert die Empfehlung … (kann beim ersten Mal einige Sekunden dauern)
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
