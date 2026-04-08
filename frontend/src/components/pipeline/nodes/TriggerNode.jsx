import { S, NODE_COLORS } from "../constants";
import BaseNode from "./BaseNode";

const WEEKDAYS = [
  { v: 1, l: "Mo" }, { v: 2, l: "Di" }, { v: 3, l: "Mi" },
  { v: 4, l: "Do" }, { v: 5, l: "Fr" }, { v: 6, l: "Sa" }, { v: 0, l: "So" },
];

function buildCron(mode, time, intervalMin, weekdays, monthDays) {
  const [h, m] = (time || "06:00").split(":").map(Number);
  const interval = parseInt(intervalMin) || 0;
  const slots = [];
  if (interval > 0) {
    let cur = h * 60 + m;
    while (cur < 24 * 60) {
      slots.push({ hh: Math.floor(cur / 60), mm: cur % 60 });
      cur += interval;
    }
  } else {
    slots.push({ hh: h, mm: m });
  }
  return slots.map(({ hh, mm }) => {
    if (mode === "weekly")  return `${mm} ${hh} * * ${weekdays?.length > 0 ? weekdays.join(",") : "*"}`;
    if (mode === "monthly") return `${mm} ${hh} ${monthDays?.length > 0 ? monthDays.join(",") : "1"} * *`;
    return `${mm} ${hh} * * *`;
  }).join(";");
}

function ChipBtn({ label, active, onClick }) {
  return (
    <button onClick={onClick} style={{
      padding: "2px 5px", borderRadius: 3, fontSize: 9, fontWeight: 600, cursor: "pointer",
      border: `1px solid ${active ? NODE_COLORS.trigger : S.border}`,
      backgroundColor: active ? NODE_COLORS.trigger + "25" : "transparent",
      color: active ? NODE_COLORS.trigger : S.textDim,
    }}>{label}</button>
  );
}

export default function TriggerNode({ node, onRemove, onPositionChange, onUpdate, outputPortRef, runResult }) {
  const config = node.config || {};
  const set = (k, v) => {
    const newConfig = { ...config, [k]: v };
    // Cron neu berechnen wenn relevante Felder ändern
    if (["mode", "time", "intervalMin", "weekdays", "monthDays"].includes(k)) {
      newConfig.cron = buildCron(
        k === "mode" ? v : newConfig.mode || "daily",
        k === "time" ? v : newConfig.time || "06:00",
        k === "intervalMin" ? v : newConfig.intervalMin || 0,
        k === "weekdays" ? v : newConfig.weekdays || [],
        k === "monthDays" ? v : newConfig.monthDays || [],
      );
    }
    onUpdate({ ...node, config: newConfig });
  };

  const toggleWeekday = (v) => {
    const cur = config.weekdays || [1,2,3,4,5];
    set("weekdays", cur.includes(v) ? cur.filter(x => x !== v) : [...cur, v].sort((a,b) => a-b));
  };
  const toggleMonthDay = (v) => {
    const cur = config.monthDays || [1];
    set("monthDays", cur.includes(v) ? cur.filter(x => x !== v) : [...cur, v].sort((a,b) => a-b));
  };

  const mode = config.mode || "daily";
  const iS = { backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 3, color: S.textBright, fontSize: 10, padding: "3px 6px", outline: "none", width: "100%" };
  const lS = { fontSize: 9, color: S.textDim, textTransform: "uppercase", letterSpacing: "0.06em", display: "block", marginBottom: 3 };
  const color = NODE_COLORS.trigger;

  // Cron-Preview
  const cronPreview = config.cron
    ? config.cron.split(";").slice(0,2).join(" | ") + (config.cron.split(";").length > 2 ? " …" : "")
    : "–";

  return (
    <BaseNode node={node} color={color} icon="⏰" label="Trigger"
      onRemove={onRemove} onPositionChange={onPositionChange} width={260}
      runResult={runResult}
      outputPorts={[{
        id: "out", label: "Starte Pipeline", portRef: outputPortRef,
        onDragStart: e => {
          e.stopPropagation();
          e.dataTransfer.setData("from_node", node.id);
          e.dataTransfer.setData("from_port", "out");
        }
      }]}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>

        {/* Auslöser */}
        <div>
          <label style={lS}>Auslöser</label>
          <select style={iS} value={config.trigger_mode || "schedule"} onChange={e => set("trigger_mode", e.target.value)}>
            <option value="schedule">Zeitplan</option>
            <option value="manual">Manuell</option>
            <option value="ftp_event">FTP-Ereignis</option>
          </select>
        </div>

        {(config.trigger_mode === "schedule" || !config.trigger_mode) && (<>

          {/* Modus */}
          <div>
            <label style={lS}>Intervall</label>
            <div style={{ display: "flex", gap: 3 }}>
              {["daily", "weekly", "monthly"].map(m => (
                <button key={m} onClick={() => set("mode", m)} style={{
                  flex: 1, padding: "3px 0", borderRadius: 3, fontSize: 9, fontWeight: 700, cursor: "pointer",
                  border: `1px solid ${mode === m ? color : S.border}`,
                  backgroundColor: mode === m ? color + "20" : "transparent",
                  color: mode === m ? color : S.textDim,
                }}>
                  {m === "daily" ? "Täglich" : m === "weekly" ? "Wöchentl." : "Monatl."}
                </button>
              ))}
            </div>
          </div>

          {/* Startzeit + Intervall */}
          <div style={{ display: "flex", gap: 6 }}>
            <div style={{ flex: 1 }}>
              <label style={lS}>Startzeit</label>
              <input type="time" style={iS} value={config.time || "06:00"} onChange={e => set("time", e.target.value)} />
            </div>
            <div style={{ flex: 1 }}>
              <label style={lS}>Alle X Min</label>
              <input type="number" style={iS} min={0} max={720} value={config.intervalMin || 0}
                onChange={e => set("intervalMin", parseInt(e.target.value) || 0)}
                placeholder="0 = einmalig" />
            </div>
          </div>

          {/* Wochentage */}
          {mode === "weekly" && (
            <div>
              <label style={lS}>Wochentage</label>
              <div style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
                {WEEKDAYS.map(d => (
                  <ChipBtn key={d.v} label={d.l} active={(config.weekdays || [1,2,3,4,5]).includes(d.v)} onClick={() => toggleWeekday(d.v)} />
                ))}
              </div>
            </div>
          )}

          {/* Monatstage */}
          {mode === "monthly" && (
            <div>
              <label style={lS}>Tage im Monat</label>
              <div style={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
                {Array.from({ length: 31 }, (_, i) => i + 1).map(d => (
                  <ChipBtn key={d} label={String(d).padStart(2,"0")} active={(config.monthDays || [1]).includes(d)} onClick={() => toggleMonthDay(d)} />
                ))}
              </div>
            </div>
          )}

          {/* Cron-Preview */}
          <div style={{ fontSize: 9, color: S.textDim, padding: "3px 6px", borderRadius: 3, backgroundColor: color + "08", border: `1px solid ${color}22`, fontFamily: "monospace" }}>
            {cronPreview}
          </div>

        </>)}

        {config.trigger_mode === "manual" && (
          <p style={{ fontSize: 9, color: S.textDim, fontStyle: "italic" }}>Pipeline wird nur manuell gestartet.</p>
        )}
        {config.trigger_mode === "ftp_event" && (
          <p style={{ fontSize: 9, color: S.textDim, fontStyle: "italic" }}>Wird durch FTP-Node ausgelöst wenn neue Dateien ankommen.</p>
        )}
      </div>
    </BaseNode>
  );
}
