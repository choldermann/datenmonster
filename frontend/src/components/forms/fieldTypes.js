import {
  Type, AlignLeft, Hash, Calendar, Clock, CheckSquare, ToggleLeft,
  ChevronDown, List, Circle, Paperclip, Play, Tag, Heading, Minus, Square, Layers,
} from "lucide-react";

export const FIELD_GROUPS = [
  {
    id: "input",
    label: "Eingabe",
    types: [
      { type: "text",     label: "Textfeld",          Icon: Type,        color: "#6ee7b7", defaultColSpan: 6 },
      { type: "textarea", label: "Mehrzeiliger Text", Icon: AlignLeft,   color: "#6ee7b7", defaultColSpan: 12 },
      { type: "number",   label: "Zahl",              Icon: Hash,        color: "#93c5fd", defaultColSpan: 4 },
      { type: "date",     label: "Datum",             Icon: Calendar,    color: "#fcd34d", defaultColSpan: 4 },
      { type: "time",     label: "Uhrzeit",           Icon: Clock,       color: "#fcd34d", defaultColSpan: 3 },
      { type: "file",     label: "Dateiauswahl",      Icon: Paperclip,   color: "#c4b5fd", defaultColSpan: 12 },
    ],
  },
  {
    id: "select",
    label: "Auswahl",
    types: [
      { type: "checkbox",    label: "Checkbox",          Icon: CheckSquare, color: "#6ee7b7", defaultColSpan: 4 },
      { type: "switch",      label: "Switch",            Icon: ToggleLeft,  color: "#6ee7b7", defaultColSpan: 4 },
      { type: "dropdown",    label: "Dropdown",          Icon: ChevronDown, color: "#f9a8d4", defaultColSpan: 6 },
      { type: "multiselect", label: "Mehrfachauswahl",  Icon: List,        color: "#f9a8d4", defaultColSpan: 8 },
      { type: "radio",       label: "Radio Buttons",    Icon: Circle,      color: "#f9a8d4", defaultColSpan: 6 },
    ],
  },
  {
    id: "action",
    label: "Aktionen",
    types: [
      { type: "button", label: "Button", Icon: Play, color: "#fb923c", defaultColSpan: 3 },
    ],
  },
  {
    id: "layout",
    label: "Layout",
    types: [
      { type: "heading",   label: "Überschrift",  Icon: Heading, color: "#a78bfa", defaultColSpan: 12 },
      { type: "label",     label: "Text / Label", Icon: Tag,     color: "#a78bfa", defaultColSpan: 12 },
      { type: "divider",   label: "Trennlinie",   Icon: Minus,   color: "#475569", defaultColSpan: 12 },
      { type: "container", label: "Container",    Icon: Square,  color: "#64748b", defaultColSpan: 12 },
    ],
  },
];

export const ALL_FIELD_TYPES = FIELD_GROUPS.flatMap(g => g.types);

export function getFieldDef(type) {
  return ALL_FIELD_TYPES.find(f => f.type === type) || { type, label: type, color: "#6b7280", defaultColSpan: 6 };
}

export function newField(type, rowIndex = 0) {
  const def = getFieldDef(type);
  const id = Math.random().toString(36).slice(2, 9);
  const base = {
    id,
    type,
    row: rowIndex,
    colSpan: def.defaultColSpan,
    label: def.label,
    name: `${type}_${id.slice(0, 4)}`,
    required: false,
    placeholder: "",
    default: "",
    options: [],
    action_id: "",
    content: "",
  };
  // Type-spezifische Defaults
  if (type === "heading") base.content = "Überschrift";
  if (type === "label")   base.content = "Text";
  if (type === "button")  { base.label = "Ausführen"; base.name = ""; }
  if (type === "dropdown" || type === "multiselect" || type === "radio") {
    base.options = [
      { value: "option1", label: "Option 1" },
      { value: "option2", label: "Option 2" },
    ];
  }
  return base;
}
