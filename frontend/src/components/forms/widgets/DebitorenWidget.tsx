import { useState, useCallback } from "react";
import { Loader2, CheckCircle2, AlertTriangle, XCircle, RefreshCw } from "lucide-react";
import api from "../../../api/client";

const S = {
  bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)", border: "var(--border)",
  textMain: "var(--text-main)", textBright: "var(--text-bright)", textDim: "var(--text-dim)",
  accent: "var(--accent)",
};

/** Fehlende Debitorennummern in einem Zug nachpflegen.
 *
 *  Ohne Debitorennummer hat eine Buchung kein Konto und DATEV weist den ganzen
 *  Stapel ab. Die Nummer in der Wawi nachzutragen ist Fleißarbeit – hier geht es
 *  mit einem Häkchen je Kunde.
 *
 *  Vorgeschlagen wird die Kundennummer, weil sie in diesem Bestand bei 90 % der
 *  gepflegten Kunden auch die Debitorennummer ist. Eine Regel ist das nicht:
 *  wo die Nummer schon einem anderen Kunden gehört, lässt sich nichts ankreuzen.
 *  Alle Häkchen starten AUS – übernommen wird nur, was jemand aktiv auswählt.
 */
export default function DebitorenWidget({ widget, baseParams }) {
  const cfg = widget.config || {};
  const connId = cfg.connection_id;
  const [faelle, setFaelle] = useState(null);
  const [wahl, setWahl] = useState({});
  const [laden, setLaden] = useState(false);
  const [schreiben, setSchreiben] = useState(false);
  const [fehler, setFehler] = useState(null);
  const [ergebnis, setErgebnis] = useState(null);
  // Gegen WELCHE Wawi hier gearbeitet wird. Das Backend lenkt den Zugriff auf den
  // aktiven Mandanten um; ohne diese Anzeige bliebe unsichtbar, wohin geschrieben
  // wird – bei einem Schreibzugriff die wichtigste Angabe überhaupt.
  const [wawi, setWawi] = useState(null);

  const jahr = Number(baseParams?.year) || new Date().getFullYear();
  const monat = Number(baseParams?.month) || (new Date().getMonth() + 1);

  const laden_ = useCallback(async () => {
    if (!connId) { setFehler("Im Widget ist keine JTL-Verbindung hinterlegt."); return; }
    setLaden(true); setFehler(null); setErgebnis(null);
    try {
      const { data } = await api.post("/api/datev/debitoren-offen",
        { connection_id: connId, year: jahr, month: monat });
      setFaelle(data.faelle || []);
      setWawi(data.wawi || null);
      setWahl({});                     // bewusst nichts vorausgewählt
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
    } finally { setLaden(false); }
  }, [connId, jahr, monat]);

  async function uebernehmen() {
    const kunden = (faelle || [])
      .filter(f => wahl[f.kKunde] && f.uebernehmbar)
      .map(f => ({ kKunde: f.kKunde, nummer: f.vorschlag }));
    if (!kunden.length) return;
    setSchreiben(true); setFehler(null);
    try {
      const { data } = await api.post("/api/datev/debitoren-schreiben",
        { connection_id: connId, kunden, bestaetigt: true });
      setErgebnis(data);
      if (!data.errors?.length) await laden_();   // Liste frisch ziehen
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
    } finally { setSchreiben(false); }
  }

  const waehlbar = (faelle || []).filter(f => f.uebernehmbar);
  const gewaehlt = waehlbar.filter(f => wahl[f.kKunde]);
  const alleGewaehlt = waehlbar.length > 0 && gewaehlt.length === waehlbar.length;

  const td = { padding: "6px 8px", fontSize: 11, color: S.textMain,
               borderBottom: `1px solid ${S.border}`, verticalAlign: "top" };

  return (
    <div style={{ padding: 14 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <button onClick={laden_} disabled={laden}
          style={{ display: "flex", alignItems: "center", gap: 6, background: S.bgEl,
            border: `1px solid ${S.border}`, color: S.textMain, borderRadius: 7,
            padding: "7px 14px", fontSize: 12, cursor: laden ? "default" : "pointer" }}>
          {laden ? <Loader2 size={13} className="spin" /> : <RefreshCw size={13} />}
          Offene Fälle laden ({String(monat).padStart(2, "0")}/{jahr})
        </button>
        {wawi && (
          <span style={{ fontSize: 11, color: S.textBright, background: S.bgEl,
            border: `1px solid ${S.border}`, borderRadius: 6, padding: "4px 9px" }}>
            Wawi: <b>{wawi}</b>
          </span>
        )}
        {faelle && (
          <span style={{ fontSize: 11, color: S.textDim }}>
            {faelle.length} Kunde{faelle.length === 1 ? "" : "n"} ohne Debitorennummer
            {waehlbar.length < faelle.length
              ? ` · ${faelle.length - waehlbar.length} davon nicht übernehmbar` : ""}
          </span>
        )}
      </div>

      {fehler && (
        <div style={{ display: "flex", gap: 8, marginTop: 10, padding: "9px 12px",
          borderRadius: 7, background: "rgba(248,113,113,.1)",
          border: "1px solid rgba(248,113,113,.4)", color: "#f87171", fontSize: 11 }}>
          <XCircle size={13} style={{ flexShrink: 0, marginTop: 1 }} />{fehler}
        </div>
      )}

      {ergebnis && (
        <div style={{ display: "flex", gap: 8, marginTop: 10, padding: "9px 12px",
          borderRadius: 7,
          background: ergebnis.errors?.length ? "rgba(248,113,113,.1)" : "rgba(52,211,153,.1)",
          border: `1px solid ${ergebnis.errors?.length ? "rgba(248,113,113,.4)" : "rgba(52,211,153,.4)"}`,
          color: ergebnis.errors?.length ? "#f87171" : "#34d399", fontSize: 11 }}>
          {ergebnis.errors?.length
            ? <XCircle size={13} style={{ flexShrink: 0, marginTop: 1 }} />
            : <CheckCircle2 size={13} style={{ flexShrink: 0, marginTop: 1 }} />}
          <span>
            {ergebnis.errors?.length
              ? ergebnis.errors.join(" · ")
              : `${ergebnis.geschrieben} Debitorennummer${ergebnis.geschrieben === 1 ? "" : "n"} in die Wawi geschrieben.`}
            {ergebnis.zeilen?.some(z => z.status === "uebersprungen") && (
              <span style={{ color: S.textDim }}>
                {" "}Übersprungen: {ergebnis.zeilen.filter(z => z.status === "uebersprungen")
                  .map(z => `Kunde ${z.kKunde} (${z.grund})`).join(", ")}
              </span>
            )}
          </span>
        </div>
      )}

      {faelle && faelle.length === 0 && (
        <div style={{ display: "flex", gap: 8, marginTop: 12, padding: "9px 12px",
          borderRadius: 7, background: "rgba(52,211,153,.1)",
          border: "1px solid rgba(52,211,153,.4)", color: "#34d399", fontSize: 11 }}>
          <CheckCircle2 size={13} style={{ flexShrink: 0, marginTop: 1 }} />
          Kein offener Fall in diesem Monat – jeder Kunde mit Umsatz hat eine Debitorennummer.
        </div>
      )}

      {faelle && faelle.length > 0 && (
        <>
          <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 12 }}>
            <thead>
              <tr style={{ background: S.bgEl }}>
                <th style={{ ...td, width: 30, borderBottom: `1px solid ${S.border}` }}>
                  <input type="checkbox" checked={alleGewaehlt}
                    onChange={e => setWahl(e.target.checked
                      ? Object.fromEntries(waehlbar.map(f => [f.kKunde, true])) : {})}
                    title="Alle übernehmbaren auswählen" />
                </th>
                {["Kunde", "Kundennr.", "Belege", "Umsatz", "wird gesetzt auf", "Prüfung"].map(h => (
                  <th key={h} style={{ padding: "6px 8px", fontSize: 10, textAlign: "left",
                    color: S.textDim, fontWeight: 600,
                    borderBottom: `1px solid ${S.border}` }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {faelle.map(f => (
                <tr key={f.kKunde} style={{ opacity: f.uebernehmbar ? 1 : 0.6 }}>
                  <td style={td}>
                    <input type="checkbox" disabled={!f.uebernehmbar}
                      checked={!!wahl[f.kKunde]}
                      onChange={e => setWahl(w => ({ ...w, [f.kKunde]: e.target.checked }))} />
                  </td>
                  <td style={td}>
                    <div style={{ color: S.textBright }}>{f.name}</div>
                    <div style={{ color: S.textDim, fontSize: 10 }}>kKunde {f.kKunde}</div>
                  </td>
                  <td style={td}>{f.kundennummer || "—"}</td>
                  <td style={td}>{f.belege}</td>
                  <td style={{ ...td, whiteSpace: "nowrap" }}>
                    {Number(f.brutto).toFixed(2)} €</td>
                  <td style={{ ...td, color: f.uebernehmbar ? S.textBright : S.textDim,
                    fontWeight: f.uebernehmbar ? 600 : 400 }}>
                    {f.vorschlag ?? "—"}</td>
                  <td style={{ ...td, fontSize: 10,
                    color: f.uebernehmbar ? S.textDim : "#e0a070" }}>
                    {!f.uebernehmbar && (
                      <AlertTriangle size={11} style={{ verticalAlign: -1, marginRight: 4 }} />
                    )}
                    {f.hinweis}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 12,
            flexWrap: "wrap" }}>
            <button onClick={uebernehmen} disabled={!gewaehlt.length || schreiben}
              style={{ display: "flex", alignItems: "center", gap: 6,
                background: gewaehlt.length ? "#6ee7b7" : S.bgEl,
                border: `1px solid ${S.border}`,
                color: gewaehlt.length ? "#0b0b0c" : S.textDim, borderRadius: 7,
                padding: "8px 16px", fontSize: 12, fontWeight: 600,
                cursor: gewaehlt.length && !schreiben ? "pointer" : "default" }}>
              {schreiben ? <Loader2 size={13} className="spin" /> : <CheckCircle2 size={13} />}
              {gewaehlt.length} Nummer{gewaehlt.length === 1 ? "" : "n"} in die Wawi übernehmen
            </button>
            <span style={{ fontSize: 10, color: S.textDim, lineHeight: 1.5 }}>
              Schreibt <b>tkunde.nDebitorennr</b>{wawi ? <> in <b>{wawi}</b></> : " in der JTL-Wawi"}. Nur leere Felder werden
              gesetzt, vorhandene bleiben unangetastet – und jede Nummer wird unmittelbar
              vorher noch einmal auf Eindeutigkeit geprüft.
            </span>
          </div>
        </>
      )}
    </div>
  );
}
