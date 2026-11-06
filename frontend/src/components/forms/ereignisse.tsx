/**
 * Eigene Ereignisse (Aktion, Messe, Preisänderung …) – gemeinsamer Zwischenspeicher je Projekt,
 * Erfassungsdialog und die Zuordnung auf die Zeitachse eines Diagramms.
 *
 * Gespeichert im Backend unter /api/business-config/ereignisse (je Projekt und Mandant).
 * Alle Diagramme einer Seite teilen sich eine Anfrage; nach jeder Änderung laden alle neu.
 */
import { useEffect, useState } from "react";
import { X, Trash2 } from "lucide-react";
import api, { fehlerText } from "../../api/client";

const cache = new Map<string, Promise<any>>();
const EVENT = "dm-ereignisse-geaendert";
const schluessel = (projectId) => String(projectId ?? "ohne");

function laden(projectId, neu = false) {
  const k = schluessel(projectId);
  if (neu || !cache.has(k)) {
    const q = projectId != null ? `?project_id=${projectId}` : "";
    cache.set(k, api.get(`/api/business-config/ereignisse${q}`).then((r) => r.data)
      .catch(() => ({ ereignisse: [], kategorien: [], mandant_name: null, fehler: true })));
  }
  return cache.get(k);
}

const geaendert = (projectId) => {
  cache.delete(schluessel(projectId));
  window.dispatchEvent(new CustomEvent(EVENT, { detail: schluessel(projectId) }));
};

export function useEreignisse(projectId, aktiv = true) {
  const [daten, setDaten] = useState({ ereignisse: [], kategorien: [], mandant_name: null });
  useEffect(() => {
    if (!aktiv) return;
    let lebt = true;
    const holen = () => laden(projectId).then((d) => lebt && setDaten(d));
    holen();
    const bei = (e) => { if (e.detail === schluessel(projectId)) holen(); };
    window.addEventListener(EVENT, bei);
    return () => { lebt = false; window.removeEventListener(EVENT, bei); };
  }, [projectId, aktiv]);
  return daten;
}

export async function ereignisSpeichern(projectId, e) {
  const body = { project_id: projectId ?? null, datum: e.datum, bis: e.bis || null,
    titel: e.titel, kategorie: e.kategorie, notiz: e.notiz || "" };
  const r = e.id ? await api.put(`/api/business-config/ereignisse/${e.id}`, body)
    : await api.post("/api/business-config/ereignisse", body);
  geaendert(projectId);
  return r.data;
}

export async function ereignisLoeschen(projectId, id) {
  const q = projectId != null ? `?project_id=${projectId}` : "";
  await api.delete(`/api/business-config/ereignisse/${id}${q}`);
  geaendert(projectId);
}

const datumDE = (iso) => iso ? iso.split("-").reverse().join(".") : "";
export const ereignisZeitraum = (e) => e.bis ? `${datumDE(e.datum)} – ${datumDE(e.bis)}` : datumDE(e.datum);

/**
 * Ereignisse auf die Kategorien einer Zeitachse legen. Erkennt Monate („2026-03“), Monatserste
 * („2026-03-01“) und Tage. Gibt null zurück, wenn die Achse keine Zeitachse ist.
 * Ergebnis je Ereignis: { e, x1, x2 } – x2 nur bei Zeiträumen, auf die Achse begrenzt.
 */
export function aufAchse(werte, ereignisse) {
  const xs = (werte || []).map((v) => String(v ?? ""));
  if (!xs.length || !ereignisse?.length) return xs.length && zeitachse(xs) ? [] : null;
  const art = zeitachse(xs);
  if (!art) return null;
  const key = (iso) => art === "monat" ? iso.slice(0, 7) : art === "monatserster" ? iso.slice(0, 7) + "-01" : iso.slice(0, 10);
  const norm = (x) => art === "tag" ? x.slice(0, 10) : x.slice(0, art === "monat" ? 7 : 10);
  const achse = xs.map(norm);
  const erst = achse[0], letzt = achse[achse.length - 1];
  const index = new Map(achse.map((x, i) => [x, i]));
  const aus = [];
  for (const e of ereignisse) {
    let a = key(e.datum), b = e.bis ? key(e.bis) : null;
    if (b && b === a) b = null;
    if (!b) { if (index.has(a)) aus.push({ e, x1: xs[index.get(a)] }); continue; }
    if (b < erst || a > letzt) continue;                    // Zeitraum ganz außerhalb
    if (a < erst) a = erst;
    if (b > letzt) b = letzt;
    if (!index.has(a) || !index.has(b)) continue;
    // Liegt der (beschnittene) Zeitraum in einer einzigen Kategorie, wäre die Fläche 0 breit: als Linie zeigen.
    aus.push(a === b ? { e, x1: xs[index.get(a)] } : { e, x1: xs[index.get(a)], x2: xs[index.get(b)] });
  }
  return aus;
}

