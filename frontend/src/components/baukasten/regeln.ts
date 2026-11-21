// Mapping-Baukasten: Steine, Regeln (welcher Stein wohin passt) und Adressen in der Kette.
// Die Regeln sind dieselben wie im Backend (app/services/baukasten/uebersetzer.py → pruefen).

export type Stein = Record<string, any> & { type: string };

export const ART: Record<string, { name: string; farbe: string; form: "hut" | "winkel" | "stein" | "trichter" | "deckel"; gruppe: string; text: string }> = {
  start:      { name: "Start", farbe: "#c99a12", form: "hut", gruppe: "Anfang", text: "Wann läuft die Auswertung?" },
  tabelle:    { name: "Aus Tabelle", farbe: "#2f6fd6", form: "winkel", gruppe: "Daten", text: "Alles im Winkel gilt für diese Tabelle" },
  join:       { name: "Dazuholen", farbe: "#6a4fd1", form: "winkel", gruppe: "Daten", text: "Zweite Tabelle im Winkel verknüpfen" },
  filter:     { name: "Nur wenn", farbe: "#11806f", form: "stein", gruppe: "Schritte", text: "Zeilen filtern – nach dem Trichter: Kennzahl prüfen" },
  rechnen:    { name: "Rechnen", farbe: "#b03c78", form: "stein", gruppe: "Schritte", text: "Neue Spalte aus zwei Werten – auch Tage seit einem Datum" },
  einteilen:  { name: "Einteilen", farbe: "#0f7c9c", form: "stein", gruppe: "Schritte", text: "Wenn … dann: Werte in Gruppen wie „groß/mittel/klein“" },
  verdichten: { name: "Zusammenfassen", farbe: "#d0640f", form: "trichter", gruppe: "Schritte", text: "Trichter: aus Zeilen werden Gruppen" },
  sortieren:  { name: "Sortieren", farbe: "#4c6b5c", form: "stein", gruppe: "Schritte", text: "Reihenfolge festlegen" },
  begrenzen:  { name: "Nur die ersten", farbe: "#4c6b5c", form: "stein", gruppe: "Schritte", text: "z. B. die Top 10" },
  ausgabe:    { name: "Ausgabe", farbe: "#c8402f", form: "deckel", gruppe: "Ende", text: "Ergebnis – immer der letzte Stein" },
};
export const PROFI_FARBE = "#6b7178";

export const OPS = ["=", "≠", ">", "<", "≥", "≤", "ist einer von", "enthält", "beginnt mit", "ist leer", "ist nicht leer", "im Jahr", "in den letzten Tagen", "im Zeitraum", "im Zeitraum + Vorjahr"];
export const OHNE_WERT = new Set(["ist leer", "ist nicht leer", "im Zeitraum", "im Zeitraum + Vorjahr"]);
export const RECHENARTEN = ["+", "−", "×", "÷", "Tage bis heute", "Tage zwischen"];

export function neu(t: string): Stein {
  switch (t) {
    case "start": return { type: "start", trigger: "Wenn das Cockpit öffnet" };
    case "tabelle": return { type: "tabelle", table: "", inner: [] };
    case "join": return { type: "join", table: "", links: "", rechts: "", inner: [] };
    case "filter": return { type: "filter", col: "", op: "=", val: "" };
    case "rechnen": return { type: "rechnen", name: "Neue Spalte", a: "", op: "÷", b: "" };
    case "einteilen": return { type: "einteilen", name: "Gruppe", col: "", regeln: [{ op: "≥", val: "", wert: "" }], sonst: "" };
    case "verdichten": return { type: "verdichten", by: ["", ""], aggs: [{ fn: "Summe", col: "" }, { fn: "Anzahl" }] };
    case "sortieren": return { type: "sortieren", col: "", dir: "absteigend" };
    case "begrenzen": return { type: "begrenzen", n: 10 };
    case "ausgabe": return { type: "ausgabe", target: "Tabelle im Cockpit" };
  }
  return { type: t };
}

