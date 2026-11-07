/**
 * USt-ID-Prüfung: Kunden mit steuerfreien innergemeinschaftlichen Lieferungen (JTL
 * nSteuereinstellung = 10) und der Stand ihrer USt-ID – fehlt, Format falsch, bei VIES gültig/ungültig,
 * zuletzt in JTL geprüft. Geprüft wird nur auf Knopfdruck (POST /api/ustid/pruefen): dann gehen die
 * USt-IDs direkt von dieser Installation an VIES (EU-Kommission). Ergebnisse je Mandant gespeichert.
 *
 * Konfiguration (widget.config):
 *   spalten: { kundennr, kunde, land, ustid, rechnungen, letzte, jtl }
 *   alter_tage: 90 – ältere Prüfungen gelten als „erneut prüfen“
 */
import { useEffect, useMemo, useState } from "react";
import api, { fehlerText } from "../../../api/client";
import { useAuth } from "../../../context/AuthContext";

const EU = new Set(["AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT",
  "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK", "XI"]);
// Grobe Formatregeln je Land (Zeichen nach dem Ländercode) – Tippfehler früh sehen, ohne VIES zu fragen
const FORMAT = {
  AT: /^U\d{8}$/, BE: /^[01]\d{9}$/, BG: /^\d{9,10}$/, CY: /^\d{8}[A-Z]$/, CZ: /^\d{8,10}$/, DE: /^\d{9}$/, DK: /^\d{8}$/,
  EE: /^\d{9}$/, EL: /^\d{9}$/, ES: /^[A-Z0-9]\d{7}[A-Z0-9]$/, FI: /^\d{8}$/, FR: /^[A-Z0-9]{2}\d{9}$/, HR: /^\d{11}$/,
  HU: /^\d{8}$/, IE: /^\d[A-Z0-9+*]\d{5}[A-Z]{1,2}$/, IT: /^\d{11}$/, LT: /^(\d{9}|\d{12})$/, LU: /^\d{8}$/, LV: /^\d{11}$/,
  MT: /^\d{8}$/, NL: /^\d{9}B\d{2}$/, PL: /^\d{10}$/, PT: /^\d{9}$/, RO: /^\d{2,10}$/, SE: /^\d{12}$/, SI: /^\d{8}$/,
  SK: /^\d{10}$/, XI: /^(\d{9}|\d{12}|GD\d{3}|HA\d{3})$/,
};

/** USt-ID normalisieren und einordnen: { id, cc, fehler } – fehler = „fehlt“ | „kein EU-Ländercode“ | „Format“. */
export function einordnen(roh) {
  let s = String(roh || "").replace(/[^A-Za-z0-9]/g, "").toUpperCase();
  if (!s) return { id: "", cc: null, fehler: "fehlt" };
  if (s.startsWith("GR")) s = "EL" + s.slice(2);
  const cc = s.slice(0, 2), nr = s.slice(2);
  if (!EU.has(cc)) return { id: s, cc: null, fehler: "kein EU-Ländercode" };
  if (FORMAT[cc] && !FORMAT[cc].test(nr)) return { id: s, cc, fehler: "Format" };
  return { id: s, cc, fehler: null };
}

const datum = (iso) => (iso ? new Date(iso.length > 10 ? iso : iso + "T12:00:00").toLocaleDateString("de-DE") : "–");

