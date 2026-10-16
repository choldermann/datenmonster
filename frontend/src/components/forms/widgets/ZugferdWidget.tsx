import { useState, useEffect, useCallback } from "react";
import { FileText, AlertCircle, Loader2, Check, Play, RefreshCw, Download, Code2,
         RotateCcw, Building2, Settings2, ListChecks, PlugZap, Save } from "lucide-react";
import api, { fehlerText } from "../../../api/client";

const S = {
  bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)", bgMain: "var(--bg-main)",
  border: "var(--border)", textMain: "var(--text-main)", textDim: "var(--text-dim)",
  textBright: "var(--text-bright)", accent: "var(--accent)",
};

const inp = {
  backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4,
  color: S.textMain, fontSize: 12, padding: "6px 9px", outline: "none", width: "100%",
};

const btn = (aktiv = true) => ({
  display: "inline-flex", alignItems: "center", gap: 6, padding: "6px 11px",
  fontSize: 12, borderRadius: 5, cursor: aktiv ? "pointer" : "default",
  border: `1px solid ${S.border}`, backgroundColor: S.bgEl, color: S.textMain,
  opacity: aktiv ? 1 : .55,
});

const hinweis = (farbe) => ({
  display: "flex", alignItems: "flex-start", gap: 7, fontSize: 12, color: `var(--${farbe})`,
  backgroundColor: `color-mix(in srgb, var(--${farbe}) 8%, transparent)`,
  border: `1px solid color-mix(in srgb, var(--${farbe}) 25%, transparent)`,
  borderRadius: 6, padding: "8px 11px",
});

const euro = (v) => v == null ? "—" :
  Number(v).toLocaleString("de-DE", { style: "currency", currency: "EUR" });
const zeit = (iso) => iso ? new Date(iso).toLocaleString("de-DE",
  { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";

const ART = { RECHNUNG: "Rechnung", STORNO: "Storno", KORREKTUR: "Korrektur" };

/**
 * Widget "ZUGFeRD-Ausgang": Rechnungen, die eine Fremdanwendung (Access) in
 * tInvoice/tInvoicePositions ablegt, werden zu ZUGFeRD-PDFs und landen auf einem
 * FTP im Firmennetz. Drei Reiter: Protokoll (was ist passiert), Firmendaten
 * (Rechnungssteller), Einrichtung (Tabellen, FTP, Zeitplan – nur Admin).
 */
export default function ZugferdWidget({ widget }) {
  const connId = widget?.config?.connection_id ? Number(widget.config.connection_id) : null;
  const [reiter, setReiter] = useState("protokoll");
  const [daten, setDaten] = useState(null);
  const [fehler, setFehler] = useState(null);

  const laden = useCallback(async () => {
    if (!connId) return;
    try {
      const { data } = await api.get("/api/zugferd/einstellungen", { params: { connection_id: connId } });
      setDaten(data); setFehler(null);
    } catch (e) { setFehler(fehlerText(e)); }
  }, [connId]);
  useEffect(() => { laden(); }, [laden]);

  if (!connId)
    return <p style={{ padding: 16, fontSize: 12, color: S.textDim }}>
      Im Widget ist noch keine Verbindung gewählt (Formular bearbeiten → Widget → Verbindung).</p>;
  if (!daten && !fehler)
    return <div style={{ padding: 24, color: S.textDim, fontSize: 12, display: "flex", gap: 8 }}>
      <Loader2 size={14} className="animate-spin" /> Wird geladen …</div>;

  const reiterListe = [
    { id: "protokoll", label: "Protokoll", Icon: ListChecks },
    { id: "firmendaten", label: "Firmendaten", Icon: Building2,
      warn: (daten?.fehlend || []).length > 0 },
    ...(daten?.darf_einrichten ? [{ id: "einrichtung", label: "Einrichtung", Icon: Settings2,
      warn: !daten?.ausgang?.host }] : []),
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14, padding: 16 }}>
      <div style={{ display: "flex", gap: 4, borderBottom: `1px solid ${S.border}` }}>
        {reiterListe.map(({ id, label, Icon, warn }) => (
          <button key={id} onClick={() => setReiter(id)} style={{
            display: "flex", alignItems: "center", gap: 6, padding: "7px 12px", fontSize: 12,
            background: "none", border: "none", cursor: "pointer", marginBottom: -1,
            borderBottom: `2px solid ${reiter === id ? S.accent : "transparent"}`,
            color: reiter === id ? S.textBright : S.textDim, fontWeight: reiter === id ? 600 : 400 }}>
            <Icon size={13} /> {label}
            {warn && <span style={{ color: "var(--warn)", fontSize: 14, lineHeight: 1 }}>•</span>}
          </button>
        ))}
      </div>
      {fehler && <div style={hinweis("err")}><AlertCircle size={14} /> {fehler}</div>}
      {daten && reiter === "protokoll" && <Protokoll connId={connId} daten={daten} onNeu={laden} />}
      {daten && reiter === "firmendaten" && <Firmendaten connId={connId} daten={daten} onNeu={laden} />}
      {daten && reiter === "einrichtung" && <Einrichtung connId={connId} daten={daten} onNeu={laden} />}
    </div>
  );
}

