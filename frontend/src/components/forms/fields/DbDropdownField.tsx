import { useState, useEffect, useMemo, useRef } from "react";
import { ChevronDown, Check, Search, X } from "lucide-react";
import api, { fehlerText } from "../../../api/client";

const S = {
  bgEl: "var(--bg-elevated)", border: "var(--border)",
  textMain: "var(--text-main)", textDim: "var(--text-dim)", accent: "var(--accent)",
};

// Ab so vielen Einträgen bekommt die Liste ein Suchfeld – darunter sieht man alles ohnehin.
const SUCHE_AB = 12;
// So viele Treffer werden gerendert; der Rest wird über die Suche eingegrenzt.
// (Artikellisten haben in der Praxis mehrere tausend Einträge.)
const MAX_TREFFER = 200;

/** Teilbegriffe UND-verknüpft: "sweat grün" findet "MIAMI+ Herren-Sweatshirt grün". */
function filtern(options, query) {
  const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return options;
  return options.filter(o => {
    const l = (o.label || "").toLowerCase();
    return terms.every(t => l.includes(t));
  });
}

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
 *
 * Lange Listen (Artikel!) sind als reines Aufklappmenü unbrauchbar – deshalb hat
 * das Popover ab SUCHE_AB Einträgen ein Suchfeld für Teilbegriffe.
 */
