import { useState, useEffect, useMemo } from "react";
import { X, Play, Code2, AlertTriangle, Loader2, Save, CheckCircle2, Trash2 } from "lucide-react";
import api from "../../api/client";
import { S } from "../dashboard/constants";
import BedingungsBlock from "./BedingungsBlock";
import Vergleichsgruppe from "./Vergleichsgruppe";

/**
 * Abfrage-Generator: Körnung → Zeilenfilter → Kennzahlen → Kennzahlfilter.
 *
 * Die Trennung von Zeilen- und Kennzahlfilter ist der Kern. „Kunde = X“ filtert
 * eine Zeile, „Anzahl Rechnungen = 0“ prüft eine Zahl, die es erst nach dem
 * Verdichten gibt — in einem Block ließe sich das nicht ausdrücken.
 */

const ZEITRAEUME = [
  { id: 12, label: "Letzte 12 Monate" },
  { id: 6,  label: "Letzte 6 Monate" },
  { id: 3,  label: "Letzte 3 Monate" },
  { id: 24, label: "Letzte 24 Monate" },
];

const leer = { op: "UND", kinder: [] };

const knopf = (primary) => ({
  padding: "8px 15px", borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: "pointer",
  backgroundColor: primary ? "rgba(252,228,153,0.15)" : "transparent",
  border: `1px solid ${primary ? "rgba(252,228,153,0.4)" : S.border}`,
  color: primary ? "var(--accent)" : S.textMain,
});

const abschnitt = {
  border: `1px solid ${S.border}`, borderRadius: 8, padding: "14px 16px",
  backgroundColor: S.bgCard, display: "flex", flexDirection: "column", gap: 10,
};
const titel = { fontSize: 12, fontWeight: 600, color: S.textBright, margin: 0 };
const unter = { fontSize: 10.5, color: S.textDim, margin: 0, lineHeight: 1.45 };

