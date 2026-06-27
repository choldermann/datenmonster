import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ProjectProvider } from "./context/ProjectContext";
import Login from "./pages/Login";
import ErrorBoundary from "./components/ErrorBoundary";
import Dashboard from "./pages/Dashboard";
import MappingEditor from "./pages/MappingEditor";
import PipelineEditor from "./pages/PipelineEditor";
import ReportEditor from "./pages/ReportEditor";
import FormEditor from "./pages/FormEditor";
import FormRunner from "./pages/FormRunner";
import PortalHome from "./pages/PortalHome";
import PortalRunner from "./pages/PortalRunner";

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

export default function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <ProjectProvider>
          <BrowserRouter>
            <Routes>
              {/* Public */}
              <Route path="/login" element={<Login />} />

              {/* Editor-Oberfläche (nur für nicht-portal-only Benutzer) */}
              <Route path="/dashboard"     element={<EditorRoute><Dashboard /></EditorRoute>} />
              <Route path="/mappings/new"  element={<EditorRoute><MappingEditor /></EditorRoute>} />
              <Route path="/mappings/:id"  element={<EditorRoute><MappingEditor /></EditorRoute>} />
              <Route path="/pipelines/:id" element={<EditorRoute><PipelineEditor /></EditorRoute>} />
              <Route path="/reports/:id"   element={<EditorRoute><ReportEditor /></EditorRoute>} />
              <Route path="/forms/new"     element={<EditorRoute><FormEditor /></EditorRoute>} />
              <Route path="/forms/:id"     element={<EditorRoute><FormEditor /></EditorRoute>} />
              <Route path="/forms/:id/run" element={<EditorRoute><FormRunner /></EditorRoute>} />

              {/* Portal-Oberfläche (alle authentifizierten Benutzer) */}
              <Route path="/portal"    element={<PrivateRoute><PortalHome /></PrivateRoute>} />
              <Route path="/app/:slug" element={<PrivateRoute><PortalRunner /></PrivateRoute>} />

              {/* Fallback */}
              <Route path="*" element={<DefaultRedirect />} />
            </Routes>
          </BrowserRouter>
        </ProjectProvider>
      </AuthProvider>
    </ErrorBoundary>
  );
}
