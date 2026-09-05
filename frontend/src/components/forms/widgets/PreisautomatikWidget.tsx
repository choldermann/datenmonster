import { useState, useEffect, useCallback } from "react";
import { Tags, Plus, Trash2, Play, FileDown, CheckCircle2, XCircle,
         RotateCcw, Loader2, AlertCircle, ChevronDown, ChevronRight, Undo2, Moon, TrendingUp } from "lucide-react";
import api, { fehlerText } from "../../../api/client";
import { onMandantChange } from "../../../services/mandant";

const S = {
  bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)", bgMain: "var(--bg-main)",
  border: "var(--border)", textMain: "var(--text-main)", textDim: "var(--text-dim)",
  textBright: "var(--text-bright)", accent: "var(--accent)",
};

const inp = {
  backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4,
  color: S.textMain, fontSize: 12, padding: "5px 8px", outline: "none",
};

const btn = (aktiv = true) => ({
  display: "inline-flex", alignItems: "center", gap: 6, padding: "6px 11px",
  borderRadius: 4, border: `1px solid ${S.border}`, backgroundColor: S.bgEl,
  color: aktiv ? S.textMain : S.textDim, fontSize: 12, cursor: aktiv ? "pointer" : "default",
  opacity: aktiv ? 1 : 0.5,
});

// Der Nachtlauf braucht nur eine Uhrzeit; der Cron-Ausdruck dahinter bleibt
// verborgen, weil „15 5 * * *" niemandem etwas sagt.
const cronZuZeit = (cron) => {
  const t = String(cron || "").trim().split(/\s+/);
  if (t.length !== 5) return "05:15";
  return `${String(t[1]).padStart(2, "0")}:${String(t[0]).padStart(2, "0")}`;
};
const zeitZuCron = (zeit) => {
  const [h, m] = String(zeit || "05:15").split(":");
  return `${parseInt(m, 10) || 0} ${parseInt(h, 10) || 0} * * *`;
};

const eur = (n) => n === null || n === undefined ? "–"
  : new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR",
      minimumFractionDigits: 2 }).format(n);

// Zustände in der Reihenfolge des Ablaufs – so liest sich die Filterleiste wie
// der Weg, den eine Preisänderung nimmt.
const ZUSTAENDE = [
  { key: "vorgeschlagen",   label: "Vorgeschlagen", farbe: "#fbbf24" },
  { key: "freigegeben",     label: "Freigegeben",   farbe: "#38bdf8" },
  { key: "angewandt",       label: "Angewandt",     farbe: "#4ade80" },
  { key: "verworfen",       label: "Verworfen",     farbe: "#94a3b8" },
  { key: "zurueckgenommen", label: "Zurückgenommen", farbe: "#a78bfa" },
];

/**
 * Widget „Preisautomatik“: Ladenhüter bekommen automatisch einen befristeten
 * Rabatt – als SONDERPREIS, nie als Grundpreis (siehe doku/jtl-preis-schema.md).
 *
 * Der Ablauf ist absichtlich sichtbar in Schritte zerlegt: Lauf → Vorschläge
 * freigeben → Ameise-Datei erzeugen → importieren → Kontrolle. „Angewandt“
 * vergibt allein die Kontrolle, und die liest die echten Preise aus der Wawi
 * zurück – eine erzeugte Datei ist noch keine Preisänderung.
 */
