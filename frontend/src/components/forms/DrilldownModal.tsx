import { X, Download, Search, Loader2, AlertCircle } from "lucide-react";

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
  if (typeof v === "number") return v.toLocaleString("de-DE", { maximumFractionDigits: 2 });
  // numerische Strings hübsch ausrichten/formatieren
  if (typeof v === "string" && v !== "" && !isNaN(Number(v)) && /^-?\d/.test(v))
    return Number(v).toLocaleString("de-DE", { maximumFractionDigits: 2 });
  return String(v);
}

function isNumericCol(col, rows) {
  return rows.some(r => {
    const v = r[col];
    return v != null && v !== "" && !isNaN(Number(v));
  });
}

export default function DrilldownModal({ title, field, value, rows = [], loading, error, onClose }) {
  const columns = rows.length ? Object.keys(rows[0]) : [];
  const numericCols = new Set(columns.filter(c => isNumericCol(c, rows)));

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
          width: "min(1000px, 92vw)", maxHeight: "85vh",
          backgroundColor: S.bgCard, border: `1px solid ${S.border}`, borderRadius: 10,
          display: "flex", flexDirection: "column", overflow: "hidden",
          boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
        }}
      >
        {/* Header */}
        <div style={{ padding: "12px 16px", borderBottom: `1px solid ${S.border}`, display: "flex", alignItems: "center", gap: 10 }}>
          <Search size={14} style={{ color: ACCENT, flexShrink: 0 }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <p style={{ fontSize: 13, fontWeight: 700, color: S.textBright, margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {title || "Drilldown"}
            </p>
            <p style={{ fontSize: 11, color: S.textDim, margin: "2px 0 0" }}>
              {field ? <><span style={{ color: S.textMain }}>{field}</span> = <span style={{ color: ACCENT }}>{String(value)}</span> · </> : null}
              {loading ? "lädt…" : `${rows.length.toLocaleString("de-DE")} Zeile${rows.length === 1 ? "" : "n"}`}
            </p>
          </div>
          <button onClick={handleExport} disabled={!rows.length}
            style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 10px", borderRadius: 4, fontSize: 11, fontWeight: 600, cursor: rows.length ? "pointer" : "not-allowed", border: `1px solid ${ACCENT}44`, backgroundColor: `${ACCENT}15`, color: ACCENT, opacity: rows.length ? 1 : 0.5 }}>
            <Download size={12} /> CSV
          </button>
          <button onClick={onClose} style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: 4 }}>
            <X size={16} />
          </button>
        </div>

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
                  <tr key={i} style={{ borderBottom: `1px solid ${S.border}`, backgroundColor: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.02)" }}>
                    {columns.map(c => (
                      <td key={c} style={{ padding: "5px 12px", color: numericCols.has(c) ? S.textBright : S.textMain, textAlign: numericCols.has(c) ? "right" : "left", whiteSpace: "nowrap" }}>
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
