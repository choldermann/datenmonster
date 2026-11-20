/**
 * Branchenprofil eines Marktlage-Pakets auf die vorhandenen Cockpits übertragen.
 *
 * Das Paket bleibt ERP-neutral; verknüpft wird über die Einstellungen, die die Cockpits schon haben
 * (je Projekt und Mandant, /api/business-config/…):
 *   preisindex      → GF-Cockpit, Umsatz preisbereinigt
 *   branche         → GF-Cockpit, „Ich gegen meine Branche“
 *   kundenbranchen  → GF-Cockpit, Insolvenzklima der Kundenbranchen
 *   erzeugerpreise  → Einkaufs-Cockpit, Erzeugerpreise der eingekauften Waren
 * Nichts wird von selbst übernommen: der Nutzer hakt an, was gelten soll (vorhandene Auswahl bleibt sonst).
 *
 * widget.config.profil = { preisindex?: {key, region, label}, branche?: {code, label},
 *                          kundenbranchen?: [{code, label}], erzeugerpreise?: [{code, label}] }
 */
import { useEffect, useMemo, useState } from "react";
import { CheckCircle, Loader2, Link2 } from "lucide-react";
import api, { fehlerText } from "../../../api/client";

type Eintrag = { code: string; label: string };
const S = { border: "var(--border)", dim: "var(--text-dim)", main: "var(--text-main)", bright: "var(--text-bright)", accent: "var(--accent)" };

const ART = {
  preisindex: { titel: "Preisindex für die Preisbereinigung", wirkt: "GF-Cockpit › Umsatz preisbereinigt" },
  branche: { titel: "Vergleichsbranche", wirkt: "GF-Cockpit › Ich gegen meine Branche" },
  kundenbranchen: { titel: "Kundenbranchen (Insolvenzklima)", wirkt: "GF-Cockpit › Kunden & Zahlungsmoral" },
  erzeugerpreise: { titel: "Erzeugerpreise der Einkaufswaren", wirkt: "Einkaufs-Cockpit › Markt, Preise & Währungen" },
} as const;
type Art = keyof typeof ART;

