import { useMemo, useState } from "react";
import { Loader2, Search, ExternalLink, AlertCircle, ShieldCheck, ShieldAlert,
  ShieldX, Eye, ChevronDown, ChevronRight, Check, Upload, AlertTriangle } from "lucide-react";
import api from "../../../api/client";
import { S } from "../../dashboard/constants";

const ACCENT = "#fce499";
const GRUEN = "#6ee7b7";
const ROT = "#e07070";

const FELD_LABEL = {
  EAN: "EAN", Warennummer: "Warennummer (cTaric)",
  Herkunftsland: "Ursprungsland", Gewicht: "Gewicht (kg)",
};

/** Ampel zum Sicherheitsgrad. Die Schwellen kommen vom Server (stufe), die
 *  Prozentzahl steht daneben, damit „prüfen" nicht alles in einen Topf wirft. */
function Sicherheit({ stufe, wert }) {
  const m = {
    gesichert:   [GRUEN,      ShieldCheck, "gesichert"],
    pruefen:     [ACCENT,     ShieldAlert, "prüfen"],
    ungesichert: [ROT,        ShieldX,     "ungesichert"],
  }[stufe] || [S.textDim, ShieldAlert, stufe];
  const [farbe, Icon, text] = m;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5,
      padding: "3px 8px", borderRadius: 20, whiteSpace: "nowrap",
      backgroundColor: `${farbe}1a`, border: `1px solid ${farbe}55`, color: farbe,
      fontSize: 11, fontWeight: 700 }}>
      <Icon size={12} /> {wert} % · {text}
    </span>
  );
}

const STATUS_TEXT = {
  bereit:        ["würde geschrieben", GRUEN],
  geschrieben:   ["geschrieben", GRUEN],
  belegt:        ["übergangen (Feld ist gefüllt)", S.textDim],
  unveraendert:  ["unverändert", S.textDim],
  fehler:        ["nicht schreibbar", ROT],
  kollision:     ["übersprungen (zwischenzeitlich geändert)", ROT],
};

