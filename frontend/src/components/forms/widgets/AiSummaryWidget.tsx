import { useState, useEffect, useMemo } from "react";
import { Sparkles, Loader2, AlertCircle, AlertTriangle } from "lucide-react";
import api from "../../../api/client";
import { streamRequest } from "../../../services/aiService";
import { onAiProviderChange, getAiProvider } from "../../../services/aiProvider";

const S = {
  textMain: "var(--text-main)", textDim: "var(--text-dim)", accent: "var(--accent)",
};

// de-DE Zahlformatierung (Tausenderpunkt, Komma). money → auf ganze Euro gerundet.
function deNum(v, money = false) {
  const f = typeof v === "number" ? v : parseFloat(v);
  if (!isFinite(f)) return null;
  const s = new Intl.NumberFormat("de-DE", {
    maximumFractionDigits: money ? 0 : 1,
  }).format(f);
  return money ? `${s} €` : s;
}

function pctChange(cur, vj) {
  const c = parseFloat(cur), v = parseFloat(vj);
  if (!isFinite(c) || !isFinite(v) || v === 0) return null;
  const p = (100 * (c - v)) / v;
  return `${p >= 0 ? "+" : ""}${p.toFixed(1)} %`;
}

// Einheit einer KPI-Spalte grob aus dem (deutschen) Spaltennamen ableiten, damit
// die KI Euro/Prozent/Tage nicht verwechselt.
function unitFor(col) {
  const c = String(col).toLowerCase();
  if (/%|anteil|quote|marge/.test(c)) return "%";
  if (/tage|dso|zahldauer/.test(c)) return "Tage";
  if (/umsatz|kapital|offen|ertrag|db2|db ii|auftrag|einsatz|prognose|ytd|vorjahr|ladenh|versand|forderung|wert/.test(c)) return "€";
  return "";
}

function fmtVal(v, unit) {
  const money = unit === "€";
  const n = deNum(v, money);
  if (n == null) return "–";
  if (unit === "%") return `${n} %`;
  if (unit === "Tage") return `${n} Tage`;
  return n; // deNum(money) hängt bereits " €" an
}

function num(v) { const f = parseFloat(v); return isFinite(f) ? f : null; }
function pctNum(cur, vj) { const c = num(cur), v = num(vj); return (c == null || v == null || v === 0) ? null : (100 * (c - v)) / v; }
function signPct(p) { return p == null ? "–" : `${p >= 0 ? "+" : ""}${p.toFixed(1)} %`; }

