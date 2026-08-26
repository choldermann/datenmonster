import { useState, useEffect, useCallback } from "react";
import { Wallet, Trash2, Plus, ChevronDown, ChevronRight, AlertCircle,
         Loader2, History } from "lucide-react";
import api from "../../../api/client";

const S = {
  bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)", bgMain: "var(--bg-main)",
  border: "var(--border)", textMain: "var(--text-main)", textDim: "var(--text-dim)",
  textBright: "var(--text-bright)", accent: "var(--accent)",
};

const inp = {
  backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4,
  color: S.textMain, fontSize: 12, padding: "5px 8px", outline: "none",
};

const eur = (n) => new Intl.NumberFormat("de-DE", {
  style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0);

// Eine Zeitscheibe zählt erst als fertig, wenn Datum UND Betrag stehen.
const unvollstaendig = (e) => !e || !e.gueltig_ab || e.betrag === "" || e.betrag === null
  || e.betrag === undefined || isNaN(Number(e.betrag));

const heuteISO = () => new Date().toISOString().slice(0, 10);
const jahresbeginnISO = () => `${new Date().getFullYear()}-01-01`;

/**
 * Widget "Kostenstruktur": monatliche Fixkosten je Kostenart pflegen.
 *
 * Bewusst ein Formular-Widget und kein eigener Bereich in der Seitenleiste:
 * Fixkosten sind kein Datenmonster-Thema, sondern gehören zu den JTL-Cockpits.
 * Das Widget wird deshalb mit dem GF-Cockpit-Template als eigenes Formular
 * ausgeliefert – wie jedes andere eigenständige Widget rendert es sofort, ohne
 * dass eine Action laufen muss.
 *
 * Der Standardkatalog (Miete, Personal, Strom …) kommt vom Backend und ist
 * immer vorgeblendet; gepflegt werden nur "gültig ab" und der Monatsbetrag.
 * Jede Kostenart trägt eine Zeitleiste: eine Mieterhöhung ist ein zweiter
 * Eintrag, kein überschriebener Wert. Nur so bleibt ein Vorjahresvergleich
 * ehrlich.
 *
 * Die Summen gehen als :cfg_kosten_monat, :cfg_kosten_<gruppe>_monat,
 * :cfg_kosten_zeitraum und :cfg_kosten_monatsreihe in jeden Mapping-Lauf ein –
 * daraus rechnet der Reiter "Ergebnis" des GF-Cockpits das Betriebsergebnis.
 */
export default function KostenWidget({ widget, projectId, canEdit = true }) {
  const [arten, setArten] = useState([]);
  const [gruppen, setGruppen] = useState([]);
  const [summe, setSumme] = useState({ gesamt: 0, gruppen: {} });
  const [laden, setLaden] = useState(true);
  const [fehler, setFehler] = useState(null);
  const [offen, setOffen] = useState({});        // key → Zeitleiste aufgeklappt
  const [neu, setNeu] = useState(null);          // Entwurf für eigene Kostenart
  const [speichert, setSpeichert] = useState(null);

  const q = projectId ? `?project_id=${projectId}` : "";

  const laden_ = useCallback(async () => {
    setLaden(true);
    try {
      const { data } = await api.get(`/api/business-config/costs${q}`);
      setArten(data.kosten || []);
      setGruppen(data.gruppen || []);
      setSumme(data.summe_monat || { gesamt: 0, gruppen: {} });
      setFehler(null);
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
    } finally {
      setLaden(false);
    }
  }, [q]);

  useEffect(() => { laden_(); }, [laden_]);

  // Lokal ändern (flüssiges Tippen), gespeichert wird beim Verlassen des Feldes.
  const aendern = (key, eintraege) =>
    setArten(prev => prev.map(a => a.key === key ? { ...a, eintraege } : a));

  const speichern = async (key) => {
    const art = arten.find(a => a.key === key);
    if (!art) return;
    // Eine halb ausgefüllte Zeile ist noch in Arbeit – typischerweise steht das
    // Datum schon, der Betrag folgt beim nächsten Feld. Solange wird gar nicht
    // gespeichert: ein Speichern würde die Zeile als leer wegschreiben und das
    // anschließende Neuladen die Eingabe überschreiben.
    if ((art.eintraege || []).some(unvollstaendig)) return;
    const eintraege = (art.eintraege || [])
      .map(e => ({ gueltig_ab: e.gueltig_ab || jahresbeginnISO(),
                   betrag: Number(e.betrag) }));
    setSpeichert(key); setFehler(null);
    try {
      await api.put("/api/business-config/costs",
        { project_id: projectId ?? null, key, eintraege });
      await laden_();
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
    } finally {
      setSpeichert(null);
    }
  };

  const leeren = async (key) => {
    setFehler(null);
    try {
      await api.delete(`/api/business-config/costs/${key}${q}`);
      await laden_();
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
    }
  };

  const eigeneAnlegen = async () => {
    if (!neu?.label?.trim()) return;
    try {
      await api.post("/api/business-config/costs/custom", {
        project_id: projectId ?? null,
        label: neu.label.trim(), gruppe_key: neu.gruppe_key || "sonstiges",
      });
      setNeu(null);
      await laden_();
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
    }
  };

  const zeitraumHinzufuegen = (art) => {
    const letzter = art.eintraege?.[art.eintraege.length - 1];
    aendern(art.key, [...(art.eintraege || []),
      { gueltig_ab: heuteISO(), betrag: letzter ? letzter.betrag : "" }]);
    setOffen(prev => ({ ...prev, [art.key]: true }));
  };

  const zeitraumEntfernen = (art, idx) => {
    const rest = (art.eintraege || []).filter((_, i) => i !== idx);
    aendern(art.key, rest);
    // Sofort speichern: ein entfernter Eintrag hat kein Feld mehr, das man
    // verlassen könnte – ohne Speicherung wäre die Zeile nur optisch weg.
    setTimeout(() => speichern(art.key), 0);
  };

  const feldAendern = (art, idx, feld, wert) =>
    aendern(art.key, (art.eintraege || []).map(
      (e, i) => i === idx ? { ...e, [feld]: wert } : e));

  const gepflegt = arten.filter(a => (a.eintraege || []).length > 0).length;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20, padding: 16 }}>
      <div style={{ display: "flex", alignItems: "flex-start",
        justifyContent: "space-between", gap: 20 }}>
        <div>
          <p style={{ fontSize: 11.5, color: S.textDim, maxWidth: 720,
            display: "flex", alignItems: "flex-start", gap: 7 }}>
            <Wallet size={14} style={{ color: S.accent, flexShrink: 0, marginTop: 1 }} />
            <span>
            Monatliche Fixkosten dieses Projekts. Die gängigen Kostenarten sind
            vorgeblendet – einzutragen sind nur Betrag und „gültig ab". Ändert sich
            ein Betrag, kommt ein <b>weiterer Zeitraum</b> dazu statt den alten Wert zu
            überschreiben; vor dem frühesten „gültig ab" wird mit 0 € gerechnet.
            Die Summen fließen in den Reiter <b>Ergebnis</b> des GF-Cockpits.</span>
          </p>
        </div>
        <div style={{ textAlign: "right", whiteSpace: "nowrap" }}>
          <div style={{ fontSize: 10.5, color: S.textDim, letterSpacing: "0.06em",
            textTransform: "uppercase" }}>Fixkosten heute</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: S.textBright }}>
            {eur(summe.gesamt)}<span style={{ fontSize: 12, color: S.textDim }}> / Monat</span>
          </div>
          <div style={{ fontSize: 11, color: S.textDim }}>
            {eur((summe.gesamt || 0) * 12)} / Jahr · {gepflegt} von {arten.length} Arten gepflegt
          </div>
        </div>
      </div>

      {fehler && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "9px 12px",
          border: "1px solid rgba(224,112,112,0.4)", borderRadius: 6, color: "#e07070",
          fontSize: 12 }}>
          <AlertCircle size={13} /> {fehler}
        </div>
      )}

      {laden ? (
        <p style={{ fontSize: 12, color: S.textDim }}>Lade …</p>
      ) : gruppen.concat(
            // Gruppen, die nur durch eigene Kostenarten existieren, nicht verlieren.
            [...new Set(arten.map(a => a.gruppe_key))]
              .filter(k => !gruppen.some(g => g.key === k))
              .map(k => ({ key: k, label: arten.find(a => a.gruppe_key === k)?.gruppe || k }))
          ).map(g => {
        const zeilen = arten.filter(a => a.gruppe_key === g.key);
        if (!zeilen.length) return null;
        return (
        <div key={g.key} style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`,
          borderRadius: 10, overflow: "hidden" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "9px 14px", borderBottom: `1px solid ${S.border}` }}>
            <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.06em",
              textTransform: "uppercase", color: S.textDim }}>{g.label}</span>
            <span style={{ fontSize: 11.5, color: (summe.gruppen?.[g.key] || 0) > 0
              ? S.textMain : S.textDim }}>
              {eur(summe.gruppen?.[g.key] || 0)} / Monat
            </span>
          </div>

          {zeilen.map((a, i) => {
            const eintraege = a.eintraege || [];
            const aktuellIdx = eintraege.length - 1;   // jüngster Eintrag = Hauptzeile
            const aktuell = eintraege[aktuellIdx];
            const istOffen = !!offen[a.key];
            return (
              <div key={a.key} style={{ borderTop: i ? `1px solid ${S.border}` : "none" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10,
                  padding: "9px 14px" }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12.5, color: S.textMain,
                      display: "flex", alignItems: "center", gap: 6 }}>
                      {a.label}
                      {a.custom && (
                        <span style={{ fontSize: 9.5, color: S.textDim, border: `1px solid ${S.border}`,
                          borderRadius: 3, padding: "1px 4px" }}>eigene</span>
                      )}
                      {speichert === a.key && (
                        <Loader2 size={11} className="animate-spin" style={{ color: S.textDim }} />
                      )}
                      {eintraege.some(unvollstaendig) && (
                        <span style={{ fontSize: 10, color: "#e8913a" }}>
                          {unvollstaendig(aktuell) && !aktuell?.betrag && aktuell?.gueltig_ab
                            ? "Betrag fehlt – noch nicht gespeichert"
                            : "unvollständig – noch nicht gespeichert"}
                        </span>
                      )}
                    </div>
                    {a.hinweis && (
                      <div style={{ fontSize: 11, color: S.textDim, marginTop: 2 }}>{a.hinweis}</div>
                    )}
                  </div>

                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: 10, color: S.textDim, marginBottom: 3 }}>gültig ab</div>
                    <input type="date" disabled={!canEdit}
                      value={aktuell?.gueltig_ab || ""}
                      onChange={e => aktuell
                        ? feldAendern(a, aktuellIdx, "gueltig_ab", e.target.value)
                        // Ein leerer Wert (halb getipptes Datum) legt noch keine Zeile an.
                        : e.target.value && aendern(a.key, [{ gueltig_ab: e.target.value, betrag: "" }])}
                      onBlur={() => speichern(a.key)}
                      style={{ ...inp, width: 140 }} />
                  </div>

                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: 10, color: S.textDim, marginBottom: 3 }}>€ / Monat</div>
                    <input type="number" step="any" min="0" disabled={!canEdit}
                      placeholder="–"
                      value={aktuell?.betrag ?? ""}
                      onChange={e => aktuell
                        ? feldAendern(a, aktuellIdx, "betrag", e.target.value)
                        : aendern(a.key, [{ gueltig_ab: jahresbeginnISO(), betrag: e.target.value }])}
                      onBlur={() => speichern(a.key)}
                      style={{ ...inp, width: 110, textAlign: "right" }} />
                  </div>

                  <button onClick={() => setOffen(p => ({ ...p, [a.key]: !istOffen }))}
                    title="Zeitliche Entwicklung"
                    style={{ display: "flex", alignItems: "center", gap: 3, background: "none",
                      border: "none", padding: 4, cursor: "pointer", width: 74,
                      color: eintraege.length > 1 ? S.accent : S.textDim, fontSize: 10.5 }}>
                    {istOffen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                    {eintraege.length > 1 ? `${eintraege.length} Zeiträume` : "Verlauf"}
                  </button>

                  <button onClick={() => leeren(a.key)}
                    disabled={!canEdit || (!a.custom && eintraege.length === 0)}
                    title={a.custom ? "Kostenart löschen" : "Werte entfernen"}
                    style={{ background: "none", border: "none", padding: 4,
                      color: (!a.custom && eintraege.length === 0) ? "transparent" : S.textDim,
                      cursor: (!a.custom && eintraege.length === 0) ? "default" : "pointer" }}>
                    <Trash2 size={13} />
                  </button>
                </div>

                {istOffen && (
                  <div style={{ padding: "4px 14px 12px 14px", backgroundColor: S.bgMain }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10.5,
                      color: S.textDim, padding: "6px 0" }}>
                      <History size={11} /> Jede Änderung ist ein eigener Zeitraum –
                      der jeweils jüngste gilt ab seinem Datum.
                    </div>
                    {eintraege.length === 0 && (
                      <div style={{ fontSize: 11.5, color: S.textDim, padding: "4px 0" }}>
                        Noch nichts erfasst.
                      </div>
                    )}
                    {eintraege.map((e, idx) => (
                      <div key={idx} style={{ display: "flex", alignItems: "center", gap: 8,
                        padding: "3px 0" }}>
                        <span style={{ fontSize: 11, color: S.textDim, width: 52 }}>ab</span>
                        <input type="date" disabled={!canEdit} value={e.gueltig_ab || ""}
                          onChange={ev => feldAendern(a, idx, "gueltig_ab", ev.target.value)}
                          onBlur={() => speichern(a.key)}
                          style={{ ...inp, width: 140 }} />
                        <input type="number" step="any" min="0" disabled={!canEdit}
                          value={e.betrag ?? ""}
                          onChange={ev => feldAendern(a, idx, "betrag", ev.target.value)}
                          onBlur={() => speichern(a.key)}
                          style={{ ...inp, width: 110, textAlign: "right" }} />
                        <span style={{ fontSize: 11, color: S.textDim }}>€ / Monat</span>
                        {idx === eintraege.length - 1 && (
                          <span style={{ fontSize: 10, color: S.accent }}>aktuell</span>
                        )}
                        <button onClick={() => zeitraumEntfernen(a, idx)} disabled={!canEdit}
                          style={{ background: "none", border: "none", padding: 3,
                            color: S.textDim, cursor: "pointer" }}>
                          <Trash2 size={12} />
                        </button>
                      </div>
                    ))}
                    {canEdit && (
                      <button onClick={() => zeitraumHinzufuegen(a)}
                        style={{ display: "flex", alignItems: "center", gap: 5, marginTop: 6,
                          background: "none", border: `1px dashed ${S.border}`, borderRadius: 5,
                          padding: "4px 9px", color: S.textDim, fontSize: 11, cursor: "pointer" }}>
                        <Plus size={11} /> Zeitraum hinzufügen
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
        );
      })}

      {/* ── Eigene Kostenart ── */}
      {!laden && canEdit && (
        neu ? (
          <div style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`,
            borderRadius: 10, padding: 14, display: "flex", alignItems: "flex-end", gap: 10 }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 10.5, color: S.textDim, marginBottom: 4 }}>Bezeichnung</div>
              <input autoFocus type="text" value={neu.label}
                placeholder="z. B. Lagermiete Außenstandort"
                onChange={e => setNeu({ ...neu, label: e.target.value })}
                onKeyDown={e => e.key === "Enter" && eigeneAnlegen()}
                style={{ ...inp, width: "100%" }} />
            </div>
            <div>
              <div style={{ fontSize: 10.5, color: S.textDim, marginBottom: 4 }}>Gruppe</div>
              <select value={neu.gruppe_key}
                onChange={e => setNeu({ ...neu, gruppe_key: e.target.value })}
                style={{ ...inp, width: 200 }}>
                {gruppen.map(g => <option key={g.key} value={g.key}>{g.label}</option>)}
              </select>
            </div>
            <button onClick={eigeneAnlegen}
              style={{ padding: "7px 12px", backgroundColor: S.accent, color: "#1a1a1a",
                border: "none", borderRadius: 6, fontSize: 12, fontWeight: 600,
                cursor: "pointer" }}>Anlegen</button>
            <button onClick={() => setNeu(null)}
              style={{ padding: "7px 12px", backgroundColor: S.bgEl, color: S.textMain,
                border: `1px solid ${S.border}`, borderRadius: 6, fontSize: 12,
                cursor: "pointer" }}>Abbrechen</button>
          </div>
        ) : (
          <button onClick={() => setNeu({ label: "", gruppe_key: gruppen[0]?.key || "sonstiges" })}
            style={{ display: "flex", alignItems: "center", gap: 6, alignSelf: "flex-start",
              background: "none", border: `1px dashed ${S.border}`, borderRadius: 6,
              padding: "8px 13px", color: S.textDim, fontSize: 12, cursor: "pointer" }}>
            <Plus size={13} /> Eigene Kostenart hinzufügen
          </button>
        )
      )}
    </div>
  );
}
