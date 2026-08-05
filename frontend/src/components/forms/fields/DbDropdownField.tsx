import { useState, useEffect } from "react";
import { ChevronDown } from "lucide-react";
import api from "../../../api/client";

const S = { textDim: "var(--text-dim)" };

/**
 * Dropdown, dessen Optionen aus der JTL-DB geladen werden (z.B. Warengruppen,
 * Kategorien). Aus Sicherheitsgründen wird KEIN SQL vom Client geschickt –
 * nur eine vordefinierte `kind` + die Verbindungs-ID; das Backend kennt die
 * (read-only) Abfrage und prüft den Verbindungszugriff.
 *
 * config: { connection_id, kind, placeholder }
 * Der Feld-`name` ist der SQL-Parameter (z.B. :kwarengruppe).
 */
export default function DbDropdownField({ field, value, onChange, inp, onRunAction, running }) {
  const cfg = field.config || {};
  const autoRun = cfg.auto_run !== false;
  const [options, setOptions] = useState([]);
  const [err, setErr] = useState(null);

  // Bei Auswahl-Wechsel den Filter setzen und (sofern auto_run) das Dashboard neu
  // laden – mit Override gegen Stale-State (setParam greift erst im nächsten Render).
  const handleChange = v => {
    onChange(v);
    if (autoRun && onRunAction && field.name)
      onRunAction(field.action_ids?.length ? field.action_ids : null, { [field.name]: v });
  };

  useEffect(() => {
    const cid = Number(cfg.connection_id);
    if (!cid || !cfg.kind) return;
    let alive = true;
    api.get("/api/lookup/options", { params: { connection_id: cid, kind: cfg.kind } })
      .then(({ data }) => { if (alive) { setOptions(data.options || []); setErr(null); } })
      .catch(e => { if (alive) setErr(e.response?.data?.detail || e.message); });
    return () => { alive = false; };
  }, [cfg.connection_id, cfg.kind]);

  return (
    <div style={{ position: "relative" }}>
      <select value={value ?? ""} onChange={e => handleChange(e.target.value)} disabled={running}
        style={{ ...inp, cursor: "pointer", appearance: "none", paddingRight: 30 }}>
        <option value="">{cfg.placeholder || "— alle —"}</option>
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      <ChevronDown size={14} style={{ position: "absolute", right: 9, top: "50%",
        transform: "translateY(-50%)", pointerEvents: "none", color: S.textDim }} />
      {err && <div style={{ fontSize: 11, color: "#e07070", marginTop: 4 }}>{err}</div>}
    </div>
  );
}
