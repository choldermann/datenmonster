/**
 * Branchenprofil eines Marktlage-Pakets auf die vorhandenen Cockpits übertragen – in beliebig viele
 * Projekte und Mandanten auf einmal.
 *
 * Das Paket bleibt ERP-neutral; verknüpft wird über die Einstellungen, die die Cockpits schon haben
 * (je Projekt und Mandant):
 *   preisindex      → GF-Cockpit, Umsatz preisbereinigt
 *   branche         → GF-Cockpit, „Ich gegen meine Branche“
 *   kundenbranchen  → GF-Cockpit, Insolvenzklima der Kundenbranchen
 *   erzeugerpreise  → Einkaufs-Cockpit, Erzeugerpreise der eingekauften Waren
 * Nichts ist vorausgewählt: der Nutzer hakt Einstellungen und Ziele an.
 * Backend: GET /api/business-config/branchenprofil/stand, PUT /api/business-config/branchenprofil.
 *
 * widget.config.profil = { preisindex?: {key, region, label}, branche?: {code, label},
 *                          kundenbranchen?: [{code, label}], erzeugerpreise?: [{code, label}] }
 */
import { useEffect, useMemo, useState } from "react";
import { CheckCircle, Loader2, Link2, Search } from "lucide-react";
import api, { fehlerText } from "../../../api/client";

const S = { border: "var(--border)", dim: "var(--text-dim)", main: "var(--text-main)", bright: "var(--text-bright)" };

const ART = {
  preisindex: { titel: "Preisindex", lang: "Preisindex für die Preisbereinigung", wirkt: "GF-Cockpit › Umsatz preisbereinigt" },
  branche: { titel: "Branche", lang: "Vergleichsbranche", wirkt: "GF-Cockpit › Ich gegen meine Branche" },
  kundenbranchen: { titel: "Kundenbranchen", lang: "Kundenbranchen (Insolvenzklima)", wirkt: "GF-Cockpit › Kunden & Zahlungsmoral" },
  erzeugerpreise: { titel: "Erzeugerpreise", lang: "Erzeugerpreise der Einkaufswaren", wirkt: "Einkaufs-Cockpit › Markt, Preise & Währungen" },
} as const;
type Art = keyof typeof ART;
type Ziel = { project_id: number; project_name: string; mandant_id: number | null; mandant_name: string | null;
  darf_schreiben: boolean; werte: Record<string, any> };

const zielKey = (z: Ziel) => `${z.project_id}:${z.mandant_id ?? ""}`;

function text(art: Art, wert: any): string {
  if (!wert) return "";
  if (art === "preisindex") return wert.label || wert.region || "";
  if (art === "branche") return wert.label || wert.code || "";
  const liste = Array.isArray(wert) ? wert : (art === "kundenbranchen" ? wert.zweige : wert.gueter) || [];
  return liste.map((x) => x.label || x.code).join(" · ");
}

function gleich(art: Art, a: any, b: any) {
  if (!a || !b) return false;
  if (art === "preisindex") return a.key === b.key && a.region === b.region;
  if (art === "branche") return a.code === b.code;
  const la = (art === "kundenbranchen" ? a.zweige : a.gueter) || [];
  return la.map((x) => x.code).sort().join() === b.map((x) => x.code).sort().join();
}

