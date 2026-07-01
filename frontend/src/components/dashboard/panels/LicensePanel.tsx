import { useState, useEffect, useCallback, useRef } from "react";
import {
  AlertTriangle, BookOpen, Brain, Cable, Check, Clock, Database,
  Edit2, GitBranch, Key, Layers, Lock, LockOpen, Mail,
  Monitor, Package, Puzzle, RefreshCw, Server, Shield,
  ShieldCheck, ShieldOff, Trash2, Users, Workflow, X,
} from "lucide-react";

const BASE = "/api/license";

async function apiFetch(method: string, path: string, body?: unknown) {
  const token = localStorage.getItem("dm_token");
  const r = await fetch(path, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  return r.json();
}

interface Feature {
  id: string;
  name: string;
  description: string;
  category: string;
  free: boolean;
}

interface LicenseData {
  status: "free" | "active" | "grace" | "grace_expired" | "expired" | "invalid";
  plan: string;
  email: string | null;
  valid_until: string | null;
  last_check: string | null;
  grace_remaining: number | null;
  validation_mode: "online" | "cached" | "grace" | "offline" | "none";
  machine_id: string;
  active_features: string[];
  features: Feature[];
  category_order: string[];
  _offline?: boolean;
}

const STATUS_CONFIG: Record<string, { color: string; bg: string; border: string; icon: typeof ShieldCheck; label: string }> = {
  free:          { color: "#6b7280", bg: "var(--bg-input)",    border: "var(--border-3)",  icon: LockOpen,   label: "Kostenlos" },
  active:        { color: "#22c55e", bg: "#0d1a10",            border: "#1a3a22",           icon: ShieldCheck, label: "Lizenz aktiv" },
  grace:         { color: "#f59e0b", bg: "#1c1500",            border: "#3a2e00",           icon: Shield,      label: "Grace Period" },
  grace_expired: { color: "#ef4444", bg: "#1a0808",            border: "#3a1212",           icon: ShieldOff,   label: "Grace Period abgelaufen" },
  expired:       { color: "#ef4444", bg: "#1a0808",            border: "#3a1212",           icon: ShieldOff,   label: "Lizenz abgelaufen" },
  invalid:       { color: "#ef4444", bg: "#1a0808",            border: "#3a1212",           icon: ShieldOff,   label: "Ungültige Lizenz" },
};

const MODE_BADGE: Record<string, { label: string; color: string }> = {
  online:  { label: "Online",   color: "#22c55e" },
  cached:  { label: "Cache",    color: "#3b82f6" },
  grace:   { label: "Grace",    color: "#f59e0b" },
  offline: { label: "Offline",  color: "#a855f7" },
  none:    { label: "Kein Key", color: "#6b7280" },
};

const FEATURE_ICONS: Record<string, typeof Database> = {
  basic_etl:      Database,
  basic_export:   Package,
  unlimited:      Layers,
  db_write:       Database,
  pipelines:      Workflow,
  ftp_sftp:       Server,
  rest_sources:   Cable,
  mail_connector: Mail,
  ai_assistant:   Brain,
  ai_memory:      BookOpen,
  schema_catalog: GitBranch,
  form_builder:   Monitor,
  plugin_tier2:   Puzzle,
  multi_user:     Users,
  monitoring:     Monitor,
};

function FeatureRow({ feature, active }: { feature: Feature; active: boolean }) {
  const Icon = FEATURE_ICONS[feature.id] || Package;
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 12,
      padding: "10px 14px",
      background: active ? "#0d1a10" : "var(--bg-card)",
      border: `1px solid ${active ? "#1a3a22" : "var(--border-2)"}`,
      borderRadius: 8, marginBottom: 5,
    }}>
      <div style={{
        width: 30, height: 30, borderRadius: 7, flexShrink: 0,
        background: active ? "#1a3a22" : "var(--bg-hover)",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        <Icon size={14} color={active ? "#22c55e" : (feature.free ? "#22c55e" : "var(--text-6)")} />
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: active ? "#d1fae5" : "var(--text-5)" }}>
          {feature.name}
        </div>
        <div style={{ fontSize: 11, color: active ? "#4a8a60" : "var(--text-7)", marginTop: 1 }}>
          {feature.description}
        </div>
      </div>
      <div style={{
        fontSize: 10, fontWeight: 700, padding: "3px 9px", borderRadius: 20,
        background: active ? "#065f46" : "var(--bg-hover)",
        color: active ? "#22c55e" : "var(--text-6)",
        border: `1px solid ${active ? "#065f46" : "var(--border-3)"}`,
        textTransform: "uppercase", letterSpacing: "0.5px", flexShrink: 0,
        display: "flex", alignItems: "center", gap: 4,
      }}>
        {active ? (
          <><Check size={9} /> {feature.free ? "Kostenlos" : "Aktiv"}</>
        ) : (
          <><Lock size={9} /> Gesperrt</>
        )}
      </div>
    </div>
  );
}