// Adresse einer Liste: "" = oberste Ebene, "1" = Winkel von kette[1], "1.2" = Winkel von kette[1].inner[2]
export const liste = (wurzel: Stein[], key: string): Stein[] => {
  let l = wurzel;
  if (key === "") return l;
  for (const p of key.split(".").map(Number)) l = l[p].inner;
  return l;
};
export const kindKey = (key: string, i: number) => (key === "" ? String(i) : `${key}.${i}`);
export const blockId = (key: string, i: number) => (key === "" ? `:${i}` : `${key}:${i}`);

function gueltigInnen(l: Stein[], art: string): boolean {
  for (const b of l) {
    if (art === "tabelle" && !["filter", "join"].includes(b.type)) return false;
    if (art === "join" && b.type !== "filter") return false;
    if (b.type === "join" && !gueltigInnen(b.inner || [], "join")) return false;
  }
  return true;
}

export function gueltig(c: Stein[]): boolean {
  let tab = -1, verd = -1;
  for (let i = 0; i < c.length; i++) {
    const t = c[i].type;
    if (t === "start" && i !== 0) return false;
    if (t === "join") return false;
    if (t === "tabelle") { if (tab >= 0) return false; tab = i; if (!gueltigInnen(c[i].inner || [], "tabelle")) return false; }
    if (["rechnen", "einteilen", "sortieren", "begrenzen", "verdichten", "profi", "ausgabe", "filter"].includes(t) && tab < 0) return false;
    if (t === "filter" && verd < 0) return false;          // oben nur als Kennzahl-Prüfung nach dem Trichter
    if (t === "verdichten") { if (verd >= 0) return false; verd = i; }
    if (t === "ausgabe" && i !== c.length - 1) return false;
  }
  return true;
}

export type Nutzlast = { kind: "new"; type: string } | { kind: "move"; key: string; index: number };

/** Kette mit dem Stein an Stelle (key, i) – oder null, wenn er dort nicht passt. */
export function simuliere(kette: Stein[], n: Nutzlast, key: string, i: number): Stein[] | null {
  const c: Stein[] = structuredClone(kette);
  let ziel: Stein[];
  try { ziel = liste(c, key); } catch { return null; }
  if (!ziel) return null;
  if (n.kind === "new") ziel.splice(i, 0, neu(n.type));
  else {
    const eigen = kindKey(n.key, n.index);
    if (key === eigen || key.startsWith(eigen + ".")) return null;
    const quelle = liste(c, n.key);
    const [stein] = quelle.splice(n.index, 1);
    let j = i;
    if (quelle === ziel && i > n.index) j--;
    if (quelle === ziel && j === n.index) return null;
    ziel.splice(j, 0, stein);
  }
  return gueltig(c) ? c : null;
}

/** Alle Einfügestellen (für das Leuchten beim Ziehen). */
export function alleStellen(kette: Stein[]): [string, number][] {
  const aus: [string, number][] = [];
  const lauf = (l: Stein[], key: string) => {
    for (let i = 0; i <= l.length; i++) aus.push([key, i]);
    l.forEach((b, i) => { if (b.inner) lauf(b.inner, kindKey(key, i)); });
  };
  lauf(kette, "");
  return aus;
}

/** Wohin passt ein neuer Stein, wenn gerade ein Stein ausgewählt ist? Erst hinein (Winkel), dann darunter, sonst irgendwo. */
export function platzFuer(kette: Stein[], typ: string, auswahl: { key: string; i: number } | null):
  { key: string; i: number; wie: "hinein" | "darunter" | "anderswo" } | null {
  const n: Nutzlast = { kind: "new", type: typ };
  if (auswahl) {
    const b = liste(kette, auswahl.key)?.[auswahl.i];
    if (b?.inner) {
      const ck = kindKey(auswahl.key, auswahl.i);
      if (simuliere(kette, n, ck, b.inner.length)) return { key: ck, i: b.inner.length, wie: "hinein" };
    }
    if (simuliere(kette, n, auswahl.key, auswahl.i + 1)) return { key: auswahl.key, i: auswahl.i + 1, wie: "darunter" };
  }
  for (const [k, i] of alleStellen(kette).reverse()) if (simuliere(kette, n, k, i)) return { key: k, i, wie: "anderswo" };
  return null;
}
