/**
 * JTL legt Artikeltexte als HTML ab. Zum Anzeigen im Cockpit machen wir daraus
 * reinen Text — fremdes HTML wird bewusst NICHT in die Seite gehängt.
 */
const ENTITAETEN = {
  amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " ", shy: "",
  auml: "ä", ouml: "ö", uuml: "ü", Auml: "Ä", Ouml: "Ö", Uuml: "Ü", szlig: "ß",
  sup2: "²", sup3: "³", frac12: "½", frac14: "¼", frac34: "¾", micro: "µ",
  euro: "€", deg: "°", plusmn: "±", times: "×", middot: "·", bull: "•",
  reg: "®", copy: "©", trade: "™",
  ndash: "–", mdash: "—", hellip: "…",
  laquo: "«", raquo: "»", bdquo: "„", ldquo: "“", rdquo: "”", lsquo: "‘", rsquo: "’",
};

/** Ein Durchgang: Markierungen raus, Sonderzeichen zurückübersetzen. */
function entkleiden(text) {
  return text
    .replace(/<\s*(script|style)\b[\s\S]*?<\s*\/\s*\1\s*>/gi, "")
    .replace(/<\s*li[^>]*>/gi, "• ")
    .replace(/<\s*(br|\/p|\/div|\/li|\/tr|\/h[1-6])\s*\/?>/gi, "\n")
    .replace(/<[^>]*>/g, "")
    // Gekürzte Texte enden mitten in einer Markierung (`<span style="…`) – der
    // Rest hat kein schließendes >, muss aber trotzdem weg. Ein „<" mit Leerzeichen
    // dahinter ist dagegen echter Text („Breite < 5 mm") und bleibt.
    .replace(/<\/?[a-z][^>]*$/i, "")
    .replace(/&#x([0-9a-f]+);/gi, (_, h) => String.fromCodePoint(parseInt(h, 16)))
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
    .replace(/&(\w+);/g, (ganz, name) => (name in ENTITAETEN ? ENTITAETEN[name] : ganz));
}

export function alsText(html) {
  if (!html) return "";
  // Zwei Durchgänge: manche Beschreibungen stecken doppelt kodiert in der Wawi
  // (`&lt;p&gt;…`) — erst das Entschlüsseln legt die Markierungen frei.
  let text = entkleiden(String(html));
  if (/<[a-z/][^>]*>/i.test(text)) text = entkleiden(text);
  return text
    .replace(/[ \t]+/g, " ")
    .replace(/ *\n */g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/** Kürzt auf ganze Wörter, damit die Vorschau nicht mitten im Wort abreißt. */
export function kuerzen(text, max) {
  if (!text || text.length <= max) return text || "";
  const schnitt = text.slice(0, max);
  const luecke = schnitt.lastIndexOf(" ");
  return (luecke > max * 0.6 ? schnitt.slice(0, luecke) : schnitt).trimEnd() + " …";
}
