/**
 * Lizenz-Auskunft für die Oberfläche.
 *
 * Zweck: Knöpfe, die ohnehin an der Sperre scheitern würden, sollen vorher
 * ausgegraut sein. Ohne das erfährt man erst beim Speichern, dass etwas zur
 * Pro-Version gehört — und hat die Arbeit schon gemacht.
 *
 * Die Oberfläche entscheidet damit NICHTS. Die Sperre sitzt im Backend
 * (app/core/lizenz_gate.py); hier geht es nur darum, sie sichtbar zu machen.
 */
import { createContext, useContext, useEffect, useState, useCallback, ReactNode } from "react";

export interface KontingentPosten {
  art: string;
  label: string;
  benutzt: number;
  grenze: number | null;
  unbegrenzt: boolean;
}

interface LizenzWert {
  geladen: boolean;
  rechte: Set<string>;
  kontingent: KontingentPosten[];
  /** Ist dieses Recht freigeschaltet? Solange nichts geladen ist: ja — lieber
   *  kurz einen Knopf zu viel zeigen als einen fälschlich gesperrten. */
  hat: (recht: string) => boolean;
  /** Text für title/Tooltip, wenn gesperrt — sonst undefined. */
  sperrgrund: (recht: string) => string | undefined;
  /** Text, wenn ein Kontingent voll ist ("mappings", "datasets", …). */
  kontingentGrund: (art: string) => string | undefined;
  neuLaden: () => void;
}

const KLARTEXT: Record<string, string> = {
  form_build:     "Eigene Formulare und Dashboards bauen",
  pipeline_build: "Eigene Pipelines bauen",
  query_build:    "Abfrage-Generator und Report-Baukasten",
  api_studio:     "API Studio",
  ftp_sftp:       "FTP- und SFTP-Verbindungen",
  rest_sources:   "Eigene REST-Schnittstellen als Datenquelle",
  mail_connector: "E-Mails als Datenquelle",
  ai_build:       "KI-Werkbank und KI-Assistent",
  ai_memory:      "KI-Wissensdatenbank",
  schema_catalog: "Schema-Katalog",
  multi_tenant:   "Mehrere Mandanten",
  multi_user:     "Weitere Administratoren",
  db_write:       "Eigene Mappings in eine Datenbank schreiben lassen",
  unlimited:      "Unbegrenzter Eigenbau",
  plugin_tier2:   "Erweiterte Plugins",
};

const Ctx = createContext<LizenzWert | null>(null);

async function hole(pfad: string) {
  const token = localStorage.getItem("dm_token");
  const r = await fetch(pfad, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!r.ok) throw new Error(String(r.status));
  return r.json();
}

export function LizenzProvider({ children }: { children: ReactNode }) {
  const [geladen, setGeladen]       = useState(false);
  const [rechte, setRechte]         = useState<Set<string>>(new Set());
  const [kontingent, setKontingent] = useState<KontingentPosten[]>([]);

  const neuLaden = useCallback(() => {
    hole("/api/license/")
      .then(d => { setRechte(new Set(d?.active_features || [])); setGeladen(true); })
      .catch(() => setGeladen(false));
    hole("/api/license/kontingent")
      .then(d => setKontingent(d?.posten || []))
      .catch(() => setKontingent([]));
  }, []);

  useEffect(() => { neuLaden(); }, [neuLaden]);

  const hat = useCallback(
    (recht: string) => (!geladen ? true : rechte.has(recht)),
    [geladen, rechte],
  );

  const sperrgrund = useCallback((recht: string) => {
    if (hat(recht)) return undefined;
    const was = KLARTEXT[recht] || recht;
    return `„${was}“ gehört zur Pro-Version. Installierte Vorlagen laufen davon unberührt weiter. Freischalten unter monstersuite.de.`;
  }, [hat]);

  const kontingentGrund = useCallback((art: string) => {
    const p = kontingent.find(x => x.art === art);
    if (!p || p.grenze === null || p.benutzt < p.grenze) return undefined;
    return `In der kostenlosen Version sind ${p.grenze} möglich (${p.label}), und so viele gibt es bereits. ` +
           `Objekte aus installierten Vorlagen zählen nicht mit. Mehr davon gehört zur Pro-Version.`;
  }, [kontingent]);

  return (
    <Ctx.Provider value={{ geladen, rechte, kontingent, hat, sperrgrund, kontingentGrund, neuLaden }}>
      {children}
    </Ctx.Provider>
  );
}

/** Ohne Provider (z.B. im Portal) gilt alles als erlaubt — dort gibt es keine
 *  Bau-Knöpfe, und die Sperre sitzt ohnehin im Backend. */
export function useLizenz(): LizenzWert {
  const v = useContext(Ctx);
  if (v) return v;
  return {
    geladen: false,
    rechte: new Set(),
    kontingent: [],
    hat: () => true,
    sperrgrund: () => undefined,
    kontingentGrund: () => undefined,
    neuLaden: () => {},
  };
}
