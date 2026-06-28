/**
 * XmlTemplateEditor – vollständiger XML-Template-Editor
 * - Visueller Baumstruktur-Editor (links)
 * - Live XML-Vorschau (rechts)
 * - XSD-Import (parst Elemente + Attribute)
 * - Felder zuweisen als Textinhalt oder Attributwert
 * - Beliebig tiefe Verschachtelung
 * - Drag & Drop zum Umsortieren
 */
import { useState, useCallback, useRef, useId } from "react";

const S = {
  accent: "var(--accent)",
  bgMain: "var(--bg-main)",
  bgCard: "var(--bg-card)",
  bgEl: "var(--bg-el)",
  border: "var(--border)",
  textMain: "var(--text-main)",
  textDim: "var(--text-dim)",
  textBright: "var(--text-bright)",
};

const ELEM_COLOR  = "#7dd3fc";  // light blue – XML elements
const ATTR_COLOR  = "#fbbf24";  // amber – attributes
const TEXT_COLOR  = "#6ee7b7";  // green – text content / mapped fields
const OPT_COLOR   = "#c084fc";  // purple – optional marker

// ─── Helpers ──────────────────────────────────────────────────────────────────

function genId() {
  return Math.random().toString(36).slice(2, 9);
}

/** Build a sample XML string from the node tree + a few mock rows */
function buildXmlPreview(tree, fields, mockRows = null) {
  const rows = mockRows || [
    Object.fromEntries(fields.map((f) => [f, `(${f})`])),
  ];

  const renderNode = (node, row, indent) => {
    const pad = "  ".repeat(indent);
    const attrStr = (node.attributes || [])
      .map((a) => {
        const val = a.fieldBinding ? row[a.fieldBinding] ?? `(${a.fieldBinding})` : a.staticValue ?? "";
        return ` ${a.name}="${escXml(val)}"`;
      })
      .join("");

    if (!node.children?.length && !node.fieldBinding && !node.staticValue) {
      // Empty element
      return `${pad}<${node.tag}${attrStr}/>`;
    }

    const content = node.fieldBinding
      ? escXml(row[node.fieldBinding] ?? `(${node.fieldBinding})`)
      : node.staticValue
      ? escXml(node.staticValue)
      : null;

    if (content !== null && !node.children?.length) {
      return `${pad}<${node.tag}${attrStr}>${content}</${node.tag}>`;
    }

    const childLines = (node.children || [])
      .map((c) => renderNode(c, row, indent + 1))
      .join("\n");

    return `${pad}<${node.tag}${attrStr}>\n${childLines}\n${pad}</${node.tag}>`;
  };

  const rootNode = tree;
  if (!rootNode) return "<!-- Kein Root-Element definiert -->";

  const rowLines = rows
    .slice(0, 2)
    .map((row) =>
      rootNode.isRepeating
        ? renderNode(rootNode, row, 0)
        : renderNode(rootNode, row, 0)
    )
    .join("\n");

  return `<?xml version="1.0" encoding="UTF-8"?>\n${rowLines}`;
}

function escXml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ─── XSD Parser ───────────────────────────────────────────────────────────────

