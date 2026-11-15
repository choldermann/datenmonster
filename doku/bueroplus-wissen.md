# microtech büro+ – Wissen für Datenmonster

Stand: 15.11.2026 · Quelle: öffentliche Online-Hilfe https://hilfe.microtech.de (Seitenstand Okt./Nov. 2026)
Anlass: Interessent mit büro+ (Vorführung 04.11.2026), siehe Gedächtnis `idea_bueroplus_cockpits`.

> **Wichtig:** Alles hier stammt aus der Hilfe, nicht aus einem echten Mandanten. Feld- und Tabellennamen
> sind nur dort sicher, wo sie in der Hilfe wörtlich vorkommen. Vor dem ersten Cockpit an echten Daten prüfen.

---

## 1. Pakete und Generationen – erst klären, was der Kunde hat

| Generation | Stufen | Erkennbar an |
|---|---|---|
| bis 2023 (Gen. 20 u. a.) | M, L, XL, XXL | Versionsangabe ohne „(G24)“ |
| ab 2024 (Gen. 24) | **Basic, Core, Enterprise** (Funktionen fast alle wie „XXL“) | Version `XXL-2x.xx.xxxx (G24)` – beim Start oder unter HILFE › LIZENZ |

Was wir je Paket nutzen können:

| Zugriffsweg | Basic | Core | Enterprise | Gen. 20 |
|---|---|---|---|---|
| Ad-hoc-Export nach Excel (von Hand) | ✅ | ✅ | ✅ | ✅ |
| Export-Layouts (CSV/SDF/XML/Excel/ADO) von Hand | ✅ | ✅ | ✅ | ✅ |
| **Automatisierungsaufgaben** (zeitgesteuerter Export/Import) | ❌ | ✅ | ✅ | ab XL |
| **ADO-Export direkt in SQL Server/ODBC-DB, zeitgesteuert** | ❌ | ✅ | ✅ | ab XL |
| COM-Aktiv / mDL (Windows-COM, Aktualitäts-Service nötig) | ✅* | ✅* | ✅* | ✅* |
| **GraphQL-API** (HTTPS, OAuth 2.0) | ❌ | ❌ | ✅ (ab Build 7076) | ❌ |
| **SQL-Replikation nach PostgreSQL** | ❌ | ❌ | ✅ (ab Build 6980) | ❌ |
| microtech ERP Cloud + Dashboard Builder | ✅ (Build 7285+) | ✅ | ✅ | ❌ |

\* COM nur mit gültigem Jahresvertrag (Aktualitäts-Service), **nicht** bei „buhl Unternehmer“. Support zu COM nur für
Solution-Partner. Für Automatisierungs-Dienste braucht es eine „Installation inkl. Datenserver“. In Gen. 24 kosten
Automatisierungs-Dienste keine eigene Anwenderlizenz mehr (Gen. 20 XL: je Dienst eine Lizenz).

**Preise laut microtech.de/preise (15.11.2026, netto, Miete pro Monat):**

| Paket | Preis | Anwender inkl. | je weiterem Anwender | max. Anwender / Unternehmen |
|---|---|---|---|---|
| Basic | 199 € | 2 | 39 € | 5 / 2 |
| Core | 299 € | 2 | 49 € | 25 / 3 |
| Enterprise | 399 € | 2 | 59 € | unbegrenzt zubuchbar |

Enterprise nennt dort „Lesender SQL-Zugriff“ (= Replikation) und „GraphQL-API“. Prozessautomatisierung ab Core.
„Zugang zur ERP Cloud“ und „KI-gestützter Dashboard Builder“ stehen in der Paket-Tabelle **ohne eigenen Preis**.
In welchen Paketen sie stecken, ließ sich aus dem Seitentext nicht sicher lesen; die Hilfe kennzeichnet sie mit
„Gen. 24“, also vermutlich in allen Paketen. Zu KI-Kontingenten oder Grenzen sagt die Seite nichts.

**Erste Frage an jeden büro+-Kunden:** Gen. 24? Welches Paket? Build-Nummer? Läuft ein Datenserver (BpServer)?

---

## 2. Die Zugriffswege – von bester zu einfachster

### 2.1 SQL-Replikation → PostgreSQL (Enterprise) ⭐ Ideal für Cockpits