// Deterministische Bewertung "gut / verbesserungswürdig" je Cockpit-Bereich – direkt
// aus den (strukturierten) KPI-Ergebnissen aller Reiter. Bewusst NICHT vom LLM: so ist
// die Tabelle immer vorhanden, korrekt und stabil; das Modell schreibt nur die Prosa.
function buildAssessment(results) {
  const rowsOf = id => (results?.[id]?.rows) || [];
  const one = id => rowsOf(id)[0] || null;
  const out = [];

  const ov = one("act_overview_kpi");
  if (ov) {
    const p = pctNum(ov.Umsatz, ov.UmsatzVJ);
    out.push({ bereich: "Ertragslage", good: (p == null || p >= 0),
      kommentar: `Umsatz ${signPct(p)} ggü. Vorjahr, DB II-Marge ${deNum(ov.DB2Marge)} %` });
  }
  const kk = one("act_kunden_kpi");
  const decl = rowsOf("act_kunden_rueckgang");
  if (kk || decl.length) {
    const ap = ov ? pctNum(ov.AktiveKunden, ov.AktiveKundenVJ) : null;
    const declSum = decl.reduce((a, r) => a + (num(r.Rueckgang) || 0), 0);
    const good = (ap == null || ap >= 0) && decl.length <= 5;
    out.push({ bereich: "Kunden", good,
      kommentar: `${kk?.Neukunden != null ? deNum(kk.Neukunden) + " Neukunden, " : ""}${decl.length} Kunden rückläufig (−${deNum(declSum, true)})` });
  }
  const zm = one("act_zm_kpi"), op = one("act_op_kpi");
  if (zm || op) {
    const zd = zm ? num(zm.ZahldauerTage) : null, zdv = zm ? num(zm.ZahldauerTageVJ) : null;
    const uq = op ? num(op.UeberfaelligQuote) : null;
    const good = (zd == null || zdv == null || zd <= zdv) && (uq == null || uq < 25);
    const parts = [];
    if (op) { parts.push(`überfällig ${deNum(op.UeberfaelligQuote)} %`); if (op.DSO != null) parts.push(`DSO ${deNum(op.DSO)}`); }
    if (zm) parts.push(`Zahldauer ${deNum(zm.ZahldauerTage)} Tage`);
    out.push({ bereich: "Liquidität", good, kommentar: parts.join(", ") });
  }
  const kap = one("act_kapital_kpi");
  if (kap) {
    const bind = num(kap.Kapitalbindung), lh = num(kap.LadenhueterKapital);
    const share = (bind && lh != null) ? lh / bind : null;
    out.push({ bereich: "Kapital & Lager", good: (share == null || share < 0.15),
      kommentar: `${deNum(kap.Kapitalbindung, true)} gebunden, davon ${deNum(kap.LadenhueterKapital, true)} Ladenhüter` });
  }
  const kl = one("act_klumpen_kpi");
  if (kl) {
    const t5 = num(kl.Top5KundenAnteil);
    out.push({ bereich: "Risiko", good: (t5 == null || t5 < 30),
      kommentar: `Top-5-Kunden ${deNum(kl.Top5KundenAnteil)} %, Top-10 ${deNum(kl.Top10KundenAnteil)} %` });
  }
  const fc = one("act_forecast");
  const churnN = rowsOf("act_churn").length;
  if (fc) {
    const pv = num(fc["Prognose vs VJ %"]);
    out.push({ bereich: "Ausblick", good: (pv == null || pv >= 0),
      kommentar: `Prognose ${signPct(pv)} ggü. Vorjahr${churnN ? `, ${churnN} schlafende Kunden` : ""}` });
  }
  // ── Lager-Cockpit ──────────────────────────────────────────────────────────
  // Greift nur, wenn die Lager-Actions Ergebnisse geliefert haben; die Schwellen
  // stehen bewusst hier (nicht im LLM), damit die Tabelle stabil und nachvollziehbar
  // bleibt. Spiegelbild in cockpit_report._assessment_rows (PDF).
  const lg = one("act_lg_kpi");
  if (lg) {
    const p = pctNum(lg.Lagerwert, lg.LagerwertVJ);
    // Bestandsaufbau bis 10 % ggü. Vorjahr gilt als normal, darüber bindet er Kapital.
    out.push({ bereich: "Lagerbestand", good: (p == null || p <= 10),
      kommentar: `${deNum(lg.Lagerwert, true)} zum historischen EK (${signPct(p)} ggü. Vorjahr)`
        + (num(lg.OhneHistorischenEK) ? `, ${deNum(lg.OhneHistorischenEK)} Artikel ohne gebuchten EK` : "") });
  }
  const dp = one("act_lg_dispo_kpi");
  if (dp) {
    const fehl = num(dp.ArtikelFehlmenge) || 0;
    const basis = lg ? num(lg.ArtikelMitBestand) : null;
    const quote = basis ? (100 * fehl) / basis : null;
    const good = (num(dp.NegativerBestand) || 0) === 0 && (quote == null || quote < 5);
    out.push({ bereich: "Disposition", good,
      kommentar: `${deNum(dp.ArtikelFehlmenge)} Artikel mit Fehlmenge (${deNum(dp.WertFehlmenge, true)})`
        + (num(dp.NegativerBestand) ? `, ${deNum(dp.NegativerBestand)} mit negativem Bestand` : "") });
  }
  const um = one("act_lg_umschlag_kpi");
  if (um) {
    const rw = num(um.ReichweiteTage);
    // Reichweite über einem halben Jahr = träges Lager.
    out.push({ bereich: "Umschlag", good: (rw == null || rw <= 180),
      kommentar: `Ø ${deNum(um.UmschlagDurchschnitt)} Umschläge/Jahr, Reichweite ${deNum(um.ReichweiteTage)} Tage, `
        + `${deNum(um.OhneAbgang12M)} Artikel ohne Abgang (${deNum(um.KapitalOhneAbgang, true)})` });
  }
  const lh = one("act_lg_lh_kpi");
  if (lh) {
    const anteil = num(lh["Anteil am Lagerwert %"]);
    out.push({ bereich: "Ladenhüter", good: (anteil == null || anteil < 15),
      kommentar: `${deNum(lh.Ladenhueter)} Ladenhüter, ${deNum(lh.GebundenesKapital, true)} gebunden `
        + `(${deNum(lh["Anteil am Lagerwert %"])} % des Lagerwerts)` });
  }
  const sw = one("act_lg_schwund_kpi");
  if (sw) {
    const wert = Math.abs(num(sw.WertNetto) || 0);
    const basis = lg ? num(lg.Lagerwert) : null;
    // Korrekturen über 1 % des Lagerwerts deuten auf Bestandsführungsprobleme.
    const good = !basis || wert / basis < 0.01;
    out.push({ bereich: "Inventur & Schwund", good,
      kommentar: `${deNum(sw.Buchungen)} Korrekturbuchungen, netto ${deNum(sw.WertNetto, true)}`
        + (num(sw.BetroffeneArtikel) ? `, ${deNum(sw.BetroffeneArtikel)} Artikel betroffen` : "") });
  }

  // ── Vertriebs-Cockpit ──────────────────────────────────────────────────────
  // Schwellen identisch zu _assessment_rows in cockpit_report.py (PDF).
  const ve = one("act_ve_kpi");
  if (ve) {
    const p = pctNum(ve.Auftragseingang, ve.AuftragseingangVJ);
    out.push({ bereich: "Auftragseingang", good: (p == null || p >= 0),
      kommentar: `${deNum(ve.Auftragseingang, true)} (${signPct(p)} ggü. Vorjahr), Ø Auftrag ${deNum(ve.AvgAuftrag, true)}`
        + (ve.StornoQuote != null ? `, Storno ${deNum(ve.StornoQuote)} %` : "") });
  }
  const ag = one("act_ve_angebot_kpi");
  if (ag) {
    const cq = num(ag.ConversionQuote);
    // Unter einem Drittel gewonnener Angebote lohnt der Blick auf die Nachfassliste.
    out.push({ bereich: "Angebote", good: (cq == null || cq >= 33),
      kommentar: `${deNum(ag.Angebote)} Angebote über ${deNum(ag.Angebotsvolumen, true)}, Conversion ${deNum(ag.ConversionQuote)} %` });
  }
  const veDecl = rowsOf("act_ve_rueckgang");
  const veChurn = rowsOf("act_ve_churn");
  if (veDecl.length || veChurn.length) {
    const summe = veDecl.reduce((a, r) => a + (num(r.Rueckgang) || 0), 0);
    out.push({ bereich: "Kundenbindung", good: veDecl.length <= 5,
      kommentar: `${veDecl.length} Kunden rückläufig (−${deNum(summe, true)})`
        + (veChurn.length ? `, ${veChurn.length} schlafende Kunden` : "") });
  }

  // ── Einkaufs-Cockpit ───────────────────────────────────────────────────────
  const ek = one("act_ek_kpi");
  if (ek) {
    const p = pctNum(ek.Bestellvolumen, ek.BestellvolumenVJ);
    out.push({ bereich: "Einkaufsvolumen", good: (p == null || p <= 10),
      kommentar: `${deNum(ek.Bestellvolumen, true)} (${signPct(p)} ggü. Vorjahr) bei ${deNum(ek.Lieferanten)} Lieferanten` });
  }
  const tt = one("act_ek_termintreue_kpi");
  if (tt) {
    const q = num(tt.TermintreueQuote);
    out.push({ bereich: "Termintreue", good: (q == null || q >= 80),
      kommentar: `${deNum(tt.TermintreueQuote)} % pünktlich bei ${deNum(tt.Lieferungen)} Lieferungen, `
        + `Ø Verzug ${deNum(tt.AvgVerzugTage)} Tage` });
  }
  const eo = one("act_ek_offen_kpi");
  if (eo) {
    const offen = num(eo.OffeneBestellungen) || 0, ueber = num(eo.Ueberfaellig) || 0;
    const anteil = offen ? (100 * ueber) / offen : null;
    out.push({ bereich: "Offene Bestellungen", good: (anteil == null || anteil < 20),
      kommentar: `${deNum(offen)} offen (${deNum(eo.OffenerWert, true)}), davon ${deNum(ueber)} überfällig` });
  }
  const er = one("act_ek_er_kpi");
  if (er) {
    const offenN = num(er.OffeneRechnungen) || 0, ueberN = num(er.Ueberfaellig) || 0;
    const anteil = offenN ? (100 * ueberN) / offenN : null;
    out.push({ bereich: "Verbindlichkeiten", good: (anteil == null || anteil < 10),
      kommentar: `${deNum(er.OffeneVerbindlichkeiten, true)} offen (${deNum(offenN)} Rechnungen), davon ${deNum(ueberN)} überfällig` });
  }

  // ── Versand-Cockpit ────────────────────────────────────────────────────────
  const vs = one("act_vs_kpi");
  if (vs) {
    const d = num(vs.AvgDauerStunden), dvj = num(vs.AvgDauerStundenVJ);
    // Schneller als im Vorjahr oder unter zwei Tagen = in Ordnung.
    const good = d == null || (dvj != null && d <= dvj) || d <= 48;
    const p = pctNum(vs.Sendungen, vs.SendungenVJ);
    out.push({ bereich: "Versandvolumen", good,
      kommentar: `${deNum(vs.Sendungen)} Sendungen (${signPct(p)} ggü. Vorjahr), Ø Laufzeit ${deNum(d)} h`
        + (dvj != null ? ` (VJ ${deNum(dvj)} h)` : "") });
  }
  const vd = one("act_vs_dauer_kpi");
  if (vd) {
    const q48 = num(vd.Bis48hQuote);
    out.push({ bereich: "Lieferzeit", good: (q48 == null || q48 >= 80),
      kommentar: `${deNum(vd.SelberTagQuote)} % am selben Tag, ${deNum(vd.Bis48hQuote)} % binnen 48 h, `
        + `${deNum(vd.Ueber72h)} Sendungen über 72 h` });
  }
  const vt = one("act_vs_tracking_kpi");
  if (vt) {
    const q = num(vt.TrackingQuote);
    out.push({ bereich: "Sendungsverfolgung", good: (q == null || q >= 90),
      kommentar: `Tracking bei ${deNum(vt.TrackingQuote)} % der Sendungen, ${deNum(vt.OhneTracking)} ohne Nummer` });
  }

  // ── Stammdaten-Health-Check ────────────────────────────────────────────────
  // Momentaufnahme ohne Vorjahresvergleich: bewertet werden Lückenquoten, nicht
  // Veränderungen. Schwellen identisch zu _assessment_rows in cockpit_report.py.
  const hc = one("act_hc_kpi");
  if (hc) {
    const chk = {};                                  // check_key → Anzahl (Ampel-Übersicht)
    rowsOf("act_hc_summary").forEach(r => { chk[r.check_key] = num(r.Anzahl) || 0; });
    const gap = {};                                  // Feld → Lückenanteil in %
    rowsOf("act_hc_luecken").forEach(r => { gap[r.Feld] = num(r.Anteil); });
    const LUECKE_OK = 5;                             // bis 5 % fehlende Werte je Feld

    const voll = num(hc.Vollstaendigkeit);
    out.push({ bereich: "Vollständigkeit", good: (voll == null || voll >= 90),
      kommentar: `${deNum(voll)} % der Artikel ohne Lücke `
        + `(${deNum(hc.ArtikelMitLuecke)} von ${deNum(hc.AktiveArtikel)} unvollständig)` });

    const eanAnteil = gap["EAN/Barcode"], eanDop = chk.ean_doppelt;
    out.push({ bereich: "EAN & Eindeutigkeit",
      good: (eanAnteil == null || eanAnteil <= LUECKE_OK) && !eanDop,
      kommentar: `${deNum(chk.artikel_ohne_ean)} Artikel ohne EAN (${deNum(eanAnteil)} %)`
        + (eanDop ? `, ${deNum(eanDop)} mehrfach vergebene EAN` : "") });

    const ekAnteil = gap["Einkaufspreis"], verlust = chk.artikel_vk_unter_ek || 0;
    // VK unter EK ist kein Lückenproblem, sondern ein Verlustgeschäft – jeder Fall zählt.
    out.push({ bereich: "Preise & Marge",
      good: (ekAnteil == null || ekAnteil <= LUECKE_OK) && verlust === 0,
      kommentar: `${deNum(chk.artikel_ohne_ek)} Artikel ohne Einkaufspreis (${deNum(ekAnteil)} %)`
        + `, ${deNum(verlust)} mit VK unter EK` });

    const taric = gap["Warentarifnummer"], herk = gap["Herkunftsland"];
    out.push({ bereich: "Außenhandel",
      good: (taric == null || taric <= LUECKE_OK) && (herk == null || herk <= LUECKE_OK),
      kommentar: `${deNum(chk.artikel_ohne_taric)} ohne Warentarifnummer (${deNum(taric)} %), `
        + `${deNum(chk.artikel_ohne_herkunftsland)} ohne Herkunftsland (${deNum(herk)} %)` });

    const gew = gap["Gewicht"], ohneName = chk.artikel_ohne_name || 0;
    out.push({ bereich: "Logistik & Struktur",
      good: (gew == null || gew <= LUECKE_OK) && ohneName === 0,
      kommentar: `${deNum(chk.artikel_ohne_gewicht)} Artikel ohne Gewicht (${deNum(gew)} %), `
        + `${deNum(chk.artikel_ohne_warengruppe)} ohne Warengruppe`
        + (ohneName ? `, ${deNum(ohneName)} ohne Bezeichnung` : "") });

    const kunden = num(hc.AktiveKunden), ohneMail = num(hc.KundenOhneMail) || 0;
    const mailQuote = kunden ? (100 * ohneMail) / kunden : null;
    // Ohne E-Mail keine Versandbenachrichtigung und keine digitale Rechnung –
    // bis zu einem Fünftel der Kunden ist im B2B-Bestand aber üblich.
    out.push({ bereich: "Kundenstamm", good: (mailQuote == null || mailQuote <= 20),
      kommentar: `${deNum(ohneMail)} von ${deNum(kunden)} Kunden ohne E-Mail (${deNum(mailQuote)} %)`
        + (chk.kunden_dubletten ? `, ${deNum(chk.kunden_dubletten)} mögliche Dubletten` : "") });
  }

  const rt = one("act_retouren_kpi");
  if (rt) {
    const q = num(rt.Quote), qvj = num(rt.QuoteVJ);
    // Eine niedrige Retourenquote ist generell gut (absolut, < 5 %); erst darüber
    // zählt zusätzlich, ob sie ggü. Vorjahr nicht gestiegen ist. So wird eine winzige
    // Quote (z.B. 0,4 %) nicht wegen eines minimalen VJ-Anstiegs als schlecht markiert.
    const RET_QUOTE_OK = 5;
    const good = (q == null) || (q < RET_QUOTE_OK) || (qvj != null && q <= qvj);
    const chg = pctNum(q, qvj);
    out.push({ bereich: "Retouren", good,
      kommentar: `Retourenquote ${deNum(rt.Quote)} % (VJ ${deNum(rt.QuoteVJ)} %${chg != null ? `, ${signPct(chg)}` : ""}), `
        + `Wert ${deNum(rt.Wert, true)}` });
  }
  return out;
}