export default function PreisautomatikWidget({ widget, projectId }) {
  const [regelwerke, setRegelwerke] = useState([]);
  const [aktivId, setAktivId] = useState(null);
  const [zeilen, setZeilen] = useState([]);
  const [zaehler, setZaehler] = useState({});
  const [filter, setFilter] = useState("vorgeschlagen");
  const [auswahl, setAuswahl] = useState(new Set());
  const [laden, setLaden] = useState(true);
  const [arbeitet, setArbeitet] = useState(null);
  const [fehler, setFehler] = useState(null);
  const [hinweis, setHinweis] = useState(null);
  const [einstellungenOffen, setEinstellungenOffen] = useState(false);
  const [gruppen, setGruppen] = useState([]);

  const q = projectId ? `?project_id=${projectId}` : "";
  const rw = regelwerke.find(r => r.id === aktivId) || null;

  const regelwerkeLaden = useCallback(async () => {
    setLaden(true);
    try {
      const { data } = await api.get(`/api/preisregeln/regelwerke${q}`);
      setRegelwerke(data.regelwerke || []);
      setAktivId(prev => prev && (data.regelwerke || []).some(r => r.id === prev)
        ? prev : (data.regelwerke?.[0]?.id ?? null));
      setFehler(null);
    } catch (e) {
      setFehler(fehlerText(e));
    } finally {
      setLaden(false);
    }
  }, [q]);

  useEffect(() => { regelwerkeLaden(); }, [regelwerkeLaden]);
  // Regelwerke gehören zu genau einem Mandanten – beim Wechsel neu laden.
  useEffect(() => onMandantChange(() => { regelwerkeLaden(); }), [regelwerkeLaden]);

  const zeilenLaden = useCallback(async (id, zustand) => {
    if (!id) { setZeilen([]); setZaehler({}); return; }
    try {
      const { data } = await api.get(
        `/api/preisregeln/regelwerke/${id}/aenderungen?zustand=${zustand}`);
      setZeilen(data.rows || []);
      setZaehler(data.zaehler || {});
      setAuswahl(new Set());
    } catch (e) {
      setFehler(fehlerText(e));
    }
  }, []);

  useEffect(() => { zeilenLaden(aktivId, filter); }, [aktivId, filter, zeilenLaden]);

  // Kundengruppen der Wawi dieses Regelwerks – für die Auswahl mit Namen statt
  // Nummern. Schlägt der Zugriff fehl (Verbindung weg), bleibt die Liste leer
  // und die Einstellungen zeigen die gespeicherten Nummern.
  useEffect(() => {
    if (!aktivId) { setGruppen([]); return; }
    let abgebrochen = false;
    api.get(`/api/preisregeln/regelwerke/${aktivId}/kundengruppen`)
      .then(({ data }) => { if (!abgebrochen) setGruppen(data.optionen || []); })
      .catch(() => { if (!abgebrochen) setGruppen([]); });
    return () => { abgebrochen = true; };
  }, [aktivId]);

  const melden = (text) => { setHinweis(text); setTimeout(() => setHinweis(null), 8000); };

  const handeln = async (name, fn) => {
    setArbeitet(name); setFehler(null);
    try { await fn(); }
    catch (e) { setFehler(fehlerText(e)); }
    finally { setArbeitet(null); }
  };

  const neuesRegelwerk = () => handeln("neu", async () => {
    const { data } = await api.post("/api/preisregeln/regelwerke", {
      project_id: projectId, name: "Ladenhüter-Rabatte",
      scope: { min_kapital: 50 }, kundengruppen: [], shops: [0],
      nie_unter_ek: true, min_marge_prozent: 15, max_rabatt_prozent: 30,
      laufzeit_tage: 30,
    });
    await regelwerkeLaden();
    setAktivId(data.id);
    setEinstellungenOffen(true);
  });

  const speichern = (felder) => handeln("speichern", async () => {
    await api.put(`/api/preisregeln/regelwerke/${rw.id}`, { name: rw.name, ...felder });
    await regelwerkeLaden();
  });

  const stufeAnlegen = () => handeln("stufe", async () => {
    const hoechste = Math.max(0, ...(rw.regeln || []).map(r => r.sort || 0));
    await api.post(`/api/preisregeln/regelwerke/${rw.id}/regeln`, {
      sort: hoechste + 10, active: true,
      condition: { tage_ohne_verkauf_ab: 90 },
      action: { typ: "rabatt_prozent", wert: 5 },
    });
    await regelwerkeLaden();
  });

  const stufeAendern = (regel, felder) => handeln(`regel${regel.id}`, async () => {
    await api.put(`/api/preisregeln/regeln/${regel.id}`, { ...regel, ...felder });
    await regelwerkeLaden();
  });

  const stufeLoeschen = (regel) => handeln(`regel${regel.id}`, async () => {
    await api.delete(`/api/preisregeln/regeln/${regel.id}`);
    await regelwerkeLaden();
  });

  const laufStarten = () => handeln("lauf", async () => {
    const { data } = await api.post(`/api/preisregeln/regelwerke/${rw.id}/lauf`, {});
    melden(`${data.kandidaten} Kandidaten geprüft: ${data.vorschlaege} Vorschläge, `
         + `${data.verworfen} durch das Sicherheitsnetz abgelehnt.`);
    setFilter("vorgeschlagen");
    await zeilenLaden(rw.id, "vorgeschlagen");
  });

  const zustandSetzen = (zustand) => handeln(zustand, async () => {
    const ids = [...auswahl];
    if (!ids.length) return;
    const { data } = await api.post("/api/preisregeln/aenderungen/zustand", { ids, zustand });
    melden(`${data.geaendert} Änderungen auf „${zustand}“ gesetzt.`);
    await zeilenLaden(rw.id, filter);
  });

  const csvErzeugen = () => handeln("csv", async () => {
    const ids = [...auswahl];
    const { data } = await api.post(`/api/preisregeln/regelwerke/${rw.id}/ameise-csv`,
      { ids });
    melden(`Datei „${data.file_name}“ mit ${data.zeilen} Zeilen liegt unter `
         + `Exporte bereit. Nach dem Import in der Ameise bitte „Kontrolle“ drücken.`);
    await zeilenLaden(rw.id, filter);
  });

  const nachtlaufJetzt = () => handeln("nachtlauf", async () => {
    const { data } = await api.post(`/api/preisregeln/regelwerke/${rw.id}/nachtlauf`, {});
    const k = data.kontrolle || {}, l = data.lauf || {};
    melden(data.fehler ? `Nachtlauf fehlgeschlagen: ${data.fehler}`
      : `Nachtlauf: ${l.vorschlaege ?? 0} neue Vorschläge, ${l.verworfen ?? 0} abgelehnt; `
        + `Kontrolle: ${k.angewandt ?? 0} angekommen, ${k.fehlt ?? 0} offen.`
        + (data.mail?.sent ? " Bericht verschickt." : ""));
    await regelwerkeLaden();
    await zeilenLaden(rw.id, filter);
  });

  const wiederverkauf = () => handeln("wiederverkauf", async () => {
    const { data } = await api.post(`/api/preisregeln/regelwerke/${rw.id}/wiederverkauf`, {});
    melden(data.aus
      ? "Der Schalter „Rabatt endet bei Wiederverkauf“ ist aus – es wurde nichts geprüft."
      : `${data.geprueft} laufende Rabatte geprüft, ${data.beendet} beendet.`);
    await zeilenLaden(rw.id, filter);
  });

  const kontrollieren = () => handeln("kontrolle", async () => {
    const { data } = await api.post(`/api/preisregeln/regelwerke/${rw.id}/kontrolle`, {});
    melden(`${data.geprueft} geprüft: ${data.angewandt} in der Wawi angekommen, `
         + `${data.fehlt} nicht gefunden, ${data.abweichend} mit abweichendem Preis.`);
    await zeilenLaden(rw.id, filter);
  });

  const zuruecknehmen = () => handeln("ruecknahme", async () => {
    const ids = [...auswahl];
    if (!ids.length) return;
    const { data } = await api.post("/api/preisregeln/aenderungen/ruecknahme", { ids });
    melden(`${data.zurueckgenommen} Änderungen zurückgenommen – die Gegenbuchungen `
         + `stehen als „freigegeben“ zum Export bereit.`);
    await zeilenLaden(rw.id, filter);
  });

  // „Ameise-Datei erzeugen" exportiert nur FREIGEGEBENE Änderungen. Ohne
  // welche lief der Klick in eine Fehlermeldung – der Knopf bleibt jetzt
  // gesperrt und sagt im Tooltip, was fehlt.
  const ausgewaehlteFreigegebene = zeilen.filter(
    z => auswahl.has(z.id) && z.Zustand === "freigegeben").length;
  const freigegebenGesamt = zaehler.freigegeben || 0;
  const exportierbar = auswahl.size > 0 ? ausgewaehlteFreigegebene : freigegebenGesamt;
  const exportHinweis = exportierbar
    ? (auswahl.size > 0
        ? `${exportierbar} ausgewählte freigegebene Änderungen exportieren`
        : `alle ${exportierbar} freigegebenen Änderungen exportieren`)
    : (auswahl.size > 0
        ? "In der Auswahl ist nichts Freigegebenes – erst „Freigeben“ drücken."
        : "Es ist nichts freigegeben. Zeilen ankreuzen und „Freigeben“ drücken.");

  const alleUmschalten = () => setAuswahl(prev =>
    prev.size === zeilen.length ? new Set() : new Set(zeilen.map(z => z.id)));

  const umschalten = (id) => setAuswahl(prev => {
    const n = new Set(prev);
    n.has(id) ? n.delete(id) : n.add(id);
    return n;
  });

  if (laden) return (
    <div style={{ padding: 20, color: S.textDim, fontSize: 12, display: "flex", gap: 8 }}>
      <Loader2 size={13} className="spin" /> Regelwerke werden geladen …
    </div>
  );

  return (
    <div style={{ padding: 14 }}>
      {/* Kopf: Regelwerk wählen */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
        marginBottom: 12 }}>
        <Tags size={14} color={S.accent} />
        {regelwerke.length > 0 ? (
          <select style={{ ...inp, minWidth: 220 }} value={aktivId || ""}
            onChange={e => setAktivId(Number(e.target.value))}>
            {regelwerke.map(r => (
              <option key={r.id} value={r.id}>
                {r.name}{r.mandant_name ? ` · ${r.mandant_name}` : ""}{r.active ? "" : " (inaktiv)"}
              </option>
            ))}
          </select>
        ) : (
          <span style={{ fontSize: 12, color: S.textDim }}>
            Noch kein Regelwerk angelegt.
          </span>
        )}
        <button style={btn()} onClick={neuesRegelwerk} disabled={arbeitet === "neu"}>
          <Plus size={12} /> Neues Regelwerk
        </button>
        {rw?.offen?.nicht_angekommen > 0 && (
          <span style={{ fontSize: 12, color: "#e07070" }}>
            {rw.offen.nicht_angekommen} freigegebene Änderungen sind nicht in der Wawi
            angekommen
          </span>
        )}
        {rw && (
          <button style={{ ...btn(), marginLeft: "auto" }}
            onClick={() => setEinstellungenOffen(o => !o)}>
            {einstellungenOffen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            Regeln und Grenzen
          </button>
        )}
      </div>

      {fehler && (
        <div style={{ display: "flex", gap: 8, alignItems: "flex-start", padding: "8px 11px",
          marginBottom: 10, borderRadius: 4, border: "1px solid #7f3b3b",
          backgroundColor: "rgba(224,112,112,0.08)", color: "#e07070", fontSize: 12 }}>
          <AlertCircle size={13} style={{ flexShrink: 0, marginTop: 1 }} /> {fehler}
        </div>
      )}
      {hinweis && (
        <div style={{ padding: "8px 11px", marginBottom: 10, borderRadius: 4,
          border: `1px solid ${S.border}`, backgroundColor: S.bgEl,
          color: S.textMain, fontSize: 12 }}>{hinweis}</div>
      )}

      {rw && einstellungenOffen && (
        <Einstellungen rw={rw} speichern={speichern} stufeAnlegen={stufeAnlegen}
          stufeAendern={stufeAendern} stufeLoeschen={stufeLoeschen} arbeitet={arbeitet}
          gruppen={gruppen} />
      )}

      {rw && (
        <>
          {/* Ablauf als Knopfleiste – in der Reihenfolge, in der er passiert */}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
            <button style={btn()} onClick={laufStarten} disabled={arbeitet === "lauf"}>
              {arbeitet === "lauf" ? <Loader2 size={12} className="spin" /> : <Play size={12} />}
              Lauf starten
            </button>
            <button style={btn(auswahl.size > 0)} onClick={() => zustandSetzen("freigegeben")}
              disabled={!auswahl.size}>
              <CheckCircle2 size={12} /> Freigeben{auswahl.size ? ` (${auswahl.size})` : ""}
            </button>
            <button style={btn(auswahl.size > 0)} onClick={() => zustandSetzen("verworfen")}
              disabled={!auswahl.size}>
              <XCircle size={12} /> Verwerfen
            </button>
            <button style={btn(exportierbar > 0)} onClick={csvErzeugen}
              disabled={!exportierbar || arbeitet === "csv"} title={exportHinweis}>
              {arbeitet === "csv" ? <Loader2 size={12} className="spin" /> : <FileDown size={12} />}
              Ameise-Datei erzeugen{exportierbar ? ` (${exportierbar})` : ""}
            </button>
            <button style={btn()} onClick={kontrollieren} disabled={arbeitet === "kontrolle"}>
              {arbeitet === "kontrolle" ? <Loader2 size={12} className="spin" /> : <RotateCcw size={12} />}
              Kontrolle
            </button>
            <button style={btn(auswahl.size > 0)} onClick={zuruecknehmen} disabled={!auswahl.size}>
              <Undo2 size={12} /> Zurücknehmen
            </button>
            {rw.ende_bei_verkauf && (
              <button style={btn()} onClick={wiederverkauf}
                disabled={arbeitet === "wiederverkauf"}
                title="Laufende Rabatte beenden, deren Artikel sich wieder verkauft">
                {arbeitet === "wiederverkauf"
                  ? <Loader2 size={12} className="spin" /> : <TrendingUp size={12} />}
                Wiederverkauf prüfen
              </button>
            )}
            <button style={{ ...btn(), marginLeft: "auto" }} onClick={nachtlaufJetzt}
              disabled={arbeitet === "nachtlauf"}
              title="Kontrollieren und neu vorschlagen – genau das, was nachts läuft">
              {arbeitet === "nachtlauf" ? <Loader2 size={12} className="spin" /> : <Moon size={12} />}
              Nachtlauf jetzt
            </button>
          </div>

          {/* Zustandsfilter mit Zählern */}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
            {ZUSTAENDE.map(z => (
              <button key={z.key} onClick={() => setFilter(z.key)}
                style={{ ...btn(), borderColor: filter === z.key ? z.farbe : S.border,
                  color: filter === z.key ? S.textBright : S.textDim, padding: "4px 9px" }}>
                <span style={{ width: 7, height: 7, borderRadius: "50%",
                  backgroundColor: z.farbe, display: "inline-block" }} />
                {z.label} {zaehler[z.key] ? `(${zaehler[z.key]})` : ""}
              </button>
            ))}
          </div>

          <Tabelle zeilen={zeilen} auswahl={auswahl} umschalten={umschalten}
            alleUmschalten={alleUmschalten} />
        </>
      )}
    </div>
  );
}


