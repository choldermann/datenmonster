import axios from "axios";

const api = axios.create({
  baseURL: "",
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("dm_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      const url = err.config?.url || "";
      // Auth-Endpunkte nicht weiterleiten – sonst Endlosschleife auf Login-Seite
      if (!url.includes("/api/auth/token") && !url.includes("/api/auth/register")) {
        localStorage.removeItem("dm_token");
        window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  }
);

export default api;
