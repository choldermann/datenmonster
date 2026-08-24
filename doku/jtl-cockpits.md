# Die JTL-Cockpits in Datenmonster

Sechs fertige Auswertungspakete, die direkt auf der JTL-Wawi-Datenbank (MS SQL Server) laufen:
Geschäftsführer, Vertrieb, Einkauf, Lager, Versand und Stammdaten-Health-Check. Jedes Paket wird
als Template installiert, fragt beim Installieren nur die Datenbankverbindung ab und bringt seine
Auswertungen (Mappings) und ein fertiges Formular mit Reitern, Kennzahlen, Diagrammen und Listen mit.

---

## 1. Was die KI in den Cockpits macht

Die Grundregel ist überall dieselbe: **Zahlen kommen aus SQL, die KI formuliert nur.**
Kennzahlen, Vorjahresvergleiche, Wahrscheinlichkeiten und Bewertungen werden vorher deterministisch
berechnet und dem Modell als fertige Fakten übergeben – mit der ausdrücklichen Anweisung, nichts
nachzurechnen und nichts zu ergänzen. Das Modell schreibt den Text drumherum.

### 1.1 KI-Kurzanalyse (Widget „KI-Analyse")

Jedes Cockpit hat oben im ersten Reiter eine KI-Kurzanalyse.

* **Sie liest nicht nur den sichtbaren Reiter.** Im GF-Cockpit zieht die Analyse über
  `extra_sections` die Kennzahlen aus **14 Bereichen** aller Reiter zusammen: Kunden, Zahlungsmoral,
  Offene Posten, Plattform-Deckungsbeiträge, Kapitalbindung, Ladenhüter, Klumpenrisiko, Prognose,
  Churn, Retouren, offene Bestellungen, Verbindlichkeiten, Termintreue. Die Analyse ist damit ein
  Lagebericht über das ganze Cockpit, nicht eine Bildunterschrift zur Kachelreihe.
* **Detailgrad umschaltbar:** *knapp* oder *ausführlich* (Schalter rechts in der Widget-Kopfzeile).
  „Ausführlich" nimmt deutlich mehr Rohzeilen in den Prompt (120 statt 30) – der wirksamste Hebel
  für Qualität, noch vor dem Modellwechsel. Ausführlich gibt es **nur über Datenmonster AI**: lokal
  gemessen ~290 s, der Proxy gibt nach 300 s auf; lokal fällt es still auf „knapp" zurück.
* **Farbige Bewertung im Text:** Erfreuliches wird grün, Kritisches rot markiert – und zwar auf den
  Zahlen, nicht auf Floskeln. Die Markier-Regel bekommt nur der Gateway; lokale Modelle schrieben
  die Marker ohnehin unsauber.
* **Bewertungstabelle „gut / verbesserungswürdig"** unter dem Text: bewusst **nicht** vom Modell,
  sondern deterministisch aus den KPI-Ergebnissen aller Reiter (Ertragslage, Kunden, Liquidität,
  Kapital & Lager, Retouren …). Sie ist damit immer vorhanden, korrekt und stabil, auch wenn die
  KI gerade nicht erreichbar ist.
* **Halluzinationsschutz:** Alle Analyse-Prompts enthalten „nur gelieferte Zahlen – erfinde keine
  Kennzahl, keinen Namen, keinen Vorjahreswert". Lokale Modelle bekommen zusätzlich höchstens
  5 Kennzahlenblöcke à 600 Zeichen statt aller 14 – weniger Blöcke, weniger Angriffsfläche.
* **Warnhinweis bei lokalem Modell:** Über der Analyse steht sichtbar, dass kleine Modelle Werte
  verwechseln oder erfinden können und dass Kacheln und Bewertungstabelle die verlässliche Quelle sind.
* Deutsche Zahlenschreibweise (Tausenderpunkt, Dezimalkomma) und Einheiten (€/%/Tage) werden
  serverseitig vorformatiert, damit das Modell Euro, Prozent und Tage nicht vertauscht.

### 1.2 KI-Handlungsempfehlung pro Zeile

