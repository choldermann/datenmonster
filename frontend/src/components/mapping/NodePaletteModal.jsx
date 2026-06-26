import { createPortal } from "react-dom";
import { X, CheckCircle } from "lucide-react";
import { S } from "./constants";

export const NODE_INFO = {
  transform: {
    desc: "Wandelt Feldwerte um — ideal für Formatierungen und Berechnungen vor der Ausgabe.",
    features: [
      "Zahlenformat: Dezimalstellen, Tausend- und Dezimaltrennzeichen",
      "Zahlenrechnung: +, −, ×, ÷, Modulo, Min, Max, AutoID",
      "Datumsformat: DE ↔ ISO ↔ US, beliebige Formate",
      "Datumsrechnung: Tag/Monat/Jahr/Stunde/Minute/Sekunde, AddDays, DaysDiff, Now",
      "Zeichenkette: Trim, GROSS/klein, Ersetzen, Prefix, Suffix",
      "Zeichenkette: Erste/Letzte N Zeichen, Von X bis Y, Aufteilen & Teil N, Länge, Umkehren",
      "Zeichenkette: Regex extrahieren (Gruppe N) oder ersetzen",
      "Verkettung: mehrere Quellfelder mit Trennzeichen zusammenführen",
    ],
    status: "Vollständig implementiert",
  },
  constant: {
    desc: "Erzeugt einen festen Wert als virtuelles Quellfeld — ohne Datenquelle.",
    features: [
      "Statischer Text oder Zahl",
      "Aktuelles Datum, Datum+Uhrzeit oder Jahr (zur Laufzeit)",
      "Zufällige UUID (v4)",
      "Boolean: true / false",
    ],
    status: "Vollständig implementiert",
  },
  sql: {
    desc: "Führt eine SQL-Abfrage auf einer gespeicherten Datenbankverbindung aus.",
    features: [
      "Scalar-Modus: liefert einen Wert pro Ausgabezeile (z. B. Lookup-Abfrage)",
      "Transform-Modus: ersetzt die gesamte Datenpipeline durch das SQL-Ergebnis",
      "Parameter aus Quellfeldern in der SQL via {{feldname}}",
      "Unterstützt MSSQL und MySQL Verbindungen",
    ],
    status: "Vollständig implementiert",
  },
  agg: {
    desc: "Aggregiert Werte über alle Zeilen der Datenpipeline zu einem Ergebnis.",
    features: [
      "SUM, COUNT, COUNT DISTINCT, AVG, MIN, MAX",
      "STDDEV, MEDIAN, FIRST, LAST",
      "GROUP BY: Gruppierung für spätere Joins",
      "Mehrere Aggregationen parallel in einem Node",
    ],
    status: "Vollständig implementiert",
  },
  rest: {
    desc: "Ruft für jede Zeile (oder als Batch) eine externe HTTP-API auf und mappt die Antwort.",
    features: [
      "GET und POST, beliebige URL mit {{feldname}}-Platzhaltern",
      "Auth: Bearer-Token, API-Key-Header, HTTP Basic",
      "JSON-Pfad zur Antwort (z. B. data.result.price)",
      "Batch-Modus: alle Schlüssel in einem einzigen API-Call zusammenfassen",
    ],
    status: "Vollständig implementiert",
  },
  lookup: {
    desc: "Sucht Werte aus einem anderen Dataset anhand eines Schlüsselfelds.",
    features: [
      "Schlüsselfeld aus der Pipeline gegen eine Spalte im Lookup-Dataset abgleichen",
      "Beliebig viele Ausgabefelder aus dem Lookup-Dataset übernehmen",
      "Verhalten bei fehlendem Wert: null, leer lassen oder festen Fallback",
    ],
    status: "Vollständig implementiert",
  },
  calc: {
    desc: "Berechnet fensterbasierte Werte über geordnete oder gruppierte Zeilen.",
    features: [
      "Kumulierte Summe (Cumsum) mit optionaler Gruppierung",
      "Gleitender Durchschnitt (Rolling Avg) mit konfigurierbarer Fenstergröße",
      "Rang (Rank) und Zeilennummer (Row Number)",
      "Prozentrang (Percent Rank) innerhalb der Gruppe",
    ],
    status: "Vollständig implementiert",
  },
  switch: {
    desc: "Wählt zur Laufzeit anhand von Bedingungen eine alternative Datenquelle aus.",
    features: [
      "Bedingung: Dataset hat Zeilen / hat keine Zeilen",
      "Bedingung: Zeilenzahl größer / kleiner als Schwellwert",
      "Fallback-Zweig (\"immer\") als letzter Ast",
      "Ausgabe-Felder des gewählten Datasets werden in die Pipeline eingefügt",
    ],
    status: "Vollständig implementiert",
  },
};

