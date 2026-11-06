/**
 * Büro: die einfache Oberfläche für JTL-Kunden.
 *
 * Fünf Bereiche statt der Werkstatt mit ihren ETL-Begriffen. Alles hier ruft
 * vorhandene Endpunkte; die Werkstatt (/dashboard) bleibt unverändert und ist
 * für Editoren und Admins über den Knopf oben rechts erreichbar.
 * Plan: ~/.claude/plans/haendler-ansicht.md (Phase 1).
 *
 * Seit 06.11.2026 stehen die Cockpits als Rubriken direkt im Menü (ein Cockpit,
 * links die Bereiche). Plan: ~/.claude/plans/ein-cockpit-rubriken.md.
 */
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Home, ListFilter, Mail, Settings, Wrench, LogOut, Star } from "lucide-react";
import { useRubrikenLaden, rubrikIcon, rubrikPfad, ART_TEXT } from "./rubriken";
import { useAuth } from "../../context/AuthContext";
import { ThemeUmschalter, KiCredits } from "../../components/portal/PortalKopfzeile";

export const S = {
  bgMain: "var(--bg-main)", bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)",
  border: "var(--border)", textMain: "var(--text-main)", textBright: "var(--text-bright)",
  textDim: "var(--text-dim)", accent: "var(--accent)", accentFg: "var(--accent-fg)",
};

/** Knopf-Stile des Büros: einer betont, einer zurückhaltend. */
export const knopf = {
  haupt: {
    display: "inline-flex", alignItems: "center", gap: 6, padding: "8px 16px", minHeight: 38,
    borderRadius: 8, border: "none", backgroundColor: S.accent, color: S.accentFg,
    fontWeight: 700, fontSize: 13, cursor: "pointer",
  },
  neben: {
    display: "inline-flex", alignItems: "center", gap: 6, padding: "8px 14px", minHeight: 38,
    borderRadius: 8, border: `1px solid ${S.border}`, backgroundColor: "transparent",
    color: S.textMain, fontSize: 13, cursor: "pointer",
  },
};

export const karte = {
  backgroundColor: S.bgCard, border: `1px solid ${S.border}`, borderRadius: 12,
};

export function Seitenkopf({ titel, text }: { titel: string; text?: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800, color: S.textBright }}>{titel}</h1>
      {text && <p style={{ margin: 0, color: S.textDim, fontSize: 14, lineHeight: 1.5 }}>{text}</p>}
    </div>
  );
}

