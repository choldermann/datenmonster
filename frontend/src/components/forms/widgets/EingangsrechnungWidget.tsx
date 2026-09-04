import { useState, useEffect, useRef, useCallback } from "react";
import {
  Upload, Loader2, CheckCircle2, AlertTriangle, XCircle, Search, FileText,
} from "lucide-react";
import api from "../../../api/client";

const S = {
  bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)", border: "var(--border)",
  textMain: "var(--text-main)", textBright: "var(--text-bright)", textDim: "var(--text-dim)",
  accent: "var(--accent)",
};

const STATUS = {
  matched:         { label: "Zugeordnet",       color: "#34d399" },
  no_order:        { label: "Ohne Bestellung",  color: "#60a5fa" },
  platzhalter:     { label: "Platzhalter",      color: "#a78bfa" },
  ambiguous:       { label: "Mehrdeutig",       color: "#fbbf24" },
  unknown_article: { label: "Artikel unbekannt", color: "#f97316" },
  unklar:          { label: "Unklar",           color: "#f87171" },
};

function Badge({ status }) {
  const m = STATUS[status] || { label: status, color: S.textDim };
  return (
    <span style={{ fontSize: 10, fontWeight: 700, color: m.color,
      background: m.color + "22", border: `1px solid ${m.color}55`,
      borderRadius: 5, padding: "2px 7px", whiteSpace: "nowrap" }}>{m.label}</span>
  );
}

