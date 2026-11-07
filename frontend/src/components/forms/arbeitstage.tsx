/**
 * Arbeitstage und Feiertage: Kalenderbereinigung von Monatswerten.
 *
 * Ein März mit 22 Arbeitstagen bringt im Großhandel mehr Umsatz als einer mit 20 – ohne dass
 * sich am Geschäft etwas geändert hat. Bereinigt wird wie bei den Statistikämtern: Wert ×
 * (übliche Arbeitstage dieses Kalendermonats ÷ tatsächliche Arbeitstage). Die Saison bleibt
 * erhalten (ein Dezember bleibt ein Dezember), nur die Abweichung vom üblichen Kalender fällt weg.
 * „Üblich“ = Mittel desselben Kalendermonats über 2015–2034 mit denselben Einstellungen.
 *
 * Feiertage werden berechnet (keine externe Quelle): gesetzliche Feiertage je Bundesland inkl.
 * der einmaligen (Reformationsjubiläum 2017, Tag der Befreiung in Berlin 2020 und 2025).
 * Nicht enthalten: Feiertage, die nur in Teilen eines Landes gelten (Mariä Himmelfahrt in
 * Bayern, Fronleichnam in Teilen Sachsens/Thüringens, Augsburger Friedensfest).
 *
 * Einstellung je Mandant unter /api/business-config/arbeitstage:
 *   { bundesland: "Bayern" | "" (nur bundesweite Feiertage), samstag: bool, halbe_tage: bool }
 *   halbe_tage: 24. und 31.12. zählen als halbe Arbeitstage.
 */
import { useEffect, useState } from "react";
import { CalendarDays, Settings2, X } from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import api, { fehlerText } from "../../api/client";

export const BUNDESLAENDER = ["Baden-Württemberg", "Bayern", "Berlin", "Brandenburg", "Bremen", "Hamburg", "Hessen",
  "Mecklenburg-Vorpommern", "Niedersachsen", "Nordrhein-Westfalen", "Rheinland-Pfalz", "Saarland", "Sachsen",
  "Sachsen-Anhalt", "Schleswig-Holstein", "Thüringen"];
const KURZ = { "Baden-Württemberg": "BW", Bayern: "BY", Berlin: "BE", Brandenburg: "BB", Bremen: "HB", Hamburg: "HH",
  Hessen: "HE", "Mecklenburg-Vorpommern": "MV", Niedersachsen: "NI", "Nordrhein-Westfalen": "NW", "Rheinland-Pfalz": "RP",
  Saarland: "SL", Sachsen: "SN", "Sachsen-Anhalt": "ST", "Schleswig-Holstein": "SH", "Thüringen": "TH" };

export type Einstellung = { bundesland?: string; samstag?: boolean; halbe_tage?: boolean };
export const STANDARD: Einstellung = { bundesland: "", samstag: false, halbe_tage: false };

// ── Kalender (rein) ──
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const tag = (j: number, m: number, t: number) => new Date(j, m - 1, t, 12);    // 12 Uhr: keine Sommerzeit-Kanten
const plus = (d: Date, n: number) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n, 12);

/** Ostersonntag (Gaußsche Osterformel, gregorianisch, anonymer Algorithmus). */
export function ostersonntag(j: number): Date {
  const a = j % 19, b = Math.floor(j / 100), c = j % 100, d = Math.floor(b / 4), e = b % 4;
  const f = Math.floor((b + 8) / 25), g = Math.floor((b - f + 1) / 3), h = (19 * a + b - d - g + 15) % 30;
  const i = Math.floor(c / 4), k = c % 4, l = (32 + 2 * e + 2 * i - h - k) % 7, m = Math.floor((a + 11 * h + 22 * l) / 451);
  const monat = Math.floor((h + l - 7 * m + 114) / 31), t = ((h + l - 7 * m + 114) % 31) + 1;
  return tag(j, monat, t);
}