- büro+ schreibt **alle freigegebenen Tabellen** selbst in eine PostgreSQL-DB, die der Kunde (oder wir) bereitstellt.
  Gedacht genau für BI-Werkzeuge („z. B. Tableau“). **Zurückschreiben ist nicht vorgesehen** (nur lesen).
- Einrichtung: MEINE FIRMA › ÜBERBLICK › Register AUTOMATISIERUNGS-DIENSTE → Dienst „Aufgaben-Dienst (mit
  eingeschränkter Berechtigung)“, Benutzer braucht Supervisor-Rechte → Automatisierungsaufgabe mit Aktion
  **„SQL Replikation“**: Server (`host:port`), TLS-Stufe, Benutzer, Passwort, DB-Name, **Schemaname** (nur
  Kleinbuchstaben, Ziffern, `_`).
- PostgreSQL-DB laut microtech anlegen mit: UTF8, template0, Locale-Provider **icu**, ICU-Locale **de-DE**.
  `max_locks_per_transaction` auf **1024** setzen (sonst Fehler „EUniError Shared Memory aufgebraucht“).
- Welche Tabellen: per Berechtigungsstruktur. Vorgabe **„(Standard-Replikation)“** kopieren und anpassen
  (Suche nach „Replikation“ in DATEI › EINSTELLUNGEN › BERECHTIGUNGEN).
- Erster Lauf: Minuten bis Stunden (Randzeit). Danach nur **geänderte Zeilen** (über interne LSN), transaktionssicher,
  „praktisch in Echtzeit“ je nach Intervall. Läuft auch, wenn büro+ später gerade nicht erreichbar ist (Daten liegen ja in PG).
- Aufbau in PostgreSQL:
  - Tabellennamen **deutsch** wie im DB-Manager, z. B. `artikel`, `Adressen`, `Anschriften`.
  - Verschachtelte Tabellen werden **flach** mit Endung, z. B. **`artikel_ums`** = Artikelumsatz (entspricht der
    Detail-Ansicht „Umsatz“).
  - Ab Schema-Version 1.1: **Selektionsfelder** in eigener Tabelle **`<Tabelle>_Sel`** (Join über `RefNr`).
  - Ab 1.2: alle Texte als `TEXT` (keine Längen).
  - Ab 1.3: Überlauftabellen `_1`, `_2`, `_3`, wenn > 1600 Spalten.
  - **VK-Preise sind enthalten**, **berechnete Felder nicht**.
- **Fallen für uns:**
  - Bei jeder Strukturänderung (neues Selektionsfeld, manche Updates, Wechsel der Schema-Version) wird die Tabelle
    **komplett neu aufgebaut** – eigene **Views und Trigger darauf werden gelöscht**. Abhilfe: Views in der Prozedur
    `<schema>.onAfterAll_ApplyNew()` anlegen (wird nicht überschrieben); weitere Hooks: `onBeforeAll_ApplyUpdates`,
    `<tab>_onAfter_ApplyUpdates(oldLSN, newLSN)`, `onAfterAll_ApplyUpdates`.
  - Keine eigenen Spalten/PK/FK in replizierten Tabellen; eigene Tabellen daneben anlegen, die fasst die Replikation
    nicht an. Keine eigenen Tabellen mit Namen `<repl-tabelle>_1/_2/_3/_Sel`.
  - `RefNr`, `insertLSN`, `modifyLSN` ändern sich bei Reorganisation → **nie als dauerhafte Schlüssel** speichern;
    fachliche Schlüssel nehmen (ArtNr, AdrNr, BelegNr).
- **Für Datenmonster:** Postgres-Verbindung → SQL-Vorlage „büro+ Cockpits“ direkt auf das Replikationsschema.
  Unsere Views/Hilfstabellen in **eigenem Schema** halten, nicht im Replikationsschema → kein Verlust bei Neuaufbau.

### 2.2 GraphQL-API (Enterprise) – lesen **und schreiben**

- Endpunkt je Mandant (ab Build 7145 automatisch): `https://<server>/microtech/erp/mand/<MandNr>/graphql/v1`
  (Beta: `erpb`, Schulung: `erps` statt `erp`). Statusseite ohne Login: `https://<server>/microtech/erp/mand/`
  (mit `Accept: application/json` maschinenlesbar). Interaktive Apollo Sandbox nur Enterprise.
- Aktivieren: DATEI › INFORMATIONEN › AKTUELLE FIRMA › MANDANT BEARBEITEN › Register WEITERE ANGABEN › „GraphQL aktiviert“.
  Voraussetzungen: HTTP/2 im Datenserver, gültiges SSL-Zertifikat in BpConfig.exe, Benutzer mit Kennzeichen
  „Zugriff über GraphQL erlaubt“.
