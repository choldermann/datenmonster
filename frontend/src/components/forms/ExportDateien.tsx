import { useState, useEffect, useCallback } from "react";
import { Download, AlertCircle, Check, History, ChevronDown, ChevronRight, Trash2 } from "lucide-react";
import api, { fehlerText } from "../../api/client";

// Export-Aktionen (export_mapping) schreiben Dateien. Gemeinsam für Editor- und
// Portal-Runner: Datei direkt im Browser speichern, Ergebnis unabhängig vom
// aktiven Reiter zeigen und – im Portal – die bisherigen Exporte auflisten.
// Portal-Benutzer haben keinen Bereich „Exporte“; ohne das sähen sie die Datei nie.

const S = {
  bgMain: "var(--bg-main)", bgCard: "var(--bg-card)",
  border: "var(--border)", textBright: "var(--text-bright)", textDim: "var(--text-dim)",
};

/** Lädt eine Exportdatei und stößt den Browser-Download an. */
export async function ladeExportHerunter(fileId, fileName) {
  let resp;
  try {
    resp = await api.get(`/api/exports/${fileId}/download`, { responseType: "blob" });
  } catch (e) {
    // Bei responseType "blob" steckt auch die Fehlermeldung in einem Blob –
    // ohne Auspacken stünde nur „Download fehlgeschlagen“ da.
    const daten = e?.response?.data;
    if (daten instanceof Blob) {
      try { e.response.data = JSON.parse(await daten.text()); } catch { /* kein JSON */ }
    }
    throw e;
  }
  const url = URL.createObjectURL(resp.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName || `export_${fileId}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Alle Dateien eines Laufs – aus Export-Aktionen und aus Pipelines mit Dateizielen. */
export function exportDateienAus(results) {
  return Object.values(results || {})
    .filter(r => r && (r.kind === "export" || r.kind === "pipeline"))
    .flatMap(r => r.files || []);
}

/** Aktionen, deren Ergebnis Dateien liefert: Exporte immer, Pipelines nur mit Dateien. */
function dateiAktionen(actions, results) {
  return (actions || []).filter(a => results?.[a.id] && (a.type === "export_mapping"
    || (a.type === "run_pipeline" && (results[a.id].files || []).length > 0)));
}

/** True, wenn ein Lauf ausschließlich Export-/Pipeline-Ergebnisse geliefert hat (Knopf). */
export function nurExporte(results) {
  const r = Object.values(results || {});
  return r.length > 0 && r.every(x => x && (x.kind === "export" || x.kind === "pipeline"));
}

/** Ergebnis der Export-Aktionen eines Laufs – steht über den Reitern, nicht in einem. */
export function ExportErgebnisse({ actions, results, allowDownload = true, onDownload }) {
  const exportActions = dateiAktionen(actions, results);
  if (!exportActions.length) return null;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 16 }}>
      {exportActions.map(a => {
        const r = results[a.id];
        const files = r.files || [];
        // Ein Ziel kann scheitern, ohne dass der Lauf als Fehler gilt (z.B. fehlende
        // Beraternummer beim DATEV-Stapel) – dann muss der Grund sichtbar werden.
        const zielFehler = r.error ? []
          : (r.targets || []).filter(t => t.status === "error" && t.error).map(t => t.error);
        return (
          <div key={a.id} style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`,
            borderRadius: 10, padding: "12px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
            {r.error ? (
              <div style={{ display: "flex", alignItems: "center", gap: 8,
                color: "var(--err-soft)", fontSize: 13 }}>
                <AlertCircle size={14} /> {a.label || a.id}: {r.error}
              </div>
            ) : (files.length > 0 || zielFehler.length === 0) && (
              <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--ok)",
                fontSize: 13, fontWeight: 600 }}>
                <Check size={14} /> {a.label || "Export"} erzeugt · {r.kind === "pipeline"
                  ? `${files.length} ${files.length === 1 ? "Datei" : "Dateien"}`
                  : `${r.total ?? 0} Zeilen`}
                {allowDownload && files.length > 0 && (
                  <span style={{ color: S.textDim, fontWeight: 400, fontSize: 12 }}>
                    · Download gestartet
                  </span>
                )}
              </div>
            )}
            {zielFehler.map((t, i) => (
              <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 8,
                color: "var(--err-soft)", fontSize: 13 }}>
                <AlertCircle size={14} style={{ flexShrink: 0, marginTop: 2 }} /> {t}
              </div>
            ))}
            {!r.error && (files.length === 0 ? (
              zielFehler.length ? null
                : <span style={{ color: S.textDim, fontSize: 12 }}>Keine Dateien erzeugt.</span>
            ) : allowDownload ? (
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {files.map(f => (
                  <DateiKnopf key={f.id} datei={f} onDownload={onDownload} />
                ))}
              </div>
            ) : (
              <span style={{ color: S.textDim, fontSize: 12 }}>
                Download ist für dieses Formular deaktiviert.
              </span>
            ))}
          </div>
        );
      })}
    </div>
  );
}