/** Gesetzliche Feiertage eines Jahres; bundesland "" = nur die bundesweiten. */
export function feiertage(j: number, bundesland = ""): { datum: string; name: string }[] {
  const bl = KURZ[bundesland] || "";
  const in_ = (...xs: string[]) => !!bl && xs.includes(bl);
  const o = ostersonntag(j);
  const liste: [Date, string, boolean][] = [
    [tag(j, 1, 1), "Neujahr", true],
    [tag(j, 1, 6), "Heilige Drei Könige", in_("BW", "BY", "ST")],
    [tag(j, 3, 8), "Internationaler Frauentag", (bl === "BE" && j >= 2019) || (bl === "MV" && j >= 2023)],
    [plus(o, -2), "Karfreitag", true],
    [plus(o, 1), "Ostermontag", true],
    [tag(j, 5, 1), "Tag der Arbeit", true],
    [tag(j, 5, 8), "Tag der Befreiung", bl === "BE" && (j === 2020 || j === 2025)],
    [plus(o, 39), "Christi Himmelfahrt", true],
    [plus(o, 50), "Pfingstmontag", true],
    [plus(o, 60), "Fronleichnam", in_("BW", "BY", "HE", "NW", "RP", "SL")],
    [tag(j, 8, 15), "Mariä Himmelfahrt", in_("SL")],
    [tag(j, 9, 20), "Weltkindertag", bl === "TH" && j >= 2019],
    [tag(j, 10, 3), "Tag der Deutschen Einheit", true],
    [tag(j, 10, 31), "Reformationstag", j === 2017 || in_("BB", "MV", "SN", "ST", "TH") || (j >= 2018 && in_("HB", "HH", "NI", "SH"))],
    [tag(j, 11, 1), "Allerheiligen", in_("BW", "BY", "NW", "RP", "SL")],
    [bussUndBettag(j), "Buß- und Bettag", in_("SN")],
    [tag(j, 12, 25), "1. Weihnachtstag", true],
    [tag(j, 12, 26), "2. Weihnachtstag", true],
  ];
  return liste.filter(([, , gilt]) => gilt).map(([d, name]) => ({ datum: iso(d), name }));
}

/** Mittwoch vor dem 23. November. */
function bussUndBettag(j: number): Date {
  const d = tag(j, 11, 22);
  return plus(d, -((d.getDay() + 4) % 7));      // getDay: 3 = Mittwoch
}

const _cache = new Map<string, number>();
/** Arbeitstage eines Monats („2026-03“). */
export function arbeitstage(monat: string, e: Einstellung = STANDARD): number {
  const schl = `${monat}|${e.bundesland || ""}|${e.samstag ? 1 : 0}|${e.halbe_tage ? 1 : 0}`;
  const hit = _cache.get(schl);
  if (hit != null) return hit;
  const [j, m] = monat.split("-").map(Number);
  const frei = new Set(feiertage(j, e.bundesland || "").map((f) => f.datum));
  let n = 0;
  for (let d = tag(j, m, 1); d.getMonth() === m - 1; d = plus(d, 1)) {
    const wt = d.getDay();
    if (wt === 0 || (wt === 6 && !e.samstag) || frei.has(iso(d))) continue;
    n += e.halbe_tage && m === 12 && (d.getDate() === 24 || d.getDate() === 31) ? 0.5 : 1;
  }
  _cache.set(schl, n);
  return n;
}

/** Übliche Arbeitstage eines Kalendermonats (1–12): Mittel über 2015–2034. */
export function ueblicheArbeitstage(kalendermonat: number, e: Einstellung = STANDARD): number {
  let s = 0;
  for (let j = 2015; j <= 2034; j++) s += arbeitstage(`${j}-${String(kalendermonat).padStart(2, "0")}`, e);
  return s / 20;
}

/** Monat um `jahre` verschoben („2026-03“, -1 → „2025-03“). */
const jahrVersetzt = (monat: string, jahre: number) => `${Number(monat.slice(0, 4)) + jahre}${monat.slice(4, 7)}`;

/**
 * Bereinigter Wert: Wert × üblich(m) / tatsächlich(m). `versatz` in Jahren für Spalten wie
 * „UmsatzVorjahr“, deren Wert zu einem anderen Jahr gehört als die Achse.
 */
export function bereinigt(monat: string, wert: number | null, e: Einstellung = STANDARD, versatz = 0): number | null {
  if (wert == null || !/^\d{4}-\d{2}/.test(monat)) return wert;
  const m = jahrVersetzt(monat.slice(0, 7), versatz);
  const at = arbeitstage(m, e);
  if (!at) return wert;
  return Math.round((wert * ueblicheArbeitstage(Number(m.slice(5, 7)), e)) / at * 100) / 100;
}

export function einstellungText(e: Einstellung | null): string {
  const x = e || STANDARD;
  return `${x.bundesland || "nur bundesweite Feiertage"} · ${x.samstag ? "Mo–Sa" : "Mo–Fr"}${x.halbe_tage ? " · 24./31.12. halb" : ""}`;
}

// ── Einstellung je Mandant ──
const EVENT = "dm-arbeitstage-geaendert";
const cache = new Map<string, Promise<any>>();
const k = (projectId) => String(projectId ?? "ohne");

function laden(projectId, neu = false) {
  if (neu || !cache.has(k(projectId))) {
    const q = projectId != null ? `?project_id=${projectId}` : "";
    cache.set(k(projectId), api.get(`/api/business-config/arbeitstage${q}`).then((r) => r.data)
      .catch(() => ({ auswahl: null })));
  }
  return cache.get(k(projectId));
}

