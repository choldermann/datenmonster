# Datenmonster – Was die Plattform kann

Stand: 2026-08-27 · Version 1.0.2 · Holdermann IT

Datenmonster ist eine selbst gehostete ETL- und BI-Plattform: Daten aus beliebigen
Quellen holen, im visuellen Editor umbauen, zurückschreiben oder exportieren,
per Zeitplan automatisieren und als Formular, Dashboard oder Portal-Seite
ausliefern – mit KI-Unterstützung an allen Stellen, an denen sonst Handarbeit
oder SQL-Kenntnisse nötig wären.

---

## 1. Datenquellen und Konnektoren

### Datenbanken
- **Microsoft SQL Server** (pyodbc)
- **MySQL / MariaDB**
- **PostgreSQL**
- **SQLite**
- **Microsoft Access** (.mdb / .accdb, eigener Import-Bereich)

Je Verbindung: Verbindungstest, automatischer Schema-Cache (Tabellen, Spalten,
Typen, Primär-/Fremdschlüssel), Cache-Alter sichtbar, Neuaufbau per Knopfdruck,
Tabelle direkt als Dataset importieren. Zugangsdaten liegen verschlüsselt
(Fernet, abgeleitet aus dem SECRET_KEY).

### Dateien
- CSV, Excel (.xlsx/.xls), ODS, XML, JSON, Parquet
- Upload im Browser oder Abholung per FTP/SFTP
- Statische Datasets: Tabellen, die direkt im Browser gepflegt werden

### Weitere Quellen
- **REST-API** (GET/POST, Bearer-/Basic-Auth, JSON-Pfad-Extraktion, Paginierung)
- **E-Mail / IMAP** – Mail-Connector, regelbasierte Anhang-Verarbeitung
- **HTML-Seiten** – Web-Scraper mit visuellem Selektor
- **FTP / SFTP** – Dateien holen und ablegen, als Quelle *und* Ziel
- **Plugins** – z. B. MongoDB-Connector, eStatistik-Core, Faker-Quelle

---

## 2. Datasets

- Anlegen aus Datei-Upload, SQL-Abfrage, REST-Aufruf, Plugin oder manuell
- **KI-Dataset-Assistent**: Beschreibung in Alltagssprache → KI schlägt Tabellen
  vor (Stichwort- und Fremdschlüssel-Expansion, deutsches Stemming) → generiert
  fertige SELECT-Abfragen, die vor dem Anlegen bearbeitet werden können
- **Database Analyzer**: interaktives ER-Diagramm, Beziehungen sichtbar machen,
  Pfadfinder mit Zwischenstationen, Dataset direkt aus dem Diagramm erzeugen
- Schema-Editor: Spaltentypen, Pflichtfelder, PK/FK-Kennzeichnung
- Daten-Explorer mit Inline-Vorschau, Suche und Sortierung
- Zeilen-Editor für statische Datasets
- Automatische Aktualisierung per Zeitplan

---

## 3. Mapping-Editor (der ETL-Canvas)

Visueller Flow-Editor: Quellen und Verarbeitungsschritte per Drag & Drop,
Felder per Klick oder Ziehen verbinden.

### Verfügbare Nodes
| Node | Funktion |
|---|---|
| **Dataset** | Quelle aus Dataset, DB, Datei, REST oder Plugin; filter- und sortierbar |
| **Params** | Laufzeit-Parameter, die beim Ausführen abgefragt oder vom Formular geliefert werden |
| **Transform** | Feldzuordnung, Umbenennen, Typen, Standardwerte, String-/Zahlen-/Datumsoperationen |
| **Konstante** | Fester Wert oder berechneter Ausdruck als zusätzliche Quelle |
| **Ausdruck** | Formelsprache: `{feld}`, `upper()`, `if_()`, `concat()`, `today()` u. v. m. |
| **Berechnung** | Fensterfunktionen: kumulierte Summe, gleitender Durchschnitt, Zeilennummer, Rang, Lag/Lead |
| **Aggregation** | GROUP BY mit SUM, COUNT, AVG, MIN, MAX, DISTINCT |
| **SQL** | Direkte SQL-Abfrage auf einer DB-Verbindung; als Quelle, Lookup (`:param`, zeilenweise oder Batch-IN) oder ausführender Schritt (Stored Procedure) |
| **Lookup** | Nachschlagen in einem anderen Dataset |
| **Python** | Beliebiges Python je Datensatz, in einer Sandbox mit Zeitlimit |
| **REST** | HTTP-Aufruf als Anreicherungsschritt |
| **Switch** | Verzweigung nach Bedingungen, mehrere Ausgänge |
| **Datenqualität** | Regeln je Feld (Pflicht, Zahl, E-Mail, IBAN, EAN, Regex …), liefert Gültigkeitsflag und Fehlerliste |
| **KI-Transform** | Feldwerte durch ein Sprachmodell erzeugen, `{{feld}}`-Vorlage, strukturierte Ausgabe |

