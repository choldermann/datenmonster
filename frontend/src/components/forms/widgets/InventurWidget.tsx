import { useState, useEffect, useCallback, Fragment } from "react";
import { ClipboardList, Plus, RefreshCw, Download, Lock, Unlock, Trash2,
         AlertCircle, Loader2, ChevronDown, ChevronRight, Wand2, Check,
         Search, X, SlidersHorizontal } from "lucide-react";
import api, { fehlerText } from "../../../api/client";
import { onMandantChange } from "../../../services/mandant";
import InventurStufenModal from "./InventurStufenModal";
import BestaetigenModal from "./BestaetigenModal";

const S = {
  bgCard: "var(--bg-card)", bgEl: "var(--bg-elevated)", bgMain: "var(--bg-main)",
  border: "var(--border)", textMain: "var(--text-main)", textDim: "var(--text-dim)",
  textBright: "var(--text-bright)", accent: "var(--accent)",
};

const inp = {
  backgroundColor: S.bgEl, border: `1px solid ${S.border}`, borderRadius: 4,
  color: S.textMain, fontSize: 12, padding: "5px 8px", outline: "none",
};

const btn = {
  display: "inline-flex", alignItems: "center", gap: 6, padding: "6px 11px",
  borderRadius: 5, border: `1px solid ${S.border}`, backgroundColor: S.bgEl,
  color: S.textMain, fontSize: 12, cursor: "pointer",
};

const eur = (n) => new Intl.NumberFormat("de-DE", {
  style: "currency", currency: "EUR", maximumFractionDigits: 2 }).format(n || 0);
const zahl = (n, k = 0) => new Intl.NumberFormat("de-DE", {
  maximumFractionDigits: k }).format(n || 0);
const datum = (iso) => iso ? new Date(iso).toLocaleDateString("de-DE") : "–";
const heuteISO = () => new Date().toISOString().slice(0, 10);

/**
 * Ein Prozentsatz braucht einen Bezug. „% auf abgelaufene Chargen" trifft nur
 * die Partien, deren MHD am Stichtag vorbei war – bei Artikel 80123 sind das
 * 31.936 € von 45.630 €, der Rest liegt in drei bis 2028 haltbaren Chargen.
 * Deshalb ist diese Art vorbelegt, wo es abgelaufene Ware gibt.
 */
const BEWERTUNGSARTEN = [
  { id: "prozent_abgelaufen", label: "% auf abgelaufene", einheit: "%" },
  { id: "prozent",    label: "% auf Position", einheit: "%" },
  { id: "stueckwert", label: "neuer Stückwert", einheit: "€/Stk" },
  { id: "betrag",     label: "Abwertungsbetrag", einheit: "€" },
];

/** Färbt die Restlaufzeit: abgelaufen rot, knapp gelb, sonst neutral. */
function restFarbe(tage) {
  if (tage === null || tage === undefined) return S.textDim;
  if (tage < 0) return "#e07070";
  if (tage < 90) return "#e0b070";
  return S.textMain;
}

/** MHD einer Charge: das Mapping liefert TT.MM.JJJJ, der Lauf JJJJ-MM-TT. */
function alsDatum(v) {
  if (!v) return null;
  const s = String(v).slice(0, 10);
  const de = s.match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
  const d = de ? new Date(`${de[3]}-${de[2]}-${de[1]}`) : new Date(s);
  return isNaN(d.getTime()) ? null : d;
}

/** Resttage einer Charge bis zum Stichtag der Inventur. */
function resttage(mhd, stichtag) {
  const a = alsDatum(mhd), b = alsDatum(stichtag);
  if (!a || !b) return null;
  return Math.round((a.getTime() - b.getTime()) / 86400000);
}

/**
 * Welche Abwertungsstufe eine Charge trifft – dieselbe Regel wie im Backend
 * (_vorschlag_fuer): aufsteigend sortiert, die engste Stufe gewinnt. Die Liste
 * zeigt damit an der Partie, was der Vorschlag mit ihr macht.
 */
function stufeFuer(tage, stufen) {
  if (tage === null || !stufen?.length) return null;
  return stufen.find(st => tage <= Number(st.bis_tage ?? 0)) || null;
}

/**
 * Widget „Inventur“: Bestände zu einem Stichtag einfrieren, bewerten und als
 * dokumentierte Liste ausgeben.
 *
 * Warum eingefroren und nicht live gerechnet: Eine Inventur ist ein Beleg. Sie
 * muss in zwei Jahren noch die Zahlen zeigen, die damals an den Steuerberater
 * gingen – auch wenn Bestände und Einkaufspreise sich längst geändert haben.
 * Die Ermittlung selbst kommt aus dem Mapping „Inventur – Bestand zum
 * Stichtag"; das Ergebnis wird beim Befüllen als Momentaufnahme gespeichert.
 *
 * Bewusst NICHT enthalten: Zurückschreiben des abgewerteten Wertes in die WaWi.
 * JTL kennt keinen Abwertungswert – der Lagerwert ist dort Menge × EK, ein
 * Rückschreiben müsste also den Einkaufspreis verfälschen.
 */