function Einstellungen({ rw, speichern, stufeAnlegen, stufeAendern, stufeLoeschen,
                        arbeitet, gruppen = [] }) {
  const [entwurf, setEntwurf] = useState(rw);
  useEffect(() => setEntwurf(rw), [rw]);
  const feld = (k, v) => setEntwurf(p => ({ ...p, [k]: v }));
  const sichern = () => speichern({
    name: entwurf.name, active: entwurf.active,
    kundengruppen: entwurf.kundengruppen, laufzeit_tage: Number(entwurf.laufzeit_tage) || 30,
    nie_unter_ek: entwurf.nie_unter_ek,
    min_marge_prozent: entwurf.min_marge_prozent === "" ? null : Number(entwurf.min_marge_prozent),
    max_rabatt_prozent: entwurf.max_rabatt_prozent === "" ? null : Number(entwurf.max_rabatt_prozent),
    scope: entwurf.scope, auto_freigabe: entwurf.auto_freigabe,
  });

  return (
    <div style={{ border: `1px solid ${S.border}`, borderRadius: 5, padding: 12,
      marginBottom: 12, backgroundColor: S.bgMain }}>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
        <Feld label="Name">
          <input style={{ ...inp, width: 200 }} value={entwurf.name || ""}
            onChange={e => feld("name", e.target.value)} onBlur={sichern} />
        </Feld>
        <Feld label="Laufzeit des Rabatts (Tage)">
          <input style={{ ...inp, width: 90 }} type="number" value={entwurf.laufzeit_tage ?? 30}
            onChange={e => feld("laufzeit_tage", e.target.value)} onBlur={sichern} />
        </Feld>

        <Feld label="Mindestmarge %">
          <input style={{ ...inp, width: 80 }} type="number"
            value={entwurf.min_marge_prozent ?? ""}
            onChange={e => feld("min_marge_prozent", e.target.value)} onBlur={sichern} />
        </Feld>
        <Feld label="Höchstrabatt %">
          <input style={{ ...inp, width: 80 }} type="number"
            value={entwurf.max_rabatt_prozent ?? ""}
            onChange={e => feld("max_rabatt_prozent", e.target.value)} onBlur={sichern} />
        </Feld>
        <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12,
          color: S.textMain, paddingBottom: 6 }}>
          <input type="checkbox" checked={!!entwurf.nie_unter_ek}
            onChange={e => { feld("nie_unter_ek", e.target.checked);
              speichern({ name: entwurf.name, nie_unter_ek: e.target.checked }); }} />
          nie unter Einstandspreis
        </label>
        <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12,
          color: S.textMain, paddingBottom: 6 }}
          title="Verkauft sich ein rabattierter Artikel wieder, wird der Rabatt beendet.">
          <input type="checkbox" checked={!!entwurf.ende_bei_verkauf}
            onChange={e => { feld("ende_bei_verkauf", e.target.checked);
              speichern({ name: entwurf.name, ende_bei_verkauf: e.target.checked,
                          ende_ab_menge: Number(entwurf.ende_ab_menge) || 1 }); }} />
          Rabatt endet bei Wiederverkauf
        </label>
        {entwurf.ende_bei_verkauf && (
          <Feld label="ab verkaufter Menge">
            <input style={{ ...inp, width: 80 }} type="number" min="1"
              value={entwurf.ende_ab_menge ?? 1}
              onChange={e => feld("ende_ab_menge", e.target.value)}
              onBlur={() => speichern({ name: entwurf.name,
                ende_ab_menge: Number(entwurf.ende_ab_menge) || 1 })} />
          </Feld>
        )}
        <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12,
          color: S.textMain, paddingBottom: 6 }}>
          <input type="checkbox" checked={!!entwurf.active}
            onChange={e => { feld("active", e.target.checked);
              speichern({ name: entwurf.name, active: e.target.checked }); }} />
          aktiv
        </label>
      </div>

      <div style={{ marginTop: 12 }}>
        <label style={{ display: "block", fontSize: 9, fontWeight: 700, letterSpacing: "0.1em",
          textTransform: "uppercase", color: S.textDim, marginBottom: 5 }}>
          Kundengruppen – ohne Auswahl gilt der Rabatt für alle
        </label>
        {gruppen.length === 0 ? (
          <div style={{ fontSize: 12, color: S.textDim }}>
            Kundengruppen konnten nicht gelesen werden
            {(entwurf.kundengruppen || []).length
              ? ` – gespeichert: ${(entwurf.kundengruppen || []).join(", ")}` : ""}
          </div>
        ) : (
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            {gruppen.map(g => {
              const drin = (entwurf.kundengruppen || []).includes(g.value);
              return (
                <label key={g.value} style={{ display: "flex", gap: 5, alignItems: "center",
                  fontSize: 12, color: drin ? S.textBright : S.textMain }}>
                  <input type="checkbox" checked={drin} onChange={e => {
                    const neu = e.target.checked
                      ? [...(entwurf.kundengruppen || []), g.value]
                      : (entwurf.kundengruppen || []).filter(v => v !== g.value);
                    feld("kundengruppen", neu);
                    speichern({ name: entwurf.name, kundengruppen: neu });
                  }} />
                  {/* Nummer vorn, Gruppenrabatt hinten: Der Rabatt der
                      Kundengruppe wirkt auf den Preis und damit auf die Marge,
                      die das Sicherheitsnetz prüft – man sollte ihn sehen.
                      Name trimmen ist nur Anzeige; gespeichert wird die Nummer,
                      und die Ameise-Spalte baut später den ungekürzten Namen. */}
                  {g.value}-{String(g.label).trim()}
                  <span style={{ color: S.textDim }}>
                    ({String(g.rabatt ?? 0).replace(".", ",")}%)
                  </span>
                </label>
              );
            })}
          </div>
        )}
      </div>

      <div style={{ marginTop: 14, paddingTop: 12, borderTop: `1px solid ${S.border}`,
        display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
        <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12,
          color: S.textMain, paddingBottom: 6 }}>
          <input type="checkbox" checked={!!entwurf.zeitplan_aktiv}
            onChange={e => { feld("zeitplan_aktiv", e.target.checked);
              speichern({ name: entwurf.name, zeitplan_aktiv: e.target.checked,
                          cron_expr: entwurf.cron_expr || "15 5 * * *" }); }} />
          Nachtlauf
        </label>
        <Feld label="Uhrzeit">
          <input style={{ ...inp, width: 90 }} type="time"
            value={cronZuZeit(entwurf.cron_expr)}
            onChange={e => feld("cron_expr", zeitZuCron(e.target.value))}
            onBlur={() => speichern({ name: entwurf.name, cron_expr: entwurf.cron_expr })} />
        </Feld>
        <Feld label="Bericht an (leer = kein Versand)">
          <input style={{ ...inp, width: 240 }} value={entwurf.email_to || ""}
            placeholder="name@firma.de"
            onChange={e => feld("email_to", e.target.value)}
            onBlur={() => speichern({ name: entwurf.name, email_to: entwurf.email_to })} />
        </Feld>
        {rw.last_run_at && (
          <div style={{ fontSize: 11, color: rw.last_status === "error" ? "#e07070" : S.textDim,
            paddingBottom: 6, maxWidth: 460 }}>
            zuletzt {rw.last_run_at}: {rw.last_message}
          </div>
        )}
      </div>
      <div style={{ fontSize: 11, color: S.textDim, marginTop: 6 }}>
        Der Nachtlauf kontrolliert zuerst, was in der Wawi angekommen ist, und bildet
        dann neue Vorschläge. Angewandt wird dabei nichts.
      </div>

      <div style={{ marginTop: 12, fontSize: 10, fontWeight: 700, letterSpacing: "0.1em",
        textTransform: "uppercase", color: S.textDim }}>
        Stufen – die höchste zutreffende gewinnt
      </div>
      {(rw.regeln || []).map(r => (
        <div key={r.id} style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 7 }}>
          <span style={{ fontSize: 12, color: S.textDim }}>ab</span>
          <input style={{ ...inp, width: 70 }} type="number"
            defaultValue={r.condition?.tage_ohne_verkauf_ab ?? 90}
            onBlur={e => stufeAendern(r, { condition: { tage_ohne_verkauf_ab: Number(e.target.value) } })} />
          <span style={{ fontSize: 12, color: S.textDim }}>Tagen ohne Verkauf →</span>
          <input style={{ ...inp, width: 70 }} type="number"
            defaultValue={r.action?.wert ?? 5}
            onBlur={e => stufeAendern(r, { action: { typ: "rabatt_prozent", wert: Number(e.target.value) } })} />
          <span style={{ fontSize: 12, color: S.textDim }}>% Rabatt</span>
          <button style={{ ...btn(), padding: "4px 7px" }} onClick={() => stufeLoeschen(r)}
            disabled={arbeitet === `regel${r.id}`}>
            <Trash2 size={12} />
          </button>
        </div>
      ))}
      <button style={{ ...btn(), marginTop: 9 }} onClick={stufeAnlegen}>
        <Plus size={12} /> Stufe hinzufügen
      </button>
    </div>
  );
}