/** Ergebnis eines Dry-Runs bzw. eines Schreibvorgangs. */
function PlanVorschau({ plan, onSchreiben, schreibt }) {
  const [sqlOffen, setSqlOffen] = useState(false);
  const [bestaetigen, setBestaetigen] = useState(false);
  const geschrieben = plan.dry_run === false;
  const th = { textAlign: "left", padding: "6px 9px", fontSize: 10, fontWeight: 700,
    color: S.textDim, textTransform: "uppercase", borderBottom: `1px solid ${S.border}` };
  const td = { padding: "6px 9px", fontSize: 12, color: S.textMain,
    borderBottom: `1px solid ${S.border}`, verticalAlign: "top" };

  return (
    <div style={{ marginTop: 14, borderRadius: 9, border: `1px solid ${S.border}`,
      backgroundColor: S.bgEl, padding: 14 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        {geschrieben ? <Check size={15} style={{ color: GRUEN }} />
                     : <Eye size={15} style={{ color: ACCENT }} />}
        <p style={{ fontSize: 13.5, fontWeight: 800, color: S.textBright, margin: 0 }}>
          {geschrieben ? "In die Wawi geschrieben"
                       : "Vorschau — es wurde nichts geschrieben"}
        </p>
      </div>
      <p style={{ fontSize: 12, color: S.textMain, margin: "0 0 10px", lineHeight: 1.6 }}>
        {geschrieben ? (
          <>
            <strong style={{ color: GRUEN }}>{plan.geschrieben}</strong> Werte wurden
            geschrieben{plan.uebersprungen ? <>, <strong style={{ color: S.textBright }}>
              {plan.uebersprungen}</strong> übersprungen</> : null}. Die Wawi-Oberfläche zeigt
            die Änderung, sobald der Artikel neu geöffnet wird.
          </>
        ) : (
          <>
            <strong style={{ color: S.textBright }}>{plan.anzahl_bereit}</strong> Werte in{" "}
            <strong style={{ color: S.textBright }}>{plan.anzahl_artikel}</strong> Artikeln wären
            schreibbar. Die Vorschau liest die aktuellen Werte direkt aus der Wawi — schon gefüllte
            Felder werden nicht überschrieben.
          </>
        )}
      </p>

      {plan.errors?.map((e, i) => (
        <p key={i} style={{ fontSize: 12, color: ROT, margin: "0 0 4px" }}>✗ {e}</p>
      ))}
      {plan.warnings?.map((w, i) => (
        <p key={i} style={{ fontSize: 12, color: ACCENT, margin: "0 0 4px" }}>⚠ {w}</p>
      ))}

      <div style={{ overflowX: "auto", maxHeight: 320, overflowY: "auto", marginTop: 8 }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr>
            {["Artikelnr.", "Feld", "in der Wawi", "neu", "Ergebnis"].map(h =>
              <th key={h} style={th}>{h}</th>)}
          </tr></thead>
          <tbody>
            {(plan.aenderungen || []).map((a, i) => {
              const [text, farbe] = STATUS_TEXT[a.status] || [a.status, S.textDim];
              return (
                <tr key={i}>
                  <td style={{ ...td, whiteSpace: "nowrap" }}>{a.ArtNr}</td>
                  <td style={{ ...td, whiteSpace: "nowrap" }}>{FELD_LABEL[a.feld] || a.feld}</td>
                  <td style={{ ...td, color: S.textDim }}>
                    {String(a.alt ?? "").trim() === "" ? "— leer —" : String(a.alt)}
                  </td>
                  <td style={{ ...td, color: S.textBright, fontWeight: 600 }}>
                    {a.neu === null || a.neu === undefined ? "—" : String(a.neu)}
                  </td>
                  <td style={{ ...td, color: farbe }}>
                    {text}{a.hinweis ? <span style={{ color: S.textDim }}> · {a.hinweis}</span> : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Schreiben ist der einzige Schritt, der die Wawi verändert – deshalb
          zweistufig und mit klarer Ansage, was gleich passiert. */}
      {!geschrieben && plan.anzahl_bereit > 0 && onSchreiben && (
        <div style={{ marginTop: 12 }}>
          {!bestaetigen ? (
            <button onClick={() => setBestaetigen(true)}
              style={{ display: "flex", alignItems: "center", gap: 7, padding: "9px 15px",
                borderRadius: 7, backgroundColor: "rgba(110,231,183,0.12)",
                border: `1px solid ${GRUEN}66`, color: GRUEN, cursor: "pointer",
                fontSize: 12.5, fontWeight: 700 }}>
              <Upload size={14} /> {plan.anzahl_bereit} Werte in die Wawi schreiben
            </button>
          ) : (
            <div style={{ padding: "12px 14px", borderRadius: 8,
              backgroundColor: "rgba(224,112,112,0.07)", border: `1px solid ${ROT}55` }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                <AlertTriangle size={15} style={{ color: ROT }} />
                <p style={{ fontSize: 13, fontWeight: 800, color: S.textBright, margin: 0 }}>
                  Wirklich in die Wawi schreiben?
                </p>
              </div>
              <p style={{ fontSize: 12, color: S.textMain, margin: "0 0 10px", lineHeight: 1.6 }}>
                {plan.anzahl_bereit} Werte in {plan.anzahl_artikel} Artikeln werden in der
                Warenwirtschaft gespeichert. Vor dem Schreiben wird die Vorschau noch einmal
                frisch gebaut; Artikel, die inzwischen jemand anders geändert hat, werden
                übersprungen statt überschrieben. <strong style={{ color: S.textBright }}>
                Rückgängig machen lässt sich das nicht.</strong>
              </p>
              <div style={{ display: "flex", gap: 8 }}>
                <button onClick={onSchreiben} disabled={schreibt}
                  style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 14px",
                    borderRadius: 6, backgroundColor: GRUEN, border: "none", color: "#111",
                    cursor: schreibt ? "wait" : "pointer", fontSize: 12, fontWeight: 700 }}>
                  {schreibt ? <Loader2 size={13} style={{ animation: "spin 1s linear infinite" }} />
                    : <Check size={13} />}
                  Ja, jetzt schreiben
                </button>
                <button onClick={() => setBestaetigen(false)}
                  style={{ padding: "8px 14px", borderRadius: 6, backgroundColor: "transparent",
                    border: `1px solid ${S.border}`, color: S.textDim, cursor: "pointer",
                    fontSize: 12 }}>
                  Abbrechen
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {plan.statements?.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <button onClick={() => setSqlOffen(o => !o)}
            style={{ display: "flex", alignItems: "center", gap: 5, background: "none",
              border: "none", color: S.textDim, cursor: "pointer", fontSize: 11.5, padding: 0 }}>
            {sqlOffen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
            SQL anzeigen, das ausgeführt würde
          </button>
          {sqlOffen && (
            <pre style={{ marginTop: 8, padding: 10, borderRadius: 6, fontSize: 11,
              backgroundColor: S.bgMain, border: `1px solid ${S.border}`, color: S.textDim,
              overflowX: "auto", lineHeight: 1.5 }}>{plan.statements.join("\n")}</pre>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Fehlende Stammdaten eines Herstellers stapelweise beim Hersteller nachschlagen
 * und je Wert einen Sicherheitsgrad anzeigen (Quelle: services/stammdaten_research.py).
 *
 * Drei Stufen, absichtlich getrennt: prüfen und auswählen → Vorschau (nichts
 * passiert) → ausdrücklich schreiben. Der Schreibvorgang baut serverseitig noch
 * einmal eine frische Vorschau; zwischenzeitlich geänderte Artikel werden
 * übersprungen statt überschrieben (bRowversion).
 */
export default function StammdatenPruefung({ hersteller, artikel, mappingId }) {
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState("");
  const [stand, setStand] = useState(null);
  const [offset, setOffset] = useState(0);
  const [ohneTreffer, setOhneTreffer] = useState(0);
  const [zeilen, setZeilen] = useState([]);       // ein Eintrag je Vorschlagswert
  const [gewaehlt, setGewaehlt] = useState({});   // "kArtikel|Feld" → gewählter Wert
  const [plan, setPlan] = useState(null);
  const [planLaeuft, setPlanLaeuft] = useState(false);
  const [schreibt, setSchreibt] = useState(false);

  const schluessel = (z) => `${z.kArtikel}|${z.feld}`;
  const istGewaehlt = (z) => gewaehlt[schluessel(z)] === z.wert;

  // Nur die Felder mitschicken, die der Server braucht – die Artikelzeilen führen
  // auch die Beschreibungstexte mit, das wären bei 500 Artikeln hunderte Kilobyte.
  const knapp = useMemo(() => artikel.map(a => ({
    kArtikel: a.kArtikel, ArtNr: a.ArtNr, Artikel: a.Artikel, HAN: a.HAN,
    EAN: a.EAN, Warennummer: a.Warennummer, Herkunftsland: a.Herkunftsland,
    Gewicht: a.Gewicht, Bestand: a.Bestand,
  })), [artikel]);

  const stapel = async (start) => {
    setLaeuft(true); setFehler(""); setPlan(null);
    try {
      const { data } = await api.post("/api/research/stammdaten", {
        hersteller, artikel: knapp, limit: 20, offset: start,
      });
      setStand(data);
      const neu = data.vorschlaege.flatMap(v =>
        v.werte.map(w => ({ ...w, kArtikel: v.kArtikel, ArtNr: v.ArtNr,
          Artikel: v.Artikel, HAN: v.HAN, quelle: v.quelle })));
      setZeilen(z => start === 0 ? neu : [...z, ...neu]);
      setOhneTreffer(n => start === 0 ? data.ohne_treffer : n + data.ohne_treffer);
      setOffset(data.naechster_offset);
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
    } finally { setLaeuft(false); }
  };

  // Je Artikel und Feld gilt genau ein Wert – eine zweite Auswahl ersetzt die erste.
  const waehle = (z) => setGewaehlt(g => {
    const k = schluessel(z);
    const neu = { ...g };
    if (neu[k] === z.wert) delete neu[k]; else neu[k] = z.wert;
    return neu;
  });

  const auswahl = useMemo(() => zeilen.filter(istGewaehlt), [zeilen, gewaehlt]);

  const vorschau = async () => {
    setPlanLaeuft(true); setFehler(""); setPlan(null);
    try {
      const { data } = await api.post("/api/stammdaten/plan", {
        mapping_id: mappingId,
        aenderungen: auswahl.map(z => ({ kArtikel: z.kArtikel, feld: z.feld,
          wert: z.wert, quelle: z.quelle })),
      });
      setPlan(data);
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
    } finally { setPlanLaeuft(false); }
  };

  const schreiben = async () => {
    setSchreibt(true); setFehler("");
    try {
      const { data } = await api.post("/api/stammdaten/write", {
        mapping_id: mappingId,
        aenderungen: auswahl.map(z => ({ kArtikel: z.kArtikel, feld: z.feld,
          wert: z.wert, quelle: z.quelle })),
        bestaetigt: true,
        // Ein einzelner ungültiger Wert soll den Rest des Stapels nicht aufhalten;
        // die übersprungenen Zeilen stehen samt Grund im Ergebnis.
        ueberspringe_fehler: true,
      });
      setPlan(data);
      // Geschriebene Werte nicht erneut anbieten – sonst schreibt man sie zweimal.
      const fertig = new Set((data.aenderungen || [])
        .filter(a => a.status === "geschrieben")
        .map(a => `${a.kArtikel}|${a.feld}`));
      setZeilen(z => z.filter(x => !fertig.has(schluessel(x))));
      setGewaehlt(g => Object.fromEntries(
        Object.entries(g).filter(([k]) => !fertig.has(k))));
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
    } finally { setSchreibt(false); }
  };

  const th = { textAlign: "left", padding: "7px 9px", fontSize: 10, fontWeight: 700,
    color: S.textDim, textTransform: "uppercase", borderBottom: `1px solid ${S.border}`,
    whiteSpace: "nowrap" };
  const td = { padding: "7px 9px", fontSize: 12, color: S.textMain,
    borderBottom: `1px solid ${S.border}`, verticalAlign: "top" };

  return (
    <div style={{ marginTop: 16, borderRadius: 10, border: `1px solid ${ACCENT}55`,
      backgroundColor: `${ACCENT}0a`, padding: 16 }}>

      <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 6 }}>
        <Search size={16} style={{ color: ACCENT }} />
        <p style={{ fontSize: 14, fontWeight: 800, color: S.textBright, margin: 0 }}>
          Fehlende Angaben beim Hersteller prüfen
        </p>
      </div>
      <p style={{ fontSize: 12, color: S.textMain, margin: "0 0 12px", lineHeight: 1.6 }}>
        Geprüft werden EAN, Warennummer, Ursprungsland und Gewicht — aber nur bei Artikeln,
        bei denen das Feld in der Wawi leer ist und eine Hersteller-Artikelnummer vorliegt.
        Jeder Fund bekommt einen Sicherheitsgrad:{" "}
        <span style={{ color: GRUEN, fontWeight: 700 }}>100 % = eindeutig</span>,{" "}
        <span style={{ color: ACCENT, fontWeight: 700 }}>über 50 % = vermutlich richtig, prüfen</span>,{" "}
        <span style={{ color: ROT, fontWeight: 700 }}>bis 50 % = ungesichert</span>. Der Grund
        steht in jeder Zeile.
      </p>

      {stand && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
          {[["Artikel des Herstellers", stand.kandidaten_gesamt],
            ["davon nachschlagbar", stand.kandidaten_machbar],
            ["geprüft", offset],
            ["Werte gefunden", zeilen.length],
            ["ausgewählt", auswahl.length],
            ["nichts hinterlegt", ohneTreffer]].map(([k, v]) => (
            <div key={k} style={{ backgroundColor: S.bgEl, border: `1px solid ${S.border}`,
              borderRadius: 7, padding: "6px 11px" }}>
              <div style={{ fontSize: 9.5, color: S.textDim, textTransform: "uppercase" }}>{k}</div>
              <div style={{ fontSize: 15, fontWeight: 700, color: S.textBright }}>{v}</div>
            </div>
          ))}
        </div>
      )}

      {fehler && (
        <div style={{ marginBottom: 10, padding: "8px 10px", borderRadius: 6,
          backgroundColor: "rgba(224,112,112,0.1)", border: "1px solid rgba(224,112,112,0.3)",
          display: "flex", gap: 8, alignItems: "center" }}>
          <AlertCircle size={14} style={{ color: ROT }} />
          <span style={{ fontSize: 12, color: ROT }}>{fehler}</span>
        </div>
      )}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <button onClick={() => stapel(stand ? offset : 0)} disabled={laeuft || stand?.fertig}
          style={{ display: "flex", alignItems: "center", gap: 7, padding: "9px 15px",
            borderRadius: 7, border: "none",
            backgroundColor: stand?.fertig ? "rgba(110,231,183,0.15)" : ACCENT,
            color: stand?.fertig ? GRUEN : "#111",
            cursor: laeuft || stand?.fertig ? "default" : "pointer",
            fontSize: 12.5, fontWeight: 700 }}>
          {laeuft ? <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} />
            : <Search size={14} />}
          {laeuft ? "Wird beim Hersteller nachgeschlagen…"
            : stand?.fertig ? "Alle geprüft"
            : stand ? "Weitere 20 prüfen" : "Artikel prüfen"}
        </button>

        {zeilen.length > 0 && (
          <>
            <button onClick={() => setGewaehlt(Object.fromEntries(
              zeilen.filter(z => z.stufe === "gesichert").map(z => [schluessel(z), z.wert])))}
              style={{ padding: "9px 13px", borderRadius: 7, backgroundColor: "rgba(255,255,255,0.05)",
                border: `1px solid ${S.border}`, color: S.textDim, cursor: "pointer",
                fontSize: 12, fontWeight: 600 }}>
              nur gesicherte auswählen
            </button>
            <button onClick={vorschau} disabled={!auswahl.length || planLaeuft}
              style={{ display: "flex", alignItems: "center", gap: 6, padding: "9px 15px",
                borderRadius: 7, border: `1px solid ${GRUEN}55`,
                backgroundColor: auswahl.length ? "rgba(110,231,183,0.15)" : "transparent",
                color: GRUEN, opacity: auswahl.length ? 1 : 0.45,
                cursor: auswahl.length && !planLaeuft ? "pointer" : "default",
                fontSize: 12.5, fontWeight: 700 }}>
              {planLaeuft ? <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} />
                : <Eye size={14} />}
              Vorschau für {auswahl.length} Wert{auswahl.length === 1 ? "" : "e"}
            </button>
          </>
        )}
        {laeuft && (
          <span style={{ fontSize: 11, color: S.textDim }}>
            je Artikel ein Seitenabruf – das dauert einen Moment
          </span>
        )}
      </div>

      {zeilen.length > 0 && (
        <div style={{ marginTop: 14, overflowX: "auto", maxHeight: 420, overflowY: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr>
              {["", "Artikelnr.", "Artikel", "Feld", "Vorschlag", "Sicherheit",
                "warum", "Quelle"].map((h, i) => <th key={i} style={th}>{h}</th>)}
            </tr></thead>
            <tbody>
              {zeilen.map((z, i) => (
                <tr key={i} style={{ backgroundColor: istGewaehlt(z)
                  ? "rgba(110,231,183,0.07)" : "transparent" }}>
                  <td style={{ ...td, width: 30 }}>
                    {/* Standardmäßig ist nichts ausgewählt – die Übernahme ist
                        immer eine bewusste Entscheidung. */}
                    <input type="checkbox" checked={istGewaehlt(z)}
                      onChange={() => waehle(z)} style={{ cursor: "pointer" }} />
                  </td>
                  <td style={{ ...td, whiteSpace: "nowrap" }}>{z.ArtNr}</td>
                  <td style={{ ...td, maxWidth: 220 }}>{z.Artikel}</td>
                  <td style={{ ...td, whiteSpace: "nowrap" }}>{FELD_LABEL[z.feld] || z.feld}</td>
                  <td style={{ ...td, whiteSpace: "nowrap" }}>
                    <code style={{ color: S.textBright, fontSize: 12, fontWeight: 700 }}>
                      {String(z.wert)}
                    </code>
                    {String(z.roh) !== String(z.wert) && (
                      <div style={{ fontSize: 10.5, color: S.textDim }}>
                        Seite nennt: {z.roh}
                      </div>
                    )}
                    <div style={{ fontSize: 10.5, color: S.textDim }}>{z.label}</div>
                  </td>
                  <td style={td}><Sicherheit stufe={z.stufe} wert={z.sicherheit} /></td>
                  <td style={{ ...td, maxWidth: 320, fontSize: 11.5, color: S.textDim,
                    lineHeight: 1.5 }}>
                    {z.begruendung?.length ? z.begruendung.join(" · ")
                      : "eindeutige Zuordnung über die Hersteller-Artikelnummer, "
                        + "eindeutige Beschriftung, Wert formal gültig"}
                  </td>
                  <td style={td}>
                    <a href={z.quelle} target="_blank" rel="noopener"
                      style={{ color: S.textDim, display: "inline-flex", alignItems: "center",
                        gap: 4 }}>
                      <ExternalLink size={11} /> Seite
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {plan && <PlanVorschau plan={plan} schreibt={schreibt}
        onSchreiben={plan.dry_run === false ? null : schreiben} />}
    </div>
  );
}
