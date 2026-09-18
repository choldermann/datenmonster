# Lagermonster – Architekturvorschlag

**Stand:** 18.09.2026 · **Status:** Entwurf zur Freigabe, noch keine Implementierung
**Entscheidung (Anwender, 18.09.):** Lagermonster wird **Teil von Datenmonster**: ein fest eingebautes
Kern-Modul nach dem Muster der Inventur, darüber ein verkaufbares, signiertes Template.

> „Lagermonster – die einfache Lagerverwaltung für Lexware Office.“
> Kein ERP. Lexware bleibt zuständig für Angebote, Aufträge, Rechnungen und Buchhaltung.

Kennzeichnung in diesem Dokument:
- **[F]** = im Datenmonster-Code festgestellt (Stand Commit `2fba64a`)
- **[E]** = Empfehlung für Lagermonster
- **[?]** = nicht sicher festgestellt oder offene Frage

---

## 1. Ausgangslage

### 1.1 Warum kein reines Template [F]
Ein Template bringt Mappings, Formulare, Widgets, Warnregeln und Wissen mit. Für eine Lagerverwaltung reicht das
nicht, und zwar aus folgenden Gründen:

| Anforderung | Stand in Datenmonster |
|---|---|
| Eigene Tabellen anlegen und migrieren | Geht nicht. Templates haben keine DDL und keine Schema-Version. |
| Buchung mit Bestandsprüfung in einer Transaktion | Geht nicht. `exec`-Knoten und `export_to_db` prüfen weder eine Bedingung noch die Anzahl betroffener Zeilen. |
| Interne Datenbank lesen | Geht nicht. Einen `DbConnection`-Typ `sqlite` gibt es nicht (`db_service.get_engine_str`). |
| Scanner-Feld (Enter löst Aktion aus) | Gibt es nicht. Kein Feld reagiert auf Enter. |
| Rollen pro Aktion | Gibt es nicht. Wer ein Formular öffnen darf, darf alle seine Aktionen ausführen. |
| Lexware-Webhook empfangen | Geht nicht. Es gibt keinen öffentlichen Eingang. |

### 1.2 Das Vorbild: die Inventur [F]
`models/inventur.py`, `api/inventur.py`, `services/inventur_service.py` und `widgets/InventurWidget.tsx` bilden
zusammen ein fest eingebautes Modul. Es hat eigene Tabellen (Migration über `create_all` plus ALTER-Liste in
`main.py`), eine eigene API unter `/api/inventur` mit eigener Rechteprüfung (`_darf_lesen` / `_darf_aendern`,
Portal-Nutzer mit Formularzugang dürfen pflegen) und ein Widget. Das Template `jtl_lager_cockpit.json` setzt dieses
Widget nur noch auf die Seite (`"type": "inventur"`). Eine abgeschlossene Inventur ist unveränderlich, der Verlauf
steht in `protokoll`.
**Lagermonster übernimmt dieses Muster 1:1.**

### 1.3 Was aus Lexware kommt (offizielle Doku, recherchiert 18.09.) [F]
- Die Positionen (`lineItems`) enthalten **keine Artikelnummer**. Sie tragen nur die Lexware-Artikel-UUID `id`, und
  auch die nur bei den Typen `material` und `service`. Positionen vom Typ `custom` haben keinen Bezug.
  Die Positionen selbst haben **keine eigene ID**.
- Lexware führt **keinen Lagerbestand**.
- **Webhooks:** Sie setzen eine öffentlich erreichbare HTTPS-Adresse mit gültigem Zertifikat voraus. Die Nutzlast
  enthält nur `resourceId`. Lexware wiederholt fehlgeschlagene Zustellungen bis zu etwa 2 Tage lang, deshalb sind
  **Duplikate möglich**. Die **Reihenfolge ist nicht garantiert**.
- **Storno** erkennt man am `voucherStatus = voided` (Rechnung, Gutschrift). Für eine **Korrektur** gibt es eine
  Gutschrift (höchstens eine je Rechnung). Eine offene Rechnung kann in der Lexware-Oberfläche **wieder auf Entwurf
  gesetzt** und dann geändert werden. Jeder Beleg hat `version` und `updatedDate`.
- **Kein Versandereignis.** `shippingDate` ist ein Plandatum.
- **OAuth** gibt es nur in der Partner-API: Client-ID auf Anfrage, Bedingungen nicht dokumentiert. Die Public API
  arbeitet mit einem **API-Key**. Limit: **2 Anfragen je Sekunde** über alle Endpunkte.
- Belege findet man nur über `voucherlist`: `updatedDateFrom` ist nur tagesgenau, bei 10.000 Treffern ist Schluss.
  Die Positionen muss man je Beleg einzeln per GET holen.

---

## 2. Wiederverwendung

### 2.1 Unverändert nutzen [F → E]
| Baustein | Wo | Wofür in Lagermonster |
|---|---|---|
| Anmeldung, Benutzer, JWT, Login-Sperre | `core/security.py`, `app/auth.py` | vollständig |
| Projekte und Mitgliedschaften | `api/projects.py` | Mandant = Projekt (Abschnitt 4) |
| Portal und Freigabe je Formular | `api/portal.py`, `portal_config.allowed_users` | Lagerpersonal als Portal-Nutzer |
| Portal-Sperre im Backend | `core/portal_zugriff.py` (seit 18.09.) | `/api/lager/...` eintragen |
| Template-Installation, Signatur, Store, Vorlagen-Gate | `api/templates.py`, `template_signatur.py`, `vorlagen_gate.py` | Verkauf und Freischaltung |
| Lizenz und Lizenz-Gate | `api/license.py`, `core/lizenz_gate.py` | Grundlage der Tarife (Abschnitt 9) |
| Scheduler (Jobs aus der DB, `reload_all` beim Start) | `services/scheduler_service.py` | Lexware-Abruf |
| Verschlüsselung von Zugangsdaten (Fernet) | `core/security.encrypt_credential` | Lexware-API-Key |
| REST-Wiederholung (429/5xx, `Retry-After`, Backoff) | `services/rest_service.py` | Grundlage des Lexware-Clients |
| Lexware-Fachwissen | `doku/lexware_wissen_seed.py`, Memory | Doku, Testfälle |
| Formular/Widget-Rahmen, Reiter, Mandantenkopf | `FormRunner`, `PortalRunner`, `WidgetRenderer` | Oberfläche |
| Bestätigungsdialog mit Zahlen | `widgets/BestaetigenModal.tsx` | Inventur abschließen, Storno |
| Excel/CSV-Zählliste | `inventur_service` (Zählliste/Export) | Muster für Zählliste und Import |
| API-Client und `fehlerText` | `frontend/src/api/client.js` | alle Aufrufe |
| Backup (SQLite-Backup-API) | `backup.sh`, `api/backup.py` | Lagerdaten sind automatisch mitgesichert |

