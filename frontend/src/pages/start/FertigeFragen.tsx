/**
 * Eigene Auswertung (Händler-Ansicht, Phase 3+4): links die fertigen Fragen,
 * rechts der Satzbaukasten „Zeige mir … die … sortiert nach …“ mit Ergebnis,
 * Excel, „Speichern“ und „Per Mail“.
 * Eine Frage mit hinterlegtem Satz lädt diesen in den Baukasten; eine frei
 * getippte Frage (startFrage, vom Fragefeld der Übersicht) übersetzt die KI.
 * Backend: /api/start/{fragen,satz,satz/verstehen,auswertung/…}.
 */
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Download, Loader2, Mail, Save, Sparkles } from "lucide-react";
import api, { fehlerText } from "../../api/client";
import { useLizenz } from "../../contexts/LizenzContext";
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

const ZEITRAUM_KNOPF = { letzte_30: "letzte 30 Tage", dieses_jahr: "dieses Jahr", "12_monate": "letzte 12 Monate" };

const TAKTE = [
  { key: "montag", text: "jeden Montag" },
  { key: "werktags", text: "werktags" },
  { key: "monat", text: "am Monatsersten" },
];

function Chip({ an, onClick, children }) {
  return (
    <button onClick={onClick} aria-pressed={an}
      style={{ padding: "6px 13px", minHeight: 36, borderRadius: 999, cursor: "pointer", fontSize: 13,
        border: `1px solid ${an ? S.accent : S.border}`, fontWeight: an ? 700 : 400,
        backgroundColor: an ? S.accent : "transparent", color: an ? S.accentFg : S.textMain }}>
      {children}
    </button>
  );
}

const marke = { backgroundColor: "color-mix(in srgb, var(--accent) 16%, transparent)", color: S.accent,
  padding: "1px 7px", borderRadius: 5, fontWeight: 600 };

