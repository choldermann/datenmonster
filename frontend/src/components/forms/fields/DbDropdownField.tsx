import { useState, useEffect, useRef } from "react";
import { ChevronDown, Check } from "lucide-react";
import api from "../../../api/client";

const S = {
  bgEl: "var(--bg-elevated)", border: "var(--border)",
  textMain: "var(--text-main)", textDim: "var(--text-dim)", accent: "var(--accent)",
};

/**
 * Dropdown, dessen Optionen aus der JTL-DB geladen werden (z.B. Warengruppen,
 * Kategorien). Aus Sicherheitsgründen wird KEIN SQL vom Client geschickt –
 * nur eine vordefinierte `kind` + die Verbindungs-ID; das Backend kennt die
 * (read-only) Abfrage und prüft den Verbindungszugriff.
 *
 * config: { connection_id, kind, placeholder, multiple }
 * Der Feld-`name` ist der SQL-Parameter. Bei multiple=true ist der Wert eine
 * Liste; das Backend expandiert sie zu einer IN-Liste (:name → :name__0, …) und
 * bindet :name_empty=1, wenn nichts gewählt ist.
 */
export default function DbDropdownField({ field, value, onChange, inp, onRunAction, running }) {
  const cfg = field.config || {};
  const autoRun = cfg.auto_run !== false;
  const multiple = !!cfg.multiple;
  const [options, setOptions] = useState([]);
  const [err, setErr] = useState(null);
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);

  const selected = multiple ? (Array.isArray(value) ? value : (value ? [value] : [])) : value;

  // Auswahl anwenden: Filter setzen und (sofern auto_run) das Dashboard neu laden –
  // mit Override gegen Stale-State (setParam greift erst im nächsten Render).
  const apply = v => {
    onChange(v);
    if (autoRun && onRunAction && field.name)
      onRunAction(field.action_ids?.length ? field.action_ids : null, { [field.name]: v });
  };
  const handleSingle = v => apply(v);
  const toggle = v => {
    const set = new Set(selected);
    set.has(v) ? set.delete(v) : set.add(v);
    apply([...set]);
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

  useEffect(() => {
    if (!open) return;
    const onDoc = e => { if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const chevron = (
    <ChevronDown size={14} style={{ position: "absolute", right: 9, top: "50%",
      transform: "translateY(-50%)", pointerEvents: "none", color: S.textDim }} />
  );

  if (!multiple) {
    return (
      <div style={{ position: "relative" }}>
        <select value={selected ?? ""} onChange={e => handleSingle(e.target.value)} disabled={running}
          style={{ ...inp, cursor: "pointer", appearance: "none", paddingRight: 30 }}>
          <option value="">{cfg.placeholder || "— alle —"}</option>
          {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        {chevron}
        {err && <div style={{ fontSize: 11, color: "#e07070", marginTop: 4 }}>{err}</div>}
      </div>
    );
  }

  const count = selected.length;
  const summary = count === 0 ? (cfg.placeholder || "— alle —")
    : count === 1 ? (options.find(o => o.value === selected[0])?.label || "1 gewählt")
    : `${count} gewählt`;

  return (
    <div ref={wrapRef} style={{ position: "relative" }}>
      <button type="button" onClick={() => setOpen(o => !o)} disabled={running}
        style={{ ...inp, textAlign: "left", cursor: running ? "wait" : "pointer",
          paddingRight: 30, color: count ? S.textMain : S.textDim }}>
        {summary}
      </button>
      {chevron}
      {open && (
        <div style={{ position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0, zIndex: 40,
          maxHeight: 260, overflowY: "auto", background: S.bgEl, border: `1px solid ${S.border}`,
          borderRadius: 8, boxShadow: "0 8px 28px rgba(0,0,0,0.4)", padding: 4 }}>
          {count > 0 && (
            <button type="button" onClick={() => apply([])}
              style={{ display: "block", width: "100%", textAlign: "left", padding: "6px 10px",
                background: "none", border: "none", color: S.textDim, fontSize: 12,
                cursor: "pointer", borderBottom: `1px solid ${S.border}` }}>
              Auswahl zurücksetzen
            </button>
          )}
          {options.length === 0 && (
            <div style={{ padding: "8px 10px", fontSize: 12, color: S.textDim }}>
              {err ? err : "Keine Einträge"}
            </div>
          )}
          {options.map(o => {
            const on = selected.includes(o.value);
            return (
              <label key={o.value} style={{ display: "flex", alignItems: "center", gap: 8,
                padding: "6px 10px", fontSize: 12, cursor: "pointer", borderRadius: 5,
                color: S.textMain }}
                onMouseEnter={e => e.currentTarget.style.background = "rgba(255,255,255,0.04)"}
                onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                <span style={{ width: 15, height: 15, borderRadius: 4, flexShrink: 0,
                  border: `1px solid ${on ? S.accent : S.border}`, background: on ? S.accent : "transparent",
                  display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
                  {on && <Check size={11} style={{ color: "#0c1a12" }} />}
                </span>
                <input type="checkbox" checked={on} onChange={() => toggle(o.value)}
                  style={{ display: "none" }} />
                {o.label}
              </label>
            );
          })}
        </div>
      )}
      {err && count >= 0 && !open && options.length === 0 &&
        <div style={{ fontSize: 11, color: "#e07070", marginTop: 4 }}>{err}</div>}
    </div>
  );
}