export default function NodePaletteModal({ info, onClose }) {
  if (!info) return null;

  const meta = NODE_INFO[info.type] || {};

  return createPortal(
    <div
      style={{ position: "fixed", inset: 0, zIndex: 9000, display: "flex", alignItems: "center", justifyContent: "center", backgroundColor: "rgba(0,0,0,0.55)" }}
      onClick={onClose}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{ width: 440, backgroundColor: S.bgCard, borderRadius: 10, border: `1px solid ${S.border}`, boxShadow: "0 20px 60px rgba(0,0,0,0.7)", overflow: "hidden" }}
      >
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "16px 20px", borderBottom: `1px solid ${S.border}`, backgroundColor: info.color + "12" }}>
          <div style={{ width: 38, height: 38, borderRadius: 8, backgroundColor: info.color + "22", border: `1px solid ${info.color}55`, display: "flex", alignItems: "center", justifyContent: "center", color: info.color, flexShrink: 0 }}>
            <info.Icon size={18} />
          </div>
          <div style={{ flex: 1 }}>
            <p style={{ fontSize: 14, fontWeight: 700, color: S.textBright, margin: 0 }}>{info.title}</p>
            <p style={{ fontSize: 11, color: info.color, margin: "2px 0 0", opacity: 0.85 }}>Node-Typ · Mapping Canvas</p>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: S.textDim, padding: 4, borderRadius: 4 }}
            onMouseEnter={e => e.currentTarget.style.color = S.textBright}
            onMouseLeave={e => e.currentTarget.style.color = S.textDim}>
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: "18px 20px" }}>
          <p style={{ fontSize: 13, color: S.textMain, lineHeight: 1.55, margin: "0 0 16px" }}>{meta.desc}</p>

          {meta.features?.length > 0 && (
            <div>
              <p style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: S.textDim, marginBottom: 8 }}>Funktionen</p>
              <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 6 }}>
                {meta.features.map((f, i) => (
                  <li key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                    <span style={{ color: info.color, flexShrink: 0, marginTop: 1 }}>▸</span>
                    <span style={{ fontSize: 12, color: S.textMain, lineHeight: 1.4 }}>{f}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {meta.status && (
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 16, padding: "7px 10px", borderRadius: 6, backgroundColor: "rgba(110,231,183,0.08)", border: "1px solid rgba(110,231,183,0.2)" }}>
              <CheckCircle size={13} style={{ color: "#6ee7b7", flexShrink: 0 }} />
              <span style={{ fontSize: 11, color: "#6ee7b7" }}>{meta.status}</span>
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, padding: "12px 20px", borderTop: `1px solid ${S.border}` }}>
          <button onClick={onClose}
            style={{ padding: "7px 14px", borderRadius: 5, border: `1px solid ${S.border}`, background: "none", color: S.textDim, fontSize: 12, cursor: "pointer" }}
            onMouseEnter={e => e.currentTarget.style.color = S.textBright}
            onMouseLeave={e => e.currentTarget.style.color = S.textDim}>
            Schließen
          </button>
          <button onClick={() => { info.onAdd(); onClose(); }}
            style={{ padding: "7px 16px", borderRadius: 5, border: `1px solid ${info.color}55`, backgroundColor: info.color + "20", color: info.color, fontSize: 12, fontWeight: 600, cursor: "pointer" }}
            onMouseEnter={e => e.currentTarget.style.backgroundColor = info.color + "35"}
            onMouseLeave={e => e.currentTarget.style.backgroundColor = info.color + "20"}>
            Auf Canvas hinzufügen
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
