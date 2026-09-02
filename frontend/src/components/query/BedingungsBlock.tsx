import { Plus, X, CornerDownRight } from "lucide-react";
import { S } from "../dashboard/constants";

/**
 * Rekursiver UND/ODER-Baum. Wird zweimal verwendet: einmal für Zeilenfilter
 * (Felder), einmal für Kennzahlfilter (Kennzahlen). Der Unterschied steckt
 * allein in der Liste, die als `felder` hereinkommt.
 *
 * Ein Knoten ist entweder
 *   { op: "UND" | "ODER", kinder: [...] }
 * oder
 *   { key, vergleich, wert }
 */

const feldStil = {
  padding: "5px 8px", borderRadius: 5, fontSize: 11.5,
  backgroundColor: S.bgMain, border: `1px solid ${S.border}`, color: S.textMain,
};

const leereBedingung = (felder) => ({
  key: felder[0]?.key || "", vergleich: "", wert: "",
});

export default function BedingungsBlock({
  knoten, felder, vergleiche, ohneWert, zweiWerte, liste, onChange, tiefe = 0,
}) {
  if (!knoten) return null;
  const istGruppe = "op" in knoten;

  // ── Einzelbedingung ──
  if (!istGruppe) {
    const feld = felder.find((f) => f.key === knoten.key);
    const moeglich = vergleiche[feld?.typ] || [];
    const vergleich = knoten.vergleich || moeglich[0]?.key || "=";
    const brauchtWert = !ohneWert.includes(vergleich);
    const istZwei = zweiWerte.includes(vergleich);
    const istListe = liste.includes(vergleich);

    return (
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
        <select value={knoten.key}
          onChange={(e) => {
            const neu = felder.find((f) => f.key === e.target.value);
            const ersterVergleich = (vergleiche[neu?.typ] || [])[0]?.key || "=";
            onChange({ key: e.target.value, vergleich: ersterVergleich, wert: "" });
          }}
          style={{ ...feldStil, minWidth: 170 }}>
          {felder.map((f) => (
            <option key={f.key} value={f.key}>{f.label}</option>
          ))}
        </select>

        <select value={vergleich}
          onChange={(e) => onChange({ ...knoten, vergleich: e.target.value, wert: "" })}
          style={{ ...feldStil, minWidth: 110 }}>
          {moeglich.map((v) => <option key={v.key} value={v.key}>{v.label}</option>)}
        </select>

        {brauchtWert && !istZwei && (
          <input
            value={Array.isArray(knoten.wert) ? knoten.wert.join(", ") : (knoten.wert ?? "")}
            onChange={(e) => onChange({ ...knoten,
              wert: istListe
                ? e.target.value.split(",").map((s) => s.trim()).filter(Boolean)
                : e.target.value })}
            placeholder={istListe ? "Werte mit Komma trennen" : "Wert"}
            type={feld?.typ === "datum" ? "date" : "text"}
            style={{ ...feldStil, minWidth: istListe ? 220 : 130 }} />
        )}

        {istZwei && (
          <>
            <input value={(knoten.wert || [])[0] ?? ""} placeholder="von"
              type={feld?.typ === "datum" ? "date" : "text"}
              onChange={(e) => onChange({ ...knoten,
                wert: [e.target.value, (knoten.wert || [])[1] ?? ""] })}
              style={{ ...feldStil, width: 120 }} />
            <span style={{ fontSize: 11, color: S.textDim }}>bis</span>
            <input value={(knoten.wert || [])[1] ?? ""} placeholder="bis"
              type={feld?.typ === "datum" ? "date" : "text"}
              onChange={(e) => onChange({ ...knoten,
                wert: [(knoten.wert || [])[0] ?? "", e.target.value] })}
              style={{ ...feldStil, width: 120 }} />
          </>
        )}

        {feld?.hinweis && (
          <span title={feld.hinweis} style={{ fontSize: 10.5, color: S.textDim,
            cursor: "help" }}>ⓘ</span>
        )}
      </div>
    );
  }

  // ── Gruppe ──
  const kinder = knoten.kinder || [];
  const setzeKind = (i, wert) => {
    const neu = [...kinder];
    if (wert === null) neu.splice(i, 1); else neu[i] = wert;
    onChange({ ...knoten, kinder: neu });
  };

  return (
    <div style={{
      border: `1px solid ${tiefe === 0 ? "transparent" : S.border}`,
      borderRadius: 6, padding: tiefe === 0 ? 0 : "10px 12px",
      backgroundColor: tiefe === 0 ? "transparent" : "rgba(255,255,255,0.02)",
      display: "flex", flexDirection: "column", gap: 8,
    }}>
      {kinder.map((kind, i) => (
        <div key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
          {/* Der Verknüpfer steht ZWISCHEN den Zeilen, nicht vor der ersten –
              sonst liest sich „UND Kunde = X" wie ein angefangener Satz. */}
          <div style={{ width: 62, flexShrink: 0, paddingTop: 4 }}>
            {i === 0 ? (
              <span style={{ fontSize: 10.5, color: S.textDim }}>Wenn</span>
            ) : i === 1 ? (
              <select value={knoten.op}
                onChange={(e) => onChange({ ...knoten, op: e.target.value })}
                style={{ ...feldStil, width: 62, padding: "3px 5px",
                  color: "var(--accent)", fontWeight: 600 }}>
                <option value="UND">UND</option>
                <option value="ODER">ODER</option>
              </select>
            ) : (
              <span style={{ fontSize: 11, color: "var(--accent)", fontWeight: 600,
                paddingLeft: 6 }}>{knoten.op}</span>
            )}
          </div>

          <div style={{ flex: 1, minWidth: 0 }}>
            <BedingungsBlock knoten={kind} felder={felder} vergleiche={vergleiche}
              ohneWert={ohneWert} zweiWerte={zweiWerte} liste={liste}
              tiefe={tiefe + 1} onChange={(w) => setzeKind(i, w)} />
          </div>

          <button onClick={() => setzeKind(i, null)} title="Entfernen"
            style={{ background: "none", border: "none", color: S.textDim,
              cursor: "pointer", padding: 3, flexShrink: 0 }}>
            <X size={13} />
          </button>
        </div>
      ))}

      <div style={{ display: "flex", gap: 8, paddingLeft: 70 }}>
        <button onClick={() => onChange({ ...knoten,
          kinder: [...kinder, leereBedingung(felder)] })}
          style={{ display: "flex", alignItems: "center", gap: 4, padding: "4px 9px",
            borderRadius: 5, border: `1px solid ${S.border}`, background: "none",
            color: S.textDim, cursor: "pointer", fontSize: 11 }}>
          <Plus size={11} /> Bedingung
        </button>
        {tiefe < 3 && (
          <button onClick={() => onChange({ ...knoten,
            kinder: [...kinder, { op: knoten.op === "UND" ? "ODER" : "UND",
                                  kinder: [leereBedingung(felder)] }] })}
            title="Für gemischte Verknüpfungen wie „A UND (B ODER C)“"
            style={{ display: "flex", alignItems: "center", gap: 4, padding: "4px 9px",
              borderRadius: 5, border: `1px solid ${S.border}`, background: "none",
              color: S.textDim, cursor: "pointer", fontSize: 11 }}>
            <CornerDownRight size={11} /> Klammer
          </button>
        )}
      </div>
    </div>
  );
}