export default function UstidWidget({ widget, result, projectId = null }) {
  const cfg = widget.config || {};
  const sp = { kundennr: "KundenNr", kunde: "Kunde", land: "Land", ustid: "UStID", rechnungen: "Rechnungen",
    letzte: "LetzteRechnung", jtl: "JTLGeprueft", ...(cfg.spalten || {}) };
  const alterTage = Number(cfg.alter_tage) || 90;
  const { user } = useAuth();
  const darfPruefen = !user?.is_portal_only && projectId != null;
  const [ergebnisse, setErgebnisse] = useState({});
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState(null);

  useEffect(() => {
    let lebt = true;
    const q = projectId != null ? `?project_id=${projectId}` : "";
    api.get(`/api/ustid/ergebnisse${q}`).then(({ data }) => lebt && setErgebnisse(data.ergebnisse || {})).catch(() => {});
    return () => { lebt = false; };
  }, [projectId]);

  const zeilen = useMemo(() => (result?.rows || []).map((r) => {
    const e = einordnen(r[sp.ustid]);
    return { kundennr: r[sp.kundennr], kunde: r[sp.kunde], land: r[sp.land], rechnungen: r[sp.rechnungen],
      letzte: r[sp.letzte], jtl: r[sp.jtl], ...e };
  }), [result]); // eslint-disable-line react-hooks/exhaustive-deps

  const status = (z) => {
    if (z.fehler) return { text: z.fehler === "fehlt" ? "USt-ID fehlt" : z.fehler === "Format" ? "Format ungültig" : "kein EU-Ländercode", art: "err" };
    const v = ergebnisse[z.id];
    if (!v) return { text: "noch nicht geprüft", art: "warn" };
    const alt = (Date.now() - new Date(v.geprueft_am).getTime()) / 864e5 > alterTage;
    if (v.status === "ungueltig") return { text: "bei VIES ungültig", art: "err" };
    if (v.status === "gueltig") return { text: alt ? "gültig, Prüfung veraltet" : "gültig", art: alt ? "warn" : "ok" };
    return { text: "nicht geprüft (VIES nicht erreichbar)", art: "warn" };
  };
  const pruefbar = [...new Set(zeilen.filter((z) => !z.fehler).map((z) => z.id))];
  const offen = pruefbar.filter((id) => status(zeilen.find((z) => z.id === id)).art !== "ok");

  const pruefen = async (ids) => {
    setLaeuft(true); setFehler(null);
    try {
      for (let i = 0; i < ids.length; i += 40) {
        const { data } = await api.post("/api/ustid/pruefen", { project_id: projectId, ustids: ids.slice(i, i + 40) });
        // Ausfälle überschreiben kein früheres Ergebnis (wie im Backend)
        setErgebnisse((alt) => ({ ...alt, ...Object.fromEntries(Object.entries(data.ergebnisse || {}).filter(([, v]) => (v as any).status !== "nicht_erreichbar")) }));
        const aus = Object.entries(data.ergebnisse || {}).filter(([, v]) => (v as any).status === "nicht_erreichbar");
        if (aus.length) setFehler(`${aus.length} USt-ID(s) konnten nicht geprüft werden: ${(aus[0][1] as any).meldung}`);
      }
    } catch (e) { setFehler(fehlerText(e)); }
    finally { setLaeuft(false); }
  };

  const farbe = { ok: "var(--ok)", warn: "var(--warn, #f59e0b)", err: "var(--err)" };
  const th = { textAlign: "left", padding: "6px 8px", fontSize: 11, color: "var(--text-dim)", fontWeight: 600,
    borderBottom: "1px solid var(--border)", whiteSpace: "nowrap" };
  const td = { padding: "6px 8px", fontSize: 12.5, color: "var(--text-main)", borderBottom: "1px solid var(--border)", verticalAlign: "top" };
  const knopf = { padding: "5px 12px", fontSize: 12.5, cursor: laeuft ? "wait" : "pointer", border: "1px solid var(--accent)", borderRadius: 6,
    background: "color-mix(in srgb, var(--accent) 14%, transparent)", color: "var(--text-bright)", fontWeight: 600 };

  if (!zeilen.length) {
    return <p style={{ padding: 16, margin: 0, color: "var(--text-dim)", fontSize: 13 }}>
      Keine steuerfreien EU-Lieferungen in den letzten 24 Monaten – keine USt-IDs zu prüfen.</p>;
  }
  const probleme = zeilen.filter((z) => status(z).art !== "ok").length;

  return (
    <div style={{ padding: "12px 16px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ fontSize: 13, color: "var(--text-main)" }}>
          {zeilen.length} Kunde{zeilen.length === 1 ? "" : "n"} mit steuerfreier EU-Lieferung –{" "}
          <b style={{ color: probleme ? "var(--err)" : "var(--ok)" }}>{probleme ? `${probleme} mit Handlungsbedarf` : "alle USt-IDs gültig"}</b>
        </span>
        {darfPruefen && offen.length > 0 && (
          <button onClick={() => pruefen(offen)} disabled={laeuft} style={knopf}
            title="Fragt die USt-IDs bei VIES (EU-Kommission) ab – direkt von dieser Installation">
            {laeuft ? "Prüfe bei VIES …" : `${offen.length} USt-ID${offen.length === 1 ? "" : "s"} bei VIES prüfen`}
          </button>
        )}
      </div>
      {fehler && <p style={{ margin: 0, fontSize: 12.5, color: "var(--err-soft, var(--err))" }}>{fehler}</p>}
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={th}>Kunde</th><th style={th}>USt-ID</th><th style={th}>Status</th>
              <th style={th}>VIES-Angaben</th><th style={{ ...th, textAlign: "right" }}>Rechnungen</th><th style={th}>Letzte Rechnung</th>
            </tr>
          </thead>
          <tbody>
            {zeilen.map((z, i) => {
              const st = status(z);
              const v = ergebnisse[z.id];
              return (
                <tr key={`${z.kundennr}-${z.id}-${i}`}>
                  <td style={td}>
                    <div style={{ color: "var(--text-bright)", fontWeight: 600 }}>{z.kunde}</div>
                    <div style={{ fontSize: 11.5, color: "var(--text-dim)" }}>Nr. {z.kundennr} · {z.land}</div>
                  </td>
                  <td style={{ ...td, fontFamily: "var(--font-mono)", whiteSpace: "nowrap" }}>{z.id || "–"}</td>
                  <td style={{ ...td, whiteSpace: "nowrap" }}>
                    <span style={{ color: farbe[st.art], fontWeight: 600 }}>● {st.text}</span>
                    <div style={{ fontSize: 11, color: "var(--text-dim)" }}>
                      {v?.geprueft_am ? `VIES ${datum(v.geprueft_am)}` : ""}{z.jtl ? `${v?.geprueft_am ? " · " : ""}JTL ${datum(z.jtl)}` : ""}
                    </div>
                  </td>
                  <td style={{ ...td, fontSize: 11.5, color: "var(--text-dim)", maxWidth: 320 }}>
                    {v?.name ? <div style={{ color: "var(--text-main)" }}>{v.name}</div> : null}
                    {v?.adresse || (v?.status === "gueltig" ? "Name/Anschrift gibt dieser Staat nicht heraus" : "")}
                  </td>
                  <td style={{ ...td, textAlign: "right" }}>{z.rechnungen}</td>
                  <td style={{ ...td, whiteSpace: "nowrap" }}>{datum(z.letzte)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <span style={{ fontSize: 12, color: "var(--text-dim)", lineHeight: 1.5 }}>
        Rechnungen der letzten 24 Monate, die JTL als steuerfreie innergemeinschaftliche Lieferung führt. Dafür braucht der Kunde eine
        gültige USt-ID eines anderen EU-Staats – sonst droht die Nachversteuerung. „Bei VIES prüfen“ fragt die einfache Bestätigung bei der
        EU-Kommission ab (gültig ja/nein, je nach Staat mit Name und Anschrift); den Nachweis mit Firmenname gegenüber dem Finanzamt
        liefert die qualifizierte Bestätigung beim BZSt. Eine Prüfung gilt {alterTage} Tage.
      </span>
    </div>
  );
}
