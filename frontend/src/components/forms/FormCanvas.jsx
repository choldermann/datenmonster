import { useState, useRef } from "react";
import { Plus } from "lucide-react";
import FieldCard from "./FieldCard";
import { newField } from "./fieldTypes";

const S = {
  bgMain: "var(--bg-main)", bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)",
  border: "var(--border)", textDim: "var(--text-dim)", accent: "var(--accent)",
};

function groupByRow(fields) {
  const rowMap = {};
  for (const f of fields) {
    const r = f.row ?? 0;
    if (!rowMap[r]) rowMap[r] = [];
    rowMap[r].push(f);
  }
  return Object.entries(rowMap)
    .sort(([a], [b]) => Number(a) - Number(b))
    .map(([row, items]) => ({ row: Number(row), items }));
}

export default function FormCanvas({ fields, selectedId, onSelect, onChange }) {
  const [dragOverRow, setDragOverRow] = useState(null);
  const dragFieldId = useRef(null);
  const dragFromRow = useRef(null);

  const maxRow = fields.length > 0 ? Math.max(...fields.map(f => f.row ?? 0)) : -1;

  const addFieldAtRow = (type, row) => {
    const f = newField(type, row);
    // Wenn eine Zeile schon Felder hat: colSpan anpassen damit's reinpasst
    const rowFields = fields.filter(x => x.row === row);
    if (rowFields.length > 0) {
      const usedCols = rowFields.reduce((s, x) => s + (x.colSpan ?? 6), 0);
      const remaining = 12 - usedCols;
      if (remaining <= 0) {
        // Neue Zeile darunter
        f.row = row + 1;
        // Alle Felder darunter eine Zeile nach unten
        return [...fields.map(x => x.row > row ? { ...x, row: x.row + 1 } : x), f];
      }
      f.colSpan = Math.min(f.colSpan, remaining);
    }
    return [...fields, f];
  };

  const handleCanvasDrop = (e, targetRow) => {
    e.preventDefault();
    setDragOverRow(null);
    const fieldType = e.dataTransfer.getData("field_type");
    if (fieldType) {
      const row = targetRow ?? maxRow + 1;
      onChange(addFieldAtRow(fieldType, row));
      return;
    }
    // Reorder innerhalb des Canvas
    const movingId = dragFieldId.current;
    if (movingId && targetRow !== null && targetRow !== dragFromRow.current) {
      onChange(fields.map(f => f.id === movingId ? { ...f, row: targetRow } : f));
      dragFieldId.current = null; dragFromRow.current = null;
    }
  };

  const handleDeleteField = (id) => {
    onChange(fields.filter(f => f.id !== id));
    if (selectedId === id) onSelect(null);
  };

  const rows = groupByRow(fields);

  // Neue Zeile nach letzter
  const addRowZone = (
    <div onDragOver={e => { e.preventDefault(); setDragOverRow("new"); }}
      onDragLeave={() => setDragOverRow(null)}
      onDrop={e => handleCanvasDrop(e, maxRow + 1)}
      style={{ margin: "6px 0", border: `2px dashed ${dragOverRow === "new" ? S.accent : "transparent"}`,
        borderRadius: 8, padding: "10px 0", transition: "border-color 0.15s",
        display: "flex", alignItems: "center", justifyContent: "center" }}>
      {dragOverRow === "new" ? (
        <span style={{ fontSize: 11, color: S.accent }}>Feld hier ablegen</span>
      ) : (
        <span style={{ fontSize: 10, color: S.textDim, opacity: 0.4, display: "flex", alignItems: "center", gap: 4 }}>
          <Plus size={10} /> Feld aus Palette ziehen
        </span>
      )}
    </div>
  );

  if (fields.length === 0) {
    return (
      <div style={{ flex: 1, overflowY: "auto", padding: "24px 20px" }}
        onDragOver={e => { e.preventDefault(); setDragOverRow("new"); }}
        onDragLeave={() => setDragOverRow(null)}
        onDrop={e => handleCanvasDrop(e, 0)}
        onClick={() => onSelect(null)}>
        <div style={{ border: `2px dashed ${dragOverRow === "new" ? S.accent : S.border}`,
          borderRadius: 12, padding: "60px 40px", textAlign: "center",
          backgroundColor: dragOverRow === "new" ? "rgba(252,228,153,0.04)" : "transparent",
          transition: "all 0.15s" }}>
          <div style={{ fontSize: 32, marginBottom: 12, opacity: 0.2 }}>⊞</div>
          <p style={{ color: S.textDim, fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
            Felder aus der Palette hierher ziehen
          </p>
          <p style={{ color: S.textDim, fontSize: 11, opacity: 0.7, lineHeight: 1.6 }}>
            Text, Datum, Dropdown, Button und viele mehr
          </p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px", scrollbarWidth: "thin" }}
      onClick={() => onSelect(null)}>

      {rows.map(({ row, items }) => (
        <div key={row}>
          {/* Drop-Zone über Zeile */}
          <div onDragOver={e => { e.preventDefault(); setDragOverRow(`above-${row}`); }}
            onDragLeave={() => setDragOverRow(null)}
            onDrop={e => {
              e.preventDefault();
              setDragOverRow(null);
              const type = e.dataTransfer.getData("field_type");
              if (type) {
                // Zeile einfügen: alle Zeilen ab hier verschieben
                const shifted = fields.map(f => f.row >= row ? { ...f, row: f.row + 1 } : f);
                onChange([...shifted, newField(type, row)]);
              }
            }}
            style={{ height: dragOverRow === `above-${row}` ? 28 : 6,
              margin: "0 -4px", borderRadius: 4, transition: "height 0.15s",
              border: `2px dashed ${dragOverRow === `above-${row}` ? S.accent : "transparent"}`,
              display: "flex", alignItems: "center", justifyContent: "center" }}>
            {dragOverRow === `above-${row}` && (
              <span style={{ fontSize: 10, color: S.accent }}>Neue Zeile hier einfügen</span>
            )}
          </div>

          {/* Zeile mit Feldern */}
          <div style={{ display: "flex", flexWrap: "wrap", margin: "0 -4px", minHeight: 56,
            padding: "2px 0", position: "relative" }}
            onDragOver={e => { e.preventDefault(); setDragOverRow(row); }}
            onDragLeave={() => setDragOverRow(null)}
            onDrop={e => handleCanvasDrop(e, row)}>

            {items.map(field => (
              <FieldCard
                key={field.id}
                field={field}
                selected={selectedId === field.id}
                onClick={() => onSelect(field.id)}
                onDelete={() => handleDeleteField(field.id)}
                dragHandleProps={{
                  draggable: true,
                  onDragStart: (e) => {
                    dragFieldId.current = field.id;
                    dragFromRow.current = row;
                    e.dataTransfer.effectAllowed = "move";
                  },
                }}
              />
            ))}
          </div>
        </div>
      ))}

      {addRowZone}
    </div>
  );
}