export default function DbDropdownField({ field, value, onChange, inp, onRunAction, running }) {
  const cfg = field.config || {};
  const autoRun = cfg.auto_run !== false;
  const multiple = !!cfg.multiple;
  const [options, setOptions] = useState([]);
  const [err, setErr] = useState(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const wrapRef = useRef(null);
  const sucheRef = useRef(null);

  const selected = multiple ? (Array.isArray(value) ? value : (value ? [value] : [])) : value;

  // Auswahl anwenden: Filter setzen und (sofern auto_run) das Dashboard neu laden –
  // mit Override gegen Stale-State (setParam greift erst im nächsten Render).
  const apply = v => {
    onChange(v);
    if (autoRun && onRunAction && field.name)
      onRunAction(field.action_ids?.length ? field.action_ids : null, { [field.name]: v });
  };
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
      .catch(e => { if (alive) setErr(fehlerText(e)); });
    return () => { alive = false; };
  }, [cfg.connection_id, cfg.kind]);

  useEffect(() => {
    if (!open) return;
    const onDoc = e => { if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  // Beim Öffnen den Cursor ins Suchfeld setzen und die letzte Suche verwerfen.
  useEffect(() => {
    if (!open) { setQuery(""); return; }
    const t = setTimeout(() => sucheRef.current?.focus(), 0);
    return () => clearTimeout(t);
  }, [open]);

  const treffer = useMemo(() => filtern(options, query), [options, query]);
  const sichtbar = treffer.slice(0, MAX_TREFFER);
  const mitSuche = options.length >= SUCHE_AB;

  const chevron = (
    <ChevronDown size={14} style={{ position: "absolute", right: 9, top: "50%",
      transform: "translateY(-50%)", pointerEvents: "none", color: S.textDim }} />
  );

  const labelVon = v => options.find(o => o.value === v)?.label || v;
  const count = multiple ? selected.length : (selected ? 1 : 0);
  const summary = multiple
    ? (count === 0 ? (cfg.placeholder || "— alle —")
       : count === 1 ? labelVon(selected[0]) : `${count} gewählt`)
    : (selected ? labelVon(selected) : (cfg.placeholder || "— alle —"));

  return (
    <div ref={wrapRef} style={{ position: "relative" }}>
      <button type="button" onClick={() => setOpen(o => !o)} disabled={running}
        style={{ ...inp, textAlign: "left", cursor: running ? "wait" : "pointer",
          paddingRight: 30, color: count ? S.textMain : S.textDim,
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {summary}
      </button>
      {chevron}
      {open && (
        <div style={{ position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0, zIndex: 40,
          background: S.bgEl, border: `1px solid ${S.border}`,
          borderRadius: 8, boxShadow: "0 8px 28px rgba(0,0,0,0.4)", padding: 4 }}>

          {mitSuche && (
            <div style={{ position: "relative", padding: "2px 2px 6px" }}>
              <Search size={13} style={{ position: "absolute", left: 10, top: 11, color: S.textDim }} />
              <input ref={sucheRef} value={query} onChange={e => setQuery(e.target.value)}
                onKeyDown={e => {
                  if (e.key === "Escape") { e.stopPropagation(); setOpen(false); }
                  // Enter bei genau einem Treffer = direkt übernehmen.
                  if (e.key === "Enter" && !multiple && treffer.length === 1) {
                    e.preventDefault(); apply(treffer[0].value); setOpen(false);
                  }
                }}
                placeholder="Suchen …"
                style={{ width: "100%", padding: "7px 26px 7px 30px", fontSize: 12,
                  background: "var(--bg-main)", border: `1px solid ${S.border}`,
                  borderRadius: 6, color: S.textMain, outline: "none" }} />
              {query && (
                <button type="button" onClick={() => { setQuery(""); sucheRef.current?.focus(); }}
                  style={{ position: "absolute", right: 8, top: 8, background: "none",
                    border: "none", color: S.textDim, cursor: "pointer", padding: 2 }}>
                  <X size={12} />
                </button>
              )}
            </div>
          )}

          <div style={{ maxHeight: 260, overflowY: "auto" }}>
            {count > 0 && (
              <button type="button" onClick={() => { apply(multiple ? [] : ""); if (!multiple) setOpen(false); }}
                style={{ display: "block", width: "100%", textAlign: "left", padding: "6px 10px",
                  background: "none", border: "none", color: S.textDim, fontSize: 12,
                  cursor: "pointer", borderBottom: `1px solid ${S.border}` }}>
                Auswahl zurücksetzen
              </button>
            )}

            {sichtbar.length === 0 && (
              <div style={{ padding: "8px 10px", fontSize: 12, color: S.textDim }}>
                {err ? err : options.length === 0 ? "Keine Einträge" : "Kein Treffer"}
              </div>
            )}

            {sichtbar.map(o => {
              const on = multiple ? selected.includes(o.value) : selected === o.value;
              return (
                <div key={o.value} role="button"
                  onClick={() => { multiple ? toggle(o.value) : (apply(o.value), setOpen(false)); }}
                  style={{ display: "flex", alignItems: "center", gap: 8,
                    padding: "6px 10px", fontSize: 12, cursor: "pointer", borderRadius: 5,
                    color: S.textMain }}
                  onMouseEnter={e => e.currentTarget.style.background = "rgba(255,255,255,0.04)"}
                  onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                  {multiple ? (
                    <span style={{ width: 15, height: 15, borderRadius: 4, flexShrink: 0,
                      border: `1px solid ${on ? S.accent : S.border}`, background: on ? S.accent : "transparent",
                      display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
                      {on && <Check size={11} style={{ color: "#0c1a12" }} />}
                    </span>
                  ) : (
                    <span style={{ width: 15, flexShrink: 0, display: "inline-flex" }}>
                      {on && <Check size={12} style={{ color: S.accent }} />}
                    </span>
                  )}
                  {o.label}
                </div>
              );
            })}

            {treffer.length > sichtbar.length && (
              <div style={{ padding: "8px 10px", fontSize: 11, color: S.textDim,
                borderTop: `1px solid ${S.border}` }}>
                … {treffer.length - sichtbar.length} weitere Treffer – Suche eingrenzen
              </div>
            )}
          </div>
        </div>
      )}
      {err && !open && options.length === 0 &&
        <div style={{ fontSize: 11, color: "#e07070", marginTop: 4 }}>{err}</div>}
    </div>
  );
}