// Generische KPI-Zeile (eine Ergebniszeile) vorformatieren: "Name: Wert (VJ …, ±%)".
// Vorjahreswerte werden über die Spalte Name+"VJ" gepaart und übersprungen.
function buildKpiText(rows) {
  if (!Array.isArray(rows) || rows.length === 0) return "";
  const row = rows[0];
  const keys = Object.keys(row);
  const vjKeys = new Set(keys.filter(k => /vj$/i.test(k)));
  const lines = [];
  for (const k of keys) {
    if (vjKeys.has(k)) continue;
    if (/^kkunde$|^kartikel$/i.test(k)) continue;
    const unit = unitFor(k);
    let line = `${k}: ${fmtVal(row[k], unit)}`;
    const vj = row[k + "VJ"];
    const chg = vj != null ? pctChange(row[k], vj) : null;
    if (vj != null && chg) line += ` (VJ ${fmtVal(vj, unit)}, ${chg})`;
    lines.push(line);
  }
  return lines.join("\n");
}

// Baut aus einem Action-Ergebnis (rows) einen kompakten, vorformatierten Kurztext.
// Die KI rechnet nichts nach – sie webt diese Texte nur in die Lagebeurteilung ein.
// `deep` (Detailgrad "ausführlich") gibt mehr Beispielzeilen mit: das große Modell
// erkennt Muster über viele Zeilen, statt nur Summen nachzuerzählen.
function buildSectionText(kind, rows, deep = false) {
  if (!Array.isArray(rows) || rows.length === 0) return "";
  const EX = deep ? 8 : 2;      // Beispiele je Themenblock

  if (kind === "kpi") return buildKpiText(rows);

  if (kind === "churn") {
    const sum = rows.reduce((a, r) => a + (parseFloat(r["Umsatz 24M"]) || 0), 0);
    const ex = rows.slice(0, EX).map(r => {
      const tage = parseFloat(r["Tage inaktiv"]);
      const t = isFinite(tage) ? `, ${deNum(tage)} Tage inaktiv` : "";
      return `${r.Kunde} (${deNum(r["Umsatz 24M"], true)}${t})`;
    }).join(", ");
    return `${rows.length} früher regelmäßige Kunden sind inaktiv geworden, zusammen ${deNum(sum, true)} Umsatz (24 Monate).`
      + (ex ? ` Beispiele: ${ex}.` : "");
  }

  if (kind === "platform") {
    // Nur Plattformen mit Umsatz im Zeitraum; Entwicklung ggü. Vorjahr.
    const withRev = rows.filter(r => parseFloat(r.Umsatz) > 0).slice(0, deep ? 15 : 6);
    if (!withRev.length) return "";
    return withRev.map(r => {
      const chg = pctChange(r.Umsatz, r.UmsatzVJ);
      const marge = r["DB-Marge %"];
      let line = `${r.Plattform}: ${deNum(r.Umsatz, true)}`;
      if (r.UmsatzVJ != null) line += ` (VJ ${deNum(r.UmsatzVJ, true)}${chg ? `, ${chg}` : ""})`;
      if (marge != null && isFinite(parseFloat(marge))) line += `, DB-Marge ${deNum(marge)} %`;
      return line;
    }).join("\n");
  }

  if (kind === "decline") {
    // Kunden mit rückläufigem Umsatz (Rueckgang = UmsatzVJ − Umsatz, absteigend).
    const sum = rows.reduce((a, r) => a + (parseFloat(r.Rueckgang) || 0), 0);
    const ex = rows.slice(0, EX)
      .map(r => `${r.Kunde} (−${deNum(r.Rueckgang, true)})`).join(", ");
    return `${rows.length} Kunden mit rückläufigem Umsatz, zusammen −${deNum(sum, true)} gegenüber dem Vorjahr.`
      + (ex ? ` Beispiele: ${ex}.` : "");
  }

  if (kind === "ladenhueter") {
    const sum = rows.reduce((a, r) => a + (parseFloat(r.Kapitalbindung) || 0), 0);
    const ex = rows.slice(0, EX).map(r => {
      const tage = parseFloat(r.TageOhneVerkauf);
      const t = isFinite(tage) && tage < 9999 ? `, ${deNum(tage)} Tage ohne Verkauf` : ", kein Verkauf erfasst";
      return `${r.Artikel} (${deNum(r.Kapitalbindung, true)}${t})`;
    }).join(", ");
    return `${rows.length} Ladenhüter binden zusammen ${deNum(sum, true)} Kapital.`
      + (ex ? ` Beispiele: ${ex}.` : "");
  }

  return "";
}