### 2.2 Anpassen oder erweitern [E]
- **Kleine allgemeine Erweiterungen in Datenmonster**, von denen andere Templates ebenfalls profitieren:
  1. **Mobiles Formular-Layout:** Auf schmalen Bildschirmen belegen Widgets und Felder die volle Breite
     (colSpan = 12). **[F]** Heute gelten feste Prozentbreiten, und es gibt keine Media-Queries.
  2. **Webhook-Eingang** `POST /api/hooks/{anbieter}/{token}` mit Prüfung der Signatur. Kommt erst in Phase 7 und
     ist optional.
- **Der Inventur-Code wird nicht verallgemeinert.** Er ist JTL-spezifisch (`k_artikel`, Chargen/MHD,
  `connection_id`) und bei Kunden produktiv im Einsatz. Wer ihn umbaut, riskiert die laufende JTL-Inventur.
  Übernommen werden die **Konzepte** (Momentaufnahme, Unveränderlichkeit, Protokoll, Zählliste) und einzelne
  Oberflächenbausteine.

### 2.3 Bewusst getrennt [E]
- Die Lagerdaten liegen in **eigenen Tabellen `lager_*`**. Mappings oder Parquet-Datasets werden nicht mitbenutzt.
- Der Lexware-Connector für die Lagerbuchung ist ein **eigener, typisierter Client** und keine generische REST-Quelle.
  Grund: Idempotenz, Versionen und Diff-Buchung lassen sich mit ETL-Generik nicht sauber abbilden.
- Kein pandas im Buchungspfad.

### 2.4 Gefundene Datenmonster-Fehler (18.09. behoben) [F]
Folgende Fehler sind in `2ee2ce4` und `2fba64a` behoben:
- Portal-Sperre fehlte im Backend
- `is_active` wurde nicht geprüft
- Benutzer-Kontingent wurde nicht geprüft
- Logging war nicht konfiguriert
- `exec`- und `column`-Knoten liefen nie
- `exec` hatte keine Parameterbindung
- `[ ]`-Quoting auf Postgres
- Formulare ohne `action_ids` führten schreibende Aktionen aus
- Das Formularprotokoll ließ sich löschen

Für Lagermonster ist das die Grundlage.

---

## 3. Datenmodell [E]

Alle Tabellen liegen in der **internen Datenmonster-SQLite**, mit dem Präfix `lager_`. Jede fachliche Tabelle hat
`project_id NOT NULL` (siehe Abschnitt 4). Mengen werden als **Ganzzahl in Zehntausendsteln** gespeichert
(`menge_e4`, 1 Stück = 10000). Grund: SQLite hat keinen echten Dezimaltyp. Mit Float würden Summen über Tausende
Bewegungen driften. Lexware liefert höchstens 4 Nachkommastellen, das passt exakt. Die API rechnet nach außen in
Dezimalzahlen.

### 3.1 Tabellen

**`lager_artikel`**: Artikelstamm
| Spalte | Typ | Hinweis |
|---|---|---|
| id | int PK | |
| project_id | int NOT NULL | Mandant |
| sku | text NOT NULL | |
| name | text NOT NULL | |
| beschreibung | text | |
| ean | text NULL | wird beim Speichern geprüft (EAN-8, EAN-13); Code128 ist Freitext |
| einheit | text NOT NULL | Standardwert „Stk“ |
| ek_preis, vk_preis | int NULL | Cent |
| mindestbestand_e4 | int NULL | NULL = keine Nachbestell-Warnung |
| aktiv | bool | Deaktivieren statt Löschen |
| created_at, updated_at, erstellt_von | | |

Bedingungen:
- `UNIQUE(project_id, sku)`
- `UNIQUE(project_id, ean) WHERE ean IS NOT NULL` (partieller Index; SQLite kann das)

Indizes:
- `(project_id, aktiv, name)`
- `(project_id, ean)`

**`lager_lagerorte`**: Warehouse (für das MVP ein Lager je Projekt, das Modell ist aber für mehrere ausgelegt)
- Spalten: `id`, `project_id`, `name`, `beschreibung`, `aktiv`, `ist_standard`
- `UNIQUE(project_id, name)`. Genau ein Standardlager je Projekt; das stellt der Service sicher, zusätzlich gilt ein
  partieller UNIQUE-Index auf `(project_id) WHERE ist_standard`.
- **Später: `lager_plaetze`** (id, lagerort_id, code, …). Die Bewegungen bekommen dafür schon jetzt die Spalte
  `lagerplatz_id NULL`, damit später keine Migration der Bewegungshistorie nötig ist.

**`lager_bewegungen`**: das Journal. **Es wird nur eingefügt, nie geändert oder gelöscht.**
| Spalte | Typ | Hinweis |
|---|---|---|
| id | int PK | |
| project_id | int NOT NULL | |
| artikel_id | int NOT NULL → lager_artikel | |
| lagerort_id | int NOT NULL → lager_lagerorte | |
| lagerplatz_id | int NULL | vorbereitet |
| art | text NOT NULL | PURCHASE_IN, SALE_OUT, MANUAL_IN, MANUAL_OUT, CORRECTION, INVENTORY, TRANSFER_IN, TRANSFER_OUT, **REVERSAL** |
| menge_e4 | int NOT NULL, ≠ 0 | mit Vorzeichen: Zugang positiv, Abgang negativ |
| bestand_nachher_e4 | int NOT NULL | Bestand nach der Buchung, macht das Journal ohne Neuberechnung lesbar |
| zeitpunkt | datetime NOT NULL | UTC |
| benutzer_id | int NULL | NULL bei Systembuchung |
| verursacher | text NOT NULL | „user:3“, „lexware-sync“, „inventur:12“, „import:datei.csv“ |
| bemerkung | text | |
| storno_von_id | int NULL → lager_bewegungen | bei REVERSAL |
| transfer_gruppe | text NULL | verbindet TRANSFER_OUT und TRANSFER_IN |
| inventur_id | int NULL | |
| ext_quelle | text NULL | „lexware“, „csv“, „api“ … |
| ext_beleg_id | text NULL | Lexware-Beleg-UUID |
| ext_position | text NULL | Positionsschlüssel (siehe 6.4) |
| ext_aktion | text NULL | „stock_out“, „stock_out_reversal“, „return_in“ … |
| ext_version | int NULL | Belegversion bei der Buchung |

