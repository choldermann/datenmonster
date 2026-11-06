/**
 * Tabelle als Excel-Datei herunterladen. Das Backend baut die Datei (openpyxl, Zahlen als
 * Zahlen, Kopfzeile fixiert, Autofilter) aus genau den Zeilen und der Sortierung, die der
 * Aufrufer übergibt – gleiche Grundlage wie der CSV-Knopf daneben.
 * Gemeinsam für Tabellen-Kachel, Drilldown-Fenster und Rohtabellen.
 */
import api from "../../api/client";

export const dateiname = (text, ersatz = "export") =>
  String(text || "").replace(/[^\wäöüÄÖÜß .-]+/g, " ").replace(/\s+/g, " ").trim().slice(0, 80) || ersatz;

export async function tabelleAlsExcel({ titel, columns, rows, datei = null }) {
  const resp = await api.post("/api/forms/table-xlsx",
    { title: titel || "Tabelle", columns, rows }, { responseType: "blob" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(resp.data);
  a.download = `${dateiname(datei || titel)}.xlsx`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