function DateiKnopf({ datei, onDownload, untertitel = null }) {
  return (
    <button onClick={() => onDownload(datei.id, datei.file_name)}
      title="Erneut herunterladen"
      style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "7px 12px",
        background: S.bgMain, border: `1px solid ${S.border}`, borderRadius: 6,
        color: S.textBright, cursor: "pointer", fontSize: 12, textAlign: "left" }}>
      <Download size={13} /> {datei.file_name}
      {untertitel && <span style={{ color: S.textDim, fontSize: 11 }}>· {untertitel}</span>}
    </button>
  );
}

const kleinKnopf = {
  display: "inline-flex", alignItems: "center", padding: "4px 8px", borderRadius: 6,
  background: "none", border: `1px solid ${S.border}`, color: S.textBright,
  cursor: "pointer", fontSize: 12,
};

function zeitpunkt(iso) {
  if (!iso) return "";
  // Der Server liefert UTC ohne Zonenangabe – sonst stünde die Uhrzeit 1–2 h zu früh da.
  const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + "Z");
  return d.toLocaleString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit" });
}

/** Portal: die bisherigen Exporte dieses Formulars (nur eigene Dateien). */
export function ExportVerlauf({ slug, aktualisiert, onDownload }) {
  const [offen, setOffen] = useState(false);
  const [dateien, setDateien] = useState(null);
  const [fehler, setFehler] = useState(null);

  const laden = useCallback(() => {
    api.get(`/api/portal/forms/${slug}/exports`)
      .then(({ data }) => { setDateien(Array.isArray(data) ? data : []); setFehler(null); })
      .catch(e => setFehler(fehlerText(e)));
  }, [slug]);

  useEffect(() => { laden(); }, [laden, aktualisiert]);

  const [fragt, setFragt] = useState(null);   // id, deren Löschen gerade bestätigt wird
  const loeschen = async (id) => {
    try {
      await api.delete(`/api/exports/${id}`);
      setDateien(d => (d || []).filter(x => x.id !== id));
    } catch (e) { setFehler(fehlerText(e)); }
    finally { setFragt(null); }
  };

  if (dateien && dateien.length === 0 && !fehler) return null;
  return (
    <div style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`,
      borderRadius: 14, marginTop: 24, overflow: "hidden" }}>
      <button onClick={() => setOffen(o => !o)}
        style={{ width: "100%", display: "flex", alignItems: "center", gap: 8,
          padding: "12px 18px", background: "none", border: "none", cursor: "pointer",
          color: S.textBright, fontSize: 14, fontWeight: 700, textAlign: "left" }}>
        {offen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <History size={14} /> Bisherige Exporte
        {dateien && <span style={{ color: S.textDim, fontWeight: 400, fontSize: 12 }}>({dateien.length})</span>}
      </button>
      {offen && (
        <div style={{ borderTop: `1px solid ${S.border}`, padding: "10px 18px 14px" }}>
          {fehler ? (
            <span style={{ color: "var(--err-soft)", fontSize: 12 }}>{fehler}</span>
          ) : !dateien ? (
            <span style={{ color: S.textDim, fontSize: 12 }}>Lädt…</span>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <tbody>
                {dateien.map(f => (
                  <tr key={f.id} style={{ borderBottom: `1px solid ${S.border}` }}>
                    <td style={{ padding: "6px 0", color: S.textDim, whiteSpace: "nowrap", width: 1 }}>
                      {zeitpunkt(f.created_at)}
                    </td>
                    <td style={{ padding: "6px 12px" }}>
                      {f.vorhanden === false ? (
                        <span style={{ color: S.textDim }}>
                          {f.file_name} · <i>Datei nicht mehr auf dem Server</i>
                        </span>
                      ) : (
                        <DateiKnopf datei={f} onDownload={onDownload} untertitel={f.mapping_name} />
                      )}
                    </td>
                    <td style={{ padding: "6px 0", textAlign: "right", whiteSpace: "nowrap", width: 1 }}>
                      {fragt === f.id ? (
                        <span style={{ display: "inline-flex", gap: 6, alignItems: "center", fontSize: 12 }}>
                          <span style={{ color: S.textDim }}>Löschen?</span>
                          <button onClick={() => loeschen(f.id)}
                            style={{ ...kleinKnopf, color: "var(--err-soft)",
                              borderColor: "color-mix(in srgb, var(--err-soft) 40%, transparent)" }}>Ja</button>
                          <button onClick={() => setFragt(null)} style={kleinKnopf}>Nein</button>
                        </span>
                      ) : (
                        <button onClick={() => setFragt(f.id)} title="Export löschen"
                          style={{ ...kleinKnopf, border: "none", color: S.textDim }}>
                          <Trash2 size={13} />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
