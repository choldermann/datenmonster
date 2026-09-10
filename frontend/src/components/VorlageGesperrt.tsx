import { useState } from "react";
import { Lock, ExternalLink, RefreshCw, Loader2 } from "lucide-react";
import api, { fehlerText } from "../api/client";

/**
 * Hinweis anstelle einer Auswertung, deren Vorlage keine laufende Berechtigung mehr hat
 * (Testphase abgelaufen, Abo beendet).
 *
 * Bewusst kein Fehler in Rot: der Kunde hat nichts falsch gemacht, es fehlt nur der
 * Kauf. Deshalb Ton und Aufbau eines Angebots — was fehlt, was es kostet, ein Weg
 * dorthin — und der ausdrueckliche Satz, dass nichts verloren ist.
 */
export default function VorlageGesperrt({ sperre, onErneutGeprueft, darfPruefen = true }) {
  const [pruefe, setPruefe] = useState(false);
  const [hinweis, setHinweis] = useState("");

  if (!sperre) return null;
  const angebote = sperre.angebote || [];
  const istTest = sperre.art === "test";

  const preis = (a) => {
    if (a.price_monthly) return `${a.price_monthly.toFixed(0)} € / Monat`;
    if (a.price_yearly)  return `${a.price_yearly.toFixed(0)} € / Jahr`;
    return "";
  };

  async function erneutPruefen() {
    setPruefe(true); setHinweis("");
    try {
      const { data } = await api.post("/api/templates/berechtigung/pruefen");
      if ((data?.gesperrt ?? 0) === 0) {
        setHinweis("Berechtigung bestätigt — die Auswertung ist wieder frei.");
        onErneutGeprueft?.();
      } else {
        setHinweis("Der Lizenzserver meldet weiterhin keine Berechtigung.");
      }
    } catch (e) {
      setHinweis(fehlerText(e, "Prüfung nicht möglich."));
    } finally {
      setPruefe(false);
    }
  }

  return (
    <div style={{
      maxWidth: 620, margin: "40px auto", padding: 24, borderRadius: 10,
      background: "var(--bg-card)", border: "1px solid var(--border)",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
        <div style={{
          width: 34, height: 34, borderRadius: 8, display: "flex", alignItems: "center",
          justifyContent: "center", background: "var(--accent-dim)", color: "var(--accent)",
          border: "1px solid var(--accent-line)",
        }}>
          <Lock size={16} />
        </div>
        <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: "var(--text-bright)" }}>
          {istTest ? "Testphase abgelaufen" : "Keine laufende Lizenz"}
        </h2>
      </div>

      <p style={{ margin: "0 0 18px", fontSize: 13, lineHeight: 1.6, color: "var(--text-main)" }}>
        {sperre.message || sperre.grund}
      </p>

      {angebote.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
          {angebote.map(a => (
            <a key={a.slug} href={a.url} target="_blank" rel="noreferrer"
              style={{
                display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12,
                padding: "10px 14px", borderRadius: 8, textDecoration: "none",
                background: "var(--bg-elevated)", border: "1px solid var(--border)",
                color: "var(--text-bright)", fontSize: 13,
              }}>
              <span style={{ fontWeight: 600 }}>{a.name}</span>
              <span style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--accent)", fontSize: 12 }}>
                {preis(a)} <ExternalLink size={13} />
              </span>
            </a>
          ))}
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        {darfPruefen && (
        <button onClick={erneutPruefen} disabled={pruefe}
          title="Nach dem Kauf: Berechtigung sofort neu beim Lizenzserver erfragen"
          style={{
            display: "flex", alignItems: "center", gap: 6, padding: "6px 12px", borderRadius: 6,
            background: "transparent", border: "1px solid var(--border)",
            color: "var(--text-dim)", fontSize: 12, cursor: pruefe ? "wait" : "pointer",
          }}>
          {pruefe ? <Loader2 size={12} style={{ animation: "spin 1s linear infinite" }} />
                  : <RefreshCw size={12} />}
          Bereits gekauft? Erneut prüfen
        </button>
        )}
        {hinweis && (
          <span style={{ fontSize: 12, color: "var(--text-dim)" }}>{hinweis}</span>
        )}
      </div>
    </div>
  );
}

/** Kleine Marke für Listen und Kacheln. */
export function GesperrtMarke({ sperre }) {
  if (!sperre) return null;
  return (
    <span title={sperre.grund || sperre.message}
      style={{
        display: "inline-flex", alignItems: "center", gap: 4, padding: "1px 7px",
        borderRadius: 4, fontSize: 10, fontWeight: 700, letterSpacing: 0.3,
        background: "var(--accent-dim)", color: "var(--accent)", border: "1px solid var(--accent-line)",
      }}>
      <Lock size={9} /> {sperre.art === "test" ? "TEST ABGELAUFEN" : "NICHT LIZENZIERT"}
    </span>
  );
}
