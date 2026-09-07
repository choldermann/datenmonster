import { useState, useEffect, useCallback } from "react";
import { Building2, Plus, Trash2, Search, AlertCircle, Loader2, X } from "lucide-react";
import api, { fehlerText } from "../../../api/client";
import { onMandantChange } from "../../../services/mandant";

const S = {
  bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)", bgMain: "var(--bg-main)",
  border: "var(--border)", textMain: "var(--text-main)", textDim: "var(--text-dim)",
  textBright: "var(--text-bright)", accent: "var(--accent)",
};

const inp = {
  backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4,
  color: S.textMain, fontSize: 12, padding: "5px 8px", outline: "none",
};

/**
 * Widget „Verbundene Unternehmen“: pflegt die Kunden, die aus den
 * Abfluss-Auswertungen herausfallen.
 *
 * Wozu: Wer wissen will, welche Kunden einen Artikel wirklich kaufen, muss die
 * Lieferungen an die eigene Firma und an Schwestergesellschaften ausblenden –
 * sonst steht der Konzern mengenmäßig ganz oben und verdeckt das echte Bild.
 * JTL bietet dafür kein Kennzeichen an; die Kundengruppen bilden Preisstufen ab,
 * nicht Verbundenheit.
 *
 * Die Liste wirkt nicht global: sie steht den Mappings als :excluded_customers
 * bereit, und nur der Reiter „Abflüsse je Artikel“ wendet sie an (gesteuert über
 * den Schalter im Filter). Eine Umsatzsumme soll die Konzernlieferung
 * weiterhin enthalten.
 */
