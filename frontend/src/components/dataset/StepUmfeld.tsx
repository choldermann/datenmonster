// Dataset-Assistent › „Umfelddaten“: Reihen des monstersuite-Datendienstes (Destatis, Eurostat, DWD …)
// als Mapping-Quelle anlegen. Backend: app/plugins/builtin/umfeld (file_type „umfeld“).
import { useEffect, useMemo, useState } from "react";
import { CheckCircle, Globe, Loader2, AlertCircle, Search } from "lucide-react";
import api, { fehlerText } from "../../api/client";

export type Region = { code: string; label: string };
export type Groesse = {
  key: string; label: string; einheit: string; quelle: string; regionen_art: string; takt: string;
  stand: string | null; von: string | null; bis: string | null; hinweis: string | null; regionen: Region[];
  aktualisierung_h: number;
};

const S = {
  bgEl: "var(--bg-elevated)", border: "var(--border)", textMain: "var(--text-main)",
  textBright: "var(--text-bright)", textDim: "var(--text-dim)", accent: "var(--accent)",
};
const inputStyle = {
  backgroundColor: S.bgEl, border: `1px solid ${S.border}`, color: S.textBright,
  borderRadius: "0.5rem", padding: "0.4rem 0.75rem", width: "100%", outline: "none", fontSize: "0.875rem",
};
const labelStyle = {
  fontSize: "0.65rem", textTransform: "uppercase" as const, letterSpacing: "0.08em",
  color: S.textDim, display: "block", marginBottom: "0.3rem",
};

// Gruppen für die Übersicht – unbekannte Größen landen unter „Weitere“
export const GRUPPEN: [string, string[]][] = [
  ["Wetter & Gesundheit", ["temperatur", "niederschlag", "sonne", "hitzetage", "pollen", "atemwege", "grippe"]],
  ["Preise", ["preise_verbraucher", "preise_grosshandel", "erzeugerpreise", "kraftstoff", "wechselkurse"]],
  ["Branchen & Konjunktur", ["umsatz_handel", "umsatz_handel_real", "umsatz_handel_ka", "umsatz_handel_real_ka",
    "umsatz_gastgewerbe", "uebernachtungen", "stimmung", "insolvenzen"]],
  ["Bevölkerung & Kaufkraft", ["einwohner", "einkommen"]],
];

const ZEITRAEUME = [[12, "12 Monate"], [24, "2 Jahre"], [60, "5 Jahre"], [120, "10 Jahre"], [0, "alles"]] as const;

export function kurzQuelle(q: string) {
  return (q || "").split(/[,(–]/)[0].trim();
}

function RegionWahl({ g, gewaehlt, setGewaehlt }: { g: Groesse; gewaehlt: string[]; setGewaehlt: (r: string[]) => void }) {
  const [suche, setSuche] = useState("");
  const alle = gewaehlt.includes("*");
  const viele = g.regionen.length > 20;
  const treffer = useMemo(() => {
    const s = suche.trim().toLowerCase();
    const liste = s ? g.regionen.filter((r) => (r.code + " " + r.label).toLowerCase().includes(s)) : g.regionen;
    return viele ? liste.slice(0, 60) : liste;
  }, [suche, g.regionen, viele]);
  const umschalten = (code: string) =>
    setGewaehlt(gewaehlt.includes(code) ? gewaehlt.filter((x) => x !== code) : [...gewaehlt.filter((x) => x !== "*"), code]);

  if (g.regionen.length <= 1) return null;
  return (
    <div style={{ marginTop: 6, marginLeft: 22, display: "flex", flexDirection: "column", gap: 6 }}>
      <label className="flex items-center gap-2 text-xs" style={{ color: S.textMain, cursor: "pointer" }}>
        <input type="checkbox" checked={alle} onChange={() => setGewaehlt(alle ? [] : ["*"])} />
        alle {g.regionen.length} {g.regionen_art === "land" ? "Regionen" : "Einträge"}
        {g.regionen.length > 300 && <span style={{ color: S.textDim }}>(ergibt sehr viele Zeilen)</span>}
      </label>
      {!alle && (
        <>
          {viele && (
            <div style={{ position: "relative" }}>
              <Search size={12} style={{ position: "absolute", left: 8, top: 9, color: S.textDim }} />
              <input style={{ ...inputStyle, paddingLeft: 26, fontSize: 12 }} value={suche}
                onChange={(e) => setSuche(e.target.value)} placeholder="Suchen (Code oder Bezeichnung) …" />
            </div>
          )}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4, maxHeight: 160, overflowY: "auto" }}>
            {treffer.map((r) => {
              const an = gewaehlt.includes(r.code);
              return (
                <button key={r.code} type="button" onClick={() => umschalten(r.code)} title={r.code}
                  style={{
                    fontSize: 11, padding: "2px 8px", borderRadius: 999, cursor: "pointer",
                    border: `1px solid ${an ? S.accent : S.border}`,
                    backgroundColor: an ? "color-mix(in srgb, var(--accent) 12%, transparent)" : "transparent",
                    color: an ? S.textBright : S.textMain,
                  }}>
                  {r.label === r.code ? r.code : r.label}
                </button>
              );
            })}
          </div>
          {viele && <p style={{ fontSize: 10, color: S.textDim }}>
            {gewaehlt.length} gewählt{treffer.length === 60 ? " · Suche eingrenzen, es werden höchstens 60 Treffer gezeigt" : ""}
          </p>}
        </>
      )}
    </div>
  );
}

