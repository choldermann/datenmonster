# JTL-Preisschema — verifizierte Referenz

Grundlage für Preisautomatik (Ladenhüter-Rabatte, Kalkulation, Zurückschreiben).
**Verifiziert am 2026-08-29** gegen beide produktiven Wawis: PPS (Verbindung 3)
und HaKo (Verbindung 1). Jede Aussage hier stammt aus einer Abfrage gegen diese
Datenbanken oder aus der Objektdefinition in der Wawi, nicht aus Dokumentation.

## 1. Wo der Preis wirklich steht

Es gibt **keinen** einzelnen Preis je Artikel. Der gültige Nettopreis ergibt sich
aus vier Ebenen:

| Ebene | Tabelle | Bedeutung |
|---|---|---|
| Grundpreis | `dbo.tArtikel.fVKNetto` | Fallback, gilt wenn nichts anderes greift |
| Gruppen-/Kundenpreis | `dbo.tPreis` + `dbo.tPreisDetail` | Abweichung je Kundengruppe, Shop, ggf. einzelnem Kunden |
| Staffel | `dbo.tPreisDetail.nAnzahlAb` | Mengenstaffel innerhalb eines Preissatzes |
| Sonderpreis | `dbo.tArtikelSonderpreis` + `dbo.tSonderpreise` | befristete Aktion, schlägt die Ebenen darüber |

`tPreis` ist nur der **Kopf** (`kPreis`, `kArtikel`, `kKundenGruppe`, `kShop`,
`kKunde`), die Beträge stehen in `tPreisDetail` (`nAnzahlAb`, `fNettoPreis`,
`fProzent`). Ein Preis wird also über den Kopf adressiert, aber über das Detail
geändert — das ist für den Schreibweg entscheidend (siehe §5).

### Schlüsselkonventionen

- `kShop = 0` → gilt für alle Kanäle (Wawi-Aufträge, POS, Shops ohne eigenen Preis).
  `kShop > 0` → gilt nur für diesen Shop und **überschreibt** den 0er-Satz.
- `kKunde = 0` → Preis gilt für die ganze Kundengruppe.
  `kKunde > 0` (dann ist `kKundenGruppe = 0`) → individueller Preis für genau
  diesen Kunden. Bei PPS: 291 solcher Sätze auf 286 Artikeln.
- `nAnzahlAb = 0` → Festpreis für diese Gruppe (ersetzt `fVKNetto`).
  `nAnzahlAb > 0` → Staffelstufe ab dieser Menge.
- `fProzent` wäre ein prozentualer Rabatt statt eines Festbetrags.
  **In beiden Wawis unbenutzt** (0 von 12.711 Zeilen bei PPS), ebenso das Flag
  `tArtikel.nProzentualePreisStaffelAktiv`. Ein Schreibweg darf also mit
  Festbeträgen arbeiten, muss `fProzent` aber auf 0 setzen.

## 2. Die Auflösung muss man nicht selbst bauen

JTL liefert sie als View mit — **die sollten wir benutzen, nicht nachbauen**:

- `Preisliste.vIndividuellePreise` — löst `tPreis`/`tPreisDetail` auf,
  inklusive Shop-Fallback (ein `kShop = 0`-Satz wird auf jeden nicht gesperrten
  Shop gespiegelt, sofern der Shop keinen eigenen Satz hat).
- `Preisliste.vPreislisteNetto` — dasselbe plus Fallback auf
  `tArtikel.fVKNetto` für jede Kombination aus Artikel × Kundengruppe × Shop,
  die keinen eigenen Festpreis hat.

Bei PPS liefert `vPreislisteNetto` 118.721 Zeilen in 0,3 Sekunden — schnell
genug für ein Cockpit-Mapping ohne Vorberechnung.

Stichprobe Artikel 5 (`fVKNetto` = 7,99): Die View gibt je Kundengruppe und Shop
7,99 ab Menge 0 und dann 7,79 / 7,69 / 7,59 / 7,49 ab 10 / 30 / 60 / 120 Stück.

## 3. Sonderpreise

