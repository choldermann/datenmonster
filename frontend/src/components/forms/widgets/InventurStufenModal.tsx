import { useState } from "react";
import { X, SlidersHorizontal, Plus, Trash2, Loader2, RotateCcw } from "lucide-react";
import { fehlerText } from "../../../api/client";

const S = {
  bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)", bgMain: "var(--bg-main)",
  border: "var(--border)", textMain: "var(--text-main)", textBright: "var(--text-bright)",
  textDim: "var(--text-dim)", accent: "var(--accent)",
};

const inp = {
  backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4,
  color: S.textMain, fontSize: 12, padding: "5px 8px", outline: "none",
  width: 72, textAlign: "right",
};

const btn = {
  display: "inline-flex", alignItems: "center", gap: 6, padding: "6px 11px",
  borderRadius: 5, border: `1px solid ${S.border}`, backgroundColor: S.bgEl,
  color: S.textMain, fontSize: 12, cursor: "pointer",
};

const eur = (n) => new Intl.NumberFormat("de-DE", {
  style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0);
const zahl = (n) => new Intl.NumberFormat("de-DE").format(n || 0);

function dauer(t) {
  if (t >= 30 && t % 30 === 0) {
    const m = t / 30;
    return `${m} ${m === 1 ? "Monat" : "Monate"}`;
  }
  return `${t} ${t === 1 ? "Tag" : "Tage"}`;
}

/**
 * Beschriftung einer Stufe aus ihren Resttagen und denen der Stufe davor.
 * Dieselbe Regel wie `_stufen_label` in inventur_service.py – die Beschriftung
 * landet im Grundtext der Bewertung und damit in der Liste für den Steuerberater.
 */
export function stufenLabel(bis, vorher) {
  if (bis < 0) {
    if (vorher === null) return `MHD mindestens ${-bis} Tage überschritten`;
    return `MHD ${-bis} bis ${-vorher - 1} Tage überschritten`;
  }
  if (bis === 0) {
    if (vorher === null) return "MHD überschritten";
    return `MHD bis ${-vorher - 1} Tage überschritten`;
  }
  if (vorher === null) return `Restlaufzeit bis ${dauer(bis)} (auch überschritten)`;
  if (vorher < 0) return `Restlaufzeit bis ${dauer(bis)}`;
  if (vorher === 0) return `unter ${dauer(bis)} Restlaufzeit`;
  if (vorher >= 30 && vorher % 30 === 0 && bis % 30 === 0) {
    return `${vorher / 30} bis ${bis / 30} Monate Restlaufzeit`;
  }
  return `${dauer(vorher)} bis ${dauer(bis)} Restlaufzeit`;
}

const alsZeilen = (stufen) => (stufen || []).map(s => ({
  bis: String(s.bis_tage ?? ""), prozent: String(s.prozent ?? ""),
}));

/**
 * Modal „Abwertungsstaffel": ab welcher Restlaufzeit wie viel abgewertet wird.
 *
 * Die Staffel gilt für genau diese Inventur und gehört zum Beleg – deshalb ist
 * sie bei einer abgeschlossenen Inventur nur lesbar. Die Vorschau rechnet mit den
 * Partien der Liste, damit man VOR dem Speichern sieht, was eine Änderung kostet.
 *
 * `vorschau(stufen)` liefert je Stufe (gleiche Reihenfolge) {chargen, wert, abwertung}.
 * `onSave(stufen, neuVorschlagen)` wirft bei Fehlern; das Modal zeigt sie selbst an.
 */
export default function InventurStufenModal({ stufen, standard, gesperrt, vorschau,
                                              onClose, onSave }) {
  const [zeilen, setZeilen] = useState(() => alsZeilen(stufen));
  // Startet aus (Vorgabe: Vorschläge wählt der Anwender aktiv) – der Hinweis
  // darunter sagt, was ohne Neuberechnung passiert.
  const [neuVorschlagen, setNeuVorschlagen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [fehler, setFehler] = useState(null);

  // Deutsches Dezimalkomma zulassen – Number("12,5") wäre NaN.
  const zahlAus = (v) => {
    const s = String(v ?? "").trim().replace(",", ".");
    if (s === "") return null;
    const n = Number(s);
    return isNaN(n) ? null : n;
  };
  const geparst = zeilen.map(z => ({ bis_tage: zahlAus(z.bis), prozent: zahlAus(z.prozent) }));

  const problem = (() => {
    if (!zeilen.length) return "Die Staffel braucht mindestens eine Stufe.";
    if (geparst.some(s => s.bis_tage === null || s.prozent === null)) {
      return "Jede Stufe braucht Resttage und einen Prozentsatz.";
    }
    if (geparst.some(s => !Number.isInteger(s.bis_tage))) return "Resttage bitte als ganze Zahl.";
    if (geparst.some(s => s.prozent < 0 || s.prozent > 100)) {
      return "Der Prozentsatz muss zwischen 0 und 100 liegen.";
    }
    const tage = geparst.map(s => s.bis_tage);
    if (new Set(tage).size !== tage.length) return "Zwei Stufen haben dieselben Resttage.";
    return null;
  })();

  // Beschriftung braucht die Stufe davor – nach Resttagen, nicht nach Eingabe-
  // reihenfolge. Die Zeilen selbst springen beim Tippen nicht; sortiert wird beim
  // Speichern.
  const vorherVon = {};
  if (!problem) {
    let v = null;
    geparst.map((s, i) => i)
      .sort((a, b) => geparst[a].bis_tage - geparst[b].bis_tage)
      .forEach(i => { vorherVon[i] = v; v = geparst[i].bis_tage; });
  }
  const vs = !problem && vorschau ? vorschau(geparst) : null;
  const summe = vs ? vs.reduce((a, x) => a + x.abwertung, 0) : 0;
  const partien = vs ? vs.reduce((a, x) => a + x.chargen, 0) : 0;

  const setze = (i, feld, wert) =>
    setZeilen(prev => prev.map((z, k) => (k === i ? { ...z, [feld]: wert } : z)));
  const neueStufe = () => {
    const hoechste = Math.max(0, ...geparst.map(s => s.bis_tage ?? 0));
    setZeilen(prev => [...prev, { bis: String(hoechste + 90), prozent: "10" }]);
  };

  const speichern = async () => {
    if (problem || gesperrt) return;
    setBusy(true);
    setFehler(null);
    try {
      await onSave(geparst, neuVorschlagen);
    } catch (e) {
      setFehler(fehlerText(e, "Speichern nicht möglich."));
      setBusy(false);
    }
  };

  const th = { padding: "4px 10px 6px 0", fontWeight: 500, color: S.textDim,
    whiteSpace: "nowrap", textAlign: "left" };
  const td = { padding: "4px 10px 4px 0", verticalAlign: "middle" };

  return (
    <div onClick={busy ? undefined : onClose}
      style={{ position: "fixed", inset: 0, zIndex: 1000, backgroundColor: "rgba(0,0,0,0.55)",
        display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
      <div onClick={e => e.stopPropagation()}
        style={{ width: "min(760px, 96vw)", maxHeight: "90vh", backgroundColor: S.bgCard,
          border: `1px solid ${S.border}`, borderRadius: 12, display: "flex",
          flexDirection: "column", overflow: "hidden", boxShadow: "0 20px 60px rgba(0,0,0,0.5)" }}>

        <div style={{ padding: "14px 18px", borderBottom: `1px solid ${S.border}`,
          display: "flex", alignItems: "center", gap: 10 }}>
          <SlidersHorizontal size={15} style={{ color: S.accent, flexShrink: 0 }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <p style={{ fontSize: 14, fontWeight: 700, color: S.textBright, margin: 0 }}>
              Abwertungsstaffel
            </p>
            <p style={{ fontSize: 11, color: S.textDim, margin: "2px 0 0" }}>
              Ab welcher Restlaufzeit wie viel abgewertet wird – gilt für „Abwertung vorschlagen“
              in dieser Inventur.
            </p>
          </div>
          <button onClick={onClose} disabled={busy}
            style={{ background: "none", border: "none", color: S.textDim,
              cursor: busy ? "default" : "pointer", padding: 2, flexShrink: 0 }}>
            <X size={16} />
          </button>
        </div>

        <div style={{ overflow: "auto", padding: "12px 18px" }}>
          <p style={{ fontSize: 11.5, color: S.textDim, margin: "0 0 10px", lineHeight: 1.5 }}>
            Gerechnet wird <b>je Charge</b>: Resttage = MHD minus Stichtag. Eine Charge fällt in
            die erste Stufe, deren Resttage sie nicht übersteigt. <b>0</b> heißt MHD am Stichtag
            erreicht oder überschritten, <b>negative</b> Werte „so viele Tage drüber“. Chargen
            jenseits der letzten Stufe bleiben unangetastet, von Hand bewertete Positionen ebenso.
          </p>

          <table style={{ borderCollapse: "collapse", fontSize: 12, width: "100%" }}>
            <thead>
              <tr>
                <th style={th}>Resttage bis</th>
                <th style={th}>Abwertung</th>
                <th style={th}>Bereich</th>
                <th style={{ ...th, textAlign: "right" }}>Partien</th>
                <th style={{ ...th, textAlign: "right" }}>Wert zum EK</th>
                <th style={{ ...th, textAlign: "right" }}>Abwertung</th>
                <th style={th} />
              </tr>
            </thead>
            <tbody>
              {zeilen.map((z, i) => {
                const g = geparst[i];
                const label = !problem ? stufenLabel(g.bis_tage, vorherVon[i]) : "";
                const v = vs ? vs[i] : null;
                return (
                  <tr key={i} style={{ borderTop: `1px solid ${S.border}` }}>
                    <td style={td}>
                      <input style={inp} value={z.bis} disabled={gesperrt || busy}
                             inputMode="numeric"
                             onChange={e => setze(i, "bis", e.target.value)} />
                    </td>
                    <td style={{ ...td, whiteSpace: "nowrap" }}>
                      <input style={{ ...inp, width: 56 }} value={z.prozent}
                             disabled={gesperrt || busy} inputMode="decimal"
                             onChange={e => setze(i, "prozent", e.target.value)} />
                      <span style={{ marginLeft: 4, color: S.textDim }}>%</span>
                    </td>
                    <td style={{ ...td, color: S.textMain }}>{label}</td>
                    <td style={{ ...td, textAlign: "right", color: S.textDim }}>
                      {v ? zahl(v.chargen) : ""}
                    </td>
                    <td style={{ ...td, textAlign: "right", color: S.textDim }}>
                      {v ? eur(v.wert) : ""}
                    </td>
                    <td style={{ ...td, textAlign: "right", color: S.textBright }}>
                      {v ? eur(v.abwertung) : ""}
                    </td>
                    <td style={{ ...td, textAlign: "right" }}>
                      {!gesperrt && (
                        <button onClick={() => setZeilen(prev => prev.filter((_, k) => k !== i))}
                          disabled={busy} title="Stufe entfernen"
                          style={{ background: "none", border: "none", color: S.textDim,
                            cursor: "pointer", padding: 2 }}>
                          <Trash2 size={13} />
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {!gesperrt && (
            <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
              <button style={btn} onClick={neueStufe} disabled={busy}>
                <Plus size={13} /> Stufe
              </button>
              <button style={btn} onClick={() => setZeilen(alsZeilen(standard))} disabled={busy}
                      title="Überschritten 100 %, unter 3 Monaten 50 %, 3 bis 6 Monate 25 %">
                <RotateCcw size={13} /> Standard
              </button>
            </div>
          )}

          <div style={{ marginTop: 12, fontSize: 12, color: problem ? "#e07070" : S.textMain }}>
            {problem
              ? problem
              : <>Vorschau: <b>{eur(summe)}</b> Abwertung auf {zahl(partien)} Partien.</>}
          </div>
          {fehler && (
            <div style={{ marginTop: 8, fontSize: 12, color: "#e07070" }}>{fehler}</div>
          )}
        </div>

        <div style={{ padding: "12px 18px", borderTop: `1px solid ${S.border}`,
          display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          {gesperrt ? (
            <span style={{ fontSize: 11.5, color: S.textDim, flex: 1 }}>
              Abgeschlossene Inventur – die Staffel gehört zum Beleg und ist nur lesbar.
            </span>
          ) : (
            <label style={{ display: "flex", alignItems: "flex-start", gap: 8, flex: 1,
              fontSize: 12, color: S.textMain, cursor: "pointer", minWidth: 240 }}>
              <input type="checkbox" checked={neuVorschlagen} disabled={busy}
                     onChange={e => setNeuVorschlagen(e.target.checked)}
                     style={{ marginTop: 2, accentColor: S.accent }} />
              <span>
                Vorschläge danach neu berechnen
                <span style={{ display: "block", fontSize: 10.5, color: S.textDim, marginTop: 1 }}>
                  Rechnet auch übernommene Staffel-Bewertungen neu: geänderte werden wieder
                  zu Vorschlägen, unveränderte bleiben bestätigt. Von Hand Bewertetes bleibt.
                  Ohne Haken passiert das erst beim nächsten „Abwertung vorschlagen“.
                </span>
              </span>
            </label>
          )}
          <button style={btn} onClick={onClose} disabled={busy}>
            {gesperrt ? "Schließen" : "Abbrechen"}
          </button>
          {!gesperrt && (
            <button style={{ ...btn, borderColor: S.accent, color: S.accent }}
                    onClick={speichern} disabled={busy || !!problem}>
              {busy && <Loader2 size={13} className="spin" />} Speichern
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
