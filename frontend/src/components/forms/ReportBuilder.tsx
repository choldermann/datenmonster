import { useState, useEffect, useMemo } from "react";
import {
  X, Search, ChevronDown, ChevronRight, Gauge, Table2, BarChart3,
  Sparkles, Lock, Clock,
} from "lucide-react";
import api, { fehlerText } from "../../api/client";
import { S } from "../dashboard/constants";

/**
 * Der Report-Baukasten: alle Bausteine aller Cockpits in einer Übersicht,
 * gruppiert nach Cockpit und Reiter. Die Auswahl wird serverseitig zu einem
 * ganz normalen Formular zusammengesetzt.
 *
 * Die Kästchen starten bewusst alle LEER – der Anwender wählt aktiv aus.
 */

const ZEITRAEUME = [
  { id: "this_month", label: "Dieser Monat" },
  { id: "last_month", label: "Letzter Monat" },
  { id: "this_year",  label: "Dieses Jahr (Jahresanfang bis heute)" },
  { id: "last_year",  label: "Letztes Jahr" },
  { id: "days_30",    label: "Letzte 30 Tage" },
  { id: "months_12",  label: "Letzte 12 Monate" },
];

const FILTER = [
  { id: "alle",    label: "Alle" },
  { id: "kachel",  label: "Kacheln" },
  { id: "tabelle", label: "Tabellen" },
  { id: "grafik",  label: "Grafiken" },
  { id: "analyse", label: "Analysen" },
];

const ICON = { kachel: Gauge, tabelle: Table2, grafik: BarChart3, analyse: Sparkles };

// Ab hier wird ein Lauf spürbar langsam – der Anwender soll es vorher wissen.
const VIELE = 15;

const btn = (primary) => ({
  padding: "8px 16px", borderRadius: 6, fontSize: 12, fontWeight: 600,
  cursor: "pointer",
  backgroundColor: primary ? "rgba(252,228,153,0.15)" : "transparent",
  border: `1px solid ${primary ? "rgba(252,228,153,0.4)" : S.border}`,
  color: primary ? "var(--accent)" : S.textMain,
});

