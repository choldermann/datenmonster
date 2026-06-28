import { useEffect, useState, useCallback } from "react";
import api from "../../../api/client";

const C = {
  success: { bg: "rgba(110,231,183,0.12)", border: "rgba(110,231,183,0.3)", text: "#6ee7b7", label: "Erfolgreich" },
  error:   { bg: "rgba(224,112,112,0.12)", border: "rgba(224,112,112,0.3)", text: "#e07070", label: "Fehler" },
  warning: { bg: "rgba(251,191,36,0.12)",  border: "rgba(251,191,36,0.3)",  text: "#fbbf24", label: "Warnung" },
  active:  { bg: "rgba(56,189,248,0.12)",  border: "rgba(56,189,248,0.3)",  text: "#38bdf8", label: "Aktiv" },
  inactive:{ bg: "rgba(255,255,255,0.04)", border: "var(--border)",         text: "var(--text-dim)", label: "Inaktiv" },
};

const s = {
  card: { background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden" },
  cardHeader: { padding: "10px 16px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" },
  cardTitle: { fontSize: 13, fontWeight: 600, color: "var(--text-bright)", margin: 0 },
  kpi: { background: "var(--bg-elevated)", borderRadius: 8, padding: "14px 16px", border: "1px solid var(--border)" },
  kpiLabel: { fontSize: 11, color: "var(--text-dim)", margin: "0 0 6px", textTransform: "uppercase", letterSpacing: "0.05em" },
  kpiValue: { fontSize: 26, fontWeight: 700, margin: 0, lineHeight: 1 },
  colHeader: { fontSize: 10, fontWeight: 600, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.05em" },
};

function StatusBadge({ status }) {
  const c = C[status] || C.inactive;
  const loadSystem = async () => {
    setSystemLoading(true);
    try {
      const { data } = await api.get("/api/monitoring/system");
      setSystemStats(data);
    } catch (e) {
      console.error("System-Stats Fehler:", e);
    } finally {
      setSystemLoading(false);
    }
  };

  return (
    <span style={{
      fontSize: 11, fontWeight: 600, padding: "3px 9px", borderRadius: 20,
      background: c.bg, border: `1px solid ${c.border}`, color: c.text, whiteSpace: "nowrap",
    }}>{c.label}</span>
  );
}

function Dot({ color }) {
  return <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, display: "inline-block", flexShrink: 0 }} />;
}

function ToggleButton({ pipeline, onToggle, toggling }) {
  const isActive = pipeline.active;
  const isToggling = toggling === pipeline.id;
  return (
    <button
      onClick={() => onToggle(pipeline.id, isActive)}
      disabled={isToggling}
      title={isActive ? "Pipeline pausieren" : "Pipeline starten"}
      style={{
        fontSize: 11, fontWeight: 600,
        padding: "4px 10px", borderRadius: 6, cursor: isToggling ? "wait" : "pointer",
        background: isActive ? "rgba(224,112,112,0.1)" : "rgba(110,231,183,0.1)",
        border: `1px solid ${isActive ? "rgba(224,112,112,0.3)" : "rgba(110,231,183,0.3)"}`,
        color: isActive ? "#e07070" : "#6ee7b7",
        opacity: isToggling ? 0.6 : 1,
        whiteSpace: "nowrap", transition: "opacity 0.15s",
      }}
      onMouseEnter={e => { if (!isToggling) e.currentTarget.style.opacity = "0.75"; }}
      onMouseLeave={e => { e.currentTarget.style.opacity = isToggling ? "0.6" : "1"; }}
    >
      {isToggling ? "…" : isActive ? "Stopp" : "Start"}
    </button>
  );
}



function CopyIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
    </svg>
  );
}

function RefreshIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
    </svg>
  );
}

const DOCKER_STATUS_COLOR = {
  running:    { text: "#6ee7b7", bg: "rgba(110,231,183,0.12)", border: "rgba(110,231,183,0.3)",  label: "running" },
  exited:     { text: "#e07070", bg: "rgba(224,112,112,0.12)", border: "rgba(224,112,112,0.3)",  label: "exited" },
  paused:     { text: "#fbbf24", bg: "rgba(251,191,36,0.12)",  border: "rgba(251,191,36,0.3)",   label: "paused" },
  restarting: { text: "#38bdf8", bg: "rgba(56,189,248,0.12)",  border: "rgba(56,189,248,0.3)",   label: "restarting" },
  created:    { text: "#a78bfa", bg: "rgba(167,139,250,0.12)", border: "rgba(167,139,250,0.3)",  label: "created" },
};
function dockerStatusColor(status: string) {
  return DOCKER_STATUS_COLOR[status] || { text: "var(--text-dim)", bg: "rgba(255,255,255,0.05)", border: "rgba(255,255,255,0.12)", label: status };
}

