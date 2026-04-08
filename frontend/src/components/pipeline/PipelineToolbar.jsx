import { NODE_TYPES, S } from "./constants";

export default function PipelineToolbar({ onAddNode }) {
  return (
    <div style={{
      width: 160, flexShrink: 0,
      backgroundColor: S.bgCard,
      borderRight: `1px solid ${S.border}`,
      display: "flex", flexDirection: "column",
      padding: "12px 8px", gap: 4,
      overflowY: "auto",
    }}>
      <p style={{ fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 700, marginBottom: 8, paddingLeft: 4 }}>
        Nodes
      </p>

      {NODE_TYPES.map(nt => (
        <div
          key={nt.type}
          draggable
          onClick={() => onAddNode(nt.type)}
          onDragStart={e => {
            e.dataTransfer.setData("new_node_type", nt.type);
            e.dataTransfer.effectAllowed = "copy";
          }}
          style={{
            display: "flex", alignItems: "center", gap: 8,
            padding: "8px 10px", borderRadius: 6, cursor: "grab",
            border: `1px solid ${nt.color}33`,
            backgroundColor: nt.color + "0c",
            color: S.textMain, fontSize: 11, fontWeight: 500,
            textAlign: "left", width: "100%",
            transition: "all 0.15s", userSelect: "none",
          }}
          onMouseEnter={e => {
            e.currentTarget.style.backgroundColor = nt.color + "20";
            e.currentTarget.style.borderColor = nt.color + "66";
          }}
          onMouseLeave={e => {
            e.currentTarget.style.backgroundColor = nt.color + "0c";
            e.currentTarget.style.borderColor = nt.color + "33";
          }}
          title={`${nt.desc} – Ziehen oder Klicken`}
        >
          <span style={{ fontSize: 14, flexShrink: 0 }}>{nt.icon}</span>
          <div>
            <p style={{ margin: 0, fontSize: 11, fontWeight: 600, color: S.textBright }}>{nt.label}</p>
            <p style={{ margin: 0, fontSize: 9, color: S.textDim, marginTop: 1 }}>{nt.desc}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
