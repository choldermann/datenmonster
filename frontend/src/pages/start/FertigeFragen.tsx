/**
 * Fertige Fragen (Händler-Ansicht, Phase 3): links die Fragen nach Bereichen,
 * rechts das Ergebnis mit Excel-Download und „Speichern“.
 * Backend: /api/start/fragen…, Fragen in services/query_builder/rezepte.py.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Download, Loader2, Save } from "lucide-react";
import api, { fehlerText } from "../../api/client";
import { S, knopf, karte } from "./StartLayout";

function zelle(wert, typ) {
  if (wert === null || wert === undefined || wert === "") return "";
  if (typ === "geld") return Number(wert).toLocaleString("de-DE", { style: "currency", currency: "EUR" });
  if (typ === "zahl") {
    const n = Number(wert);
    return Number.isFinite(n) ? n.toLocaleString("de-DE", { maximumFractionDigits: 2 }) : String(wert);
  }
  if (typ === "datum") {
    const d = new Date(String(wert).replace(" ", "T"));
    return Number.isNaN(d.getTime()) ? String(wert) : d.toLocaleDateString("de-DE");
  }
  return String(wert);
}

export default function FertigeFragen() {
  const navigate = useNavigate();
  const [fragen, setFragen] = useState(null);
  const [aktiv, setAktiv] = useState(null);
  const [ergebnis, setErgebnis] = useState(null);
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState(null);
  const [meldung, setMeldung] = useState(null);
  const [speichert, setSpeichert] = useState(false);

  useEffect(() => {
    api.get("/api/start/fragen").then(({ data }) => setFragen(data || [])).catch((e) => setFehler(fehlerText(e)));
  }, []);

  const oeffnen = async (f) => {
    setAktiv(f); setErgebnis(null); setFehler(null); setMeldung(null); setLaeuft(true);
    try {
      const { data } = await api.post(`/api/start/fragen/${f.key}/vorschau`, null, { timeout: 120000 });
      setErgebnis(data);
    } catch (e) {
      setFehler(fehlerText(e));
    } finally {
      setLaeuft(false);
    }
  };

  // Ausgabespalten: der interne Schlüssel (erste Spalte) bleibt weg.
  const spalten = (ergebnis?.spalten || []).filter((s) => !s.schluessel);

  const excel = async () => {
    const titel = aktiv?.titel || "Auswertung";
    const zeilen = (ergebnis?.zeilen || []).map((z) =>
      Object.fromEntries(spalten.map((s) => [s.label || s.name, zelle(z[s.name], s.typ === "geld" ? "zahl" : s.typ)])));
    try {
      const resp = await api.post("/api/forms/table-xlsx",
        { title: titel.slice(0, 31), columns: spalten.map((s) => s.label || s.name), rows: zeilen },
        { responseType: "blob" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(resp.data);
      a.download = `${titel.replace(/[^\wäöüÄÖÜß -]+/g, "").trim() || "auswertung"}.xlsx`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    } catch (e) {
      setFehler(`Excel-Export fehlgeschlagen: ${fehlerText(e)}`);
    }
  };

  const speichern = async () => {
    setSpeichert(true); setFehler(null); setMeldung(null);
    try {
      const { data } = await api.post(`/api/start/fragen/${aktiv.key}/speichern`, null, { timeout: 120000 });
      setMeldung({ text: `Gespeichert unter „${data.form_name}“. Dort lässt sie sich jederzeit öffnen und per Mail verschicken.`,
        formId: data.form_id });
    } catch (e) {
      setFehler(fehlerText(e));
    } finally {
      setSpeichert(false);
    }
  };

  const gruppen = [];
  for (const f of fragen || []) {
    let g = gruppen.find((x) => x.name === f.gruppe);
    if (!g) gruppen.push(g = { name: f.gruppe, fragen: [] });
    g.fragen.push(f);
  }

  return (
    <section aria-label="Fertige Fragen" style={{ display: "flex", flexWrap: "wrap", gap: 20, alignItems: "flex-start" }}>
      <div style={{ flex: "1 1 260px", maxWidth: 360, minWidth: 0, display: "flex", flexDirection: "column", gap: 14 }}>
        <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: S.textBright }}>Fertige Fragen</h2>
        {!fragen && !fehler && <span style={{ color: S.textDim }}>Lädt…</span>}
        {gruppen.map((g) => (
          <div key={g.name} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase", color: S.textDim }}>
              {g.name}
            </span>
            {g.fragen.map((f) => {
              const an = aktiv?.key === f.key;
              return (
                <button key={f.key} onClick={() => oeffnen(f)} aria-pressed={an}
                  style={{ textAlign: "left", padding: "10px 12px", minHeight: 42, borderRadius: 8, cursor: "pointer", fontSize: 14,
                    color: an ? S.accent : S.textMain, fontWeight: an ? 600 : 400,
                    border: `1px solid ${an ? "color-mix(in srgb, var(--accent) 45%, transparent)" : S.border}`,
                    backgroundColor: an ? "color-mix(in srgb, var(--accent) 10%, transparent)" : S.bgCard }}>
                  {f.titel}
                </button>
              );
            })}
          </div>
        ))}
      </div>

      <div style={{ flex: "999 1 480px", minWidth: 0, ...karte, padding: 20, display: "flex", flexDirection: "column", gap: 14 }}>
        {!aktiv && (
          <p style={{ margin: 0, color: S.textDim, lineHeight: 1.6 }}>
            Wählen Sie links eine Frage. Das Ergebnis erscheint hier, mit Ihren aktuellen Zahlen aus der Wawi.
          </p>
        )}
        {aktiv && (
          <>
            <div>
              <h3 style={{ margin: 0, fontSize: 19, color: S.textBright }}>{aktiv.titel}</h3>
              <p style={{ margin: "4px 0 0", color: S.textDim, fontSize: 14, lineHeight: 1.5 }}>
                {aktiv.text}{aktiv.zeitraum ? ` Zeitraum: ${aktiv.zeitraum.toLowerCase()}.` : ""}
              </p>
            </div>
            {laeuft && <span style={{ color: S.textDim, display: "flex", gap: 8, alignItems: "center" }}>
              <Loader2 size={15} style={{ animation: "spin 1s linear infinite" }} /> Rechne…</span>}
            {fehler && <p style={{ color: "var(--err)", margin: 0 }}>{fehler}</p>}
            {meldung && (
              <p role="status" style={{ color: "var(--ok)", margin: 0 }}>
                {meldung.text}{" "}
                <button onClick={() => navigate(`/start/cockpit/${meldung.formId}`)}
                  style={{ background: "none", border: "none", color: S.accent, cursor: "pointer", padding: 0, fontWeight: 600 }}>
                  Öffnen
                </button>
              </p>
            )}
            {ergebnis && (
              <>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                  <span style={{ fontSize: 13, color: S.textDim, marginRight: "auto" }}>
                    {ergebnis.anzahl === 0 ? "Keine Treffer – gut so."
                      : `${ergebnis.anzahl.toLocaleString("de-DE")} ${ergebnis.gedeckelt ? "Treffer (die ersten)" : "Treffer"}`}
                    {ergebnis.mandant ? ` · ${ergebnis.mandant}` : ""}
                  </span>
                  {ergebnis.anzahl > 0 && (
                    <button onClick={excel} style={knopf.neben}><Download size={14} /> Als Excel</button>
                  )}
                  <button onClick={speichern} disabled={speichert} style={knopf.haupt}>
                    {speichert ? <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} /> : <Save size={14} />}
                    Speichern
                  </button>
                </div>
                {ergebnis.anzahl > 0 && (
                  <div style={{ overflowX: "auto", border: `1px solid ${S.border}`, borderRadius: 8, maxHeight: 560 }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, minWidth: 560 }}>
                      <thead>
                        <tr>
                          {spalten.map((s) => (
                            <th key={s.name} style={{ position: "sticky", top: 0, textAlign: s.typ === "geld" || s.typ === "zahl" ? "right" : "left",
                              padding: "8px 12px", backgroundColor: S.bgEl, color: S.textDim, fontWeight: 600, whiteSpace: "nowrap" }}>
                              {s.label || s.name}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {ergebnis.zeilen.map((z, i) => (
                          <tr key={i}>
                            {spalten.map((s) => (
                              <td key={s.name} style={{ padding: "7px 12px", borderTop: `1px solid ${S.border}`,
                                textAlign: s.typ === "geld" || s.typ === "zahl" ? "right" : "left",
                                fontVariantNumeric: "tabular-nums", whiteSpace: s.typ === "text" ? "normal" : "nowrap" }}>
                                {zelle(z[s.name], s.typ)}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>
    </section>
  );
}