### Canvas
- Zoom, Verschieben, Minimap, Nodes minimieren/aufklappen
- Verbindungen per Klick löschen, Vorschau an jeder Verbindungslinie
- Automatische Join-Erkennung beim Hinzufügen weiterer Datasets
- Primär-/Fremdschlüssel werden erkannt und als Kennzeichen angezeigt
- Anti-Join (LEFT ANTI / RIGHT ANTI)
- Filter-Pushdown in die Datenbank statt Filtern im Speicher
- Typkonvertierung je Verbindung mit Warnung bei Typkonflikten
- Mehrere Ziele pro Mapping
- Export und Import ganzer Mappings als Vorlage

### Debug-Lauf
- Stufenweiser Durchlauf mit Stichprobendaten je Stufe
- Zeilen rein/raus und Fehler je Node
- Einzelnen Datensatz durch alle Stufen verfolgen (Row Inspector, Step-Through)
- SQL-Nodes sind im Ablaufprotokoll enthalten

---

## 4. Ziele – wohin die Daten geschrieben werden

- **Dataset** (Anhängen, Ersetzen, Upsert nach Schlüssel)
- **Datenbank**: Insert, Truncate+Insert, Update, Upsert, Delete
- **Dateien**: CSV, Excel, JSON, XML, Parquet
- **Amtliche Formate**: Destatis-CSV, Intrahandels-CSV, IDEV (`.idev`)
- **FTP/SFTP-Ablage**
- **Plugin-Ziele** (z. B. MongoDB-Collection)

Alle erzeugten Dateien landen in einer Export-Liste mit Download.

---

## 5. Automatisierung

- **Pipelines**: mehrere Mappings sequenziell oder parallel verketten;
  Node-Typen für Trigger, Mapping, Bedingung, FTP, REST-Abruf, Dispatcher,
  Business-Insights und Ausgaben
- **Scheduler**: Mappings und Pipelines per Cron-Ausdruck; Verlauf der letzten Läufe;
  nächster Lauf wird aus dem Scheduler ausgewiesen
- **Dispatcher**: eingehende Dateien anhand von Regeln (Dateiname, Inhalt, XML-Struktur)
  automatisch dem richtigen Mapping zuordnen, inklusive Folgeaktionen
- **Eingehende REST-Schnittstelle**: eigene Endpunkte, Daten per POST annehmen und
  ein Mapping auslösen
- **Ereignis-Bus** für interne Auslöser

---

## 6. Formulare, Dashboards und Portal

### Formular-Editor
Drei-Spalten-Oberfläche (Palette | Canvas | Eigenschaften), Raster-Layout,
Feldsichtbarkeit je Reiter.

**Feldtypen**
- Eingabe: Text, mehrzeiliger Text, Zahl, Datum, Uhrzeit, Dateiauswahl
- Auswahl: Checkbox, Schalter, Dropdown, Mehrfachauswahl, Radio
- Dashboard-Filter: Zeitraum (Kalender-Popover), DB-Auswahl mit Tippsuche
  (Werte kommen live aus der Datenbank, auch mehrfach wählbar)
- Aktionen: Button
- Layout: Überschrift, Text, Trennlinie, Container

**Aktionen**: Mapping ausführen, Pipeline ausführen, Warnungen auswerten,
Mapping exportieren. Ergebnisse können auf Reiter verteilt werden.

### Widgets
| Widget | Zweck |
|---|---|
| **Tabelle** | sortierbar, klickbar, volle Zeilenzahl statt Vorschau, Download |
| **KPI** | Kennzahl mit Vorjahresvergleich |
| **Balken / Linie / Kreis** | Diagramme, klickbar für Drilldown |
| **KI-Analyse** | Sprachmodell kommentiert die Zahlen des Dashboards; knapp oder ausführlich, mit Bewertungstabelle |
| **Aufgabenliste** | Ampel mit Anzahl, Klick öffnet die Detailliste |
| **Unternehmenswarnungen** | Ergebnisse der Warn-Engine |
| **Kostenstruktur** | monatliche Fixkosten je Kostenart pflegen |
| **Eingangsrechnungs-Freigabe** | E-Rechnung prüfen und übernehmen |
| **EAN-Recherche / Hersteller-Navigator / Stammdatenprüfung** | Stammdaten anreichern |

### Drilldown und Interaktion
- Mehrstufiger Drilldown bis auf Belegebene (Navigations-Stack)
- KI-Handlungsempfehlung je Tabellenzeile
- Tabelle per E-Mail versenden
- **PDF-Report**: komplettes Dashboard inklusive Diagrammen, KI-Analyse und
  Bewertungstabelle als PDF, mit Firmendaten aus der Wawi

