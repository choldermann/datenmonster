import { useState, useEffect } from "react";
import { Building2, Loader2, Check, ChevronDown } from "lucide-react";
import { ladeMandanten, setzeMandant, onMandantChange } from "../services/mandant";
import { fehlerText } from "../api/client";

const S = {
  border: "var(--border)", textDim: "var(--text-dim)", textBright: "var(--text-bright)",
  textMain: "var(--text-main)", bgEl: "var(--bg-elevated)", bgCard: "var(--bg-card)",
};

/**
 * Umschalter für den aktiven Mandanten – dieselben Cockpits, andere WaWi.
 *
 * Sichtbar nur, wenn es überhaupt etwas zu wählen gibt: bei genau einem
 * freigegebenen Mandanten steht der Name da, aber ohne Menü; bei keinem gar
 * nichts. Der Name steht bewusst immer im Kopf und nicht hinter einem Menü –
 * wer eine Umsatzzahl liest, muss ohne Klick wissen, von welchem Betrieb sie ist.
 *
 * onWechsel bekommt die neue Verbindungs-ID: die Cockpits laufen danach neu, sonst
 * stünden die Zahlen des alten Mandanten unter dem neuen Namen.
 */
export default function MandantWaehler({ projectId, onWechsel = null, kompakt = false }) {
  const [mandanten, setMandanten] = useState([]);
  const [aktiv, setAktiv] = useState(null);
  const [offen, setOffen] = useState(false);
  const [laedt, setLaedt] = useState(false);

  useEffect(() => {
    let lebt = true;
    ladeMandanten(projectId, { frisch: true }).then(stand => {
      if (!lebt) return;
      setMandanten(stand.mandanten || []);
      setAktiv(stand.aktiv ?? null);
    });
    return () => { lebt = false; };
  }, [projectId]);

  // Wechsel an anderer Stelle (z.B. zweites Cockpit im selben Tab) mitziehen.
  useEffect(() => onMandantChange((pid, neu) => {
    if (String(pid ?? "") === String(projectId ?? "")) setAktiv(neu);
  }), [projectId]);

  if (!mandanten.length) return null;

  const name = mandanten.find(m => m.connection_id === aktiv)?.name
    || mandanten[0]?.name || "—";

  const waehlen = async (cid) => {
    setOffen(false);
    if (cid === aktiv) return;
    setLaedt(true);
    try {
      await setzeMandant(projectId, cid);
      setAktiv(cid);
      onWechsel?.(cid);
    } catch (e) {
      alert(fehlerText(e, "Mandant konnte nicht gewechselt werden"));
    } finally {
      setLaedt(false);
    }
  };

  const einzeln = mandanten.length === 1;

  return (
    <div style={{ position: "relative" }}>
      <button
        onClick={() => !einzeln && setOffen(o => !o)}
        title={einzeln ? `Mandant: ${name}` : "Mandant wechseln"}
        style={{
          display: "flex", alignItems: "center", gap: 6, padding: "5px 9px",
          borderRadius: 7, border: `1px solid ${S.border}`, backgroundColor: "transparent",
          color: S.textBright, cursor: einzeln ? "default" : "pointer",
          fontSize: 11.5, fontWeight: 600, maxWidth: kompakt ? 170 : 260,
        }}>
        {laedt ? <Loader2 size={13} className="animate-spin" /> : <Building2 size={13} />}
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {name}
        </span>
        {!einzeln && <ChevronDown size={12} style={{ color: S.textDim }} />}
      </button>

      {offen && (
        <>
          <div style={{ position: "fixed", inset: 0, zIndex: 40 }} onClick={() => setOffen(false)} />
          <div style={{
            position: "absolute", top: "calc(100% + 6px)", right: 0, zIndex: 41,
            minWidth: 220, backgroundColor: S.bgCard, border: `1px solid ${S.border}`,
            borderRadius: 8, boxShadow: "0 8px 30px rgba(0,0,0,0.35)", overflow: "hidden",
          }}>
            <div style={{ padding: "8px 12px", fontSize: 10, letterSpacing: "0.06em",
              textTransform: "uppercase", color: S.textDim, borderBottom: `1px solid ${S.border}` }}>
              Mandant
            </div>
            {mandanten.map(m => (
              <button key={m.connection_id} onClick={() => waehlen(m.connection_id)}
                style={{
                  display: "flex", alignItems: "center", gap: 8, width: "100%",
                  padding: "9px 12px", background: "none", border: "none",
                  cursor: "pointer", textAlign: "left", fontSize: 12,
                  color: m.connection_id === aktiv ? S.textBright : S.textMain,
                }}
                onMouseEnter={e => e.currentTarget.style.backgroundColor = S.bgEl}
                onMouseLeave={e => e.currentTarget.style.backgroundColor = "transparent"}>
                <span style={{ flex: 1 }}>{m.name}</span>
                {m.connection_id === aktiv && <Check size={13} />}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
