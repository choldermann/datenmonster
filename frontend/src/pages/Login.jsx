import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Loader2, LogIn, UserPlus } from "lucide-react";
import api from "../api/client";
import DatenmonsterLogo from "../components/DatenmonsterLogo";

const S = {
  accent: "var(--accent)", bgMain: "var(--bg-main)", bgCard: "var(--bg-card)",
  bgEl: "var(--bg-elevated)", border: "var(--border)", textMain: "var(--text-main)",
  textBright: "var(--text-bright)", textDim: "var(--text-dim)",
};

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleLogin = async () => {
    setError(""); setLoading(true);
    try { await login(username, password); navigate("/dashboard"); }
    catch { setError("Falscher Benutzername oder Passwort"); }
    finally { setLoading(false); }
  };

  const handleRegister = async () => {
    setError("");
    if (!username.trim()) { setError("Benutzername eingeben"); return; }
    if (password.length < 6) { setError("Passwort mindestens 6 Zeichen"); return; }
    if (password !== password2) { setError("Passwörter stimmen nicht überein"); return; }
    setLoading(true);
    try {
      const { data } = await api.post("/api/auth/register", { username: username.trim(), password });
      localStorage.setItem("dm_token", data.access_token);
      window.location.href = "/dashboard";
    } catch (err) {
      setError(err.response?.data?.detail || "Registrierung fehlgeschlagen");
    } finally { setLoading(false); }
  };

  const handleKey = (e) => { if (e.key === "Enter") mode === "login" ? handleLogin() : handleRegister(); };

  return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{ backgroundColor: S.bgMain }}>
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-28 h-28 rounded-2xl mb-4"
            style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}` }}>
            <DatenmonsterLogo size={192} />
          </div>
          <h1 className="font-bold font-mono text-xl tracking-wider" style={{ color: S.accent }}>Datenmonster</h1>
          <p className="text-xs mt-1" style={{ color: S.textDim }}>Holdermann IT · ETL Tool</p>
        </div>

        <div className="flex mb-4 rounded-xl overflow-hidden" style={{ border: `1px solid ${S.border}`, backgroundColor: S.bgEl }}>
          {[["login", "Anmelden"], ["register", "Registrieren"]].map(([m, label]) => (
            <button key={m} onClick={() => { setMode(m); setError(""); }}
              className="flex-1 py-2.5 text-xs font-medium transition-all"
              style={{ backgroundColor: mode === m ? S.accent : "transparent", color: mode === m ? "#111" : S.textDim }}>
              {label}
            </button>
          ))}
        </div>

        <div className="card">
          <div className="flex flex-col gap-4">
            <div>
              <label className="block text-xs uppercase tracking-widest mb-1.5" style={{ color: S.textDim }}>Benutzername</label>
              <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} onKeyDown={handleKey} placeholder="benutzername" autoFocus />
            </div>
            <div>
              <label className="block text-xs uppercase tracking-widest mb-1.5" style={{ color: S.textDim }}>Passwort</label>
              <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={handleKey} placeholder="••••••••" />
            </div>
            {mode === "register" && (
              <div>
                <label className="block text-xs uppercase tracking-widest mb-1.5" style={{ color: S.textDim }}>Passwort wiederholen</label>
                <input className="input" type="password" value={password2} onChange={(e) => setPassword2(e.target.value)} onKeyDown={handleKey} placeholder="••••••••" />
              </div>
            )}
            {error && <p className="text-xs text-center" style={{ color: "#e07070" }}>{error}</p>}
            {mode === "login" ? (
              <button onClick={handleLogin} disabled={loading || !username || !password} className="btn-primary w-full justify-center mt-1">
                {loading ? <Loader2 size={14} className="animate-spin" /> : <LogIn size={14} />} Anmelden
              </button>
            ) : (
              <button onClick={handleRegister} disabled={loading || !username || !password || !password2} className="btn-primary w-full justify-center mt-1">
                {loading ? <Loader2 size={14} className="animate-spin" /> : <UserPlus size={14} />} Konto erstellen
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