// Fettschrift **…** inline auflösen.
// Bewertungsmarker der KI: {+ erfreulich +} / {- kritisch -}. Bewusst keine reine
// Vorzeichenlogik – ein Plus ist nicht immer gut (Retourenquote, Lagerwert), das
// weiß nur das Modell aus dem Zusammenhang.
// Nur ein sauber geschlossenes Paar färbt: {+…+} bzw. {-…-}. Setzt das Modell
// {+…-} (kommt bei kleinen Modellen vor), bliebe die Farbe geraten – dann lieber
// nur die Klammern entfernen und den Text neutral zeigen.
const MARKER_RE = /\{([+-])([\s\S]*?)\1\}/g;
const GUT = "#3f9d5a", SCHLECHT = "#c9524a";

/** Marker, die halb geschrieben wurden, dürfen nicht als Text stehen bleiben. */
function markerBereinigen(s) {
  return String(s).replace(/\{[+-]|[+-]\}/g, "");
}

/** **fett** im (bereits marker-freien) Textstück. */
function renderFett(s, keyBase) {
  return markerBereinigen(s).split(/(\*\*[^*]+\*\*)/g).map((p, j) => {
    const m = /^\*\*([^*]+)\*\*$/.exec(p);
    return m
      ? <strong key={`${keyBase}-f${j}`} style={{ color: S.textMain }}>{m[1]}</strong>
      : <span key={`${keyBase}-f${j}`}>{p}</span>;
  });
}