function Feld({ label, children }) {
  return (
    <div>
      <label style={{ display: "block", fontSize: 9, fontWeight: 700, letterSpacing: "0.1em",
        textTransform: "uppercase", color: S.textDim, marginBottom: 4 }}>{label}</label>
      {children}
    </div>
  );
}


function Tabelle({ zeilen, auswahl, umschalten, alleUmschalten }) {
  if (!zeilen.length) return (
    <div style={{ padding: "14px 4px", color: S.textDim, fontSize: 12 }}>
      Keine Einträge in diesem Zustand.
    </div>
  );
  const th = { textAlign: "left", padding: "6px 8px", fontSize: 10, fontWeight: 700,
    letterSpacing: "0.08em", textTransform: "uppercase", color: S.textDim,
    borderBottom: `1px solid ${S.border}`, whiteSpace: "nowrap" };
  const td = { padding: "6px 8px", fontSize: 12, color: S.textMain,
    borderBottom: `1px solid ${S.border}` };
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={{ ...th, width: 28 }}>
              <input type="checkbox" checked={auswahl.size === zeilen.length && zeilen.length > 0}
                onChange={alleUmschalten} />
            </th>
            <th style={th}>ArtNr</th>
            <th style={th}>Artikel</th>
            <th style={th}>Gruppe</th>
            <th style={{ ...th, textAlign: "right" }}>bisher</th>
            <th style={{ ...th, textAlign: "right" }}>neu</th>
            <th style={{ ...th, textAlign: "right" }}>Rabatt</th>
            <th style={{ ...th, textAlign: "right" }}>EK</th>
            <th style={th}>gültig bis</th>
            <th style={th}>Ist</th>
            <th style={th}>Begründung</th>
          </tr>
        </thead>
        <tbody>
          {zeilen.map(z => (
            <tr key={z.id}>
              <td style={td}>
                <input type="checkbox" checked={auswahl.has(z.id)}
                  onChange={() => umschalten(z.id)} />
              </td>
              <td style={{ ...td, whiteSpace: "nowrap" }}>{z.ArtNr}</td>
              <td style={{ ...td, maxWidth: 320 }}>{z.Artikel}</td>
              <td style={td}>{z.Kundengruppe}</td>
              <td style={{ ...td, textAlign: "right" }}>{eur(z.PreisAlt)}</td>
              <td style={{ ...td, textAlign: "right", color: S.textBright }}>{eur(z.PreisNeu)}</td>
              <td style={{ ...td, textAlign: "right" }}>
                {z.RabattProzent === null ? "–" : `${z.RabattProzent} %`}
              </td>
              <td style={{ ...td, textAlign: "right", color: S.textDim }}>{eur(z.EKNetto)}</td>
              <td style={{ ...td, whiteSpace: "nowrap" }}>{z.GueltigBis}</td>
              <td style={{ ...td, whiteSpace: "nowrap",
                color: z.Abweichung === "ok" ? "#4ade80"
                     : z.Abweichung === "abweichend" ? "#e07070" : S.textDim }}>
                {z.Abweichung ? (z.IstPreis != null ? `${z.Abweichung} · ${eur(z.IstPreis)}`
                                                    : z.Abweichung) : "–"}
              </td>
              <td style={{ ...td, color: S.textDim, maxWidth: 380 }}>{z.Begruendung}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
