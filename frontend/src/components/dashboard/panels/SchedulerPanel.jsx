import { useState, useEffect, useCallback } from "react";
import { Clock, Play, Square, CalendarClock, CheckCircle2, XCircle, History, X, Plus, Trash2, Pencil, ChevronDown, Loader2, RefreshCw, Check } from "lucide-react";
import api from "../../../api/client";
import { S } from "../constants";
import ToggleChip from "../shared/ToggleChip";
import Modal from "../shared/Modal";

const TODAY = new Date().toISOString().slice(0, 10);

function buildCronExprs(mode, startTime, intervalMin, weekdays, monthDays) {
  // Returns array of cron expressions (one per repetition step within a day)
  // startTime: "HH:MM", intervalMin: number (0 = no repeat)
  // weekdays: array of 0-6, monthDays: array of 1-31
  const [h, m] = startTime.split(":").map(Number);
  const interval = parseInt(intervalMin) || 0;

  // Build time slots: start, start+interval, start+2*interval, ... until end of day
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

  // Build cron expressions
  return slots.map(({ hh, mm }) => {
    if (mode === "daily")   return `${mm} ${hh} * * *`;
    if (mode === "weekly")  {
      const days = weekdays.length > 0 ? weekdays.join(",") : "*";
      return `${mm} ${hh} * * ${days}`;
    }
    if (mode === "monthly") {
      const days = monthDays.length > 0 ? monthDays.join(",") : "1";
      return `${mm} ${hh} ${days} * *`;
    }
    return `${mm} ${hh} * * *`;
  });
}

