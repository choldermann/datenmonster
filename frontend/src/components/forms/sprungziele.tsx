/**
 * Sprünge zwischen ERP-neutralen Ansichten (Marktlage-Pakete) und den Cockpits.
 * Gesucht wird nach Widget-Typ (GET /api/start/sprungziele?typen=…): je Typ die sichtbaren Cockpits, die ein
 * solches Widget haben, mit Reiter. Kein passendes Cockpit (z. B. bei büro+) = kein Link.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import api from "../../api/client";

export type Sprungziel = { form_id: number; name: string; projekt?: string; reiter?: string | null; reiter_label?: string | null };

const cache = new Map<string, Promise<Record<string, Sprungziel[]>>>();

export function useSprungziele(typen: string[]): Record<string, Sprungziel[]> {
  const key = [...new Set(typen.filter(Boolean))].sort().join(",");
  const [ziele, setZiele] = useState<Record<string, Sprungziel[]>>({});
  useEffect(() => {
    if (!key) { setZiele({}); return; }
    if (!cache.has(key)) {
      cache.set(key, api.get("/api/start/sprungziele", { params: { typen: key } })
        .then(({ data }) => data.ziele || {}).catch(() => { cache.delete(key); return {}; }));
    }
    let lebt = true;
    cache.get(key)!.then((z) => lebt && setZiele(z));
    return () => { lebt = false; };
  }, [key]);
  return ziele;
}

export const sprungPfad = (z: Sprungziel) => `/start/cockpit/${z.form_id}${z.reiter ? `?reiter=${encodeURIComponent(z.reiter)}` : ""}`;

/** Links zu allen Zielen eines Typs; bei gleichem Cockpitnamen in mehreren Projekten mit Projektname. */
export function SprungLinks({ ziele }: { ziele: Sprungziel[] }) {
  if (!ziele?.length) return <span style={{ color: "var(--text-dim)" }}>–</span>;
  const doppelt = new Set(ziele.map((z) => z.name).filter((n, i, a) => a.indexOf(n) !== i));
  return (
    <span style={{ display: "inline-flex", flexDirection: "column", gap: 2 }}>
      {ziele.slice(0, 4).map((z) => (
        <Link key={z.form_id} to={sprungPfad(z)} onClick={(e) => e.stopPropagation()}
          title={`${z.name}${z.reiter_label ? ` › ${z.reiter_label}` : ""}${z.projekt ? ` (${z.projekt})` : ""}`}
          style={{ color: "var(--accent)", textDecoration: "none", whiteSpace: "nowrap", display: "inline-flex", alignItems: "center", gap: 3 }}>
          <ArrowUpRight size={12} />
          {z.name.replace(/-Cockpit$/, "")}{z.reiter_label ? ` › ${z.reiter_label}` : ""}
          {doppelt.has(z.name) && z.projekt ? <span style={{ color: "var(--text-dim)" }}> · {z.projekt}</span> : null}
        </Link>
      ))}
    </span>
  );
}
