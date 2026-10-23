/**
 * Einrichtungsassistent für JTL-Kunden (Büro, Phase 2).
 * Drei Schritte: Wawi verbinden → Cockpits wählen → Angaben zum Betrieb.
 * Backend: app/api/einrichtung.py; Versionsprüfung je Vorlage über /api/templates/pruefe.
 */
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Check, Loader2 } from "lucide-react";
import api, { fehlerText } from "../../api/client";
import { S, knopf, karte } from "./StartLayout";

const SCHRITTE = ["Wawi verbinden", "Cockpits wählen", "Angaben zum Betrieb"];

const feld = {
  width: "100%", minHeight: 44, padding: "10px 12px", borderRadius: 8, boxSizing: "border-box",
  border: `1px solid ${S.border}`, backgroundColor: S.bgMain, color: S.textMain, fontSize: 14,
} as const;
const etikett = { fontSize: 13, color: S.textDim, display: "block", marginBottom: 6 } as const;
const hilfe = { fontSize: 12, color: S.textDim, marginTop: 4 } as const;

function Feld({ id, label, hint = null, children }) {
  return (
    <div style={{ minWidth: 0 }}>
      <label htmlFor={id} style={etikett}>{label}</label>
      {children}
      {hint && <div style={hilfe}>{hint}</div>}
    </div>
  );
}

