/** Verfügbare Farbschemata. Die Farben selbst stehen in themes.css unter
 *  [data-theme="<id>"] – hier nur, was die Auswahl zum Anzeigen braucht.
 *  `scheme` sagt, ob das Theme hell oder dunkel ist (für Regeln wie die
 *  Scrollbalken, die nur zwischen hell und dunkel unterscheiden). */
export type ThemeGruppe = "klassisch" | "ruhig" | "retro";

export interface ThemeDef {
  id: string;
  label: string;
  desc: string;
  scheme: "dark" | "light";
  gruppe: ThemeGruppe;
}

export const THEMES: ThemeDef[] = [
  { id: "dark",       label: "Dunkel",          desc: "Das Standard-Theme",                    scheme: "dark",  gruppe: "klassisch" },
  { id: "light",      label: "Hell",            desc: "Helles Theme",                          scheme: "light", gruppe: "klassisch" },
  { id: "nord",       label: "Nord",            desc: "Kühles Blaugrau, ruhig für lange Tage", scheme: "dark",  gruppe: "ruhig" },
  { id: "solarized",  label: "Solarized Hell",  desc: "Warmes Papier, wenig Kontrasthärte",    scheme: "light", gruppe: "ruhig" },
  { id: "bernstein",  label: "Bernstein",       desc: "Monochrom-Monitor, 80er Terminal",      scheme: "dark",  gruppe: "retro" },
  { id: "phosphor",   label: "Grüner Phosphor", desc: "Der klassische grüne Bildschirm",       scheme: "dark",  gruppe: "retro" },
  { id: "amiga",      label: "Amiga Workbench", desc: "Blau, Weiß und Orange – Workbench 1.3", scheme: "dark",  gruppe: "retro" },
  { id: "c64",        label: "C64",             desc: "READY. – Hellblau auf Dunkelblau",      scheme: "dark",  gruppe: "retro" },
  { id: "gameboy",    label: "Game Boy",        desc: "Vier Grüntöne, 160 × 144 Gefühl",       scheme: "light", gruppe: "retro" },
  { id: "nextstep",   label: "NeXTSTEP",        desc: "Graue 3D-Kanten, Helvetica, 1989",      scheme: "light", gruppe: "retro" },
  { id: "atari",      label: "Atari ST",        desc: "GEM-Desktop: Grün, Weiß, Schwarz",      scheme: "light", gruppe: "retro" },
  { id: "norton",     label: "Norton Commander", desc: "Blaue Panels, Doppellinien, F10 = Quit", scheme: "dark",  gruppe: "retro" },
  { id: "turbopascal", label: "Turbo Pascal",   desc: "Gelb auf Blau, Turbo Vision 1992",      scheme: "dark",  gruppe: "retro" },
  { id: "videotext",  label: "Videotext",       desc: "Tafel 100 – sieben Farben auf Schwarz", scheme: "dark",  gruppe: "retro" },
  { id: "zx",         label: "ZX Spectrum",     desc: "Schwarz mit Regenbogenstreifen, 1982",  scheme: "dark",  gruppe: "retro" },
  { id: "win95",      label: "Windows 95",      desc: "Petrol-Desktop, graue 3D-Knöpfe",       scheme: "light", gruppe: "retro" },
  { id: "system7",    label: "Mac System 7",    desc: "Schwarz auf Weiß, grauer Schreibtisch", scheme: "light", gruppe: "retro" },
  { id: "os2",        label: "OS/2 Warp",       desc: "Graue Fenster auf tiefem Blau",         scheme: "light", gruppe: "retro" },
  { id: "beos",       label: "BeOS",            desc: "Hellgrau mit dem gelben Reiter",        scheme: "light", gruppe: "retro" },
];

export const GRUPPEN: { id: ThemeGruppe; label: string }[] = [
  { id: "klassisch", label: "Klassisch" },
  { id: "ruhig",     label: "Ruhig" },
  { id: "retro",     label: "Retro" },
];

export function findeTheme(id: string): ThemeDef | undefined {
  return THEMES.find(t => t.id === id);
}
