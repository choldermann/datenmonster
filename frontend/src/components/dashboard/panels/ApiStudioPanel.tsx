import { useState, useEffect, useCallback, useMemo } from "react";
import {
  Send, Plus, Trash2, Pencil, Loader2, X, FolderOpen, Save, History,
  Globe, ChevronRight, ChevronDown, Layers, Check, AlertTriangle, Table2,
  Sparkles, Bug, ShieldCheck, KeyRound, Workflow, FileJson,
} from "lucide-react";
import api from "../../../api/client";
import {
  KvEditor, AuthEditor, PaginationEditor, REST_AUTH_TYPES, METHODS, BODY_TYPES, TEMPLATE_VARS,
} from "./RestApiPanel";

const C = "#22d3ee";                       // Akzentfarbe des API Studios
const BASE = "/api/api-studio";

// Farbe je HTTP-Methode – dieselbe Sprache, die man aus API-Werkzeugen kennt.
const METHOD_COLOR = {
  GET: "#6ee7b7", POST: "#fbbf24", PUT: "#60a5fa", PATCH: "#c084fc",
  DELETE: "#f87171", HEAD: "#94a3b8", OPTIONS: "#94a3b8",
};

const LEER_REQUEST = {
  name: "", url: "", method: "GET",
  headers: {}, query_params: {},
  body_type: "none", body_content: "",
  auth_type: "inherit", auth_config: {},
  data_path: "", flatten: 1,
  collection_id: null, environment_id: null, description: "", store_response: 0,
  pagination: { type: "none" }, dataset_mode: "replace", cron_expr: "", active: 1,
};

const iS = { width: "100%", backgroundColor: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 6, color: "#f1f5f9", fontSize: 12, padding: "7px 10px", outline: "none", boxSizing: "border-box" as const };
const lS = { fontSize: 10, fontWeight: 700, textTransform: "uppercase" as const, letterSpacing: "0.07em", color: "#64748b", display: "block", marginBottom: 4 };
const btn = { padding: "7px 14px", borderRadius: 6, fontSize: 12, cursor: "pointer", backgroundColor: "transparent", border: "1px solid rgba(255,255,255,0.12)", color: "#94a3b8" };
const btnPrimary = { ...btn, backgroundColor: C, color: "#083344", border: "none", fontWeight: 700 };

function statusFarbe(code) {
  if (!code) return "#64748b";
  if (code < 300) return "#6ee7b7";
  if (code < 400) return "#60a5fa";
  if (code < 500) return "#fbbf24";
  return "#f87171";
}