function zeitachse(xs) {
  if (xs.every((x) => /^\d{4}-\d{2}$/.test(x))) return "monat";
  if (xs.every((x) => /^\d{4}-\d{2}-\d{2}/.test(x))) return xs.every((x) => x.slice(8, 10) === "01") && xs.length > 1 ? "monatserster" : "tag";
  return null;
}

/** Dialog zum Anlegen/Ändern. `vorgabe` = bestehendes Ereignis oder {datum}. */
export function EreignisDialog({ projectId, vorgabe, kategorien, mandantName, onClose }) {
  const [e, setE] = useState({ datum: "", bis: "", titel: "", kategorie: "Aktion", notiz: "", ...vorgabe });
  const [mitEnde, setMitEnde] = useState(!!vorgabe?.bis);
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState("");
  const setze = (k) => (ev) => setE((x) => ({ ...x, [k]: ev.target.value }));
  const speichern = async () => {
    setLaeuft(true); setFehler("");
    try { await ereignisSpeichern(projectId, { ...e, bis: mitEnde ? e.bis : null }); onClose(); }
    catch (err) { setFehler(fehlerText(err)); }
    finally { setLaeuft(false); }
  };
  const loeschen = async () => {
    setLaeuft(true);
    try { await ereignisLoeschen(projectId, e.id); onClose(); }
    catch (err) { setFehler(fehlerText(err)); setLaeuft(false); }
  };
  const feld = { width: "100%", padding: "7px 9px", borderRadius: 6, border: "1px solid var(--border)",
    background: "var(--bg-input, var(--bg-elevated))", color: "var(--text-main)", fontSize: 13, boxSizing: "border-box" as const };
  const lab = { fontSize: 11.5, fontWeight: 600, color: "var(--text-dim)", marginBottom: 4, display: "block" };
  const knopf = { padding: "7px 14px", borderRadius: 6, fontSize: 13, cursor: "pointer", border: "1px solid var(--border)",
    background: "transparent", color: "var(--text-main)" };
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 1000, background: "rgba(0,0,0,.45)",
      display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <div onClick={(ev) => ev.stopPropagation()} role="dialog" aria-label="Ereignis"
        style={{ width: "min(440px, 100%)", background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 10,
          padding: 18, display: "flex", flexDirection: "column", gap: 12, color: "var(--text-main)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <strong style={{ fontSize: 15, color: "var(--text-bright)" }}>{e.id ? "Ereignis ändern" : "Ereignis eintragen"}</strong>
          <button onClick={onClose} aria-label="Schließen" style={{ ...knopf, padding: 4, border: "none" }}><X size={16} /></button>
        </div>
        <p style={{ margin: 0, fontSize: 12.5, color: "var(--text-dim)", lineHeight: 1.45 }}>
          Erscheint als Markierung in den Verläufen aller Cockpits{mandantName ? ` von ${mandantName}` : ""} – damit ein Ausreißer später erklärt ist.
        </p>
        <div>
          <label style={lab}>Bezeichnung</label>
          <input autoFocus value={e.titel} onChange={setze("titel")} maxLength={120} placeholder="z. B. Frühjahrsaktion −10 %" style={feld} />
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <div style={{ flex: 1 }}>
            <label style={lab}>{mitEnde ? "Beginn" : "Datum"}</label>
            <input type="date" value={e.datum} onChange={setze("datum")} style={feld} />
          </div>
          {mitEnde && (
            <div style={{ flex: 1 }}>
              <label style={lab}>Ende</label>
              <input type="date" value={e.bis || ""} min={e.datum} onChange={setze("bis")} style={feld} />
            </div>
          )}
        </div>
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12.5, color: "var(--text-dim)" }}>
          <input type="checkbox" checked={mitEnde} onChange={(ev) => setMitEnde(ev.target.checked)} /> geht über mehrere Tage
        </label>
        <div>
          <label style={lab}>Art</label>
          <select value={e.kategorie} onChange={setze("kategorie")} style={feld}>
            {(kategorien?.length ? kategorien : ["Aktion", "Messe", "Werbung", "Preisänderung", "Lieferengpass", "Sonstiges"])
              .map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
        </div>
        <div>
          <label style={lab}>Notiz (optional)</label>
          <textarea value={e.notiz} onChange={setze("notiz")} maxLength={1000} rows={2} style={{ ...feld, resize: "vertical" }} />
        </div>
        {fehler && <span style={{ fontSize: 12.5, color: "var(--err-soft, var(--err))" }}>{fehler}</span>}
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
          {e.id ? <button onClick={loeschen} disabled={laeuft} style={{ ...knopf, color: "var(--err)" }}><Trash2 size={13} /> Löschen</button> : <span />}
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={onClose} style={knopf}>Abbrechen</button>
            <button onClick={speichern} disabled={laeuft || !e.titel.trim() || !e.datum || (mitEnde && !e.bis)}
              style={{ ...knopf, borderColor: "var(--accent)", background: "var(--accent)", color: "var(--accent-fg, #fff)", fontWeight: 600 }}>
              {laeuft ? "Speichert…" : "Speichern"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