export default function LicensePanel() {
  const [license, setLicense] = useState<LicenseData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [email, setEmail] = useState("");
  const [key, setKey] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notification, setNotification] = useState<{ type: "ok" | "err"; msg: string } | null>(null);
  const notifTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  function toast(type: "ok" | "err", msg: string) {
    if (notifTimer.current) clearTimeout(notifTimer.current);
    setNotification({ type, msg });
    notifTimer.current = setTimeout(() => setNotification(null), 3500);
  }

  const load = useCallback(async () => {
    const d = await apiFetch("GET", BASE + "/");
    setLicense(d);
    setEmail(d.email || "");
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function activate() {
    if (!key.trim() || !email.trim()) { toast("err", "Bitte Key und E-Mail eingeben"); return; }
    setSaving(true);
    const r = await apiFetch("POST", BASE + "/activate", { key: key.trim(), email: email.trim() });
    if (r.ok) {
      toast("ok", `Lizenz aktiviert: ${r.plan}${r.mode === "offline" ? " (Offline)" : ""}`);
      setShowForm(false);
      setKey("");
      load();
    } else {
      toast("err", r.error || "Aktivierung fehlgeschlagen");
    }
    setSaving(false);
  }

  async function refresh() {
    setRefreshing(true);
    const r = await apiFetch("POST", BASE + "/refresh");
    if (r.ok) { toast("ok", "Lizenz erfolgreich aktualisiert"); load(); }
    else       { toast("err", r.error || "Lizenzserver nicht erreichbar"); }
    setRefreshing(false);
  }

  async function deactivate() {
    const r = await apiFetch("DELETE", BASE + "/");
    if (r.ok) { toast("ok", "Lizenz entfernt"); load(); }
  }

  if (loading) return <div style={{ color: "var(--text-5)", padding: 40 }}>Lade Lizenzstatus…</div>;
  if (!license) return null;

  const sc       = STATUS_CONFIG[license.status] || STATUS_CONFIG.free;
  const StatusIcon = sc.icon;
  const isActive = license.status === "active";
  const isGrace  = license.status === "grace";
  const hasFull  = isActive || isGrace;
  const activeSet = new Set(license.active_features || []);
  const mode = license._offline ? "offline" : license.validation_mode;
  const mb = MODE_BADGE[mode] || MODE_BADGE.none;

  const grouped: Record<string, Feature[]> = {};
  const catOrder = license.category_order || [];
  for (const cat of catOrder) {
    grouped[cat] = (license.features || []).filter(f => f.category === cat);
  }

  return (
    <div style={{ maxWidth: 780 }}>

      {/* Notification */}
      {notification && (
        <div style={{
          padding: "10px 16px", marginBottom: 14, borderRadius: 8,
          background: notification.type === "ok" ? "#0d1a10" : "#1a0808",
          border: `1px solid ${notification.type === "ok" ? "#1a3a22" : "#3a1212"}`,
          color: notification.type === "ok" ? "#22c55e" : "#ef4444",
          fontSize: 13, display: "flex", alignItems: "center", gap: 8,
        }}>
          {notification.type === "ok" ? <Check size={14} /> : <X size={14} />}
          {notification.msg}
        </div>
      )}

      {/* Grace-Warnung */}
      {isGrace && (
        <div style={{
          padding: "12px 18px", marginBottom: 16, borderRadius: 10,
          background: "#1c1500", border: "1px solid #3a2e00",
          display: "flex", gap: 12, alignItems: "flex-start",
        }}>
          <AlertTriangle size={16} color="#f59e0b" style={{ marginTop: 1, flexShrink: 0 }} />
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: "#f59e0b" }}>Lizenzserver nicht erreichbar</div>
            <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 3, lineHeight: "18px" }}>
              Die Lizenz läuft im Offline-Modus. Noch{" "}
              {license.grace_remaining != null
                ? <strong style={{ color: "#f59e0b" }}>{license.grace_remaining} Tage</strong>
                : "einige Tage"}{" "}
              verbleibend. Bitte Verbindung zu <strong style={{ color: "#f59e0b" }}>monstersuite.de</strong> prüfen.
            </div>
          </div>
        </div>
      )}

      {/* Status-Banner */}
      <div style={{
        padding: "18px 22px", marginBottom: 22, borderRadius: 12,
        background: sc.bg, border: `1px solid ${sc.border}`,
        display: "flex", alignItems: "center", gap: 16,
      }}>
        <div style={{
          width: 46, height: 46, borderRadius: 12, flexShrink: 0,
          background: sc.border,
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <StatusIcon size={22} color={sc.color} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
            <div style={{ fontSize: 15, fontWeight: 700, color: sc.color }}>{sc.label}</div>
            <div style={{
              fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 20,
              background: mb.color + "22", color: mb.color,
              border: `1px solid ${mb.color}44`,
              textTransform: "uppercase", letterSpacing: "0.5px",
            }}>
              {mb.label}
            </div>
          </div>
          {hasFull && (
            <div style={{ fontSize: 13, color: "var(--text-3)", lineHeight: "20px" }}>
              Plan: <strong style={{ color: sc.color }}>{license.plan}</strong>
              {license.email && <> · {license.email}</>}
              {license.valid_until
                ? <> · Gültig bis <strong style={{ color: sc.color }}>{license.valid_until}</strong></>
                : <> · Unbegrenzt gültig</>}
            </div>
          )}
          {license.status === "free" && (
            <div style={{ fontSize: 13, color: "var(--text-5)", marginTop: 3 }}>
              {activeSet.size} / {(license.features || []).length} Features aktiv —{" "}
              Upgrade auf <strong style={{ color: "var(--text-3)" }}>monstersuite.de</strong>
            </div>
          )}
          {license.last_check && (
            <div style={{ fontSize: 11, color: "var(--text-4)", marginTop: 5, display: "flex", alignItems: "center", gap: 5 }}>
              <Clock size={11} />
              Zuletzt geprüft: {license.last_check.replace("T", " ")}
            </div>
          )}
          {license.machine_id && (
            <div style={{ fontSize: 10, color: "var(--text-6)", marginTop: 3, fontFamily: "monospace" }}>
              Machine-ID: {license.machine_id}
            </div>
          )}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6, flexShrink: 0 }}>
          {hasFull && (
            <button onClick={refresh} disabled={refreshing} style={{
              padding: "6px 12px", background: "transparent",
              border: `1px solid ${sc.border}`, borderRadius: 7,
              color: sc.color, fontSize: 11, cursor: "pointer",
              display: "flex", alignItems: "center", gap: 5,
            }}>
              <RefreshCw size={11} style={{ animation: refreshing ? "spin 1s linear infinite" : undefined }} />
              {refreshing ? "Prüfe…" : "Jetzt prüfen"}
            </button>
          )}
          {hasFull ? (
            <>
              <button onClick={() => setShowForm(f => !f)} style={{
                padding: "6px 12px", background: "transparent",
                border: `1px solid ${sc.border}`, borderRadius: 7,
                color: sc.color, fontSize: 11, cursor: "pointer",
                display: "flex", alignItems: "center", gap: 5,
              }}>
                <Edit2 size={11} /> Ändern
              </button>
              <button onClick={deactivate} style={{
                padding: "6px 12px", background: "transparent",
                border: "1px solid #3a1212", borderRadius: 7,
                color: "#ef4444", fontSize: 11, cursor: "pointer",
                display: "flex", alignItems: "center", gap: 5,
              }}>
                <Trash2 size={11} /> Entfernen
              </button>
            </>
          ) : (
            <button onClick={() => setShowForm(true)} style={{
              padding: "9px 18px", background: "var(--accent)",
              color: "var(--accent-fg)", border: "none", borderRadius: 8,
              fontSize: 13, fontWeight: 700, cursor: "pointer",
              display: "flex", alignItems: "center", gap: 6,
            }}>
              <Key size={14} /> Lizenz aktivieren
            </button>
          )}
        </div>
      </div>

      {/* Aktivierungsformular */}
      {showForm && (
        <div style={{
          background: "var(--bg-card)", border: "1px solid var(--accent-bd)",
          borderRadius: 12, padding: "20px 22px", marginBottom: 22,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: "var(--accent)" }}>Lizenz aktivieren</div>
            <button onClick={() => { setShowForm(false); setKey(""); }} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-5)", padding: 4 }}>
              <X size={14} />
            </button>
          </div>
          <div style={{ fontSize: 12, color: "var(--text-5)", marginBottom: 16 }}>
            Lizenzen kaufen und verwalten auf <strong style={{ color: "var(--text-3)" }}>monstersuite.de</strong>.
            Die Aktivierung benötigt eine Internetverbindung.
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
            <div>
              <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: "var(--text-5)", textTransform: "uppercase", letterSpacing: ".8px", marginBottom: 5 }}>E-Mail</label>
              <input
                style={{ width: "100%", padding: "9px 12px", background: "var(--bg-input)", border: "1px solid var(--border-3)", borderRadius: 8, color: "var(--text-3)", fontSize: 13, outline: "none", boxSizing: "border-box", fontFamily: "inherit" }}
                value={email} onChange={e => setEmail(e.target.value)} placeholder="deine@email.de"
              />
            </div>
            <div />
          </div>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: "var(--text-5)", textTransform: "uppercase", letterSpacing: ".8px", marginBottom: 5 }}>Lizenzschlüssel</label>
            <textarea rows={3}
              style={{ width: "100%", padding: "9px 12px", background: "var(--bg-input)", border: "1px solid var(--border-3)", borderRadius: 8, color: "#22c55e", fontSize: 11, outline: "none", boxSizing: "border-box", fontFamily: "monospace", resize: "vertical" }}
              value={key} onChange={e => setKey(e.target.value)} placeholder="DM-XXXX-XXXX-XXXX-XXXX"
            />
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={activate} disabled={saving} style={{
              padding: "9px 18px", background: "var(--accent)", color: "var(--accent-fg)",
              border: "none", borderRadius: 8, fontSize: 13, fontWeight: 700,
              cursor: saving ? "not-allowed" : "pointer",
              display: "flex", alignItems: "center", gap: 6, opacity: saving ? 0.6 : 1,
            }}>
              <Key size={14} /> {saving ? "Aktiviere…" : "Aktivieren"}
            </button>
            <button onClick={() => { setShowForm(false); setKey(""); }} style={{
              padding: "9px 18px", background: "transparent", color: "var(--text-3)",
              border: "1px solid var(--border-3)", borderRadius: 8, fontSize: 13, cursor: "pointer",
            }}>
              Abbrechen
            </button>
          </div>
        </div>
      )}

      {/* Feature-Übersicht */}
      <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text-2)", marginBottom: 14, display: "flex", alignItems: "center", gap: 10 }}>
        <Layers size={16} color="var(--accent)" />
        Feature-Übersicht
        <span style={{ fontSize: 11, color: "var(--text-5)", fontWeight: 400 }}>
          {activeSet.size} / {(license.features || []).length} aktiv
        </span>
      </div>

      {catOrder.map(cat => (grouped[cat]?.length ? (
        <div key={cat} style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-6)", textTransform: "uppercase", letterSpacing: "1.2px", marginBottom: 8 }}>{cat}</div>
          {(grouped[cat] || []).map(f => (
            <FeatureRow key={f.id} feature={f} active={activeSet.has(f.id)} />
          ))}
        </div>
      ) : null))}

      {!isActive && (
        <div style={{ marginTop: 8, padding: "14px 18px", background: "var(--bg-input)", border: "1px solid var(--border-2)", borderRadius: 10, fontSize: 12, color: "var(--text-5)", lineHeight: "19px" }}>
          {isGrace
            ? "Die Lizenz ist im Grace-Modus — alle Features bleiben bis zum Ablauf aktiv. Bitte Verbindung zum Lizenzserver prüfen."
            : <>Lizenzen kaufen und verwalten auf <strong style={{ color: "var(--text-3)" }}>monstersuite.de</strong>. Ohne Lizenz stehen nur die kostenlosen Basis-Features zur Verfügung.</>}
        </div>
      )}
    </div>
  );
}
