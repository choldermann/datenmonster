import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import api, { fehlerText } from "../../api/client";
import { useAuth } from "../../context/AuthContext";
import { useLizenz } from "../../contexts/LizenzContext";
import FormRunner from "../FormRunner";
import PortalRunner from "../PortalRunner";
import { S, knopf, karte } from "./StartLayout";
import { passendesCockpit } from "./cockpitSuche";

const BEISPIELFRAGEN = [
  "Welche Kunden haben seit drei Monaten nichts bestellt?",
  "Welche Artikel muss ich nachbestellen?",
  "Wie lief der letzte Monat im Vergleich zum Vorjahr?",
];

function gruss() {
  const h = new Date().getHours();
  return h < 11 ? "Guten Morgen" : h < 18 ? "Guten Tag" : "Guten Abend";
}

const AMPEL = { rot: "var(--err)", gelb: "var(--warn)", gruen: "var(--ok)" };

export default function Uebersicht() {
  const { user } = useAuth();
  const lizenz = useLizenz();
  const navigate = useNavigate();
  const portal = !!user?.is_portal_only;

  const [daten, setDaten] = useState(null);
  const [cockpits, setCockpits] = useState([]);
  const [fehler, setFehler] = useState(null);
  const [frage, setFrage] = useState("");
  const [alleWarnungen, setAlleWarnungen] = useState(false);
  const [richtetEin, setRichtetEin] = useState(false);

  const laden = () => {
    api.get("/api/start/uebersicht").then(({ data }) => setDaten(data))
      .catch((e) => setFehler(fehlerText(e)));
    api.get("/api/start/cockpits").then(({ data }) => setCockpits(data || [])).catch(() => {});
  };
  useEffect(laden, []);

  // Das Fragefeld führt (bis Phase 4) in die KI-Werkbank der Werkstatt.
  const fragenMoeglich = !portal && lizenz.hat("ai_build");
  const fragen = (text = frage) => {
    if (!text.trim()) return;
    navigate("/dashboard", { state: { tab: "werkbank", frage: text.trim() } });
  };

  const kennzahlenEinrichten = async () => {
    setRichtetEin(true);
    try {
      await api.post("/api/start/kennzahlen");
      laden();
    } catch (e) {
      setFehler(fehlerText(e));
    } finally {
      setRichtetEin(false);
    }
  };

  const heute = new Date().toLocaleDateString("de-DE", { weekday: "long", day: "numeric", month: "long" });
  const warnungen = daten?.warnungen || [];
  const sichtbar = alleWarnungen ? warnungen : warnungen.slice(0, 5);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28, maxWidth: 1400 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <h1 style={{ margin: 0, fontSize: 28, fontWeight: 800, color: S.textBright }}>{gruss()}</h1>
        <p style={{ margin: 0, color: S.textDim }}>
          {heute}
          {daten && (warnungen.length
            ? ` · ${warnungen.length} ${warnungen.length === 1 ? "Punkt braucht" : "Punkte brauchen"} Ihre Aufmerksamkeit.`
            : " · Keine offenen Warnungen.")}
        </p>
      </div>

      {fehler && <p style={{ color: "var(--err)", margin: 0 }}>{fehler}</p>}

      {fragenMoeglich && (
        <section aria-label="Frage stellen" style={{ ...karte, padding: 20, display: "flex", flexDirection: "column", gap: 12 }}>
          <label htmlFor="start-frage" style={{ fontWeight: 600, fontSize: 16, color: S.textBright }}>
            Was möchten Sie wissen?
          </label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
            <input id="start-frage" value={frage} onChange={(e) => setFrage(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") fragen(); }}
              placeholder="z. B. Welche Kunden haben seit drei Monaten nichts bestellt?"
              style={{ flex: "1 1 320px", minWidth: 0, minHeight: 44, padding: "10px 14px", borderRadius: 8,
                border: `1px solid ${S.border}`, backgroundColor: S.bgMain, color: S.textMain, fontSize: 14 }} />
            <button onClick={() => fragen()} style={knopf.haupt}>Fragen</button>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {BEISPIELFRAGEN.map((b) => (
              <button key={b} onClick={() => fragen(b)}
                style={{ ...knopf.neben, minHeight: 32, padding: "4px 12px", borderRadius: 999, fontSize: 12.5, color: S.textDim }}>
                {b}
              </button>
            ))}
          </div>
        </section>
      )}

      {daten?.kennzahlen && (
        <section aria-label="Kennzahlen">
          {portal
            ? <PortalRunner slug={daten.kennzahlen.slug} eingebettet="inhalt" />
            : <FormRunner formId={daten.kennzahlen.id} eingebettet="inhalt" />}
        </section>
      )}
      {daten?.kennzahlen_moeglich && (
        <section style={{ ...karte, padding: 18, display: "flex", flexWrap: "wrap", alignItems: "center", gap: 14 }}>
          <div style={{ flex: "1 1 320px", minWidth: 0 }}>
            <div style={{ fontWeight: 600, color: S.textBright }}>Kennzahlen auf der Übersicht</div>
            <div style={{ fontSize: 13, color: S.textDim }}>
              Umsatz, Rohertrag, Marge und Kundenzahl aus dem Geschäftsführer-Cockpit, hier oben auf einen Blick.
            </div>
          </div>
          <button onClick={kennzahlenEinrichten} disabled={richtetEin} style={knopf.haupt}>
            {richtetEin && <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} />}
            Kennzahlen einrichten
          </button>
        </section>
      )}

      <div style={{ display: "flex", flexWrap: "wrap", gap: 24, alignItems: "flex-start" }}>
        <section aria-label="Heute zu erledigen" style={{ flex: "3 1 380px", minWidth: 0, display: "flex", flexDirection: "column", gap: 10 }}>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: S.textBright }}>Heute zu erledigen</h2>
          {!daten && <span style={{ color: S.textDim, fontSize: 13 }}>Lädt…</span>}
          {daten && warnungen.length === 0 && (
            <span style={{ color: S.textDim, fontSize: 13 }}>Der letzte Prüflauf hat nichts gefunden.</span>
          )}
          {sichtbar.map((w, i) => {
            const ziel = passendesCockpit(w, cockpits);
            return (
              <div key={`${w.project_id}-${w.rule_key}-${i}`} style={{ ...karte, borderRadius: 10, padding: "12px 14px",
                display: "flex", gap: 12, alignItems: "flex-start" }}>
                <span style={{ width: 10, height: 10, borderRadius: "50%", marginTop: 6, flex: "none",
                  backgroundColor: AMPEL[w.ampel] || "var(--warn)" }} />
                <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 2 }}>
                  <span style={{ fontWeight: 600, color: S.textBright }}>{w.titel}</span>
                  <span style={{ fontSize: 13, color: S.textDim }}>
                    {w.untertitel}{w.projekt ? ` · ${w.projekt}` : ""}
                  </span>
                </div>
                {ziel && (
                  <button onClick={() => navigate(`/start/cockpit/${ziel.id}`)}
                    style={{ background: "none", border: "none", color: S.accent, fontWeight: 600, cursor: "pointer",
                      padding: "6px 8px", minHeight: 36, whiteSpace: "nowrap" }}>
                    Ansehen
                  </button>
                )}
              </div>
            );
          })}
          {warnungen.length > 5 && (
            <button onClick={() => setAlleWarnungen((v) => !v)} style={{ ...knopf.neben, alignSelf: "flex-start" }}>
              {alleWarnungen ? "Weniger zeigen" : `Alle ${warnungen.length} zeigen`}
            </button>
          )}
        </section>

        <section aria-label="Meine Cockpits" style={{ flex: "2 1 280px", minWidth: 0, display: "flex", flexDirection: "column", gap: 10 }}>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: S.textBright }}>Meine Cockpits</h2>
          {daten && !(daten.angeheftet || []).length && (
            <p style={{ margin: 0, fontSize: 13, color: S.textDim, lineHeight: 1.5 }}>
              Cockpits, die Sie oft brauchen, heften Sie unter „Cockpits“ mit dem Stern an.
              Sie erscheinen dann hier.
            </p>
          )}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 8 }}>
            {(daten?.angeheftet || []).map((c) => (
              <button key={c.id} onClick={() => navigate(`/start/cockpit/${c.id}`)}
                style={{ ...karte, borderRadius: 10, padding: 12, minHeight: 60, textAlign: "left", cursor: "pointer",
                  color: S.textMain, display: "flex", flexDirection: "column", gap: 2 }}>
                <span style={{ fontWeight: 600, color: S.textBright }}>{c.name}</span>
                {c.zusatz && <span style={{ fontSize: 12, color: S.textDim }}>{c.zusatz}</span>}
              </button>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
