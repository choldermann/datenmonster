import { WIDGET_TYPES, S } from "./constants";

export default function ReportToolbar({ onAddWidget }) {
  return (
    <div style={{ width: 150, flexShrink: 0, backgroundColor: S.bgCard, borderRight: `1px solid ${S.border}`, padding: "12px 8px", display: "flex", flexDirection: "column", gap: 3 }}>
      <p style={{ fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 700, marginBottom: 8, paddingLeft: 4 }}>Widgets</p>
      {WIDGET_TYPES.map(wt => (
        <button key={wt.type} onClick={() => onAddWidget(wt.type)}
          draggable
          onDragStart={e => { e.dataTransfer.setData("new_widget_type", wt.type); }}
          style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 8px", borderRadius: 5, cursor: "grab", border: `1px solid ${S.border}`, backgroundColor: "transparent", color: S.textMain, fontSize: 11, textAlign: "left", width: "100%" }}
          onMouseEnter={e => { e.currentTarget.style.backgroundColor = "rgba(252,228,153,0.08)"; e.currentTarget.style.borderColor = "rgba(252,228,153,0.3)"; }}
          onMouseLeave={e => { e.currentTarget.style.backgroundColor = "transparent"; e.currentTarget.style.borderColor = S.border; }}>
          <span style={{ fontSize: 14 }}>{wt.icon}</span>
          <div>
            <p style={{ margin: 0, fontSize: 11, fontWeight: 600, color: S.textBright }}>{wt.label}</p>
            <p style={{ margin: 0, fontSize: 9, color: S.textDim }}>{wt.desc}</p>
          </div>
        </button>
      ))}
    </div>
  );
}
