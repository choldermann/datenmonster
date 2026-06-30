import { useState, useEffect } from "react";
import { ChevronDown, ChevronUp, Sparkles, RotateCcw } from "lucide-react";
import { S, NODE_COLORS } from "../constants";
import BaseNode from "./BaseNode";
import api from "../../../api/client";

const COLOR = "#c084fc"; // violet-400
const ROLES = [
  { key: "revenue",  label: "Umsatz / Kennzahl", required: true },
  { key: "date",     label: "Datumsfeld",         required: true },
  { key: "country",  label: "Land / Region",      required: false },
  { key: "customer", label: "Kunde",               required: false },
  { key: "article",  label: "Artikel",             required: false },
  { key: "quantity", label: "Menge",               required: false },
  { key: "stock",    label: "Lagerbestand",        required: false },
];
const MODULES = [
  { key: "umsatzentwicklung", label: "Umsatzentwicklung" },
  { key: "laenderanalyse",    label: "Länderanalyse" },
  { key: "top_kunden",        label: "Top-Kunden" },
  { key: "lagerbestand",      label: "Lagerbestand" },
];
const COMPARISON_MODES = [
  { value: "mom",       label: "Aktueller Monat vs. Vormonat" },
  { value: "yoy_month", label: "Aktueller Monat vs. Vorjahr (gleicher Monat)" },
  { value: "yoy_year",  label: "Aktuelles Jahr vs. Vorjahr" },
  { value: "custom",    label: "Freier Zeitraum" },
];

const iS = {
  backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 3,
  color: S.textBright, fontSize: 10, padding: "3px 6px", outline: "none", width: "100%",
};
const lS = {
  fontSize: 9, color: S.textDim, textTransform: "uppercase" as const,
  letterSpacing: "0.06em", display: "block", marginBottom: 2,
};