export default function InventurWidget({ widget, projectId }) {
  const [laeufe, setLaeufe] = useState([]);
  const [aktiv, setAktiv] = useState(null);        // ausgewählter Lauf
  const [positionen, setPositionen] = useState([]);
  const [laden, setLaden] = useState(true);
  const [arbeitet, setArbeitet] = useState(null);  // Text der laufenden Aktion
  const [fehler, setFehler] = useState(null);
  const [neuOffen, setNeuOffen] = useState(false);
  const [neuStichtag, setNeuStichtag] = useState(heuteISO());
  const [neuName, setNeuName] = useState("");
  const [suche, setSuche] = useState("");
  const [nurBewertet, setNurBewertet] = useState(false);
  const [nurAbgelaufen, setNurAbgelaufen] = useState(false);
  const [detail, setDetail] = useState({});        // pos.id → Chargen aufgeklappt
  const [entwurf, setEntwurf] = useState({});      // pos.id → {art, wert, grund}
  const [standardStufen, setStandardStufen] = useState([]);
  const [stufenOffen, setStufenOffen] = useState(false);
  const [frage, setFrage] = useState(null);         // offene Rückfrage (BestaetigenModal)
  const [gruende, setGruende] = useState([]);       // Auswahl für Differenzgründe
  const [zaehlEntwurf, setZaehlEntwurf] = useState({}); // Eingaben: "id" Ist, "id:i" Charge, "n id" Notiz
  const [zaehltagEntwurf, setZaehltagEntwurf] = useState(null);
  const [nurAbweichung, setNurAbweichung] = useState(false);
  const [nurUngezaehlt, setNurUngezaehlt] = useState(false);

  // Die Staffel DIESER Inventur (sie gehört zum Beleg), sonst die Standardstaffel.
  // Aufsteigend sortiert wie im Backend – die engste Stufe gewinnt.
  const stufen = [...(aktiv?.abwertung_stufen || standardStufen)]
    .sort((a, b) => Number(a.bis_tage ?? 0) - Number(b.bis_tage ?? 0));

  const q = projectId ? `?project_id=${projectId}` : "";

  const laeufeLaden = useCallback(async () => {
    setLaden(true);
    try {
      const { data } = await api.get(`/api/inventur/laeufe${q}`);
      setLaeufe(data || []);
      setFehler(null);
      return data || [];
    } catch (e) {
      setFehler(fehlerText(e));
      return [];
    } finally {
      setLaden(false);
    }
  }, [q]);

  const positionenLaden = useCallback(async (laufId) => {
    if (!laufId) { setPositionen([]); return; }
    try {
      const { data } = await api.get(`/api/inventur/laeufe/${laufId}/positionen`);
      setPositionen(data.positionen || []);
      setAktiv(data.lauf);
      setFehler(null);
    } catch (e) {
      setFehler(fehlerText(e));
    }
  }, []);

  useEffect(() => { laeufeLaden(); }, [laeufeLaden]);

  // Die Standardstaffel: Rückfall für Inventuren ohne eigene und Vorlage für den
  // Knopf „Standard" im Staffel-Modal.
  useEffect(() => {
    api.get("/api/inventur/stufen")
      .then(({ data }) => setStandardStufen(data || []))
      .catch(() => setStandardStufen([]));   // ohne Stufen fehlt nur die Spalte
    api.get("/api/inventur/differenzgruende")
      .then(({ data }) => setGruende(data || []))
      .catch(() => setGruende([]));
  }, []);

  // Beim Mandantenwechsel neu laden: die Inventur des einen Betriebs hat in der
  // Maske des anderen nichts zu suchen.
  useEffect(() => onMandantChange(() => {
    setAktiv(null); setPositionen([]); laeufeLaden();
  }), [laeufeLaden]);

  const anlegen = async () => {
    setArbeitet("anlegen");
    try {
      const { data } = await api.post("/api/inventur/laeufe", {
        project_id: projectId || null,
        stichtag: neuStichtag,
        name: neuName.trim() || null,
      });
      setNeuOffen(false); setNeuName("");
      await laeufeLaden();
      setAktiv(data);
      // Direkt befüllen: ein leerer Inventurkopf nützt niemandem.
      await befuellen(data.id);
    } catch (e) {
      setFehler(fehlerText(e));
    } finally {
      setArbeitet(null);
    }
  };

  const befuellen = async (laufId) => {
    setArbeitet("befuellen");
    setFehler(null);
    try {
      const { data } = await api.post(`/api/inventur/laeufe/${laufId}/befuellen`);
      setAktiv(data.lauf);
      await positionenLaden(laufId);
      await laeufeLaden();
    } catch (e) {
      setFehler(fehlerText(e));
    } finally {
      setArbeitet(null);
    }
  };

  const vorschlagen = async () => {
    setArbeitet("vorschlag");
    try {
      const { data } = await api.post(`/api/inventur/laeufe/${aktiv.id}/vorschlag`,
                                      { nur_unbewertete: true });
      setAktiv(data.lauf);
      await positionenLaden(aktiv.id);
    } catch (e) {
      setFehler(fehlerText(e));
    } finally {
      setArbeitet(null);
    }
  };

  // Speichert die Staffel dieser Inventur. Fehler gehen an das Modal zurück –
  // dort sieht man sie, statt hinter dem Overlay.
  const stufenSpeichern = async (neu, neuVorschlagen) => {
    const { data } = await api.put(`/api/inventur/laeufe/${aktiv.id}/stufen`,
                                   { stufen: neu, neu_vorschlagen: neuVorschlagen });
    setAktiv(data.lauf);
    setStufenOffen(false);
    if (neuVorschlagen) await positionenLaden(aktiv.id);
  };

  // Was eine Staffel mit dieser Inventur machen würde – dieselbe Rechnung wie
  // _vorschlag_fuer im Backend: je Charge. Übernommene Staffel-Bewertungen zählen
  // mit, nur echte Handbewertungen bleiben unberührt (wie vorschlag_anwenden).
  // Ergebnis in der Reihenfolge der übergebenen Stufen.
  const stufenVorschau = (entwurfStufen) => {
    const reihe = entwurfStufen.map((_, i) => i)
      .sort((a, b) => entwurfStufen[a].bis_tage - entwurfStufen[b].bis_tage);
    const je = entwurfStufen.map(() => ({ chargen: 0, wert: 0, abwertung: 0 }));
    for (const p of positionen) {
      const ausStaffel = p.vorschlag || p.bewertung_quelle === "staffel";
      if (p.bewertung_art && !ausStaffel) continue;
      // Artikelzählung: die Partien anteilig zur gezählten Menge (wie _vorschlag_fuer).
      const faktor = p.zaehlung_ebene === "artikel" && p.bestand_soll > 0.0005
        ? (p.bestand || 0) / p.bestand_soll : 1;
      const mitMhd = (p.chargen || []).filter(c => alsDatum(c.mhd));
      const teile = mitMhd.length
        ? mitMhd.map(c => ({ rest: resttage(c.mhd, aktiv.stichtag),
                             wert: (c.wert ?? (c.menge || 0) * (c.ek || 0)) * faktor }))
        : (p.resttage !== null && p.resttage !== undefined
            ? [{ rest: p.resttage, wert: p.wert || 0 }] : []);
      for (const t of teile) {
        if (t.rest === null || !(t.wert > 0)) continue;
        const i = reihe.find(k => t.rest <= entwurfStufen[k].bis_tage);
        if (i === undefined) continue;
        je[i].chargen += 1;
        je[i].wert += t.wert;
        je[i].abwertung += t.wert * entwurfStufen[i].prozent / 100;
      }
    }
    return je;
  };

  const bestaetigen = async () => {
    setArbeitet("bestaetigen");
    try {
      const { data } = await api.post(`/api/inventur/laeufe/${aktiv.id}/vorschlaege-bestaetigen`);
      setAktiv(data.lauf);
      await positionenLaden(aktiv.id);
    } catch (e) {
      setFehler(fehlerText(e));
    } finally {
      setArbeitet(null);
    }
  };

  // Eingaben kommen mit deutschem Dezimalkomma – Number() macht daraus sonst NaN
  // und die Bewertung verschwindet stillschweigend.
  const alsZahl = (v) => Number(String(v ?? "").replace(/\./g, "").replace(",", "."));

  const bewerten = async (pos) => {
    const e = entwurf[pos.id];
    if (!e || e.wert === "" || e.wert === null || isNaN(alsZahl(e.wert))) return;
    try {
      const { data } = await api.put(`/api/inventur/positionen/${pos.id}/bewertung`,
        { art: e.art || "prozent", wert: alsZahl(e.wert), grund: e.grund || null });
      setPositionen(prev => prev.map(p => p.id === pos.id ? data.position : p));
      setAktiv(data.lauf);
      setEntwurf(prev => { const n = { ...prev }; delete n[pos.id]; return n; });
    } catch (err) {
      setFehler(fehlerText(err));
    }
  };

  // Zählung speichern. `felder` nur mit dem, was sich ändert ({ist}, {grund},
  // {notiz}, {charge_index, charge_ist}) – der Server lässt den Rest stehen.
  const zaehlungSpeichern = async (pos, felder) => {
    try {
      const { data } = await api.put(`/api/inventur/positionen/${pos.id}/zaehlung`, felder);
      setPositionen(prev => prev.map(p => p.id === pos.id ? data.position : p));
      setAktiv(data.lauf);
    } catch (err) {
      setFehler(fehlerText(err));
    }
  };

  // Eingabe „Ist" übernehmen: leer = nicht gezählt, sonst Zahl (deutsches Komma).
  const zaehlungUebernehmen = (pos, schluessel, felderFuer) => {
    const roh = zaehlEntwurf[schluessel];
    if (roh === undefined) return;
    setZaehlEntwurf(d => { const n = { ...d }; delete n[schluessel]; return n; });
    const s = String(roh).trim();
    const wert = s === "" ? null : alsZahl(s);
    if (wert !== null && isNaN(wert)) { setFehler("Bitte eine Zahl eintragen."); return; }
    zaehlungSpeichern(pos, felderFuer(wert));
  };

  // Zähltag: holt die Buchmengen dieses Tages – Soll steht dann gegen das Regal,
  // wie es der Zähler sieht; zurückgerechnet wird auf den Stichtag.
  const zaehltagSetzen = async (wert) => {
    setArbeitet("zaehltag");
    try {
      const { data } = await api.put(`/api/inventur/laeufe/${aktiv.id}/zaehltag`,
        { zaehltag: wert && wert !== aktiv.stichtag ? wert : null });
      setAktiv(data.lauf);
      setZaehltagEntwurf(null);
      await positionenLaden(aktiv.id);
    } catch (e) {
      setFehler(fehlerText(e));
    } finally {
      setArbeitet(null);
    }
  };

  const bewertungLoeschen = async (pos) => {
    try {
      const { data } = await api.delete(`/api/inventur/positionen/${pos.id}/bewertung`);
      setPositionen(prev => prev.map(p => p.id === pos.id ? data.position : p));
      setAktiv(data.lauf);
    } catch (err) {
      setFehler(fehlerText(err));
    }
  };

  const abschliessen = async () => {
    setArbeitet("abschliessen");
    try {
      const { data } = await api.post(`/api/inventur/laeufe/${aktiv.id}/abschliessen`);
      setAktiv(data);
      await positionenLaden(aktiv.id);
      await laeufeLaden();
    } catch (e) {
      setFehler(fehlerText(e));
    } finally {
      setArbeitet(null);
    }
  };

  const oeffnen = async () => {
    try {
      const { data } = await api.post(`/api/inventur/laeufe/${aktiv.id}/oeffnen`);
      setAktiv(data);
      await laeufeLaden();
    } catch (e) { setFehler(fehlerText(e)); }
  };

  const loeschen = async (lauf) => {
    try {
      await api.delete(`/api/inventur/laeufe/${lauf.id}`);
      if (aktiv?.id === lauf.id) { setAktiv(null); setPositionen([]); }
      await laeufeLaden();
    } catch (e) { setFehler(fehlerText(e)); }
  };

  // Rückfragen vor Schritten, die sich nicht zurücknehmen lassen. Sie nennen die
  // Folgen in Zahlen – ein bloßes „Wirklich?" klickt jeder weg.
  const bewertete = positionen.filter(p => p.bewertung_art).length;
  const offeneVorschlaege = positionen.filter(p => p.vorschlag).length;
  const kopfzeile = () => `${aktiv.name} · Stichtag ${datum(aktiv.stichtag)}`;

  const abschliessenFragen = () => setFrage({
    titel: "Inventur abschließen",
    label: "Abschließen",
    aktion: abschliessen,
    punkte: [
      kopfzeile(),
      `Wert zum EK ${eur(aktiv.bestand_wert)} · Abwertung ${eur(aktiv.abwertung_summe)} · `
        + `Wert nach Abwertung ${eur(aktiv.wert_nach_abwertung)}`,
      offeneVorschlaege > 0
        ? `${zahl(offeneVorschlaege)} offene Vorschläge gelten damit als bestätigt – mit deinem Namen.`
        : "Es gibt keine offenen Vorschläge.",
      `Gezählt: ${zahl(aktiv.gezaehlte_positionen)} von ${zahl(aktiv.positionen_anzahl)} Positionen `
        + `(ungezählte mit der Buchmenge) · Inventurdifferenz ${eur(aktiv.differenz_wert)}`,
      aktiv.abweichungen_ohne_grund > 0
        ? `${zahl(aktiv.abweichungen_ohne_grund)} Abweichungen haben noch keinen Grund – der `
          + "Abschluss wird abgelehnt, bis jede einen hat."
        : null,
      "Danach sind Bewertungen, Staffel und neues Einlesen gesperrt, Löschen ebenfalls. "
        + "Ansehen und Export bleiben möglich.",
    ],
  });

  const befuellenFragen = () => {
    // Ohne Bewertungen geht nichts verloren – dann keine Rückfrage.
    if (!bewertete) return befuellen(aktiv.id);
    setFrage({
      titel: "Bestände neu einlesen",
      label: "Neu einlesen",
      gefahr: true,
      aktion: () => befuellen(aktiv.id),
      punkte: [
        `Liest die Bestände zum Stichtag ${datum(aktiv.stichtag)} neu aus der Wawi.`,
        `${zahl(bewertete)} Bewertungen mit zusammen ${eur(aktiv.abwertung_summe)} Abwertung `
          + "gehen dabei verloren.",
        "Die Staffel bleibt: „Abwertung vorschlagen“ stellt Staffel-Bewertungen danach wieder "
          + "her, von Hand eingetragene nicht.",
        "Gezählte Mengen, Gründe und Notizen bleiben erhalten.",
      ],
    });
  };

  const loeschenFragen = () => setFrage({
    titel: "Inventur löschen",
    label: "Endgültig löschen",
    gefahr: true,
    aktion: () => loeschen(aktiv),
    punkte: [
      kopfzeile(),
      `${zahl(positionen.length)} Positionen und ${zahl(bewertete)} Bewertungen werden gelöscht.`,
      "Das lässt sich nicht rückgängig machen.",
    ],
  });

  const oeffnenFragen = () => setFrage({
    titel: "Inventur wieder öffnen",
    label: "Wieder öffnen",
    gefahr: true,
    aktion: oeffnen,
    punkte: [
      `Abgeschlossen am ${datum(aktiv.abgeschlossen_am)}`
        + (aktiv.abgeschlossen_von ? ` von ${aktiv.abgeschlossen_von}` : "") + ".",
      "Danach sind Bewertungen wieder änderbar. Das Öffnen steht im Verlauf der Inventur "
        + "und im Excel-Info-Blatt.",
      "Nur für den Irrtumsfall – eine abgegebene Inventur sollte abgeschlossen bleiben.",
    ],
  });

  // Der Export läuft über einen Blob, weil die API mit Anmeldung geschützt ist –
  // ein einfacher Link würde ohne Kopfzeile gehen und 401 liefern.
  const exportieren = async (format) => {
    try {
      const res = await api.get(`/api/inventur/laeufe/${aktiv.id}/export.${format}`,
                                { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = `Inventur_${aktiv.stichtag}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) { setFehler(fehlerText(e)); }
  };

  const offen = aktiv && aktiv.status !== "abgeschlossen";
  const gefiltert = positionen.filter(p => {
    if (nurBewertet && !p.bewertung_art) return false;
    // Die Frage des Kunden lautet „was ist abgelaufen?" – nicht „was hat ein
    // MHD?". Deshalb hängt der Filter an der abgelaufenen MENGE, nicht daran,
    // ob die Position überhaupt ein MHD trägt.
    if (nurAbgelaufen && !(p.menge_abgelaufen > 0)) return false;
    if (nurAbweichung && !(p.zaehlung_ebene && Math.abs(p.differenz || 0) > 0.0005)) return false;
    if (nurUngezaehlt && p.zaehlung_ebene) return false;
    if (!suche.trim()) return true;
    const s = suche.trim().toLowerCase();
    return (p.art_nr || "").toLowerCase().includes(s)
        || (p.artikel || "").toLowerCase().includes(s);
  });
  const vorschlaege = positionen.filter(p => p.vorschlag).length;

  // Differenz + Grund einer gezählten Position. Fehlt der Grund, ist die Auswahl
  // rot umrandet – so sieht man vor dem Abschluss, was noch offen ist.
  const diffZelle = (p) => {
    if (!p.zaehlung_ebene) return <span style={{ color: S.textDim }}>–</span>;
    const d = p.differenz || 0;
    if (Math.abs(d) <= 0.0005) return <span style={{ color: "#6ec28e" }}>0</span>;
    const fehlt = !p.differenz_grund || (p.differenz_grund === "sonstiges" && !p.differenz_notiz);
    const notizKey = `n${p.id}`;
    return (
      <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
        <span style={{ color: d < 0 ? "#e07070" : "#6ec28e" }}
              title={p.differenz_wert != null ? `Differenzwert zum Stichtag ${eur(p.differenz_wert)}` : ""}>
          {d > 0 ? "+" : ""}{zahl(d, 3)}
        </span>
        {offen ? (
          <>
            <select style={{ ...inp, padding: "2px 4px", fontSize: 10.5, maxWidth: 140,
                      borderColor: fehlt ? "#e07070" : S.border }}
                    value={p.differenz_grund || ""}
                    onChange={ev => zaehlungSpeichern(p, { grund: ev.target.value || null })}>
              <option value="">Grund …</option>
              {gruende.map(g => <option key={g.id} value={g.id}>{g.label}</option>)}
            </select>
            {p.differenz_grund && (
              <input style={{ ...inp, padding: "2px 4px", fontSize: 10.5, width: 110,
                        borderColor: fehlt ? "#e07070" : S.border }}
                     placeholder={p.differenz_grund === "sonstiges" ? "Notiz (Pflicht)" : "Notiz"}
                     value={zaehlEntwurf[notizKey] ?? (p.differenz_notiz || "")}
                     onChange={ev => setZaehlEntwurf(x => ({ ...x, [notizKey]: ev.target.value }))}
                     onBlur={() => {
                       const v = zaehlEntwurf[notizKey];
                       if (v === undefined) return;
                       setZaehlEntwurf(x => { const n = { ...x }; delete n[notizKey]; return n; });
                       zaehlungSpeichern(p, { notiz: v });
                     }}
                     onKeyDown={ev => { if (ev.key === "Enter") ev.currentTarget.blur(); }} />
            )}
          </>
        ) : (
          <span style={{ fontSize: 10.5, color: S.textDim }}>
            {gruende.find(g => g.id === p.differenz_grund)?.label || p.differenz_grund || "ohne Grund"}
            {p.differenz_notiz ? ` · ${p.differenz_notiz}` : ""}
          </span>
        )}
      </span>
    );
  };

  return (
    <div style={{ padding: 14 }}>
      {fehler && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12,
          padding: "8px 10px", borderRadius: 5, backgroundColor: "rgba(224,112,112,.1)",
          border: "1px solid rgba(224,112,112,.3)", color: "#e07070", fontSize: 12 }}>
          <AlertCircle size={13} /> {fehler}
          <X size={13} style={{ marginLeft: "auto", cursor: "pointer" }}
             onClick={() => setFehler(null)} />
        </div>
      )}

      {/* ── Kopf: Lauf wählen oder anlegen ─────────────────────────────── */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
        marginBottom: 14 }}>
        <ClipboardList size={15} style={{ color: S.accent }} />
        <select
          style={{ ...inp, minWidth: 260 }}
          value={aktiv?.id || ""}
          onChange={e => {
            const id = Number(e.target.value);
            if (!id) { setAktiv(null); setPositionen([]); return; }
            positionenLaden(id);
          }}>
          <option value="">— Inventur wählen —</option>
          {laeufe.map(l => (
            <option key={l.id} value={l.id}>
              {datum(l.stichtag)} · {l.name}
              {l.status === "abgeschlossen" ? " (abgeschlossen)" : ""}
            </option>
          ))}
        </select>

        <button style={btn} onClick={() => setNeuOffen(o => !o)}>
          <Plus size={13} /> Neue Inventur
        </button>

        {aktiv && offen && (
          <button style={btn} onClick={befuellenFragen}
                  disabled={arbeitet === "befuellen"}
                  title="Liest die Bestände zum Stichtag neu ein. Bereits erfasste Bewertungen gehen dabei verloren.">
            {arbeitet === "befuellen"
              ? <Loader2 size={13} className="spin" /> : <RefreshCw size={13} />}
            Bestände neu einlesen
          </button>
        )}
        {aktiv && (
          <>
            <button style={btn} onClick={() => exportieren("xlsx")}
                    title="Kopfzeile fixiert, sortier- und filterbar, Summen der sichtbaren Zeilen">
              <Download size={13} /> Liste als Excel
            </button>
            <button style={btn} onClick={() => exportieren("csv")}>
              <Download size={13} /> CSV
            </button>
          </>
        )}
        {aktiv && offen && positionen.length > 0 && (
          <button style={{ ...btn, borderColor: S.accent, color: S.accent }}
                  onClick={abschliessenFragen} disabled={arbeitet === "abschliessen"}>
            <Lock size={13} /> Inventur abschließen
          </button>
        )}
        {aktiv && !offen && (
          <button style={btn} onClick={oeffnenFragen}
                  title="Nur für den Irrtumsfall – der Abschluss bleibt vermerkt.">
            <Unlock size={13} /> Wieder öffnen
          </button>
        )}
        {aktiv && (
          <button style={{ ...btn, marginLeft: "auto", color: "#e07070",
                    opacity: offen ? 1 : 0.45, cursor: offen ? "pointer" : "not-allowed" }}
                  onClick={offen ? loeschenFragen : undefined} disabled={!offen}
                  title={offen ? "Inventur mit allen Positionen löschen"
                               : "Eine abgeschlossene Inventur ist ein Beleg und kann nicht gelöscht werden."}>
            <Trash2 size={13} /> Löschen
          </button>
        )}
      </div>

      {neuOffen && (
        <div style={{ display: "flex", alignItems: "flex-end", gap: 10, marginBottom: 14,
          padding: 12, borderRadius: 6, backgroundColor: S.bgMain,
          border: `1px solid ${S.border}` }}>
          <label style={{ fontSize: 11, color: S.textDim }}>
            Stichtag<br />
            <input type="date" style={{ ...inp, marginTop: 4 }} value={neuStichtag}
                   onChange={e => setNeuStichtag(e.target.value)} />
          </label>
          <label style={{ fontSize: 11, color: S.textDim, flex: 1 }}>
            Bezeichnung (optional)<br />
            <input style={{ ...inp, marginTop: 4, width: "100%" }} value={neuName}
                   placeholder="z. B. Jahresinventur 2026"
                   onChange={e => setNeuName(e.target.value)} />
          </label>
          <button style={{ ...btn, borderColor: S.accent, color: S.accent }}
                  onClick={anlegen} disabled={arbeitet !== null}>
            {arbeitet ? <Loader2 size={13} className="spin" /> : <Check size={13} />}
            Anlegen und Bestände einlesen
          </button>
        </div>
      )}

      {laden && <p style={{ fontSize: 12, color: S.textDim }}>Lade …</p>}

      {!laden && !aktiv && (
        <p style={{ fontSize: 12, color: S.textDim, lineHeight: 1.6 }}>
          Noch keine Inventur ausgewählt. „Neue Inventur“ legt eine an und liest
          die Bestände zum gewählten Stichtag ein – mit Einkaufspreis, MHD,
          Restlaufzeit und Abverkaufsdauer je Artikel.
        </p>
      )}

      {aktiv && (
        <>
          {/* ── Summen ─────────────────────────────────────────────────── */}
          <div style={{ display: "flex", gap: 20, flexWrap: "wrap", marginBottom: 12,
            padding: "10px 14px", borderRadius: 6, backgroundColor: S.bgMain,
            border: `1px solid ${S.border}` }}>
            {[["Positionen", zahl(aktiv.positionen_anzahl)],
              ["Bestandswert zum EK", eur(aktiv.bestand_wert)],
              ["Abwertung", eur(aktiv.abwertung_summe)],
              ["Wert nach Abwertung", eur(aktiv.wert_nach_abwertung)],
              ["bewertet", `${zahl(aktiv.bewertete_positionen)} von ${zahl(aktiv.positionen_anzahl)}`],
              ["gezählt", `${zahl(aktiv.gezaehlte_positionen)} von ${zahl(aktiv.positionen_anzahl)}`],
              ["Inventurdifferenz", eur(aktiv.differenz_wert)],
            ].map(([label, wert]) => (
              <div key={label}>
                <div style={{ fontSize: 10, color: S.textDim, textTransform: "uppercase",
                  letterSpacing: .4 }}>{label}</div>
                <div style={{ fontSize: 15, color: S.textBright, fontWeight: 600 }}>{wert}</div>
              </div>
            ))}
            {!offen && (
              <div style={{ marginLeft: "auto", display: "flex", alignItems: "center",
                gap: 6, fontSize: 11, color: S.accent }}>
                <Lock size={12} /> abgeschlossen am {datum(aktiv.abgeschlossen_am)}
                {aktiv.abgeschlossen_von ? ` von ${aktiv.abgeschlossen_von}` : ""}
              </div>
            )}
            {/* War schon einmal abgeschlossen: das soll man der offenen Inventur ansehen. */}
            {offen && (() => {
              const w = [...(aktiv.protokoll || [])].reverse()
                .find(e => e.aktion === "wieder_geoeffnet");
              return w ? (
                <div style={{ marginLeft: "auto", display: "flex", alignItems: "center",
                  gap: 6, fontSize: 11, color: "#e0b070" }}
                  title="Die Inventur war schon abgeschlossen und wurde wieder geöffnet – das steht im Verlauf und im Excel-Info-Blatt.">
                  <Unlock size={12} /> wieder geöffnet am {datum(w.am)}
                  {w.von ? ` von ${w.von}` : ""}
                </div>
              ) : null;
            })()}
          </div>

          {/* ── Zählung: Zähltag und offene Gründe ────────────────────────── */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
            marginBottom: 12, fontSize: 11, color: S.textDim }}>
            <label style={{ display: "flex", alignItems: "center", gap: 6 }}
                   title="Tag, an dem physisch gezählt wird. Liegt er neben dem Stichtag, zeigt „Soll“ die Buchmenge dieses Tages, und die Differenz wird auf den Stichtag zurückgerechnet.">
              Zähltag
              <input type="date" style={{ ...inp, padding: "3px 6px" }} max={heuteISO()}
                     value={zaehltagEntwurf ?? (aktiv.zaehltag || aktiv.stichtag)}
                     disabled={!offen || arbeitet === "zaehltag"}
                     onChange={e => setZaehltagEntwurf(e.target.value)} />
            </label>
            {offen && zaehltagEntwurf && zaehltagEntwurf !== (aktiv.zaehltag || aktiv.stichtag) && (
              <button style={{ ...btn, padding: "3px 9px", borderColor: S.accent, color: S.accent }}
                      onClick={() => zaehltagSetzen(zaehltagEntwurf)} disabled={arbeitet !== null}>
                {arbeitet === "zaehltag" ? <Loader2 size={12} className="spin" /> : <Check size={12} />}
                übernehmen
              </button>
            )}
            <span>
              {arbeitet === "zaehltag"
                ? "Buchmengen am Zähltag werden aus der Wawi geladen …"
                : aktiv.zaehltag
                  ? `Soll = Buchmenge am ${datum(aktiv.zaehltag)}; Differenzen werden auf den Stichtag ${datum(aktiv.stichtag)} zurückgerechnet.`
                  : "Gezählt wird am Stichtag. Leeres Ist = nicht gezählt, dann gilt Soll."}
            </span>
            {aktiv.abweichungen_ohne_grund > 0 && (
              <span style={{ marginLeft: "auto", color: "#e07070", display: "inline-flex",
                alignItems: "center", gap: 4 }}>
                <AlertCircle size={12} /> {zahl(aktiv.abweichungen_ohne_grund)} Abweichungen ohne Grund
                – so lässt sich nicht abschließen
              </span>
            )}
          </div>

          {/* Prüfhinweise: was beim Einlesen aufgefallen ist. */}
          {(aktiv.hinweise || []).length > 0 && (
            <div style={{ marginBottom: 12, padding: "8px 12px", borderRadius: 5,
              backgroundColor: "rgba(224,176,112,.08)",
              border: "1px solid rgba(224,176,112,.25)", fontSize: 11,
              color: S.textMain, lineHeight: 1.6 }}>
              {aktiv.hinweise.map((h, i) => <div key={i}>· {h.text}</div>)}
            </div>
          )}

          {/* ── Werkzeugleiste ─────────────────────────────────────────── */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10,
            flexWrap: "wrap" }}>
            <div style={{ position: "relative" }}>
              <Search size={12} style={{ position: "absolute", left: 8, top: 8,
                color: S.textDim }} />
              <input style={{ ...inp, paddingLeft: 24, width: 200 }} value={suche}
                     placeholder="Artikel suchen …"
                     onChange={e => setSuche(e.target.value)} />
            </div>
            <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11,
              color: S.textDim, cursor: "pointer" }}>
              <input type="checkbox" checked={nurBewertet}
                     onChange={e => setNurBewertet(e.target.checked)} />
              nur bewertete
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11,
              color: S.textDim, cursor: "pointer" }}
              title="Zeigt nur Positionen, bei denen am Stichtag mindestens eine Charge über dem MHD war.">
              <input type="checkbox" checked={nurAbgelaufen}
                     onChange={e => setNurAbgelaufen(e.target.checked)} />
              nur mit abgelaufenen Chargen
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11,
              color: S.textDim, cursor: "pointer" }}>
              <input type="checkbox" checked={nurAbweichung}
                     onChange={e => setNurAbweichung(e.target.checked)} />
              nur Abweichungen
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11,
              color: S.textDim, cursor: "pointer" }}>
              <input type="checkbox" checked={nurUngezaehlt}
                     onChange={e => setNurUngezaehlt(e.target.checked)} />
              nur ungezählte
            </label>
            <button style={btn} onClick={() => setStufenOffen(true)}
                    title={"Ab wann wie viel abgewertet wird: "
                      + stufen.map(s => `${s.label} ${Number(s.prozent)} %`).join(" · ")}>
              <SlidersHorizontal size={13} /> Staffel
            </button>
            {offen && (
              <button style={btn} onClick={vorschlagen} disabled={arbeitet !== null}
                      title="Wertet abgelaufene und bald ablaufende Chargen nach Stufen ab – jede Zeile bleibt änderbar.">
                {arbeitet === "vorschlag"
                  ? <Loader2 size={13} className="spin" /> : <Wand2 size={13} />}
                Abwertung vorschlagen
              </button>
            )}
            {offen && vorschlaege > 0 && (
              <button style={{ ...btn, borderColor: S.accent, color: S.accent }}
                      onClick={bestaetigen} disabled={arbeitet !== null}>
                <Check size={13} /> {vorschlaege} Vorschläge übernehmen
              </button>
            )}
            <span style={{ marginLeft: "auto", fontSize: 11, color: S.textDim }}>
              {zahl(gefiltert.length)} von {zahl(positionen.length)} Positionen
            </span>
          </div>

          {/* ── Positionsliste ─────────────────────────────────────────── */}
          <div style={{ overflowX: "auto", border: `1px solid ${S.border}`,
            borderRadius: 6 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr style={{ backgroundColor: S.bgMain }}>
                  {["", "Artikel", "Soll", "Ist", "Diff.", "EK", "Wert", "MHD", "Rest",
                    "Abgang 12M", "Reichw.", "Bewertung", "Abwertung", "neuer Wert", ""]
                    .map((h, i) => (
                    <th key={i} style={{ padding: "7px 9px", textAlign: i >= 2 && i <= 10 ? "right" : "left",
                      color: S.textDim, fontWeight: 500, fontSize: 10,
                      textTransform: "uppercase", letterSpacing: .3,
                      borderBottom: `1px solid ${S.border}`, whiteSpace: "nowrap" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {gefiltert.map(p => {
                  const e = entwurf[p.id] || {};
                  const hatAbgelaufen = (p.wert_abgelaufen || 0) > 0;
                  // Wo abgelaufene Ware liegt, ist der Bezug auf sie die
                  // richtige Vorauswahl – sonst schreibt ein „100 %" die noch
                  // haltbaren Chargen mit ab. Ohne abgelaufene Ware wäre die
                  // Art sinnlos (Bezugswert 0) und steht deshalb nicht zur Wahl.
                  const arten = hatAbgelaufen
                    ? BEWERTUNGSARTEN
                    : BEWERTUNGSARTEN.filter(a => a.id !== "prozent_abgelaufen");
                  const art = e.art || p.bewertung_art
                    || (hatAbgelaufen ? "prozent_abgelaufen" : "prozent");
                  const einheit = BEWERTUNGSARTEN.find(a => a.id === art)?.einheit || "";
                  return (
                    <Fragment key={p.id}>
                      <tr style={{ borderBottom: `1px solid ${S.border}` }}>
                        <td style={{ padding: "5px 6px" }}>
                          {(p.chargen || []).length > 0 && (
                            <span style={{ cursor: "pointer", color: S.textDim }}
                                  onClick={() => setDetail(d => ({ ...d, [p.id]: !d[p.id] }))}>
                              {detail[p.id] ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                            </span>
                          )}
                        </td>
                        <td style={{ padding: "5px 9px", maxWidth: 290 }}>
                          <div style={{ color: S.textBright }}>{p.artikel || "—"}</div>
                          <div style={{ fontSize: 10, color: S.textDim }}>{p.art_nr}</div>
                        </td>
                        <td style={{ padding: "5px 9px", textAlign: "right", color: S.textDim }}
                            title={aktiv.zaehltag
                              ? `Buchmenge am Zähltag ${datum(aktiv.zaehltag)} (zum Stichtag: ${zahl(p.bestand_soll, 3)})`
                              : "Buchmenge zum Stichtag"}>
                          {zahl(p.soll_zaehltag ?? p.bestand_soll, 3)}
                        </td>
                        <td style={{ padding: "5px 9px", textAlign: "right" }}>
                          {offen && p.zaehlung_ebene !== "charge" ? (
                            <input style={{ ...inp, width: 70, padding: "3px 5px", fontSize: 11,
                                      textAlign: "right",
                                      borderColor: p.zaehlung_ebene ? S.accent : S.border }}
                                   value={zaehlEntwurf[p.id] ?? (p.ist_gezaehlt === null
                                     || p.ist_gezaehlt === undefined ? "" : zahl(p.ist_gezaehlt, 3))}
                                   placeholder="–"
                                   title="Gezählte Menge. Leer = nicht gezählt, dann gilt Soll."
                                   onChange={ev => setZaehlEntwurf(d => ({ ...d, [p.id]: ev.target.value }))}
                                   onBlur={() => zaehlungUebernehmen(p, p.id, wert => ({ ist: wert }))}
                                   onKeyDown={ev => { if (ev.key === "Enter") ev.currentTarget.blur(); }} />
                          ) : (
                            <span style={{ color: p.zaehlung_ebene ? S.textBright : S.textDim }}
                                  title={p.zaehlung_ebene === "charge"
                                    ? "Summe der je Charge gezählten Mengen (ungezählte Chargen mit Soll)" : ""}>
                              {p.zaehlung_ebene ? zahl(p.ist_gezaehlt, 3) : "–"}
                              {p.zaehlung_ebene === "charge" && (
                                <span style={{ fontSize: 9, color: S.textDim }}> je Ch.</span>
                              )}
                            </span>
                          )}
                        </td>
                        <td style={{ padding: "5px 9px", textAlign: "right", whiteSpace: "nowrap" }}>
                          {diffZelle(p)}
                        </td>
                        <td style={{ padding: "5px 9px", textAlign: "right" }}>{eur(p.ek)}</td>
                        <td style={{ padding: "5px 9px", textAlign: "right",
                          color: S.textBright }}>{eur(p.wert)}</td>
                        <td style={{ padding: "5px 9px" }}>{p.mhd ? datum(p.mhd) : "–"}</td>
                        <td style={{ padding: "5px 9px", textAlign: "right",
                          color: restFarbe(p.resttage) }}>
                          {p.resttage === null || p.resttage === undefined
                            ? "–" : `${zahl(p.resttage)} T`}
                        </td>
                        <td style={{ padding: "5px 9px", textAlign: "right" }}>{zahl(p.abgang_12m)}</td>
                        <td style={{ padding: "5px 9px", textAlign: "right" }}>
                          {p.reichweite_tage ? `${zahl(p.reichweite_tage)} T` : "–"}
                        </td>
                        <td style={{ padding: "5px 9px", whiteSpace: "nowrap" }}>
                          {offen ? (
                            <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
                              <select style={{ ...inp, padding: "3px 5px", fontSize: 11 }}
                                      value={art}
                                      onChange={ev => setEntwurf(d => ({ ...d,
                                        [p.id]: { ...e, art: ev.target.value,
                                                  wert: e.wert ?? p.bewertung_wert ?? "" } }))}>
                                {arten.map(a =>
                                  <option key={a.id} value={a.id}>{a.label}</option>)}
                              </select>
                              <input style={{ ...inp, width: 62, padding: "3px 5px", fontSize: 11,
                                        textAlign: "right" }}
                                     value={e.wert ?? (p.bewertung_wert === null
                                              || p.bewertung_wert === undefined
                                              ? "" : zahl(p.bewertung_wert, 2))}
                                     placeholder={einheit}
                                     onChange={ev => setEntwurf(d => ({ ...d,
                                       [p.id]: { ...e, art, wert: ev.target.value } }))}
                                     onBlur={() => bewerten(p)}
                                     onKeyDown={ev => { if (ev.key === "Enter") ev.currentTarget.blur(); }} />
                            </span>
                          ) : (
                            <span style={{ color: S.textDim, fontSize: 11 }}
                                  title={BEWERTUNGSARTEN.find(a => a.id === p.bewertung_art)?.label || ""}>
                              {p.bewertung_art
                                ? `${zahl(p.bewertung_wert, 2)} ${BEWERTUNGSARTEN.find(a => a.id === p.bewertung_art)?.einheit || ""}`
                                  + (p.bewertung_art === "prozent_abgelaufen" ? " auf abgel." : "")
                                : "–"}
                            </span>
                          )}
                        </td>
                        <td style={{ padding: "5px 9px", textAlign: "right",
                          color: p.abwertung_betrag > 0 ? "#e07070" : S.textDim }}>
                          {p.abwertung_betrag > 0 ? `− ${eur(p.abwertung_betrag)}` : "–"}
                          {p.vorschlag && (
                            <span style={{ marginLeft: 5, fontSize: 9, color: "#e0b070",
                              border: "1px solid rgba(224,176,112,.4)", borderRadius: 3,
                              padding: "0 3px" }}>Vorschlag</span>
                          )}
                          {!p.vorschlag && p.bewertung_art && p.bewertung_quelle === "staffel" && (
                            <span title="Aus der Staffel übernommen – eine geänderte Staffel rechnet sie neu."
                              style={{ marginLeft: 5, fontSize: 9, color: S.textDim,
                              border: `1px solid ${S.border}`, borderRadius: 3,
                              padding: "0 3px" }}>Staffel</span>
                          )}
                        </td>
                        <td style={{ padding: "5px 9px", textAlign: "right",
                          color: S.textBright }}>{eur(p.wert_neu)}</td>
                        <td style={{ padding: "5px 6px" }}>
                          {offen && p.bewertung_art && (
                            <X size={12} style={{ cursor: "pointer", color: S.textDim }}
                               onClick={() => bewertungLoeschen(p)} />
                          )}
                        </td>
                      </tr>
                      {detail[p.id] && (
                        <tr style={{ backgroundColor: S.bgMain }}>
                          <td colSpan={15} style={{ padding: "8px 34px" }}>
                            {p.grund && (
                              <div style={{ fontSize: 11, color: S.textDim, marginBottom: 6 }}>
                                Begründung: {p.grund}
                              </div>
                            )}
                            {/* Woran die Abwertung hängt, muss an der Partie
                                stehen – sonst rät man, worauf sich ein Prozent
                                bezieht. */}
                            {(p.wert_abgelaufen || 0) > 0 && (
                              <div style={{ fontSize: 11, marginBottom: 6, color: S.textMain }}>
                                davon abgelaufen: <b style={{ color: "#e07070" }}>
                                  {zahl(p.menge_abgelaufen)} Stück · {eur(p.wert_abgelaufen)}
                                </b>
                                <span style={{ color: S.textDim }}>
                                  {"  ·  noch haltbar: "}
                                  {zahl((p.bestand || 0) - (p.menge_abgelaufen || 0))} Stück ·{" "}
                                  {eur((p.wert || 0) - (p.wert_abgelaufen || 0))}
                                </span>
                              </div>
                            )}
                            <table style={{ borderCollapse: "collapse", fontSize: 11 }}>
                              <thead>
                                <tr style={{ color: S.textDim }}>
                                  {["Charge", "MHD", "Rest", "Soll", "Ist", "EK", "Wert",
                                    "Vorschlag", ""].map((h, i) => (
                                    <th key={i} style={{ padding: "3px 12px 3px 0",
                                      textAlign: i <= 1 ? "left" : i >= 7 ? "left" : "right",
                                      fontWeight: 500, whiteSpace: "nowrap" }}>{h}</th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {(p.chargen || []).map((c, i) => {
                                  const rest = resttage(c.mhd, aktiv.stichtag);
                                  const st = stufeFuer(rest, stufen);
                                  return (
                                  <tr key={i} style={{ color: restFarbe(rest) }}>
                                    <td style={{ padding: "3px 12px 3px 0" }}>{c.charge || "–"}</td>
                                    <td style={{ padding: "3px 12px 3px 0" }}>{c.mhd || "–"}</td>
                                    <td style={{ padding: "3px 12px 3px 0", textAlign: "right" }}>
                                      {rest === null ? "–" : `${zahl(rest)} T`}
                                    </td>
                                    <td style={{ padding: "3px 12px 3px 0", textAlign: "right", color: S.textDim }}>
                                      {zahl(c.soll_zaehltag ?? c.menge_soll ?? c.menge, 3)}
                                      {c.nach_stichtag && (
                                        <span title="Nach dem Stichtag eingelagert – wird mitgezählt, gehört aber nicht zum Stichtagsbestand."
                                              style={{ fontSize: 9, marginLeft: 4 }}>neu</span>
                                      )}
                                    </td>
                                    <td style={{ padding: "3px 12px 3px 0", textAlign: "right", whiteSpace: "nowrap" }}
                                        title={p.zaehlung_ebene === "artikel"
                                          ? "Die Position ist je Artikel gezählt – erst das Ist oben leeren, um je Charge zu zählen." : ""}>
                                      {offen && p.zaehlung_ebene !== "artikel" ? (
                                        <input style={{ ...inp, width: 64, padding: "2px 5px", fontSize: 11,
                                                  textAlign: "right",
                                                  borderColor: c.ist != null ? S.accent : S.border }}
                                               value={zaehlEntwurf[`${p.id}:${i}`]
                                                 ?? (c.ist == null ? "" : zahl(c.ist, 3))}
                                               placeholder="–"
                                               onChange={ev => setZaehlEntwurf(d => ({ ...d, [`${p.id}:${i}`]: ev.target.value }))}
                                               onBlur={() => zaehlungUebernehmen(p, `${p.id}:${i}`,
                                                 wert => ({ charge_index: i, charge_ist: wert }))}
                                               onKeyDown={ev => { if (ev.key === "Enter") ev.currentTarget.blur(); }} />
                                      ) : (c.ist != null ? zahl(c.ist, 3) : "–")}
                                      {c.differenz != null && Math.abs(c.differenz) > 0.0005 && (
                                        <span style={{ marginLeft: 4, fontSize: 10,
                                          color: c.differenz < 0 ? "#e07070" : "#6ec28e" }}>
                                          {c.differenz > 0 ? "+" : ""}{zahl(c.differenz, 3)}
                                        </span>
                                      )}
                                    </td>
                                    <td style={{ padding: "3px 12px 3px 0", textAlign: "right" }}>{eur(c.ek)}</td>
                                    <td style={{ padding: "3px 12px 3px 0", textAlign: "right" }}>
                                      {/* exakt summiert aus der Abfrage – Menge × EK
                                          wäre um die Rundung des EK daneben */}
                                      {eur(c.wert ?? (c.menge || 0) * (c.ek || 0))}
                                    </td>
                                    {/* Was „Abwertung vorschlagen" mit genau dieser
                                        Partie macht. Leer heißt: bleibt unangetastet. */}
                                    <td style={{ padding: "3px 12px 3px 0", whiteSpace: "nowrap" }}>
                                      {st ? `${st.label} · ${Number(st.prozent)} %` : ""}
                                    </td>
                                    {/* JTL legt je Wareneingang einen Satz an, auch bei
                                        gleicher Charge. Die Zeile ist zusammengefasst –
                                        die Zahl sagt, aus wie vielen Einlagerungen. */}
                                    <td style={{ padding: "3px 12px 3px 0", textAlign: "right",
                                      color: S.textDim }}>
                                      {(c.einlagerungen || 1) > 1
                                        ? `${zahl(c.einlagerungen)} Einlagerungen` : ""}
                                    </td>
                                  </tr>
                                  );
                                })}
                                {p.menge_ohne_partie > 0 && (
                                  <tr style={{ color: S.textDim }}>
                                    <td style={{ padding: "3px 12px 3px 0" }}>ohne Chargenzuordnung</td>
                                    <td>–</td>
                                    <td />
                                    <td style={{ padding: "3px 12px 3px 0", textAlign: "right" }}>
                                      {zahl(p.menge_ohne_partie)}</td>
                                    <td colSpan={5} />
                                  </tr>
                                )}
                              </tbody>
                            </table>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
                {gefiltert.length === 0 && (
                  <tr><td colSpan={15} style={{ padding: 16, textAlign: "center",
                    color: S.textDim, fontSize: 12 }}>
                    {positionen.length === 0
                      ? "Noch keine Positionen – „Bestände neu einlesen“ füllt die Liste."
                      : "Kein Treffer."}
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {frage && (
        <BestaetigenModal titel={frage.titel} punkte={frage.punkte} label={frage.label}
                          gefahr={frage.gefahr} onBestaetigen={frage.aktion}
                          onClose={() => setFrage(null)} />
      )}

      {stufenOffen && aktiv && (
        <InventurStufenModal
          stufen={stufen}
          standard={standardStufen}
          gesperrt={!offen}
          vorschau={stufenVorschau}
          onClose={() => setStufenOffen(false)}
          onSave={stufenSpeichern}
        />
      )}
    </div>
  );
}
