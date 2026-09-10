# Inventur und Abfluss-Analyse (Lager-Cockpit)

Zwei Reiter im Lager-Cockpit (Template `jtl_lager_cockpit` ab v1.6), entstanden
aus zwei Kundenwünschen: einen nachvollziehbaren Inventurweg statt Excel-Listen,
und die Frage „welche Mengen sind an *richtige* Kunden gegangen?".

---

## 1. Reiter „Inventur zum Stichtag"

### Was er löst
Bisher: Listen aus JTL ziehen, von Hand bewerten, an den Steuerberater schicken.
Der Warenwert in JTL bleibt unkorrigiert, und ein Jahr später ist nicht mehr
nachvollziehbar, wie die Abwertung zustande kam.

Jetzt: Bestände zum Stichtag einfrieren, gestaffelt abwerten, als dokumentierte
Liste ausgeben. Die Inventur ist ein Beleg – nach dem Abschluss unveränderlich.

### Wie der Bestand ermittelt wird
Die Auswertung heißt **„Inventur – Bestand zum Stichtag"** und ist ein normales
Mapping (im Editor lesbar und anpassbar). Sie kombiniert zwei Wege:

1. **Gesamtmenge je Artikel** – aus `dbo.tlagerbestand`, auf den Stichtag
   zurückgerechnet (minus aller Buchungen nach dem Stichtag). Nur so ist auch
   Altbestand erfasst, der vor Beginn der Buchungshistorie eingelagert wurde.
   Vaterartikel (`nIstVater = 1`) bleiben draußen – sie führen die Summe ihrer
   Varianten und würden den Bestand verdoppeln.
2. **Aufteilung nach Charge, MHD und EK** – aus `dbo.tWarenLagerEingang`,
   fortgeschrieben über `dbo.vArtikelHistorie`. Jede Historienzeile trägt
   `kWarenLagerEingang`, deshalb lässt sich jede Eingangspartie auf jeden
   Stichtag zurückrechnen.

**Verprobt** (PPS, 2026-09-07): Die Partie-Rekonstruktion trifft
`tWarenLagerEingang.fAnzahlAktuell` bei **4.773 von 4.773** Partien exakt, die
Artikelsummen `tlagerbestand` bei **676 von 676** Artikeln. Beide Wege stimmen
zum 31.12.2025 bei 663 von 673 Artikeln überein; die Differenz von 92 Stück ist
Altbestand ohne Partie und wird als Prüfhinweis ausgewiesen.

### Bewertung
- **EK je Partie**: der bei der Einlagerung gebuchte `fEKEinzel`; fehlt er,
  `tArtikel.fEKNetto`. Fehlt beides, steht die Position mit 0 € da – die
  Inventur weist das als Hinweis aus, statt es zu verschlucken.
- **Der Positionswert** ist die Summe der Partien plus der Rest zum
  Stammdaten-EK. Der angezeigte EK ist der daraus gewichtete Durchschnitt.

### Abwertung
Der Anwender bewertet je Position auf vier Arten: **% auf abgelaufene Chargen**,
**% auf Position**, **neuer Stückwert** oder **Abwertungsbetrag**. Der Betrag
ist auf den Bestandswert gedeckelt – eine Position kann auf null fallen, aber
nicht ins Negative.

> **Ein Prozentsatz braucht einen Bezug.** „% auf abgelaufene Chargen" rechnet
> nur auf den Wert der Partien, deren MHD am Stichtag vorbei war
> (`wert_abgelaufen`), „% auf Position" auf den ganzen Bestandswert. Wo es
> abgelaufene Ware gibt, ist der Bezug auf sie vorbelegt und die Begründung
> nennt ihn ausdrücklich („50 % auf 7.056 Stück abgelaufene Ware
> (31.936,11 €)"). Ohne abgelaufene Ware steht die Art nicht zur Wahl – ihr
> Bezugswert wäre 0.

„Abwertung vorschlagen" staffelt nach Restlaufzeit (Standard: abgelaufen 100 %,
unter 3 Monate 50 %, 3–6 Monate 25 %).

> **Der Vorschlag rechnet je CHARGE, nicht je Artikel.** Ein Artikel mit zehn
> Chargen hat oft eine abgelaufene und neun frische. Beispiel aus der Praxis
> (PPS, Artikel 80123): Bestandswert 45.630 €, davon abgelaufen 31.936 €. Eine
> Regel „MHD überschritten → 100 % des Positionswerts" hätte 13.694 € zu viel
> abgewertet. Die Begründung nennt deshalb die betroffenen Mengen je Stufe.