Bedingungen:
- `CHECK(menge_e4 <> 0)`
- Art und Vorzeichen passen zusammen (CHECK je Art)
- **Idempotenz:** `UNIQUE(project_id, ext_quelle, ext_beleg_id, ext_position, ext_aktion, ext_version)`. SQLite
  behandelt NULL-Werte als verschieden, deshalb greift der Index nur für externe Buchungen, wie gewollt.
- **Unveränderlichkeit auf DB-Ebene:** Trigger `BEFORE UPDATE` und `BEFORE DELETE` auf `lager_bewegungen` mit
  `RAISE(ABORT, 'Lagerbewegungen sind unveränderlich')`. Damit schützt sich die Tabelle auch gegen Code, der sie
  versehentlich anfasst.

Indizes:
- `(project_id, artikel_id, zeitpunkt)`
- `(project_id, zeitpunkt)`
- `(project_id, art, zeitpunkt)`
- `(project_id, ext_quelle, ext_beleg_id)`
- `(project_id, benutzer_id, zeitpunkt)`

**`lager_bestand`**: der materialisierte aktuelle Bestand (Begründung in 5.1)
- Spalten: `project_id`, `artikel_id`, `lagerort_id`, `menge_e4`, `letzte_bewegung_id`, `aktualisiert_am`
- Primärschlüssel: `PK(artikel_id, lagerort_id)`
- Index: `(project_id, lagerort_id)`
- Wird **ausschließlich** vom Buchungsservice geschrieben, in derselben Transaktion wie die Bewegung.

**`lager_inventuren`** und **`lager_inventur_positionen`**
- Kopf: `id`, `project_id`, `lagerort_id`, `name`, `stichtag`, `status` (offen, abgeschlossen, verworfen),
  `protokoll` (JSON: Verlauf mit Zeit und Person), `erstellt_von`/`_am`, `abgeschlossen_von`/`_am`
- Position: `id`, `inventur_id`, `artikel_id`, `sku`/`name` (Momentaufnahme), `soll_e4` (eingefroren beim Start),
  `ist_e4 NULL`, `differenz_e4`, `grund`, `gezaehlt_von`/`_am`, `korrektur_bewegung_id`
- `UNIQUE(inventur_id, artikel_id)`
- Ist die Inventur abgeschlossen, verweigern **Trigger** jede Änderung an Kopf und Positionen (gleiches Muster wie
  bei den Bewegungen).

**`lager_fremdzuordnung`**: ExternalMapping, unabhängig vom Anbieter
- Spalten: `id`, `project_id`, `system` („lexware“, „shopware“, „jtl“, „api“ …), `fremd_typ` („artikel“,
  „freitext“), `fremd_id` (Lexware-Artikel-UUID bzw. normalisierter Positionstext), `fremd_nummer` (Artikelnummer
  zur Anzeige), `fremd_name`, `artikel_id NULL`, `ignorieren` (bool), `angelegt_von`/`_am`
- `UNIQUE(project_id, system, fremd_typ, fremd_id)`
- `artikel_id` NULL und `ignorieren` false bedeuten „noch offen“; daraus entsteht eine Aufgabe.

**`lager_eingang`**: Eingangskorb für externe Ereignisse (Webhook oder Abruf)
- Spalten: `id`, `project_id`, `quelle`, `ressource` („invoice“, „credit-note“, „delivery-note“ …), `ressource_id`,
  `version`, `ereignis`, `empfangen_am`, `status` (neu, verarbeitet, warten, fehler, ignoriert), `versuche`,
  `naechster_versuch`, `fehler`, `rohdaten` (JSON, gekürzt)
- `UNIQUE(project_id, quelle, ressource, ressource_id, version)`: Ein doppelter Webhook bzw. ein doppelter Abruf wird
  hier schon verworfen.

**`lager_aufgaben`**
- Spalten: `id`, `project_id`, `typ` (position_unzugeordnet, warenausgang_bestaetigen, retoure_pruefen,
  beleg_fehler …), `status` (offen, erledigt, ignoriert), `bezug` (JSON: Beleg, Position, Menge, Name), `erledigt_von`/`_am`,
  `ergebnis`
- Eine offene Aufgabe gibt es je (typ, Beleg, Position) nur einmal: partieller UNIQUE-Index mit `WHERE status='offen'`.

**`lager_einstellungen`**: eine Zeile je Projekt
- `negativer_bestand_erlaubt` (Standard false)
- `buchungsstrategie` (Abschnitt 6.3)
- `gutschrift_als_retoure` (Standard: aus, siehe Abschnitt 6.3)
- `lexware_key_enc`
- `lexware_abruf_cron`
- `lexware_aktiv_seit` (Datum, ab dem Belege zählen; Altbelege werden nicht nachgebucht)

**`lager_rollen`**: `project_id`, `user_id`, `rolle` (ADMIN, WAREHOUSE_MANAGER, WAREHOUSE_USER, VIEWER),
`UNIQUE(project_id, user_id)`

**`lager_audit`**: Änderungsprotokoll für Stammdaten und Einstellungen
- Spalten: `id`, `project_id`, `zeitpunkt`, `benutzer_id`, `objekt` („artikel:17“), `aktion`, `vorher` (JSON),
  `nachher` (JSON)
- Nur Einfügen, gleicher Trigger-Schutz wie bei den Bewegungen.
- Die Bewegungen sind selbst das Audit des Bestands. Für Artikel, Zuordnungen, Einstellungen und Rollen braucht es
  dieses Protokoll.

