import { useState, useEffect, useCallback } from "react";
import { ShieldAlert, RotateCcw, Play, Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import api from "../../../api/client";

const S = {
  bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)", bgMain: "var(--bg-main)",
  border: "var(--border)", textMain: "var(--text-main)", textDim: "var(--text-dim)",
  textBright: "var(--text-bright)", accent: "var(--accent)",
};
const AMPEL = { rot: "#e05656", orange: "#e8913a", gelb: "#e6c84f", gruen: "#5cb85c" };

const inp = {
  backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4,
  color: S.textMain, fontSize: 12, padding: "5px 8px", outline: "none",
  width: 90, textAlign: "right",
};

/**
 * Panel "Kennzahlen & Warnungen": Schwellwerte je Projekt pflegen und die
 * Warnregeln einsehen/abschalten.
 *
 * Die Schwellwerte gehen als :cfg_<key> in jeden Mapping-Lauf ein – hier
 * eingestellt, wirken sie sofort in allen Regeln und Cockpits, die den
 * jeweiligen Parameter verwenden.
 */
export default function AlertsPanel({ projectId, canEdit }) {
  const [thresholds, setThresholds] = useState([]);
  const [rules, setRules] = useState([]);
  const [entwurf, setEntwurf] = useState({});   // key → Eingabewert
  const [laden, setLaden] = useState(true);
  const [pruefe, setPruefe] = useState(false);
  const [lauf, setLauf] = useState(null);
  const [fehler, setFehler] = useState(null);

  const q = projectId ? `?project_id=${projectId}` : "";

  const laden_ = useCallback(async () => {
    setLaden(true);
    try {
      const [t, r] = await Promise.all([
        api.get(`/api/business-config/thresholds${q}`),
        api.get(`/api/alerts/rules${q}`),
      ]);
      setThresholds(t.data.thresholds || []);
      setRules(r.data || []);
      setFehler(null);
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
    } finally {
      setLaden(false);
    }
  }, [q]);

  useEffect(() => { laden_(); }, [laden_]);

  useEffect(() => {
    // Letzten gespeicherten Lauf zeigen, ohne die Quell-DB zu belasten.
    api.get(`/api/alerts/latest${q}`).then(r => setLauf(r.data)).catch(() => {});
  }, [q]);

  const speichern = async (key, wert) => {
    try {
      await api.put("/api/business-config/thresholds",
        { project_id: projectId ?? null, key, value: wert });
      setThresholds(prev => prev.map(t => t.key === key
        ? { ...t, value: Number(wert), is_default: Number(wert) === t.default } : t));
      setEntwurf(prev => { const n = { ...prev }; delete n[key]; return n; });
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
    }
  };

  const zuruecksetzen = async (key) => {
    await api.delete(`/api/business-config/thresholds/${key}${q}`);
    setEntwurf(prev => { const n = { ...prev }; delete n[key]; return n; });
    laden_();
  };

  const regelUmschalten = async (r) => {
    await api.patch(`/api/alerts/rules/${r.id}`, { active: !r.active });
    setRules(prev => prev.map(x => x.id === r.id ? { ...x, active: !x.active } : x));
  };

  const jetztPruefen = async () => {
    setPruefe(true); setFehler(null);
    try {
      const heute = new Date();
      const von = new Date(heute.getFullYear(), heute.getMonth(), 1);
      const iso = d => d.toISOString().slice(0, 10);
      const { data } = await api.post("/api/alerts/evaluate", {
        project_id: projectId ?? null,
        params: { von: iso(von), bis: iso(heute) },
        include_ok: true,
      });
      setLauf(data);
    } catch (e) {
      setFehler(e.response?.data?.detail || e.message);
    } finally {
      setPruefe(false);
    }
  };

  const gruppen = [...new Set(thresholds.map(t => t.gruppe))];
  const kategorien = [...new Set(rules.map(r => r.category))];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <h2 style={{ fontSize: 15, fontWeight: 700, color: S.textBright,
            display: "flex", alignItems: "center", gap: 8 }}>
            <ShieldAlert size={16} style={{ color: S.accent }} /> Kennzahlen &amp; Warnungen
          </h2>
          <p style={{ fontSize: 11.5, color: S.textDim, marginTop: 4, maxWidth: 720 }}>
            Schwellwerte gelten für dieses Projekt und wirken sofort in allen Warnregeln.
            Anzahl und Beträge einer Warnung stammen immer aus der Auswertung selbst –
            hier wird nur festgelegt, ab wann daraus eine Meldung wird.
          </p>
        </div>
        <button onClick={jetztPruefen} disabled={pruefe}
          style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 12px",
            backgroundColor: S.accent, color: "#1a1a1a", border: "none", borderRadius: 6,
            fontSize: 12, fontWeight: 600, cursor: pruefe ? "wait" : "pointer" }}>
          {pruefe ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
          {pruefe ? "Prüfe …" : "Jetzt prüfen"}
        </button>
      </div>

      {fehler && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "9px 12px",
          border: "1px solid rgba(224,112,112,0.4)", borderRadius: 6, color: "#e07070",
          fontSize: 12 }}>
          <AlertCircle size={13} /> {fehler}
        </div>
      )}

      {/* ── Letzter Lauf ── */}
      {lauf && (lauf.alerts?.length || lauf.started_at) && (
        <div style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`,
          borderRadius: 10, overflow: "hidden" }}>
          <div style={{ padding: "9px 14px", borderBottom: `1px solid ${S.border}`,
            fontSize: 11, color: S.textDim, display: "flex", justifyContent: "space-between" }}>
            <span>Letzter Lauf: {lauf.triggered ?? 0} von {lauf.checked ?? 0} Regeln ausgelöst</span>
            <span>{lauf.started_at ? new Date(lauf.started_at).toLocaleString("de-DE") : ""}</span>
          </div>
          {(lauf.alerts || []).length === 0 ? (
            <div style={{ padding: 14, fontSize: 12, color: S.textDim,
              display: "flex", alignItems: "center", gap: 8 }}>
              <CheckCircle2 size={14} style={{ color: AMPEL.gruen }} /> Keine offenen Warnungen.
            </div>
          ) : (lauf.alerts || []).slice(0, 8).map((a, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 10,
              padding: "8px 14px", borderTop: i ? `1px solid ${S.border}` : "none",
              fontSize: 12.5, color: S.textMain }}>
              <span style={{ width: 9, height: 9, borderRadius: "50%", flexShrink: 0,
                backgroundColor: AMPEL[String(a.Ampel || "").toLowerCase()] || AMPEL.gelb }} />
              <span style={{ flex: 1 }}>{a.titel}</span>
              <span style={{ fontSize: 10.5, color: S.textDim }}>{a.kategorie}</span>
            </div>
          ))}
        </div>
      )}

      {/* ── Schwellwerte ── */}
      {laden ? (
        <p style={{ fontSize: 12, color: S.textDim }}>Lade …</p>
      ) : gruppen.map(g => (
        <div key={g} style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`,
          borderRadius: 10, overflow: "hidden" }}>
          <div style={{ padding: "9px 14px", borderBottom: `1px solid ${S.border}`,
            fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase",
            color: S.textDim }}>{g}</div>
          {thresholds.filter(t => t.gruppe === g).map((t, i) => (
            <div key={t.key} style={{ display: "flex", alignItems: "center", gap: 12,
              padding: "9px 14px", borderTop: i ? `1px solid ${S.border}` : "none" }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12.5, color: S.textMain }}>{t.label}</div>
                {t.hinweis && (
                  <div style={{ fontSize: 11, color: S.textDim, marginTop: 2 }}>{t.hinweis}</div>
                )}
              </div>
              <input type="number" step="any" disabled={!canEdit}
                value={entwurf[t.key] ?? t.value}
                onChange={e => setEntwurf(prev => ({ ...prev, [t.key]: e.target.value }))}
                onBlur={e => {
                  const v = e.target.value;
                  if (v !== "" && Number(v) !== Number(t.value)) speichern(t.key, v);
                }}
                style={inp} />
              <span style={{ fontSize: 11, color: S.textDim, width: 130 }}>{t.unit}</span>
              <button onClick={() => zuruecksetzen(t.key)} disabled={!canEdit || t.is_default}
                title={t.is_default ? "Standardwert" : `Zurücksetzen auf ${t.default}`}
                style={{ background: "none", border: "none", padding: 4,
                  color: t.is_default ? "transparent" : S.textDim,
                  cursor: t.is_default ? "default" : "pointer" }}>
                <RotateCcw size={13} />
              </button>
            </div>
          ))}
        </div>
      ))}

      {/* ── Regeln ── */}
      {!laden && (
        <div style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`,
          borderRadius: 10, overflow: "hidden" }}>
          <div style={{ padding: "9px 14px", borderBottom: `1px solid ${S.border}`,
            fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase",
            color: S.textDim }}>
            Warnregeln ({rules.length})
          </div>
          {rules.length === 0 ? (
            <div style={{ padding: 14, fontSize: 12, color: S.textDim }}>
              Noch keine Regeln – sie kommen mit dem Template „Unternehmensmonitor (JTL)".
            </div>
          ) : kategorien.map(k => (
            <div key={k}>
              <div style={{ padding: "6px 14px", backgroundColor: S.bgMain,
                fontSize: 10.5, color: S.textDim, borderTop: `1px solid ${S.border}` }}>{k}</div>
              {rules.filter(r => r.category === k).map(r => (
                <div key={r.id} style={{ display: "flex", alignItems: "center", gap: 10,
                  padding: "8px 14px", borderTop: `1px solid ${S.border}` }}>
                  <input type="checkbox" checked={!!r.active} disabled={!canEdit}
                    onChange={() => regelUmschalten(r)} style={{ cursor: "pointer" }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12.5, color: r.active ? S.textMain : S.textDim }}>
                      {r.name}
                    </div>
                    <div style={{ fontSize: 10.5, color: S.textDim, marginTop: 1 }}>
                      Quelle: {r.mapping_name || `Mapping ${r.mapping_id}`}
                      {r.cockpit ? ` · ${r.cockpit}` : ""}
                    </div>
                  </div>
                  <span style={{ fontSize: 10.5, color: S.textDim }}>{r.severity}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
