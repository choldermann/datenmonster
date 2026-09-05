import { Fragment, useState, useEffect, useMemo } from "react";
import { ChevronLeft, ChevronDown, ChevronRight, Globe, GlobeLock, Loader2,
  AlertTriangle, Sparkles, Barcode } from "lucide-react";
import api, { fehlerText } from "../../../api/client";
import { S } from "../../dashboard/constants";
import { alsText } from "../../../utils/html";
import AiActionModal from "../AiActionModal";
import StammdatenPruefung from "./StammdatenPruefung";

const ACCENT = "#fce499";
const GRUEN = "#6ee7b7";
const ROT = "#e07070";

const fehltChip = () => (
  <span style={{ display: "inline-flex", alignItems: "center", gap: 4, color: ROT,
    fontSize: 11, fontWeight: 600 }}>
    <AlertTriangle size={11} /> fehlt
  </span>
);

const zahl = (v) => (typeof v === "number" ? v : parseFloat(v) || 0)
  .toLocaleString("de-DE", { maximumFractionDigits: 0 });

const Abschnitt = ({ titel, text }) => (
  <div>
    <p style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: "0.05em",
      textTransform: "uppercase", color: S.textDim, margin: "0 0 3px" }}>{titel}</p>
    <p style={{ fontSize: 12, lineHeight: 1.6, color: S.textMain, margin: 0,
      whiteSpace: "pre-wrap", maxHeight: 220, overflowY: "auto" }}>{text}</p>
  </div>
);

/** Der in der Wawi hinterlegte Text. Die Kurzbeschreibung steht oben, weil dort
 *  meist die echten technischen Daten stehen. */
function HinterlegterText({ artikel }) {
  const kurz = alsText(artikel.Kurzbeschreibung);
  const lang = alsText(artikel.Beschreibung);
  if (!kurz && !lang) {
    return (
      <p style={{ fontSize: 12, color: ROT, margin: 0 }}>
        Kein Text hinterlegt — hier lohnt der Beschreibungsvorschlag.
      </p>
    );
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {kurz && <Abschnitt titel="Kurzbeschreibung" text={kurz} />}
      {lang && <Abschnitt titel="Beschreibung" text={lang} />}
      {(artikel.Zeichen || 0) > 1200 && (
        <p style={{ fontSize: 10.5, color: S.textDim, margin: 0 }}>
          Anzeige nach 1.200 Zeichen gekürzt — vollständig steht der Text in der Wawi.
        </p>
      )}
    </div>
  );
}

/**
 * Einstieg in den Artikelstamm über den Hersteller:
 *   Hersteller (mit Pflegezustand seiner Produktseiten)
 *     → Artikel des Herstellers (Lücken markiert)
 *       → Beschreibungsvorschlag
 *
 * Die Zuordnung Herstellername → Adapter kommt vom Server (/api/research/supported),
 * damit die Registry die einzige Wahrheit bleibt.
 */