Ein Klick auf eine Zeile in bestimmten Tabellen öffnet ein Modal mit einer konkreten Empfehlung.
Auch hier rechnet der Server, nicht das Modell:

| Art | Wo | Was berechnet wird |
|---|---|---|
| `customer_winback` | GF: *Kunden mit Umsatzrückgang*, *Schlafende Kunden* | Rückgewinnungswahrscheinlichkeit aus Inaktivität, Bestellhistorie, Umsatzrang |
| `article_liquidation` | GF: *Ladenhüter* | Reichweite, gebundenes Kapital, Rabattvorschlag |
| `region_potential` | Vertrieb: *Auftragseingang je Bundesland* | Marktdurchdringung gegen Bevölkerungsanteil |
| `article_description` | Health-Check: *Artikel mit dürftiger Beschreibung* | Textvorschlag auf Basis der vorhandenen Stammdaten |

### 1.3 KI im Stammdaten-Health-Check

* **EAN-Recherche beim Hersteller** – fehlende EANs werden über Hersteller-Adapter (u. a. Deiss,
  Denios, Rhenus) gesucht, mit Sicherheitsgrad (gesichert / prüfen / ungesichert).
* **Hersteller-Navigator** – Hersteller → Artikel → Vorschlag, um Stammdatenlücken serienweise zu schließen.
* **Beschreibungsvorschläge** für Artikel mit dürftiger Beschreibung, mit Drilldown auf die
  aktuell gepflegte Beschreibung.

### 1.4 KI im PDF-Report

Der PDF-Report jedes Cockpits enthält eine KI-Management-Summary plus dieselbe deterministische
Bewertungstabelle. Damit das im synchronen Report klappt, ist die Generierung zeitlich begrenzt und
die Modelle lassen sich über *KI-Einstellungen → Aufwärmen* vorab laden.

### 1.5 Wo die KI rechnet

* **Lokal (Ollama-Container):** kostenlos, datensparsam, aber klein und langsam – für Kurzanalysen
  brauchbar, für belastbare Analysetexte mit Warnhinweis versehen.
* **Datenmonster AI (Gateway):** große Modelle, Abrechnung über Credits; Voraussetzung ist eine
  aktivierte Lizenz. Meldet der Gateway „nicht erreichbar", ist fast immer die Lizenz der Grund.

