// Pipeline Node Farben und Typen
export const S = {
  accent: "var(--accent)",
  bgMain: "var(--bg-main)",
  bgCard: "var(--bg-card)",
  bgEl: "var(--bg-elevated)",
  border: "var(--border)",
  textMain: "var(--text-main)",
  textBright: "var(--text-bright)",
  textDim: "var(--text-dim)",
};

export const NODE_COLORS = {
  trigger:     "#fce499", // gold - Akzent
  ftp:         "#38bdf8", // sky - FTP Input
  dispatcher:  "#a78bfa", // violet - Bedingungen
  mapping:     "#6ee7b7", // emerald - Verarbeitung
  ftp_upload:  "#f97316", // orange - Output
  email:       "#f472b6", // pink - Benachrichtigung
  condition:   "#fbbf24", // amber - IF/ELSE
  webhook:     "#818cf8", // indigo - HTTP
  rest_fetch:  "#34d399", // teal - REST API
};

export const NODE_TYPES = [
  { type: "trigger",    label: "Trigger",       icon: "⏰", color: NODE_COLORS.trigger,    desc: "Startet die Pipeline" },
  { type: "ftp",        label: "FTP Input",     icon: "📥", color: NODE_COLORS.ftp,         desc: "Dateien von FTP holen" },
  { type: "rest_fetch", label: "REST Fetch",    icon: "🌐", color: NODE_COLORS.rest_fetch,  desc: "REST API abrufen" },
  { type: "dispatcher", label: "Verzweigung",   icon: "🔀", color: NODE_COLORS.dispatcher,  desc: "Bedingungen & Verzweigung" },
  { type: "mapping",    label: "Mapping",       icon: "⚙️", color: NODE_COLORS.mapping,     desc: "Mapping ausführen" },
  { type: "ftp_upload", label: "FTP Upload",    icon: "📤", color: NODE_COLORS.ftp_upload,  desc: "Datei hochladen" },
  { type: "email",      label: "E-Mail",        icon: "📧", color: NODE_COLORS.email,       desc: "E-Mail senden" },
];

export const PORT_SIZE = 10;