function parseXsd(xmlText) {
  /**
   * Parses an XSD and returns a suggested tree structure.
   * Only handles the uploaded file – external refs become empty placeholders.
   */
  const parser = new DOMParser();
  const doc = parser.parseFromString(xmlText, "application/xml");
  const ns = "http://www.w3.org/2001/XMLSchema";

  const getAttr = (el, name) => el.getAttribute(name) || el.getAttribute(`xs:${name}`) || null;

  // Collect all top-level element definitions keyed by name
  const elementDefs = {};
  const complexTypeDefs = {};

  doc.querySelectorAll("schema > element").forEach((el) => {
    elementDefs[getAttr(el, "name")] = el;
  });
  doc.querySelectorAll("schema > complexType").forEach((ct) => {
    complexTypeDefs[getAttr(ct, "name")] = ct;
  });

  function buildNode(el, depth = 0) {
    if (depth > 8) return null; // safety

    const name = getAttr(el, "name") || getAttr(el, "ref") || "element";
    const node = {
      id: genId(),
      tag: name,
      attributes: [],
      children: [],
      fieldBinding: null,
      staticValue: null,
      isRepeating: getAttr(el, "maxOccurs") === "unbounded",
      isOptional: getAttr(el, "minOccurs") === "0",
    };

    // Get complex type – inline or referenced
    let ct = el.querySelector(":scope > complexType");
    const typeRef = getAttr(el, "type");
    if (!ct && typeRef && complexTypeDefs[typeRef]) {
      ct = complexTypeDefs[typeRef];
    }

    if (ct) {
      // Attributes
      ct.querySelectorAll(":scope > attribute, sequence > attribute, all > attribute").forEach((a) => {
        const aName = getAttr(a, "name");
        if (aName) {
          node.attributes.push({
            id: genId(),
            name: aName,
            fieldBinding: null,
            staticValue: "",
            required: getAttr(a, "use") === "required",
          });
        }
      });

      // Child elements
      ct.querySelectorAll(":scope > sequence > element, :scope > all > element").forEach((child) => {
        const childName = getAttr(child, "name") || getAttr(child, "ref");
        if (!childName) return;

        // Try to resolve ref
        let resolvedEl = child;
        if (!getAttr(child, "name") && getAttr(child, "ref")) {
          resolvedEl = elementDefs[getAttr(child, "ref")] || child;
        }

        const childNode = buildNode(resolvedEl, depth + 1);
        if (childNode) {
          childNode.isRepeating = getAttr(child, "maxOccurs") === "unbounded";
          childNode.isOptional = getAttr(child, "minOccurs") === "0";
          node.children.push(childNode);
        }
      });
    }

    return node;
  }

  // Find root element
  const rootEl = doc.querySelector("schema > element");
  if (!rootEl) return null;

  return buildNode(rootEl, 0);
}

// ─── Default empty tree ───────────────────────────────────────────────────────

function defaultTree(rootTag = "Root", rowTag = "Row") {
  return {
    id: genId(),
    tag: rootTag,
    attributes: [],
    isRepeating: false,
    isOptional: false,
    fieldBinding: null,
    staticValue: null,
    children: [
      {
        id: genId(),
        tag: rowTag,
        attributes: [],
        isRepeating: true,
        isOptional: false,
        fieldBinding: null,
        staticValue: null,
        children: [],
      },
    ],
  };
}

// ─── Tree operations ──────────────────────────────────────────────────────────

function treeUpdate(node, id, updater) {
  if (node.id === id) return updater(node);
  return { ...node, children: (node.children || []).map((c) => treeUpdate(c, id, updater)) };
}

function treeDelete(node, id) {
  return {
    ...node,
    children: (node.children || [])
      .filter((c) => c.id !== id)
      .map((c) => treeDelete(c, id)),
  };
}

function treeInsertChild(node, parentId, newChild) {
  if (node.id === parentId) {
    return { ...node, children: [...(node.children || []), newChild] };
  }
  return { ...node, children: (node.children || []).map((c) => treeInsertChild(c, parentId, newChild)) };
}

// ─── Attribute Row ────────────────────────────────────────────────────────────