### 3.2 Beziehungen (Kurzform)
```
Projekt ─┬─< lager_artikel ─┬─< lager_bewegungen >─ lager_lagerorte
         │                  └─< lager_bestand     >─┘
         ├─< lager_inventuren ─< lager_inventur_positionen ─> lager_bewegungen (Korrektur)
         ├─< lager_fremdzuordnung ─> lager_artikel
         ├─< lager_eingang ─> (erzeugt) lager_bewegungen | lager_aufgaben
         ├─1 lager_einstellungen
         └─< lager_rollen >─ users
```

### 3.3 Migrationen
**[F]** Datenmonster hat kein Alembic. Tabellen entstehen über `create_all` (idempotent), Änderungen über eine
ALTER-Liste in `main.py` mit `try/except: pass`.
**[E]** Einen Alembic-Umstieg nur für Lagermonster würde ich nicht machen: Er wäre ein Fremdkörper, und das
Datenmonster-Schema hängt nicht daran. Stattdessen:
- `app/lager/schema.py` mit einer **versionierten Liste von Schema-Schritten** (`LAGER_SCHEMA = [(1, [...ddl...]), (2, [...])]`)
- Die erreichte Version steht in `system_settings` unter `lager_schema_version`.
- Beim Start läuft jeder fehlende Schritt **in einer Transaktion**. Scheitert ein Schritt, wird der Fehler **laut
  gemeldet**, nicht verschluckt.
- Trigger und partielle Indizes werden dort als DDL angelegt, weil `create_all` sie nicht abbildet.

Damit ist die Anforderung „Datenbankänderungen über Migrationen“ erfüllt, ohne den Datenmonster-Start umzubauen.

---

## 4. Mandantenkonzept [E]

**[F]** In Datenmonster ist ein Mandant eine DB-Verbindung (`is_mandant`, `MandantAuswahl`). Das passt zu
JTL-Datenbanken, die man liest. Lagermonster hält dagegen **eigene** Daten.

**Empfehlung: Mandant = Datenmonster-Projekt.**
- Ein Betrieb bekommt ein Projekt „Lager Firma X“ mit eigener Lexware-Verbindung, eigenen Lagern und eigenen
  Artikeln. Wer mehrere Firmen hat, legt mehrere Projekte an.
- Jede `lager_*`-Tabelle trägt `project_id NOT NULL`, und jede Abfrage läuft über **eine** zentrale Funktion
  `lager_kontext(project_id, user, recht)`. Sie prüft Projektzugriff, Rolle und Tarif und gibt ein Kontextobjekt
  zurück. Der Service nimmt nur dieses Objekt an, keine rohe `project_id`. Dadurch **kann man die Mandantenprüfung
  nicht vergessen**.
- Fremdschlüssel werden zusätzlich geprüft: Artikel und Lagerort einer Bewegung müssen zum selben Projekt gehören.
  Das prüft der Service, und Tests decken es ab.
- Der Mandantenwechsler von Datenmonster bleibt für Lagermonster ungenutzt.

---

## 5. Bestand, Transaktionen, Parallelität [E]

### 5.1 Bestand: berechnen oder speichern?
**Entscheidung: beides.** Die Bewegungen sind die Wahrheit. `lager_bestand` ist ein Zwischenspeicher, der **in
derselben Transaktion** wie die Bewegung geschrieben wird.

| | Nur berechnen (A) | Zusätzlich speichern (B) |
|---|---|---|
| Lesen (Dashboard, Liste, Warnung bei Mindestbestand) | SUM über das Journal, wächst mit der Zeit | ein Indexzugriff |
| Prüfung „genug Bestand?“ beim Buchen | SUM innerhalb der Sperre | eine Zeile |
| Konsistenz | immer korrekt | korrekt, solange nur der Service schreibt, deshalb Abgleich (s. u.) |
| Parallelität | man braucht trotzdem eine Sperre | man braucht dieselbe Sperre |

Für B spricht außerdem `bestand_nachher_e4` im Journal. Damit lässt sich der Verlauf ohne Rechnen zeigen.
Absicherung: Ein **Abgleich** vergleicht `lager_bestand` mit `SUM(lager_bewegungen)`. Er läuft nachts und auf Knopfdruck
in den Einstellungen. Weicht etwas ab, wird es laut gemeldet und nicht still repariert.

### 5.2 Transaktion und Sperre (SQLite)
**[F]** Datenmonster läuft als **ein** uvicorn-Prozess mit Threads. SQLite hat keine Zeilensperren, sondern immer
nur **einen Schreiber** für die ganze Datenbank. WAL und `busy_timeout` sind nicht gesetzt; es gelten die
pysqlite-Voreinstellungen (5 s Warten). Zusätzlich gibt es den Helfer `db_retry`.

Jede Buchung läuft in **genau einer Funktion** `buchen(ctx, posten[])` ab:
1. `BEGIN IMMEDIATE`. Damit holt sich die Transaktion die Schreibsperre **vor** dem Lesen. Zwei gleichzeitige
   Buchungen laufen so garantiert nacheinander, und keine liest einen veralteten Bestand.
2. Für jeden Posten: `lager_bestand` lesen und prüfen, ob `bestand + menge >= 0` gilt (sofern negativer Bestand
   verboten ist).
3. Bewegung einfügen; die UNIQUE-Bedingung fängt eine doppelte externe Buchung ab.
4. `UPDATE lager_bestand SET menge_e4 = menge_e4 + :m WHERE … AND (:neg_erlaubt OR menge_e4 + :m >= 0)` und danach
   **prüfen, dass `rowcount == 1` ist**. Das ist eine zweite Absicherung zusätzlich zur Sperre.
5. `COMMIT`. Scheitert ein Schritt, wird **alles** zurückgerollt; das gilt auch für Umbuchungen (OUT und IN) und
   Inventurabschlüsse (viele Korrekturen).

Beispiel aus dem Briefing: Bestand 5, gleichzeitig −4 und −3. Die erste Buchung bekommt die Sperre, bucht −4 und
landet bei 1. Die zweite wartet, liest 1, und −3 wird abgelehnt: „Nicht genug Bestand: 1 Stk vorhanden, 3
angefordert“. Ist negativer Bestand erlaubt, wird −2 gebucht und im Journal markiert.

**Optional, aber empfohlen: WAL-Modus** für die gesamte Datenmonster-Datenbank. Dann blockieren Leser die
Schreiber nicht mehr, und das Journal liest sich während einer Buchung weiter. Das betrifft ganz Datenmonster und
wäre ein eigener, getesteter Schritt, siehe offene Fragen. Die Backup-API von SQLite kommt mit WAL zurecht.

