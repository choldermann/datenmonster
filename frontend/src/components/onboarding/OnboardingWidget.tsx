import { useState, useEffect } from "react";
import { CheckCircle2, Circle, X, Minus, ChevronUp, Rocket, Loader2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import api from "../../api/client";

const STEPS = [
  {
    key:   "connection",
    label: "DB-Verbindung anlegen",
    sub:   "Datenbank anbinden (SQL Server, PostgreSQL, MySQL)",
    tab:   "connections",
    check: () => api.get("/api/connections/").then(r => Array.isArray(r.data) && r.data.length > 0),
  },
  {
    key:   "dataset",
    label: "Erstes Dataset importieren",
    sub:   "CSV, Excel, Datenbankabfrage oder Plugin",
    tab:   "datasets",
    check: () => api.get("/api/datasets/").then(r => Array.isArray(r.data) && r.data.length > 0),
  },
  {
    key:   "mapping",
    label: "Erstes Mapping erstellen",
    sub:   "Felder verbinden, transformieren und verknüpfen",
    tab:   "mappings",
    check: () => api.get("/api/mappings/").then(r => Array.isArray(r.data) && r.data.length > 0),
  },
  {
    key:   "pipeline",
    label: "Pipeline einrichten",
    sub:   "Schritte automatisieren und zeitgesteuert ausführen",
    tab:   "pipelines",
    check: () => api.get("/api/pipelines/").then(r => Array.isArray(r.data) && r.data.length > 0),
  },
];

const ACCENT = "var(--accent)";

interface Props {
  open: boolean;
  onClose: () => void;
  /** Wenn true: schließt sich nach 5s automatisch wenn alles erledigt ist */
  autoClose?: boolean;
}

export default function OnboardingWidget({ open, onClose, autoClose = false }: Props) {
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(false);
  const [done, setDone] = useState<Record<string, boolean | null>>(
    Object.fromEntries(STEPS.map(s => [s.key, null]))
  );

  // Checks neu ausführen wenn Widget geöffnet wird
  useEffect(() => {
    if (!open) return;
    setDone(Object.fromEntries(STEPS.map(s => [s.key, null])));
    let cancelled = false;
    STEPS.forEach(step => {
      step.check()
        .then(r => { if (!cancelled) setDone(prev => ({ ...prev, [step.key]: r })); })
        .catch(() => { if (!cancelled) setDone(prev => ({ ...prev, [step.key]: false })); });
    });
    return () => { cancelled = true; };
  }, [open]);

  const completedCount = STEPS.filter(s => done[s.key] === true).length;
  const allDone        = STEPS.every(s => done[s.key] === true);

  // Auto-close wenn alles erledigt (nur im autoClose-Modus)
  useEffect(() => {
    if (!open || !autoClose || !allDone) return;
    const t = setTimeout(onClose, 5000);
    return () => clearTimeout(t);
  }, [open, autoClose, allDone, onClose]);

  // Widget beim Öffnen immer aufgeklappt zeigen
  useEffect(() => { if (open) setCollapsed(false); }, [open]);

  if (!open) return null;

  // ── Minimiert ──────────────────────────────────────────────────────────────
  if (collapsed) {
    return (
      <div onClick={() => setCollapsed(false)} title="Erste Schritte anzeigen"
        style={{
          position: "fixed", bottom: 24, left: 24, zIndex: 950,
          display: "flex", alignItems: "center", gap: 8,
          padding: "8px 14px", borderRadius: 20,
          backgroundColor: "var(--bg-card)", border: "1px solid var(--border)",
          boxShadow: "0 4px 20px rgba(0,0,0,0.4)",
          cursor: "pointer", userSelect: "none" as const,
        }}
        onMouseEnter={e => (e.currentTarget.style.borderColor = ACCENT)}
        onMouseLeave={e => (e.currentTarget.style.borderColor = "var(--border)")}
      >
        <Rocket size={14} style={{ color: ACCENT }} />
        <span style={{ fontSize: 11, color: "var(--text-bright)", fontWeight: 600 }}>
          {allDone ? "Alles erledigt 🎉" : `${completedCount} / ${STEPS.length} Schritte`}
        </span>
        <ChevronUp size={12} style={{ color: "var(--text-dim)" }} />
      </div>
    );
  }

  // ── Vollansicht ────────────────────────────────────────────────────────────
  return (
    <div style={{
      position: "fixed", bottom: 24, left: 24, zIndex: 950,
      width: 300, borderRadius: 10,
      backgroundColor: "var(--bg-card)", border: "1px solid var(--border)",
      boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
      overflow: "hidden",
    }}>
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 14px", borderBottom: "1px solid var(--border)",
        background: "linear-gradient(135deg, rgba(252,228,153,0.08) 0%, transparent 100%)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <Rocket size={14} style={{ color: ACCENT }} />
          <span style={{ fontSize: 12, fontWeight: 700, color: "var(--text-bright)" }}>
            Erste Schritte
          </span>
        </div>
        <div style={{ display: "flex", gap: 4 }}>
          <button onClick={() => setCollapsed(true)} title="Minimieren"
            style={{ background: "none", border: "none", cursor: "pointer", padding: 3,
              color: "var(--text-dim)", display: "flex", alignItems: "center" }}
            onMouseEnter={e => (e.currentTarget.style.color = "var(--text-bright)")}
            onMouseLeave={e => (e.currentTarget.style.color = "var(--text-dim)")}>
            <Minus size={13} />
          </button>
          <button onClick={onClose} title="Schließen"
            style={{ background: "none", border: "none", cursor: "pointer", padding: 3,
              color: "var(--text-dim)", display: "flex", alignItems: "center" }}
            onMouseEnter={e => (e.currentTarget.style.color = "#e07070")}
            onMouseLeave={e => (e.currentTarget.style.color = "var(--text-dim)")}>
            <X size={13} />
          </button>
        </div>
      </div>

      {/* Fortschrittsbalken */}
      <div style={{ height: 3, backgroundColor: "rgba(255,255,255,0.05)" }}>
        <div style={{
          height: "100%", backgroundColor: ACCENT,
          width: `${(completedCount / STEPS.length) * 100}%`,
          transition: "width 0.5s ease", borderRadius: "0 2px 2px 0",
        }} />
      </div>

      {/* Schritte — immer sichtbar */}
      <div style={{ padding: "8px 0" }}>
        {STEPS.map((step, i) => {
          const isDone    = done[step.key] === true;
          const isLoading = done[step.key] === null;
          const isNext    = !isDone && !isLoading && STEPS.slice(0, i).every(s => done[s.key] === true);

          return (
            <div key={step.key}
              onClick={() => !isDone && navigate(`/dashboard?tab=${step.tab}`)}
              style={{
                display: "flex", alignItems: "flex-start", gap: 10,
                padding: "8px 14px", cursor: isDone ? "default" : "pointer",
                transition: "background 0.15s",
              }}
              onMouseEnter={e => { if (!isDone) e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.03)"; }}
              onMouseLeave={e => { e.currentTarget.style.backgroundColor = "transparent"; }}
            >
              {isLoading
                ? <Loader2 size={16} style={{ color: "var(--text-dim)", flexShrink: 0, marginTop: 1, animation: "spin 1s linear infinite" }} />
                : isDone
                ? <CheckCircle2 size={16} style={{ color: "#6ee7b7", flexShrink: 0, marginTop: 1 }} />
                : <Circle size={16} style={{ color: isNext ? ACCENT : "var(--text-dim)", flexShrink: 0, marginTop: 1 }} />
              }
              <div style={{ flex: 1, minWidth: 0 }}>
                <p style={{
                  fontSize: 11, fontWeight: 600, margin: 0,
                  color: isDone ? "#6ee7b7" : isNext ? "var(--text-bright)" : "var(--text-main)",
                }}>
                  {step.label}
                </p>
                {!isDone && (
                  <p style={{ fontSize: 10, color: "var(--text-dim)", margin: "2px 0 0" }}>
                    {step.sub}
                  </p>
                )}
              </div>
              {!isDone && isNext && (
                <span style={{ fontSize: 9, color: ACCENT, fontWeight: 700,
                  alignSelf: "center", flexShrink: 0, letterSpacing: "0.05em" }}>
                  JETZT →
                </span>
              )}
            </div>
          );
        })}
        {allDone && (
          <div style={{ margin: "4px 14px 4px", padding: "6px 10px", borderRadius: 6,
            backgroundColor: "rgba(110,231,183,0.08)", border: "1px solid rgba(110,231,183,0.2)",
            fontSize: 11, color: "#6ee7b7", textAlign: "center" }}>
            🎉 Alles eingerichtet — Datenmonster ist bereit!
          </div>
        )}
      </div>

      {/* Footer */}
      <div style={{
        padding: "6px 14px 10px", borderTop: "1px solid var(--border)",
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <span style={{ fontSize: 10, color: "var(--text-dim)" }}>
          {completedCount} von {STEPS.length} abgeschlossen
        </span>
        {autoClose && allDone && (
          <span style={{ fontSize: 10, color: "var(--text-dim)" }}>schließt gleich…</span>
        )}
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
