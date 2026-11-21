// Kurze Einführung in den Baukasten – erscheint beim ersten Öffnen, danach über „?“ im Kopf.
import { useState } from "react";

const SCHRITTE = [
  { titel: "Willkommen im Baukasten", text: "Hier baust du Auswertungen aus Steinen – ohne SQL. Jeder Stein ist ein Schritt: Tabelle wählen, filtern, verknüpfen, zusammenfassen, sortieren. Die Form zeigt, wohin ein Stein passt." },
  { titel: "Bausteine links", text: "Klick einen Baustein an oder zieh ihn auf die Fläche – die passenden Stellen leuchten. Wählst du einen Stein auf der Fläche aus, leuchten links die Bausteine, die dort passen, und darunter steht, was der Stein macht." },
  { titel: "Zahlen an jedem Stein", text: "Die Zahl zeigt, wie viele Zeilen an dieser Stelle ankommen und weitergehen. Ein Klick darauf zeigt die Zeilen rechts in der Vorschau – als Tabelle, Balken oder Linie." },
  { titel: "Schnell starten", text: "Oben kannst du mit einem fertigen Rezept beginnen oder in eigenen Worten beschreiben, was du sehen willst – die KI legt dann die Steine, und du kannst jeden einzelnen ändern." },
  { titel: "Ins Cockpit", text: "Im letzten Stein „Ergebnis“ wählst du Tabelle, Balken, Linie oder Kachel und das Cockpit. „Speichern“ legt die Auswertung an und stellt sie direkt dorthin. Vertippt? Strg+Z macht jeden Schritt rückgängig." },
];

export const TOUR_KEY = "dm-baukasten-tour-gesehen";

export default function Tour({ onEnde }: { onEnde: () => void }) {
  const [n, setN] = useState(0);
  const s = SCHRITTE[n];
  const ende = () => { try { localStorage.setItem(TOUR_KEY, "1"); } catch { /* privat/gesperrt */ } onEnde(); };
  return (
    <div role="dialog" aria-modal="true" aria-label="Einführung Baukasten" onClick={(e) => e.stopPropagation()}
      style={{ position: "fixed", inset: 0, zIndex: 100, background: "rgba(0,0,0,.55)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <div style={{ width: "min(460px, 100%)", background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 14, padding: "20px 22px", boxShadow: "0 18px 50px rgba(0,0,0,.4)" }}>
        <div style={{ fontSize: 11, color: "var(--text-dim)", letterSpacing: ".08em", textTransform: "uppercase" }}>Schritt {n + 1} von {SCHRITTE.length}</div>
        <h2 style={{ fontSize: 18, fontWeight: 700, color: "var(--text-bright)", margin: "6px 0 8px" }}>{s.titel}</h2>
        <p style={{ fontSize: 14, lineHeight: 1.55, color: "var(--text-main)", margin: 0 }}>{s.text}</p>
        <div style={{ display: "flex", gap: 6, margin: "16px 0 0", alignItems: "center" }}>
          {SCHRITTE.map((_, k) => <span key={k} style={{ width: 7, height: 7, borderRadius: 4, background: k === n ? "var(--accent)" : "var(--border)" }} />)}
          <button className="btn-ghost text-xs" style={{ marginLeft: "auto" }} onClick={ende}>Überspringen</button>
          {n > 0 && <button className="btn-ghost text-xs" onClick={() => setN(n - 1)}>Zurück</button>}
          <button className="btn-primary text-xs" autoFocus onClick={() => (n < SCHRITTE.length - 1 ? setN(n + 1) : ende())}>
            {n < SCHRITTE.length - 1 ? "Weiter" : "Los geht’s"}</button>
        </div>
      </div>
    </div>
  );
}
