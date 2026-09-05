import { useState, useEffect, useCallback } from "react";
import { FileSpreadsheet, AlertCircle, Loader2, Building2, Check,
         RotateCcw } from "lucide-react";
import api from "../../../api/client";
import { fehlerText } from "../../../api/client";
import { onMandantChange } from "../../../services/mandant";

const S = {
  bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)", bgMain: "var(--bg-main)",
  border: "var(--border)", textMain: "var(--text-main)", textDim: "var(--text-dim)",
  textBright: "var(--text-bright)", accent: "var(--accent)",
};

const inp = {
  backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4,
  color: S.textMain, fontSize: 12, padding: "6px 9px", outline: "none",
  width: "100%", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
};

/**
 * Widget "DATEV-Stammdaten": Berater-/Mandantennummer, USt-IdNr. und Sachkonten.
 *
 * ⭐ Warum je Mandant und nicht im Installationsdialog: diese Werte bezeichnen den
 * BETRIEB, nicht die Auswertung. Standen sie fest im Mapping, trug ein Export
 * unter dem Mandanten-Umschalter die Zahlen des einen und die Beraternummer des
 * anderen Betriebs – der Stapel landete beim Steuerberater im falschen Mandanten,
 * und zwar lautlos. Deshalb hängen sie hier am Umschalter: gepflegt wird immer
 * der Mandant, der oben steht.
 *
 * Die Werte gehen als :cfg_datev_* und :cfg_konto_* in jeden Lauf ein; die
 * Abfragen setzen daraus ihre Gegenkonten und geben die Kennung als Spalte aus.
 */
