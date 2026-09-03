import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { useState, useEffect } from "react";
import "./hooks/useTheme"; // Theme beim Start sofort anwenden
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ProjectProvider } from "./context/ProjectContext";
import { AIAssistantProvider, useAIAssistant } from "./contexts/AIAssistantContext";
import { aiDownloadStore } from "./store/aiDownloadStore";
import FloatingAIAssistant from "./components/ai/FloatingAIAssistant";
import Login from "./pages/Login";
import ErrorBoundary from "./components/ErrorBoundary";
import Dashboard from "./pages/Dashboard";
import MappingEditor from "./pages/MappingEditor";
import PipelineEditor from "./pages/PipelineEditor";
import FormEditor from "./pages/FormEditor";
import FormRunner from "./pages/FormRunner";
import PortalHome from "./pages/PortalHome";
import PortalRunner from "./pages/PortalRunner";

/** Blendet den schwebenden KI-Assistenten in Formular-Runnern aus (Editor-Run
 *  /forms/:id/run und Portal /app/:slug), sofern das Formular ihn nicht per
 *  schema.show_ai_assistant ausdrücklich einblendet. Sonst ist er überall aktiv. */
/**
 * Orte, an denen der schwebende Assistent etwas kann – die Editoren.
 *
 * Bewusst eine Erlaubnisliste statt einer Verbotsliste: Sonst taucht er bei
 * jeder neuen Seite von selbst wieder auf, und jemand muss ihn einzeln wieder
 * abschalten. Maßstab ist, ob die Seite ihm Arbeitskontext gibt – der
 * Mapping-Editor meldet ihm den aktiven Knoten, lässt ihn Fehler erklären und
 * ganze Knoten bauen; der Formular-Editor hinterlegt ihm Aktionen. Auf
 * Übersichtsseiten hätte er nur allgemeine Auskunft gegeben, und dafür gibt es
 * jetzt die KI-Werkbank als eigenen Bereich.
 *
 * `/forms/:id/run` fällt bewusst NICHT darunter (das `$` verhindert es) – der
 * Formularlauf hat seine eigene Regel weiter unten.
 */
const ARBEITSORTE = [
  /^\/mappings\/[^/]+$/,
  /^\/pipelines\/[^/]+$/,
  /^\/forms\/new$/,
  /^\/forms\/[^/]+$/,
];

function AiAssistantGate() {
  const location = useLocation();
  const { formAiAllowed, versteckt } = useAIAssistant();
  const { user } = useAuth();
  const pfad = location.pathname;

  // Vor der Anmeldung gibt es keinen Kontext, keine Berechtigung und nichts zu
  // fragen – dort wäre es nur ein Knopf ohne Funktion.
  if (!user) return null;
  // Bereiche, die den Assistenten selbst ersetzen (KI-Werkbank).
  if (versteckt) return null;

  // Formularlauf und Portal: nur, wenn das Formular ihn ausdrücklich einblendet
  // (schema.show_ai_assistant). Dort sitzen auch Anwender ohne Editor-Rechte.
  if (/^\/forms\/[^/]+\/run$/.test(pfad) || pfad.startsWith("/app/")) {
    return formAiAllowed ? <FloatingAIAssistant /> : null;
  }

  if (!ARBEITSORTE.some(r => r.test(pfad))) return null;
  return <FloatingAIAssistant />;
}

/** Schützt Editor-Routen: Portal-Only-Benutzer werden zu /portal umgeleitet. */
function EditorRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  if (user.is_portal_only) return <Navigate to="/portal" replace />;
  return children;
}

/** Schützt alle authentifizierten Routen (Editor + Portal-Benutzer). */
function PrivateRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  return user ? children : <Navigate to="/login" replace />;
}

/** Startseite: je nach Rolle → Dashboard oder Portal. */
function DefaultRedirect() {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={user.is_portal_only ? "/portal" : "/dashboard"} replace />;
}

function AiDownloadBanner() {
  const [dl, setDl] = useState(aiDownloadStore.getState());
  useEffect(() => aiDownloadStore.subscribe(setDl), []);

  if (!dl.pulling && !dl.done) return null;

  const ACCENT = "#fce499";
  const barColor = dl.done ? "#6ee7b7" : dl.error ? "#e07070" : ACCENT;

  return (
    <div style={{
      position: "fixed", bottom: 0, left: 0, right: 0, zIndex: 9999,
      backgroundColor: "#1a1a2e", borderTop: `1px solid ${barColor}30`,
      padding: "6px 20px", display: "flex", alignItems: "center", gap: 12,
      boxShadow: "0 -4px 20px rgba(0,0,0,0.4)",
    }}>
      <span style={{ fontSize: 11, color: barColor, whiteSpace: "nowrap", fontWeight: 600 }}>
        {dl.done ? "✓" : dl.error ? "✗" : "⬇"} Modell-Download{dl.model ? `: ${dl.model}` : ""}
      </span>
      <div style={{ flex: 1, height: 4, backgroundColor: "rgba(255,255,255,0.07)", borderRadius: 2, overflow: "hidden" }}>
        {dl.percent != null ? (
          <div style={{ height: "100%", width: `${dl.percent}%`, backgroundColor: barColor, borderRadius: 2, transition: "width 0.4s ease" }} />
        ) : (
          <div style={{ height: "100%", width: "35%", backgroundColor: barColor, borderRadius: 2, animation: "aiSweep 1.4s ease-in-out infinite" }} />
        )}
      </div>
      <span style={{ fontSize: 11, color: "rgba(255,255,255,0.4)", whiteSpace: "nowrap" }}>
        {dl.done ? "Fertig!" : dl.error ? dl.status : dl.percent != null ? `${dl.percent}%` : dl.status || "..."}
      </span>
      <style>{`@keyframes aiSweep { 0% { margin-left:-35% } 100% { margin-left:100% } }`}</style>
    </div>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <ProjectProvider>
          <AIAssistantProvider>
          <BrowserRouter>
            <Routes>
              {/* Public */}
              <Route path="/login" element={<Login />} />

              {/* Editor-Oberfläche (nur für nicht-portal-only Benutzer) */}
              <Route path="/dashboard"     element={<EditorRoute><Dashboard /></EditorRoute>} />
              <Route path="/mappings/new"  element={<EditorRoute><MappingEditor /></EditorRoute>} />
              <Route path="/mappings/:id"  element={<EditorRoute><MappingEditor /></EditorRoute>} />
              <Route path="/pipelines/:id" element={<EditorRoute><PipelineEditor /></EditorRoute>} />
              <Route path="/forms/new"     element={<EditorRoute><FormEditor /></EditorRoute>} />
              <Route path="/forms/:id"     element={<EditorRoute><FormEditor /></EditorRoute>} />
              <Route path="/forms/:id/run" element={<EditorRoute><FormRunner /></EditorRoute>} />

              {/* Portal-Oberfläche (alle authentifizierten Benutzer) */}
              <Route path="/portal"    element={<PrivateRoute><PortalHome /></PrivateRoute>} />
              <Route path="/app/:slug" element={<PrivateRoute><PortalRunner /></PrivateRoute>} />

              {/* Fallback */}
              <Route path="*" element={<DefaultRedirect />} />
            </Routes>
            <AiDownloadBanner />
            <AiAssistantGate />
          </BrowserRouter>
          </AIAssistantProvider>
        </ProjectProvider>
      </AuthProvider>
    </ErrorBoundary>
  );
}