export default function StepUmfeld({ onDone, projectId }: { onDone: () => void; projectId?: number | null }) {
  const [katalog, setKatalog] = useState<Groesse[]>([]);
  const [laden, setLaden] = useState(true);
  const [fehler, setFehler] = useState("");
  const [wahl, setWahl] = useState<Record<string, string[]>>({});
  const [monate, setMonate] = useState<number>(60);
  const [format, setFormat] = useState<"lang" | "breit">("lang");
  const [name, setName] = useState("Umfelddaten");
  const [speichern, setSpeichern] = useState(false);
  const [fertig, setFertig] = useState(false);

  useEffect(() => {
    api.get("/api/umfeld/datenkatalog")
      .then(({ data }) => setKatalog(data.groessen || []))
      .catch((e) => setFehler(fehlerText(e, "Datenkatalog nicht erreichbar")))
      .finally(() => setLaden(false));
  }, []);

  const gruppen = useMemo(() => {
    const bekannt = new Set(GRUPPEN.flatMap(([, k]) => k));
    const nachKey = Object.fromEntries(katalog.map((g) => [g.key, g]));
    const aus = GRUPPEN.map(([t, keys]) => [t, keys.map((k) => nachKey[k]).filter(Boolean)] as [string, Groesse[]]);
    const rest = katalog.filter((g) => !bekannt.has(g.key));
    if (rest.length) aus.push(["Weitere", rest]);
    return aus.filter(([, l]) => l.length);
  }, [katalog]);

  const gewaehlt = Object.entries(wahl);
  const unvollstaendig = gewaehlt.filter(([k, r]) => {
    const g = katalog.find((x) => x.key === k);
    return g && g.regionen.length > 1 && r.length === 0;
  });

  const umschalten = (g: Groesse) => setWahl((w) => {
    const n = { ...w };
    if (n[g.key]) delete n[g.key];
    else {
      // sinnvolle Vorbelegung: Deutschland bzw. die einzige Region, sonst nichts (Nutzer wählt)
      const de = g.regionen.find((r) => r.code === "Deutschland" || r.code === "Insgesamt");
      n[g.key] = g.regionen.length === 1 ? [g.regionen[0].code] : de ? [de.code] : [];
    }
    return n;
  });

  const anlegen = async () => {
    setSpeichern(true); setFehler("");
    try {
      await api.post("/api/datasets/plugin", {
        name: name.trim(), source_type_id: "umfeld", project_id: projectId ?? null,
        query_config: { auswahl: gewaehlt.map(([groesse, regionen]) => ({ groesse, regionen })), monate, format },
      });
      setFertig(true);
      setTimeout(onDone, 800);
    } catch (e) {
      setFehler(fehlerText(e, "Dataset konnte nicht angelegt werden"));
    } finally { setSpeichern(false); }
  };

  if (fertig) return (
    <div className="flex flex-col items-center justify-center py-12 gap-3">
      <CheckCircle size={40} style={{ color: "var(--ok)" }} />
      <p className="text-sm font-medium" style={{ color: S.textBright }}>Dataset erstellt!</p>
    </div>
  );
  if (laden) return (
    <div className="flex items-center justify-center py-12 gap-2" style={{ color: S.textDim }}>
      <Loader2 size={16} className="animate-spin" /> Lade Datenkatalog …
    </div>
  );

  return (
    <div className="flex flex-col gap-5">
      <p className="text-xs" style={{ color: S.textDim, lineHeight: 1.5 }}>
        Amtliche Markt- und Umfelddaten als Dataset – im Mapping z. B. über die Spalte <b>Periode</b> (JJJJ-MM)
        mit dem eigenen Monatsumsatz verknüpfen. Es werden keine eigenen Daten übertragen, nur Größe, Region und Zeitraum.
      </p>

      {gruppen.map(([titel, liste]) => (
        <div key={titel}>
          <label style={labelStyle}>{titel}</label>
          <div className="flex flex-col gap-2">
            {liste.map((g) => {
              const an = !!wahl[g.key];
              return (
                <div key={g.key} className="rounded-lg px-3 py-2" style={{
                  backgroundColor: an ? "color-mix(in srgb, var(--accent) 6%, transparent)" : S.bgEl,
                  border: `1px solid ${an ? S.accent : S.border}`,
                }}>
                  <label className="flex items-start gap-2" style={{ cursor: "pointer" }}>
                    <input type="checkbox" checked={an} onChange={() => umschalten(g)} style={{ marginTop: 3 }}
                      disabled={!an && gewaehlt.length >= 12} />
                    <div style={{ minWidth: 0 }}>
                      <p className="text-xs font-medium" style={{ color: S.textBright }}>
                        {g.label} <span style={{ color: S.textDim, fontWeight: 400 }}>· {g.einheit}</span>
                      </p>
                      <p style={{ fontSize: 10, color: S.textDim }}>
                        {kurzQuelle(g.quelle)}
                        {g.von ? ` · ${g.von} bis ${g.bis}` : ""}
                        {g.takt === "jahr" ? " · Jahreswerte" : ""}
                        {g.hinweis ? ` · ${g.hinweis}` : ""}
                      </p>
                    </div>
                  </label>
                  {an && <RegionWahl g={g} gewaehlt={wahl[g.key]}
                    setGewaehlt={(r) => setWahl((w) => ({ ...w, [g.key]: r }))} />}
                </div>
              );
            })}
          </div>
        </div>
      ))}

      <div>
        <label style={labelStyle}>Zeitraum</label>
        <div className="flex gap-2 flex-wrap">
          {ZEITRAEUME.map(([m, t]) => (
            <button key={m} type="button" onClick={() => setMonate(m)} className="text-xs px-3 py-1 rounded"
              style={{ border: `1px solid ${monate === m ? S.accent : S.border}`, color: monate === m ? S.textBright : S.textMain }}>
              {t}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label style={labelStyle}>Aufbau</label>
        {([["lang", "Eine Zeile je Reihe und Monat", "Spalten Größe, Region, Periode, Wert, Einheit, Quelle – gut zum Filtern und für viele Regionen"],
           ["breit", "Eine Zeile je Monat", "eine Spalte je Reihe (z. B. temperatur_Bayern) – direkt neben den Monatsumsatz joinen"]] as const)
          .map(([k, t, d]) => (
            <label key={k} className="flex items-start gap-2 mb-1" style={{ cursor: "pointer" }}>
              <input type="radio" checked={format === k} onChange={() => setFormat(k)} style={{ marginTop: 3 }} />
              <span className="text-xs" style={{ color: S.textMain }}>{t}
                <span style={{ display: "block", fontSize: 10, color: S.textDim }}>{d}</span></span>
            </label>
          ))}
      </div>

      <div>
        <label style={labelStyle}>Dataset-Name</label>
        <input style={inputStyle} value={name} onChange={(e) => setName(e.target.value)} />
      </div>

      {unvollstaendig.length > 0 && (
        <p className="text-xs" style={{ color: "var(--warn, var(--text-dim))" }}>
          Bitte bei {unvollstaendig.map(([k]) => katalog.find((g) => g.key === k)?.label).join(", ")} mindestens eine Region wählen.
        </p>
      )}
      {fehler && (
        <div className="flex items-center gap-2 text-xs px-3 py-2 rounded"
          style={{ backgroundColor: "rgba(220,50,50,0.08)", border: "1px solid rgba(220,50,50,0.2)", color: "var(--err-soft)" }}>
          <AlertCircle size={13} /> {fehler}
        </div>
      )}

      <button onClick={anlegen} className="btn-primary w-full justify-center"
        disabled={speichern || !name.trim() || gewaehlt.length === 0 || unvollstaendig.length > 0}>
        {speichern ? <Loader2 size={14} className="animate-spin" /> : <Globe size={14} />}
        {speichern ? "Wird erstellt …" : `Dataset anlegen (${gewaehlt.length} ${gewaehlt.length === 1 ? "Größe" : "Größen"})`}
      </button>
      <p style={{ fontSize: 10, color: S.textDim, lineHeight: 1.4 }}>
        Quellenangabe ist Pflicht (Datenlizenz Deutschland 2.0, CC BY 4.0, Eurostat): sie steht in der Spalte „Quelle“
        (Aufbau „eine Zeile je Reihe“) – bei Weitergabe der Zahlen bitte mitnennen.
      </p>
    </div>
  );
}
