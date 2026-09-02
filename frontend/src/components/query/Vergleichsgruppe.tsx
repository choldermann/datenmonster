import { useState, useEffect, useMemo } from "react";
import { Search, X, Users } from "lucide-react";
import api from "../../api/client";
import { S } from "../dashboard/constants";

/**
 * Auswahl der Vergleichsgruppe: die Kunden, deren Sortiment als Maßstab dient.
 *
 * Eine Auswahlliste über den ganzen Kundenstamm wäre unbedienbar (22.495), das
 * Backend liefert darum nur Kunden mit Bewegung in 24 Monaten (3.300). Gesucht
 * wird trotzdem im Browser – die Liste ist klein genug, und jede Eingabe eine
 * Serverrunde zu kosten wäre hier reine Verschwendung.
 */

const feld = {
  width: "100%", padding: "7px 10px 7px 28px", borderRadius: 6,
  backgroundColor: S.bgMain, border: `1px solid ${S.border}`,
  color: S.textMain, fontSize: 12,
};

export default function Vergleichsgruppe({ projectId, gewaehlt, onChange, hinweis }) {
  const [alle, setAlle] = useState([]);
  const [suche, setSuche] = useState("");
  const [laedt, setLaedt] = useState(true);
  const [fehler, setFehler] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const md = await api.get("/api/mandanten",
          { params: projectId ? { project_id: projectId } : {} });
        const conn = md.data?.aktiv;
        if (!conn) { setFehler("Kein Mandant gewählt."); return; }
        const { data } = await api.get("/api/lookup/options",
          { params: { connection_id: conn, kind: "kunde" } });
        setAlle(data.options || []);
      } catch (e) {
        setFehler(e.response?.data?.detail || e.message);
      } finally { setLaedt(false); }
    })();
  }, [projectId]);

  const gewaehltSet = useMemo(
    () => new Set((gewaehlt || []).map(String)), [gewaehlt]);

  // Erst ab zwei Zeichen filtern – sonst stünden 3.300 Zeilen im Fenster.
  const treffer = useMemo(() => {
    const s = suche.trim().toLowerCase();
    if (s.length < 2) return [];
    return alle.filter((o) => o.label.toLowerCase().includes(s)).slice(0, 40);
  }, [alle, suche]);

  const umschalten = (value) => {
    const v = String(value);
    onChange(gewaehltSet.has(v)
      ? (gewaehlt || []).filter((x) => String(x) !== v)
      : [...(gewaehlt || []), Number(v)]);
  };

  const beschriftung = (v) =>
    alle.find((o) => String(o.value) === String(v))?.label || `Kunde ${v}`;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
      {hinweis && (
        <p style={{ fontSize: 10.5, color: S.textDim, margin: 0, lineHeight: 1.45 }}>
          {hinweis}
        </p>
      )}

      {(gewaehlt || []).length > 0 && (
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {gewaehlt.map((v) => (
            <span key={v} style={{ display: "flex", alignItems: "center", gap: 6,
              padding: "4px 8px", borderRadius: 5, fontSize: 11.5,
              backgroundColor: "rgba(252,228,153,0.12)",
              border: "1px solid rgba(252,228,153,0.35)", color: "var(--accent)" }}>
              <Users size={11} />
              {beschriftung(v)}
              <button onClick={() => umschalten(v)} title="Entfernen"
                style={{ background: "none", border: "none", color: "var(--accent)",
                  cursor: "pointer", padding: 0, display: "flex" }}>
                <X size={11} />
              </button>
            </span>
          ))}
        </div>
      )}

      <div style={{ position: "relative", maxWidth: 420 }}>
        <Search size={13} style={{ position: "absolute", left: 9, top: 9, color: S.textDim }} />
        <input value={suche} onChange={(e) => setSuche(e.target.value)}
          placeholder={laedt ? "Kunden werden geladen…" : "Kunden suchen (ab 2 Zeichen)…"}
          disabled={laedt} style={feld} />
      </div>

      {fehler && <p style={{ fontSize: 11.5, color: "#f87171", margin: 0 }}>{fehler}</p>}

      {treffer.length > 0 && (
        <div style={{ maxHeight: 190, overflowY: "auto", maxWidth: 560,
          border: `1px solid ${S.border}`, borderRadius: 6 }}>
          {treffer.map((o) => {
            const an = gewaehltSet.has(String(o.value));
            return (
              <label key={o.value}
                style={{ display: "flex", alignItems: "center", gap: 8,
                  padding: "6px 10px", cursor: "pointer", fontSize: 11.5,
                  backgroundColor: an ? "rgba(252,228,153,0.08)" : "transparent",
                  color: an ? S.textBright : S.textMain }}>
                <input type="checkbox" checked={an} onChange={() => umschalten(o.value)}
                  style={{ accentColor: "var(--accent)" }} />
                {o.label}
              </label>
            );
          })}
        </div>
      )}

      {suche.trim().length >= 2 && treffer.length === 0 && !laedt && (
        <p style={{ fontSize: 11, color: S.textDim, margin: 0 }}>
          Nichts gefunden. Die Liste enthält Kunden mit Bewegung in den letzten
          24 Monaten.
        </p>
      )}
    </div>
  );
}
