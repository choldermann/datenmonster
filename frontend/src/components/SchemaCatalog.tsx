import { useState, useEffect, useCallback, Fragment } from "react";
import { BookOpen, ChevronDown, ChevronRight, Download, Link2, Loader2, Sparkles, Plus, Trash2, Search, Star, StarOff, Upload } from "lucide-react";
import { useRef } from "react";
import api from "../api/client";
import { S } from "./dashboard/constants";

const CATEGORIES = ["Stammdaten", "Bewegungsdaten", "Konfiguration", "Lookup", "System", "Sonstige"];
const CAT_COLOR: Record<string, string> = {
  Stammdaten: "#60a5fa", Bewegungsdaten: "#34d399", Konfiguration: "#fbbf24",
  Lookup: "#a78bfa", System: "#f87171", Sonstige: S.textDim,
};

const inp = (extra?: object) => ({
  backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4,
  color: S.textBright, fontSize: 12, padding: "4px 8px", outline: "none", width: "100%",
  ...extra,
});

interface ColumnMeta { column_name: string; description: string | null; example_values: string | null; }
interface TableMeta {
  id: number; table_full_name: string; business_name: string | null;
  description: string | null; category: string | null; is_important: boolean;
  columns: ColumnMeta[];
}
interface Relation { id: number; from_table: string; from_col: string; to_table: string; to_col: string; description: string | null; }
interface Kandidat {
  from_table: string; from_col: string; to_table: string; to_col: string;
  quelle: "fk" | "schluessel" | "unsicher";
  alternativen: string[];
}
const QUELLE_LABEL: Record<string, { text: string; farbe: string; titel: string }> = {
  fk:         { text: "FK",        farbe: "#34d399", titel: "Echter Fremdschlüssel in der Datenbank" },
  schluessel: { text: "Schlüssel", farbe: "#60a5fa", titel: "Spalte heißt wie der Primärschlüssel der Zieltabelle" },
  unsicher:   { text: "unsicher",  farbe: "#fbbf24", titel: "Mehrere Tabellen kommen als Ziel in Frage" },
};

interface SchemaInfo { name: string; tabellen: number; views: number; empfohlen: boolean; }
interface Befund {
  art: string; objekt: string; titel: string; beleg: string;
  zahlen: Record<string, any>; gewicht: number;
}
interface Beziehung {
  von: string; von_spalte: string; nach: string; nach_spalte: string;
  quote: number; treffer: number; geprueft: number;
}
interface Entwurf {
  kategorie: string; objekt: string; titel: string; inhalt: string; zeichen: number;
  ungedeckte_zahlen: string[]; titel_existiert: boolean; zu_lang: boolean;
}
const ART_FARBE: Record<string, string> = {
  leer: "#f87171", ohne_treffer: "#f87171", beziehung: "#34d399",
  statuswerte: "#60a5fa", zeitraum: "#fbbf24",
};

