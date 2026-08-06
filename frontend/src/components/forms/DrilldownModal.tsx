import { useState } from "react";
import { X, Download, Search, Loader2, AlertCircle, ChevronLeft, ChevronRight, Info, Mail, Send, CheckCircle2 } from "lucide-react";
import api from "../../api/client";

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
// Deckungsbeitrags-Spalte enthält (DB, DB I, DB II …).
const DB_INFO = "Deckungsbeitrag I (= Rohertrag) = Umsatz − Wareneinsatz (Einkaufspreis). "
  + "Deckungsbeitrag II = DB I zzgl. Versandergebnis (Versanderlöse − Versandkosten).";

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
  emailEnabled = false }) {
  const hidden = new Set(hiddenColumns || []);
  const columns = (rows.length ? Object.keys(rows[0]) : []).filter(c => !hidden.has(c));
  const numericCols = new Set(columns.filter(c => isNumericCol(c, rows)));
  // Lange Textspalten (z.B. Artikelbeschreibung) umbrechen statt horizontal scrollen.
  const longTextCols = new Set(columns.filter(c => !numericCols.has(c)
    && rows.some(r => typeof r[c] === "string" && r[c].length > 60)));

  // E-Mail-Panel-State: Tabelle an Mitarbeiter schicken (CSV-Anhang + HTML-Vorschau)
  const [mailOpen, setMailOpen] = useState(false);
  const [recipients, setRecipients] = useState("");
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [mailMsg, setMailMsg] = useState(null);   // { ok, text }

  const sendMail = async () => {
    if (!recipients.trim()) { setMailMsg({ ok: false, text: "Bitte mindestens einen Empfänger angeben." }); return; }
    setSending(true); setMailMsg(null);
    try {
      const { data } = await api.post("/api/forms/email-table", {
        recipients, subject: subject || null, message: message || null,
        title: title || "Tabelle", columns, rows,
      });
      setMailMsg({ ok: true, text: `Gesendet an ${data.recipients.join(", ")} (${data.rows} Zeilen).` });
      setTimeout(() => { setMailOpen(false); setMailMsg(null); }, 2500);
    } catch (e) {
      setMailMsg({ ok: false, text: e.response?.data?.detail || e.message || "Versand fehlgeschlagen." });
    } finally { setSending(false); }
  };

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
            <button onClick={() => { setMailOpen(o => !o); setMailMsg(null); }} disabled={!rows.length}
              title="Tabelle per E-Mail an Mitarbeiter senden"
              style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 10px", borderRadius: 4, fontSize: 11, fontWeight: 600, cursor: rows.length ? "pointer" : "not-allowed", border: `1px solid ${mailOpen ? ACCENT : S.border}`, backgroundColor: mailOpen ? `${ACCENT}22` : "transparent", color: mailOpen ? ACCENT : S.textMain, opacity: rows.length ? 1 : 0.5 }}>
              <Mail size={12} /> E-Mail
            </button>
          )}
          <button onClick={handleExport} disabled={!rows.length}
            style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 10px", borderRadius: 4, fontSize: 11, fontWeight: 600, cursor: rows.length ? "pointer" : "not-allowed", border: `1px solid ${ACCENT}44`, backgroundColor: `${ACCENT}15`, color: ACCENT, opacity: rows.length ? 1 : 0.5 }}>
            <Download size={12} /> CSV
          </button>
          <button onClick={onClose} style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 4 }}>
            <X size={16} />
          </button>
        </div>

        {/* E-Mail-Panel: Tabelle an Mitarbeiter schicken (CSV-Anhang + HTML-Vorschau) */}
        {emailEnabled && mailOpen && (
          <div style={{ padding: "12px 16px", borderBottom: `1px solid ${S.border}`, backgroundColor: "rgba(255,255,255,0.02)", display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <input value={recipients} onChange={e => setRecipients(e.target.value)}
                placeholder="Empfänger (mehrere mit Komma trennen)"
                style={{ flex: "2 1 260px", minWidth: 220, padding: "6px 9px", fontSize: 12, borderRadius: 5, border: `1px solid ${S.border}`, backgroundColor: S.bgEl, color: S.textMain }} />
              <input value={subject} onChange={e => setSubject(e.target.value)}
                placeholder={`Betreff (Standard: „Cockpit: ${title || "Tabelle"}")`}
                style={{ flex: "1 1 200px", minWidth: 160, padding: "6px 9px", fontSize: 12, borderRadius: 5, border: `1px solid ${S.border}`, backgroundColor: S.bgEl, color: S.textMain }} />
            </div>
            <textarea value={message} onChange={e => setMessage(e.target.value)} rows={2}
              placeholder="Nachricht an die Mitarbeiter (optional) – z. B. „Bitte Beschreibungen ergänzen und zurücksenden.“"
              style={{ padding: "6px 9px", fontSize: 12, borderRadius: 5, border: `1px solid ${S.border}`, backgroundColor: S.bgEl, color: S.textMain, resize: "vertical", fontFamily: "inherit" }} />
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <button onClick={sendMail} disabled={sending || !rows.length}
                style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 14px", borderRadius: 5, fontSize: 12, fontWeight: 700, cursor: sending ? "wait" : "pointer", border: "none", backgroundColor: ACCENT, color: "#1a1a1a" }}>
                {sending ? <Loader2 size={13} style={{ animation: "spin 1s linear infinite" }} /> : <Send size={13} />}
                {sending ? "Sende…" : `Senden (${rows.length} Zeilen als CSV)`}
              </button>
              {mailMsg && (
                <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11.5, color: mailMsg.ok ? "#5cb85c" : "#e07070" }}>
                  {mailMsg.ok ? <CheckCircle2 size={13} /> : <AlertCircle size={13} />} {mailMsg.text}
                </span>
              )}
            </div>
          </div>
        )}

        {/* DB-Erklärung, wenn die Detailtabelle eine Deckungsbeitrags-Spalte hat */}
        {!loading && !error && columns.some(c => /^DB([ -]|$)/.test(c)) && (
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
