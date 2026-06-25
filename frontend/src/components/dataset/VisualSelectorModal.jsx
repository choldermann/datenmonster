import { useState, useEffect, useRef, useCallback } from "react";
import { createPortal } from "react-dom";
import { Globe, Loader2, MousePointer, Rows3, Plus, Trash2, Eye, Check, X, ChevronDown } from "lucide-react";
import api from "../../api/client";

// ── Farben ────────────────────────────────────────────────────────────────────
const S = {
  bg:       "#0f1117",
  bgCard:   "#161b27",
  bgEl:     "#1e2535",
  bgMain:   "#12161f",
  border:   "#232c40",
  accent:   "#fce499",
  green:    "#6ee7b7",
  textBright: "#f1f5f9",
  textMain:   "#94a3b8",
  textDim:    "#475569",
  red:      "#e07070",
};

const TRANSFORMS = [
  { value: "text",      label: "Text (innerText)" },
  { value: "html",      label: "HTML (innerHTML)" },
  { value: "attr:href", label: "Link-URL (href)" },
  { value: "attr:src",  label: "Bild-URL (src)" },
  { value: "attr:title",label: "title-Attribut" },
  { value: "attr:alt",  label: "alt-Attribut" },
];

function smartTransform(tagName) {
  if (tagName === "a")   return "attr:href";
  if (tagName === "img") return "attr:src";
  return "text";
}