- Anmeldung: **OAuth 2.0** (Authorization Code oder **Client Credentials**) → Bearer Token. Anwendungen unter
  MEINE FIRMA › ÜBERBLICK › SYSTEMEINSTELLUNGEN › ANWENDUNGEN VERWALTEN. Keine 2FA. Rechte = Berechtigungsstruktur des Benutzers.
- Namensschema: Tabellen **englisch** (`tblProducts`, `tblAddresses`, `tblTransactions`), Felder **deutsch** mit
  Präfix (`fldArtNr`, `fldBelegNr`). Präfixe: `tbl` Tabelle, `row` Verweis auf einen Datensatz, `lnk` Link auf
  verwandte Liste, `fld` Feld, `by` Sortierfolge, `kf1..` Schlüsselfeld, `aco` Betragsgruppe, `img` Bild, `fn` Funktion.
- Lesen: `rowRead` (einer), `rowsRead` (alle/Bereich), `conRead(first, after)` (Seitenweise, Relay-Cursor).
  Filter: `fastFilter` (auf dem Datenserver, schnell) vs. `slowFilter` (im Executor, flexibel, langsam).
- Änderungen erkennen: jede Top-Level-Tabelle hat `fldModifyLSN` / `fldInsertLSN` (stetig steigend). **Keine
  Webhooks/Subscriptions.** `structureTag` je Tabelle ändert sich bei Strukturänderung → dann gespeicherte LSNs
  verwerfen und neu laden.
- Schreiben (Mutations): `rowNew`/`rowModify`/`rowSave`, transaktional, bei gesperrtem Datensatz kompletter Rollback.
  Vorgangsfunktionen: `fnPost` (buchen), `fnReverse` (stornieren), `fnConvert` (wandeln), `fnMoveToArchive`,
  `fnRestoreToTransactions`. **Kein Druck** über GraphQL, **kein „Kundenpreis inkl. aller Preislogik“** ohne Vorgang.
- Eigene „Freie Datenbank-Tabellen“: im DB-Manager Feld „GraphQL-Bezeichnung“ füllen → `tblCust<Name>`.
- microtech hat eine eigene Anleitung „Claude mit microtech GraphQL verbinden (MCP)“ (`npx mcp-graphql`) – die Konkurrenz
  denkt also schon in KI-Zugriff.
- **Für Datenmonster:** REST-/GraphQL-Knoten als Quelle möglich, aber für Cockpits ist die Replikation viel bequemer.
  GraphQL ist interessant fürs **Zurückschreiben** (Stammdaten, Preise) und für Kunden ohne eigenen Postgres.

### 2.3 ADO-Export (ab Core / Gen. 20 XL) ⭐ Weg für Kunden ohne Enterprise

- Export-Layout mit Eingabeformat **ADO** schreibt direkt in eine **Microsoft-SQL-Server-, Access-, Excel- oder
  ODBC-Datenbank**. Zieldatenbank muss die gleichen Felder (Anzahl/Namen) haben; Zielfeldnamen im Layout anpassbar.
- **Zeitgesteuert** über Automatisierungsaufgabe, Aktion „EXPORT“ (Feld „Dateiname“ dort leer lassen).
- Hinweis der Hilfe: „Mit dem ADO-Export werden keine Daten aktualisiert“ → vermutlich nur Anfügen. Für uns heißt das:
  Staging-Tabelle vor jedem Lauf leeren (Voll-Export) oder per Datenmonster-Upsert weiterverarbeiten. **Am echten
  System testen.**
- Braucht MDAC-/ODBC-Treiber auf dem Rechner, auf dem der Automatisierungs-Dienst läuft.

### 2.4 Export-Layouts in Dateien (alle Pakete; zeitgesteuert ab Core)

- DATEI › SCHNITTSTELLEN › EXPORT: links Datenbereich (Stammdaten Artikel/Adressen, Vorgänge, Buchhaltung …), rechts Layouts.
  Felder per GESTALTEN (Feldeditor), Datensätze per Bereichsauswahl begrenzen.
- Formate: Text/CSV, **SDF** (ANSI/ASCII/Unicode, Komma-getrennt), Excel, XML-Tag-/INI-Tag-Feldformat, ADO.
  Zeilenumbrüche aus Textfeldern können als **zwei Leerzeichen** ankommen.
