import { useState } from "react";
import { X, Download, Search, Loader2, AlertCircle, ChevronLeft, ChevronRight, Info, Copy, Check } from "lucide-react";
import EmailTableButton from "./EmailTableButton";

const S = {
  bgMain: "var(--bg-main)",
  bgCard: "var(--bg-card)",
  bgEl: "var(--bg-elevated)",
  border: "var(--border)",
  textMain: "var(--text-main)",
  textBright: "var(--text-bright)",
  textDim: "var(--text-dim)",
};

const ACCENT = "#fce499";

// Erklärung wird automatisch eingeblendet, sobald die Detailtabelle eine
// Ertrags-Spalte enthält (DB, Rohertrag Ware, Rohertrag gesamt …).
const DB_INFO = "Rohertrag Ware = Umsatz − Wareneinsatz (Einkaufspreis), nur Artikelpositionen. "
  + "Rohertrag gesamt = derselbe Rohertrag über alle Positionsarten, also zuzüglich "
  + "Versandergebnis und sonstiger Positionen wie Rabatten.";

/** XML einrücken, damit es lesbar ist – SQL Server liefert xml-Spalten ohne
 *  Zeilenumbrüche. Kein Parser: ein kaputtes Dokument soll trotzdem sichtbar sein. */
export function xmlEinruecken(xml) {
  const t = String(xml ?? "").trim();
  if (!t.startsWith("<")) return t;
  let tiefe = 0;
  return t.replace(/>\s*</g, ">\n<").split("\n").map(zeile => {
    let rein = 0;
    if (/^<\/[^>]+>$/.test(zeile)) tiefe = Math.max(tiefe - 1, 0);
    else if (/^<[\w:][^>]*[^/]>$/.test(zeile) || /^<[\w:]+>$/.test(zeile)) rein = 1;
    const out = "  ".repeat(tiefe) + zeile;
    tiefe += rein;
    return out;
  }).join("\n");
}

/** Inhalt einer Spalte als Dokument (eine Zeile): Kopfdaten, Kopieren, Herunterladen. */
function DokumentAnsicht({ row, spalte, dateiSpalte, hidden }) {
  const [kopiert, setKopiert] = useState(false);
  const roh = row[spalte];
  const istXml = typeof roh === "string" && roh.trim().startsWith("<");
  const text = istXml ? xmlEinruecken(roh) : String(roh ?? "");
  const kopf = Object.keys(row).filter(c => c !== spalte && !hidden.has(c)
    && row[c] !== null && row[c] !== "");

  const kopieren = async () => {
    try { await navigator.clipboard.writeText(text); setKopiert(true); setTimeout(() => setKopiert(false), 1500); }
    catch { /* Zwischenablage gesperrt (kein HTTPS) – Text bleibt markierbar */ }
  };
  const herunterladen = () => {
    // Aus einer xml-Spalte kommt das Dokument ohne Kopfzeile zurück; für die Datei ergänzen.
    const inhalt = istXml && !text.startsWith("<?xml")
      ? '<?xml version="1.0" encoding="UTF-8"?>\n' + text : text;
    const name = (dateiSpalte && row[dateiSpalte]) || `${spalte}.${istXml ? "xml" : "txt"}`;
    const url = URL.createObjectURL(new Blob([inhalt], { type: istXml ? "application/xml" : "text/plain" }));
    const a = document.createElement("a");
    a.href = url; a.download = String(name); a.click();
    URL.revokeObjectURL(url);
  };
  const knopf = { display: "flex", alignItems: "center", gap: 5, padding: "4px 9px", borderRadius: 4,
    fontSize: 11, fontWeight: 600, cursor: "pointer", border: `1px solid ${S.border}`,
    backgroundColor: S.bgEl, color: S.textMain };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "10px 16px",
        borderBottom: `1px solid ${S.border}` }}>
        <div style={{ flex: 1, display: "flex", flexWrap: "wrap", gap: "4px 16px", fontSize: 11 }}>
          {kopf.map(c => (
            <span key={c}><span style={{ color: S.textDim }}>{c}: </span>
              <span style={{ color: S.textMain }}>{fmtCell(row[c])}</span></span>
          ))}
        </div>
        <button onClick={kopieren} disabled={!text} style={knopf}>
          {kopiert ? <Check size={12} /> : <Copy size={12} />} {kopiert ? "Kopiert" : "Kopieren"}
        </button>
        <button onClick={herunterladen} disabled={!text} style={knopf}>
          <Download size={12} /> {istXml ? "XML" : "Datei"}
        </button>
      </div>
      {text ? (
        <pre style={{ margin: 0, padding: "12px 16px", flex: 1, overflow: "auto", fontSize: 11.5,
          lineHeight: 1.5, color: S.textMain, fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          whiteSpace: "pre", tabSize: 2 }}>{text}</pre>
      ) : (
        <div style={{ padding: 40, textAlign: "center", color: S.textDim, fontSize: 12 }}>
          „{spalte}“ ist leer.
        </div>
      )}
    </div>
  );
}