### 5.3 Korrekturen und Storno
- Eine Bewegung wird nie geändert. Ein Storno ist eine **REVERSAL**-Buchung mit umgekehrtem Vorzeichen und
  `storno_von_id`. Eine Bewegung lässt sich nur einmal stornieren (UNIQUE auf `storno_von_id`).
- Eine manuelle Korrektur ist eine `CORRECTION`-Buchung mit Pflichtbemerkung.

---

## 6. Lexware-Connector [E]

### 6.1 Aufbau
```
Abruf (Scheduler)  ─┐
Webhook (optional) ─┴─> lager_eingang (UNIQUE je Beleg+Version) ─> Verarbeiter ─> GET Beleg
     ─> Soll je Artikel ─> Zuordnung (lager_fremdzuordnung) ─> Differenz zum bereits Gebuchten
     ─> buchen(...) | Aufgabe
```
- **`lager/lexware/client.py`**: typisierter Client für `voucherlist`, `invoices`, `credit-notes`, `delivery-notes`
  und `articles`.
  - **Token-Bucket mit 2 Anfragen je Sekunde**
  - Wiederholung bei 429 und 5xx mit `Retry-After`, nach dem Muster aus `rest_service`
  - Timeout 30 s
  - klare Fehlerklassen (`LexwareNichtErreichbar`, `LexwareSchluesselUngueltig`, `LexwareRateLimit`)
- **Schnittstelle `BelegQuelle`** (abstrakt): `geaenderte_belege(seit)`, `beleg(id)` → neutrales Format
  `Beleg(id, typ, nummer, status, version, datum, positionen[PositionNeutral(fremd_artikel_id, text, menge, einheit)])`.
  Shopware, WooCommerce oder JTL werden später je eine weitere `BelegQuelle`. Der Verarbeiter kennt kein Lexware.
- **Abruf ist der Standardweg.** Weil Lexware nur tagesgenau filtert, gilt `updatedDateFrom = letzter Lauf − 1 Tag`.
  Belege, die sich nicht geändert haben, fallen über (Beleg-ID, Version) im Eingangskorb heraus. Der Takt ist
  einstellbar, Standard 15 min. Bei 2 Anfragen je Sekunde und einem GET je Beleg sind das rund 100 Belege in einer
  Minute, genug für kleine und mittlere Betriebe.
- **Webhook als Beschleuniger (Phase 7, optional):** nur, wenn die Installation öffentlich per HTTPS erreichbar
  ist. Er legt lediglich einen Eintrag im Eingangskorb an, antwortet sofort mit 200 und verarbeitet asynchron.
  Die Signatur (`X-Lxo-Signature`, RSA-SHA512 mit dem öffentlichen Schlüssel von Lexware) wird geprüft. Der Abruf
  läuft trotzdem weiter und fängt verlorene Ereignisse auf.

### 6.2 Zuordnung von Positionen
- **Position vom Typ `material` oder `service` mit `id`:** Die Zuordnung sucht (lexware, artikel, UUID). Kennt sie
  die UUID nicht, holt der Client einmal `GET /v1/articles/{id}`, speichert Artikelnummer und GTIN zur Anzeige und
  legt eine **Aufgabe „Nicht zugeordnete Lexware-Position“** an. Dazu gibt es einen **Vorschlag**, wenn Artikelnummer
  = SKU oder GTIN = EAN genau einen Treffer ergibt.
  - Ob ein eindeutiger Treffer automatisch übernommen wird, ist eine Einstellung. Sie ist **standardmäßig aus**
    (Grundsatz: Vorschläge starten aus).
- **Position vom Typ `custom` (ohne Bezug):** Zugeordnet wird über den normalisierten Positionstext. Bis zur
  Entscheidung gibt es ebenfalls eine Aufgabe.
- **Position vom Typ `text`:** wird übergangen, ohne Aufgabe.
- **In der Aufgabe hat der Anwender drei Möglichkeiten:**
  - vorhandenen Artikel wählen
  - neuen Artikel anlegen (vorbefüllt mit Name, Artikelnummer, GTIN und Einheit)
  - ignorieren
  Die Entscheidung wird in `lager_fremdzuordnung` gespeichert und gilt für alle künftigen Belege. Wartende Belege
  werden danach **automatisch nachverarbeitet**.
- Ein Beleg mit offenen Positionen bucht **die zugeordneten Positionen sofort** und hält die übrigen zurück
  (Status `warten`). Nichts geht verloren, nichts wird still übergangen.

### 6.3 Buchungsstrategie (einstellbar je Projekt)
| Strategie | Wann wird ausgebucht | Hinweis |
|---|---|---|
| `rechnung` (Standard) | Rechnung wird `open`/`paid` (finalisiert) | Entwürfe buchen nie |
| `lieferschein` | Lieferschein wird `open` | für Betriebe, die Lieferscheine schreiben |
| `manuell` | jeder finalisierte Beleg erzeugt die Aufgabe „Warenausgang bestätigen“; erst der Klick bucht | |
| später `versand` | Versandereignis aus einer anderen Quelle, z. B. Datenmonster mit DHL/DPD | Lexware liefert keins |

**Doppelzählung ausgeschlossen:** Es zählt **genau ein** Belegtyp. Bei `rechnung` lösen Lieferscheine nie eine
Buchung aus, und umgekehrt.

**Gutschriften:** Eine Gutschrift kann eine Warenrücknahme sein oder eine reine Preisminderung, das lässt sich aus
Lexware nicht ablesen. Deshalb erzeugt sie **immer eine Aufgabe „Retoure prüfen“**, die eine Bestätigung als
Wareneingang anbietet. Automatisch gebucht wird nie, außer der Anwender schaltet es ausdrücklich ein.

### 6.4 Idempotenz und Änderungen (Kernstück)
Die Positionen haben in Lexware keine ID, und ein Beleg kann sich nachträglich ändern (zurück auf Entwurf, neue
Version). Deshalb gilt:

1. **Positionsschlüssel** = zugeordneter Lagerartikel. Mehrere Positionen desselben Artikels in einem Beleg werden
   addiert. Damit ist die Buchung unabhängig von der Reihenfolge der Positionen.