function renderInline(s, keyBase) {
  const text = String(s);
  const out = [];
  let pos = 0;
  for (const m of text.matchAll(MARKER_RE)) {
    if (m.index > pos) out.push(...renderFett(text.slice(pos, m.index), `${keyBase}-${pos}`));
    const farbe = m[1] === "+" ? GUT : SCHLECHT;
    out.push(<span key={`${keyBase}-m${m.index}`} style={{ color: farbe, fontWeight: 600 }}>
      {renderFett(m[2], `${keyBase}-m${m.index}i`)}
    </span>);
    pos = m.index + m[0].length;
  }
  if (pos < text.length) out.push(...renderFett(text.slice(pos), `${keyBase}-${pos}`));
  return out;
}

const SEP_RE = /^:?-{2,}:?$/;

// Sehr schlanker Markdown-Renderer (nur was der Report-Prompt erzeugt):
// ## Überschriften, Absätze mit **fett**, und eine Pipe-Tabelle. Wird laufend
// beim Streamen neu geparst – halbe Tabellenzeilen erscheinen erst, wenn vollständig.
// Listenzeile: "- ", "* ", "• ", "1. ", "2) " …
const LIST_RE = /^\s*(?:[-*•]|\d+[.)])\s+/;
// Aufzählung, die das Modell in EINE Zeile gepackt hat ("… 1. Erstens … 2. Zweitens …").
const INLINE_NUM_RE = /(?:^|\s)(\d+)[.)]\s+/g;

/** Zerlegt einen Absatz mit eingebetteter Nummerierung in Vorspann + Punkte.
 *  Nur wenn mindestens zwei Nummern in Folge (1., 2., …) vorkommen – sonst bliebe
 *  ein Satz wie "… um 13,1 % auf 835.799,30 € gestiegen" zerschossen. */