### Portal
- Formulare veröffentlichen, eigene URL, mehrere Formulare je Portal
- Portal-Benutzer sehen nur das Portal, keinen Editor
- Vollständige Funktionsgleichheit: Drilldown, KI-Empfehlung, PDF-Report,
  Export und Ausschlusslisten funktionieren auch dort
- Formular-Einreichungen werden gespeichert und sind einsehbar

---

## 7. Betriebswirtschaftliche Auswertung (BI)

- **Warn-Engine**: Regeln auf Kennzahlen und Listen, Schweregrade, Fakten je
  Warnung, Drilldown; nächtlicher Lauf mit Vergleich zum Vortag
  („neu seit gestern"), Läufe werden archiviert
- **Zentrale Schwellwerte**: einmal gepflegt, von allen Regeln und Cockpits genutzt
- **Kostenstruktur**: 25 vorbereitete Fixkostenarten plus eigene, jeweils mit
  „gültig ab"-Zeitleiste; fließt als Parameter in die Auswertungen
- **Unternehmensziele** hinterlegen
- **Business-Insights-Node**: fertige Analysen (Umsatz, Länder, Top-Kunden,
  Lagerbestand) mit semantischer Feldzuordnung und Voreinstellungen

---

## 8. Künstliche Intelligenz

### Anbieter
- **Ollama**, lokal im eigenen Container – keine Daten verlassen den Server
- **Datenmonster AI** – gehosteter Gateway über monstersuite mit Guthaben (Credits),
  Verbrauchsanzeige, Paketkauf und Rechnung
- Anbieter ist pro Oberfläche wählbar; getrennte Modelle für Code und Fließtext;
  Modelle lassen sich vorwärmen, damit der erste Aufruf nicht ins Timeout läuft
- Modellverwaltung im UI: installieren, wechseln, Download-Fortschritt

### Wo die KI hilft
- SQL erklären und generieren, Python erzeugen, Fehler erklären
- Ausdruck für den Ausdrucks-Node vorschlagen
- Feldverknüpfungen vorschlagen (Smart Mapping), ganze Nodes generieren
- Datasets und Tabellen zu einer Beschreibung vorschlagen
- Daten zusammenfassen und bewerten (Dashboard-Analyse, Lagebericht)
- Handlungsempfehlung zu einer einzelnen Zeile (Kundenrückgang, Ladenhüter, Winback)
- Artikelbeschreibungen vorschlagen
- Schema-Katalog: Tabellen und Spalten beschreiben, Beziehungen vorschlagen
- Schwebender KI-Assistent als Chat über die ganze Anwendung

### KI-Gedächtnis
- Wissensdatenbank mit Fachregeln (z. B. JTL-Besonderheiten)
- Lösungsarchiv und Korrekturen, die in künftige Antworten einfließen
- Kontextauswahl nach Stichwörtern und Token-Budget statt „alles mitschicken"
- Antwort-Cache mit Trefferquote, Vorschau des tatsächlich gesendeten Kontexts

---

## 9. Schema-Katalog

- Datenbankschema einlesen und dauerhaft dokumentieren
- Tabellen und Spalten beschreiben (manuell oder per KI)
- Beziehungen pflegen, **aus Schlüsseln ableiten** (Fremdschlüssel plus
  Namensgleichheit mit Primärschlüsseln), Massenübernahme
- Katalog exportieren und importieren

---

## 10. API Studio

Ein vollwertiger REST-Arbeitsplatz in der Anwendung:
- Sammlungen und Umgebungen (Variablen, Geheimnisse maskiert)
- Anfragen senden, Verlauf mit Wiederholung
- **Analyse und Fehler-Debugger** für fehlgeschlagene Aufrufe
- Variablen vorschlagen lassen, Sammlung befragen („was macht dieser Endpunkt?")
- **OpenAPI-Import**: Spezifikation einlesen, Sammlung erzeugen
- **Verkettung**: mehrere Aufrufe hintereinander, Vorschau und Anlegen
- **Integration erstellen**: aus einem Aufruf direkt Dataset, Mapping und
  Pipeline generieren

---

## 11. Vorlagen (Templates) und Store

Fertige Lösungspakete, die Mappings, Formulare, Pipelines und Verbindungen in
einem Rutsch installieren. Beim Installieren wird abgeglichen statt doppelt
angelegt.

**Ausgelieferte JTL-Wawi-Vorlagen**
| Vorlage | Inhalt |
|---|---|
| **GF-Cockpit** | Übersicht, Ergebnis (Betriebsergebnis und Break-even nach Fixkosten), Kundenentwicklung, Umsatzanalyse, Kapitalbindung, Einkauf & Verbindlichkeiten, Offene Posten, Retouren, Mitarbeiter, Ausblick (Hochrechnung, Churn), Warnungen – 67 Mappings |
| **Vertriebs-Cockpit** | Auftragseingang, Auftragsbestand, Angebote mit Nachfassliste, Kunden, Artikel, Mitarbeiter – 31 Mappings |
| **Einkaufs-Cockpit** | Bestellvolumen, offene Bestellungen mit Verzug, Termintreue aus echten Wareneingängen, Verbindlichkeiten, EK-Preisentwicklung – 21 Mappings |
| **Lager-Cockpit** | Lagerwert zum Stichtag (bewertet zum historischen EK), Disposition, Umschlag und Reichweite, Preisverlauf EK gegen VK – 26 Mappings |
| **Versand-Cockpit** | Sendungsaufkommen je Versandart, Durchlaufzeit, Tracking-Qualität, Rückstand – 11 Mappings |
| **Health-Check** | Artikel- und Kundenstammdaten auf Lücken prüfen: EAN, Gewicht, EK, VK unter EK, Warentarifnummer, Herkunftsland, Dubletten – 26 Mappings |
| **Intrastat** | Ausfuhr und Einfuhr, eSTATISTIK.core und Destatis-CSV, Zeitraum-Formular, Monats-Pipelines |

Dazu: eigene Vorlagen erstellen und hochladen, In-App-Store mit den über
monstersuite gekauften Paketen.

---

## 12. Fachmodule

### Intrastat
Ausfuhr- und Einfuhrmeldung, Ausgabe als IDEV-Datei oder Destatis-CSV,
Ausschlussliste für Artikel, die nicht in die Statistik gehören,
Datenqualitätsprüfung mit Herkunftsland-Ersatzwert.

### Eingangsrechnungen (E-Rechnung)
ZUGFeRD/Factur-X (CII) und XRechnung (UBL) einlesen, Positionen den
Bestellungen zuordnen, Artikelsuche, Vorschau vor dem Schreiben, Übernahme in
die Wawi.

### Stammdaten-Rückschreiben
Änderungen direkt in die Warenwirtschaft schreiben, Kollisionsschutz über
Zeilenversion, Trockenlauf mit Plan-Vorschau vor der Ausführung.

### Produktrecherche
Herstellerseiten auswerten (robots.txt wird beachtet) und EAN, Warennummer,
Herkunftsland und Gewicht vorschlagen – jeweils mit **Sicherheitsgrad**
(gesichert / prüfen / ungesichert) statt blinder Übernahme.

---

## 13. Plugins

- Ein einheitlicher Katalog mit „Aktiv" und „Verfügbar"; ob ein Plugin im
  Backend eingebaut oder extern ist, bleibt Interna
- Eingebaut: Mail-Connector, Web/HTML-Connector
- Extern (`manifest.json` + `connector.py`): MongoDB, eStatistik-Core, Faker
- Installation per Datei-Upload; lizenzgeprüfte Auslieferung über monstersuite

---

## 14. Benutzer, Projekte, Lizenz

- **Mehrmandantenfähig**: Projekte kapseln Datasets, Mappings, Formulare
- Benutzerverwaltung, Administrator- und Portal-Rolle, Projektfreigabe,
  Passwortänderung
- **Lizenzierung** über monstersuite: Aktivierung per Schlüssel, tägliche
  Neuvalidierung, 14 Tage Kulanzzeit bei Serverausfall, danach Rückfall auf den
  kostenlosen Plan. Freischaltbare Funktionsbereiche: unbegrenzte Projekte,
  DB-Schreiben, Pipelines & Scheduler, FTP/SFTP, REST-Quellen, Mail, KI-Assistent,
  KI-Wissensdatenbank, Schema-Katalog, Formular-Builder & Portal, erweiterte
  Plugins, mehrere Benutzer, erweitertes Monitoring

---

## 15. Betrieb

- **Monitoring**: CPU, Arbeitsspeicher, Plattenplatz, Datenbankgröße, Laufzeit
- **Systemprotokoll** mit Projektspalte, Ausführungshistorie
- **Update-Funktion in der Anwendung**: Version prüfen, Änderungsliste ansehen,
  installieren – Auslieferung über GHCR und CI/CD
- Onboarding: Erste-Schritte-Checkliste und Leerzustände mit Hinweisen

---

## 16. Technischer Unterbau

| Schicht | Technologie |
|---|---|
| Backend | FastAPI, SQLAlchemy, SQLite |
| Frontend | React, Tailwind CSS |
| Verarbeitung | pandas (Joins und Transformationen im Prozess) |
| KI | Ollama lokal oder Datenmonster-AI-Gateway (OpenAI-kompatibel) |
| Zeitsteuerung | APScheduler |
| PDF | xhtml2pdf und matplotlib |
| Betrieb | Docker Compose, nginx mit SSE-Unterstützung |