- Vorgänge exportierbar als „Liste mit Positionen“ und „Liste mit Protokoll“ (Variablen `Vog.VPo.*`, `Vog.VPtk.*`),
  jeweils aus **„Vorgänge“ und „Archiv Vorgänge“ getrennt**.
  Lieferanten-Nr. je Position nur, wenn im DB-Manager › Vorgangspositionen „Lieferantenfelder bei Vorgangspositionen
  bereitstellen“ an ist (`Vog.VPo.Lief.AdrNr`).
- Umsatz-Exporte für Artikel, Lager, Adressen, Warengruppen, Vertreter, Kostenstellen (Register „Umsatz“).
  Kennzeichen „Ausgabe über Feld ‚Letzter Umsatz‘ beschleunigen“ filtert über das Feld „Letzter Umsatz“ – kann
  inkonsistent sein (DB-Manager › „Letzter Umsatz neu aufbauen“).
- Artikelbilder (`Art.Bild`) werden als JPG neben die Exportdatei gelegt.
- Dateiname per Formel mit Zeitstempel, z. B. `C:\temp\Adressen $Replace($getAktDate(Time),:,_).xlsx`.
  Zeitplan z. B. `07:00-19:00 (00:01)` = jede Minute.
- **Für Datenmonster:** genau unser Hotfolder-Weg (Konvertierungen/FileConnector → Staging → Cockpit). Festen Dateinamen
  bevorzugen (Voll-Export überschreibt) oder Zeitstempel + Hotfolder-Abholung.

### 2.5 Ad-hoc-Export (alle Pakete, von Hand)

- START › SCHNITTSTELLEN › ADHOC EXPORTE › „… Auswahl nach Excel“ / „… Tabelle nach Excel“ – exportiert **genau die
  Spalten der aktuellen Tabellenansicht**. Mit SHIFT: Dateiname wählen. Ist die Detail-Ansicht „Umsatz“ eingeblendet,
  kommen die Umsätze mit. Recht: GLOBAL › DATEI › EXPORTE › ADHOC-EXPORTE.
- Das macht der Interessent heute vermutlich von Hand. Für Demos/Prototypen reicht das.

### 2.6 COM-Aktiv und mDL (alle Pakete, nur Windows)

- COM-Objekt `BpNT.Application` → `Init(Firmenname, "", Benutzer, Passwort)` → `SelectMand("1")` → DataSets.
- **mDL** = nur lesende Abfragesprache über COM: `BpApp.GetData("Adressen|Nr|[10000]|[]|[AdrNr]")`, Antwort als XML
  (`Definition` + `Data`). Nicht für große Mengen; keine verschachtelten Tabellen.
- microtech nennt COM „perspektivisch abgelöst“ durch GraphQL. Für uns nur Notlösung (Windows-Agent nötig).

### 2.7 Konkurrenz im eigenen Haus: microtech ERP Cloud + Dashboard Builder

- Ab Gen. 24 Build 7285 (KW 40/2026): Dashboards im Browser, **per KI-Prompt** gebaut, „ohne Formeln oder
  Datenbankwissen“. Datenbasis sind neue Tabellen **„Verkaufsstatistik (Umsatz)“** und **„Einkaufsstatistik (Umsatz)“**
  (VERKAUF › VORGÄNGE › VERWALTEN einblenden).
- Statistik wird beim Update aufgebaut (aktuelles Jahr + 2 Vorjahre), bei > 250.000 Belegen nur von Hand
  (DB-Manager › Mandant › „Umsatzstatistik neu aufbauen“).
- **Warengruppe steht nicht im Vorgang** → Statistik nimmt die **heutige** Warengruppe aus dem Artikel (historisch falsch,
  wenn umgruppiert). Gilt auch für uns!
- Abgrenzung für den Vertrieb: Dashboard Builder = Umsatzsicht in der microtech-Cloud. Datenmonster = self-hosted,
  Drilldown bis zum Beleg, Lager/Einkauf/OP/Preis-Cockpits, Warnungen, Zurückschreiben, mehrere Systeme kombinierbar.

---

## 3. Wo steckt was? (Datenmodell)

