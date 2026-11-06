/**
 * Pflegeliste der eigenen Ereignisse (Unternehmensübersicht · Ereignisse). Gleiche Daten wie die
 * Markierungen in den Verläufen; Anlegen auch direkt am Diagramm („+ Ereignis“).
 * Portal-Benutzer sehen die Liste, ändern können nur Bearbeiter (Backend: require_editor).
 */
import { useState } from "react";
import { Plus, Pencil, Flag } from "lucide-react";
import { useAuth } from "../../../context/AuthContext";
import { useEreignisse, ereignisZeitraum, EreignisDialog } from "../ereignisse";

export default function EreignisseWidget({ widget, projectId = null }) {
  const { user } = useAuth();
  const ev = useEreignisse(projectId);
  const [dialog, setDialog] = useState(null);
  const [jahr, setJahr] = useState("alle");
  const darf = !user?.is_portal_only;
  const jahre = [...new Set(ev.ereignisse.map((e) => (e.datum || "").slice(0, 4)).filter(Boolean))].sort().reverse();
  const liste = [...ev.ereignisse].reverse().filter((e) => jahr === "alle" || (e.datum || "").startsWith(jahr));
  const knopf = { display: "inline-flex", alignItems: "center", gap: 5, padding: "6px 12px", borderRadius: 6, fontSize: 12.5,
    border: "1px solid var(--border)", background: "transparent", color: "var(--text-main)", cursor: "pointer" };
  return (
    <div style={{ padding: "12px 16px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10, justifyContent: "space-between" }}>
        <span style={{ fontSize: 12.5, color: "var(--text-dim)", lineHeight: 1.45, maxWidth: "70ch" }}>
          Aktionen, Messen, Preisänderungen oder Lieferengpässe erscheinen als Markierung in den Verläufen aller
          Cockpits{ev.mandant_name ? ` von ${ev.mandant_name}` : ""}. So bleibt erklärt, warum ein Monat aus der Reihe fällt.
        </span>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {jahre.length > 1 && (
            <select value={jahr} onChange={(e) => setJahr(e.target.value)}
              style={{ ...knopf, padding: "5px 8px" }} aria-label="Jahr">
              <option value="alle">Alle Jahre</option>
              {jahre.map((j) => <option key={j} value={j}>{j}</option>)}
            </select>
          )}
          {darf && <button onClick={() => setDialog({ datum: new Date().toISOString().slice(0, 10) })}
            style={{ ...knopf, borderColor: "var(--accent)", color: "var(--accent)", fontWeight: 600 }}><Plus size={13} /> Ereignis</button>}
        </div>
      </div>
      {liste.length === 0 ? (
        <p style={{ margin: 0, padding: "18px 0", color: "var(--text-dim)", fontSize: 13, textAlign: "center" }}>
          Noch keine Ereignisse eingetragen.
        </p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ color: "var(--text-dim)", fontSize: 11, textAlign: "left" }}>
              <th style={{ padding: "6px 8px", fontWeight: 600 }}>Wann</th>
              <th style={{ padding: "6px 8px", fontWeight: 600 }}>Ereignis</th>
              <th style={{ padding: "6px 8px", fontWeight: 600 }}>Art</th>
              <th style={{ padding: "6px 8px", fontWeight: 600 }}>Notiz</th>
              {darf && <th />}
            </tr>
          </thead>
          <tbody>
            {liste.map((e) => (
              <tr key={e.id} style={{ borderTop: "1px solid var(--border)" }}>
                <td style={{ padding: "7px 8px", whiteSpace: "nowrap", color: "var(--text-dim)", fontVariantNumeric: "tabular-nums" }}>{ereignisZeitraum(e)}</td>
                <td style={{ padding: "7px 8px", color: "var(--text-bright)" }}>
                  <Flag size={11} style={{ color: "var(--text-dim)", marginRight: 5, verticalAlign: "-1px" }} />{e.titel}
                </td>
                <td style={{ padding: "7px 8px", color: "var(--text-main)" }}>{e.kategorie}</td>
                <td style={{ padding: "7px 8px", color: "var(--text-dim)" }}>{e.notiz}</td>
                {darf && (
                  <td style={{ padding: "4px 8px", textAlign: "right" }}>
                    <button onClick={() => setDialog(e)} aria-label={`${e.titel} ändern`} style={{ ...knopf, padding: "4px 8px" }}>
                      <Pencil size={12} />
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {dialog && <EreignisDialog projectId={projectId} vorgabe={dialog} kategorien={ev.kategorien}
        mandantName={ev.mandant_name} onClose={() => setDialog(null)} />}
    </div>
  );
}
