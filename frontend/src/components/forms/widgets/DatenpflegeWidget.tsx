import { useState, useEffect, useCallback, useMemo } from "react";
import { Plus, Search, AlertCircle, Loader2, X, Pencil, Lock, Unlock, RotateCcw,
         Save } from "lucide-react";
import api, { fehlerText } from "../../../api/client";
import { onMandantChange } from "../../../services/mandant";
import BestaetigenModal from "./BestaetigenModal";

const S = {
  bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)", bgMain: "var(--bg-main)",
  border: "var(--border)", textMain: "var(--text-main)", textDim: "var(--text-dim)",
  textBright: "var(--text-bright)", accent: "var(--accent)",
};

const inp = {
  backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4,
  color: S.textMain, fontSize: 12, padding: "6px 9px", outline: "none",
  width: "100%", boxSizing: "border-box",
};

const btn = {
  display: "inline-flex", alignItems: "center", gap: 6, padding: "5px 11px",
  borderRadius: 5, border: `1px solid ${S.border}`, backgroundColor: S.bgEl,
  color: S.textMain, fontSize: 12, cursor: "pointer", whiteSpace: "nowrap",
};

const GRUEN = "#6ee7b7", ROT = "#e07070";

function anzeige(spalte, v) {
  if (v === null || v === undefined || v === "") return <span style={{ color: S.textDim }}>–</span>;
  if (spalte.typ === "bool") return v ? "ja" : "nein";
  if (spalte.typ === "datum") {
    const d = new Date(v);
    return isNaN(d) ? String(v) : d.toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" });
  }
  return String(v);
}

/** Eingabefeld passend zum Spaltentyp. */
function Feld({ spalte, wert, onChange, gesperrt }) {
  if (spalte.typ === "bool") {
    return (
      <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12,
        color: S.textMain, cursor: gesperrt ? "default" : "pointer", padding: "6px 0" }}>
        <input type="checkbox" checked={!!wert} disabled={gesperrt}
          onChange={e => onChange(e.target.checked)} style={{ width: 14, height: 14 }} />
        {wert ? "ja" : "nein"}
      </label>
    );
  }
  if (spalte.auswahl?.length && !gesperrt) {
    // Ein Wert, der (noch) nicht in der Liste steht, bleibt wählbar – sonst
    // würde das Öffnen der Maske ihn stillschweigend verlieren.
    const optionen = wert && !spalte.auswahl.includes(wert) ? [wert, ...spalte.auswahl] : spalte.auswahl;
    return (
      <select value={wert ?? ""} onChange={e => onChange(e.target.value)}
        style={{ ...inp, cursor: "pointer" }}>
        <option value="">—</option>
        {optionen.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    );
  }
  const typ = spalte.typ === "int" || spalte.typ === "zahl" ? "text"
    : spalte.typ === "datum" ? "datetime-local" : "text";
  const v = spalte.typ === "datum" && wert ? String(wert).slice(0, 16) : (wert ?? "");
  return (
    <input type={typ} value={v} disabled={gesperrt}
      maxLength={spalte.max_laenge || undefined}
      inputMode={spalte.typ === "int" || spalte.typ === "zahl" ? "decimal" : undefined}
      onChange={e => onChange(e.target.value)}
      style={{ ...inp, opacity: gesperrt ? 0.6 : 1 }} />
  );
}

