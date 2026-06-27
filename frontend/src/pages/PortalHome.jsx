import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Play, LogOut, LayoutGrid } from "lucide-react";
import api from "../api/client";
import { useAuth } from "../context/AuthContext";

const S = {
  bgMain: "var(--bg-main)", bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)",
  border: "var(--border)", textMain: "var(--text-main)", textBright: "var(--text-bright)",
  textDim: "var(--text-dim)", accent: "var(--accent)",
};

export default function PortalHome() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [forms, setForms] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/api/portal/forms")
      .then(({ data }) => setForms(data || []))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const handleLogout = () => { logout(); navigate("/login"); };

  return (
    <div style={{ minHeight: "100vh", backgroundColor: S.bgMain, color: S.textMain }}>
      {/* Header */}
      <header style={{ borderBottom: `1px solid ${S.border}`, backgroundColor: S.bgCard }}>
        <div style={{ maxWidth: 1100, margin: "0 auto", padding: "14px 24px",
          display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <LayoutGrid size={20} style={{ color: S.accent }} />
            <span style={{ fontSize: 16, fontWeight: 700, color: S.textBright }}>Datenportal</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <span style={{ fontSize: 12, color: S.textDim }}>{user?.username}</span>
            {!user?.is_portal_only && (
              <button onClick={() => navigate("/dashboard")}
                style={{ fontSize: 11, color: S.accent, background: "none", border: "none",
                  cursor: "pointer", padding: "4px 8px" }}>
                Editor →
              </button>
            )}
            <button onClick={handleLogout}
              style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11,
                color: S.textDim, background: "none", border: "none", cursor: "pointer" }}>
              <LogOut size={13} /> Abmelden
            </button>
          </div>
        </div>
      </header>

      {/* Content */}
      <main style={{ maxWidth: 1100, margin: "0 auto", padding: "40px 24px" }}>
        {loading ? (
          <p style={{ color: S.textDim, fontSize: 12 }}>Lädt…</p>
        ) : forms.length === 0 ? (
          <div style={{ textAlign: "center", padding: "80px 0" }}>
            <LayoutGrid size={48} style={{ color: S.textDim, opacity: 0.2, marginBottom: 16 }} />
            <p style={{ color: S.textDim, fontSize: 14 }}>Keine veröffentlichten Formulare verfügbar.</p>
          </div>
        ) : (
          <>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: S.textBright, marginBottom: 8 }}>
              Meine Anwendungen
            </h1>
            <p style={{ fontSize: 12, color: S.textDim, marginBottom: 32 }}>
              Klicken Sie auf eine Karte um die Anwendung zu starten.
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 16 }}>
              {forms.map((f) => (
                <div key={f.id}
                  onClick={() => navigate(`/app/${f.slug}`)}
                  style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`,
                    borderRadius: 12, padding: "20px 22px", cursor: "pointer",
                    transition: "border-color 0.15s, box-shadow 0.15s" }}
                  onMouseEnter={e => {
                    e.currentTarget.style.borderColor = "rgba(252,228,153,0.4)";
                    e.currentTarget.style.boxShadow = "0 4px 20px rgba(0,0,0,0.3)";
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.borderColor = S.border;
                    e.currentTarget.style.boxShadow = "none";
                  }}>
                  <div style={{ fontSize: 28, marginBottom: 10 }}>{f.icon || "📊"}</div>
                  <h3 style={{ fontSize: 14, fontWeight: 700, color: S.textBright, margin: "0 0 6px" }}>
                    {f.name}
                  </h3>
                  {f.description && (
                    <p style={{ fontSize: 11, color: S.textDim, margin: "0 0 14px", lineHeight: 1.5 }}>
                      {f.description}
                    </p>
                  )}
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 12 }}>
                    <Play size={11} style={{ color: "#6ee7b7" }} />
                    <span style={{ fontSize: 10, color: "#6ee7b7", fontWeight: 600 }}>Öffnen</span>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </main>
    </div>
  );
}
