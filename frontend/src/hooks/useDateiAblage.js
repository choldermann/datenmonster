import { useCallback, useEffect, useState } from "react";

/** Datei per Ziehen-und-Ablegen entgegennehmen.
 *
 *  Ohne `preventDefault` im dragover-Ereignis lehnt der Browser jede Ablage ab —
 *  eine Flaeche, die "Datei hierher ziehen" verspricht, tut dann schlicht nichts.
 *  Deshalb liefert dieser Haken die vier Ereignisse fertig verdrahtet.
 *
 *  Nebenher haengt er einen Schutz ans Fenster: faellt die Datei NEBEN die
 *  Flaeche, wuerde Chrome sie im selben Tab oeffnen — die Anwendung waere weg,
 *  samt allem, was gerade halb ausgefuellt in der Maske steht.
 *
 *  @param annehmen  Rueckruf, bekommt die abgelegte Datei
 *  @param endungen  erlaubte Endungen, z. B. [".pdf", ".xml"] (leer = alle)
 *  @param abgelehnt Rueckruf fuer eine Datei mit falscher Endung (bekommt einen Satz)
 *  @returns { ueberDerFlaeche, ablageProps }
 */
export function useDateiAblage(annehmen, endungen = [], abgelehnt) {
  const [ueberDerFlaeche, setUeber] = useState(false);

  useEffect(() => {
    const abfangen = (e) => e.preventDefault();
    window.addEventListener("dragover", abfangen);
    window.addEventListener("drop", abfangen);
    return () => {
      window.removeEventListener("dragover", abfangen);
      window.removeEventListener("drop", abfangen);
    };
  }, []);

  const passt = useCallback((datei) => {
    if (!endungen.length) return true;
    const name = (datei?.name || "").toLowerCase();
    return endungen.some((e) => name.endsWith(e.toLowerCase()));
  }, [endungen]);

  const ablageProps = {
    onDragEnter: (e) => { e.preventDefault(); e.stopPropagation(); setUeber(true); },
    onDragOver: (e) => {
      e.preventDefault(); e.stopPropagation();
      if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
      setUeber(true);
    },
    // dragleave feuert auch beim Wechsel auf ein Kindelement – der Test auf
    // currentTarget verhindert, dass die Markierung dabei flackert.
    onDragLeave: (e) => {
      e.preventDefault(); e.stopPropagation();
      if (!e.currentTarget.contains(e.relatedTarget)) setUeber(false);
    },
    onDrop: (e) => {
      e.preventDefault(); e.stopPropagation();
      setUeber(false);
      const datei = e.dataTransfer?.files?.[0];
      if (!datei) return;
      if (!passt(datei)) {
        abgelehnt?.(`${datei.name} passt nicht – erwartet wird ${endungen.join(" oder ")}.`);
        return;
      }
      annehmen(datei);
    },
  };

  return { ueberDerFlaeche, ablageProps };
}

export default useDateiAblage;