export default function BusinessInsightsNode({
  node, onRemove, onPositionChange, onUpdate,
  inputPortRef, inputPortDrop, outputPortRef,
  datasets,
  runResult, isActive, onActivate,
}: any) {
  const config  = node.config || {};
  const set     = (k: string, v: any) => onUpdate({ ...node, config: { ...config, [k]: v } });
  const setSem  = (role: string, col: string) => set("semantic", { ...(config.semantic || {}), [role]: col || null });
  const setMod  = (key: string, val: boolean) => set("modules", { ...(config.modules || defaultModules()), [key]: val });
  const setCmp  = (k: string, v: any) => set("comparison", { ...(config.comparison || { mode: "mom" }), [k]: v });

  const [showConfig, setShowConfig] = useState(false);
  const [columns, setColumns]       = useState<string[]>([]);
  const [suggestions, setSuggestions] = useState<Record<string, string | null>>({});
  const [confirmed, setConfirmed]   = useState<Record<string, boolean>>(
    Object.fromEntries(ROLES.map(r => [r.key, !!(config.semantic?.[r.key])]))
  );
  const [presets, setPresets]       = useState<any[]>([]);
  const [loadingCols, setLoadingCols] = useState(false);

  function defaultModules() {
    return { umsatzentwicklung: true, laenderanalyse: true, top_kunden: true, lagerbestand: false };
  }

  // Presets laden
  useEffect(() => {
    api.get("/api/insights/presets").then(r => setPresets(r.data || [])).catch(() => {});
  }, []);

  // Spalten laden wenn Dataset gewählt
  useEffect(() => {
    const dsId = config.dataset_id;
    if (!dsId) { setColumns([]); setSuggestions({}); return; }
    const ds = (datasets || []).find((d: any) => d.id === dsId);
    if (!ds?.columns) return;
    const cols: string[] = Array.isArray(ds.columns) ? ds.columns : [];
    setColumns(cols);
    if (cols.length > 0) {
      setLoadingCols(true);
      api.post("/api/insights/suggest-mapping", { columns: cols })
        .then(r => { setSuggestions(r.data || {}); })
        .catch(() => {})
        .finally(() => setLoadingCols(false));
    }
  }, [config.dataset_id, datasets]);

  function applyPreset(preset: any) {
    set("semantic", preset.mapping);
    setConfirmed(Object.fromEntries(
      Object.entries(preset.mapping).map(([k, v]) => [k, !!v])
    ));
  }

  function confirmSuggestion(role: string) {
    const col = suggestions[role];
    if (col) {
      setSem(role, col);
      setConfirmed(prev => ({ ...prev, [role]: true }));
    }
  }

  const semantic    = config.semantic || {};
  const comparison  = config.comparison || { mode: "mom" };
  const modules     = config.modules   || defaultModules();
  const confirmedCount = ROLES.filter(r => confirmed[r.key] && semantic[r.key]).length;
  const requiredOk  = ROLES.filter(r => r.required).every(r => confirmed[r.key] && semantic[r.key]);

  const selectedDs = (datasets || []).find((d: any) => d.id === config.dataset_id);

  return (
    <BaseNode
      node={node} color={COLOR} icon="💡" label="Business Insights"
      runResult={runResult} isActive={isActive} onActivate={onActivate}
      onRemove={onRemove} onPositionChange={onPositionChange}
      inputPorts={[{ id: "in", label: "Daten", portRef: inputPortRef, onDrop: inputPortDrop }]}
      outputPorts={[{
        id: "out", label: "Findings",
        portRef: outputPortRef,
        onDragStart: (e: any) => {
          e.stopPropagation();
          e.dataTransfer.setData("from_node", node.id);
          e.dataTransfer.setData("from_port", "out");
        },
      }]}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>

        {/* Dataset */}
        <div>
          <label style={lS}>Dataset (historische Daten)</label>
          <select style={iS} value={config.dataset_id || ""}
            onChange={e => { set("dataset_id", parseInt(e.target.value) || null); setConfirmed({}); }}>
            <option value="">— Dataset wählen —</option>
            {(datasets || []).map((d: any) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </select>
        </div>

        {/* Status-Zeile */}
        {config.dataset_id && (
          <div style={{
            fontSize: 9, color: requiredOk ? "#4ade80" : S.textDim,
            padding: "3px 6px", borderRadius: 3,
            backgroundColor: requiredOk ? "#4ade8010" : `${COLOR}10`,
            border: `1px solid ${requiredOk ? "#4ade8030" : COLOR + "30"}`,
          }}>
            {requiredOk
              ? `✓ ${confirmedCount} Felder zugeordnet — bereit`
              : `⚠ Umsatz + Datum benötigt (${confirmedCount} zugeordnet)`}
          </div>
        )}

        {/* Konfigurations-Aufklapper */}
        {config.dataset_id && (
          <button
            onClick={() => setShowConfig(v => !v)}
            style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              gap: 4, padding: "4px 6px", borderRadius: 3, cursor: "pointer",
              backgroundColor: `${COLOR}15`, border: `1px solid ${COLOR}40`,
              color: COLOR, fontSize: 10, fontWeight: 600,
            }}
          >
            <span>Feldzuordnung & Module</span>
            {showConfig ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
          </button>
        )}

        {showConfig && config.dataset_id && (
          <div style={{
            display: "flex", flexDirection: "column", gap: 8,
            padding: "8px", borderRadius: 4,
            backgroundColor: `${COLOR}08`, border: `1px solid ${COLOR}25`,
          }}>

            {/* Presets */}
            {presets.length > 0 && (
              <div>
                <label style={lS}>Preset laden</label>
                <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                  {presets.map(p => (
                    <button key={p.id} onClick={() => applyPreset(p)} style={{
                      fontSize: 9, padding: "2px 6px", borderRadius: 3, cursor: "pointer",
                      backgroundColor: `${COLOR}20`, border: `1px solid ${COLOR}50`, color: COLOR,
                    }}>
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Semantic Mapping */}
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                <label style={{ ...lS, marginBottom: 0 }}>Feldzuordnung</label>
                {loadingCols && <span style={{ fontSize: 8, color: COLOR }}>wird vorgeschlagen…</span>}
              </div>
              {ROLES.map(role => {
                const sugg = suggestions[role.key];
                const cur  = semantic[role.key] || "";
                const isConfirmed = confirmed[role.key] && cur;
                return (
                  <div key={role.key} style={{ marginBottom: 5 }}>
                    <label style={lS}>
                      {role.label}{role.required ? " *" : ""}
                    </label>
                    <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                      <select style={{ ...iS, flex: 1 }} value={cur}
                        onChange={e => {
                          setSem(role.key, e.target.value);
                          setConfirmed(prev => ({ ...prev, [role.key]: !!e.target.value }));
                        }}>
                        <option value="">— nicht zugeordnet —</option>
                        {columns.map(c => <option key={c} value={c}>{c}</option>)}
                      </select>
                      {/* Vorschlag-Badge */}
                      {sugg && !isConfirmed && (
                        <button
                          title={`Vorschlag übernehmen: ${sugg}`}
                          onClick={() => confirmSuggestion(role.key)}
                          style={{
                            display: "flex", alignItems: "center", gap: 2,
                            fontSize: 8, padding: "2px 5px", borderRadius: 3,
                            cursor: "pointer", whiteSpace: "nowrap",
                            backgroundColor: `${COLOR}20`, border: `1px solid ${COLOR}50`,
                            color: COLOR, flexShrink: 0,
                          }}>
                          <Sparkles size={8} />
                          {sugg}
                        </button>
                      )}
                      {isConfirmed && (
                        <span style={{ color: "#4ade80", fontSize: 10, flexShrink: 0 }}>✓</span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Module */}
            <div>
              <label style={lS}>Analyse-Module</label>
              {MODULES.map(m => (
                <label key={m.key} style={{
                  display: "flex", alignItems: "center", gap: 5,
                  fontSize: 10, color: S.textMain, cursor: "pointer", marginBottom: 3,
                }}>
                  <input type="checkbox" checked={!!modules[m.key]}
                    onChange={e => setMod(m.key, e.target.checked)}
                    style={{ accentColor: COLOR }} />
                  {m.label}
                </label>
              ))}
            </div>

            {/* Vergleichsmodus */}
            <div>
              <label style={lS}>Vergleichszeitraum</label>
              <select style={iS} value={comparison.mode || "mom"}
                onChange={e => setCmp("mode", e.target.value)}>
                {COMPARISON_MODES.map(m => (
                  <option key={m.value} value={m.value}>{m.label}</option>
                ))}
              </select>
            </div>

            {/* Custom Zeiträume */}
            {comparison.mode === "custom" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <label style={lS}>Aktueller Zeitraum</label>
                <div style={{ display: "flex", gap: 4 }}>
                  <input type="date" style={{ ...iS, flex: 1 }}
                    value={comparison.custom_start || ""}
                    onChange={e => setCmp("custom_start", e.target.value)} />
                  <span style={{ color: S.textDim, fontSize: 10, alignSelf: "center" }}>bis</span>
                  <input type="date" style={{ ...iS, flex: 1 }}
                    value={comparison.custom_end || ""}
                    onChange={e => setCmp("custom_end", e.target.value)} />
                </div>
                <label style={lS}>Vergleichszeitraum</label>
                <div style={{ display: "flex", gap: 4 }}>
                  <input type="date" style={{ ...iS, flex: 1 }}
                    value={comparison.custom_prev_start || ""}
                    onChange={e => setCmp("custom_prev_start", e.target.value)} />
                  <span style={{ color: S.textDim, fontSize: 10, alignSelf: "center" }}>bis</span>
                  <input type="date" style={{ ...iS, flex: 1 }}
                    value={comparison.custom_prev_end || ""}
                    onChange={e => setCmp("custom_prev_end", e.target.value)} />
                </div>
              </div>
            )}

            {/* Output-Name */}
            <div>
              <label style={lS}>Ausgabe-Dataset-Name</label>
              <input type="text" style={iS}
                value={config.output_name || ""}
                placeholder="Insights-Ergebnis"
                onChange={e => set("output_name", e.target.value)} />
            </div>

            {/* Reset-Button */}
            <button onClick={() => {
              set("semantic", {});
              setSuggestions({});
              setConfirmed({});
            }} style={{
              display: "flex", alignItems: "center", gap: 4, justifyContent: "center",
              fontSize: 9, padding: "3px 6px", borderRadius: 3, cursor: "pointer",
              backgroundColor: "transparent", border: `1px solid ${S.border}`,
              color: S.textDim,
            }}>
              <RotateCcw size={9} />
              Zuordnung zurücksetzen
            </button>
          </div>
        )}

        {/* Run-Ergebnis */}
        {runResult?.status === "ok" && runResult.rows !== undefined && (
          <div style={{
            fontSize: 9, color: "#4ade80", padding: "3px 6px", borderRadius: 3,
            backgroundColor: "#4ade8010", border: "1px solid #4ade8030",
          }}>
            {runResult.rows} Findings → Dataset {runResult.dataset_name || "erstellt"}
          </div>
        )}
      </div>
    </BaseNode>
  );
}