export default function StartLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const portal = !!user?.is_portal_only;

  const rubriken = useRubrikenLaden();
  const ort = useLocation();

  // Eigene Auswertungen und Zustellpläne bauen nur Editoren und Admins.
  const menueUnten = [
    ...(portal ? [] : [
      { to: "/start/auswertung", label: "Eigene Auswertung", icon: ListFilter },
      { to: "/start/mail", label: "Per Mail", icon: Mail },
    ]),
    { to: "/start/einstellungen", label: "Einstellungen", icon: Settings },
  ];

  const punkt = (aktiv, eingerueckt = false) => ({
    display: "flex", alignItems: "center", gap: 10, textDecoration: "none", borderRadius: 8,
    padding: eingerueckt ? "5px 12px 5px 38px" : "8px 12px", minHeight: eingerueckt ? 30 : 38,
    fontSize: eingerueckt ? 13 : 14, lineHeight: 1.3,
    // Ohne Hintergrund, wenn nicht aktiv: den Hover setzt .start-menue-punkt in index.css.
    ...(aktiv ? { backgroundColor: "color-mix(in srgb, var(--accent) 14%, transparent)" } : {}),
    color: aktiv ? S.accent : eingerueckt ? S.textDim : S.textMain, fontWeight: aktiv ? 700 : 500,
  });
  const gruppenKopf = { fontSize: 11, fontWeight: 700, letterSpacing: ".08em", textTransform: "uppercase" as const,
    color: S.textDim, padding: "14px 12px 4px" };
  const pfad = ort.pathname;

  return (
    <div style={{ minHeight: "100vh", backgroundColor: S.bgMain, color: S.textMain, display: "flex", flexDirection: "column" }}>
      <header style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between",
        gap: 12, padding: "12px 24px", borderBottom: `1px solid ${S.border}`, backgroundColor: S.bgCard }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <img src="/datenmonster.svg" alt="" style={{ width: 32, height: 32, borderRadius: 6 }} />
          <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.2 }}>
            <span style={{ fontWeight: 700, fontSize: 16, color: S.textBright }}>Datenmonster</span>
            <span style={{ fontSize: 12, color: S.textDim }}>Angemeldet als {user?.username}</span>
          </div>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12 }}>
          <KiCredits />
          <ThemeUmschalter />
          {!portal && (
            <button onClick={() => navigate("/dashboard")} style={knopf.neben}
              title="Die vollständige Oberfläche mit Verbindungen, Mappings, Abläufen und Vorlagen-Bau">
              <Wrench size={14} /> Werkstatt
            </button>
          )}
          <button onClick={() => { logout(); navigate("/login"); }}
            style={{ ...knopf.neben, border: "none", color: S.textDim }}>
            <LogOut size={14} /> Abmelden
          </button>
        </div>
      </header>

      <div style={{ display: "flex", flexWrap: "wrap", flex: 1 }}>
        <nav aria-label="Hauptmenü" style={{ flex: "1 1 200px", maxWidth: 240, padding: "20px 12px",
          borderRight: `1px solid ${S.border}`, display: "flex", flexDirection: "column", gap: 4 }}>
          <NavLink to="/start" end className="start-menue-punkt" style={({ isActive }) => punkt(isActive)}>
            <Home size={16} /> Übersicht
          </NavLink>
          {rubriken.gruppen === null && <span style={{ ...gruppenKopf, textTransform: "none" }}>Lädt…</span>}
          {(rubriken.gruppen || []).map((g) => (
            <div key={g.id} role="group" aria-label={g.name} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <span style={gruppenKopf}>{g.name}</span>
              {g.rubriken.map((r) => {
                const Icon = rubrikIcon(r.icon);
                const basis = `/start/r/${r.id}`;
                const hauptAktiv = pfad === basis || pfad === `${basis}/${r.haupt.id}`;
                return (
                  <div key={r.id} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    <Link to={rubrikPfad(r)} aria-current={hauptAktiv ? "page" : undefined}
                      className="start-menue-punkt" style={punkt(hauptAktiv)}>
                      <Icon size={16} style={{ flex: "none" }} />
                      <span style={{ flex: 1, minWidth: 0 }}>{r.name}</span>
                      {rubriken.pins.includes(r.haupt.id) && (
                        <Star size={12} fill="currentColor" aria-label="angeheftet" style={{ color: S.accent, flex: "none" }} />
                      )}
                    </Link>
                    {r.eintraege.map((e) => {
                      const aktiv = pfad === `${basis}/${e.id}`;
                      return (
                        <Link key={e.id} to={rubrikPfad(r, e)} aria-current={aktiv ? "page" : undefined}
                          className="start-menue-punkt" style={punkt(aktiv, true)} title={e.zusatz ? `${e.name} · ${e.zusatz}` : e.name}>
                          <span style={{ flex: 1, minWidth: 0 }}>
                            {e.name}
                            {e.zusatz && <span style={{ display: "block", fontSize: 11.5, color: S.textDim }}>{e.zusatz}</span>}
                          </span>
                          {ART_TEXT[e.art] && (
                            <span style={{ flex: "none", fontSize: 10.5, border: `1px solid ${S.border}`, borderRadius: 999,
                              padding: "0 6px", color: S.textDim }}>{ART_TEXT[e.art]}</span>
                          )}
                        </Link>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          ))}
          {rubriken.fehler && <span style={{ fontSize: 12, color: "var(--err)", padding: "6px 12px" }}>{rubriken.fehler}</span>}
          <div style={{ height: 1, backgroundColor: S.border, margin: "12px 6px" }} />
          {menueUnten.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} className="start-menue-punkt" style={({ isActive }) => punkt(isActive)}>
              <Icon size={16} /> {label}
            </NavLink>
          ))}
        </nav>
        <main style={{ flex: "999 1 560px", minWidth: 0, padding: "28px 32px 48px" }}>
          <Outlet context={rubriken} />
        </main>
      </div>
    </div>
  );
}
