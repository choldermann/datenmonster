import { useState, useEffect } from "react";
import { Plus, Pencil, Trash2, Play, Check, X, ChevronDown, GitBranch, Loader2 } from "lucide-react";
import api from "../../../api/client";
import { S } from "../constants";

const DISP_COLOR = "#fce499"; // Akzent-Gold wie im Rest des Dashboards

const CONDITION_TYPES = [
  { v: "filename",        l: "Dateiname passt zu Muster" },
  { v: "file_extension",  l: "Dateiendung" },
  { v: "column_exists",   l: "Spalte/Tag existiert" },
  { v: "column_value",    l: "Spalte/Tag enthält Wert" },
  { v: "row_count_gt",    l: "Zeilenzahl > N" },
  { v: "row_count_lt",    l: "Zeilenzahl < N" },
  { v: "xml_tag_exists",  l: "XML: Tag existiert" },
  { v: "xml_tag_value",   l: "XML: Tag hat Wert" },
  { v: "xml_xpath",       l: "XML: XPath-Ausdruck" },
  { v: "xml_schema",      l: "XML: Schema-Übereinstimmung (Dataset)" },
];

const POST_ACTION_TYPES = [
  { v: "ftp_upload",    l: "FTP Upload" },
  { v: "chain_mapping", l: "Weiteres Mapping starten" },
  { v: "email",         l: "E-Mail senden" },
];

const EMPTY_RULE = {
  name: "", ftp_source_id: null, mapping_id: null,
  active: true, priority: 0, condition_mode: "AND",
  conditions: [], post_actions: [], project_id: null,
};