export default function ReportBuilder({ projectId, onClose, onCreated, formId = null }) {
  const aendern = formId != null;
  const [cockpits, setCockpits] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fehler, setFehler] = useState("");
  const [suche, setSuche] = useState("");
  const [filter, setFilter] = useState("alle");
  const [offen, setOffen] = useState({});
  const [gewaehlt, setGewaehlt] = useState([]);          // [{form_id, widget_id}]
  const [name, setName] = useState("");
  const [zeitraum, setZeitraum] = useState("this_month");
  const [speichert, setSpeichert] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [kat, sel] = await Promise.all([
          api.get("/api/reports/catalog", { params: projectId ? { project_id: projectId } : {} }),
          aendern ? api.get(`/api/reports/selection/${formId}`) : Promise.resolve(null),
        ]);
        const liste = kat.data.cockpits || [];
        setCockpits(liste);

        if (sel?.data) {
          setGewaehlt(sel.data.entries || []);
          setName(sel.data.name || "");
          setZeitraum(sel.data.zeitraum_preset || "this_month");
          // Beim Ändern die Cockpits aufklappen, aus denen etwas drin ist –
          // sonst sucht der Anwender seine Auswahl hinter zugeklappten Zeilen.
          const drin = new Set((sel.data.entries || []).map((e) => e.form_id));
          setOffen(Object.fromEntries([...drin].map((id) => [id, true])));
        } else if (liste[0]) {
          setOffen({ [liste[0].form_id]: true });
        }
      } catch (e) {
        setFehler(fehlerText(e));
      } finally { setLoading(false); }
    })();
  }, [projectId, formId]);

  const key = (e) => `${e.form_id}:${e.widget_id}`;
  const gewaehltSet = useMemo(
    () => new Set(gewaehlt.map(key)), [gewaehlt]);

  const toggle = (eintrag) => {
    if (!eintrag.uebernehmbar) return;
    const k = key(eintrag);
    setGewaehlt((alt) => gewaehltSet.has(k)
      ? alt.filter((x) => key(x) !== k)
      : [...alt, { form_id: eintrag.form_id, widget_id: eintrag.widget_id }]);
  };

  // Suche und Filter greifen auf die Einträge; Reiter und Cockpits ohne Treffer
  // verschwinden, damit die Liste beim Suchen wirklich kürzer wird.
  const sichtbar = useMemo(() => {
    const s = suche.trim().toLowerCase();
    return cockpits.map((c) => ({
      ...c,
      reiter: c.reiter.map((r) => ({
        ...r,
        eintraege: r.eintraege.filter((e) =>
          (filter === "alle" || e.gruppe === filter) &&
          (!s || e.label.toLowerCase().includes(s) ||
                 c.name.toLowerCase().includes(s) ||
                 r.label.toLowerCase().includes(s))),
      })).filter((r) => r.eintraege.length),
    })).filter((c) => c.reiter.length);
  }, [cockpits, suche, filter]);

  const treffer = sichtbar.reduce(
    (n, c) => n + c.reiter.reduce((m, r) => m + r.eintraege.length, 0), 0);

  const erstellen = async () => {
    setFehler(""); setSpeichert(true);
    try {
      const rumpf = { name: name.trim(), entries: gewaehlt,
                      zeitraum_preset: zeitraum, project_id: projectId || null };
      const { data } = aendern
        ? await api.put(`/api/reports/build/${formId}`, rumpf)
        : await api.post("/api/reports/build", rumpf);
      onCreated?.(data);
    } catch (e) {
      setFehler(fehlerText(e));
    } finally { setSpeichert(false); }
  };

  const bereit = name.trim().length > 0 && gewaehlt.length > 0 && !speichert;

  return (
    <div style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.6)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, padding: 24 }}>
      <div style={{ backgroundColor: S.bgMain, border: `1px solid ${S.border}`, borderRadius: 10,
        width: "100%", maxWidth: 920, maxHeight: "90vh", display: "flex", flexDirection: "column" }}>

        {/* Kopf */}
        <div style={{ padding: "16px 20px", borderBottom: `1px solid ${S.border}`,
          display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <h2 style={{ fontSize: 15, fontWeight: 700, color: S.textBright, margin: 0 }}>
              {aendern ? "Bausteine ändern" : "Report zusammenstellen"}
            </h2>
            <p style={{ fontSize: 11, color: S.textDim, marginTop: 3 }}>
              {aendern
                ? "Haken setzen oder entfernen – der Report wird angepasst"
                : "Kacheln, Tabellen und Grafiken aus allen Cockpits auswählen"}
            </p>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none",
            color: S.textDim, cursor: "pointer", padding: 4 }}><X size={18} /></button>
        </div>

        {/* Suche + Filter */}
        <div style={{ padding: "12px 20px", borderBottom: `1px solid ${S.border}`,
          display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <div style={{ position: "relative", flex: "1 1 220px" }}>
            <Search size={13} style={{ position: "absolute", left: 9, top: 9, color: S.textDim }} />
            <input value={suche} onChange={(e) => setSuche(e.target.value)}
              placeholder="Kennzahl oder Cockpit suchen…"
              style={{ width: "100%", padding: "7px 10px 7px 28px", borderRadius: 6,
                backgroundColor: S.bgCard, border: `1px solid ${S.border}`,
                color: S.textMain, fontSize: 12 }} />
          </div>
          <div style={{ display: "flex", gap: 4 }}>
            {FILTER.map((f) => (
              <button key={f.id} onClick={() => setFilter(f.id)}
                style={{ padding: "6px 11px", borderRadius: 5, fontSize: 11, cursor: "pointer",
                  backgroundColor: filter === f.id ? "rgba(252,228,153,0.15)" : "transparent",
                  border: `1px solid ${filter === f.id ? "rgba(252,228,153,0.4)" : S.border}`,
                  color: filter === f.id ? "var(--accent)" : S.textDim }}>
                {f.label}
              </button>
            ))}
          </div>
          <span style={{ fontSize: 11, color: S.textDim, marginLeft: "auto" }}>
            {treffer} Einträge
          </span>
        </div>

        {/* Liste */}
        <div style={{ flex: 1, overflowY: "auto", padding: "8px 20px" }}>
          {loading ? (
            <div style={{ padding: 40, textAlign: "center", color: S.textDim, fontSize: 12 }}>Lädt…</div>
          ) : sichtbar.length === 0 ? (
            <div style={{ padding: 40, textAlign: "center", color: S.textDim, fontSize: 12 }}>
              Nichts gefunden.
            </div>
          ) : sichtbar.map((c) => {
            const auf = offen[c.form_id];
            const gewaehltHier = c.reiter.reduce((n, r) =>
              n + r.eintraege.filter((e) => gewaehltSet.has(key(e))).length, 0);
            return (
              <div key={c.form_id} style={{ marginBottom: 6 }}>
                <button onClick={() => setOffen((o) => ({ ...o, [c.form_id]: !auf }))}
                  style={{ width: "100%", display: "flex", alignItems: "center", gap: 8,
                    padding: "10px 8px", background: "none", border: "none", cursor: "pointer",
                    borderBottom: `1px solid ${S.border}` }}>
                  {auf ? <ChevronDown size={14} color={S.textDim} /> : <ChevronRight size={14} color={S.textDim} />}
                  <span style={{ fontSize: 12.5, fontWeight: 600, color: S.textBright }}>{c.name}</span>
                  <span style={{ fontSize: 11, color: S.textDim }}>
                    {c.reiter.reduce((n, r) => n + r.eintraege.length, 0)}
                  </span>
                  {gewaehltHier > 0 && (
                    <span style={{ fontSize: 10.5, fontWeight: 600, color: "var(--accent)",
                      backgroundColor: "rgba(252,228,153,0.15)", padding: "1px 7px", borderRadius: 10 }}>
                      {gewaehltHier} gewählt
                    </span>
                  )}
                </button>

                {auf && c.reiter.map((r) => (
                  <div key={r.id} style={{ paddingLeft: 22, paddingTop: 8, paddingBottom: 4 }}>
                    <div style={{ fontSize: 10, letterSpacing: "0.06em", textTransform: "uppercase",
                      color: S.textDim, marginBottom: 5 }}>{r.label}</div>
                    {r.eintraege.map((e) => {
                      const an = gewaehltSet.has(key(e));
                      const Icon = ICON[e.gruppe] || Gauge;
                      return (
                        <label key={e.widget_id}
                          title={e.grund || ""}
                          style={{ display: "flex", alignItems: "center", gap: 9,
                            padding: "6px 8px", borderRadius: 5, marginBottom: 2,
                            cursor: e.uebernehmbar ? "pointer" : "not-allowed",
                            opacity: e.uebernehmbar ? 1 : 0.45,
                            backgroundColor: an ? "rgba(252,228,153,0.08)" : "transparent" }}>
                          <input type="checkbox" checked={an} disabled={!e.uebernehmbar}
                            onChange={() => toggle(e)} style={{ accentColor: "var(--accent)" }} />
                          <Icon size={13} color={an ? "var(--accent)" : S.textDim} />
                          <span style={{ fontSize: 12, color: an ? S.textBright : S.textMain, flex: 1 }}>
                            {e.label}
                          </span>
                          {!e.uebernehmbar && <Lock size={11} color={S.textDim} />}
                          <span style={{ fontSize: 10, color: S.textDim }}>{e.type_label}</span>
                        </label>
                      );
                    })}
                  </div>
                ))}
              </div>
            );
          })}
        </div>

        {/* Fuß */}
        <div style={{ padding: "14px 20px", borderTop: `1px solid ${S.border}`,
          display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div style={{ flex: "1 1 200px" }}>
            <label style={{ display: "block", fontSize: 10.5, color: S.textDim, marginBottom: 4 }}>
              Name des Reports
            </label>
            <input value={name} onChange={(e) => setName(e.target.value)}
              placeholder="z. B. Montagsbericht"
              style={{ width: "100%", padding: "7px 10px", borderRadius: 6,
                backgroundColor: S.bgCard, border: `1px solid ${S.border}`,
                color: S.textMain, fontSize: 12 }} />
          </div>
          <div style={{ flex: "0 1 240px" }}>
            <label style={{ display: "block", fontSize: 10.5, color: S.textDim, marginBottom: 4 }}>
              Voreingestellter Zeitraum
            </label>
            <select value={zeitraum} onChange={(e) => setZeitraum(e.target.value)}
              style={{ width: "100%", padding: "7px 10px", borderRadius: 6,
                backgroundColor: S.bgCard, border: `1px solid ${S.border}`,
                color: S.textMain, fontSize: 12 }}>
              {ZEITRAEUME.map((z) => <option key={z.id} value={z.id}>{z.label}</option>)}
            </select>
          </div>
          <div style={{ display: "flex", gap: 8, marginLeft: "auto" }}>
            <button onClick={onClose} style={btn(false)}>Abbrechen</button>
            <button onClick={erstellen} disabled={!bereit}
              style={{ ...btn(true), opacity: bereit ? 1 : 0.4,
                cursor: bereit ? "pointer" : "not-allowed" }}>
              {speichert ? "Wird gebaut…"
                : `${aendern ? "Änderungen übernehmen" : "Report erstellen"} (${gewaehlt.length})`}
            </button>
          </div>

          {gewaehlt.length >= VIELE && (
            <div style={{ flexBasis: "100%", display: "flex", alignItems: "center", gap: 6,
              fontSize: 11, color: S.textDim }}>
              <Clock size={12} />
              {gewaehlt.length} Einträge – ein Lauf über so viele Abfragen dauert
              spürbar. Für die Montagsmail unkritisch, beim Öffnen im Browser merklich.
            </div>
          )}
          {fehler && (
            <div style={{ flexBasis: "100%", fontSize: 11.5, color: "#f87171" }}>{fehler}</div>
          )}
        </div>
      </div>
    </div>
  );
}
