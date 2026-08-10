import { useState } from "react";
import { Barcode, Loader2, Download, ExternalLink, AlertCircle, Check } from "lucide-react";
import api from "../../../api/client";
import { S } from "../../dashboard/constants";

const ACCENT = "#fce499";

/**
 * Eigenständiges Widget: schlägt für Artikel ohne EAN die offiziellen Nummern
 * beim Hersteller nach (über die Hersteller-Artikelnummer, siehe
 * services/product_research.py) und zeigt sie als Vorschlag zum Prüfen.
 *
 * Stapelweise, weil je Artikel ein Seitenabruf beim Hersteller anfällt.
 * Geschrieben wird nichts – die Übernahme in die Wawi bleibt beim Anwender.
 */
export default function EanResearchWidget({ widget }) {
  const cfg = widget.config?.ean_research || {};
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState("");
  const [stand, setStand] = useState(null);      // Zahlen des letzten Laufs
  const [zeilen, setZeilen] = useState([]);      // gesammelte Vorschläge
  const [offset, setOffset] = useState(0);
  const [ohneTreffer, setOhneTreffer] = useState(0);

  const stapel = async (start) => {
    if (!cfg.mapping_id) { setFehler("Kein Kandidaten-Mapping hinterlegt."); return; }
    setLaeuft(true); setFehler("");
    try {
      const { data } = await api.post("/api/research/ean", {
        mapping_id: cfg.mapping_id, limit: cfg.batch || 20, offset: start,
      });
      setStand(data);
      setZeilen(z => start === 0 ? data.vorschlaege : [...z, ...data.vorschlaege]);
      setOhneTreffer(n => start === 0 ? data.ohne_treffer : n + data.ohne_treffer);
      setOffset(data.naechster_offset);
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
    } finally {
      setLaeuft(false);
    }
  };

  const csv = () => {
    const kopf = ["Artikelnummer", "Artikel", "Hersteller", "HerstellerArtNr", "EAN", "EAN-Typ", "Quelle"];
    const rows = zeilen.flatMap(v =>
      Object.entries(v.eans).map(([typ, ean]) =>
        [v.ArtNr, v.Artikel, v.Hersteller, v.HAN, ean, typ, v.quelle]));
    const text = [kopf, ...rows]
      .map(r => r.map(f => `"${String(f ?? "").replace(/"/g, '""')}"`).join(";")).join("\r\n");
    const url = URL.createObjectURL(new Blob(["﻿" + text], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url; a.download = "ean-vorschlaege.csv"; a.click();
    URL.revokeObjectURL(url);
  };

  const th = { textAlign: "left", padding: "7px 10px", fontSize: 10, fontWeight: 700,
    color: S.textDim, textTransform: "uppercase", letterSpacing: "0.05em",
    borderBottom: `1px solid ${S.border}` };
  const td = { padding: "7px 10px", fontSize: 12, color: S.textMain,
    borderBottom: `1px solid ${S.border}` };

  return (
    <div style={{ borderRadius: 10, border: `1px solid ${ACCENT}55`,
      backgroundColor: `${ACCENT}0a`, padding: 18, marginBottom: 4 }}>

      <div style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: 12 }}>
        <div style={{ width: 38, height: 38, borderRadius: 9, backgroundColor: `${ACCENT}1a`,
          border: `1px solid ${ACCENT}44`, display: "flex", alignItems: "center",
          justifyContent: "center", flexShrink: 0 }}>
          <Barcode size={19} style={{ color: ACCENT }} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{ fontSize: 15, fontWeight: 800, color: S.textBright, margin: 0 }}>
            Fehlende EANs beim Hersteller holen
          </p>
          <p style={{ fontSize: 12, color: S.textDim, margin: "3px 0 0" }}>
            Der wirksamste Hebel in diesem Bericht — deshalb steht er oben.
          </p>
        </div>
      </div>

      <div style={{ fontSize: 12.5, color: S.textMain, lineHeight: 1.65, marginBottom: 14 }}>
        <p style={{ margin: "0 0 8px" }}>
          <strong style={{ color: S.textBright }}>Warum das wichtig ist:</strong> Die EAN ist die
          einzige weltweit eindeutige Kennung deiner Artikel. Ohne sie hängt vieles in der Luft:
        </p>
        <ul style={{ margin: "0 0 8px", paddingLeft: 18, display: "flex",
          flexDirection: "column", gap: 4 }}>
          <li><strong style={{ color: S.textBright }}>Marktplätze</strong> – Amazon und eBay verlangen
            eine GTIN, ohne sie ist der Artikel dort nicht listbar.</li>
          <li><strong style={{ color: S.textBright }}>Lieferantendaten</strong> – Artikelkataloge deiner
            Lieferanten lassen sich nur über die EAN automatisch zuordnen. Ohne sie bleibt der Abgleich
            über Namen: mühsam und fehleranfällig.</li>
          <li><strong style={{ color: S.textBright }}>Lager und Wareneingang</strong> – Scannen setzt
            einen gepflegten Barcode voraus.</li>
          <li><strong style={{ color: S.textBright }}>Recherche</strong> – mit EAN findet man genau ein
            Produkt, ohne sie irgendeines mit ähnlichem Namen.</li>
        </ul>
        <p style={{ margin: 0 }}>
          Viele Hersteller veröffentlichen die EAN auf ihrer Produktseite. Diese Suche schlägt jeden
          Artikel über seine Hersteller-Artikelnummer dort nach — die Zuordnung ist damit eindeutig,
          nicht geraten.
        </p>
      </div>

      {stand && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
          {[["Artikel ohne EAN", stand.kandidaten_gesamt],
            ["davon nachschlagbar", stand.kandidaten_machbar],
            ["geprüft", offset],
            ["EAN gefunden", zeilen.length],
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
          <AlertCircle size={14} style={{ color: "#e07070" }} />
          <span style={{ fontSize: 12, color: "#e07070" }}>{fehler}</span>
        </div>
      )}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <button onClick={() => stapel(stand ? offset : 0)} disabled={laeuft || stand?.fertig}
          style={{ display: "flex", alignItems: "center", gap: 7, padding: "9px 16px",
            borderRadius: 7, backgroundColor: stand?.fertig ? "rgba(110,231,183,0.15)" : ACCENT,
            border: "none", color: stand?.fertig ? "#6ee7b7" : "#111",
            cursor: laeuft || stand?.fertig ? "default" : "pointer",
            fontSize: 12.5, fontWeight: 700 }}>
          {laeuft ? <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} />
            : stand?.fertig ? <Check size={14} /> : <Barcode size={14} />}
          {laeuft ? "Wird beim Hersteller nachgeschlagen…"
            : stand?.fertig ? "Alle geprüft"
            : stand ? "Weitere prüfen" : "Beim Hersteller nachschlagen"}
        </button>
        {zeilen.length > 0 && (
          <button onClick={csv}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "9px 14px",
              borderRadius: 7, backgroundColor: "rgba(255,255,255,0.05)",
              border: `1px solid ${S.border}`, color: S.textDim, cursor: "pointer",
              fontSize: 12, fontWeight: 600 }}>
            <Download size={13} /> Als CSV
          </button>
        )}
        {laeuft && (
          <span style={{ fontSize: 11, color: S.textDim }}>
            je Artikel ein Seitenabruf – das dauert einen Moment
          </span>
        )}
      </div>

      {zeilen.length > 0 && (
        <div style={{ marginTop: 14, overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                {["Artikelnr.", "Artikel", "Hersteller-ArtNr", "Gefundene EAN", "Quelle"].map(h => (
                  <th key={h} style={th}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {zeilen.map(v => (
                <tr key={v.kArtikel}>
                  <td style={{ ...td, whiteSpace: "nowrap" }}>{v.ArtNr}</td>
                  <td style={td}>{v.Artikel}</td>
                  <td style={{ ...td, whiteSpace: "nowrap" }}>{v.HAN}</td>
                  <td style={td}>
                    {Object.entries(v.eans).map(([typ, ean]) => (
                      <div key={typ} style={{ whiteSpace: "nowrap" }}>
                        <code style={{ color: ACCENT, fontSize: 12 }}>{ean}</code>
                        <span style={{ color: S.textDim, fontSize: 10.5, marginLeft: 6 }}>{typ}</span>
                      </div>
                    ))}
                  </td>
                  <td style={td}>
                    <a href={v.quelle} target="_blank" rel="noopener"
                      style={{ color: S.textDim, display: "inline-flex", alignItems: "center", gap: 4 }}>
                      <ExternalLink size={11} /> Seite
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p style={{ fontSize: 11, color: S.textDim, margin: "10px 0 0", lineHeight: 1.5 }}>
            Vorschläge — geschrieben wird nichts. Prüfe die Nummern anhand der verlinkten Seite und
            übernimm sie über die CSV in die Wawi. Achte darauf, ob du die EAN der Verkaufseinheit
            brauchst: Hersteller geben oft Karton und Rolle getrennt an.
          </p>
        </div>
      )}
    </div>
  );
}