Zusätzlich hat jedes Cockpit-Formular den **KI-Assistenten** aktiviert („Frag deine Daten"), mit dem
sich Fragen an die hinterlegten Daten stellen lassen.

---

## 2. Was alle Cockpits gemeinsam haben

* **Zeitraumfilter mit Vorjahresvergleich.** Voreinstellung: laufendes Jahr, lädt beim Öffnen
  automatisch. Presets (Dieser Monat, Letztes Jahr, 12 Monate …) aktualisieren das ganze Cockpit.
  Alle KPI-Kacheln vergleichen mit dem gleichen Zeitraum des Vorjahres.
* **Momentaufnahmen sind gekennzeichnet.** Reiter wie *Auftragsbestand*, *Offene Bestellungen*,
  *Rückstand* oder der komplette Health-Check ignorieren den Zeitraumfilter bewusst.
* **Tabellen sind Arbeitsmittel:** sortierbar per Klick auf die Spaltenüberschrift, CSV-Export,
  Versand per E-Mail direkt aus dem Widget, Drilldown bis auf Belegebene (Land → Rechnungen →
  Positionen → Artikel; Artikel → Lagerbuchungen; Bestellung → Positionen).
* **PDF-Report** über den Button oben im Formular, mit Abschnittsauswahl, Firmenlogo/Absender aus
  `tFirma` und der KI-Management-Summary.
* **Portalfähig:** Cockpits lassen sich veröffentlichen und Portal-Benutzern zugänglich machen.
* **Installation:** Template auswählen, JTL-Datenbankverbindung angeben – Zugangsdaten sind nie Teil
  des Templates. Eine Neuinstallation legt keine Doppel an, sondern aktualisiert vorhandene Mappings.

---

## 3. Die Cockpits im Einzelnen

### 3.1 Geschäftsführer-Cockpit
*Template `jtl_gf_cockpit`, Version 2.2 – 64 Auswertungen, 12 Reiter*

Das Unternehmenscockpit: Ertragslage, Kunden, Liquidität, Kapital und Risiken auf einen Blick,
durchgängig mit Vorjahresvergleich.

| Reiter | Inhalt |
|---|---|
| **Unternehmensübersicht** | „Heute zu tun" aus der Warnungs-Engine (Ampel mit Klick auf die Detailliste), Umsatz, Rohertrag (DB I), DB II, Marge, Rechnungen, Ø Auftragswert, aktive Kunden, KI-Kurzanalyse, Umsatzverlauf gegen Vorjahr |
| **Kundenentwicklung** | Aktive Kunden, Neukunden, Ø Umsatz je Kunde, Top-10-Kunden, Kunden mit Umsatzrückgang (KI-Empfehlung), Zahlungsmoral: Ø Zahlungsdauer, Anteil verspätet, langsamste Zahler, sich verschlechternde Zahler |
| **Mitarbeiter** | Aufträge und Angebote je Mitarbeiter, Auftrags- und Angebotswert |
| **Ausblick** | Umsatzprognose Jahresende (saisonal, plus linear als Gegenprobe), Ist YTD, Prognose gegen Vorjahr, schlafende Kunden mit Winback-Empfehlung |
| **Offene Posten** | Offene Forderungen, davon überfällig, Überfälligkeitsquote, DSO, Aging, Top-Debitoren, Mahnkandidaten |
| **Einkauf & Verbindlichkeiten** | Bestellvolumen, offene Bestellungen und Verzug, Rechnungsvolumen, offene Verbindlichkeiten, Termintreue – die Einkaufssicht verdichtet für die GF |
| **Umsatzanalyse** | Warengruppen aktuell/Vorjahr, Top-15-Artikel, Umsatz nach Land/Bundesland (mit Drilldown), Rechnungen im Zeitraum, Jahresvergleich, DB je Plattform |
| **Kapitalbindung** | Kapitalbindung Lager, Artikel mit Bestand, Kapital in Ladenhütern, Verteilung je Warengruppe, Top-Artikel, Umschlag & Reichweite |
| **Trends** | Umsatz & Rohertrag über 24 Monate, Warengruppen-Trend (letzte 12 vs. vorherige 12 Monate) – feste rollierende Fenster, unabhängig vom Zeitraumfilter |
| **Warnungen** | Ladenhüter (KI-Empfehlung), umsatzstarke Artikel ohne Bestand, negative Marge, gesperrte Artikel mit Bestand |
| **Klumpenrisiko / ABC** | Umsatzanteil Top-5/Top-10-Kunden und Top-5-Artikel, ABC-Verteilung und -Listen für Kunden und Artikel |
| **Retouren** | Retourenzahl, Menge, Wert, Retourenquote, Verlauf über 13 Monate, Gründe als Tabelle und Tortendiagramm, Top-Artikel und -Kunden |

Gut zu wissen:
* Rohertrag/Marge rechnen mit dem aktuellen Artikel-EK; die Ladenhüter-Schwelle ist beim
  Installieren einstellbar (Standard 180 Tage ohne Verkauf).
* Gesperrte Kunden und inaktive Artikel fliegen aus Listen und Rankings raus, aus den KPIs nicht –
  für gesperrte Artikel mit Bestand gibt es einen eigenen Warnblock.
* Bundesländer werden aus der PLZ hergeleitet, weil das JTL-Feld leer bleibt.
* **„Heute zu tun" kommt aus denselben Prüfregeln wie der Unternehmensmonitor.** Angezeigt werden
  die Regeln, deren Auswertungen dieses Cockpit mitbringt, plus die Ladenhüter-Warnung des
  Lager-Cockpits, falls installiert. Die Schwellwerte stehen zentral im Dashboard-Reiter
  „Warnungen" und gelten damit für Cockpit, Monitor und PDF-Report gleichermaßen. Bis Version 2.1
  stand hier eine eigene Aufgabenliste mit im SQL verdrahteten Schwellen – sie ist ersetzt, weil
  dieselbe Frage sonst zweimal und mit unterschiedlichen Grenzen beantwortet wurde.

### 3.2 Vertriebs-Cockpit
*Template `jtl_vertrieb_cockpit`, Version 1.3 – 31 Auswertungen, 7 Reiter*

Vertrieb misst man am Auftragseingang, nicht an der Rechnung. Genau das macht dieses Cockpit.

| Reiter | Inhalt |
|---|---|
| **Auftragseingang** | Auftragseingang netto, Aufträge, Ø Auftragswert, Storno-Quote, KI-Kurzanalyse, Monatsverlauf gegen Vorjahr, Eingang je Plattform, stornierte Aufträge |
| **Auftragsbestand** | Backlog-Wert, offene Aufträge, Ø Alter, überschrittene Liefertermine, Altersverteilung, offene Aufträge nach Wert |
| **Angebote** | Angebote, Volumen, Ø Wert, Conversion, gestellt gegen gewonnen je Monat, Nachfass-Liste der letzten 180 Tage |
| **Kunden** | Auftragseingang je Kunde, Neukunden, Top-Kunden nach Rechnungsumsatz, Rückgänge, schlafende Kunden, ABC-Analyse |
| **Regionen** | Auftragseingang je Bundesland (KI-Empfehlung zum Potenzial), Umsatzanteil gegen Bevölkerungsanteil, Nachfass-Kandidaten |
| **Artikel** | Auftragseingang je Artikel, Top-Artikel nach Rechnungsumsatz |
| **Mitarbeiter** | Aufträge je Mitarbeiter, Angebote je Mitarbeiter mit Conversion |

Gut zu wissen:
* Auftragseingang = Nettowert der im Zeitraum erfassten Aufträge (ohne Stornos) – der Frühindikator
  vor der Rechnung.
* JTL verknüpft Angebot und Auftrag nicht (getrennte Nummernkreise). Die Conversion ist deshalb eine
  Heuristik: Angebot gilt als gewonnen, wenn derselbe Kunde binnen 60 Tagen einen Auftrag bekommt.
* „Mitarbeiter" ist der Erfasser des Belegs. Im Backoffice erfasste Aufträge laufen auf die
  erfassende Person – die Angebotstabelle bildet den aktiven Vertrieb besser ab.

### 3.3 Einkaufs-Cockpit
*Template `jtl_einkauf_cockpit`, Version 1.1 – 21 Auswertungen, 5 Reiter*

| Reiter | Inhalt |
|---|---|
| **Einkaufsvolumen** | Bestellvolumen netto, Bestellungen, Ø Bestellwert, aktive Lieferanten, KI-Kurzanalyse, Monatsverlauf gegen Vorjahr, Volumen je Lieferant |
| **Offene Bestellungen** | Anzahl und Wert offener Bestellungen, überschrittene Liefertermine, Ø Verzug, offener Wert nach Verzugsklasse, Liste nach offenem Wert |
| **Lieferantenqualität** | Termintreue, Ø Verzug, Ø Lieferzeit, Termintreue je Lieferant (ab 3 Lieferungen), Lieferantenstamm mit Konditionen und 12-Monats-Volumen |
| **Eingangsrechnungen** | Rechnungsvolumen, offene Verbindlichkeiten, offene und überfällige Rechnungen, Liste (überfällige zuerst), Volumen je Lieferant |
| **Artikel & Preise** | Top-Einkaufsartikel, EK-Preisentwicklung der letzten 12 Monate |

Gut zu wissen:
* Die Termintreue vergleicht den Soll-Liefertermin mit dem **echten Wareneingang**
  (`tWarenLagerEingang`), nicht mit einem Statusfeld.
* „Offen" heißt: Restmenge vorhanden, nicht gelöscht, nicht manuell abgeschlossen. Sehr alte offene
  Bestellungen sind meist Karteileichen und verzerren den Ø-Verzug.

### 3.4 Lager-Cockpit
*Template `jtl_lager_cockpit`, Version 1.0 – 26 Auswertungen, 7 Reiter*

Das analytisch anspruchsvollste Paket: Es rekonstruiert den Lagerbestand aus der Buchungshistorie
und bewertet ihn zum **historischen** Einkaufspreis.

| Reiter | Inhalt |
|---|---|
| **Lagerwert** | Lagerwert zum historischen EK, Artikel mit Bestand, Stück im Lager, Anteil ohne gebuchten EK, KI-Kurzanalyse, Wertverlauf über 12 Monatsstichtage, Wert je Warengruppe und Hersteller, Artikel nach gebundenem Kapital (Klick → Buchungen) |
| **Disposition** | Artikel mit Fehlmenge, Wert der Fehlmenge, Überreservierungen, Zulauf; Fehlmengen gegen offene Aufträge, erwarteter Zulauf aus offenen Bestellungen |
| **Umschlag & Reichweite** | Ø Umschlag pro Jahr, Ø Reichweite, Artikel ohne Abgang (12 Monate), Kapital ohne Abgang, Lagerwert nach Reichweiteklasse, Detail je Artikel |
| **Ladenhüter** | Ladenhüter über 180 Tage, gebundenes Kapital, über ein Jahr ohne Abgang, Anteil am Lagerwert, Kapital nach Zeit ohne Abgang |
| **Inventur & Schwund** | Korrekturbuchungen, Wert und Menge netto, davon Inventurdifferenzen, Korrekturwert je Monat, größte Korrekturen je Artikel, Korrekturen je Benutzer |
| **Preishistorie** | EK aktuell, tiefster/höchster EK, Anzahl verschiedener Preise, Preisverlauf Einkauf gegen Verkauf über 24 Monate, jede EK-Änderung mit Lieferant |
| **Lager & Buchungen** | Bestand und Wert je Warenlager, Buchungsarten im Zeitraum |

Gut zu wissen:
* Grundlage ist `vArtikelHistorie`; der Stichtagsbestand ist die Summe aller Buchungen bis zu diesem
  Tag. Gegenprobe auf der Prüf-Datenbank: bei 2.817 von 2.817 aktiven Artikeln deckungsgleich mit
  `tlagerbestand`.
* Bewertet wird mit dem EK, der auf der Buchungszeile steht – eine spätere EK-Pflege verändert die
  Vergangenheit also nicht. Nur wenn nie ein EK gebucht wurde, greift der aktuelle Artikel-EK;
  die Kennzahl „davon ohne gebuchten EK" zeigt, wie oft das passiert.

### 3.5 Versand-Cockpit
*Template `jtl_versand_cockpit`, Version 1.0 – 11 Auswertungen, 4 Reiter*

| Reiter | Inhalt |
|---|---|
| **Versandübersicht** | Sendungen, Ø Durchlaufzeit, Tracking-Quote, Ø Gewicht, KI-Kurzanalyse, Sendungen je Monat gegen Vorjahr, je Versandart und je Wochentag |
| **Durchlaufzeit** | Ausgewertete Sendungen, Ø Auftrag → Versand, Anteil binnen 24 h, Anteil über 72 h, Verteilung, längste Durchläufe |
| **Tracking** | Sendungen mit/ohne Tracking-Nummer, Quote, Liste der Sendungen ohne Tracking |
| **Rückstand** | Lieferscheine ohne Versand, Ø Alter, ältester Vorgang, Sendungen ohne Versanddatum |

Gut zu wissen:
* Der Dienstleister kommt aus `tVersandArt.cName` – `tVersand.cLogistiker` befüllt die Wawi nicht.
* Durchlaufzeit = Stunden vom Auftragsdatum bis zum Versanddatum (`tVersand → tLieferschein → tAuftrag`).
* Die Liste „ohne Tracking" blendet Versandarten aus, die generell ohne Tracking arbeiten
  (Selbstabholer, Spedition): gezeigt werden nur Arten mit sonst mindestens 50 % Tracking-Quote.

### 3.6 Stammdaten-Health-Check
*Template `jtl_health_check`, Version 1.6 – 24 Auswertungen (19 Prüfungen + 5 Detailansichten), 6 Reiter*

Kein Zeitraum, keine Umsätze: Dieses Cockpit prüft die Datenqualität und liefert Arbeitslisten.

| Reiter | Inhalt |
|---|---|
| **Übersicht** | Aktive Artikel, Artikel mit Datenlücke, vollständig gepflegte Artikel, Kunden ohne E-Mail, Ampel „Stammdaten-Prüfungen" (Klick → Detailliste), KI-Kurzanalyse, fehlende Angaben je Feld |
| **Artikelstamm** | Artikel ohne Gewicht, ohne Warengruppe, ohne Bezeichnung |
| **Datenpflege** | Artikel ohne EAN, mehrfach vergebene EAN, **EAN-Recherche beim Hersteller**, Artikel mit dürftiger Beschreibung (KI-Vorschlag), **Hersteller-Navigator** |
| **Preise & Marge** | Artikel ohne Einkaufspreis, Artikel mit VK unter EK |
| **Außenhandel** | Artikel ohne Warentarifnummer, Artikel ohne Herkunftsland (Intrastat-Pflichtfelder) |
| **Kunden** | Kunden ohne E-Mail-Adresse, mögliche Kundendubletten |

Gut zu wissen:
* Geprüft werden aktive, nicht gelöschte Artikel ohne Vater-Artikel (Väter tragen selbst keine
  EAN/Gewichte) sowie nicht gesperrte Kunden mit Standardadresse.
* Ampel: grün = keine Treffer, gelb = Einzelfälle, rot = über dem Schwellwert. Die Schwellwerte
  stehen im Mapping „Health-Check – Übersicht (Ampel)" und sind anpassbar.
* Die Schwelle für „dürftige Beschreibung" wird beim Installieren gesetzt (Standard 120 Zeichen).
* Nicht jede Lücke ist ein Fehler – die Listen sind Arbeitsvorräte, keine Fehlermeldungen.
* **Jede Befundliste ist anklickbar.** Eine Artikelzeile öffnet das Artikel-Detail mit allen
  Pflichtfeldern, einer Spalte „FehlendeFelder" und der Verkaufshistorie (Bestand, letzter Verkauf,
  Menge und Umsatz der letzten 12 Monate) – so ist vor dem Pflegen sichtbar, ob sich die Arbeit für
  diesen Artikel lohnt; ein weiterer Klick zeigt die einzelnen Verkäufe. Eine mehrfach vergebene EAN
  führt zu den betroffenen Artikeln, eine Kundenzeile zum Kunden-Detail, eine Dublettenzeile zu allen
  Kunden dieser Firma (Adresse, Umsatz, letzte Bestellung – Filialen sind so von echten Dubletten
  unterscheidbar).