| Fachlich | GraphQL-Tabelle | DB-/Replikationsname (deutsch) | Schlüssel / Hinweise |
|---|---|---|---|
| Artikel | `tblProducts` | `artikel` (Umsatz: `artikel_ums`) | `ArtNr`; Sortierfolgen `byNr`, `byNrNum`; `LagKz`, `LagNr`, `LiefNr` (Standard-Lieferant), `SuchBeg` |
| VK-Preise | in `tblProducts` | in `artikel` | **3–10 Preisstufen** je Artikel (DB-Manager › Artikel › „Verkaufspreise/Rabatte“), Felder `Vk0_Preis` … ; je Stufe Mindestpreis; eine Stufe ist „Standard“, Adresse kann Preisstufe vorgeben. Beträge netto **oder** brutto gespeichert (`aco…isCalculatedAndStoredAsGross`). |
| Weitere Preise | `tblCommodityPrices`, `tblSurchargeCalculations`, `tblSurchargeGroups`, `tblCalculationSchemes`, `tblRoundingGroups` | – | Rohstoff-/Zuschlagspreise, Kalkulationsschemen. Kundenpreis „mit aller Logik“ gibt es **nicht** per API. |
| Adressen | `tblAddresses` | `Adressen` | `AdrNr`; `Status` (Kunde, Lieferant, Interessent …); AdrNr wird bei Status „Kunde“ automatisch vergeben |
| Anschriften | `tblPostalAddresses` | `Anschriften` | `AdrNr`+`AnsNr`; Name `Na2`, `Str`, `PLZ`, `Ort`, `Tel`, `EMail1`; `StdReKz`/`StdLiKz` = Standard-Rechnungs-/Lieferanschrift |
| Ansprechpartner | `tblContactPeople` | (Ansprechpartner) | `AdrNr`+`AnsNr`+`AspNr` |
| Vorgänge (offen/Übersicht) | `tblTransactions` | (Vorgang) | `BelegNr`, `Art` = Vorgangsart-Nummer (z. B. 50 Lieferschein laut Beispiel), `DokGUID` |
| Vorgangspositionen | `tblTransactionItems` (verschachtelt) | flach mit Endung | `EPr` Einzelpreis (Betragsgruppe), `Bez` |
| **Vorgangsarchiv** | `tblTransactionsArchive` | (Archiv) | **getrennte Tabelle!** siehe Abschnitt 4 |
| Vorgangsarten | `tblTransactionTypes` | – | Parametertabelle |
| Buchungsparameter | `tblPostingParameters` | – | steuern Lager, OP, FiBu, Archiv |
| Lager | `tblWarehouses` (Bestand je ArtNr+LagNr: `Mge`, `MinMge`), `tblMasterWarehouses`, `tblWarehouseSlotInventory` | – | Sortierfolge `byArtNrLagNr` |
| Offene Posten | `tblOpenItems` | – | Adresse › `lnkOpenItems` › `rowBelegNr` → Vorgang |
| Dokumente / PDFs | `tblDocuments` | – | über `fldDokGUID` aus dem Vorgang |
| Projekte | `tblProjects`, `tblProjectsArchive` | – | |
| Mandant | `tblClient` | – | genau ein Datensatz |
| Stammtabellen | `tblPaymentTerms`, `tblPaymentMethods`, `tblCurrencies`, `tblUnitsOfMeasure`, `tblShippingTypes`, `tblValueAddedTaxTypes`, `tblDunningLevels`, `tblUsers` … | – | |
| Freie Tabellen | `tblCust<Name>` | eigener Name | nur mit GraphQL-Bezeichnung |
| Umsätze | Detail-Ansicht „Umsatz“ bei Artikel/Adresse/Warengruppe/Vertreter/Kostenstelle | `*_ums` | vorverdichtet; neu: Verkaufs-/Einkaufsstatistik |

Die exakten Spaltennamen liefert später die Replikation (oder GraphQL-Introspection:
`{ __type(name: "Query") { fields { name description } } }`).

---

## 4. Vorgänge, Buchen, Wandeln, Archiv – wann wandert was wohin?

**Grundbegriffe:**
- **Buchen** = Abarbeiten der **Buchungsparameter** der Vorgangsart: Lager bewegen, Offene Posten anlegen, FiBu-Protokoll
  („Auftragsbuchungsliste“), Statistik usw. (PARAMETER › VORGÄNGE › BUCHUNGSPARAMETER; Zuordnung zur Vorgangsart unter
  PARAMETER › VORGÄNGE › ARTEN, Register „Parameter“).