export default function BranchenprofilWidget({ widget, projectId }) {
  const profil = widget.config?.profil || {};
  const arten = (Object.keys(ART) as Art[]).filter((a) => profil[a] && (!Array.isArray(profil[a]) || profil[a].length));
  const [ziele, setZiele] = useState<Ziel[] | null>(null);
  const [artWahl, setArtWahl] = useState<Record<string, boolean>>({});
  const [zielWahl, setZielWahl] = useState<Record<string, boolean>>({});
  const [suche, setSuche] = useState("");
  const [speichern, setSpeichern] = useState(false);
  const [meldung, setMeldung] = useState("");
  const [fehler, setFehler] = useState("");

  const laden = () => api.get("/api/business-config/branchenprofil/stand")
    .then(({ data }) => setZiele((data.ziele || []).filter((z) => z.project_id !== projectId)))
    .catch((e) => setFehler(fehlerText(e)));
  useEffect(() => { laden(); }, [projectId]);

  const sichtbar = useMemo(() => {
    const s = suche.trim().toLowerCase();
    return (ziele || []).filter((z) => !s || `${z.project_name} ${z.mandant_name || ""}`.toLowerCase().includes(s));
  }, [ziele, suche]);

  const gewaehlteArten = arten.filter((a) => artWahl[a]);
  const gewaehlteZiele = (ziele || []).filter((z) => zielWahl[zielKey(z)]);
  const alleSichtbarAn = sichtbar.filter((z) => z.darf_schreiben).every((z) => zielWahl[zielKey(z)]);

  const uebernehmen = async () => {
    setSpeichern(true); setFehler(""); setMeldung("");
    try {
      await api.put("/api/business-config/branchenprofil", {
        ziele: gewaehlteZiele.map((z) => ({ project_id: z.project_id, mandant_id: z.mandant_id })),
        profil: Object.fromEntries(gewaehlteArten.map((a) => [a, profil[a]])),
      });
      setMeldung(`${gewaehlteArten.length} ${gewaehlteArten.length === 1 ? "Einstellung" : "Einstellungen"} in `
        + `${gewaehlteZiele.length} ${gewaehlteZiele.length === 1 ? "Ziel" : "Ziele"} übernommen – die Cockpits zeigen das beim nächsten Laden.`);
      setZielWahl({});
      await laden();
    } catch (e) {
      setFehler(fehlerText(e, "Übernehmen fehlgeschlagen"));
    } finally { setSpeichern(false); }
  };

  if (!arten.length) return null;
  const zelle = { padding: "7px 10px", borderTop: `1px solid ${S.border}`, verticalAlign: "top" as const };
  return (
    <div style={{ padding: "12px 16px 16px", display: "flex", flexDirection: "column", gap: 12 }}>
      <p style={{ margin: 0, fontSize: 12.5, color: S.dim, lineHeight: 1.5 }}>
        Dieselben Marktdaten können Ihre Cockpits direkt neben den eigenen Zahlen zeigen. Haken Sie an, welche
        Einstellungen übernommen werden sollen und in welche Projekte und Mandanten – alles andere bleibt unverändert.
      </p>

      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <span style={{ fontSize: 12, color: S.dim }}>1. Was übernehmen?</span>
        {arten.map((a) => (
          <label key={a} style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: 13, color: S.main, cursor: "pointer" }}>
            <input type="checkbox" checked={!!artWahl[a]} onChange={(e) => setArtWahl({ ...artWahl, [a]: e.target.checked })}
              style={{ marginTop: 3 }} />
            <span><b style={{ color: S.bright, fontWeight: 600 }}>{ART[a].lang}:</b> {text(a, profil[a])}
              <span style={{ display: "block", fontSize: 11, color: S.dim }}>wirkt in {ART[a].wirkt}</span></span>
          </label>
        ))}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ fontSize: 12, color: S.dim }}>2. Wohin? (Projekt und Mandant)</span>
          <div style={{ position: "relative" }}>
            <Search size={12} style={{ position: "absolute", left: 8, top: 8, color: S.dim }} />
            <input value={suche} onChange={(e) => setSuche(e.target.value)} placeholder="Projekt oder Mandant suchen …"
              style={{ fontSize: 12, padding: "4px 8px 4px 24px", borderRadius: 8, border: `1px solid ${S.border}`,
                backgroundColor: "var(--bg-elevated)", color: S.bright, outline: "none", width: 220 }} />
          </div>
        </div>
        {ziele === null && !fehler && <span style={{ color: S.dim, fontSize: 12 }}><Loader2 size={13} className="animate-spin" /> Lädt …</span>}
        {ziele && (
          <div style={{ overflowX: "auto", border: `1px solid ${S.border}`, borderRadius: 10, maxHeight: 360, overflowY: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, minWidth: 640 }}>
              <thead><tr style={{ color: S.dim, textAlign: "left", position: "sticky", top: 0, background: "var(--bg-card)" }}>
                <th style={{ padding: "7px 10px", width: 28 }}>
                  <input type="checkbox" title="alle angezeigten" checked={sichtbar.length > 0 && alleSichtbarAn}
                    onChange={(e) => {
                      const n = { ...zielWahl };
                      sichtbar.filter((z) => z.darf_schreiben).forEach((z) => { n[zielKey(z)] = e.target.checked; });
                      setZielWahl(n);
                    }} />
                </th>
                <th style={{ padding: "7px 10px", fontWeight: 500 }}>Projekt</th>
                <th style={{ padding: "7px 10px", fontWeight: 500 }}>Mandant</th>
                {arten.map((a) => <th key={a} style={{ padding: "7px 10px", fontWeight: 500 }}>{ART[a].titel} bisher</th>)}
              </tr></thead>
              <tbody>
                {sichtbar.map((z) => (
                  <tr key={zielKey(z)} style={{ opacity: z.darf_schreiben ? 1 : 0.5 }}>
                    <td style={zelle}>
                      <input type="checkbox" disabled={!z.darf_schreiben} checked={!!zielWahl[zielKey(z)]}
                        title={z.darf_schreiben ? "" : "Keine Bearbeitungsrechte in diesem Projekt"}
                        onChange={(e) => setZielWahl({ ...zielWahl, [zielKey(z)]: e.target.checked })} />
                    </td>
                    <td style={{ ...zelle, color: S.bright }}>{z.project_name}</td>
                    <td style={{ ...zelle, color: z.mandant_name ? S.main : S.dim }}>{z.mandant_name || "–"}</td>
                    {arten.map((a) => {
                      const v = z.werte?.[a];
                      return (
                        <td key={a} style={{ ...zelle, color: v ? S.main : S.dim, maxWidth: 220 }}>
                          {gleich(a, v, profil[a])
                            ? <span style={{ color: "var(--ok)", display: "inline-flex", gap: 4, alignItems: "center" }}>
                                <CheckCircle size={12} /> wie Vorschlag</span>
                            : v ? text(a, v) : "–"}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {fehler && <p style={{ margin: 0, color: "var(--err)", fontSize: 12.5 }}>{fehler}</p>}
      {meldung && <p role="status" style={{ margin: 0, color: "var(--ok)", fontSize: 12.5 }}>{meldung}</p>}
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <button onClick={uebernehmen} className="btn-primary"
          disabled={speichern || !gewaehlteArten.length || !gewaehlteZiele.length}
          style={{ opacity: gewaehlteArten.length && gewaehlteZiele.length ? 1 : 0.5 }}>
          {speichern ? <Loader2 size={14} className="animate-spin" /> : <Link2 size={14} />}
          Übernehmen
        </button>
        <span style={{ fontSize: 12, color: S.dim }}>
          {gewaehlteArten.length} {gewaehlteArten.length === 1 ? "Einstellung" : "Einstellungen"} → {gewaehlteZiele.length} {gewaehlteZiele.length === 1 ? "Ziel" : "Ziele"}
          {gewaehlteZiele.some((z) => arten.some((a) => artWahl[a] && z.werte?.[a] && !gleich(a, z.werte[a], profil[a])))
            ? " · ersetzt vorhandene Einstellungen" : ""}
        </span>
      </div>
    </div>
  );
}
