import { useState, useEffect } from "react";
import { Brain, BookOpen, Wrench, MessageSquareX, Zap, Plus, Trash2, Edit2, Check, X, ChevronDown, ChevronRight, ToggleLeft, ToggleRight, Sparkles, Upload } from "lucide-react";
import { S } from "../constants";
import {
  Knowledge, Solution, Correction, CacheStats, Suggestion,
  listKnowledge, createKnowledge, updateKnowledge, deleteKnowledge,
  listSolutions, deleteSolution,
  listCorrections, deleteCorrection,
  getCacheStats, clearCache,
  getSuggestions, promoteSolution,
  importSchema,
} from "../../../api/aiMemory";
import { useProject } from "../../../context/ProjectContext";

const TABS = [
  { id: "knowledge", label: "Projektwissen",     icon: BookOpen },
  { id: "solutions", label: "Lösungen",          icon: Wrench },
  { id: "corrections", label: "Korrekturen",     icon: MessageSquareX },
  { id: "cache",     label: "Prompt Cache",      icon: Zap },
];

const CATEGORIES_KNOWLEDGE = ["rule", "field_mapping", "table", "format", "other"];
const CATEGORIES_SOLUTION  = ["sql", "python", "expression", "mapping", "ai_transform", "other"];
const SCOPE_LABELS = { global: "Global", datasource: "Datenquelle", project: "Projekt" };
const CAT_LABELS: Record<string, string> = {
  rule: "Regel", field_mapping: "Feld-Mapping", table: "Tabelle", format: "Format", other: "Sonstige",
  sql: "SQL", python: "Python", expression: "Ausdruck", mapping: "Mapping", ai_transform: "KI-Transform",
};

// ── Inline-Editor für Wissenseintrag ─────────────────────────────────────────

function KnowledgeForm({ item, onSave, onCancel }: {
  item?: Partial<Knowledge>;
  onSave: (data: Partial<Knowledge>) => void;
  onCancel: () => void;
}) {
  const { activeProject } = useProject();
  const [scope, setScope]     = useState<string>(item?.scope ?? "global");
  const [scopeId, setScopeId] = useState<string>(item?.scope_id ?? "");
  const [category, setCategory] = useState<string>(item?.category ?? "rule");
  const [title, setTitle]     = useState<string>(item?.title ?? "");
  const [content, setContent] = useState<string>(item?.content ?? "");

  const inp = (style?: object) => ({
    background: "rgba(255,255,255,0.06)", border: `1px solid ${S.border}`,
    borderRadius: 6, padding: "6px 10px", color: S.textMain, fontSize: 13, width: "100%",
    outline: "none", ...style,
  });

  const handleSave = () => {
    if (!title.trim() || !content.trim()) return;
    const effectiveScopeId =
      scope === "project" && !scopeId && activeProject ? String(activeProject.id) : scopeId;
    onSave({ scope, scope_id: effectiveScopeId || null, category, title: title.trim(), content: content.trim() });
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", gap: 8 }}>
        <div style={{ flex: 1 }}>
          <label style={{ fontSize: 11, color: S.textDim, display: "block", marginBottom: 4 }}>Geltungsbereich</label>
          <select value={scope} onChange={e => setScope(e.target.value)} style={inp() as any}>
            <option value="global">Global (alle Projekte)</option>
            <option value="datasource">Datenquelle (z.B. JTL)</option>
            <option value="project">Projekt</option>
          </select>
        </div>
        <div style={{ flex: 1 }}>
          <label style={{ fontSize: 11, color: S.textDim, display: "block", marginBottom: 4 }}>Kategorie</label>
          <select value={category} onChange={e => setCategory(e.target.value)} style={inp() as any}>
            {CATEGORIES_KNOWLEDGE.map(c => <option key={c} value={c}>{CAT_LABELS[c]}</option>)}
          </select>
        </div>
      </div>
      {scope === "datasource" && (
        <div>
          <label style={{ fontSize: 11, color: S.textDim, display: "block", marginBottom: 4 }}>Datenquellenname (z.B. "JTL", "Amazon")</label>
          <input value={scopeId} onChange={e => setScopeId(e.target.value)} style={inp() as any} placeholder="JTL" />
        </div>
      )}
      {scope === "project" && (
        <div>
          <label style={{ fontSize: 11, color: S.textDim, display: "block", marginBottom: 4 }}>
            Projekt-ID {activeProject ? `(aktuell: ${activeProject.name} = ${activeProject.id})` : ""}
          </label>
          <input value={scopeId || (activeProject ? String(activeProject.id) : "")}
            onChange={e => setScopeId(e.target.value)} style={inp() as any}
            placeholder={activeProject ? String(activeProject.id) : "Projekt-ID eingeben"} />
        </div>
      )}
      <div>
        <label style={{ fontSize: 11, color: S.textDim, display: "block", marginBottom: 4 }}>Titel / Kurzbezeichnung</label>
        <input value={title} onChange={e => setTitle(e.target.value)} style={inp() as any}
          placeholder="z.B. Umsatz-Feld, Amazon-Bestandstabelle, Datumsformat ..." />
      </div>
      <div>
        <label style={{ fontSize: 11, color: S.textDim, display: "block", marginBottom: 4 }}>Wissen / Regel</label>
        <textarea value={content} onChange={e => setContent(e.target.value)} rows={3}
          style={{ ...inp(), resize: "vertical" } as any}
          placeholder="z.B. 'Umsatz = fVKNetto' oder 'Datum immer als dd.MM.yyyy'" />
      </div>
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button onClick={onCancel}
          style={{ padding: "6px 14px", borderRadius: 6, border: `1px solid ${S.border}`, background: "none", color: S.textDim, cursor: "pointer", fontSize: 13 }}>
          Abbrechen
        </button>
        <button onClick={handleSave} disabled={!title.trim() || !content.trim()}
          style={{ padding: "6px 14px", borderRadius: 6, border: "none", background: S.accent, color: "#111", cursor: "pointer", fontSize: 13, fontWeight: 600 }}>
          Speichern
        </button>
      </div>
    </div>
  );
}


