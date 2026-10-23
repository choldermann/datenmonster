/**
 * Büro: die einfache Oberfläche für JTL-Kunden.
 *
 * Fünf Bereiche statt der Werkstatt mit ihren ETL-Begriffen. Alles hier ruft
 * vorhandene Endpunkte; die Werkstatt (/dashboard) bleibt unverändert und ist
 * für Editoren und Admins über den Knopf oben rechts erreichbar.
 * Plan: ~/.claude/plans/haendler-ansicht.md (Phase 1).
 */
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { Home, LayoutGrid, ListFilter, Mail, Settings, Wrench, LogOut } from "lucide-react";
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

  const menue = [
    { to: "/start", label: "Übersicht", icon: Home, end: true },
    { to: "/start/cockpits", label: "Cockpits", icon: LayoutGrid },
    // Eigene Auswertungen und Zustellpläne bauen nur Editoren und Admins.
    ...(portal ? [] : [
      { to: "/start/auswertung", label: "Eigene Auswertung", icon: ListFilter },
      { to: "/start/mail", label: "Per Mail", icon: Mail },
    ]),
    { to: "/start/einstellungen", label: "Einstellungen", icon: Settings },
  ];

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
          {menue.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end}
              style={({ isActive }) => ({
                display: "flex", alignItems: "center", gap: 10, padding: "10px 12px", minHeight: 42,
                borderRadius: 8, fontSize: 14, textDecoration: "none", whiteSpace: "nowrap",
                backgroundColor: isActive ? "color-mix(in srgb, var(--accent) 14%, transparent)" : "transparent",
                color: isActive ? S.accent : S.textMain, fontWeight: isActive ? 700 : 500,
              })}>
              <Icon size={16} /> {label}
            </NavLink>
          ))}
        </nav>
        <main style={{ flex: "999 1 560px", minWidth: 0, padding: "28px 32px 48px" }}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
