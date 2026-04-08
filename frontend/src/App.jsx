import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ProjectProvider } from "./context/ProjectContext";
import Login from "./pages/Login";
import ErrorBoundary from "./components/ErrorBoundary";
import Dashboard from "./pages/Dashboard";
import MappingEditor from "./pages/MappingEditor";
import PipelineEditor from "./pages/PipelineEditor";
import ReportEditor from "./pages/ReportEditor";

function PrivateRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  return user ? children : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <ErrorBoundary>
    <AuthProvider>
      <ProjectProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/dashboard" element={<PrivateRoute><Dashboard /></PrivateRoute>} />
            <Route path="/mappings/new" element={<PrivateRoute><MappingEditor /></PrivateRoute>} />
            <Route path="/mappings/:id" element={<PrivateRoute><MappingEditor /></PrivateRoute>} />
            <Route path="/pipelines/:id" element={<PrivateRoute><PipelineEditor /></PrivateRoute>} />
            <Route path="/reports/:id" element={<PrivateRoute><ReportEditor /></PrivateRoute>} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </BrowserRouter>
      </ProjectProvider>
    </AuthProvider>
    </ErrorBoundary>
  );
}