function DockerLogModal({ container, logs, onClose, onRefresh, loading }) {
  const [copied, setCopied] = useState(false);
  if (!container) return null;

  const handleCopy = async () => {
    try { await navigator.clipboard.writeText(logs); }
    catch { const ta = document.createElement("textarea"); ta.value = logs; document.body.appendChild(ta); ta.select(); document.execCommand("copy"); document.body.removeChild(ta); }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 1100, background: "rgba(0,0,0,0.75)", display: "flex", alignItems: "center", justifyContent: "center", padding: "2rem" }}>
      <div onClick={e => e.stopPropagation()} style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, width: "100%", maxWidth: 900, maxHeight: "85vh", display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 7px", borderRadius: 20, ...(() => { const c = dockerStatusColor(container.status); return { background: c.bg, color: c.text, border: `1px solid ${c.border}` }; })(), textTransform: "uppercase" }}>{container.status}</span>
            <p style={{ fontSize: 14, fontWeight: 600, margin: 0, color: "var(--text-bright)", fontFamily: "var(--font-mono, monospace)" }}>{container.name}</p>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={onRefresh} disabled={loading} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, padding: "5px 12px", borderRadius: 6, cursor: loading ? "wait" : "pointer", background: "var(--bg-elevated)", border: "1px solid var(--border)", color: "var(--text-main)" }}>
              <RefreshIcon /> {loading ? "Lädt…" : "Aktualisieren"}
            </button>
            <button onClick={handleCopy} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, padding: "5px 12px", borderRadius: 6, cursor: "pointer", background: copied ? "rgba(110,231,183,0.15)" : "var(--bg-elevated)", border: `1px solid ${copied ? "rgba(110,231,183,0.4)" : "var(--border)"}`, color: copied ? "#6ee7b7" : "var(--text-main)", transition: "all 0.2s" }}>
              {copied ? <CheckIcon /> : <CopyIcon />} {copied ? "Kopiert!" : "Kopieren"}
            </button>
            <button onClick={onClose} style={{ display: "flex", alignItems: "center", justifyContent: "center", width: 28, height: 28, borderRadius: 6, cursor: "pointer", background: "transparent", border: "1px solid var(--border)", color: "var(--text-dim)" }}
              onMouseEnter={e => e.currentTarget.style.color = "var(--text-bright)"}
              onMouseLeave={e => e.currentTarget.style.color = "var(--text-dim)"}
            ><CloseIcon /></button>
          </div>
        </div>
        <div style={{ overflow: "auto", padding: "12px 16px", flexGrow: 1 }}>
          {loading ? (
            <p style={{ color: "var(--text-dim)", fontSize: 13, textAlign: "center", paddingTop: "2rem" }}>Logs werden geladen…</p>
          ) : logs ? (
            <pre style={{ margin: 0, fontSize: 11, lineHeight: 1.6, color: "var(--text-main)", fontFamily: "var(--font-mono, monospace)", whiteSpace: "pre-wrap", wordBreak: "break-all" }}>{logs}</pre>
          ) : (
            <p style={{ color: "var(--text-dim)", fontSize: 13, textAlign: "center", paddingTop: "2rem" }}>Keine Log-Ausgabe</p>
          )}
        </div>
      </div>
    </div>
  );
}