/** Artikelsuche fürs manuelle Zuordnen. */
function ArtikelSuche({ connectionId, onPick }) {
  const [q, setQ] = useState("");
  const [res, setRes] = useState([]);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (q.trim().length < 2) { setRes([]); return; }
    const t = setTimeout(async () => {
      try {
        const { data } = await api.get("/api/eingangsrechnung/artikel-suche",
          { params: { connection_id: connectionId, q } });
        setRes(data.results || []); setOpen(true);
      } catch { /* still */ }
    }, 300);
    return () => clearTimeout(t);
  }, [q, connectionId]);
  return (
    <div style={{ position: "relative", minWidth: 220 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 5, background: S.bgEl,
        border: `1px solid ${S.border}`, borderRadius: 6, padding: "3px 7px" }}>
        <Search size={12} color={S.textDim} />
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="Artikel suchen…"
          style={{ background: "transparent", border: "none", outline: "none",
            color: S.textMain, fontSize: 11, width: "100%" }} />
      </div>
      {open && res.length > 0 && (
        <div style={{ position: "absolute", zIndex: 20, top: "100%", left: 0, right: 0,
          background: S.bgCard, border: `1px solid ${S.border}`, borderRadius: 6, marginTop: 3,
          maxHeight: 200, overflowY: "auto", boxShadow: "0 8px 24px rgba(0,0,0,0.4)" }}>
          {res.map(a => (
            <button key={a.kArtikel} onClick={() => { onPick(a); setOpen(false); setQ(""); }}
              style={{ display: "block", width: "100%", textAlign: "left", padding: "6px 9px",
                background: "transparent", border: "none", borderBottom: `1px solid ${S.border}`,
                color: S.textMain, fontSize: 11, cursor: "pointer" }}
              onMouseEnter={e => e.currentTarget.style.background = S.bgEl}
              onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
              <b>{a.cArtNr}</b> {a.cName ? <span style={{ color: S.textDim }}>· {a.cName}</span> : null}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** Ein Eingabefeld des Anlege-Modals.
 *
 * Bewusst AUSSERHALB des Modals definiert: eine im Rumpf der Elternkomponente
 * erzeugte Komponente ist bei jedem Rendern ein neuer Typ, React wirft das alte
 * <input> dann weg und baut ein neues – der Fokus ginge nach jedem Tastendruck
 * verloren.
 */
function ModalFeld({ k, label, wert, onChange, breit, ...rest }) {
  return (
    <div style={{ gridColumn: breit ? "span 2" : "span 1" }}>
      <label style={{ display: "block", fontSize: 10, color: S.textDim, marginBottom: 3 }}>
        {label}</label>
      <input value={wert} onChange={onChange} {...rest}
        style={{ width: "100%", background: S.bgEl, color: S.textMain,
          border: `1px solid ${S.border}`, borderRadius: 6, fontSize: 12,
          padding: "5px 8px" }} />
    </div>
  );
}

/** Artikel aus dem Beleg heraus neu anlegen.
 *
 * Warum hier und nicht in der Wawi: wer eine Rechnung bucht, will den Beleg
 * nicht verlassen, nur weil eine Zeile noch keinen Artikel hat. Alles, was der
 * Beleg schon weiß, ist vorbelegt – Name, Lieferanten-Artikelnummer, EK und,
 * wenn die Rechnung sie ausweist, Warennummer, Herkunftsland und Gewicht.
 *
 * Zweistufig wie jeder Schreibweg in die Wawi: geprüft wird laufend (schreibt
 * nichts), angelegt erst auf ausdrücklichen Klick. Das Backend prüft im Moment
 * des Schreibens noch einmal von vorn – die Artikelnummer könnte inzwischen
 * vergeben sein.
 */
function NeuerArtikelModal({ connectionId, position, lieferant, stammdaten, onFertig, onAbbruch }) {
  const liefNr = position?.cLieferantenArtNr || position?.cArtNr || "";
  const zoll = stammdaten?.[liefNr] || {};
  const [f, setF] = useState({
    cArtNr: liefNr,
    cName: position?.cName || "",
    cKurzBeschreibung: "",
    cBarcode: "",
    cHAN: "",
    cTaric: zoll.warennummer || "",
    cHerkunftsland: zoll.herkunftsland || "",
    fGewicht: zoll.gewichtKg ? String(zoll.gewichtKg).replace(".", ",") : "",
    fVKNetto: "",
    lagerAktiv: true,
    cLiefArtNr: liefNr,
    fEKNetto: position?.fEKNetto != null ? String(position.fEKNetto).replace(".", ",") : "",
  });
  const [pruefung, setPruefung] = useState(null);
  const [busy, setBusy] = useState(false);
  const [fehler, setFehler] = useState(null);

  const rumpf = useCallback(() => ({
    connection_id: connectionId, ...f,
    kLieferant: lieferant?.kLieferant || null,
    cLiefName: position?.cName || null,
  }), [connectionId, f, lieferant, position]);

  // Laufend prüfen, aber entspannt: der Anwender tippt, wir warten kurz ab.
  useEffect(() => {
    if (!f.cArtNr.trim() || !f.cName.trim()) { setPruefung(null); return; }
    const t = setTimeout(async () => {
      try {
        const { data } = await api.post("/api/stammdaten/artikel-pruefen", rumpf());
        setPruefung(data);
      } catch (e) { setPruefung(null); }
    }, 400);
    return () => clearTimeout(t);
  }, [rumpf, f.cArtNr, f.cName]);

  async function anlegen() {
    setBusy(true); setFehler(null);
    try {
      const { data } = await api.post("/api/stammdaten/artikel-anlegen",
        { ...rumpf(), bestaetigt: true });
      if (data.ok && data.kArtikel) onFertig(data);
      else { setPruefung(data); setFehler("Anlegen nicht möglich – bitte offene Punkte prüfen."); }
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
    } finally { setBusy(false); }
  }

  const set = (k) => (e) => setF({ ...f,
    [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  const Feld = (k, label, extra = {}) => (
    <ModalFeld k={k} label={label} wert={f[k]} onChange={set(k)} {...extra} />
  );

  return (
    <div onClick={onAbbruch} style={{ position: "fixed", inset: 0, zIndex: 100,
      background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center",
      justifyContent: "center", padding: 20 }}>
      <div onClick={e => e.stopPropagation()} style={{ background: S.bgCard,
        border: `1px solid ${S.border}`, borderRadius: 10, padding: 18,
        width: "min(680px, 100%)", maxHeight: "88vh", overflowY: "auto",
        boxShadow: "0 20px 60px rgba(0,0,0,0.5)" }}>
        <div style={{ color: S.textBright, fontWeight: 700, fontSize: 14, marginBottom: 3 }}>
          Artikel neu anlegen
        </div>
        <div style={{ color: S.textDim, fontSize: 11, marginBottom: 14 }}>
          Wird direkt in der Wawi angelegt. Vorbelegt ist, was auf der Rechnung steht.
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          {Feld("cArtNr", "Artikelnummer *")}
          {Feld("cName", "Artikelname *")}
          {Feld("cKurzBeschreibung", "Kurzbeschreibung", { breit: true })}
          {Feld("cBarcode", "EAN / GTIN", { placeholder: "8, 12, 13 oder 14 Ziffern" })}
          {Feld("cHAN", "Herstellernummer (HAN)")}
          {Feld("cTaric", "Warentarifnummer", { placeholder: "8 Ziffern" })}
          {Feld("cHerkunftsland", "Herkunftsland", { placeholder: "z. B. CN oder China" })}
          {Feld("fGewicht", "Gewicht", { placeholder: "z. B. 0,115 kg" })}
          {Feld("fVKNetto", "VK netto (optional)")}
        </div>

        <div style={{ marginTop: 12, paddingTop: 12, borderTop: `1px solid ${S.border}` }}>
          <div style={{ color: S.textMain, fontSize: 11, fontWeight: 600, marginBottom: 8 }}>
            Beim Lieferanten{lieferant?.cFirma ? ` · ${lieferant.cFirma}` : ""}
          </div>
          {lieferant?.kLieferant ? (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              {Feld("cLiefArtNr", "Bestellnummer beim Lieferanten")}
              {Feld("fEKNetto", "EK netto")}
            </div>
          ) : (
            <div style={{ color: S.textDim, fontSize: 11 }}>
              Zu diesem Beleg steht kein Lieferant fest – die Zuordnung wird nicht angelegt.
            </div>
          )}
        </div>

        <label style={{ display: "flex", alignItems: "center", gap: 7, marginTop: 12,
          color: S.textMain, fontSize: 11, cursor: "pointer" }}>
          <input type="checkbox" checked={f.lagerAktiv} onChange={set("lagerAktiv")} />
          Lagerbestand für diesen Artikel führen
        </label>

        {(pruefung?.fehler?.length > 0 || pruefung?.hinweise?.length > 0) && (
          <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 5 }}>
            {(pruefung.fehler || []).map((t, i) => (
              <div key={`f${i}`} style={{ display: "flex", gap: 6, fontSize: 11, color: "#f87171" }}>
                <XCircle size={13} style={{ flexShrink: 0, marginTop: 1 }} />{t}</div>
            ))}
            {(pruefung.hinweise || []).map((t, i) => (
              <div key={`h${i}`} style={{ display: "flex", gap: 6, fontSize: 11, color: "#fbbf24" }}>
                <AlertTriangle size={13} style={{ flexShrink: 0, marginTop: 1 }} />{t}</div>
            ))}
          </div>
        )}
        {fehler && (
          <div style={{ marginTop: 10, fontSize: 11, color: "#f87171" }}>{fehler}</div>
        )}

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
          <button onClick={onAbbruch} style={{ background: "none", border: `1px solid ${S.border}`,
            color: S.textMain, borderRadius: 7, padding: "7px 14px", fontSize: 12, cursor: "pointer" }}>
            Abbrechen</button>
          <button onClick={anlegen} disabled={busy || !pruefung?.ok}
            style={{ background: pruefung?.ok ? S.accent : S.bgEl, border: "none",
              color: pruefung?.ok ? "#0b0b0c" : S.textDim, borderRadius: 7,
              padding: "7px 14px", fontSize: 12, fontWeight: 700,
              cursor: busy || !pruefung?.ok ? "not-allowed" : "pointer",
              display: "flex", alignItems: "center", gap: 6 }}>
            {busy && <Loader2 size={13} className="animate-spin" />}
            In der Wawi anlegen</button>
        </div>
      </div>
    </div>
  );
}

export default function EingangsrechnungWidget({ widget }) {
  const connId = widget?.config?.connection_id ? Number(widget.config.connection_id) : null;
  const [kopf, setKopf] = useState(null);
  const [plan, setPlan] = useState(null);
  const [overrides, setOverrides] = useState({});
  const [merken, setMerken] = useState(true);
  const [loading, setLoading] = useState(false);
  const [writing, setWriting] = useState(false);
  const [written, setWritten] = useState(null);
  const [error, setError] = useState(null);
  // Was der Leser über den Beleg herausgefunden hat (erkannte Bestellung,
  // Zolldaten je Lieferanten-Artikelnummer). Wird nicht gebucht, nur zum
  // Vorbelegen beim Neuanlegen benutzt.
  const [befund, setBefund] = useState(null);
  const [neuFuer, setNeuFuer] = useState(null);   // Index der Zeile im Modal
  const fileRef = useRef(null);

  const num = (v) => (v == null ? 0 : Number(v));

  async function upload(file) {
    if (!file) return;
    setLoading(true); setError(null); setWritten(null); setOverrides({}); setBefund(null);
    try {
      const fd = new FormData();
      fd.append("connection_id", String(connId));
      fd.append("file", file);
      const { data } = await api.post("/api/eingangsrechnung/plan", fd);
      setKopf(data.kopf); setPlan(data.plan); setBefund(data.befund || null);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally { setLoading(false); }
  }

  const replan = useCallback(async (ov) => {
    if (!kopf) return;
    setLoading(true);
    try {
      const { data } = await api.post("/api/eingangsrechnung/replan",
        { connection_id: connId, kopf, overrides: ov });
      setPlan(data);
    } catch (e) { setError(e.response?.data?.detail || e.message); }
    finally { setLoading(false); }
  }, [kopf, connId]);

  function setOverride(zeile, patch) {
    const cur = overrides[zeile] || {};
    const next = { ...overrides, [zeile]: { ...cur, ...patch } };
    setOverrides(next); replan(next);
  }

  // Zusatzkosten einer Kostenart dieser Wawi zuordnen. Eigener Schlüssel, weil
  // die übrigen Overrides nach Positionsindex gehen – die Kostenarten hängen
  // aber an den Zusatzkostenzeilen, nicht an den Positionen.
  function setKostenart(index, kZusatzkosten) {
    const cur = overrides.zusatzkosten_arten || {};
    const arten = { ...cur };
    if (kZusatzkosten) arten[index] = Number(kZusatzkosten);
    else delete arten[index];
    const next = { ...overrides, zusatzkosten_arten: arten };
    setOverrides(next); replan(next);
  }

  async function freigeben() {
    setWriting(true); setError(null);
    try {
      // Lern-Zuordnungen sammeln: manuell gesetzte Artikel mit Lieferanten-ArtNr
      const learn = [];
      if (merken && plan?.lieferant?.kLieferant) {
        Object.entries(overrides).forEach(([z, ov]) => {
          const pos = kopf.positionen[Number(z)];
          if (ov.kArtikel && pos?.cLieferantenArtNr) {
            learn.push({ kLieferant: plan.lieferant.kLieferant,
              cLiefArtNr: pos.cLieferantenArtNr, kArtikel: ov.kArtikel });
          }
        });
      }
      const { data } = await api.post("/api/eingangsrechnung/write",
        { connection_id: connId, kopf, overrides, learn });
      if (data.ok) setWritten(data);
      else { setPlan(data); setError("Freigabe nicht möglich – bitte offene Punkte prüfen."); }
    } catch (e) { setError(e.response?.data?.detail || e.message); }
    finally { setWriting(false); }
  }

  if (!connId) return (
    <div style={{ padding: 16, color: "#e0a070", fontSize: 12 }}>
      <AlertTriangle size={13} style={{ verticalAlign: -2 }} /> Bitte im Formular-Editor
      eine JTL-Verbindung für dieses Widget wählen.
    </div>
  );

  // Erfolgsansicht
  if (written) return (
    <div style={{ padding: 20, textAlign: "center" }}>
      <CheckCircle2 size={34} color="#34d399" />
      <div style={{ fontSize: 15, fontWeight: 700, color: S.textBright, marginTop: 8 }}>
        Eingangsrechnung verbucht</div>
      <div style={{ fontSize: 12, color: S.textDim, marginTop: 4 }}>
        kEingangsrechnung {written.kEingangsrechnung} · Nr. {written.kopf_werte?.cEigeneRechnungsnummer}</div>
      {written.learned?.filter(l => l.created).length > 0 && (
        <div style={{ fontSize: 11, color: S.textDim, marginTop: 6 }}>
          {written.learned.filter(l => l.created).length} neue Artikel-Zuordnung(en) gemerkt</div>
      )}
      <button onClick={() => { setWritten(null); setKopf(null); setPlan(null); }}
        style={{ marginTop: 14, padding: "7px 16px", background: S.accent, color: "#0b1120",
          border: "none", borderRadius: 7, fontSize: 12, fontWeight: 700, cursor: "pointer" }}>
        Nächste Rechnung</button>
    </div>
  );

  // Upload-Ansicht
  if (!plan) return (
    <div style={{ padding: 20 }}>
      <div onClick={() => fileRef.current?.click()}
        style={{ border: `2px dashed ${S.border}`, borderRadius: 10, padding: "30px 20px",
          textAlign: "center", cursor: "pointer", color: S.textDim }}>
        {loading ? <Loader2 size={26} className="animate-spin" /> : <Upload size={26} />}
        <div style={{ marginTop: 8, fontSize: 13, color: S.textMain }}>
          E-Rechnung hochladen (ZUGFeRD-PDF oder XRechnung-XML)</div>
        <div style={{ fontSize: 11, marginTop: 3 }}>Klicken oder Datei hierher ziehen</div>
      </div>
      <input ref={fileRef} type="file" accept=".pdf,.xml" style={{ display: "none" }}
        onChange={e => upload(e.target.files?.[0])} />
      {error && <div style={{ marginTop: 10, color: "#e07070", fontSize: 12 }}>{error}</div>}
    </div>
  );

  const td = { padding: "6px 8px", fontSize: 11, color: S.textMain, borderBottom: `1px solid ${S.border}`, verticalAlign: "top" };
  const summen = plan.summen || {};

  // Review-Ansicht
  return (
    <div style={{ padding: 14 }}>
      {/* Kopf */}
      <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 8,
        background: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 8, padding: "10px 12px" }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, color: S.textBright }}>
            <FileText size={13} style={{ verticalAlign: -2 }} /> {plan.lieferant?.cFirma || kopf.lieferantName || "—"}</div>
          <div style={{ fontSize: 11, color: S.textDim, marginTop: 2 }}>
            Rechnung {kopf.cFremdbelegnummer} · {kopf.dBelegdatum?.slice(0, 10)}
            {plan.lieferant?._match ? ` · Lieferant via ${plan.lieferant._match}` : ""}</div>
        </div>
        {summen.rechnung_brutto != null && (
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 15, fontWeight: 700, color: S.textBright }}>
              {num(summen.rechnung_brutto).toFixed(2)} €</div>
            <div style={{ fontSize: 10, color: plan.reconciliation_ok ? "#34d399" : "#f87171" }}>
              {plan.reconciliation_ok ? "✓ Summe stimmt" : `✗ Δ ${num(summen.differenz).toFixed(2)}`}</div>
          </div>
        )}
      </div>

      {/* Positionen */}
      <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 12 }}>
        <thead>
          <tr style={{ background: S.bgEl }}>
            {["Artikel / Bezeichnung", "Menge", "EK", "Status", "Zuordnung"].map(h => (
              <th key={h} style={{ padding: "6px 8px", fontSize: 10, textAlign: "left",
                color: S.textDim, fontWeight: 600, borderBottom: `1px solid ${S.border}` }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {kopf.positionen.map((src, i) => {
            const p = plan.positionen.find(x => x._zeile === i);
            const ov = overrides[i] || {};
            if (!p) {   // als Zusatzkosten umklassifiziert
              return (
                <tr key={i} style={{ opacity: 0.7 }}>
                  <td style={td}>{src.cName}</td>
                  <td style={td}>{num(src.fMenge)}</td>
                  <td style={td}>{num(src.fEKNetto).toFixed(2)}</td>
                  <td style={td}><Badge status="no_order" /></td>
                  <td style={td}>
                    → Zusatzkosten ·{" "}
                    <button onClick={() => setOverride(i, { als_zusatzkosten: false })}
                      style={{ background: "none", border: "none", color: S.accent, cursor: "pointer", fontSize: 11 }}>
                      rückgängig</button>
                  </td>
                </tr>
              );
            }
            const needsFix = ["unknown_article", "ambiguous", "unklar"].includes(p.status);
            return (
              <tr key={i}>
                <td style={td}>
                  <div style={{ color: S.textBright }}>{p.cName}</div>
                  <div style={{ color: S.textDim, fontSize: 10 }}>
                    {p.cArtNr ? `ArtNr ${p.cArtNr}` : "keine ArtNr"}
                    {p.cLieferantenArtNr ? ` · Lief ${p.cLieferantenArtNr}` : ""}
                    {p.kArtikel ? ` · kArtikel ${p.kArtikel}` : ""}</div>
                </td>
                <td style={td}>{num(p.fMenge)}</td>
                <td style={td}>{num(p.fEKNetto).toFixed(2)}</td>
                <td style={td}><Badge status={p.status} /></td>
                <td style={{ ...td, minWidth: 240 }}>
                  {needsFix && (
                    <>
                      <ArtikelSuche connectionId={connId}
                        onPick={a => setOverride(i, { kArtikel: a.kArtikel })} />
                      <button onClick={() => setNeuFuer(i)}
                        style={{ marginTop: 4, background: "none", border: "none",
                          color: S.accent, cursor: "pointer", fontSize: 10,
                          textDecoration: "underline", padding: 0 }}>
                        Artikel neu anlegen</button>
                    </>
                  )}
                  {(p._kandidaten?.length > 1) && (
                    <select value={ov.kLieferantenBestellungPos || p.kLieferantenBestellungPos || ""}
                      onChange={e => {
                        const k = p._kandidaten.find(c => String(c.kPos) === e.target.value);
                        if (k) setOverride(i, { kLieferantenbestellung: k.kBest, kLieferantenBestellungPos: k.kPos });
                      }}
                      style={{ marginTop: 4, width: "100%", background: S.bgEl, color: S.textMain,
                        border: `1px solid ${S.border}`, borderRadius: 6, fontSize: 11, padding: "3px 6px" }}>
                      {p._kandidaten.map(c => (
                        <option key={c.kPos} value={c.kPos}>
                          {c.bestellnr} · EK {num(c.ek).toFixed(2)} · offen {num(c.offen)} (Score {Math.round(c.score)})
                        </option>
                      ))}
                    </select>
                  )}
                  {p.kLieferantenbestellung && !needsFix && (p._kandidaten?.length || 0) <= 1 && (
                    <span style={{ color: S.textDim, fontSize: 10 }}>Bestellung ✓</span>
                  )}
                  <div style={{ marginTop: 4 }}>
                    <button onClick={() => setOverride(i, { als_zusatzkosten: true })}
                      style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer",
                        fontSize: 10, textDecoration: "underline" }}>
                      als Zusatzkosten</button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {/* Zusatzkosten – je Zeile die Kostenart dieser Wawi zuordnen.
          Die Kostenarten-IDs sind installationsspezifisch, deshalb wird nichts
          geraten: erkennt der Server den Namen nicht, muss hier gewählt werden. */}
      {plan.zusatzkosten?.length > 0 && (
        <div style={{ marginTop: 10, fontSize: 11 }}>
          <b style={{ color: S.textMain }}>Zusatzkosten:</b>
          <table style={{ width: "100%", marginTop: 4, borderCollapse: "collapse" }}>
            <tbody>
              {plan.zusatzkosten.map((z, k) => (
                <tr key={k}>
                  <td style={{ padding: "3px 6px 3px 0", color: S.textDim }}>
                    {z.ist_zuschlag ? "+" : "−"}{z.cName}
                  </td>
                  <td style={{ padding: "3px 6px", color: S.textMain, textAlign: "right",
                               whiteSpace: "nowrap" }}>
                    {num(z.betrag).toFixed(2)} €
                    <span style={{ color: S.textDim }}> ({num(z.fMwSt).toFixed(0)} %)</span>
                  </td>
                  <td style={{ padding: "3px 0" }}>
                    <select value={z.kZusatzkosten || ""}
                      onChange={e => setKostenart(k, e.target.value)}
                      style={{ background: S.bgEl, color: S.textMain, borderRadius: 6,
                        fontSize: 11, padding: "3px 6px",
                        border: `1px solid ${z.kZusatzkosten ? S.border : "#e0a070"}` }}>
                      <option value="">— Kostenart wählen —</option>
                      {(plan.kostenarten || []).map(a => (
                        <option key={a.kZusatzkosten} value={a.kZusatzkosten}>{a.cName}</option>
                      ))}
                    </select>
                    {z.kostenart_quelle && (
                      <span style={{ marginLeft: 6, color: S.textDim }}>{z.kostenart_quelle}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {plan.zusatzkosten_zeilen?.length > 0 && (
            <div style={{ marginTop: 4, color: S.textDim }}>
              wird mengenproportional auf die Artikelzeilen verteilt
              {" – "}
              {plan.zusatzkosten_zeilen
                .filter(zk => num(zk.dWert) !== 0)
                .map(zk => num(zk.dWert).toFixed(2)).join(" · ")} €
            </div>
          )}
        </div>
      )}

      {/* Warnungen */}
      {plan.warnings?.length > 0 && (
        <div style={{ marginTop: 10 }}>
          {plan.warnings.map((w, k) => (
            <div key={k} style={{ fontSize: 11, color: "#e0a070", display: "flex", gap: 6 }}>
              <AlertTriangle size={12} style={{ flexShrink: 0, marginTop: 1 }} /> {w}</div>
          ))}
        </div>
      )}
      {plan.errors?.length > 0 && (
        <div style={{ marginTop: 8 }}>
          {plan.errors.map((w, k) => (
            <div key={k} style={{ fontSize: 11, color: "#e07070", display: "flex", gap: 6 }}>
              <XCircle size={12} style={{ flexShrink: 0, marginTop: 1 }} /> {w}</div>
          ))}
        </div>
      )}

      {/* Aktionen */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
        marginTop: 14, gap: 10, flexWrap: "wrap" }}>
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: S.textMain, cursor: "pointer" }}>
          <input type="checkbox" checked={merken} onChange={e => setMerken(e.target.checked)}
            style={{ width: 13, height: 13 }} />
          Manuelle Artikel-Zuordnungen für die Zukunft merken
        </label>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => { setKopf(null); setPlan(null); setOverrides({}); }}
            style={{ padding: "8px 14px", background: "transparent", color: S.textDim,
              border: `1px solid ${S.border}`, borderRadius: 7, fontSize: 12, cursor: "pointer" }}>
            Abbrechen</button>
          <button onClick={freigeben} disabled={!plan.ok || writing || loading}
            style={{ padding: "8px 18px", background: plan.ok ? "#34d399" : S.bgEl,
              color: plan.ok ? "#0b1120" : S.textDim, border: "none", borderRadius: 7,
              fontSize: 12, fontWeight: 700, cursor: plan.ok ? "pointer" : "not-allowed",
              display: "flex", alignItems: "center", gap: 6 }}>
            {writing ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle2 size={13} />}
            Freigeben & verbuchen</button>
        </div>
      </div>

      {neuFuer != null && (
        <NeuerArtikelModal
          connectionId={connId}
          position={kopf.positionen[neuFuer]}
          lieferant={plan.lieferant}
          stammdaten={befund?.stammdaten}
          onAbbruch={() => setNeuFuer(null)}
          onFertig={(res) => {
            // Der Artikel steht jetzt in der Wawi. Ihn der Zeile zuzuordnen ist
            // derselbe Vorgang wie eine Zuordnung von Hand – also derselbe Weg,
            // damit der Plan neu gerechnet wird.
            const zeile = neuFuer;
            setNeuFuer(null);
            setOverride(zeile, { kArtikel: res.kArtikel });
          }} />
      )}
    </div>
  );
}