function Fortschritt({ schritt }) {
  return (
    <ol aria-label="Fortschritt" style={{ listStyle: "none", margin: 0, padding: 0, display: "grid",
      gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 10 }}>
      {SCHRITTE.map((label, i) => {
        const n = i + 1, fertig = schritt > n, aktiv = schritt === n;
        const farbe = aktiv ? S.accent : fertig ? "var(--ok)" : S.textDim;
        return (
          <li key={label} aria-current={aktiv ? "step" : undefined}
            style={{ display: "flex", flexDirection: "column", gap: 2, padding: "10px 12px", borderRadius: 8,
              border: `1px solid ${aktiv ? S.accent : fertig ? "color-mix(in srgb, var(--ok) 45%, transparent)" : S.border}`,
              backgroundColor: aktiv ? "color-mix(in srgb, var(--accent) 10%, transparent)" : "transparent", color: farbe }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>{fertig ? "erledigt" : `Schritt ${n}`}</span>
            <span style={{ fontWeight: 600 }}>{label}</span>
          </li>
        );
      })}
    </ol>
  );
}

// ── Schritt 1 ────────────────────────────────────────────────────────────────

function SchrittVerbindung({ onFertig }) {
  const [vorhandene, setVorhandene] = useState(null);
  const [eingabe, setEingabe] = useState({ server: "", port: "", datenbank: "eazybusiness", benutzer: "sa", passwort: "" });
  const [laeuft, setLaeuft] = useState(false);
  const [ergebnis, setErgebnis] = useState(null);
  const [fehler, setFehler] = useState(null);

  useEffect(() => {
    api.get("/api/start/status")
      .then(({ data }) => setVorhandene((data?.verbindungen || []).filter((v) => v.jtl_version)))
      .catch(() => setVorhandene([]));
  }, []);

  const setze = (k) => (e) => setEingabe((alt) => ({ ...alt, [k]: e.target.value }));

  const testen = async () => {
    setLaeuft(true); setErgebnis(null); setFehler(null);
    try {
      const { data } = await api.post("/api/einrichtung/verbindung", {
        ...eingabe, port: eingabe.port ? Number(eingabe.port) : null,
      }, { timeout: 60000 });
      setErgebnis(data);
    } catch (e) {
      setFehler(fehlerText(e));
    } finally {
      setLaeuft(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div>
        <h1 style={{ margin: 0, fontSize: 24, fontWeight: 800, color: S.textBright }}>Mit Ihrer JTL-Wawi verbinden</h1>
        <p style={{ margin: "6px 0 0", color: S.textDim, lineHeight: 1.5 }}>
          Die Angaben stehen in JTL beim Anmelden unter „Datenbank verbinden“.
          Datenmonster liest nur, es ändert nichts in Ihrer Wawi.
        </p>
      </div>

      {vorhandene?.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <span style={etikett}>Schon eingerichtet – mit einer davon weitermachen:</span>
          {vorhandene.map((v) => (
            <button key={v.id} onClick={() => onFertig({ connection_id: v.id, jtl_version: v.jtl_version, name: v.name })}
              style={{ ...knopf.neben, justifyContent: "space-between", width: "100%", textAlign: "left" }}>
              <span><b style={{ color: S.textBright }}>{v.name}</b>
                <span style={{ color: S.textDim }}> · JTL-Wawi {v.jtl_version} · {v.server}</span></span>
              <span style={{ color: S.accent, fontWeight: 600 }}>Verwenden</span>
            </button>
          ))}
          <span style={{ ...hilfe, marginTop: 8 }}>Oder eine neue Verbindung eintragen:</span>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14 }}>
        <Feld id="e-server" label="Server" hint="So, wie er in JTL beim Anmelden steht">
          <input id="e-server" value={eingabe.server} onChange={setze("server")} className="dm-feld" style={feld} placeholder="z. B. WAWI-SRV\JTLWAWI" />
        </Feld>
        <Feld id="e-port" label="Port (optional)" hint="Leer lassen, dann wird er ermittelt">
          <input id="e-port" value={eingabe.port} onChange={setze("port")} inputMode="numeric" className="dm-feld" style={feld} />
        </Feld>
        <Feld id="e-db" label="Datenbank">
          <input id="e-db" value={eingabe.datenbank} onChange={setze("datenbank")} className="dm-feld" style={feld} />
        </Feld>
        <Feld id="e-user" label="Benutzer">
          <input id="e-user" value={eingabe.benutzer} onChange={setze("benutzer")} className="dm-feld" style={feld} autoComplete="off" />
        </Feld>
        <Feld id="e-pw" label="Passwort">
          <input id="e-pw" type="password" value={eingabe.passwort} onChange={setze("passwort")} className="dm-feld" style={feld} autoComplete="new-password" />
        </Feld>
      </div>

      <div>
        <button onClick={testen} disabled={laeuft || !eingabe.server.trim() || !eingabe.benutzer.trim()} style={knopf.haupt}>
          {laeuft && <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} />}
          {laeuft ? "Verbinde…" : "Verbindung testen"}
        </button>
      </div>

      {fehler && <p style={{ color: "var(--err)", margin: 0 }}>{fehler}</p>}

      {ergebnis?.ok && (
        <div role="status" style={{ borderRadius: 10, padding: "14px 16px", display: "flex", flexDirection: "column", gap: 6,
          border: "1px solid color-mix(in srgb, var(--ok) 45%, transparent)", backgroundColor: "color-mix(in srgb, var(--ok) 8%, transparent)" }}>
          <span style={{ fontWeight: 700, color: "var(--ok)" }}>Verbunden</span>
          <span style={{ fontSize: 14 }}>
            JTL-Wawi <b>{ergebnis.jtl_version}</b>
            {ergebnis.artikel != null && <> · {Number(ergebnis.artikel).toLocaleString("de-DE")} Artikel</>}
            {ergebnis.auftraege != null && <> · {Number(ergebnis.auftraege).toLocaleString("de-DE")} Aufträge</>}
            {" · "}Port {ergebnis.port}
          </span>
          {ergebnis.mandanten?.length > 1 && (
            <span style={{ fontSize: 13, color: S.textDim }}>
              Auf dem Server gibt es weitere Mandanten ({ergebnis.mandanten.join(", ")}). Eingerichtet wird jetzt
              „{eingabe.datenbank}“; weitere lassen sich später in der Werkstatt unter „Verbindungen“ ergänzen.
            </span>
          )}
        </div>
      )}
      {ergebnis && !ergebnis.ok && (
        <div role="alert" style={{ borderRadius: 10, padding: "14px 16px", display: "flex", flexDirection: "column", gap: 8,
          border: "1px solid color-mix(in srgb, var(--err) 45%, transparent)", backgroundColor: "color-mix(in srgb, var(--err) 8%, transparent)" }}>
          <span style={{ fontWeight: 700, color: "var(--err)" }}>{ergebnis.titel}</span>
          <span style={{ fontSize: 14 }}>{ergebnis.text}</span>
          {ergebnis.schritte?.length > 0 && (
            <ol style={{ margin: 0, paddingLeft: 22, fontSize: 14, listStyle: "decimal", display: "flex", flexDirection: "column", gap: 4 }}>
              {ergebnis.schritte.map((s) => <li key={s}>{s}</li>)}
            </ol>
          )}
          {ergebnis.technisch && (
            <details style={{ fontSize: 12, color: S.textDim }}>
              <summary style={{ cursor: "pointer" }}>Technische Meldung</summary>
              <code style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{ergebnis.technisch}</code>
            </details>
          )}
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <button onClick={() => onFertig({ connection_id: ergebnis.connection_id, jtl_version: ergebnis.jtl_version })}
          disabled={!ergebnis?.ok} style={{ ...knopf.haupt, opacity: ergebnis?.ok ? 1 : 0.45 }}>
          Weiter
        </button>
      </div>
    </div>
  );
}

// ── Schritt 2 ────────────────────────────────────────────────────────────────

function SchrittCockpits({ verbindung, gewaehlt, setGewaehlt, onZurueck, onWeiter }) {
  const [liste, setListe] = useState(null);
  const [befund, setBefund] = useState({});   // template_id → Ergebnis von /pruefe oder "laeuft"
  const [fehler, setFehler] = useState(null);

  useEffect(() => {
    api.get("/api/einrichtung/cockpits", { timeout: 60000 })
      .then(({ data }) => setListe(data?.cockpits || []))
      .catch((e) => setFehler(fehlerText(e)));
  }, []);

  // Versionsprüfung: drei Vorlagen gleichzeitig, jede meldet sich einzeln.
  useEffect(() => {
    if (!liste) return;
    const offen = liste.filter((c) => c.berechtigt && c.im_katalog).map((c) => c.template_id);
    let abgebrochen = false;
    const arbeiter = async () => {
      while (offen.length && !abgebrochen) {
        const tid = offen.shift();
        setBefund((b) => ({ ...b, [tid]: "laeuft" }));
        try {
          const { data } = await api.post("/api/templates/pruefe",
            { template_id: tid, connection_id: verbindung.connection_id }, { timeout: 120000 });
          if (!abgebrochen) setBefund((b) => ({ ...b, [tid]: data }));
        } catch {
          if (!abgebrochen) setBefund((b) => ({ ...b, [tid]: null }));
        }
      }
    };
    arbeiter(); arbeiter(); arbeiter();
    return () => { abgebrochen = true; };
  }, [liste, verbindung.connection_id]);

  const umschalten = (tid) => setGewaehlt((alt) => alt.includes(tid) ? alt.filter((x) => x !== tid) : [...alt, tid]);

  const marke = (c) => {
    if (!c.berechtigt) return { text: "im Shop erhältlich", farbe: S.textDim };
    if (!c.im_katalog) return { text: "wird beim Einrichten geladen", farbe: S.textDim };
    const b = befund[c.template_id];
    if (b === "laeuft" || b === undefined) return { text: "wird geprüft…", farbe: S.textDim };
    if (b === null) return { text: "nicht prüfbar", farbe: S.textDim };
    if (!b.mappings_betroffen) return { text: `passt zu ${verbindung.jtl_version || b.version}`, farbe: "var(--ok)" };
    return { text: `${b.mappings_betroffen} von ${b.mappings_gesamt} Auswertungen laufen hier nicht`, farbe: "var(--warn)" };
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div>
        <h1 style={{ margin: 0, fontSize: 24, fontWeight: 800, color: S.textBright }}>Welche Cockpits möchten Sie?</h1>
        <p style={{ margin: "6px 0 0", color: S.textDim }}>Wählen Sie, was Sie brauchen. Weitere lassen sich jederzeit dazunehmen.</p>
      </div>
      {fehler && <p style={{ color: "var(--err)", margin: 0 }}>{fehler}</p>}
      {!liste && !fehler && <span style={{ color: S.textDim }}>Lädt…</span>}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {(liste || []).map((c) => {
          const an = gewaehlt.includes(c.template_id);
          const m = marke(c);
          return (
            <button key={c.template_id} onClick={() => c.berechtigt && umschalten(c.template_id)}
              disabled={!c.berechtigt} aria-pressed={an}
              style={{ display: "flex", alignItems: "center", gap: 14, width: "100%", padding: "12px 14px", minHeight: 58,
                borderRadius: 10, textAlign: "left", cursor: c.berechtigt ? "pointer" : "default", color: S.textMain,
                opacity: c.berechtigt ? 1 : 0.6,
                border: `1px solid ${an ? "color-mix(in srgb, var(--accent) 50%, transparent)" : S.border}`,
                backgroundColor: an ? "color-mix(in srgb, var(--accent) 10%, transparent)" : S.bgMain }}>
              <span aria-hidden="true" style={{ width: 22, height: 22, flex: "none", borderRadius: 5, display: "flex",
                alignItems: "center", justifyContent: "center",
                ...(an ? { backgroundColor: S.accent, color: S.accentFg } : { border: `2px solid ${S.border}` }) }}>
                {an && <Check size={15} strokeWidth={3} />}
              </span>
              <span style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 2 }}>
                <span style={{ fontWeight: 600, color: S.textBright }}>{c.name}</span>
                {c.beschreibung && (
                  <span style={{ fontSize: 13, color: S.textDim, overflow: "hidden", textOverflow: "ellipsis",
                    display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>{c.beschreibung}</span>
                )}
              </span>
              <span style={{ fontSize: 12, fontFamily: "var(--font-mono)", color: m.farbe, textAlign: "right", maxWidth: 220 }}>
                {!c.berechtigt && c.shop_url
                  ? <a href={c.shop_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>{m.text}</a>
                  : m.text}
              </span>
            </button>
          );
        })}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <button onClick={onZurueck} style={knopf.neben}>Zurück</button>
        <span style={{ fontSize: 14, color: S.textDim }}>
          {gewaehlt.length ? `${gewaehlt.length} ausgewählt` : "Noch nichts gewählt"}
        </span>
        <button onClick={onWeiter} disabled={!gewaehlt.length} style={{ ...knopf.haupt, opacity: gewaehlt.length ? 1 : 0.45 }}>
          Weiter
        </button>
      </div>
    </div>
  );
}

// ── Schritt 3 ────────────────────────────────────────────────────────────────

function SchrittBetrieb({ gewaehlt, angaben, setAngaben, laeuft, onZurueck, onEinrichten }) {
  const setze = (k) => (e) => setAngaben((alt) => ({ ...alt, [k]: e.target.value }));
  const mitGf = gewaehlt.includes("jtl_gf_cockpit");
  const mitDatev = gewaehlt.includes("jtl_datev");
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div>
        <h1 style={{ margin: 0, fontSize: 24, fontWeight: 800, color: S.textBright }}>Ein paar Angaben zu Ihrem Betrieb</h1>
        <p style={{ margin: "6px 0 0", color: S.textDim, lineHeight: 1.5 }}>
          Diese Werte stehen nicht in der Wawi. Ohne sie bleiben einzelne Zahlen leer, alles andere funktioniert trotzdem.
        </p>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 16 }}>
        {mitGf && (
          <Feld id="e-fix" label="Fixkosten pro Monat (€)" hint="Miete, Personal, Software. Nötig für das Betriebsergebnis.">
            <input id="e-fix" value={angaben.fixkosten} onChange={setze("fixkosten")} inputMode="decimal" className="dm-feld" style={feld} placeholder="z. B. 28500" />
          </Feld>
        )}
        {mitGf && (
          <Feld id="e-lh" label="Ladenhüter ab … Tagen ohne Verkauf" hint="Leer lassen für die Vorgabe (180 Tage).">
            <input id="e-lh" value={angaben.ladenhueter} onChange={setze("ladenhueter")} inputMode="numeric" className="dm-feld" style={feld} placeholder="180" />
          </Feld>
        )}
        <Feld id="e-mail" label="Warnungen per Mail an" hint="Jeden Morgen um 5:30. Leer lassen, wenn Sie keine Mails möchten.">
          <input id="e-mail" type="email" value={angaben.mail} onChange={setze("mail")} className="dm-feld" style={feld} placeholder="name@firma.de" />
        </Feld>
        {mitDatev && (
          <Feld id="e-berater" label="DATEV-Beraternummer" hint="Bekommen Sie vom Steuerberater.">
            <input id="e-berater" value={angaben.berater} onChange={setze("berater")} inputMode="numeric" className="dm-feld" style={feld} />
          </Feld>
        )}
        {mitDatev && (
          <Feld id="e-mandant" label="DATEV-Mandantennummer">
            <input id="e-mandant" value={angaben.mandant} onChange={setze("mandant")} inputMode="numeric" className="dm-feld" style={feld} />
          </Feld>
        )}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
        <button onClick={onZurueck} disabled={laeuft} style={knopf.neben}>Zurück</button>
        <button onClick={onEinrichten} disabled={laeuft} style={knopf.haupt}>
          {laeuft && <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} />}
          {laeuft ? `Richte ${gewaehlt.length} ${gewaehlt.length === 1 ? "Cockpit" : "Cockpits"} ein…` : "Einrichten"}
        </button>
      </div>
    </div>
  );
}

