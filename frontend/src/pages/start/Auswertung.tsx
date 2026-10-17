import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Filter, LayoutGrid, Lock } from "lucide-react";
import api, { fehlerText } from "../../api/client";
import { useLizenz } from "../../contexts/LizenzContext";
import ReportBuilder from "../../components/forms/ReportBuilder";
import QueryBuilder from "../../components/query/QueryBuilder";
import { S, knopf, karte, Seitenkopf } from "./StartLayout";
import FertigeFragen from "./FertigeFragen";

/** Eigene Auswertung (Phase 1): Einstieg in Report-Baukasten und Abfrage-Generator
 *  ohne Umweg über die Werkstatt, dazu die selbst gebauten Berichte.
 *  Fertige Fragen und der Satzbaukasten folgen in Phase 3/4. */
export default function Auswertung() {
  const navigate = useNavigate();
  const lizenz = useLizenz();
  const [cockpits, setCockpits] = useState([]);
  const [fehler, setFehler] = useState(null);
  const [offen, setOffen] = useState(null);   // "bericht" | "abfrage"

  const laden = () => api.get("/api/start/cockpits").then(({ data }) => setCockpits(data || []))
    .catch((e) => setFehler(fehlerText(e)));
  useEffect(() => { laden(); }, []);

  // Die Händler-Ansicht kennt keine Projekte. Gebaut wird dort, wo die meisten
  // Cockpits liegen – bei einer Einrichtung aus dem Assistenten das einzige Projekt.
  const zaehlung = {};
  for (const c of cockpits) if (c.project_id != null) zaehlung[c.project_id] = (zaehlung[c.project_id] || 0) + 1;
  const projektId = Object.keys(zaehlung).sort((a, b) => zaehlung[b] - zaehlung[a])[0];
  const projectId = projektId != null ? Number(projektId) : null;

  const gesperrt = lizenz.sperrgrund("query_build");
  const berichte = cockpits.filter((c) => c.art === "bericht");

  const Kachel = ({ icon: Icon, titel, text, onClick }) => (
    <button onClick={onClick} disabled={!!gesperrt} title={gesperrt}
      style={{ ...karte, padding: 18, textAlign: "left", cursor: gesperrt ? "not-allowed" : "pointer",
        opacity: gesperrt ? 0.55 : 1, color: S.textMain, display: "flex", flexDirection: "column", gap: 8, minHeight: 120 }}>
      <span style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 700, fontSize: 16, color: S.textBright }}>
        <Icon size={18} style={{ color: S.accent }} /> {titel}
        {gesperrt && <Lock size={13} style={{ color: S.textDim }} />}
      </span>
      <span style={{ fontSize: 13.5, color: S.textDim, lineHeight: 1.5 }}>{text}</span>
    </button>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22, maxWidth: 1400 }}>
      <Seitenkopf titel="Eigene Auswertung"
        text="Fertige Fragen an Ihre Wawi mit einem Klick – oder eine Liste nach eigenen Bedingungen und Berichte aus mehreren Cockpits." />
      {fehler && <p style={{ color: "var(--err)", margin: 0 }}>{fehler}</p>}

      <FertigeFragen />

      <h2 style={{ margin: "8px 0 0", fontSize: 18, fontWeight: 700, color: S.textBright }}>Selbst zusammenstellen</h2>
      {gesperrt && <p style={{ margin: 0, fontSize: 13, color: S.textDim }}>{gesperrt}</p>}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 14 }}>
        <Kachel icon={Filter} titel="Eigene Liste"
          text="Kunden, Aufträge oder Rechnungen nach Ihren Bedingungen, z. B. „Kunden ohne Rechnung seit 90 Tagen“."
          onClick={() => setOffen("abfrage")} />
        <Kachel icon={LayoutGrid} titel="Bericht zusammenstellen"
          text="Kacheln und Tabellen aus Ihren Cockpits auf einer Seite – auf Wunsch jede Woche per Mail."
          onClick={() => setOffen("bericht")} />
      </div>

      <section style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: S.textBright }}>Ihre Berichte</h2>
        {berichte.length === 0 && (
          <span style={{ fontSize: 13, color: S.textDim }}>Noch keine eigenen Berichte.</span>
        )}
        {berichte.map((b) => (
          <div key={b.id} style={{ ...karte, borderRadius: 10, padding: "12px 14px", display: "flex",
            flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
            <span style={{ fontWeight: 600, color: S.textBright }}>{b.name}</span>
            <button onClick={() => navigate(`/start/cockpit/${b.id}`)} style={knopf.neben}>Öffnen</button>
          </div>
        ))}
      </section>

      {offen === "abfrage" && <QueryBuilder projectId={projectId} onClose={() => { setOffen(null); laden(); }} />}
      {offen === "bericht" && (
        <ReportBuilder projectId={projectId} onClose={() => setOffen(null)}
          onCreated={(neu) => { setOffen(null); if (neu?.id) navigate(`/start/cockpit/${neu.id}`); else laden(); }} />
      )}
    </div>
  );
}