2. Je Beleg und Artikel wird **Soll** berechnet (Menge laut aktueller Belegversion, 0 bei `voided`, gelöscht oder
   zurück im Entwurf) und **Ist** (Summe der bereits gebuchten Bewegungen mit `ext_beleg_id` = Beleg).
3. Gebucht wird **nur die Differenz** Soll − Ist:
   - neue Rechnung: stock_out
   - Menge erhöht: weiterer Abgang
   - Storno: REVERSAL auf 0
4. Jede dieser Buchungen trägt (`ext_quelle`, `ext_beleg_id`, `ext_position` = Artikel-ID, `ext_aktion`,
   `ext_version`) und ist dadurch **eindeutig**.
5. **Doppelter Webhook oder doppelter Abruf:** Der Eingangskorb verwirft dieselbe Version. Kommt es dennoch zu einer
   Wiederverarbeitung, ergibt die Differenz 0, und es wird **nichts** gebucht. Laufen zwei Verarbeitungen gleichzeitig,
   serialisiert sie `BEGIN IMMEDIATE`, und der UNIQUE-Index fängt den Rest.
6. **Falsche Reihenfolge** (alte Version kommt nach neuer): Verarbeitet wird immer der **aktuelle** Stand per GET,
   nicht der Stand aus dem Ereignis. Eine veraltete Meldung löst deshalb höchstens eine Differenz von 0 aus.
7. Belege vor `lexware_aktiv_seit` werden nie gebucht, damit der Start keine Altlast ausbucht.

### 6.5 Fehler
- **Lexware nicht erreichbar:** Der Eingang bleibt `neu`, `versuche` wird hochgezählt, und der nächste Versuch folgt
  mit Backoff. Nach n Versuchen entsteht eine sichtbare Aufgabe bzw. Warnung. Eine lokale Buchung wird dadurch nie
  blockiert.
- **Schlüssel ungültig (401) oder Event `token.revoked`:** Der Abruf pausiert, und im Lagermonster-Kopf erscheint ein
  deutlicher Hinweis „Lexware-Verbindung prüfen“.
- **OAuth:** Die Schnittstelle `LexwareAnmeldung` hat die Umsetzungen `ApiKey` (jetzt) und `OAuthPartner` (später).
  Der Client kennt nur „gib mir einen gültigen Header“ und „Token abgelaufen, erneuern“. Der Test „ungültiges
  OAuth-Token“ läuft für das MVP gegen `ApiKey` (401) und gegen einen Stub der OAuth-Umsetzung.

---

## 7. Backend und REST-API [E]

Paket `backend/app/lager/`:
- `models.py`
- `schema.py` (Migrationen)
- `service/`: `buchung.py`, `artikel.py`, `inventur.py`, `zuordnung.py`, `import_csv.py`, `abgleich.py`
- `lexware/`: `client.py`, `quelle.py`, `verarbeiter.py`
- `rechte.py`
- `tarif.py`
- `api.py` (Router)

Pydantic-Schemas liegen in `lager/schemas.py`, **nicht** inline in den Routern. Das ist eine Abweichung vom
DM-Stil, bewusst gewählt.

| Methode und Pfad | Zweck | Mindestrolle |
|---|---|---|
| GET `/api/lager/{pid}/dashboard` | Kennzahlen, letzte Bewegungen | VIEWER |
| GET `/api/lager/{pid}/artikel?q=&aktiv=&unter_mindest=` | Suche/Filter, paginiert | VIEWER |
| GET `/api/lager/{pid}/artikel/scan/{code}` | Suche nach EAN/SKU/Code128 | WAREHOUSE_USER |
| POST/PUT `/api/lager/{pid}/artikel[/{id}]` | anlegen/bearbeiten (Audit) | WAREHOUSE_MANAGER |
| POST `/api/lager/{pid}/artikel/{id}/deaktivieren` | kein Delete | WAREHOUSE_MANAGER |
| POST `/api/lager/{pid}/buchungen` | WE/WA/Umbuchung/Korrektur; Body mit `client_ref` für Idempotenz aus der Oberfläche | WAREHOUSE_USER (Korrektur: MANAGER) |
| POST `/api/lager/{pid}/bewegungen/{id}/storno` | Gegenbuchung | WAREHOUSE_MANAGER |
| GET `/api/lager/{pid}/bewegungen?von=&bis=&artikel=&lager=&art=&benutzer=&quelle=` | Journal, paginiert, CSV-Export | VIEWER |
| GET `/api/lager/{pid}/nachbestellung` | unter Mindestbestand | VIEWER |
| `/api/lager/{pid}/inventuren…` | starten, zählen, abschließen, verwerfen | WAREHOUSE_MANAGER (zählen: USER) |
| `/api/lager/{pid}/aufgaben…` | Liste, zuordnen, anlegen, ignorieren, bestätigen | WAREHOUSE_MANAGER |
| `/api/lager/{pid}/import…` | CSV/Excel hochladen, Spalten zuordnen, Probelauf, Übernehmen | WAREHOUSE_MANAGER |
| `/api/lager/{pid}/lexware…` | Schlüssel setzen/prüfen, Abruf jetzt, Status | ADMIN |
| `/api/lager/{pid}/einstellungen`, `/rollen` | | ADMIN |

- **Idempotenz auch aus der Oberfläche:** Jeder Buchen-Klick schickt eine `client_ref` (UUID). Ein Doppelklick oder
  ein Netzwerk-Retry findet sie über `ext_quelle='ui'` und `ext_beleg_id=client_ref` und bucht nicht doppelt.
- **Einheitliches Fehlerformat:** `{"detail": "...", "code": "BESTAND_ZU_NIEDRIG", "daten": {...}}`. Fehler kommen
  nie mit Status 200, Pagination einheitlich als `{items, total, limit, offset}`.
- Die API ist ausdrücklich auch die **spätere Datenmonster-Integrationsschnittstelle** (Excel/Shop/REST →
  Datenmonster → Lagermonster). Im BUSINESS-Tarif kommen API-Schlüssel je Projekt dazu, statt nur Benutzer-JWT.
- Alle Pfade werden in `core/portal_zugriff.py` eingetragen, damit Portal-Nutzer (Lagerpersonal) sie erreichen.
  Die feinere Prüfung macht `rechte.py`.

## 8. Rollen und Rechte [E]

