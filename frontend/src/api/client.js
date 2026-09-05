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

/** Fehlermeldung einer API-Antwort als TEXT.
 *
 *  FastAPI liefert `detail` je nach Lage als Zeichenkette (HTTPException) oder
 *  als Liste von Objekten (Validierungsfehler: {type, loc, msg, input}). Wird so
 *  ein Objekt direkt in JSX gesetzt, wirft React Fehler #31 und reisst die ganze
 *  Seite ab – aus einem Bedienfehler wird ein Totalausfall. Deshalb geht jede
 *  Fehlerausgabe durch diese Funktion.
 *
 *  Nimmt sowohl axios-Fehler (err.response.data.detail) als auch den bereits
 *  ausgepackten Antwortkoerper eines fetch-Aufrufs (err.detail).
 */
export function fehlerText(err, rueckfall) {
  const d = err?.response?.data?.detail ?? err?.response?.data ?? err?.detail;
  const einer = (x) => {
    if (x == null) return "";
    if (typeof x === "string") return x;
    if (typeof x === "object") {
      const wo = Array.isArray(x.loc) ? x.loc.filter(t => t !== "body").join(".") : "";
      return [wo, x.msg || x.message || JSON.stringify(x)].filter(Boolean).join(": ");
    }
    return String(x);
  };
  if (Array.isArray(d)) {
    const txt = d.map(einer).filter(Boolean).join(" · ");
    if (txt) return txt;
  } else {
    const txt = einer(d);
    if (txt) return txt;
  }
  // Ein mitgegebener Rueckfalltext ist der fachliche Satz der Stelle und schlaegt
  // deshalb die technische Meldung von axios ("Request failed with status code 500").
  return rueckfall || err?.message || "Unbekannter Fehler";
}

export default api;
