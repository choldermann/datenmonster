// Gemeinsame Spaltensortierung für TableWidget und DrilldownModal.
//
// Datumswerte kommen aus den Abfragen meist als Text „31.08.2026“ (CONVERT … 104),
// teils mit Uhrzeit. Als Text verglichen stünde der 31.08. vor dem 30.09. – deshalb
// werden solche Werte vor dem Vergleich in „2026-08-31 …“ umgestellt.

const DE_DATUM = /^(\d{1,2})\.(\d{1,2})\.(\d{4})(.*)$/;

function datumsSchluessel(v) {
  const m = DE_DATUM.exec(String(v).trim());
  if (!m) return null;
  return `${m[3]}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}${m[4]}`;
}

const leer = (v) => v === null || v === undefined || v === "";

/** Zeilen nach `sort` ({col, dir}) ordnen. Zahlen numerisch, deutsche Datumsangaben
 *  chronologisch, sonst locale-Vergleich; Leerwerte immer ans Ende.
 *  `vorrang(row)` (optional) ordnet vor der Spalte – z. B. Sammelzeilen nach unten. */
export function sortiereZeilen(rows, sort, numericCols, vorrang = null) {
  if (!sort) return rows;
  const num = numericCols.has(sort.col);
  const dir = sort.dir === "asc" ? 1 : -1;
  // Datumsspalte nur, wenn ALLE gefüllten Werte wie ein Datum aussehen.
  const gefuellt = rows.map(r => r[sort.col]).filter(v => !leer(v));
  const datum = !num && gefuellt.length > 0 && gefuellt.every(v => datumsSchluessel(v) !== null);
  return [...rows].sort((a, b) => {
    if (vorrang) {
      const d = vorrang(a) - vorrang(b);
      if (d !== 0) return d;
    }
    const va = a[sort.col], vb = b[sort.col];
    if (leer(va) && leer(vb)) return 0;
    if (leer(va)) return 1;
    if (leer(vb)) return -1;
    if (num) return (Number(va) - Number(vb)) * dir;
    if (datum) return datumsSchluessel(va).localeCompare(datumsSchluessel(vb)) * dir;
    return String(va).localeCompare(String(vb), "de", { numeric: true }) * dir;
  });
}