- **Zentrale Rechte-Matrix** in `lager/rechte.py`, z. B. `RECHTE = {"buchen": {USER, MANAGER, ADMIN}, …}`. Eine
  einzige Prüffunktion wird überall aufgerufen, im Zweifel wird **verweigert**.
- Woher die Rolle kommt:
  1. Datenmonster-Admin ist immer ADMIN.
  2. Sonst gilt der Eintrag in `lager_rollen`.
  3. Ohne Eintrag: Projekt-Owner → ADMIN, Editor → WAREHOUSE_MANAGER, Viewer → VIEWER, Portal-Nutzer mit
     Formularzugang → WAREHOUSE_USER.
- Lagerpersonal sind typischerweise **Portal-Nutzer**: Sie sehen nur das Lagermonster-Formular.

## 9. Tarife (Entitlements) [E]

- **Eine Datei** `lager/tarif.py`:
  ```python
  TARIFE = {
    "FREE":     {"benutzer": 1, "lager": 1, "artikel": 100, "funktionen": {"basis"}},
    "PRO":      {"benutzer": None, "lager": 1, "artikel": None,
                 "funktionen": {"basis","lexware","inventur","barcode","mindestbestand"}},
    "BUSINESS": {"benutzer": None, "lager": None, "artikel": None,
                 "funktionen": {…PRO, "mehrlager","lagerplaetze","api","automatisierung","dm_integration"}},
  }
  ```
- Genutzt wird nur `tarif.darf(ctx, "inventur")` bzw. `tarif.grenze(ctx, "artikel")`. Im übrigen Code steht keine
  einzige Zahl. Die Meldungen folgen dem Klartext-Muster aus `lizenz_gate.meldung()`, HTTP 402.
- **[?] Woher der Tarif kommt:** Naheliegend ist die Vorlagen-Berechtigung aus monstersuite
  (`/api/v1/templates/entitlements`, täglich abgeglichen, mit Übergangsfrist). Sie müsste um ein Feld `tarif`
  ergänzt werden, und das ist eine Änderung in monstersuite. Bis dahin: installiertes Template = PRO, ohne
  Template = kein Lagermonster.

## 10. Frontend [E]

Lagermonster erscheint als **ein Formular „Lagermonster“** aus dem Template, mit Reitern (`result_tabs`) und
Modul-Widgets. Es läuft in Editor und Portal ohne eigene Top-Level-Seite, gemäß dem Grundsatz „Vorhandenes nutzen“.

| Reiter | Widget | Inhalt |
|---|---|---|
| Übersicht | `lager_dashboard` | Kacheln: aktive Artikel, Bestandswert, unter Mindestbestand, WE/WA heute, letzte Bewegungen |
| Wareneingang | `lager_buchen` (modus=ein) | Scanfeld mit Autofokus → Artikel erscheint → Menge (große Tasten ±, Zahlenfeld) → **Buchen** → Feld wird geleert, Fokus zurück |
| Warenausgang | `lager_buchen` (modus=aus) | dito, Warnung bei zu wenig Bestand bzw. Sperre, wenn negativer Bestand verboten ist |
| Artikel | `lager_artikel` | Suche, Filter, Anlegen/Bearbeiten im Seitenpanel, Deaktivieren, Import-Knopf |
| Bewegungen | `lager_journal` | Filter wie gefordert, CSV-Export, Storno-Knopf (MANAGER) |
| Nachbestellung | `lager_nachbestellung` | unter Mindestbestand, Fehlmenge; Export |
| Inventur | `lager_inventur` | starten → zählen (Scan) → Soll/Ist → abschließen, mit `BestaetigenModal` |
| Aufgaben | `lager_aufgaben` | nicht zugeordnete Positionen, Bestätigungen, Retouren; die Zahl steht am Reiter |
| Einstellungen | `lager_einstellungen` | Lexware-Schlüssel, Strategie, negativer Bestand, Lager, Rollen (ADMIN) |

Scanner und Touch:
- USB- und Bluetooth-Scanner arbeiten als Tastatur. Das Scanfeld erkennt schnelle Eingabe plus Enter, sucht nach
  EAN-8, EAN-13 und SKU/Code128 und springt direkt zur Menge. Bei eindeutigem Treffer mit Standardmenge 1 bucht ein
  zweites Enter sofort.
- Große Schaltflächen, mindestens 44 px hoch. Der Kamera-Scan (PWA) kommt später und ist im Widget als zweite
  Eingabequelle vorgesehen.

Technik:
- Die Widgets liegen unter `components/forms/widgets/lager/` und werden im `WidgetRenderer` angemeldet.
- **Nur neuer Code nutzt Tailwind-Klassen und CSS-Variablen** statt Inline-Styles. Das ist lokal begrenzt und
  verändert den übrigen Datenmonster-Stil nicht.

## 11. Docker und Deployment [E]
- **Kein neuer Container.** Das Modul steckt im Backend-Image, die Widgets im Frontend-Image. Ausgeliefert wird
  über den bestehenden CI-, GHCR- und Updater-Weg.
- Die Lagerdaten liegen in der bestehenden SQLite im Volume `datenmonster-data` und sind damit automatisch in Backup
  und Wiederherstellung enthalten.
- Das Template „Lagermonster“ ist signiert und im Store erhältlich. Die Installation legt Formular, Reiter und
  Widgets an. Das Modul selbst ist immer im Image, aber ohne Berechtigung gesperrt (402).
- Der Webhook braucht einen öffentlichen HTTPS-Zugang, z. B. einen Reverse-Proxy beim Kunden. Das wird dokumentiert
  und nicht mitgeliefert.

## 12. Sicherheit [E]
- **Mandantentrennung:** Kontextobjekt statt roher `project_id`, dazu Tests, die fremde IDs verwenden.
- **Rechte:** Server-seitig, zentrale Matrix, im Zweifel verweigern, Portal-Freigabeliste.
- **Unveränderlichkeit:** Trigger auf Journal, Audit und abgeschlossene Inventuren.
- **Zugangsdaten:** Lexware-Schlüssel mit Fernet verschlüsselt, nie im Klartext in API-Antworten oder im Log.
  **[F]** `encrypt_credential` speichert im Fehlerfall Klartext. Für Lagermonster wird eine strenge Variante genutzt,
  die im Fehlerfall abbricht.
