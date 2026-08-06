import { Download } from "lucide-react";
import EmailTableButton from "../EmailTableButton";

const S = {
  bgEl: "var(--bg-elevated)", border: "var(--border)",
  textMain: "var(--text-main)", textDim: "var(--text-dim)", accent: "var(--accent)",
};

// Nur echte Zahlen mit deutschen Tausenderpunkten formatieren (6.000.000);
// numerische String-IDs (Artikel-/Rechnungsnr) bleiben unverändert.
function fmtCell(v) {
  if (v === null || v === undefined) return "";
  if (typeof v === "number") return v.toLocaleString("de-DE", { maximumFractionDigits: 2 });
  return String(v);
}

export default function TableWidget({ widget, result, allowDownload, onDrilldown, onAiAction }) {
  const cfg = widget.config || {};
  const dd = cfg.drilldown;
  const ai = cfg.ai_action;
  // Technische Spalten (z.B. kRechnung/kArtikel als Drilldown-Schlüssel) können
  // ausgeblendet werden – sie bleiben in den Zeilendaten für den Drilldown erhalten.
  const hidden = new Set(cfg.hidden_columns || []);
  const allColumns = result.columns || [];
  const columns = allColumns.filter(c => !hidden.has(c));
  const { rows = [], total } = result;
  // Zeilen sind klickbar, wenn eine KI-Aktion oder ein Detail-Mapping (+ Schlüsselspalte)
  // konfiguriert ist. KI-Aktion hat Vorrang, falls beides gesetzt wäre.
  const aiClickable = !!(onAiAction && ai?.mapping_id && ai?.key_column);
  const rowClickable = aiClickable || !!(onDrilldown && dd?.mapping_id && dd?.key_column);
  const clickRow = (row) => {
    if (aiClickable) {
      const v = row[ai.key_column];
      if (v === null || v === undefined || v === "") return;
      onAiAction(row);
      return;
    }
    if (!onDrilldown || !dd?.mapping_id || !dd?.key_column) return;
    const v = row[dd.key_column];
    if (v === null || v === undefined || v === "") return;
    onDrilldown(dd.key_column, v);
  };
  // Zahlenspalten rechtsbündig (bessere Lesbarkeit der Beträge).
  const numericCols = new Set(columns.filter(c => rows.some(r => typeof r[c] === "number")));
  if (!allColumns.length) return <p style={{ padding: "14px 16px", color: S.textDim, fontSize: 12 }}>Keine Daten</p>;

  const downloadCsv = () => {
    const header = columns.join(";");
    const body = rows.map(r =>
      columns.map(c => `"${(r[c] ?? "").toString().replace(/"/g, '""')}"`).join(";")
    ).join("\n");
    const blob = new Blob(["﻿" + header + "\n" + body], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${widget.label || "export"}.csv`;
    a.click();
  };

  const canDownload = allowDownload && !result.download_disabled;

  return (
    <div>
      {(total !== undefined || canDownload) && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "8px 16px", borderBottom: `1px solid ${S.border}` }}>
          {total !== undefined && <span style={{ fontSize: 11, color: S.textDim }}>{total} Zeilen</span>}
          {canDownload && (
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <EmailTableButton columns={columns} rows={rows} title={widget.label || "Tabelle"} disabled={!rows.length} />
              <button onClick={downloadCsv}
                style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11,
                  color: S.accent, background: "none", border: `1px solid ${S.border}`,
                  borderRadius: 5, padding: "4px 10px", cursor: "pointer" }}>
                <Download size={11} /> CSV
              </button>
            </div>
          )}
        </div>
      )}
      <div style={{ overflowX: "auto", maxHeight: 480 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr style={{ position: "sticky", top: 0, backgroundColor: S.bgEl }}>
              {columns.map(c => (
                <th key={c} style={{ padding: "8px 12px", textAlign: numericCols.has(c) ? "right" : "left",
                  borderBottom: `1px solid ${S.border}`, color: S.textDim,
                  fontWeight: 600, whiteSpace: "nowrap", fontSize: 11 }}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} onClick={() => clickRow(row)}
                style={{ borderBottom: `1px solid ${S.border}`, cursor: rowClickable ? "pointer" : "default" }}
                onMouseEnter={e => e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.025)"}
                onMouseLeave={e => e.currentTarget.style.backgroundColor = ""}>
                {columns.map(c => (
                  <td key={c} style={{ padding: "7px 12px", color: S.textMain,
                    textAlign: numericCols.has(c) ? "right" : "left" }}>{fmtCell(row[c])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
