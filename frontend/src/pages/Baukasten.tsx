/**
 * Mapping-Baukasten (Schritt 3): Auswertungen aus Lego-Steinen bauen.
 *
 * Die Kette (JSON) ist die einzige Wahrheit; das Backend übersetzt sie in SQL (app/services/baukasten), rechnet
 * Zähler je Stein und eine Vorschau an jeder Stelle und speichert sie als ganz normales Mapping. Formen zeigen
 * die Rolle (Fliese = Start, Winkel = Tabelle, Stein = Schritt, Trichter = Zusammenfassen, Deckel = Ausgabe),
 * Farben das Thema. Ist ein Stein ausgewählt, leuchten links die Steine, die darunter oder hinein passen.
 * Prototyp: doku/entwuerfe/mapping_baukasten_prototyp.html.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, Code2, Loader2, Save, AlertTriangle, X, Sparkles, BookOpen, Undo2, Redo2, HelpCircle } from "lucide-react";
import api, { fehlerText } from "../api/client";
import TabellenSuche from "../components/baukasten/TabellenSuche";
import VorschauDiagramm from "../components/baukasten/VorschauDiagramm";
import Tour, { TOUR_KEY } from "../components/baukasten/Tour";
import { useProject } from "../context/ProjectContext";
import {
  ART, HILFE, OPS, OHNE_WERT, RECHENARTEN, PROFI_FARBE, Stein, Nutzlast, liste, kindKey, blockId, simuliere, alleStellen, platzFuer, gueltig,
} from "../components/baukasten/regeln";

const CSS = `
.bk { --plate: var(--bg-main); display: grid; grid-template-columns: 250px minmax(0,1fr) 400px; gap: 14px; padding: 14px; align-items: start; }
@media (max-width: 1250px) { .bk { grid-template-columns: 230px minmax(0,1fr); } .bk-vorschau { grid-column: 1 / -1; } }
.bk-panel { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; }
.bk-leiste { padding: 12px; display: flex; flex-direction: column; gap: 4px; position: sticky; top: 10px; }
.bk-leiste h3, .bk-vorschau h3 { font-size: 14px; font-weight: 700; margin: 2px 2px 6px; color: var(--text-bright); }
.bk-grp { font-size: 10.5px; text-transform: uppercase; letter-spacing: .09em; color: var(--text-dim); margin: 8px 2px 2px; }
.bk-pal { display: flex; align-items: center; gap: 10px; padding: 7px 8px; border-radius: 9px; cursor: pointer; border: 1px solid transparent;
  background: transparent; color: var(--text-main); text-align: left; width: 100%; transition: opacity .15s, box-shadow .15s, background .15s; }
.bk-pal:hover { background: var(--bg-elevated); }
.bk-pal b { font-size: 13px; font-weight: 600; display: block; }
.bk-pal small { display: block; color: var(--text-dim); font-size: 11.5px; line-height: 1.3; }
.bk-pal.passt { background: color-mix(in srgb, var(--accent) 12%, transparent); border-color: var(--accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent); }
.bk-pal.aus { opacity: .32; }
.bk-pal.platz { border-color: var(--accent); }
.bk-badge { font-size: 10px; font-weight: 700; color: var(--accent); white-space: nowrap; margin-left: auto; }
.bk-mini { flex: none; width: 36px; height: 26px; position: relative; }
.bk-mini .k { position: absolute; left: 0; right: 0; bottom: 0; height: 18px; border-radius: 3px; background: var(--c);
  box-shadow: inset 0 2px 0 rgba(255,255,255,.3), inset 0 -3px 0 rgba(0,0,0,.25); }
.bk-mini .n { position: absolute; top: 3px; width: 8px; height: 5px; border-radius: 2px 2px 0 0; background: var(--c);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.45); }
.bk-platte { background: var(--bg-elevated); border: 1px solid var(--border); border-radius: 12px; padding: 16px 18px 28px; min-height: 560px; min-width: 0;
  background-image: radial-gradient(color-mix(in srgb, var(--text-dim) 22%, transparent) 1.2px, transparent 1.3px); background-size: 20px 20px; }
.bk-info { font-size: 12.5px; color: var(--text-dim); margin: 0 0 6px; }
.bk-stapel { max-width: 720px; }

/* ── Lego-Steine ── */
.bk-stein { --c: #2f6fd6; position: relative; background: var(--c); color: #fff; border-radius: 5px; padding: 10px 12px 12px 14px;
  margin-top: 9px; display: flex; flex-wrap: wrap; align-items: center; gap: 6px 8px; min-height: 46px; cursor: grab;
  box-shadow: inset 0 2px 0 rgba(255,255,255,.28), inset 0 -5px 0 rgba(0,0,0,.24), inset 2px 0 0 rgba(255,255,255,.07), 0 2px 3px rgba(0,0,0,.28); }
.bk-noppen { position: absolute; top: -7px; left: 14px; display: flex; gap: 7px; pointer-events: none; }
.bk-noppen i { display: block; width: 15px; height: 7px; border-radius: 3px 3px 0 0; background: var(--c);
  box-shadow: inset 0 2px 0 rgba(255,255,255,.42), inset -2px 0 0 rgba(0,0,0,.18); }
