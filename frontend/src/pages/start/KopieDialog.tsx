/**
 * „Kopie anpassen“ (Händler-Ansicht, Phase 3): eine eigene Fassung eines Cockpits
 * mit anderen Vorgaben – Zeitraum und die übrigen Filter des Cockpits.
 * Die Kopie nutzt dieselben Abfragen; sie startet nur mit anderen Werten.
 */
import { useEffect, useState } from "react";
import { Loader2, X } from "lucide-react";
import api, { fehlerText } from "../../api/client";
import FormFields, { DEFAULT_PRESETS, feldVorgabe } from "../../components/forms/FormFields";
import { S, knopf } from "./StartLayout";

// Felder, die keine Vorgabe tragen: Knöpfe, Überschriften, Pflegemasken.
const OHNE_VORGABE = new Set(["button", "heading", "label", "divider", "container", "article_exclusion", "daterange"]);

export default function KopieDialog({ cockpit, onClose, onFertig }) {
  const [form, setForm] = useState(null);
  const [name, setName] = useState(`${cockpit.name} – meine Fassung`);
  const [zeitraum, setZeitraum] = useState({});     // daterange-Feldname → Preset-ID
  const [werte, setWerte] = useState({});
  const [fehler, setFehler] = useState(null);
  const [speichert, setSpeichert] = useState(false);

  useEffect(() => {
    api.get(`/api/forms/${cockpit.id}`).then(({ data }) => {
      setForm(data);
      const felder = data.schema?.fields || [];
      setZeitraum(Object.fromEntries(felder.filter((f) => f.type === "daterange")
        .map((f) => [f.name, f.config?.default || ""])));
      const isMulti = (f) => f.type === "multiselect" || (f.type === "db_dropdown" && f.config?.multiple);
      setWerte(Object.fromEntries(felder.filter((f) => f.name && !OHNE_VORGABE.has(f.type))
        .map((f) => [f.name, feldVorgabe(f, isMulti(f))])));
    }).catch((e) => setFehler(fehlerText(e)));
  }, [cockpit.id]);

  useEffect(() => {
    const esc = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [onClose]);

  const felder = form?.schema?.fields || [];
  const datumsfelder = felder.filter((f) => f.type === "daterange");
  const filterfelder = felder.filter((f) => f.name && !OHNE_VORGABE.has(f.type));

  const speichern = async () => {
    setSpeichert(true); setFehler(null);
    try {
      const vorgaben = { ...werte };
      for (const [k, v] of Object.entries(zeitraum)) if (v) vorgaben[k] = v;
      const { data } = await api.post(`/api/start/cockpits/${cockpit.id}/kopie`, { name, vorgaben });
      onFertig(data);
    } catch (e) {
      setFehler(fehlerText(e));
    } finally {
      setSpeichert(false);
    }
  };

  return (
    <div role="dialog" aria-modal="true" aria-labelledby="kopie-titel" onClick={onClose}
      style={{ position: "fixed", inset: 0, zIndex: 50, backgroundColor: "rgba(0,0,0,0.55)", display: "flex",
        alignItems: "flex-start", justifyContent: "center", padding: "60px 16px", overflowY: "auto" }}>
      <div onClick={(e) => e.stopPropagation()}
        style={{ width: "100%", maxWidth: 640, backgroundColor: S.bgCard, border: `1px solid ${S.border}`, borderRadius: 14,
          padding: 24, display: "flex", flexDirection: "column", gap: 18, color: S.textMain }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
          <div>
            <h2 id="kopie-titel" style={{ margin: 0, fontSize: 20, fontWeight: 700, color: S.textBright }}>Eigene Fassung von „{cockpit.name}“</h2>
            <p style={{ margin: "4px 0 0", fontSize: 13.5, color: S.textDim, lineHeight: 1.5 }}>
              Die Kopie startet mit Ihren Vorgaben. Das Original bleibt unverändert.
            </p>
          </div>
          <button onClick={onClose} aria-label="Schließen"
            style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 6, minWidth: 36, minHeight: 36 }}>
            <X size={18} />
          </button>
        </div>

        {!form && !fehler && <span style={{ color: S.textDim }}>Lädt…</span>}

        {datumsfelder.map((f) => {
          const presets = f.config?.presets || DEFAULT_PRESETS;
          return (
            <div key={f.name} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <span style={{ fontSize: 13, color: S.textDim }}>{f.label || "Zeitraum"} beim Öffnen</span>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {presets.map((p) => {
                  const an = zeitraum[f.name] === p.id;
                  return (
                    <button key={p.id} onClick={() => setZeitraum((z) => ({ ...z, [f.name]: p.id }))} aria-pressed={an}
                      style={{ padding: "6px 14px", minHeight: 36, borderRadius: 999, cursor: "pointer", fontSize: 13,
                        border: `1px solid ${an ? S.accent : S.border}`, fontWeight: an ? 700 : 400,
                        backgroundColor: an ? S.accent : "transparent", color: an ? S.accentFg : S.textMain }}>
                      {p.label}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}

        {filterfelder.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <span style={{ fontSize: 13, color: S.textDim }}>Weitere Vorgaben</span>
            <FormFields fields={filterfelder} params={werte}
              setParam={(k, v) => setWerte((w) => ({ ...w, [k]: v }))}
              onRunAction={() => {}} running={false} compact errors={[]} />
          </div>
        )}

        <div>
          <label htmlFor="kopie-name" style={{ fontSize: 13, color: S.textDim, display: "block", marginBottom: 6 }}>Name</label>
          <input id="kopie-name" value={name} onChange={(e) => setName(e.target.value)}
            style={{ width: "100%", minHeight: 44, padding: "10px 12px", borderRadius: 8, boxSizing: "border-box",
              border: `1px solid ${S.border}`, backgroundColor: S.bgMain, color: S.textMain, fontSize: 14 }} />
        </div>

        {fehler && <p style={{ color: "var(--err)", margin: 0 }}>{fehler}</p>}

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", flexWrap: "wrap" }}>
          <button onClick={onClose} style={knopf.neben}>Abbrechen</button>
          <button onClick={speichern} disabled={speichert || !form || !name.trim()} style={knopf.haupt}>
            {speichert && <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} />}
            Kopie anlegen
          </button>
        </div>
      </div>
    </div>
  );
}