`tArtikelSonderpreis` ist der Kopf **je Artikel** (nicht je Gruppe):
`nAktiv`, `dStart`/`dEnde` mit Schalter `nIstDatum`, `nAnzahl` mit Schalter
`nIstAnzahl` (Aktion endet nach n verkauften Stück).
`tSonderpreise` hängt daran und trägt den Betrag je `kKundenGruppe` × `kShop`.
Fertig verbunden in `DbeS.vArtikelSonderpreis`.

Ein Sonderpreis gilt also **nicht**, wenn `nAktiv = 0` ist, oder wenn
`nIstDatum = 1` und das heutige Datum außerhalb von `dStart`/`dEnde` liegt, oder
wenn kein Satz in `tSonderpreise` für die Kundengruppe existiert.

## 4. Steuer

`tArtikel.kSteuerklasse` → `dbo.tSteuersatz` je Steuerzone.
Inland (Steuerzone 3): Klasse 1 = 19 %, Klasse 2 = 7 %, Klasse 3 = 0 %.
Steuerzone 4 führt alle Klassen mit 0 % (Ausland/Reverse Charge).
Alle Preistabellen führen **netto**; Brutto ist immer abgeleitet.

Ob der Kunde netto oder brutto sieht, steht an der Kundengruppe:
`tkundenGruppe.nNettoPreise`. Bei PPS ist das für **alle neun Gruppen** auf 1
gesetzt, bei HaKo für alle außer der leeren Gruppe „Otto". Ein errechneter
Nettopreis ist dort also genau der Preis, den der Kunde liest — eine
Preisendung (x,99) wirkt wie beabsichtigt. Für eine Gruppe mit Bruttoausweis
gilt das nicht: Dort müsste die Rundung auf den Bruttopreis rechnen.

`tkundenGruppe.fRabatt` ist ein zusätzlicher Gruppenrabatt auf den Preis. In
beiden Betrieben steht er überall auf 0. Wäre er gesetzt, käme er zu einem
Sonderpreis möglicherweise noch obendrauf — ob JTL ihn auf Sonderpreise
anwendet, ist **nicht geprüft**. Vor dem Einsatz einer Rabattautomatik in einer
Gruppe mit `fRabatt > 0` gehört das nachgemessen, sonst unterläuft der
Gruppenrabatt still das Margen-Minimum.

## 5. Schreibweg — was die Trigger von selbst erledigen

Auf allen vier Tabellen liegen aktive JTL-Trigger. Der wichtigste ist
`tgr_tPreisDetail_INSUP`; er feuert bei Änderung von `kPreis`, `nAnzahlAb`,
`fNettoPreis` oder `fProzent` und erledigt den kompletten Abgleich:

1. `Sync.tEntityTracking.dLastModified` wird gesetzt (POS/Kasse),
2. `dbo.tArtikelShop.nAktion |= 2` plus `cInet = 'Y'` — der Artikel wird
   vollständig an die Webshops gesendet,
3. bei B2B-Preisen werden Amazon-Angebotspreise mitgezogen.

**Konsequenz:** Wer direkt in `tPreisDetail` schreibt, löst denselben Abgleich
aus wie eine Änderung von Hand in der Wawi. Es ist kein eigener Sync nötig —
dieselbe Lage wie beim Stammdaten-Schreiben in `tArtikel`.
`tgr_tSonderpreise_INSUP` verhält sich analog.

`jtlActionValidator_tPreis` ist **kein** Wächter, der Schreibzugriffe ablehnt:
Der Trigger ist ein AFTER-DELETE, der verwaiste `tPreisDetail`-Zeilen aufräumt.

### Fallen für einen künftigen Schreibkern

- Wertänderungen gehören in `tPreisDetail`, nicht in `tPreis`. Der Trigger auf
  `tPreis` feuert nur bei Änderung der **Zuordnung** (Artikel/Gruppe/Shop/Kunde)
  und würde eine reine Preisänderung nicht an den Shop melden.
- Ein neuer Gruppenpreis braucht **beides**: einen Kopf in `tPreis` und
  mindestens eine Zeile mit `nAnzahlAb = 0` in `tPreisDetail`.
