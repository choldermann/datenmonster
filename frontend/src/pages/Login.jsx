import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Loader2, LogIn } from "lucide-react";
import DatenmonsterLogo from "../components/DatenmonsterLogo";

const S = {
  accent: "var(--accent)", bgMain: "var(--bg-main)", bgCard: "var(--bg-card)",
  bgEl: "var(--bg-elevated)", border: "var(--border)", textMain: "var(--text-main)",
  textBright: "var(--text-bright)", textDim: "var(--text-dim)",
};

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleLogin = async () => {
    setError(""); setLoading(true);
    try { await login(username, password); navigate("/dashboard"); }
    catch { setError("Falscher Benutzername oder Passwort"); }
    finally { setLoading(false); }
  };

  const handleKey = (e) => { if (e.key === "Enter") handleLogin(); };

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
            {error && <p className="text-xs text-center" style={{ color: "#e07070" }}>{error}</p>}
            <button onClick={handleLogin} disabled={loading || !username || !password} className="btn-primary w-full justify-center mt-1">
              {loading ? <Loader2 size={14} className="animate-spin" /> : <LogIn size={14} />} Anmelden
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