export default function KundenAusschlussWidget({ widget, projectId }) {
  const [liste, setListe] = useState([]);
  const [laden, setLaden] = useState(true);
  const [fehler, setFehler] = useState(null);
  const [suche, setSuche] = useState("");
  const [treffer, setTreffer] = useState([]);
  const [sucht, setSucht] = useState(false);
  const [offen, setOffen] = useState(false);

  const q = projectId ? `?project_id=${projectId}` : "";

  const listeLaden = useCallback(async () => {
    setLaden(true);
    try {
      const { data } = await api.get(`/api/kunden-ausschluss${q}`);
      setListe(data || []);
      setFehler(null);
    } catch (e) {
      setFehler(fehlerText(e));
    } finally {
      setLaden(false);
    }
  }, [q]);

  useEffect(() => { listeLaden(); }, [listeLaden]);

  // Die kKunde-Nummern gelten nur in einer WaWi – beim Mandantenwechsel neu laden.
  useEffect(() => onMandantChange(() => { setTreffer([]); listeLaden(); }),
            [listeLaden]);

  const suchen = async () => {
    const term = suche.trim();
    if (!term) { setTreffer([]); return; }
    setSucht(true);
    try {
      const { data } = await api.get("/api/kunden-ausschluss/kunden/suche", {
        // Ohne connection_id nimmt das Backend den aktiven Mandanten.
        params: { project_id: projectId || undefined, q: term, limit: 25 },
      });
      setTreffer(data || []);
      setFehler(null);
    } catch (e) {
      setFehler(fehlerText(e));
    } finally {
      setSucht(false);
    }
  };

  const hinzufuegen = async (k) => {
    try {
      await api.post("/api/kunden-ausschluss", {
        project_id: projectId || null,
        k_kunde: k.k_kunde,
        kunden_nr: k.kunden_nr,
        name: k.name,
      });
      setTreffer(t => t.filter(x => x.k_kunde !== k.k_kunde));
      await listeLaden();
    } catch (e) { setFehler(fehlerText(e)); }
  };

  const entfernen = async (e) => {
    try {
      await api.delete(`/api/kunden-ausschluss/${e.id}`);
      await listeLaden();
    } catch (err) { setFehler(fehlerText(err)); }
  };

  const drin = new Set(liste.map(e => e.k_kunde));

  return (
    <div style={{ padding: 14 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <Building2 size={14} style={{ color: S.accent }} />
        <span style={{ fontSize: 12, color: S.textBright }}>
          {laden ? "Lade …" : `${liste.length} ausgeschlossene Kunden`}
        </span>
        <button style={{ display: "inline-flex", alignItems: "center", gap: 5,
          marginLeft: "auto", padding: "5px 10px", borderRadius: 5,
          border: `1px solid ${S.border}`, backgroundColor: S.bgEl,
          color: S.textMain, fontSize: 12, cursor: "pointer" }}
          onClick={() => setOffen(o => !o)}>
          {offen ? <X size={12} /> : <Plus size={12} />}
          {offen ? "Schließen" : "Kunde hinzufügen"}
        </button>
      </div>

      {fehler && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10,
          padding: "7px 10px", borderRadius: 5, backgroundColor: "rgba(224,112,112,.1)",
          border: "1px solid rgba(224,112,112,.3)", color: "#e07070", fontSize: 12 }}>
          <AlertCircle size={13} /> {fehler}
        </div>
      )}

      {offen && (
        <div style={{ marginBottom: 12, padding: 10, borderRadius: 6,
          backgroundColor: S.bgMain, border: `1px solid ${S.border}` }}>
          <div style={{ display: "flex", gap: 8 }}>
            <div style={{ position: "relative", flex: 1 }}>
              <Search size={12} style={{ position: "absolute", left: 8, top: 8,
                color: S.textDim }} />
              <input style={{ ...inp, paddingLeft: 24, width: "100%" }} value={suche}
                     placeholder="Kundenname oder Kundennummer …"
                     onChange={e => setSuche(e.target.value)}
                     onKeyDown={e => { if (e.key === "Enter") suchen(); }} />
            </div>
            <button style={{ ...inp, cursor: "pointer", padding: "5px 12px" }}
                    onClick={suchen} disabled={sucht}>
              {sucht ? <Loader2 size={12} className="spin" /> : "Suchen"}
            </button>
          </div>
          {treffer.length > 0 && (
            <div style={{ marginTop: 8, maxHeight: 220, overflowY: "auto" }}>
              {treffer.map(k => (
                <div key={k.k_kunde} style={{ display: "flex", alignItems: "center",
                  gap: 8, padding: "5px 4px", fontSize: 12,
                  borderBottom: `1px solid ${S.border}` }}>
                  <span style={{ color: S.textBright, flex: 1 }}>{k.name || "—"}</span>
                  <span style={{ color: S.textDim, fontSize: 11 }}>{k.ort}</span>
                  <span style={{ color: S.textDim, fontSize: 11 }}>Nr. {k.kunden_nr}</span>
                  {drin.has(k.k_kunde) ? (
                    <span style={{ color: S.textDim, fontSize: 11 }}>bereits in der Liste</span>
                  ) : (
                    <button style={{ ...inp, cursor: "pointer", padding: "2px 8px",
                      fontSize: 11 }} onClick={() => hinzufuegen(k)}>
                      <Plus size={11} /> übernehmen
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
          {!sucht && suche.trim() && treffer.length === 0 && (
            <p style={{ margin: "8px 0 0", fontSize: 11, color: S.textDim }}>
              Kein Treffer. Ein Betrieb kann in der WaWi mehrfach angelegt sein –
              dann nach dem Ort oder einer anderen Schreibweise suchen.
            </p>
          )}
        </div>
      )}

      {liste.length === 0 && !laden && (
        <p style={{ fontSize: 12, color: S.textDim, lineHeight: 1.6 }}>
          Noch kein Kunde ausgeschlossen. Solange die Liste leer ist, zeigen die
          Auswertungen alle Abgänge – auch die an verbundene Unternehmen.
        </p>
      )}

      {liste.length > 0 && (
        <div style={{ border: `1px solid ${S.border}`, borderRadius: 6,
          overflow: "hidden" }}>
          {liste.map(e => (
            <div key={e.id} style={{ display: "flex", alignItems: "center", gap: 10,
              padding: "7px 11px", fontSize: 12,
              borderBottom: `1px solid ${S.border}` }}>
              <span style={{ color: S.textBright, flex: 1 }}>{e.name || `Kunde ${e.k_kunde}`}</span>
              <span style={{ color: S.textDim, fontSize: 11 }}>Nr. {e.kunden_nr || "—"}</span>
              <Trash2 size={12} style={{ cursor: "pointer", color: S.textDim }}
                      onClick={() => entfernen(e)} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