Damit man den Bezug nicht raten muss, zeigt die aufgeklappte Chargenliste je
Partie die **Restlaufzeit zum Stichtag** (abgelaufen rot, unter 3 Monate gelb)
und die **Stufe, die der Vorschlag auf sie anwenden würde**; darüber steht die
Aufteilung „davon abgelaufen / noch haltbar". Das Häkchen **„nur mit
abgelaufenen Chargen"** blendet die übrigen Positionen aus.

Vorschläge sind als solche markiert und überschreiben keine Handbewertung. Der
Abschluss bestätigt offene Vorschläge – wer abschließt, steht für die Zahlen ein.

### Abwertungsstaffel
Der Knopf **„Staffel"** öffnet ein Modal: ab welcher Restlaufzeit wie viel
abgewertet wird. Standard ist MHD überschritten 100 %, unter 3 Monaten 50 %,
3 bis 6 Monate 25 %.
* **Resttage** = MHD minus Stichtag, je Charge. Eine Charge fällt in die erste
  Stufe, deren Resttage sie nicht übersteigt. 0 heißt „am Stichtag erreicht oder
  überschritten", negative Werte „so viele Tage drüber" – damit lässt sich z.B.
  „ab 30 Tagen drüber 100 %, darunter 50 %" abbilden.
* Die **Beschriftung** entsteht aus den Zahlen (`_stufen_label`, gleiche Regel im
  Modal) und steht im Grundtext jeder vorgeschlagenen Bewertung.
* Das Modal zeigt **vor dem Speichern**, wie viele Partien jede Stufe trifft und
  wie viel Euro sie abwertet.
* Die Staffel gehört **zur Inventur** (`inventur_laeufe.abwertung_stufen`), bei
  einer abgeschlossenen ist sie nur lesbar und steht im Excel-Info-Blatt. Eine
  neue Inventur übernimmt die Staffel der letzten desselben Mandanten.
* **„Vorschläge danach neu berechnen"** (startet aus) setzt die Vorschläge nach der
  neuen Staffel und entfernt die, die sie nicht mehr trägt. Handbewertungen bleiben.
* **Herkunft je Bewertung** (`inventur_positionen.bewertung_quelle` = `staffel` |
  `hand`). Sie bleibt nach „Vorschläge übernehmen" erhalten. Neu berechnet werden
  deshalb auch übernommene Staffel-Bewertungen: ändert sich der Betrag, werden sie
  wieder zum Vorschlag (neu übernehmen), sonst bleiben sie bestätigt. Anlass
  (10.09., PPS): alle 49 Bewertungen waren übernommene Vorschläge – die Staffel
  wirkte danach gar nicht mehr, die Vorschau zeigte überall 0. Altbestand wird beim
  Start einmalig nachgetragen: Art „Abwertungsbetrag" mit Grundtext „… (x %)" = Staffel,
  alles andere = Hand.
  Mit PPS geprüft: Standard 63.842 €, „ab 30 Tagen drüber 100 %, bis dahin 50 %,
  unter 3 Monaten 20 %" 47.719 €.

### Ausgabe
Unbewertete Positionen stehen in beiden Formaten mit ihrem vollen Wert in der
Spalte „Wert nach Abwertung", damit die Summe stimmt.

**„Liste als Excel"** ist der Weg für den Steuerberater:
* Kopfzeile und die Spalten Artikelnummer/Artikel sind fixiert, über allen
  Spalten liegt ein Autofilter (sortieren und filtern).
* Zahlen und das MHD sind echte Werte mit Format, keine Texte – die MHD-Spalte
  sortiert also nach Datum, nicht nach Tag.
* Unter der Tabelle steht eine Summenzeile mit `TEILERGEBNIS`: Sortieren lässt sie
  stehen, beim Filtern summiert sie nur die sichtbaren Zeilen. Die Formel hat keinen
  vorberechneten Wert; LibreOffice rechnet sie beim Öffnen aus (am 10.09. geprüft),
  in Excel selbst noch nicht getestet.
* Ein Blatt „Info" nennt Inventur, Stichtag, Status, Summen und wer wann
  abgeschlossen hat.

**„CSV"** bleibt für Weiterverarbeitung: Semikolon, BOM (sonst zerlegt Excel die
Umlaute), Summenzeile am Ende. Zwei Fallen, die am 10.09. bei PPS auftraten:
* **Jedes Feld steht in Anführungszeichen.** LibreOffice merkt sich die Trenner des
  letzten Imports; war dort auch das Komma angehakt, zerfielen alle Zeilen mit
  Komma im Artikelnamen (410 von 688).