/** Maske zum Anlegen (zeile = null) oder Bearbeiten einer Zeile. */
function Maske({ meta, zeile, onClose, onSpeichern }) {
  const neu = !zeile;
  const spalten = meta.spalten.filter(s => !(neu && s.auto) && s.name !== meta.aktiv_spalte);
  const [werte, setWerte] = useState(() => Object.fromEntries(
    spalten.map(s => [s.name, zeile ? zeile[s.name] : (s.typ === "bool" ? false : "")])));
  const [busy, setBusy] = useState(false);
  const [fehler, setFehler] = useState(null);

  const fehlend = spalten.filter(s => s.pflicht && (s.bearbeitbar || (neu && s.schluessel))
    && s.typ !== "bool" && (werte[s.name] === "" || werte[s.name] == null));

  const speichern = async () => {
    setBusy(true); setFehler(null);
    try {
      await onSpeichern(werte);
      onClose();
    } catch (e) {
      setFehler(fehlerText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div onClick={busy ? undefined : onClose}
      style={{ position: "fixed", inset: 0, zIndex: 1000, backgroundColor: "rgba(0,0,0,0.55)",
        display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
      <div onClick={e => e.stopPropagation()}
        style={{ width: "min(720px, 96vw)", maxHeight: "90vh", display: "flex",
          flexDirection: "column", backgroundColor: S.bgCard, border: `1px solid ${S.border}`,
          borderRadius: 12, overflow: "hidden", boxShadow: "0 20px 60px rgba(0,0,0,0.5)" }}>
        <div style={{ padding: "14px 18px", borderBottom: `1px solid ${S.border}`,
          display: "flex", alignItems: "center", gap: 10 }}>
          <p style={{ flex: 1, fontSize: 14, fontWeight: 700, color: S.textBright, margin: 0 }}>
            {neu ? "Neuer Eintrag" : `Eintrag ${zeile[meta.key]} bearbeiten`}
          </p>
          <button onClick={onClose} disabled={busy}
            style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer" }}>
            <X size={16} />
          </button>
        </div>

        <div style={{ padding: "14px 18px", overflowY: "auto", display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "10px 16px" }}>
          {spalten.map(s => {
            const gesperrt = !(s.bearbeitbar || (neu && s.schluessel && !s.auto));
            return (
              <div key={s.name}>
                <label style={{ display: "block", fontSize: 10, fontWeight: 700,
                  textTransform: "uppercase", letterSpacing: "0.06em", color: S.textDim,
                  marginBottom: 4 }}>
                  {s.label}{s.pflicht && !gesperrt && s.typ !== "bool" &&
                    <span style={{ color: ROT }}> *</span>}
                  {s.max_laenge && !gesperrt && s.typ === "text" &&
                    <span style={{ fontWeight: 400, textTransform: "none" }}> · max. {s.max_laenge}</span>}
                </label>
                <Feld spalte={s} wert={werte[s.name]} gesperrt={gesperrt}
                  onChange={v => setWerte(w => ({ ...w, [s.name]: v }))} />
              </div>
            );
          })}
        </div>

        {fehler && (
          <div style={{ margin: "0 18px 10px", padding: "8px 12px", borderRadius: 6,
            border: `1px solid ${ROT}`, color: ROT, fontSize: 12, display: "flex", gap: 8 }}>
            <AlertCircle size={14} style={{ flexShrink: 0, marginTop: 1 }} /> {fehler}
          </div>
        )}

        <div style={{ padding: "12px 18px", borderTop: `1px solid ${S.border}`,
          display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 10 }}>
          {fehlend.length > 0 && (
            <span style={{ flex: 1, fontSize: 11, color: S.textDim }}>
              Noch offen: {fehlend.map(s => s.label).join(", ")}
            </span>
          )}
          <button style={btn} onClick={onClose} disabled={busy}>Abbrechen</button>
          <button style={{ ...btn, borderColor: S.accent, color: S.accent,
            opacity: fehlend.length ? 0.5 : 1 }}
            onClick={speichern} disabled={busy || fehlend.length > 0}>
            {busy ? <Loader2 size={13} className="spin" /> : <Save size={13} />}
            {neu ? "Anlegen" : "Speichern"}
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Widget „Datenpflege": eine Tabelle einer angebundenen Datenbank anzeigen,
 * Zeilen anlegen, bearbeiten und sperren.
 *
 * Welche Tabelle, steht in der Widget-Einstellung des gespeicherten Formulars;
 * der Server liest sie dort nach und nimmt vom Browser nur Formular- und
 * Widget-ID entgegen. Löschen gibt es absichtlich nicht – gesperrt wird über
 * die Aktiv-Spalte, damit Verweise aus anderen Tabellen gültig bleiben.
 */
export default function DatenpflegeWidget({ widget, formId }) {
  const [daten, setDaten] = useState(null);
  const [laden, setLaden] = useState(true);
  const [fehler, setFehler] = useState(null);
  const [suche, setSuche] = useState("");
  const [filter, setFilter] = useState("alle");      // alle | aktiv | gesperrt
  const [maske, setMaske] = useState(null);          // { zeile } | { zeile: null }
  const [rueckfrage, setRueckfrage] = useState(null);
  const [hinweis, setHinweis] = useState(null);

  const url = formId ? `/api/datenpflege/${formId}/${widget.id}` : null;

  const neuLaden = useCallback(async () => {
    if (!url) { setLaden(false); return; }
    setLaden(true);
    try {
      const { data } = await api.get(url);
      setDaten(data);
      setFehler(null);
    } catch (e) {
      setFehler(fehlerText(e));
    } finally {
      setLaden(false);
    }
  }, [url]);

  useEffect(() => { neuLaden(); }, [neuLaden]);
  useEffect(() => onMandantChange(() => neuLaden()), [neuLaden]);

  const aktivSp = daten?.aktiv_spalte;
  const sichtbar = useMemo(() => (daten?.spalten || []).filter(s => !s.ausgeblendet), [daten]);

  const zeilen = useMemo(() => {
    let r = daten?.rows || [];
    if (aktivSp && filter !== "alle")
      r = r.filter(z => !!z[aktivSp] === (filter === "aktiv"));
    const t = suche.trim().toLowerCase();
    if (t) r = r.filter(z => sichtbar.some(s => String(z[s.name] ?? "").toLowerCase().includes(t)));
    return r;
  }, [daten, suche, filter, aktivSp, sichtbar]);

  const ersetzeZeile = (zeile) => {
    if (!zeile) return neuLaden();
    setDaten(d => {
      const da = d.rows.some(z => z[d.key] === zeile[d.key]);
      return { ...d, rows: da ? d.rows.map(z => z[d.key] === zeile[d.key] ? zeile : z)
                              : [...d.rows, zeile] };
    });
  };

  const speichern = async (zeile, werte) => {
    if (!zeile) {
      const { data } = await api.post(url, { werte });
      ersetzeZeile(data.zeile);
      setHinweis(`Eintrag ${data.key} angelegt`);
    } else {
      const { data } = await api.put(url, { key: zeile[daten.key], werte, vorher: zeile });
      ersetzeZeile(data.zeile);
      setHinweis(data.geaendert ? `Eintrag ${zeile[daten.key]} gespeichert` : "Keine Änderung");
    }
  };

  const aktivSetzen = async (zeile, aktiv) => {
    try {
      const { data } = await api.post(`${url}/aktiv`, { key: zeile[daten.key], aktiv });
      ersetzeZeile(data.zeile);
      setHinweis(`Eintrag ${zeile[daten.key]} ${aktiv ? "entsperrt" : "gesperrt"}`);
    } catch (e) {
      setFehler(fehlerText(e));
    }
  };

  useEffect(() => {
    if (!hinweis) return;
    const t = setTimeout(() => setHinweis(null), 3500);
    return () => clearTimeout(t);
  }, [hinweis]);

  if (!formId) return (
    <p style={{ padding: 14, fontSize: 12, color: S.textDim }}>
      Die Datenpflege erscheint im Formular selbst (nicht in der Vorschau).
    </p>
  );

  const nurLesen = daten?.nur_lesen;
  const bezeichnung = (z) => {
    const s = sichtbar.find(s => !s.schluessel && s.typ === "text");
    return s ? `„${z[s.name]}“` : `Eintrag ${z[daten.key]}`;
  };
  const anzahlGesperrt = aktivSp ? (daten?.rows || []).filter(z => !z[aktivSp]).length : 0;

  return (
    <div>
      {/* Werkzeugleiste */}
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8,
        padding: "10px 16px", borderBottom: `1px solid ${S.border}` }}>
        <div style={{ position: "relative", flex: "1 1 220px", maxWidth: 340 }}>
          <Search size={13} style={{ position: "absolute", left: 9, top: 8, color: S.textDim }} />
          <input value={suche} onChange={e => setSuche(e.target.value)} placeholder="Suchen …"
            style={{ ...inp, paddingLeft: 28 }} />
        </div>
        {aktivSp && (
          <div style={{ display: "flex", border: `1px solid ${S.border}`, borderRadius: 5,
            overflow: "hidden" }}>
            {[["alle", "Alle"], ["aktiv", "Aktiv"], ["gesperrt", `Gesperrt (${anzahlGesperrt})`]]
              .map(([k, l]) => (
                <button key={k} onClick={() => setFilter(k)}
                  style={{ padding: "5px 10px", fontSize: 11, border: "none", cursor: "pointer",
                    backgroundColor: filter === k ? "rgba(252,228,153,0.12)" : "transparent",
                    color: filter === k ? S.accent : S.textDim }}>{l}</button>
              ))}
          </div>
        )}
        <span style={{ fontSize: 11, color: S.textDim }}>
          {daten ? `${zeilen.length} von ${daten.rows.length}` : ""}
        </span>
        <div style={{ flex: 1 }} />
        {hinweis && <span style={{ fontSize: 11, color: GRUEN }}>{hinweis}</span>}
        <button style={btn} onClick={neuLaden} title="Neu laden" disabled={laden}>
          {laden ? <Loader2 size={13} className="spin" /> : <RotateCcw size={13} />}
        </button>
        {daten && !nurLesen && (
          <button style={{ ...btn, borderColor: S.accent, color: S.accent }}
            onClick={() => setMaske({ zeile: null })}>
            <Plus size={13} /> Neu
          </button>
        )}
      </div>

      {fehler && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 16px",
          color: ROT, fontSize: 12 }}>
          <AlertCircle size={13} /> {fehler}
          <button onClick={() => setFehler(null)} style={{ marginLeft: "auto", background: "none",
            border: "none", color: S.textDim, cursor: "pointer" }}><X size={13} /></button>
        </div>
      )}

      {daten && (
        <div style={{ overflowX: "auto", maxHeight: 560, overflowY: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr>
                {aktivSp && <th style={th}>Status</th>}
                {sichtbar.filter(s => s.name !== aktivSp).map(s => (
                  <th key={s.name} style={th}>{s.label}</th>
                ))}
                <th style={{ ...th, width: 1 }} />
              </tr>
            </thead>
            <tbody>
              {zeilen.map(z => {
                const aktiv = aktivSp ? !!z[aktivSp] : true;
                return (
                  <tr key={z[daten.key]}
                    onDoubleClick={() => !nurLesen && setMaske({ zeile: z })}
                    style={{ borderTop: `1px solid ${S.border}`, opacity: aktiv ? 1 : 0.55 }}>
                    {aktivSp && (
                      <td style={td}>
                        <span style={{ fontSize: 10, fontWeight: 600, padding: "2px 8px",
                          borderRadius: 10, whiteSpace: "nowrap",
                          color: aktiv ? GRUEN : ROT,
                          border: `1px solid ${aktiv ? GRUEN : ROT}` }}>
                          {aktiv ? "aktiv" : "gesperrt"}
                        </span>
                      </td>
                    )}
                    {sichtbar.filter(s => s.name !== aktivSp).map(s => (
                      <td key={s.name} style={td}>{anzeige(s, z[s.name])}</td>
                    ))}
                    <td style={{ ...td, whiteSpace: "nowrap", textAlign: "right" }}>
                      {!nurLesen && (
                        <>
                          <button style={iconBtn} title="Bearbeiten"
                            onClick={() => setMaske({ zeile: z })}><Pencil size={13} /></button>
                          {aktivSp && (aktiv ? (
                            <button style={{ ...iconBtn, color: ROT }} title="Sperren"
                              onClick={() => setRueckfrage({ zeile: z })}><Lock size={13} /></button>
                          ) : (
                            <button style={{ ...iconBtn, color: GRUEN }} title="Entsperren"
                              onClick={() => aktivSetzen(z, true)}><Unlock size={13} /></button>
                          ))}
                        </>
                      )}
                    </td>
                  </tr>
                );
              })}
              {!zeilen.length && (
                <tr><td colSpan={sichtbar.length + 2}
                  style={{ ...td, textAlign: "center", color: S.textDim, padding: 20 }}>
                  {daten.rows.length ? "Keine Treffer" : "Noch keine Einträge"}
                </td></tr>
              )}
            </tbody>
          </table>
          {daten.abgeschnitten && (
            <p style={{ padding: "8px 16px", fontSize: 11, color: S.textDim }}>
              Es werden nur die ersten {daten.rows.length} Zeilen angezeigt.
            </p>
          )}
        </div>
      )}

      {maske && daten && (
        <Maske meta={daten} zeile={maske.zeile} onClose={() => setMaske(null)}
          onSpeichern={(werte) => speichern(maske.zeile, werte)} />
      )}
      {rueckfrage && (
        <BestaetigenModal gefahr titel={`${bezeichnung(rueckfrage.zeile)} sperren?`}
          label="Sperren"
          punkte={[
            `${aktivSp} wird auf 0 gesetzt – der Eintrag bleibt erhalten und lässt sich jederzeit wieder entsperren.`,
            "Verweise aus anderen Tabellen bleiben gültig.",
          ]}
          onBestaetigen={() => aktivSetzen(rueckfrage.zeile, false)}
          onClose={() => setRueckfrage(null)} />
      )}
    </div>
  );
}

const th = {
  position: "sticky", top: 0, backgroundColor: "var(--bg-card)", textAlign: "left",
  padding: "8px 12px", fontSize: 10, fontWeight: 700, textTransform: "uppercase",
  letterSpacing: "0.06em", color: "var(--text-dim)", whiteSpace: "nowrap",
};
const td = { padding: "7px 12px", color: "var(--text-main)", verticalAlign: "top" };
const iconBtn = {
  background: "none", border: "none", color: "var(--text-dim)", cursor: "pointer",
  padding: "2px 5px",
};