- **Wandeln** = Vorgang in andere Art überführen (Angebot → Auftrag → Lieferschein → Rechnung). Bereits gebuchte
  Parameter werden im neuen Vorgang als erledigt markiert (keine Doppelbuchung).
- Drei Register in der Vorgangsbearbeitung: **„Vorgänge“** (Übersicht), **„Zwischenbelege“**, **„Archiv Vorgänge“**.

**Wann landet ein Vorgang im Archiv?** (alles je Vorgangsart einstellbar → beim Kunden nachsehen!)

1. **Nach dem Buchen** – Parameter „Register: für das Buchen dieses Vorgangs“ bietet:
   - Vorgang **in Archiv verschieben** (ersetzen falls vorhanden)
   - Vorgang **nach Zwischenbelege verschieben**
   - Vorgang **in Archiv kopieren** (→ steht dann in Übersicht **und** Archiv!)
   - Vorgang **löschen** (gegen Rückfrage)
   - Option: Buchen erst **nach dem Drucken**.
2. **Beim Wandeln** – Register „für das Wandeln in diesen Vorgang“:
   - „Vorgang **vor dem Wandeln** in Vorgangsarchiv kopieren (ersetzen falls vorhanden)“ – nur dann bleibt der Quellvorgang
     erhalten und das Wandeln steht im Vorgangsprotokoll.
   - Positionen in neuen Vorgang **verschieben** (Quelle ist danach weg, außer vorher archiviert) oder **kopieren** (Quelle bleibt).
   - „Vorgang nach **Komplettlieferung/letzter Teillieferung** in Archiv kopieren“ (typisch Kundenbestellung → Lieferschein;
     sonst ist die Bestellung nach der letzten Lieferung einfach weg).
   - Teillieferung: Geliefert- und Rückstandspositionen können erzeugt werden.
3. **Sammelrechnung/Einladen**: „Vorgänge nach dem Einladen in Archiv verschieben“ – oder „… **löschen**“ (unwiderruflich!).
4. **Von Hand**: Schaltfläche IN ARCHIV VERSCHIEBEN; per API `fnMoveToArchive`.
5. **AutoArchivierung** (PARAMETER › SONSTIGE › AUTO ARCHIVIERUNG): für Vorgänge, Kalender, Kontakte, Projekte, Versand,
   Ausgabeverzeichnis. Datensatz wird nach „Anzahl der Tage“ seit Erstellung als **erledigt** markiert und nach weiterem
   „Mindestalter in Tagen“ archiviert. Datum: Belegdatum (oder letztes Änderungsdatum, wenn so eingestellt). Formel je
   Vorgangsart möglich (z. B. `«Art»=50` für Lieferscheine). Läuft **beim Wechsel des Arbeitsdatums / nach der Anmeldung**,
   nicht nachts per Dienst (außer manuell / Startsequenz). microtech empfiehlt das z. B. für alte offene Angebote.

**Zurück aus dem Archiv:** ÄNDERN im Archiv erzeugt eine **Kopie** in der Übersicht (bei gebuchten Vorgängen mit
„stornieren & ändern“), „In Übersicht kopieren“, oder (Parameter) „Archiv-Vorgänge direkt wandeln“. `CopyFromArchiv`
(COM) vergibt eine **neue Belegnummer**.

**Storno / Gutschrift:** Stornieren kann Gutschrift erzeugen und das Original ins Archiv schieben. Rechnung → Gutschrift
**am selben Tag mit gleichem Betrag** entfernt die Rechnung aus FiBu-Protokoll und RA-Journal (außer Parameter
„Datensätze in History … nicht stornieren“ ist gesetzt).

### Folgen für unsere Cockpits

- **Umsatz = Übersicht ∪ Archiv (∪ Zwischenbelege)** – nie nur eine Tabelle lesen.
- **Doppelte** möglich (Modus „in Archiv kopieren“, „vor dem Wandeln kopieren“, „ersetzen falls vorhanden“) →
  nach `BelegNr` (und Vorgangsart) entdoppeln, Archiv-Stand bevorzugen bzw. jüngsten Stand.
- **Fehlende** möglich (Modus „löschen“, „verschieben“ ohne vorheriges Archivieren, Sammelrechnung mit Löschen) →
  Auftragseingang/Angebote historisch nicht vollständig rekonstruierbar. Für Umsatz besser auf **Rechnungen/Gutschriften**,
  auf die Umsatztabellen (`*_ums`) oder die neue **Verkaufsstatistik** stützen.
