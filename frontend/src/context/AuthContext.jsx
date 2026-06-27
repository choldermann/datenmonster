import { createContext, useContext, useState, useEffect } from "react";
import api from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("dm_token");
    if (!token) { setLoading(false); return; }
    api.get("/api/auth/me")
      .then(({ data }) => setUser(data))
      .catch(() => localStorage.removeItem("dm_token"))
      .finally(() => setLoading(false));
  }, []);

  const login = async (username, password) => {
    const form = new URLSearchParams({ username, password });
    const { data } = await api.post("/api/auth/token", form, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    localStorage.setItem("dm_token", data.access_token);
    setUser({
      username:       data.username,
      is_admin:       data.is_admin ?? false,
      is_portal_only: data.is_portal_only ?? false,
    });
    return data;
  };

  const logout = () => {
    localStorage.removeItem("dm_token");
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
