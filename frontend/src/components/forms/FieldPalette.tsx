import { FIELD_GROUPS, newField } from "./fieldTypes";
import AiFieldSuggest from "./AiFieldSuggest";

const S = {
  bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)", border: "var(--border)",
  textDim: "var(--text-dim)", textMain: "var(--text-main)",
};

interface Props {
  existingFields?: { name?: string; type: string }[];
  onAddFields?: (fields: ReturnType<typeof newField>[]) => void;
  maxRow?: number;
}

export default function FieldPalette({ existingFields = [], onAddFields, maxRow = 0 }: Props) {
  return (
    <div style={{ width: 180, flexShrink: 0, borderRight: `1px solid ${S.border}`,
      backgroundColor: S.bgCard, display: "flex", flexDirection: "column",
      overflowY: "auto", scrollbarWidth: "thin" }}>

      <div style={{ padding: "10px 12px 6px", borderBottom: `1px solid ${S.border}` }}>
        <p style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase",
          letterSpacing: "0.12em", color: S.textDim, margin: 0 }}>
          Felder
        </p>
      </div>

      {FIELD_GROUPS.map(group => (
        <div key={group.id}>
          <div style={{ padding: "8px 12px 4px",
            fontSize: 9, fontWeight: 700, textTransform: "uppercase",
            letterSpacing: "0.1em", color: S.textDim, opacity: 0.6 }}>
            {group.label}
          </div>
          {group.types.map(ft => (
            <div key={ft.type} draggable
              onDragStart={e => {
                e.dataTransfer.setData("field_type", ft.type);
                e.dataTransfer.effectAllowed = "copy";
              }}
              style={{ display: "flex", alignItems: "center", gap: 8,
                padding: "6px 12px", cursor: "grab", userSelect: "none",
                borderLeft: "2px solid transparent",
                transition: "background-color 0.1s" }}
              onMouseEnter={e => {
                e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.04)";
                e.currentTarget.style.borderLeftColor = ft.color;
              }}
              onMouseLeave={e => {
                e.currentTarget.style.backgroundColor = "";
                e.currentTarget.style.borderLeftColor = "transparent";
              }}>
              <div style={{ width: 22, height: 22, borderRadius: 4, flexShrink: 0,
                backgroundColor: `${ft.color}18`, border: `1px solid ${ft.color}33`,
                display: "flex", alignItems: "center", justifyContent: "center" }}>
                <ft.Icon size={11} style={{ color: ft.color }} />
              </div>
              <span style={{ fontSize: 11, color: S.textMain }}>{ft.label}</span>
            </div>
          ))}
        </div>
      ))}

      {onAddFields && (
        <AiFieldSuggest
          existingFields={existingFields}
          onAddFields={onAddFields}
          maxRow={maxRow}
        />
      )}
    </div>
  );
}