function groesse(bytes) {
  if (bytes == null) return "–";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** Sehr schlichtes JSON-Einfärben – reicht, um Struktur schnell zu erfassen. */
function JsonAnsicht({ text }) {
  const teile = useMemo(() => {
    const out = [];
    const re = /("(?:\\.|[^"\\])*"\s*:)|("(?:\\.|[^"\\])*")|(\b-?\d+\.?\d*(?:[eE][+-]?\d+)?\b)|(\btrue\b|\bfalse\b|\bnull\b)/g;
    let last = 0, m;
    while ((m = re.exec(text)) !== null) {
      if (m.index > last) out.push({ t: text.slice(last, m.index), f: "#64748b" });
      const farbe = m[1] ? "#7dd3fc" : m[2] ? "#a5b4fc" : m[3] ? "#fbbf24" : "#f472b6";
      out.push({ t: m[0], f: farbe });
      last = m.index + m[0].length;
    }
    if (last < text.length) out.push({ t: text.slice(last), f: "#64748b" });
    return out;
  }, [text]);

  return (
    <pre style={{ margin: 0, fontFamily: "monospace", fontSize: 11, lineHeight: 1.6, whiteSpace: "pre", color: "#94a3b8" }}>
      {teile.map((p, i) => <span key={i} style={{ color: p.f }}>{p.t}</span>)}
    </pre>
  );
}

// ── Schalter ──────────────────────────────────────────────────────────────────

function Schalter({ an, onChange, label, hinweis }) {
  return (
    <label style={{ display: "flex", alignItems: "flex-start", gap: 8, cursor: "pointer" }}>
      <input type="checkbox" checked={an} onChange={e => onChange(e.target.checked)} style={{ marginTop: 2 }} />
      <span>
        <span style={{ fontSize: 12, color: "#94a3b8" }}>{label}</span>
        {hinweis && <span style={{ display: "block", fontSize: 10, color: "#475569", marginTop: 1 }}>{hinweis}</span>}
      </span>
    </label>
  );
}

// ── Analyse ───────────────────────────────────────────────────────────────────

/**
 * Erst rechnen, dann fragen: Struktur, Datenpfad und Paginierung stehen sofort
 * fest – ganz ohne Sprachmodell. Die KI-Deutung ist ein bewusster zweiter Schritt,
 * weil dabei (maskierte) Auszüge die Maschine verlassen können.
 */
function AnalysePanel({ antwort, kontext, aufDatenpfad, aufPaginierung, aufIntegration }) {
  const [daten, setDaten] = useState(null);
  const [laedt, setLaedt] = useState(false);
  const [kiLaedt, setKiLaedt] = useState(false);
  const [echteWerte, setEchteWerte] = useState(false);
  const [fehler, setFehler] = useState("");

  const analysieren = async (mitKi) => {
    const setzeLaden = mitKi ? setKiLaedt : setLaedt;
    setzeLaden(true); setFehler("");
    try {
      const { data } = await api.post(`${BASE}/analyze`, {
        body: antwort.json, response_headers: antwort.response_headers,
        status_code: antwort.status_code, url: kontext.url, method: kontext.method,
        data_path: kontext.data_path || null, project_id: kontext.projectId ?? null,
        mit_ki: mitKi, echte_werte: mitKi && echteWerte,
      });
      setDaten(data);
      if (data.ki_fehler) setFehler(data.ki_fehler);
    } catch (e) { setFehler(e.response?.data?.detail || "Analyse fehlgeschlagen"); }
    finally { setzeLaden(false); }
  };

  // Der rechnende Teil kostet nichts und ist sofort da – der läuft von selbst.
  useEffect(() => { setDaten(null); setFehler(""); analysieren(false); }, [antwort]);

  if (laedt && !daten) return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#64748b", fontSize: 12 }}>
      <Loader2 size={14} className="animate-spin" /> Antwort wird untersucht…
    </div>
  );
  if (!daten) return <p style={{ fontSize: 12, color: "#f87171" }}>{fehler || "Keine Analyse verfügbar."}</p>;

  const bedeutungen = {};
  (daten.ki?.felder || []).forEach(f => { bedeutungen[f.pfad] = f.bedeutung; });
  const pag = daten.paginierung || {};

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Datenpfad */}
      <div>
        <p style={{ ...lS, marginBottom: 6 }}>Wo die Daten liegen</p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
          {(daten.datenpfad_kandidaten || []).length === 0 && (
            <span style={{ fontSize: 11, color: "#475569" }}>Keine Liste gefunden – die Antwort ist ein Einzelobjekt.</span>
          )}
          {(daten.datenpfad_kandidaten || []).map(k => (
            <button key={k.pfad} onClick={() => aufDatenpfad(k.pfad)}
              title="Als Datenpfad übernehmen"
              style={{ padding: "4px 10px", borderRadius: 5, fontSize: 11, cursor: "pointer", fontFamily: "monospace",
                border: `1px solid ${daten.datenpfad === k.pfad ? C : "rgba(255,255,255,0.12)"}`,
                backgroundColor: daten.datenpfad === k.pfad ? `${C}18` : "transparent",
                color: daten.datenpfad === k.pfad ? C : "#94a3b8" }}>
              {k.pfad || "(Wurzel)"} <span style={{ color: "#475569" }}>· {k.zeilen}×{k.spalten}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Paginierung */}
      <div>
        <p style={{ ...lS, marginBottom: 6 }}>Weitere Seiten</p>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span style={{ fontSize: 11, color: pag.config ? "#6ee7b7" : "#64748b" }}>{pag.begruendung}</span>
          {pag.config && (
            <button onClick={() => aufPaginierung(pag.config)}
              style={{ ...btn, padding: "3px 10px", fontSize: 11, color: C, borderColor: `${C}55` }}>
              Paginierung übernehmen ({pag.typ})
            </button>
          )}
        </div>
      </div>

      {/* KI-Deutung */}
      <div style={{ padding: 12, borderRadius: 8, backgroundColor: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)" }}>
        {!daten.ki ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <ShieldCheck size={14} style={{ color: "#6ee7b7", flexShrink: 0 }} />
              <span style={{ fontSize: 11, color: "#64748b" }}>
                Bisher blieb alles auf dieser Maschine. Für die Deutung geht das Feld-Inventar an die KI –
                Beispielwerte maskiert (<code style={{ fontFamily: "monospace" }}>&lt;email&gt;</code>,
                <code style={{ fontFamily: "monospace" }}> &lt;text:12&gt;</code>), nie die vollständige Antwort.
              </span>
            </div>
            <Schalter an={echteWerte} onChange={setEchteWerte}
              label="Echte Beispielwerte mitsenden"
              hinweis="Zugangsdaten und klar personenbezogene Felder bleiben auch dann maskiert." />
            <button onClick={() => analysieren(true)} disabled={kiLaedt}
              style={{ ...btnPrimary, alignSelf: "flex-start", display: "flex", alignItems: "center", gap: 6, opacity: kiLaedt ? 0.5 : 1 }}>
              {kiLaedt ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />} Mit KI erklären
            </button>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <p style={{ fontSize: 12, color: "#e2e8f0", margin: 0, lineHeight: 1.6 }}>{daten.ki.zusammenfassung}</p>
            {daten.ki.vorgeschlagener_dataset_name && (
              <p style={{ fontSize: 11, color: "#64748b", margin: 0 }}>
                Vorgeschlagener Name: <strong style={{ color: C }}>{daten.ki.vorgeschlagener_dataset_name}</strong>
              </p>
            )}
            {(daten.ki.hinweise || []).length > 0 && (
              <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                {daten.ki.hinweise.map((h, i) => (
                  <li key={i} style={{ fontSize: 11, color: "#94a3b8", lineHeight: 1.6 }}>{h}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      {fehler && <p style={{ fontSize: 11, color: "#fbbf24" }}>{fehler}</p>}

      {/* Weiterverarbeiten */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: 12, borderRadius: 8, backgroundColor: `${C}0a`, border: `1px solid ${C}2a`, flexWrap: "wrap" }}>
        <Workflow size={15} style={{ color: C, flexShrink: 0 }} />
        <span style={{ fontSize: 11, color: "#94a3b8", flex: 1, minWidth: 200 }}>
          {kontext.restSourceId
            ? "Aus dieser Antwort einen Datenfluss machen: Dataset, wahlweise Mapping und Pipeline."
            : "Request zuerst speichern – danach lässt sich daraus ein Datenfluss anlegen."}
        </span>
        <button onClick={aufIntegration} disabled={!kontext.restSourceId}
          style={{ ...btnPrimary, opacity: kontext.restSourceId ? 1 : 0.4,
                   cursor: kontext.restSourceId ? "pointer" : "not-allowed" }}>
          Integration erstellen
        </button>
      </div>

      {/* Feld-Inventar */}
      <div>
        <p style={{ ...lS, marginBottom: 6 }}>Felder ({daten.inventar.length}) · {daten.zeilen} Datensätze untersucht</p>
        <div style={{ overflowX: "auto" }}>
          <table style={{ fontSize: 11, borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr>{["Feld", "Typ", "Gefüllt", "Beispiel", ...(daten.ki ? ["Bedeutung"] : [])].map(h => (
                <th key={h} style={{ textAlign: "left", padding: "4px 10px 6px 0", color: "#64748b", fontWeight: 600, borderBottom: "1px solid rgba(255,255,255,0.08)", whiteSpace: "nowrap" }}>{h}</th>
              ))}</tr>
            </thead>
            <tbody>
              {daten.inventar.map(f => (
                <tr key={f.pfad}>
                  <td style={{ padding: "4px 10px 4px 0", fontFamily: "monospace", color: "#e2e8f0", whiteSpace: "nowrap" }}>
                    {f.pfad}
                    {f.wirkt_wie_schluessel && <span title="Wert ist in allen Datensätzen eindeutig" style={{ marginLeft: 6, fontSize: 9, color: "#fbbf24" }}>◆</span>}
                  </td>
                  <td style={{ padding: "4px 10px 4px 0", color: "#94a3b8", whiteSpace: "nowrap" }}>{f.typ}</td>
                  <td style={{ padding: "4px 10px 4px 0", whiteSpace: "nowrap" }}>
                    <span style={{ display: "inline-block", width: 42, height: 5, borderRadius: 3, backgroundColor: "rgba(255,255,255,0.08)", verticalAlign: "middle", overflow: "hidden" }}>
                      <span style={{ display: "block", width: `${f.anteil_gefuellt * 100}%`, height: "100%", backgroundColor: f.anteil_gefuellt < 0.5 ? "#fbbf24" : "#6ee7b7" }} />
                    </span>
                    <span style={{ fontSize: 10, color: "#64748b", marginLeft: 6 }}>{Math.round(f.anteil_gefuellt * 100)}%</span>
                  </td>
                  <td style={{ padding: "4px 10px 4px 0", fontFamily: "monospace", color: "#64748b", maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {f.beispiel === null || f.beispiel === undefined ? "–" : String(f.beispiel)}
                  </td>
                  {daten.ki && <td style={{ padding: "4px 0", color: "#94a3b8" }}>{bedeutungen[f.pfad] || ""}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ── Fehler-Debugger ───────────────────────────────────────────────────────────

function DebugKasten({ antwort, kontext, onUebernehmen }) {
  const [d, setD] = useState(null);
  const [laedt, setLaedt] = useState(false);
  const [fehler, setFehler] = useState("");

  useEffect(() => { setD(null); setFehler(""); }, [antwort]);

  const untersuchen = async () => {
    setLaedt(true); setFehler("");
    try {
      const { data } = await api.post(`${BASE}/debug`, {
        url: kontext.url, method: kontext.method, headers: kontext.headers,
        query_params: kontext.query_params, body_type: kontext.body_type,
        auth_type: kontext.auth_type, project_id: kontext.projectId ?? null,
        status_code: antwort.status_code, reason: antwort.reason,
        response_body: (antwort.body_text || "").slice(0, 4000),
        error: antwort.error,
      });
      setD(data);
    } catch (e) { setFehler(e.response?.data?.detail || "KI-Analyse fehlgeschlagen"); }
    finally { setLaedt(false); }
  };

  return (
    <div style={{ margin: "12px 16px 0", padding: 12, borderRadius: 8, backgroundColor: "rgba(251,191,36,0.05)", border: "1px solid rgba(251,191,36,0.2)" }}>
      {!d ? (
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <Bug size={14} style={{ color: "#fbbf24", flexShrink: 0 }} />
          <span style={{ fontSize: 11, color: "#94a3b8", flex: 1 }}>
            Die Anfrage kam nicht durch. Die KI kann Anfrage und Fehlermeldung durchsehen –
            Zugangsdaten werden dabei maskiert.
          </span>
          <button onClick={untersuchen} disabled={laedt}
            style={{ ...btn, padding: "4px 12px", fontSize: 11, color: "#fbbf24", borderColor: "rgba(251,191,36,0.35)", display: "flex", alignItems: "center", gap: 6 }}>
            {laedt ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />} Fehler untersuchen
          </button>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <p style={{ fontSize: 12, color: "#e2e8f0", margin: 0, lineHeight: 1.6 }}>{d.diagnose}</p>
          {(d.pruefpunkte || []).length > 0 && (
            <ol style={{ margin: 0, paddingLeft: 18 }}>
              {d.pruefpunkte.map((p, i) => <li key={i} style={{ fontSize: 11, color: "#94a3b8", lineHeight: 1.7 }}>{p}</li>)}
            </ol>
          )}
          {(d.vorschlaege || []).length > 0 && (
            <div>
              <p style={{ ...lS, marginBottom: 6 }}>Vorschläge</p>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {d.vorschlaege.map((v, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", borderRadius: 6, backgroundColor: "rgba(255,255,255,0.03)" }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <code style={{ fontSize: 11, fontFamily: "monospace", color: C }}>{v.feld} = {v.neuer_wert}</code>
                      <p style={{ fontSize: 10, color: "#64748b", margin: "2px 0 0" }}>{v.begruendung}</p>
                    </div>
                    <button onClick={() => onUebernehmen(v.feld, v.neuer_wert)}
                      style={{ ...btn, padding: "3px 10px", fontSize: 11, flexShrink: 0 }}>Übernehmen</button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
      {fehler && <p style={{ fontSize: 11, color: "#f87171", margin: "8px 0 0" }}>{fehler}</p>}
    </div>
  );
}

// ── Variablen-Vorschläge ──────────────────────────────────────────────────────

/**
 * Was aus der Anfrage gehört in eine Umgebung? Der Vorschlag ist rein
 * deterministisch (Host + alles, was nach Zugangsdaten aussieht). Übernommen
 * wird nur, was der Nutzer ankreuzt – Vorauswahl gibt es bewusst keine.
 */
function VariablenDialog({ kontext, umgebungen, projectId, onFertig, onClose }) {
  const [vorschlaege, setVorschlaege] = useState(null);
  const [gewaehlt, setGewaehlt] = useState({});
  const [zielId, setZielId] = useState(umgebungen[0]?.id ?? "");
  const [neuName, setNeuName] = useState("");
  const [speichert, setSpeichert] = useState(false);
  const [fehler, setFehler] = useState("");

  useEffect(() => {
    api.post(`${BASE}/suggest-variables`, {
      url: kontext.url, headers: kontext.headers,
      query_params: kontext.query_params, project_id: projectId ?? null,
    }).then(({ data }) => setVorschlaege(data.vorschlaege))
      .catch(e => setFehler(e.response?.data?.detail || "Vorschläge konnten nicht geholt werden"));
  }, []);

  const uebernehmen = async () => {
    const auswahl = (vorschlaege || []).filter((_, i) => gewaehlt[i]);
    if (!auswahl.length) return;
    setSpeichert(true); setFehler("");
    try {
      const ziel = umgebungen.find(u => u.id === zielId);
      // Bestehende Variablen unverändert mitschicken: die Maske *** bedeutet
      // serverseitig „Wert behalten", sonst würden Geheimnisse überschrieben.
      const bestehend = ziel ? [...(ziel.variables || [])] : [];
      const namen = new Set(bestehend.map(v => v.key));
      auswahl.forEach(v => {
        if (!namen.has(v.key)) bestehend.push({ key: v.key, value: v.wert, secret: v.secret });
      });
      const payload = { name: ziel ? ziel.name : (neuName || "Standard"),
                        project_id: projectId ?? null, variables: bestehend };
      const { data } = ziel
        ? await api.put(`${BASE}/environments/${ziel.id}`, payload)
        : await api.post(`${BASE}/environments`, payload);
      onFertig(data, auswahl.map(v => ({ ersetzt: v.ersetzt, key: v.key })));
    } catch (e) { setFehler(e.response?.data?.detail || "Übernehmen fehlgeschlagen"); }
    finally { setSpeichert(false); }
  };

  const anzahl = Object.values(gewaehlt).filter(Boolean).length;

  return (
    <Dialog titel="Variablen vorschlagen" onClose={onClose}>
      {!vorschlaege ? (
        <p style={{ fontSize: 12, color: "#64748b" }}>{fehler || "Wird geprüft…"}</p>
      ) : vorschlaege.length === 0 ? (
        <p style={{ fontSize: 12, color: "#64748b" }}>
          In dieser Anfrage steckt nichts, was sich offensichtlich in eine Umgebung auslagern ließe.
        </p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <p style={{ fontSize: 11, color: "#64748b", margin: 0 }}>
            Ausgelagerte Werte stehen danach als <code style={{ fontFamily: "monospace" }}>{"{{name}}"}</code> in
            der Anfrage – so lässt sich zwischen Test und Produktion umschalten, ohne den Request anzufassen.
          </p>
          {vorschlaege.map((v, i) => (
            <div key={i} style={{ display: "flex", gap: 8, padding: 10, borderRadius: 6, backgroundColor: "rgba(255,255,255,0.03)" }}>
              <input type="checkbox" checked={!!gewaehlt[i]} style={{ marginTop: 2 }}
                onChange={e => setGewaehlt(g => ({ ...g, [i]: e.target.checked }))} />
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                  <code style={{ fontSize: 11, fontFamily: "monospace", color: C }}>{`{{${v.key}}}`}</code>
                  {v.secret && <span style={{ fontSize: 9, color: "#fbbf24", backgroundColor: "rgba(251,191,36,0.12)", padding: "1px 5px", borderRadius: 3 }}>geheim</span>}
                  <span style={{ fontSize: 10, color: "#475569" }}>aus {v.quelle}</span>
                </div>
                <p style={{ fontSize: 10, color: "#64748b", margin: "3px 0 0" }}>{v.begruendung}</p>
                <p style={{ fontSize: 10, color: "#475569", margin: "2px 0 0", fontFamily: "monospace", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {v.secret ? "•".repeat(Math.min(v.wert.length, 24)) : v.wert}
                </p>
              </div>
            </div>
          ))}

          <div>
            <label style={lS}>Ziel-Umgebung</label>
            <select style={iS} value={zielId} onChange={e => setZielId(e.target.value ? parseInt(e.target.value) : "")}>
              {umgebungen.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
              <option value="">Neue Umgebung anlegen…</option>
            </select>
            {zielId === "" && (
              <input style={{ ...iS, marginTop: 6 }} placeholder="Name der neuen Umgebung, z.B. Produktion"
                value={neuName} onChange={e => setNeuName(e.target.value)} />
            )}
          </div>
          {fehler && <p style={{ fontSize: 12, color: "#f87171", margin: 0 }}>{fehler}</p>}
        </div>
      )}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 18 }}>
        <button style={btn} onClick={onClose}>Abbrechen</button>
        <button style={{ ...btnPrimary, opacity: !anzahl || speichert ? 0.5 : 1 }}
          disabled={!anzahl || speichert} onClick={uebernehmen}>
          {speichert ? "Übernehme…" : `${anzahl || ""} übernehmen`}
        </button>
      </div>
    </Dialog>
  );
}

// ── OpenAPI-Import ────────────────────────────────────────────────────────────

/**
 * Aus einer OpenAPI-/Swagger-Beschreibung wird eine fertige Sammlung. Der
 * Nutzer sieht erst alle Endpunkte und wählt aus – importiert wird nichts,
 * was er nicht angekreuzt hat.
 */
function OpenApiDialog({ projectId, onFertig, onClose }) {
  const [quelle, setQuelle] = useState("url");     // "url" | "text"
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [spec, setSpec] = useState(null);
  const [laedt, setLaedt] = useState(false);
  const [fehler, setFehler] = useState("");

  const [gewaehlt, setGewaehlt] = useState({});
  const [suche, setSuche] = useState("");
  const [name, setName] = useState("");
  const [mitUmgebung, setMitUmgebung] = useState(false);
  const [werte, setWerte] = useState({});          // eingetragene Platzhalter-Werte
  const [legtAn, setLegtAn] = useState(false);
  const [erg, setErg] = useState(null);

  const einlesen = async () => {
    setLaedt(true); setFehler("");
    try {
      const { data } = await api.post(`${BASE}/openapi/import`, {
        url: quelle === "url" ? url : null,
        inhalt: quelle === "text" ? text : null,
        project_id: projectId ?? null,
      });
      setSpec(data);
      setName(data.titel || "API");
      setWerte({});
      setGewaehlt({});
    } catch (e) { setFehler(e.response?.data?.detail || "Einlesen fehlgeschlagen"); }
    finally { setLaedt(false); }
  };

  const anlegen = async () => {
    setLegtAn(true); setFehler("");
    try {
      const endpunkte = spec.endpunkte.filter(e => gewaehlt[e.id]);
      const { data } = await api.post(`${BASE}/openapi/create-collection`, {
        project_id: projectId ?? null, name,
        basis_url: spec.basis_url, beschreibung: spec.beschreibung?.slice(0, 500),
        auth_type: spec.auth_type, auth_config: spec.auth_config,
        endpunkte, umgebung_anlegen: mitUmgebung,
        umgebung_name: `${name} – Standard`, variablen,
      });
      setErg(data);
      onFertig();
    } catch (e) { setFehler(e.response?.data?.detail || "Anlegen fehlgeschlagen"); }
    finally { setLegtAn(false); }
  };

  // Nach Tag gruppieren – so ist auch eine Datei mit 300 Endpunkten benutzbar.
  const gruppen = useMemo(() => {
    if (!spec) return [];
    const suchbegriff = suche.trim().toLowerCase();
    const gefiltert = spec.endpunkte.filter(e =>
      !suchbegriff ||
      e.pfad.toLowerCase().includes(suchbegriff) ||
      (e.titel || "").toLowerCase().includes(suchbegriff));
    const nach = {};
    gefiltert.forEach(e => { (nach[e.tags?.[0] || "Allgemein"] ||= []).push(e); });
    return Object.entries(nach).sort(([a], [b]) => a.localeCompare(b));
  }, [spec, suche]);

  /**
   * Die vorgeschlagenen Platzhalter richten sich nach der Auswahl – eine Datei
   * mit 300 Endpunkten brächte sonst Dutzende Variablen mit, die keiner der
   * gewählten Requests je benutzt. Regel wie `platzhalter_sammeln` im Backend:
   * Pfad-Parameter immer, Query/Header nur, wenn Pflicht und ohne Beispielwert.
   */
  const variablen = useMemo(() => {
    if (!spec) return [];
    const namen = new Map();
    const merken = (p) => { if (!namen.has(p.name)) namen.set(p.name, p.beschreibung || ""); };
    spec.endpunkte.filter(e => gewaehlt[e.id]).forEach(e => {
      (e.pfad_parameter || []).forEach(merken);
      [...(e.query_parameter || []), ...(e.header_parameter || [])]
        .forEach(p => { if (p.pflicht && !p.beispiel) merken(p); });
    });
    return [...namen.entries()].sort(([a], [b]) => a.localeCompare(b))
      .map(([key, beschreibung]) => ({ key, value: werte[key] || "", secret: false, beschreibung }));
  }, [spec, gewaehlt, werte]);

  const anzahl = Object.values(gewaehlt).filter(Boolean).length;
  const alleUmschalten = (an) => {
    const neu = { ...gewaehlt };
    gruppen.forEach(([, eps]) => eps.forEach(e => { neu[e.id] = an; }));
    setGewaehlt(neu);
  };

  if (erg) return (
    <Dialog titel="Import abgeschlossen" onClose={onClose}>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", borderRadius: 6, backgroundColor: "rgba(110,231,183,0.06)", border: "1px solid rgba(110,231,183,0.2)" }}>
          <Check size={13} style={{ color: "#6ee7b7" }} />
          <span style={{ fontSize: 12, color: "#e2e8f0" }}>
            Sammlung <strong>{erg.sammlung.name}</strong> mit {erg.requests} Requests
            {erg.umgebung ? ` und Umgebung „${erg.umgebung.name}"` : ""}
          </span>
        </div>
        {erg.umgebung && (
          <p style={{ fontSize: 11, color: "#64748b", margin: 0 }}>
            Die Platzhalter in der Umgebung sind noch leer – dort die passenden Werte eintragen,
            dann laufen die Requests.
          </p>
        )}
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 18 }}>
        <button style={btnPrimary} onClick={onClose}>Schließen</button>
      </div>
    </Dialog>
  );

  return (
    <Dialog titel="OpenAPI importieren" onClose={onClose} breit>
      {!spec ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "flex", gap: 6 }}>
            {[["url", "Von URL"], ["text", "Datei einfügen"]].map(([v, l]) => (
              <button key={v} onClick={() => setQuelle(v)}
                style={{ padding: "5px 12px", borderRadius: 5, fontSize: 11, cursor: "pointer",
                  border: `1px solid ${quelle === v ? C : "rgba(255,255,255,0.1)"}`,
                  backgroundColor: quelle === v ? `${C}18` : "transparent",
                  color: quelle === v ? C : "#64748b" }}>{l}</button>
            ))}
          </div>
          {quelle === "url" ? (
            <div>
              <label style={lS}>Adresse der Beschreibung</label>
              <input style={iS} value={url} onChange={e => setUrl(e.target.value)} autoFocus
                placeholder="https://api.example.com/openapi.json"
                onKeyDown={e => { if (e.key === "Enter" && url) einlesen(); }} />
              <p style={{ fontSize: 10, color: "#475569", marginTop: 4 }}>
                Wird über denselben Netz-Schutz geladen wie jeder andere Request. JSON oder YAML, OpenAPI 3.x oder Swagger 2.0.
              </p>
            </div>
          ) : (
            <div>
              <label style={lS}>Inhalt der Datei</label>
              <textarea style={{ ...iS, minHeight: 200, fontFamily: "monospace", resize: "vertical" }}
                value={text} onChange={e => setText(e.target.value)}
                placeholder='{ "openapi": "3.0.0", … }  oder  openapi: 3.0.0' />
            </div>
          )}
          {fehler && <p style={{ fontSize: 12, color: "#f87171", margin: 0 }}>{fehler}</p>}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {/* Kopf der Beschreibung */}
          <div style={{ padding: 10, borderRadius: 6, backgroundColor: "rgba(255,255,255,0.03)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <strong style={{ fontSize: 12, color: "#e2e8f0" }}>{spec.titel}</strong>
              {spec.api_version && <span style={{ fontSize: 10, color: "#64748b" }}>v{spec.api_version}</span>}
              <span style={{ fontSize: 9, color: "#64748b", backgroundColor: "rgba(255,255,255,0.05)", padding: "1px 6px", borderRadius: 3 }}>Spec {spec.version}</span>
              {spec.auth_type !== "none" && (
                <span style={{ fontSize: 9, color: "#fbbf24", backgroundColor: "rgba(251,191,36,0.1)", padding: "1px 6px", borderRadius: 3 }}>{spec.auth_type}</span>
              )}
            </div>
            <p style={{ fontSize: 10, color: "#64748b", margin: "4px 0 0", fontFamily: "monospace" }}>
              {spec.basis_url || "— keine Basis-URL in der Datei —"}
            </p>
            {spec.abgeschnitten && (
              <p style={{ fontSize: 10, color: "#fbbf24", margin: "4px 0 0" }}>
                Sehr viele Endpunkte – es werden die ersten {spec.endpunkte.length} angezeigt.
              </p>
            )}
          </div>

          <div style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
            <div style={{ flex: 1 }}>
              <label style={lS}>Name der Sammlung</label>
              <input style={iS} value={name} onChange={e => setName(e.target.value)} />
            </div>
            <input style={{ ...iS, width: 190 }} placeholder="Endpunkte durchsuchen…"
              value={suche} onChange={e => setSuche(e.target.value)} />
          </div>

          {/* Endpunkte */}
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <span style={{ ...lS, marginBottom: 0 }}>Endpunkte ({anzahl} gewählt)</span>
              <button style={{ ...btn, padding: "2px 8px", fontSize: 10 }} onClick={() => alleUmschalten(true)}>alle</button>
              <button style={{ ...btn, padding: "2px 8px", fontSize: 10 }} onClick={() => alleUmschalten(false)}>keine</button>
            </div>
            <div style={{ maxHeight: 280, overflowY: "auto", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 6 }}>
              {gruppen.length === 0 && <p style={{ fontSize: 11, color: "#475569", padding: 12, margin: 0 }}>Nichts gefunden.</p>}
              {gruppen.map(([tag, eps]) => (
                <div key={tag}>
                  <div style={{ padding: "5px 10px", backgroundColor: "rgba(255,255,255,0.03)", fontSize: 10, fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.06em", position: "sticky", top: 0 }}>
                    {tag}
                  </div>
                  {eps.map(e => (
                    <label key={e.id} title={e.beschreibung || undefined}
                      style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 10px", cursor: "pointer", borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
                      <input type="checkbox" checked={!!gewaehlt[e.id]}
                        onChange={ev => setGewaehlt(g => ({ ...g, [e.id]: ev.target.checked }))} />
                      <span style={{ fontSize: 9, fontWeight: 700, fontFamily: "monospace", width: 48, flexShrink: 0, color: METHOD_COLOR[e.methode] || "#94a3b8" }}>{e.methode}</span>
                      <span style={{ fontSize: 11, fontFamily: "monospace", color: "#94a3b8", flexShrink: 0 }}>{e.pfad}</span>
                      <span style={{ fontSize: 10, color: "#475569", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{e.titel}</span>
                      {e.veraltet && <span style={{ fontSize: 9, color: "#f87171", flexShrink: 0, marginLeft: "auto" }}>veraltet</span>}
                    </label>
                  ))}
                </div>
              ))}
            </div>
          </div>

          {/* Platzhalter */}
          {variablen.length > 0 && (
            <div style={{ padding: 12, borderRadius: 8, backgroundColor: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)" }}>
              <Schalter an={mitUmgebung} onChange={setMitUmgebung}
                label={`Umgebung mit ${variablen.length} Platzhaltern anlegen`}
                hinweis="Pfad- und Pflichtparameter stehen in den Requests als {{name}} – hier lassen sich die Werte einmal zentral hinterlegen." />
              {mitUmgebung && (
                <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 10 }}>
                  {variablen.map(v => (
                    <div key={v.key} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      <code style={{ fontSize: 10, fontFamily: "monospace", color: C, width: 130, flexShrink: 0 }}>{`{{${v.key}}}`}</code>
                      <input style={{ ...iS, fontSize: 11, padding: "3px 6px" }} placeholder={v.beschreibung || "Wert"}
                        value={v.value} onChange={e => setWerte(p => ({ ...p, [v.key]: e.target.value }))} />
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {fehler && <p style={{ fontSize: 12, color: "#f87171", margin: 0 }}>{fehler}</p>}
        </div>
      )}

      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 18 }}>
        <button style={btn} onClick={onClose}>Abbrechen</button>
        {!spec ? (
          <button style={{ ...btnPrimary, opacity: laedt || (quelle === "url" ? !url : !text) ? 0.5 : 1 }}
            disabled={laedt || (quelle === "url" ? !url : !text)} onClick={einlesen}>
            {laedt ? "Wird gelesen…" : "Einlesen"}
          </button>
        ) : (
          <button style={{ ...btnPrimary, opacity: !anzahl || !name || legtAn ? 0.5 : 1 }}
            disabled={!anzahl || !name || legtAn} onClick={anlegen}>
            {legtAn ? "Wird angelegt…" : `${anzahl} übernehmen`}
          </button>
        )}
      </div>
    </Dialog>
  );
}

// ── Integration ───────────────────────────────────────────────────────────────

const ZIEL_TYPEN = ["string", "integer", "float", "boolean", "date", "datetime"];

/**
 * Vom getesteten Request zum laufenden Datenfluss. Es entsteht nichts Exotisches:
 * ein ganz normales Dataset, ein ganz normales Mapping und eine ganz normale
 * Pipeline – nur eben ohne dass man sie einzeln zusammenklicken muss.
 */
function IntegrationDialog({ antwort, kontext, restSourceId, umgebungen, envId, projectId, onFertig, onClose }) {
  const [vs, setVs] = useState(null);
  const [laedt, setLaedt] = useState(true);
  const [kiLaedt, setKiLaedt] = useState(false);
  const [mitMapping, setMitMapping] = useState(false);
  const [mitPipeline, setMitPipeline] = useState(false);
  const [cron, setCron] = useState("");
  const [umgebung, setUmgebung] = useState(envId ?? "");
  const [erg, setErg] = useState(null);
  const [legtAn, setLegtAn] = useState(false);
  const [fehler, setFehler] = useState("");

  const vorschau = async (mitKi) => {
    (mitKi ? setKiLaedt : setLaedt)(true); setFehler("");
    try {
      const { data } = await api.post(`${BASE}/integration/preview`, {
        rest_source_id: restSourceId, body: antwort.json, url: kontext.url,
        method: kontext.method, data_path: kontext.data_path || null,
        name: kontext.name || null, project_id: projectId ?? null, mit_ki: mitKi,
      });
      setVs(data);
      if (data.ki_fehler) setFehler(data.ki_fehler);
    } catch (e) { setFehler(e.response?.data?.detail || "Vorschau fehlgeschlagen"); }
    finally { (mitKi ? setKiLaedt : setLaedt)(false); }
  };

  useEffect(() => { vorschau(false); }, []);

  const setFeld = (i, k, v) => setVs(p => ({ ...p, felder: p.felder.map((f, j) => j === i ? { ...f, [k]: v } : f) }));

  const anlegen = async () => {
    setLegtAn(true); setFehler("");
    try {
      const { data } = await api.post(`${BASE}/integration/create`, {
        rest_source_id: restSourceId, dataset_name: vs.dataset_name,
        project_id: projectId ?? null,
        environment_id: umgebung === "" ? null : umgebung,
        felder: vs.felder.map(f => ({ quelle: f.quelle, ziel: f.ziel, typ: f.typ, uebernehmen: f.uebernehmen })),
        mit_mapping: mitMapping, mit_pipeline: mitPipeline,
        cron: cron || null,
      });
      setErg(data);
      onFertig();
    } catch (e) { setFehler(e.response?.data?.detail || "Anlegen fehlgeschlagen"); }
    finally { setLegtAn(false); }
  };

  const gewaehlt = (vs?.felder || []).filter(f => f.uebernehmen).length;

  if (erg) return (
    <Dialog titel="Integration angelegt" onClose={onClose}>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {[["Dataset", erg.dataset && `${erg.dataset.name} · ${erg.dataset.zeilen} Zeilen`],
          ["Mapping", erg.mapping && `${erg.mapping.name} → ${erg.mapping.ziel_dataset}`],
          ["Pipeline", erg.pipeline && `${erg.pipeline.name}${erg.pipeline.cron ? ` · ${erg.pipeline.cron}` : " · manuell"}`],
        ].filter(([, w]) => w).map(([l, w]) => (
          <div key={l} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", borderRadius: 6, backgroundColor: "rgba(110,231,183,0.06)", border: "1px solid rgba(110,231,183,0.2)" }}>
            <Check size={13} style={{ color: "#6ee7b7", flexShrink: 0 }} />
            <span style={{ fontSize: 11, color: "#64748b", width: 60 }}>{l}</span>
            <span style={{ fontSize: 12, color: "#e2e8f0" }}>{w}</span>
          </div>
        ))}
        <p style={{ fontSize: 11, color: "#64748b", margin: 0 }}>
          Zu finden unter Datasets{erg.mapping ? ", Mappings" : ""}{erg.pipeline ? " und Pipelines" : ""}.
        </p>
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 18 }}>
        <button style={btnPrimary} onClick={onClose}>Schließen</button>
      </div>
    </Dialog>
  );

  return (
    <Dialog titel="Integration erstellen" onClose={onClose} breit>
      {laedt && !vs ? (
        <p style={{ fontSize: 12, color: "#64748b" }}>{fehler || "Vorschlag wird erstellt…"}</p>
      ) : !vs ? (
        <p style={{ fontSize: 12, color: "#f87171" }}>{fehler}</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{ display: "flex", gap: 10, alignItems: "flex-end" }}>
            <div style={{ flex: 1 }}>
              <label style={lS}>Name des Datasets</label>
              <input style={iS} value={vs.dataset_name} onChange={e => setVs(p => ({ ...p, dataset_name: e.target.value }))} />
            </div>
            <button onClick={() => vorschau(true)} disabled={kiLaedt}
              style={{ ...btn, display: "flex", alignItems: "center", gap: 6, opacity: kiLaedt ? 0.5 : 1 }}>
              {kiLaedt ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />} Namen von der KI
            </button>
          </div>

          <div>
            <p style={{ ...lS, marginBottom: 6 }}>Spalten ({gewaehlt} von {vs.felder.length} übernommen)</p>
            <div style={{ maxHeight: 260, overflowY: "auto", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 6 }}>
              <table style={{ fontSize: 11, borderCollapse: "collapse", width: "100%" }}>
                <tbody>
                  {vs.felder.map((f, i) => (
                    <tr key={f.quelle} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)", opacity: f.uebernehmen ? 1 : 0.45 }}>
                      <td style={{ padding: "4px 8px", width: 26 }}>
                        <input type="checkbox" checked={f.uebernehmen} onChange={e => setFeld(i, "uebernehmen", e.target.checked)} />
                      </td>
                      <td style={{ padding: "4px 8px", fontFamily: "monospace", color: "#64748b", whiteSpace: "nowrap" }}>
                        {f.quelle}
                        {f.anteil_gefuellt < 0.5 && (
                          <span title="Nur selten gefüllt" style={{ marginLeft: 5, fontSize: 9, color: "#fbbf24" }}>
                            {Math.round(f.anteil_gefuellt * 100)}%
                          </span>
                        )}
                      </td>
                      <td style={{ padding: "4px 4px", color: "#475569" }}>→</td>
                      <td style={{ padding: "4px 8px" }}>
                        <input style={{ ...iS, fontSize: 11, padding: "3px 6px" }} value={f.ziel}
                          title={f.hinweis || undefined}
                          onChange={e => setFeld(i, "ziel", e.target.value)} />
                      </td>
                      <td style={{ padding: "4px 8px", width: 110 }}>
                        <select style={{ ...iS, fontSize: 11, padding: "3px 6px" }} value={f.typ}
                          onChange={e => setFeld(i, "typ", e.target.value)}>
                          {ZIEL_TYPEN.map(t => <option key={t} value={t}>{t}</option>)}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: 12, borderRadius: 8, backgroundColor: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)" }}>
            <p style={{ fontSize: 11, color: "#64748b", margin: 0 }}>
              Das Dataset wird immer angelegt und sofort mit echten Daten gefüllt
              {vs.paginierung?.config ? " (inklusive aller Seiten)" : ""}.
            </p>
            <Schalter an={mitMapping} onChange={setMitMapping}
              label="Mapping anlegen"
              hinweis="Benennt die Spalten wie oben um und schreibt in ein aufbereitetes Dataset." />
            <Schalter an={mitPipeline} onChange={setMitPipeline}
              label="Pipeline anlegen"
              hinweis="Holt die Daten künftig automatisch – wahlweise nach Zeitplan." />
            {mitPipeline && (
              <div style={{ display: "flex", gap: 10, paddingLeft: 24 }}>
                <div style={{ flex: 1 }}>
                  <label style={lS}>Zeitplan (leer = nur manuell)</label>
                  <input style={iS} value={cron} onChange={e => setCron(e.target.value)} placeholder='z.B. "0 6 * * *" = täglich 6 Uhr' />
                </div>
              </div>
            )}
            <div>
              <label style={lS}>Umgebung für geplante Läufe</label>
              <select style={iS} value={umgebung} onChange={e => setUmgebung(e.target.value ? parseInt(e.target.value) : "")}>
                <option value="">Ohne Umgebung</option>
                {umgebungen.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
              </select>
              <p style={{ fontSize: 10, color: "#475569", marginTop: 4 }}>
                Wird am Request hinterlegt – sonst stünden Platzhalter wie <code style={{ fontFamily: "monospace" }}>{"{{basis_url}}"}</code> beim
                geplanten Lauf wörtlich in der URL.
              </p>
            </div>
          </div>

          {fehler && <p style={{ fontSize: 12, color: "#f87171", margin: 0 }}>{fehler}</p>}
        </div>
      )}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 18 }}>
        <button style={btn} onClick={onClose}>Abbrechen</button>
        <button style={{ ...btnPrimary, opacity: !vs || !gewaehlt || legtAn ? 0.5 : 1 }}
          disabled={!vs || !gewaehlt || legtAn} onClick={anlegen}>
          {legtAn ? "Wird angelegt…" : "Anlegen"}
        </button>
      </div>
    </Dialog>
  );
}

// ── Antwort-Ansicht ───────────────────────────────────────────────────────────

function AntwortAnsicht({ antwort, aufDatenpfad, aufPaginierung, kontext, onUebernehmen, aufIntegration }) {
  const [reiter, setReiter] = useState("pretty");

  if (!antwort) return (
    <div style={{ padding: "48px 24px", textAlign: "center", color: "#475569" }}>
      <Send size={28} style={{ marginBottom: 10, opacity: 0.35 }} />
      <p style={{ fontSize: 13, margin: 0 }}>Noch keine Antwort – Request abschicken.</p>
    </div>
  );

  if (!antwort.success) return (
    <div style={{ paddingBottom: 16 }}>
      <div style={{ display: "flex", gap: 10, padding: 14, margin: 16, marginBottom: 0, borderRadius: 8, backgroundColor: "rgba(248,113,113,0.07)", border: "1px solid rgba(248,113,113,0.25)" }}>
        <AlertTriangle size={16} style={{ color: "#f87171", flexShrink: 0, marginTop: 1 }} />
        <div>
          <p style={{ fontSize: 12, color: "#f87171", fontWeight: 700, margin: 0 }}>Request nicht zustande gekommen</p>
          <p style={{ fontSize: 11, color: "#fca5a5", fontFamily: "monospace", margin: "6px 0 0", wordBreak: "break-word" }}>{antwort.error}</p>
        </div>
      </div>
      <DebugKasten antwort={antwort} kontext={kontext} onUebernehmen={onUebernehmen} />
    </div>
  );

  const pretty = antwort.json != null ? JSON.stringify(antwort.json, null, 2) : null;
  const REITER = [
    { id: "pretty", l: "Lesbar", aus: !pretty },
    { id: "raw", l: "Roh" },
    { id: "headers", l: `Header (${Object.keys(antwort.response_headers || {}).length})` },
    { id: "tabelle", l: `Tabelle${antwort.rows ? ` (${antwort.rows})` : ""}`, aus: !antwort.rows },
    { id: "analyse", l: "Analyse", aus: antwort.json == null },
  ].filter(r => !r.aus);
  const aktiv = REITER.some(r => r.id === reiter) ? reiter : REITER[0]?.id;

  return (
    <div>
      {/* Statuszeile */}
      <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "10px 16px", borderBottom: "1px solid rgba(255,255,255,0.06)", flexWrap: "wrap" }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: statusFarbe(antwort.status_code), fontFamily: "monospace" }}>
          {antwort.status_code} {antwort.reason}
        </span>
        <span style={{ fontSize: 11, color: "#64748b" }}>{antwort.duration_ms} ms</span>
        <span style={{ fontSize: 11, color: "#64748b" }}>{groesse(antwort.size_bytes)}</span>
        {antwort.content_type && (
          <span style={{ fontSize: 10, color: "#64748b", fontFamily: "monospace", backgroundColor: "rgba(255,255,255,0.04)", padding: "2px 6px", borderRadius: 3 }}>
            {antwort.content_type.split(";")[0]}
          </span>
        )}
        {antwort.truncated && (
          <span style={{ fontSize: 10, color: "#fbbf24" }}>Antwort gekürzt angezeigt</span>
        )}
      </div>

      {/* Bei einem Fehlerstatus gleich Hilfe anbieten */}
      {!antwort.ok && <DebugKasten antwort={antwort} kontext={kontext} onUebernehmen={onUebernehmen} />}

      {/* Hinweis, wo die Daten stecken */}
      {antwort.table_hint && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "12px 16px 0", padding: "8px 12px", borderRadius: 6, backgroundColor: `${C}0e`, border: `1px solid ${C}33` }}>
          <Table2 size={13} style={{ color: C, flexShrink: 0 }} />
          <span style={{ fontSize: 11, color: "#94a3b8" }}>
            Die Liste steckt vermutlich unter <code style={{ fontFamily: "monospace", color: C }}>{antwort.table_hint}</code>
          </span>
          <button onClick={() => aufDatenpfad(antwort.table_hint)}
            style={{ ...btn, marginLeft: "auto", padding: "3px 10px", fontSize: 11, borderColor: `${C}55`, color: C }}>
            Als Datenpfad übernehmen
          </button>
        </div>
      )}

      {/* Reiter */}
      <div style={{ display: "flex", gap: 2, padding: "10px 16px 0" }}>
        {REITER.map(r => (
          <button key={r.id} onClick={() => setReiter(r.id)}
            style={{ padding: "5px 12px", fontSize: 11, fontWeight: 600, cursor: "pointer", border: "none", borderRadius: 5,
              backgroundColor: aktiv === r.id ? `${C}18` : "transparent", color: aktiv === r.id ? C : "#64748b" }}>
            {r.l}
          </button>
        ))}
      </div>

      <div style={{ padding: 16, maxHeight: 420, overflow: "auto" }}>
        {aktiv === "pretty" && <JsonAnsicht text={pretty} />}
        {aktiv === "raw" && (
          <pre style={{ margin: 0, fontFamily: "monospace", fontSize: 11, lineHeight: 1.6, whiteSpace: "pre-wrap", wordBreak: "break-word", color: "#94a3b8" }}>
            {antwort.body_text || "(leerer Antwortkörper)"}
          </pre>
        )}
        {aktiv === "headers" && (
          <table style={{ fontSize: 11, borderCollapse: "collapse", width: "100%" }}>
            <tbody>
              {Object.entries(antwort.response_headers || {}).map(([k, v]) => (
                <tr key={k}>
                  <td style={{ padding: "3px 12px 3px 0", color: "#7dd3fc", fontFamily: "monospace", verticalAlign: "top", whiteSpace: "nowrap" }}>{k}</td>
                  <td style={{ padding: "3px 0", color: "#94a3b8", fontFamily: "monospace", wordBreak: "break-all" }}>{String(v)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {aktiv === "tabelle" && (
          <div style={{ overflowX: "auto" }}>
            <table style={{ fontSize: 10, borderCollapse: "collapse", minWidth: "max-content" }}>
              <thead>
                <tr>{antwort.columns.map(c => (
                  <th key={c} style={{ textAlign: "left", padding: "4px 10px", color: "#64748b", borderBottom: "1px solid rgba(255,255,255,0.08)", whiteSpace: "nowrap", fontFamily: "monospace" }}>{c}</th>
                ))}</tr>
              </thead>
              <tbody>
                {antwort.preview.map((row, i) => (
                  <tr key={i}>{antwort.columns.map(c => (
                    <td key={c} style={{ padding: "3px 10px", color: "#94a3b8", fontFamily: "monospace", whiteSpace: "nowrap", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis" }}>
                      {row[c] === null || row[c] === undefined ? "–" : String(row[c])}
                    </td>
                  ))}</tr>
                ))}
              </tbody>
            </table>
            {antwort.rows > antwort.preview.length && (
              <p style={{ fontSize: 10, color: "#475569", marginTop: 8 }}>
                Vorschau der ersten {antwort.preview.length} von {antwort.rows} Zeilen.
              </p>
            )}
          </div>
        )}
        {aktiv === "analyse" && (
          <AnalysePanel antwort={antwort} kontext={kontext}
            aufDatenpfad={aufDatenpfad} aufPaginierung={aufPaginierung}
            aufIntegration={aufIntegration} />
        )}
      </div>
    </div>
  );
}

// ── Sammlungs-Dialog ──────────────────────────────────────────────────────────

function SammlungsDialog({ initial, projectId, onSaved, onClose }) {
  const [f, setF] = useState({
    name: "", description: "", base_url: "", default_headers: {},
    auth_type: "none", auth_config: {}, ...(initial || {}),
  });
  const [saving, setSaving] = useState(false);
  const [fehler, setFehler] = useState("");
  const set = (k, v) => setF(p => ({ ...p, [k]: v }));

  const speichern = async () => {
    setSaving(true); setFehler("");
    try {
      const payload = { ...f, project_id: projectId ?? null };
      if (initial?.id) await api.put(`${BASE}/collections/${initial.id}`, payload);
      else await api.post(`${BASE}/collections`, payload);
      onSaved();
    } catch (e) { setFehler(e.response?.data?.detail || "Fehler beim Speichern"); }
    finally { setSaving(false); }
  };

  return (
    <Dialog titel={initial?.id ? "Sammlung bearbeiten" : "Neue Sammlung"} onClose={onClose}>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div><label style={lS}>Name</label>
          <input style={iS} value={f.name} onChange={e => set("name", e.target.value)} placeholder="z.B. Shopware Shop" autoFocus /></div>
        <div><label style={lS}>Basis-URL</label>
          <input style={iS} value={f.base_url || ""} onChange={e => set("base_url", e.target.value)} placeholder="https://api.example.com/v1" />
          <p style={{ fontSize: 10, color: "#475569", marginTop: 4 }}>Requests dürfen dann nur noch den Pfad angeben, z.B. <code style={{ fontFamily: "monospace" }}>/orders</code>. Eine vollständige URL im Request gewinnt.</p>
        </div>
        <div><label style={lS}>Beschreibung</label>
          <input style={iS} value={f.description || ""} onChange={e => set("description", e.target.value)} /></div>
        <KvEditor label="Standard-Header" value={f.default_headers} onChange={v => set("default_headers", v)} />
        <div>
          <label style={lS}>Standard-Auth</label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 4 }}>
            {REST_AUTH_TYPES.map(a => (
              <button key={a.v} onClick={() => { set("auth_type", a.v); set("auth_config", {}); }}
                style={{ padding: "5px 12px", borderRadius: 5, fontSize: 11, cursor: "pointer",
                  border: `1px solid ${f.auth_type === a.v ? C : "rgba(255,255,255,0.1)"}`,
                  backgroundColor: f.auth_type === a.v ? `${C}18` : "transparent",
                  color: f.auth_type === a.v ? C : "#64748b" }}>{a.l}</button>
            ))}
          </div>
          <AuthEditor authType={f.auth_type} authConfig={f.auth_config || {}} onChange={v => set("auth_config", v)} />
        </div>
        {fehler && <p style={{ fontSize: 12, color: "#f87171" }}>{fehler}</p>}
      </div>
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 18 }}>
        <button style={btn} onClick={onClose}>Abbrechen</button>
        <button style={{ ...btnPrimary, opacity: !f.name || saving ? 0.5 : 1 }} disabled={!f.name || saving} onClick={speichern}>
          {saving ? "Speichern…" : "Speichern"}
        </button>
      </div>
    </Dialog>
  );
}

// ── Umgebungs-Dialog ──────────────────────────────────────────────────────────

function UmgebungsDialog({ umgebungen, projectId, onChanged, onClose }) {
  const [auswahl, setAuswahl] = useState(umgebungen[0] || null);
  const [f, setF] = useState(umgebungen[0] || { name: "", variables: [] });
  const [saving, setSaving] = useState(false);
  const [fehler, setFehler] = useState("");

  const waehlen = (u) => { setAuswahl(u); setF(u ? { ...u } : { name: "", variables: [] }); setFehler(""); };
  const setVar = (i, k, v) => setF(p => ({ ...p, variables: p.variables.map((x, j) => j === i ? { ...x, [k]: v } : x) }));

  const speichern = async () => {
    setSaving(true); setFehler("");
    try {
      const payload = { ...f, project_id: projectId ?? null, variables: f.variables || [] };
      if (f.id) await api.put(`${BASE}/environments/${f.id}`, payload);
      else await api.post(`${BASE}/environments`, payload);
      await onChanged();
      onClose();
    } catch (e) { setFehler(e.response?.data?.detail || "Fehler beim Speichern"); }
    finally { setSaving(false); }
  };

  const loeschen = async () => {
    if (!f.id || !window.confirm(`Umgebung „${f.name}" löschen?`)) return;
    await api.delete(`${BASE}/environments/${f.id}`);
    await onChanged();
    onClose();
  };

  return (
    <Dialog titel="Umgebungen" onClose={onClose} breit>
      <div style={{ display: "grid", gridTemplateColumns: "180px 1fr", gap: 16 }}>
        {/* Liste */}
        <div style={{ borderRight: "1px solid rgba(255,255,255,0.07)", paddingRight: 12 }}>
          {umgebungen.map(u => (
            <button key={u.id} onClick={() => waehlen(u)}
              style={{ display: "block", width: "100%", textAlign: "left", padding: "6px 8px", borderRadius: 5, fontSize: 12, cursor: "pointer", border: "none", marginBottom: 2,
                backgroundColor: f.id === u.id ? `${C}18` : "transparent", color: f.id === u.id ? C : "#94a3b8" }}>
              {u.name}
            </button>
          ))}
          <button onClick={() => waehlen(null)}
            style={{ display: "flex", alignItems: "center", gap: 5, width: "100%", padding: "6px 8px", borderRadius: 5, fontSize: 12, cursor: "pointer", border: "none", backgroundColor: "transparent", color: "#64748b", marginTop: 4 }}>
            <Plus size={12} /> Neue Umgebung
          </button>
        </div>

        {/* Bearbeiten */}
        <div>
          <label style={lS}>Name</label>
          <input style={{ ...iS, marginBottom: 14 }} value={f.name || ""} onChange={e => setF(p => ({ ...p, name: e.target.value }))} placeholder="z.B. Produktion" />

          <label style={lS}>Variablen</label>
          <p style={{ fontSize: 10, color: "#475569", margin: "0 0 8px" }}>
            Im Request als <code style={{ fontFamily: "monospace" }}>{"{{name}}"}</code> einsetzbar. Geheime Werte werden verschlüsselt gespeichert und nie zurückgegeben.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 5, marginBottom: 8 }}>
            {(f.variables || []).map((v, i) => (
              <div key={i} style={{ display: "flex", gap: 5, alignItems: "center" }}>
                <input style={{ ...iS, fontSize: 11, padding: "4px 8px", flex: "0 0 140px" }} placeholder="name"
                  value={v.key || ""} onChange={e => setVar(i, "key", e.target.value)} />
                <input style={{ ...iS, fontSize: 11, padding: "4px 8px", flex: 1 }} placeholder="Wert"
                  type={v.secret ? "password" : "text"}
                  value={v.value || ""} onChange={e => setVar(i, "value", e.target.value)} />
                <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10, color: "#64748b", cursor: "pointer", whiteSpace: "nowrap" }}>
                  <input type="checkbox" checked={!!v.secret} onChange={e => setVar(i, "secret", e.target.checked)} /> geheim
                </label>
                <button onClick={() => setF(p => ({ ...p, variables: p.variables.filter((_, j) => j !== i) }))}
                  style={{ color: "#f87171", fontSize: 14, padding: "2px 4px", background: "none", border: "none", cursor: "pointer" }}>×</button>
              </div>
            ))}
          </div>
          <button onClick={() => setF(p => ({ ...p, variables: [...(p.variables || []), { key: "", value: "", secret: false }] }))}
            style={{ ...btn, padding: "4px 10px", fontSize: 11, color: C, borderColor: `${C}44` }}>
            <Plus size={11} style={{ display: "inline", marginRight: 4 }} /> Variable
          </button>

          {fehler && <p style={{ fontSize: 12, color: "#f87171", marginTop: 10 }}>{fehler}</p>}
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 18 }}>
        {f.id && <button style={{ ...btn, color: "#f87171", borderColor: "rgba(248,113,113,0.25)", marginRight: "auto" }} onClick={loeschen}>Löschen</button>}
        <button style={btn} onClick={onClose}>Schließen</button>
        <button style={{ ...btnPrimary, opacity: !f.name || saving ? 0.5 : 1 }} disabled={!f.name || saving} onClick={speichern}>
          {saving ? "Speichern…" : "Speichern"}
        </button>
      </div>
    </Dialog>
  );
}

// ── Verlauf ───────────────────────────────────────────────────────────────────

function VerlaufsListe({ eintraege, onLaden, onLeeren, canEdit }) {
  if (!eintraege.length) return (
    <p style={{ fontSize: 12, color: "#475569", padding: "24px 16px", textAlign: "center" }}>Noch keine Requests geschickt.</p>
  );
  return (
    <div>
      {canEdit && (
        <div style={{ display: "flex", justifyContent: "flex-end", padding: "8px 12px" }}>
          <button style={{ ...btn, padding: "3px 10px", fontSize: 11, color: "#f87171", borderColor: "rgba(248,113,113,0.22)" }} onClick={onLeeren}>
            Verlauf leeren
          </button>
        </div>
      )}
      <div style={{ display: "flex", flexDirection: "column" }}>
        {eintraege.map(h => (
          <button key={h.id} onClick={() => onLaden(h)}
            style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", background: "none", border: "none", borderBottom: "1px solid rgba(255,255,255,0.04)", cursor: "pointer", textAlign: "left", width: "100%" }}>
            <span style={{ fontSize: 9, fontWeight: 700, fontFamily: "monospace", color: METHOD_COLOR[h.method] || "#94a3b8", flex: "0 0 52px" }}>{h.method}</span>
            <span style={{ fontSize: 11, fontWeight: 700, fontFamily: "monospace", color: statusFarbe(h.status_code), flex: "0 0 34px" }}>{h.status_code ?? "—"}</span>
            <span style={{ fontSize: 11, color: "#94a3b8", fontFamily: "monospace", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{h.url}</span>
            <span style={{ fontSize: 10, color: "#475569", flexShrink: 0 }}>{h.duration_ms} ms</span>
            <span style={{ fontSize: 10, color: "#475569", flexShrink: 0 }}>{new Date(h.created_at).toLocaleTimeString("de-DE")}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Dialog-Hülle ──────────────────────────────────────────────────────────────

function Dialog({ titel, children, onClose, breit }) {
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60, padding: 20 }}>
      <div onClick={e => e.stopPropagation()}
        style={{ backgroundColor: "#0f172a", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, width: breit ? 760 : 520, maxWidth: "100%", maxHeight: "88vh", overflowY: "auto", padding: 20 }}>
        <div style={{ display: "flex", alignItems: "center", marginBottom: 16 }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: "#f1f5f9", margin: 0 }}>{titel}</h3>
          <button onClick={onClose} style={{ marginLeft: "auto", color: "#64748b", background: "none", border: "none", cursor: "pointer" }}><X size={16} /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

// ── Hauptpanel ────────────────────────────────────────────────────────────────

function ApiStudioPanel({ projectId, canEdit }) {
  const [sammlungen, setSammlungen] = useState([]);
  const [requests, setRequests] = useState([]);
  const [umgebungen, setUmgebungen] = useState([]);
  const [verlauf, setVerlauf] = useState([]);

  const [envId, setEnvId] = useState(null);
  const [offen, setOffen] = useState({});           // aufgeklappte Sammlungen
  const [aktiveId, setAktiveId] = useState(null);   // id des geladenen Requests
  const [f, setF] = useState(LEER_REQUEST);
  const [reiter, setReiter] = useState("params");

  const [antwort, setAntwort] = useState(null);
  const [sende, setSende] = useState(false);
  const [speichere, setSpeichere] = useState(false);
  const [fehler, setFehler] = useState("");
  const [dialog, setDialog] = useState(null);       // "sammlung" | "umgebung" | "verlauf"
  const [sammlungEdit, setSammlungEdit] = useState(null);

  const p = projectId ? { project_id: projectId } : {};

  const laden = useCallback(async () => {
    try {
      const [c, r, u] = await Promise.all([
        api.get(`${BASE}/collections`, { params: p }),
        api.get("/api/rest-sources/", { params: p }),
        api.get(`${BASE}/environments`, { params: p }),
      ]);
      setSammlungen(c.data);
      setRequests(r.data);
      setUmgebungen(u.data);
      setEnvId(prev => (u.data.some(e => e.id === prev) ? prev
        : (u.data.find(e => e.is_default)?.id ?? null)));
    } catch { /* Panel bleibt leer */ }
  }, [projectId]);

  const verlaufLaden = useCallback(async () => {
    try {
      const { data } = await api.get(`${BASE}/history`, { params: { ...p, limit: 100 } });
      setVerlauf(data);
    } catch { /* ignorieren */ }
  }, [projectId]);

  useEffect(() => { laden(); verlaufLaden(); }, [laden, verlaufLaden]);

  const set = (k, v) => setF(prev => ({ ...prev, [k]: v }));

  const requestLaden = (r) => {
    setAktiveId(r.id);
    setF({ ...LEER_REQUEST, ...r, auth_config: r.auth_config || {}, body_content: r.body_content || "" });
    setAntwort(null); setFehler("");
    // Hat der Request eine Umgebung hinterlegt, gilt sie auch hier. Sonst legt
    // etwa der OpenAPI-Import eine Umgebung an, und der Nutzer sähe trotzdem
    // „Ohne Umgebung" – seine {{platzhalter}} blieben beim Senden stehen.
    if (r.environment_id && umgebungen.some(u => u.id === r.environment_id)) {
      setEnvId(r.environment_id);
    }
  };

  const neuerRequest = (collectionId = null) => {
    setAktiveId(null);
    setF({ ...LEER_REQUEST, collection_id: collectionId });
    setAntwort(null); setFehler("");
  };

  const senden = async () => {
    setSende(true); setFehler(""); setAntwort(null);
    try {
      const { data } = await api.post(`${BASE}/send`, {
        rest_source_id: aktiveId, collection_id: f.collection_id,
        environment_id: envId, project_id: projectId ?? null,
        name: f.name || null, url: f.url, method: f.method,
        headers: f.headers, query_params: f.query_params,
        body_type: f.body_type, body_content: f.body_content,
        auth_type: f.auth_type, auth_config: f.auth_config,
        data_path: f.data_path || null, flatten: f.flatten,
      });
      setAntwort(data);
      verlaufLaden();
    } catch (e) {
      setFehler(e.response?.data?.detail || "Request fehlgeschlagen");
    } finally { setSende(false); }
  };

  const speichern = async () => {
    setSpeichere(true); setFehler("");
    try {
      const payload = { ...f, project_id: projectId ?? null,
        data_path: f.data_path || null,
        pagination: f.pagination || { type: "none" } };
      const { data } = aktiveId
        ? await api.put(`/api/rest-sources/${aktiveId}`, payload)
        : await api.post("/api/rest-sources/", payload);
      setAktiveId(data.id);
      await laden();
    } catch (e) { setFehler(e.response?.data?.detail || "Speichern fehlgeschlagen"); }
    finally { setSpeichere(false); }
  };

  /**
   * Einen KI-Vorschlag in das Formular übernehmen. Bewusst nur auf Klick –
   * die KI ändert nie selbst etwas an der Anfrage.
   */
  const vorschlagUebernehmen = (feld, wert) => {
    const AUTH_ALIAS = { api_key: "apikey", apikey: "apikey", bearer: "bearer", basic: "basic",
                         none: "none", oauth2: "oauth2_cc", oauth2_cc: "oauth2_cc",
                         client_credentials: "oauth2_cc", refresh_token: "oauth2_refresh" };
    if (feld === "url") set("url", wert);
    else if (feld === "method") set("method", String(wert).toUpperCase());
    else if (feld === "auth_type") set("auth_type", AUTH_ALIAS[String(wert).toLowerCase()] || wert);
    else if (feld === "body_type") set("body_type", wert);
    else if (feld === "body_content") set("body_content", wert);
    else if (feld.startsWith("header:")) set("headers", { ...f.headers, [feld.slice(7)]: wert });
    else if (feld.startsWith("query:")) set("query_params", { ...f.query_params, [feld.slice(6)]: wert });
    else return;
    setFehler("");
  };

  const requestLoeschen = async (r) => {
    if (!window.confirm(`Request „${r.name}" löschen?`)) return;
    await api.delete(`/api/rest-sources/${r.id}`);
    if (aktiveId === r.id) neuerRequest();
    laden();
  };

  const sammlungLoeschen = async (c) => {
    if (!window.confirm(`Sammlung „${c.name}" löschen? Die Requests bleiben erhalten.`)) return;
    await api.delete(`${BASE}/collections/${c.id}`);
    laden();
  };

  const verlaufEintragLaden = async (h) => {
    const s = h.request_snapshot || (await api.get(`${BASE}/history/${h.id}`)).data.request_snapshot || {};
    setAktiveId(h.rest_source_id ?? null);
    setF(prev => ({ ...prev, url: s.url || h.url, method: s.method || h.method,
      query_params: s.query_params || {}, body_type: s.body_type || "none",
      body_content: s.body_content || "" }));
    setDialog(null);
  };

  const ohneSammlung = requests.filter(r => !r.collection_id);
  const envVars = umgebungen.find(u => u.id === envId)?.variables || [];
  const alleVars = [...envVars.map(v => `{{${v.key}}}`), ...TEMPLATE_VARS];

  /**
   * Platzhalter, für die es keinen Wert gibt. Ohne diesen Hinweis geht die
   * Anfrage mit dem Platzhalter im Klartext hinaus, und die API antwortet mit
   * einer Fehlermeldung, die nach einem Fehler der API aussieht – tatsächlich
   * fehlt nur eine Umgebung. Eine leer gelassene Variable zählt mit: sie würde
   * gegen einen leeren Text ersetzt und die URL genauso unbrauchbar machen.
   */
  const offenePlatzhalter = useMemo(() => {
    const bekannt = new Set([
      ...TEMPLATE_VARS.map(v => v.replace(/[{}]/g, "")),
      ...envVars.filter(v => v.value !== "" && v.value != null).map(v => v.key),
    ]);
    const texte = [f.url, f.body_content,
      ...Object.values(f.query_params || {}), ...Object.values(f.headers || {})];
    const offen = new Set();
    texte.forEach(t => {
      String(t || "").replace(/\{\{\s*([^{}]+?)\s*\}\}/g, (_, name) => {
        if (!bekannt.has(name)) offen.add(name);
        return "";
      });
    });
    return [...offen];
  }, [f.url, f.body_content, f.query_params, f.headers, envVars]);

  const REITER = [
    { id: "params", l: `Params${Object.keys(f.query_params || {}).length ? ` (${Object.keys(f.query_params).length})` : ""}` },
    { id: "headers", l: `Headers${Object.keys(f.headers || {}).length ? ` (${Object.keys(f.headers).length})` : ""}` },
    { id: "body", l: "Body" },
    { id: "auth", l: "Auth" },
    { id: "daten", l: "Datenpfad" },
  ];

  return (
    <div style={{ maxWidth: 1400, margin: "0 auto", padding: "20px 0" }}>
      {/* Kopfzeile */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
        <div style={{ width: 38, height: 38, borderRadius: 8, backgroundColor: `${C}18`, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Globe size={18} style={{ color: C }} />
        </div>
        <div>
          <h2 style={{ fontSize: 15, fontWeight: 700, color: "#f1f5f9", margin: 0 }}>API Studio</h2>
          <p style={{ fontSize: 12, color: "#64748b", margin: 0 }}>REST-APIs testen, verstehen und als Connector speichern</p>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
          <select style={{ ...iS, width: "auto", fontSize: 11, padding: "6px 8px" }}
            value={envId ?? ""} onChange={e => setEnvId(e.target.value ? parseInt(e.target.value) : null)}>
            <option value="">Ohne Umgebung</option>
            {umgebungen.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
          {canEdit && <button style={{ ...btn, padding: "6px 10px", fontSize: 11 }} onClick={() => setDialog("umgebung")}>
            <Layers size={12} style={{ display: "inline", marginRight: 5 }} />Umgebungen
          </button>}
          <button style={{ ...btn, padding: "6px 10px", fontSize: 11 }} onClick={() => { verlaufLaden(); setDialog("verlauf"); }}>
            <History size={12} style={{ display: "inline", marginRight: 5 }} />Verlauf
          </button>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "250px 1fr", gap: 16, alignItems: "start" }}>
        {/* ── Seitenleiste ── */}
        <div style={{ backgroundColor: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 10, padding: 10, position: "sticky", top: 20 }}>
          {canEdit && (
            <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
              <button style={{ ...btn, flex: 1, padding: "5px 8px", fontSize: 11, color: C, borderColor: `${C}44` }}
                onClick={() => { setSammlungEdit(null); setDialog("sammlung"); }}>
                <Plus size={11} style={{ display: "inline", marginRight: 4 }} />Sammlung
              </button>
              <button style={{ ...btn, flex: 1, padding: "5px 8px", fontSize: 11 }} onClick={() => neuerRequest()}>
                <Plus size={11} style={{ display: "inline", marginRight: 4 }} />Request
              </button>
            </div>
          )}
          {canEdit && (
            <button style={{ ...btn, width: "100%", padding: "5px 8px", fontSize: 11, marginBottom: 10,
                             display: "flex", alignItems: "center", justifyContent: "center", gap: 5 }}
              onClick={() => setDialog("openapi")}>
              <FileJson size={11} /> OpenAPI importieren
            </button>
          )}

          {sammlungen.length === 0 && requests.length === 0 && (
            <p style={{ fontSize: 11, color: "#475569", padding: "16px 6px", textAlign: "center", lineHeight: 1.6 }}>
              Noch nichts angelegt. Einfach rechts eine URL eintippen und senden – speichern kannst du später.
            </p>
          )}

          {sammlungen.map(c => {
            const kinder = requests.filter(r => r.collection_id === c.id);
            const auf = offen[c.id] !== false;
            return (
              <div key={c.id} style={{ marginBottom: 4 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 4, padding: "4px 2px" }}>
                  <button onClick={() => setOffen(o => ({ ...o, [c.id]: !auf }))}
                    style={{ display: "flex", alignItems: "center", gap: 5, flex: 1, minWidth: 0, background: "none", border: "none", cursor: "pointer", padding: 0, textAlign: "left" }}>
                    {auf ? <ChevronDown size={12} style={{ color: "#64748b", flexShrink: 0 }} /> : <ChevronRight size={12} style={{ color: "#64748b", flexShrink: 0 }} />}
                    <FolderOpen size={12} style={{ color: C, flexShrink: 0 }} />
                    <span style={{ fontSize: 12, fontWeight: 600, color: "#e2e8f0", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.name}</span>
                  </button>
                  {canEdit && (
                    <>
                      <button title="Request in dieser Sammlung" onClick={() => neuerRequest(c.id)}
                        style={{ color: "#64748b", background: "none", border: "none", cursor: "pointer", padding: 2 }}><Plus size={11} /></button>
                      <button title="Sammlung bearbeiten" onClick={() => { setSammlungEdit(c); setDialog("sammlung"); }}
                        style={{ color: "#64748b", background: "none", border: "none", cursor: "pointer", padding: 2 }}><Pencil size={10} /></button>
                      <button title="Sammlung löschen" onClick={() => sammlungLoeschen(c)}
                        style={{ color: "#64748b", background: "none", border: "none", cursor: "pointer", padding: 2 }}><Trash2 size={10} /></button>
                    </>
                  )}
                </div>
                {auf && (
                  <div style={{ marginLeft: 14, borderLeft: "1px solid rgba(255,255,255,0.06)", paddingLeft: 6 }}>
                    {kinder.length === 0 && <p style={{ fontSize: 10, color: "#475569", padding: "3px 4px", margin: 0 }}>leer</p>}
                    {kinder.map(r => <RequestZeile key={r.id} r={r} aktiv={aktiveId === r.id} onClick={() => requestLaden(r)} onDelete={canEdit ? () => requestLoeschen(r) : null} />)}
                  </div>
                )}
              </div>
            );
          })}

          {ohneSammlung.length > 0 && (
            <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid rgba(255,255,255,0.06)" }}>
              <p style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em", color: "#475569", margin: "0 0 4px 2px" }}>Ohne Sammlung</p>
              {ohneSammlung.map(r => <RequestZeile key={r.id} r={r} aktiv={aktiveId === r.id} onClick={() => requestLaden(r)} onDelete={canEdit ? () => requestLoeschen(r) : null} />)}
            </div>
          )}
        </div>

        {/* ── Arbeitsbereich ── */}
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {/* URL-Leiste */}
          <div style={{ backgroundColor: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 10, padding: 14 }}>
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10 }}>
              <input style={{ ...iS, flex: 1, fontWeight: 600 }} placeholder="Name des Requests (zum Speichern)"
                value={f.name} onChange={e => set("name", e.target.value)} />
              <select style={{ ...iS, width: "auto", fontSize: 11 }} value={f.collection_id ?? ""}
                onChange={e => set("collection_id", e.target.value ? parseInt(e.target.value) : null)}>
                <option value="">Ohne Sammlung</option>
                {sammlungen.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>

            <div style={{ display: "flex", gap: 8 }}>
              <select style={{ ...iS, width: 110, fontWeight: 700, color: METHOD_COLOR[f.method] || "#f1f5f9" }}
                value={f.method} onChange={e => set("method", e.target.value)}>
                {METHODS.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
              <input style={{ ...iS, flex: 1, fontFamily: "monospace" }} placeholder="https://api.example.com/v1/orders  oder  /orders"
                value={f.url} onChange={e => set("url", e.target.value)}
                onKeyDown={e => { if (e.key === "Enter" && f.url && !sende) senden(); }} />
              <button style={{ ...btnPrimary, display: "flex", alignItems: "center", gap: 6, opacity: !f.url || sende ? 0.5 : 1 }}
                disabled={!f.url || sende} onClick={senden}>
                {sende ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />} Senden
              </button>
              {canEdit && (
                <button style={{ ...btn, display: "flex", alignItems: "center", gap: 6, opacity: !f.name || !f.url || speichere ? 0.5 : 1 }}
                  disabled={!f.name || !f.url || speichere} onClick={speichern} title={!f.name ? "Name vergeben, dann speichern" : "Als Connector speichern"}>
                  {speichere ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} {aktiveId ? "Sichern" : "Speichern"}
                </button>
              )}
            </div>

            {/* Verfügbare Variablen */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 10, alignItems: "center" }}>
              {alleVars.map(v => (
                <code key={v} title="In die URL einfügen"
                  onClick={() => set("url", (f.url || "") + v)}
                  style={{ fontSize: 10, backgroundColor: `${C}12`, color: C, padding: "2px 6px", borderRadius: 3, cursor: "pointer", fontFamily: "monospace" }}>{v}</code>
              ))}
              {canEdit && f.url && (
                <button onClick={() => setDialog("variablen")}
                  style={{ ...btn, marginLeft: "auto", padding: "3px 10px", fontSize: 10, display: "flex", alignItems: "center", gap: 5 }}>
                  <KeyRound size={11} /> Variablen vorschlagen
                </button>
              )}
            </div>

            {offenePlatzhalter.length > 0 && (
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginTop: 8, padding: "6px 10px", borderRadius: 6, backgroundColor: "rgba(251,191,36,0.07)", border: "1px solid rgba(251,191,36,0.2)" }}>
                <AlertTriangle size={12} style={{ color: "#fbbf24", flexShrink: 0 }} />
                <span style={{ fontSize: 11, color: "#e2e8f0" }}>
                  Ohne Wert: {offenePlatzhalter.map(n => (
                    <code key={n} style={{ fontFamily: "monospace", color: "#fbbf24", marginRight: 6 }}>{`{{${n}}}`}</code>
                  ))}
                  <span style={{ color: "#64748b" }}>
                    – so geht der Platzhalter wörtlich an die API.
                    {umgebungen.length === 0
                      ? " Dafür braucht es eine Umgebung."
                      : envId === null ? " Oben rechts eine Umgebung wählen." : ""}
                  </span>
                </span>
                {canEdit && (
                  <button onClick={() => setDialog(umgebungen.length === 0 ? "umgebung" : "variablen")}
                    style={{ ...btn, marginLeft: "auto", padding: "3px 10px", fontSize: 10, flexShrink: 0 }}>
                    {umgebungen.length === 0 ? "Umgebung anlegen" : "Werte hinterlegen"}
                  </button>
                )}
              </div>
            )}

            {/* Reiter */}
            <div style={{ display: "flex", gap: 2, marginTop: 14, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
              {REITER.map(t => (
                <button key={t.id} onClick={() => setReiter(t.id)}
                  style={{ padding: "7px 12px", fontSize: 11, fontWeight: 600, cursor: "pointer", background: "none", border: "none",
                    borderBottom: `2px solid ${reiter === t.id ? C : "transparent"}`, color: reiter === t.id ? C : "#64748b" }}>
                  {t.l}
                </button>
              ))}
            </div>

            <div style={{ paddingTop: 14 }}>
              {reiter === "params" && <KvEditor label="Query-Parameter" value={f.query_params} onChange={v => set("query_params", v)} />}
              {reiter === "headers" && <KvEditor label="Headers" value={f.headers} onChange={v => set("headers", v)} />}
              {reiter === "body" && (
                <div>
                  <div style={{ display: "flex", gap: 6, marginBottom: 8, flexWrap: "wrap" }}>
                    {BODY_TYPES.map(b => (
                      <button key={b.v} onClick={() => set("body_type", b.v)}
                        style={{ padding: "4px 10px", borderRadius: 4, fontSize: 11, cursor: "pointer",
                          border: `1px solid ${f.body_type === b.v ? C : "rgba(255,255,255,0.1)"}`,
                          backgroundColor: f.body_type === b.v ? `${C}18` : "transparent",
                          color: f.body_type === b.v ? C : "#64748b" }}>{b.l}</button>
                    ))}
                  </div>
                  {f.body_type !== "none" && (
                    <textarea style={{ ...iS, fontFamily: "monospace", minHeight: 140, resize: "vertical", lineHeight: 1.5 }}
                      placeholder={f.body_type === "json" ? '{\n  "key": "value"\n}'
                        : f.body_type === "xml" ? "<anfrage>\n  <feld>Wert</feld>\n</anfrage>"
                        : ["form", "multipart"].includes(f.body_type) ? "key=value\nkey2=value2"
                        : "Roher Text…"}
                      value={f.body_content || ""} onChange={e => set("body_content", e.target.value)} />
                  )}
                </div>
              )}
              {reiter === "auth" && (
                <div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
                    {[{ v: "inherit", l: "Von Sammlung erben" }, ...REST_AUTH_TYPES].map(a => (
                      <button key={a.v} onClick={() => { set("auth_type", a.v); set("auth_config", {}); }}
                        style={{ padding: "5px 12px", borderRadius: 5, fontSize: 11, cursor: "pointer",
                          border: `1px solid ${f.auth_type === a.v ? C : "rgba(255,255,255,0.1)"}`,
                          backgroundColor: f.auth_type === a.v ? `${C}18` : "transparent",
                          color: f.auth_type === a.v ? C : "#64748b" }}>{a.l}</button>
                    ))}
                  </div>
                  {f.auth_type === "inherit" && (
                    <p style={{ fontSize: 11, color: "#64748b", margin: 0 }}>
                      {f.collection_id
                        ? <>Nutzt die Auth der Sammlung <strong style={{ color: "#94a3b8" }}>{sammlungen.find(c => c.id === f.collection_id)?.name}</strong>.</>
                        : "Ohne Sammlung bedeutet das: keine Authentifizierung."}
                    </p>
                  )}
                  <AuthEditor authType={f.auth_type} authConfig={f.auth_config || {}} onChange={v => set("auth_config", v)} />
                </div>
              )}
              {reiter === "daten" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  <div>
                    <label style={lS}>Datenpfad in der Antwort</label>
                    <input style={{ ...iS, fontFamily: "monospace" }} value={f.data_path || ""} onChange={e => set("data_path", e.target.value)}
                      placeholder='z.B. "data", "results.items"' />
                    <p style={{ fontSize: 10, color: "#475569", marginTop: 4 }}>Wo die Liste in der Antwort steckt. Leer lassen, wenn die Antwort direkt ein Array ist.</p>
                  </div>
                  <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                    <input type="checkbox" checked={!!f.flatten} onChange={e => set("flatten", e.target.checked ? 1 : 0)} />
                    <span style={{ fontSize: 12, color: "#94a3b8" }}>Verschachtelte Objekte flach machen</span>
                  </label>
                  <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                    <input type="checkbox" checked={!!f.store_response} onChange={e => set("store_response", e.target.checked ? 1 : 0)} />
                    <span style={{ fontSize: 12, color: "#94a3b8" }}>Antwortkörper im Verlauf speichern</span>
                  </label>
                  <p style={{ fontSize: 10, color: "#475569", margin: 0 }}>
                    Standardmäßig merkt sich der Verlauf nur Status, Dauer und Größe – Antworten können personenbezogene Daten enthalten.
                  </p>
                  <div style={{ paddingTop: 6, borderTop: "1px solid rgba(255,255,255,0.06)" }}>
                    <label style={lS}>Umgebung für geplante Läufe</label>
                    <select style={iS} value={f.environment_id ?? ""}
                      onChange={e => set("environment_id", e.target.value ? parseInt(e.target.value) : null)}>
                      <option value="">Ohne Umgebung</option>
                      {umgebungen.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
                    </select>
                    <p style={{ fontSize: 10, color: "#475569", marginTop: 4 }}>
                      Die Auswahl oben rechts gilt nur fürs Ausprobieren. Für Scheduler, Pipeline und Import
                      zählt die hier hinterlegte Umgebung.
                    </p>
                  </div>
                  <div style={{ paddingTop: 6, borderTop: "1px solid rgba(255,255,255,0.06)" }}>
                    <label style={{ ...lS, marginBottom: 8 }}>Weitere Seiten holen</label>
                    <PaginationEditor value={f.pagination} onChange={v => set("pagination", v)} />
                  </div>
                </div>
              )}
            </div>

            {fehler && (
              <p style={{ fontSize: 12, color: "#f87171", marginTop: 12, padding: "8px 12px", backgroundColor: "rgba(248,113,113,0.08)", borderRadius: 6 }}>{fehler}</p>
            )}
          </div>

          {/* Antwort */}
          <div style={{ backgroundColor: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 10, overflow: "hidden" }}>
            <AntwortAnsicht
              antwort={antwort}
              kontext={{ url: f.url, method: f.method, headers: f.headers, query_params: f.query_params,
                         body_type: f.body_type, auth_type: f.auth_type, data_path: f.data_path,
                         name: f.name, restSourceId: aktiveId, projectId }}
              aufDatenpfad={(pfad) => { set("data_path", pfad); setReiter("daten"); }}
              aufPaginierung={(cfg) => { set("pagination", cfg); setReiter("daten"); }}
              onUebernehmen={vorschlagUebernehmen}
              aufIntegration={() => setDialog("integration")}
            />
          </div>
        </div>
      </div>

      {/* Dialoge */}
      {dialog === "sammlung" && (
        <SammlungsDialog initial={sammlungEdit} projectId={projectId}
          onSaved={() => { setDialog(null); laden(); }} onClose={() => setDialog(null)} />
      )}
      {dialog === "umgebung" && (
        <UmgebungsDialog umgebungen={umgebungen} projectId={projectId}
          onChanged={laden} onClose={() => setDialog(null)} />
      )}
      {dialog === "openapi" && (
        <OpenApiDialog projectId={projectId}
          onFertig={laden} onClose={() => setDialog(null)} />
      )}
      {dialog === "integration" && antwort && (
        <IntegrationDialog
          antwort={antwort}
          kontext={{ url: f.url, method: f.method, data_path: f.data_path, name: f.name }}
          restSourceId={aktiveId} umgebungen={umgebungen} envId={envId} projectId={projectId}
          onFertig={laden} onClose={() => setDialog(null)} />
      )}
      {dialog === "variablen" && (
        <VariablenDialog
          kontext={{ url: f.url, headers: f.headers, query_params: f.query_params }}
          umgebungen={umgebungen} projectId={projectId}
          onClose={() => setDialog(null)}
          onFertig={(umgebung, ersetzungen) => {
            // Die ausgelagerten Werte im Request durch ihren Platzhalter ersetzen,
            // damit die Anfrage sofort über die Umgebung läuft.
            setF(prev => {
              let url = prev.url || "";
              const headers = { ...prev.headers };
              const params = { ...prev.query_params };
              ersetzungen.forEach(({ ersetzt, key }) => {
                const platzhalter = `{{${key}}}`;
                if (ersetzt && url.includes(ersetzt)) url = url.split(ersetzt).join(platzhalter);
                Object.keys(headers).forEach(k => {
                  if (String(headers[k]) === ersetzt) headers[k] = platzhalter;
                });
                Object.keys(params).forEach(k => {
                  if (String(params[k]) === ersetzt) params[k] = platzhalter;
                });
              });
              return { ...prev, url, headers, query_params: params };
            });
            setEnvId(umgebung.id);
            setDialog(null);
            laden();
          }} />
      )}
      {dialog === "verlauf" && (
        <Dialog titel="Verlauf" onClose={() => setDialog(null)} breit>
          <VerlaufsListe eintraege={verlauf} canEdit={canEdit} onLaden={verlaufEintragLaden}
            onLeeren={async () => {
              if (!window.confirm("Gesamten Verlauf dieses Projekts löschen?")) return;
              await api.delete(`${BASE}/history`, { params: p });
              verlaufLaden();
            }} />
        </Dialog>
      )}
    </div>
  );
}

function RequestZeile({ r, aktiv, onClick, onDelete }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4, borderRadius: 5, backgroundColor: aktiv ? `${C}14` : "transparent" }}>
      <button onClick={onClick}
        style={{ display: "flex", alignItems: "center", gap: 6, flex: 1, minWidth: 0, padding: "4px 6px", background: "none", border: "none", cursor: "pointer", textAlign: "left" }}>
        <span style={{ fontSize: 8, fontWeight: 700, fontFamily: "monospace", flex: "0 0 34px", color: METHOD_COLOR[r.method] || "#94a3b8" }}>{r.method}</span>
        <span style={{ fontSize: 11, color: aktiv ? C : "#94a3b8", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.name}</span>
      </button>
      {onDelete && (
        <button onClick={onDelete} title="Request löschen"
          style={{ color: "#475569", background: "none", border: "none", cursor: "pointer", padding: 2, flexShrink: 0 }}><Trash2 size={10} /></button>
      )}
    </div>
  );
}

export default ApiStudioPanel;
export { ApiStudioPanel };