// ── Protokoll ────────────────────────────────────────────────────────────────

function Protokoll({ connId, daten, onNeu }) {
  const [belege, setBelege] = useState([]);
  const [stat, setStat] = useState({});
  const [filter, setFilter] = useState("alle");
  const [suche, setSuche] = useState("");
  const [laeuft, setLaeuft] = useState(false);
  const [meldung, setMeldung] = useState(null);
  const [offen, setOffen] = useState(null);
  const [xml, setXml] = useState(null);

  const laden = useCallback(async () => {
    const p = { connection_id: connId };
    const [b, s] = await Promise.all([
      api.get("/api/zugferd/belege", { params: { ...p, status: filter, suche } }),
      api.get("/api/zugferd/statistik", { params: p }).catch(() => ({ data: { status: {} } })),
    ]);
    setBelege(b.data || []); setStat(s.data?.status || {});
  }, [connId, filter, suche]);
  useEffect(() => { laden().catch(() => {}); }, [laden]);

  const jetzt = async () => {
    setLaeuft(true); setMeldung(null);
    try {
      const { data } = await api.post("/api/zugferd/lauf", null, { params: { connection_id: connId } });
      setMeldung({ ok: data.ok && !data.fehler, text: data.meldung });
      await laden(); onNeu();
    } catch (e) { setMeldung({ ok: false, text: fehlerText(e) }); }
    finally { setLaeuft(false); }
  };

  const oeffnen = async (b) => {
    const r = await api.get(`/api/zugferd/belege/${b.id}/datei`, { responseType: "blob" });
    const url = URL.createObjectURL(r.data);
    window.open(url, "_blank");
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  };
  const xmlZeigen = async (b) => {
    const r = await api.get(`/api/zugferd/belege/${b.id}/xml`, { responseType: "text" });
    setXml({ nummer: b.nummer, text: r.data });
  };
  const erneut = async (b) => {
    try {
      await api.post(`/api/zugferd/belege/${b.id}/erneut`);
      setMeldung({ ok: true, text: `${b.nummer} steht wieder auf NEU und geht beim nächsten Lauf durch` });
      await laden();
    } catch (e) { setMeldung({ ok: false, text: fehlerText(e) }); }
  };

  const a = daten.ausgang;
  const kachel = (label, wert, farbe) => (
    <div style={{ padding: "8px 14px", borderRadius: 6, border: `1px solid ${S.border}`,
      backgroundColor: S.bgCard, minWidth: 92 }}>
      <div style={{ fontSize: 10.5, color: S.textDim }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 600, color: wert ? `var(--${farbe})` : S.textDim }}>
        {wert || 0}</div>
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {(daten.fehlend || []).length > 0 && (
        <div style={hinweis("warn")}><AlertCircle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
          <span>Firmendaten unvollständig ({daten.fehlend.join(", ")}) – solange läuft nichts.</span></div>
      )}
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "stretch" }}>
        {kachel("In Access offen", stat.ENTWURF, "muted")}
        {kachel("Wartet", (stat.NEU || 0) + (stat.IN_ARBEIT || 0), "accent")}
        {kachel("Abgewiesen", stat.FEHLER, "err")}
        {kachel("Erzeugt", stat.OK, "ok")}
        <div style={{ flex: 1 }} />
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "center",
          alignItems: "flex-end", gap: 5, fontSize: 11, color: S.textDim }}>
          <button onClick={jetzt} disabled={laeuft || !a} style={btn(!laeuft && !!a)}>
            {laeuft ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
            Jetzt verarbeiten</button>
          {a ? <span>
            {a.aktiv ? `Automatisch (${a.cron_expr})` : "Zeitplan aus"} · letzter Lauf {zeit(a.letzter_lauf)}
            {a.letzter_status === "fehler" &&
              <span style={{ color: "var(--err)" }}> · {a.letzter_fehler}</span>}
          </span> : <span>Noch nicht eingerichtet</span>}
        </div>
      </div>
      {meldung && <div style={hinweis(meldung.ok ? "ok" : "err")}>
        {meldung.ok ? <Check size={14} /> : <AlertCircle size={14} />} {meldung.text}</div>}

      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <select value={filter} onChange={e => setFilter(e.target.value)}
          style={{ ...inp, width: 150, cursor: "pointer" }}>
          <option value="alle">Alle</option>
          <option value="ok">Erzeugt</option>
          <option value="fehler">Abgewiesen</option>
        </select>
        <input value={suche} onChange={e => setSuche(e.target.value)}
          placeholder="Rechnungsnummer oder Kunde" style={{ ...inp, maxWidth: 280 }} />
        <button onClick={() => laden()} style={btn()} title="Neu laden"><RefreshCw size={13} /></button>
      </div>

      <div style={{ border: `1px solid ${S.border}`, borderRadius: 8, overflow: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead><tr style={{ backgroundColor: S.bgMain, color: S.textDim, textAlign: "left" }}>
            {["Zeit", "Nummer", "Art", "Kunde", "Brutto", "Ergebnis", ""].map(h =>
              <th key={h} style={{ padding: "7px 10px", fontWeight: 500, fontSize: 11 }}>{h}</th>)}
          </tr></thead>
          <tbody>
            {belege.length === 0 && <tr><td colSpan={7} style={{ padding: 18, color: S.textDim,
              textAlign: "center" }}>Noch keine Rechnungen verarbeitet</td></tr>}
            {belege.map(b => {
              const ok = b.status === "ok";
              return [
                <tr key={b.id} onClick={() => setOffen(offen === b.id ? null : b.id)}
                  style={{ borderTop: `1px solid ${S.border}`, cursor: b.meldung ? "pointer" : "default" }}>
                  <td style={{ padding: "6px 10px", whiteSpace: "nowrap", color: S.textDim }}>{zeit(b.erstellt_am)}</td>
                  <td style={{ padding: "6px 10px", fontWeight: 600, color: S.textBright }}>{b.nummer}</td>
                  <td style={{ padding: "6px 10px" }}>{ART[b.art] || b.art}</td>
                  <td style={{ padding: "6px 10px" }}>{b.kunde}</td>
                  <td style={{ padding: "6px 10px", textAlign: "right", whiteSpace: "nowrap" }}>{euro(b.brutto)}</td>
                  <td style={{ padding: "6px 10px", color: ok ? "var(--ok)" : "var(--err)" }}>
                    {ok ? <>✓ {b.dateiname}</> : <>✕ abgewiesen</>}
                    {ok && b.meldung && <span style={{ color: "var(--warn)" }}> · Hinweis</span>}
                  </td>
                  <td style={{ padding: "4px 8px", whiteSpace: "nowrap", textAlign: "right" }}
                    onClick={e => e.stopPropagation()}>
                    {b.hat_datei && <>
                      <button onClick={() => oeffnen(b)} title="PDF öffnen" style={{ ...btn(), padding: "3px 7px" }}>
                        <FileText size={12} /></button>{" "}
                      <button onClick={() => xmlZeigen(b)} title="XML ansehen" style={{ ...btn(), padding: "3px 7px" }}>
                        <Code2 size={12} /></button>
                    </>}
                    {!ok && <button onClick={() => erneut(b)} title="In Access korrigiert? Wieder einreihen"
                      style={{ ...btn(), padding: "3px 7px" }}><RotateCcw size={12} /> erneut</button>}
                  </td>
                </tr>,
                offen === b.id && b.meldung && (
                  <tr key={`${b.id}m`}><td colSpan={7} style={{ padding: "4px 12px 10px 12px" }}>
                    <pre style={{ margin: 0, whiteSpace: "pre-wrap", fontSize: 11.5, fontFamily: "inherit",
                      color: ok ? "var(--warn)" : "var(--err)" }}>{b.meldung}</pre>
                    <div style={{ fontSize: 10.5, color: S.textDim, marginTop: 4 }}>
                      ausgelöst von {b.ausgeloest_von}</div>
                  </td></tr>
                ),
              ];
            })}
          </tbody>
        </table>
      </div>

      {xml && (
        <div onClick={() => setXml(null)} style={{ position: "fixed", inset: 0, zIndex: 60,
          backgroundColor: "rgba(0,0,0,.5)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div onClick={e => e.stopPropagation()} style={{ width: "min(900px, 92vw)", maxHeight: "85vh",
            display: "flex", flexDirection: "column", backgroundColor: S.bgCard, borderRadius: 8,
            border: `1px solid ${S.border}` }}>
            <div style={{ padding: "9px 14px", borderBottom: `1px solid ${S.border}`, fontSize: 12,
              fontWeight: 600, color: S.textBright, display: "flex", justifyContent: "space-between" }}>
              factur-x.xml – {xml.nummer}
              <button onClick={() => setXml(null)} style={{ background: "none", border: "none",
                color: S.textDim, cursor: "pointer" }}>✕</button>
            </div>
            <pre style={{ margin: 0, padding: 14, overflow: "auto", fontSize: 11, color: S.textMain }}>{xml.text}</pre>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Firmendaten ──────────────────────────────────────────────────────────────

function Firmendaten({ connId, daten, onNeu }) {
  const [entwurf, setEntwurf] = useState(() =>
    Object.fromEntries(daten.felder.map(f => [f.key, f.value ?? ""])));
  const [speichert, setSpeichert] = useState(null);
  const [gespeichert, setGespeichert] = useState(null);
  const [fehler, setFehler] = useState(null);

  const speichern = async (key, sofort = null) => {
    const feld = daten.felder.find(f => f.key === key);
    const wert = (sofort ?? entwurf[key] ?? "").toString().trim();
    if (!feld || wert === (feld.value ?? "")) return;
    setSpeichert(key); setFehler(null);
    try {
      const { data } = await api.put("/api/zugferd/firmendaten", { connection_id: connId, key, value: wert });
      setEntwurf(p => ({ ...p, [key]: data.value }));
      setGespeichert(key);
      setTimeout(() => setGespeichert(g => (g === key ? null : g)), 1500);
      await onNeu();
    } catch (e) {
      setFehler(fehlerText(e));
      setEntwurf(p => ({ ...p, [key]: feld.value ?? "" }));
    } finally { setSpeichert(null); }
  };

  const gruppen = [];
  for (const f of daten.felder) {
    let g = gruppen.find(x => x.label === f.gruppe);
    if (!g) { g = { label: f.gruppe, felder: [] }; gruppen.push(g); }
    g.felder.push(f);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <p style={{ fontSize: 11.5, color: S.textDim, margin: 0, maxWidth: 760 }}>
        Der Rechnungssteller, wie er in jeder E-Rechnung steht. Gilt für alle Rechnungen
        aus <b>{daten.connection_name}</b>. Gespeichert wird beim Verlassen des Feldes.
      </p>
      {fehler && <div style={hinweis("err")}><AlertCircle size={14} /> {fehler}</div>}
      {(daten.fehlend || []).length > 0 && (
        <div style={hinweis("warn")}><AlertCircle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
          <span>Pflicht und noch leer: <b>{daten.fehlend.join(", ")}</b></span></div>
      )}
      {gruppen.map(g => (
        <div key={g.label} style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`,
          borderRadius: 8, overflow: "hidden" }}>
          <div style={{ padding: "8px 13px", backgroundColor: S.bgMain, borderBottom: `1px solid ${S.border}`,
            fontSize: 11, fontWeight: 600, letterSpacing: .4, textTransform: "uppercase", color: S.textDim }}>
            {g.label}</div>
          <div style={{ padding: 13, display: "grid", gap: 13,
            gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))" }}>
            {g.felder.map(f => (
              <div key={f.key}>
                <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11,
                  color: S.textBright, marginBottom: 4 }}>
                  {f.label}
                  {f.pflicht && !String(entwurf[f.key] ?? "").trim() &&
                    <span style={{ color: "var(--warn)", fontSize: 13, lineHeight: 1 }}>•</span>}
                  {speichert === f.key && <Loader2 size={11} className="animate-spin" />}
                  {gespeichert === f.key && <Check size={12} style={{ color: "var(--ok)" }} />}
                </label>
                {f.optionen ? (
                  <select value={entwurf[f.key] ?? ""} style={{ ...inp, cursor: "pointer" }}
                    onChange={e => { setEntwurf(p => ({ ...p, [f.key]: e.target.value }));
                                     speichern(f.key, e.target.value); }}>
                    {f.optionen.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                ) : (
                  <input value={entwurf[f.key] ?? ""} placeholder={f.default || ""} style={inp}
                    onChange={e => setEntwurf(p => ({ ...p, [f.key]: e.target.value }))}
                    onBlur={() => speichern(f.key)}
                    onKeyDown={e => { if (e.key === "Enter") e.currentTarget.blur(); }} />
                )}
                {f.hinweis && <div style={{ fontSize: 10.5, color: S.textDim, marginTop: 3 }}>{f.hinweis}</div>}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Einrichtung ──────────────────────────────────────────────────────────────

const LEER = {
  tabelle_kopf: "dbo.tInvoice", tabelle_positionen: "dbo.tInvoicePositions",
  protokoll: "ftp", host: "", port: "", username: "", password: "", verzeichnis: "/",
  dateiname_muster: "{nummer}.pdf", aktiv: false, cron_expr: "*/5 * * * *",
};

function Einrichtung({ connId, daten, onNeu }) {
  const [f, setF] = useState(() => ({ ...LEER, ...(daten.ausgang || {}) }));
  const [arbeitet, setArbeitet] = useState(null);
  const [meldung, setMeldung] = useState(null);
  const [test, setTest] = useState(null);
  const set = (k, v) => setF(p => ({ ...p, [k]: v }));

  const speichern = async () => {
    setArbeitet("speichern"); setMeldung(null);
    try {
      await api.put("/api/zugferd/ausgang", { ...f, connection_id: connId,
        port: f.port ? Number(f.port) : null });
      setMeldung({ ok: true, text: "Gespeichert" });
      await onNeu();
    } catch (e) { setMeldung({ ok: false, text: fehlerText(e) }); }
    finally { setArbeitet(null); }
  };
  const testen = async () => {
    setArbeitet("testen"); setTest(null);
    try {
      const { data } = await api.post("/api/zugferd/ausgang/test", null, { params: { connection_id: connId } });
      setTest(data);
    } catch (e) { setTest({ ftp: { ok: false, meldung: fehlerText(e) } }); }
    finally { setArbeitet(null); }
  };
  const skript = async () => {
    const r = await api.get("/api/zugferd/sql-skript", { responseType: "blob" });
    const url = URL.createObjectURL(r.data);
    const el = document.createElement("a");
    el.href = url; el.download = "zugferd_tabellen.sql"; el.click();
    URL.revokeObjectURL(url);
  };

  const feld = (label, key, extra = {}, hinweisText = null) => (
    <div>
      <label style={{ display: "block", fontSize: 11, color: S.textBright, marginBottom: 4 }}>{label}</label>
      <input value={f[key] ?? ""} onChange={e => set(key, e.target.value)} style={inp} {...extra} />
      {hinweisText && <div style={{ fontSize: 10.5, color: S.textDim, marginTop: 3 }}>{hinweisText}</div>}
    </div>
  );
  const box = (titel, kinder) => (
    <div style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`, borderRadius: 8 }}>
      <div style={{ padding: "8px 13px", backgroundColor: S.bgMain, borderBottom: `1px solid ${S.border}`,
        fontSize: 11, fontWeight: 600, letterSpacing: .4, textTransform: "uppercase", color: S.textDim,
        borderRadius: "8px 8px 0 0" }}>{titel}</div>
      <div style={{ padding: 13, display: "grid", gap: 13,
        gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))" }}>{kinder}</div>
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {box("Übergabetabellen", <>
        {feld("Rechnungskopf", "tabelle_kopf")}
        {feld("Positionen", "tabelle_positionen")}
        <div style={{ display: "flex", alignItems: "flex-end" }}>
          <button onClick={skript} style={btn()}><Download size={13} /> SQL-Skript zum Anlegen</button>
        </div>
      </>)}
      {box("Ziel (FTP im Firmennetz)", <>
        <div>
          <label style={{ display: "block", fontSize: 11, color: S.textBright, marginBottom: 4 }}>Protokoll</label>
          <select value={f.protokoll} onChange={e => set("protokoll", e.target.value)}
            style={{ ...inp, cursor: "pointer" }}>
            <option value="ftp">FTP</option><option value="sftp">SFTP</option>
          </select>
        </div>
        {feld("Server", "host", { placeholder: "192.168.1.20" })}
        {feld("Port", "port", { placeholder: f.protokoll === "sftp" ? "22" : "21" })}
        {feld("Benutzer", "username")}
        {feld("Kennwort", "password", { type: "password", autoComplete: "new-password" })}
        {feld("Verzeichnis", "verzeichnis", {}, "Hierhin werden die fertigen PDFs gelegt.")}
        {feld("Dateiname", "dateiname_muster", {},
          "Platzhalter: {nummer} {typ} {datum} {kunde}")}
      </>)}
      {box("Zeitplan", <>
        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: S.textMain }}>
          <input type="checkbox" checked={!!f.aktiv} onChange={e => set("aktiv", e.target.checked)} />
          Automatisch verarbeiten
        </label>
        {feld("Takt (Cron)", "cron_expr", {}, "*/5 * * * * = alle 5 Minuten")}
      </>)}

      <div style={{ display: "flex", gap: 8 }}>
        <button onClick={speichern} disabled={!!arbeitet} style={btn(!arbeitet)}>
          {arbeitet === "speichern" ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
          Speichern</button>
        <button onClick={testen} disabled={!!arbeitet || !daten.ausgang} style={btn(!arbeitet && !!daten.ausgang)}
          title={daten.ausgang ? "" : "Erst speichern"}>
          {arbeitet === "testen" ? <Loader2 size={13} className="animate-spin" /> : <PlugZap size={13} />}
          Verbindung und Tabellen prüfen</button>
      </div>
      {meldung && <div style={hinweis(meldung.ok ? "ok" : "err")}>
        {meldung.ok ? <Check size={14} /> : <AlertCircle size={14} />} {meldung.text}</div>}
      {test && ["ftp", "tabellen"].map(k => test[k] && (
        <div key={k} style={hinweis(test[k].ok ? "ok" : "err")}>
          {test[k].ok ? <Check size={14} /> : <AlertCircle size={14} />}
          <span><b>{k === "ftp" ? "FTP" : "Tabellen"}:</b> {test[k].meldung}</span>
        </div>
      ))}
    </div>
  );
}
