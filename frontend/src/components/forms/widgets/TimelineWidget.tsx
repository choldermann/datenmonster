// Zeitleiste: Buchungen senkrecht untereinander, Zugänge links, Abgänge rechts,
// in der Mitte der Bestand nach der Buchung. Gedacht für die Artikelhistorie im
// Lager-Cockpit, aber nicht daran gebunden – alles über Spaltennamen konfiguriert.
//
// config: { date_column, qty_column, stock_column, title_column,
//           detail_columns: [], height, total_column }
// Das Vorzeichen von qty_column entscheidet die Seite (> 0 links, < 0 rechts).

const S = {
  textDim: "var(--text-dim)", textBright: "var(--text-bright)", textMain: "var(--text-main)",
  border: "var(--border)", bgEl: "var(--bg-elevated)", bgCard: "var(--bg-card)",
};

const zahl = (v) => Number(v ?? 0).toLocaleString("de-DE", { maximumFractionDigits: 2 });

// „2026-09-02 15:22“ oder ISO → { tag: "02.09.2026", zeit: "15:22" }
function zerlege(v) {
  const s = String(v ?? "");
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/);
  if (!m) return { tag: s, zeit: "" };
  return { tag: `${m[3]}.${m[2]}.${m[1]}`, zeit: m[4] ? `${m[4]}:${m[5]}` : "" };
}

function Karte({ row, cfg, menge, seite, tag, zeit }) {
  const farbe = seite === "links" ? "var(--ok)" : "var(--err-soft)";
  const details = (cfg.detail_columns || [])
    .map(c => [c, row[c]]).filter(([, v]) => v !== null && v !== undefined && v !== "");
  return (
    <div style={{
      backgroundColor: S.bgEl, borderRadius: 8, padding: "8px 12px", fontSize: 12,
      border: `1px solid color-mix(in srgb, ${farbe} 35%, transparent)`,
      textAlign: seite === "links" ? "right" : "left", maxWidth: 340,
      marginLeft: seite === "links" ? "auto" : 0,
    }}>
      <div style={{ display: "flex", gap: 8, alignItems: "baseline",
        flexDirection: seite === "links" ? "row-reverse" : "row" }}>
        <span style={{ color: farbe, fontWeight: 700, fontSize: 15 }}>
          {menge > 0 ? "+" : "−"}{zahl(Math.abs(menge))}
        </span>
        {cfg.title_column && <span style={{ color: S.textBright }}>{row[cfg.title_column]}</span>}
        <span style={{ color: S.textDim, fontSize: 11, whiteSpace: "nowrap" }}>
          {tag}{zeit ? ` · ${zeit}` : ""}
        </span>
      </div>
      {details.map(([c, v]) => (
        <div key={c} style={{ color: S.textMain, marginTop: 2, overflowWrap: "anywhere" }}
          title={c}>{String(v)}</div>
      ))}
    </div>
  );
}

export default function TimelineWidget({ widget, result }) {
  const { rows = [] } = result;
  const cfg = widget.config || {};
  const { date_column, qty_column, stock_column } = cfg;

  if (!date_column || !qty_column) return (
    <div style={{ padding: "32px 20px", textAlign: "center", color: S.textDim, fontSize: 12 }}>
      date_column und qty_column konfigurieren
    </div>
  );
  if (!rows.length) return (
    <div style={{ padding: "32px 20px", textAlign: "center", color: S.textDim, fontSize: 12 }}>
      Keine Buchungen im Zeitraum
    </div>
  );

  // total_column: Gesamtzahl vor dem Zeilenlimit – eine gekürzte Liste sagt es.
  const gesamt = cfg.total_column ? Number(rows[0]?.[cfg.total_column] ?? 0) : 0;
  let letzterTag = null;
  return (
    <div style={{ maxHeight: cfg.height || 640, overflowY: "auto", padding: "12px 8px",
      position: "relative" }}>
      {gesamt > rows.length && (
        <div style={{ fontSize: 11, color: "var(--warn)", textAlign: "center", marginBottom: 6 }}>
          Angezeigt werden die neuesten {zahl(rows.length)} von {zahl(gesamt)} Buchungen –
          für ältere den Zeitraum eingrenzen.
        </div>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 96px 1fr", fontSize: 11,
        color: S.textDim, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8,
        position: "sticky", top: -12, background: S.bgCard, zIndex: 2, padding: "4px 0" }}>
        <div style={{ textAlign: "right", color: "var(--ok)" }}>Zugänge</div>
        <div style={{ textAlign: "center" }}>Bestand</div>
        <div style={{ color: "var(--err-soft)" }}>Abgänge</div>
      </div>
      {rows.map((row, i) => {
        const menge = Number(row[qty_column] ?? 0);
        const { tag, zeit } = zerlege(row[date_column]);
        const neuerTag = tag !== letzterTag;
        letzterTag = tag;
        const bestand = stock_column ? row[stock_column] : null;
        const leer = bestand !== null && Number(bestand) <= 0;
        return (
          <div key={i}>
            {neuerTag && (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 96px 1fr" }}>
                <div />
                <div style={{ display: "flex", justifyContent: "center", position: "relative",
                  padding: "10px 0 6px" }}>
                  <div style={{ position: "absolute", top: 0, bottom: 0, left: "50%", width: 2,
                    marginLeft: -1, background: S.border }} />
                  <span style={{ position: "relative", fontSize: 11, fontWeight: 600,
                    color: S.textBright, background: S.bgEl, border: `1px solid ${S.border}`,
                    borderRadius: 4, padding: "2px 8px", whiteSpace: "nowrap" }}>{tag}</span>
                </div>
                <div />
              </div>
            )}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 96px 1fr",
              alignItems: "center", minHeight: 44 }}>
              <div style={{ padding: "4px 0" }}>
                {menge > 0 && <Karte row={row} cfg={cfg} menge={menge} seite="links" tag={tag} zeit={zeit} />}
              </div>
              <div style={{ position: "relative", alignSelf: "stretch", display: "flex",
                alignItems: "center", justifyContent: "center" }}>
                <div style={{ position: "absolute", top: 0, bottom: 0, left: "50%", width: 2,
                  marginLeft: -1, background: S.border }} />
                {/* Verbindung zur Karte */}
                <div style={{ position: "absolute", top: "50%", height: 2, marginTop: -1,
                  width: "50%", left: menge > 0 ? 0 : "50%",
                  background: menge > 0 ? "color-mix(in srgb, var(--ok) 40%, transparent)"
                    : "color-mix(in srgb, var(--err-soft) 40%, transparent)" }} />
                {bestand !== null && (
                  <span title="Bestand nach der Buchung" style={{
                    position: "relative", zIndex: 1, minWidth: 40, textAlign: "center",
                    padding: "3px 8px", borderRadius: 999, fontSize: 12, fontWeight: 600,
                    background: S.bgCard, color: leer ? "var(--warn)" : S.textBright,
                    border: `2px solid ${leer ? "var(--warn)" : "var(--accent)"}`,
                  }}>{zahl(bestand)}</span>
                )}
              </div>
              <div style={{ padding: "4px 0" }}>
                {menge < 0 && <Karte row={row} cfg={cfg} menge={menge} seite="rechts" tag={tag} zeit={zeit} />}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
