import { useState, useEffect, useCallback, useRef } from "react";
import { Wand2, Loader2, Play, Hammer, Trash2, RotateCcw, CheckCircle2,
         AlertTriangle, ChevronRight, ChevronDown, X, Sparkles, Info,
         Building2, Inbox, Unlink, Package, Plus } from "lucide-react";
import api from "../../../api/client";
import { useAIAssistant } from "../../../contexts/AIAssistantContext";
import MandantWaehler from "../../MandantWaehler";
import { onMandantChange } from "../../../services/mandant";

const S = {
  bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)", bgMain: "var(--bg-main)",
  border: "var(--border)", textMain: "var(--text-main)", textDim: "var(--text-dim)",
  textBright: "var(--text-bright)", accent: "var(--accent)",
};

const STATUS = {
  entwurf:        { farbe: "var(--accent)", label: "Entwurf" },
  installiert:    { farbe: "#5cb85c",       label: "Gebaut" },
  teilrueckbau:   { farbe: "#e8913a",       label: "Teilweise zurückgebaut" },
  zurueckgebaut:  { farbe: "#777",          label: "Zurückgebaut" },
};

const inp = {
  backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4,
  color: S.textMain, fontSize: 12, padding: "6px 8px", outline: "none", width: "100%",
};

const knopf = (aktiv = true) => ({
  fontSize: 12, fontWeight: 600, padding: "7px 14px", borderRadius: 5,
  border: "none", cursor: aktiv ? "pointer" : "not-allowed",
  backgroundColor: S.accent, color: "#111", opacity: aktiv ? 1 : 0.5,
  display: "inline-flex", alignItems: "center", gap: 6,
});

const knopfLeer = {
  fontSize: 12, padding: "7px 14px", borderRadius: 5, cursor: "pointer",
  border: `1px solid ${S.border}`, background: "transparent", color: S.textDim,
  display: "inline-flex", alignItems: "center", gap: 6,
};

/**
 * KI-Werkbank: aus einem Satz ein Bauvorhaben.
 *
 * Vier Schritte – Beschreiben, Bauzettel prüfen, Vorschau, Übernehmen. Die
 * Häkchen am Bauzettel sind bewusst VORBELEGT statt vorgeschaltet: „Mapping
 * oder Report?" ist die Frage der Plattform, nicht die des Anwenders. Er sagt,
 * was er sehen will; korrigieren kann er trotzdem alles.
 */