function parseCronToConfig(cron) {
  // Try to reverse-parse a saved cron back to structured config
  // Returns { mode, startTime, weekdays, monthDays } or null
  try {
    const p = cron.trim().split(/\s+/);
    if (p.length !== 5) return null;
    const [mm, hh, dom, , dow] = p;
    const time = `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
    if (dom === "*" && dow === "*") return { mode: "daily", startTime: time };
    if (dom === "*" && dow !== "*") return { mode: "weekly", startTime: time, weekdays: dow.split(",").map(Number) };
    if (dom !== "*" && dow === "*") return { mode: "monthly", startTime: time, monthDays: dom.split(",").map(Number) };
  } catch { /* ignore */ }
  return null;
}

// ─── Checkbox Toggle Button ────────────────────────────────────────────────────

function JobFormModal({ mappings, projectId, onClose, onSaved, existing }) {
  const existingConfig = existing ? parseCronToConfig(existing.cron_expr) : null;

  const [name, setName] = useState(existing?.name || "");
  const [mappingId, setMappingId] = useState(existing?.mapping_id || "");
  const [startDate, setStartDate] = useState(existing?.start_date || TODAY);
  const [endDate, setEndDate] = useState(existing?.end_date || "2099-12-31");
  const [mode, setMode] = useState(existingConfig?.mode || "daily");
  const [startTime, setStartTime] = useState(existingConfig?.startTime || "06:00");
  const [intervalMin, setIntervalMin] = useState(0);
  const [weekdays, setWeekdays] = useState(existingConfig?.weekdays || [1, 2, 3, 4, 5]);
  const [monthDays, setMonthDays] = useState(existingConfig?.monthDays || [1]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const toggleWeekday = (v) => setWeekdays((p) => p.includes(v) ? p.filter((x) => x !== v) : [...p, v].sort((a, b) => a - b));
  const toggleMonthDay = (v) => setMonthDays((p) => p.includes(v) ? p.filter((x) => x !== v) : [...p, v].sort((a, b) => a - b));

  // Preview of generated cron expressions
  const cronExprs = buildCronExprs(mode, startTime, intervalMin, weekdays, monthDays);
  const cronPreview = cronExprs.length <= 4
    ? cronExprs.join("  |  ")
    : `${cronExprs.slice(0, 3).join("  |  ")}  … (+${cronExprs.length - 3} weitere)`;

  const handleSave = async () => {
    setError("");
    if (!name.trim()) { setError("Name fehlt"); return; }
    if (!existing && !mappingId) { setError("Mapping fehlt"); return; }
    if (mode === "weekly" && weekdays.length === 0) { setError("Mindestens einen Wochentag wählen"); return; }
    if (mode === "monthly" && monthDays.length === 0) { setError("Mindestens einen Tag wählen"); return; }
    if (startDate && endDate && startDate > endDate) { setError("Startdatum muss vor dem Enddatum liegen"); return; }
    const allCrons = cronExprs.join(";");
    setSaving(true);
    try {
      if (existing) {
        await api.patch(`/api/scheduler/jobs/${existing.id}`, { name, cron_expr: allCrons, start_date: startDate, end_date: endDate });
      } else {
        await api.post("/api/scheduler/jobs", {
          name, mapping_id: parseInt(mappingId),
          cron_expr: allCrons,
          start_date: startDate,
          end_date: endDate,
          project_id: projectId,
        });
      }
      onSaved();
    } catch (e) {
      setError(e.response?.data?.detail || "Fehler beim Speichern");
    } finally {
      setSaving(false);
    }
  };

  const labelStyle = { fontSize: 11, color: S.textDim, marginBottom: 4 };
  const rowStyle = { display: "flex", gap: 8, alignItems: "center" };

  return (
    <Modal title={existing ? "Job bearbeiten" : "Neuer Scheduler-Job"} onClose={onClose} width="max-w-lg">
      <div className="flex flex-col gap-5" style={{ minWidth: 420 }}>

        {/* Name */}
        <div className="flex flex-col gap-1">
          <label style={labelStyle}>Name</label>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)}
            placeholder="z.B. Täglicher Rechnungsexport" autoFocus />
        </div>

        {/* Mapping */}
        {!existing && (
          <div className="flex flex-col gap-1">
            <label style={labelStyle}>Mapping</label>
            <select className="input" value={mappingId} onChange={(e) => setMappingId(e.target.value)}>
              <option value="">– Mapping wählen –</option>
              {mappings.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          </div>
        )}

        {/* Start / End Date */}
        <div style={{ display: "flex", gap: 16 }}>
          <div className="flex flex-col gap-1" style={{ flex: 1 }}>
            <label style={labelStyle}>Startdatum</label>
            <input type="date" className="input" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1" style={{ flex: 1 }}>
            <label style={labelStyle}>Enddatum</label>
            <input type="date" className="input" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
          </div>
        </div>

        {/* Mode Tabs */}
        <div className="flex flex-col gap-2">
          <label style={labelStyle}>Intervall</label>
          <div style={{ display: "flex", gap: 6 }}>
            {["daily", "weekly", "monthly"].map((m) => (
              <button key={m} onClick={() => setMode(m)} style={{
                flex: 1, padding: "6px 0", borderRadius: 8, fontSize: 12, fontWeight: 500, cursor: "pointer",
                border: `1px solid ${mode === m ? "var(--accent)" : "var(--border)"}`,
                backgroundColor: mode === m ? "rgba(252,228,153,0.12)" : "transparent",
                color: mode === m ? "var(--accent)" : S.textDim,
                transition: "all 0.12s",
              }}>
                {m === "daily" ? "Täglich" : m === "weekly" ? "Wöchentlich" : "Monatlich"}
              </button>
            ))}
          </div>
        </div>

        {/* Weekday picker */}
        {mode === "weekly" && (
          <div className="flex flex-col gap-2">
            <label style={labelStyle}>Wochentage</label>
            <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
              {WEEKDAYS.map((d) => (
                <ToggleChip key={d.value} label={d.label} active={weekdays.includes(d.value)}
                  onClick={() => toggleWeekday(d.value)} />
              ))}
            </div>
          </div>
        )}

        {/* Month day picker */}
        {mode === "monthly" && (
          <div className="flex flex-col gap-2">
            <label style={labelStyle}>Tage im Monat</label>
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
              {Array.from({ length: 31 }, (_, i) => i + 1).map((d) => (
                <ToggleChip key={d} label={String(d).padStart(2, "0")} active={monthDays.includes(d)}
                  onClick={() => toggleMonthDay(d)} />
              ))}
            </div>
          </div>
        )}

        {/* Time + Interval */}
        <div style={{ display: "flex", gap: 16 }}>
          <div className="flex flex-col gap-1" style={{ flex: 1 }}>
            <label style={labelStyle}>Startzeit</label>
            <input type="time" className="input" value={startTime}
              onChange={(e) => setStartTime(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1" style={{ flex: 1 }}>
            <label style={labelStyle}>Intervall in Minuten <span style={{ opacity: 0.5 }}>(0 = einmalig)</span></label>
            <input type="number" className="input" min={0} max={1439} value={intervalMin}
              onChange={(e) => setIntervalMin(Math.max(0, parseInt(e.target.value) || 0))} />
          </div>
        </div>

        {/* Cron Preview */}
        <div style={{ padding: "8px 12px", borderRadius: 8, backgroundColor: "rgba(0,0,0,0.25)", border: `1px solid ${S.border}` }}>
          <p style={{ fontSize: 10, color: S.textDim, marginBottom: 2 }}>Generierte Ausführungszeiten (Cron)</p>
          <p style={{ fontSize: 11, fontFamily: "monospace", color: S.accent, wordBreak: "break-all" }}>{cronPreview}</p>
          {cronExprs.length > 1 && (
            <p style={{ fontSize: 10, color: S.textDim, marginTop: 2 }}>{cronExprs.length} Ausführungen pro Tag/Woche/Monat</p>
          )}
        </div>

        {error && <p className="text-xs" style={{ color: "#e07070" }}>{error}</p>}

        <div className="flex gap-3 justify-end">
          <button onClick={onClose} className="btn-ghost text-xs">Abbrechen</button>
          <button onClick={handleSave} disabled={saving} className="btn-primary text-xs">
            {saving && <Loader2 size={12} className="animate-spin" />} Speichern
          </button>
        </div>
      </div>
    </Modal>
  );
}

function RunHistoryModal({ job, onClose }) {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    api.get(`/api/scheduler/jobs/${job.id}/runs`).then(({ data }) => setRuns(data)).finally(() => setLoading(false));
  }, [job.id]);

  const statusIcon = (s) => s === "success" ? <CheckCircle2 size={13} style={{ color: "#6ee7b7" }} />
    : s === "error" ? <XCircle size={13} style={{ color: "#e07070" }} />
    : <Loader2 size={13} className="animate-spin" style={{ color: S.accent }} />;

  return (
    <Modal title={`Protokoll: ${job.name}`} onClose={onClose}>
      <div style={{ minWidth: 480, maxHeight: 400, overflowY: "auto" }}>
        {loading ? <div className="text-xs" style={{ color: S.textDim }}>Lade...</div>
          : runs.length === 0 ? <div className="text-xs" style={{ color: S.textDim }}>Noch keine Läufe</div>
          : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
              <thead><tr style={{ color: S.textDim, borderBottom: `1px solid ${S.border}` }}>
                <th className="text-left pb-2">Status</th>
                <th className="text-left pb-2">Gestartet</th>
                <th className="text-left pb-2">Dauer</th>
                <th className="text-left pb-2">Zeilen</th>
                <th className="text-left pb-2">Auslöser</th>
              </tr></thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id} style={{ borderBottom: `1px solid ${S.border}` }}>
                    <td className="py-2 flex items-center gap-1">{statusIcon(r.status)} {r.status}</td>
                    <td className="py-2">{r.started_at ? new Date(r.started_at).toLocaleString("de-DE") : "–"}</td>
                    <td className="py-2">{r.duration_sec != null ? `${r.duration_sec}s` : "–"}</td>
                    <td className="py-2">{r.rows_processed ?? "–"}</td>
                    <td className="py-2" style={{ color: S.textDim }}>{r.triggered_by}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        {runs.find((r) => r.error_msg) && (
          <div className="mt-3 p-2 rounded text-xs font-mono" style={{ backgroundColor: "rgba(224,112,112,0.08)", color: "#e07070" }}>
            {runs.find((r) => r.error_msg)?.error_msg}
          </div>
        )}
      </div>
    </Modal>
  );
}

function SchedulerPanel({ mappings, projectId, canEdit }) {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [showHistory, setShowHistory] = useState(null);
  const [triggering, setTriggering] = useState(null);

  const loadJobs = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/api/scheduler/jobs", { params: projectId ? { project_id: projectId } : {} });
      setJobs(data);
    } finally { setLoading(false); }
  };

  useEffect(() => { loadJobs(); }, [projectId]);

  const toggleActive = async (job) => {
    await api.patch(`/api/scheduler/jobs/${job.id}`, { active: !job.active });
    loadJobs();
  };

  const deleteJob = async (id) => {
    if (!window.confirm("Job wirklich löschen?")) return;
    await api.delete(`/api/scheduler/jobs/${id}`);
    loadJobs();
  };

  const triggerNow = async (job) => {
    setTriggering(job.id);
    try {
      await api.post(`/api/scheduler/jobs/${job.id}/trigger`);
      setTimeout(loadJobs, 2000);
    } finally { setTimeout(() => setTriggering(null), 1500); }
  };

  const statusColor = (s) => s === "success" ? "#6ee7b7" : s === "error" ? "#e07070" : S.accent;
  const statusLabel = (s) => s === "success" ? "Erfolgreich" : s === "error" ? "Fehler" : s === "running" ? "Läuft..." : "–";

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-sm font-medium uppercase tracking-widest" style={{ color: S.accent }}>Scheduler</h1>
          <p className="text-xs mt-0.5" style={{ color: S.textDim }}>
            {jobs.length > 0 ? `${jobs.length} Jobs` : "Noch keine Scheduler-Jobs"}
            {projectId && <span> · Gefiltert nach Projekt</span>}
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={loadJobs} className="btn-ghost text-xs"><RefreshCw size={12} /> Aktualisieren</button>
          {canEdit && <button onClick={() => setShowForm(true)} className="btn-primary text-xs"><Plus size={13} /> Neuer Job</button>}
        </div>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-xs" style={{ color: S.textDim }}><Loader2 size={13} className="animate-spin" /> Lade...</div>
      ) : jobs.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 gap-3" style={{ color: S.textDim }}>
          <CalendarClock size={36} style={{ opacity: 0.3 }} />
          <p className="text-sm">Noch keine Scheduler-Jobs</p>
          {canEdit && <button onClick={() => setShowForm(true)} className="btn-primary text-xs mt-2"><Plus size={12} /> Ersten Job erstellen</button>}
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {jobs.map((job) => {
            const mapping = mappings.find((m) => m.id === job.mapping_id);
            return (
              <div key={job.id} className="card" style={{ borderColor: job.active ? S.border : "rgba(255,255,255,0.04)" }}>
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-3 min-w-0">
                    <CalendarClock size={16} style={{ color: job.active ? S.accent : S.textDim, flexShrink: 0, marginTop: 2 }} />
                    <div className="min-w-0">
                      <p className="font-medium text-sm" style={{ color: job.active ? S.textBright : S.textDim }}>{job.name}</p>
                      <p className="text-xs mt-0.5 font-mono" style={{ color: S.textDim }}>
                        {(() => {
                          const parts = job.cron_expr.split(";").filter(Boolean);
                          if (parts.length === 1) return parts[0];
                          const times = parts.map((c) => { const p = c.trim().split(/\s+/); return `${p[1].padStart(2,"0")}:${p[0].padStart(2,"0")}`; });
                          return times.length <= 4 ? times.join(" · ") : `${times.slice(0,3).join(" · ")} … (+${times.length-3})`;
                        })()}
                      </p>
                      <p className="text-xs mt-0.5" style={{ color: S.textDim }}>
                        Mapping: <span style={{ color: S.textMain }}>{mapping?.name || `#${job.mapping_id}`}</span>
                      </p>
                      {(job.start_date || job.end_date) && (
                        <p className="text-xs mt-0.5" style={{ color: S.textDim }}>
                          {job.start_date && <span>ab {new Date(job.start_date).toLocaleDateString("de-DE")}</span>}
                          {job.start_date && job.end_date && <span> · </span>}
                          {job.end_date && job.end_date !== "2099-12-31" && <span>bis {new Date(job.end_date).toLocaleDateString("de-DE")}</span>}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {canEdit && (
                      <button onClick={() => triggerNow(job)} title="Jetzt ausführen"
                        className="btn-ghost text-xs" style={{ padding: "4px 8px" }}>
                        {triggering === job.id ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
                      </button>
                    )}
                    <button onClick={() => setShowHistory(job)} title="Protokoll" className="btn-ghost text-xs" style={{ padding: "4px 8px" }}>
                      <History size={12} />
                    </button>
                    {canEdit && (
                      <>
                        <button onClick={() => { setEditing(job); setShowForm(true); }} title="Bearbeiten"
                          className="btn-ghost text-xs" style={{ padding: "4px 8px" }}>
                          <Pencil size={12} />
                        </button>
                        <button onClick={() => toggleActive(job)} title={job.active ? "Deaktivieren" : "Aktivieren"}
                          className="btn-ghost text-xs" style={{ padding: "4px 8px", color: job.active ? "#6ee7b7" : S.textDim }}>
                          {job.active ? <CheckCircle2 size={12} /> : <Square size={12} />}
                        </button>
                        <button onClick={() => deleteJob(job.id)} className="btn-ghost text-xs"
                          style={{ padding: "4px 8px" }}
                          onMouseEnter={(e) => e.currentTarget.style.color = "#e07070"}
                          onMouseLeave={(e) => e.currentTarget.style.color = ""}>
                          <Trash2 size={12} />
                        </button>
                      </>
                    )}
                  </div>
                </div>

                {/* Status-Zeile */}
                <div className="flex items-center gap-4 mt-3 text-xs" style={{ color: S.textDim }}>
                  {job.last_run && (
                    <span style={{ color: statusColor(job.last_run.status) }}>
                      Letzter Lauf: {statusLabel(job.last_run.status)}
                      {job.last_run.started_at && ` · ${new Date(job.last_run.started_at).toLocaleString("de-DE")}`}
                      {job.last_run.duration_sec != null && ` · ${job.last_run.duration_sec}s`}
                      {job.last_run.rows_processed != null && ` · ${job.last_run.rows_processed} Zeilen`}
                    </span>
                  )}
                  {job.next_run && (
                    <span><Clock size={10} style={{ display: "inline", marginRight: 3 }} />
                      Nächster Lauf: {new Date(job.next_run).toLocaleString("de-DE")}
                    </span>
                  )}
                  {!job.active && <span style={{ color: "#e07070" }}>Inaktiv</span>}
                </div>

                {job.last_run?.error_msg && (
                  <div className="mt-2 px-2 py-1 rounded text-xs font-mono truncate"
                    style={{ backgroundColor: "rgba(224,112,112,0.08)", color: "#e07070" }}>
                    {job.last_run.error_msg}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {showForm && (
        <JobFormModal
          mappings={mappings}
          projectId={projectId}
          existing={editing}
          onClose={() => { setShowForm(false); setEditing(null); }}
          onSaved={() => { setShowForm(false); setEditing(null); loadJobs(); }}
        />
      )}
      {showHistory && <RunHistoryModal job={showHistory} onClose={() => setShowHistory(null)} />}
    </div>
  );
}

// ─── Change Password Modal ────────────────────────────────────────────────────

export { SchedulerPanel, JobFormModal, RunHistoryModal };