export default function DatevStammdatenWidget({ widget, projectId, canEdit = true }) {
  const [felder, setFelder] = useState([]);
  const [entwurf, setEntwurf] = useState({});      // key → getippter Wert
  const [mandant, setMandant] = useState(null);
  const [fehlend, setFehlend] = useState([]);
  const [laden, setLaden] = useState(true);
  const [fehler, setFehler] = useState(null);
  const [speichert, setSpeichert] = useState(null);
  const [gespeichert, setGespeichert] = useState(null);

  const q = projectId ? `?project_id=${projectId}` : "";

  const laden_ = useCallback(async () => {
    setLaden(true);
    try {
      const { data } = await api.get(`/api/business-config/datev${q}`);
      setFelder(data.felder || []);
      setEntwurf(Object.fromEntries((data.felder || []).map(f => [f.key, f.value ?? ""])));
      setMandant(data.mandant_name || null);
      setFehlend(data.fehlend || []);
      setFehler(null);
    } catch (e) {
      setFehler(fehlerText(e));
    } finally {
      setLaden(false);
    }
  }, [q]);

  useEffect(() => { laden_(); }, [laden_]);

  // Beim Mandantenwechsel neu laden – sonst tippt man die Beraternummer des
  // einen Betriebs in die Maske des anderen.
  useEffect(() => onMandantChange(() => { laden_(); }), [laden_]);

  const speichern = async (key) => {
    const feld = felder.find(f => f.key === key);
    const wert = (entwurf[key] ?? "").trim();
    if (!feld || wert === (feld.value ?? "")) return;   // nichts geändert
    setSpeichert(key); setFehler(null);
    try {
      await api.put("/api/business-config/datev",
        { project_id: projectId ?? null, key, value: wert });
      setGespeichert(key);
      setTimeout(() => setGespeichert(g => (g === key ? null : g)), 1500);
      await laden_();
    } catch (e) {
      setFehler(fehlerText(e));
      // Zurück auf den gespeicherten Stand: ein abgelehnter Wert darf nicht
      // stehen bleiben, sonst hält man ihn für hinterlegt.
      setEntwurf(prev => ({ ...prev, [key]: feld.value ?? "" }));
    } finally {
      setSpeichert(null);
    }
  };

  const zuruecksetzen = async (key) => {
    setEntwurf(prev => ({ ...prev, [key]: "" }));
    setSpeichert(key);
    try {
      await api.put("/api/business-config/datev",
        { project_id: projectId ?? null, key, value: "" });
      await laden_();
    } catch (e) {
      setFehler(fehlerText(e));
    } finally {
      setSpeichert(null);
    }
  };

  const gruppen = [];
  for (const f of felder) {
    let g = gruppen.find(x => x.label === f.gruppe);
    if (!g) { g = { label: f.gruppe, felder: [] }; gruppen.push(g); }
    g.felder.push(f);
  }

  if (laden)
    return <div style={{ padding: 24, color: S.textDim, fontSize: 12,
      display: "flex", alignItems: "center", gap: 8 }}>
      <Loader2 size={14} className="animate-spin" /> Stammdaten werden geladen …
    </div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18, padding: 16 }}>
      <div style={{ display: "flex", alignItems: "flex-start",
        justifyContent: "space-between", gap: 20 }}>
        <p style={{ fontSize: 11.5, color: S.textDim, maxWidth: 720,
          display: "flex", alignItems: "flex-start", gap: 7, margin: 0 }}>
          <FileSpreadsheet size={14} style={{ color: S.accent, flexShrink: 0, marginTop: 1 }} />
          <span>
            Kennung und Konten {mandant ? <>von <b>{mandant}</b></> : "dieses Projekts"},
            wie sie in der Kopfzeile des Buchungsstapels stehen. Berater- und
            Mandantennummer bekommst du vom <b>Steuerberater</b>. Die Konten sind auf
            SKR03 vorbelegt – bei SKR04 hier überschreiben. Gespeichert wird beim
            Verlassen des Feldes, <b>getrennt je Mandant</b>.
          </span>
        </p>
        {mandant && (
          <div style={{ display: "flex", alignItems: "center", gap: 5,
            whiteSpace: "nowrap", fontSize: 11.5, fontWeight: 600, color: S.accent }}>
            <Building2 size={12} /> {mandant}
          </div>
        )}
      </div>

      {fehler && (
        <div style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 12,
          color: "#f87171", backgroundColor: "rgba(248,113,113,.08)",
          border: "1px solid rgba(248,113,113,.25)", borderRadius: 6, padding: "8px 11px" }}>
          <AlertCircle size={14} /> {fehler}
        </div>
      )}

      {/* Was fehlt, muss VOR dem Export auffallen – nicht erst, wenn der
          Steuerberater den Stapel zurueckweist. */}
      {fehlend.length > 0 && (
        <div style={{ display: "flex", alignItems: "flex-start", gap: 7, fontSize: 12,
          color: "#fbbf24", backgroundColor: "rgba(251,191,36,.08)",
          border: "1px solid rgba(251,191,36,.25)", borderRadius: 6, padding: "9px 11px" }}>
          <AlertCircle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
          <span>Noch nicht hinterlegt: <b>{fehlend.join(", ")}</b>
            {mandant ? <> für <b>{mandant}</b></> : null}. Ohne diese Angaben weist
            DATEV den Buchungsstapel beim Einlesen ab.</span>
        </div>
      )}

      {gruppen.map(g => (
        <div key={g.label} style={{ backgroundColor: S.bgCard,
          border: `1px solid ${S.border}`, borderRadius: 8, overflow: "hidden" }}>
          <div style={{ padding: "8px 13px", backgroundColor: S.bgMain,
            borderBottom: `1px solid ${S.border}`, fontSize: 11, fontWeight: 600,
            letterSpacing: .4, textTransform: "uppercase", color: S.textDim }}>
            {g.label}
          </div>
          <div style={{ padding: 13, display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 13 }}>
            {g.felder.map(f => (
              <div key={f.key}>
                <label style={{ display: "flex", alignItems: "center", gap: 5,
                  fontSize: 11, color: S.textBright, marginBottom: 4 }}>
                  {f.label}
                  {f.identitaet && !String(entwurf[f.key] ?? "").trim() && (
                    <span style={{ color: "#fbbf24", fontSize: 13, lineHeight: 1 }}>•</span>
                  )}
                  {speichert === f.key && <Loader2 size={11} className="animate-spin" />}
                  {gespeichert === f.key && <Check size={12} style={{ color: "#4ade80" }} />}
                </label>
                <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                  <input
                    value={entwurf[f.key] ?? ""}
                    disabled={!canEdit}
                    onChange={e => setEntwurf(p => ({ ...p, [f.key]: e.target.value }))}
                    onBlur={() => canEdit && speichern(f.key)}
                    onKeyDown={e => { if (e.key === "Enter") e.currentTarget.blur(); }}
                    placeholder={f.default || "—"}
                    style={{ ...inp, opacity: canEdit ? 1 : .6 }}
                  />
                  {/* Nur bei Konten sinnvoll: sie haben einen echten Standard,
                      auf den man zurueckfallen kann. */}
                  {canEdit && !f.identitaet && f.default && !f.is_default && (
                    <button onClick={() => zuruecksetzen(f.key)} title={`Zurück auf ${f.default}`}
                      style={{ background: "none", border: "none", cursor: "pointer",
                        color: S.textDim, padding: 3, display: "flex" }}>
                      <RotateCcw size={12} />
                    </button>
                  )}
                </div>
                {f.hinweis && (
                  <div style={{ fontSize: 10.5, color: S.textDim, marginTop: 3 }}>
                    {f.hinweis}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