export default function SchemaCatalog({ connectionId }: { connectionId: number }) {
  const [tables, setTables]       = useState<TableMeta[]>([]);
  const [relations, setRelations] = useState<Relation[]>([]);
  const [loading, setLoading]     = useState(true);
  const [search, setSearch]       = useState("");
  const [expanded, setExpanded]   = useState<Set<string>>(new Set());
  const [suggesting, setSuggesting] = useState(false);
  const [suggestProgress, setSuggestProgress] = useState<{done: number; total: number} | null>(null);
  const [activeTab, setActiveTab] = useState<"tables" | "relations" | "erkunden">("tables");
  // ── Schema-Erkundung ───────────────────────────────────────────────────────
  const [schemata, setSchemata]     = useState<SchemaInfo[] | null>(null);
  const [erkSchemas, setErkSchemas] = useState<Set<string>>(new Set());
  const [erkGrenze, setErkGrenze]   = useState(60);
  const [erkLaeuft, setErkLaeuft]   = useState(false);
  const [erkFortschritt, setErkFortschritt] = useState<{ objekt: string; i: number; n: number } | null>(null);
  const [befunde, setBefunde]       = useState<Befund[] | null>(null);
  const [beziehungen, setBeziehungen] = useState<Beziehung[]>([]);
  const [erkDauer, setErkDauer]     = useState<number | null>(null);
  const [entwerfend, setEntwerfend] = useState(false);
  const [entwuerfe, setEntwuerfe]   = useState<Entwurf[] | null>(null);
  // Vorschläge starten IMMER unausgewählt — der Benutzer entscheidet aktiv,
  // was in die Wissensdatenbank wandert.
  const [wahlWissen, setWahlWissen] = useState<Set<number>>(new Set());
  const [wahlBez, setWahlBez]       = useState<Set<number>>(new Set());
  const [uebernehmend, setUebernehmend] = useState(false);
  const [erkErgebnis, setErkErgebnis]   = useState<string | null>(null);
  // Für welche Wawi die Messwerte gelten — kommt vom Server (Verbindungsname).
  const [geltungsbereich, setGeltungsbereich] = useState<string | null>(null);
  const [newRel, setNewRel]       = useState({ from_table: "", from_col: "", to_table: "", to_col: "", description: "" });
  const [addingRel, setAddingRel] = useState(false);
  const [deriving, setDeriving]   = useState(false);
  const [kandidaten, setKandidaten] = useState<Kandidat[] | null>(null);
  const [deriveInfo, setDeriveInfo] = useState<{ auswahl: string; schon_vorhanden: number } | null>(null);
  // Vorschläge starten IMMER unausgewählt — der Anwender entscheidet, was gilt.
  const [gewaehlt, setGewaehlt]   = useState<Set<number>>(new Set());
  const [dirty, setDirty]         = useState<Record<string, TableMeta>>({});
  const [importing, setImporting] = useState(false);
  const [cacheBaut, setCacheBaut]  = useState(false);
  const importRef = useRef<HTMLInputElement>(null);
  // Anbieterwahl: nur sichtbar, wenn die Lizenz Guthaben hat. Vorbelegt ist der
  // eingestellte Anbieter — der Schalter gilt nur für diesen Katalog.
  const [guthaben, setGuthaben] = useState<number | null>(null);
  const [provider, setProvider] = useState<"ollama" | "datenmonster">("ollama");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/api/schema-catalog/${connectionId}`);
      // Erste Verwendung: Katalog-Einträge aus Schema-Cache anlegen
      if ((data.tables || []).length === 0) {
        await api.post(`/api/schema-catalog/${connectionId}/sync`);
        const { data: fresh } = await api.get(`/api/schema-catalog/${connectionId}`);
        setTables(fresh.tables || []);
        setRelations(fresh.relations || []);
      } else {
        setTables(data.tables || []);
        setRelations(data.relations || []);
      }
    } finally { setLoading(false); }
  }, [connectionId]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    api.get("/api/ai/credits")
      .then(({ data }) => {
        if (typeof data?.balance === "number") setGuthaben(data.balance);
        if (data?.enabled) setProvider("datenmonster");
      })
      .catch(() => {});   // ohne Lizenz bleibt der Schalter einfach weg
  }, []);

  const save = async (tbl: TableMeta) => {
    await api.put(`/api/schema-catalog/${connectionId}/table`, {
      table_full_name: tbl.table_full_name,
      business_name: tbl.business_name || null,
      description: tbl.description || null,
      category: tbl.category || null,
      is_important: tbl.is_important,
    });
    setDirty(d => { const n = {...d}; delete n[tbl.table_full_name]; return n; });
  };

  const saveCol = async (tableName: string, col: ColumnMeta) => {
    await api.put(`/api/schema-catalog/${connectionId}/column`, {
      table_full_name: tableName, column_name: col.column_name,
      description: col.description || null, example_values: col.example_values || null,
    });
  };

  const updateDirty = (tbl: TableMeta, changes: Partial<TableMeta>) => {
    const updated = { ...tbl, ...changes };
    setTables(ts => ts.map(t => t.table_full_name === tbl.table_full_name ? updated : t));
    setDirty(d => ({ ...d, [tbl.table_full_name]: updated }));
  };

  const handleAiSuggest = async (tableNames: string[] = []) => {
    setSuggesting(true);
    setSuggestProgress({ done: 0, total: tableNames.length || tables.filter(t => !t.description).length });
    try {
      const token = localStorage.getItem("dm_token") || "";
      const resp  = await fetch(`/api/schema-catalog/${connectionId}/ai-suggest`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ table_full_names: tableNames, provider }),
      });
      const reader  = resp.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop()!;
        for (const line of lines) {
          if (!line.startsWith("data:")) continue;
          const msg = JSON.parse(line.slice(5).trim());
          if (msg.error) { alert("KI-Fehler: " + msg.error); setSuggestProgress(null); break; }
          if (msg.warning) console.warn("KI-Warnung:", msg.warning, msg.raw);
          if (msg.progress !== undefined) setSuggestProgress({ done: msg.progress, total: msg.total });
          if (msg.done) { await load(); setSuggestProgress(null); }
        }
      }
    } finally { setSuggesting(false); }
  };

  const addRelation = async () => {
    if (!newRel.from_table || !newRel.from_col || !newRel.to_table || !newRel.to_col) return;
    setAddingRel(true);
    try {
      await api.post(`/api/schema-catalog/${connectionId}/relations`, newRel);
      setNewRel({ from_table: "", from_col: "", to_table: "", to_col: "", description: "" });
      await load();
    } finally { setAddingRel(false); }
  };

  const ableiten = async () => {
    setDeriving(true);
    try {
      // Ohne Tabellenauswahl entscheidet der Server: markierte Tabellen, sonst alle.
      const { data } = await api.post(`/api/schema-catalog/${connectionId}/relations/derive`, { tables: [] });
      setKandidaten(data.kandidaten || []);
      setDeriveInfo({ auswahl: data.auswahl, schon_vorhanden: data.schon_vorhanden });
      setGewaehlt(new Set());
    } catch (err: any) {
      alert(err.response?.data?.detail || "Ableiten fehlgeschlagen");
    } finally { setDeriving(false); }
  };

  const uebernehmen = async () => {
    if (!kandidaten || gewaehlt.size === 0) return;
    const auswahl = [...gewaehlt].map(i => {
      const k = kandidaten[i];
      return {
        from_table: k.from_table, from_col: k.from_col,
        to_table: k.to_table, to_col: k.to_col,
        description: k.quelle === "fk" ? "aus DB-Fremdschlüssel" : "aus Schlüsselnamen abgeleitet",
      };
    });
    await api.post(`/api/schema-catalog/${connectionId}/relations/bulk`, { relations: auswahl });
    setKandidaten(null); setGewaehlt(new Set()); setDeriveInfo(null);
    await load();
  };

  // Ohne Schema-Cache bleiben Tabellen- und Beziehungsreiter leer. Statt den
  // Katalog dann ganz zu verstecken (dann findet niemand das Erkunden), wird
  // hier angeboten, ihn aufzubauen.
  const cacheAufbauen = async () => {
    setCacheBaut(true);
    try {
      await api.post(`/api/connections/${connectionId}/rebuild-schema-cache`);
      // Der Aufbau läuft im Hintergrund — kurz warten, dann nachladen.
      await new Promise(r => setTimeout(r, 6000));
      await api.post(`/api/schema-catalog/${connectionId}/sync`);
      await load();
    } catch (err: any) {
      alert(err.response?.data?.detail || "Schema-Cache konnte nicht aufgebaut werden");
    } finally { setCacheBaut(false); }
  };

  // ── Schema-Erkundung ───────────────────────────────────────────────────────
  const schemataLaden = useCallback(async () => {
    try {
      const { data } = await api.get(`/api/schema-catalog/${connectionId}/schemata`);
      setSchemata(data.schemata || []);
    } catch { setSchemata([]); }
  }, [connectionId]);

  useEffect(() => { if (activeTab === "erkunden" && !schemata) schemataLaden(); },
           [activeTab, schemata, schemataLaden]);

  const erkunden = async () => {
    setErkLaeuft(true); setBefunde(null); setEntwuerfe(null); setErkErgebnis(null);
    setErkFortschritt(null);
    try {
      const token = localStorage.getItem("dm_token") || "";
      const resp = await fetch(`/api/schema-catalog/${connectionId}/erkunden`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ schemas: [...erkSchemas], max_objekte: erkGrenze }),
      });
      const reader = resp.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop()!;
        for (const line of lines) {
          if (!line.startsWith("data:")) continue;
          const roh = line.slice(5).trim();
          if (!roh || roh === "[DONE]") continue;
          const msg = JSON.parse(roh);
          if (msg.error) { alert("Erkundung fehlgeschlagen: " + msg.error); continue; }
          if (msg.progress) setErkFortschritt(msg.progress);
          if (msg.result) {
            setBefunde(msg.result.befunde || []);
            setBeziehungen(msg.result.beziehungen || []);
            setErkDauer(msg.result.dauer_sek);
          }
        }
      }
    } finally { setErkLaeuft(false); setErkFortschritt(null); }
  };

  const entwerfen = async () => {
    if (!befunde) return;
    setEntwerfend(true); setErkErgebnis(null);
    try {
      // Nur die berichtenswerten Befunde — der Rest bläht den Prompt auf.
      const wichtig = befunde.filter(b => b.gewicht >= 2).slice(0, 80);
      const { data } = await api.post(
        `/api/schema-catalog/${connectionId}/erkunden/wissen`,
        { befunde: wichtig, hoechstens: 12, provider });
      setEntwuerfe(data.entwuerfe || []);
      setGeltungsbereich(data.geltungsbereich || null);
      setWahlWissen(new Set());
    } catch (err: any) {
      alert(err.response?.data?.detail || "Entwurf fehlgeschlagen");
    } finally { setEntwerfend(false); }
  };

  const erkUebernehmen = async () => {
    setUebernehmend(true);
    try {
      const { data } = await api.post(
        `/api/schema-catalog/${connectionId}/erkunden/uebernehmen`, {
          eintraege:   [...wahlWissen].map(i => entwuerfe![i]),
          beziehungen: [...wahlBez].map(i => belegteBeziehungen[i]),
        });
      setErkErgebnis(
        `${data.wissen_neu} Regeln neu, ${data.wissen_aktualisiert} aktualisiert, ` +
        `${data.beziehungen_neu} Beziehungen in den Katalog übernommen` +
        (data.geltungsbereich ? ` — Wissen gilt für „${data.geltungsbereich}".` : "."));
      setWahlWissen(new Set()); setWahlBez(new Set());
      await load();
    } catch (err: any) {
      alert(err.response?.data?.detail || "Übernehmen fehlgeschlagen");
    } finally { setUebernehmend(false); }
  };

  const handleExport = async () => {
    const token = localStorage.getItem("dm_token") || "";
    const resp  = await fetch(`/api/schema-catalog/${connectionId}/export`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const blob = await resp.blob();
    const cd   = resp.headers.get("content-disposition") || "";
    const name = cd.match(/filename="([^"]+)"/)?.[1] || `schema_catalog_${connectionId}.json`;
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href = url; a.download = name; a.click();
    URL.revokeObjectURL(url);
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const text    = await file.text();
      const payload = JSON.parse(text);
      await api.post(`/api/schema-catalog/${connectionId}/import`, payload);
      await load();
    } catch (err: any) {
      alert("Import fehlgeschlagen: " + (err.response?.data?.detail || err.message));
    } finally {
      setImporting(false);
      if (importRef.current) importRef.current.value = "";
    }
  };

  const deleteRelation = async (id: number) => {
    await api.delete(`/api/schema-catalog/${connectionId}/relations/${id}`);
    setRelations(rs => rs.filter(r => r.id !== id));
  };

  const filtered = tables.filter(t =>
    !search || t.table_full_name.toLowerCase().includes(search.toLowerCase()) ||
    (t.description || "").toLowerCase().includes(search.toLowerCase()) ||
    (t.business_name || "").toLowerCase().includes(search.toLowerCase())
  );

  const toggleExpand = (name: string) =>
    setExpanded(s => { const n = new Set(s); n.has(name) ? n.delete(name) : n.add(name); return n; });

  // Belegte Beziehungen für den Katalog; je Quellspalte die beste.
  //
  // Die Grenze liegt bei 50 %, nicht bei 99 %: ein OPTIONALER Fremdschlüssel
  // erreicht die hohe Hürde nie. Rechnung.tRechnung.kShop trifft zu 34 %, weil
  // zwei Drittel der Rechnungen keine Shop-Bestellungen sind — der Join ist
  // richtig, er braucht nur ein LEFT JOIN. Mit der 99-%-Grenze verlor jeder
  // Lauf genau diese Joins (bei PPS 13 brauchbare, darunter
  // tArtikel.kWarengruppe und tArtikel.kHersteller).
  //
  // Sortiert: sichere zuerst, danach die optionalen — die Anzeige trennt sie,
  // damit niemand einen 60-%-Join für einen Pflichtjoin hält.
  const belegteBeziehungen = (() => {
    const beste = new Map<string, Beziehung>();
    for (const b of beziehungen) {
      if (b.quote < 50) continue;
      const k = `${b.von}.${b.von_spalte}`;
      const alt = beste.get(k);
      if (!alt || b.quote > alt.quote) beste.set(k, b);
    }
    return [...beste.values()].sort((a, b) => b.quote - a.quote);
  })();
  const ersterOptionale = belegteBeziehungen.findIndex(b => b.quote < 99);
  const anzahlSicher = ersterOptionale < 0 ? belegteBeziehungen.length : ersterOptionale;

  const described = tables.filter(t => t.description).length;
  const undescribed = tables.filter(t => !t.description).length;

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: 20, color: S.textDim, fontSize: 12 }}>
      <Loader2 size={14} className="animate-spin" /> Lade Katalog…
    </div>
  );

  return (
    <div style={{ fontSize: 12, color: S.textMain }}>
      {/* Hidden file input for import */}
      <input ref={importRef} type="file" accept=".json" style={{ display: "none" }} onChange={handleImport} />

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <BookOpen size={14} color={S.accent} />
          <span style={{ fontWeight: 700, color: S.textBright }}>Schema-Katalog</span>
          <span style={{ color: S.textDim }}>
            {described}/{tables.length} beschrieben
          </span>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <button onClick={handleExport}
            style={{ display: "flex", alignItems: "center", gap: 5, backgroundColor: S.bgEl,
              color: S.textDim, border: `1px solid ${S.border}`, borderRadius: 6, padding: "5px 10px",
              cursor: "pointer", fontSize: 11 }}>
            <Download size={11} /> Export
          </button>
          <button onClick={() => importRef.current?.click()} disabled={importing}
            style={{ display: "flex", alignItems: "center", gap: 5, backgroundColor: S.bgEl,
              color: S.textDim, border: `1px solid ${S.border}`, borderRadius: 6, padding: "5px 10px",
              cursor: importing ? "not-allowed" : "pointer", fontSize: 11 }}>
            {importing ? <Loader2 size={11} className="animate-spin" /> : <Upload size={11} />}
            Import
          </button>
          {guthaben !== null && guthaben > 0 && (
            <div title={`Datenmonster AI: ${guthaben} Credits übrig`}
              style={{ display: "flex", alignItems: "center", gap: 0, border: `1px solid ${S.border}`,
                borderRadius: 6, overflow: "hidden" }}>
              {([["ollama", "Ollama"], ["datenmonster", `Datenmonster AI · ${guthaben}`]] as const).map(([wert, text]) => (
                <button key={wert} onClick={() => setProvider(wert as any)} disabled={suggesting}
                  style={{ border: "none", padding: "5px 9px", fontSize: 10, cursor: suggesting ? "not-allowed" : "pointer",
                    backgroundColor: provider === wert ? "rgba(252,228,153,0.14)" : "transparent",
                    color: provider === wert ? S.textBright : S.textDim }}>
                  {text}
                </button>
              ))}
            </div>
          )}
          <button
            onClick={() => handleAiSuggest()}
            disabled={suggesting || undescribed === 0}
            style={{ display: "flex", alignItems: "center", gap: 5, backgroundColor: suggesting ? S.bgEl : "#7c3aed",
              color: "#fff", border: "none", borderRadius: 6, padding: "5px 10px", cursor: suggesting ? "not-allowed" : "pointer",
              fontSize: 11, opacity: undescribed === 0 ? 0.5 : 1 }}
          >
            {suggesting ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} />}
            {suggesting
              ? suggestProgress ? `${suggestProgress.done}/${suggestProgress.total}` : "…"
              : undescribed > 100
                ? `KI: 100 beschreiben (${undescribed - 100} weitere)`
                : `KI: ${undescribed} beschreiben`}
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 2, marginBottom: 12, borderBottom: `1px solid ${S.border}` }}>
        {(["tables", "relations", "erkunden"] as const).map(tab => (
          <button key={tab} onClick={() => setActiveTab(tab)} style={{
            background: "none", border: "none", cursor: "pointer", padding: "6px 12px",
            fontSize: 11, fontWeight: activeTab === tab ? 700 : 400,
            color: activeTab === tab ? S.textBright : S.textDim,
            borderBottom: activeTab === tab ? `2px solid ${S.accent}` : "2px solid transparent",
            marginBottom: -1,
          }}>
            {tab === "tables" ? `Tabellen (${tables.length})`
              : tab === "relations" ? `Beziehungen (${relations.length})`
              : "Erkunden"}
          </button>
        ))}
      </div>

      {activeTab === "tables" && tables.length === 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 12px",
          backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 6,
          color: S.textDim, lineHeight: 1.6 }}>
          <span>
            Für diese Verbindung gibt es noch keinen Schema-Cache — deshalb sind Tabellen
            und Beziehungen leer. Der Reiter <b>Erkunden</b> funktioniert trotzdem, er misst
            direkt gegen die Datenbank.
          </span>
          <button onClick={cacheAufbauen} disabled={cacheBaut}
            style={{ marginLeft: "auto", whiteSpace: "nowrap", display: "flex", alignItems: "center",
              gap: 6, backgroundColor: S.accent, color: "#111", border: "none", borderRadius: 6,
              padding: "6px 12px", fontWeight: 700, fontSize: 11,
              cursor: cacheBaut ? "not-allowed" : "pointer" }}>
            {cacheBaut ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
            {cacheBaut ? "Baue auf…" : "Schema-Cache aufbauen"}
          </button>
        </div>
      )}

      {activeTab === "tables" && (
        <>
          {/* Search */}
          <div style={{ position: "relative", marginBottom: 10 }}>
            <Search size={11} style={{ position: "absolute", left: 8, top: "50%", transform: "translateY(-50%)", color: S.textDim }} />
            <input value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Tabelle suchen…"
              style={{ ...inp(), paddingLeft: 26 }} />
          </div>

          {/* Table List */}
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {filtered.map(tbl => {
              const isOpen = expanded.has(tbl.table_full_name);
              const isDirty = !!dirty[tbl.table_full_name];
              const current = dirty[tbl.table_full_name] || tbl;
              return (
                <div key={tbl.table_full_name} style={{ backgroundColor: S.bgEl, borderRadius: 6, border: `1px solid ${isDirty ? S.accent : S.border}` }}>
                  {/* Row header */}
                  <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 10px", cursor: "pointer" }}
                    onClick={() => toggleExpand(tbl.table_full_name)}>
                    {isOpen ? <ChevronDown size={11} color={S.textDim} /> : <ChevronRight size={11} color={S.textDim} />}
                    <button onClick={e => { e.stopPropagation(); updateDirty(current, { is_important: !current.is_important }); save({ ...current, is_important: !current.is_important }); }}
                      style={{ background: "none", border: "none", cursor: "pointer", padding: 0, display: "flex" }}>
                      {current.is_important
                        ? <Star size={11} fill="#fbbf24" color="#fbbf24" />
                        : <StarOff size={11} color={S.textDim} />}
                    </button>
                    <span style={{ fontWeight: 600, color: S.textBright, fontFamily: "monospace" }}>{tbl.table_full_name}</span>
                    {current.business_name && (
                      <span style={{ color: S.accent, fontSize: 11 }}>"{current.business_name}"</span>
                    )}
                    {current.category && (
                      <span style={{ color: CAT_COLOR[current.category] || S.textDim, fontSize: 10,
                        backgroundColor: S.bgCard, borderRadius: 3, padding: "1px 5px" }}>
                        {current.category}
                      </span>
                    )}
                    {!current.description && (
                      <span style={{ color: "#f87171", fontSize: 10, marginLeft: "auto" }}>keine Beschreibung</span>
                    )}
                    {current.description && (
                      <span style={{ color: S.textDim, fontSize: 11, marginLeft: "auto", overflow: "hidden",
                        textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 260 }}>
                        {current.description}
                      </span>
                    )}
                  </div>

                  {/* Expanded edit form */}
                  {isOpen && (
                    <div style={{ padding: "0 10px 10px", borderTop: `1px solid ${S.border}`, marginTop: 4, paddingTop: 10 }}>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
                        <div>
                          <div style={{ fontSize: 10, color: S.textDim, marginBottom: 3 }}>ANZEIGENAME</div>
                          <input style={inp()} value={current.business_name || ""}
                            onChange={e => updateDirty(current, { business_name: e.target.value })}
                            onBlur={() => save(current)} placeholder="z.B. Artikel" />
                        </div>
                        <div>
                          <div style={{ fontSize: 10, color: S.textDim, marginBottom: 3 }}>KATEGORIE</div>
                          <select style={{ ...inp(), cursor: "pointer" }} value={current.category || ""}
                            onChange={e => { const updated = { ...current, category: e.target.value || null }; updateDirty(current, { category: e.target.value || null }); save(updated); }}>
                            <option value="">— wählen —</option>
                            {CATEGORIES.map(c => <option key={c}>{c}</option>)}
                          </select>
                        </div>
                      </div>
                      <div style={{ marginBottom: 8 }}>
                        <div style={{ fontSize: 10, color: S.textDim, marginBottom: 3 }}>BESCHREIBUNG</div>
                        <input style={inp()} value={current.description || ""}
                          onChange={e => updateDirty(current, { description: e.target.value })}
                          onBlur={() => save(current)}
                          placeholder="Was enthält diese Tabelle? (1 Satz)" />
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <button onClick={() => handleAiSuggest([tbl.table_full_name])}
                          disabled={suggesting}
                          style={{ display: "flex", alignItems: "center", gap: 4, background: "none",
                            border: `1px solid ${S.border}`, borderRadius: 4, padding: "3px 8px",
                            color: S.textDim, fontSize: 10, cursor: "pointer" }}>
                          <Sparkles size={10} /> KI-Vorschlag
                        </button>
                        {isDirty && (
                          <button onClick={() => save(current)}
                            style={{ backgroundColor: S.accent, color: "#fff", border: "none",
                              borderRadius: 4, padding: "3px 10px", fontSize: 10, cursor: "pointer" }}>
                            Speichern
                          </button>
                        )}
                      </div>

                      {/* Columns */}
                      {current.columns.length > 0 && (
                        <div style={{ marginTop: 10, borderTop: `1px solid ${S.border}`, paddingTop: 8 }}>
                          <div style={{ fontSize: 10, color: S.textDim, marginBottom: 6 }}>SPALTEN</div>
                          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                            {current.columns.map(col => (
                              <div key={col.column_name} style={{ display: "grid", gridTemplateColumns: "120px 1fr 100px", gap: 6, alignItems: "center" }}>
                                <span style={{ fontFamily: "monospace", fontSize: 11, color: S.textBright }}>{col.column_name}</span>
                                <input style={inp({ padding: "2px 6px" })}
                                  defaultValue={col.description || ""}
                                  onBlur={e => saveCol(tbl.table_full_name, { ...col, description: e.target.value })}
                                  placeholder="Beschreibung…" />
                                <input style={inp({ padding: "2px 6px" })}
                                  defaultValue={col.example_values || ""}
                                  onBlur={e => saveCol(tbl.table_full_name, { ...col, example_values: e.target.value })}
                                  placeholder="Beispiel…" />
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}

      {activeTab === "relations" && (
        <div>
          {/* Aus Schlüsseln ableiten */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
            <button onClick={ableiten} disabled={deriving}
              style={{ display: "flex", alignItems: "center", gap: 5, backgroundColor: S.bgEl,
                color: S.textBright, border: `1px solid ${S.border}`, borderRadius: 4,
                padding: "5px 10px", cursor: deriving ? "wait" : "pointer", fontSize: 11 }}>
              {deriving ? <Loader2 size={11} className="animate-spin" /> : <Link2 size={11} />}
              Aus Schlüsseln ableiten
            </button>
            <span style={{ fontSize: 10, color: S.textDim }}>
              Fremdschlüssel der Datenbank plus Spalten, die wie der Primärschlüssel einer
              anderen Tabelle heißen — dieselbe Regel wie beim Auto-Join im Mapping.
            </span>
          </div>

          {kandidaten && (
            <div style={{ backgroundColor: S.bgEl, borderRadius: 6, padding: 12, marginBottom: 12,
              border: `1px solid ${S.border}` }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: 11, color: S.textBright }}>
                  {kandidaten.length} Vorschläge
                  {deriveInfo?.auswahl === "wichtige" && " aus den mit ★ markierten Tabellen"}
                  {deriveInfo?.auswahl === "alle" && " aus allen Tabellen"}
                  {!!deriveInfo?.schon_vorhanden && ` · ${deriveInfo.schon_vorhanden} bereits vorhanden`}
                </span>
                {deriveInfo?.auswahl === "alle" && (
                  <span style={{ fontSize: 10, color: S.textDim }}>
                    Tipp: Tabellen im Reiter „Tabellen" mit ★ markieren, dann werden nur deren
                    Beziehungen vorgeschlagen.
                  </span>
                )}
                <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
                  <button onClick={() => setGewaehlt(g =>
                      g.size === kandidaten.length ? new Set() : new Set(kandidaten.map((_, i) => i)))}
                    style={{ background: "none", border: `1px solid ${S.border}`, borderRadius: 4,
                      color: S.textDim, fontSize: 10, padding: "3px 8px", cursor: "pointer" }}>
                    {gewaehlt.size === kandidaten.length ? "Keine" : "Alle"}
                  </button>
                  <button onClick={() => { setKandidaten(null); setDeriveInfo(null); }}
                    style={{ background: "none", border: `1px solid ${S.border}`, borderRadius: 4,
                      color: S.textDim, fontSize: 10, padding: "3px 8px", cursor: "pointer" }}>
                    Verwerfen
                  </button>
                  <button onClick={uebernehmen} disabled={gewaehlt.size === 0}
                    style={{ backgroundColor: gewaehlt.size ? S.accent : S.bgEl, color: gewaehlt.size ? "#fff" : S.textDim,
                      border: "none", borderRadius: 4, fontSize: 10, padding: "3px 10px",
                      cursor: gewaehlt.size ? "pointer" : "default" }}>
                    {gewaehlt.size} übernehmen
                  </button>
                </div>
              </div>

              {kandidaten.length === 0 ? (
                <div style={{ fontSize: 11, color: S.textDim }}>
                  Keine neuen Beziehungen gefunden — entweder sind sie schon erfasst, oder in
                  diesen Tabellen führen keine Schlüssel weiter.
                </div>
              ) : (
                <div style={{ maxHeight: 320, overflowY: "auto", display: "flex",
                  flexDirection: "column", gap: 3 }}>
                  {kandidaten.map((k, i) => (
                    <label key={i} style={{ display: "flex", alignItems: "center", gap: 8,
                      padding: "4px 6px", borderRadius: 4, cursor: "pointer",
                      backgroundColor: gewaehlt.has(i) ? "rgba(255,255,255,0.05)" : "transparent" }}>
                      <input type="checkbox" checked={gewaehlt.has(i)} style={{ cursor: "pointer" }}
                        onChange={() => setGewaehlt(g => {
                          const n = new Set(g); n.has(i) ? n.delete(i) : n.add(i); return n;
                        })} />
                      <span title={QUELLE_LABEL[k.quelle].titel}
                        style={{ fontSize: 9, padding: "1px 5px", borderRadius: 8, flexShrink: 0,
                          color: QUELLE_LABEL[k.quelle].farbe,
                          backgroundColor: "rgba(255,255,255,0.06)" }}>
                        {QUELLE_LABEL[k.quelle].text}
                      </span>
                      <span style={{ fontFamily: "monospace", fontSize: 11, color: S.textBright }}>
                        {k.from_table}.<span style={{ color: "#fbbf24" }}>{k.from_col}</span>
                        {" → "}
                        {k.to_table}.<span style={{ color: "#fbbf24" }}>{k.to_col}</span>
                      </span>
                      {k.quelle === "unsicher" && k.alternativen.length > 0 && (
                        <span style={{ fontSize: 10, color: S.textDim }}>
                          auch möglich: {k.alternativen.slice(0, 2).join(", ")}
                          {k.alternativen.length > 2 && ` (+${k.alternativen.length - 2})`}
                        </span>
                      )}
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Neue Relation */}
          <div style={{ backgroundColor: S.bgEl, borderRadius: 6, padding: 12, marginBottom: 12, border: `1px solid ${S.border}` }}>
            <div style={{ fontSize: 10, color: S.textDim, marginBottom: 8 }}>NEUE FK-BEZIEHUNG</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 80px 1fr 80px", gap: 6, marginBottom: 6 }}>
              <input style={inp()} value={newRel.from_table}
                onChange={e => setNewRel(r => ({ ...r, from_table: e.target.value }))}
                placeholder="Von Tabelle (z.B. Rechnung.tRechnungPos)" />
              <input style={inp()} value={newRel.from_col}
                onChange={e => setNewRel(r => ({ ...r, from_col: e.target.value }))}
                placeholder="Spalte" />
              <input style={inp()} value={newRel.to_table}
                onChange={e => setNewRel(r => ({ ...r, to_table: e.target.value }))}
                placeholder="Zu Tabelle (z.B. dbo.tArtikel)" />
              <input style={inp()} value={newRel.to_col}
                onChange={e => setNewRel(r => ({ ...r, to_col: e.target.value }))}
                placeholder="Spalte" />
            </div>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <input style={{ ...inp(), flex: 1 }} value={newRel.description}
                onChange={e => setNewRel(r => ({ ...r, description: e.target.value }))}
                placeholder="Beschreibung (optional)" />
              <button onClick={addRelation} disabled={addingRel || !newRel.from_table || !newRel.to_table}
                style={{ display: "flex", alignItems: "center", gap: 4, backgroundColor: S.accent,
                  color: "#fff", border: "none", borderRadius: 4, padding: "5px 10px",
                  cursor: "pointer", fontSize: 11, whiteSpace: "nowrap" }}>
                <Plus size={11} /> Hinzufügen
              </button>
            </div>
          </div>

          {/* Relation List */}
          {relations.length === 0 ? (
            <div style={{ color: S.textDim, fontSize: 11, padding: "12px 0" }}>
              Noch keine Beziehungen erfasst — „Aus Schlüsseln ableiten" schlägt welche vor.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {relations.map(r => (
                <div key={r.id} style={{ display: "flex", alignItems: "center", gap: 8,
                  backgroundColor: S.bgEl, borderRadius: 6, padding: "6px 10px",
                  border: `1px solid ${S.border}` }}>
                  <span style={{ fontFamily: "monospace", fontSize: 11, color: S.textBright }}>
                    {r.from_table}.<span style={{ color: "#fbbf24" }}>{r.from_col}</span>
                    {" → "}
                    {r.to_table}.<span style={{ color: "#fbbf24" }}>{r.to_col}</span>
                  </span>
                  {r.description && <span style={{ color: S.textDim, fontSize: 11 }}>({r.description})</span>}
                  <button onClick={() => deleteRelation(r.id)}
                    style={{ marginLeft: "auto", background: "none", border: "none",
                      color: "#f87171", cursor: "pointer", padding: 2 }}>
                    <Trash2 size={11} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === "erkunden" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ color: S.textDim, lineHeight: 1.6, fontSize: 11,
            backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 6, padding: "8px 10px" }}>
            Die Erkundung <b>misst</b> die gewählten Objekte gegen die Datenbank — Füllstand,
            Trefferquoten der Schlüssel, tatsächlich vorkommende Statuswerte, Zeitspannen.
            Erst danach formuliert die KI daraus Regeln, und zwar ausschließlich aus diesen
            Messwerten. Views werden mitgemessen; der Schema-Cache kennt nur Tabellen.
          </div>

          {/* Auswahl */}
          <div>
            <div style={{ color: S.textBright, fontWeight: 700, marginBottom: 6 }}>
              Wo soll gemessen werden?
              <span style={{ color: S.textDim, fontWeight: 400, marginLeft: 6 }}>
                (nichts gewählt = alle Fachschemata; Ziele einer Beziehung kommen immer aus der ganzen DB)
              </span>
            </div>
            {!schemata ? (
              <div style={{ color: S.textDim, display: "flex", gap: 6, alignItems: "center" }}>
                <Loader2 size={12} className="animate-spin" /> Schemata werden geladen…
              </div>
            ) : (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 5, maxHeight: 150, overflowY: "auto" }}>
                {schemata.filter(sc => sc.empfohlen && sc.tabellen + sc.views > 0).map(sc => {
                  const an = erkSchemas.has(sc.name);
                  return (
                    <button key={sc.name} onClick={() => setErkSchemas(m => {
                      const n = new Set(m); n.has(sc.name) ? n.delete(sc.name) : n.add(sc.name); return n;
                    })} style={{
                      border: `1px solid ${an ? S.accent : S.border}`, borderRadius: 5,
                      backgroundColor: an ? "rgba(252,228,153,0.14)" : S.bgEl,
                      color: an ? S.textBright : S.textDim, padding: "3px 8px",
                      fontSize: 11, cursor: "pointer",
                    }}>
                      {sc.name} <span style={{ opacity: 0.6 }}>{sc.tabellen + sc.views}</span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <label style={{ color: S.textDim }}>
              höchstens
              <input type="number" min={1} max={500} value={erkGrenze}
                onChange={e => setErkGrenze(Math.max(1, Math.min(500, +e.target.value || 1)))}
                style={{ ...inp({ width: 64, display: "inline-block", margin: "0 6px" }) }} />
              Objekte
            </label>
            <button onClick={erkunden} disabled={erkLaeuft}
              style={{ display: "flex", alignItems: "center", gap: 6, backgroundColor: S.accent,
                color: "#111", border: "none", borderRadius: 6, padding: "6px 12px",
                fontWeight: 700, cursor: erkLaeuft ? "not-allowed" : "pointer", fontSize: 11 }}>
              {erkLaeuft ? <Loader2 size={12} className="animate-spin" /> : <Search size={12} />}
              {erkLaeuft ? "Messe…" : "Messen"}
            </button>
            {erkFortschritt && (
              <span style={{ color: S.textDim }}>
                {erkFortschritt.i}/{erkFortschritt.n} · {erkFortschritt.objekt}
              </span>
            )}
            {befunde && !erkLaeuft && (
              <span style={{ color: S.textDim }}>
                {befunde.length} Befunde in {erkDauer}s
              </span>
            )}
          </div>

          {/* Befunde */}
          {befunde && befunde.length > 0 && (
            <div>
              <div style={{ color: S.textBright, fontWeight: 700, marginBottom: 6 }}>Messwerte</div>
              <div style={{ maxHeight: 260, overflowY: "auto", display: "flex",
                flexDirection: "column", gap: 4 }}>
                {befunde.map((b, i) => (
                  <div key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start",
                    padding: "5px 8px", backgroundColor: S.bgEl, borderRadius: 5,
                    border: `1px solid ${S.border}`, lineHeight: 1.45 }}>
                    <span style={{ color: ART_FARBE[b.art] || S.textDim, fontSize: 10,
                      fontWeight: 700, minWidth: 86 }}>{b.art}</span>
                    <span style={{ color: S.textDim }}>{b.beleg}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Belegte Beziehungen für den Katalog */}
          {belegteBeziehungen.length > 0 && (
            <div>
              <div style={{ color: S.textBright, fontWeight: 700, marginBottom: 6 }}>
                Belegte Beziehungen ({belegteBeziehungen.length}) — für den Schema-Katalog
              </div>
              <div style={{ maxHeight: 180, overflowY: "auto", display: "flex",
                flexDirection: "column", gap: 3 }}>
                {belegteBeziehungen.map((b, i) => (
                  <Fragment key={i}>
                  {i === 0 && anzahlSicher > 0 && (
                    <div style={{ color: S.textDim, fontSize: 10, textTransform: "uppercase",
                      letterSpacing: "0.06em", marginTop: 2 }}>
                      Sicher ({anzahlSicher}) — trifft bei fast jeder Zeile
                    </div>
                  )}
                  {i === anzahlSicher && (
                    <div style={{ color: "#e0a070", fontSize: 10, textTransform: "uppercase",
                      letterSpacing: "0.06em", marginTop: 6 }}>
                      Optional ({belegteBeziehungen.length - anzahlSicher}) — Spalte ist oft leer,
                      im SQL LEFT JOIN nehmen
                    </div>
                  )}
                  <label style={{ display: "flex", gap: 8, alignItems: "center",
                    padding: "4px 8px", backgroundColor: S.bgEl, borderRadius: 5,
                    border: `1px solid ${b.quote < 99 ? "#e0a070" : S.border}`, cursor: "pointer" }}>
                    <input type="checkbox" checked={wahlBez.has(i)}
                      onChange={() => setWahlBez(m => {
                        const n = new Set(m); n.has(i) ? n.delete(i) : n.add(i); return n;
                      })} />
                    <span style={{ fontFamily: "monospace", fontSize: 11 }}>
                      {b.von}.<span style={{ color: "#fbbf24" }}>{b.von_spalte}</span>
                      {" → "}{b.nach}.<span style={{ color: "#fbbf24" }}>{b.nach_spalte}</span>
                    </span>
                    <span style={{ color: b.quote < 99 ? "#e0a070" : "#34d399",
                      fontSize: 10, marginLeft: "auto" }}>
                      {b.quote} % ({b.treffer}/{b.geprueft})
                    </span>
                  </label>
                  </Fragment>
                ))}
              </div>
            </div>
          )}

          {/* Entwürfe */}
          {befunde && befunde.length > 0 && (
            <button onClick={entwerfen} disabled={entwerfend}
              style={{ alignSelf: "flex-start", display: "flex", alignItems: "center", gap: 6,
                backgroundColor: S.bgEl, color: S.textBright, border: `1px solid ${S.border}`,
                borderRadius: 6, padding: "6px 12px", fontSize: 11,
                cursor: entwerfend ? "not-allowed" : "pointer" }}>
              {entwerfend ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
              {entwerfend ? "KI formuliert…" : "Regeln daraus formulieren"}
            </button>
          )}

          {entwuerfe && (
            <div>
              <div style={{ color: S.textBright, fontWeight: 700, marginBottom: 6 }}>
                Entwürfe ({entwuerfe.length}) — nichts wird gespeichert, bevor du es auswählst
              </div>
              {geltungsbereich && (
                <div style={{ color: S.textDim, fontSize: 11, marginBottom: 6 }}>
                  Gilt nur für „{geltungsbereich}" — Messwerte einer Wawi sind über
                  einer anderen falsch. Bestehendes Wissen anderer Verbindungen
                  bleibt unberührt.
                </div>
              )}
              <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                {entwuerfe.map((e, i) => {
                  const warnung = e.ungedeckte_zahlen.length > 0 || e.zu_lang || e.titel_existiert;
                  return (
                    <label key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start",
                      padding: "7px 9px", backgroundColor: S.bgEl, borderRadius: 6,
                      border: `1px solid ${warnung ? "#e0a070" : S.border}`, cursor: "pointer" }}>
                      <input type="checkbox" checked={wahlWissen.has(i)} style={{ marginTop: 2 }}
                        onChange={() => setWahlWissen(m => {
                          const n = new Set(m); n.has(i) ? n.delete(i) : n.add(i); return n;
                        })} />
                      <div style={{ minWidth: 0, lineHeight: 1.5 }}>
                        <div style={{ color: S.textBright, fontWeight: 600 }}>
                          {e.titel}
                          <span style={{ color: S.textDim, fontWeight: 400, marginLeft: 6 }}>
                            {e.kategorie} · {e.zeichen} Z.
                          </span>
                        </div>
                        <div style={{ color: S.textDim }}>{e.inhalt}</div>
                        {e.ungedeckte_zahlen.length > 0 && (
                          <div style={{ color: "#e0a070", fontSize: 10, marginTop: 3 }}>
                            ⚠ Nicht gemessene Zahlen: {e.ungedeckte_zahlen.join(", ")} — bitte prüfen.
                          </div>
                        )}
                        {e.titel_existiert && (
                          <div style={{ color: "#e0a070", fontSize: 10, marginTop: 3 }}>
                            ⚠ Ein Eintrag mit diesem Titel existiert und würde überschrieben.
                          </div>
                        )}
                        {e.zu_lang && (
                          <div style={{ color: "#e0a070", fontSize: 10, marginTop: 3 }}>
                            ⚠ Über 800 Zeichen — kommt im Prompt oft nicht mehr ins Budget.
                          </div>
                        )}
                      </div>
                    </label>
                  );
                })}
              </div>
            </div>
          )}

          {(wahlWissen.size > 0 || wahlBez.size > 0) && (
            <button onClick={erkUebernehmen} disabled={uebernehmend}
              style={{ alignSelf: "flex-start", display: "flex", alignItems: "center", gap: 6,
                backgroundColor: S.accent, color: "#111", border: "none", borderRadius: 6,
                padding: "7px 14px", fontWeight: 700, fontSize: 11,
                cursor: uebernehmend ? "not-allowed" : "pointer" }}>
              {uebernehmend ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
              {wahlWissen.size} Regeln und {wahlBez.size} Beziehungen übernehmen
            </button>
          )}

          {erkErgebnis && (
            <div style={{ color: "#34d399", fontSize: 11 }}>{erkErgebnis}</div>
          )}
        </div>
      )}
    </div>
  );
}