export default function HerstellerNavigator({ widget, result }) {
  const cfg = widget.config?.hersteller_navigator || {};
  const [status, setStatus] = useState({});
  const [gewaehlt, setGewaehlt] = useState(null);   // Hersteller-Zeile
  const [artikel, setArtikel] = useState([]);
  const [laedt, setLaedt] = useState(false);
  const [fehler, setFehler] = useState("");
  const [aiZeile, setAiZeile] = useState(null);
  const [textOffen, setTextOffen] = useState(null);   // kArtikel des aufgeklappten Textes

  const zeilen = result?.rows || [];

  useEffect(() => {
    const namen = zeilen.map(r => r.Hersteller).filter(Boolean);
    if (!namen.length) return;
    api.post("/api/research/supported", { namen })
      .then(r => setStatus(r.data || {}))
      .catch(() => setStatus({}));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zeilen.length]);

  const oeffne = async (h) => {
    setGewaehlt(h); setArtikel([]); setFehler(""); setLaedt(true); setTextOffen(null);
    try {
      const { data } = await api.post("/api/forms/drilldown", {
        mapping_id: cfg.artikel_mapping_id,
        params: { kHersteller: h.kHersteller },
        max_rows: 500,          // Hersteller mit vielen Artikeln nicht abschneiden
      });
      setArtikel(data.rows || []);
    } catch (e) {
      setFehler(fehlerText(e));
    } finally { setLaedt(false); }
  };

  const sortiert = useMemo(() => [...zeilen].sort(
    (a, b) => (b.DuerftigerText || 0) - (a.DuerftigerText || 0)), [zeilen]);

  // Summen über alle Hersteller – für den Intrastat-Hinweis.
  const summe = useMemo(() => zeilen.reduce((s, r) => ({
    OhneTaric:    s.OhneTaric    + (r.OhneTaric || 0),
    OhneHerkunft: s.OhneHerkunft + (r.OhneHerkunft || 0),
    OhneGewicht:  s.OhneGewicht  + (r.OhneGewicht || 0),
    Auslandsartikel: s.Auslandsartikel + (r.Auslandsartikel || 0),
  }), { OhneTaric: 0, OhneHerkunft: 0, OhneGewicht: 0, Auslandsartikel: 0 }), [zeilen]);
  const auslandsartikel = summe.Auslandsartikel;

  const th = { textAlign: "left", padding: "8px 10px", fontSize: 10, fontWeight: 700,
    color: S.textDim, textTransform: "uppercase", letterSpacing: "0.05em",
    borderBottom: `1px solid ${S.border}`, whiteSpace: "nowrap" };
  const td = { padding: "8px 10px", fontSize: 12, color: S.textMain,
    borderBottom: `1px solid ${S.border}` };
  const num = { ...td, textAlign: "right", whiteSpace: "nowrap" };

  // ── Ebene 2: Artikel eines Herstellers ──────────────────────────────────
  if (gewaehlt) {
    const st = status[gewaehlt.Hersteller] || {};
    return (
      <div style={{ padding: 14 }}>
        <button onClick={() => { setGewaehlt(null); setArtikel([]); }}
          style={{ display: "flex", alignItems: "center", gap: 5, background: "none",
            border: "none", color: S.textDim, cursor: "pointer", fontSize: 12, marginBottom: 10 }}>
          <ChevronLeft size={14} /> Alle Hersteller
        </button>

        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
          <p style={{ fontSize: 15, fontWeight: 700, color: S.textBright, margin: 0 }}>
            {gewaehlt.Hersteller}
          </p>
          {st.auswertbar
            ? <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11,
                color: GRUEN }}><Globe size={12} /> Produktseiten auswertbar</span>
            : <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11,
                color: S.textDim }}><GlobeLock size={12} /> keine auswertbaren Produktseiten</span>}
        </div>
        <p style={{ fontSize: 11, color: S.textDim, margin: "0 0 12px" }}>
          {laedt ? "Artikel werden geladen…"
            : `${artikel.length === 500 ? "die ersten 500" : artikel.length} Artikel `
              + "· Klick auf die Zeile öffnet den Beschreibungsvorschlag, "
              + "Klick auf die Spalte „Text“ zeigt den hinterlegten Text"}
        </p>

        {fehler && <p style={{ fontSize: 12, color: ROT }}>{fehler}</p>}

        <div style={{ overflowX: "auto", maxHeight: 460, overflowY: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr>
              {["Artikelnr.", "Artikel", "EAN", "Hersteller-Nr.", "Warennr.", "Herkunft", "Gewicht",
                "Text", "Bestand"].map(h =>
                <th key={h} style={th}>{h}</th>)}
            </tr></thead>
            <tbody>
              {artikel.map(a => {
                const offen = textOffen === a.kArtikel;
                const ohneEan = !String(a.EAN || "").trim();
                const ohneHan = !String(a.HAN || "").trim();
                const ohneWn = !String(a.Warennummer || "").trim();
                const ohneHk = !String(a.Herkunftsland || "").trim();
                const ohneGew = !(Number(a.Gewicht) > 0);
                const duenn = (a.Zeichen || 0) < 120;
                return (
                  <Fragment key={a.kArtikel}>
                  <tr onClick={() => setAiZeile(a)}
                    style={{ cursor: "pointer" }}
                    onMouseEnter={e => e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.03)"}
                    onMouseLeave={e => e.currentTarget.style.backgroundColor = "transparent"}>
                    <td style={{ ...td, whiteSpace: "nowrap" }}>{a.ArtNr}</td>
                    <td style={td}>{a.Artikel}</td>
                    <td style={td}>
                      {ohneEan
                        ? <span style={{ display: "inline-flex", alignItems: "center", gap: 4,
                            color: ROT, fontSize: 11, fontWeight: 600 }}>
                            <AlertTriangle size={11} /> fehlt</span>
                        : <code style={{ fontSize: 11.5, color: S.textDim }}>{a.EAN}</code>}
                    </td>
                    <td style={td}>
                      {ohneHan
                        ? <span style={{ display: "inline-flex", alignItems: "center", gap: 4,
                            color: ROT, fontSize: 11, fontWeight: 600 }}>
                            <AlertTriangle size={11} /> fehlt</span>
                        : <span style={{ fontSize: 11.5, color: S.textDim }}>{a.HAN}</span>}
                    </td>
                    <td style={td}>
                      {ohneWn ? fehltChip() : <span style={{ fontSize: 11.5, color: S.textDim }}>{a.Warennummer}</span>}
                    </td>
                    <td style={td}>
                      {ohneHk ? fehltChip() : <span style={{ fontSize: 11.5, color: S.textDim }}>{a.Herkunftsland}</span>}
                    </td>
                    <td style={{ ...num, color: ohneGew ? ROT : S.textDim }}>
                      {ohneGew ? "fehlt" : `${Number(a.Gewicht).toLocaleString("de-DE",
                        { maximumFractionDigits: 3 })} kg`}
                    </td>
                    <td style={{ ...num, padding: 0, color: duenn ? ROT : S.textDim }}
                      title="hinterlegten Text anzeigen"
                      onClick={e => { e.stopPropagation(); setTextOffen(offen ? null : a.kArtikel); }}>
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 3,
                        padding: "8px 10px" }}>
                        {offen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                        {a.Zeichen === 0 ? "leer" : `${zahl(a.Zeichen)} Z.`}
                      </span>
                    </td>
                    <td style={num}>{zahl(a.Bestand)}</td>
                  </tr>
                  {offen && (
                    <tr>
                      <td colSpan={9} style={{ ...td, padding: "10px 14px 14px",
                        backgroundColor: "rgba(255,255,255,0.02)" }}>
                        <HinterlegterText artikel={a} />
                      </td>
                    </tr>
                  )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Sammelprüfung des ganzen Herstellers. Auch ohne Adapter sinnvoll: die
            Ableitung aus dem eigenen Stamm braucht keine Produktseite. */}
        {artikel.length > 0 && (
          <StammdatenPruefung hersteller={gewaehlt.Hersteller} artikel={artikel}
            mappingId={cfg.artikel_mapping_id} auswertbar={!!st.auswertbar} />
        )}

        {aiZeile && (
          <AiActionModal
            kind="article_description"
            label={aiZeile.Artikel}
            title="Artikelbeschreibung – KI-Vorschlag"
            factsMapping={cfg.fakten_mapping_id}
            keyParam="kArtikel"
            keyValue={aiZeile.kArtikel}
            manual
            buttonLabel="Beschreibung erzeugen"
            onClose={() => setAiZeile(null)}
          />
        )}
      </div>
    );
  }

  // ── Ebene 1: Hersteller ─────────────────────────────────────────────────
  return (
    <div style={{ padding: 14 }}>
      <p style={{ fontSize: 11.5, color: S.textDim, margin: "0 0 12px", lineHeight: 1.55 }}>
        Wo lohnt die Pflege zuerst? Die Spalte <strong style={{ color: S.textBright }}>Quelle</strong> zeigt,
        ob sich die Produktseiten des Herstellers auswerten lassen — dort geht Nachpflegen am
        schnellsten. Klick auf einen Hersteller listet dessen Artikel.
      </p>

      {/* Intrastat: gesetzliche Pflicht, deshalb vor allen anderen Lücken erklärt. */}
      {auslandsartikel > 0 && (
        <div style={{ borderRadius: 9, border: `1px solid ${ROT}55`,
          backgroundColor: "rgba(224,112,112,0.07)", padding: "13px 15px", marginBottom: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
            <AlertTriangle size={15} style={{ color: ROT }} />
            <p style={{ fontSize: 13.5, fontWeight: 800, color: S.textBright, margin: 0 }}>
              Pflichtangaben für die Intrastat-Meldung
            </p>
          </div>
          <p style={{ fontSize: 12, color: S.textMain, margin: "0 0 8px", lineHeight: 1.6 }}>
            <strong style={{ color: S.textBright }}>Warum das dringend ist:</strong> Wer Waren über
            EU-Grenzen bewegt und die Meldeschwelle überschreitet, ist zur monatlichen
            Intrastat-Meldung beim Statistischen Bundesamt <strong style={{ color: S.textBright }}>gesetzlich
            verpflichtet</strong>. Jede Meldezeile braucht drei Angaben aus dem Artikelstamm — fehlt
            eine davon, wird die Meldung falsch oder lässt sich gar nicht erst erzeugen:
          </p>
          <ul style={{ margin: "0 0 8px", paddingLeft: 18, fontSize: 12, color: S.textMain,
            lineHeight: 1.6, display: "flex", flexDirection: "column", gap: 3 }}>
            <li><strong style={{ color: S.textBright }}>Warennummer (cTaric)</strong> — die
              achtstellige Nummer der Kombinierten Nomenklatur; ohne sie ist keine Zeile meldefähig.</li>
            <li><strong style={{ color: S.textBright }}>Ursprungsland</strong> — seit 2022 Pflichtfeld
              auch bei der Versendung.</li>
            <li><strong style={{ color: S.textBright }}>Eigenmasse (Gewicht)</strong> — bei den meisten
              Warennummern die Mengeneinheit der Meldung.</li>
          </ul>
          <p style={{ fontSize: 12, color: S.textMain, margin: 0, lineHeight: 1.6 }}>
            Betroffen sind vor allem Artikel aus dem Ausland: <strong style={{ color: ROT }}>
            {zahl(auslandsartikel)}</strong> Artikel haben ein Ursprungsland außerhalb Deutschlands.
            Fehlend im gesamten Stamm: <strong style={{ color: ROT }}>{zahl(summe.OhneTaric)}</strong> ohne
            Warennummer, <strong style={{ color: ROT }}>{zahl(summe.OhneHerkunft)}</strong> ohne
            Ursprungsland, <strong style={{ color: ROT }}>{zahl(summe.OhneGewicht)}</strong> ohne Gewicht.
          </p>
        </div>
      )}

      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr>
            {["Hersteller", "Quelle", "Artikel", "ohne EAN", "ohne Hersteller-Nr.",
              "dürftiger Text", "ohne Warennr.", "ohne Herkunft", "ohne Gewicht",
              "Lagerwert"].map(h => <th key={h} style={th}>{h}</th>)}
          </tr></thead>
          <tbody>
            {sortiert.map(h => {
              const st = status[h.Hersteller] || {};
              return (
                <tr key={h.kHersteller} onClick={() => oeffne(h)}
                  style={{ cursor: "pointer" }}
                  onMouseEnter={e => e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.03)"}
                  onMouseLeave={e => e.currentTarget.style.backgroundColor = "transparent"}>
                  <td style={{ ...td, fontWeight: 600, color: S.textBright }}>{h.Hersteller}</td>
                  <td style={td}>
                    {st.auswertbar ? (
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 5,
                        fontSize: 11, color: GRUEN, fontWeight: 600 }}>
                        <Globe size={12} />
                        {st.liefert_ean && <Barcode size={11} title="liefert EANs" />}
                        {st.liefert_text && <Sparkles size={11} title="liefert Produkttexte" />}
                        auswertbar
                      </span>
                    ) : (
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 5,
                        fontSize: 11, color: S.textDim }}>
                        <GlobeLock size={12} /> keine Quelle
                      </span>
                    )}
                  </td>
                  <td style={num}>{zahl(h.Artikel)}</td>
                  <td style={{ ...num, color: h.OhneEAN > 0 ? ROT : S.textDim }}>{zahl(h.OhneEAN)}</td>
                  <td style={{ ...num, color: h.OhneHAN > 0 ? ROT : S.textDim }}>{zahl(h.OhneHAN)}</td>
                  <td style={{ ...num, color: h.DuerftigerText > 0 ? ACCENT : S.textDim }}>
                    {zahl(h.DuerftigerText)}
                  </td>
                  <td style={{ ...num, color: h.OhneTaric > 0 ? ROT : S.textDim }}>{zahl(h.OhneTaric)}</td>
                  <td style={{ ...num, color: h.OhneHerkunft > 0 ? ROT : S.textDim }}>{zahl(h.OhneHerkunft)}</td>
                  <td style={{ ...num, color: h.OhneGewicht > 0 ? ROT : S.textDim }}>{zahl(h.OhneGewicht)}</td>
                  <td style={num}>{zahl(h.Lagerwert)} €</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {laedt && (
        <p style={{ fontSize: 11, color: S.textDim, marginTop: 10,
          display: "flex", alignItems: "center", gap: 6 }}>
          <Loader2 size={12} style={{ animation: "spin 1s linear infinite" }} /> lädt…
        </p>
      )}
    </div>
  );
}