* Der PDF-Report enthält – wie bei den anderen Cockpits – die deterministische Bewertungstabelle:
  Vollständigkeit, EAN & Eindeutigkeit, Preise & Marge, Außenhandel, Logistik & Struktur, Kundenstamm.
  Als „gut" gilt eine Lückenquote bis 5 % je Feld (Kundenstamm: bis 20 % ohne E-Mail); VK unter EK und
  mehrfach vergebene EANs zählen absolut.

---

## 4. Nicht Cockpit, aber gleiche Familie

Das Template **Intrastat** (`jtl_intrastat`) gehört zur JTL-Reihe, ist aber kein Dashboard: Es liefert
Mappings für Ausfuhr und Einfuhr (eSTATISTIK.core `.idev` und Destatis-CSV), ein Formular für die
Zeitraumauswahl, eine Pflege von Ausschlussartikeln und monatliche Pipelines.

---

## 5. Kurzüberblick

| Cockpit | Auswertungen | Reiter | Kernfrage |
|---|---:|---:|---|
| Geschäftsführer | 64 | 12 | Wie steht das Unternehmen da – und wo muss ich hin? |
| Vertrieb | 31 | 7 | Was kommt rein, was liegt offen, wo ist Potenzial? |
| Einkauf | 21 | 5 | Was kaufe ich wo ein, und liefern die Lieferanten pünktlich? |
| Lager | 26 | 7 | Was ist mein Lager wert, und wo liegt totes Kapital? |
| Versand | 11 | 4 | Wie schnell versende ich, und was hängt fest? |
| Health-Check | 24 | 6 | Wo sind meine Stammdaten lückenhaft oder widersprüchlich? |