function AttrRow({ attr, fields, onChange, onDelete }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "3px 0" }}>
      <span style={{ color: ATTR_COLOR, fontSize: 10, flexShrink: 0 }}>@</span>
      <input value={attr.name} onChange={(e) => onChange({ ...attr, name: e.target.value })}
        style={{ width: 90, padding: "2px 6px", backgroundColor: S.bgMain, border: `1px solid ${S.border}`, borderRadius: 3, color: ATTR_COLOR, fontSize: 10, fontFamily: "monospace", outline: "none" }}
        placeholder="attribut" />
      <span style={{ color: S.textDim, fontSize: 10 }}>=</span>
      <select value={attr.fieldBinding ? `__field__${attr.fieldBinding}` : "__static__"}
        onChange={(e) => {
          if (e.target.value === "__static__") onChange({ ...attr, fieldBinding: null });
          else onChange({ ...attr, fieldBinding: e.target.value.replace("__field__", "") });
        }}
        style={{ flex: 1, padding: "2px 4px", backgroundColor: S.bgMain, border: `1px solid ${S.border}`, borderRadius: 3, color: S.textMain, fontSize: 10, outline: "none" }}>
        <option value="__static__">– Statischer Wert –</option>
        {fields.map((f) => <option key={f} value={`__field__${f}`}>{f}</option>)}
      </select>
      {!attr.fieldBinding && (
        <input value={attr.staticValue || ""} onChange={(e) => onChange({ ...attr, staticValue: e.target.value })}
          style={{ width: 80, padding: "2px 6px", backgroundColor: S.bgMain, border: `1px solid ${S.border}`, borderRadius: 3, color: S.textMain, fontSize: 10, outline: "none" }}
          placeholder="Wert" />
      )}
      {attr.required && <span style={{ fontSize: 9, color: "#f87171", flexShrink: 0 }}>*</span>}
      <button onClick={onDelete} style={{ color: S.textDim, flexShrink: 0, fontSize: 11, lineHeight: 1, background: "none", border: "none", cursor: "pointer" }}
        onMouseEnter={(e) => (e.currentTarget.style.color = "#f87171")}
        onMouseLeave={(e) => (e.currentTarget.style.color = S.textDim)}>✕</button>
    </div>
  );
}

// ─── Tree Node Row ────────────────────────────────────────────────────────────