- „Gebucht“ ist ein eigener Zustand – Kennzeichen im Vorgang prüfen (gebucht/ungebucht), sonst zählen Entwürfe mit.
- Warengruppe historisch nicht im Vorgang → Auswertung nach Warengruppe immer mit **heutiger** Zuordnung (im Cockpit sagen).
- LSN/RefNr nicht als Schlüssel; nach Reorganisation alles neu laden.
- Vorgangsart-Nummern sind kundenindividuell erweiterbar („Freier Typ“) → Mapping-Tabelle Art → Kategorie
  (Angebot/Auftrag/Lieferschein/Rechnung/Gutschrift) je Kunde pflegen, wie bei JTL.

---

## 4a. Historische EK-/VK-Preise – Quellen für einen Preisverlauf

| Quelle | Was steht drin | Voraussetzung / Haken |
|---|---|---|
| **Artikel-Preisverlauf** (Tabelle, VERKAUF › STAMMDATEN › ARTIKEL › VERWEISE: VERWALTEN › ARTIKEL PREISVERLAUF; auch als Detail-Ansicht) | VK je **Preisgruppe** und **Tag** (1 Datensatz pro Tag und VK-Preisgruppe), Server-Datum; beim ersten Änderungsfall wird auch der alte Preis als Startwert eingestellt; Sonderpreise mit Von/Bis als eigener Datensatz | Ab Build 6810, Stufe XL bzw. Gen. 24 Core+. Füllt sich **nur**, wenn eine Automatisierungsaufgabe „**Überwachung für Artikel-Preisverlauf**“ (Laufzeit kontinuierlich) läuft – **keine Rückwirkung** davor. Gedacht für PAngV („niedrigster Preis 30 Tage“, Funktion `CalcNiedrigsterPreis(ArtNr\|Tage)` in Export/Druck). Manuell nachpflegbar. Nur VK, kein EK. |
| **Vorgangspositionen** (Übersicht + Archiv) | tatsächlich berechneter **Einzelpreis** (`EPr`), Rabatt, Roherlös/„EK für Roherlöse“ je Position mit Belegdatum | Rückwirkend vorhanden, soweit Vorgänge nicht gelöscht wurden (Abschnitt 4). **Achtung:** Buchungsparameter „Roherlös EK-Preise immer aktualisieren“ / „Kalkulations-EK-Preise immer aktualisieren“ → EK in alten Vorgängen kann beim Öffnen **überschrieben** werden. |
| **Einkaufsvorgänge** (Bestellung, Wareneingang, Eingangsrechnung) | tatsächlich gezahlter EK je Lieferant und Datum | Bester rückwirkender EK-Verlauf; Union Übersicht + Archiv nötig. |
| **Lagerbuch** (Lagerbewegungen) | je Bewegung **„Einzel-Einkaufspreis“** (EK zum Zeitpunkt der Bewegung) und **„Einkaufswert“** (MEK nach Bewegung × Gesamtmenge) | Stufe XL. Liefert MEK-Verlauf je Artikel. „Nachträgliche Lagerbewertung“ kann den MEK zu einem Datum manuell setzen. |
| **Lagerbestand mit EK** | bei jedem Zugang eigener Bestandsdatensatz mit EK (FIFO) | Stufe XL; Chargen gleichen Verfallsdatums werden gemittelt. |
| **History** (VERKAUF › ÜBERBLICK/STAMMDATEN › HISTORY) | Warenbewegungen als Zu-/Abgänge, Grundlage für Beschaffungs-/Verkaufsauswertungen | Nur wenn Vorgangsart **und** Artikel (History-Kennzeichen) dafür eingestellt sind; Einträge auch von Hand änderbar. |
| **Artikelstamm heute** | aktuelle VK-Stufen (`Vk0_Preis` …), Roherlös je Stufe (`RohSz`, `RohBet`), Artikel-Lieferanten-EK (EK0 …, effektiver EK mit Zuschlag), „EK für Roherlöse“ (z. B. MEK) | Nur aktueller Stand – für einen Verlauf ab jetzt selbst täglich **Schnappschuss** ziehen (Datenmonster-Zeitplan). |
| **SQL-Replikation** | bildet nur den **aktuellen** Stand ab, keine Historie | Historie nur über obige Tabellen (Preisverlauf, Lagerbuch, Vorgänge), die ja mit repliziert werden. |