function LogDetailModal({ log, onClose }) {
  const [copied, setCopied] = useState(false);
  if (!log) return null;

  // Vollständigen Text für Kopieren zusammenbauen
  const fullText = [
    `Level:    ${log.level}`,
    `Quelle:   ${log.pipeline}`,
    `Aktion:   ${log.action}`,
    `Zeit:     ${log.created_at || log.time}`,
    `Meldung:  ${log.message}`,
    log.rows != null ? `Zeilen:   ${log.rows}` : null,
    log.details ? `\nDetails:\n${typeof log.details === "string" ? log.details : JSON.stringify(log.details, null, 2)}` : null,
  ].filter(Boolean).join("\n");

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(fullText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (e) {
      // Fallback
      const ta = document.createElement("textarea");
      ta.value = fullText;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const lvlC = lvlColor(log.level);

  // Details parsen falls JSON-String
  let details = null;
  if (log.details) {
    try {
      details = typeof log.details === "string" ? JSON.parse(log.details) : log.details;
    } catch {
      details = { raw: log.details };
    }
  }

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, zIndex: 1000,
        background: "rgba(0,0,0,0.7)",
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: "2rem",
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border)",
          borderRadius: 12,
          width: "100%", maxWidth: 760,
          maxHeight: "85vh",
          display: "flex", flexDirection: "column",
          overflow: "hidden",
        }}
      >
        {/* Modal Header */}
        <div style={{
          padding: "14px 18px",
          borderBottom: "1px solid var(--border)",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          flexShrink: 0,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <LevelBadge level={log.level} />
            <p style={{ fontSize: 14, fontWeight: 600, margin: 0, color: "var(--text-bright)" }}>
              {log.pipeline}
            </p>
            {log.action && (
              <span style={{ fontSize: 12, color: "var(--text-dim)" }}>· {log.action}</span>
            )}
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <button onClick={handleCopy} style={{
              display: "flex", alignItems: "center", gap: 6,
              fontSize: 12, fontWeight: 500, padding: "5px 12px", borderRadius: 6, cursor: "pointer",
              background: copied ? "rgba(110,231,183,0.15)" : "var(--bg-elevated)",
              border: `1px solid ${copied ? "rgba(110,231,183,0.4)" : "var(--border)"}`,
              color: copied ? "#6ee7b7" : "var(--text-main)",
              transition: "all 0.2s",
            }}>
              {copied ? <CheckIcon /> : <CopyIcon />}
              {copied ? "Kopiert!" : "Kopieren"}
            </button>
            <button onClick={onClose} style={{
              display: "flex", alignItems: "center", justifyContent: "center",
              width: 28, height: 28, borderRadius: 6, cursor: "pointer",
              background: "transparent", border: "1px solid var(--border)",
              color: "var(--text-dim)",
            }}
              onMouseEnter={e => e.currentTarget.style.color = "var(--text-bright)"}
              onMouseLeave={e => e.currentTarget.style.color = "var(--text-dim)"}
            ><CloseIcon /></button>
          </div>
        </div>

        {/* Modal Body scrollbar */}
        <div style={{ overflow: "auto", padding: "16px 18px", display: "flex", flexDirection: "column", gap: 14 }}>

          {/* Meta-Infos */}
          <div style={{
            display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 8,
          }}>
            {[
              { label: "Zeit", value: log.created_at || log.time },
              { label: "Aktion", value: log.action || "—" },
              { label: "Zeilen", value: log.rows != null ? log.rows : "—" },
            ].map(({ label, value }) => (
              <div key={label} style={{
                background: "var(--bg-elevated)", borderRadius: 6, padding: "8px 12px",
                border: "1px solid var(--border)",
              }}>
                <p style={{ fontSize: 10, fontWeight: 600, color: "var(--text-dim)", margin: "0 0 3px", textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</p>
                <p style={{ fontSize: 13, color: "var(--text-bright)", margin: 0 }}>{String(value)}</p>
              </div>
            ))}
          </div>

          {/* Meldung */}
          <div>
            <p style={{ fontSize: 11, fontWeight: 600, color: "var(--text-dim)", margin: "0 0 6px", textTransform: "uppercase", letterSpacing: "0.05em" }}>Meldung</p>
            <div style={{
              background: "var(--bg-elevated)", borderRadius: 6, padding: "10px 14px",
              border: "1px solid var(--border)", fontSize: 13, color: "var(--text-main)",
              lineHeight: 1.6, wordBreak: "break-word",
            }}>{log.message}</div>
          </div>

          {/* Details / Traceback */}
          {details && (
            <div>
              <p style={{ fontSize: 11, fontWeight: 600, color: "var(--text-dim)", margin: "0 0 6px", textTransform: "uppercase", letterSpacing: "0.05em" }}>Details</p>

              {/* Traceback extra hervorheben */}
              {details.traceback && (
                <div style={{ marginBottom: 10 }}>
                  <p style={{ fontSize: 11, fontWeight: 600, color: "#e07070", margin: "0 0 4px" }}>Stacktrace</p>
                  <pre style={{
                    background: "rgba(224,112,112,0.06)", border: "1px solid rgba(224,112,112,0.2)",
                    borderRadius: 6, padding: "10px 14px", fontSize: 11, color: "#e07070",
                    overflowX: "auto", margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-word",
                    fontFamily: "var(--font-mono, monospace)", lineHeight: 1.5,
                  }}>{details.traceback}</pre>
                </div>
              )}

              {/* Restliche Details als Key-Value */}
              {Object.entries(details)
                .filter(([k]) => k !== "traceback")
                .map(([key, val]) => (
                  <div key={key} style={{
                    display: "grid", gridTemplateColumns: "160px 1fr",
                    borderTop: "1px solid var(--border)", padding: "7px 0",
                    gap: 12, alignItems: "start",
                  }}>
                    <span style={{ fontSize: 12, color: "var(--text-dim)", fontWeight: 500 }}>{key}</span>
                    <span style={{
                      fontSize: 12, color: "var(--text-main)", wordBreak: "break-word",
                      fontFamily: typeof val === "object" ? "var(--font-mono, monospace)" : "inherit",
                    }}>
                      {typeof val === "object" ? JSON.stringify(val, null, 2) : String(val)}
                    </span>
                  </div>
                ))
              }
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const LOG_LEVELS = ["all", "info", "success", "warning", "error"];
const PAGE_SIZE = 15;

const lvlColor = (level) => {
  if (level === "error")   return { text: "#e07070", bg: "rgba(224,112,112,0.12)", border: "rgba(224,112,112,0.3)" };
  if (level === "warning") return { text: "#fbbf24", bg: "rgba(251,191,36,0.12)",  border: "rgba(251,191,36,0.3)" };
  if (level === "success") return { text: "#6ee7b7", bg: "rgba(110,231,183,0.12)", border: "rgba(110,231,183,0.3)" };
  return { text: "var(--text-dim)", bg: "rgba(255,255,255,0.05)", border: "rgba(255,255,255,0.1)" };
};

function LevelBadge({ level }) {
  const c = lvlColor(level);
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 20,
      background: c.bg, color: c.text, border: `1px solid ${c.border}`,
      textTransform: "uppercase", whiteSpace: "nowrap",
    }}>{level}</span>
  );
}

function TrashIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/>
    </svg>
  );
}

function SystemLogTable({ logs, onDeleteOne, onDeleteAll, deleting }) {
  const [levelFilter, setLevelFilter] = useState("all");
  const [page, setPage] = useState(0);
  const [confirmClear, setConfirmClear] = useState(false);
  const [selectedLog, setSelectedLog] = useState(null);

  const filtered = logs.filter(l => levelFilter === "all" || l.level === levelFilter);
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const pageItems = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const counts = LOG_LEVELS.slice(1).reduce((acc, lvl) => {
    acc[lvl] = logs.filter(l => l.level === lvl).length;
    return acc;
  }, {});

  const handleLevelFilter = (lvl) => { setLevelFilter(lvl); setPage(0); };

  return (
    <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden" }}>
      {selectedLog && <LogDetailModal log={selectedLog} onClose={() => setSelectedLog(null)} />}

      {/* Header mit Filter + Löschen-Alle */}
      <div style={{
        padding: "10px 16px", borderBottom: "1px solid var(--border)",
        display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8,
      }}>
        <p style={{ fontSize: 13, fontWeight: 600, color: "var(--text-bright)", margin: 0 }}>System-Log</p>
        <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
          {LOG_LEVELS.map(lvl => {
            const active = levelFilter === lvl;
            const c = lvl === "all" ? null : lvlColor(lvl);
            const count = lvl === "all" ? logs.length : counts[lvl] || 0;
            return (
              <button key={lvl} onClick={() => handleLevelFilter(lvl)} style={{
                fontSize: 11, fontWeight: 600, padding: "3px 10px", borderRadius: 20, cursor: "pointer",
                background: active ? (c ? c.bg : "rgba(255,255,255,0.08)") : "transparent",
                border: active ? `1px solid ${c ? c.border : "rgba(255,255,255,0.2)"}` : "1px solid var(--border)",
                color: active ? (c ? c.text : "var(--text-bright)") : "var(--text-dim)",
                transition: "all 0.15s",
              }}>
                {lvl === "all" ? "Alle" : lvl.charAt(0).toUpperCase() + lvl.slice(1)}
                {count > 0 && <span style={{ marginLeft: 4, opacity: 0.7 }}>({count})</span>}
              </button>
            );
          })}

          {/* Trennlinie */}
          <div style={{ width: 1, height: 18, background: "var(--border)", margin: "0 2px" }} />

          {/* Alle löschen */}
          {!confirmClear ? (
            <button onClick={() => setConfirmClear(true)} disabled={logs.length === 0}
              title="Alle Logs löschen"
              style={{
                fontSize: 11, fontWeight: 600, padding: "3px 10px", borderRadius: 20, cursor: logs.length === 0 ? "default" : "pointer",
                background: "rgba(224,112,112,0.08)", border: "1px solid rgba(224,112,112,0.25)",
                color: "#e07070", display: "flex", alignItems: "center", gap: 5,
                opacity: logs.length === 0 ? 0.4 : 1,
              }}>
              <TrashIcon /> Log leeren
            </button>
          ) : (
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <span style={{ fontSize: 11, color: "#e07070" }}>Wirklich löschen?</span>
              <button onClick={() => { onDeleteAll(); setConfirmClear(false); }} style={{
                fontSize: 11, fontWeight: 600, padding: "3px 10px", borderRadius: 20, cursor: "pointer",
                background: "rgba(224,112,112,0.15)", border: "1px solid rgba(224,112,112,0.4)", color: "#e07070",
              }}>Ja, löschen</button>
              <button onClick={() => setConfirmClear(false)} style={{
                fontSize: 11, padding: "3px 10px", borderRadius: 20, cursor: "pointer",
                background: "transparent", border: "1px solid var(--border)", color: "var(--text-dim)",
              }}>Abbrechen</button>
            </div>
          )}
        </div>
      </div>

      {/* Tabelle scrollbar */}
      <div style={{ overflowX: "auto", maxHeight: 380, overflowY: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead style={{ position: "sticky", top: 0, background: "var(--bg-elevated)", zIndex: 1 }}>
            <tr style={{ borderBottom: "1px solid var(--border)" }}>
              {["Level", "Quelle", "Aktion", "Meldung", "Zeilen", "Zeit", ""].map((h, i) => (
                <th key={i} style={{
                  padding: "7px 14px", textAlign: "left",
                  fontSize: 10, fontWeight: 600, color: "var(--text-dim)",
                  textTransform: "uppercase", letterSpacing: "0.05em", whiteSpace: "nowrap",
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageItems.length === 0 ? (
              <tr><td colSpan={7} style={{ padding: "2rem", textAlign: "center", color: "var(--text-dim)" }}>
                Keine Einträge für diesen Filter
              </td></tr>
            ) : pageItems.map((log, i) => (
              <tr key={log.id || i}
                style={{ borderTop: "1px solid var(--border)", transition: "background 0.1s", cursor: "pointer" }}
                onMouseEnter={e => e.currentTarget.style.background = "var(--bg-elevated)"}
                onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                onClick={() => setSelectedLog(log)}
              >
                <td style={{ padding: "7px 14px", whiteSpace: "nowrap" }}>
                  <LevelBadge level={log.level} />
                </td>
                <td style={{ padding: "7px 14px", color: "var(--text-main)", whiteSpace: "nowrap", maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis" }}>{log.pipeline}</td>
                <td style={{ padding: "7px 14px", color: "var(--text-dim)", whiteSpace: "nowrap" }}>{log.action}</td>
                <td
                  style={{ padding: "7px 14px", color: "var(--text-main)", maxWidth: 320, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", cursor: "pointer" }}
                  title="Klicken für Details"
                  onClick={() => setSelectedLog(log)}
                  onMouseEnter={e => e.currentTarget.style.color = "var(--accent)"}
                  onMouseLeave={e => e.currentTarget.style.color = "var(--text-main)"}
                >
                  {log.message && log.message.length > 80 ? log.message.slice(0, 80) + "…" : log.message}
                </td>
                <td style={{ padding: "7px 14px", color: "var(--text-dim)", textAlign: "right", whiteSpace: "nowrap" }}>{log.rows != null ? log.rows : "—"}</td>
                <td style={{ padding: "7px 14px", color: "var(--text-dim)", whiteSpace: "nowrap" }}>{log.time}</td>
                <td style={{ padding: "7px 10px", textAlign: "center" }}>
                  <button
                    onClick={e => { e.stopPropagation(); log.id && onDeleteOne(log.id); }}
                    disabled={!log.id || deleting === log.id}
                    title="Eintrag löschen"
                    style={{
                      background: "transparent", border: "none", cursor: log.id ? "pointer" : "default",
                      color: deleting === log.id ? "var(--text-dim)" : "var(--text-dim)",
                      padding: "3px 5px", borderRadius: 4, display: "flex", alignItems: "center",
                      opacity: deleting === log.id ? 0.4 : 0.5,
                      transition: "all 0.15s",
                    }}
                    onMouseEnter={e => { if (log.id) { e.currentTarget.style.color = "#e07070"; e.currentTarget.style.opacity = "1"; e.currentTarget.style.background = "rgba(224,112,112,0.1)"; }}}
                    onMouseLeave={e => { e.currentTarget.style.color = "var(--text-dim)"; e.currentTarget.style.opacity = "0.5"; e.currentTarget.style.background = "transparent"; }}
                  >
                    <TrashIcon />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Paginierung */}
      {totalPages > 1 && (
        <div style={{
          padding: "10px 16px", borderTop: "1px solid var(--border)",
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <span style={{ fontSize: 12, color: "var(--text-dim)" }}>
            {filtered.length} Einträge · Seite {page + 1} von {totalPages}
          </span>
          <div style={{ display: "flex", gap: 6 }}>
            <button onClick={() => setPage(0)} disabled={page === 0}
              style={{ fontSize: 12, padding: "4px 10px", borderRadius: 6, cursor: page === 0 ? "default" : "pointer",
                background: "var(--bg-elevated)", border: "1px solid var(--border)",
                color: page === 0 ? "var(--text-dim)" : "var(--text-main)", opacity: page === 0 ? 0.4 : 1 }}>«</button>
            <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
              style={{ fontSize: 12, padding: "4px 10px", borderRadius: 6, cursor: page === 0 ? "default" : "pointer",
                background: "var(--bg-elevated)", border: "1px solid var(--border)",
                color: page === 0 ? "var(--text-dim)" : "var(--text-main)", opacity: page === 0 ? 0.4 : 1 }}>‹</button>
            {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
              const p = Math.max(0, Math.min(page - 2, totalPages - 5)) + i;
              return (
                <button key={p} onClick={() => setPage(p)}
                  style={{ fontSize: 12, padding: "4px 10px", borderRadius: 6, cursor: "pointer",
                    background: p === page ? "rgba(110,231,183,0.15)" : "var(--bg-elevated)",
                    border: `1px solid ${p === page ? "rgba(110,231,183,0.4)" : "var(--border)"}`,
                    color: p === page ? "#6ee7b7" : "var(--text-main)", fontWeight: p === page ? 600 : 400 }}>
                  {p + 1}
                </button>
              );
            })}
            <button onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page === totalPages - 1}
              style={{ fontSize: 12, padding: "4px 10px", borderRadius: 6, cursor: page === totalPages - 1 ? "default" : "pointer",
                background: "var(--bg-elevated)", border: "1px solid var(--border)",
                color: page === totalPages - 1 ? "var(--text-dim)" : "var(--text-main)", opacity: page === totalPages - 1 ? 0.4 : 1 }}>›</button>
            <button onClick={() => setPage(totalPages - 1)} disabled={page === totalPages - 1}
              style={{ fontSize: 12, padding: "4px 10px", borderRadius: 6, cursor: page === totalPages - 1 ? "default" : "pointer",
                background: "var(--bg-elevated)", border: "1px solid var(--border)",
                color: page === totalPages - 1 ? "var(--text-dim)" : "var(--text-main)", opacity: page === totalPages - 1 ? 0.4 : 1 }}>»</button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function MonitoringPanel() {
  const [data, setData] = useState(null);
  const [systemStats, setSystemStats] = useState(null);
  const [systemLoading, setSystemLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [filterProject, setFilterProject] = useState("all");
  const [lastUpdate, setLastUpdate] = useState(null);
  const [activeTab, setActiveTab] = useState("overview"); // "overview" | "system"
  const [toggling, setToggling] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [dockerContainers, setDockerContainers] = useState<any[]>([]);
  const [dockerLoading, setDockerLoading] = useState(false);
  const [dockerError, setDockerError] = useState<string | null>(null);
  const [dockerActioning, setDockerActioning] = useState<string | null>(null);
  const [dockerLogModal, setDockerLogModal] = useState<{ container: any; logs: string; loading: boolean } | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await api.get("/api/monitoring/");
      setData(res.data);
      setLastUpdate(new Date());
    } catch (e) {
      console.error("Monitoring laden fehlgeschlagen", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 30000);
    return () => clearInterval(interval);
  }, [load]);

  const handleDeleteLog = useCallback(async (logId) => {
    setDeleting(logId);
    try {
      await api.delete(`/api/monitoring/logs/${logId}`);
      await load();
    } catch (e) {
      console.error("Log löschen fehlgeschlagen", e);
    } finally {
      setDeleting(null);
    }
  }, [load]);

  const handleDeleteAllLogs = useCallback(async () => {
    try {
      await api.delete("/api/monitoring/logs");
      await load();
    } catch (e) {
      console.error("Logs leeren fehlgeschlagen", e);
    }
  }, [load]);

  const handleToggle = useCallback(async (pipelineId, currentlyActive) => {
    setToggling(pipelineId);
    try {
      await api.post(`/api/pipelines/${pipelineId}/toggle`);
      await load();
    } catch (e) {
      console.error("Toggle fehlgeschlagen", e);
    } finally {
      setToggling(null);
    }
  }, [load]);

  const loadDocker = useCallback(async () => {
    setDockerLoading(true);
    setDockerError(null);
    try {
      const { data } = await api.get("/api/monitoring/docker");
      if (data.error) setDockerError(data.error);
      setDockerContainers(data.containers || []);
    } catch (e) {
      setDockerError("Docker-Daten konnten nicht geladen werden");
    } finally {
      setDockerLoading(false);
    }
  }, []);

  const dockerAction = useCallback(async (containerId: string, action: "start" | "stop" | "restart") => {
    setDockerActioning(containerId + "_" + action);
    try {
      await api.post(`/api/monitoring/docker/${containerId}/${action}`);
      await loadDocker();
    } catch (e) {
      console.error(`Docker ${action} fehlgeschlagen`, e);
    } finally {
      setDockerActioning(null);
    }
  }, [loadDocker]);

  const openDockerLogs = useCallback(async (container: any) => {
    setDockerLogModal({ container, logs: "", loading: true });
    try {
      const { data } = await api.get(`/api/monitoring/docker/${container.id}/logs`, { params: { lines: 200 } });
      setDockerLogModal({ container, logs: data.logs || "", loading: false });
    } catch (e) {
      setDockerLogModal(prev => prev ? { ...prev, logs: "Fehler beim Laden der Logs", loading: false } : null);
    }
  }, []);

  const refreshDockerLogs = useCallback(async () => {
    if (!dockerLogModal) return;
    setDockerLogModal(prev => prev ? { ...prev, loading: true } : null);
    try {
      const { data } = await api.get(`/api/monitoring/docker/${dockerLogModal.container.id}/logs`, { params: { lines: 200 } });
      setDockerLogModal(prev => prev ? { ...prev, logs: data.logs || "", loading: false } : null);
    } catch (e) {
      setDockerLogModal(prev => prev ? { ...prev, logs: "Fehler beim Laden der Logs", loading: false } : null);
    }
  }, [dockerLogModal]);

  if (loading) return (
    <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-dim)", fontSize: 13 }}>
      Monitoring wird geladen…
    </div>
  );

  if (!data) return (
    <div style={{ padding: "3rem", textAlign: "center", color: "#e07070", fontSize: 13 }}>
      Monitoring-Daten konnten nicht geladen werden.
    </div>
  );

  const { summary, pipelines, errors, next_runs, projects, system_logs } = data;
  const filteredPipelines = filterProject === "all"
    ? pipelines
    : pipelines.filter(p => String(p.project_id) === filterProject);

  const loadSystem = async () => {
    setSystemLoading(true);
    try {
      const { data } = await api.get("/api/monitoring/system");
      setSystemStats(data);
    } catch (e) {
      console.error("System-Stats Fehler:", e);
    } finally {
      setSystemLoading(false);
    }
  };

  const hasErrors = errors.some(e => e.level === "error");
  const hasWarnings = errors.some(e => e.level === "warning");
  const alertColor = hasErrors ? "#e07070" : hasWarnings ? "#fbbf24" : "#6ee7b7";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20, padding: "4px 0" }}>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <h2 style={{ fontSize: 18, fontWeight: 700, margin: "0 0 4px", color: "var(--text-bright)" }}>Monitoring</h2>
          <p style={{ fontSize: 13, color: "var(--text-dim)", margin: 0 }}>Alle Projekte auf einen Blick</p>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          {lastUpdate && (
            <span style={{ fontSize: 11, color: "var(--text-dim)" }}>
              Aktualisiert: {lastUpdate.toLocaleTimeString("de-DE")}
            </span>
          )}
          <button onClick={load} style={{
            fontSize: 12, padding: "6px 14px", cursor: "pointer",
            background: "var(--bg-elevated)", border: "1px solid var(--border)",
            borderRadius: 6, color: "var(--text-main)", fontWeight: 500,
          }}
            onMouseEnter={e => e.currentTarget.style.borderColor = "var(--accent)"}
            onMouseLeave={e => e.currentTarget.style.borderColor = "var(--border)"}
          >Aktualisieren</button>
        </div>
      </div>

      {/* Tab Navigation */}
      <div style={{ display: "flex", gap: 4, borderBottom: "1px solid var(--border)", marginBottom: -4 }}>
        {[
          { id: "overview", label: "Übersicht" },
          { id: "system",   label: "System" },
        ].map(t => (
          <button key={t.id} onClick={() => { setActiveTab(t.id); if (t.id === "system") { loadSystem(); loadDocker(); } }}
            style={{
              fontSize: 12, fontWeight: 600, padding: "8px 16px", cursor: "pointer",
              background: "none", border: "none", borderBottom: activeTab === t.id ? "2px solid var(--accent)" : "2px solid transparent",
              color: activeTab === t.id ? "var(--accent)" : "var(--text-dim)",
              marginBottom: -1,
            }}>{t.label}</button>
        ))}
      </div>

      {activeTab === "system" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <button onClick={loadSystem} style={{ fontSize: 12, padding: "6px 14px", cursor: "pointer",
              background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 6,
              color: "var(--text-main)", fontWeight: 500 }}>
              {systemLoading ? "Lädt..." : "Aktualisieren"}
            </button>
          </div>

          {!systemStats && !systemLoading && (
            <div style={{ padding: "40px", textAlign: "center", color: "var(--text-dim)", fontSize: 13 }}>
              Klick auf Aktualisieren um System-Daten zu laden
            </div>
          )}

          {systemStats && (
            <>
              {/* Gauge-Kacheln */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0,1fr))", gap: 12 }}>
                {/* CPU */}
                <div style={s.kpi}>
                  <p style={s.kpiLabel}>CPU Auslastung</p>
                  <p style={{ ...s.kpiValue, color: systemStats.cpu_percent > 80 ? "#e07070" : systemStats.cpu_percent > 50 ? "#fbbf24" : "#6ee7b7" }}>
                    {systemStats.cpu_percent ?? "—"}%
                  </p>
                  <div style={{ marginTop: 10, height: 6, background: "var(--bg-elevated)", borderRadius: 3, overflow: "hidden" }}>
                    <div style={{ height: "100%", borderRadius: 3, width: `${systemStats.cpu_percent ?? 0}%`,
                      background: systemStats.cpu_percent > 80 ? "#e07070" : systemStats.cpu_percent > 50 ? "#fbbf24" : "#6ee7b7",
                      transition: "width 0.4s ease" }} />
                  </div>
                  <p style={{ fontSize: 10, color: "var(--text-dim)", marginTop: 4 }}>{systemStats.cpu_count} Kerne</p>
                </div>

                {/* RAM */}
                <div style={s.kpi}>
                  <p style={s.kpiLabel}>RAM Auslastung</p>
                  <p style={{ ...s.kpiValue, color: systemStats.ram_percent > 85 ? "#e07070" : systemStats.ram_percent > 65 ? "#fbbf24" : "#6ee7b7" }}>
                    {systemStats.ram_percent ?? "—"}%
                  </p>
                  <div style={{ marginTop: 10, height: 6, background: "var(--bg-elevated)", borderRadius: 3, overflow: "hidden" }}>
                    <div style={{ height: "100%", borderRadius: 3, width: `${systemStats.ram_percent ?? 0}%`,
                      background: systemStats.ram_percent > 85 ? "#e07070" : systemStats.ram_percent > 65 ? "#fbbf24" : "#6ee7b7",
                      transition: "width 0.4s ease" }} />
                  </div>
                  <p style={{ fontSize: 10, color: "var(--text-dim)", marginTop: 4 }}>
                    {systemStats.ram_used_gb} GB / {systemStats.ram_total_gb} GB
                  </p>
                </div>

                {/* Disk */}
                <div style={s.kpi}>
                  <p style={s.kpiLabel}>Speicherplatz</p>
                  <p style={{ ...s.kpiValue, color: systemStats.disk_percent > 90 ? "#e07070" : systemStats.disk_percent > 75 ? "#fbbf24" : "#6ee7b7" }}>
                    {systemStats.disk_percent ?? "—"}%
                  </p>
                  <div style={{ marginTop: 10, height: 6, background: "var(--bg-elevated)", borderRadius: 3, overflow: "hidden" }}>
                    <div style={{ height: "100%", borderRadius: 3, width: `${systemStats.disk_percent ?? 0}%`,
                      background: systemStats.disk_percent > 90 ? "#e07070" : systemStats.disk_percent > 75 ? "#fbbf24" : "#6ee7b7",
                      transition: "width 0.4s ease" }} />
                  </div>
                  <p style={{ fontSize: 10, color: "var(--text-dim)", marginTop: 4 }}>
                    {systemStats.disk_free_gb} GB frei / {systemStats.disk_total_gb} GB gesamt
                  </p>
                </div>
              </div>

              {/* Detail-Kacheln */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0,1fr))", gap: 12 }}>
                <div style={s.kpi}>
                  <p style={s.kpiLabel}>SQLite DB</p>
                  <p style={{ ...s.kpiValue, fontSize: 20, color: "var(--text-bright)" }}>
                    {systemStats.db_size_mb ?? "—"} MB
                  </p>
                </div>
                <div style={s.kpi}>
                  <p style={s.kpiLabel}>Dataset-Daten</p>
                  <p style={{ ...s.kpiValue, fontSize: 20, color: "var(--text-bright)" }}>
                    {systemStats.datasets_size_mb ?? "—"} MB
                  </p>
                  <p style={{ fontSize: 10, color: "var(--text-dim)", marginTop: 4 }}>
                    {systemStats.datasets_count} Dateien
                  </p>
                </div>
                <div style={s.kpi}>
                  <p style={s.kpiLabel}>Scheduler-Jobs</p>
                  <p style={{ ...s.kpiValue, fontSize: 20, color: systemStats.scheduler_jobs > 0 ? "#6ee7b7" : "var(--text-dim)" }}>
                    {systemStats.scheduler_jobs}
                  </p>
                </div>
                <div style={s.kpi}>
                  <p style={s.kpiLabel}>Uptime</p>
                  <p style={{ ...s.kpiValue, fontSize: 20, color: "var(--text-bright)" }}>
                    {systemStats.uptime_seconds != null
                      ? systemStats.uptime_seconds < 3600
                        ? `${Math.floor(systemStats.uptime_seconds / 60)} Min`
                        : systemStats.uptime_seconds < 86400
                          ? `${Math.floor(systemStats.uptime_seconds / 3600)} Std`
                          : `${Math.floor(systemStats.uptime_seconds / 86400)} Tage`
                      : "—"}
                  </p>
                </div>
              </div>

              {systemStats.psutil_unavailable && (
                <div style={{ padding: "12px 16px", borderRadius: 8, background: "rgba(251,191,36,0.08)",
                  border: "1px solid rgba(251,191,36,0.25)", fontSize: 12, color: "#fbbf24" }}>
                  psutil nicht installiert – CPU/RAM/Disk nicht verfügbar.
                  Im Container: <code>pip install psutil --break-system-packages</code>
                </div>
              )}
            </>
          )}

          {/* Docker Container */}
          {dockerLogModal && (
            <DockerLogModal
              container={dockerLogModal.container}
              logs={dockerLogModal.logs}
              loading={dockerLogModal.loading}
              onClose={() => setDockerLogModal(null)}
              onRefresh={refreshDockerLogs}
            />
          )}
          <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden" }}>
            <div style={{ padding: "10px 16px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <p style={{ fontSize: 13, fontWeight: 600, color: "var(--text-bright)", margin: 0 }}>Docker Container</p>
              <button onClick={loadDocker} disabled={dockerLoading} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, padding: "5px 12px", borderRadius: 6, cursor: dockerLoading ? "wait" : "pointer", background: "var(--bg-elevated)", border: "1px solid var(--border)", color: "var(--text-main)", opacity: dockerLoading ? 0.6 : 1 }}>
                <RefreshIcon /> {dockerLoading ? "Lädt…" : "Aktualisieren"}
              </button>
            </div>

            {dockerError && (
              <div style={{ padding: "12px 16px", background: "rgba(224,112,112,0.08)", borderBottom: "1px solid var(--border)", fontSize: 12, color: "#e07070" }}>
                {dockerError}
              </div>
            )}

            {dockerContainers.length === 0 && !dockerLoading && !dockerError ? (
              <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-dim)", fontSize: 13 }}>
                Keine Container gefunden
              </div>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border)", background: "var(--bg-elevated)" }}>
                      {["Status", "Name", "Image", "Ports", "Aktionen"].map((h, i) => (
                        <th key={i} style={{ padding: "7px 14px", textAlign: "left", fontSize: 10, fontWeight: 600, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.05em", whiteSpace: "nowrap" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {dockerContainers.map(c => {
                      const sc = dockerStatusColor(c.status);
                      const isRunning = c.status === "running";
                      const actionKey = dockerActioning?.startsWith(c.id) ? dockerActioning.split("_")[1] : null;
                      return (
                        <tr key={c.id} style={{ borderTop: "1px solid var(--border)" }}
                          onMouseEnter={e => e.currentTarget.style.background = "var(--bg-elevated)"}
                          onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                        >
                          <td style={{ padding: "9px 14px", whiteSpace: "nowrap" }}>
                            <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 20, background: sc.bg, color: sc.text, border: `1px solid ${sc.border}` }}>{sc.label}</span>
                          </td>
                          <td style={{ padding: "9px 14px", color: "var(--text-bright)", fontFamily: "var(--font-mono, monospace)", fontSize: 12, whiteSpace: "nowrap" }}>{c.name}</td>
                          <td style={{ padding: "9px 14px", color: "var(--text-dim)", fontSize: 11, maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={c.image}>{c.image}</td>
                          <td style={{ padding: "9px 14px", color: "var(--text-dim)", fontSize: 11, whiteSpace: "nowrap" }}>
                            {c.ports.length > 0 ? c.ports.join(", ") : <span style={{ opacity: 0.4 }}>—</span>}
                          </td>
                          <td style={{ padding: "9px 14px", whiteSpace: "nowrap" }}>
                            <div style={{ display: "flex", gap: 5 }}>
                              {!isRunning && (
                                <button onClick={() => dockerAction(c.id, "start")} disabled={!!dockerActioning}
                                  style={{ fontSize: 11, fontWeight: 600, padding: "3px 10px", borderRadius: 6, cursor: dockerActioning ? "wait" : "pointer", background: "rgba(110,231,183,0.1)", border: "1px solid rgba(110,231,183,0.3)", color: "#6ee7b7", opacity: actionKey === "start" ? 0.6 : 1 }}>
                                  {actionKey === "start" ? "…" : "Start"}
                                </button>
                              )}
                              {isRunning && (
                                <button onClick={() => dockerAction(c.id, "stop")} disabled={!!dockerActioning}
                                  style={{ fontSize: 11, fontWeight: 600, padding: "3px 10px", borderRadius: 6, cursor: dockerActioning ? "wait" : "pointer", background: "rgba(224,112,112,0.1)", border: "1px solid rgba(224,112,112,0.3)", color: "#e07070", opacity: actionKey === "stop" ? 0.6 : 1 }}>
                                  {actionKey === "stop" ? "…" : "Stopp"}
                                </button>
                              )}
                              {isRunning && (
                                <button onClick={() => dockerAction(c.id, "restart")} disabled={!!dockerActioning}
                                  style={{ fontSize: 11, fontWeight: 600, padding: "3px 10px", borderRadius: 6, cursor: dockerActioning ? "wait" : "pointer", background: "rgba(56,189,248,0.1)", border: "1px solid rgba(56,189,248,0.3)", color: "#38bdf8", opacity: actionKey === "restart" ? 0.6 : 1 }}>
                                  {actionKey === "restart" ? "…" : "Neustart"}
                                </button>
                              )}
                              <button onClick={() => openDockerLogs(c)}
                                style={{ fontSize: 11, fontWeight: 600, padding: "3px 10px", borderRadius: 6, cursor: "pointer", background: "rgba(255,255,255,0.05)", border: "1px solid var(--border)", color: "var(--text-dim)" }}
                                onMouseEnter={e => { e.currentTarget.style.color = "var(--text-bright)"; e.currentTarget.style.borderColor = "var(--text-dim)"; }}
                                onMouseLeave={e => { e.currentTarget.style.color = "var(--text-dim)"; e.currentTarget.style.borderColor = "var(--border)"; }}
                              >
                                Logs
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === "overview" && (
      <>

      {/* KPI Kacheln */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0,1fr))", gap: 12 }}>
        <div style={s.kpi}>
          <p style={s.kpiLabel}>Projekte</p>
          <p style={{ ...s.kpiValue, color: "var(--text-bright)" }}>{summary.projects}</p>
        </div>
        <div style={s.kpi}>
          <p style={s.kpiLabel}>Pipelines aktiv</p>
          <p style={{ ...s.kpiValue, color: summary.pipelines_active > 0 ? "#6ee7b7" : "var(--text-dim)" }}>
            {summary.pipelines_active}
          </p>
        </div>
        <div style={s.kpi}>
          <p style={s.kpiLabel}>Fehler heute</p>
          <p style={{ ...s.kpiValue, color: summary.errors_today > 0 ? "#e07070" : "#6ee7b7" }}>
            {summary.errors_today}
          </p>
        </div>
        <div style={s.kpi}>
          <p style={s.kpiLabel}>Läufe heute</p>
          <p style={{ ...s.kpiValue, color: "var(--text-bright)" }}>{summary.runs_today}</p>
        </div>
      </div>

      {/* Hauptbereich */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 300px", gap: 16 }}>

        {/* Pipeline Tabelle */}
        <div style={s.card}>
          <div style={s.cardHeader}>
            <p style={s.cardTitle}>Pipelines</p>
            <select
              value={filterProject}
              onChange={e => setFilterProject(e.target.value)}
              style={{
                fontSize: 12, padding: "4px 10px", cursor: "pointer",
                background: "var(--bg-elevated)", border: "1px solid var(--border)",
                borderRadius: 6, color: "var(--text-main)",
              }}
            >
              <option value="all">Alle Projekte</option>
              {projects.map(p => <option key={p.id} value={String(p.id)}>{p.name}</option>)}
            </select>
          </div>

          {/* Spalten-Header */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "1fr 110px 110px 130px 60px 80px",
            padding: "7px 16px",
            borderBottom: "1px solid var(--border)",
            gap: 8,
          }}>
            <span style={s.colHeader}>Pipeline</span>
            <span style={s.colHeader}>Status</span>
            <span style={s.colHeader}>Letzter Lauf</span>
            <span style={s.colHeader}>Nächster Lauf</span>
            <span style={s.colHeader}>Heute</span>
            <span style={s.colHeader}></span>
          </div>

          {filteredPipelines.length === 0 ? (
            <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-dim)", fontSize: 13 }}>
              Keine Pipelines gefunden
            </div>
          ) : filteredPipelines.map((p, i) => (
            <div key={p.id} style={{
              display: "grid",
              gridTemplateColumns: "1fr 110px 110px 130px 60px 80px",
              padding: "10px 16px",
              borderTop: "1px solid var(--border)",
              alignItems: "center",
              gap: 8,
            }}>
              <div style={{ minWidth: 0 }}>
                <p style={{ fontSize: 13, fontWeight: 500, margin: 0, color: "var(--text-bright)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.name}</p>
                <p style={{ fontSize: 11, color: "var(--text-dim)", margin: "2px 0 0" }}>{p.project}</p>
              </div>
              <div><StatusBadge status={p.status} /></div>
              <span style={{ fontSize: 12, color: "var(--text-dim)" }}>{p.last_run}</span>
              <span style={{ fontSize: 12, color: p.next_run ? "#38bdf8" : "var(--text-dim)" }}>
                {p.next_run || (p.active ? "—" : "Inaktiv")}
              </span>
              <span style={{ fontSize: 12, color: "var(--text-dim)", textAlign: "center" }}>{p.runs_today}</span>
              <ToggleButton pipeline={p} onToggle={handleToggle} toggling={toggling} />
            </div>
          ))}
        </div>

        {/* Rechte Spalte */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>

          {/* Fehler & Warnungen */}
          <div style={{
            ...s.card,
            borderColor: hasErrors ? "rgba(224,112,112,0.4)" : hasWarnings ? "rgba(251,191,36,0.3)" : "var(--border)",
          }}>
            <div style={s.cardHeader}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Dot color={alertColor} />
                <p style={s.cardTitle}>Fehler & Warnungen</p>
              </div>
              {errors.length > 0 && (
                <span style={{
                  fontSize: 11, fontWeight: 600, padding: "2px 7px", borderRadius: 20,
                  background: hasErrors ? "rgba(224,112,112,0.15)" : "rgba(251,191,36,0.15)",
                  color: hasErrors ? "#e07070" : "#fbbf24",
                }}>{errors.length}</span>
              )}
            </div>
            {errors.length === 0 ? (
              <div style={{ padding: "16px 14px", display: "flex", alignItems: "center", gap: 8 }}>
                <Dot color="#6ee7b7" />
                <span style={{ fontSize: 12, color: "var(--text-dim)" }}>Alles läuft problemlos</span>
              </div>
            ) : errors.slice(0, 6).map((e, i) => (
              <div key={i} style={{ padding: "10px 14px", borderTop: "1px solid var(--border)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                  <Dot color={e.level === "error" ? "#e07070" : "#fbbf24"} />
                  <p style={{ fontSize: 12, fontWeight: 600, margin: 0, color: "var(--text-bright)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {e.pipeline}
                  </p>
                </div>
                <p style={{ fontSize: 11, color: "var(--text-dim)", margin: "0 0 3px", paddingLeft: 14 }}>{e.message}</p>
                <p style={{ fontSize: 10, color: "var(--text-dim)", margin: 0, paddingLeft: 14, opacity: 0.7 }}>{e.time}</p>
              </div>
            ))}
          </div>

          {/* Nächste Läufe */}
          <div style={s.card}>
            <div style={s.cardHeader}>
              <p style={s.cardTitle}>Nächste Läufe</p>
            </div>
            {next_runs.length === 0 ? (
              <div style={{ padding: "16px 14px", fontSize: 12, color: "var(--text-dim)" }}>
                Keine geplanten Läufe
              </div>
            ) : next_runs.map((r, i) => (
              <div key={i} style={{
                padding: "10px 14px", borderTop: "1px solid var(--border)",
                display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8,
              }}>
                <div style={{ minWidth: 0 }}>
                  <p style={{ fontSize: 12, fontWeight: 500, margin: 0, color: "var(--text-bright)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {r.pipeline}
                  </p>
                  <p style={{ fontSize: 11, color: "var(--text-dim)", margin: "2px 0 0" }}>{r.cron}</p>
                </div>
                <span style={{ fontSize: 12, color: "#38bdf8", fontWeight: 600, whiteSpace: "nowrap" }}>
                  {r.next_run}
                </span>
              </div>
            ))}
          </div>

        </div>
      </div>

      {/* System-Log */}
      <SystemLogTable logs={system_logs || []} onDeleteOne={handleDeleteLog} onDeleteAll={handleDeleteAllLogs} deleting={deleting} />
      </>
      )}
    </div>
  );
}
// PATCH - wird durch write_monitoring.py ersetzt
