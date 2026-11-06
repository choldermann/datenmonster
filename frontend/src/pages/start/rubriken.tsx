/**
 * Ein Cockpit mit Rubriken: Menüzustand des Büros.
 *
 * Lädt /api/start/rubriken und die persönlichen Einstellungen (Pins, ausgeblendete
 * Projekte) einmal in der Büro-Schale und reicht sie über den Outlet-Kontext an
 * die Seiten weiter. Plan: ~/.claude/plans/ein-cockpit-rubriken.md, Phase 1.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";
import {
  Gauge, Activity, TrendingUp, ShoppingCart, Package, Truck, Tag, HeartPulse,
  FileSpreadsheet, Globe, Inbox, LayoutGrid,
} from "lucide-react";
import api, { fehlerText } from "../../api/client";

export const RUBRIK_ICONS = {
  gf: Gauge, monitor: Activity, vertrieb: TrendingUp, einkauf: ShoppingCart, lager: Package,
  versand: Truck, preis: Tag, health: HeartPulse, datev: FileSpreadsheet, intrastat: Globe,
  eingangsrechnungen: Inbox,
};
export const rubrikIcon = (key) => RUBRIK_ICONS[key] || LayoutGrid;

export const ART_TEXT = { kopie: "Kopie", bericht: "Bericht", pflege: "Pflege", cockpit: "" };

/** Pfad zu einem Eintrag: Haupteintrag ohne Formular-ID, alle anderen mit. */
export const rubrikPfad = (rubrik, eintrag = null, reiter = null) => {
  const basis = !eintrag || eintrag.id === rubrik.haupt?.id
    ? `/start/r/${rubrik.id}` : `/start/r/${rubrik.id}/${eintrag.id}`;
  return reiter ? `${basis}?reiter=${encodeURIComponent(reiter)}` : basis;
};

/** Zustand für StartLayout. */
export function useRubrikenLaden() {
  const [roh, setRoh] = useState(null);          // null = lädt
  const [pins, setPinsState] = useState([]);
  const [projekteAus, setProjekteAusState] = useState([]);
  const [fehler, setFehler] = useState(null);

  const neuLaden = useCallback(() => {
    api.get("/api/start/rubriken").then(({ data }) => { setRoh(data?.gruppen || []); setFehler(null); })
      .catch((e) => { setRoh([]); setFehler(fehlerText(e)); });
  }, []);

  useEffect(() => {
    neuLaden();
    api.get("/api/start/einstellungen").then(({ data }) => {
      setPinsState(data?.pins || []);
      setProjekteAusState(data?.projekte_aus || []);
    }).catch(() => {});
  }, [neuLaden]);

  const speichern = async (feld, wert, setzen) => {
    setzen(wert);
    try {
      const { data } = await api.put("/api/start/einstellungen", { [feld]: wert });
      setzen(data?.[feld] || []);
    } catch (e) {
      setFehler(fehlerText(e));
    }
  };
  const pinUmschalten = (formId) =>
    speichern("pins", pins.includes(formId) ? pins.filter((p) => p !== formId) : [...pins, formId], setPinsState);
  const projektUmschalten = (pid) =>
    speichern("projekte_aus", projekteAus.includes(pid) ? projekteAus.filter((p) => p !== pid) : [...projekteAus, pid],
      setProjekteAusState);

  // Alle Projekte, die im Menü vorkommen (0 = ohne Projekt) – für die Einstellungen.
  const projekte = useMemo(() => {
    const m = new Map();
    for (const g of roh || []) for (const r of g.rubriken) for (const e of [r.haupt, ...r.eintraege]) {
      const k = e.project_id || 0;
      if (!m.has(k)) m.set(k, { id: k, name: e.projekt || "Ohne Projekt", anzahl: 0 });
      m.get(k).anzahl += 1;
    }
    return [...m.values()].sort((a, b) => (a.id === 0) - (b.id === 0) || a.name.localeCompare(b.name, "de"));
  }, [roh]);

  // Ausgeblendete Projekte herausnehmen; fällt der Haupteintrag weg, rückt der nächste auf.
  const gruppen = useMemo(() => {
    if (roh === null) return null;
    const sichtbar = (e) => !projekteAus.includes(e.project_id || 0);
    return roh.map((g) => ({
      ...g,
      rubriken: g.rubriken.map((r) => {
        const alle = [r.haupt, ...r.eintraege].filter(sichtbar);
        if (!alle.length) return null;
        const haupt = alle.find((e) => e.art === "cockpit") || alle[0];
        return { ...r, haupt, eintraege: alle.filter((e) => e !== haupt) };
      }).filter(Boolean),
    })).filter((g) => g.rubriken.length);
  }, [roh, projekteAus]);

  return { gruppen, pins, pinUmschalten, projekte, projekteAus, projektUmschalten, neuLaden, fehler };
}

export type RubrikenKontext = ReturnType<typeof useRubrikenLaden>;
export const useRubriken = () => useOutletContext<RubrikenKontext>();

/** Rubrik und Eintrag zu einer Formular-ID suchen. */
export function findeEintrag(gruppen, formId) {
  for (const g of gruppen || []) for (const r of g.rubriken) {
    for (const e of [r.haupt, ...r.eintraege]) if (String(e.id) === String(formId)) return { rubrik: r, eintrag: e };
  }
  return null;
}

export function findeRubrik(gruppen, rubrikId) {
  for (const g of gruppen || []) for (const r of g.rubriken) if (r.id === rubrikId) return r;
  return null;
}

export const ersteRubrik = (gruppen) => (gruppen || [])[0]?.rubriken?.[0] || null;
