import { useState, useEffect, useCallback, useRef } from "react";
import { Search, Plus, Trash2, Loader2, X, PackageX, AlertCircle, ArrowRightLeft } from "lucide-react";
import api, { fehlerText } from "../../api/client";
import { ladeMandanten, onMandantChange } from "../../services/mandant";

const S = {
  bgMain: "var(--bg-main)", bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)",
  border: "var(--border)", textMain: "var(--text-main)", textBright: "var(--text-bright)",
  textDim: "var(--text-dim)", accent: "var(--accent)",
};

const inputStyle = {
  flex: 1, padding: "8px 12px", borderRadius: 6, fontSize: 13,
  backgroundColor: S.bgEl, border: `1px solid ${S.border}`, color: S.textMain, outline: "none",
};

/**
 * Ausschlussartikel-Verwaltung: Artikel in der JTL-DB suchen, auswählen und pro
 * Projekt als Ausschluss speichern. Diese Artikel werden bei jeder Intrastat-
 * Auswertung/Export automatisch herausgefiltert.
 */
export default function IntrastatExclusionPanel({ projectId, connectionId: fixedConn }) {
  const [connections, setConnections] = useState([]);
  const [connId, setConnId] = useState(fixedConn ?? null);
  const [mandantAktiv, setMandantAktiv] = useState(null);
  const [uebertragbar, setUebertragbar] = useState(null);   // { quellen, gesamt }
  const [uebernehmend, setUebernehmend] = useState(false);
  const [bericht, setBericht] = useState(null);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [exclusions, setExclusions] = useState([]);
  const [error, setError] = useState(null);
  const debounceRef = useRef(null);

  const pq = projectId != null ? `?project_id=${projectId}` : "";

  const loadExclusions = useCallback(async () => {
    try {
      const { data } = await api.get(`/api/intrastat/exclusions${pq}`);
      setExclusions(Array.isArray(data) ? data : []);
    } catch (e) { setError(fehlerText(e)); }
  }, [pq]);

  useEffect(() => { loadExclusions(); }, [loadExclusions, mandantAktiv]);

  // Der aktive Mandant schlägt die Verbindung aus dem Formular-Schema. Diese ist
  // beim Installieren eingefroren worden und zeigt nach einem Serverwechsel auf
  // eine WaWi, die es nicht mehr gibt; die Ausschlussliste richtet sich dagegen
  // immer nach dem Mandanten. Beides muss dieselbe Datenbank meinen, sonst sucht
  // man im einen Betrieb und sieht die Artikel des anderen.
  useEffect(() => {
    let abgemeldet = false;
    ladeMandanten(projectId).then(({ aktiv }) => {
      if (!abgemeldet) setMandantAktiv(aktiv ?? null);
    });
    const ab = onMandantChange((pid, aktiv) => {
      if (String(pid ?? "") === String(projectId ?? "")) setMandantAktiv(aktiv ?? null);
    });
    return () => { abgemeldet = true; ab(); };
  }, [projectId]);

  // Die tatsächlich befragte WaWi: Mandant, sonst die Vorgabe aus dem Formular.
  const effConnId = mandantAktiv ?? connId;

  // Verbindungen des Projekts laden (für die Artikel-Suche). Bei genau einer
  // Verbindung automatisch vorauswählen.
  useEffect(() => {
    if (fixedConn != null) { setConnId(fixedConn); return; }
    api.get(`/api/connections/${pq}`).then(({ data }) => {
      const list = Array.isArray(data) ? data : [];
      setConnections(list);
      if (list.length === 1) setConnId(list[0].id);
    }).catch(() => {});
  }, [pq, fixedConn]);

  const runSearch = useCallback(async (term) => {
    if (effConnId == null) { setError("Bitte zuerst eine JTL-Verbindung wählen."); return; }
    setSearching(true);
    setError(null);
    try {
      const p = new URLSearchParams({ connection_id: String(effConnId), q: term });
      if (projectId != null) p.set("project_id", String(projectId));
      const { data } = await api.get(`/api/intrastat/articles/search?${p}`);
      setSearchResults(Array.isArray(data) ? data : []);
    } catch (e) {
      setError(fehlerText(e));
      setSearchResults([]);
    } finally { setSearching(false); }
  }, [effConnId, projectId]);

  // Debounced Suche bei Eingabe
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!query.trim() || effConnId == null) { setSearchResults([]); return; }
    debounceRef.current = setTimeout(() => runSearch(query.trim()), 350);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [query, effConnId, runSearch]);

  const excludedIds = new Set(exclusions.map(e => e.k_artikel));

  const addExclusion = async (art) => {
    try {
      await api.post("/api/intrastat/exclusions", {
        project_id: projectId ?? null,
        connection_id: effConnId ?? null,
        k_artikel: art.k_artikel,
        art_nr: art.art_nr,
        name: art.name,
      });
      loadExclusions();
    } catch (e) { setError(fehlerText(e)); }
  };

  const removeExclusion = async (id) => {
    try {
      await api.delete(`/api/intrastat/exclusions/${id}`);
      setExclusions(prev => prev.filter(e => e.id !== id));
    } catch (e) { setError(fehlerText(e)); }
  };

  // Ausschlüsse hängen an der Verbindung, aus der sie stammen – kArtikel ist eine
  // interne ID je WaWi. Nach einem Serverwechsel stehen die gepflegten Artikel
  // deshalb an der alten Verbindung und wirken nicht mehr. Statt das stillschweigend
  // hinzunehmen, wird darauf hingewiesen; übernommen wird nur auf Klick.
  useEffect(() => {
    if (effConnId == null) { setUebertragbar(null); return; }
    let ab = false;
    const p = new URLSearchParams({ connection_id: String(effConnId) });
    if (projectId != null) p.set("project_id", String(projectId));
    api.get(`/api/intrastat/exclusions/uebertragbar?${p}`)
      .then(({ data }) => { if (!ab) setUebertragbar(data?.gesamt ? data : null); })
      .catch(() => { if (!ab) setUebertragbar(null); });
    return () => { ab = true; };
  }, [effConnId, projectId, exclusions.length]);

  const uebernehmen = async () => {
    setUebernehmend(true);
    setError(null);
    setBericht(null);
    try {
      const { data } = await api.post("/api/intrastat/exclusions/uebernehmen", {
        project_id: projectId ?? null,
        connection_id: effConnId ?? null,
        from_connection_id: uebertragbar?.quellen?.length === 1
          ? uebertragbar.quellen[0].connection_id : null,
      });
      setBericht(data);
      loadExclusions();
    } catch (e) { setError(fehlerText(e)); }
    finally { setUebernehmend(false); }
  };

  return (
    <div style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`, borderRadius: 10, padding: "20px 24px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
        <PackageX size={16} color={S.textDim} />
        <span style={{ fontSize: 14, fontWeight: 600, color: S.textBright }}>Ausschlussartikel</span>
      </div>
      <p style={{ fontSize: 12, color: S.textDim, margin: "0 0 16px" }}>
        Hier ausgewählte Artikel (z.B. Europaletten oder anderes Verpackungsmaterial) werden
        bei jeder Intrastat-Auswertung und beim Export automatisch herausgefiltert.
      </p>

      {error && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", borderRadius: 6,
          backgroundColor: "rgba(224,112,112,0.1)", border: "1px solid rgba(224,112,112,0.3)",
          color: "#e07070", fontSize: 12, marginBottom: 14 }}>
          <AlertCircle size={14} /> {error}
        </div>
      )}

      {/* Verbindungsauswahl nur ohne Mandanten: sonst führt der Umschalter in der
          Kopfzeile, und zwei Auswahlen für dieselbe Sache widersprechen sich. */}
      {mandantAktiv == null && fixedConn == null && connections.length > 1 && (
        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 11, color: S.textDim, display: "block", marginBottom: 4 }}>JTL-Verbindung</label>
          <select value={connId ?? ""} onChange={e => setConnId(e.target.value ? Number(e.target.value) : null)}
            style={{ ...inputStyle, width: "100%", flex: "none" }}>
            <option value="">— Verbindung wählen —</option>
            {connections.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
      )}

      {/* Hinweis: gepflegte Ausschlüsse hängen an einer anderen Verbindung.
          Sie sind dann unsichtbar UND wirkungslos – ohne diesen Hinweis merkt das
          niemand, bis in der Auswertung plötzlich wieder Paletten auftauchen. */}
      {uebertragbar && (
        <div style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "10px 12px",
          borderRadius: 6, marginBottom: 14, backgroundColor: "rgba(240,180,52,0.08)",
          border: "1px solid rgba(240,180,52,0.3)" }}>
          <ArrowRightLeft size={14} color="#f0b434" style={{ marginTop: 2, flexShrink: 0 }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 12, color: S.textBright, marginBottom: 3 }}>
              {uebertragbar.gesamt} ausgeschlossene{uebertragbar.gesamt === 1 ? "r Artikel liegt" : " Artikel liegen"}
              {" "}an {uebertragbar.quellen.length === 1
                ? <>einer anderen Verbindung (<b>{uebertragbar.quellen[0].name}</b>)</>
                : <>anderen Verbindungen ({uebertragbar.quellen.map(q => q.name).join(", ")})</>}.
            </div>
            <div style={{ fontSize: 11, color: S.textDim, lineHeight: 1.5 }}>
              Für die aktuelle WaWi gelten sie nicht – die interne Artikel-ID ist je
              Datenbank eine andere. Bei der Übernahme werden die Artikel über die
              Artikelnummer neu gesucht; was hier nicht existiert, wird gemeldet.
              Drüben bleibt alles unverändert stehen.
            </div>
          </div>
          <button onClick={uebernehmen} disabled={uebernehmend}
            style={{ display: "flex", alignItems: "center", gap: 5, padding: "6px 12px", borderRadius: 5,
              fontSize: 11, whiteSpace: "nowrap", flexShrink: 0,
              cursor: uebernehmend ? "default" : "pointer",
              backgroundColor: "rgba(240,180,52,0.14)", border: "1px solid rgba(240,180,52,0.4)",
              color: "#f0b434" }}>
            {uebernehmend
              ? <><Loader2 size={12} className="animate-spin" /> Übernehme…</>
              : <>Artikel übernehmen</>}
          </button>
        </div>
      )}

      {/* Ergebnis der Übernahme. Die nicht gefundenen Artikel stehen namentlich da:
          nur so weiß der Anwender, was er von Hand nachpflegen muss. */}
      {bericht && (
        <div style={{ padding: "10px 12px", borderRadius: 6, marginBottom: 14,
          backgroundColor: S.bgEl, border: `1px solid ${S.border}` }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom:
            bericht.nicht_gefunden?.length ? 6 : 0 }}>
            <div style={{ flex: 1, fontSize: 12, color: S.textBright }}>
              {bericht.uebernommen} übernommen
              {bericht.schon_vorhanden > 0 && `, ${bericht.schon_vorhanden} waren schon vorhanden`}
              {bericht.nicht_gefunden?.length > 0 && `, ${bericht.nicht_gefunden.length} nicht gefunden`}
            </div>
            <button onClick={() => setBericht(null)} title="Schließen"
              style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer" }}>
              <X size={14} />
            </button>
          </div>
          {bericht.nicht_gefunden?.length > 0 && (
            <div style={{ fontSize: 11, color: S.textDim, lineHeight: 1.6 }}>
              Diese Artikelnummern gibt es in der aktuellen WaWi nicht – sie bleiben
              unberücksichtigt:{" "}
              {bericht.nicht_gefunden.map(a => a.art_nr).join(", ")}
            </div>
          )}
        </div>
      )}

      {/* Suche */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <div style={{ position: "relative", flex: 1, display: "flex" }}>
          <Search size={14} color={S.textDim}
            style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)" }} />
          <input value={query} onChange={e => setQuery(e.target.value)}
            placeholder="Artikel suchen (Artikelnummer oder Name)…"
            style={{ ...inputStyle, paddingLeft: 30 }} />
          {query && (
            <button onClick={() => setQuery("")} title="Leeren"
              style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)",
                background: "none", border: "none", color: S.textDim, cursor: "pointer" }}>
              <X size={14} />
            </button>
          )}
        </div>
        {searching && <Loader2 size={16} className="animate-spin" color={S.textDim} />}
      </div>

      {/* Suchergebnisse */}
      {searchResults.length > 0 && (
        <div style={{ border: `1px solid ${S.border}`, borderRadius: 6, marginBottom: 20, maxHeight: 260, overflowY: "auto" }}>
          {searchResults.map(art => {
            const already = excludedIds.has(art.k_artikel);
            return (
              <div key={art.k_artikel}
                style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px",
                  borderBottom: `1px solid ${S.border}` }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ fontSize: 12, color: S.textBright, fontFamily: "monospace" }}>{art.art_nr}</span>
                  <span style={{ fontSize: 12, color: S.textDim, marginLeft: 8 }}>{art.name}</span>
                </div>
                <button onClick={() => addExclusion(art)} disabled={already}
                  style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 10px", borderRadius: 5,
                    fontSize: 11, cursor: already ? "default" : "pointer",
                    backgroundColor: already ? "transparent" : "rgba(110,231,183,0.12)",
                    border: `1px solid ${already ? S.border : "rgba(110,231,183,0.35)"}`,
                    color: already ? S.textDim : "#6ee7b7" }}>
                  {already ? "ausgeschlossen" : <><Plus size={12} /> Ausschließen</>}
                </button>
              </div>
            );
          })}
        </div>
      )}

      {/* Aktuelle Ausschlussliste */}
      <div style={{ fontSize: 12, fontWeight: 600, color: S.textMain, marginBottom: 8 }}>
        Ausgeschlossene Artikel ({exclusions.length})
      </div>
      {exclusions.length === 0 ? (
        <p style={{ fontSize: 12, color: S.textDim }}>Noch keine Artikel ausgeschlossen.</p>
      ) : (
        <div style={{ border: `1px solid ${S.border}`, borderRadius: 6 }}>
          {exclusions.map(e => (
            <div key={e.id}
              style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px",
                borderBottom: `1px solid ${S.border}` }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <span style={{ fontSize: 12, color: S.textBright, fontFamily: "monospace" }}>{e.art_nr || `kArtikel ${e.k_artikel}`}</span>
                <span style={{ fontSize: 12, color: S.textDim, marginLeft: 8 }}>{e.name}</span>
              </div>
              <button onClick={() => removeExclusion(e.id)} title="Entfernen"
                style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 10px", borderRadius: 5,
                  fontSize: 11, cursor: "pointer", backgroundColor: "transparent",
                  border: `1px solid ${S.border}`, color: "#e07070" }}>
                <Trash2 size={12} /> Entfernen
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