- `bRowversion` gibt es auf allen vier Tabellen — damit lässt sich eine
  Fremdänderung erkennen, bevor man sie überschreibt.
- Löschen eines `tPreis`-Kopfes räumt die Details per Trigger mit ab; einzelne
  Staffelstufen müssen dagegen direkt aus `tPreisDetail` entfernt werden.

## 6. Wie die beiden Betriebe tatsächlich damit arbeiten

|  | PPS | HaKo |
|---|---|---|
| Artikel | 3.256 | 3.238 |
| `tPreis` / `tPreisDetail` | 4.993 / 12.711 | 581 / 589 |
| Kundengruppen (mit Kunden) | 9 | 30 (14 belegt) |
| Sonderpreise aktiv **und** mit Betrag | 439 | 7 |

**PPS pflegt echte Gruppenpreise.** Basis, Bronze, Silver, Gold und Diamant
haben jeweils rund 830 Artikel mit eigenem Preis, dazu Staffeln ab 10/30/60/120
Stück (die vier häufigsten Stufen machen 9.195 der 12.711 Zeilen aus). Das ist
gepflegte Handarbeit auf ~830 Artikeln × 5 Gruppen — genau der Aufwand, den eine
Kalkulation ersetzen würde.

**HaKo pflegt sie praktisch nicht.** 6.240 von rund 7.200 Kunden hängen in der
Gruppe „Neukunde", 16 der 30 Gruppen haben keinen einzigen Kunden, und ganze 10
Artikel haben überhaupt einen Gruppenpreis.

### Zwei Datenbefunde nebenbei

- **PPS: 90 der 439 aktiven Sonderpreise sind abgelaufen** (`dEnde` in der
  Vergangenheit, `nAktiv` steht trotzdem auf 1). Sie greifen zur Laufzeit nicht,
  stehen aber in jeder Liste. JTL hat dafür sogar eine eigene View:
  `Dashboard.vAbgelaufeneSonderpreise`.
- **HaKo: 495 der 502 „aktiven" Sonderpreise haben gar keine Preiszeile** in
  `tSonderpreise` und sind damit wirkungslos. Real existiert dort **ein**
  wirksamer Sonderpreis; die übrigen 6 mit Betrag sind abgelaufen.

## 7. Was daraus für die Planung folgt

- Die Auflösung ist gelöst (§2) — ein Preis-Cockpit ist reine Anzeigearbeit.
- Der Schreibweg ist gangbar und der Shop-Abgleich kostet uns nichts (§5).
- **Pilot für jede Preisautomatik ist PPS**, nicht HaKo: nur dort gibt es eine
  Preisstruktur, die man automatisieren kann. Bei HaKo müsste zuerst die
  Gruppenzuordnung der Kunden aufgeräumt werden — das ist Beratung, nicht Code.
- Für den Ladenhüter-Rabatt („Reiniger") ist `tArtikelSonderpreis` das richtige
  Werkzeug: befristet, mengenbegrenzbar, je Gruppe und Shop, und durch `dEnde`
  von Natur aus selbstauflösend. Der Grundpreis bleibt unangetastet.

## 8. Offen

- Ob die Wawi bei mehreren zutreffenden Sonderpreisen den günstigsten oder den
  jüngsten nimmt, wurde nicht geprüft (in beiden Datenbanken gibt es je Artikel
  aktuell höchstens einen aktiven Kopf).
- `tArtikel.fAmazonVK` und `fEbayPreis` existieren, sind in beiden Betrieben
  aber leer — Marktplatzpreise sind hier kein Thema.
- `dbo.tPreiskalkulation` und `tPreiskalkulationSetting` sind JTLs **eigene**
  Preiskalkulation. Beide Tabellen sind in beiden Wawis leer: Die Funktion wird
  nicht genutzt. Vor dem Bau eines eigenen Kalkulierers lohnt der Blick, was sie
  kann — sie ist der nächstliegende Wettbewerber, und er ist schon bezahlt.