.bk-stein.fliese { border-radius: 18px 18px 5px 5px; padding-top: 13px; margin-top: 0; }
.bk-stein.deckel { border-radius: 5px 5px 18px 18px; padding-bottom: 15px; }
.bk-stein.sel, .bk-trichter.sel { outline: 3px solid var(--accent); outline-offset: 2px; }
.bk-stein .t { font-weight: 700; white-space: nowrap; text-shadow: 0 1px 0 rgba(0,0,0,.2); }
.bk-stein.drag { opacity: .35; }
.bk-stein.profi { background: repeating-linear-gradient(-45deg, var(--c) 0 10px, color-mix(in srgb, var(--c) 82%, #000) 10px 20px); }
.bk-winkel { position: relative; margin-top: 9px; }
.bk-winkel > .bk-stein { margin-top: 0; border-radius: 5px 5px 5px 0; }
.bk-arm { border-left: 22px solid var(--c); padding: 6px 0 10px 12px; min-height: 34px; position: relative; }
.bk-arm::before { content: ""; position: absolute; left: -22px; top: 0; bottom: 0; width: 22px;
  box-shadow: inset 2px 0 0 rgba(255,255,255,.22), inset -4px 0 0 rgba(0,0,0,.2); pointer-events: none; }
.bk-fuss { background: var(--c); color: #fff; border-radius: 0 5px 5px 5px; padding: 6px 12px 9px 14px; font-size: 12.5px; display: flex;
  align-items: center; gap: 8px; flex-wrap: wrap; min-height: 32px;
  box-shadow: inset 0 -4px 0 rgba(0,0,0,.24), 0 2px 3px rgba(0,0,0,.25); }
.bk-leer { font-size: 12px; color: var(--text-dim); padding: 8px 2px 2px; font-style: italic; }
.bk-trichter-wrap { position: relative; margin-top: 9px; }
.bk-trichter { --c: #d0640f; position: relative; background: var(--c); color: #fff; clip-path: polygon(0 0, 100% 0, 94% 100%, 6% 100%);
  padding: 11px 9% 15px; display: flex; flex-wrap: wrap; align-items: center; gap: 6px 8px; min-height: 68px; cursor: grab;
  box-shadow: inset 0 2px 0 rgba(255,255,255,.28), inset 0 -6px 0 rgba(0,0,0,.24); }

/* Steckplätze: Rechteck = Spalte, Oval = Wert, Sechseck = Bedingung */
.bk-chip, .bk-oval, .bk-op { background: rgba(255,255,255,.94); color: #1b1f1d; border: 0; height: 27px; padding: 0 6px; font-size: 12.5px; cursor: pointer; }
.bk-chip { border-radius: 3px; border-left: 5px solid #1b1f1d55; font-weight: 600; max-width: 220px; }
.bk-chip.breit { max-width: 320px; min-width: 200px; }
.bk-suche { position: relative; display: inline-block; }
.bk-suche input { cursor: text; width: 300px; }
.bk-suche-liste { position: absolute; left: 0; top: 30px; z-index: 50; min-width: 320px; max-width: 460px; max-height: 300px; overflow: auto;
  margin: 0; padding: 4px 0; list-style: none; background: var(--bg-card); color: var(--text-main);
  border: 1px solid var(--border); border-radius: 6px; box-shadow: 0 8px 24px rgba(0,0,0,.22); font-size: 12.5px; font-weight: 500; }
.bk-suche-liste li { display: flex; justify-content: space-between; gap: 12px; padding: 5px 10px; cursor: pointer; white-space: nowrap; }
.bk-suche-liste li span { opacity: .55; font-size: 11px; }
.bk-suche-liste li.aktiv { background: color-mix(in srgb, var(--accent) 18%, transparent); }
.bk-suche-liste li.leer { cursor: default; opacity: .65; font-style: italic; }
.bk-oval { border-radius: 999px; padding: 0 11px; width: 110px; cursor: text; }
.bk-oval.kurz { width: 62px; }
.bk-oval.leer { box-shadow: inset 0 0 0 2px #f0994f; }
.bk-op { border-radius: 4px; font-family: ui-monospace, Consolas, monospace; max-width: 150px; }
.bk-hex { display: inline-flex; align-items: center; gap: 5px; background: rgba(0,0,0,.22); padding: 5px 18px; min-height: 37px;
  clip-path: polygon(13px 0, calc(100% - 13px) 0, 100% 50%, calc(100% - 13px) 100%, 13px 100%, 0 50%); }
.bk-pille { display: inline-flex; align-items: center; gap: 4px; background: rgba(0,0,0,.2); border-radius: 999px; padding: 3px 7px; }
.bk-zahl { margin-left: auto; font-family: ui-monospace, Consolas, monospace; font-size: 12px; background: rgba(255,255,255,.24); color: #fff; border: 0;
  border-radius: 999px; padding: 3px 9px; cursor: pointer; white-space: nowrap; }
.bk-zahl:hover { background: rgba(255,255,255,.4); }
.bk-x { border: 0; background: transparent; color: rgba(255,255,255,.75); cursor: pointer; font-size: 17px; line-height: 1; padding: 2px 4px; }
.bk-x:hover { color: #fff; }
.bk-warn { flex-basis: 100%; font-size: 12px; background: rgba(0,0,0,.28); border-radius: 6px; padding: 5px 8px; display: flex; gap: 6px; align-items: flex-start; }
.bk-tag { font-size: 11px; background: rgba(255,255,255,.22); border-radius: 4px; padding: 2px 6px; }

/* Einfügestellen */
.bk-slot { position: relative; height: 0; }
.bk-slot .hit { position: absolute; left: -6px; right: -6px; top: -4px; height: 26px; z-index: 5; display: none; cursor: pointer; }
.bk-slot.ok .hit { display: block; }
.bk-slot.ok .hit::before { content: "+ hier einsetzen"; position: absolute; inset: 3px 0; display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 700; color: var(--accent); background: color-mix(in srgb, var(--accent) 14%, var(--bg-elevated));
  border: 2px dashed var(--accent); border-radius: 6px; }
.bk-slot.ok.over .hit::before { background: var(--accent); color: var(--accent-fg, #fff); border-style: solid; }
.bk-slot.ok { height: 26px; }

/* Vorschau */
.bk-vorschau { padding: 12px; min-width: 0; position: sticky; top: 10px; }
.bk-hilfe { margin-top: 10px; padding: 9px 10px; border-left: 4px solid var(--c); background: var(--bg-card); border-radius: 6px; font-size: 12.5px; line-height: 1.5; color: var(--text-main); }
.bk-hilfe b { display: block; color: var(--text-bright); margin-bottom: 3px; }
.bk-ansicht { display: inline-flex; border: 1px solid var(--border); border-radius: 7px; overflow: hidden; margin: 0 0 8px; }
.bk-ansicht button { background: none; border: 0; color: var(--text-dim); font-size: 12px; padding: 4px 11px; cursor: pointer; }
.bk-ansicht button + button { border-left: 1px solid var(--border); }
.bk-ansicht button[aria-pressed="true"] { background: color-mix(in srgb, var(--accent) 20%, transparent); color: var(--text-bright); font-weight: 600; }
.bk-tbl { overflow: auto; border: 1px solid var(--border); border-radius: 8px; max-height: 380px; }
.bk-tbl table { border-collapse: collapse; width: 100%; font-size: 12px; font-variant-numeric: tabular-nums; }
.bk-tbl th { position: sticky; top: 0; background: var(--bg-elevated); color: var(--text-dim); font-weight: 600; text-align: left; padding: 6px 8px; white-space: nowrap; }
.bk-tbl td { padding: 5px 8px; border-top: 1px solid var(--border); white-space: nowrap; color: var(--text-main); }
.bk-tbl td.n { text-align: right; }
.bk-fluss { display: flex; flex-direction: column; gap: 2px; margin-top: 10px; font-size: 12px; }
.bk-fluss button { display: flex; justify-content: space-between; gap: 8px; border: 0; background: transparent; color: var(--text-main); padding: 4px 6px;
  border-radius: 6px; cursor: pointer; text-align: left; }
.bk-fluss button:hover, .bk-fluss button[aria-current="true"] { background: var(--bg-elevated); }
.bk-fluss .dot { width: 9px; height: 9px; border-radius: 2px; flex: none; margin-top: 4px; }
.bk-fluss .cnt { font-family: ui-monospace, Consolas, monospace; color: var(--text-dim); }
.bk-kopf { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 14px; padding: 10px 16px; background: var(--bg-card); border-bottom: 1px solid var(--border); }
.bk-kopf input, .bk-kopf select { background: var(--bg-elevated); color: var(--text-bright); border: 1px solid var(--border); border-radius: 7px; padding: 5px 8px; font-size: 13px; }
.bk-meldung { margin: 10px 14px 0; padding: 8px 12px; border-radius: 8px; font-size: 12.5px; display: flex; gap: 8px; align-items: center; }
`;

const nf = new Intl.NumberFormat("de-DE");
const nf2 = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const heute = () => new Date().toISOString().slice(0, 10);
const vorJahr = () => { const d = new Date(); d.setFullYear(d.getFullYear() - 1); d.setDate(d.getDate() + 1); return d.toISOString().slice(0, 10); };

const STARTER: Stein[] = [{ type: "start", trigger: "Wenn das Cockpit öffnet" }, { type: "tabelle", table: "", inner: [] }, { type: "ausgabe", target: "Tabelle im Cockpit" }];

function Noppen({ n = 4 }) { return <span className="bk-noppen">{Array.from({ length: n }, (_, i) => <i key={i} />)}</span>; }

function Mini({ typ }) {
  const a = ART[typ];
  const form = a.form;
  return (
    <span className="bk-mini" style={{ "--c": a.farbe } as any}>
      {form !== "hut" && [2, 13, 24].map((x) => <i key={x} className="n" style={{ left: x }} />)}
      <i className="k" style={{
        borderRadius: form === "hut" ? "10px 10px 3px 3px" : form === "deckel" ? "3px 3px 10px 10px" : 3,
        clipPath: form === "trichter" ? "polygon(0 0,100% 0,80% 100%,20% 100%)" : undefined,
        height: form === "winkel" ? 7 : 18, top: form === "winkel" ? 8 : undefined,
      }} />
      {form === "winkel" && <><i className="k" style={{ left: 0, width: 8, height: 11, bottom: 6 }} /><i className="k" style={{ height: 6, right: 6 }} /></>}
    </span>
  );
}

export default function Baukasten() {
  const { id } = useParams();
  const [such] = useSearchParams();
  const navigate = useNavigate();
  const { activeProject } = useProject() as any;
  const [mappingId, setMappingId] = useState<number | null>(id ? Number(id) : null);
  const [projectId, setProjectId] = useState<number | null>(such.get("project_id") ? Number(such.get("project_id")) : activeProject?.id ?? null);
  const [name, setName] = useState("");
  const [verbindungen, setVerbindungen] = useState<any[]>([]);
  const [connectionId, setConnectionId] = useState<number | null>(null);
  const [kette, setKette] = useState<Stein[]>(STARTER);
  const [tabellen, setTabellen] = useState<any[] | null>(null);
  const [erg, setErg] = useState<any>(null);
  const [rechnet, setRechnet] = useState(false);
  const [fehler, setFehler] = useState("");
  const [meldung, setMeldung] = useState("");
  const [auswahl, setAuswahl] = useState<{ key: string; i: number } | null>(null);
  const [tragen, setTragen] = useState<Nutzlast | null>(null);
  const [platzieren, setPlatzieren] = useState<string | null>(null);
  const [zeige, setZeige] = useState<string | null>(null);
  const [von, setVon] = useState(vorJahr());
  const [bis, setBis] = useState(heute());
  const [profiGeaendert, setProfiGeaendert] = useState(false);
  const [profiVerwerfen, setProfiVerwerfen] = useState(false);
  const [speichert, setSpeichert] = useState(false);
  const [rezepte, setRezepte] = useState<any[]>([]);
  const [ansicht, setAnsicht] = useState<"tabelle" | "balken" | "linie" | null>(null);
  const [cockpits, setCockpits] = useState<{ id: number; name: string; reiter: { id: string; label: string }[] }[]>([]);
  const [imCockpit, setImCockpit] = useState<{ form_id: number; name: string; reiter: string | null } | null>(null);
  const [kiText, setKiText] = useState("");
  const [kiLaeuft, setKiLaeuft] = useState(false);
  const [kiHinweis, setKiHinweis] = useState("");
  // Verlauf für Rückgängig/Wiederholen: jede Änderung der Kette; Tipp-Folgen (< 0,7 s) zählen als ein Schritt
  const verlauf = useRef<{ zurueck: Stein[][]; vor: Stein[][]; letzt: Stein[] | null; zeit: number; still: boolean }>(
    { zurueck: [], vor: [], letzt: null, zeit: 0, still: true });
  const [, setVerlaufStand] = useState(0);
  const [tour, setTour] = useState(() => { try { return !localStorage.getItem(TOUR_KEY); } catch { return false; } });
  const rechenNr = useRef(0);

  // Laden: vorhandenes Baukasten-Mapping oder neu
  useEffect(() => {
    if (!id) return;
    api.get(`/api/baukasten/mapping/${id}`).then(({ data }) => {
      setName(data.name || ""); setProjectId(data.project_id ?? null);
      if (data.baukasten) { verlauf.current = { zurueck: [], vor: [], letzt: null, zeit: 0, still: true }; setKette(data.kette || STARTER); setConnectionId(data.connection_id); setProfiGeaendert(!!data.profi_geaendert); }
      else setFehler("Dieses Mapping wurde nicht im Baukasten gebaut – es lässt sich nur in der Profi-Ansicht bearbeiten.");
    }).catch((e) => setFehler(fehlerText(e)));
  }, [id]);
  useEffect(() => {
    api.get("/api/connections/", { params: projectId ? { project_id: projectId } : {} }).then(({ data }) => {
      const l = (data || []).filter((c) => ["mssql", "mysql", "postgresql"].includes(c.db_type));
      setVerbindungen(l);
      setConnectionId((akt) => akt ?? (l.find((c) => c.is_mandant_default) || l[0])?.id ?? null);
    }).catch(() => {});
  }, [projectId]);
  useEffect(() => {
    if (!connectionId) return;
    setTabellen(null);
    api.get("/api/baukasten/tabellen", { params: { connection_id: connectionId } })
      .then(({ data }) => setTabellen(data.tabellen || [])).catch((e) => { setTabellen([]); setFehler(fehlerText(e)); });
  }, [connectionId]);
  useEffect(() => {
    const h = verlauf.current;
    if (h.still || h.letzt === null) { h.still = false; h.letzt = kette; return; }
    if (h.letzt !== kette) {
      const jetzt = Date.now();
      if (jetzt - h.zeit > 700 || !h.zurueck.length) { h.zurueck.push(h.letzt); if (h.zurueck.length > 100) h.zurueck.shift(); }
      h.zeit = jetzt; h.vor = []; h.letzt = kette; setVerlaufStand((x) => x + 1);
    }
  }, [kette]);
  const rueckgaengig = () => {
    const h = verlauf.current; const alt = h.zurueck.pop(); if (!alt) return;
    h.vor.push(kette); h.still = true; h.zeit = 0; h.letzt = alt; setKette(alt); setAuswahl(null); setKiHinweis(""); setVerlaufStand((x) => x + 1);
  };
  const wiederholen = () => {
    const h = verlauf.current; const neu = h.vor.pop(); if (!neu) return;
    h.zurueck.push(kette); h.still = true; h.zeit = 0; h.letzt = neu; setKette(neu); setAuswahl(null); setVerlaufStand((x) => x + 1);
  };
  // Strg+Z / Strg+Y (in Eingabefeldern bleibt das normale Rückgängig des Feldes)
  useEffect(() => {
    const taste = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      const ziel = e.target as HTMLElement;
      if (ziel?.closest?.("input, textarea, [contenteditable=true]")) return;
      const k = e.key.toLowerCase();
      if (k === "z" && !e.shiftKey) { e.preventDefault(); rueckgaengig(); }
      else if (k === "y" || (k === "z" && e.shiftKey)) { e.preventDefault(); wiederholen(); }
    };
    window.addEventListener("keydown", taste);
    return () => window.removeEventListener("keydown", taste);
  });
  // Beim Ziehen am Fensterrand mitscrollen
  useEffect(() => {
    if (!tragen) return;
    const rand = (e: DragEvent) => {
      if (e.clientY < 70) window.scrollBy(0, -18);
      else if (e.clientY > window.innerHeight - 70) window.scrollBy(0, 18);
    };
    document.addEventListener("dragover", rand);
    return () => document.removeEventListener("dragover", rand);
  }, [tragen]);
  const cockpitsLaden = () => {
    if (!projectId) return;
    api.get("/api/baukasten/cockpits", { params: { project_id: projectId } }).then(({ data }) => setCockpits(data || [])).catch(() => setCockpits([]));
  };
  useEffect(cockpitsLaden, [projectId]);
  useEffect(() => {
    if (!connectionId) return;
    api.get("/api/baukasten/rezepte", { params: { connection_id: connectionId } })
      .then(({ data }) => setRezepte(data.rezepte || [])).catch(() => setRezepte([]));
  }, [connectionId]);
  const ersetzen = (neu: Stein[], hinweis = "") => {
    setKette(neu); setAuswahl(null); setZeige(null); setKiHinweis(hinweis);
  };
  const kiBauen = async () => {
    if (!kiText.trim() || !connectionId) return;
    setKiLaeuft(true); setFehler(""); setKiHinweis("");
    try {
      const { data } = await api.post("/api/baukasten/ki", { connection_id: connectionId, text: kiText.trim() }, { timeout: 180000 });
      ersetzen(data.kette, data.hinweis || "Die KI hat die Steine gelegt – prüfe sie Stein für Stein.");
      if (!name.trim()) setName(kiText.trim().slice(0, 60));
    } catch (e) { setFehler(fehlerText(e, "Die KI konnte keine Steinkette bauen")); }
    finally { setKiLaeuft(false); }
  };
  const tabSpalten = useMemo(() => Object.fromEntries((tabellen || []).map((t) => [t.name, t.spalten.map((s) => s.name)])), [tabellen]);

  // Rechnen (Zähler + Vorschau), verzögert nach jeder Änderung
  const bereit = !!connectionId && kette.some((b) => b.type === "tabelle" && b.table);
  useEffect(() => {
    if (!bereit) { setErg(null); return; }
    const nr = ++rechenNr.current;
    const t = setTimeout(() => {
      setRechnet(true);
      api.post("/api/baukasten/rechnen", { connection_id: connectionId, kette, zeige, von, bis }, { timeout: 120000 })
        .then(({ data }) => { if (nr === rechenNr.current) { setErg(data); setFehler(""); } })
        .catch((e) => { if (nr === rechenNr.current) setFehler(fehlerText(e)); })
        .finally(() => { if (nr === rechenNr.current) setRechnet(false); });
    }, 650);
    return () => clearTimeout(t);
  }, [JSON.stringify(kette), connectionId, zeige, von, bis, bereit]); // eslint-disable-line react-hooks/exhaustive-deps

  const aendern = (key: string, i: number, patch: Record<string, any>) => setKette((k) => {
    const c = structuredClone(k); Object.assign(liste(c, key)[i], patch); return c;
  });
  const setzen = (n: Nutzlast, key: string, i: number) => {
    const c = simuliere(kette, n, key, i);
    if (!c) return;
    setKette(c); setTragen(null); setPlatzieren(null); setMeldung("");
    if (n.kind === "new") setAuswahl({ key, i });
  };
  const entfernen = (key: string, i: number) => {
    const c = structuredClone(kette); liste(c, key).splice(i, 1);
    if (!gueltig(c)) { setMeldung("Dieser Stein trägt andere – erst die Steine darunter entfernen."); return; }
    setKette(c); setAuswahl(null); setMeldung("");
  };

  // Palette: was passt zur Auswahl?
  const palette = useMemo(() => Object.keys(ART).map((typ) => {
    const p = platzFuer(kette, typ, auswahl);
    return { typ, p };
  }), [kette, auswahl]);

  const stellenOk = useMemo(() => {
    const n: Nutzlast | null = tragen || (platzieren ? { kind: "new", type: platzieren } : null);
    if (!n) return new Set<string>();
    return new Set(alleStellen(kette).filter(([k, i]) => simuliere(kette, n, k, i)).map(([k, i]) => `${k}|${i}`));
  }, [tragen, platzieren, kette]);

  const speichern = async () => {
    if (!name.trim()) { setMeldung("Bitte oben einen Namen vergeben."); return; }
    if (profiGeaendert && !profiVerwerfen) { setMeldung("Das Mapping wurde in der Profi-Ansicht geändert. Zum Überschreiben oben „Profi-Änderungen verwerfen“ anhaken."); return; }
    setSpeichert(true); setMeldung("");
    try {
      const { data } = await api.post("/api/baukasten/speichern", { project_id: projectId, connection_id: connectionId, name: name.trim(), kette, mapping_id: mappingId });
      setMappingId(data.mapping_id); setProfiGeaendert(false); setProfiVerwerfen(false);
      setImCockpit(data.cockpit || null);
      if (data.cockpit) {
        cockpitsLaden();
        // „Neues Cockpit“ ist jetzt angelegt: der Stein zeigt ab sofort auf genau dieses
        setKette((k) => k.map((b) => b.type === "ausgabe" && b.cockpit === "neu" ? { ...b, cockpit: data.cockpit.form_id } : b));
        setMeldung(`Gespeichert und ins Cockpit „${data.cockpit.name}“ gestellt${data.cockpit.reiter ? ` (Reiter „${data.cockpit.reiter}“)` : ""}.`);
      } else setMeldung("Gespeichert – das Mapping steht jetzt wie jedes andere im Projekt bereit.");
      if (!id) navigate(`/baukasten/${data.mapping_id}`, { replace: true });
    } catch (e) { setMeldung(fehlerText(e, "Speichern fehlgeschlagen")); }
    finally { setSpeichert(false); }
  };

  // ── Darstellung eines Steins ──
  const z = erg?.zaehler || {}, warn = erg?.warnungen || {}, sjb = erg?.spalten_je_block || {};
  const zahl = (bid: string, mitRein = true, vorher?: number) => z[bid] == null ? null : (
    <button className="bk-zahl" title="Zeilen an dieser Stelle in der Vorschau zeigen" onClick={(e) => { e.stopPropagation(); setZeige(bid); }}>
      {mitRein && vorher != null && vorher !== z[bid] ? `${nf.format(vorher)} → ` : ""}{nf.format(z[bid])} ▸
    </button>);
  const sel = (feld: string, werte: string[], akt: string, onChange: (v: string) => void, leer = "Spalte wählen …", cls = "bk-chip") => (
    <select className={cls} value={akt || ""} aria-label={feld} onChange={(e) => onChange(e.target.value)} onClick={(e) => e.stopPropagation()}>
      {leer !== null && <option value="">{leer}</option>}
      {!werte.includes(akt) && akt ? <option value={akt}>{akt} (fehlt)</option> : null}
      {werte.map((w) => <option key={w} value={w}>{w}</option>)}
    </select>);
  const tabWahl = (akt: string, onChange: (v: string) => void, _listeId?: string) => (
    <TabellenSuche tabellen={tabellen} wert={akt} onWahl={onChange} />);
  const weg = (key: string, i: number) => <button className="bk-x" title="Stein entfernen" aria-label="Stein entfernen" onClick={(e) => { e.stopPropagation(); entfernen(key, i); }}>×</button>;
  const warnung = (bid: string) => warn[bid] ? <div className="bk-warn"><AlertTriangle size={13} style={{ flex: "none", marginTop: 1 }} />{warn[bid]}</div> : null;

  const vorherZahl = (key: string, i: number): number | undefined => {
    if (key === "") { for (let j = i - 1; j >= 0; j--) if (z[`:${j}`] != null) return z[`:${j}`]; return undefined; }
    if (!key.includes(".")) return i === 0 ? z[`:${key}:kopf`] : z[`${key}:${i - 1}`];
    return i === 0 ? z[`${key.split(".")[0]}:${key.split(".")[1]}:fremd`] : z[`${key}:${i - 1}`];
  };

  function steinHTML(b: Stein, key: string, i: number) {
    const bid = blockId(key, i);
    const istSel = auswahl?.key === key && auswahl?.i === i;
    const ziehbar = {
      draggable: true,
      onDragStart: (e) => { if ((e.target as HTMLElement).closest("select,input")) { e.preventDefault(); return; } e.stopPropagation(); setTragen({ kind: "move", key, index: i }); e.dataTransfer.effectAllowed = "move"; },
      onDragEnd: () => setTragen(null),
      onClick: (e) => { e.stopPropagation(); setAuswahl(istSel ? null : { key, i }); setPlatzieren(null); },
    };
    const farbe = b.type === "profi" ? PROFI_FARBE : ART[b.type]?.farbe;
    const cols: string[] = sjb[bid] || [];
    const ziehtGerade = tragen?.kind === "move" && tragen.key === key && tragen.index === i;
    const cls = (x = "") => `bk-stein ${x}${istSel ? " sel" : ""}${ziehtGerade ? " drag" : ""}`;
    switch (b.type) {
      case "start": return (
        <div className={cls("fliese")} style={{ "--c": farbe } as any} {...ziehbar}>
          <span>▶</span>{sel("trigger", ["Wenn das Cockpit öffnet", "Jeden Montag um 6 Uhr", "Wenn eine Datei ankommt"], b.trigger, (v) => aendern(key, i, { trigger: v }), null)}{weg(key, i)}
        </div>);
      case "filter": {
        const oben = key === "";
        const spalten = cols.length ? cols : key.includes(".") ? (tabSpalten[liste(kette, key.split(".")[0])[Number(key.split(".")[1])]?.table] || [])
          : !oben ? (tabSpalten[kette[Number(key)]?.table] || []) : [];
        return (
          <div className={cls()} style={{ "--c": farbe } as any} {...ziehbar}><Noppen />
            <span className="t">{oben ? "Nur Gruppen mit" : "Nur wenn"}</span>
            <span className="bk-hex">{sel("Spalte", spalten, b.col, (v) => aendern(key, i, { col: v }))}
              {sel("Vergleich", OPS, b.op, (v) => aendern(key, i, { op: v }), null, "bk-op")}
              {!OHNE_WERT.has(b.op) && <input className={`bk-oval${String(b.val ?? "").trim() === "" ? " leer" : ""}`} value={b.val ?? ""} placeholder={b.op === "ist einer von" ? "Wert 1, Wert 2 …" : "Wert"}
                aria-label="Wert" onClick={(e) => e.stopPropagation()} onChange={(e) => aendern(key, i, { val: e.target.value })} />}
              {b.op === "im Zeitraum" && <span className="bk-tag">Zeitraum des Cockpits</span>}
              {b.op === "im Zeitraum + Vorjahr" && <span className="bk-tag" title="„Zusammenfassen“ zeigt danach je Kennzahl den Zeitraum und dieselbe Spanne ein Jahr davor">Zeitraum + Vorjahr → Vergleichsspalten</span>}
            </span>
            {zahl(bid, true, vorherZahl(key, i))}{weg(key, i)}{warnung(bid)}
          </div>);
      }
      case "rechnen": {
        const datum = b.op === "Tage bis heute" || b.op === "Tage zwischen";
        return (
        <div className={cls()} style={{ "--c": farbe } as any} {...ziehbar}><Noppen />
          <span className="t">Rechnen</span>
          <input className="bk-oval" value={b.name} aria-label="Name der neuen Spalte" onClick={(e) => e.stopPropagation()} onChange={(e) => aendern(key, i, { name: e.target.value })} /> =
          {datum && b.op === "Tage bis heute" ? <span>Tage von</span> : null}
          {sel("a", cols, b.a, (v) => aendern(key, i, { a: v }))}{sel("Rechenart", RECHENARTEN, b.op, (v) => aendern(key, i, { op: v }), null, "bk-op")}
          {b.op === "Tage zwischen" ? <>{sel("bis Datum", cols, b.b, (v) => aendern(key, i, { b: v }))}</>
            : b.op === "Tage bis heute" ? <span>bis heute</span>
            : <><input className="bk-oval kurz" list={`bk-cols-${bid}`} value={b.b} placeholder="Spalte/Zahl" aria-label="zweiter Wert" onClick={(e) => e.stopPropagation()} onChange={(e) => aendern(key, i, { b: e.target.value })} />
              <datalist id={`bk-cols-${bid}`}>{cols.map((c) => <option key={c} value={c} />)}</datalist></>}
          {zahl(bid, false)}{weg(key, i)}
        </div>);
      }
      case "einteilen": {
        const regeln: any[] = b.regeln || [];
        const setzeRegel = (k: number, teil: any) => aendern(key, i, { regeln: regeln.map((r, n) => n === k ? { ...r, ...teil } : r) });
        return (
        <div className={cls()} style={{ "--c": farbe } as any} {...ziehbar}><Noppen />
          <span className="t">Einteilen</span>
          <input className="bk-oval" value={b.name} aria-label="Name der neuen Spalte" onClick={(e) => e.stopPropagation()} onChange={(e) => aendern(key, i, { name: e.target.value })} />
          <span>nach</span>{sel("Spalte", cols, b.col, (v) => aendern(key, i, { col: v }))}
          {zahl(bid, false)}{weg(key, i)}
          {regeln.map((r, k) => (
            <span key={k} className="bk-hex" style={{ flexBasis: "100%" }}>
              <span>{k === 0 ? "wenn" : "sonst wenn"}</span>
              {sel("Vergleich", OPS.filter((o) => !["im Zeitraum", "im Zeitraum + Vorjahr"].includes(o)), r.op, (v) => setzeRegel(k, { op: v }), null, "bk-op")}
              {!OHNE_WERT.has(r.op) && <input className="bk-oval kurz" value={r.val ?? ""} placeholder="Wert" aria-label="Wert" onClick={(e) => e.stopPropagation()} onChange={(e) => setzeRegel(k, { val: e.target.value })} />}
              <span>→</span>
              <input className="bk-oval" value={r.wert ?? ""} placeholder="z. B. groß" aria-label="Gruppe" onClick={(e) => e.stopPropagation()} onChange={(e) => setzeRegel(k, { wert: e.target.value })} />
              {regeln.length > 1 && <button className="bk-x" title="Regel entfernen" aria-label="Regel entfernen" onClick={(e) => { e.stopPropagation(); aendern(key, i, { regeln: regeln.filter((_, n) => n !== k) }); }}>×</button>}
            </span>))}
          <span className="bk-hex" style={{ flexBasis: "100%" }}>
            <button className="bk-tag" style={{ cursor: "pointer" }} onClick={(e) => { e.stopPropagation(); aendern(key, i, { regeln: [...regeln, { op: regeln[regeln.length - 1]?.op || "=", val: "", wert: "" }] }); }}>＋ Regel</button>
            <span>sonst →</span>
            <input className="bk-oval" value={b.sonst ?? ""} placeholder="z. B. klein (leer = nichts)" aria-label="sonst" onClick={(e) => e.stopPropagation()} onChange={(e) => aendern(key, i, { sonst: e.target.value })} />
          </span>
        </div>);
      }
      case "sortieren": return (
        <div className={cls()} style={{ "--c": farbe } as any} {...ziehbar}><Noppen />
          <span className="t">Sortieren nach</span>{sel("Spalte", cols, b.col, (v) => aendern(key, i, { col: v }))}
          {sel("Richtung", ["absteigend", "aufsteigend"], b.dir, (v) => aendern(key, i, { dir: v }), null, "bk-op")}{zahl(bid, false)}{weg(key, i)}
        </div>);
      case "begrenzen": return (
        <div className={cls()} style={{ "--c": farbe } as any} {...ziehbar}><Noppen />
          <span className="t">Nur die ersten</span>
          <input className="bk-oval kurz" value={b.n} inputMode="numeric" aria-label="Anzahl" onClick={(e) => e.stopPropagation()} onChange={(e) => aendern(key, i, { n: Number(e.target.value) || 0 })} />
          <span>Zeilen</span>{zahl(bid, false)}{weg(key, i)}
        </div>);
      case "ausgabe": {
        const ziele = ["Tabelle im Cockpit", "Balken im Cockpit", "Linie im Cockpit", "Kachel im Cockpit", "Nur als Auswertung speichern"];
        const imC = b.target !== "Nur als Auswertung speichern";
        const sp: { name: string; typ: string }[] = erg?.spalten || [];
        const zahlen = sp.filter((x) => x.typ === "zahl").map((x) => x.name);
        const akt = cockpits.find((c) => String(c.id) === String(b.cockpit));
        const diagramm = b.target === "Balken im Cockpit" || b.target === "Linie im Cockpit";
        const ys: string[] = b.y || [];
        return (
          <div className={cls("deckel")} style={{ "--c": farbe } as any} {...ziehbar}><Noppen />
            <span>▣</span><span className="t">Ergebnis</span>
            {sel("Ziel", ziele, b.target, (v) => aendern(key, i, { target: v }), null, "bk-chip breit")}
            {imC && <>
              <span>in</span>
              <select className="bk-chip breit" aria-label="Cockpit" value={b.cockpit ?? ""} onClick={(e) => e.stopPropagation()}
                onChange={(e) => aendern(key, i, { cockpit: e.target.value === "neu" ? "neu" : e.target.value ? Number(e.target.value) : null, reiter: null })}>
                <option value="">Cockpit wählen …</option>
                {cockpits.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                <option value="neu">＋ Neues Cockpit …</option>
              </select>
              {b.cockpit === "neu" && <input className="bk-oval" value={b.cockpit_name ?? ""} placeholder={name || "Name des Cockpits"} aria-label="Name des neuen Cockpits"
                onClick={(e) => e.stopPropagation()} onChange={(e) => aendern(key, i, { cockpit_name: e.target.value })} />}
              {akt && akt.reiter.length > 0 && (
                <select className="bk-chip" aria-label="Reiter" value={b.reiter ?? ""} onClick={(e) => e.stopPropagation()} onChange={(e) => aendern(key, i, { reiter: e.target.value || null })}>
                  <option value="">Reiter „Eigene Auswertungen“</option>
                  {akt.reiter.filter((r) => r.label !== "Eigene Auswertungen").map((r) => <option key={r.id} value={r.id}>Reiter „{r.label}“</option>)}
                </select>)}
            </>}
            {zahl(bid, false)}{weg(key, i)}
            {imC && !b.cockpit && <span className="bk-tag" style={{ flexBasis: "100%" }}>Ohne Cockpit wird nur die Auswertung gespeichert.</span>}
            {imC && diagramm && sp.length > 0 && (
              <span className="bk-hex" style={{ flexBasis: "100%", flexWrap: "wrap" }}>
                <span>Achse</span>{sel("Achse", sp.map((x) => x.name), b.x || "", (v) => aendern(key, i, { x: v }), "automatisch")}
                <span>Werte</span>
                {zahlen.filter((c) => c !== b.x).map((c) => (
                  <label key={c} className="bk-tag" style={{ cursor: "pointer" }} onClick={(e) => e.stopPropagation()}>
                    <input type="checkbox" checked={ys.length ? ys.includes(c) : zahlen.filter((x) => x !== b.x).indexOf(c) < 4}
                      onChange={(e) => { const basis = ys.length ? ys : zahlen.filter((x) => x !== b.x).slice(0, 4);
                        aendern(key, i, { y: e.target.checked ? [...basis, c] : basis.filter((x) => x !== c) }); }} /> {c}
                  </label>))}
              </span>)}
            {imC && b.target === "Kachel im Cockpit" && zahlen.length > 0 && (
              <span className="bk-hex" style={{ flexBasis: "100%" }}><span>Kennzahl</span>
                {sel("Kennzahl", zahlen, b.wert || "", (v) => aendern(key, i, { wert: v }), "automatisch")}<span>(Summe aller Zeilen)</span></span>)}
          </div>);
      }
      case "profi": return (
        <div className={cls("profi")} style={{ "--c": farbe } as any} {...ziehbar}><Noppen />
          <span>🔒</span><span className="t">Profi-Stein</span><span style={{ fontSize: 12.5 }}>{b.label || "nur in der Profi-Ansicht bearbeitbar"}</span>{weg(key, i)}
        </div>);
      case "verdichten": return (
        <div className="bk-trichter-wrap" style={{ "--c": farbe } as any} {...ziehbar}><Noppen n={5} />
          <div className={`bk-trichter${istSel ? " sel" : ""}`} style={{ "--c": farbe } as any}>
            <span>⧩</span><span className="t">Je</span>
            {[0, 1].map((k) => {
              const x = b.by[k]; const col = typeof x === "object" && x ? x.col : x || ""; const teil = typeof x === "object" && x ? x.teil || "" : "";
              const setze = (c: string, t: string) => { const by = [...b.by]; by[k] = c ? (t ? { col: c, teil: t } : c) : ""; aendern(key, i, { by }); };
              return (
                <span key={k} className="bk-pille">
                  {sel("je", cols, col, (v) => setze(v, teil), k === 0 ? "Spalte wählen …" : "— (keine)")}
                  {col && (
                    <select className="bk-op" value={teil} aria-label="Datum zusammenfassen" onClick={(e) => e.stopPropagation()} onChange={(e) => setze(col, e.target.value)}>
                      <option value="">wie es ist</option><option value="monat">je Monat</option><option value="jahr">je Jahr</option>
                    </select>)}
                </span>);
            })}
            <span className="t">zusammenfassen:</span>
            {b.aggs.map((a, k) => (
              <span key={k} className="bk-pille">
                {sel("Kennzahl", ["Summe", "Anzahl", "Durchschnitt", "Höchstwert", "Tiefstwert"], a.fn, (v) => { const aggs = structuredClone(b.aggs); aggs[k].fn = v; aendern(key, i, { aggs }); }, null, "bk-op")}
                {a.fn !== "Anzahl" && sel("von", cols, a.col, (v) => { const aggs = structuredClone(b.aggs); aggs[k].col = v; aendern(key, i, { aggs }); })}
              </span>))}
            {zahl(bid, true, vorherZahl(key, i))}{weg(key, i)}
          </div>
        </div>);
      case "tabelle": case "join": {
        const ck = kindKey(key, i);
        const kopfId = b.type === "tabelle" ? `:${i}:kopf` : bid;
        const vorher = b.type === "join" ? vorherZahl(key, i) : undefined;
        const fremd = z[`${bid}:fremd`];
        return (
          <div className="bk-winkel" style={{ "--c": farbe } as any}>
            <div className={cls()} style={{ "--c": farbe } as any} {...ziehbar}><Noppen />
              <span>▤</span><span className="t">{b.type === "tabelle" ? "Aus Tabelle" : "Dazuholen"}</span>
              {tabWahl(b.table, (v) => {
                if (b.type === "tabelle") { aendern(key, i, { table: v, inner: [] }); return; }
                aendern(key, i, { table: v, links: "", rechts: "" });
                // Vorschlag gegen alle schon vorhandenen Tabellen (Haupttabelle, dann die bereits dazugeholten)
                const vorhandene = [kette[Number(key)]?.table, ...(kette[Number(key)]?.inner || []).slice(0, i).filter((x) => x.type === "join" && x.table).map((x) => x.table)].filter(Boolean);
                if (vorhandene.length) api.get("/api/baukasten/verknuepfung", { params: { connection_id: connectionId, von: vorhandene.join(","), zu: v } })
                  .then(({ data }) => {
                    const vs = data.vorschlag; if (!vs) return;
                    // Spalte einer dazugeholten Tabelle kann umbenannt sein („cName (tkunde)“)
                    const kurz = String(vs.von).split(".").pop();
                    const links = cols.includes(vs.links) && vs.von === vorhandene[0] ? vs.links : cols.includes(`${vs.links} (${kurz})`) ? `${vs.links} (${kurz})` : vs.links;
                    aendern(key, i, { links, rechts: vs.rechts, vorgeschlagen: true });
                  }).catch(() => {});
              }, `bk-tab-${bid}`)}
              {b.type === "join" && <>
                <span>über</span>{sel("links", cols, b.links, (v) => aendern(key, i, { links: v, vorgeschlagen: false }))}
                <span>=</span>{sel("rechts", tabSpalten[b.table] || [], b.rechts, (v) => aendern(key, i, { rechts: v, vorgeschlagen: false }))}
                {b.vorgeschlagen && <span className="bk-tag" title="Aus den Schlüsseln der Tabellen erkannt">✓ vorgeschlagen</span>}
                <select className="bk-chip" aria-label="Welche Zeilen bleiben" value={b.ohne ? "ohne" : b.alle ? "alle" : "mit"} onClick={(e) => e.stopPropagation()}
                  title="nur mit Treffer: INNER JOIN · auch ohne Treffer: LEFT JOIN, fehlende Werte bleiben leer · nur OHNE Treffer: z. B. Kunden ohne Rechnung"
                  onChange={(e) => aendern(key, i, { alle: e.target.value === "alle", ohne: e.target.value === "ohne" })}>
                  <option value="mit">nur Zeilen mit Treffer</option>
                  <option value="alle">auch ohne Treffer behalten</option>
                  <option value="ohne">nur Zeilen OHNE Treffer</option>
                </select>
              </>}
              {b.type === "tabelle" ? zahl(kopfId, false) : zahl(bid, true, vorher)}{weg(key, i)}{warnung(bid)}
            </div>
            <div className="bk-arm">
              {stapel(b.inner || [], ck, true)}
              {!(b.inner || []).length && <div className="bk-leer">{b.type === "tabelle" ? "„Nur wenn“ oder „Dazuholen“ hier hinein" : "„Nur wenn“ hier hinein – z. B. nur Rechnungsadressen"}</div>}
            </div>
            <div className="bk-fuss">
              {b.type === "tabelle"
                ? <>ergibt <b>{z[bid] != null ? nf.format(z[bid]) : "…"}</b> Zeilen {z[bid] != null && <button className="bk-zahl" onClick={(e) => { e.stopPropagation(); setZeige(bid); }}>ansehen ▸</button>}</>
                : <>{fremd != null ? `${nf.format(fremd)} Einträge aus ${b.table.split(".").pop()} passen` : "…"}{fremd != null && <button className="bk-zahl" onClick={(e) => { e.stopPropagation(); setZeige(`${bid}:fremd`); }}>ansehen ▸</button>}</>}
            </div>
          </div>);
      }
    }
    return null;
  }

  function stapel(l: Stein[], key: string, innen = false) {
    const out: any[] = [];
    for (let i = 0; i <= l.length; i++) {
      const k = `${key}|${i}`;
      const ok = stellenOk.has(k);
      out.push(
        <div key={`s${k}`} className={`bk-slot${ok ? " ok" : ""}`}
          onDragOver={(e) => { if (ok) { e.preventDefault(); e.currentTarget.classList.add("over"); } }}
          onDragLeave={(e) => e.currentTarget.classList.remove("over")}
          onDrop={(e) => { e.preventDefault(); e.currentTarget.classList.remove("over"); if (tragen) setzen(tragen, key, i); }}
          onClick={(e) => { e.stopPropagation(); if (ok && platzieren) setzen({ kind: "new", type: platzieren }, key, i); }}>
          <div className="hit" />
        </div>);
      if (i < l.length) out.push(<div key={`b${key}:${i}`}>{steinHTML(l[i], key, i)}</div>);
    }
    return out;
  }

  // Datenfluss für die Vorschau
  const fluss = useMemo(() => {
    const aus: [string, string, string][] = [];
    kette.forEach((b, i) => {
      if (b.type === "tabelle") {
        aus.push([`:${i}:kopf`, `Tabelle ${b.table || "…"}`, ART.tabelle.farbe]);
        (b.inner || []).forEach((x, j) => aus.push([`${i}:${j}`, x.type === "join" ? `Dazuholen ${x.table}` : `Nur wenn ${x.col} ${x.op} ${x.val ?? ""}`, ART[x.type].farbe]));
      } else if (!["start"].includes(b.type)) aus.push([`:${i}`, ART[b.type]?.name || "Profi-Stein", ART[b.type]?.farbe || PROFI_FARBE]);
    });
    return aus;
  }, [kette]);

  const v = erg?.vorschau;
  const ausgabeStein = kette[kette.length - 1]?.type === "ausgabe" ? kette[kette.length - 1] : null;
  const amEnde = !!ausgabeStein && v?.block === `:${kette.length - 1}`;
  const zeigeAls = ansicht ?? (ausgabeStein?.target === "Balken im Cockpit" ? "balken" : ausgabeStein?.target === "Linie im Cockpit" ? "linie" : "tabelle");
  const vorschauName = fluss.find(([fid]) => fid === v?.block)?.[1] || (v?.block?.endsWith(":fremd") ? "dazugeholte Tabelle" : "");

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-main)", color: "var(--text-main)" }}
      onClick={() => { setAuswahl(null); }}
      onKeyDown={(e) => { if (e.key === "Escape") { setAuswahl(null); setPlatzieren(null); } }} tabIndex={-1}>
      <style>{CSS}</style>
      {tour && <Tour onEnde={() => setTour(false)} />}
      <div className="bk-kopf">
        <button className="btn-ghost text-xs" onClick={() => navigate("/dashboard", { state: { tab: "mappings" } })}><ArrowLeft size={13} /> Dashboard</button>
        <strong style={{ fontSize: 15, color: "var(--text-bright)" }}>Baukasten</strong>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name der Auswertung …" style={{ minWidth: 240 }} aria-label="Name" />
        <label style={{ fontSize: 12, color: "var(--text-dim)", display: "flex", gap: 6, alignItems: "center" }}>Datenbank
          <select value={connectionId ?? ""} onChange={(e) => setConnectionId(Number(e.target.value) || null)}>
            {verbindungen.map((c) => <option key={c.id} value={c.id}>{c.mandant_label || c.name}</option>)}
          </select></label>
        <label style={{ fontSize: 12, color: "var(--text-dim)", display: "flex", gap: 6, alignItems: "center" }} title="Gilt für Steine mit „im Zeitraum“ – im Cockpit kommt der Zeitraum aus dem Formular">
          Zeitraum <input type="date" value={von} onChange={(e) => setVon(e.target.value)} /> – <input type="date" value={bis} onChange={(e) => setBis(e.target.value)} /></label>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
          {rechnet && <span style={{ fontSize: 12, color: "var(--text-dim)", display: "flex", gap: 5, alignItems: "center" }}><Loader2 size={13} className="animate-spin" /> rechnet …</span>}
          <button className="btn-ghost text-xs" onClick={rueckgaengig} disabled={!verlauf.current.zurueck.length} title="Rückgängig (Strg+Z)" aria-label="Rückgängig"><Undo2 size={13} /></button>
          <button className="btn-ghost text-xs" onClick={wiederholen} disabled={!verlauf.current.vor.length} title="Wiederholen (Strg+Y)" aria-label="Wiederholen"><Redo2 size={13} /></button>
          <button className="btn-ghost text-xs" onClick={() => setTour(true)} title="Kurze Einführung" aria-label="Kurze Einführung"><HelpCircle size={13} /></button>
          <button className="btn-ghost text-xs" title={mappingId ? "Dasselbe Mapping in der technischen Ansicht" : "Erst speichern, dann gibt es die Profi-Ansicht"}
            onClick={() => mappingId ? navigate(`/mappings/${mappingId}`) : setMeldung("Erst speichern – dann lässt sich die Profi-Ansicht öffnen.")}><Code2 size={13} /> Profi-Ansicht</button>
          <button className="btn-primary text-xs" onClick={speichern} disabled={speichert || !connectionId}>
            {speichert ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} Speichern</button>
        </div>
      </div>
      {profiGeaendert && (
        <div className="bk-meldung" style={{ background: "color-mix(in srgb, var(--warn, #f0994f) 14%, transparent)", border: "1px solid var(--warn, #f0994f)" }}>
          <AlertTriangle size={14} /> Dieses Mapping wurde in der Profi-Ansicht geändert. Der Baukasten zeigt den Stand von vorher; beim Speichern gingen die Profi-Änderungen verloren.
          <label style={{ marginLeft: "auto", display: "flex", gap: 6, alignItems: "center" }}><input type="checkbox" checked={profiVerwerfen} onChange={(e) => setProfiVerwerfen(e.target.checked)} /> Profi-Änderungen verwerfen</label>
        </div>)}
      {(meldung || fehler) && (
        <div className="bk-meldung" style={{ background: "var(--bg-card)", border: `1px solid ${fehler ? "var(--err)" : "var(--border)"}`, color: fehler ? "var(--err)" : "var(--text-main)" }}>
          {fehler || meldung}
          {!fehler && imCockpit && meldung.startsWith("Gespeichert und ins Cockpit") && (
            <button className="btn-primary text-xs" style={{ marginLeft: 10 }} onClick={() => navigate(`/forms/${imCockpit.form_id}/run`)}>Cockpit öffnen</button>)}
          <button onClick={() => { setMeldung(""); setFehler(""); }} style={{ marginLeft: "auto", background: "none", border: 0, color: "inherit", cursor: "pointer" }} aria-label="Schließen"><X size={14} /></button>
        </div>)}

      <div className="bk">
        <aside className="bk-panel bk-leiste" aria-label="Bausteine" onClick={(e) => e.stopPropagation()}>
          <h3>Bausteine</h3>
          {(() => {
            let g = ""; const out: any[] = [];
            for (const { typ, p } of palette) {
              const a = ART[typ];
              if (a.gruppe !== g) { g = a.gruppe; out.push(<div key={`g${g}`} className="bk-grp">{g}</div>); }
              const passt = auswahl && p && p.wie !== "anderswo";
              const aus = auswahl && !passt;
              out.push(
                <button key={typ} className={`bk-pal${passt ? " passt" : ""}${aus ? " aus" : ""}${platzieren === typ ? " platz" : ""}`} draggable
                  title={passt ? `Klicken setzt den Stein ${p!.wie} „${ART[liste(kette, auswahl!.key)[auswahl!.i]?.type]?.name || "Stein"}“` : a.text}
                  onDragStart={(e) => { setTragen({ kind: "new", type: typ }); e.dataTransfer.effectAllowed = "move"; }} onDragEnd={() => setTragen(null)}
                  onClick={() => {
                    if (passt) { setzen({ kind: "new", type: typ }, p!.key, p!.i); return; }
                    if (aus) { setMeldung(`„${a.name}“ passt nicht an den gewählten Stein. Auswahl aufheben (Esc), dann leuchten alle möglichen Stellen.`); return; }
                    setPlatzieren(platzieren === typ ? null : typ);
                  }}>
                  <Mini typ={typ} /><span><b>{a.name}</b><small>{a.text}</small></span>
                  {passt && <span className="bk-badge">{p!.wie === "hinein" ? "↳ hinein" : "↓ darunter"}</span>}
                </button>);
            }
            return out;
          })()}
          <p className="bk-info" style={{ marginTop: 8, lineHeight: 1.45 }}>
            {auswahl ? "Leuchtende Steine passen an den gewählten Stein – ein Klick setzt sie ein. Esc hebt die Auswahl auf."
              : "Stein antippen: dann leuchten die passenden Bausteine. Oder einen Baustein ziehen bzw. anklicken – dann leuchten die passenden Stellen."}
          </p>
          {(() => {
            const typ = auswahl ? (() => { try { return liste(kette, auswahl.key)[auswahl.i]?.type; } catch { return undefined; } })() : undefined;
            return typ && HILFE[typ] ? (
              <div className="bk-hilfe" style={{ "--c": ART[typ]?.farbe || PROFI_FARBE } as any}>
                <b>{ART[typ]?.name || "Profi-Stein"}</b>{HILFE[typ]}
              </div>) : null;
          })()}
        </aside>

        <main className="bk-platte" onClick={() => setAuswahl(null)}>
          <p className="bk-info">
            {platzieren ? `„${ART[platzieren].name}“ einsetzen: auf eine leuchtende Stelle klicken · Esc bricht ab`
              : !connectionId ? "Zuerst oben eine Datenbank wählen." : tabellen === null ? "Tabellen werden geladen …"
              : "Die Zahl an jedem Stein zeigt, wie viele Zeilen hier ankommen und weitergehen – ein Klick zeigt sie rechts."}
          </p>
          {connectionId && (
            <div onClick={(e) => e.stopPropagation()} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", margin: "0 0 12px",
              padding: "8px 10px", background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 10, maxWidth: 720 }}>
              <BookOpen size={14} style={{ color: "var(--text-dim)" }} />
              <select aria-label="Mit einem Rezept beginnen" value="" disabled={!rezepte.length}
                onChange={(e) => { const r = rezepte.find((x) => x.key === e.target.value); if (r) { ersetzen(r.kette, r.text); if (!name.trim()) setName(r.name); } }}
                style={{ background: "var(--bg-elevated)", color: "var(--text-bright)", border: "1px solid var(--border)", borderRadius: 7, padding: "5px 8px", fontSize: 13 }}>
                <option value="">{rezepte.length ? `Mit einem Rezept beginnen (${rezepte.length}) …` : "Keine Rezepte für diese Datenbank"}</option>
                {rezepte.map((r) => <option key={r.key} value={r.key}>{r.name} – {r.text}</option>)}
              </select>
              <span style={{ fontSize: 12, color: "var(--text-dim)" }}>oder</span>
              <input value={kiText} onChange={(e) => setKiText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") kiBauen(); }}
                placeholder="In eigenen Worten: z. B. „Welche Kunden aus Österreich haben offene Rechnungen?“" aria-label="Auswertung beschreiben"
                style={{ flex: "1 1 260px", minWidth: 0, background: "var(--bg-elevated)", color: "var(--text-bright)", border: "1px solid var(--border)", borderRadius: 7, padding: "5px 8px", fontSize: 13 }} />
              <button className="btn-primary text-xs" onClick={kiBauen} disabled={kiLaeuft || !kiText.trim()} title="Die KI legt die Steine – du siehst danach jeden einzelnen">
                {kiLaeuft ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />} {kiLaeuft ? "baut …" : "Mit KI bauen"}</button>
              {kiHinweis && <span style={{ flexBasis: "100%", fontSize: 12, color: "var(--text-main)" }}>💡 {kiHinweis}</span>}
            </div>)}
          <div className="bk-stapel">{stapel(kette, "")}</div>
        </main>

        <section className="bk-panel bk-vorschau" aria-label="Vorschau" onClick={(e) => e.stopPropagation()}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <h3>Vorschau</h3>
            {v && z[v.block] != null && <span style={{ fontFamily: "ui-monospace, Consolas, monospace", fontSize: 12, color: "var(--text-dim)" }}>{nf.format(z[v.block])} Zeilen</span>}
          </div>
          {!bereit && <p className="bk-info">Wähle im Stein „Aus Tabelle“ eine Tabelle – dann erscheinen hier ihre Zeilen.</p>}
          {v && <p className="bk-info">nach: <b>{vorschauName}</b>{v.zeilen?.length >= 50 ? " · die ersten 50" : ""}</p>}
          {v?.fehler && <p className="bk-info" style={{ color: "var(--err)" }}>{v.fehler}</p>}
          {v && v.spalten?.length > 0 && (
            <div className="bk-ansicht" role="group" aria-label="Darstellung">
              {(["tabelle", "balken", "linie"] as const).map((a) => (
                <button key={a} aria-pressed={zeigeAls === a} onClick={() => setAnsicht(a)}>{a === "tabelle" ? "Tabelle" : a === "balken" ? "Balken" : "Linie"}</button>))}
            </div>)}
          {v && v.spalten?.length > 0 && zeigeAls !== "tabelle" && (
            <VorschauDiagramm art={zeigeAls} spalten={v.spalten} zeilen={v.zeilen}
              x={amEnde ? ausgabeStein?.x : undefined} y={amEnde ? ausgabeStein?.y : undefined} />)}
          {v && v.spalten?.length > 0 && zeigeAls === "tabelle" && (
            <div className="bk-tbl"><table>
              <thead><tr>{v.spalten.map((c) => <th key={c}>{c}</th>)}</tr></thead>
              <tbody>{v.zeilen.map((r, k) => <tr key={k}>{v.spalten.map((c) => {
                const x = r[c]; const zahlig = typeof x === "number";
                return <td key={c} className={zahlig ? "n" : ""}>{x == null ? "–" : zahlig ? (Number.isInteger(x) ? nf.format(x) : nf2.format(x)) : String(x).slice(0, 80)}</td>;
              })}</tr>)}</tbody>
            </table></div>)}
          {erg && (
            <div className="bk-fluss" aria-label="Datenfluss">
              {fluss.filter(([fid]) => z[fid] != null).map(([fid, l, f]) => (
                <button key={fid} aria-current={fid === v?.block} onClick={() => setZeige(fid)}>
                  <span style={{ display: "flex", gap: 7, minWidth: 0 }}><i className="dot" style={{ background: f }} />
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{l}</span></span>
                  <span className="cnt">{nf.format(z[fid])}{warn[fid] ? " ⚠" : ""}</span>
                </button>))}
            </div>)}
          {erg?.sql && (
            <details style={{ marginTop: 10 }}><summary style={{ fontSize: 12, color: "var(--text-dim)", cursor: "pointer" }}>Erzeugtes SQL ansehen</summary>
              <pre style={{ fontSize: 11, whiteSpace: "pre-wrap", background: "var(--bg-elevated)", padding: 8, borderRadius: 6, maxHeight: 260, overflow: "auto" }}>{erg.sql}</pre>
            </details>)}
        </section>
      </div>
    </div>
  );
}