function RuleModal({ rule, ftpSources, mappings, xmlDatasets, projectId, onSave, onClose }) {
  const isNew = !rule?.id;
  const [form, setForm] = useState(rule?.id ? { ...rule } : { ...EMPTY_RULE, project_id: projectId || null });
  const [saving, setSaving] = useState(false);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const addCondition = () => set("conditions", [...(form.conditions || []), { type: "filename", pattern: "", column: "", value: "" }]);
  const updateCond = (i, k, v) => set("conditions", form.conditions.map((c, idx) => idx === i ? { ...c, [k]: v } : c));
  const removeCond = (i) => set("conditions", form.conditions.filter((_, idx) => idx !== i));

  const addAction = () => set("post_actions", [...(form.post_actions || []), { type: "ftp_upload", ftp_source_id: null, mapping_id: null, to: "", subject: "" }]);
  const updateAction = (i, k, v) => set("post_actions", form.post_actions.map((a, idx) => idx === i ? { ...a, [k]: v } : a));
  const removeAction = (i) => set("post_actions", form.post_actions.filter((_, idx) => idx !== i));

  const handleSave = async () => {
    if (!form.name?.trim()) return;
    setSaving(true);
    try {
      if (isNew) await api.post("/api/dispatcher/", form);
      else await api.put(`/api/dispatcher/${form.id}`, form);
      onSave();
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    } finally { setSaving(false); }
  };

  const iS = { backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4, color: S.textBright, fontSize: 11, padding: "5px 8px", outline: "none", width: "100%" };
  const lS = { fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", color: S.textDim, display: "block", marginBottom: 3 };

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 60, backgroundColor: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center" }} onClick={onClose}>
      <div style={{ width: 560, maxHeight: "90vh", display: "flex", flexDirection: "column", backgroundColor: S.bgCard, borderRadius: 10, border: `1px solid ${DISP_COLOR}55`, boxShadow: "0 24px 64px rgba(0,0,0,0.6)" }} onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div style={{ padding: "14px 18px", borderBottom: `1px solid ${S.border}`, display: "flex", alignItems: "center", gap: 10 }}>
          <GitBranch size={14} style={{ color: DISP_COLOR }} />
          <span style={{ fontSize: 13, fontWeight: 700, color: S.textBright, flex: 1 }}>{isNew ? "Neue Dispatcher-Regel" : "Regel bearbeiten"}</span>
          <button onClick={onClose} style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer" }}><X size={14} /></button>
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: "16px 18px", display: "flex", flexDirection: "column", gap: 14 }}>

          {/* Basis */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <div>
              <label style={lS}>Name *</label>
              <input style={iS} value={form.name} onChange={e => set("name", e.target.value)} placeholder="z.B. DPD Scaninfo Dispatcher" />
            </div>
            <div>
              <label style={lS}>Priorität</label>
              <input style={iS} type="number" value={form.priority || 0} onChange={e => set("priority", parseInt(e.target.value) || 0)} />
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <div>
              <label style={lS}>FTP-Quelle</label>
              <select style={iS} value={form.ftp_source_id || ""} onChange={e => set("ftp_source_id", parseInt(e.target.value) || null)}>
                <option value="">— Alle FTP-Quellen —</option>
                {ftpSources.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div>
              <label style={lS}>Mapping ausführen</label>
              <select style={iS} value={form.mapping_id || ""} onChange={e => set("mapping_id", parseInt(e.target.value) || null)}>
                <option value="">— Kein Mapping —</option>
                {mappings.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
            </div>
          </div>

          {/* Bedingungen */}
          <div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
              <label style={{ ...lS, marginBottom: 0 }}>Bedingungen</label>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                {["AND", "OR"].map(m => (
                  <button key={m} onClick={() => set("condition_mode", m)}
                    style={{ padding: "2px 8px", borderRadius: 3, fontSize: 10, fontWeight: 700, cursor: "pointer", border: `1px solid ${form.condition_mode === m ? DISP_COLOR : S.border}`, backgroundColor: form.condition_mode === m ? `${DISP_COLOR}20` : "transparent", color: form.condition_mode === m ? DISP_COLOR : S.textDim }}>
                    {m}
                  </button>
                ))}
                <button onClick={addCondition} style={{ fontSize: 10, color: DISP_COLOR, background: "none", border: "none", cursor: "pointer", display: "flex", alignItems: "center", gap: 3 }}>
                  <Plus size={10} /> Bedingung
                </button>
              </div>
            </div>
            {(form.conditions || []).length === 0 && (
              <p style={{ fontSize: 10, color: S.textDim, fontStyle: "italic" }}>Keine Bedingungen = gilt für alle Dateien dieser FTP-Quelle</p>
            )}
            {(form.conditions || []).map((c, i) => (
              <div key={i} style={{ display: "flex", gap: 6, alignItems: "flex-start", marginBottom: 6 }}>
                <select style={{ ...iS, flex: "0 0 160px" }} value={c.type} onChange={e => updateCond(i, "type", e.target.value)}>
                  {CONDITION_TYPES.map(t => <option key={t.v} value={t.v}>{t.l}</option>)}
                </select>
                {c.type === "filename" && (
                  <input style={iS} value={c.pattern || ""} onChange={e => updateCond(i, "pattern", e.target.value)} placeholder="*_orders.csv" />
                )}
                {c.type === "file_extension" && (
                  <input style={iS} value={c.extension || ""} onChange={e => updateCond(i, "extension", e.target.value)} placeholder=".xml oder .csv" />
                )}
                {(c.type === "column_exists" || c.type === "xml_tag_exists") && (
                  <input style={iS} value={c.column || ""} onChange={e => updateCond(i, "column", e.target.value)} placeholder={c.type === "xml_tag_exists" ? "Tag-Name (z.B. Sendung)" : "Spaltenname"} />
                )}
                {(c.type === "column_value" || c.type === "xml_tag_value") && <>
                  <input style={iS} value={c.column || ""} onChange={e => updateCond(i, "column", e.target.value)} placeholder={c.type === "xml_tag_value" ? "Tag-Name" : "Spalte"} />
                  <input style={iS} value={c.value || ""} onChange={e => updateCond(i, "value", e.target.value)} placeholder="Wert" />
                </>}
                {c.type === "xml_xpath" && (
                  <input style={iS} value={c.xpath || ""} onChange={e => updateCond(i, "xpath", e.target.value)} placeholder="//Sendung[@typ='express']" />
                )}
                {(c.type === "row_count_gt" || c.type === "row_count_lt") && (
                  <input style={{ ...iS, flex: "0 0 80px" }} type="number" value={c.threshold || 0} onChange={e => updateCond(i, "threshold", parseInt(e.target.value) || 0)} placeholder="N" />
                )}
                {c.type === "xml_schema" && (
                  <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 4 }}>
                    <select style={iS} value={c.dataset_id || ""} onChange={e => updateCond(i, "dataset_id", parseInt(e.target.value) || null)}>
                      <option value="">— XML-Dataset wählen —</option>
                      {(xmlDatasets || []).map(d => <option key={d.id} value={d.id}>{d.name} ({d.xml_target_node || "?"})</option>)}
                    </select>
                    <p style={{ fontSize: 9, color: S.textDim, margin: 0 }}>
                      Prüft Root-Tag und bekannte Spalten gegen das Dataset-Schema
                    </p>
                  </div>
                )}
                <button onClick={() => removeCond(i)} style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", padding: "5px 0", flexShrink: 0 }}><X size={11} /></button>
              </div>
            ))}
          </div>

          {/* Post-Actions */}
          <div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
              <label style={{ ...lS, marginBottom: 0 }}>Aktionen nach Mapping</label>
              <button onClick={addAction} style={{ fontSize: 10, color: DISP_COLOR, background: "none", border: "none", cursor: "pointer", display: "flex", alignItems: "center", gap: 3 }}>
                <Plus size={10} /> Aktion
              </button>
            </div>
            {(form.post_actions || []).length === 0 && (
              <p style={{ fontSize: 10, color: S.textDim, fontStyle: "italic" }}>Keine Post-Aktionen</p>
            )}
            {(form.post_actions || []).map((a, i) => (
              <div key={i} style={{ padding: "8px 10px", borderRadius: 5, border: `1px solid ${S.border}`, backgroundColor: S.bgEl, marginBottom: 6 }}>
                <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 6 }}>
                  <select style={{ ...iS, flex: "0 0 180px" }} value={a.type} onChange={e => updateAction(i, "type", e.target.value)}>
                    {POST_ACTION_TYPES.map(t => <option key={t.v} value={t.v}>{t.l}</option>)}
                  </select>
                  <button onClick={() => removeAction(i)} style={{ background: "none", border: "none", color: S.textDim, cursor: "pointer", marginLeft: "auto" }}><X size={11} /></button>
                </div>
                {a.type === "ftp_upload" && (
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                    <select style={iS} value={a.ftp_source_id || ""} onChange={e => updateAction(i, "ftp_source_id", parseInt(e.target.value) || null)}>
                      <option value="">— FTP-Ziel wählen —</option>
                      {ftpSources.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </select>
                    <input style={iS} value={a.remote_dir || ""} onChange={e => updateAction(i, "remote_dir", e.target.value)} placeholder="Zielverzeichnis" />
                  </div>
                )}
                {a.type === "chain_mapping" && (
                  <select style={iS} value={a.mapping_id || ""} onChange={e => updateAction(i, "mapping_id", parseInt(e.target.value) || null)}>
                    <option value="">— Folge-Mapping wählen —</option>
                    {mappings.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
                  </select>
                )}
                {a.type === "email" && (
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                    <input style={iS} value={a.to || ""} onChange={e => updateAction(i, "to", e.target.value)} placeholder="E-Mail Adresse" />
                    <input style={iS} value={a.subject || ""} onChange={e => updateAction(i, "subject", e.target.value)} placeholder="Betreff" />
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Aktiv */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }} onClick={() => set("active", !form.active)}>
            <div style={{ width: 16, height: 16, borderRadius: 3, border: `2px solid ${form.active ? S.accent : S.textDim}`, backgroundColor: form.active ? S.accent : "transparent", display: "flex", alignItems: "center", justifyContent: "center" }}>
              {form.active && <Check size={10} color="#111" strokeWidth={3} />}
            </div>
            <span style={{ fontSize: 11, color: form.active ? S.textBright : S.textDim }}>Regel aktiv</span>
          </div>
        </div>

        {/* Footer */}
        <div style={{ padding: "12px 18px", borderTop: `1px solid ${S.border}`, display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button onClick={onClose} style={{ padding: "6px 14px", borderRadius: 5, border: `1px solid ${S.border}`, background: "none", color: S.textDim, cursor: "pointer", fontSize: 12 }}>Abbrechen</button>
          <button onClick={handleSave} disabled={saving || !form.name?.trim()}
            style={{ padding: "6px 16px", borderRadius: 5, backgroundColor: DISP_COLOR, border: "none", color: "#111", cursor: "pointer", fontSize: 12, fontWeight: 700, display: "flex", alignItems: "center", gap: 6 }}>
            {saving ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
            {isNew ? "Erstellen" : "Speichern"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function DispatcherPanel({ projectId, canEdit }) {
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [ftpSources, setFtpSources] = useState([]);
  const [xmlDatasets, setXmlDatasets] = useState([]);
  const [mappings, setMappings] = useState([]);
  const [editing, setEditing] = useState(null); // null | {} | rule
  const [testResult, setTestResult] = useState({});

  const load = async () => {
    setLoading(true);
    try {
      const [rulesRes, ftpRes, mapRes, dsRes] = await Promise.all([
        api.get("/api/dispatcher/", { params: projectId ? { project_id: projectId } : {} }),
        api.get("/api/ftp-sources/", { params: projectId ? { project_id: projectId } : {} }),
        api.get("/api/mappings/", { params: projectId ? { project_id: projectId } : {} }),
        api.get("/api/datasets/" + (projectId ? `?project_id=${projectId}` : "")),
      ]);
      setRules(rulesRes.data || []);
      setFtpSources(ftpRes.data || []);
      setMappings(mapRes.data || []);
      setXmlDatasets((dsRes.data || []).filter(d => d.file_type === "xml" && d.xml_configured === 1));
    } catch (e) {
      console.error(e);
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [projectId]);

  const deleteRule = async (id) => {
    if (!window.confirm("Regel löschen?")) return;
    await api.delete(`/api/dispatcher/${id}`);
    load();
  };

  const testRule = async (id) => {
    try {
      const { data } = await api.post(`/api/dispatcher/${id}/test`);
      setTestResult(prev => ({ ...prev, [id]: { ok: true, msg: data.message } }));
    } catch (e) {
      setTestResult(prev => ({ ...prev, [id]: { ok: false, msg: e.response?.data?.detail || e.message } }));
    }
  };

  const getMapping = (id) => mappings.find(m => m.id === id);
  const getFtp = (id) => ftpSources.find(s => s.id === id);

  return (
    <div style={{ padding: 20, maxWidth: 900 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <div>
          <h2 style={{ fontSize: 16, fontWeight: 700, color: S.textBright, margin: 0 }}>Dispatcher</h2>
          <p style={{ fontSize: 11, color: S.textDim, marginTop: 4 }}>Eingehende Dateien automatisch erkennen und das passende Mapping starten.</p>
        </div>
        {canEdit && (
          <button onClick={() => setEditing({})}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 14px", borderRadius: 6, backgroundColor: `${DISP_COLOR}20`, border: `1px solid ${DISP_COLOR}55`, color: DISP_COLOR, cursor: "pointer", fontSize: 12, fontWeight: 600 }}>
            <Plus size={13} /> Neue Regel
          </button>
        )}
      </div>

      {loading && <div style={{ color: S.textDim, fontSize: 12 }}>Lade...</div>}

      {!loading && rules.length === 0 && (
        <div style={{ textAlign: "center", padding: 40, border: `1px dashed ${S.border}`, borderRadius: 8 }}>
          <GitBranch size={32} style={{ color: S.textDim, marginBottom: 12 }} />
          <p style={{ fontSize: 13, color: S.textDim }}>Noch keine Dispatcher-Regeln</p>
          <p style={{ fontSize: 11, color: S.textDim, marginTop: 4 }}>Erstelle eine Regel um eingehende FTP-Dateien automatisch zu verarbeiten.</p>
        </div>
      )}

      {rules.map(rule => {
        const mapping = getMapping(rule.mapping_id);
        const ftp = getFtp(rule.ftp_source_id);
        const tr = testResult[rule.id];
        return (
          <div key={rule.id} style={{ marginBottom: 10, borderRadius: 8, border: `1px solid ${rule.active ? DISP_COLOR + "44" : S.border}`, backgroundColor: S.bgCard, overflow: "hidden" }}>
            <div style={{ padding: "10px 14px", display: "flex", alignItems: "center", gap: 10, backgroundColor: rule.active ? `${DISP_COLOR}08` : "transparent" }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", backgroundColor: rule.active ? DISP_COLOR : S.textDim, flexShrink: 0 }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <p style={{ fontSize: 12, fontWeight: 600, color: S.textBright, margin: 0 }}>{rule.name}</p>
                <p style={{ fontSize: 10, color: S.textDim, margin: "2px 0 0" }}>
                  {ftp ? `FTP: ${ftp.name}` : "Alle FTP-Quellen"} →
                  {mapping ? ` Mapping: ${mapping.name}` : " Kein Mapping"}
                  {rule.conditions?.length > 0 ? ` · ${rule.conditions.length} Bedingung(en)` : " · Immer"}
                  {rule.post_actions?.length > 0 ? ` · ${rule.post_actions.length} Aktion(en)` : ""}
                </p>
              </div>
              <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                <button onClick={() => testRule(rule.id)} title="Testen"
                  style={{ padding: "3px 8px", borderRadius: 4, border: `1px solid ${S.border}`, background: "none", color: S.textDim, cursor: "pointer", fontSize: 10 }}>
                  <Play size={10} />
                </button>
                {canEdit && <>
                  <button onClick={() => setEditing(rule)}
                    style={{ padding: "3px 8px", borderRadius: 4, border: `1px solid ${S.border}`, background: "none", color: S.textDim, cursor: "pointer" }}>
                    <Pencil size={10} />
                  </button>
                  <button onClick={() => deleteRule(rule.id)}
                    style={{ padding: "3px 8px", borderRadius: 4, border: `1px solid ${S.border}`, background: "none", color: S.textDim, cursor: "pointer" }}
                    onMouseEnter={e => e.currentTarget.style.color = "#e07070"}
                    onMouseLeave={e => e.currentTarget.style.color = S.textDim}>
                    <Trash2 size={10} />
                  </button>
                </>}
              </div>
            </div>
            {tr && (
              <div style={{ padding: "6px 14px", backgroundColor: tr.ok ? "rgba(110,231,183,0.06)" : "rgba(224,112,112,0.06)", borderTop: `1px solid ${S.border}` }}>
                <p style={{ fontSize: 10, color: tr.ok ? "#6ee7b7" : "#e07070", margin: 0 }}>{tr.ok ? "✓" : "✗"} {tr.msg}</p>
              </div>
            )}
          </div>
        );
      })}

      {editing !== null && (
        <RuleModal
          rule={editing?.id ? editing : null}
          ftpSources={ftpSources}
          mappings={mappings}
          xmlDatasets={xmlDatasets}
          projectId={projectId}
          onSave={() => { setEditing(null); load(); }}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}
