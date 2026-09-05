import { useState, useEffect, useRef } from "react";
import { X, Trash2, Send, AlertTriangle, CheckCircle2 } from "lucide-react";
import api, { fehlerText } from "../../api/client";
import { S } from "../dashboard/constants";

/**
 * Zustellplan eines Reports: wann er läuft, für welchen Zeitraum, an wen.
 *
 * Der Zeitraum wird bei jedem Lauf neu berechnet – „Dieses Jahr" heißt
 * Jahresanfang bis zum Auslösetag, nicht bis zum Tag, an dem der Plan
 * eingerichtet wurde.
 */

const ZEITRAEUME = [
  { id: "this_month", label: "Dieser Monat" },
  { id: "last_month", label: "Letzter Monat" },
  { id: "this_year",  label: "Dieses Jahr (Jahresanfang bis Auslösetag)" },
  { id: "last_year",  label: "Letztes Jahr" },
  { id: "days_30",    label: "Letzte 30 Tage" },
  { id: "months_12",  label: "Letzte 12 Monate" },
];

// Fertige Cron-Ausdrücke; „eigener" gibt das Feld frei.
const TAKTE = [
  { id: "0 6 * * 1",  label: "Jeden Montag, 6:00" },
  { id: "0 6 * * 2",  label: "Jeden Dienstag, 6:00" },
  { id: "0 6 * * 1-5", label: "Werktags, 6:00" },
  { id: "0 6 1 * *",  label: "Am 1. des Monats, 6:00" },
  { id: "0 7 * * *",  label: "Täglich, 7:00" },
  { id: "__eigen",    label: "Eigener Ausdruck…" },
];

const feld = {
  width: "100%", padding: "7px 10px", borderRadius: 6,
  backgroundColor: S.bgCard, border: `1px solid ${S.border}`,
  color: S.textMain, fontSize: 12,
};
const label = { display: "block", fontSize: 10.5, color: S.textDim, marginBottom: 4 };