/** Einstellung des aktiven Mandanten; `gewaehlt` = false, solange niemand etwas festgelegt hat. */
export function useArbeitstage(projectId, aktiv = true) {
  const [stand, setStand] = useState<{ e: Einstellung; gewaehlt: boolean; mandantName: string | null } | null>(null);
  useEffect(() => {
    if (!aktiv) return;
    let lebt = true;
    const holen = (neu = false) => laden(projectId, neu).then((d) => {
      if (lebt) setStand({ e: { ...STANDARD, ...(d.auswahl || {}) }, gewaehlt: !!d.auswahl, mandantName: d.mandant_name || null });
    });
    holen();
    const bei = (ev) => { if (ev.detail === k(projectId)) holen(); };
    window.addEventListener(EVENT, bei);
    return () => { lebt = false; window.removeEventListener(EVENT, bei); };
  }, [projectId, aktiv]);
  return stand;
}

export async function arbeitstageSpeichern(projectId, e: Einstellung) {
  await api.put("/api/business-config/arbeitstage", { project_id: projectId ?? null, ...e });
  cache.delete(k(projectId));
  window.dispatchEvent(new CustomEvent(EVENT, { detail: k(projectId) }));
}

/** Schalter „Arbeitstage“ je Widget merken (nur Komfort, darf fehlen). */
export function schalterLesen(id: string): boolean {
  try { return localStorage.getItem(`dm-at-${id}`) === "1"; } catch { return false; }
}
export function schalterSchreiben(id: string, an: boolean) {
  try { localStorage.setItem(`dm-at-${id}`, an ? "1" : "0"); } catch { /* egal */ }
}

