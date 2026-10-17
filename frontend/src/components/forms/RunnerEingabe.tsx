/**
 * Eingabebereich eines Formularlaufs – gemeinsam für FormRunner und PortalRunner
 * (Zusammenführung der Runner, Schritt 2; Schritt 1 ist RunnerErgebnis).
 *
 * Zwei Darstellungen, damit sich beim Zusammenlegen nichts sichtbar ändert:
 *  - kompakt (Editor/Werkstatt): enge Karte, ohne Felder ein Hinweis für Bauende
 *  - großzügig (Portal): weite Karte, ohne Felder ein „Aktualisieren“-Knopf
 */
import { Loader2, Play } from "lucide-react";
import FormFields, { ALLE_AKTIONEN } from "./FormFields";
import IntrastatExclusionPanel from "./IntrastatExclusionPanel";

const S = {
  bgCard: "var(--bg-card)", border: "var(--border)", textBright: "var(--text-bright)",
  textDim: "var(--text-dim)", accent: "var(--accent)",
};

const startKnopf = (gross) => ({
  display: "inline-flex", alignItems: "center", gap: gross ? 8 : 7,
  padding: gross ? "10px 24px" : "8px 18px", borderRadius: gross ? 8 : 6,
  fontSize: gross ? 14 : 13, fontWeight: 600,
  backgroundColor: "color-mix(in srgb, var(--ok) 12%, transparent)",
  border: `1px solid color-mix(in srgb, var(--ok) ${gross ? 40 : 35}%, transparent)`, color: "var(--ok)",
});

function Dreher({ gross }) {
  const g = gross ? 14 : 13;
  return <Loader2 size={g} style={{ animation: "spin 1s linear infinite" }} />;
}

/** Reiter „Auswertung | Ausschlussartikel“ samt Pflegemaske – nur, wenn das Schema
 *  ein article_exclusion-Feld hat. Gibt true zurück über `zeigeHaupt`, ob der
 *  Auswertungsteil sichtbar ist. */
export function EingabeReiter({ exclusionField, inputTab, setInputTab, projectId, abstand = 20 }) {
  if (!exclusionField) return null;
  const cId = Number(exclusionField.config?.connection_id);
  return (
    <>
      <div style={{ display: "flex", gap: 4, marginBottom: abstand, borderBottom: `1px solid ${S.border}` }}>
        {[{ id: "main", label: "Auswertung" },
          { id: "exclusions", label: exclusionField.label || "Ausschlussartikel" }].map(t => {
          const active = inputTab === t.id;
          return (
            <button key={t.id} onClick={() => setInputTab(t.id)}
              style={{ padding: "8px 16px", background: "none", border: "none",
                borderBottom: `2px solid ${active ? S.accent : "transparent"}`,
                color: active ? S.textBright : S.textDim, cursor: "pointer",
                fontSize: 13, fontWeight: active ? 600 : 400 }}>
              {t.label}
            </button>
          );
        })}
      </div>
      {/* Verbindung aus dem Template (config.connection_id, beim Install aufgelöst).
          Nur übernehmen, wenn es eine gültige Zahl ist – sonst Auto-Erkennung im Panel. */}
      {inputTab === "exclusions" && (
        <IntrastatExclusionPanel projectId={projectId}
          connectionId={Number.isFinite(cId) && cId > 0 ? cId : null} />
      )}
    </>
  );
}

export default function RunnerEingabe({
  fields, params, setParam, onRun, running, missing, actions, results,
  hasButtonField, kompakt = false, ohneFelderHinweis = false,
}) {
  const gross = !kompakt;

  if (!fields.length) {
    if (!actions.length) return null;   // reine Pflegemaske: ein Knopf wäre funktionslos
    if (ohneFelderHinweis) return (
      <div style={{ textAlign: "center", padding: "40px 0", marginBottom: 24 }}>
        <p style={{ color: S.textDim, fontSize: 12, marginBottom: 16 }}>
          Dieses Formular hat noch keine Eingabefelder.
        </p>
        <button onClick={() => onRun(ALLE_AKTIONEN)} disabled={running}
          style={{ ...startKnopf(false), cursor: running ? "wait" : "pointer" }}>
          {running ? <Dreher gross={false} /> : <Play size={13} />}
          Mappings ausführen
        </button>
      </div>
    );
    // Dashboard ohne Eingabefelder: der Lauf beginnt automatisch, der Knopf
    // bleibt zum Aktualisieren.
    return (
      <div style={{ textAlign: "center", marginBottom: gross ? 28 : 20 }}>
        <button onClick={() => onRun(ALLE_AKTIONEN)} disabled={running}
          style={{ ...startKnopf(gross), cursor: running ? "wait" : "pointer" }}>
          {running ? <Dreher gross={gross} /> : <Play size={gross ? 14 : 13} />}
          {running ? "Wird ausgeführt …" : results ? "Aktualisieren" : "Ausführen"}
        </button>
      </div>
    );
  }

  return (
    <div style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`,
      borderRadius: gross ? 14 : 10, padding: gross ? "28px 32px" : "20px 24px", marginBottom: gross ? 32 : 24 }}>
      <FormFields fields={fields} params={params} setParam={setParam}
        onRunAction={onRun} running={running} compact={kompakt} errors={missing} />

      {/* Ohne Button-Feld im Schema genau EIN Sammel-Lauf über alle Actions – bei
          Dashboards mit vielen Actions wäre ein Button je Action eine Buttonwand. */}
      {!hasButtonField && actions.length > 0 && (
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: gross ? 12 : 8 }}>
          <button onClick={() => onRun(ALLE_AKTIONEN)} disabled={running}
            style={{ ...startKnopf(gross), cursor: running ? "wait" : "pointer" }}>
            {running ? <Dreher gross={gross} /> : <Play size={gross ? 14 : 13} />}
            {gross && actions.length === 1 ? (actions[0].label || "Ausführen") : "Ausführen"}
          </button>
        </div>
      )}

      {gross && running && (
        <div style={{ marginTop: 16, display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: S.textDim }}>
          <Loader2 size={12} style={{ animation: "spin 1s linear infinite" }} />
          Wird ausgeführt…
        </div>
      )}
    </div>
  );
}
