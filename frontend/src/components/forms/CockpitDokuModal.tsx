import { useEffect, useState } from "react";
import { BookOpen, Database, Layers, Loader2, SlidersHorizontal, X } from "lucide-react";
import api from "../../api/client";
import { S } from "../mapping/constants";

/**
 * "Was zeigt dieses Cockpit?" – Erklärseite für Anwender.
 *
 * Der Inhalt kommt aus GET /api/forms/{id}/doku: Einleitung und Hinweise sind im
 * Template handgeschrieben, Quelltabellen/Reiter/Widgets werden serverseitig aus
 * dem Formular abgeleitet und sind damit immer auf Stand.
 */
export default function CockpitDokuModal({ formId, onClose }) {
  const [doku, setDoku] = useState(null);
  const [fehler, setFehler] = useState(null);

  useEffect(() => {
    let abgemeldet = false;
    api.get(`/api/forms/${formId}/doku`)
      .then(({ data }) => { if (!abgemeldet) setDoku(data); })
      .catch((e) => { if (!abgemeldet) setFehler(e?.response?.data?.detail || e.message); });
    return () => { abgemeldet = true; };
  }, [formId]);

  useEffect(() => {
    const aufEsc = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", aufEsc);
    return () => window.removeEventListener("keydown", aufEsc);
  }, [onClose]);

  return (
    <div onClick={onClose}
      style={{ position: "fixed", inset: 0, zIndex: 1000, backgroundColor: "rgba(0,0,0,0.55)",
        display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
      <div onClick={(e) => e.stopPropagation()}
        style={{ width: "min(760px, 94vw)", maxHeight: "88vh", backgroundColor: S.bgCard,
          border: `1px solid ${S.border}`, borderRadius: 12, display: "flex", flexDirection: "column",
          overflow: "hidden", boxShadow: "0 20px 60px rgba(0,0,0,0.5)" }}>

        {/* Kopf */}
        <div style={{ padding: "14px 18px", borderBottom: `1px solid ${S.border}`,
          display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
          <BookOpen size={15} style={{ color: S.accent, flexShrink: 0 }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <p style={{ fontSize: 14, fontWeight: 700, color: S.textBright, margin: 0 }}>
              Was zeigt dieses Cockpit?
            </p>
            <p style={{ fontSize: 11, color: S.textDim, margin: "2px 0 0" }}>
              {doku?.name || "…"}
            </p>
          </div>
          <button onClick={onClose} title="Schließen"
            style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer",
              display: "flex", padding: 2 }}>
            <X size={16} />
          </button>
        </div>

        {/* Inhalt */}
        <div style={{ padding: "18px", overflowY: "auto", display: "flex",
          flexDirection: "column", gap: 20 }}>

          {fehler && (
            <p style={{ fontSize: 12, color: "#e07070", margin: 0 }}>
              Erklärung konnte nicht geladen werden: {fehler}
            </p>
          )}

          {!doku && !fehler && (
            <p style={{ fontSize: 12, color: S.textDim, display: "flex", alignItems: "center", gap: 8, margin: 0 }}>
              <Loader2 size={13} style={{ animation: "spin 1s linear infinite" }} /> Lade Erklärung…
            </p>
          )}

          {doku && (
            <>
              {/* Wozu – handgeschrieben */}
              {doku.intro && (
                <Abschnitt titel="Wozu dieses Cockpit">
                  <p style={{ fontSize: 13, lineHeight: 1.65, color: S.textMain, margin: 0 }}>
                    {doku.intro}
                  </p>
                </Abschnitt>
              )}

              {doku.hinweise?.length > 0 && (
                <Abschnitt titel="Gut zu wissen">
                  <ul style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 6 }}>
                    {doku.hinweise.map((h, i) => (
                      <li key={i} style={{ fontSize: 12, lineHeight: 1.6, color: S.textMain }}>{h}</li>
                    ))}
                  </ul>
                </Abschnitt>
              )}

              {/* Datenquellen – abgeleitet */}
              <Abschnitt titel="Woher die Daten kommen" Icon={Database}>
                <p style={{ fontSize: 12, color: S.textDim, margin: "0 0 8px" }}>
                  {doku.quellen.auswertungen} Auswertung{doku.quellen.auswertungen === 1 ? "" : "en"} auf
                  {" "}{doku.quellen.tabellen.length} Tabelle{doku.quellen.tabellen.length === 1 ? "" : "n"} der JTL-Wawi.
                  Es wird ausschließlich gelesen.
                </p>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                  {doku.quellen.tabellen.map((t) => (
                    <code key={t} style={{ fontSize: 10.5, fontFamily: "monospace", padding: "2px 7px",
                      borderRadius: 4, backgroundColor: S.bgEl, border: `1px solid ${S.border}`,
                      color: S.textMain }}>{t}</code>
                  ))}
                </div>
              </Abschnitt>

              {/* Reiter – abgeleitet */}
              {doku.reiter.length > 0 && (
                <Abschnitt titel="Was Sie sehen" Icon={Layers}>
                  <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    {doku.reiter.map((r, i) => (
                      <div key={i} style={{ paddingLeft: 10, borderLeft: `2px solid ${S.border}` }}>
                        <p style={{ fontSize: 12.5, fontWeight: 600, color: S.textBright, margin: 0 }}>
                          {r.label}
                        </p>
                        {r.inhalt.length > 0 && (
                          <p style={{ fontSize: 11, color: S.textDim, margin: "2px 0 0" }}>
                            {r.inhalt.join(" · ")}
                          </p>
                        )}
                        {r.hinweise.map((h, j) => (
                          <p key={j} style={{ fontSize: 11.5, lineHeight: 1.55, color: S.textMain,
                            margin: "6px 0 0", opacity: 0.85 }}>
                            ⓘ {h}
                          </p>
                        ))}
                      </div>
                    ))}
                  </div>
                </Abschnitt>
              )}

              {/* Filter – abgeleitet */}
              {doku.filter.length > 0 && (
                <Abschnitt titel="Womit Sie filtern können" Icon={SlidersHorizontal}>
                  <p style={{ fontSize: 12, color: S.textMain, margin: 0, lineHeight: 1.6 }}>
                    {doku.filter.map((f) => f.label).filter(Boolean).join(" · ")}
                  </p>
                </Abschnitt>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function Abschnitt({ titel, Icon, children }) {
  return (
    <div>
      <p style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.09em",
        color: S.accent, margin: "0 0 8px", display: "flex", alignItems: "center", gap: 6 }}>
        {Icon && <Icon size={11} />} {titel}
      </p>
      {children}
    </div>
  );
}
