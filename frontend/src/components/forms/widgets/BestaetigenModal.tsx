import { useState } from "react";
import { X, AlertTriangle, Loader2, CheckCircle2 } from "lucide-react";

const S = {
  bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)", border: "var(--border)",
  textMain: "var(--text-main)", textBright: "var(--text-bright)", textDim: "var(--text-dim)",
  accent: "var(--accent)",
};

const btn = {
  display: "inline-flex", alignItems: "center", gap: 6, padding: "6px 12px",
  borderRadius: 5, border: `1px solid ${S.border}`, backgroundColor: S.bgEl,
  color: S.textMain, fontSize: 12, cursor: "pointer",
};

/**
 * Rückfrage vor einem Schritt, der sich nicht (leicht) zurücknehmen lässt.
 *
 * Bewusst mit Zahlen statt „Wirklich?": die Punkte nennen, was konkret passiert –
 * wie viele Bewertungen verloren gehen, welche Summen festgeschrieben werden.
 * Bei `gefahr` liegt der Fokus auf „Abbrechen", damit ein versehentliches Enter
 * nichts zerstört.
 *
 * `onBestaetigen` darf async sein; das Modal schließt danach von selbst.
 */
export default function BestaetigenModal({ titel, punkte = [], label = "OK", gefahr = false,
                                           onBestaetigen, onClose }) {
  const [busy, setBusy] = useState(false);
  const farbe = gefahr ? "#e07070" : S.accent;

  const los = async () => {
    setBusy(true);
    try {
      await onBestaetigen?.();
    } finally {
      setBusy(false);
      onClose();
    }
  };

  return (
    <div onClick={busy ? undefined : onClose}
      style={{ position: "fixed", inset: 0, zIndex: 1100, backgroundColor: "rgba(0,0,0,0.55)",
        display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
      <div onClick={e => e.stopPropagation()}
        style={{ width: "min(520px, 94vw)", backgroundColor: S.bgCard,
          border: `1px solid ${S.border}`, borderRadius: 12, overflow: "hidden",
          boxShadow: "0 20px 60px rgba(0,0,0,0.5)" }}>

        <div style={{ padding: "14px 18px", borderBottom: `1px solid ${S.border}`,
          display: "flex", alignItems: "center", gap: 10 }}>
          {gefahr
            ? <AlertTriangle size={15} style={{ color: farbe, flexShrink: 0 }} />
            : <CheckCircle2 size={15} style={{ color: farbe, flexShrink: 0 }} />}
          <p style={{ flex: 1, fontSize: 14, fontWeight: 700, color: S.textBright, margin: 0 }}>
            {titel}
          </p>
          <button onClick={onClose} disabled={busy}
            style={{ background: "none", border: "none", color: S.textDim,
              cursor: busy ? "default" : "pointer", padding: 2 }}>
            <X size={16} />
          </button>
        </div>

        <ul style={{ margin: 0, padding: "14px 18px 14px 34px", display: "flex",
          flexDirection: "column", gap: 6 }}>
          {punkte.filter(Boolean).map((p, i) => (
            <li key={i} style={{ fontSize: 12.5, lineHeight: 1.5, color: S.textMain }}>{p}</li>
          ))}
        </ul>

        <div style={{ padding: "12px 18px", borderTop: `1px solid ${S.border}`,
          display: "flex", justifyContent: "flex-end", gap: 10 }}>
          <button style={btn} onClick={onClose} disabled={busy} autoFocus={gefahr}>
            Abbrechen
          </button>
          <button style={{ ...btn, borderColor: farbe, color: farbe }}
                  onClick={los} disabled={busy} autoFocus={!gefahr}>
            {busy && <Loader2 size={13} className="spin" />} {label}
          </button>
        </div>
      </div>
    </div>
  );
}
