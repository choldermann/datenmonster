import { ChevronRight, CheckCircle2, AlertCircle } from "lucide-react";

const AMPEL = {
  rot:    "#e05656",
  orange: "#e8913a",
  gelb:   "#e6c84f",
  gruen:  "#5cb85c",
};
const SEV_LABEL = {
  kritisch: "kritisch", warnung: "Warnung", hinweis: "Hinweis",
  info: "Info", positiv: "erfreulich",
};
const SEV_ORDER = { kritisch: 0, warnung: 1, hinweis: 2, info: 3, positiv: 4 };

function de(v, decimals = 0) {
  const n = typeof v === "number" ? v : parseFloat(v);
  if (!isFinite(n)) return null;
  return n.toLocaleString("de-DE", { maximumFractionDigits: decimals });
}

/**
 * Widget "alerts": Unternehmenswarnungen aus dem Regelwerk (Action-Typ run_alerts).
 *
 * Jede Zeile kommt fertig bewertet aus dem Backend: Severity, Anzahl und Wert
 * stammen aus SQL, nicht aus dieser Komponente – hier wird NICHTS gerechnet und
 * nichts geraten. Die Fakten unter dem Titel sind die Grundlage der Warnung und
 * stehen bewusst direkt in der Liste: eine Warnung, deren Herkunft man erst
 * aufklappen muss, wird nicht geglaubt.
 *
 * Klick auf eine Zeile öffnet – sofern die Regel einen Drilldown hinterlegt hat –
 * die zugehörige Detailliste (derselbe Weg wie beim tasklist-Widget).
 *
 * config: { width, info?, max?, hide_facts? }
 */
export default function AlertsWidget({ widget, result, onTaskClick }) {
  const cfg = widget.config || {};
  const alle = result.rows || [];
  const rows = cfg.max ? alle.slice(0, Number(cfg.max)) : alle;
  const meta = result.meta || {};

  const zaehler = {};
  for (const r of alle) {
    const s = r.severity || "warnung";
    zaehler[s] = (zaehler[s] || 0) + 1;
  }
  const kopfzeile = Object.keys(zaehler)
    .sort((a, b) => (SEV_ORDER[a] ?? 9) - (SEV_ORDER[b] ?? 9))
    .map(s => `${zaehler[s]} ${SEV_LABEL[s] || s}`)
    .join(" · ");

  if (!alle.length) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: 16,
        color: "var(--text-dim)", fontSize: 13 }}>
        <CheckCircle2 size={15} style={{ color: AMPEL.gruen }} />
        Keine offenen Warnungen – alle Prüfungen im grünen Bereich.
        {meta.checked ? (
          <span style={{ fontSize: 11 }}>({meta.checked} Regeln geprüft)</span>
        ) : null}
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
        gap: 10, padding: "8px 16px", borderBottom: "1px solid var(--border)",
        fontSize: 11, color: "var(--text-dim)" }}>
        <span>{kopfzeile}</span>
        {meta.checked ? (
          <span>{meta.checked} Regeln geprüft
            {meta.duration_ms ? ` · ${(meta.duration_ms / 1000).toFixed(1)} s` : ""}</span>
        ) : null}
      </div>

      {rows.map((r, i) => {
        const color = AMPEL[String(r.Ampel || "").toLowerCase()] || AMPEL.gelb;
        const dd = r.drilldown;
        const canClick = !!(onTaskClick && dd?.mapping_id);
        const fakten = cfg.hide_facts ? [] : (r.fakten || []);
        const wert = de(r.summe ?? r.wert, 0);
        return (
          <div key={r.rule_key || i}
            onClick={canClick ? () => onTaskClick(r, {
              mapping_id: dd.mapping_id,
              title: dd.title || r.name,
              hidden_columns: dd.hidden_columns || [],
              param: dd.param || null,
            }) : undefined}
            style={{ display: "flex", alignItems: "flex-start", gap: 12,
              padding: "11px 16px",
              borderBottom: i < rows.length - 1 ? "1px solid var(--border)" : "none",
              cursor: canClick ? "pointer" : "default" }}
            onMouseEnter={canClick ? e => e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.03)" : undefined}
            onMouseLeave={canClick ? e => e.currentTarget.style.backgroundColor = "" : undefined}>

            <span style={{ width: 11, height: 11, borderRadius: "50%", backgroundColor: color,
              flexShrink: 0, marginTop: 4, boxShadow: `0 0 8px ${color}66` }} />

            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13.5, color: "var(--text-main)", fontWeight: 600 }}>
                {r.titel || r.name}
              </div>
              {r.untertitel && (
                <div style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 2 }}>
                  {r.untertitel}
                </div>
              )}
              {fakten.length > 0 && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
                  {fakten.map((f, fi) => (
                    <span key={fi} style={{ fontSize: 11, color: "var(--text-dim)",
                      backgroundColor: "var(--bg-elevated)", border: "1px solid var(--border)",
                      borderRadius: 5, padding: "2px 7px" }}>
                      {f.label}: <b style={{ color: "var(--text-main)" }}>{f.wert}</b>
                      {f.einheit ? ` ${f.einheit}` : ""}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {wert !== null && (
              <span style={{ fontSize: 13, fontWeight: 700, color: "var(--text-bright)",
                whiteSpace: "nowrap", marginTop: 2 }}>{wert} €</span>
            )}
            {canClick && <ChevronRight size={15} style={{ color: "var(--text-dim)",
              flexShrink: 0, marginTop: 3 }} />}
          </div>
        );
      })}

      {(meta.errors || []).length > 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: 7, padding: "8px 16px",
          borderTop: "1px solid var(--border)", fontSize: 11, color: "#e07070" }}>
          <AlertCircle size={12} />
          {meta.errors.length} Regel(n) konnten nicht geprüft werden:{" "}
          {meta.errors.slice(0, 2).map(e => e.name).join(", ")}
        </div>
      )}
      {(meta.unavailable || []).length > 0 && (
        <div style={{ padding: "8px 16px", borderTop: "1px solid var(--border)",
          fontSize: 11, color: "var(--text-dim)" }}>
          {meta.unavailable.length} Regel(n) ohne installierte Auswertung übersprungen.
        </div>
      )}
    </div>
  );
}
