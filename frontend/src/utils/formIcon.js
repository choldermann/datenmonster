// Das Sinnbild eines Formulars fuer das Portal.
//
// Das Feld `portal_config.icon` ist als **Emoji** gedacht und wird als Text
// gerendert. Steht dort stattdessen der Name eines Icons - wie es beim
// Unternehmensmonitor der Fall war ("shield-alert") -, stand dieser Name
// woertlich in der Kachel und im Kopf: "shield-alert Unternehmensmonitor".
//
// Diese Funktion nimmt beides an: ein Emoji wird durchgereicht, ein bekannter
// Name uebersetzt, alles Uebrige faellt auf das Standardzeichen zurueck -
// lieber ein neutrales Sinnbild als ein technischer Name in der Oberflaeche.

const NAME_ZU_EMOJI = {
  "shield-alert": "\u{1F6E1}\u{FE0F}", "shield": "\u{1F6E1}\u{FE0F}",
  "alert-triangle": "\u{26A0}\u{FE0F}", "bell": "\u{1F514}",
  "bar-chart": "\u{1F4CA}", "bar-chart-2": "\u{1F4CA}", "bar-chart-3": "\u{1F4CA}",
  "pie-chart": "\u{1F967}", "line-chart": "\u{1F4C8}",
  "trending-up": "\u{1F4C8}", "trending-down": "\u{1F4C9}",
  "package": "\u{1F4E6}", "warehouse": "\u{1F3ED}", "truck": "\u{1F69A}",
  "shopping-cart": "\u{1F6D2}", "receipt": "\u{1F9FE}", "file-text": "\u{1F4C4}",
  "clipboard-list": "\u{1F4CB}", "users": "\u{1F465}", "user": "\u{1F464}",
  "euro": "\u{1F4B6}", "wallet": "\u{1F4B0}", "coins": "\u{1FA99}",
  "activity": "\u{1F4C8}", "gauge": "\u{23F1}\u{FE0F}", "calendar": "\u{1F4C5}",
  "search": "\u{1F50D}", "settings": "\u{2699}\u{FE0F}", "database": "\u{1F5C4}\u{FE0F}",
  "stethoscope": "\u{1FA7A}",
};

const STANDARD = "\u{1F4CA}";

// Ein Emoji liegt ausserhalb des ASCII-Bereichs; ein Icon-Name besteht nur aus
// Kleinbuchstaben, Ziffern und Bindestrichen.
const istEmoji = (wert) => /[^\x00-\x7F]/.test(wert);

export function formIcon(wert) {
  const w = (wert || "").trim();
  if (!w) return STANDARD;
  if (istEmoji(w)) return w;
  return NAME_ZU_EMOJI[w.toLowerCase()] || STANDARD;
}

export default formIcon;
