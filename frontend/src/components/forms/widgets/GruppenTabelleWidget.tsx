/**
 * Gruppentabelle: aufklappbare Gruppen (z. B. Warengruppe) mit Zwischensummen, darunter die
 * Einzelzeilen (z. B. Artikel) mit Werten je Zeitscheibe, Suche, Kennzahl-Umschalter,
 * Veränderung zur Vorperiode, Mini-Verlauf und Excel-Export. Gefiltert und gerechnet wird
 * im Browser – die Action liefert alle Zeilen (config.full_rows = Zeilenzahl).
 *
 * Konfiguration (widget.config):
 *   gruppe:        "Warengruppe"                      – Spalte, nach der gruppiert wird
 *   text_spalten:  ["ArtNr", "Bezeichnung", "Einheit"] – Textspalten der Einzelzeile
 *   kennzahlen:    [{ id, label, praefix: "U", summe: true, dezimal: 0 }]
 *                  – Werte stehen in <praefix>0 … <praefix>(scheiben-1), 0 = jüngste Scheibe
 *                  – summe: "einheit" = Gruppensumme nur „echt“, wenn alle Zeilen dieselbe Einheit
 *                    haben; sonst wird sie blass mit „≈“ gezeigt (gemischte Einheiten im Tooltip)
 *   einheit_spalte:"Einheit",  einheit_gleich: { "%o": "Stück", "Stk": "Stück" } – Einheiten zusammenfassen
 *   scheiben:      6
 *   scheiben_titel:["letzte 12 Monate", "Vorjahr", …]  – optional; sonst aus params.bis berechnet
 *   zusatz_spalten:[{ spalte: "Kunden0", titel: "Kunden" }] – rechts angehängt
 *   aktiv_spalte:  "Aktuell"   – 1 = Zeile hat Werte in der jüngsten Scheibe (Schalter)
 *   such_spalte:   "Suchtext"  – Volltext für die Suche (sonst die Textspalten)
 *   drilldown:     wie beim Tabellen-Widget (key_column, mapping_id, …) – Klick auf Einzelzeile
 */
import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Download, Search } from "lucide-react";
import { tabelleAlsExcel } from "../excelExport";
import { fehlerText } from "../../../api/client";

const S = {
  bgEl: "var(--bg-elevated)", border: "var(--border)", textMain: "var(--text-main)",
  textDim: "var(--text-dim)", accent: "var(--accent)", ok: "var(--ok)", err: "var(--err)",
};

const zahl = (v) => {
  if (v === null || v === undefined || v === "") return 0;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : 0;
};
const fmt = (v, dez = 0) => v.toLocaleString("de-DE", { minimumFractionDigits: dez, maximumFractionDigits: dez });

// Scheibe i endet i Jahre vor „bis“ und umfasst die zwölf Monate davor.
function scheibenTitel(anzahl, bis) {
  const d = bis ? new Date(String(bis).slice(0, 10) + "T00:00:00") : null;
  const mm = (x) => `${String(x.getMonth() + 1).padStart(2, "0")}/${String(x.getFullYear()).slice(2)}`;
  return Array.from({ length: anzahl }, (_, i) => {
    const titel = i === 0 ? "letzte 12 Mon." : i === 1 ? "Vorjahr" : `vor ${i} Jahren`;
    if (!d || isNaN(d.getTime())) return { titel, zeitraum: "" };
    const ende = new Date(d); ende.setFullYear(d.getFullYear() - i);
    const start = new Date(ende); start.setFullYear(ende.getFullYear() - 1); start.setDate(start.getDate() + 1);
    return { titel, zeitraum: `${mm(start)}–${mm(ende)}` };
  });
}

function Verlauf({ werte }) {
  // älteste links, jüngste rechts
  const w = [...werte].reverse();
  const max = Math.max(...w.map(Math.abs), 0);
  if (!max) return <span style={{ color: S.textDim }}>–</span>;
  const B = 64, H = 16, schritt = w.length > 1 ? B / (w.length - 1) : B;
  const pkt = w.map((v, i) => `${(i * schritt).toFixed(1)},${(H - 1 - (Math.max(v, 0) / max) * (H - 2)).toFixed(1)}`).join(" ");
  return (
    <svg width={B} height={H} style={{ display: "block" }} aria-hidden="true">
      <polyline points={pkt} fill="none" stroke="var(--accent)" strokeWidth="1.5" />
    </svg>
  );
}