function splitInlineList(text) {
  const treffer = [...text.matchAll(INLINE_NUM_RE)];
  const folge = treffer.filter((m, idx) => Number(m[1]) === idx + 1);
  if (folge.length < 2) return null;
  const start = folge[0].index + folge[0][0].length - folge[0][0].trimStart().length;
  const vorspann = text.slice(0, start).trim();
  const items = [];
  folge.forEach((m, idx) => {
    const von = m.index + m[0].length;
    const bis = idx + 1 < folge.length ? folge[idx + 1].index : text.length;
    items.push(text.slice(von, bis).trim());
  });
  return { vorspann, items };
}

function MiniMarkdown({ text }) {
  const lines = String(text).split("\n");
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (/^\s*$/.test(line)) { i++; continue; }
    if (/^##\s+/.test(line)) { blocks.push({ type: "h", text: line.replace(/^#+\s+/, "") }); i++; continue; }
    if (/^\s*\|/.test(line)) {
      const rows = [];
      while (i < lines.length && /^\s*\|/.test(lines[i])) {
        const cells = lines[i].trim().replace(/^\|/, "").replace(/\|\s*$/, "").split("|").map(c => c.trim());
        if (!cells.every(c => c === "" || SEP_RE.test(c))) rows.push(cells);
        i++;
      }
      if (rows.length) blocks.push({ type: "table", rows });
      continue;
    }
    if (LIST_RE.test(line)) {
      const items = [];
      while (i < lines.length && LIST_RE.test(lines[i])) {
        items.push(lines[i].replace(LIST_RE, "").trim()); i++;
      }
      blocks.push({ type: "ul", items });
      continue;
    }
    const para = [lines[i]];
    i++;
    // Folgezeilen anhängen – aber ein neuer **Themenblock:** beginnt immer einen
    // eigenen Absatz, auch ohne Leerzeile davor (Modelle setzen sie oft nicht).
    while (i < lines.length && !/^\s*$/.test(lines[i]) && !/^##\s+/.test(lines[i])
           && !/^\s*\|/.test(lines[i]) && !LIST_RE.test(lines[i])
           && !/^\s*\*\*/.test(lines[i])) {
      para.push(lines[i]); i++;
    }
    const absatz = para.join(" ");
    // Auch ohne Zeilenumbrüche im Modelltext als Liste zeigen – sonst steht der
    // Handlungsbedarf als eine einzige Textwurst da.
    const zerlegt = splitInlineList(absatz);
    if (zerlegt) {
      if (zerlegt.vorspann) blocks.push({ type: "p", text: zerlegt.vorspann });
      blocks.push({ type: "ul", items: zerlegt.items });
    } else {
      blocks.push({ type: "p", text: absatz });
    }
  }

  return (
    <div style={{ fontSize: 13.5, lineHeight: 1.6, color: S.textMain }}>
      {blocks.map((b, bi) => {
        if (b.type === "h") return (
          <div key={bi} style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.05em",
            textTransform: "uppercase", color: S.accent, margin: bi ? "14px 0 6px" : "0 0 6px" }}>
            {b.text}
          </div>
        );
        if (b.type === "p") return (
          <p key={bi} style={{ margin: "0 0 10px" }}>{renderInline(b.text, `p${bi}`)}</p>
        );
        if (b.type === "ul") return (
          <ul key={bi} style={{ margin: "0 0 10px", paddingLeft: 18 }}>
            {b.items.map((it, ii) => (
              <li key={ii} style={{ margin: "0 0 4px" }}>{renderInline(it, `l${bi}-${ii}`)}</li>
            ))}
          </ul>
        );
        // table
        const [head, ...body] = b.rows;
        return (
          <table key={bi} style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, margin: "4px 0 6px" }}>
            <thead>
              <tr>{head.map((c, ci) => (
                <th key={ci} style={{ textAlign: "left", padding: "5px 8px", borderBottom: "2px solid var(--border)",
                  color: S.textDim, fontWeight: 600, whiteSpace: "nowrap" }}>{renderInline(c, `h${bi}-${ci}`)}</th>
              ))}</tr>
            </thead>
            <tbody>
              {body.map((r, ri) => (
                <tr key={ri}>{r.map((c, ci) => (
                  <td key={ci} style={{ padding: "5px 8px", borderBottom: "1px solid var(--border)",
                    verticalAlign: "top", whiteSpace: ci === 1 ? "nowrap" : "normal" }}>{renderInline(c, `c${bi}-${ri}-${ci}`)}</td>
                ))}</tr>
              ))}
            </tbody>
          </table>
        );
      })}
    </div>
  );
}

