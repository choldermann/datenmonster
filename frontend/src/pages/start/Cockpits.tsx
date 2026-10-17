import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Star, Search } from "lucide-react";
import api, { fehlerText } from "../../api/client";
import { GesperrtMarke } from "../../components/VorlageGesperrt";
import { S, knopf, karte, Seitenkopf } from "./StartLayout";
import { useAuth } from "../../context/AuthContext";
import KopieDialog from "./KopieDialog";

function Karte({ c, angeheftet, onPin, onOeffnen, onKopie }) {
  return (
    <article style={{ ...karte, padding: 18, display: "flex", flexDirection: "column", gap: 10, minWidth: 0 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
        <div style={{ minWidth: 0 }}>
          <h3 style={{ margin: 0, fontSize: 16, color: S.textBright }}>{c.name}</h3>
          {(c.zusatz || c.kopie_von) && (
            <span style={{ fontSize: 12, color: S.textDim }}>
              {[c.kopie_von && `Kopie von ${c.kopie_von}`, c.zusatz].filter(Boolean).join(" · ")}
            </span>
          )}
        </div>
        <button onClick={onPin} aria-pressed={angeheftet}
          aria-label={angeheftet ? `${c.name} von der Übersicht lösen` : `${c.name} auf der Übersicht anheften`}
          title={angeheftet ? "Von der Übersicht lösen" : "Auf der Übersicht anheften"}
          style={{ background: "none", border: "none", cursor: "pointer", padding: 6, minWidth: 36, minHeight: 36,
            color: angeheftet ? S.accent : S.textDim }}>
          <Star size={18} fill={angeheftet ? "currentColor" : "none"} />
        </button>
      </div>
      {c.gesperrt && <GesperrtMarke sperre={c.gesperrt} />}
      <div style={{ flex: 1 }}>
        <p style={{ margin: 0, fontSize: 13.5, color: S.textDim, lineHeight: 1.5,
          display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
          {c.intro || (c.art === "bericht" ? "Selbst zusammengestellter Bericht." : "")}
        </p>
      </div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <span style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button onClick={onOeffnen} style={knopf.haupt}>Öffnen</button>
          {onKopie && <button onClick={onKopie} style={knopf.neben}>Kopie anpassen</button>}
        </span>
        {c.reiter > 1 && (
          <span style={{ fontSize: 12, color: S.textDim, fontFamily: "var(--font-mono)" }}>{c.reiter} Reiter</span>
        )}
      </div>
    </article>
  );
}

export default function Cockpits() {
  const navigate = useNavigate();
  const [liste, setListe] = useState(null);
  const [pins, setPins] = useState([]);
  const [suche, setSuche] = useState("");
  const [fehler, setFehler] = useState(null);
  const [kopieVon, setKopieVon] = useState(null);
  const { user } = useAuth();
  const portal = !!user?.is_portal_only;

  useEffect(() => {
    api.get("/api/start/cockpits").then(({ data }) => setListe(data || []))
      .catch((e) => setFehler(fehlerText(e)));
    api.get("/api/start/einstellungen").then(({ data }) => setPins(data?.pins || [])).catch(() => {});
  }, []);

  const umschalten = async (id) => {
    const neu = pins.includes(id) ? pins.filter((p) => p !== id) : [...pins, id];
    setPins(neu);
    try {
      const { data } = await api.put("/api/start/einstellungen", { pins: neu });
      setPins(data?.pins || []);
    } catch (e) {
      setFehler(fehlerText(e));
    }
  };

  const gefiltert = useMemo(() => {
    const q = suche.trim().toLowerCase();
    return (liste || []).filter((c) => !q || `${c.name} ${c.intro} ${c.zusatz || ""}`.toLowerCase().includes(q));
  }, [liste, suche]);
  const cockpits = gefiltert.filter((c) => c.art === "cockpit");
  const berichte = gefiltert.filter((c) => c.art === "bericht");

  const raster = { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 14 };
  const karteFuer = (c) => (
    <Karte key={c.id} c={c} angeheftet={pins.includes(c.id)}
      onPin={() => umschalten(c.id)} onOeffnen={() => navigate(`/start/cockpit/${c.id}`)}
      onKopie={portal ? null : () => setKopieVon(c)} />
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22, maxWidth: 1400 }}>
      <Seitenkopf titel="Cockpits" text="Fertige Auswertungen für Ihre Wawi. Mit dem Stern heften Sie ein Cockpit auf die Übersicht." />
      {fehler && <p style={{ color: "var(--err)", margin: 0 }}>{fehler}</p>}
      {(liste || []).length > 8 && (
        <div style={{ position: "relative", maxWidth: 420 }}>
          <Search size={15} style={{ position: "absolute", left: 12, top: 13, color: S.textDim }} />
          <input value={suche} onChange={(e) => setSuche(e.target.value)} placeholder="Cockpit suchen"
            aria-label="Cockpit suchen"
            style={{ width: "100%", minHeight: 42, padding: "8px 12px 8px 34px", borderRadius: 8,
              border: `1px solid ${S.border}`, backgroundColor: S.bgCard, color: S.textMain, fontSize: 14 }} />
        </div>
      )}
      {liste === null && !fehler && <span style={{ color: S.textDim }}>Lädt…</span>}
      {liste && liste.length === 0 && (
        <div style={{ ...karte, padding: 20, color: S.textDim }}>
          Noch keine Cockpits eingerichtet. Ihr Administrator kann sie in der Werkstatt unter
          „Cockpits &amp; Erweiterungen“ installieren.
        </div>
      )}
      {cockpits.length > 0 && <div style={raster}>{cockpits.map(karteFuer)}</div>}
      {berichte.length > 0 && (
        <section style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: S.textBright }}>Eigene Berichte</h2>
          <div style={raster}>{berichte.map(karteFuer)}</div>
        </section>
      )}
      {kopieVon && (
        <KopieDialog cockpit={kopieVon} onClose={() => setKopieVon(null)}
          onFertig={(neu) => { setKopieVon(null); navigate(`/start/cockpit/${neu.id}`); }} />
      )}
    </div>
  );
}