function Delta({ jetzt, vorher }) {
  if (!vorher) return <span style={{ color: S.textDim }}>{jetzt ? "neu" : ""}</span>;
  const p = ((jetzt - vorher) / Math.abs(vorher)) * 100;
  const farbe = p > 0.5 ? S.ok : p < -0.5 ? S.err : S.textDim;
  return <span style={{ color: farbe }}>{p > 0 ? "+" : ""}{fmt(p, 0)} %</span>;
}

export default function GruppenTabelleWidget({ widget, result, params = {}, onDrilldown, allowDownload }) {
  const cfg = widget.config || {};
  const gruppe = cfg.gruppe;
  const textSp = cfg.text_spalten || [];
  const kennzahlen = cfg.kennzahlen || [];
  const anzahl = cfg.scheiben || 1;
  const zusatz = cfg.zusatz_spalten || [];
  const dd = cfg.drilldown;
  const rows = result?.rows || [];

  const [kzId, setKzId] = useState(kennzahlen[0]?.id);
  const kz = kennzahlen.find(k => k.id === kzId) || kennzahlen[0];
  const [suche, setSuche] = useState("");
  const [nurAktuell, setNurAktuell] = useState(true);
  const [offen, setOffen] = useState(() => new Set());
  const [sortIdx, setSortIdx] = useState(0);      // Scheibe, nach der sortiert wird
  const [xlsx, setXlsx] = useState(false);

  const titel = useMemo(() => cfg.scheiben_titel
    ? cfg.scheiben_titel.map(t => ({ titel: t, zeitraum: "" }))
    : scheibenTitel(anzahl, params?.bis), [cfg.scheiben_titel, anzahl, params?.bis]);

  const werte = (row) => Array.from({ length: anzahl }, (_, i) => zahl(row[`${kz.praefix}${i}`]));
  const umsatzRef = kennzahlen.find(k => k.summe) || kz;   // Reihenfolge der Gruppen

  const gefiltert = useMemo(() => {
    const woerter = suche.trim().toLowerCase().split(/\s+/).filter(Boolean);
    return rows.filter(r => {
      if (nurAktuell && cfg.aktiv_spalte && !zahl(r[cfg.aktiv_spalte])) return false;
      if (!woerter.length) return true;
      const text = String(cfg.such_spalte ? r[cfg.such_spalte] ?? "" : textSp.map(c => r[c] ?? "").join(" ")).toLowerCase();
      return woerter.every(w => text.includes(w));
    });
  }, [rows, suche, nurAktuell, cfg.aktiv_spalte, cfg.such_spalte, textSp]);

  const gruppen = useMemo(() => {
    const m = new Map();
    for (const r of gefiltert) {
      const g = r[gruppe] ?? "–";
      if (!m.has(g)) m.set(g, []);
      m.get(g).push(r);
    }
    const sum = (zeilen, praefix, i) => zeilen.reduce((a, r) => a + zahl(r[`${praefix}${i}`]), 0);
    const liste = [...m.entries()].map(([name, zeilen]) => ({
      name,
      zeilen: [...zeilen].sort((a, b) => zahl(b[`${kz.praefix}${sortIdx}`]) - zahl(a[`${kz.praefix}${sortIdx}`])),
      summen: kz.summe ? Array.from({ length: anzahl }, (_, i) => sum(zeilen, kz.praefix, i)) : null,
      einheiten: kz.summe === "einheit" && cfg.einheit_spalte
        ? [...new Set(zeilen.map(r => {
            const e = String(r[cfg.einheit_spalte] ?? "").trim();
            return (cfg.einheit_gleich || {})[e] || e || "ohne Einheit";
          }))].sort()
        : [],
      ordnung: sum(zeilen, umsatzRef.praefix, sortIdx),
    }));
    liste.sort((a, b) => b.ordnung - a.ordnung);
    return liste;
  }, [gefiltert, gruppe, kz, sortIdx, anzahl, umsatzRef, cfg.einheit_spalte, cfg.einheit_gleich]);

  if (!rows.length) return <p style={{ padding: "14px 16px", color: S.textDim, fontSize: 12 }}>Keine Daten</p>;

  const sucheAktiv = suche.trim().length > 0;
  const istOffen = (g) => sucheAktiv || offen.has(g);
  const umschalten = (g) => setOffen(prev => {
    const n = new Set(prev); n.has(g) ? n.delete(g) : n.add(g); return n;
  });
  const klickbar = !!(onDrilldown && dd?.mapping_id && dd?.key_column);
  const dez = kz?.dezimal ?? 0;
  const zelle = (v) => v === 0 ? <span style={{ color: S.textDim, opacity: 0.5 }}>·</span> : fmt(v, dez);

  const excel = async () => {
    setXlsx(true);
    try {
      const spalten = [gruppe, ...textSp, ...titel.map((t, i) => `${kz.label} ${t.titel}${t.zeitraum ? ` (${t.zeitraum})` : ""}`),
        ...zusatz.map(z => z.titel)];
      const zeilen = gruppen.flatMap(g => g.zeilen.map(r => {
        const o = { [gruppe]: g.name };
        textSp.forEach(c => { o[c] = r[c]; });
        werte(r).forEach((v, i) => { o[spalten[1 + textSp.length + i]] = v; });
        zusatz.forEach(z => { o[z.titel] = r[z.spalte]; });
        return o;
      }));
      await tabelleAlsExcel({ titel: widget.label || "Gruppentabelle", columns: spalten, rows: zeilen });
    } catch (e) {
      alert(`Excel-Export fehlgeschlagen: ${fehlerText(e)}`);
    } finally { setXlsx(false); }
  };

  const th = { padding: "7px 10px", borderBottom: `1px solid ${S.border}`, color: S.textDim, fontWeight: 600,
    fontSize: 11, whiteSpace: "nowrap", position: "sticky", top: 0, backgroundColor: S.bgEl };
  const td = { padding: "6px 10px", color: S.textMain, whiteSpace: "nowrap" };
  const knopf = { display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: S.accent, background: "none",
    border: `1px solid ${S.border}`, borderRadius: 5, padding: "4px 10px", cursor: "pointer" };
  const artikelAnzahl = gruppen.reduce((a, g) => a + g.zeilen.length, 0);

  return (
    <div>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10, padding: "8px 16px",
        borderBottom: `1px solid ${S.border}` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, border: `1px solid ${S.border}`, borderRadius: 6,
          padding: "4px 8px", minWidth: 260, flex: "1 1 260px", maxWidth: 420 }}>
          <Search size={13} color="var(--text-dim)" />
          <input value={suche} onChange={e => setSuche(e.target.value)}
            placeholder="Artikelnummer oder Name, z. B. pizza karton"
            style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: S.textMain, fontSize: 12 }} />
          {suche && <button onClick={() => setSuche("")} style={{ background: "none", border: "none",
            color: S.textDim, cursor: "pointer", fontSize: 12 }}>✕</button>}
        </div>
        {kennzahlen.length > 1 && (
          <div style={{ display: "flex", border: `1px solid ${S.border}`, borderRadius: 6, overflow: "hidden" }}>
            {kennzahlen.map(k => (
              <button key={k.id} onClick={() => setKzId(k.id)}
                style={{ fontSize: 11, padding: "4px 10px", border: "none", cursor: "pointer",
                  background: k.id === kz.id ? "var(--accent)" : "transparent",
                  color: k.id === kz.id ? "var(--bg-main, #000)" : S.textDim }}>{k.label}</button>
            ))}
          </div>
        )}
        {cfg.aktiv_spalte && (
          <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: S.textDim, cursor: "pointer" }}>
            <input type="checkbox" checked={!nurAktuell} onChange={e => setNurAktuell(!e.target.checked)} />
            auch ohne Verkauf in den letzten 12 Monaten
          </label>
        )}
        <span style={{ fontSize: 11, color: S.textDim, marginLeft: "auto" }}>
          {fmt(artikelAnzahl)} Zeilen in {fmt(gruppen.length)} Gruppen
        </span>
        <button style={knopf} onClick={() => setOffen(new Set(gruppen.map(g => g.name)))}>alle auf</button>
        <button style={knopf} onClick={() => setOffen(new Set())}>alle zu</button>
        {allowDownload !== false && (
          <button style={{ ...knopf, cursor: xlsx ? "wait" : "pointer" }} onClick={excel} disabled={xlsx || !artikelAnzahl}>
            <Download size={11} /> {xlsx ? "Excel …" : "Excel"}
          </button>
        )}
      </div>
      <div style={{ overflow: "auto", maxHeight: 640 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr>
              <th style={{ ...th, textAlign: "left" }}>{gruppe} / {textSp.slice(0, 2).join(" · ")}</th>
              {textSp.slice(2).map(c => <th key={c} style={{ ...th, textAlign: "left" }}>{c}</th>)}
              {titel.map((t, i) => (
                <th key={i} onClick={() => setSortIdx(i)} title="Klicken: danach sortieren"
                  style={{ ...th, textAlign: "right", cursor: "pointer", color: sortIdx === i ? S.accent : S.textDim }}>
                  <div>{t.titel}{sortIdx === i ? " ▼" : ""}</div>
                  {t.zeitraum && <div style={{ fontWeight: 400, fontSize: 10, opacity: 0.8 }}>{t.zeitraum}</div>}
                </th>
              ))}
              <th style={{ ...th, textAlign: "right" }}>ggü. Vorjahr</th>
              <th style={{ ...th, textAlign: "left" }}>Verlauf</th>
              {zusatz.map(z => <th key={z.spalte} style={{ ...th, textAlign: "right" }}>{z.titel}</th>)}
            </tr>
          </thead>
          <tbody>
            {gruppen.map(g => {
              const auf = istOffen(g.name);
              const gemischt = g.einheiten.length > 1;
              const summenStil = gemischt ? { opacity: 0.55, fontStyle: "italic" } : {};
              const summenTitel = gemischt ? `Summe über gemischte Einheiten: ${g.einheiten.join(", ")}` : undefined;
              return [
                <tr key={`g:${g.name}`} onClick={() => umschalten(g.name)}
                  style={{ cursor: "pointer", backgroundColor: "color-mix(in srgb, var(--accent) 7%, transparent)",
                    borderBottom: `1px solid ${S.border}` }}>
                  <td style={{ ...td, fontWeight: 600 }} colSpan={1 + Math.max(textSp.length - 2, 0)}>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                      {auf ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                      {g.name}
                      <span style={{ color: S.textDim, fontWeight: 400, marginLeft: 6 }}>({g.zeilen.length})</span>
                    </span>
                  </td>
                  {titel.map((_, i) => (
                    <td key={i} title={summenTitel} style={{ ...td, textAlign: "right", fontWeight: 600, ...summenStil }}>
                      {g.summen ? <>{gemischt && g.summen[i] !== 0 ? "≈ " : ""}{zelle(g.summen[i])}</> : ""}
                    </td>
                  ))}
                  <td style={{ ...td, textAlign: "right", fontWeight: 600 }}>
                    {g.summen ? <Delta jetzt={g.summen[0]} vorher={g.summen[1]} /> : ""}
                  </td>
                  <td style={td}>{g.summen ? <Verlauf werte={g.summen} /> : ""}</td>
                  {zusatz.map(z => <td key={z.spalte} style={td} />)}
                </tr>,
                ...(auf ? g.zeilen.map((r, j) => {
                  const w = werte(r);
                  const schluessel = dd?.key_column ? r[dd.key_column] : null;
                  const kann = klickbar && schluessel !== null && schluessel !== undefined && schluessel !== "";
                  return (
                    <tr key={`z:${g.name}:${j}`} onClick={() => kann && onDrilldown(dd.key_column, schluessel)}
                      style={{ borderBottom: `1px solid ${S.border}`, cursor: kann ? "pointer" : "default" }}
                      onMouseEnter={e => e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.025)"}
                      onMouseLeave={e => e.currentTarget.style.backgroundColor = ""}>
                      <td style={{ ...td, paddingLeft: 30, whiteSpace: "normal", minWidth: 280 }}>
                        <span style={{ color: S.textDim, marginRight: 8 }}>{r[textSp[0]]}</span>
                        {textSp[1] ? r[textSp[1]] : ""}
                      </td>
                      {textSp.slice(2).map(c => <td key={c} style={{ ...td, color: S.textDim }}>{r[c] ?? ""}</td>)}
                      {w.map((v, i) => <td key={i} style={{ ...td, textAlign: "right" }}>{zelle(v)}</td>)}
                      <td style={{ ...td, textAlign: "right" }}><Delta jetzt={w[0]} vorher={w[1]} /></td>
                      <td style={td}><Verlauf werte={w} /></td>
                      {zusatz.map(z => (
                        <td key={z.spalte} style={{ ...td, textAlign: typeof r[z.spalte] === "number" ? "right" : "left" }}>
                          {typeof r[z.spalte] === "number" ? fmt(r[z.spalte]) : (r[z.spalte] ?? "")}
                        </td>
                      ))}
                    </tr>
                  );
                }) : []),
              ];
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
