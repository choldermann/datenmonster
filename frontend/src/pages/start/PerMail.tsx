import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import api, { fehlerText } from "../../api/client";
import ReportScheduleModal, { TAKTE } from "../../components/forms/ReportScheduleModal";
import { S, knopf, Seitenkopf } from "./StartLayout";

function takt(cron) {
  return TAKTE.find((t) => t.id === cron)?.label || cron;
}

const zelle = { padding: "12px 14px", borderTop: `1px solid ${S.border}`, verticalAlign: "top" };
const kopf = { textAlign: "left", padding: "10px 14px", backgroundColor: S.bgCard, color: S.textDim,
  fontWeight: 500, fontSize: 12.5 };

export default function PerMail() {
  const [plaene, setPlaene] = useState(null);
  const [formulare, setFormulare] = useState({});
  const [fehler, setFehler] = useState(null);
  const [meldung, setMeldung] = useState(null);
  const [laeuft, setLaeuft] = useState(null);
  const [bearbeiten, setBearbeiten] = useState(null);

  const laden = () => {
    api.get("/api/reports/schedules").then(({ data }) => setPlaene(data || []))
      .catch((e) => setFehler(fehlerText(e)));
    api.get("/api/start/cockpits")
      .then(({ data }) => setFormulare(Object.fromEntries((data || []).map((c) => [c.id, c]))))
      .catch(() => {});
  };
  useEffect(laden, []);

  const jetzt = async (p) => {
    setLaeuft(p.id); setMeldung(null); setFehler(null);
    try {
      await api.post(`/api/reports/schedules/${p.id}/run-now`, null, { timeout: 180000 });
      setMeldung(`„${p.name}“ wurde an ${p.email_to} verschickt.`);
      laden();
    } catch (e) {
      setFehler(fehlerText(e));
    } finally {
      setLaeuft(null);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20, maxWidth: 1100 }}>
      <Seitenkopf titel="Per Mail"
        text="Was regelmäßig von selbst kommt. Jede Mail enthält eine Kurzfassung und den Bericht als PDF." />
      {fehler && <p style={{ color: "var(--err)", margin: 0 }}>{fehler}</p>}
      {meldung && <p role="status" style={{ color: "var(--ok)", margin: 0 }}>{meldung}</p>}
      {plaene === null && !fehler && <span style={{ color: S.textDim }}>Lädt…</span>}
      {plaene && plaene.length === 0 && (
        <p style={{ margin: 0, color: S.textDim }}>
          Noch nichts eingeplant. Einen Bericht per Mail legen Sie unter „Eigene Auswertung“ an.
        </p>
      )}
      {plaene && plaene.length > 0 && (
        <div style={{ overflowX: "auto", border: `1px solid ${S.border}`, borderRadius: 10 }}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 680, fontSize: 14 }}>
            <thead>
              <tr>
                <th style={kopf}>Was</th><th style={kopf}>Wann</th><th style={kopf}>An</th>
                <th style={kopf}>Zuletzt</th><th style={kopf}></th>
              </tr>
            </thead>
            <tbody>
              {plaene.map((p) => (
                <tr key={p.id} style={{ opacity: p.active ? 1 : 0.55 }}>
                  <td style={{ ...zelle, fontWeight: 600, color: S.textBright }}>
                    {p.name}
                    {!p.active && <span style={{ fontWeight: 400, color: S.textDim }}> · pausiert</span>}
                  </td>
                  <td style={zelle}>{takt(p.cron_expr)}</td>
                  <td style={{ ...zelle, color: S.textDim }}>{p.email_to}</td>
                  <td style={{ ...zelle, color: p.last_status === "error" ? "var(--err)" : S.textDim, fontSize: 13 }}>
                    {p.last_run_at ? new Date(p.last_run_at).toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" }) : "noch nie"}
                  </td>
                  <td style={{ ...zelle, textAlign: "right", whiteSpace: "nowrap" }}>
                    <button onClick={() => jetzt(p)} disabled={laeuft === p.id} style={{ ...knopf.neben, minHeight: 34, marginRight: 6 }}>
                      {laeuft === p.id && <Loader2 size={13} style={{ animation: "spin 1s linear infinite" }} />}
                      Jetzt senden
                    </button>
                    {p.form_id && (
                      <button onClick={() => setBearbeiten(p)} style={{ ...knopf.neben, minHeight: 34 }}>Ändern</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {bearbeiten && (
        <ReportScheduleModal formId={bearbeiten.form_id}
          formName={formulare[bearbeiten.form_id]?.name || bearbeiten.name}
          projectId={formulare[bearbeiten.form_id]?.project_id ?? bearbeiten.project_id}
          onClose={() => { setBearbeiten(null); laden(); }} />
      )}
    </div>
  );
}
