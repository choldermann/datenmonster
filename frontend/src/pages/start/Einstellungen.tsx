import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { fehlerText } from "../../api/client";
import { useAuth } from "../../context/AuthContext";
import { useLizenz } from "../../contexts/LizenzContext";
import { PasswortKnopf } from "../../components/portal/PortalKopfzeile";
import { S, knopf, karte, Seitenkopf } from "./StartLayout";

const block = { ...karte, padding: 18, display: "flex", flexDirection: "column", gap: 12, minWidth: 0 };
const h2 = { margin: 0, fontSize: 17, fontWeight: 700, color: S.textBright };

export default function Einstellungen() {
  const { user } = useAuth();
  const lizenz = useLizenz();
  const navigate = useNavigate();
  const portal = !!user?.is_portal_only;

  const [status, setStatus] = useState(null);
  const [werkstattStart, setWerkstattStart] = useState(false);
  const [fehler, setFehler] = useState(null);

  useEffect(() => {
    if (portal) return;
    api.get("/api/start/status").then(({ data }) => setStatus(data)).catch((e) => setFehler(fehlerText(e)));
    api.get("/api/start/einstellungen").then(({ data }) => setWerkstattStart(!!data?.werkstatt_start)).catch(() => {});
  }, [portal]);

  const umschalten = async (wert) => {
    setWerkstattStart(wert);
    try {
      await api.put("/api/start/einstellungen", { werkstatt_start: wert });
    } catch (e) {
      setFehler(fehlerText(e));
    }
  };

  const pro = lizenz.hat("unlimited");
  const jtl = (status?.verbindungen || []).filter((v) => v.jtl_version);
  const andere = (status?.verbindungen || []).filter((v) => !v.jtl_version);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20, maxWidth: 1100 }}>
      <Seitenkopf titel="Einstellungen" />
      {fehler && <p style={{ color: "var(--err)", margin: 0 }}>{fehler}</p>}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 14 }}>

        {!portal && (
          <section style={block}>
            <h2 style={h2}>Verbindung zur Wawi</h2>
            {status === null && (
              <span style={{ color: S.textDim, fontSize: 13 }}>Prüfe Verbindungen… das kann beim ersten Mal einige Sekunden dauern.</span>
            )}
            {status && jtl.length === 0 && (
              <span style={{ color: S.textDim, fontSize: 13 }}>Keine erreichbare JTL-Wawi gefunden.</span>
            )}
            {jtl.map((v) => (
              <div key={v.id} style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: 14 }}>
                <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ width: 9, height: 9, borderRadius: "50%", backgroundColor: "var(--ok)" }} />
                  <span style={{ fontWeight: 600, color: S.textBright }}>{v.name}</span>
                </span>
                <span style={{ color: S.textDim, fontSize: 13, paddingLeft: 17 }}>
                  JTL-Wawi {v.jtl_version} · {v.server}{v.datenbank ? ` / ${v.datenbank}` : ""}
                </span>
              </div>
            ))}
            {andere.length > 0 && (
              <span title={andere.map((v) => v.name).join(", ")} style={{ color: S.textDim, fontSize: 12.5 }}>
                {andere.length} weitere {andere.length === 1 ? "Verbindung ist" : "Verbindungen sind"} nicht
                erreichbar oder keine JTL-Datenbank.
              </span>
            )}
          </section>
        )}

        <section style={block}>
          <h2 style={h2}>Ihr Zugang</h2>
          <span style={{ fontSize: 14 }}>Angemeldet als <b>{user?.username}</b></span>
          <div><PasswortKnopf /></div>
          {!portal && (
            <label style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 14, cursor: "pointer" }}>
              <input type="checkbox" checked={werkstattStart} onChange={(e) => umschalten(e.target.checked)}
                style={{ width: 18, height: 18 }} />
              Nach dem Anmelden direkt in der Werkstatt starten
            </label>
          )}
        </section>

        {!portal && (
          <section style={block}>
            <h2 style={h2}>Lizenz</h2>
            <span style={{ fontSize: 14 }}>Datenmonster <b>{pro ? "Pro" : "Frei"}</b></span>
            <span style={{ fontSize: 13, color: S.textDim, lineHeight: 1.5 }}>
              {pro
                ? "Alle Funktionen der Werkstatt sind freigeschaltet."
                : "Gekaufte Cockpits laufen ohne Grenze. Eigene Datenquellen, Abläufe und Vorlagen baut man mit Pro."}
            </span>
            <button onClick={() => navigate("/dashboard", { state: { tab: "license" } })}
              style={{ ...knopf.neben, alignSelf: "flex-start" }}>
              Lizenz verwalten
            </button>
          </section>
        )}
      </div>
    </div>
  );
}