export default function FertigeFragen({ startFrage = "" }) {
  const navigate = useNavigate();
  const lizenz = useLizenz();
  const [fragen, setFragen] = useState(null);
  const [wortschatz, setWortschatz] = useState(null);
  const [frage, setFrage] = useState(null);          // gewählte fertige Frage (ohne Satz)
  const [auswahl, setAuswahl] = useState(null);      // {koernung, bedingung, n, sortierung, zeitraum}
  const [ergebnis, setErgebnis] = useState(null);
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState(null);
  const [meldung, setMeldung] = useState(null);
  const [speichert, setSpeichert] = useState(false);
  const [ki, setKi] = useState(null);                // {laeuft} | {hinweis} beim Übersetzen einer Frage
  const [mailOffen, setMailOffen] = useState(false);
  const [mail, setMail] = useState({ email: "", takt: "montag" });
  const lauf = useRef(0);

  useEffect(() => {
    api.get("/api/start/fragen").then(({ data }) => setFragen(data || [])).catch((e) => setFehler(fehlerText(e)));
    api.get("/api/start/satz").then(({ data }) => setWortschatz(data)).catch((e) => setFehler(fehlerText(e)));
  }, []);

  // Frage aus dem Fragefeld der Übersicht: die KI bildet sie auf den Satz ab.
  useEffect(() => {
    if (!startFrage) return;
    setKi({ laeuft: true, text: startFrage });
    api.post("/api/start/satz/verstehen", { text: startFrage }, { timeout: 120000 })
      .then(({ data }) => {
        if (data.passt) { setKi({ text: startFrage, satz: data.satz }); waehle(data.auswahl); }
        else setKi({ text: startFrage, hinweis: data.hinweis });
      })
      .catch((e) => setKi({ text: startFrage, hinweis: fehlerText(e) }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startFrage]);

  const objekt = wortschatz?.objekte.find((o) => o.key === auswahl?.koernung) || null;
  const bedingung = objekt?.bedingungen.find((b) => b.key === auswahl?.bedingung) || null;

  const rechnen = async (body) => {
    const nr = ++lauf.current;
    setErgebnis(null); setFehler(null); setMeldung(null); setMailOffen(false); setLaeuft(true);
    try {
      const { data } = await api.post("/api/start/auswertung/vorschau", body, { timeout: 120000 });
      if (nr === lauf.current) setErgebnis(data);
    } catch (e) {
      if (nr === lauf.current) setFehler(fehlerText(e));
    } finally {
      if (nr === lauf.current) setLaeuft(false);
    }
  };

  // Satz ändern → neu rechnen (leicht verzögert, damit Tippen in der Zahl nicht jedes Mal rechnet)
  useEffect(() => {
    if (!auswahl) return;
    const t = setTimeout(() => rechnen({ satz: auswahl }), 350);
    return () => clearTimeout(t);
  }, [auswahl]);

  const waehle = (neu) => { setFrage(null); setAuswahl(neu); };

  const frageOeffnen = (f) => {
    setKi(null);
    if (f.satz) { waehle({ ...f.satz }); return; }
    setAuswahl(null); setFrage(f);
    rechnen({ frage: f.key });
  };

  const satzNeu = (koernung) => {
    const o = wortschatz.objekte.find((x) => x.key === koernung);
    waehle({ koernung, bedingung: o.bedingungen[0].key, n: o.bedingungen[0].n,
      sortierung: o.sortierungen[0].key, zeitraum: o.zeitraum ? (auswahl?.zeitraum || "12_monate") : null });
  };
  const setze = (teil) => setAuswahl((a) => ({ ...a, ...teil }));

  const quelle = frage ? { frage: frage.key } : auswahl ? { satz: auswahl } : null;
  const titel = ergebnis?.titel || frage?.titel || "Auswertung";

  // Ausgabespalten: der interne Schlüssel (erste Spalte) bleibt weg.
  const spalten = (ergebnis?.spalten || []).filter((s) => !s.schluessel);

  const excel = async () => {
    const zeilen = (ergebnis?.zeilen || []).map((z) =>
      Object.fromEntries(spalten.map((s) => [s.label || s.name, zelle(z[s.name], s.typ === "geld" ? "zahl" : s.typ)])));
    try {
      const resp = await api.post("/api/forms/table-xlsx",
        { title: titel.slice(0, 31), columns: spalten.map((s) => s.label || s.name), rows: zeilen },
        { responseType: "blob" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(resp.data);
      a.download = `${titel.replace(/[^\wäöüÄÖÜß -]+/g, "").trim().slice(0, 80) || "auswertung"}.xlsx`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    } catch (e) {
      setFehler(`Excel-Export fehlgeschlagen: ${fehlerText(e)}`);
    }
  };

  const speichern = async () => {
    setSpeichert(true); setFehler(null); setMeldung(null);
    try {
      const { data } = await api.post("/api/start/auswertung/speichern", quelle, { timeout: 120000 });
      setMeldung({ text: `Gespeichert unter „${data.form_name}“.`, formId: data.form_id });
    } catch (e) {
      setFehler(fehlerText(e));
    } finally {
      setSpeichert(false);
    }
  };

  const mailen = async () => {
    setSpeichert(true); setFehler(null); setMeldung(null);
    try {
      const { data } = await api.post("/api/start/auswertung/mailen", { ...quelle, ...mail }, { timeout: 120000 });
      setMailOffen(false);
      setMeldung({ text: `Eingerichtet: „${data.titel}“ geht ${data.takt} an ${data.email}.`, formId: data.form_id });
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
  const frageAktiv = (f) => (frage?.key === f.key)
    || (!!f.satz && !!auswahl && Object.keys(f.satz).every((k) => f.satz[k] === auswahl[k]));

  const zahlText = bedingung?.einheit === "€" ? "Betrag" : bedingung?.einheit === "%" ? "Prozent" : "Tage";
  const [vorN, nachN] = (bedingung?.text || "").split("{n}");

  return (
    <section aria-label="Auswertung" style={{ display: "flex", flexWrap: "wrap", gap: 20, alignItems: "flex-start" }}>
      <div style={{ flex: "1 1 260px", maxWidth: 360, minWidth: 0, display: "flex", flexDirection: "column", gap: 14 }}>
        <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: S.textBright }}>Fertige Fragen</h2>
        {!fragen && !fehler && <span style={{ color: S.textDim }}>Lädt…</span>}
        {gruppen.map((g) => (
          <div key={g.name} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase", color: S.textDim }}>
              {g.name}
            </span>
            {g.fragen.map((f) => {
              const an = frageAktiv(f);
              return (
                <button key={f.key} onClick={() => frageOeffnen(f)} aria-pressed={an}
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

      <div style={{ flex: "999 1 480px", minWidth: 0, ...karte, padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
        {ki && (
          <div style={{ display: "flex", gap: 10, alignItems: "flex-start", fontSize: 14, padding: "10px 12px", borderRadius: 8,
            backgroundColor: "color-mix(in srgb, var(--accent) 7%, transparent)" }}>
            {ki.laeuft ? <Loader2 size={16} style={{ animation: "spin 1s linear infinite", marginTop: 2, flex: "none" }} />
              : <Sparkles size={16} style={{ color: S.accent, marginTop: 2, flex: "none" }} />}
            <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
              <span style={{ color: S.textDim }}>„{ki.text}“</span>
              {ki.laeuft && <span>Übersetze die Frage…</span>}
              {ki.satz && <span>So verstanden – unten anpassbar.</span>}
              {ki.hinweis && (
                <span>
                  {ki.hinweis}{" "}
                  {lizenz.hat("ai_build") && (
                    <button onClick={() => navigate("/dashboard", { state: { tab: "werkbank", frage: ki.text } })}
                      style={{ background: "none", border: "none", color: S.accent, cursor: "pointer", padding: 0, fontWeight: 600 }}>
                      In der KI-Werkbank fragen
                    </button>
                  )}
                </span>
              )}
            </div>
          </div>
        )}

        {/* Satzbaukasten */}
        {wortschatz && !frage && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {auswahl && objekt ? (
              <p style={{ margin: 0, fontSize: 19, lineHeight: 1.6, color: S.textBright }}>
                Zeige mir <span style={marke}>{objekt.plural}</span>, die{" "}
                <span style={marke}>
                  {vorN}
                  {bedingung?.n != null && (
                    <input aria-label={zahlText} value={auswahl.n ?? ""} inputMode="numeric"
                      onChange={(e) => setze({ n: e.target.value.replace(/[^\d.,]/g, "").replace(",", ".") })}
                      style={{ width: `${Math.max(3, String(auswahl.n ?? "").length + 1)}ch`, font: "inherit", fontWeight: 700,
                        color: S.accent, background: "transparent", border: "none", borderBottom: `2px solid ${S.accent}`,
                        textAlign: "center", padding: 0 }} />
                  )}
                  {nachN}
                </span>, sortiert nach{" "}
                <span style={marke}>{objekt.sortierungen.find((s) => s.key === auswahl.sortierung)?.text}</span>
                {objekt.zeitraum && auswahl.zeitraum && (
                  <> ({wortschatz.zeitraeume.find((z) => z.key === auswahl.zeitraum)?.text})</>
                )}.
              </p>
            ) : (
              <p style={{ margin: 0, color: S.textDim, lineHeight: 1.6 }}>
                Wählen Sie links eine Frage – oder stellen Sie hier selbst einen Satz zusammen.
              </p>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <span style={{ fontSize: 13, color: S.textDim }}>Was soll in der Liste stehen?</span>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {wortschatz.objekte.map((o) => (
                  <Chip key={o.key} an={auswahl?.koernung === o.key} onClick={() => satzNeu(o.key)}>{o.plural}</Chip>
                ))}
              </div>
            </div>
            {objekt && (
              <>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <span style={{ fontSize: 13, color: S.textDim }}>Welche davon?</span>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                    {objekt.bedingungen.map((b) => (
                      <Chip key={b.key} an={auswahl.bedingung === b.key}
                        onClick={() => setze({ bedingung: b.key, n: b.n })}>
                        {b.text.replace("{n}", b.n != null ? String(b.n) : "…")}
                      </Chip>
                    ))}
                  </div>
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 24 }}>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <span style={{ fontSize: 13, color: S.textDim }}>Sortiert nach</span>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                      {objekt.sortierungen.map((s) => (
                        <Chip key={s.key} an={auswahl.sortierung === s.key} onClick={() => setze({ sortierung: s.key })}>{s.text}</Chip>
                      ))}
                    </div>
                  </div>
                  {objekt.zeitraum && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      <span style={{ fontSize: 13, color: S.textDim }}>Zeitraum</span>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                        {wortschatz.zeitraeume.map((z) => (
                          <Chip key={z.key} an={auswahl.zeitraum === z.key} onClick={() => setze({ zeitraum: z.key })}>
                            {ZEITRAUM_KNOPF[z.key] || z.text}
                          </Chip>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        )}

        {frage && (
          <div>
            <h3 style={{ margin: 0, fontSize: 19, color: S.textBright }}>{frage.titel}</h3>
            <p style={{ margin: "4px 0 0", color: S.textDim, fontSize: 14, lineHeight: 1.5 }}>
              {frage.text}{frage.zeitraum ? ` Zeitraum: ${frage.zeitraum.toLowerCase()}.` : ""}{" "}
              <button onClick={() => { setFrage(null); setErgebnis(null); }}
                style={{ background: "none", border: "none", color: S.accent, cursor: "pointer", padding: 0, fontWeight: 600 }}>
                Selbst einen Satz bauen
              </button>
            </p>
          </div>
        )}

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
                {ergebnis.anzahl === 0 ? "Keine Treffer."
                  : `${ergebnis.anzahl.toLocaleString("de-DE")} ${ergebnis.gedeckelt ? "Treffer (die ersten)" : "Treffer"}`}
                {ergebnis.mandant ? ` · ${ergebnis.mandant}` : ""}
              </span>
              {ergebnis.anzahl > 0 && (
                <button onClick={excel} style={knopf.neben}><Download size={14} /> Als Excel</button>
              )}
              <button onClick={() => setMailOffen((v) => !v)} style={knopf.neben} aria-expanded={mailOffen}>
                <Mail size={14} /> Per Mail
              </button>
              <button onClick={speichern} disabled={speichert} style={knopf.haupt}>
                {speichert ? <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} /> : <Save size={14} />}
                Speichern
              </button>
            </div>

            {mailOffen && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end", padding: 14, borderRadius: 10,
                border: `1px solid ${S.border}`, backgroundColor: S.bgMain }}>
                <div style={{ display: "flex", flexDirection: "column", gap: 6, flex: "1 1 220px", minWidth: 0 }}>
                  <label htmlFor="mail-an" style={{ fontSize: 13, color: S.textDim }}>An</label>
                  <input id="mail-an" type="email" value={mail.email} placeholder="name@firma.de"
                    onChange={(e) => setMail((m) => ({ ...m, email: e.target.value }))}
                    style={{ minHeight: 40, padding: "8px 10px", borderRadius: 8, border: `1px solid ${S.border}`,
                      backgroundColor: S.bgCard, color: S.textMain, fontSize: 14 }} />
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <span style={{ fontSize: 13, color: S.textDim }}>Wann</span>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {TAKTE.map((t) => (
                      <Chip key={t.key} an={mail.takt === t.key} onClick={() => setMail((m) => ({ ...m, takt: t.key }))}>{t.text}</Chip>
                    ))}
                  </div>
                </div>
                <button onClick={mailen} disabled={speichert || !mail.email.trim()} style={knopf.haupt}>
                  {speichert && <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} />}
                  Einrichten
                </button>
                <span style={{ flexBasis: "100%", fontSize: 12, color: S.textDim }}>
                  Jede Mail enthält die aktuelle Liste als PDF. Abstellen unter „Per Mail“.
                </span>
              </div>
            )}

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
      </div>
    </section>
  );
}