function text(art: Art, wert: any): string {
  if (!wert) return "";
  if (art === "preisindex") return wert.label || wert.region || "";
  if (art === "branche") return wert.label || wert.code || "";
  const liste: Eintrag[] = art === "kundenbranchen" ? wert.zweige || wert : wert.gueter || wert;
  return (Array.isArray(liste) ? liste : []).map((x) => x.label || x.code).join(" · ");
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
  const [projekte, setProjekte] = useState<any[]>([]);
  const [ziel, setZiel] = useState<number | null>(null);
  const [aktuell, setAktuell] = useState<Record<string, any>>({});
  const [mandant, setMandant] = useState<string>("");
  const [laden, setLaden] = useState(false);
  const [wahl, setWahl] = useState<Record<string, boolean>>({});
  const [speichern, setSpeichern] = useState(false);
  const [meldung, setMeldung] = useState("");
  const [fehler, setFehler] = useState("");

  useEffect(() => {
    api.get("/api/projects/").then(({ data }) => {
      const liste = (data || []).filter((p) => p.id !== projectId);
      setProjekte(liste);
      if (liste.length === 1) setZiel(liste[0].id);
    }).catch(() => {});
  }, [projectId]);

  const holen = (pid: number, meldungBehalten = false) => {
    setLaden(true); setFehler(""); if (!meldungBehalten) setMeldung(""); setWahl({});
    Promise.all(arten.map((a) => api.get(`/api/business-config/${a}`, { params: { project_id: pid } })
      .then(({ data }) => [a, data] as const)))
      .then((xs) => {
        setAktuell(Object.fromEntries(xs.map(([a, d]) => [a, d.auswahl])));
        setMandant(xs[0]?.[1]?.mandant_name || "");
      })
      .catch((e) => setFehler(fehlerText(e)))
      .finally(() => setLaden(false));
  };
  useEffect(() => { if (ziel != null) holen(ziel); }, [ziel]);

  const gewaehlt = useMemo(() => arten.filter((a) => wahl[a]), [wahl, arten]);

  const uebernehmen = async () => {
    if (ziel == null) return;
    setSpeichern(true); setFehler(""); setMeldung("");
    try {
      for (const a of gewaehlt) {
        const v = profil[a];
        const body = a === "preisindex" ? { project_id: ziel, key: v.key, region: v.region, label: v.label }
          : a === "branche" ? { project_id: ziel, code: v.code, label: v.label }
          : a === "kundenbranchen" ? { project_id: ziel, zweige: v }
          : { project_id: ziel, gueter: v };
        await api.put(`/api/business-config/${a}`, body);
      }
      setMeldung(`${gewaehlt.length} ${gewaehlt.length === 1 ? "Einstellung" : "Einstellungen"} übernommen – die Cockpits zeigen das beim nächsten Laden.`);
      holen(ziel, true);
    } catch (e) {
      setFehler(fehlerText(e, "Übernehmen fehlgeschlagen"));
    } finally { setSpeichern(false); }
  };

  if (!arten.length) return null;
  return (
    <div style={{ padding: "12px 16px 16px", display: "flex", flexDirection: "column", gap: 12 }}>
      <p style={{ margin: 0, fontSize: 12.5, color: S.dim, lineHeight: 1.5 }}>
        Dieselben Marktdaten können Ihre Cockpits direkt neben den eigenen Zahlen zeigen. Wählen Sie das Projekt mit
        Ihren Cockpits und haken Sie an, was übernommen werden soll – vorhandene Einstellungen bleiben sonst unverändert.
      </p>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <label style={{ fontSize: 12, color: S.dim }}>Projekt mit den Cockpits</label>
        <select value={ziel ?? ""} onChange={(e) => setZiel(e.target.value ? Number(e.target.value) : null)}
          style={{ fontSize: 13, padding: "5px 8px", borderRadius: 8, border: `1px solid ${S.border}`,
            backgroundColor: "var(--bg-elevated)", color: S.bright }}>
          <option value="">– wählen –</option>
          {projekte.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        {mandant && <span style={{ fontSize: 12, color: S.dim }}>Mandant: {mandant}</span>}
        {laden && <Loader2 size={14} className="animate-spin" style={{ color: S.dim }} />}
      </div>

      {ziel != null && !laden && (
        <div style={{ overflowX: "auto", border: `1px solid ${S.border}`, borderRadius: 10 }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, minWidth: 640 }}>
            <thead><tr style={{ color: S.dim, textAlign: "left" }}>
              <th style={{ padding: "8px 10px", width: 28 }} />
              <th style={{ padding: "8px 10px", fontWeight: 500 }}>Einstellung</th>
              <th style={{ padding: "8px 10px", fontWeight: 500 }}>Bisher</th>
              <th style={{ padding: "8px 10px", fontWeight: 500 }}>Vorschlag aus diesem Paket</th>
            </tr></thead>
            <tbody>
              {arten.map((a) => {
                const schon = gleich(a, aktuell[a], profil[a]);
                return (
                  <tr key={a} style={{ borderTop: `1px solid ${S.border}`, verticalAlign: "top" }}>
                    <td style={{ padding: "8px 10px" }}>
                      {schon ? <CheckCircle size={14} style={{ color: "var(--ok)" }} />
                        : <input type="checkbox" checked={!!wahl[a]} onChange={(e) => setWahl({ ...wahl, [a]: e.target.checked })} />}
                    </td>
                    <td style={{ padding: "8px 10px", color: S.bright }}>
                      {ART[a].titel}
                      <div style={{ fontSize: 11, color: S.dim }}>wirkt in {ART[a].wirkt}</div>
                    </td>
                    <td style={{ padding: "8px 10px", color: aktuell[a] ? S.main : S.dim }}>
                      {aktuell[a] ? text(a, aktuell[a]) : "nicht eingestellt"}
                    </td>
                    <td style={{ padding: "8px 10px", color: schon ? S.dim : S.main }}>
                      {schon ? "bereits so eingestellt" : text(a, profil[a])}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {fehler && <p style={{ margin: 0, color: "var(--err)", fontSize: 12.5 }}>{fehler}</p>}
      {meldung && <p role="status" style={{ margin: 0, color: "var(--ok)", fontSize: 12.5 }}>{meldung}</p>}
      {ziel != null && (
        <div>
          <button onClick={uebernehmen} disabled={speichern || !gewaehlt.length} className="btn-primary"
            style={{ opacity: gewaehlt.length ? 1 : 0.5 }}>
            {speichern ? <Loader2 size={14} className="animate-spin" /> : <Link2 size={14} />}
            {gewaehlt.length ? `${gewaehlt.length} übernehmen` : "Auswahl übernehmen"}
          </button>
        </div>
      )}
    </div>
  );
}