- **Webhook:** Signatur prüfen, Geheimnis in der URL, Rate-Limit, sofort 200, Verarbeitung asynchron.
- **Import:** Größenlimit, nur CSV und XLSX, keine Formeln ausführen, Probelauf vor dem Übernehmen.
- **Keine Secrets im Repository.** Tests nutzen Stubs, kein echter Lexware-Schlüssel.

## 13. Tests [E]
**[F]** Datenmonster hat kein pytest. Die Tests unter `backend/tests/` sind Skripte mit eigener `pruefe()`-Funktion.
**[E]** Für das Modul wird **pytest** eingeführt, als Dev-Abhängigkeit mit eigener `requirements-dev.txt`, damit das
Laufzeit-Image unverändert bleibt. Dazu `backend/tests/lager/` mit einer Fixture, die eine frische SQLite-Datei je
Test anlegt, plus `lager/schema.py`.

Abgedeckt werden:
- Artikel anlegen, doppelte SKU, EAN-Prüfung
- Wareneingang, Warenausgang, Umbuchung atomar
- negativer Bestand erlaubt und verboten
- **parallele Buchungen** (Threads gegen dieselbe Datei; Bestand 5, −4 und −3 → genau eine scheitert)
- Storno, doppeltes Storno, Trigger verhindern UPDATE/DELETE
- Inventur (Soll eingefroren, Korrekturbuchungen, abgeschlossen = unveränderlich)
- Mandantentrennung (fremde Artikel-ID → 404), Rollen (jede Aktion × jede Rolle, als parametrisierte Tabelle)
- Doppeltes Lexware-Ereignis, Ereignis in falscher Reihenfolge, Storno, Beleg zurück im Entwurf, Mengenänderung
- Unbekannter Artikel (Aufgabe, Beleg wartet, Nachverarbeitung nach Zuordnung), Position `custom`
- Lexware nicht erreichbar, 429 mit `Retry-After`, 401 bzw. ungültiges OAuth-Token
- Abgleich Bestand = Summe des Journals

Tests laufen mit `docker compose exec backend pytest tests/lager` und nach jeder Phase. Ein CI-Job wäre ein
sinnvoller nächster Schritt, ist aber nicht Teil des MVP.

## 14. Technische Risiken
| Risiko | Wirkung | Gegenmittel |
|---|---|---|
| SQLite hat nur einen Schreiber | Bei sehr vielen parallelen Buchungen entstehen Wartezeiten | kurze Transaktionen, `BEGIN IMMEDIATE`, optional WAL; für KMU ausreichend. Postgres wäre später möglich (Modul nutzt nur Standard-SQL), ist aber nicht Teil des MVP |
| Lexware-Positionen ohne ID oder Artikelnummer | Zuordnung braucht Handarbeit | Zuordnung merken, Vorschläge, Aufgaben |
| Rechnung wird nachträglich geändert | falscher Bestand | Diff-Buchung je Version (6.4) |
| Webhook bei Selbsthostern nicht erreichbar | Verzögerung | Abruf als Standard |
| Lexware-Limit (2 Anfragen/s, 10.000 Treffer) | langsamer Erstabgleich | `lexware_aktiv_seit`, kein Nachbuchen alter Belege |
| Inventur-Code doppelt (JTL und Lager) | zwei Implementierungen | bewusst gewählt; eine gemeinsame UI-Komponente folgt nach dem MVP |
| Tarif-Quelle in monstersuite fehlt | Tarife nicht durchsetzbar | Übergang: Template installiert = PRO |
| Mobiles Layout in DM fehlt | schlechte Bedienung am Handy | Phase 3 enthält die DM-Erweiterung „schmale Bildschirme“ |

## 15. Reihenfolge der Entwicklung
Jede Phase ist klein, einzeln testbar und endet mit grünen Tests und einem Commit.

| Phase | Inhalt | Ergebnis |
|---|---|---|
| **0** | pytest-Gerüst, `lager/schema.py`, WAL-Entscheidung | Tests laufen |
| **1** | Modelle, Buchungsservice, Bestand, Storno, Abgleich, Trigger | Kernlogik mit Tests (Parallelität, negativ, Idempotenz) |
| **2** | API, Kontext/Mandant, Rollen, Tarif, Audit, Portal-Freigabe | per API bedienbar |
| **3** | Widgets Buchen (Scan), Artikel, Bewegungen, Übersicht, Nachbestellung; mobiles Layout in DM; Template v1 | nutzbar ohne Lexware |
| **4** | CSV/Excel-Import mit Spaltenzuordnung und Probelauf | Bestand übernehmen |
| **5** | Inventur | Zählen, Soll/Ist, Korrekturen |
| **6** | Lexware: Client, Abruf, Eingangskorb, Zuordnung/Aufgaben, Strategien, Storno/Änderung | **„die Funktion, die in Lexware fehlt“** |
| **7** | Webhook (optional), Store-Veröffentlichung, Handbuch | verkaufsfertig |

Ausdrücklich **nicht** im MVP: Bestellwesen, Lieferanten, Chargen, Seriennummern, Stücklisten, Etikettendruck,
Versand, Marktplätze, Shop. Das Modell hält dafür nur die nötigen Stellen frei: `lagerplatz_id`, `BelegQuelle`,
`fremdzuordnung.system`.

## 16. Offene Fragen an den Anwender
1. **Mandant = Projekt**: Einverstanden?
2. **WAL-Modus** für die gesamte Datenmonster-Datenbank einschalten, als eigener Schritt mit Test von Backup und
   Wiederherstellung?
3. **Tarif-Quelle:** Soll monstersuite die Vorlagen-Berechtigung um `tarif` (FREE/PRO/BUSINESS) ergänzen?
   Und gibt es FREE als kostenloses Template im Store?
4. **Lagerpersonal als Portal-Nutzer:** Zählen sie im FREE-Tarif („1 Benutzer“) mit oder nicht?
   (Datenmonster zählt Portal-Zugänge heute nicht.)
5. **Standard-Buchungsstrategie:** `rechnung` oder `lieferschein`?
6. **Einheiten:** Reicht eine Einheit je Artikel, also keine Umrechnung zwischen Karton und Stück im MVP?
7. **Preise:** EK und VK nur als Information, oder soll der Bestandswert (Menge × EK) im Dashboard erscheinen?
