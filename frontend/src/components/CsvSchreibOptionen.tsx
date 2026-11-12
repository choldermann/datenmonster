// Gemeinsame CSV-Optionen beim Schreiben – Mapping-Ziel und Pipeline-FTP-Upload.
// Werte und Vorgaben entsprechen backend/app/services/csv_format.py (csv_optionen).

type Props = {
  opts: Record<string, any>;
  set: (k: string, v: any) => void;
  iS: React.CSSProperties;
  lS: React.CSSProperties;
  vorgabeTrenner?: string;
  vorgabeKodierung?: string;
  kompakt?: boolean;
};

export default function CsvSchreibOptionen({ opts, set, iS, lS, vorgabeTrenner = ";", vorgabeKodierung = "utf-8-sig", kompakt = false }: Props) {
  const gap = kompakt ? 6 : 10;
  const grid = { display: "grid", gridTemplateColumns: "1fr 1fr", gap } as React.CSSProperties;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap }}>
      <div style={grid}>
        <div>
          <label style={lS}>Trennzeichen</label>
          <select style={iS} value={opts.delimiter || vorgabeTrenner} onChange={(e) => set("delimiter", e.target.value)}>
            {[";", ",", "|", "\t"].map((d) => <option key={d} value={d}>{d === "\t" ? "Tab" : d}</option>)}
          </select>
        </div>
        <div>
          <label style={lS}>Zahlen</label>
          <select style={iS} value={opts.decimal || "."} onChange={(e) => set("decimal", e.target.value)}>
            <option value=".">{kompakt ? "1234.56" : "1234.56 (Punkt)"}</option>
            <option value=",">{kompakt ? "1234,56" : "1234,56 (Komma, Excel-DE)"}</option>
          </select>
        </div>
      </div>
      <div style={grid}>
        <div>
          <label style={lS}>Kodierung</label>
          <select style={iS} value={opts.encoding || vorgabeKodierung} onChange={(e) => set("encoding", e.target.value)}>
            <option value="utf-8-sig">{kompakt ? "UTF-8 BOM" : "UTF-8 mit BOM (Excel)"}</option>
            <option value="utf-8">{kompakt ? "UTF-8" : "UTF-8 ohne BOM"}</option>
            <option value="cp1252">{kompakt ? "ANSI" : "ANSI / Windows-1252"}</option>
          </select>
        </div>
        <div>
          <label style={lS}>{kompakt ? "Anführung" : "Anführungszeichen"}</label>
          <select style={iS} value={opts.quote || "minimal"} onChange={(e) => set("quote", e.target.value)}>
            <option value="minimal">{kompakt ? "wo nötig" : "nur wo nötig"}</option>
            <option value="text">{kompakt ? "um Text" : "um Text, nicht um Zahlen"}</option>
            <option value="alle">{kompakt ? "alle" : "um jedes Feld"}</option>
          </select>
        </div>
      </div>
      <div style={grid}>
        <div>
          <label style={lS}>Zeilenende</label>
          <select style={iS} value={opts.line_ending || "lf"} onChange={(e) => set("line_ending", e.target.value)}>
            <option value="lf">{kompakt ? "LF" : "LF (Linux, Standard)"}</option>
            <option value="crlf">{kompakt ? "CRLF" : "CRLF (Windows)"}</option>
          </select>
        </div>
        <div>
          <label style={lS}>Datumsformat</label>
          <select style={iS} value={opts.date_format || ""} onChange={(e) => set("date_format", e.target.value)}>
            <option value="">{kompakt ? "wie es ist" : "unverändert"}</option>
            <option value="%d.%m.%Y">12.11.2026</option>
            <option value="%d.%m.%Y %H:%M:%S">{kompakt ? "12.11.26 14:30" : "12.11.2026 14:30:00"}</option>
            <option value="%Y-%m-%d">{kompakt ? "2026-11-12" : "2026-11-12 (ISO)"}</option>
            <option value="%Y-%m-%d %H:%M:%S">{kompakt ? "ISO + Zeit" : "2026-11-12 14:30:00"}</option>
            <option value="%Y%m%d">20261112</option>
          </select>
        </div>
      </div>
      <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: kompakt ? 10 : 11, color: "var(--text-dim)", cursor: "pointer" }}>
        <input type="checkbox" checked={opts.header !== false} onChange={(e) => set("header", e.target.checked)} />
        Kopfzeile schreiben
      </label>
    </div>
  );
}