// ── Seite ────────────────────────────────────────────────────────────────────

export default function Einrichtung() {
  const navigate = useNavigate();
  const [schritt, setSchritt] = useState(1);
  const [verbindung, setVerbindung] = useState(null);
  const [gewaehlt, setGewaehlt] = useState([]);
  const [angaben, setAngaben] = useState({ fixkosten: "", ladenhueter: "", mail: "", berater: "", mandant: "" });
  const [laeuft, setLaeuft] = useState(false);
  const [ergebnis, setErgebnis] = useState(null);
  const [fehler, setFehler] = useState(null);

  const einrichten = async () => {
    setLaeuft(true); setFehler(null);
    const zahl = (t) => { const n = parseFloat(String(t).replace(/\./g, "").replace(",", ".")); return Number.isFinite(n) ? n : null; };
    try {
      const { data } = await api.post("/api/einrichtung/abschliessen", {
        connection_id: verbindung.connection_id, vorlagen: gewaehlt,
        fixkosten_monat: zahl(angaben.fixkosten),
        ladenhueter_tage: angaben.ladenhueter ? parseInt(angaben.ladenhueter, 10) || null : null,
        warn_email: angaben.mail || null, datev_berater: angaben.berater || null, datev_mandant: angaben.mandant || null,
      }, { timeout: 600000 });
      setErgebnis(data);
      setSchritt(4);
    } catch (e) {
      setFehler(fehlerText(e));
    } finally {
      setLaeuft(false);
    }
  };

  const fertig = (ergebnis?.ergebnisse || []).filter((e) => e.ok);
  const gescheitert = (ergebnis?.ergebnisse || []).filter((e) => !e.ok);

  return (
    <div style={{ minHeight: "100vh", backgroundColor: S.bgMain, color: S.textMain, display: "flex", justifyContent: "center",
      padding: "40px 16px 64px", boxSizing: "border-box" }}>
      {/* Beispielwerte in leeren Feldern dürfen nicht wie Eingaben aussehen */}
      <style>{".dm-feld::placeholder { color: var(--text-dim); opacity: 0.55; }"}</style>
      <div style={{ width: "100%", maxWidth: 780, display: "flex", flexDirection: "column", gap: 24 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <img src="/datenmonster.svg" alt="" style={{ width: 32, height: 32, borderRadius: 6 }} />
            <span style={{ fontWeight: 700, fontSize: 16, color: S.textBright }}>Datenmonster einrichten</span>
          </div>
          {schritt < 4 && <Link to="/start" style={{ fontSize: 14, color: S.accent }}>Später, zur Übersicht</Link>}
        </div>

        {schritt < 4 && <Fortschritt schritt={schritt} />}
        {fehler && <p style={{ color: "var(--err)", margin: 0 }}>{fehler}</p>}

        <section style={{ ...karte, borderRadius: 14, padding: 28 }}>
          {schritt === 1 && <SchrittVerbindung onFertig={(v) => { setVerbindung(v); setSchritt(2); }} />}
          {schritt === 2 && (
            <SchrittCockpits verbindung={verbindung} gewaehlt={gewaehlt} setGewaehlt={setGewaehlt}
              onZurueck={() => setSchritt(1)} onWeiter={() => setSchritt(3)} />
          )}
          {schritt === 3 && (
            <SchrittBetrieb gewaehlt={gewaehlt} angaben={angaben} setAngaben={setAngaben} laeuft={laeuft}
              onZurueck={() => setSchritt(2)} onEinrichten={einrichten} />
          )}
          {schritt === 4 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <h1 style={{ margin: 0, fontSize: 24, fontWeight: 800, color: S.textBright }}>
                {gescheitert.length ? "Fast fertig" : "Fertig eingerichtet"}
              </h1>
              <ul style={{ margin: 0, paddingLeft: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 6 }}>
                {fertig.map((e) => (
                  <li key={e.template_id} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <Check size={16} style={{ color: "var(--ok)" }} /> {e.name}
                  </li>
                ))}
                {gescheitert.map((e) => (
                  <li key={e.template_id} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    <span style={{ color: "var(--err)", fontWeight: 600 }}>{e.name || e.template_id}: nicht eingerichtet</span>
                    <span style={{ fontSize: 13, color: S.textDim }}>{e.fehler}</span>
                  </li>
                ))}
              </ul>
              {(ergebnis?.hinweise || []).map((h) => <p key={h} style={{ margin: 0, color: "var(--warn)", fontSize: 14 }}>{h}</p>)}
              <ul style={{ margin: 0, paddingLeft: 20, fontSize: 14, color: S.textDim, listStyle: "disc", display: "flex", flexDirection: "column", gap: 4 }}>
                <li>Die Cockpits rechnen beim ersten Öffnen; das kann einen Moment dauern.</li>
                {angaben.mail && <li>Warnungen gehen jeden Morgen um 5:30 an {angaben.mail}.</li>}
              </ul>
              <button onClick={() => navigate("/start")} style={{ ...knopf.haupt, alignSelf: "flex-start" }}>Zur Übersicht</button>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