// ── Lern-Vorschläge Banner ────────────────────────────────────────────────────

function SuggestionsBanner({ onDismiss }: { onDismiss: () => void }) {
  const { activeProject } = useProject();
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [promoting, setPromoting] = useState<number | null>(null);
  const [done, setDone] = useState<Set<number>>(new Set());

  useEffect(() => {
    getSuggestions(activeProject?.id).then(s => setSuggestions(s)).catch(() => {});
  }, [activeProject?.id]);

  if (!suggestions.length) return null;
  const pending = suggestions.filter(s => !done.has(s.solution_id));
  if (!pending.length) return null;

  const handlePromote = async (s: Suggestion) => {
    setPromoting(s.solution_id);
    try {
      await promoteSolution({
        solution_id: s.solution_id,
        scope: activeProject ? "project" : "global",
        scope_id: activeProject ? String(activeProject.id) : undefined,
        category: "rule",
      });
      setDone(prev => new Set([...prev, s.solution_id]));
    } catch (_e) {}
    setPromoting(null);
  };

  return (
    <div style={{ marginBottom: 20 }}>
      {pending.map(s => (
        <div key={s.solution_id} style={{ display: "flex", alignItems: "flex-start", gap: 12, padding: "12px 14px",
          background: "rgba(252,228,153,0.06)", border: "1px solid rgba(252,228,153,0.25)", borderRadius: 8, marginBottom: 8 }}>
          <Sparkles size={16} style={{ color: "#fce499", flexShrink: 0, marginTop: 1 }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <p style={{ margin: "0 0 4px", fontSize: 13, fontWeight: 600, color: "#fce499" }}>Lern-Vorschlag</p>
            <p style={{ margin: 0, fontSize: 12, color: S.textDim }}>{s.message}</p>
            <p style={{ margin: "4px 0 0", fontSize: 11, color: S.textDim, fontFamily: "monospace",
              background: "rgba(0,0,0,0.2)", padding: "4px 8px", borderRadius: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {s.response_preview}
            </p>
          </div>
          <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
            <button onClick={() => handlePromote(s)} disabled={promoting === s.solution_id}
              style={{ padding: "5px 12px", borderRadius: 6, border: "none", background: "#fce499", color: "#111",
                cursor: "pointer", fontSize: 12, fontWeight: 600 }}>
              {promoting === s.solution_id ? "..." : "Ja, speichern"}
            </button>
            <button onClick={() => setDone(prev => new Set([...prev, s.solution_id]))}
              style={{ padding: "5px 10px", borderRadius: 6, border: `1px solid ${S.border}`, background: "none",
                color: S.textDim, cursor: "pointer", fontSize: 12 }}>
              Nein
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}


// ── Schema Quick-Import ───────────────────────────────────────────────────────

function SchemaImportSection({ onImported }: { onImported: () => void }) {
  const { activeProject } = useProject();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [scope, setScope] = useState("global");
  const [scopeId, setScopeId] = useState("");
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const inp = (style?: object) => ({
    background: "rgba(255,255,255,0.06)", border: `1px solid ${S.border}`,
    borderRadius: 6, padding: "6px 10px", color: S.textMain, fontSize: 13, width: "100%",
    outline: "none", ...style,
  });

  const handleImport = async () => {
    if (!text.trim()) return;
    setImporting(true);
    setResult(null);
    try {
      const effectiveScopeId = scope === "project" && !scopeId && activeProject
        ? String(activeProject.id) : scopeId;
      const res = await importSchema(text, scope, effectiveScopeId || undefined);
      setResult(`${res.created} Einträge importiert`);
      setText("");
      setTimeout(() => { setResult(null); setOpen(false); onImported(); }, 1500);
    } catch (_e) {
      setResult("Fehler beim Import");
    }
    setImporting(false);
  };

  return (
    <div style={{ marginBottom: 16 }}>
      <button onClick={() => setOpen(o => !o)}
        style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 12px", borderRadius: 6,
          border: `1px dashed ${S.border}`, background: "none", color: S.textDim, cursor: "pointer", fontSize: 12, width: "100%" }}>
        <Upload size={13} />
        Feld-Definitionen schnell importieren (feldname = Bedeutung)
        {open ? <ChevronDown size={13} style={{ marginLeft: "auto" }} /> : <ChevronRight size={13} style={{ marginLeft: "auto" }} />}
      </button>
      {open && (
        <div style={{ marginTop: 8, padding: 14, background: "rgba(255,255,255,0.03)", border: `1px solid ${S.border}`, borderRadius: 8 }}>
          <p style={{ fontSize: 11, color: S.textDim, marginBottom: 8 }}>
            Eine Definition pro Zeile im Format <code style={{ background: "rgba(255,255,255,0.08)", padding: "1px 5px", borderRadius: 3 }}>feldname = Bedeutung</code>
          </p>
          <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
            <select value={scope} onChange={e => setScope(e.target.value)} style={{ ...inp(), flex: 1 } as any}>
              <option value="global">Global</option>
              <option value="datasource">Datenquelle</option>
              <option value="project">Projekt</option>
            </select>
            {scope === "datasource" && (
              <input value={scopeId} onChange={e => setScopeId(e.target.value)} style={{ ...inp(), flex: 1 } as any} placeholder="z.B. JTL" />
            )}
            {scope === "project" && (
              <input value={scopeId || (activeProject ? String(activeProject.id) : "")}
                onChange={e => setScopeId(e.target.value)} style={{ ...inp(), flex: 1 } as any}
                placeholder={activeProject ? String(activeProject.id) : "Projekt-ID"} />
            )}
          </div>
          <textarea value={text} onChange={e => setText(e.target.value)} rows={6}
            style={{ ...inp(), resize: "vertical", fontFamily: "monospace", fontSize: 12 } as any}
            placeholder={"fVKNetto = Umsatz (Netto)\ndErstellt = Rechnungsdatum\nkKunde = Kunden-ID\ncArtNr = Artikelnummer\ncVersandlandISO = Versandland (ISO-Code)"} />
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 8, alignItems: "center" }}>
            {result && <span style={{ fontSize: 12, color: result.startsWith("Fehler") ? "#ef4444" : "#22c55e" }}>{result}</span>}
            <button onClick={handleImport} disabled={importing || !text.trim()}
              style={{ padding: "6px 14px", borderRadius: 6, border: "none", background: S.accent, color: "#111",
                cursor: "pointer", fontSize: 13, fontWeight: 600, opacity: !text.trim() ? 0.5 : 1 }}>
              {importing ? "Importiere..." : "Importieren"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}


// ── Wissen-Tab ────────────────────────────────────────────────────────────────

function KnowledgeTab() {
  const [items, setItems] = useState<Knowledge[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [filterScope, setFilterScope] = useState<string>("all");

  const load = () => { setLoading(true); listKnowledge().then(setItems).finally(() => setLoading(false)); };
  useEffect(load, []);

  const handleSave = async (data: Partial<Knowledge>) => {
    await createKnowledge(data);
    setAdding(false);
    load();
  };

  const handleUpdate = async (id: number, data: Partial<Knowledge>) => {
    await updateKnowledge(id, data);
    setEditId(null);
    load();
  };

  const handleToggle = async (item: Knowledge) => {
    await updateKnowledge(item.id, { ...item, enabled: !item.enabled });
    load();
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Wissenseintrag löschen?")) return;
    await deleteKnowledge(id);
    load();
  };

  const filtered = filterScope === "all" ? items : items.filter(i => i.scope === filterScope);
  const byScope: Record<string, Knowledge[]> = {};
  for (const item of filtered) {
    const key = item.scope + (item.scope_id ? `:${item.scope_id}` : "");
    if (!byScope[key]) byScope[key] = [];
    byScope[key].push(item);
  }

  return (
    <div>
      <SuggestionsBanner onDismiss={load} />
      <SchemaImportSection onImported={load} />

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 6 }}>
          {["all", "global", "datasource", "project"].map(s => (
            <button key={s} onClick={() => setFilterScope(s)}
              style={{ padding: "4px 12px", borderRadius: 20, border: `1px solid ${S.border}`, fontSize: 12,
                background: filterScope === s ? S.accent : "none", color: filterScope === s ? "#111" : S.textDim, cursor: "pointer" }}>
              {s === "all" ? "Alle" : SCOPE_LABELS[s as keyof typeof SCOPE_LABELS]}
            </button>
          ))}
        </div>
        <button onClick={() => setAdding(true)}
          style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 14px", borderRadius: 6, border: "none",
            background: S.accent, color: "#111", cursor: "pointer", fontSize: 13, fontWeight: 600 }}>
          <Plus size={14} /> Neu
        </button>
      </div>

      {adding && (
        <div style={{ background: "rgba(255,255,255,0.04)", border: `1px solid ${S.border}`, borderRadius: 8, padding: 16, marginBottom: 16 }}>
          <p style={{ fontSize: 13, fontWeight: 600, color: S.textMain, marginBottom: 12 }}>Neues Wissen hinzufügen</p>
          <KnowledgeForm onSave={handleSave} onCancel={() => setAdding(false)} />
        </div>
      )}

      {loading ? (
        <p style={{ color: S.textDim, fontSize: 13 }}>Laden...</p>
      ) : filtered.length === 0 ? (
        <EmptyState icon={BookOpen} title="Noch kein Projektwissen gespeichert"
          desc="Füge Regeln, Feld-Mappings und projektspezifische Informationen hinzu, damit die KI deinen Kontext kennt." />
      ) : (
        Object.entries(byScope).map(([key, group]) => {
          const first = group[0];
          const scopeLabel = SCOPE_LABELS[first.scope as keyof typeof SCOPE_LABELS] || first.scope;
          const scopeDetail = first.scope_id ? ` — ${first.scope_id}` : "";
          return (
            <div key={key} style={{ marginBottom: 20 }}>
              <p style={{ fontSize: 11, fontWeight: 700, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>
                {scopeLabel}{scopeDetail}
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {group.map(item => (
                  editId === item.id ? (
                    <div key={item.id} style={{ background: "rgba(255,255,255,0.04)", border: `1px solid ${S.border}`, borderRadius: 8, padding: 16 }}>
                      <KnowledgeForm item={item} onSave={d => handleUpdate(item.id, d)} onCancel={() => setEditId(null)} />
                    </div>
                  ) : (
                    <div key={item.id} style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "10px 14px",
                      background: "rgba(255,255,255,0.03)", border: `1px solid ${S.border}`, borderRadius: 8,
                      opacity: item.enabled ? 1 : 0.5 }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
                          <span style={{ fontSize: 13, fontWeight: 600, color: S.textMain }}>{item.title}</span>
                          <span style={{ fontSize: 10, padding: "1px 6px", borderRadius: 10, background: "rgba(255,255,255,0.08)", color: S.textDim }}>
                            {CAT_LABELS[item.category] || item.category}
                          </span>
                          {item.use_count > 0 && <span style={{ fontSize: 10, color: S.textDim }}>{item.use_count}× verwendet</span>}
                        </div>
                        <p style={{ fontSize: 12, color: S.textDim, margin: 0, whiteSpace: "pre-wrap" }}>{item.content}</p>
                      </div>
                      <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
                        <IconBtn icon={item.enabled ? ToggleRight : ToggleLeft} onClick={() => handleToggle(item)} title={item.enabled ? "Deaktivieren" : "Aktivieren"} />
                        <IconBtn icon={Edit2} onClick={() => setEditId(item.id)} title="Bearbeiten" />
                        <IconBtn icon={Trash2} onClick={() => handleDelete(item.id)} title="Löschen" danger />
                      </div>
                    </div>
                  )
                ))}
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}


// ── Lösungen-Tab ──────────────────────────────────────────────────────────────

function SolutionsTab() {
  const [items, setItems] = useState<Solution[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterCat, setFilterCat] = useState<string>("all");
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const load = () => { setLoading(true); listSolutions().then(setItems).finally(() => setLoading(false)); };
  useEffect(load, []);

  const handleDelete = async (id: number) => {
    if (!confirm("Lösung löschen?")) return;
    await deleteSolution(id);
    load();
  };

  const toggle = (id: number) => setExpanded(prev => {
    const n = new Set(prev);
    n.has(id) ? n.delete(id) : n.add(id);
    return n;
  });

  const cats = ["all", ...CATEGORIES_SOLUTION];
  const filtered = filterCat === "all" ? items : items.filter(i => i.category === filterCat);

  return (
    <div>
      <div style={{ display: "flex", gap: 6, marginBottom: 16, flexWrap: "wrap" }}>
        {cats.map(c => (
          <button key={c} onClick={() => setFilterCat(c)}
            style={{ padding: "4px 12px", borderRadius: 20, border: `1px solid ${S.border}`, fontSize: 12,
              background: filterCat === c ? S.accent : "none", color: filterCat === c ? "#111" : S.textDim, cursor: "pointer" }}>
            {c === "all" ? "Alle" : CAT_LABELS[c] || c}
          </button>
        ))}
      </div>

      {loading ? (
        <p style={{ color: S.textDim, fontSize: 13 }}>Laden...</p>
      ) : filtered.length === 0 ? (
        <EmptyState icon={Wrench} title="Noch keine Lösungen gespeichert"
          desc="Klicke im KI-Assistenten auf '✓ Als Lösung speichern' um erfolgreiche Antworten dauerhaft zu sichern." />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {filtered.map(item => {
            const isOpen = expanded.has(item.id);
            return (
              <div key={item.id} style={{ background: "rgba(255,255,255,0.03)", border: `1px solid ${S.border}`, borderRadius: 8, overflow: "hidden" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", cursor: "pointer" }}
                  onClick={() => toggle(item.id)}>
                  {isOpen ? <ChevronDown size={14} style={{ color: S.textDim, flexShrink: 0 }} /> : <ChevronRight size={14} style={{ color: S.textDim, flexShrink: 0 }} />}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: 13, fontWeight: 600, color: S.textMain }}>{item.title}</span>
                      <span style={{ fontSize: 10, padding: "1px 6px", borderRadius: 10, background: "rgba(255,255,255,0.08)", color: S.textDim }}>
                        {CAT_LABELS[item.category] || item.category}
                      </span>
                      {item.use_count > 1 && <span style={{ fontSize: 10, color: S.textDim }}>{item.use_count}× verwendet</span>}
                    </div>
                  </div>
                  <IconBtn icon={Trash2} onClick={e => { e.stopPropagation(); handleDelete(item.id); }} title="Löschen" danger />
                </div>
                {isOpen && (
                  <div style={{ padding: "0 14px 14px", borderTop: `1px solid ${S.border}` }}>
                    {item.prompt && (
                      <div style={{ marginTop: 10 }}>
                        <p style={{ fontSize: 11, color: S.textDim, marginBottom: 4, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>Anfrage</p>
                        <p style={{ fontSize: 12, color: S.textDim, margin: 0 }}>{item.prompt}</p>
                      </div>
                    )}
                    <div style={{ marginTop: 10 }}>
                      <p style={{ fontSize: 11, color: S.textDim, marginBottom: 4, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>Antwort</p>
                      <pre style={{ fontSize: 12, color: S.textMain, margin: 0, whiteSpace: "pre-wrap", fontFamily: "monospace",
                        background: "rgba(0,0,0,0.3)", padding: 10, borderRadius: 6, maxHeight: 300, overflowY: "auto" }}>
                        {item.response}
                      </pre>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}


// ── Korrekturen-Tab ───────────────────────────────────────────────────────────

function CorrectionsTab() {
  const [items, setItems] = useState<Correction[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const load = () => { setLoading(true); listCorrections().then(setItems).finally(() => setLoading(false)); };
  useEffect(load, []);

  const handleDelete = async (id: number) => {
    if (!confirm("Korrektur löschen?")) return;
    await deleteCorrection(id);
    load();
  };

  const toggle = (id: number) => setExpanded(prev => {
    const n = new Set(prev);
    n.has(id) ? n.delete(id) : n.add(id);
    return n;
  });

  return (
    <div>
      {loading ? (
        <p style={{ color: S.textDim, fontSize: 13 }}>Laden...</p>
      ) : items.length === 0 ? (
        <EmptyState icon={MessageSquareX} title="Noch keine Korrekturen gespeichert"
          desc="Benutzerkorrekturen helfen der KI, deine bevorzugte Schreibweise und Struktur zu lernen." />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {items.map(item => {
            const isOpen = expanded.has(item.id);
            return (
              <div key={item.id} style={{ background: "rgba(255,255,255,0.03)", border: `1px solid ${S.border}`, borderRadius: 8, overflow: "hidden" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", cursor: "pointer" }}
                  onClick={() => toggle(item.id)}>
                  {isOpen ? <ChevronDown size={14} style={{ color: S.textDim, flexShrink: 0 }} /> : <ChevronRight size={14} style={{ color: S.textDim, flexShrink: 0 }} />}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: 13, fontWeight: 600, color: S.textMain }}>
                        {item.user_correction.slice(0, 80)}{item.user_correction.length > 80 ? "…" : ""}
                      </span>
                      <span style={{ fontSize: 10, padding: "1px 6px", borderRadius: 10, background: "rgba(255,255,255,0.08)", color: S.textDim }}>
                        {CAT_LABELS[item.category] || item.category}
                      </span>
                    </div>
                  </div>
                  <IconBtn icon={Trash2} onClick={e => { e.stopPropagation(); handleDelete(item.id); }} title="Löschen" danger />
                </div>
                {isOpen && (
                  <div style={{ padding: "0 14px 14px", borderTop: `1px solid ${S.border}` }}>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 10 }}>
                      <div>
                        <p style={{ fontSize: 11, color: "#ef4444", marginBottom: 4, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>KI-Antwort (original)</p>
                        <pre style={{ fontSize: 12, color: S.textDim, margin: 0, whiteSpace: "pre-wrap", fontFamily: "monospace",
                          background: "rgba(239,68,68,0.07)", padding: 10, borderRadius: 6, border: "1px solid rgba(239,68,68,0.2)" }}>
                          {item.ai_response}
                        </pre>
                      </div>
                      <div>
                        <p style={{ fontSize: 11, color: "#22c55e", marginBottom: 4, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>Benutzer-Korrektur</p>
                        <pre style={{ fontSize: 12, color: S.textMain, margin: 0, whiteSpace: "pre-wrap", fontFamily: "monospace",
                          background: "rgba(34,197,94,0.07)", padding: 10, borderRadius: 6, border: "1px solid rgba(34,197,94,0.2)" }}>
                          {item.user_correction}
                        </pre>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}


// ── Cache-Tab ─────────────────────────────────────────────────────────────────

function CacheTab() {
  const [stats, setStats] = useState<CacheStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [clearing, setClearing] = useState(false);

  const load = () => { setLoading(true); getCacheStats().then(setStats).finally(() => setLoading(false)); };
  useEffect(load, []);

  const handleClear = async () => {
    if (!confirm("Prompt-Cache leeren?")) return;
    setClearing(true);
    await clearCache();
    setClearing(false);
    load();
  };

  if (loading) return <p style={{ color: S.textDim, fontSize: 13 }}>Laden...</p>;

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 20 }}>
        <StatCard label="Einträge" value={stats?.total_entries ?? 0} />
        <StatCard label="Cache-Treffer" value={stats?.total_hit_count ?? 0} />
        <StatCard label="Trefferquote" value={`${stats?.hit_rate ?? 0}%`} />
      </div>

      <div style={{ background: "rgba(255,255,255,0.03)", border: `1px solid ${S.border}`, borderRadius: 8, padding: 16 }}>
        <p style={{ fontSize: 13, color: S.textMain, marginBottom: 6, fontWeight: 600 }}>Prompt Cache</p>
        <p style={{ fontSize: 12, color: S.textDim, marginBottom: 12 }}>
          Identische Anfragen werden zwischengespeichert und sofort beantwortet — ohne LLM-Aufruf.
          Cache-Key: SHA-256(Prompt + Modell + Projekt).
        </p>
        <button onClick={handleClear} disabled={clearing || !stats?.total_entries}
          style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 14px", borderRadius: 6,
            border: `1px solid rgba(239,68,68,0.4)`, background: "rgba(239,68,68,0.1)",
            color: "#ef4444", cursor: "pointer", fontSize: 13, opacity: !stats?.total_entries ? 0.4 : 1 }}>
          <Trash2 size={13} /> Cache leeren ({stats?.total_entries ?? 0} Einträge)
        </button>
      </div>

      <div style={{ marginTop: 16, background: "rgba(255,255,255,0.03)", border: `1px solid ${S.border}`, borderRadius: 8, padding: 16 }}>
        <p style={{ fontSize: 12, color: S.textDim }}>
          <strong style={{ color: S.textMain }}>Hinweis:</strong> Der Prompt Cache speichert exakte Treffer.
          Semantische Ähnlichkeitssuche (Embeddings) ist für eine spätere Version geplant.
        </p>
      </div>
    </div>
  );
}


// ── Hilfselemente ─────────────────────────────────────────────────────────────

function IconBtn({ icon: Icon, onClick, title, danger = false }: { icon: any; onClick: (e: any) => void; title: string; danger?: boolean }) {
  return (
    <button onClick={onClick} title={title}
      style={{ background: "none", border: "none", cursor: "pointer", padding: 4, borderRadius: 4,
        color: danger ? "#ef4444" : S.textDim, opacity: 0.7 }}
      onMouseEnter={e => (e.currentTarget.style.opacity = "1")}
      onMouseLeave={e => (e.currentTarget.style.opacity = "0.7")}>
      <Icon size={14} />
    </button>
  );
}

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div style={{ background: "rgba(255,255,255,0.04)", border: `1px solid ${S.border}`, borderRadius: 8, padding: "14px 16px", textAlign: "center" }}>
      <p style={{ fontSize: 22, fontWeight: 700, color: S.accent, margin: 0 }}>{value}</p>
      <p style={{ fontSize: 12, color: S.textDim, margin: "4px 0 0" }}>{label}</p>
    </div>
  );
}

function EmptyState({ icon: Icon, title, desc }: { icon: any; title: string; desc: string }) {
  return (
    <div style={{ textAlign: "center", padding: "48px 24px" }}>
      <Icon size={32} style={{ color: S.textDim, margin: "0 auto 12px" }} />
      <p style={{ fontSize: 14, fontWeight: 600, color: S.textMain, marginBottom: 6 }}>{title}</p>
      <p style={{ fontSize: 12, color: S.textDim, maxWidth: 400, margin: "0 auto" }}>{desc}</p>
    </div>
  );
}


// ── Haupt-Panel ───────────────────────────────────────────────────────────────

export default function AIMemoryPanel() {
  const [tab, setTab] = useState("knowledge");

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      {/* Header */}
      <div style={{ padding: "16px 24px", borderBottom: `1px solid ${S.border}`, display: "flex", alignItems: "center", gap: 10 }}>
        <Brain size={18} style={{ color: S.accent }} />
        <div>
          <p style={{ margin: 0, fontSize: 15, fontWeight: 700, color: S.textMain }}>AI Memory</p>
          <p style={{ margin: 0, fontSize: 12, color: S.textDim }}>Projektbezogenes KI-Gedächtnis — kein Fine-Tuning, nur Kontext</p>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", borderBottom: `1px solid ${S.border}`, padding: "0 24px" }}>
        {TABS.map(({ id, label, icon: Icon }) => (
          <button key={id} onClick={() => setTab(id)}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "10px 16px", background: "none", border: "none",
              borderBottom: tab === id ? `2px solid ${S.accent}` : "2px solid transparent",
              color: tab === id ? S.accent : S.textDim, cursor: "pointer", fontSize: 13, fontWeight: tab === id ? 600 : 400,
              marginBottom: -1 }}>
            <Icon size={14} />
            {label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: "auto", padding: 24 }}>
        {tab === "knowledge"   && <KnowledgeTab />}
        {tab === "solutions"   && <SolutionsTab />}
        {tab === "corrections" && <CorrectionsTab />}
        {tab === "cache"       && <CacheTab />}
      </div>
    </div>
  );
}