function TreeNodeRow({ node, fields, depth, onUpdate, onDelete, onAddChild, dragRef, selectedId, onSelect }) {
  const [expanded, setExpanded] = useState(true);
  const [showAttrs, setShowAttrs] = useState(false);
  const isSelected = selectedId === node.id;
  const hasChildren = node.children?.length > 0;
  const indentPx = depth * 18;

  const updateAttr = (idx, updated) => {
    onUpdate({ ...node, attributes: node.attributes.map((a, i) => i === idx ? updated : a) });
  };
  const deleteAttr = (idx) => {
    onUpdate({ ...node, attributes: node.attributes.filter((_, i) => i !== idx) });
  };
  const addAttr = () => {
    onUpdate({ ...node, attributes: [...(node.attributes || []), { id: genId(), name: "attr", fieldBinding: null, staticValue: "", required: false }] });
  };

  return (
    <div>
      {/* Node row */}
      <div
        draggable
        onDragStart={(e) => { e.stopPropagation(); e.dataTransfer.setData("nodeId", node.id); }}
        onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); e.currentTarget.style.outline = `1px solid ${S.accent}`; }}
        onDragLeave={(e) => { e.currentTarget.style.outline = "none"; }}
        onDrop={(e) => {
          e.preventDefault(); e.stopPropagation();
          e.currentTarget.style.outline = "none";
          const draggedId = e.dataTransfer.getData("nodeId");
          if (draggedId && draggedId !== node.id) {
            dragRef.current = { draggedId, targetId: node.id };
          }
        }}
        onClick={() => onSelect(isSelected ? null : node.id)}
        style={{
          display: "flex", alignItems: "center", gap: 4,
          paddingLeft: indentPx + 6, paddingRight: 6, paddingTop: 3, paddingBottom: 3,
          cursor: "pointer", borderRadius: 3,
          backgroundColor: isSelected ? "rgba(252,228,153,0.1)" : "transparent",
          outline: isSelected ? `1px solid ${S.accent}44` : "none",
          userSelect: "none",
        }}
        onMouseEnter={(e) => { if (!isSelected) e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.03)"; }}
        onMouseLeave={(e) => { if (!isSelected) e.currentTarget.style.backgroundColor = "transparent"; }}
      >
        {/* Expand toggle */}
        <span onClick={(e) => { e.stopPropagation(); setExpanded((v) => !v); }}
          style={{ width: 14, flexShrink: 0, color: S.textDim, fontSize: 10, textAlign: "center" }}>
          {hasChildren ? (expanded ? "▼" : "▶") : "·"}
        </span>

        {/* Tag name */}
        <span style={{ color: ELEM_COLOR, fontSize: 11, fontFamily: "monospace", fontWeight: 600 }}>&lt;</span>
        <input value={node.tag} onClick={(e) => e.stopPropagation()}
          onChange={(e) => onUpdate({ ...node, tag: e.target.value })}
          style={{ background: "transparent", border: "none", outline: "none", color: ELEM_COLOR, fontSize: 11, fontFamily: "monospace", fontWeight: 600, width: Math.max(node.tag.length * 7.5, 60) }} />
        <span style={{ color: ELEM_COLOR, fontSize: 11, fontFamily: "monospace", fontWeight: 600 }}>&gt;</span>

        {/* Badges */}
        {node.isRepeating && <span style={{ fontSize: 9, color: OPT_COLOR, marginLeft: 2 }}>∞</span>}
        {node.isOptional && <span style={{ fontSize: 9, color: S.textDim, marginLeft: 2 }}>?</span>}

        {/* Field binding */}
        <div style={{ flex: 1, marginLeft: 6 }}>
          {!hasChildren && (
            <select value={node.fieldBinding ? `__f__${node.fieldBinding}` : "__none__"}
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => {
                const v = e.target.value;
                onUpdate({ ...node, fieldBinding: v === "__none__" ? null : v.replace("__f__", ""), staticValue: null });
              }}
              style={{ padding: "1px 4px", backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 3, color: node.fieldBinding ? TEXT_COLOR : S.textDim, fontSize: 10, outline: "none", maxWidth: 150 }}>
              <option value="__none__">– Feld zuweisen –</option>
              {fields.map((f) => <option key={f} value={`__f__${f}`}>{f}</option>)}
            </select>
          )}
          {!hasChildren && !node.fieldBinding && (
            <input value={node.staticValue || ""} onClick={(e) => e.stopPropagation()}
              onChange={(e) => onUpdate({ ...node, staticValue: e.target.value || null })}
              placeholder="statischer Text"
              style={{ marginLeft: 4, padding: "1px 6px", backgroundColor: "transparent", border: `1px solid transparent`, borderRadius: 3, color: S.textDim, fontSize: 10, outline: "none", width: 100 }}
              onFocus={(e) => (e.currentTarget.style.borderColor = S.border)}
              onBlur={(e) => (e.currentTarget.style.borderColor = "transparent")} />
          )}
        </div>

        {/* Actions */}
        <div style={{ display: "flex", gap: 3, flexShrink: 0 }} onClick={(e) => e.stopPropagation()}>
          <button title="Attribut hinzufügen" onClick={() => { addAttr(); setShowAttrs(true); setExpanded(true); }}
            style={{ fontSize: 9, padding: "1px 5px", borderRadius: 3, cursor: "pointer", backgroundColor: S.bgEl, border: `1px solid ${S.border}`, color: ATTR_COLOR }}>@+</button>
          <button title="Kindelement hinzufügen" onClick={() => { onAddChild(node.id); setExpanded(true); }}
            style={{ fontSize: 9, padding: "1px 5px", borderRadius: 3, cursor: "pointer", backgroundColor: S.bgEl, border: `1px solid ${S.border}`, color: ELEM_COLOR }}>+</button>
          <button title="Element löschen" onClick={() => onDelete(node.id)}
            style={{ fontSize: 9, padding: "1px 5px", borderRadius: 3, cursor: "pointer", backgroundColor: S.bgEl, border: `1px solid ${S.border}`, color: S.textDim }}
            onMouseEnter={(e) => (e.currentTarget.style.color = "#f87171")}
            onMouseLeave={(e) => (e.currentTarget.style.color = S.textDim)}>✕</button>
        </div>
      </div>

      {/* Attributes */}
      {expanded && node.attributes?.length > 0 && (
        <div style={{ paddingLeft: indentPx + 28, paddingRight: 8, paddingBottom: 2 }}>
          {node.attributes.map((a, idx) => (
            <AttrRow key={a.id} attr={a} fields={fields}
              onChange={(updated) => updateAttr(idx, updated)}
              onDelete={() => deleteAttr(idx)} />
          ))}
        </div>
      )}

      {/* Children */}
      {expanded && node.children?.map((child) => (
        <TreeNodeRow
          key={child.id} node={child} fields={fields} depth={depth + 1}
          onUpdate={(updated) => onUpdate({ ...node, children: node.children.map((c) => c.id === updated.id ? updated : c) })}
          onDelete={onDelete} onAddChild={onAddChild}
          dragRef={dragRef} selectedId={selectedId} onSelect={onSelect}
        />
      ))}
    </div>
  );
}