export default function WerkbankPanel({ projectId, canEdit }) {
  const [vorhaben, setVorhaben] = useState([]);
  const [aktiv, setAktiv] = useState(null);
  const [werkzeuge, setWerkzeuge] = useState(null);
  const [abfrageSchema, setAbfrageSchema] = useState(null);
  const [mandanten, setMandanten] = useState([]);
  const [betrieb, setBetrieb] = useState(null);       // gegen welche DB gebaut wird
  const [betriebWahl, setBetriebWahl] = useState(null);
  const [adoption, setAdoption] = useState(null);     // {eintraege, anzahl}
  const [adoptionOffen, setAdoptionOffen] = useState(false);
  const [laden, setLaden] = useState(true);
  const [fehler, setFehler] = useState(null);

  const [beschreibung, setBeschreibung] = useState("");
  const [planLaeuft, setPlanLaeuft] = useState(false);
  const [fortschritt, setFortschritt] = useState("");
  const [rueckfragen, setRueckfragen] = useState([]);

  const [vorschau, setVorschau] = useState(null);
  const [vorschauLaeuft, setVorschauLaeuft] = useState(false);
  const [baut, setBaut] = useState(false);
  const [offen, setOffen] = useState({});          // Schritt-Index → aufgeklappt
  const [templateOffen, setTemplateOffen] = useState(false);
  const [templateErg, setTemplateErg] = useState(null);
  const [rueckbauPlan, setRueckbauPlan] = useState(null);
  const [rueckbauLaeuft, setRueckbauLaeuft] = useState(false);

  const eingabeRef = useRef(null);
  const q = projectId ? `?project_id=${projectId}` : "";

  // Der schwebende Assistent verschwindet, solange die Werkbank offen ist: sie
  // IST derselbe Assistent, nur ganzseitig. Zwei Einstiege nebeneinander sind
  // kein Angebot, sondern eine Frage, die der Anwender nicht beantworten kann.
  const { setVersteckt } = useAIAssistant();
  useEffect(() => { setVersteckt(true); return () => setVersteckt(false); },
            [setVersteckt]);

  const listeLaden = useCallback(async () => {
    setLaden(true);
    try {
      const { data } = await api.get(`/api/werkbank/vorhaben${q}`);
      setVorhaben(data || []);
      setFehler(null);
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
    } finally {
      setLaden(false);
    }
  }, [q]);

  useEffect(() => { listeLaden(); }, [listeLaden]);
  useEffect(() => {
    api.get("/api/werkbank/werkzeuge").then(r => setWerkzeuge(r.data)).catch(() => {});
    api.get("/api/query/schema").then(r => setAbfrageSchema(r.data)).catch(() => {});
  }, []);
  useEffect(() => {
    api.get(`/api/mandanten${q}`).then(r => setMandanten(r.data?.mandanten || []))
       .catch(() => setMandanten([]));
  }, [q]);

  const betriebLaden = useCallback(() => {
    api.get(`/api/werkbank/betrieb${q}`).then(r => { setBetrieb(r.data);
      setBetriebWahl(null); }).catch(() => setBetrieb(null));
  }, [q]);
  useEffect(() => { betriebLaden(); }, [betriebLaden]);

  const adoptionLaden = useCallback(() => {
    api.get(`/api/werkbank/adoptieren${q}`).then(r => setAdoption(r.data))
       .catch(() => setAdoption(null));
  }, [q]);
  useEffect(() => { adoptionLaden(); }, [adoptionLaden]);

  const uebernehmen = async (auswahl) => {
    try {
      await api.post("/api/werkbank/adoptieren",
        { auswahl, project_id: projectId ?? null });
      setAdoptionOffen(false);
      adoptionLaden();
      listeLaden();
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
    }
  };
  // Ein Vorhaben gehört einem Mandanten. Nach dem Wechsel stünden sonst die
  // Zahlen des einen Betriebs unter dem Namen des anderen.
  useEffect(() => onMandantChange(() => { listeLaden(); betriebLaden(); setVorschau(null); }),
            [listeLaden, betriebLaden]);

  const oeffnen = async (id) => {
    setVorschau(null); setRueckfragen([]); setFehler(null);
    try {
      const { data } = await api.get(`/api/werkbank/vorhaben/${id}`);
      setAktiv(data);
      setOffen({ 0: true });
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
    }
  };

  // ── Bauzettel erzeugen (Datenstrom) ────────────────────────────────────────
  const verstehen = async () => {
    const text = beschreibung.trim();
    if (!text) return;
    setPlanLaeuft(true); setFehler(null); setFortschritt("Anfrage läuft …");
    setVorschau(null); setRueckfragen([]);
    try {
      const resp = await fetch("/api/werkbank/verstehen", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("dm_token") || ""}`,
        },
        body: JSON.stringify({ beschreibung: text, project_id: projectId ?? null,
                               mandant_id: betriebWahl ?? betrieb?.connection_id ?? null }),
      });
      if (!resp.ok) {
        const e = await resp.json().catch(() => ({}));
        throw new Error(e.detail || `Backend-Fehler (HTTP ${resp.status})`);
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let puffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        puffer += decoder.decode(value, { stream: true });
        const zeilen = puffer.split("\n");
        puffer = zeilen.pop();
        for (const z of zeilen) {
          if (!z.startsWith("data:")) continue;
          const roh = z.slice(5).trim();
          if (roh === "[DONE]") continue;
          let msg;
          try { msg = JSON.parse(roh); } catch { continue; }
          if (msg.fortschritt) setFortschritt(msg.fortschritt);
          if (msg.fehler) throw new Error(msg.fehler);
          if (msg.vorhaben) {
            setAktiv({ ...msg.vorhaben, artefakte: [] });
            setRueckfragen(msg.rueckfragen || []);
            setBeschreibung("");
            setOffen({ 0: true });
            listeLaden();
          }
        }
      }
    } catch (e) {
      setFehler(e.message);
    } finally {
      setPlanLaeuft(false); setFortschritt("");
    }
  };

  // ── Bauplan ändern ─────────────────────────────────────────────────────────
  const planSpeichern = async (bauplan, extra = {}) => {
    if (!aktiv) return null;
    try {
      const { data } = await api.put(`/api/werkbank/vorhaben/${aktiv.id}`,
        { bauplan, ...extra });
      setAktiv(data);
      listeLaden();
      return data;
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
      return null;
    }
  };

  const schrittAendern = (i, aenderung) => {
    const plan = (aktiv.bauplan || []).map((s, idx) =>
      idx === i ? { ...s, ...aenderung } : s);
    setAktiv({ ...aktiv, bauplan: plan });        // sofort sichtbar
    return plan;
  };

  const eingabeAendern = (i, feld, wert) => {
    const s = aktiv.bauplan[i];
    schrittAendern(i, { eingabe: { ...(s.eingabe || {}), [feld]: wert } });
  };

  const vorschauLaufen = async () => {
    if (!aktiv) return;
    setVorschauLaeuft(true); setFehler(null);
    const gespeichert = await planSpeichern(aktiv.bauplan);
    if (!gespeichert) { setVorschauLaeuft(false); return; }
    try {
      const { data } = await api.post(`/api/werkbank/vorhaben/${aktiv.id}/vorschau`);
      setVorschau(data.schritte || []);
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
    } finally {
      setVorschauLaeuft(false);
    }
  };

  const bauenLaufen = async (neu = false) => {
    if (!aktiv) return;
    setBaut(true); setFehler(null);
    const gespeichert = await planSpeichern(aktiv.bauplan);
    if (!gespeichert) { setBaut(false); return; }
    try {
      const pfad = neu ? "neu-bauen" : "bauen";
      const { data } = await api.post(`/api/werkbank/vorhaben/${aktiv.id}/${pfad}`);
      setAktiv(data.vorhaben);
      setVorschau(null);
      listeLaden();
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
    } finally {
      setBaut(false);
    }
  };

  const alsTemplate = async (angaben) => {
    try {
      const { data } = await api.post(
        `/api/werkbank/vorhaben/${aktiv.id}/als-template`, angaben);
      setTemplateErg(data);
      setTemplateOffen(false);
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
    }
  };

  const rueckbauPruefen = async () => {
    try {
      const { data } = await api.post(
        `/api/werkbank/vorhaben/${aktiv.id}/rueckbau/vorschau`);
      setRueckbauPlan(data);
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
    }
  };

  const rueckbauAusfuehren = async (nurUngenutzte) => {
    setRueckbauLaeuft(true);
    try {
      await api.delete(`/api/werkbank/vorhaben/${aktiv.id}` +
        `?nur_ungenutzte=${nurUngenutzte ? "true" : "false"}`);
      setRueckbauPlan(null);
      await oeffnen(aktiv.id);
      listeLaden();
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
    } finally {
      setRueckbauLaeuft(false);
    }
  };

  const aufloesen = async (id) => {
    try {
      await api.post(`/api/werkbank/vorhaben/${id}/aufloesen`);
      if (aktiv?.id === id) setAktiv(null);
      adoptionLaden();
      listeLaden();
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
    }
  };

  const eintragLoeschen = async (id) => {
    try {
      await api.delete(`/api/werkbank/vorhaben/${id}/eintrag`);
      if (aktiv?.id === id) setAktiv(null);
      listeLaden();
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
    }
  };

  // ────────────────────────────────────────────────────────────────────────────
  const istGebaut = aktiv?.status === "installiert";

  return (
    <div>
      {/* Der Betrieb gehört ohne Klick sichtbar – wer eine Zahl liest, muss
          wissen, von welcher Warenwirtschaft sie stammt. Er steht deshalb
          dauerhaft im Kopf, nicht nur auf dem Startbildschirm. */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16,
          paddingBottom: 12, borderBottom: `1px solid ${S.border}` }}>
        <Wand2 size={16} style={{ color: S.accent }} />
        <div style={{ flex: 1 }}>
          <p style={{ margin: 0, fontSize: 13, fontWeight: 700, color: S.textBright }}>
            KI-Werkbank
          </p>
          <p style={{ margin: 0, fontSize: 11, color: S.textDim }}>
            Neue Vorhaben werden für den hier gewählten Betrieb gebaut
          </p>
        </div>
        <BetriebAnzeige betrieb={betrieb} wahl={betriebWahl} onWahl={setBetriebWahl}
          projectId={projectId} />
      </div>

      {betrieb?.hinweis && betrieb.quelle !== "einzige_verbindung" && (
        <div style={{ marginBottom: 14, padding: "10px 14px", borderRadius: 6,
            background: betrieb.connection_id ? "rgba(252,228,153,0.07)"
                                              : "rgba(232,145,58,0.1)",
            border: `1px solid ${betrieb.connection_id ? "rgba(252,228,153,0.25)"
                                                       : "rgba(232,145,58,0.35)"}` }}>
          <p style={{ margin: 0, fontSize: 12, color: S.textMain, lineHeight: 1.55 }}>
            {betrieb.hinweis}
          </p>
        </div>
      )}

    <div style={{ display: "flex", gap: 18, alignItems: "flex-start" }}>
      {/* ── Vorhabenliste ── */}
      <div style={{ width: 260, flexShrink: 0, display: "flex", flexDirection: "column",
                    gap: 10, position: "sticky", top: 0 }}>
        <button onClick={() => { setAktiv(null); setVorschau(null); setRueckfragen([]);
                                 setTimeout(() => eingabeRef.current?.focus(), 50); }}
          style={{ ...knopf(true), width: "100%", justifyContent: "center" }}>
          <Sparkles size={13} /> Neues Vorhaben
        </button>

        {/* Wer den Abfrage-Generator oder den Baukasten schon benutzt hat, hat
            Objekte im Bestand, die von der Werkbank nichts wissen – und damit
            keinen sicheren Rückbau. */}
        {adoption?.anzahl > 0 && (
          <button onClick={() => setAdoptionOffen(true)}
            style={{ ...knopfLeer, width: "100%", justifyContent: "center",
                     fontSize: 11.5, color: S.accent,
                     borderColor: "rgba(252,228,153,0.35)" }}>
            <Inbox size={13} /> {adoption.anzahl} aus dem Bestand übernehmen
          </button>
        )}

        <div style={{ maxHeight: "calc(100vh - 260px)", overflowY: "auto",
                      display: "flex", flexDirection: "column", gap: 4 }}>
          {laden && <p style={{ fontSize: 12, color: S.textDim }}>Lade …</p>}
          {!laden && vorhaben.length === 0 && (
            <p style={{ fontSize: 12, color: S.textDim, lineHeight: 1.6, margin: 0 }}>
              Noch kein Vorhaben. Beschreibe rechts, was du sehen willst.
            </p>
          )}
          {vorhaben.map(v => {
            const st = STATUS[v.status] || STATUS.entwurf;
            const gewaehlt = aktiv?.id === v.id;
            return (
              <button key={v.id} onClick={() => oeffnen(v.id)}
                style={{ textAlign: "left", padding: "9px 10px", borderRadius: 6,
                  border: `1px solid ${gewaehlt ? S.accent : S.border}`,
                  backgroundColor: gewaehlt ? "rgba(252,228,153,0.07)" : S.bgCard,
                  cursor: "pointer", display: "flex", flexDirection: "column", gap: 4 }}>
                <span style={{ fontSize: 12.5, fontWeight: 600, color: S.textBright,
                               lineHeight: 1.3 }}>{v.name}</span>
                <span style={{ fontSize: 10.5, color: S.textDim, display: "flex",
                               alignItems: "center", gap: 5 }}>
                  <span style={{ width: 6, height: 6, borderRadius: "50%",
                                 backgroundColor: st.farbe }} />
                  {st.label} · {(v.bauplan || []).filter(s => s.aktiv).length} Schritt(e)
                  {v.mandant ? ` · ${v.mandant}` : ""}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Arbeitsfläche ── */}
      <div style={{ flex: 1, minWidth: 0 }}>
        {fehler && (
          <div style={{ marginBottom: 12, padding: "10px 14px", borderRadius: 6,
              background: "rgba(224,86,86,0.1)", border: "1px solid rgba(224,86,86,0.3)" }}>
            <p style={{ margin: 0, fontSize: 12, color: "#e05656" }}>{fehler}</p>
          </div>
        )}

        {!aktiv ? (
          <Beschreiben value={beschreibung} onChange={setBeschreibung}
            onSubmit={verstehen} laeuft={planLaeuft} fortschritt={fortschritt}
            eingabeRef={eingabeRef} projectId={projectId}
            canEdit={canEdit && !!(betriebWahl ?? betrieb?.connection_id)} />
        ) : (
          <>
            <Kopf v={aktiv} mandanten={mandanten} gebaut={istGebaut}
              onUmbenennen={n => planSpeichern(aktiv.bauplan, { name: n })}
              onMandant={id => planSpeichern(aktiv.bauplan, { mandant_id: id })} />

            {rueckfragen.length > 0 && (
              <div style={{ margin: "0 0 14px", padding: "12px 14px", borderRadius: 6,
                  background: "rgba(252,228,153,0.07)",
                  borderLeft: `3px solid ${S.accent}` }}>
                <p style={{ margin: "0 0 6px", fontSize: 12, fontWeight: 700,
                            color: S.textBright }}>Bevor gebaut wird</p>
                {rueckfragen.map((r, i) => (
                  <p key={i} style={{ margin: "0 0 4px", fontSize: 12, color: S.textMain }}>
                    · {r}
                  </p>
                ))}
              </div>
            )}

            {(aktiv.hinweise || []).length > 0 && (
              <div style={{ margin: "0 0 14px", padding: "10px 14px", borderRadius: 6,
                  backgroundColor: S.bgCard, border: `1px solid ${S.border}` }}>
                {aktiv.hinweise.map((h, i) => (
                  <p key={i} style={{ margin: "0 0 3px", fontSize: 11.5, color: S.textDim,
                                      display: "flex", gap: 6 }}>
                    <Info size={12} style={{ flexShrink: 0, marginTop: 2 }} /> {h}
                  </p>
                ))}
              </div>
            )}

            {/* Bauzettel */}
            <p style={{ fontSize: 11, fontWeight: 700, color: S.textDim, margin: "0 0 8px",
                        textTransform: "uppercase", letterSpacing: "0.05em" }}>
              Bauzettel
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 6,
                          marginBottom: 16 }}>
              {(aktiv.bauplan || []).map((s, i) => (
                <Schritt key={i} s={s} i={i} offen={!!offen[i]} gebaut={istGebaut}
                  werkzeuge={werkzeuge} abfrageSchema={abfrageSchema}
                  vorschau={(vorschau || []).find(x => x.werkzeug === s.werkzeug)}
                  onToggle={() => setOffen(o => ({ ...o, [i]: !o[i] }))}
                  onAktiv={a => schrittAendern(i, { aktiv: a })}
                  onEingabe={(f, w) => eingabeAendern(i, f, w)} />
              ))}
            </div>

            {/* Aktionen */}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center",
                          paddingTop: 12, borderTop: `1px solid ${S.border}` }}>
              {!istGebaut && (
                <>
                  <button onClick={vorschauLaufen} disabled={vorschauLaeuft || !canEdit}
                    style={knopfLeer}>
                    {vorschauLaeuft ? <Loader2 size={13} className="animate-spin" />
                                    : <Play size={13} />} Vorschau mit echten Zahlen
                  </button>
                  <button onClick={() => bauenLaufen(false)}
                    disabled={baut || !canEdit} style={knopf(!baut && canEdit)}>
                    {baut ? <Loader2 size={13} className="animate-spin" />
                          : <Hammer size={13} />} Übernehmen
                  </button>
                </>
              )}
              {istGebaut && (
                <>
                  <button onClick={() => bauenLaufen(true)} disabled={baut || !canEdit}
                    style={knopfLeer}>
                    {baut ? <Loader2 size={13} className="animate-spin" />
                          : <RotateCcw size={13} />} Neu bauen
                  </button>
                  <button onClick={() => { setTemplateErg(null); setTemplateOffen(true); }}
                    disabled={!canEdit} style={knopfLeer}
                    title="Bündelt Mappings, Formulare und Pipelines dieses Vorhabens als installierbares Template">
                    <Package size={13} /> Als Template
                  </button>
                  <button onClick={rueckbauPruefen} disabled={!canEdit}
                    style={{ ...knopfLeer, color: "#e05656",
                             borderColor: "rgba(224,86,86,0.4)" }}>
                    <Trash2 size={13} /> Zurückbauen
                  </button>
                </>
              )}
              {(aktiv.status === "zurueckgebaut" || aktiv.status === "entwurf") && (
                <button onClick={() => eintragLoeschen(aktiv.id)} style={{
                  ...knopfLeer, marginLeft: "auto", fontSize: 11 }}>
                  <X size={12} /> Eintrag entfernen
                </button>
              )}
              {istGebaut && (
                <button onClick={() => aufloesen(aktiv.id)} style={{
                  ...knopfLeer, marginLeft: "auto", fontSize: 11 }}
                  title="Nimmt dem Vorhaben nur die Zuordnung – Auswertung, Report und Zeitplan bleiben unverändert bestehen">
                  <Unlink size={12} /> Zuordnung aufheben
                </button>
              )}
            </div>

            {templateErg && (
              <div style={{ marginTop: 14, padding: "11px 14px", borderRadius: 6,
                  background: "rgba(110,231,183,0.09)",
                  border: "1px solid rgba(110,231,183,0.3)" }}>
                <p style={{ margin: 0, fontSize: 12, color: S.textMain, lineHeight: 1.55 }}>
                  Template angelegt: <b>{templateErg.template_id}</b> —{" "}
                  {templateErg.mappings} Mapping(s), {templateErg.forms} Formular(e),
                  {" "}{templateErg.pipelines} Pipeline(s). Es steht jetzt unter
                  „Templates" zum Installieren und Herunterladen bereit.
                </p>
              </div>
            )}

            {/* Was gebaut wurde */}
            {(aktiv.artefakte || []).length > 0 && (
              <div style={{ marginTop: 20 }}>
                <p style={{ fontSize: 11, fontWeight: 700, color: S.textDim,
                    margin: "0 0 8px", textTransform: "uppercase",
                    letterSpacing: "0.05em" }}>Angelegt</p>
                <div style={{ border: `1px solid ${S.border}`, borderRadius: 6,
                              overflow: "hidden" }}>
                  {aktiv.artefakte.map(a => (
                    <div key={a.id} style={{ padding: "8px 12px",
                        borderBottom: `1px solid ${S.border}`, display: "flex",
                        alignItems: "center", gap: 10, backgroundColor: S.bgCard }}>
                      <span style={{ fontSize: 10, fontFamily: "monospace",
                          color: S.textDim, width: 108, flexShrink: 0 }}>{a.art}</span>
                      <span style={{ fontSize: 12, color: S.textMain, flex: 1 }}>
                        {a.label}
                      </span>
                      {!a.erzeugt && (
                        <span style={{ fontSize: 10, color: S.textDim,
                            border: `1px solid ${S.border}`, borderRadius: 3,
                            padding: "1px 6px" }}>nur ergänzt</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {templateOffen && aktiv && (
        <TemplateModal vorhaben={aktiv} onClose={() => setTemplateOffen(false)}
          onErzeugen={alsTemplate} />
      )}

      {adoptionOffen && adoption && (
        <AdoptionModal eintraege={adoption.eintraege || []}
          onClose={() => setAdoptionOffen(false)} onUebernehmen={uebernehmen} />
      )}

      {rueckbauPlan && (
        <RueckbauModal plan={rueckbauPlan} laeuft={rueckbauLaeuft}
          onClose={() => setRueckbauPlan(null)}
          onAusfuehren={rueckbauAusfuehren} />
      )}
    </div>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────────────────────

/** Schritt 1: Beschreiben. Kein leeres Feld – die Beispiele sind der Einstieg. */
function Beschreiben({ value, onChange, onSubmit, laeuft, fortschritt, eingabeRef,
                       canEdit, projectId }) {
  const beispiele = [
    "Zeig mir jeden Montag die Kunden, die Ware bekommen haben, aber keine Rechnung",
    "Welche Kunden haben letztes Jahr gekauft und dieses Jahr nicht mehr?",
    "Warne mich, wenn ein Kunde mehr als 5.000 € offen hat",
  ];
  return (
    <div style={{ maxWidth: 720 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
        <Wand2 size={18} style={{ color: S.accent }} />
        <h2 style={{ margin: 0, fontSize: 17, fontWeight: 700, color: S.textBright }}>
          Was möchtest du sehen?
        </h2>
      </div>
      <p style={{ fontSize: 12.5, color: S.textDim, margin: "0 0 14px", lineHeight: 1.6 }}>
        Ein Satz genügt. Die Werkbank schlägt vor, was dafür gebaut werden muss –
        du prüfst es, siehst eine Vorschau mit echten Zahlen und entscheidest dann.
        Alles Gebaute lässt sich später mit einem Klick wieder zurückbauen.
      </p>

      <textarea ref={eingabeRef} value={value} onChange={e => onChange(e.target.value)}
        rows={3} placeholder="z. B. Zeig mir jeden Montag die Kunden ohne Rechnung"
        onKeyDown={e => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) onSubmit(); }}
        style={{ ...inp, resize: "vertical", lineHeight: 1.5, fontSize: 13 }} />

      <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 10 }}>
        <button onClick={onSubmit} disabled={laeuft || !value.trim() || !canEdit}
          style={knopf(!laeuft && !!value.trim() && canEdit)}>
          {laeuft ? <Loader2 size={13} className="animate-spin" /> : <Wand2 size={13} />}
          Bauzettel erstellen
        </button>
        {laeuft && <span style={{ fontSize: 12, color: S.textDim }}>{fortschritt}</span>}
      </div>

      <p style={{ fontSize: 11, fontWeight: 700, color: S.textDim, margin: "26px 0 8px",
                  textTransform: "uppercase", letterSpacing: "0.05em" }}>Beispiele</p>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {beispiele.map((b, i) => (
          <button key={i} onClick={() => onChange(b)}
            style={{ textAlign: "left", padding: "9px 12px", borderRadius: 6,
              border: `1px solid ${S.border}`, backgroundColor: S.bgCard,
              color: S.textMain, fontSize: 12, cursor: "pointer", lineHeight: 1.4 }}>
            {b}
          </button>
        ))}
      </div>
    </div>
  );
}


function Kopf({ v, mandanten, gebaut, onUmbenennen, onMandant }) {
  const [name, setName] = useState(v.name);
  useEffect(() => setName(v.name), [v.id, v.name]);
  const st = STATUS[v.status] || STATUS.entwurf;
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <input value={name} onChange={e => setName(e.target.value)}
          onBlur={() => name.trim() && name !== v.name && onUmbenennen(name.trim())}
          style={{ ...inp, fontSize: 15, fontWeight: 700, color: S.textBright,
                   background: "transparent", border: "1px solid transparent",
                   padding: "4px 6px", flex: 1 }} />
        <span style={{ fontSize: 11, color: st.farbe, border: `1px solid ${st.farbe}40`,
            borderRadius: 4, padding: "3px 8px", whiteSpace: "nowrap" }}>{st.label}</span>
      </div>
      <p style={{ margin: "4px 0 0 6px", fontSize: 12, color: S.textDim, lineHeight: 1.5 }}>
        „{v.beschreibung}“
      </p>
      {/* Der Betrieb ist Teil des Vorhabens, nicht der Sitzung: gerechnet und
          später auch nachts zugestellt wird gegen genau diese Warenwirtschaft.
          Nach dem Bauen festgezurrt – ein Wechsel würde die schon gebauten
          Objekte gegen einen anderen Betrieb laufen lassen. */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, margin: "8px 0 0 6px" }}>
        <Building2 size={13} style={{ color: S.textDim }} />
        <span style={{ fontSize: 11.5, color: S.textDim }}>Betrieb</span>
        {gebaut || (mandanten || []).length < 2 ? (
          <span style={{ fontSize: 12, color: S.textMain, fontWeight: 600 }}>
            {v.mandant || "—"}
            {gebaut && (mandanten || []).length > 1 && (
              <span style={{ marginLeft: 8, fontSize: 11, color: S.textDim,
                             fontWeight: 400 }}>
                (nach dem Bauen nicht mehr wechselbar)
              </span>
            )}
          </span>
        ) : (
          <select value={v.mandant_id || ""} onChange={e => onMandant(Number(e.target.value))}
            style={{ ...inp, width: "auto", minWidth: 140, fontSize: 12 }}>
            {(mandanten || []).map(m => (
              <option key={m.connection_id} value={m.connection_id}>{m.name}</option>
            ))}
          </select>
        )}
      </div>
    </div>
  );
}


/** Eine Zeile des Bauzettels: Häkchen, Klartext, aufklappbare Einstellungen. */
function Schritt({ s, i, offen, gebaut, werkzeuge, abfrageSchema, vorschau,
                   onToggle, onAktiv, onEingabe }) {
  const wz = (werkzeuge?.werkzeuge || []).find(w => w.key === s.werkzeug);
  const aus = !s.aktiv;
  return (
    <div style={{ border: `1px solid ${S.border}`, borderRadius: 6,
                  backgroundColor: S.bgCard, opacity: aus ? 0.5 : 1 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 12px" }}>
        <input type="checkbox" checked={!!s.aktiv} disabled={gebaut}
          onChange={e => onAktiv(e.target.checked)}
          style={{ accentColor: S.accent, cursor: gebaut ? "default" : "pointer" }} />
        <button onClick={onToggle} style={{ background: "none", border: "none",
            padding: 0, cursor: "pointer", color: S.textDim, display: "flex" }}>
          {offen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{ margin: 0, fontSize: 12.5, fontWeight: 600, color: S.textBright }}>
            {s.titel || wz?.label || s.werkzeug}
          </p>
          <p style={{ margin: "2px 0 0", fontSize: 11.5, color: S.textDim,
                      overflow: "hidden", textOverflow: "ellipsis",
                      whiteSpace: "nowrap" }}>
            {s.zusammenfassung || wz?.wofuer}
          </p>
        </div>
        {vorschau && <VorschauMarke v={vorschau} />}
      </div>

      {offen && (
        <div style={{ padding: "0 12px 12px 46px", display: "flex",
                      flexDirection: "column", gap: 10 }}>
          {s.warum && (
            <p style={{ margin: 0, fontSize: 11.5, color: S.textDim, lineHeight: 1.5,
                        fontStyle: "italic" }}>{s.warum}</p>
          )}
          <Einstellungen s={s} gebaut={gebaut} werkzeuge={werkzeuge}
            abfrageSchema={abfrageSchema} onEingabe={onEingabe} />
          {vorschau && <VorschauInhalt v={vorschau} />}
        </div>
      )}
    </div>
  );
}


function VorschauMarke({ v }) {
  if (v.fehler) return (
    <span style={{ fontSize: 11, color: "#e05656", display: "flex", alignItems: "center",
                   gap: 4, whiteSpace: "nowrap" }}>
      <AlertTriangle size={12} /> Fehler
    </span>
  );
  const anzahl = v.ergebnis?.anzahl;
  if (anzahl === undefined || anzahl === null) return null;
  const leer = anzahl === 0;
  return (
    <span style={{ fontSize: 11, whiteSpace: "nowrap",
        color: leer ? "#e8913a" : "#5cb85c", display: "flex", alignItems: "center",
        gap: 4 }}>
      {leer ? <AlertTriangle size={12} /> : <CheckCircle2 size={12} />}
      {anzahl} Zeile{anzahl === 1 ? "" : "n"}
    </span>
  );
}


/** Die Vorschau zeigt echte Zahlen – Struktur allein sagt nichts über Richtigkeit. */
function VorschauInhalt({ v }) {
  if (v.fehler) return (
    <div style={{ padding: "9px 12px", borderRadius: 5,
        background: "rgba(224,86,86,0.08)", border: "1px solid rgba(224,86,86,0.25)" }}>
      <p style={{ margin: 0, fontSize: 11.5, color: "#e05656" }}>{v.fehler}</p>
    </div>
  );
  const e = v.ergebnis;
  if (!e) return null;

  if (e.treffer) {
    return (
      <div style={{ fontSize: 11.5, color: S.textDim }}>
        <p style={{ margin: "0 0 6px" }}>{e.hinweis}</p>
        {e.treffer.map((t, i) => (
          <p key={i} style={{ margin: "0 0 3px", color: S.textMain }}>
            · {t.label} <span style={{ color: S.textDim }}>({t.cockpit} → {t.reiter})</span>
          </p>
        ))}
      </div>
    );
  }

  if (!e.zeilen) {
    return <p style={{ margin: 0, fontSize: 11.5, color: S.textDim }}>{e.hinweis}</p>;
  }

  const spalten = (e.spalten || []).filter(s => !s.schluessel).slice(0, 6);
  return (
    <div>
      {e.befund && (
        <div style={{ marginBottom: 8, padding: "9px 12px", borderRadius: 5,
            background: "rgba(232,145,58,0.09)", border: "1px solid rgba(232,145,58,0.3)" }}>
          <p style={{ margin: 0, fontSize: 11.5, color: "#e8913a" }}>{e.befund}</p>
        </div>
      )}
      <p style={{ margin: "0 0 6px", fontSize: 11, color: S.textDim }}>
        {e.anzahl} Zeile(n){e.gedeckelt ? " (gedeckelt)" : ""} · Betrieb {e.mandant}
        {e.zeitraum ? ` · ${e.zeitraum.von} bis ${e.zeitraum.bis}` : ""}
      </p>
      {e.zeilen.length > 0 && (
        <div style={{ overflowX: "auto", border: `1px solid ${S.border}`,
                      borderRadius: 5 }}>
          <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 11.5 }}>
            <thead>
              <tr>{spalten.map(c => (
                <th key={c.name} style={{ textAlign: "left", padding: "6px 10px",
                    color: S.textDim, fontWeight: 500, whiteSpace: "nowrap",
                    borderBottom: `1px solid ${S.border}` }}>{c.label || c.name}</th>
              ))}</tr>
            </thead>
            <tbody>
              {e.zeilen.slice(0, 5).map((z, i) => (
                <tr key={i}>{spalten.map(c => (
                  <td key={c.name} style={{ padding: "6px 10px", color: S.textMain,
                      borderBottom: `1px solid ${S.border}`, whiteSpace: "nowrap",
                      maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis" }}>
                    {String(z[c.name] ?? "")}
                  </td>
                ))}</tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}


/** Die Stellschrauben eines Schritts – bewusst wenige, alle mit fester Auswahl. */
function Einstellungen({ s, gebaut, werkzeuge, abfrageSchema, onEingabe }) {
  const e = s.eingabe || {};
  const zeit = werkzeuge?.zeitraeume || [];
  const takte = werkzeuge?.takte || [];
  const feld = (label, kind) => (
    <label style={{ display: "flex", flexDirection: "column", gap: 4, flex: 1,
                    minWidth: 150 }}>
      <span style={{ fontSize: 10.5, color: S.textDim, textTransform: "uppercase",
                     letterSpacing: "0.05em" }}>{label}</span>
      {kind}
    </label>
  );
  const reihe = { display: "flex", gap: 10, flexWrap: "wrap" };

  if (s.werkzeug === "abfrage") {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={reihe}>
          {feld("Name", <input value={e.name || ""} disabled={gebaut} style={inp}
            onChange={ev => onEingabe("name", ev.target.value)} />)}
          {feld("Zeitraum der Vorschau", (
            <select value={e.zeitraum_preset || "months_12"} disabled={gebaut} style={inp}
              onChange={ev => onEingabe("zeitraum_preset", ev.target.value)}>
              {zeit.map(z => <option key={z.key} value={z.key}>{z.label}</option>)}
            </select>
          ))}
        </div>
        <Definition d={e.definition} schema={abfrageSchema} gebaut={gebaut}
          onChange={d => onEingabe("definition", d)} />
      </div>
    );
  }

  if (s.werkzeug === "mapping_frei") {
    const befund = e.fehler || e.leer || e.warnung;
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={reihe}>
          {feld("Name", <input value={e.name || ""} disabled={gebaut} style={inp}
            onChange={ev => onEingabe("name", ev.target.value)} />)}
          {feld("Zeitraum der Vorschau", (
            <select value={e.zeitraum_preset || "months_12"} disabled={gebaut} style={inp}
              onChange={ev => onEingabe("zeitraum_preset", ev.target.value)}>
              {zeit.map(z => <option key={z.key} value={z.key}>{z.label}</option>)}
            </select>
          ))}
        </div>
        {befund && (
          <div style={{ padding: "9px 12px", borderRadius: 5,
              background: e.fehler ? "rgba(224,86,86,0.08)" : "rgba(232,145,58,0.09)",
              border: `1px solid ${e.fehler ? "rgba(224,86,86,0.25)" : "rgba(232,145,58,0.3)"}` }}>
            <p style={{ margin: 0, fontSize: 11.5,
                        color: e.fehler ? "#e05656" : "#e8913a" }}>
              {e.fehler ? "Die Datenbank lehnt das SQL ab: " : ""}{befund}
            </p>
          </div>
        )}
        {/* Das SQL steht sichtbar da: wer es lesen kann, prüft es; wer nicht,
            sieht wenigstens, dass nichts gezaubert wird. */}
        <div>
          <p style={{ margin: "0 0 5px", fontSize: 10.5, color: S.textDim,
              textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Erzeugtes SQL {(e.spalten || []).length > 0
              ? `· ${e.spalten.length} geprüfte Spalten` : ""}
          </p>
          <pre style={{ margin: 0, padding: "10px 12px", borderRadius: 5,
              backgroundColor: S.bgMain, border: `1px solid ${S.border}`,
              fontSize: 11, lineHeight: 1.5, color: S.textMain,
              overflowX: "auto", maxHeight: 220, whiteSpace: "pre" }}>
            {e.sql || "(noch kein SQL)"}
          </pre>
        </div>
      </div>
    );
  }

  if (s.werkzeug === "pipeline") {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={reihe}>
          {feld("Name", <input value={e.name || ""} disabled={gebaut} style={inp}
            onChange={ev => onEingabe("name", ev.target.value)} />)}
          {feld("Takt", (
            <select value={e.cron_expr || "0 6 * * 1"} disabled={gebaut} style={inp}
              onChange={ev => onEingabe("cron_expr", ev.target.value)}>
              {takte.map(t => <option key={t.key} value={t.key}>{t.label}</option>)}
            </select>
          ))}
        </div>
        {feld("Meldung nach dem Lauf an (leer = keine Mail)", (
          <input value={e.email_to || ""} disabled={gebaut} style={inp}
            placeholder="name@firma.de"
            onChange={ev => onEingabe("email_to", ev.target.value)} />
        ))}
      </div>
    );
  }

  if (s.werkzeug === "app") {
    const felder = e.felder || [];
    const feldAendern = (i, feld, wert) => onEingabe("felder",
      felder.map((f, idx) => idx === i ? { ...f, [feld]: wert } : f));
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={reihe}>
          {feld("Name", <input value={e.name || ""} disabled={gebaut} style={inp}
            onChange={ev => onEingabe("name", ev.target.value)} />)}
          {feld("Beschriftung des Knopfes", (
            <input value={e.knopf || "Anzeigen"} disabled={gebaut} style={inp}
              onChange={ev => onEingabe("knopf", ev.target.value)} />
          ))}
        </div>

        <div>
          <p style={{ margin: "0 0 5px", fontSize: 10.5, color: S.textDim,
              textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Eingabefelder der Maske
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            {felder.map((f, i) => (
              <div key={i} style={{ display: "flex", gap: 8, alignItems: "center",
                  padding: "6px 9px", borderRadius: 4, backgroundColor: S.bgEl,
                  border: `1px solid ${S.border}`, flexWrap: "wrap" }}>
                <input value={f.label || ""} disabled={gebaut} placeholder="Beschriftung"
                  style={{ ...inp, width: 150 }}
                  onChange={ev => feldAendern(i, "label", ev.target.value)} />
                <span style={{ fontFamily: "monospace", fontSize: 11,
                               color: S.textDim }}>:{f.name}</span>
                <span style={{ fontSize: 11, color: S.textDim }}>{f.typ}</span>
                <input value={f.beispiel ?? ""} disabled={gebaut}
                  placeholder="Beispielwert für die Vorschau"
                  style={{ ...inp, width: 200, marginLeft: "auto" }}
                  onChange={ev => feldAendern(i, "beispiel", ev.target.value)} />
              </div>
            ))}
            {!felder.length && (
              <p style={{ margin: 0, fontSize: 11.5, color: S.textDim }}>
                Keine Eingabefelder – die Maske zeigt dann immer dasselbe.
              </p>
            )}
          </div>
          <p style={{ margin: "6px 0 0", fontSize: 11, color: S.textDim,
                      lineHeight: 1.5 }}>
            Der Beispielwert wird nur für die Vorschau benutzt. Er muss in den
            echten Daten vorkommen, sonst kommt nichts zurück – das ist dann kein
            Fehler der Maske.
          </p>
        </div>

        <div>
          <p style={{ margin: "0 0 5px", fontSize: 10.5, color: S.textDim,
              textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Erzeugtes SQL {(e.spalten || []).length > 0
              ? `· ${e.spalten.length} geprüfte Spalten` : ""}
          </p>
          <pre style={{ margin: 0, padding: "10px 12px", borderRadius: 5,
              backgroundColor: S.bgMain, border: `1px solid ${S.border}`,
              fontSize: 11, lineHeight: 1.5, color: S.textMain,
              overflowX: "auto", maxHeight: 200, whiteSpace: "pre" }}>
            {e.sql || "(noch kein SQL)"}
          </pre>
        </div>
      </div>
    );
  }

  if (s.werkzeug === "report") {
    return (
      <div style={reihe}>
        {feld("Name", <input value={e.name || ""} disabled={gebaut} style={inp}
          onChange={ev => onEingabe("name", ev.target.value)} />)}
        {feld("Zeitraum-Vorgabe", (
          <select value={e.zeitraum_preset || "months_12"} disabled={gebaut} style={inp}
            onChange={ev => onEingabe("zeitraum_preset", ev.target.value)}>
            {zeit.map(z => <option key={z.key} value={z.key}>{z.label}</option>)}
          </select>
        ))}
      </div>
    );
  }

  if (s.werkzeug === "zustellplan") {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={reihe}>
          {feld("Takt", (
            <select value={e.cron_expr || "0 6 * * 1"} disabled={gebaut} style={inp}
              onChange={ev => onEingabe("cron_expr", ev.target.value)}>
              {takte.map(t => <option key={t.key} value={t.key}>{t.label}</option>)}
            </select>
          ))}
          {feld("Zeitraum je Lauf", (
            <select value={e.zeitraum_preset || "last_month"} disabled={gebaut} style={inp}
              onChange={ev => onEingabe("zeitraum_preset", ev.target.value)}>
              {zeit.map(z => <option key={z.key} value={z.key}>{z.label}</option>)}
            </select>
          ))}
        </div>
        {feld("Empfänger (kommagetrennt)", (
          <input value={e.email_to || ""} disabled={gebaut} style={inp}
            placeholder="name@firma.de"
            onChange={ev => onEingabe("email_to", ev.target.value)} />
        ))}
      </div>
    );
  }

  if (s.werkzeug === "warnung") {
    return (
      <div style={reihe}>
        {feld("Melden ab … Treffern", (
          <input type="number" min={1} value={e.schwelle ?? 1} disabled={gebaut} style={inp}
            onChange={ev => onEingabe("schwelle", Number(ev.target.value))} />
        ))}
        {feld("Dringlichkeit", (
          <select value={e.severity || "warnung"} disabled={gebaut} style={inp}
            onChange={ev => onEingabe("severity", ev.target.value)}>
            {(werkzeuge?.dringlichkeiten || []).map(d =>
              <option key={d} value={d}>{d}</option>)}
          </select>
        ))}
      </div>
    );
  }

  if (s.werkzeug === "veroeffentlichen") {
    return feld("Beschreibung im Portal", (
      <input value={e.beschreibung || ""} disabled={gebaut} style={inp}
        onChange={ev => onEingabe("beschreibung", ev.target.value)} />
    ));
  }

  if (s.werkzeug === "nachsehen") {
    return feld("Suchbegriffe", (
      <input value={e.suchtext || ""} disabled={gebaut} style={inp}
        onChange={ev => onEingabe("suchtext", ev.target.value)} />
    ));
  }
  return null;
}


/**
 * Die Abfrage im Klartext. Bedingungen lassen sich entfernen – genau das
 * braucht man, wenn die KI eine zu viel gesetzt hat. Zum Hinzufügen führt der
 * Weg über den Abfrage-Generator; hier soll niemand einen Baum bauen müssen.
 */
function Definition({ d, schema, gebaut, onChange }) {
  if (!d) return null;
  const koernung = (schema?.koernungen || []).find(k => k.key === d.koernung);

  const eintrag = (key, art) => {
    const liste = art === "kennzahl" ? (koernung?.kennzahlen || []) : (koernung?.felder || []);
    return liste.find(x => x.key === key) || {};
  };
  const beschriften = (key, art) => eintrag(key, art).label || key;

  // Das Vergleichs-Label hängt am TYP des Feldes: „=" heißt bei Text „ist",
  // bei einer Zahl aber „=". Ohne den Typ gewinnt die erste Gruppe, und aus
  // „Anzahl Rechnungen = 0" wurde „Anzahl Rechnungen ist 0".
  const vergleichLabel = (key, art, feldKey) => {
    const typ = eintrag(feldKey, art).typ;
    const gruppen = schema?.vergleiche || {};
    const suchreihe = typ && gruppen[typ] ? [gruppen[typ]] : Object.values(gruppen);
    for (const gruppe of suchreihe) {
      const t = gruppe.find(v => v.key === key);
      if (t) return t.label;
    }
    return key;
  };

  const entfernen = (feldName, index) => {
    const baum = d[feldName] || {};
    const kinder = (baum.kinder || []).filter((_, i) => i !== index);
    onChange({ ...d, [feldName]: kinder.length ? { ...baum, kinder } : {} });
  };

  const block = (feldName, ueberschrift, art) => {
    const kinder = (d[feldName] || {}).kinder || [];
    if (!kinder.length) return null;
    const op = (d[feldName] || {}).op || "UND";
    return (
      <div>
        <p style={{ margin: "0 0 5px", fontSize: 10.5, color: S.textDim,
            textTransform: "uppercase", letterSpacing: "0.05em" }}>
          {ueberschrift} <span style={{ opacity: 0.7 }}>({op})</span>
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {kinder.map((b, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 8,
                padding: "5px 9px", borderRadius: 4, backgroundColor: S.bgEl,
                border: `1px solid ${S.border}` }}>
              <span style={{ fontSize: 11.5, color: S.textMain, flex: 1 }}>
                <b style={{ fontWeight: 600 }}>{beschriften(b.key, art)}</b>{" "}
                {vergleichLabel(b.vergleich, art, b.key)}{" "}
                {b.wert !== undefined && <b style={{ fontWeight: 600 }}>{String(b.wert)}</b>}
              </span>
              {!gebaut && (
                <button onClick={() => entfernen(feldName, i)} title="Bedingung entfernen"
                  style={{ background: "none", border: "none", cursor: "pointer",
                           color: S.textDim, display: "flex", padding: 0 }}>
                  <X size={12} />
                </button>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  };

  const kennzahlen = d.kennzahlen || [];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10,
        padding: "10px 12px", borderRadius: 5, backgroundColor: S.bgMain,
        border: `1px solid ${S.border}` }}>
      <p style={{ margin: 0, fontSize: 11.5, color: S.textDim }}>
        Eine Zeile im Ergebnis ist: <b style={{ color: S.textMain }}>
          {koernung?.label || d.koernung}</b>
        {koernung?.beschreibung && (
          <span style={{ display: "block", marginTop: 3, opacity: 0.85 }}>
            {koernung.beschreibung}</span>
        )}
      </p>
      {block("zeilenfilter", "Zeilenfilter", "feld")}
      {block("kennzahlfilter", "Kennzahlfilter (nach dem Zählen)", "kennzahl")}
      {kennzahlen.length > 0 && (
        <div>
          <p style={{ margin: "0 0 5px", fontSize: 10.5, color: S.textDim,
              textTransform: "uppercase", letterSpacing: "0.05em" }}>Kennzahlen</p>
          <p style={{ margin: 0, fontSize: 11.5, color: S.textMain }}>
            {kennzahlen.map(k => beschriften(k, "kennzahl")).join(" · ")}
          </p>
        </div>
      )}
    </div>
  );
}


/** Vorhaben als installierbares Template ausgeben. */
function TemplateModal({ vorhaben, onClose, onErzeugen }) {
  const [name, setName] = useState(vorhaben.name);
  const [beschreibung, setBeschreibung] = useState(vorhaben.beschreibung || "");

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 300,
        backgroundColor: "rgba(0,0,0,0.75)", display: "flex", alignItems: "center",
        justifyContent: "center", padding: 20 }}>
      <div onClick={ev => ev.stopPropagation()} style={{ backgroundColor: S.bgCard,
          border: `1px solid ${S.border}`, borderRadius: 10, width: "100%",
          maxWidth: 520 }}>
        <div style={{ padding: "16px 20px", borderBottom: `1px solid ${S.border}` }}>
          <p style={{ margin: 0, fontSize: 15, fontWeight: 700, color: S.textBright }}>
            Als Template ausgeben
          </p>
          <p style={{ margin: "4px 0 0", fontSize: 12, color: S.textDim,
                      lineHeight: 1.55 }}>
            Bündelt Mappings, Formulare und Pipelines dieses Vorhabens zu einer
            installierbaren Datei. Die Datenbankverbindung wird als Platzhalter
            abgelegt – Zugangsdaten wandern nie mit.
          </p>
        </div>
        <div style={{ padding: "16px 20px", display: "flex", flexDirection: "column",
                      gap: 12 }}>
          <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span style={{ fontSize: 10.5, color: S.textDim, textTransform: "uppercase",
                           letterSpacing: "0.05em" }}>Name im Katalog</span>
            <input value={name} onChange={e => setName(e.target.value)} style={inp} />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span style={{ fontSize: 10.5, color: S.textDim, textTransform: "uppercase",
                           letterSpacing: "0.05em" }}>Beschreibung</span>
            <textarea value={beschreibung} rows={3}
              onChange={e => setBeschreibung(e.target.value)}
              style={{ ...inp, resize: "vertical" }} />
          </label>
        </div>
        <div style={{ padding: "14px 20px", borderTop: `1px solid ${S.border}`,
            display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button onClick={onClose} style={knopfLeer}>Abbrechen</button>
          <button disabled={!name.trim()} style={knopf(!!name.trim())}
            onClick={() => onErzeugen({ name: name.trim(), beschreibung })}>
            <Package size={13} /> Template erzeugen
          </button>
        </div>
      </div>
    </div>
  );
}


/**
 * Gegen welche Datenbank gebaut wird – immer sichtbar.
 *
 * Drei Fälle: Gibt es als Mandant markierte Verbindungen, ist der gewohnte
 * Umschalter richtig. Gibt es mehrere unmarkierte, muss der Anwender hier
 * wählen. Gibt es genau eine, steht sie einfach da – eine Wahl wäre Schikane.
 */
function BetriebAnzeige({ betrieb, wahl, onWahl, projectId }) {
  const hatMandanten = (betrieb?.auswahl || []).some(a => a.ist_mandant);
  if (hatMandanten) return <MandantWaehler projectId={projectId} />;

  if (betrieb?.quelle === "mehrdeutig") {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <Building2 size={13} style={{ color: S.textDim }} />
        <select value={wahl ?? ""} onChange={e => onWahl(Number(e.target.value) || null)}
          style={{ ...inp, width: "auto", minWidth: 170 }}>
          <option value="">— Datenbank wählen —</option>
          {(betrieb.auswahl || []).map(a => (
            <option key={a.connection_id} value={a.connection_id}>{a.name}</option>
          ))}
        </select>
      </div>
    );
  }

  if (betrieb?.connection_id) {
    return (
      <span style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 12,
          color: S.textMain, border: `1px solid ${S.border}`, borderRadius: 5,
          padding: "5px 10px" }}>
        <Building2 size={13} style={{ color: S.textDim }} />
        {betrieb.name}
      </span>
    );
  }

  return (
    <span style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 12,
        color: "#e8913a" }}>
      <AlertTriangle size={13} /> keine Datenbank
    </span>
  );
}


/**
 * Bestand übernehmen. Die Häkchen starten bewusst LEER – hier wird fremder
 * Bestand angefasst, und was übernommen wird, entscheidet der Anwender aktiv.
 */
function AdoptionModal({ eintraege, onClose, onUebernehmen }) {
  const [gewaehlt, setGewaehlt] = useState([]);
  const schluessel = (e) => `${e.art}:${e.id}`;
  const an = (e) => gewaehlt.includes(schluessel(e));
  const um = (e) => setGewaehlt(g => an(e)
    ? g.filter(x => x !== schluessel(e)) : [...g, schluessel(e)]);

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 300,
        backgroundColor: "rgba(0,0,0,0.75)", display: "flex", alignItems: "center",
        justifyContent: "center", padding: 20 }}>
      <div onClick={ev => ev.stopPropagation()} style={{ backgroundColor: S.bgCard,
          border: `1px solid ${S.border}`, borderRadius: 10, width: "100%",
          maxWidth: 620, maxHeight: "82vh", display: "flex", flexDirection: "column" }}>
        <div style={{ padding: "16px 20px", borderBottom: `1px solid ${S.border}` }}>
          <p style={{ margin: 0, fontSize: 15, fontWeight: 700, color: S.textBright }}>
            Bestand übernehmen
          </p>
          <p style={{ margin: "4px 0 0", fontSize: 12, color: S.textDim,
                      lineHeight: 1.55 }}>
            Diese Auswertungen und Reports gehören zu keinem Vorhaben. Übernommen
            bekommen sie eine Herkunft – und damit Rückbau samt Prüfung, ob
            inzwischen jemand anders daran hängt. An den Objekten selbst ändert
            sich nichts.
          </p>
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: "12px 20px",
            display: "flex", flexDirection: "column", gap: 5 }}>
          {eintraege.map(e => (
            <label key={schluessel(e)} style={{ display: "flex", gap: 10,
                alignItems: "flex-start", padding: "9px 11px", borderRadius: 5,
                backgroundColor: S.bgEl, border: `1px solid ${an(e) ? S.accent : S.border}`,
                cursor: "pointer" }}>
              <input type="checkbox" checked={an(e)} onChange={() => um(e)}
                style={{ accentColor: S.accent, marginTop: 2 }} />
              <span style={{ flex: 1, minWidth: 0 }}>
                <span style={{ display: "block", fontSize: 12.5, fontWeight: 600,
                               color: S.textBright }}>{e.name}</span>
                <span style={{ display: "block", fontSize: 11, color: S.textDim,
                               marginTop: 2 }}>
                  {e.art === "adhoc_query" ? "Eigene Auswertung" : "Report"}
                  {(e.teile || []).length ? ` · ${e.teile.join(" · ")}` : ""}
                  {e.mandant_id ? "" : " · Betrieb unbekannt, Projekt-Standard wird gesetzt"}
                </span>
              </span>
            </label>
          ))}
        </div>

        <div style={{ padding: "14px 20px", borderTop: `1px solid ${S.border}`,
            display: "flex", gap: 8, justifyContent: "flex-end", alignItems: "center" }}>
          <span style={{ flex: 1, fontSize: 11.5, color: S.textDim }}>
            {gewaehlt.length} von {eintraege.length} gewählt
          </span>
          <button onClick={onClose} style={knopfLeer}>Abbrechen</button>
          <button disabled={!gewaehlt.length} style={knopf(!!gewaehlt.length)}
            onClick={() => onUebernehmen(gewaehlt.map(k => {
              const [art, id] = k.split(":");
              return { art, id: Number(id) };
            }))}>
            <Inbox size={13} /> Übernehmen
          </button>
        </div>
      </div>
    </div>
  );
}


/**
 * Die Rückbau-Vorschau ist Pflicht, nicht Zierde: Sie ist die einzige Stelle,
 * an der jemand sieht, dass an dieser Auswertung inzwischen eine Warnung oder
 * ein fremder Report hängt.
 */
function RueckbauModal({ plan, laeuft, onClose, onAusfuehren }) {
  const [trotzdem, setTrotzdem] = useState(false);
  const hatBlockiert = (plan.blockiert || []).length > 0;

  const liste = (eintraege, farbe, titel, hinweis) => eintraege.length > 0 && (
    <div style={{ marginBottom: 14 }}>
      <p style={{ margin: "0 0 6px", fontSize: 11, fontWeight: 700, color: farbe,
          textTransform: "uppercase", letterSpacing: "0.05em" }}>{titel}</p>
      {hinweis && <p style={{ margin: "0 0 6px", fontSize: 11.5, color: S.textDim,
          lineHeight: 1.5 }}>{hinweis}</p>}
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {eintraege.map(e => (
          <div key={e.artefakt_id} style={{ padding: "7px 10px", borderRadius: 4,
              backgroundColor: S.bgEl, border: `1px solid ${S.border}` }}>
            <p style={{ margin: 0, fontSize: 12, color: S.textMain }}>{e.label || e.art}</p>
            {(e.verwender || []).map((v, i) => (
              <p key={i} style={{ margin: "3px 0 0", fontSize: 11, color: "#e8913a" }}>
                wird benutzt von: {v.art} „{v.name}“
              </p>
            ))}
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 300,
        backgroundColor: "rgba(0,0,0,0.75)", display: "flex", alignItems: "center",
        justifyContent: "center", padding: 20 }}>
      <div onClick={ev => ev.stopPropagation()} style={{ backgroundColor: S.bgCard,
          border: `1px solid ${S.border}`, borderRadius: 10, width: "100%",
          maxWidth: 560, maxHeight: "82vh", display: "flex", flexDirection: "column" }}>
        <div style={{ padding: "16px 20px", borderBottom: `1px solid ${S.border}` }}>
          <p style={{ margin: 0, fontSize: 15, fontWeight: 700, color: S.textBright }}>
            Vorhaben zurückbauen
          </p>
          <p style={{ margin: "3px 0 0", fontSize: 12, color: S.textDim }}>
            {plan.zusammenfassung}
          </p>
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px" }}>
          {liste(plan.loeschen, "#e05656", "Wird gelöscht")}
          {liste(plan.bereinigen, S.textDim, "Bleibt stehen",
                 "Vorgefunden, nicht von diesem Vorhaben angelegt – es wird nur "
                 + "unsere Ergänzung zurückgenommen.")}
          {liste(plan.blockiert, "#e8913a", "Wird benutzt",
                 "Daran hängt noch etwas. Wird das gelöscht, meldet die andere "
                 + "Stelle keinen Fehler – sie zeigt einfach nichts mehr an.")}

          {hatBlockiert && (
            <label style={{ display: "flex", gap: 8, alignItems: "flex-start",
                marginTop: 8, cursor: "pointer" }}>
              <input type="checkbox" checked={trotzdem}
                onChange={ev => setTrotzdem(ev.target.checked)}
                style={{ accentColor: "#e05656", marginTop: 2 }} />
              <span style={{ fontSize: 12, color: S.textMain, lineHeight: 1.5 }}>
                Auch das Benutzte löschen – mir ist klar, dass die oben genannten
                Stellen danach leer bleiben.
              </span>
            </label>
          )}
        </div>

        <div style={{ padding: "14px 20px", borderTop: `1px solid ${S.border}`,
            display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button onClick={onClose} style={knopfLeer}>Abbrechen</button>
          <button onClick={() => onAusfuehren(!trotzdem)} disabled={laeuft}
            style={{ ...knopf(true), backgroundColor: "#e05656", color: "#fff" }}>
            {laeuft ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
            {trotzdem ? "Alles löschen" : "Zurückbauen"}
          </button>
        </div>
      </div>
    </div>
  );
}
