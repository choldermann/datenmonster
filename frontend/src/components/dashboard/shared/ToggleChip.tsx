import { S } from "../constants";

function ToggleChip({ label, active, onClick }) {
  return (
    <button onClick={onClick} style={{
      padding: "4px 10px", borderRadius: 6, fontSize: 11, fontWeight: 500, cursor: "pointer",
      border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
      backgroundColor: active ? "color-mix(in srgb, var(--accent) 15%, transparent)" : "transparent",
      color: active ? "var(--accent)" : "var(--text-dim)",
      transition: "all 0.12s",
    }}>{label}</button>
  );
}

// ─── Scheduler Form Modal ─────────────────────────────────────────────────────
const TODAY = new Date().toISOString().slice(0, 10);


export default ToggleChip;