export default function QueryBuilder({ projectId, onClose }) {
  const [schema, setSchema] = useState(null);
  const [koernung, setKoernung] = useState("kunde");
  const [zeilenfilter, setZeilenfilter] = useState(leer);
  const [kennzahlen, setKennzahlen] = useState([]);
  const [kennzahlfilter, setKennzahlfilter] = useState(leer);
  const [gruppierung, setGruppierung] = useState("");
  const [vglGruppe, setVglGruppe] = useState([]);
  const [monate, setMonate] = useState(12);
  const [ergebnis, setErgebnis] = useState(null);
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState("");
  const [sqlOffen, setSqlOffen] = useState(false);
  const [name, setName] = useState("");
  const [speichert, setSpeichert] = useState(false);
  const [gespeichert, setGespeichert] = useState(null);
  const [bestand, setBestand] = useState([]);      // gespeicherte Auswertungen
  const [offeneId, setOffeneId] = useState("");    // "" = neue Abfrage

  useEffect(() => {
    api.get("/api/query/schema")
      .then(({ data }) => setSchema(data))
      .catch((e) => setFehler(e.response?.data?.detail || e.message));
    api.get("/api/query/list", { params: projectId ? { project_id: projectId } : {} })
      .then(({ data }) => setBestand(data || []))
      .catch(() => {});
  }, [projectId]);

  const k = useMemo(
    () => schema?.koernungen.find((x) => x.key === koernung), [schema, koernung]);

  // Der Kennzahlfilter darf nur anbieten, was auch berechnet wird – sonst
  // filtert der Anwender auf eine Spalte, die er nie zu sehen bekommt.
  const kennzahlFelder = useMemo(
    () => (k?.kennzahlen || []).filter((m) => kennzahlen.includes(m.key)),
    [k, kennzahlen]);

  // „kunde" rechnet immer verdichtet; die übrigen brauchen dafür eine Gruppierung.
  const hatGruppen = (k?.gruppierungen || []).length > 0;
  const verdichtet = !hatGruppen || !!gruppierung;

  const definition = () => ({
    koernung, zeilenfilter, gruppierung: gruppierung || undefined,
    kennzahlen: verdichtet ? kennzahlen : [],
    kennzahlfilter: verdichtet ? kennzahlfilter : leer,
    vergleichsgruppe: vglGruppe.length ? { kunden: vglGruppe } : undefined,
    sortierung: kennzahlen[0] ? { key: kennzahlen[0], richtung: "desc" } : undefined,
  });

  const zuruecksetzen = () => {
    setOffeneId(""); setName(""); setKoernung("kunde"); setGruppierung("");
    setZeilenfilter(leer); setKennzahlen([]); setKennzahlfilter(leer);
    setVglGruppe([]); setErgebnis(null); setGespeichert(null); setFehler("");
  };

  const oeffnen = async (id) => {
    if (!id) return zuruecksetzen();
    setFehler(""); setErgebnis(null); setGespeichert(null);
    try {
      const { data } = await api.get(`/api/query/${id}`);
      const d = data.definition || {};
      setOffeneId(id);
      setName(data.name || "");
      setKoernung(d.koernung || "kunde");
      setGruppierung(d.gruppierung || "");
      setZeilenfilter(d.zeilenfilter || leer);
      setKennzahlen(d.kennzahlen || []);
      setKennzahlfilter(d.kennzahlfilter || leer);
      setVglGruppe((d.vergleichsgruppe || {}).kunden || []);
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
    }
  };

  const loeschen = async () => {
    if (!offeneId) return;
    const treffer = bestand.find((b) => String(b.id) === String(offeneId));
    if (!window.confirm(`Auswertung „${treffer?.name || ""}“ mitsamt ihren `
      + `Bausteinen löschen? Reports, die sie verwenden, verlieren diese Kacheln.`)) return;
    setSpeichert(true);
    try {
      await api.delete(`/api/query/${offeneId}`);
      setBestand((b) => b.filter((x) => String(x.id) !== String(offeneId)));
      zuruecksetzen();
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
    } finally { setSpeichert(false); }
  };

  const speichern = async () => {
    setSpeichert(true); setFehler(""); setGespeichert(null);
    try {
      const rumpf = { name: name.trim(), definition: definition(),
                      project_id: projectId || null };
      const { data } = offeneId
        ? await api.put(`/api/query/${offeneId}`, rumpf)
        : await api.post("/api/query/save", rumpf);
      setGespeichert(data);
      setOffeneId(data.id);
      setBestand((b) => b.some((x) => x.id === data.id)
        ? b.map((x) => (x.id === data.id ? { ...x, name: data.name } : x))
        : [{ id: data.id, name: data.name }, ...b]);
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
    } finally { setSpeichert(false); }
  };

  const ausfuehren = async () => {
    setLaeuft(true); setFehler(""); setErgebnis(null);
    const bis = new Date();
    const von = new Date(); von.setMonth(von.getMonth() - monate);
    const iso = (d) => d.toISOString().slice(0, 10);
    try {
      const { data } = await api.post("/api/query/preview", {
        definition: definition(),
        project_id: projectId || null,
        von: iso(von), bis: iso(bis),
      });
      setErgebnis(data);
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
    } finally { setLaeuft(false); }
  };

  const zeigeWert = (v, sp) => {
    if (v === null || v === undefined) return "–";
    if (sp?.typ === "geld") return Number(v).toLocaleString("de-DE",
      { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
    if (sp?.typ === "zahl") return Number(v).toLocaleString("de-DE");
    if (sp?.typ === "datum") return String(v).slice(0, 10).split("-").reverse().join(".");
    return String(v);
  };

  return (
    <div style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.6)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, padding: 24 }}>
      <div style={{ backgroundColor: S.bgMain, border: `1px solid ${S.border}`, borderRadius: 10,
        width: "100%", maxWidth: 1020, maxHeight: "92vh", display: "flex", flexDirection: "column" }}>

        <div style={{ padding: "16px 20px", borderBottom: `1px solid ${S.border}`,
          display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <h2 style={{ fontSize: 15, fontWeight: 700, color: S.textBright, margin: 0 }}>
              Eigene Abfrage
            </h2>
            <p style={{ fontSize: 11, color: S.textDim, marginTop: 3 }}>
              Bedingungen zusammenklicken – die Joins sitzen fest im Hintergrund
            </p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {bestand.length > 0 && (
              <select value={offeneId} onChange={(e) => oeffnen(e.target.value)}
                title="Gespeicherte Auswertung öffnen"
                style={{ padding: "6px 10px", borderRadius: 6, fontSize: 11.5,
                  backgroundColor: S.bgCard, border: `1px solid ${S.border}`,
                  color: S.textMain, maxWidth: 260 }}>
                <option value="">Neue Abfrage …</option>
                {bestand.map((b) => (
                  <option key={b.id} value={b.id}>{b.name}</option>
                ))}
              </select>
            )}
            <button onClick={onClose} style={{ background: "none", border: "none",
              color: S.textDim, cursor: "pointer", padding: 4 }}><X size={18} /></button>
          </div>
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: 20,
          display: "flex", flexDirection: "column", gap: 14 }}>

          {!schema ? (
            <div style={{ padding: 40, textAlign: "center", color: S.textDim, fontSize: 12 }}>Lädt…</div>
          ) : (
            <>
              {/* 1 — Körnung */}
              <div style={abschnitt}>
                <p style={titel}>1 · Was ist eine Ergebniszeile?</p>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {schema.koernungen.map((x) => (
                    <button key={x.key} onClick={() => {
                        setKoernung(x.key); setZeilenfilter(leer); setGruppierung("");
                        setVglGruppe([]);
                        setKennzahlen([]); setKennzahlfilter(leer); setErgebnis(null);
                      }}
                      style={{ padding: "6px 12px", borderRadius: 5, fontSize: 11.5,
                        cursor: "pointer",
                        backgroundColor: koernung === x.key ? "rgba(252,228,153,0.15)" : "transparent",
                        border: `1px solid ${koernung === x.key ? "rgba(252,228,153,0.4)" : S.border}`,
                        color: koernung === x.key ? "var(--accent)" : S.textMain }}>
                      {x.label}
                    </button>
                  ))}
                </div>
                {k?.beschreibung && <p style={unter}>{k.beschreibung}</p>}
              </div>

              {/* 2 — Zeilenfilter */}
              <div style={abschnitt}>
                <p style={titel}>2 · Welche {k?.plural ?? "Zeilen"} kommen in Frage?</p>
                <p style={unter}>
                  Filter auf die Zeile selbst. Leer lassen heißt: alle.
                </p>
                <BedingungsBlock knoten={zeilenfilter} felder={k?.felder || []}
                  vergleiche={schema.vergleiche} ohneWert={schema.ohne_wert}
                  zweiWerte={schema.zwei_werte} liste={schema.liste}
                  onChange={setZeilenfilter} />
              </div>

              {/* Vergleichsgruppe – nur wo die Körnung sie kennt */}
              {k?.vergleichsgruppe && (
                <div style={abschnitt}>
                  <p style={titel}>
                    {k.vergleichsgruppe.label} <span style={{ fontWeight: 400,
                      color: S.textDim }}>· optional</span>
                  </p>
                  <Vergleichsgruppe projectId={projectId} gewaehlt={vglGruppe}
                    onChange={setVglGruppe} hinweis={k.vergleichsgruppe.beschreibung} />
                </div>
              )}

              {/* 3 — Gruppierung (nur Zeilen-Körnungen) */}
              {hatGruppen && (
                <div style={abschnitt}>
                  <p style={titel}>3 · Verdichten?</p>
                  <p style={unter}>
                    Ohne Verdichtung ist das Ergebnis eine Liste. Mit Verdichtung
                    entstehen Kennzahlen, auf die sich dann Bedingungen stellen lassen.
                  </p>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <button onClick={() => { setGruppierung(""); setKennzahlfilter(leer); }}
                      style={{ padding: "6px 12px", borderRadius: 5, fontSize: 11.5,
                        cursor: "pointer",
                        backgroundColor: !gruppierung ? "rgba(252,228,153,0.15)" : "transparent",
                        border: `1px solid ${!gruppierung ? "rgba(252,228,153,0.4)" : S.border}`,
                        color: !gruppierung ? "var(--accent)" : S.textMain }}>
                      Einzelne Zeilen
                    </button>
                    {(k?.gruppierungen || []).map((gr) => (
                      <button key={gr.key} onClick={() => setGruppierung(gr.key)}
                        style={{ padding: "6px 12px", borderRadius: 5, fontSize: 11.5,
                          cursor: "pointer",
                          backgroundColor: gruppierung === gr.key ? "rgba(252,228,153,0.15)" : "transparent",
                          border: `1px solid ${gruppierung === gr.key ? "rgba(252,228,153,0.4)" : S.border}`,
                          color: gruppierung === gr.key ? "var(--accent)" : S.textMain }}>
                        {gr.label}{gr.verlauf ? " ↗" : ""}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* 4 — Kennzahlen */}
              <div style={{ ...abschnitt, opacity: verdichtet ? 1 : 0.5 }}>
                <p style={titel}>{hatGruppen ? "4" : "3"} · Welche Zahlen sollen dazu berechnet werden?</p>
                {!verdichtet && (
                  <p style={unter}>
                    Eine Liste einzelner Zeilen trägt keine verdichteten Zahlen –
                    oben eine Verdichtung wählen.
                  </p>
                )}
                <p style={unter}>
                  Alle Kennzahlen zählen nur im gewählten Zeitfenster. Ohne Fenster
                  wäre „Rechnungen = 0“ wertlos – über die ganze Historie trifft es
                  fast niemanden.
                </p>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap",
                  pointerEvents: verdichtet ? "auto" : "none" }}>
                  {(k?.kennzahlen || []).map((m) => {
                    const an = kennzahlen.includes(m.key);
                    // Ohne Vergleichsgruppe hätten diese Kennzahlen keine Bezugsmenge.
                    const gesperrt = m.braucht_gruppe && !vglGruppe.length;
                    return (
                      <button key={m.key} disabled={gesperrt}
                        title={gesperrt ? "Erst oben eine Vergleichsgruppe wählen"
                                        : (m.hinweis || "")}
                        onClick={() => setKennzahlen((alt) => an
                          ? alt.filter((x) => x !== m.key) : [...alt, m.key])}
                        style={{ padding: "5px 11px", borderRadius: 5, fontSize: 11.5,
                          cursor: gesperrt ? "not-allowed" : "pointer",
                          opacity: gesperrt ? 0.4 : 1,
                          backgroundColor: an ? "rgba(252,228,153,0.15)" : "transparent",
                          border: `1px solid ${an ? "rgba(252,228,153,0.4)" : S.border}`,
                          color: an ? "var(--accent)" : S.textMain }}>
                        {m.label}
                      </button>
                    );
                  })}
                </div>
                <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 2 }}>
                  <span style={{ fontSize: 10.5, color: S.textDim }}>Zeitfenster</span>
                  <select value={monate} onChange={(e) => setMonate(Number(e.target.value))}
                    style={{ padding: "5px 8px", borderRadius: 5, fontSize: 11.5,
                      backgroundColor: S.bgMain, border: `1px solid ${S.border}`, color: S.textMain }}>
                    {ZEITRAEUME.map((z) => <option key={z.id} value={z.id}>{z.label}</option>)}
                  </select>
                  <span style={{ fontSize: 10.5, color: S.textDim }}>
                    (im fertigen Report der Zeitraum des Reports)
                  </span>
                </div>
              </div>

              {/* 4 — Kennzahlfilter */}
              <div style={{ ...abschnitt, opacity: (verdichtet && kennzahlen.length) ? 1 : 0.5 }}>
                <p style={titel}>{hatGruppen ? "5" : "4"} · Bedingungen an diese Zahlen</p>
                <p style={unter}>
                  {!verdichtet
                    ? "Erst eine Verdichtung wählen."
                    : kennzahlen.length
                      ? "Hier wird nach dem Rechnen gefiltert – z. B. „Anzahl Lieferscheine ≥ 1 UND Anzahl Rechnungen = 0“."
                      : "Erst oben Kennzahlen wählen."}
                </p>
                {verdichtet && kennzahlen.length > 0 && (
                  <BedingungsBlock knoten={kennzahlfilter} felder={kennzahlFelder}
                    vergleiche={schema.vergleiche} ohneWert={schema.ohne_wert}
                    zweiWerte={schema.zwei_werte} liste={schema.liste}
                    onChange={setKennzahlfilter} />
                )}
              </div>

              {/* Ergebnis */}
              {fehler && (
                <div style={{ display: "flex", gap: 7, alignItems: "flex-start",
                  fontSize: 11.5, color: "#f87171" }}>
                  <AlertTriangle size={13} style={{ flexShrink: 0, marginTop: 1 }} />
                  <span>{fehler}</span>
                </div>
              )}

              {ergebnis && (
                <div style={abschnitt}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <p style={titel}>
                      {ergebnis.anzahl}{ergebnis.gedeckelt ? "+" : ""} Treffer
                      <span style={{ fontWeight: 400, color: S.textDim, marginLeft: 8 }}>
                        {ergebnis.mandant} · {ergebnis.zeitraum.von} bis {ergebnis.zeitraum.bis}
                      </span>
                    </p>
                    <button onClick={() => setSqlOffen((v) => !v)}
                      style={{ display: "flex", alignItems: "center", gap: 5, background: "none",
                        border: `1px solid ${S.border}`, borderRadius: 5, padding: "4px 9px",
                        color: S.textDim, cursor: "pointer", fontSize: 11 }}>
                      <Code2 size={11} /> {sqlOffen ? "SQL verbergen" : "SQL zeigen"}
                    </button>
                  </div>

                  {sqlOffen && (
                    <pre style={{ margin: 0, maxHeight: 240, overflow: "auto", fontSize: 10.5,
                      lineHeight: 1.5, padding: 10, borderRadius: 5, color: S.textMain,
                      backgroundColor: S.bgMain, border: `1px solid ${S.border}` }}>
                      {ergebnis.sql}
                    </pre>
                  )}

                  {ergebnis.gedeckelt && (
                    <p style={{ ...unter, color: "var(--accent)" }}>
                      Vorschau auf {ergebnis.anzahl} Zeilen begrenzt. Der gespeicherte
                      Report zeigt alle.
                    </p>
                  )}

                  <div style={{ overflowX: "auto", maxHeight: 320, overflowY: "auto",
                    border: `1px solid ${S.border}`, borderRadius: 5 }}>
                    <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 11.5 }}>
                      <thead>
                        <tr>
                          {ergebnis.spalten.filter((s) => !s.schluessel).map((s) => (
                            <th key={s.name} style={{ textAlign: "left", padding: "7px 10px",
                              borderBottom: `1px solid ${S.border}`, color: S.textDim,
                              fontWeight: 500, whiteSpace: "nowrap", position: "sticky", top: 0,
                              backgroundColor: S.bgCard }}>
                              {s.label || s.name}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {ergebnis.zeilen.map((z, i) => (
                          <tr key={i}>
                            {ergebnis.spalten.filter((s) => !s.schluessel).map((s) => (
                              <td key={s.name} style={{ padding: "6px 10px",
                                borderBottom: `1px solid ${S.border}`, whiteSpace: "nowrap",
                                textAlign: ["zahl", "geld"].includes(s.typ) ? "right" : "left",
                                fontVariantNumeric: "tabular-nums", color: S.textMain }}>
                                {zeigeWert(z[s.name], s)}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        <div style={{ padding: "14px 20px", borderTop: `1px solid ${S.border}`,
          display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <input value={name} onChange={(e) => setName(e.target.value)}
            placeholder="Name der Auswertung, z. B. Lieferung ohne Rechnung"
            style={{ flex: "1 1 260px", padding: "7px 10px", borderRadius: 6,
              backgroundColor: S.bgCard, border: `1px solid ${S.border}`,
              color: S.textMain, fontSize: 12 }} />
          {gespeichert && (
            <span style={{ display: "flex", alignItems: "center", gap: 5,
              fontSize: 11.5, color: "#4ade80" }}>
              <CheckCircle2 size={13} />
              {offeneId && gespeichert.id === offeneId ? "Übernommen" : "Gespeichert"}
              {" – steht im Report-Baukasten unter „"}{gespeichert.form_name}{"“."}
            </span>
          )}
          <button onClick={speichern}
            disabled={speichert || !name.trim() || !ergebnis}
            title={!ergebnis ? "Erst eine Vorschau rechnen" : ""}
            style={{ ...knopf(false), display: "flex", alignItems: "center", gap: 6,
              opacity: (speichert || !name.trim() || !ergebnis) ? 0.4 : 1,
              cursor: (speichert || !name.trim() || !ergebnis) ? "not-allowed" : "pointer" }}>
            <Save size={12} /> {speichert ? "Speichert…"
              : offeneId ? "Änderungen übernehmen" : "Als Baustein speichern"}
          </button>
          {offeneId && (
            <button onClick={loeschen} disabled={speichert} title="Auswertung löschen"
              style={{ ...knopf(false), padding: "8px 10px",
                cursor: speichert ? "not-allowed" : "pointer" }}>
              <Trash2 size={13} />
            </button>
          )}
          <button onClick={onClose} style={knopf(false)}>Schließen</button>
          <button onClick={ausfuehren} disabled={laeuft || !schema}
            style={{ ...knopf(true), display: "flex", alignItems: "center", gap: 6,
              opacity: laeuft ? 0.6 : 1 }}>
            {laeuft ? <Loader2 size={12} className="spin" /> : <Play size={12} />}
            {laeuft ? "Rechnet…" : "Vorschau"}
          </button>
        </div>
      </div>
    </div>
  );
}