* **Zahlen mit Dezimalkomma.** Ein deutsches Tabellenprogramm liest „3.281" als
  3281 – der EK stand vorher tausendfach zu hoch da.

### Bewusst nicht enthalten: Rückschreiben nach JTL
JTL kennt **keinen Abwertungswert** – der Lagerwert ist dort immer Menge × EK.
Ein Zurückschreiben müsste also entweder `tArtikel.fEKNetto` senken (verfälscht
Marge und Einkaufsauswertungen dauerhaft) oder `tWarenLagerEingang.fEKEinzel`
je Charge (chargengenau, aber ein Eingriff in gebuchte Beleghistorie).
Buchhalterisch ist der übliche Weg ohnehin, dass die Abwertung im Jahresabschluss
gebucht wird und die Wawi Mengen führt. Falls das später doch gewünscht wird:
zuerst gegen die Testumgebung mit Golden-Master-Vergleich, siehe
`doku/gm_diff.py`.

---

## 2. Reiter „Abflüsse je Artikel"

### Was er löst
Die Frage lautete: „Welche Mengen der einzelnen Größen von VAR80215 sind an
*richtige* Kunden gegangen, und an welche?" – also alles ausblenden, was an
verbundene Unternehmen ging.

### Bedienung
Artikelnummer oder Name eingeben, Zeitraum wählen, „Abflüsse auswerten".
Eine **Vater-Artikelnummer findet alle Größen darunter** (`VAR80215` → 80216
bis 80219), eine einzelne Nummer nur diese. Ohne Eingabe bleibt die Auswertung
leer – eine Abgangsliste über das ganze Sortiment beantwortet keine Frage.

### Drei Fallen, die die Auswertung abfängt
1. **Korrekturbuchungen sind kein Abverkauf.** Bei einer der Größen des
   Beispielartikels waren 9.800 von 13.122 Stück reine Korrekturbuchungen ohne
   Lieferschein. Sie stehen deshalb in einer eigenen Kachel („ohne Kundenbezug")
   und im Reiter „Woher die Abgänge stammen", nicht in der Kundenliste.
2. **„Ohne Rechnung" erkennt man am Preis, nicht am Rechnungsbezug.** Die
   0-€-Lieferungen haben in JTL sauber verknüpfte Rechnungen über 0 €.
   Merkmal ist `tBestellPos.fVkNetto = 0` – die Kachel „geliefert zum Preis 0".
3. **Ein Betrieb kann in der WaWi mehrfach angelegt sein.** Hygiene Daheim gibt
   es bei PPS zweimal (kKunde 4389 und 23296). Wer nur einen einträgt, blendet
   die halbe Menge nicht aus.

### Die Ausschlussliste
Das Widget „Verbundene Unternehmen" pflegt die Kunden, die aus den Listen
fallen. Technisch landen sie als `:excluded_customers` /
`:excluded_customers_empty` in jedem Mapping-Lauf
(`customer_exclusion_service`, eingehängt in `mandant_service.lauf_vorbereiten`) –
gleiches Muster wie die Artikel-Ausschlussliste der Intrastat-Meldung.

Die Liste **filtert nicht automatisch alles**: sie steht als Parameter bereit,
und nur die Abfluss-Mappings wenden sie an, gesteuert über den Schalter
„Verbundene Unternehmen: ausblenden / mit anzeigen". Eine Umsatzsumme soll die
Konzernlieferung weiterhin enthalten.

Die IDs sind mandantengebunden – dieselbe `kKunde` bezeichnet in einer anderen
WaWi einen anderen Kunden.

---

## Technisches

| Teil | Ort |
|---|---|
| Modelle | `backend/app/models/inventur.py`, `customer_exclusion.py` |
| Fachlogik | `backend/app/services/inventur_service.py` |
| Parameter-Injektion | `backend/app/services/customer_exclusion_service.py` |
| API | `backend/app/api/inventur.py`, `kunden_ausschluss.py` |
| Oberfläche | `frontend/src/components/forms/widgets/InventurWidget.tsx`, `KundenAusschlussWidget.tsx` |
| Auswertungen | Template `templates/jtl_lager_cockpit.json`, Mappings `m_inv_*` und `m_ab_*` |

Nach einer Änderung am Template: reseeden, installieren, und das **installierte
Formular gezielt patchen** – der Installer fasst bestehende Formulare bewusst
nicht an (siehe `doku/jtl_template_reseed.py`).