**Vorgehen für ein Preisverlauf-Cockpit:**
1. **VK-Listenpreis:** Artikel-Preisverlauf, falls die Überwachung beim Kunden schon läuft; sonst ab sofort einschalten lassen
   **und** parallel eigenen Tages-Schnappschuss der VK-Stufen in Datenmonster speichern.
2. **Erzielter VK:** aus Rechnungs-/Gutschriftspositionen (Übersicht ∪ Archiv), Durchschnitt je Artikel und Monat – rückwirkend.
3. **EK:** aus Einkaufsvorgängen (Lieferant, Datum, Preis) bzw. Lagerbuch „Einzel-Einkaufspreis“ und MEK-Verlauf – rückwirkend.
4. Marge im Zeitverlauf = 2 − 3; Vorsicht bei „EK für Roherlöse“ in alten Positionen (siehe oben).

## 5. Empfehlung für den Datenmonster-Weg

1. **Enterprise beim Kunden?** → SQL-Replikation in eine PostgreSQL (kann in unserem Docker-Stack laufen) →
   Vorlage „büro+ Cockpits“ mit SQL direkt auf das Replikationsschema; eigene Views in eigenem Schema.
   Schreibwünsche später über GraphQL.
2. **Core / Gen. 20 XL?** → ADO-Export zeitgesteuert in eine SQL-Server-/ODBC-Staging-DB **oder** Export-Layouts
   (CSV/SDF/Excel) zeitgesteuert in einen Ordner → Datenmonster-Hotfolder → Staging → Cockpits.
3. **Basic / kleiner?** → Export-Layouts von Hand oder Ad-hoc-Excel in den Hotfolder (halbautomatisch).
4. In jedem Fall: Vorgänge **und** Archiv exportieren, Positionen mit, Adressen+Anschriften, Artikel inkl. VK-Preise,
   Lager, Offene Posten.

## 6. Offene Fragen an den Interessenten

- Generation, Paket, Build-Nummer? Läuft ein Datenserver? Wer ist der microtech-Partner?
- Welche Auswertungen baut er heute von Hand in Excel? (→ erstes Cockpit)
- Buchungsparameter je Vorgangsart: verschieben, kopieren oder löschen nach dem Buchen? AutoArchivierung aktiv?
- Anzahl VK-Preisstufen und welche ist Standard? Netto- oder Bruttopreise?
- Läuft die Automatisierungsaufgabe „Überwachung für Artikel-Preisverlauf“? Ist „Roherlös EK-Preise immer aktualisieren“ gesetzt?
- Gibt es Selektionsfelder / Freie Tabellen, die wichtig sind?
- Mehrere Mandanten / Filialen?

## 7. Wichtigste Hilfeseiten

- SQL-Replikation: /04_moduluebergreifend/sql-replikation/ (+ `glsqlreplikationfaq`, `sqlreplikationaenderungenderschemaversionen`, `sqlreplikationsereignisprozeduren`, `glsqlreplikationstandardvorgabe`)
- GraphQL: /18_graphql/ (`graphqldoku`, `graphqlmutations`, `graphqlbeispielqueries`, `graphqlendpunkteinrichten`, `oauthapidoku`, `graphqlvorgangfunktionsreferenz`, `graphqladressverwaltungbsp`, `graphqlopbelegkunden`, `graphqlparametertabellenauslesen`, `graphqlfaq`) – Seiten gibt es auch als `…/index.md`
- Export/Import: /04_moduluebergreifend/eintr auf datei_ansicht/datei/schnittstellen/ (`export`, `gladoselect` = ADO)
- Ad-hoc: /020_basis/bedienung/die-grundlagen-der-hauptmasken/menueband/start/verweise/adhoc_exporte/
- Automatisierung: /04_moduluebergreifend/prozessautomatisierung/
- Archiv: /020_basis/vorgaenge/vorgangsbearbeitung/die-register-des-bereichs-vorgangsbearbeitung/archiv-vorgaenge/
- Buchungsparameter: /04_moduluebergreifend/parameter/vorgaenge/buchungsparameter/
- AutoArchivierung: /04_moduluebergreifend/parameter/sonstige/glparamautoarchivierungen/
- COM/mDL: /19_comaktiv/ · ERP Cloud Dashboards: /20_microtech_erp_cloud/dashboards/
- Sitemap (3.600 Seiten): https://hilfe.microtech.de/sitemap.xml
