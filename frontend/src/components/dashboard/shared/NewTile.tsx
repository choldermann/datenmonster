import { useState } from "react";
import { S } from "../constants";

// `gesperrt` traegt den Grund als Text — gesetzt heisst: ausgegraut und nicht klickbar.
function NewTile({ label, sub, icon: Icon, onClick, gesperrt }) {
  const [hovered, setHovered] = useState(false);
  const an = hovered && !gesperrt;
  return (
    <div onClick={gesperrt ? undefined : onClick} title={gesperrt}
      onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
      className="card transition-all duration-150 flex flex-col items-center justify-center gap-3 min-h-[116px]"
      style={{
        borderColor: an ? "rgba(110,231,170,0.6)" : "rgba(110,231,170,0.25)",
        backgroundColor: an ? "rgba(110,231,170,0.07)" : "rgba(110,231,170,0.03)",
        borderStyle: "dashed",
        opacity: gesperrt ? 0.4 : 1,
        cursor: gesperrt ? "not-allowed" : "pointer",
      }}>
      <div className="rounded-full p-2" style={{ backgroundColor: an ? "rgba(110,231,170,0.15)" : "rgba(110,231,170,0.07)" }}>
        <Icon size={20} style={{ color: an ? "#6ee7aa" : "#4ade80" }} />
      </div>
      <div className="text-center">
        <p className="text-sm font-medium" style={{ color: an ? "#6ee7aa" : "#4ade80" }}>{label}</p>
        <p className="text-xs mt-0.5" style={{ color: "rgba(110,231,170,0.5)" }}>{sub}</p>
      </div>
    </div>
  );
}

// ─── Data Explorer ────────────────────────────────────────────────────────────
const PAGE_SIZE = 100;
// ─── Feldtyp-Hilfsfunktionen ─────────────────────────────────────────────────
const TYPE_META = {
  integer: { label: "INT",  color: "#93c5fd" },
  decimal: { label: "DEC",  color: "#6ee7b7" },
  string:  { label: "STR",  color: "#8a8a8a" },
  date:    { label: "DATE", color: "#fcd34d" },
  bool:    { label: "BOOL", color: "#c4b5fd" },
};

export default NewTile;