// ── Kleines Inline-Formular nach Element-Klick ────────────────────────────────
function PendingFieldForm({ pending, onConfirm, onCancel }) {
  const [name, setName]           = useState("");
  const [transform, setTransform] = useState(() => smartTransform(pending.tagName));
  const inputRef = useRef(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  const iS = {
    backgroundColor: S.bgMain, border: `1px solid ${S.border}`,
    color: S.textBright, borderRadius: 4, padding: "5px 8px",
    width: "100%", outline: "none", fontSize: 11, fontFamily: "monospace",
  };

  return (
    <div style={{ padding: "10px 12px", borderRadius: 6, border: `1px solid ${S.accent}44`,
      backgroundColor: "rgba(252,228,153,0.06)", display: "flex", flexDirection: "column", gap: 8 }}>
      <p style={{ fontSize: 10, color: S.accent, fontWeight: 700, textTransform: "uppercase",
        letterSpacing: "0.08em" }}>Feld definieren</p>
      <div style={{ fontSize: 10, color: S.textDim, fontFamily: "monospace",
        backgroundColor: S.bgMain, padding: "4px 8px", borderRadius: 4, border: `1px solid ${S.border}` }}>
        {pending.selector}
      </div>
      {pending.sample && (
        <div style={{ fontSize: 10, color: S.textMain, fontStyle: "italic", lineHeight: 1.4 }}>
          "{pending.sample.slice(0, 60)}{pending.sample.length > 60 ? "…" : ""}"
        </div>
      )}
      <input ref={inputRef} style={iS} placeholder="Feldname (z.B. preis)" value={name}
        onChange={e => setName(e.target.value)}
        onKeyDown={e => { if (e.key === "Enter" && name.trim()) onConfirm(name.trim(), transform);
                          if (e.key === "Escape") onCancel(); }} />
      <select style={{ ...iS, cursor: "pointer" }} value={transform} onChange={e => setTransform(e.target.value)}>
        {TRANSFORMS.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
      </select>
      <div style={{ display: "flex", gap: 6 }}>
        <button onClick={() => name.trim() && onConfirm(name.trim(), transform)}
          disabled={!name.trim()}
          style={{ flex: 1, padding: "5px", borderRadius: 4, cursor: name.trim() ? "pointer" : "not-allowed",
            backgroundColor: name.trim() ? "rgba(252,228,153,0.15)" : "transparent",
            border: `1px solid ${name.trim() ? S.accent : S.border}`, color: name.trim() ? S.accent : S.textDim,
            fontSize: 11, fontWeight: 600 }}>
          <Check size={11} style={{ display: "inline", marginRight: 4 }} />Hinzufügen
        </button>
        <button onClick={onCancel}
          style={{ padding: "5px 10px", borderRadius: 4, cursor: "pointer",
            backgroundColor: "transparent", border: `1px solid ${S.border}`, color: S.textDim, fontSize: 11 }}>
          <X size={11} />
        </button>
      </div>
    </div>
  );
}

// ── Vorschau-Tabelle ──────────────────────────────────────────────────────────
function PreviewTable({ rows, columns }) {
  if (!rows || rows.length === 0) return (
    <div style={{ padding: "12px 16px", fontSize: 11, color: S.textDim, textAlign: "center" }}>
      Keine Daten extrahiert
    </div>
  );
  return (
    <div style={{ overflowX: "auto", maxHeight: 180 }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
        <thead>
          <tr style={{ backgroundColor: S.bgEl }}>
            {columns.map(c => (
              <th key={c} style={{ padding: "5px 10px", textAlign: "left", color: S.accent,
                fontWeight: 700, borderBottom: `1px solid ${S.border}`, whiteSpace: "nowrap",
                fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} style={{ borderBottom: `1px solid ${S.border}22`,
              backgroundColor: i % 2 === 0 ? "transparent" : S.bgEl + "44" }}>
              {columns.map(c => (
                <td key={c} style={{ padding: "4px 10px", color: S.textMain,
                  maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {String(row[c] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Haupt-Komponente ──────────────────────────────────────────────────────────
export default function VisualSelectorModal({ initialUrl = "", initialConfig = null, onSave, onClose }) {
  const [url, setUrl]                   = useState(initialUrl);
  const [loadedUrl, setLoadedUrl]       = useState("");
  const [iframeSrc, setIframeSrc]       = useState(null);
  const [pageLoading, setPageLoading]   = useState(false);
  const [pageError, setPageError]       = useState("");
  const [iframeReady, setIframeReady]   = useState(false);

  const [mode, setMode]                 = useState(null); // null | 'field' | 'row'
  const [fields, setFields]             = useState(() =>
    initialConfig?.selections?.map((s, i) => ({ id: `f${i}`, ...s })) || []);
  const [rowSelector, setRowSelector]   = useState(initialConfig?.row_selector || "");
  const [pending, setPending]           = useState(null);

  const [preview, setPreview]           = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState("");

  const iframeRef  = useRef(null);
  const blobUrlRef = useRef(null);

  // ── Seite laden ─────────────────────────────────────────────────────────────
  const loadPage = useCallback(async () => {
    if (!url.trim()) return;
    setPageLoading(true); setPageError(""); setIframeReady(false); setPreview(null);
    try {
      const { data } = await api.get("/api/plugins/web/proxy", {
        params: { url: url.trim() },
        responseType: "text",
      });
      if (blobUrlRef.current) URL.revokeObjectURL(blobUrlRef.current);
      const blob = new Blob([data], { type: "text/html" });
      const blobUrl = URL.createObjectURL(blob);
      blobUrlRef.current = blobUrl;
      setIframeSrc(blobUrl);
      setLoadedUrl(url.trim());
    } catch (e) {
      setPageError(e.response?.data?.detail || e.message || "Seite konnte nicht geladen werden");
    } finally {
      setPageLoading(false);
    }
  }, [url]);

  // Cleanup Blob-URL
  useEffect(() => () => { if (blobUrlRef.current) URL.revokeObjectURL(blobUrlRef.current); }, []);

  // Initiale URL sofort laden
  useEffect(() => { if (initialUrl) loadPage(); }, []); // eslint-disable-line

  // ── postMessage vom iframe empfangen ────────────────────────────────────────
  useEffect(() => {
    const handler = (e) => {
      const d = e.data;
      if (!d || typeof d !== "object") return;

      if (d.type === "dm_ready") {
        setIframeReady(true);
      }
      if (d.type === "dm_element_selected") {
        if (d.mode === "row") {
          setRowSelector(d.selector);
          sendCmd("set_mode", null);
          setMode(null);
        } else if (d.mode === "field") {
          setPending({ selector: d.selector, sample: d.sample, tagName: d.tagName, matches: d.matches });
          sendCmd("set_mode", null);
          setMode(null);
        }
      }
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, []);

  // Modus-Wechsel an iframe senden
  const sendCmd = (cmd, value) => {
    iframeRef.current?.contentWindow?.postMessage(
      { source: "datenmonster", cmd, mode: value }, "*"
    );
  };

  const activateMode = (newMode) => {
    if (mode === newMode) {
      setMode(null); sendCmd("set_mode", null);
    } else {
      setPending(null);
      setMode(newMode); sendCmd("set_mode", newMode);
    }
  };

  // ── Feld hinzufügen ──────────────────────────────────────────────────────────
  const confirmField = (name, transform) => {
    if (!pending) return;
    setFields(prev => [...prev, {
      id: `f${Date.now()}`,
      field_name: name,
      css_selector: pending.selector,
      transform,
      sample: pending.sample,
    }]);
    setPending(null);
  };

  const removeField = (id) => setFields(prev => prev.filter(f => f.id !== id));

  // ── Vorschau ─────────────────────────────────────────────────────────────────
  const handlePreview = async () => {
    if (!loadedUrl || fields.length === 0) return;
    setPreviewLoading(true); setPreviewError(""); setPreview(null);
    try {
      const cfg = {
        url: loadedUrl,
        extract_type: "css_selector",
        visual_selector_config: buildConfig(),
      };
      const { data } = await api.post("/api/plugins/web/preview", { config: cfg, limit: 10 });
      setPreview(data);
    } catch (e) {
      setPreviewError(e.response?.data?.detail || e.message);
    } finally {
      setPreviewLoading(false);
    }
  };

  // ── Konfiguration zusammenbauen ───────────────────────────────────────────
  const buildConfig = () => ({
    ...(rowSelector.trim() ? { row_selector: rowSelector.trim() } : {}),
    selections: fields.map(({ field_name, css_selector, transform }) =>
      ({ field_name, css_selector, transform })
    ),
  });

  const handleSave = () => {
    if (fields.length === 0) return;
    onSave(buildConfig(), loadedUrl || url);
  };

  // ── Styles ────────────────────────────────────────────────────────────────────
  const btnMode = (active) => ({
    display: "flex", alignItems: "center", gap: 5, padding: "6px 10px", borderRadius: 4,
    cursor: "pointer", fontSize: 11, fontWeight: 600, border: `1px solid ${active ? S.accent : S.border}`,
    backgroundColor: active ? "rgba(252,228,153,0.12)" : S.bgEl, color: active ? S.accent : S.textMain,
  });

  const iS = {
    backgroundColor: S.bgMain, border: `1px solid ${S.border}`, color: S.textBright,
    borderRadius: 4, padding: "6px 10px", width: "100%", outline: "none", fontSize: 12,
  };

  return createPortal(
    <div style={{ position: "fixed", inset: 0, zIndex: 9000, backgroundColor: "rgba(0,0,0,0.85)",
      display: "flex", alignItems: "center", justifyContent: "center" }}
      onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        width: "92vw", height: "90vh", backgroundColor: S.bgCard,
        border: `1px solid ${S.border}`, borderRadius: 10,
        boxShadow: "0 32px 80px rgba(0,0,0,0.8)",
        display: "flex", flexDirection: "column", overflow: "hidden",
      }}>

        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 16px",
          borderBottom: `1px solid ${S.border}`, flexShrink: 0 }}>
          <Globe size={15} style={{ color: S.accent }} />
          <span style={{ fontSize: 13, fontWeight: 700, color: S.textBright }}>Visual Selektor</span>
          <span style={{ fontSize: 11, color: S.textDim }}>— Klicke auf Elemente um Felder zu definieren</span>
          <div style={{ marginLeft: "auto" }}>
            <button onClick={onClose} style={{ color: S.textDim, background: "none",
              border: "none", cursor: "pointer", fontSize: 18, lineHeight: 1 }}>✕</button>
          </div>
        </div>

        {/* URL-Leiste */}
        <div style={{ display: "flex", gap: 8, padding: "8px 16px",
          borderBottom: `1px solid ${S.border}`, flexShrink: 0, backgroundColor: S.bgMain }}>
          <input style={{ ...iS, flex: 1, fontFamily: "monospace" }}
            placeholder="https://example.com/produkte"
            value={url}
            onChange={e => setUrl(e.target.value)}
            onKeyDown={e => e.key === "Enter" && loadPage()} />
          <button onClick={loadPage} disabled={pageLoading || !url.trim()}
            style={{ padding: "6px 16px", borderRadius: 4, fontSize: 12, fontWeight: 600,
              cursor: pageLoading || !url.trim() ? "not-allowed" : "pointer",
              backgroundColor: "rgba(252,228,153,0.12)", border: `1px solid ${S.accent}66`,
              color: S.accent, display: "flex", alignItems: "center", gap: 6,
              opacity: pageLoading || !url.trim() ? 0.5 : 1 }}>
            {pageLoading ? <Loader2 size={13} className="animate-spin" /> : <Globe size={13} />}
            Laden
          </button>
        </div>

        {/* Haupt-Bereich: iframe + Sidebar */}
        <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>

          {/* iFrame */}
          <div style={{ flex: 1, position: "relative", backgroundColor: "#fff" }}>
            {!iframeSrc && !pageLoading && (
              <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column",
                alignItems: "center", justifyContent: "center", gap: 12, color: S.textDim,
                backgroundColor: S.bgMain }}>
                <Globe size={40} style={{ opacity: 0.3 }} />
                <p style={{ fontSize: 12 }}>URL eingeben und Laden klicken</p>
              </div>
            )}
            {pageLoading && (
              <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center",
                justifyContent: "center", backgroundColor: S.bgMain, zIndex: 10 }}>
                <Loader2 size={24} className="animate-spin" style={{ color: S.accent }} />
              </div>
            )}
            {pageError && !pageLoading && (
              <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column",
                alignItems: "center", justifyContent: "center", gap: 8, backgroundColor: S.bgMain }}>
                <p style={{ fontSize: 12, color: S.red }}>⚠ {pageError}</p>
              </div>
            )}
            {iframeSrc && (
              <>
                {mode && (
                  <div style={{ position: "absolute", top: 8, left: "50%", transform: "translateX(-50%)",
                    zIndex: 20, backgroundColor: mode === "row" ? "#6ee7b744" : "#fce49944",
                    border: `1px solid ${mode === "row" ? S.green : S.accent}`,
                    color: mode === "row" ? S.green : S.accent,
                    padding: "5px 14px", borderRadius: 20, fontSize: 11, fontWeight: 600,
                    backdropFilter: "blur(8px)", pointerEvents: "none" }}>
                    {mode === "row" ? "Klicke auf ein Zeilen-Element (wiederkehrend)" : "Klicke auf ein Element zum Auswählen"}
                  </div>
                )}
                <iframe
                  ref={iframeRef}
                  src={iframeSrc}
                  style={{ width: "100%", height: "100%", border: "none",
                    pointerEvents: mode ? "all" : "all",
                    cursor: mode ? "crosshair" : "default" }}
                  sandbox="allow-scripts allow-same-origin allow-forms"
                  title="Visual Selektor Vorschau"
                />
              </>
            )}
          </div>

          {/* Sidebar */}
          <div style={{ width: 260, borderLeft: `1px solid ${S.border}`, display: "flex",
            flexDirection: "column", backgroundColor: S.bgCard, overflow: "hidden" }}>

            {/* Modus-Buttons */}
            <div style={{ padding: "10px 12px", borderBottom: `1px solid ${S.border}`, display: "flex", flexDirection: "column", gap: 6 }}>
              <button style={btnMode(mode === "field")}
                onClick={() => iframeReady && activateMode("field")}
                disabled={!iframeReady}>
                <MousePointer size={12} /> Feld auswählen
              </button>
              <button style={btnMode(mode === "row")}
                onClick={() => iframeReady && activateMode("row")}
                disabled={!iframeReady}>
                <Rows3 size={12} /> Zeilen-Selektor setzen
              </button>
            </div>

            {/* Zeilen-Selektor */}
            {(rowSelector || mode === "row") && (
              <div style={{ padding: "8px 12px", borderBottom: `1px solid ${S.border}` }}>
                <p style={{ fontSize: 9, color: S.green, fontWeight: 700, textTransform: "uppercase",
                  letterSpacing: "0.08em", marginBottom: 4 }}>Zeilen-Selektor</p>
                <div style={{ display: "flex", gap: 4 }}>
                  <input style={{ ...{ backgroundColor: S.bgMain, border: `1px solid ${S.border}`,
                    color: S.green, borderRadius: 4, padding: "4px 6px", fontSize: 10,
                    fontFamily: "monospace", outline: "none", flex: 1 } }}
                    value={rowSelector} onChange={e => setRowSelector(e.target.value)}
                    placeholder="z.B. div.product" />
                  {rowSelector && (
                    <button onClick={() => setRowSelector("")}
                      style={{ padding: "4px 6px", borderRadius: 4, cursor: "pointer",
                        backgroundColor: "transparent", border: `1px solid ${S.border}`,
                        color: S.textDim, fontSize: 11 }}>
                      <X size={10} />
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* Pending Field Form */}
            {pending && (
              <div style={{ padding: "8px 12px", borderBottom: `1px solid ${S.border}` }}>
                <PendingFieldForm
                  pending={pending}
                  onConfirm={confirmField}
                  onCancel={() => setPending(null)}
                />
              </div>
            )}

            {/* Felder-Liste */}
            <div style={{ flex: 1, overflowY: "auto", padding: "8px 12px" }}>
              {fields.length === 0 ? (
                <p style={{ fontSize: 11, color: S.textDim, textAlign: "center", marginTop: 20 }}>
                  Noch keine Felder — klicke auf "Feld auswählen" und dann auf ein Element auf der Seite.
                </p>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {fields.map((f) => (
                    <div key={f.id} style={{ padding: "7px 10px", borderRadius: 5,
                      border: `1px solid ${S.border}`, backgroundColor: S.bgEl,
                      display: "flex", flexDirection: "column", gap: 3 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontSize: 11, fontWeight: 600, color: S.textBright }}>{f.field_name}</span>
                        <button onClick={() => removeField(f.id)}
                          style={{ color: S.textDim, background: "none", border: "none",
                            cursor: "pointer", padding: 2 }}>
                          <Trash2 size={10} />
                        </button>
                      </div>
                      <div style={{ fontSize: 9, color: S.textDim, fontFamily: "monospace",
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {f.css_selector}
                      </div>
                      <div style={{ fontSize: 9, color: S.accent + "aa" }}>
                        {TRANSFORMS.find(t => t.value === f.transform)?.label || f.transform}
                      </div>
                      {f.sample && (
                        <div style={{ fontSize: 9, color: S.textMain, fontStyle: "italic",
                          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          "{f.sample.slice(0, 40)}"
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Vorschau-Button */}
            <div style={{ padding: "8px 12px", borderTop: `1px solid ${S.border}` }}>
              <button onClick={handlePreview}
                disabled={previewLoading || fields.length === 0 || !loadedUrl}
                style={{ width: "100%", padding: "6px", borderRadius: 4, cursor: fields.length > 0 && loadedUrl ? "pointer" : "not-allowed",
                  fontSize: 11, fontWeight: 600, border: `1px solid ${S.border}`,
                  backgroundColor: S.bgEl, color: fields.length > 0 ? S.textMain : S.textDim,
                  display: "flex", alignItems: "center", justifyContent: "center", gap: 5,
                  opacity: fields.length === 0 || !loadedUrl ? 0.5 : 1 }}>
                {previewLoading ? <Loader2 size={12} className="animate-spin" /> : <Eye size={12} />}
                Vorschau
              </button>
            </div>
          </div>
        </div>

        {/* Vorschau-Tabelle */}
        {(preview || previewError) && (
          <div style={{ borderTop: `1px solid ${S.border}`, flexShrink: 0,
            maxHeight: 200, overflow: "auto", backgroundColor: S.bgMain }}>
            {previewError ? (
              <p style={{ padding: "8px 12px", fontSize: 11, color: S.red }}>⚠ {previewError}</p>
            ) : (
              <PreviewTable rows={preview.rows} columns={preview.columns} />
            )}
          </div>
        )}

        {/* Footer */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "10px 16px", borderTop: `1px solid ${S.border}`, flexShrink: 0,
          backgroundColor: S.bgEl }}>
          <span style={{ fontSize: 11, color: S.textDim }}>
            {fields.length === 0 ? "Noch keine Felder definiert" :
              `${fields.length} Feld${fields.length !== 1 ? "er" : ""} definiert${rowSelector ? " · Zeilen-Selektor aktiv" : ""}`}
          </span>
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={onClose}
              style={{ padding: "7px 14px", borderRadius: 5, cursor: "pointer", fontSize: 12,
                backgroundColor: "transparent", border: `1px solid ${S.border}`, color: S.textDim }}>
              Abbrechen
            </button>
            <button onClick={handleSave} disabled={fields.length === 0}
              style={{ padding: "7px 16px", borderRadius: 5, cursor: fields.length > 0 ? "pointer" : "not-allowed",
                fontSize: 12, fontWeight: 600, backgroundColor: fields.length > 0 ? S.accent : S.bgEl,
                border: `1px solid ${fields.length > 0 ? S.accent : S.border}`,
                color: fields.length > 0 ? "#111" : S.textDim,
                display: "flex", alignItems: "center", gap: 5, opacity: fields.length === 0 ? 0.5 : 1 }}>
              <Check size={13} /> Übernehmen
            </button>
          </div>
        </div>

      </div>
    </div>,
    document.body
  );
}
