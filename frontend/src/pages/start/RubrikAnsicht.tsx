/**
 * Eine Rubrik im Büro: Kopf (Name, Anheften, Kopie anpassen) und darunter das
 * Cockpit mit seinen Reitern. /start/r/:rubrik = Haupteintrag,
 * /start/r/:rubrik/:formId = Kopie, Bericht oder Pflegemaske, ?reiter=<tab_id> springt in einen Reiter.
 * Plan: ~/.claude/plans/ein-cockpit-rubriken.md, Phase 1.
 */
import { useState } from "react";
import { Link, Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Star } from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import FormRunner from "../FormRunner";
import PortalRunner from "../PortalRunner";
import KopieDialog from "./KopieDialog";
import { S, knopf } from "./StartLayout";
import { useRubriken, findeRubrik, findeEintrag, ersteRubrik, rubrikPfad, ART_TEXT } from "./rubriken";
import CockpitAnsicht from "./CockpitAnsicht";

const merkKey = (formId) => `dm-reiter-${formId}`;
const gemerkt = (formId) => { try { return sessionStorage.getItem(merkKey(formId)); } catch { return null; } };
const merken = (formId, tab) => { try { sessionStorage.setItem(merkKey(formId), tab); } catch { /* egal */ } };

function untertitel(rubrik, e) {
  if (e.art === "kopie") return `Kopie von ${e.kopie_von || rubrik.haupt.name} · eigene Anpassung`;
  if (e.art === "bericht") return `Eigener Bericht · gehört zu ${rubrik.name}`;
  if (e.art === "pflege") return `Pflege · gehört zu ${rubrik.name}`;
  return e.intro || "";
}

export default function RubrikAnsicht() {
  const { rubrik: rubrikId, formId } = useParams();
  const [such] = useSearchParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const portal = !!user?.is_portal_only;
  const ktx = useRubriken();
  const [kopieVon, setKopieVon] = useState(null);

  if (ktx.gruppen === null) return <span style={{ color: S.textDim }}>Lädt…</span>;
  const rubrik = findeRubrik(ktx.gruppen, rubrikId);
  if (!rubrik) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <p style={{ margin: 0, color: S.textMain }}>Diesen Bereich gibt es hier nicht oder er ist nicht freigeschaltet.</p>
        <Link to="/start" style={{ color: S.accent }}>Zur Übersicht</Link>
      </div>
    );
  }
  const eintrag = formId ? [rubrik.haupt, ...rubrik.eintraege].find((e) => String(e.id) === formId) : rubrik.haupt;
  if (!eintrag) return <Navigate to={rubrikPfad(rubrik)} replace />;

  const istHaupt = eintrag.id === rubrik.haupt.id;
  const titel = istHaupt && eintrag.art === "cockpit" ? rubrik.name : eintrag.name;
  const text = untertitel(rubrik, eintrag);
  const angeheftet = ktx.pins.includes(eintrag.id);
  const startReiter = such.get("reiter") || gemerkt(eintrag.id);
  const kannKopie = !portal && eintrag.art !== "bericht" && eintrag.art !== "pflege";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, maxWidth: 1760 }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-start", justifyContent: "space-between", gap: "10px 20px" }}>
        <div style={{ minWidth: 0, flex: "1 1 360px", display: "flex", flexDirection: "column", gap: 3 }}>
          <h1 style={{ margin: 0, fontSize: 24, fontWeight: 800, color: S.textBright }}>
            {titel}
            {ART_TEXT[eintrag.art] && (
              <span style={{ marginLeft: 10, verticalAlign: "middle", fontSize: 12, fontWeight: 600, border: `1px solid ${S.border}`,
                borderRadius: 999, padding: "2px 8px", color: S.textDim }}>{ART_TEXT[eintrag.art]}</span>
            )}
          </h1>
          {(text || eintrag.zusatz) && (
            <p style={{ margin: 0, color: S.textDim, fontSize: 13.5, lineHeight: 1.5, maxWidth: "75ch",
              display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
              {[text, eintrag.zusatz && `Projekt ${eintrag.zusatz}`].filter(Boolean).join(" · ")}
            </p>
          )}
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <button onClick={() => ktx.pinUmschalten(eintrag.id)} aria-pressed={angeheftet}
            title={angeheftet ? "Von der Übersicht lösen" : "Das ganze Cockpit mit allen Reitern auf die Übersicht heften"}
            style={{ ...knopf.neben, ...(angeheftet ? { borderColor: S.accent, color: S.accent } : {}) }}>
            <Star size={14} fill={angeheftet ? "currentColor" : "none"} /> {angeheftet ? "Angeheftet" : "Anheften"}
          </button>
          {kannKopie && <button onClick={() => setKopieVon(eintrag)} style={knopf.neben}>Kopie anpassen</button>}
        </div>
      </div>

      {portal
        ? <PortalRunner key={eintrag.id} slug={eintrag.slug} eingebettet="seite"
            startReiter={startReiter} onReiter={(t) => merken(eintrag.id, t)} />
        : <FormRunner key={eintrag.id} formId={eintrag.id} eingebettet="seite"
            startReiter={startReiter} onReiter={(t) => merken(eintrag.id, t)} />}

      {kopieVon && (
        <KopieDialog cockpit={kopieVon} onClose={() => setKopieVon(null)}
          onFertig={(neu) => { setKopieVon(null); ktx.neuLaden(); navigate(`/start/r/${rubrik.id}/${neu.id}`); }} />
      )}
    </div>
  );
}

/** /start/cockpits → erste Rubrik (das Kartenraster gibt es nicht mehr). */
export function ZurErstenRubrik() {
  const { gruppen } = useRubriken();
  if (gruppen === null) return <span style={{ color: S.textDim }}>Lädt…</span>;
  const r = ersteRubrik(gruppen);
  if (!r) {
    return (
      <p style={{ color: S.textDim, margin: 0 }}>
        Noch keine Cockpits eingerichtet. Ihr Administrator kann sie in der Werkstatt unter
        „Cockpits &amp; Erweiterungen“ installieren.
      </p>
    );
  }
  return <Navigate to={rubrikPfad(r)} replace />;
}

/** Alte Adresse /start/cockpit/:id (Links in Mails, Übersicht, Warnungen) → passende Rubrik.
 *  Was in keiner Rubrik steht, öffnet wie bisher direkt. */
export function AlteCockpitAdresse() {
  const { id } = useParams();
  const [such] = useSearchParams();
  const { gruppen } = useRubriken();
  if (gruppen === null) return <span style={{ color: S.textDim }}>Lädt…</span>;
  const treffer = findeEintrag(gruppen, id);
  if (!treffer) return <CockpitAnsicht />;
  return <Navigate to={rubrikPfad(treffer.rubrik, treffer.eintrag, such.get("reiter"))} replace />;
}
