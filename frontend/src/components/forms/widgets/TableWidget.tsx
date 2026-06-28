import { Download } from "lucide-react";

const S = {
  bgEl: "var(--bg-elevated)", border: "var(--border)",
  textMain: "var(--text-main)", textDim: "var(--text-dim)", accent: "var(--accent)",
};

export default function TableWidget({ widget, result, allowDownload }) {
  const { columns = [], rows = [], total } = result;
  if (!columns.length) return <p style={{ padding: "14px 16px", color: S.textDim, fontSize: 12 }}>Keine Daten</p>;

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
            <button onClick={downloadCsv}
              style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11,
                color: S.accent, background: "none", border: `1px solid ${S.border}`,
                borderRadius: 5, padding: "4px 10px", cursor: "pointer" }}>
              <Download size={11} /> CSV
            </button>
          )}
        </div>
      )}
      <div style={{ overflowX: "auto", maxHeight: 480 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr style={{ position: "sticky", top: 0, backgroundColor: S.bgEl }}>
              {columns.map(c => (
                <th key={c} style={{ padding: "8px 12px", textAlign: "left",
                  borderBottom: `1px solid ${S.border}`, color: S.textDim,
                  fontWeight: 600, whiteSpace: "nowrap", fontSize: 11 }}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} style={{ borderBottom: `1px solid ${S.border}` }}
                onMouseEnter={e => e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.025)"}
                onMouseLeave={e => e.currentTarget.style.backgroundColor = ""}>
                {columns.map(c => (
                  <td key={c} style={{ padding: "7px 12px", color: S.textMain }}>{row[c] ?? ""}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