// CSV aus Zeilen bauen (RFC-4180-konform: Felder mit " , \n werden gequotet)
function toCsv(columns, rows) {
  const esc = (v) => {
    const s = v == null ? "" : String(v);
    return /[";\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const head = columns.map(esc).join(";");
  const body = rows.map(r => columns.map(c => esc(r[c])).join(";")).join("\n");
  return head + "\n" + body;
}

function fmtCell(v) {
  if (v == null) return "–";
  // Nur echte Zahlen mit Tausenderpunkten formatieren – String-IDs wie Artikel-/
  // Rechnungsnummern (numerische Strings) bleiben unverändert (keine 4.038.015).
  if (typeof v === "number") return v.toLocaleString("de-DE", { maximumFractionDigits: 2 });
  return String(v);
}

function isNumericCol(col, rows) {
  // Rechtsbündig nur echte Zahlenspalten – numerische String-IDs bleiben linksbündig.
  return rows.some(r => typeof r[col] === "number");
}

export default function DrilldownModal({ title, field, value, rows = [], loading, error, onClose,
  trail = [], canDrillDeeper = false, onRowClick = null, onBack = null, hiddenColumns = [],
  emailEnabled = false, dokument = null }) {
  const hidden = new Set(hiddenColumns || []);
  const columns = (rows.length ? Object.keys(rows[0]) : []).filter(c => !hidden.has(c));
  const numericCols = new Set(columns.filter(c => isNumericCol(c, rows)));
  // Lange Textspalten (z.B. Artikelbeschreibung) umbrechen statt horizontal scrollen.
  const longTextCols = new Set(columns.filter(c => !numericCols.has(c)
    && rows.some(r => typeof r[c] === "string" && r[c].length > 60)));

  const handleExport = () => {
    const csv = toCsv(columns, rows);
    const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const safeVal = String(value ?? "detail").replace(/[^a-z0-9]+/gi, "_").slice(0, 40);
    a.href = url;
    a.download = `drilldown_${field || "wert"}_${safeVal}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, zIndex: 1000,
        backgroundColor: "rgba(0,0,0,0.55)",
        display: "flex", alignItems: "center", justifyContent: "center", padding: 24,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          width: "min(1400px, 96vw)", maxHeight: "85vh",
          backgroundColor: S.bgCard, border: `1px solid ${S.border}`, borderRadius: 10,
          display: "flex", flexDirection: "column", overflow: "hidden",
          boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
        }}
      >
        {/* Header */}
        <div style={{ padding: "12px 16px", borderBottom: `1px solid ${S.border}`, display: "flex", alignItems: "center", gap: 10 }}>
          {onBack ? (
            <button onClick={onBack} title="Eine Ebene zurück"
              style={{ background: "none", border: `1px solid ${S.border}`, borderRadius: 5, color: S.textMain, cursor: "pointer", padding: "3px 6px", display: "flex", alignItems: "center", flexShrink: 0 }}>
              <ChevronLeft size={14} />
            </button>
          ) : (
            <Search size={14} style={{ color: ACCENT, flexShrink: 0 }} />
          )}
          <div style={{ flex: 1, minWidth: 0 }}>
            {/* Breadcrumb-Pfad über alle Ebenen */}
            {trail.length > 1 && (
              <div style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap", marginBottom: 3 }}>
                {trail.map((t, i) => (
                  <span key={i} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 9.5,
                    color: i === trail.length - 1 ? ACCENT : S.textDim, whiteSpace: "nowrap" }}>
                    {i > 0 && <ChevronRight size={9} style={{ color: S.textDim }} />}
                    {t.title}{t.value != null && t.value !== "" ? `: ${String(t.value)}` : ""}
                  </span>
                ))}
              </div>
            )}
            <p style={{ fontSize: 13, fontWeight: 700, color: S.textBright, margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {title || "Drilldown"}
            </p>
            <p style={{ fontSize: 11, color: S.textDim, margin: "2px 0 0" }}>
              {field ? <><span style={{ color: S.textMain }}>{field}</span> = <span style={{ color: ACCENT }}>{String(value)}</span> · </> : null}
              {loading ? "lädt…" : `${rows.length.toLocaleString("de-DE")} Zeile${rows.length === 1 ? "" : "n"}`}
              {canDrillDeeper && !loading && rows.length > 0 ? " · Zeile klicken für Details" : ""}
            </p>
          </div>
          {emailEnabled && (
            <EmailTableButton columns={columns} rows={rows} title={title || "Drilldown"} disabled={!rows.length} />
          )}
          <button onClick={handleExport} disabled={!rows.length}
            style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 10px", borderRadius: 4, fontSize: 11, fontWeight: 600, cursor: rows.length ? "pointer" : "not-allowed", border: `1px solid ${ACCENT}44`, backgroundColor: `${ACCENT}15`, color: ACCENT, opacity: rows.length ? 1 : 0.5 }}>
            <Download size={12} /> CSV
          </button>
          <button onClick={onClose} style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 4 }}>
            <X size={16} />
          </button>
        </div>

        {/* DB-Erklärung, wenn die Detailtabelle eine Deckungsbeitrags-Spalte hat */}
        {!loading && !error && columns.some(c => /^(DB([ -]|$)|Rohertrag)/.test(c)) && (
          <div style={{ display: "flex", alignItems: "flex-start", gap: 7, padding: "8px 16px",
            borderBottom: `1px solid ${S.border}`, fontSize: 10.5, lineHeight: 1.5, color: S.textDim,
            backgroundColor: "rgba(255,255,255,0.02)" }}>
            <Info size={12} style={{ flexShrink: 0, marginTop: 1 }} /> <span>{DB_INFO}</span>
          </div>
        )}

        {/* Tabelle */}
        <div style={{ flex: 1, overflow: "auto", scrollbarWidth: "thin" }}>
          {loading ? (
            <div style={{ padding: 40, textAlign: "center", color: S.textDim, fontSize: 12, display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
              <Loader2 size={20} className="spin" style={{ color: ACCENT, animation: "spin 1s linear infinite" }} />
              Detaildaten werden geladen…
            </div>
          ) : error ? (
            <div style={{ padding: 40, textAlign: "center", color: "#e07070", fontSize: 12, display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
              <AlertCircle size={20} />
              {error}
            </div>
          ) : rows.length === 0 ? (
            <div style={{ padding: 40, textAlign: "center", color: S.textDim, fontSize: 12 }}>
              Keine Detailzeilen für diese Auswahl.
            </div>
          ) : dokument && dokument.spalte in rows[0] ? (
            <DokumentAnsicht row={rows[0]} spalte={dokument.spalte}
              dateiSpalte={dokument.datei_spalte} hidden={hidden} />
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
              <thead style={{ position: "sticky", top: 0, zIndex: 1 }}>
                <tr style={{ backgroundColor: S.bgEl }}>
                  {columns.map(c => (
                    <th key={c} style={{ padding: "7px 12px", textAlign: numericCols.has(c) ? "right" : "left", color: S.textDim, fontWeight: 700, fontSize: 10, textTransform: "uppercase", letterSpacing: "0.05em", borderBottom: `1px solid ${S.border}`, whiteSpace: "nowrap" }}>
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr key={i}
                    onClick={canDrillDeeper && onRowClick ? () => onRowClick(row) : undefined}
                    style={{ borderBottom: `1px solid ${S.border}`, backgroundColor: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.02)",
                      cursor: canDrillDeeper && onRowClick ? "pointer" : "default" }}
                    onMouseEnter={canDrillDeeper ? e => e.currentTarget.style.backgroundColor = `${ACCENT}18` : undefined}
                    onMouseLeave={canDrillDeeper ? e => e.currentTarget.style.backgroundColor = i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.02)" : undefined}>
                    {columns.map(c => (
                      <td key={c} style={{ padding: "5px 12px", color: numericCols.has(c) ? S.textBright : S.textMain, textAlign: numericCols.has(c) ? "right" : "left",
                        whiteSpace: longTextCols.has(c) ? "pre-wrap" : "nowrap",
                        maxWidth: longTextCols.has(c) ? 560 : undefined,
                        wordBreak: longTextCols.has(c) ? "break-word" : undefined,
                        lineHeight: longTextCols.has(c) ? 1.45 : undefined }}>
                        {fmtCell(row[c])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
