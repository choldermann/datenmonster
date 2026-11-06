/**
 * Erzeugt public/lizenzen.txt: alle Bibliotheken, die ins Frontend ausgeliefert werden
 * (dependencies aus package.json samt ihren Abhängigkeiten), mit Lizenz und Lizenztext.
 *
 * Grund: MIT/ISC/BSD verlangen, dass Copyright-Vermerk und Lizenztext „in allen Kopien“
 * mitgehen – beim Minifizieren gehen die Kommentare verloren. Läuft vor jedem Build
 * (npm run build, auch im Docker-Image). Bei fehlendem Lizenztext bleibt der Eintrag
 * mit Hinweis stehen, der Build bricht nicht ab.
 */
import fs from "fs";
import path from "path";

const wurzel = process.cwd();
const paket = JSON.parse(fs.readFileSync(path.join(wurzel, "package.json"), "utf8"));
const LIZENZ_DATEI = /^(licen[cs]e|copying|notice)(\.(md|txt|markdown))?$/i;

// Paket so auflösen, wie Node es tut: erst neben dem Aufrufer, dann nach oben.
function finde(name, von) {
  let dir = von;
  while (true) {
    const p = path.join(dir, "node_modules", name, "package.json");
    if (fs.existsSync(p)) return path.dirname(p);
    const oben = path.dirname(dir);
    if (oben === dir || !oben.startsWith(wurzel)) return null;
    dir = oben;
  }
}

// Paket ohne Lizenzdatei: Standardtext der angegebenen Lizenz mit dem Autor aus package.json.
const MIT = (c) => `Copyright (c) ${c}\n\nPermission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:\n\nThe above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.\n\nTHE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.`;
const ISC = (c) => `Copyright (c) ${c}\n\nPermission to use, copy, modify, and/or distribute this software for any purpose with or without fee is hereby granted, provided that the above copyright notice and this permission notice appear in all copies.\n\nTHE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.`;
function standardText(lizenz, autor) {
  const c = autor || "die Autoren des Pakets";
  const teile = [];
  if (/\bMIT\b/.test(lizenz)) teile.push(MIT(c));
  if (/\bISC\b/.test(lizenz)) teile.push(ISC(c));
  return teile.length ? "(Keine Lizenzdatei im Paket; Standardtext der angegebenen Lizenz.)\n\n" + teile.join("\n\n") : "";
}

const gesehen = new Map();   // "name@version" -> Eintrag
const offen = Object.keys(paket.dependencies || {}).map((n) => [n, wurzel]);
while (offen.length) {
  const [name, von] = offen.shift();
  const dir = finde(name, von);
  if (!dir) continue;
  const pj = JSON.parse(fs.readFileSync(path.join(dir, "package.json"), "utf8"));
  const key = `${pj.name}@${pj.version}`;
  if (gesehen.has(key)) continue;
  const lizenz = typeof pj.license === "string" ? pj.license
    : pj.license?.type || (Array.isArray(pj.licenses) ? pj.licenses.map((l) => l.type || l).join(" OR ") : "unbekannt");
  const dateien = fs.readdirSync(dir).filter((f) => LIZENZ_DATEI.test(f)).sort();
  const autor = typeof pj.author === "string" ? pj.author : pj.author?.name || "";
  const text = dateien.map((f) => fs.readFileSync(path.join(dir, f), "utf8").trim()).join("\n\n")
    || standardText(lizenz, autor);
  gesehen.set(key, { name: pj.name, version: pj.version, lizenz, url: pj.homepage || pj.repository?.url || pj.repository || "", text });
  for (const n of Object.keys(pj.dependencies || {})) offen.push([n, dir]);
}

const eintraege = [...gesehen.values()].sort((a, b) => a.name.localeCompare(b.name));
const zaehlung = {};
for (const e of eintraege) zaehlung[e.lizenz] = (zaehlung[e.lizenz] || 0) + 1;

let out = "﻿Datenmonster – Lizenzen der verwendeten Open-Source-Bibliotheken (Frontend)\n";
out += "=".repeat(76) + "\n\n";
out += `Erzeugt beim Bauen aus package.json (${eintraege.length} Pakete). Lizenzen: `
  + Object.entries(zaehlung).sort((a, b) => b[1] - a[1]).map(([l, n]) => `${l} ${n}`).join(", ") + ".\n\n";
out += "Kartenumrisse: Natural Earth (naturalearthdata.com), gemeinfrei (public domain);\n"
  + "Weltkarte über das Paket world-atlas, Bundesländer aus „Admin 1 – States, Provinces“ 1:10m, vereinfacht.\n\n";
for (const e of eintraege) {
  out += "-".repeat(76) + "\n";
  out += `${e.name} ${e.version}\nLizenz: ${e.lizenz}\n${e.url ? `Quelle: ${String(e.url).replace(/^git\+/, "")}\n` : ""}\n`;
  out += (e.text || "(Kein Lizenztext im Paket enthalten – es gilt die oben genannte Lizenz.)") + "\n\n";
}
fs.mkdirSync(path.join(wurzel, "public"), { recursive: true });
fs.writeFileSync(path.join(wurzel, "public", "lizenzen.txt"), out);
console.log(`lizenzen.txt: ${eintraege.length} Pakete (${Object.entries(zaehlung).map(([l, n]) => `${l} ${n}`).join(", ")})`);
const ohne = eintraege.filter((e) => !e.text).map((e) => e.name);
if (ohne.length) console.log("  ohne Lizenztext im Paket:", ohne.join(", "));
