import { useState, useEffect } from "react";
import { X, Loader2, CheckCircle, ChevronRight, ChevronDown, FileText } from "lucide-react";
import api from "../api/client";

const S = {
  accent: "var(--accent)", bgMain: "var(--bg-main)", bgCard: "var(--bg-card)",
  bgEl: "var(--bg-elevated)", border: "var(--border)", textMain: "var(--text-main)",
  textBright: "var(--text-bright)", textDim: "var(--text-dim)",
};

// ─── Rekursiver Baum-Knoten ───────────────────────────────────────────────────
function TreeNode({ node, path, selectedNode, onSelect, depth = 0 }) {
  const [open, setOpen] = useState(depth < 2);
  const hasChildren = node.children && node.children.length > 0;
  const isSelected = selectedNode === path;
  const indent = depth * 16;

  return (
    <div>
      <div
        className="flex items-center gap-1.5 py-1.5 px-2 rounded cursor-pointer transition-all"
        style={{
          marginLeft: `${indent}px`,
          backgroundColor: isSelected ? "rgba(252,228,153,0.1)" : "transparent",
          border: `1px solid ${isSelected ? S.accent : "transparent"}`,
        }}
        onMouseEnter={(e) => { if (!isSelected) e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.03)"; }}
        onMouseLeave={(e) => { if (!isSelected) e.currentTarget.style.backgroundColor = "transparent"; }}
      >
        {/* Toggle */}
        <button
          onClick={() => setOpen((o) => !o)}
          className="shrink-0 w-4 h-4 flex items-center justify-center"
          style={{ color: S.textDim, visibility: hasChildren ? "visible" : "hidden" }}
        >
          {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        </button>

        {/* Node name */}
        <button
          onClick={() => onSelect(path)}
          className="flex-1 text-left flex items-center gap-2 min-w-0"
        >
          <span
            className="text-xs font-mono truncate"
            style={{ color: isSelected ? S.accent : S.textBright }}
          >
            {node.tag}
          </span>
          {node.attributes?.length > 0 && (
            <span className="text-xs shrink-0" style={{ color: S.textDim }}>
              @{node.attributes.join(", @")}
            </span>
          )}
          {node.has_text && (
            <span className="text-xs shrink-0" style={{ color: S.textDim }}>„…"</span>
          )}
        </button>

        {isSelected && (
          <CheckCircle size={12} className="shrink-0" style={{ color: S.accent }} />
        )}
      </div>

      {open && hasChildren && node.children.map((child, i) => (
        <TreeNode
          key={i}
          node={child}
          path={path ? `${path}/${child.tag}` : child.tag}
          selectedNode={selectedNode}
          onSelect={onSelect}
          depth={depth + 1}
        />
      ))}
    </div>
  );
}

// ─── Hauptkomponente ──────────────────────────────────────────────────────────
export default function XmlConfigurator({ dataset, onDone, onCancel }) {
  const [step, setStep] = useState("tree"); // "tree" | "refs"
  const [structure, setStructure] = useState(null);
  const [loadingTree, setLoadingTree] = useState(true);
  const [selectedNode, setSelectedNode] = useState("");

  const [refFields, setRefFields] = useState([]);       // available ref fields
  const [loadingRefs, setLoadingRefs] = useState(false);
  const [selectedRefs, setSelectedRefs] = useState([]); // checked ref fields

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // Lade XML-Struktur
  useEffect(() => {
    api.get(`/api/datasets/${dataset.id}/xml-structure`)
      .then(({ data }) => { setStructure(data); setLoadingTree(false); })
      .catch((e) => {
        setError(e.response?.data?.detail || "Fehler beim Laden der XML-Struktur");
        setLoadingTree(false);
      });
  }, [dataset.id]);

  // Wenn Zielknoten gewählt → Referenzfelder laden
  const handleNodeSelect = async (path) => {
    // Pfad ohne Root-Tag (der Baum startet beim root-kind)
    setSelectedNode(path);
    setSelectedRefs([]);
    setRefFields([]);
  };

  const handleWeiter = async () => {
    if (!selectedNode) return;
    setLoadingRefs(true);
    setError("");
    try {
      const { data } = await api.post(`/api/datasets/${dataset.id}/xml-node-fields`, {
        node_path: selectedNode,
      });
      setRefFields(data.fields || []);
      setStep("refs");
    } catch (e) {
      setError(e.response?.data?.detail || "Fehler beim Laden der Referenzfelder");
    } finally {
      setLoadingRefs(false);
    }
  };

  const toggleRef = (field) => {
    setSelectedRefs((prev) =>
      prev.includes(field) ? prev.filter((f) => f !== field) : [...prev, field]
    );
  };

  const handleSave = async () => {
    setSaving(true);
    setError("");
    try {
      await api.post(`/api/datasets/${dataset.id}/xml-configure`, {
        target_node: selectedNode,
        ref_fields: selectedRefs,
      });
      onDone();
    } catch (e) {
      setError(e.response?.data?.detail || "Fehler beim Importieren");
      setSaving(false);
    }
  };

  const rootNode = structure ? { tag: structure.root, ...structure.tree } : null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: "rgba(0,0,0,0.8)", backdropFilter: "blur(4px)" }}
    >
      <div
        className="w-full max-w-xl flex flex-col rounded-lg overflow-hidden"
        style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`, maxHeight: "85vh" }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 shrink-0"
          style={{ borderBottom: `1px solid ${S.border}` }}>
          <div>
            <h2 className="text-sm font-semibold" style={{ color: S.textBright }}>XML konfigurieren</h2>
            <p className="text-xs mt-0.5" style={{ color: S.textDim }}>{dataset.original_filename}</p>
          </div>
          <button onClick={onCancel} style={{ color: S.textDim }}
            onMouseEnter={(e) => (e.currentTarget.style.color = S.textMain)}
            onMouseLeave={(e) => (e.currentTarget.style.color = S.textDim)}>
            <X size={16} />
          </button>
        </div>

        {/* Step indicator */}
        <div className="flex shrink-0" style={{ borderBottom: `1px solid ${S.border}` }}>
          {["tree", "refs"].map((s, i) => (
            <div key={s} className="flex-1 px-5 py-2.5 flex items-center gap-2"
              style={{ borderBottom: `2px solid ${step === s ? S.accent : "transparent"}` }}>
              <span className="text-xs font-mono px-1.5 py-0.5 rounded"
                style={{
                  backgroundColor: step === s ? S.accent : S.bgEl,
                  color: step === s ? "#111" : S.textDim,
                }}>
                {i + 1}
              </span>
              <span className="text-xs" style={{ color: step === s ? S.textBright : S.textDim }}>
                {s === "tree" ? "Zielknoten wählen" : "Referenzfelder"}
              </span>
            </div>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 min-h-0 overflow-y-auto px-5 py-4" style={{ scrollbarWidth: "thin" }}>

          {/* ── Schritt 1: Baumstruktur ── */}
          {step === "tree" && (
            <>
              <p className="text-xs mb-4" style={{ color: S.textDim }}>
                Wähle den Knoten, dessen Kinder als Tabellenzeilen importiert werden:
              </p>
              {loadingTree ? (
                <div className="flex items-center justify-center py-12" style={{ color: S.textDim }}>
                  <Loader2 size={18} className="animate-spin mr-2" /> Analysiere XML...
                </div>
              ) : error && !structure ? (
                <p className="text-xs py-4 text-center" style={{ color: "#e07070" }}>{error}</p>
              ) : rootNode ? (
                <div className="rounded" style={{ border: `1px solid ${S.border}` }}>
                  <div className="p-3">
                    {rootNode.children?.map((child, i) => (
                      <TreeNode
                        key={i}
                        node={child}
                        path={child.tag}
                        selectedNode={selectedNode}
                        onSelect={handleNodeSelect}
                        depth={0}
                      />
                    ))}
                  </div>
                </div>
              ) : null}

              {selectedNode && (
                <div className="mt-4 px-3 py-2.5 rounded flex items-center gap-2"
                  style={{ backgroundColor: "rgba(252,228,153,0.08)", border: `1px solid ${S.accent}` }}>
                  <FileText size={13} style={{ color: S.accent }} />
                  <span className="text-xs font-mono" style={{ color: S.accent }}>{selectedNode}</span>
                </div>
              )}
            </>
          )}

          {/* ── Schritt 2: Referenzfelder ── */}
          {step === "refs" && (
            <>
              <p className="text-xs mb-1" style={{ color: S.textDim }}>
                Zielknoten: <span className="font-mono" style={{ color: S.accent }}>{selectedNode}</span>
              </p>
              <p className="text-xs mb-4" style={{ color: S.textDim }}>
                Optionale Felder aus übergeordneten Knoten mitimportieren:
              </p>

              {loadingRefs ? (
                <div className="flex items-center justify-center py-8" style={{ color: S.textDim }}>
                  <Loader2 size={16} className="animate-spin mr-2" /> Lade Felder...
                </div>
              ) : refFields.length === 0 ? (
                <div className="text-center py-8" style={{ color: S.textDim }}>
                  <p className="text-xs">Keine übergeordneten Felder verfügbar.</p>
                  <p className="text-xs mt-1">Du kannst direkt importieren.</p>
                </div>
              ) : (
                <div className="flex flex-col gap-1">
                  {refFields.map((field) => {
                    const checked = selectedRefs.includes(field);
                    return (
                      <label key={field}
                        className="flex items-center gap-3 px-3 py-2 rounded cursor-pointer transition-all"
                        style={{
                          backgroundColor: checked ? "rgba(252,228,153,0.06)" : S.bgEl,
                          border: `1px solid ${checked ? S.accent : S.border}`,
                        }}
                        onMouseEnter={(e) => { if (!checked) e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.03)"; }}
                        onMouseLeave={(e) => { if (!checked) e.currentTarget.style.backgroundColor = S.bgEl; }}>
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleRef(field)}
                          className="shrink-0"
                          style={{ accentColor: S.accent, width: "13px", height: "13px" }}
                        />
                        <span className="text-xs font-mono" style={{ color: checked ? S.accent : S.textMain }}>
                          {field}
                        </span>
                      </label>
                    );
                  })}
                </div>
              )}

              {selectedRefs.length > 0 && (
                <p className="text-xs mt-3" style={{ color: S.textDim }}>
                  {selectedRefs.length} Referenzfeld{selectedRefs.length !== 1 ? "er" : ""} werden als{" "}
                  <span className="font-mono" style={{ color: S.accent }}>_ref_*</span>-Spalten hinzugefügt.
                </p>
              )}
            </>
          )}

          {error && step === "refs" && (
            <p className="text-xs mt-3" style={{ color: "#e07070" }}>{error}</p>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center gap-3 px-5 py-4 shrink-0"
          style={{ borderTop: `1px solid ${S.border}` }}>

          {step === "tree" && (
            <>
              <button onClick={onCancel} className="btn-ghost text-xs">Abbrechen</button>
              <button
                onClick={handleWeiter}
                disabled={!selectedNode || loadingRefs}
                className="btn-primary text-xs ml-auto"
              >
                {loadingRefs
                  ? <Loader2 size={12} className="animate-spin" />
                  : <ChevronRight size={12} />}
                Weiter
              </button>
            </>
          )}

          {step === "refs" && (
            <>
              <button onClick={() => setStep("tree")} className="btn-ghost text-xs">Zurück</button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="btn-primary text-xs ml-auto"
              >
                {saving
                  ? <Loader2 size={12} className="animate-spin" />
                  : <CheckCircle size={12} />}
                Importieren
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