// Bewertungstabelle (deterministisch, siehe buildAssessment).
function AssessmentTable({ rows }) {
  if (!rows?.length) return null;
  return (
    <div style={{ marginTop: 14 }}>
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.05em",
        textTransform: "uppercase", color: S.accent, margin: "0 0 6px" }}>
        Bewertung
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr>
            {["Bereich", "Status", "Kommentar"].map((h, i) => (
              <th key={i} style={{ textAlign: "left", padding: "5px 8px",
                borderBottom: "2px solid var(--border)", color: S.textDim, fontWeight: 600, whiteSpace: "nowrap" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td style={{ padding: "5px 8px", borderBottom: "1px solid var(--border)",
                fontWeight: 600, color: S.textMain, whiteSpace: "nowrap" }}>{r.bereich}</td>
              <td style={{ padding: "5px 8px", borderBottom: "1px solid var(--border)", whiteSpace: "nowrap",
                color: r.good ? "#3f9d5a" : "#c98a1c", fontWeight: 600 }}>
                {r.good ? "👍 gut" : "⚠️ verbesserungswürdig"}
              </td>
              <td style={{ padding: "5px 8px", borderBottom: "1px solid var(--border)", color: S.textMain }}>{r.kommentar}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Detailgrad-Umschalter (knapp | ausführlich) – rechts in der Widget-Kopfzeile.
// Während der Text streamt gesperrt, sonst würde ein Klick den halben Lauf verwerfen.
function DetailSwitch({ value, onChange, disabled, nurKnapp }) {
  // Ohne Gateway gibt es nichts zu wählen – der ausführliche Prompt braucht lokal
  // Minuten und läuft in die Proxy-Grenze. Dann bleibt der Schalter weg.
  if (nurKnapp) return (
    <span style={{ marginLeft: "auto", fontSize: 10, fontWeight: 500, letterSpacing: 0,
      textTransform: "none", color: S.textDim }}
      title="Die ausführliche Analyse gibt es nur über Datenmonster AI – das lokale Modell braucht dafür mehrere Minuten.">
      knapp
    </span>
  );
  const opts = [{ v: "knapp", l: "knapp" }, { v: "ausfuehrlich", l: "ausführlich" }];
  return (
    <div style={{ marginLeft: "auto", display: "flex", border: "1px solid var(--border)",
      borderRadius: 5, overflow: "hidden" }}
      title="Ausführlich: mehr Detailzeilen, längere Analyse mit Ursachen und Zusammenhängen (dauert länger)">
      {opts.map(o => {
        const on = value === o.v;
        return (
          <button key={o.v} type="button" disabled={disabled}
            onClick={() => !disabled && onChange(o.v)}
            style={{ border: "none", padding: "2px 8px", fontSize: 10, fontWeight: 600,
              letterSpacing: 0, textTransform: "none",
              cursor: disabled ? "default" : "pointer", opacity: disabled && !on ? 0.5 : 1,
              backgroundColor: on ? "var(--accent)" : "transparent",
              color: on ? "var(--bg-main)" : S.textDim }}>
            {o.l}
          </button>
        );
      })}
    </div>
  );
}

/**
 * Widget "ai_summary": erzeugt aus dem Ergebnis der verknüpften Action (z.B. der
 * KPI-Zeile) eine kurze KI-Management-Zusammenfassung über /api/ai/summarize-data.
 * Verbraucht KEINE eigene DB-Abfrage – es nutzt das bereits geladene Action-Ergebnis.
 *
 * Optional können über config.extra_sections weitere, bereits geladene Action-
 * Ergebnisse desselben Formulars einbezogen werden (z.B. Umsatz je Plattform,
 * Kundenrückgang, Ladenhüter). Sie werden hier vorformatiert und als »sections«
 * mitgeschickt, damit die KI eine reichere Lagebeurteilung schreibt.
 *
 * Der Detailgrad ist zur Laufzeit umschaltbar (knapp | ausführlich). "Ausführlich"
 * schickt mehr Rohzeilen mit und löst serverseitig die Längenfesseln im Prompt –
 * dort liegt der eigentliche Engpass, nicht beim Modell.
 *
 * config: { width, instruction?, detail_level?, extra_sections?: [{action_id, label, kind}] }
 */
export default function AiSummaryWidget({ widget, result, results, onAiText }) {
  const cfg = widget.config || {};
  const rows = result?.rows || [];
  const columns = result?.columns || [];
  const [detail, setDetail] = useState(
    String(cfg.detail_level || "knapp").startsWith("ausf") ? "ausfuehrlich" : "knapp");
  const deep = detail === "ausfuehrlich";
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);
  // Welches Modell den Text geschrieben hat (bzw. ob er aus dem Server-Cache kam) –
  // sonst ist ein Modellwechsel im Ergebnis nicht nachvollziehbar.
  const [meta, setMeta] = useState(null);

  // Fertigen KI-Text + Lade-Status nach oben melden: FormRunner gibt den Text dem
  // PDF-Report mit (Report überspringt so den langsamen KI-Aufruf) und sperrt den
  // Report-Button, solange die Analyse noch streamt.
  useEffect(() => {
    onAiText?.(widget.action_id, text || "", loading);
  }, [text, loading, widget.action_id]);

  // Zusatz-Sektionen aus den übrigen Action-Ergebnissen aufbauen (leere fallen raus).
  const sections = useMemo(() => {
    const defs = Array.isArray(cfg.extra_sections) ? cfg.extra_sections : [];
    return defs
      .map(s => ({ label: s.label || "",
                   text: buildSectionText(s.kind, (results?.[s.action_id]?.rows) || [], deep) }))
      .filter(s => s.text);
  }, [cfg.extra_sections, results, deep]);

  // Bewertungstabelle (nur im Report-Layout) – rein aus den Daten, unabhängig vom LLM.
  const assessment = useMemo(
    () => (cfg.report_layout ? buildAssessment(results) : []),
    [cfg.report_layout, results],
  );

  // Nur (neu) generieren, wenn sich die zugrunde liegenden Daten (oder der Detailgrad) ändern.
  const dataKey = JSON.stringify(rows) + "|" + JSON.stringify(sections) + "|" + (cfg.instruction || "")
    + "|" + detail;

  const [providerTick, setProviderTick] = useState(0);
  useEffect(() => onAiProviderChange(() => setProviderTick(t => t + 1)), []);

  // Läuft die Analyse über den Gateway? Eigene Wahl schlägt die globale Einstellung
  // (die steckt in /api/ai/credits als `enabled`). null = noch unbekannt.
  const [globalGateway, setGlobalGateway] = useState(null);
  useEffect(() => {
    let aktiv = true;
    api.get("/api/ai/credits")
      .then(({ data }) => { if (aktiv) setGlobalGateway(!!data.enabled); })
      .catch(() => { if (aktiv) setGlobalGateway(false); });
    return () => { aktiv = false; };
  }, []);
  const gewaehlt = getAiProvider();
  const ueberGateway = gewaehlt ? gewaehlt === "datenmonster" : globalGateway;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const nurKnapp = ueberGateway === false;

  // Beim Wechsel auf das lokale Modell zurück auf „knapp" – der Server würde ohnehin
  // darauf zurückfallen, so bleibt die Anzeige ehrlich.
  useEffect(() => {
    if (nurKnapp && detail !== "knapp") setDetail("knapp");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nurKnapp, providerTick]);

  useEffect(() => {
    if (!rows.length) { setText(""); setErr(null); setMeta(null); return; }
    const ac = new AbortController();
    setLoading(true); setErr(null); setText(""); setMeta(null);

    // Beim Filterwechsel (z.B. Zeitraum) wird die noch streamende Anfrage per abort()
    // abgebrochen und sofort eine neue gestartet. Die gerade schließende SSE-Verbindung
    // kann die neue Anfrage mit "Failed to fetch" abschmieren lassen – das ist KEIN
    // echter Serverausfall. Darum bei transientem Netzwerkfehler einmal kurz verzögert
    // neu versuchen (der Retry feuert nur, wenn noch kein Token gestreamt wurde).
    async function run() {
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          await streamRequest(
            "/summarize-data",
            { label: widget.label || "", columns, rows, sections,
              instruction: cfg.instruction || "",
              layout: cfg.report_layout ? "report" : "prose",
              detail },
            (_tok, full) => { if (!ac.signal.aborted) setText(full); },
            m => { if (!ac.signal.aborted) setMeta(m); },
            ac.signal,
          );
          return;
        } catch (e) {
          if (ac.signal.aborted || e.message === "__ABORTED__") return;
          const transient = /nicht erreichbar|Netzwerkfehler/.test(e.message);
          if (attempt === 0 && transient) {
            await new Promise(r => setTimeout(r, 500));
            if (ac.signal.aborted) return;
            continue;
          }
          setErr(e.message);
          return;
        }
      }
    }
    run().finally(() => { if (!ac.signal.aborted) setLoading(false); });
    return () => ac.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataKey, providerTick]);

  return (
    <div style={{ padding: "14px 16px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8,
        fontSize: 10, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase",
        color: S.accent }}>
        <Sparkles size={12} /> KI-Analyse
        {loading && <Loader2 size={11} style={{ animation: "spin 1s linear infinite", color: S.textDim }} />}
        {meta?.model && (
          // Anbieter mit ausweisen: "auto" allein sagt nicht, dass gerade Datenmonster AI
          // gerechnet hat – und genau das will man beim Umschalten sehen.
          <span style={{ color: S.textDim, fontWeight: 500, letterSpacing: 0, textTransform: "none" }}>
            · {meta.provider === "datenmonster"
                 ? `Datenmonster AI${meta.model && meta.model !== "auto" ? ` (${meta.model})` : ""}`
                 : `${meta.model} (lokal)`}
            {meta.cached ? " (zwischengespeichert)" : ""}
          </span>
        )}
        <DetailSwitch value={detail} onChange={setDetail} disabled={loading} nurKnapp={nurKnapp} />
      </div>

      {/* Lokale Modelle sind klein und erfinden im Cockpit-Kontext nachweislich Zahlen.
          Der Hinweis steht deshalb dauerhaft über der Analyse – nicht als feine Fußnote. */}
      {nurKnapp && (rows.length > 0) && (
        <div style={{ display: "flex", alignItems: "flex-start", gap: 8, marginBottom: 10,
          padding: "9px 12px", borderRadius: 7, backgroundColor: "rgba(224,160,80,0.12)",
          border: "1px solid rgba(224,160,80,0.45)" }}>
          <AlertTriangle size={14} style={{ color: "#e0a050", flexShrink: 0, marginTop: 1 }} />
          <span style={{ fontSize: 12, lineHeight: 1.45, color: S.textMain }}>
            <b style={{ color: "#e0a050" }}>Lokales Modell – Zahlen bitte prüfen.</b>{" "}
            Kleine Modelle formulieren flüssig, verwechseln oder erfinden aber Werte.
            Verlässlich sind die Kennzahlen-Kacheln und die Bewertungstabelle darunter –
            beide kommen direkt aus den Daten. Für belastbare Analysetexte oben auf
            <b> Datenmonster AI</b> umschalten.
          </span>
        </div>
      )}

      {!rows.length ? (
        <p style={{ fontSize: 12, color: S.textDim, margin: 0 }}>Warten auf Kennzahlen …</p>
      ) : err ? (
        <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#e07070", fontSize: 12 }}>
          <AlertCircle size={13} /> {err}
        </div>
      ) : text ? (
        // Der ausführliche Prompt gliedert mit **fetten Labels** – der muss durch den
        // Markdown-Renderer, sonst stehen die Sternchen im Text.
        (cfg.report_layout || deep) ? (
          <>
            <MiniMarkdown text={text} />
            <AssessmentTable rows={assessment} />
          </>
        ) : (
          // Auch ohne Report-Layout durch renderInline: sonst stünden die
          // Bewertungsmarker {+ … +} als Rohtext in der Analyse.
          <p style={{ fontSize: 13.5, lineHeight: 1.65, color: S.textMain, margin: 0, whiteSpace: "pre-wrap" }}>
            {renderInline(text, "plain")}
          </p>
        )
      ) : (
        cfg.report_layout && assessment.length ? (
          <AssessmentTable rows={assessment} />
        ) : (
          <p style={{ fontSize: 12, color: S.textDim, margin: 0 }}>
            KI erstellt die Analyse … (kann beim ersten Mal einige Sekunden dauern)
          </p>
        )
      )}
    </div>
  );
}