/** Einstellungsdialog mit Vorschau der Feiertage des laufenden Jahres. */
export function ArbeitstageDialog({ projectId, aktuell, mandantName, onClose }) {
  const [e, setE] = useState<Einstellung>({ ...STANDARD, ...(aktuell || {}) });
  const [fehler, setFehler] = useState("");
  const [laeuft, setLaeuft] = useState(false);
  const jahr = new Date().getFullYear();
  const fts = feiertage(jahr, e.bundesland || "");
  let summe = 0;
  for (let m = 1; m <= 12; m++) summe += arbeitstage(`${jahr}-${String(m).padStart(2, "0")}`, e);
  const speichern = async () => {
    setLaeuft(true); setFehler("");
    try { await arbeitstageSpeichern(projectId, e); onClose(); }
    catch (x) { setFehler(fehlerText(x)); setLaeuft(false); }
  };
  const knopf = { padding: "7px 14px", borderRadius: 6, fontSize: 13, cursor: "pointer", border: "1px solid var(--border)",
    background: "transparent", color: "var(--text-main)" };
  const zeile = { display: "flex", alignItems: "center", gap: 8, fontSize: 13 };
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 1000, background: "rgba(0,0,0,.45)",
      display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <div onClick={(x) => x.stopPropagation()} role="dialog" aria-label="Arbeitstage"
        style={{ width: "min(520px, 100%)", maxHeight: "85vh", overflowY: "auto", background: "var(--bg-card)", border: "1px solid var(--border)",
          borderRadius: 10, padding: 18, display: "flex", flexDirection: "column", gap: 12, color: "var(--text-main)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <strong style={{ fontSize: 15, color: "var(--text-bright)" }}>Arbeitstage</strong>
          <button onClick={onClose} aria-label="Schließen" style={{ ...knopf, padding: 4, border: "none" }}><X size={16} /></button>
        </div>
        <p style={{ margin: 0, fontSize: 12.5, color: "var(--text-dim)", lineHeight: 1.45 }}>
          Monate mit mehr Arbeitstagen bringen mehr Umsatz, ohne dass sich am Geschäft etwas ändert. Mit diesen Angaben rechnet
          das Cockpit den Kalender heraus. Gilt für {mandantName || "diesen Betrieb"}.
        </p>
        <label style={zeile}>
          <span style={{ width: 130 }}>Feiertage von</span>
          <select value={e.bundesland || ""} onChange={(x) => setE({ ...e, bundesland: x.target.value })}
            style={{ flex: 1, padding: "6px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg-elevated)", color: "var(--text-main)" }}>
            <option value="">nur bundesweite Feiertage</option>
            {BUNDESLAENDER.map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
        </label>
        <label style={zeile}>
          <input type="checkbox" checked={!!e.samstag} onChange={(x) => setE({ ...e, samstag: x.target.checked })} />
          Samstag ist Arbeitstag (Versand/Verkauf auch samstags)
        </label>
        <label style={zeile}>
          <input type="checkbox" checked={!!e.halbe_tage} onChange={(x) => setE({ ...e, halbe_tage: x.target.checked })} />
          24. und 31. Dezember als halbe Arbeitstage
        </label>
        <div style={{ fontSize: 12.5, border: "1px solid var(--border)", borderRadius: 8, padding: "8px 12px", lineHeight: 1.6 }}>
          <b>{jahr}: {String(summe).replace(".", ",")} Arbeitstage</b>
          <div style={{ color: "var(--text-dim)" }}>
            {fts.map((f) => `${f.datum.slice(8, 10)}.${f.datum.slice(5, 7)}. ${f.name}`).join(" · ")}
          </div>
        </div>
        {fehler && <span style={{ fontSize: 12.5, color: "var(--err-soft, var(--err))" }}>{fehler}</span>}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button onClick={onClose} style={knopf}>Abbrechen</button>
          <button onClick={speichern} disabled={laeuft}
            style={{ ...knopf, background: "var(--accent)", color: "var(--bg-main, #111)", border: "none", fontWeight: 600 }}>Speichern</button>
        </div>
      </div>
    </div>
  );
}

/**
 * Schalter „Arbeitstage“ für Diagramme mit Monatsachse (Linie, Balken).
 * `spalten`: { Spalte: Jahresversatz } oder "*" (alle Serien, Versatz 0 – z. B. Pivot-Balken).
 * Liefert Knopf, Dialog und Hinweiszeile fertig; `anwenden` bereinigt die Daten an Ort und Stelle.
 */
export function useArbeitstageSchalter({ widget, projectId, spalten, monatsachse }) {
  const { user } = useAuth();
  const stand = useArbeitstage(projectId, !!spalten);
  const [an, setAn] = useState(() => !!spalten && schalterLesen(widget.id));
  const [dialog, setDialog] = useState(false);
  const moeglich = !!spalten && monatsachse && !!stand;
  const aktiv = moeglich && an;
  const versatzVon = (col) => (spalten === "*" ? 0 : spalten?.[col] != null ? Number(spalten[col]) || 0 : null);

  const anwenden = (data, xCol, cols) => {
    if (!aktiv) return;
    for (const d of data) {
      const mo = String(d[xCol]).slice(0, 7);
      for (const col of cols) {
        const v = versatzVon(col);
        if (v != null) d[col] = bereinigt(mo, d[col], stand.e, v);
      }
    }
  };
  const name = (col) => (aktiv && versatzVon(col) != null ? `${col} (arbeitstagbereinigt)` : col);
  const hinweis = (label) => {
    if (!moeglich || !/^\d{4}-\d{2}/.test(String(label))) return null;
    const mo = String(label).slice(0, 7);
    const n = arbeitstage(mo, stand.e), u = ueblicheArbeitstage(Number(mo.slice(5, 7)), stand.e);
    return (
      <div style={{ marginTop: 4, color: "var(--text-dim)" }}>
        {String(n).replace(".", ",")} Arbeitstage (üblich {u.toFixed(1).replace(".", ",")})
      </div>
    );
  };
  const knopf = moeglich ? (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
      <button onClick={() => { setAn(!an); schalterSchreiben(widget.id, !an); }} aria-pressed={an}
        title={`Kalendereffekt herausrechnen: Wert × übliche ÷ tatsächliche Arbeitstage des Monats\n${einstellungText(stand.e)}`}
        style={{ display: "inline-flex", alignItems: "center", gap: 3, fontSize: 11.5, padding: "2px 8px", borderRadius: 5,
          border: "1px solid var(--border)", cursor: "pointer",
          background: an ? "color-mix(in srgb, var(--accent) 18%, transparent)" : "transparent",
          color: an ? "var(--text-bright)" : "var(--text-main)" }}>
        <CalendarDays size={11} /> Arbeitstage{an ? " bereinigt" : ""}
      </button>
      {!user?.is_portal_only && projectId != null && (
        <button onClick={() => setDialog(true)} aria-label="Arbeitstage einstellen"
          title={`Arbeitstage einstellen (${einstellungText(stand.gewaehlt ? stand.e : null)})`}
          style={{ display: "inline-flex", padding: 2, border: "none", background: "transparent", color: "var(--text-dim)", cursor: "pointer" }}>
          <Settings2 size={12} />
        </button>
      )}
    </span>
  ) : null;
  const dialogEl = dialog && stand ? (
    <ArbeitstageDialog projectId={projectId} aktuell={stand.gewaehlt ? stand.e : null} mandantName={stand.mandantName}
      onClose={() => setDialog(false)} />
  ) : null;
  return { moeglich, aktiv, anwenden, name, hinweis, knopf, dialog: dialogEl };
}