export default function ReportScheduleModal({ formId, formName, projectId, onClose }) {
  const [plan, setPlan] = useState(null);
  const [laedt, setLaedt] = useState(true);
  const [meldung, setMeldung] = useState(null);   // {art: "ok"|"warn"|"fehler", text}
  const [eigenerTakt, setEigenerTakt] = useState(false);
  const [busy, setBusy] = useState(false);
  // Die nachfassenden Statusabfragen laufen per setTimeout und sähen sonst
  // immer die plan-Fassung von dem Moment, in dem der Test gestartet wurde.
  const planIdRef = useRef(null);
  const [mandanten, setMandanten] = useState([]);

  useEffect(() => {
    (async () => {
      try {
        const [{ data }, md] = await Promise.all([
          api.get("/api/reports/schedules", { params: { form_id: formId } }),
          api.get("/api/mandanten", { params: projectId ? { project_id: projectId } : {} })
            .catch(() => ({ data: { mandanten: [], aktiv: null } })),
        ]);
        setMandanten(md.data?.mandanten || []);
        const vorhanden = (data || [])[0];
        if (vorhanden) {
          setPlan(vorhanden);
          setEigenerTakt(!TAKTE.some((t) => t.id === vorhanden.cron_expr));
        } else {
          setPlan({
            name: formName, form_id: formId, project_id: projectId || null,
            mandant_id: md.data?.aktiv ?? null,
            cron_expr: "0 6 * * 1", active: false, zeitraum_preset: "this_month",
            email_to: "", email_subject: "", sections: [], params: {},
          });
        }
      } catch (e) {
        setMeldung({ art: "fehler", text: fehlerText(e) });
      } finally { setLaedt(false); }
    })();
  }, [formId]);

  useEffect(() => { planIdRef.current = plan?.id ?? null; }, [plan?.id]);

  const setzen = (k, v) => setPlan((p) => ({ ...p, [k]: v }));

  const speichern = async () => {
    setBusy(true); setMeldung(null);
    try {
      const { data } = plan.id
        ? await api.put(`/api/reports/schedules/${plan.id}`, plan)
        : await api.post("/api/reports/schedules", plan);
      setPlan(data);
      setMeldung({ art: "ok", text: data.active
        ? "Gespeichert und eingeplant."
        : "Gespeichert. Der Plan ist noch nicht aktiv." });
    } catch (e) {
      setMeldung({ art: "fehler", text: fehlerText(e) });
    } finally { setBusy(false); }
  };

  const testen = async () => {
    if (!plan.id) { setMeldung({ art: "warn", text: "Bitte erst speichern." }); return; }
    setBusy(true); setMeldung(null);
    try {
      const { data } = await api.post(`/api/reports/schedules/${plan.id}/run-now`);
      setMeldung(data.hinweis
        ? { art: "warn", text: data.hinweis }
        : { art: "ok", text: "Lauf gestartet – das Ergebnis erscheint gleich unten." });
      // Der Lauf läuft im Hintergrund; ohne Nachfassen bliebe die Meldung
      // „gestartet" stehen und der Anwender wüsste nie, ob es geklappt hat.
      // Ein Cockpit-Lauf braucht je nach Umfang einige Sekunden.
      [3000, 8000, 15000, 30000].forEach((ms) => setTimeout(status, ms));
    } catch (e) {
      setMeldung({ art: "fehler", text: fehlerText(e) });
    } finally { setBusy(false); }
  };

  const loeschen = async () => {
    if (!plan.id || !window.confirm("Zeitplan löschen?")) return;
    await api.delete(`/api/reports/schedules/${plan.id}`);
    onClose();
  };

  /** Holt NUR den Laufstatus nach. Den Rest des Plans anzufassen wäre falsch:
   *  der Anwender kann währenddessen schon weitergetippt haben. */
  const status = async () => {
    const pid = planIdRef.current;
    if (!pid) return;
    try {
      const { data } = await api.get("/api/reports/schedules", { params: { form_id: formId } });
      const akt = (data || []).find((s) => s.id === pid);
      if (akt) setPlan((p) => ({ ...p, last_run_at: akt.last_run_at,
        last_status: akt.last_status, last_message: akt.last_message }));
    } catch { /* der nächste Versuch kommt gleich */ }
  };

  const farbe = { ok: "#4ade80", warn: "var(--accent)", fehler: "#f87171" };
  const Icon = meldung?.art === "ok" ? CheckCircle2 : AlertTriangle;

  return (
    <div style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.6)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, padding: 24 }}>
      <div style={{ backgroundColor: S.bgMain, border: `1px solid ${S.border}`, borderRadius: 10,
        width: "100%", maxWidth: 560, maxHeight: "90vh", display: "flex", flexDirection: "column" }}>

        <div style={{ padding: "16px 20px", borderBottom: `1px solid ${S.border}`,
          display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <h2 style={{ fontSize: 15, fontWeight: 700, color: S.textBright, margin: 0 }}>
              Regelmäßig zustellen
            </h2>
            <p style={{ fontSize: 11, color: S.textDim, marginTop: 3 }}>{formName}</p>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none",
            color: S.textDim, cursor: "pointer", padding: 4 }}><X size={18} /></button>
        </div>

        {laedt || !plan ? (
          <div style={{ padding: 40, textAlign: "center", color: S.textDim, fontSize: 12 }}>Lädt…</div>
        ) : (
          <div style={{ flex: 1, overflowY: "auto", padding: 20,
            display: "flex", flexDirection: "column", gap: 14 }}>

            <label style={{ display: "flex", alignItems: "center", gap: 9, cursor: "pointer" }}>
              <input type="checkbox" checked={!!plan.active}
                onChange={(e) => setzen("active", e.target.checked)}
                style={{ accentColor: "var(--accent)" }} />
              <span style={{ fontSize: 12.5, color: S.textBright, fontWeight: 600 }}>
                Zeitplan aktiv
              </span>
            </label>

            {mandanten.length > 1 && (
              <div>
                <label style={label}>Mandant – dessen Zahlen und Briefkopf</label>
                <select value={plan.mandant_id ?? ""}
                  onChange={(e) => setzen("mandant_id",
                    e.target.value === "" ? null : Number(e.target.value))}
                  style={feld}>
                  {mandanten.map((m) => (
                    <option key={m.connection_id} value={m.connection_id}>
                      {m.name}{m.ist_standard ? " (Standard)" : ""}
                    </option>
                  ))}
                </select>
                <p style={{ fontSize: 10.5, color: S.textDim, marginTop: 4 }}>
                  Der Zeitplan läuft ohne angemeldeten Benutzer – der Betrieb muss
                  hier festgelegt sein, nicht aus der Sitzung geraten werden.
                </p>
              </div>
            )}

            <div>
              <label style={label}>Takt</label>
              <select
                value={eigenerTakt ? "__eigen" : plan.cron_expr}
                onChange={(e) => {
                  if (e.target.value === "__eigen") setEigenerTakt(true);
                  else { setEigenerTakt(false); setzen("cron_expr", e.target.value); }
                }}
                style={feld}>
                {TAKTE.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
              </select>
              {eigenerTakt && (
                <input value={plan.cron_expr || ""} onChange={(e) => setzen("cron_expr", e.target.value)}
                  placeholder="Minute Stunde Tag Monat Wochentag – z. B. 0 6 * * 1"
                  style={{ ...feld, marginTop: 6, fontFamily: "monospace" }} />
              )}
              <p style={{ fontSize: 10.5, color: S.textDim, marginTop: 4 }}>
                Zeitzone Europe/Berlin.
              </p>
            </div>

            <div>
              <label style={label}>Zeitraum, bei jedem Lauf neu berechnet</label>
              <select value={plan.zeitraum_preset || "this_month"}
                onChange={(e) => setzen("zeitraum_preset", e.target.value)} style={feld}>
                {ZEITRAEUME.map((z) => <option key={z.id} value={z.id}>{z.label}</option>)}
              </select>
            </div>

            <div>
              <label style={label}>Empfänger (mehrere durch Komma trennen)</label>
              <input value={plan.email_to || ""} onChange={(e) => setzen("email_to", e.target.value)}
                placeholder="name@firma.de, chef@firma.de" style={feld} />
              <p style={{ fontSize: 10.5, color: S.textDim, marginTop: 4 }}>
                Ohne Empfänger wird der Report nur gerechnet, nicht verschickt.
              </p>
            </div>

            <div>
              <label style={label}>Eigener Betreff (leer = automatisch)</label>
              <input value={plan.email_subject || ""} onChange={(e) => setzen("email_subject", e.target.value)}
                placeholder={`${plan.name || formName} – Dieser Monat (01.09.2026 – 30.09.2026)`}
                style={feld} />
            </div>

            {plan.last_run_at && (
              <div onClick={status} title="Aktualisieren"
                style={{ padding: "10px 12px", borderRadius: 6, cursor: "pointer",
                  backgroundColor: S.bgCard, border: `1px solid ${S.border}` }}>
                <div style={{ fontSize: 10.5, color: S.textDim, marginBottom: 3 }}>
                  Letzter Lauf · {String(plan.last_run_at).slice(0, 19).replace("T", " ")}
                </div>
                <div style={{ fontSize: 11.5,
                  color: plan.last_status === "error" ? "#f87171" : S.textMain }}>
                  {plan.last_message || plan.last_status}
                </div>
              </div>
            )}

            {meldung && (
              <div style={{ display: "flex", alignItems: "flex-start", gap: 7,
                fontSize: 11.5, color: farbe[meldung.art] }}>
                <Icon size={13} style={{ flexShrink: 0, marginTop: 1 }} />
                <span>{meldung.text}</span>
              </div>
            )}
          </div>
        )}

        <div style={{ padding: "14px 20px", borderTop: `1px solid ${S.border}`,
          display: "flex", gap: 8, alignItems: "center" }}>
          {plan?.id && (
            <button onClick={loeschen} title="Zeitplan löschen"
              style={{ padding: "8px 10px", borderRadius: 6, border: `1px solid ${S.border}`,
                background: "none", color: S.textDim, cursor: "pointer" }}>
              <Trash2 size={13} />
            </button>
          )}
          <button onClick={testen} disabled={busy || !plan?.id}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 14px",
              borderRadius: 6, border: `1px solid ${S.border}`, background: "none",
              color: S.textMain, fontSize: 12, fontWeight: 600,
              cursor: plan?.id && !busy ? "pointer" : "not-allowed",
              opacity: plan?.id && !busy ? 1 : 0.4 }}>
            <Send size={12} /> Jetzt testen
          </button>
          <button onClick={speichern} disabled={busy}
            style={{ marginLeft: "auto", padding: "8px 16px", borderRadius: 6,
              backgroundColor: "rgba(252,228,153,0.15)", border: "1px solid rgba(252,228,153,0.4)",
              color: "var(--accent)", fontSize: 12, fontWeight: 600,
              cursor: busy ? "not-allowed" : "pointer", opacity: busy ? 0.5 : 1 }}>
            {busy ? "…" : "Speichern"}
          </button>
        </div>
      </div>
    </div>
  );
}