// ─── Main XmlTemplateEditor ───────────────────────────────────────────────────

export default function XmlTemplateEditor({ fields, template, onChange, onClose }) {
  const [tree, setTree] = useState(() => {
    if (template?.tree) return template.tree;
    return defaultTree("Root", "Row");
  });
  const [selectedId, setSelectedId] = useState(null);
  const [xsdError, setXsdError] = useState(null);
  const dragRef = useRef(null);
  const fileInputRef = useRef(null);

  // Live XML preview
  const xmlPreview = buildXmlPreview(tree, fields);

  const updateTree = useCallback((updater) => {
    setTree((prev) => updater(prev));
  }, []);

  const handleNodeUpdate = useCallback((updated) => {
    setTree((prev) => treeUpdate(prev, updated.id, () => updated));
  }, []);

  const handleNodeDelete = useCallback((id) => {
    setTree((prev) => {
      if (prev.id === id) return defaultTree();
      return treeDelete(prev, id);
    });
  }, []);

  const handleAddChild = useCallback((parentId) => {
    const newNode = { id: genId(), tag: "Element", attributes: [], children: [], fieldBinding: null, staticValue: null, isRepeating: false, isOptional: false };
    setTree((prev) => treeInsertChild(prev, parentId, newNode));
  }, []);

  // Drag & drop reorder (simple: move dragged as last child of target)
  const handleDragEnd = useCallback(() => {
    if (!dragRef.current) return;
    const { draggedId, targetId } = dragRef.current;
    dragRef.current = null;
    // Find dragged node, remove, insert as child of target
    setTree((prev) => {
      let draggedNode = null;
      const findAndRemove = (n) => {
        const filtered = (n.children || []).filter((c) => {
          if (c.id === draggedId) { draggedNode = c; return false; }
          return true;
        }).map(findAndRemove);
        return { ...n, children: filtered };
      };
      const pruned = findAndRemove(prev);
      if (!draggedNode) return prev;
      return treeInsertChild(pruned, targetId, draggedNode);
    });
  }, []);

  // XSD Import
  const handleXsdImport = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setXsdError(null);
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const parsed = parseXsd(ev.target.result);
        if (!parsed) { setXsdError("Kein Root-Element in der XSD gefunden."); return; }
        setTree(parsed);
      } catch (err) {
        setXsdError(`XSD-Parse-Fehler: ${err.message}`);
      }
    };
    reader.readAsText(file);
    e.target.value = "";
  };

  const handleSave = () => {
    onChange({ ...template, tree });
    onClose();
  };

  // Syntax highlighting for XML preview
  const highlightXml = (xml) => {
    return xml
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      // Restore for coloring
      .replace(/&lt;\?([^?]*)\?&gt;/g, '<span style="color:#94a3b8">&lt;?$1?&gt;</span>')
      .replace(/&lt;!--([^]*?)--&gt;/g, '<span style="color:#64748b">&lt;!--$1--&gt;</span>')
      .replace(/&lt;\/(\w[\w.-]*)&gt;/g, '<span style="color:#7dd3fc">&lt;/$1&gt;</span>')
      .replace(/&lt;(\w[\w.-]*)((?:[^&]|&amp;|&quot;)*?)\/&gt;/g,
        '<span style="color:#7dd3fc">&lt;$1</span><span style="color:#fbbf24">$2</span><span style="color:#7dd3fc">/&gt;</span>')
      .replace(/&lt;(\w[\w.-]*)((?:[^&]|&amp;|&quot;)*?)&gt;/g,
        '<span style="color:#7dd3fc">&lt;$1</span><span style="color:#fbbf24">$2</span><span style="color:#7dd3fc">&gt;</span>')
      .replace(/(\w+)=&quot;([^&]*)&quot;/g,
        '<span style="color:#fbbf24">$1</span>=<span style="color:#6ee7b7">&quot;$2&quot;</span>');
  };

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 80, display: "flex", flexDirection: "column", backgroundColor: "rgba(0,0,0,0.85)" }} onClick={onClose}>
      <div style={{ margin: "24px auto", width: "92vw", maxWidth: 1200, height: "calc(100vh - 48px)", display: "flex", flexDirection: "column", backgroundColor: S.bgCard, borderRadius: 10, overflow: "hidden", border: `1px solid ${S.border}`, boxShadow: "0 32px 80px rgba(0,0,0,0.8)" }} onClick={(e) => e.stopPropagation()}>

        {/* ── Header ── */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 18px", borderBottom: `1px solid ${S.border}`, flexShrink: 0, backgroundColor: S.bgEl }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: S.textBright }}>XML-Template-Editor</span>
          <span style={{ fontSize: 11, color: S.textDim }}>{fields.length} Zielfelder verfügbar</span>

          <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
            {/* XSD Import */}
            <input ref={fileInputRef} type="file" accept=".xsd" style={{ display: "none" }} onChange={handleXsdImport} />
            <button onClick={() => fileInputRef.current?.click()}
              style={{ fontSize: 11, padding: "5px 12px", borderRadius: 4, cursor: "pointer", backgroundColor: "rgba(167,139,250,0.1)", border: "1px solid rgba(167,139,250,0.3)", color: "#c084fc" }}>
              ⬆ XSD importieren
            </button>
            <button onClick={() => { setTree(defaultTree()); }}
              style={{ fontSize: 11, padding: "5px 12px", borderRadius: 4, cursor: "pointer", backgroundColor: S.bgMain, border: `1px solid ${S.border}`, color: S.textDim }}>
              Zurücksetzen
            </button>
            <button onClick={handleSave}
              style={{ fontSize: 12, padding: "6px 18px", borderRadius: 4, cursor: "pointer", backgroundColor: S.accent, border: "none", color: "#111", fontWeight: 700 }}>
              Übernehmen
            </button>
            <button onClick={onClose} style={{ color: S.textDim, background: "none", border: "none", cursor: "pointer", fontSize: 16 }}>✕</button>
          </div>
        </div>

        {xsdError && (
          <div style={{ padding: "6px 18px", backgroundColor: "rgba(248,113,113,0.1)", borderBottom: `1px solid rgba(248,113,113,0.3)`, fontSize: 11, color: "#f87171" }}>
            ⚠ {xsdError}
          </div>
        )}

        {/* ── Legend ── */}
        <div style={{ display: "flex", gap: 16, padding: "6px 18px", borderBottom: `1px solid ${S.border}`, flexShrink: 0, backgroundColor: S.bgMain }}>
          <span style={{ fontSize: 10, color: S.textDim }}>Legende:</span>
          <span style={{ fontSize: 10, color: ELEM_COLOR, fontFamily: "monospace" }}>&lt;Element&gt;</span>
          <span style={{ fontSize: 10, color: ATTR_COLOR, fontFamily: "monospace" }}>@Attribut</span>
          <span style={{ fontSize: 10, color: TEXT_COLOR, fontFamily: "monospace" }}>Feldbindung</span>
          <span style={{ fontSize: 10, color: OPT_COLOR }}>∞ wiederholt</span>
          <span style={{ fontSize: 10, color: S.textDim }}>? optional</span>
          <span style={{ fontSize: 10, color: S.textDim, marginLeft: "auto" }}>
            Doppelklick = umbenennen · <strong>+</strong> = Kindelement · <strong>@+</strong> = Attribut · Drag = verschieben
          </span>
        </div>

        {/* ── Body: Tree + Preview ── */}
        <div style={{ flex: 1, minHeight: 0, display: "flex" }}>

          {/* LEFT: Tree Editor */}
          <div style={{ flex: "0 0 55%", overflowY: "auto", scrollbarWidth: "thin", borderRight: `1px solid ${S.border}`, padding: "10px 0" }} onDragEnd={handleDragEnd}>

            {/* Add root-level element button */}
            <div style={{ padding: "4px 10px 10px", borderBottom: `1px solid ${S.border}`, marginBottom: 6 }}>
              <button onClick={() => handleAddChild(tree.id)}
                style={{ fontSize: 10, padding: "4px 10px", borderRadius: 3, cursor: "pointer", backgroundColor: S.bgEl, border: `1px dashed ${S.border}`, color: S.textDim, width: "100%" }}>
                + Kindelement zu &lt;{tree.tag}&gt; hinzufügen
              </button>
            </div>

            <TreeNodeRow
              node={tree} fields={fields} depth={0}
              onUpdate={handleNodeUpdate}
              onDelete={handleNodeDelete}
              onAddChild={handleAddChild}
              dragRef={dragRef}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          </div>

          {/* RIGHT: XML Preview */}
          <div style={{ flex: "0 0 45%", display: "flex", flexDirection: "column", overflow: "hidden" }}>
            <div style={{ padding: "8px 14px", borderBottom: `1px solid ${S.border}`, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span style={{ fontSize: 10, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.08em" }}>Live XML-Vorschau</span>
              <span style={{ fontSize: 10, color: S.textDim }}>(mit Platzhaltern)</span>
            </div>
            <pre style={{ flex: 1, overflowY: "auto", overflowX: "auto", scrollbarWidth: "thin", margin: 0, padding: "14px 16px", fontSize: 11, lineHeight: 1.7, fontFamily: "monospace", backgroundColor: S.bgMain, color: S.textMain, whiteSpace: "pre" }}
              dangerouslySetInnerHTML={{ __html: highlightXml(xmlPreview) }}
            />
          </div>
        </div>

        {/* ── Footer ── */}
        <div style={{ padding: "8px 18px", borderTop: `1px solid ${S.border}`, flexShrink: 0, display: "flex", alignItems: "center", gap: 12, backgroundColor: S.bgEl }}>
          <span style={{ fontSize: 10, color: S.textDim }}>
            Tiefe: {countDepth(tree)} · Elemente: {countNodes(tree)} · Attribute: {countAttrs(tree)}
          </span>
          <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
            <button onClick={onClose} style={{ fontSize: 11, padding: "5px 14px", borderRadius: 4, cursor: "pointer", backgroundColor: S.bgMain, border: `1px solid ${S.border}`, color: S.textDim }}>Abbrechen</button>
            <button onClick={handleSave} style={{ fontSize: 12, padding: "6px 18px", borderRadius: 4, cursor: "pointer", backgroundColor: S.accent, border: "none", color: "#111", fontWeight: 700 }}>Übernehmen</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function countDepth(node, d = 0) {
  if (!node.children?.length) return d;
  return Math.max(...node.children.map((c) => countDepth(c, d + 1)));
}
function countNodes(node) {
  return 1 + (node.children || []).reduce((s, c) => s + countNodes(c), 0);
}
function countAttrs(node) {
  return (node.attributes?.length || 0) + (node.children || []).reduce((s, c) => s + countAttrs(c), 0);
}
